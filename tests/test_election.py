import tempfile
import unittest
from pathlib import Path

from config import ServerConfig
from election import ClusterNode, Role
from file_store import FileStore
from replication import ReplicationLog


class ClusterNodeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.store = FileStore(self.base / "files")
        self.addCleanup(self.store.close)
        self.log = ReplicationLog(self.base / "replication.sqlite3")
        self.addCleanup(self.log.close)

    def make_node(self, **overrides):
        values = {
            "host": "127.0.0.1",
            "port": 50012,
            "server_id": "server1",
            "role": "primary",
            "replication_timeout": 0.1,
            "failure_timeout": 0.2,
            "election_timeout": 0.1,
            "client_addresses": (
                "server1@host1:50012,server2@host2:50012,server3@host3:50012"
            ),
        }
        values.update(overrides)
        return ClusterNode(ServerConfig(**values), self.store, self.log)

    def test_initial_primary_becomes_leader(self):
        node = self.make_node()
        node.start()
        self.addCleanup(node.stop)

        self.assertEqual(node.role, Role.Leader)
        self.assertEqual(node.client_endpoint(), ("host1", 50012))

    def test_vote_is_persisted(self):
        node = self.make_node(role="secondary")
        granted = node.handle_vote(
            {
                "term": 2,
                "candidate": "server2",
                "last_term": 0,
                "last_index": 0,
            }
        )
        denied = node.handle_vote(
            {
                "term": 2,
                "candidate": "server3",
                "last_term": 0,
                "last_index": 0,
            }
        )

        self.assertTrue(granted)
        self.assertFalse(denied)
        self.assertEqual(self.log.voted_for(), "server2")

    def test_stale_candidate_is_rejected(self):
        self.log.append(2, 1, '{"operations":[]}', committed=True)
        self.log.set_term(2)
        node = self.make_node(role="secondary")

        granted = node.handle_vote(
            {
                "term": 3,
                "candidate": "server2",
                "last_term": 1,
                "last_index": 1,
            }
        )

        self.assertFalse(granted)

    def test_higher_term_forces_follower(self):
        node = self.make_node()
        node.start()
        self.addCleanup(node.stop)
        self.assertEqual(node.role, Role.Leader)

        accepted = node.handle_hb(
            {"term": 5, "leader": "server2", "last_index": 0, "commit_index": 0}
        )

        self.assertTrue(accepted)
        self.assertEqual(node.role, Role.Follower)
        self.assertEqual(self.log.term(), 5)
        self.assertEqual(node.client_endpoint(), ("host2", 50012))

    def test_leader_steps_down_without_quorum(self):
        node = self.make_node(peers="server2@127.0.0.1:1")
        node.start()
        self.addCleanup(node.stop)
        self.assertEqual(node.role, Role.Leader)

        node._heartbeat_round()

        self.assertEqual(node.role, Role.Follower)

    def test_step_down_moves_to_follower(self):
        node = self.make_node()
        node.start()
        self.addCleanup(node.stop)
        self.assertTrue(node.step_down())
        self.assertEqual(node.role, Role.Follower)
        self.assertFalse(node.step_down())

    def test_coord_updates_leader(self):
        node = self.make_node(role="secondary")
        accepted = node.handle_coord({"term": 3, "leader": "server3"})

        self.assertTrue(accepted)
        self.assertEqual(node.role, Role.Follower)
        self.assertEqual(node.client_endpoint(), ("host3", 50012))


if __name__ == "__main__":
    unittest.main()
