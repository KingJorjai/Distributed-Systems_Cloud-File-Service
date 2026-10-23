#!/usr/bin/env python3
"""Run a local three-server, two-client failover and sharing demo."""

import argparse
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import trustme

from client_session import ClientSession
from config import ClientConfig, ServerConfig
from file_store import FileStore
from replication import ReplicationLog
from server_runtime import ServerRuntime
from sync_client import SyncWorker


def free_port():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    return port


def wait_until(predicate, timeout=8, label="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            print("  ok:", label)
            return True
        time.sleep(0.05)
    raise TimeoutError("Timed out waiting for {}.".format(label))


def start_runtime(config):
    store = FileStore(config.files_path)
    runtime = ServerRuntime(config, store)
    runtime.start()
    thread = threading.Thread(target=runtime.serve_forever, daemon=True)
    thread.start()
    return runtime, store, thread


def stop_runtime(runtime):
    runtime.stop()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    directory = tempfile.TemporaryDirectory(prefix="cloudfs-demo-")
    base = Path(directory.name)
    print("Cloud File Service demo:", base)
    runtimes = []
    stores = []
    workers = []
    restart = None
    try:
        ca = trustme.CA()
        certificate = ca.issue_cert("localhost", "127.0.0.1")
        ca_path = base / "ca.crt"
        cert_path = base / "server.crt"
        key_path = base / "server.key"
        ca.cert_pem.write_to_path(ca_path)
        certificate.cert_chain_pems[0].write_to_path(cert_path)
        certificate.private_key_pem.write_to_path(key_path)

        client_ports = {
            name: free_port() for name in ("server1", "server2", "server3")
        }
        replication_ports = {
            name: free_port() for name in ("server1", "server2", "server3")
        }
        client_addresses = ",".join(
            "{}@localhost:{}".format(name, client_ports[name])
            for name in client_ports
        )

        def config(server_id, role, peers):
            return ServerConfig(
                host="127.0.0.1",
                port=client_ports[server_id],
                replication_host="127.0.0.1",
                replication_port=replication_ports[server_id],
                files_path=str(base / server_id),
                tls_cert_file=str(cert_path),
                tls_key_file=str(key_path),
                tls_ca_file=str(ca_path),
                server_id=server_id,
                role=role,
                peers=peers,
                client_addresses=client_addresses,
                cluster_token="demo-token",
                heartbeat_interval=0.1,
                failure_timeout=0.6,
                election_timeout=0.15,
                replication_timeout=0.4,
                admin_enabled=False,
            )

        print("1. Starting secondary nodes")
        secondary2_config = config(
            "server2",
            "secondary",
            "server1@localhost:{},server3@localhost:{}".format(
                replication_ports["server1"], replication_ports["server3"]
            ),
        )
        secondary3_config = config(
            "server3",
            "secondary",
            "server1@localhost:{},server2@localhost:{}".format(
                replication_ports["server1"], replication_ports["server2"]
            ),
        )
        secondary2, store2, _ = start_runtime(secondary2_config)
        secondary3, store3, _ = start_runtime(secondary3_config)
        runtimes.extend([secondary2, secondary3])
        stores.extend([store2, store3])

        print("2. Starting primary node")
        primary_config = config(
            "server1",
            "primary",
            "server2@localhost:{},server3@localhost:{}".format(
                replication_ports["server2"], replication_ports["server3"]
            ),
        )
        primary, store1, _ = start_runtime(primary_config)
        runtimes.append(primary)
        stores.append(store1)
        wait_until(
            lambda: primary.cluster.client_endpoint() is not None,
            label="primary announces its client endpoint",
        )

        peers = ",".join(
            "localhost:{}".format(client_ports[name])
            for name in ("server1", "server2", "server3")
        )

        def client_config(username):
            return ClientConfig(
                server="localhost",
                port=client_ports["server1"],
                local_path=str(base / (username + "-files")),
                tls_ca_file=str(ca_path),
                state_dir=str(base / (username + "-state")),
                peers=peers,
            )

        print("3. Registering alice and bob")
        registration = ClientSession(client_config("alice"))
        registration.connect()
        registration.register("alice", "password-alice")
        registration.register("bob", "password-bob")
        registration.close()

        print("4. Starting two synchronization clients")
        alice_root = base / "alice-files"
        bob_root = base / "bob-files"
        alice_root.mkdir()
        bob_root.mkdir()
        alice_worker = SyncWorker(
            alice_root, client_config("alice"), "alice", "password-alice"
        )
        bob_worker = SyncWorker(
            bob_root, client_config("bob"), "bob", "password-bob"
        )
        alice_worker.start()
        bob_worker.start()
        workers.extend([alice_worker, bob_worker])

        print("5. Uploading a local file from alice")
        alice_dir = alice_root / "docs"
        alice_dir.mkdir()
        (alice_dir / "readme.txt").write_text("hello from alice\n")
        wait_until(
            lambda: store1.stat("alice", "docs/readme.txt") is not None,
            label="alice upload replicated",
        )

        print("6. Sharing docs with bob as rw")
        alice_session = ClientSession(client_config("alice"))
        alice_session.connect_and_login("alice", "password-alice")
        alice_session.share("docs", "bob", "rw")
        bob_path = bob_root / "shared" / "alice" / "docs" / "readme.txt"
        wait_until(bob_path.exists, label="bob receives the shared file")
        print("  bob local copy:", bob_path.read_bytes().decode().strip())

        print("7. Modifying the shared file from bob")
        time.sleep(2.1)
        bob_path.write_text("hello from bob\n")
        wait_until(
            lambda: store1.get("alice", "docs/readme.txt")[0]
            == b"hello from bob\n",
            label="bob change replicated to alice",
        )

        print("8. Comparing the three replicas")
        wait_until(
            lambda: store1.state_hash()
            == store2.state_hash()
            == store3.state_hash(),
            label="three replicas have the same state hash",
        )

        print("9. Stopping the primary")
        stop_runtime(primary)
        runtimes.remove(primary)
        wait_until(
            lambda: secondary2.cluster.is_leader()
            or secondary3.cluster.is_leader(),
            timeout=6,
            label="a secondary is elected",
        )
        new_leader = (
            secondary2 if secondary2.cluster.is_leader() else secondary3
        )
        print("  new primary:", new_leader.config.server_id)

        print("10. Uploading after failover")
        after = ClientSession(client_config("alice"))
        after.connect_and_login("alice", "password-alice")
        after.upload("alice", "docs/after.txt", b"after failover\n")
        wait_until(
            lambda: new_leader.store.stat("alice", "docs/after.txt") is not None,
            label="post-failover upload committed",
        )

        print("11. Restarting the old primary")
        restart_log = ReplicationLog(
            Path(primary_config.files_path) / ".replication.sqlite3"
        )
        restart = ServerRuntime(primary_config, store1, restart_log)
        restart.start()
        threading.Thread(target=restart.serve_forever, daemon=True).start()
        wait_until(
            lambda: store1.state_hash() == new_leader.store.state_hash(),
            timeout=8,
            label="old primary rejoined via snapshot",
        )
        print("12. Demo complete")
        print("  state hashes:", store1.state_hash()[:12], store2.state_hash()[:12], store3.state_hash()[:12])
        return 0
    finally:
        for worker in workers:
            try:
                worker.stop()
            except Exception:
                pass
        if restart is not None:
            try:
                restart.stop()
            except Exception:
                pass
        for runtime in list(runtimes):
            try:
                stop_runtime(runtime)
            except Exception:
                pass
        for store in stores:
            try:
                store.close()
            except Exception:
                pass
        if args.keep:
            print("Kept demo directory:", base)
            directory.cleanup = lambda: None
        else:
            directory.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
