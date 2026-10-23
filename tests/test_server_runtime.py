import hashlib
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import quote

import trustme

from config import ServerConfig
from file_store import FileStore
from server_runtime import ServerRuntime
from szasar import SocketReader
from tls import client_context


class RuntimeTestCase(unittest.TestCase):
    registration_enabled = True

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        base = Path(self.directory.name)
        self.root = base / "files"

        ca = trustme.CA()
        certificate = ca.issue_cert("localhost", "127.0.0.1")
        self.ca_path = base / "ca.crt"
        cert_path = base / "server.crt"
        key_path = base / "server.key"
        ca.cert_pem.write_to_path(self.ca_path)
        certificate.cert_chain_pems[0].write_to_path(cert_path)
        certificate.private_key_pem.write_to_path(key_path)

        self.store = FileStore(self.root)
        self.addCleanup(self.store.close)
        self.config = ServerConfig(
            host="127.0.0.1",
            port=0,
            replication_port=0,
            files_path=str(self.root),
            tls_cert_file=str(cert_path),
            tls_key_file=str(key_path),
            tls_ca_file=str(self.ca_path),
            registration_enabled=self.registration_enabled,
        )
        self.runtime = ServerRuntime(self.config, self.store)
        self.runtime.start()
        self.thread = threading.Thread(
            target=self.runtime.serve_forever, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.runtime.stop)

    def connect(self):
        raw = socket.create_connection(("127.0.0.1", self.runtime.port), timeout=5)
        return client_context(self.ca_path).wrap_socket(
            raw, server_hostname="localhost"
        )

    def command(self, sock, reader, text):
        sock.sendall((text + "\r\n").encode("ascii"))
        return reader.readline().decode("ascii")

    def register_and_login(self, sock, reader, username, password):
        response = self.command(
            sock, reader, "REGI{}?{}".format(username, quote(password, safe=""))
        )
        self.assertEqual(response, "OK")
        self.assertEqual(self.command(sock, reader, "USER" + username), "OK")
        self.assertEqual(self.command(sock, reader, "PASS" + password), "OK")

    def read_manifest(self, sock, reader):
        header = reader.readline().decode("ascii")
        self.assertTrue(header.startswith("OK"))
        count = int(header[2:])
        lines = [reader.readline().decode("ascii") for _ in range(count)]
        self.assertEqual(reader.readline(), b"END")
        return lines


