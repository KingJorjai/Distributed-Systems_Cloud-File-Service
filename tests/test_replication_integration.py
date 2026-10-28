import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path

import trustme

from client_session import ClientSession, SyncError
from config import ClientConfig, ServerConfig
from file_store import FileStore
from replication import ReplicationLog
from server_runtime import ServerRuntime


def wait_until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class ReplicationIntegrationTests(unittest.TestCase):
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
        self.stores = []
        self.runtimes = []

    def make_config(self, server_id, role, port=0, replication_port=0, peers=""):
        return ServerConfig(
            host="127.0.0.1",
            port=port,
            files_path=str(self.base / server_id),
            tls_cert_file=str(self.cert_path),
            tls_key_file=str(self.key_path),
            tls_ca_file=str(self.ca_path),
            server_id=server_id,
            role=role,
            peers=peers,
            replication_host="127.0.0.1",
            replication_port=replication_port,
            cluster_token="secret",
            replication_timeout=1.0,
            heartbeat_interval=0.5,
            failure_timeout=5.0,
            election_timeout=2.0,
        )

    def start_runtime(self, config):
        store = FileStore(config.files_path)
        log = ReplicationLog(
            Path(config.files_path) / ".replication.sqlite3", term=config.term
        )
        runtime = ServerRuntime(config, store, log)
        runtime.start()
        thread = threading.Thread(target=runtime.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(runtime.stop)
        self.addCleanup(store.close)
        self.stores.append(store)
        self.runtimes.append(runtime)
        return runtime

    def start_cluster(self):
        secondary2 = self.start_runtime(self.make_config("server2", "secondary"))
        secondary3 = self.start_runtime(self.make_config("server3", "secondary"))
        peers = "server2@localhost:{},server3@localhost:{}".format(
            secondary2.replication_server.port,
            secondary3.replication_server.port,
        )
        primary = self.start_runtime(
            self.make_config("server1", "primary", peers=peers)
        )
        return primary, secondary2, secondary3

    def client_config(self, port):
        return ClientConfig(
            server="localhost",
            port=port,
            local_path=str(self.base / "client"),
            tls_ca_file=str(self.ca_path),
            tls_server_name="localhost",
            state_dir=str(self.base / "state"),
            peers=",".join(
                ["localhost:{}".format(port)]
                + [
                    "localhost:{}".format(runtime.port)
                    for runtime in self.runtimes
                    if runtime.port != port
                ]
            ),
        )

    def connect(self, runtime):
        session = ClientSession(self.client_config(runtime.port))
        session.connect()
        self.addCleanup(session.close)
        return session

    def test_three_replicas_converge_after_mutations(self):
        primary, secondary2, secondary3 = self.start_cluster()
        client = self.connect(primary)
        client.register("alice", "password-alice")
        client.login("alice", "password-alice")

        for index in range(20):
            for attempt in range(3):
                try:
                    client.upload("alice", "file-{}.txt".format(index), b"data")
                    break
                except SyncError as error:
                    if error.code != 13 or attempt == 2:
                        raise
                    client.close()
                    client = ClientSession(self.client_config(primary.port))
                    self.addCleanup(client.close)
                    client.connect_and_login("alice", "password-alice")
            else:
                self.fail("No primary available for file-{}".format(index))

        self.assertTrue(
            wait_until(
                lambda: primary.store.state_hash()
                == secondary2.store.state_hash()
                == secondary3.store.state_hash()
            )
        )

    def test_one_secondary_down_does_not_block(self):
        primary, secondary2, secondary3 = self.start_cluster()
        client = self.connect(primary)
        client.register("alice", "password-alice")
        client.login("alice", "password-alice")
        secondary3.stop()

        client.upload("alice", "a.txt", b"hello")

        self.assertTrue(
            wait_until(
                lambda: primary.store.state_hash()
                == secondary2.store.state_hash()
            )
        )

    def test_no_quorum_rejects_without_applying(self):
        primary, secondary2, secondary3 = self.start_cluster()
        client = self.connect(primary)
        client.register("alice", "password-alice")
        client.login("alice", "password-alice")
        secondary2.stop()
        secondary3.stop()

        with self.assertRaises(SyncError) as raised:
            client.upload("alice", "a.txt", b"hello")

        self.assertIn(raised.exception.code, {12, 13})
        self.assertIsNone(primary.store.stat("alice", "a.txt"))

    def test_prim_redirects_client_to_primary(self):
        primary, secondary2, secondary3 = self.start_cluster()
        client = self.connect(primary)
        client.register("alice", "password-alice")
        self.assertTrue(
            wait_until(lambda: secondary2.cluster.client_endpoint() is not None)
        )

        seed = self.client_config(secondary2.port)
        seed = replace(seed, peers="localhost:{}".format(secondary2.port))
        redirected = ClientSession(seed)
        self.addCleanup(redirected.close)
        redirected.connect_and_login("alice", "password-alice")
        redirected.upload("alice", "redirected.txt", b"hello")

        self.assertTrue(
            wait_until(
                lambda: primary.store.stat("alice", "redirected.txt") is not None
            )
        )

    def test_secondary_rejects_client_mutation(self):
        primary, secondary2, secondary3 = self.start_cluster()
        client = self.connect(primary)
        client.register("alice", "password-alice")
        client.login("alice", "password-alice")
        self.assertTrue(
            wait_until(lambda: secondary2.store.get_user("alice") is not None)
        )

        secondary_client = self.connect(secondary2)
        secondary_client.login("alice", "password-alice")
        with self.assertRaises(SyncError) as raised:
            secondary_client.upload("alice", "a.txt", b"hello")

        self.assertEqual(raised.exception.code, 13)


if __name__ == "__main__":
    unittest.main()
