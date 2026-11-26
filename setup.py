"""First-run setup for Cloud File Service.

The module is intentionally dependency-light: it uses only the standard
library plus ``openssl`` (available on every supported Linux distribution)
and the project's own :mod:`config` / :mod:`file_store` helpers.
"""

from __future__ import annotations

import argparse
import ipaddress
import secrets
import socket
import subprocess
import sys
from pathlib import Path

from config import (
    ClientConfig,
    ServerConfig,
    save_client_config,
    save_server_config,
)
from file_store import FileStore
from version import __version__


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def generate_certificates(cert_dir: Path, hosts: list[str]) -> None:
    """Create a CA and a server certificate with SANs for ``hosts``."""
    cert_dir.mkdir(parents=True, exist_ok=True)
    ca_key = cert_dir / "ca.key"
    ca_cert = cert_dir / "ca.crt"
    server_key = cert_dir / "server.key"
    server_csr = cert_dir / "server.csr"
    server_cert = cert_dir / "server.crt"
    ext_file = cert_dir / "server.ext"

    subprocess.run(
        ["openssl", "genrsa", "-out", str(ca_key), "2048"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["openssl", "req", "-x509", "-new", "-nodes", "-key", str(ca_key),
         "-sha256", "-days", "3650", "-out", str(ca_cert),
         "-subj", "/CN=Cloud File Service CA",
         "-addext", "basicConstraints=critical,CA:TRUE",
         "-addext", "keyUsage=critical,keyCertSign,cRLSign",
         "-addext", "subjectKeyIdentifier=hash"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    subprocess.run(
        ["openssl", "genrsa", "-out", str(server_key), "2048"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    alt_names = []
    for i, host in enumerate(hosts, start=1):
        if _is_ip(host):
            alt_names.append("IP.{} = {}".format(i, host))
        else:
            alt_names.append("DNS.{} = {}".format(i, host))

    ext_file.write_text(
        "[req]\n"
        "distinguished_name = req_distinguished_name\n"
        "req_extensions = v3_req\n"
        "prompt = no\n"
        "[req_distinguished_name]\n"
        "CN = Cloud File Service\n"
        "[v3_req]\n"
        "keyUsage = critical, digitalSignature, keyEncipherment\n"
        "extendedKeyUsage = serverAuth, clientAuth\n"
        "basicConstraints = critical, CA:FALSE\n"
        "subjectKeyIdentifier = hash\n"
        "subjectAltName = @alt_names\n"
        "[v3_cert]\n"
        "keyUsage = critical, digitalSignature, keyEncipherment\n"
        "extendedKeyUsage = serverAuth, clientAuth\n"
        "basicConstraints = critical, CA:FALSE\n"
        "subjectKeyIdentifier = hash\n"
        "authorityKeyIdentifier = keyid,issuer\n"
        "subjectAltName = @alt_names\n"
        "[alt_names]\n" + "\n".join(alt_names) + "\n",
        encoding="utf-8",
    )

    subprocess.run(
        ["openssl", "req", "-new", "-key", str(server_key), "-out", str(server_csr),
         "-config", str(ext_file)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["openssl", "x509", "-req", "-in", str(server_csr),
         "-CA", str(ca_cert), "-CAkey", str(ca_key), "-CAcreateserial",
         "-out", str(server_cert), "-days", "825", "-sha256",
         "-extfile", str(ext_file), "-extensions", "v3_cert"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    for leftover in (server_csr, ext_file, cert_dir / "ca.srl", ca_key):
        try:
            leftover.unlink()
        except FileNotFoundError:
            pass


def _detect_host() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _admin_password(provided: str | None) -> str:
    if provided:
        return provided
    return secrets.token_urlsafe(16)


def _write_single(root: Path, hosts: list[str], args) -> str:
    root = root.resolve()
    config_dir = root / "config"
    cert_dir = root / "certs"
    data_dir = root / "data"
    state_dir = root / "state"
    logs_dir = root / "logs"
    for directory in (config_dir, cert_dir, data_dir, state_dir, logs_dir):
        directory.mkdir(parents=True, exist_ok=True)

    primary_host = hosts[0]
    generate_certificates(cert_dir, hosts)

    admin_user = args.admin_user
    admin_password = _admin_password(args.admin_password)

    server_config = ServerConfig(
        host="0.0.0.0",
        port=args.port,
        files_path=str(data_dir),
        tls_cert_file=str(cert_dir / "server.crt"),
        tls_key_file=str(cert_dir / "server.key"),
        tls_ca_file=str(cert_dir / "ca.crt"),
        registration_enabled=True,
        server_id=args.server_id,
        role="primary",
        peers="",
        primary="",
        replication_host="0.0.0.0",
        replication_port=args.replication_port,
        cluster_token=secrets.token_urlsafe(24),
        admin_enabled=True,
        admin_host="0.0.0.0",
        admin_port=args.admin_port,
        admin_addresses="{}@{}:{}".format(args.server_id, primary_host, args.admin_port),
        client_addresses="{}@{}:{}".format(args.server_id, primary_host, args.port),
        allow_admin_failover=False,
        admin_session_timeout=3600.0,
    )
    client_config = ClientConfig(
        server=primary_host,
        port=args.port,
        local_path=str(root / "client_files"),
        tls_ca_file=str(cert_dir / "ca.crt"),
        tls_server_name="",
        state_dir=str(state_dir),
        peers="",
    )

    save_server_config(config_dir / "server.toml", server_config)
    save_client_config(config_dir / "client.toml", client_config)

    # Bootstrap the admin account directly in the store.
    store = FileStore(str(data_dir))
    try:
        existing = store.get_user(admin_user)
    except Exception:
        existing = None
    if existing is None:
        store.ensure_bootstrap_user(
            admin_user, admin_password, "admin",
            created_at="1970-01-01T00:00:00+00:00",
        )
    elif args.reset_admin:
        store.set_password(admin_user, admin_password)
    store.close()

    return admin_user, admin_password, primary_host, args.port, args.admin_port


def _write_cluster(root: Path, hosts: list[str], args) -> str:
    root = root.resolve()
    cluster_dir = root / "cluster"
    cluster_dir.mkdir(parents=True, exist_ok=True)

    admin_user = args.admin_user
    admin_password = _admin_password(args.admin_password)

    # One CA and one server certificate shared by every node.
    shared_cert_dir = cluster_dir / "shared-certs"
    generate_certificates(shared_cert_dir, hosts + ["localhost", "127.0.0.1"])
    try:
        (shared_cert_dir / "ca.key").unlink()
    except FileNotFoundError:
        pass

    node_dirs = []
    for index, host in enumerate(hosts, start=1):
        node_id = "server{}".format(index)
        node_dir = cluster_dir / node_id
        cert_dir = node_dir / "certs"
        data_dir = node_dir / "data"
        logs_dir = node_dir / "logs"
        for directory in (cert_dir, data_dir, logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        for name in ("ca.crt", "server.crt", "server.key"):
            (cert_dir / name).write_bytes((shared_cert_dir / name).read_bytes())

        peers = ",".join(
            "server{}@{}:6001{}".format(j, h, j) if False else
            "server{}@{}:{}".format(j, h, 60010 + j)
            for j, h in enumerate(hosts, start=1)
            if j != index
        )
        # replication peers use the replication port (60010 + node index)
        peer_list = []
        for j, h in enumerate(hosts, start=1):
            if j == index:
                continue
            peer_list.append("server{}@{}:{}".format(j, h, 60010 + j))
        peers = ",".join(peer_list)

        client_addresses = ",".join(
            "server{}@{}:50012".format(j, h) for j, h in enumerate(hosts, start=1)
        )
        admin_addresses = ",".join(
            "server{}@{}:50080".format(j, h) for j, h in enumerate(hosts, start=1)
        )

        server_config = ServerConfig(
            host="0.0.0.0",
            port=50012,
            files_path="data",
            tls_cert_file="certs/server.crt",
            tls_key_file="certs/server.key",
            tls_ca_file="certs/ca.crt",
            registration_enabled=True,
            server_id=node_id,
            role="primary" if index == 1 else "secondary",
            peers=peers,
            primary="",
            replication_host="0.0.0.0",
            replication_port=60010 + index,
            cluster_token=secrets.token_urlsafe(24),
            admin_enabled=True,
            admin_host="0.0.0.0",
            admin_port=50080,
            admin_addresses=admin_addresses,
            allow_admin_failover=True,
            admin_session_timeout=3600.0,
            client_addresses=client_addresses,
        )
        save_server_config(node_dir / "config.toml", server_config)

        store = FileStore(str(data_dir))
        try:
            existing = store.get_user(admin_user)
        except Exception:
            existing = None
        if existing is None:
            store.ensure_bootstrap_user(
                admin_user, admin_password, "admin",
                created_at="1970-01-01T00:00:00+00:00",
            )
        elif args.reset_admin:
            store.set_password(admin_user, admin_password)
        store.close()

        node_dirs.append((index, host, node_dir))

    # Shared client config at the root.
    cert_root = root / "certs"
    cert_root.mkdir(parents=True, exist_ok=True)
    for name in ("ca.crt",):
        (cert_root / name).write_bytes((shared_cert_dir / name).read_bytes())
    client_config = ClientConfig(
        server=hosts[0],
        port=50012,
        local_path=str(root / "client_files"),
        tls_ca_file=str(cert_root / "ca.crt"),
        tls_server_name="",
        state_dir=str(root / "state"),
        peers=",".join("{}:50012".format(h) for h in hosts),
    )
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    save_client_config(config_dir / "client.toml", client_config)

    # Per-node README.
    readme = cluster_dir / "README.txt"
    lines = [
        "Cloud File Service - cluster bundle",
        "University of the Basque Country (UPV/EHU) - Distributed Systems",
        "",
        "Admin user: {}".format(admin_user),
        "Admin password: {}".format(admin_password),
        "",
        "Copy each node directory to its machine and run the server:",
        "",
    ]
    for index, host, node_dir in node_dirs:
        lines.append("  node {} -> {}:".format(index, host))
        lines.append("    scp -r {} user@{}:~/cloudfs/".format(node_dir.name, host))
        lines.append("    ssh user@{} 'cd ~/cloudfs/{} && ../cloudfs server --config config.toml'".format(
            host, node_dir.name))
        lines.append("")
    lines.append("Or copy the whole cluster/ folder to every machine and run only its node.")
    lines.append("")
    lines.append("Client (any machine):")
    lines.append("  ./cloudfs client")
    lines.append("  Panel: https://{}:50080/".format(hosts[0]))
    readme.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Clean up shared cert staging? Keep it; it is small.
    return admin_user, admin_password


def _parse_hosts(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cloudfs setup", description="Set up Cloud File Service.")
    parser.add_argument("--root", default=".", help="Target directory (default: current).")
    parser.add_argument("--cluster", default=None,
                        help="Comma-separated list of node IPs/hostnames for a replicated cluster.")
    parser.add_argument("--host", action="append", default=None,
                        help="Address (IP or hostname) to include as a certificate SAN. Repeatable.")
    parser.add_argument("--port", type=int, default=50012, help="Client port (default 50012).")
    parser.add_argument("--replication-port", type=int, default=60012, dest="replication_port")
    parser.add_argument("--admin-port", type=int, default=50080, dest="admin_port")
    parser.add_argument("--server-id", default="server1", dest="server_id")
    parser.add_argument("--admin-user", default="sar", dest="admin_user")
    parser.add_argument("--admin-password", default=None, dest="admin_password")
    parser.add_argument("--reset-admin", action="store_true", dest="reset_admin")
    parser.add_argument("--yes", action="store_true", help="Non-interactive (accept defaults).")
    args = parser.parse_args(argv)

    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)

    if args.cluster:
        hosts = _parse_hosts(args.cluster)
        if len(hosts) < 1:
            print("At least one host is required for --cluster.", file=sys.stderr)
            return 2
        admin_user, admin_password = _write_cluster(root, hosts, args)
        print("")
        print("Cluster bundle created in {}/cluster/".format(root))
        print("Admin user:     {}".format(admin_user))
        print("Admin password: {}".format(admin_password))
        print("")
        print("Copy each cluster/serverN directory to its machine and run:")
        print("  ./cloudfs server --config config.toml")
        return 0

    hosts = args.host or []
    if not hosts:
        detected = _detect_host()
        hosts = [detected, "localhost", "127.0.0.1"]
        if not args.yes:
            print("No --host given; using detected address {} plus localhost.".format(detected))
    # de-duplicate while preserving order
    seen = set()
    unique_hosts = []
    for h in hosts:
        if h not in seen:
            seen.add(h)
            unique_hosts.append(h)
    hosts = unique_hosts

    admin_user, admin_password, primary_host, port, admin_port = _write_single(
        root, hosts, args
    )

    print("")
    print("Cloud File Service {} is ready.".format(__version__))
    print("")
    print("  Root:       {}".format(root.resolve()))
    print("  Config:     {}/config/server.toml".format(root))
    print("  Data:       {}/data".format(root))
    print("  Certs:      {}/certs".format(root))
    print("")
    print("  Admin user:     {}".format(admin_user))
    print("  Admin password: {}".format(admin_password))
    print("")
    print("Start the server:")
    print("  ./cloudfs server")
    print("")
    print("Open the admin panel:")
    print("  https://{}:{}/".format(primary_host, admin_port))
    print("")
    print("Start the desktop client (another terminal):")
    print("  ./cloudfs client")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
