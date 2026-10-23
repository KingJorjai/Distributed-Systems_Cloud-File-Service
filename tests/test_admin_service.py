import tempfile
import threading
import unittest
from pathlib import Path

import trustme

from admin_service import AdminError, AdminService
from client_session import ClientSession, SyncError
from config import ClientConfig, ServerConfig
from file_store import FileStore
from server_runtime import ServerRuntime


class AdminServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        ca = trustme.CA()
        certificate = ca.issue_cert("localhost", "127.0.0.1")
        cert_path = self.base / "server.crt"
        key_path = self.base / "server.key"
        ca_path = self.base / "ca.crt"
        ca.cert_pem.write_to_path(ca_path)
        certificate.cert_chain_pems[0].write_to_path(cert_path)
        certificate.private_key_pem.write_to_path(key_path)

        self.store = FileStore(self.base / "files")
        self.addCleanup(self.store.close)
        self.store.create_user("admin1", "password-admin", role="admin")
        self.store.create_user("user1", "password-user")
        self.config = ServerConfig(
            host="127.0.0.1",
            port=0,
            replication_port=0,
            files_path=str(self.base / "files"),
            tls_cert_file=str(cert_path),
            tls_key_file=str(key_path),
            tls_ca_file=str(ca_path),
            admin_enabled=False,
        )
        self.runtime = ServerRuntime(self.config, self.store)
        self.runtime.start()
        self.thread = threading.Thread(
            target=self.runtime.serve_forever, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.runtime.stop)
        self.service = AdminService(self.runtime)

    def test_status_and_user_operations(self):
        self.assertTrue(self.service.status()["is_primary"])
        self.assertTrue(self.service.authenticate("admin1", "password-admin"))
        self.assertIn("user1", [user["username"] for user in self.service.users()])

        self.service.create_user("alice", "password-alice", actor="admin1")
        self.service.set_user_disabled("alice", True, "admin1")
        self.assertTrue(
            [user for user in self.service.users() if user["username"] == "alice"][0]["disabled"]
        )
        self.service.set_user_disabled("alice", False, "admin1")
        self.service.reset_password("alice", "new-password", "admin1")
        self.assertTrue(self.store.authenticate("alice", "new-password"))
        self.assertTrue(self.service.audit())

    def test_last_admin_and_self_disable_are_rejected(self):
        with self.assertRaises(AdminError):
            self.service.set_user_disabled("admin1", True, "admin1")
        with self.assertRaises(AdminError):
            self.service.set_user_disabled("admin1", True, "user1")

    def test_registration_setting_and_share_revoke(self):
        self.store.create_share("user1", "docs", "admin1", "ro")
        self.assertFalse(self.service.status()["registration_enabled"] is False)
        self.service.set_registration(False, "admin1")
        self.assertFalse(self.store.registration_enabled(True))
        self.assertEqual(len(self.service.shares()), 1)
        self.service.revoke_share("user1", "docs", "admin1", "admin1")
        self.assertEqual(self.service.shares(), [])

    def test_disabled_user_cannot_continue(self):
        client_config = ClientConfig(
            server="localhost",
            port=self.runtime.port,
            local_path=str(self.base / "client"),
            tls_ca_file=str(self.base / "ca.crt"),
            tls_server_name="localhost",
            state_dir=str(self.base / "state"),
        )
        session = ClientSession(client_config)
        self.addCleanup(session.close)
        session.connect_and_login("user1", "password-user")
        session.upload("user1", "a.txt", b"a")

        self.service.set_user_disabled("user1", True, "admin1")

        with self.assertRaises(SyncError) as raised:
            session.upload("user1", "b.txt", b"b")
        self.assertEqual(raised.exception.code, 17)

    def test_step_down_requires_configuration(self):
        with self.assertRaises(AdminError):
            self.service.step_down("admin1")


if __name__ == "__main__":
    unittest.main()
