import os
import tempfile
import unittest
from pathlib import Path

from ipc import IpcClient, IpcServer, ipc_address, ipc_key


class IpcTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = Path(self.directory.name) / "state"
        self.address = ipc_address(self.state)
        self.key = ipc_key(self.state)

    def test_key_file_is_private_on_posix(self):
        if os.name == "nt":
            self.skipTest("mode bits are not available on Windows")
        self.assertEqual((self.state / "daemon.key").stat().st_mode & 0o777, 0o600)

    def test_request_response_round_trip(self):
        def handler(connection):
            request = connection.recv()
            connection.send({"ok": True, "echo": request["value"]})

        server = IpcServer(self.address, self.key, handler)
        server.start()
        self.addCleanup(server.close)
        client = IpcClient(self.address, self.key)
        self.addCleanup(client.close)

        self.assertEqual(client.request({"value": 7}), {"ok": True, "echo": 7})

    def test_missing_key_is_rejected(self):
        def handler(connection):
            connection.send({"ok": True})

        server = IpcServer(self.address, self.key, handler)
        server.start()
        self.addCleanup(server.close)

        with self.assertRaises(Exception):
            IpcClient(self.address, b"wrong-key")


if __name__ == "__main__":
    unittest.main()
