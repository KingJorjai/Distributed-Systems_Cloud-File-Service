import unittest

from replication import Peer, parse_peers


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


if __name__ == "__main__":
    unittest.main()
