import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

import trustme

from client_session import ClientSession
from config import ClientConfig, ServerConfig
from file_store import FileStore
from replication import ReplicationLog
from server_runtime import ServerRuntime


def free_port():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    return port


def wait_until(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class FailoverTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.ca = trustme.CA()
        certificate = self.ca.issue_cert("localhost", "127.0.0.1")
        self.ca_path = self.base / "ca.crt"
        self.cert_path = self.base / "server.crt"
        self.key_path = self.base / "server.key"
        self.ca.cert_pem.write_to_path(self.ca_path)
        certificate.cert_chain_pems[0].write_to_path(self.cert_path)
        certificate.private_key_pem.write_to_path(self.key_path)
        self.ports = {
            name: (free_port(), free_port())
            for name in ("server1", "server2", "server3")
        }
        self.client_addresses = ",".join(
            "{}@localhost:{}".format(name, client)
            for name, (client, _) in self.ports.items()
        )
        self.runtimes = {}
        self.stores = {}

    def config(self, server_id, role, peers):
        client_port, replication_port = self.ports[server_id]
        return ServerConfig(
            host="127.0.0.1",
            port=client_port,
            replication_port=replication_port,
            files_path=str(self.base / server_id),
            tls_cert_file=str(self.cert_path),
            tls_key_file=str(self.key_path),
            tls_ca_file=str(self.ca_path),
            server_id=server_id,
            role=role,
            peers=peers,
            cluster_token="secret",
            heartbeat_interval=0.05,
            failure_timeout=0.4,
            election_timeout=0.1,
            replication_timeout=0.2,
            client_addresses=self.client_addresses,
        )

    def start(self, config):
        store = FileStore(config.files_path)
        log = ReplicationLog(
            Path(config.files_path) / ".replication.sqlite3", term=config.term
        )
        runtime = ServerRuntime(config, store, log)
        runtime.start()
        thread = threading.Thread(target=runtime.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(runtime.stop)
        self.addCleanup(store.close)
        self.runtimes[config.server_id] = runtime
        self.stores[config.server_id] = store
        return runtime

    def start_cluster(self):
        secondary2 = self.start(
            self.config(
                "server2",
                "secondary",
                "server1@localhost:{},server3@localhost:{}".format(
                    self.ports["server1"][1], self.ports["server3"][1]
                ),
            )
        )
        secondary3 = self.start(
            self.config(
                "server3",
                "secondary",
                "server1@localhost:{},server2@localhost:{}".format(
                    self.ports["server1"][1], self.ports["server2"][1]
                ),
            )
        )
        primary = self.start(
            self.config(
                "server1",
                "primary",
                "server2@localhost:{},server3@localhost:{}".format(
                    self.ports["server2"][1], self.ports["server3"][1]
                ),
            )
        )
        return primary, secondary2, secondary3

    def client_config(self):
        peers = ",".join(
            "localhost:{}".format(client)
            for client, _ in self.ports.values()
        )
        return ClientConfig(
            server="localhost",
            port=self.ports["server1"][0],
            local_path=str(self.base / "client"),
            tls_ca_file=str(self.ca_path),
            state_dir=str(self.base / "state"),
            peers=peers,
        )

    def test_failover_and_rejoin(self):
        primary, secondary2, secondary3 = self.start_cluster()
        self.assertTrue(
            wait_until(lambda: secondary2.cluster.client_endpoint() is not None)
        )
        registration = ClientSession(self.client_config())
        registration.connect()
        registration.register("alice", "password-alice")
        registration.register("bob", "password-bob")
        registration.close()
        client = ClientSession(self.client_config())
        self.addCleanup(client.close)
        client.connect_and_login("alice", "password-alice")
        client.upload("alice", "docs/before.txt", b"before")
        client.share("docs", "bob", "ro")
        self.assertTrue(
            wait_until(
                lambda: primary.store.state_hash()
                == secondary2.store.state_hash()
                == secondary3.store.state_hash()
            )
        )

        primary.stop()
        self.assertTrue(
            wait_until(
                lambda: secondary2.cluster.is_leader()
                or secondary3.cluster.is_leader(),
                timeout=5,
            )
        )
        new_leader = (
            secondary2 if secondary2.cluster.is_leader() else secondary3
        )
        other = secondary3 if new_leader is secondary2 else secondary2
        self.assertTrue(
            wait_until(
                lambda: new_leader.store.state_hash()
                == other.store.state_hash()
            )
        )
        self.assertTrue(new_leader.store.list_shares(grantee="bob"))

        listener = ClientSession(self.client_config())
        self.addCleanup(listener.close)
        listener.connect_and_login("alice", "password-alice")
        listener.subscribe("listener-client")
        notifier = ClientSession(self.client_config())
        self.addCleanup(notifier.close)
        notifier.connect_and_login("alice", "password-alice")
        notifier.upload("alice", "notify.txt", b"n", client_id="notifier-client")
        update = listener.read_notification()
        self.assertEqual((update.owner, update.path, update.op), ("alice", "notify.txt", "U"))

        client.close()
        client = ClientSession(self.client_config())
        self.addCleanup(client.close)
        client.connect_and_login("alice", "password-alice")
        client.upload("alice", "after.txt", b"after")
        self.assertTrue(
            wait_until(
                lambda: new_leader.store.stat("alice", "after.txt") is not None
            )
        )

        new_log = ReplicationLog(
            Path(primary.config.files_path) / ".replication.sqlite3"
        )
        rejoined = ServerRuntime(primary.config, primary.store, new_log)
        rejoined.start()
        thread = threading.Thread(target=rejoined.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(rejoined.stop)

        self.assertTrue(
            wait_until(
                lambda: primary.store.state_hash()
                == new_leader.store.state_hash()
            )
        )
        self.assertFalse(rejoined.cluster.is_leader())


if __name__ == "__main__":
    unittest.main()