class ProtocolIntegrationTests(RuntimeTestCase):
    def test_register_login_sync_stat_download(self):
        with self.connect() as sock:
            reader = SocketReader(sock)
            self.register_and_login(sock, reader, "alice", "password-alice")
            data = b"hello"
            digest = hashlib.sha256(data).hexdigest()
            response = self.command(
                sock,
                reader,
                "UPLOa.txt?size={}&rev=0&hash={}".format(len(data), digest),
            )
            self.assertEqual(response, "OK")
            sock.sendall(b"UPL2\r\n" + data)
            self.assertTrue(reader.readline().startswith(b"OK"))
            sock.sendall(b"SYNC\r\n")

            lines = self.read_manifest(sock, reader)
            self.assertEqual(len(lines), 1)
            fields = lines[0].split("\t")
            self.assertEqual(fields[0], "alice")
            self.assertEqual(fields[1], "a.txt")
            self.assertEqual(fields[2], "1")
            self.assertEqual(fields[6], "rw")

            stat = self.command(sock, reader, "STATa.txt")
            self.assertTrue(stat.startswith("OK1\t"))

            self.assertEqual(self.command(sock, reader, "DOWNa.txt"), "OK5")
            sock.sendall(b"DOW2\r\n")
            self.assertEqual(reader.readline(), b"OK")
            self.assertEqual(reader.read_exact(5), data)

    def test_duplicate_registration_is_rejected(self):
        with self.connect() as sock:
            reader = SocketReader(sock)
            self.register_and_login(sock, reader, "alice", "password-alice")

        with self.connect() as second:
            second_reader = SocketReader(second)
            response = self.command(
                second, second_reader, "REGIalice?password-alice"
            )
            self.assertEqual(response, "ER18")

    def test_registration_can_be_disabled(self):
        self.runtime.config = ServerConfig(
            host=self.config.host,
            port=self.config.port,
            files_path=self.config.files_path,
            tls_cert_file=self.config.tls_cert_file,
            tls_key_file=self.config.tls_key_file,
            tls_ca_file=self.config.tls_ca_file,
            registration_enabled=False,
        )
        with self.connect() as sock:
            reader = SocketReader(sock)
            response = self.command(sock, reader, "REGIalice?password-alice")
            self.assertEqual(response, "ER15")

    def test_anonymous_cannot_upload(self):
        with self.connect() as sock:
            reader = SocketReader(sock)
            self.assertEqual(self.command(sock, reader, "USERanonimous"), "OK")
            self.assertEqual(self.command(sock, reader, "PASS"), "OK")
            response = self.command(sock, reader, "UPLOa.txt?size=5")
            self.assertEqual(response, "ER7")

    def test_sync_manifest_uses_encoded_paths(self):
        with self.connect() as sock:
            reader = SocketReader(sock)
            self.register_and_login(sock, reader, "alice", "password-alice")
            self.assertEqual(
                self.command(sock, reader, "UPLOdir/a%20b.txt?size=1&rev=0"),
                "OK",
            )
            sock.sendall(b"UPL2\r\nx")
            self.assertTrue(reader.readline().startswith(b"OK"))
            sock.sendall(b"SYNC\r\n")

            lines = self.read_manifest(sock, reader)
            self.assertEqual(lines[0].split("\t")[1], "dir/a%20b.txt")

    def test_stale_upload_returns_conflict_path(self):
        with self.connect() as sock:
            reader = SocketReader(sock)
            self.register_and_login(sock, reader, "alice", "password-alice")
            self.assertEqual(
                self.command(sock, reader, "UPLOa.txt?size=6&rev=0"), "OK"
            )
            sock.sendall(b"UPL2\r\nserver")
            self.assertTrue(reader.readline().startswith(b"OK"))

            self.assertEqual(
                self.command(
                    sock, reader, "UPLOa.txt?size=6&rev=0&client=client-1"
                ),
                "OK",
            )
            sock.sendall(b"UPL2\r\nclient")
            response = reader.readline().decode("ascii")
            self.assertTrue(response.startswith("OK2\t"))

            conflict = response.split("\t", 1)[1]
            self.assertIn("conflict", conflict)
            self.assertEqual(self.command(sock, reader, "DOWN" + conflict), "OK6")
            sock.sendall(b"DOW2\r\n")
            self.assertEqual(reader.readline(), b"OK")
            self.assertEqual(reader.read_exact(6), b"server")

    def test_stale_delete_returns_conflict_path(self):
        with self.connect() as sock:
            reader = SocketReader(sock)
            self.register_and_login(sock, reader, "alice", "password-alice")
            self.assertEqual(
                self.command(sock, reader, "UPLOa.txt?size=6&rev=0"), "OK"
            )
            sock.sendall(b"UPL2\r\nserver")
            self.assertTrue(reader.readline().startswith(b"OK"))

            response = self.command(
                sock,
                reader,
                "DELEa.txt?rev=0&client=client-1",
            )
            self.assertTrue(response.startswith("OK2\t"))
            conflict = response.split("\t", 1)[1]
            self.assertEqual(self.command(sock, reader, "DOWN" + conflict), "OK6")
            sock.sendall(b"DOW2\r\n")
            self.assertEqual(reader.readline(), b"OK")
            self.assertEqual(reader.read_exact(6), b"server")

    def test_legacy_upload_without_revision_still_works(self):
        with self.connect() as sock:
            reader = SocketReader(sock)
            self.register_and_login(sock, reader, "alice", "password-alice")
            self.assertEqual(self.command(sock, reader, "UPLOa.txt?size=1"), "OK")
            sock.sendall(b"UPL2\r\nx")
            self.assertTrue(reader.readline().startswith(b"OK"))

    def test_share_commands_and_acl(self):
        with self.connect() as alice_sock, self.connect() as bob_sock:
            alice = SocketReader(alice_sock)
            bob = SocketReader(bob_sock)
            self.register_and_login(alice_sock, alice, "alice", "password-alice")
            self.register_and_login(bob_sock, bob, "bob", "password-bob")

            self.assertEqual(
                self.command(alice_sock, alice, "UPLOdocs/a.txt?size=1&rev=0"),
                "OK",
            )
            alice_sock.sendall(b"UPL2\r\nx")
            self.assertTrue(alice.readline().startswith(b"OK"))

            self.assertEqual(
                self.command(alice_sock, alice, "SHARdocs?bob?ro"), "OK"
            )
            alice_sock.sendall(b"SYNC\r\n")
            alice_manifest = self.read_manifest(alice_sock, alice)
            self.assertEqual(len(alice_manifest), 1)
            bob_sock.sendall(b"SYNC\r\n")
            bob_manifest = self.read_manifest(bob_sock, bob)
            self.assertEqual(len(bob_manifest), 1)
            self.assertEqual(bob_manifest[0].split("\t")[0], "alice")
            self.assertEqual(bob_manifest[0].split("\t")[6], "ro")

            response = self.command(
                bob_sock, bob, "UPLO@alice/docs/a.txt?size=1&rev=0"
            )
            self.assertTrue(response.startswith("ER"))

            self.assertEqual(self.command(alice_sock, alice, "SHARdocs?bob?rw"), "OK")
            self.assertEqual(
                self.command(
                    bob_sock, bob, "UPLO@alice/docs/b.txt?size=1&rev=0"
                ),
                "OK",
            )
            bob_sock.sendall(b"UPL2\r\ny")
            self.assertTrue(bob.readline().startswith(b"OK"))

            self.assertEqual(self.command(alice_sock, alice, "UNSHdocs?bob"), "OK")
            bob_sock.sendall(b"SYNC\r\n")
            self.assertEqual(len(self.read_manifest(bob_sock, bob)), 0)

    def test_share_to_self_is_rejected(self):
        with self.connect() as sock:
            reader = SocketReader(sock)
            self.register_and_login(sock, reader, "alice", "password-alice")
            self.assertEqual(self.command(sock, reader, "SHARa.txt?alice?rw"), "ER14")

    def test_plaintext_rejected(self):
        raw = socket.create_connection(
            ("127.0.0.1", self.runtime.port), timeout=5
        )
        with raw:
            raw.sendall(b"USERalice\r\n")
            raw.settimeout(1)
            try:
                self.assertEqual(raw.recv(1), b"")
            except ConnectionResetError:
                pass

    def test_refuses_to_start_without_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FileStore(Path(directory) / "files")
            try:
                config = ServerConfig(
                    host="127.0.0.1",
                    port=0,
                    files_path=str(Path(directory) / "files"),
                    tls_cert_file=str(Path(directory) / "missing.crt"),
                    tls_key_file=str(Path(directory) / "missing.key"),
                )
                runtime = ServerRuntime(config, store)
                try:
                    with self.assertRaises(FileNotFoundError):
                        runtime.start()
                finally:
                    runtime.stop()
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
