import http.client
import re
import ssl
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode

import trustme

from config import ServerConfig
from file_store import FileStore
from server_runtime import ServerRuntime


def wait_until(predicate, timeout=20):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class AdminWebTests(unittest.TestCase):
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
        self.store.create_user("admin1", "password-admin", role="admin")
        self.store.create_user("user1", "password-user")
        self.config = ServerConfig(
            host="127.0.0.1",
            port=0,
            replication_port=0,
            files_path=str(self.base / "files"),
            tls_cert_file=str(cert_path),
            tls_key_file=str(key_path),
            tls_ca_file=str(self.ca_path),
            admin_enabled=True,
            admin_host="127.0.0.1",
            admin_port=0,
        )
        self.runtime = ServerRuntime(self.config, self.store)
        self.runtime.start()
        self.thread = threading.Thread(
            target=self.runtime.serve_forever, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.runtime.stop)
        self.port = self.runtime.admin_server.port
        self.context = ssl.create_default_context(cafile=str(self.ca_path))
        self.cookie = None
        self.csrf = None

    def request(self, method, path, body=None, headers=None, plain=False):
        connection_class = http.client.HTTPConnection if plain else http.client.HTTPSConnection
        kwargs = {"timeout": 3}
        if not plain:
            kwargs["context"] = self.context
        connection = connection_class("localhost", self.port, **kwargs)
        request_headers = dict(headers or {})
        if self.cookie:
            request_headers["Cookie"] = self.cookie
        if body is not None and "Content-Type" not in request_headers:
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        data = response.read().decode("utf-8", errors="replace")
        set_cookie = response.getheader("Set-Cookie")
        if set_cookie:
            self.cookie = set_cookie.split(";", 1)[0]
        result = (response.status, dict(response.getheaders()), data)
        connection.close()
        return result

    def login(self):
        body = urlencode({"username": "admin1", "password": "password-admin"})
        status, headers, text = self.request("POST", "/login", body)
        self.assertEqual(status, 303)
        self.assertIn("cloudfs_admin=", self.cookie or "")
        self.assertIn("HttpOnly", headers.get("Set-Cookie", ""))
        self.assertIn("SameSite=Strict", headers.get("Set-Cookie", ""))
        self.assertIn("Secure", headers.get("Set-Cookie", ""))
        status, _, page = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)

    def test_login_csrf_users_shares_settings(self):
        self.login()
        self.assertIn("admin1", self.request("GET", "/users")[2])
        body = urlencode(
            {"csrf": self.csrf, "username": "alice", "password": "password-alice"}
        )
        self.assertEqual(self.request("POST", "/users", body)[0], 303)
        self.assertTrue(self.store.get_user("alice"))

        status, _, _ = self.request(
            "POST", "/users/alice/disable", urlencode({"csrf": self.csrf})
        )
        self.assertEqual(status, 303)
        self.assertTrue(self.store.get_user("alice").disabled)

        self.store.create_share("user1", "docs", "alice", "ro")
        status, _, shares = self.request("GET", "/shares")
        self.assertIn("docs", shares)
        self.assertEqual(
            self.request(
                "POST",
                "/shares/revoke",
                urlencode(
                    {
                        "csrf": self.csrf,
                        "owner": "user1",
                        "path": "docs",
                        "grantee": "alice",
                    }
                ),
            )[0],
            303,
        )
        self.assertEqual(len(self.store.list_shares()), 0)

        self.assertEqual(
            self.request(
                "POST",
                "/settings/registration",
                urlencode({"csrf": self.csrf}),
            )[0],
            303,
        )
        self.assertFalse(self.store.registration_enabled(True))

    def test_login_requires_admin_and_csrf(self):
        body = urlencode({"username": "user1", "password": "password-user"})
        status, _, page = self.request("POST", "/login", body)
        self.assertEqual(status, 200)
        self.assertIn("Administrator role required", page)
        self.login()
        self.assertEqual(self.request("POST", "/users", "username=x")[0], 403)

    def test_plaintext_http_is_rejected(self):
        with self.assertRaises(Exception):
            self.request("GET", "/healthz", plain=True)

    def test_step_down_disabled_by_default(self):
        self.login()
        status, _, _ = self.request(
            "POST", "/admin/step-down", urlencode({"csrf": self.csrf})
        )
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
