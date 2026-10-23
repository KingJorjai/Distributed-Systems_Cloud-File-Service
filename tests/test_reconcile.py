import tempfile
import threading
import unittest
from pathlib import Path

import trustme

from client_session import ClientSession
from client_state import ClientState
from config import ClientConfig, ServerConfig
from file_store import FileStore, ManifestEntry
from server_runtime import ServerRuntime
from sync_client import SyncWorker


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.server_root = self.base / "files"
        self.client_root = self.base / "client_files"

        ca = trustme.CA()
        certificate = ca.issue_cert("localhost", "127.0.0.1")
        self.ca_path = self.base / "ca.crt"
        cert_path = self.base / "server.crt"
        key_path = self.base / "server.key"
        ca.cert_pem.write_to_path(self.ca_path)
        certificate.cert_chain_pems[0].write_to_path(cert_path)
        certificate.private_key_pem.write_to_path(key_path)

        self.store = FileStore(self.server_root)
        self.addCleanup(self.store.close)
        self.server_config = ServerConfig(
            host="127.0.0.1",
            port=0,
            files_path=str(self.server_root),
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
        self.register_user()

    def session(self):
        session = ClientSession(self.config)
        session.connect()
        self.addCleanup(session.close)
        return session

    def register_user(self):
        session = self.session()
        session.register("alice", "password-alice")

    def login_session(self):
        session = self.session()
        session.login("alice", "password-alice")
        return session

    def start_worker(self):
        worker = SyncWorker(
            self.client_root, self.config, "alice", "password-alice"
        )
        worker.start()
        self.addCleanup(worker.stop)
        return worker

    def write_local(self, path, data):
        target = self.client_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def test_startup_uploads_local_only(self):
        self.write_local("a.txt", b"local")

        self.start_worker()

        self.assertEqual(self.store.get("alice", "a.txt")[0], b"local")

    def test_startup_downloads_remote_only(self):
        session = self.login_session()
        session.upload("alice", "remote.txt", b"remote")

        self.start_worker()

        self.assertEqual((self.client_root / "remote.txt").read_bytes(), b"remote")

    def test_startup_adopts_equal_hashes(self):
        session = self.login_session()
        session.upload("alice", "a.txt", b"same")
        self.write_local("a.txt", b"same")

        self.start_worker()

        self.assertEqual(len(self.store.manifest("alice")), 1)
        self.assertEqual(self.store.stat("alice", "a.txt").rev, 1)

    def test_startup_uploads_modified_local(self):
        session = self.login_session()
        session.upload("alice", "a.txt", b"remote")
        self.write_local("a.txt", b"local")

        self.start_worker()

        record = self.store.stat("alice", "a.txt")
        self.assertEqual(record.rev, 2)
        self.assertNotIn("conflict", record.path)

    def test_startup_downloads_modified_remote(self):
        session = self.login_session()
        session.upload("alice", "a.txt", b"one")
        self.write_local("a.txt", b"one")
        worker = self.start_worker()
        worker.stop()
        session.upload("alice", "a.txt", b"two", rev=1)

        self.start_worker()

        self.assertEqual((self.client_root / "a.txt").read_bytes(), b"two")

    def test_both_modified_creates_conflict_copy(self):
        session = self.login_session()
        session.upload("alice", "a.txt", b"remote")
        self.write_local("a.txt", b"remote")
        worker = self.start_worker()
        worker.stop()
        session.upload("alice", "a.txt", b"remote-2", rev=1)
        self.write_local("a.txt", b"local-2")

        self.start_worker()

        official = self.store.get("alice", "a.txt")[0]
        self.assertEqual(official, b"local-2")
        entries = self.store.manifest("alice")
        conflict = [entry for entry in entries if entry.path != "a.txt"]
        self.assertEqual(len(conflict), 1)
        self.assertIn("conflict", conflict[0].path)
        self.assertEqual(
            (self.client_root / conflict[0].path).read_bytes(), b"remote-2"
        )

    def test_first_run_different_content_creates_conflict(self):
        session = self.login_session()
        session.upload("alice", "a.txt", b"remote")
        self.write_local("a.txt", b"local")

        self.start_worker()

        self.assertEqual(self.store.get("alice", "a.txt")[0], b"local")
        entries = self.store.manifest("alice")
        self.assertEqual(len(entries), 2)
        self.assertTrue(any("conflict" in entry.path for entry in entries))

    def test_local_delete_propagates(self):
        self.write_local("a.txt", b"local")
        worker = self.start_worker()
        worker.stop()
        (self.client_root / "a.txt").unlink()

        self.start_worker()

        self.assertTrue(self.store.stat("alice", "a.txt").deleted)

    def test_remote_delete_removes_local_file(self):
        session = self.login_session()
        session.upload("alice", "a.txt", b"remote")
        self.write_local("a.txt", b"remote")
        worker = self.start_worker()
        worker.stop()
        session.delete("alice", "a.txt", rev=1)

        self.start_worker()

        self.assertFalse((self.client_root / "a.txt").exists())
        self.assertTrue(self.store.stat("alice", "a.txt").deleted)

    def test_local_delete_with_remote_modification_preserves_conflict(self):
        session = self.login_session()
        session.upload("alice", "a.txt", b"remote")
        self.write_local("a.txt", b"remote")
        worker = self.start_worker()
        worker.stop()
        session.upload("alice", "a.txt", b"remote-2", rev=1)
        (self.client_root / "a.txt").unlink()

        self.start_worker()

        self.assertTrue(self.store.stat("alice", "a.txt").deleted)
        entries = [
            entry for entry in self.store.manifest("alice") if not entry.deleted
        ]
        self.assertEqual(len(entries), 1)
        self.assertIn("conflict", entries[0].path)
        self.assertEqual(
            (self.client_root / entries[0].path).read_bytes(), b"remote-2"
        )

    def test_local_modification_with_remote_delete_uploads_local(self):
        session = self.login_session()
        session.upload("alice", "a.txt", b"remote")
        self.write_local("a.txt", b"remote")
        worker = self.start_worker()
        worker.stop()
        session.delete("alice", "a.txt", rev=1)
        self.write_local("a.txt", b"local-2")

        self.start_worker()

        record = self.store.stat("alice", "a.txt")
        self.assertFalse(record.deleted)
        self.assertEqual(self.store.get("alice", "a.txt")[0], b"local-2")

    def test_remote_tombstone_is_not_resurrected(self):
        session = self.login_session()
        session.upload("alice", "a.txt", b"remote")
        self.write_local("a.txt", b"remote")
        worker = self.start_worker()
        worker.stop()
        session.delete("alice", "a.txt", rev=1)
        self.start_worker().stop()

        self.start_worker()

        self.assertFalse((self.client_root / "a.txt").exists())
        self.assertTrue(self.store.stat("alice", "a.txt").deleted)

    def test_crash_after_upload_does_not_duplicate_conflict(self):
        self.write_local("a.txt", b"local")
        worker = self.start_worker()
        worker.stop()

        state = ClientState(
            "alice",
            self.config.server,
            self.config.port,
            self.client_root,
            self.config.state_dir,
        )
        state.set_file(
            ManifestEntry(
                owner="alice",
                path="a.txt",
                rev=0,
                digest="stale",
                size=5,
                deleted=False,
                access="rw",
            )
        )
        state.close()

        self.start_worker()

        self.assertEqual(len(self.store.manifest("alice")), 1)

    def test_unsynced_local_delete_is_not_sent(self):
        worker = SyncWorker(
            self.client_root, self.config, "alice", "password-alice"
        )
        self.addCleanup(worker.state.close)
        worker._remove_local_file("never-synced.txt")

        self.assertIsNone(self.store.stat("alice", "never-synced.txt"))

    def test_paths_with_spaces_are_reconciled(self):
        self.write_local("dir/a b.txt", b"space")

        self.start_worker()

        self.assertEqual(self.store.get("alice", "dir/a b.txt")[0], b"space")


if __name__ == "__main__":
    unittest.main()
