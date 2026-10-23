import tempfile
import threading
import unittest
from pathlib import Path

import trustme

from client_session import ClientSession
from config import ClientConfig, ServerConfig
from file_store import FileStore
from server_runtime import ServerRuntime


class NotificationTests(unittest.TestCase):
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

        self.config = ClientConfig(
            server="localhost",
            port=self.runtime.port,
            local_path=str(self.base / "client"),
            tls_ca_file=str(self.ca_path),
            tls_server_name="localhost",
            state_dir=str(self.base / "state"),
        )
        self.register("alice", "password-alice")
        self.register("bob", "password-bob")

    def register(self, username, password):
        session = ClientSession(self.config)
        session.connect()
        session.register(username, password)
        session.close()

    def login(self, username, password):
        session = ClientSession(self.config)
        session.connect_and_login(username, password)
        self.addCleanup(session.close)
        return session

    def subscribe(self, username, password, client_id):
        session = self.login(username, password)
        session.subscribe(client_id)
        return session

    def test_owner_other_client_receives_update(self):
        uploader = self.login("alice", "password-alice")
        listener = self.subscribe("alice", "password-alice", "alice-2")

        uploader.upload("alice", "a.txt", b"a", client_id="alice-1")

        update = listener.read_notification()
        self.assertEqual((update.owner, update.path, update.op), ("alice", "a.txt", "U"))

    def test_grantee_receives_shared_update(self):
        alice = self.login("alice", "password-alice")
        alice.upload("alice", "docs/a.txt", b"a")
        alice.share("docs", "bob", "ro")
        bob = self.subscribe("bob", "password-bob", "bob-1")

        alice.upload("alice", "docs/a.txt", b"b", rev=1, client_id="alice-1")

        update = bob.read_notification()
        self.assertEqual((update.owner, update.path, update.access), ("alice", "docs/a.txt", "ro"))

    def test_share_create_and_revoke_notify_grantee(self):
        alice = self.login("alice", "password-alice")
        alice.upload("alice", "docs/a.txt", b"a")
        bob = self.subscribe("bob", "password-bob", "bob-1")

        alice.share("docs", "bob", "rw")
        created = bob.read_notification()
        self.assertEqual(created.op, "S")

        alice.unshare("docs", "bob")
        revoked = bob.read_notification()
        self.assertEqual(revoked.op, "R")

    def test_originator_is_excluded(self):
        uploader = self.login("alice", "password-alice")
        uploader.subscribe("same-client")
        uploader.socket.settimeout(0.3)

        uploader.upload("alice", "a.txt", b"a", client_id="same-client")

        with self.assertRaises(OSError):
            uploader.read_notification()


if __name__ == "__main__":
    unittest.main()
