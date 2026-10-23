import tempfile
import threading
import time
import unittest
from pathlib import Path

import trustme

from client_session import ClientSession, SyncError
from client_state import ClientState
from config import ClientConfig, ServerConfig
from file_store import FileStore
from server_runtime import ServerRuntime
from sync_client import SyncWorker


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class ClientSessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.root = self.base / "files"
        self.client_root = self.base / "client_files"

        ca = trustme.CA()
        certificate = ca.issue_cert("localhost", "127.0.0.1")
        self.ca_path = self.base / "ca.crt"
        cert_path = self.base / "server.crt"
        key_path = self.base / "server.key"
        ca.cert_pem.write_to_path(self.ca_path)
        certificate.cert_chain_pems[0].write_to_path(cert_path)
        certificate.private_key_pem.write_to_path(key_path)

        self.store = FileStore(self.root)
        self.addCleanup(self.store.close)
        self.server_config = ServerConfig(
            host="127.0.0.1",
            port=0,
            replication_port=0,
            files_path=str(self.root),
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

        self.config = ClientConfig(
            server="localhost",
            port=self.runtime.port,
            local_path=str(self.client_root),
            tls_ca_file=str(self.ca_path),
            tls_server_name="localhost",
            state_dir=str(self.base / "state"),
        )

    def make_session(self):
        session = ClientSession(self.config)
        session.connect()
        self.addCleanup(session.close)
        return session

    def register(self, session, username="alice", password="password-alice"):
        session.register(username, password)
        session.login(username, password)

    def test_register_login_upload_sync_stat_download_delete(self):
        session = self.make_session()
        self.register(session)

        uploaded = session.upload("alice", "a.txt", b"hello")
        self.assertEqual(uploaded.rev, 1)
        self.assertIsNone(uploaded.conflict_path)
        entries = session.sync()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].path, "a.txt")
        self.assertEqual(session.stat("alice", "a.txt").size, 5)
        self.assertEqual(session.download("alice", "a.txt"), b"hello")

        deleted = session.delete("alice", "a.txt", rev=1)
        self.assertEqual(deleted.rev, 2)
        self.assertTrue(session.sync()[0].deleted)
        with self.assertRaises(SyncError):
            session.stat("alice", "a.txt")

    def test_conflict_upload_returns_conflict_path(self):
        first = self.make_session()
        self.register(first)
        first.upload("alice", "a.txt", b"server")

        second = self.make_session()
        second.login("alice", "password-alice")
        result = second.upload("alice", "a.txt", b"client", rev=0)

        self.assertEqual(result.rev, 2)
        self.assertIsNotNone(result.conflict_path)
        self.assertIn("conflict", result.conflict_path)
        self.assertEqual(
            second.download("alice", result.conflict_path), b"server"
        )

    def test_users_and_change_password(self):
        session = self.make_session()
        self.register(session)
        self.assertIn("alice", session.users())

        session.change_password("password-alice", "new-password")

        second = self.make_session()
        second.login("alice", "new-password")
        self.assertEqual(second.sync(), [])

    def test_sync_worker_uploads_existing_file(self):
        session = self.make_session()
        self.register(session)
        session.close()

        self.client_root.mkdir(parents=True, exist_ok=True)
        (self.client_root / "a.txt").write_bytes(b"hello")

        worker = SyncWorker(
            self.client_root, self.config, "alice", "password-alice"
        )
        worker.start()
        self.addCleanup(worker.stop)

        self.assertTrue(
            wait_until(lambda: self.store.stat("alice", "a.txt") is not None)
        )

    def test_outbox_is_replayed_on_startup(self):
        self.client_root.mkdir(parents=True, exist_ok=True)
        (self.client_root / "a.txt").write_bytes(b"hello")
        state = ClientState(
            "alice",
            self.config.server,
            self.config.port,
            self.client_root,
            self.config.state_dir,
        )
        change_id = state.enqueue("upload", "alice", "a.txt")
        state.close()
        self.assertIsNotNone(change_id)

        session = self.make_session()
        self.register(session)
        session.close()

        worker = SyncWorker(
            self.client_root, self.config, "alice", "password-alice"
        )
        worker.start()
        self.addCleanup(worker.stop)

        self.assertTrue(
            wait_until(lambda: self.store.stat("alice", "a.txt") is not None)
        )


if __name__ == "__main__":
    unittest.main()
