import tempfile
import unittest
from pathlib import Path

from replication import Peer, ReplicationLog, parse_peers


class PeerParsingTests(unittest.TestCase):
    def test_parses_multiple_peers(self):
        peers = parse_peers("server2@host2:60012, server3@host3:60013")

        self.assertEqual(
            peers,
            (
                Peer("server2", "host2", 60012),
                Peer("server3", "host3", 60013),
            ),
        )

    def test_ignores_empty_entries(self):
        self.assertEqual(parse_peers(" , "), ())

    def test_rejects_invalid_peer(self):
        with self.assertRaises(ValueError):
            parse_peers("server2-host2-60012")


class ReplicationLogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "replication.sqlite3"
        self.log = ReplicationLog(self.path)
        self.addCleanup(self.log.close)

    def test_log_survives_reopen(self):
        self.log.append(1, 1, '{"operations":[]}', committed=True)
        self.log.set_meta("commit_index", 1)
        self.log.close()

        self.log = ReplicationLog(self.path)
        self.addCleanup(self.log.close)
        self.assertEqual(self.log.last_index(), 1)
        self.assertEqual(self.log.commit_index(), 1)
        self.assertIsNotNone(self.log.get(1, 1))

    def test_log_is_idempotent(self):
        self.log.append(1, 1, '{"operations":[]}')
        self.log.append(1, 1, '{"operations":[]}')

        self.log.append(1, 1, '{"operations":[]}', committed=True)
        self.assertTrue(self.log.get(1, 1)["committed"])

    def test_truncate_removes_uncommitted_entries(self):
        self.log.append(1, 1, '{"operations":[]}')
        self.log.append(1, 2, '{"operations":[]}')
        self.log.truncate_from(1, 1)

        self.assertIsNone(self.log.get(1, 1))
        self.assertIsNone(self.log.get(1, 2))

    def test_committed_entries_survive_truncate(self):
        self.log.append(1, 1, '{"operations":[]}', committed=True)
        self.log.truncate_from(1, 1)

        self.assertIsNotNone(self.log.get(1, 1))


if __name__ == "__main__":
    unittest.main()
