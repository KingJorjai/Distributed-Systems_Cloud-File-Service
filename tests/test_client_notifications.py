import tempfile
import threading
import time
import unittest
from pathlib import Path

import trustme

from client_session import ClientSession
from config import ClientConfig, ServerConfig
from file_store import FileStore
from server_runtime import ServerRuntime
from sync_client import SyncWorker


def wait_until(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class ClientNotificationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        ca = trustme.CA()
        certificate = ca.issue_cert("localhost", "127.0.0.1")
        self.ca_path = self.base / "ca.crt"
        cert_path = self.base / "server.crt"
        key_path = self.base / "server.key"
        ca.cert_pem.write_to_path(self.ca_path)
        certificate.cert_chain_pems[0].write_to_path(cert_path)
        certificate.private_key_pem.write_to_path(key_path)

        self.store = FileStore(self.base / "files")
        self.addCleanup(self.store.close)
        self.server_config = ServerConfig(
            host="127.0.0.1",
            port=0,
            replication_port=0,
            files_path=str(self.base / "files"),
            tls_cert_file=str(cert_path),
            tls_key_file=str(key_path),
            tls_ca_file=str(self.ca_path),
        )
        self.runtime = ServerRuntime(self.server_config, self.store)
        self.runtime.start()
        self.thread = threading.Thread(
            target=self.runtime.serve_forever, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.runtime.stop)

        self.register("alice", "password-alice")
        self.register("bob", "password-bob")

    def register(self, username, password):
        session = ClientSession(self.config("alice"))
        session.connect()
        session.register(username, password)
        session.close()

    def config(self, username, root_name=None):
        return ClientConfig(
            server="localhost",
            port=self.runtime.port,
            local_path=str(self.base / (root_name or (username + "_files"))),
            tls_ca_file=str(self.ca_path),
            tls_server_name="localhost",
            state_dir=str(self.base / "state"),
        )

    def session(self, username, password):
        session = ClientSession(self.config(username))
        session.connect_and_login(username, password)
        self.addCleanup(session.close)
        return session

    def worker(self, username, password, root_name=None):
        root = root_name or (username + "_files")
        worker = SyncWorker(
            str(self.base / root),
            self.config(username, root),
            username,
            password,
        )
        worker.start()
        self.addCleanup(worker.stop)
        return worker

    def test_two_clients_same_user_notify(self):
        self.worker("alice", "password-alice", "alice_a")
        self.worker("alice", "password-alice", "alice_b")

        source = self.base / "alice_a" / "a.txt"
        target = self.base / "alice_b" / "a.txt"
        source.write_bytes(b"hello")

        self.assertTrue(
            wait_until(
                lambda: target.exists() and target.read_bytes() == b"hello"
            )
        )

    def test_shared_rw_notifications_both_ways(self):
        alice = self.session("alice", "password-alice")
        alice.upload("alice", "docs/a.txt", b"a")
        alice.share("docs", "bob", "rw")
        alice_worker = self.worker("alice", "password-alice")
        bob_worker = self.worker("bob", "password-bob")
        bob_path = self.base / "bob_files" / "shared" / "alice" / "docs" / "a.txt"
        self.assertTrue(wait_until(bob_path.exists))
        self.assertEqual(bob_path.read_bytes(), b"a")

        time.sleep(2.1)
        alice.upload("alice", "docs/a.txt", b"b", rev=1, client_id="alice-cli")
        self.assertTrue(
            wait_until(lambda: bob_path.read_bytes() == b"b")
        )

        time.sleep(2.1)
        bob_path.write_bytes(b"c")
        bob_worker.reconcile()
        alice_path = self.base / "alice_files" / "docs" / "a.txt"
        self.assertTrue(
            wait_until(lambda: alice_path.read_bytes() == b"c")
        )
        alice_worker.stop()
        bob_worker.stop()

    def test_revoked_share_notifies_and_removes_local_copy(self):
        alice = self.session("alice", "password-alice")
        alice.upload("alice", "docs/a.txt", b"a")
        alice.share("docs", "bob", "rw")
        self.worker("alice", "password-alice")
        self.worker("bob", "password-bob")
        bob_path = self.base / "bob_files" / "shared" / "alice" / "docs" / "a.txt"
        self.assertTrue(wait_until(bob_path.exists))

        alice.unshare("docs", "bob")

        self.assertTrue(wait_until(lambda: not bob_path.exists()))

    def test_offline_client_reconciles_on_restart(self):
        alice = self.session("alice", "password-alice")
        alice.upload("alice", "docs/a.txt", b"a")
        alice.share("docs", "bob", "rw")
        bob = self.worker("bob", "password-bob")
        bob_path = self.base / "bob_files" / "shared" / "alice" / "docs" / "a.txt"
        self.assertTrue(wait_until(bob_path.exists))
        bob.stop()

        alice.upload("alice", "docs/a.txt", b"b", rev=1, client_id="alice-cli")

        self.worker("bob", "password-bob")
        self.assertEqual(bob_path.read_bytes(), b"b")


if __name__ == "__main__":
    unittest.main()
