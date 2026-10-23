import tempfile
import threading
import time
import unittest
from pathlib import Path

import trustme

from config import ClientConfig, ServerConfig, save_client_config
from daemon_service import DaemonService
from file_store import FileStore
from ipc import IpcClient, ipc_address, ipc_key
from server_runtime import ServerRuntime


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class DaemonTests(unittest.TestCase):
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

        self.config_path = self.base / "config.toml"
        client = ClientConfig(
            server="localhost",
            port=self.runtime.port,
            local_path=str(self.base / "client"),
            tls_ca_file=str(self.ca_path),
            tls_server_name="localhost",
            state_dir=str(self.base / "state"),
        )
        save_client_config(self.config_path, client)
        self.service = DaemonService(self.config_path)
        self.service.start()
        self.addCleanup(self.service.stop)
        self.client = IpcClient(
            ipc_address(Path(client.state_dir)),
            ipc_key(Path(client.state_dir)),
            timeout=30,
        )
        self.addCleanup(self.client.close)

    def request(self, **message):
        return self.client.request(message)

    def test_register_login_share_and_status(self):
        self.assertFalse(self.request(action="status")["data"]["logged_in"])
        self.assertTrue(self.request(action="register", username="alice", password="password-alice")["ok"])
        self.assertTrue(self.request(action="register", username="bob", password="password-bob")["ok"])
        self.assertTrue(
            self.request(
                action="login", username="alice", password="password-alice"
            )["ok"]
        )
        status = self.request(action="status")["data"]
        self.assertTrue(status["logged_in"])
        self.assertTrue(status["running"])

        (self.base / "client" / "a.txt").write_bytes(b"hello")
        self.assertTrue(
            wait_until(lambda: self.store.stat("alice", "a.txt") is not None)
        )

        self.assertIn("alice", self.request(action="users")["data"])
        self.assertTrue(
            self.request(
                action="share", path="a.txt", grantee="bob", access="ro"
            )["ok"]
        )
        shares = self.request(action="shares")["data"]
        self.assertEqual(len(shares), 1)
        self.assertEqual(shares[0]["grantee"], "bob")

    def test_subscribe_receives_status(self):
        self.client.send({"action": "subscribe"})
        first = self.client.recv()
        self.assertTrue(first["ok"])
        other = IpcClient(
            ipc_address(Path(self.service.state_dir)),
            ipc_key(Path(self.service.state_dir)),
            timeout=30,
        )
        self.addCleanup(other.close)
        other.request(
            {"action": "register", "username": "carol", "password": "password-carol"}
        )
        other.request(
            {"action": "login", "username": "carol", "password": "password-carol"}
        )
        message = self.client.recv()
        self.assertIn(message["event"], {"worker", "status"})


if __name__ == "__main__":
    unittest.main()
