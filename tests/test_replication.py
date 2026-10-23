import base64
import hashlib
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

import trustme

from config import ServerConfig
from file_store import FileStore
from replication import (
    NoQuorumError,
    Peer,
    PeerConnection,
    ReplicationError,
    ReplicationLog,
    ReplicationServer,
    Replicator,
    parse_peers,
)


class PeerParsingTests(unittest.TestCase):
    def test_parses_multiple_peers(self):
        peers = parse_peers("server2@host2:60012, server3@host3:60013")

        self.assertEqual(
            peers,
            (
                Peer("server2", "host2", 60012),
                Peer("server3", "host3", 60013),
            ),
        )

    def test_ignores_empty_entries(self):
        self.assertEqual(parse_peers(" , "), ())

    def test_rejects_invalid_peer(self):
        with self.assertRaises(ValueError):
            parse_peers("server2-host2-60012")


class ReplicationLogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "replication.sqlite3"
        self.log = ReplicationLog(self.path)
        self.addCleanup(self.log.close)

    def test_log_survives_reopen(self):
        self.log.append(1, 1, '{"operations":[]}', committed=True)
        self.log.set_meta("commit_index", 1)
        self.log.close()

        self.log = ReplicationLog(self.path)
        self.addCleanup(self.log.close)
        self.assertEqual(self.log.last_index(), 1)
        self.assertEqual(self.log.commit_index(), 1)
        self.assertIsNotNone(self.log.get(1, 1))

    def test_log_is_idempotent(self):
        self.log.append(1, 1, '{"operations":[]}')
        self.log.append(1, 1, '{"operations":[]}')

        self.log.append(1, 1, '{"operations":[]}', committed=True)
        self.assertTrue(self.log.get(1, 1)["committed"])

    def test_truncate_removes_uncommitted_entries(self):
        self.log.append(1, 1, '{"operations":[]}')
        self.log.append(1, 2, '{"operations":[]}')
        self.log.truncate_from(1, 1)

        self.assertIsNone(self.log.get(1, 1))
        self.assertIsNone(self.log.get(1, 2))

    def test_advance_term_persists_and_clears_vote(self):
        self.log.set_voted_for("server2")
        self.log.advance_term(4)

        self.assertEqual(self.log.term(), 4)
        self.assertIsNone(self.log.voted_for())

    def test_reset_to_snapshot_index(self):
        self.log.append(1, 1, '{"operations":[]}', committed=True)
        self.log.reset_to(2, 7)

        self.assertEqual(self.log.term(), 2)
        self.assertEqual(self.log.commit_index(), 7)
        self.assertEqual(self.log.last_index(), 7)
        self.assertEqual(self.log.last_term(), 2)
        self.assertIsNone(self.log.get(1, 1))
        self.assertEqual(self.log.next_index(), 8)

    def test_committed_entries_survive_truncate(self):
        self.log.append(1, 1, '{"operations":[]}', committed=True)
        self.log.truncate_from(1, 1)

        self.assertIsNotNone(self.log.get(1, 1))


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class ReplicationServerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.ca = trustme.CA()
        certificate = self.ca.issue_cert("localhost", "127.0.0.1")
        self.ca_path = self.base / "ca.crt"
        self.cert_path = self.base / "server.crt"
        self.key_path = self.base / "server.key"
        self.ca.cert_pem.write_to_path(self.ca_path)
        certificate.cert_chain_pems[0].write_to_path(self.cert_path)
        certificate.private_key_pem.write_to_path(self.key_path)

        self.store = FileStore(self.base / "files")
        self.addCleanup(self.store.close)
        self.store.create_user("alice", "password-alice")
        self.log = ReplicationLog(self.base / "replication.sqlite3")
        self.addCleanup(self.log.close)
        self.config = ServerConfig(
            host="127.0.0.1",
            replication_host="127.0.0.1",
            replication_port=0,
            files_path=str(self.base / "files"),
            tls_cert_file=str(self.cert_path),
            tls_key_file=str(self.key_path),
            tls_ca_file=str(self.ca_path),
            server_id="server2",
            role="secondary",
            cluster_token="secret",
        )
        self.server = ReplicationServer(self.config, self.store, self.log)
        self.server.start()
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.server.stop)

        self.primary_config = ServerConfig(
            host="127.0.0.1",
            tls_cert_file=str(self.cert_path),
            tls_key_file=str(self.key_path),
            tls_ca_file=str(self.ca_path),
            server_id="server1",
            role="primary",
            cluster_token="secret",
            replication_timeout=2.0,
        )

    def peer(self, token=None):
        config = self.primary_config
        if token is not None:
            config = ServerConfig(
                host=config.host,
                tls_cert_file=config.tls_cert_file,
                tls_key_file=config.tls_key_file,
                tls_ca_file=config.tls_ca_file,
                server_id=config.server_id,
                role=config.role,
                cluster_token=token,
            )
        connection = PeerConnection(
            config, Peer("server2", "localhost", self.server.port)
        )
        connection.connect()
        return connection

    def operation(self, path, data, rev=1):
        digest = hashlib.sha256(data).hexdigest()
        return {
            "operations": [
                {
                    "kind": "file",
                    "owner": "alice",
                    "path": path,
                    "rev": rev,
                    "hash": digest,
                    "size": len(data),
                    "mtime_ns": 1,
                    "deleted": False,
                    "data_b64": base64.b64encode(data).decode("ascii"),
                }
            ]
        }

    def test_mtls_replication_round_trip(self):
        connection = self.peer()
        self.addCleanup(connection.close)
        self.assertEqual(connection.remote["id"], "server2")

        connection.send(
            {"type": "RB", "term": 1, "index": 1, "op": self.operation("a.txt", b"hello")}
        )
        self.assertEqual(connection.recv()["type"], "ACK")
        connection.send({"type": "COMMIT", "term": 1, "index": 1})
        self.assertEqual(connection.recv()["type"], "COMMITTED")

        self.assertTrue(
            wait_until(lambda: self.store.stat("alice", "a.txt") is not None)
        )
        self.assertEqual(self.store.get("alice", "a.txt")[0], b"hello")

    def test_duplicate_rb_is_idempotent(self):
        connection = self.peer()
        self.addCleanup(connection.close)
        operation = self.operation("a.txt", b"hello")

        for _ in range(2):
            connection.send(
                {"type": "RB", "term": 1, "index": 1, "op": operation}
            )
            self.assertEqual(connection.recv()["type"], "ACK")
        connection.send({"type": "COMMIT", "term": 1, "index": 1})
        self.assertEqual(connection.recv()["type"], "COMMITTED")

        self.assertEqual(self.store.stat("alice", "a.txt").rev, 1)

    def test_replication_rejects_unknown_token(self):
        with self.assertRaises(ReplicationError):
            self.peer(token="wrong")

    def test_replication_rejects_plaintext(self):
        raw = socket.create_connection(
            ("127.0.0.1", self.server.port), timeout=5
        )
        with raw:
            raw.sendall(b'{"type":"HELLO"}\r\n')
            raw.settimeout(1)
            try:
                self.assertEqual(raw.recv(1), b"")
            except ConnectionResetError:
                pass

    def test_commit_applies_in_order(self):
        connection = self.peer()
        self.addCleanup(connection.close)
        connection.send(
            {"type": "RB", "term": 1, "index": 1, "op": self.operation("a.txt", b"one")}
        )
        self.assertEqual(connection.recv()["type"], "ACK")
        connection.send(
            {"type": "RB", "term": 1, "index": 2, "op": self.operation("b.txt", b"two")}
        )
        self.assertEqual(connection.recv()["type"], "ACK")
        connection.send({"type": "COMMIT", "term": 1, "index": 2})
        self.assertEqual(connection.recv()["type"], "COMMITTED")

        self.assertEqual(self.store.get("alice", "a.txt")[0], b"one")
        self.assertEqual(self.store.get("alice", "b.txt")[0], b"two")

    def test_snapshot_replaces_secondary_state(self):
        source = FileStore(self.base / "source")
        self.addCleanup(source.close)
        source.create_user("alice", "password-alice")
        source.put("alice", "snapshot.txt", b"snapshot")
        snapshot = source.export_snapshot()
        connection = self.peer()
        self.addCleanup(connection.close)

        connection.send(
            {"type": "SNAP", "term": 1, "index": 5, "snapshot": snapshot}
        )
        self.assertEqual(connection.recv()["type"], "SNAP_OK")

        self.assertEqual(self.store.state_hash(), source.state_hash())

    def test_abort_removes_uncommitted_entry(self):
        connection = self.peer()
        self.addCleanup(connection.close)
        connection.send(
            {"type": "RB", "term": 1, "index": 1, "op": self.operation("a.txt", b"one")}
        )
        self.assertEqual(connection.recv()["type"], "ACK")
        connection.send({"type": "ABORT", "term": 1, "index": 1})
        self.assertEqual(connection.recv()["type"], "ABORTED")

        self.assertIsNone(self.store.stat("alice", "a.txt"))
        self.assertIsNone(self.log.get(1, 1))


class ReplicatorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.ca = trustme.CA()
        certificate = self.ca.issue_cert("localhost", "127.0.0.1")
        self.ca_path = self.base / "ca.crt"
        self.cert_path = self.base / "server.crt"
        self.key_path = self.base / "server.key"
        self.ca.cert_pem.write_to_path(self.ca_path)
        certificate.cert_chain_pems[0].write_to_path(self.cert_path)
        certificate.private_key_pem.write_to_path(self.key_path)
        self.servers = []
        self.stores = []

    def add_secondary(self, server_id):
        store = FileStore(self.base / server_id)
        self.addCleanup(store.close)
        store.create_user("alice", "password-alice")
        log = ReplicationLog(self.base / (server_id + ".sqlite3"))
        self.addCleanup(log.close)
        config = ServerConfig(
            host="127.0.0.1",
            replication_host="127.0.0.1",
            replication_port=0,
            files_path=str(self.base / server_id),
            tls_cert_file=str(self.cert_path),
            tls_key_file=str(self.key_path),
            tls_ca_file=str(self.ca_path),
            server_id=server_id,
            role="secondary",
            cluster_token="secret",
        )
        server = ReplicationServer(config, store, log)
        server.start()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.stop)
        self.servers.append(server)
        self.stores.append(store)
        return server.port

    def primary_config(self, ports):
        peers = ",".join(
            "server{}@localhost:{}".format(index + 2, port)
            for index, port in enumerate(ports)
        )
        return ServerConfig(
            host="127.0.0.1",
            tls_cert_file=str(self.cert_path),
            tls_key_file=str(self.key_path),
            tls_ca_file=str(self.ca_path),
            server_id="server1",
            role="primary",
            peers=peers,
            cluster_token="secret",
            replication_timeout=0.5,
        )

    def operation(self, path, data):
        digest = hashlib.sha256(data).hexdigest()
        return {
            "operations": [
                {
                    "kind": "file",
                    "owner": "alice",
                    "path": path,
                    "rev": 1,
                    "hash": digest,
                    "size": len(data),
                    "mtime_ns": 1,
                    "deleted": False,
                    "data_b64": base64.b64encode(data).decode("ascii"),
                }
            ]
        }

    def test_primary_commits_with_two_of_three(self):
        ports = [self.add_secondary("server2"), self.add_secondary("server3")]
        config = self.primary_config(ports)
        log = ReplicationLog(self.base / "primary.sqlite3")
        self.addCleanup(log.close)
        replicator = Replicator(config, log)

        index = replicator.replicate(self.operation("a.txt", b"hello"))

        self.assertEqual(index, 1)
        self.assertTrue(log.get(1, 1)["committed"])
        self.assertTrue(
            wait_until(
                lambda: all(
                    store.stat("alice", "a.txt") is not None
                    for store in self.stores
                )
            )
        )

    def test_primary_commits_with_one_secondary_down(self):
        port = self.add_secondary("server2")
        config = self.primary_config([port, 1])
        log = ReplicationLog(self.base / "primary.sqlite3")
        self.addCleanup(log.close)
        replicator = Replicator(config, log)

        replicator.replicate(self.operation("a.txt", b"hello"))

        self.assertTrue(
            wait_until(lambda: self.stores[0].stat("alice", "a.txt") is not None)
        )

    def test_primary_rejects_without_quorum(self):
        config = self.primary_config([1, 1])
        log = ReplicationLog(self.base / "primary.sqlite3")
        self.addCleanup(log.close)
        replicator = Replicator(config, log)

        with self.assertRaises(NoQuorumError):
            replicator.replicate(self.operation("a.txt", b"hello"))

        self.assertEqual(log.commit_index(), 0)
        self.assertIsNone(log.get(1, 1))


if __name__ == "__main__":
    unittest.main()
