import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from client_state import ClientState, default_state_dir
from file_store import ManifestEntry


class ClientStateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.root = self.base / "client"
        self.root.mkdir()
        self.state = ClientState(
            "alice", "localhost", 50012, self.root, self.base / "state"
        )
        self.addCleanup(self.state.close)

    def test_round_trip_file_record(self):
        entry = ManifestEntry(
            owner="alice",
            path="a.txt",
            rev=2,
            digest="abc",
            size=3,
            deleted=False,
            access="rw",
        )
        self.state.set_file(entry)

        self.assertEqual(self.state.get_file("alice", "a.txt")["rev"], 2)
        self.assertEqual(len(self.state.list_files()), 1)

    def test_outbox_survives_reopen(self):
        change_id = self.state.enqueue("upload", "alice", "a.txt")
        self.state.close()

        self.state = ClientState(
            "alice", "localhost", 50012, self.root, self.base / "state"
        )
        self.addCleanup(self.state.close)
        pending = self.state.pending()

        self.assertEqual(pending[0]["id"], change_id)
        self.state.ack(change_id)
        self.assertEqual(self.state.pending(), [])

    def test_users_are_isolated(self):
        self.state.enqueue("upload", "alice", "a.txt")
        other = ClientState(
            "bob", "localhost", 50012, self.root, self.base / "state"
        )
        self.addCleanup(other.close)

        self.assertEqual(other.pending(), [])

    def test_default_state_dir_uses_env(self):
        with patch.dict(os.environ, {"XDG_STATE_HOME": "/tmp/cloudfs-state"}):
            self.assertEqual(default_state_dir(), Path("/tmp/cloudfs-state/cloudfs"))


if __name__ == "__main__":
    unittest.main()
