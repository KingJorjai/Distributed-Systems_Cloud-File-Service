import tempfile
import threading
import time
import unittest
from pathlib import Path

import trustme

from admin_service import AdminService
from config import ServerConfig
from file_store import FileStore
from server_runtime import ServerRuntime


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class AdminReplicationTests(unittest.TestCase):
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

        self.secondary_store = FileStore(self.base / "secondary")
        self.addCleanup(self.secondary_store.close)
        self.secondary_config = ServerConfig(
            host="127.0.0.1",
            port=0,
            replication_host="127.0.0.1",
            replication_port=0,
            files_path=str(self.base / "secondary"),
            tls_cert_file=str(cert_path),
            tls_key_file=str(key_path),
            tls_ca_file=str(self.ca_path),
            server_id="server2",
            role="secondary",
            cluster_token="secret",
            replication_timeout=0.5,
        )
        self.secondary = ServerRuntime(
            self.secondary_config, self.secondary_store
        )
        self.secondary.start()
        threading.Thread(
            target=self.secondary.serve_forever, daemon=True
        ).start()
        self.addCleanup(self.secondary.stop)

        self.primary_store = FileStore(self.base / "primary")
        self.addCleanup(self.primary_store.close)
        self.primary_store.create_user(
            "admin1", "password-admin", role="admin"
        )
        self.primary_config = ServerConfig(
            host="127.0.0.1",
            port=0,
            replication_port=0,
            files_path=str(self.base / "primary"),
            tls_cert_file=str(cert_path),
            tls_key_file=str(key_path),
            tls_ca_file=str(self.ca_path),
            server_id="server1",
            role="primary",
            peers="server2@localhost:{}".format(
                self.secondary.replication_server.port
            ),
            cluster_token="secret",
            replication_timeout=0.5,
        )
        self.primary = ServerRuntime(self.primary_config, self.primary_store)
        self.primary.start()
        threading.Thread(
            target=self.primary.serve_forever, daemon=True
        ).start()
        self.addCleanup(self.primary.stop)
        self.service = AdminService(self.primary)

    def test_admin_user_creation_is_replicated(self):
        self.service.create_user("alice", "password-alice", "admin1")

        self.assertTrue(
            wait_until(
                lambda: self.secondary_store.get_user("alice") is not None
            )
        )
        self.assertEqual(
            self.secondary_store.get_user("alice").role, "user"
        )


if __name__ == "__main__":
    unittest.main()
