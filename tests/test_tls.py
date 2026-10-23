import socket
import ssl
import tempfile
import threading
import unittest
from pathlib import Path

import trustme

from tls import client_context, server_context


class TlsTests(unittest.TestCase):
    def make_certificates(self, directory, hosts=("localhost", "127.0.0.1")):
        ca = trustme.CA()
        certificate = ca.issue_cert(*hosts)
        ca_path = Path(directory) / "ca.crt"
        cert_path = Path(directory) / "server.crt"
        key_path = Path(directory) / "server.key"
        ca.cert_pem.write_to_path(ca_path)
        certificate.cert_chain_pems[0].write_to_path(cert_path)
        certificate.private_key_pem.write_to_path(key_path)
        return ca_path, cert_path, key_path

    def start_server(self, context):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def serve():
            connection, _ = listener.accept()
            try:
                with context.wrap_socket(connection, server_side=True) as tls_socket:
                    tls_socket.sendall(b"hello")
            except (OSError, ssl.SSLError):
                connection.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        self.addCleanup(listener.close)
        return port

    def test_tls_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            ca_path, cert_path, key_path = self.make_certificates(directory)
            port = self.start_server(server_context(cert_path, key_path))

            with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
                with client_context(ca_path).wrap_socket(
                    raw, server_hostname="localhost"
                ) as tls_socket:
                    self.assertEqual(tls_socket.recv(5), b"hello")

    def test_untrusted_ca_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _, cert_path, key_path = self.make_certificates(directory)
            port = self.start_server(server_context(cert_path, key_path))

            with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
                with self.assertRaises(ssl.SSLCertVerificationError):
                    client_context().wrap_socket(raw, server_hostname="localhost")

    def test_hostname_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            ca_path, cert_path, key_path = self.make_certificates(
                directory, hosts=("other.example",)
            )
            port = self.start_server(server_context(cert_path, key_path))

            with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
                with self.assertRaises(ssl.SSLCertVerificationError):
                    client_context(ca_path).wrap_socket(
                        raw, server_hostname="localhost"
                    )

    def test_plaintext_client_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _, cert_path, key_path = self.make_certificates(directory)
            port = self.start_server(server_context(cert_path, key_path))

            with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
                raw.sendall(b"USERsar\r\n")
                raw.settimeout(1)
                try:
                    received = raw.recv(1)
                except ConnectionResetError:
                    received = b""
                self.assertEqual(received, b"")


if __name__ == "__main__":
    unittest.main()
