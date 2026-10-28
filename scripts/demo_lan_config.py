#!/usr/bin/env python3
"""Generate LAN demo bundles configuration for an arbitrary server/client layout."""

from __future__ import annotations

import argparse
import secrets
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLIENT_PORT = 50012
DEFAULT_REPLICATION_PORT = 60012
DEFAULT_ADMIN_PORT = 50080


@dataclass(frozen=True)
class ServerSpec:
    server_id: str
    host: str
    client_port: int = DEFAULT_CLIENT_PORT
    replication_port: int = DEFAULT_REPLICATION_PORT
    admin_port: int = DEFAULT_ADMIN_PORT


@dataclass(frozen=True)
class ClientSpec:
    name: str
    host: str


def _port(value, label):
    try:
        port = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("{} must be an integer.".format(label)) from error
    if not 1 <= port <= 65535:
        raise ValueError("{} must be between 1 and 65535.".format(label))
    return port


def parse_server_spec(value):
    """Parse ``id@host[:client[:replication[:admin]]]``."""
    server_id, separator, rest = value.partition("@")
    if not separator or not server_id or not rest:
        raise ValueError(
            "Server must use id@host[:client[:replication[:admin]]]: {}".format(
                value
            )
        )
    parts = rest.split(":")
    if len(parts) > 4 or not parts[0]:
        raise ValueError("Invalid server address: {}".format(value))
    host = parts[0]
    ports = [DEFAULT_CLIENT_PORT, DEFAULT_REPLICATION_PORT, DEFAULT_ADMIN_PORT]
    for index, raw in enumerate(parts[1:]):
        if raw:
            ports[index] = _port(raw, "server port")
    return ServerSpec(server_id, host, ports[0], ports[1], ports[2])


def parse_client_spec(value):
    """Parse ``name@host`` (host is used by the runbook only)."""
    name, separator, host = value.partition("@")
    if not name:
        raise ValueError("Client name is empty: {}".format(value))
    if not separator:
        host = "unassigned"
    if not host:
        raise ValueError("Client host is empty: {}".format(value))
    return ClientSpec(name, host)


def parse_server_specs(values):
    servers = [parse_server_spec(value) for value in values]
    if not servers:
        raise ValueError("At least one server is required.")
    ids = set()
    client_addresses = set()
    replication_addresses = set()
    admin_addresses = set()
    for server in servers:
        if server.server_id in ids:
            raise ValueError("Duplicate server id: {}".format(server.server_id))
        ids.add(server.server_id)
        for address, kind in (
            ((server.host, server.client_port), "client"),
            ((server.host, server.replication_port), "replication"),
            ((server.host, server.admin_port), "admin"),
        ):
            target = {
                "client": client_addresses,
                "replication": replication_addresses,
                "admin": admin_addresses,
            }[kind]
            if address in target:
                raise ValueError(
                    "Duplicate {} address: {}:{}".format(kind, *address)
                )
            target.add(address)
    return servers


def parse_client_specs(values):
    clients = [parse_client_spec(value) for value in values]
    if not clients:
        raise ValueError("At least one client is required.")
    names = set()
    for client in clients:
        if client.name in names:
            raise ValueError("Duplicate client name: {}".format(client.name))
        names.add(client.name)
    return clients


def _toml_string(value):
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return '"{}"'.format(escaped)


def _server_toml(server, servers, token, registration_enabled):
    peers = ",".join(
        "{}@{}:{}".format(item.server_id, item.host, item.replication_port)
        for item in servers
        if item.server_id != server.server_id
    )
    client_addresses = ",".join(
        "{}@{}:{}".format(item.server_id, item.host, item.client_port)
        for item in servers
    )
    admin_addresses = ",".join(
        "{}@{}:{}".format(item.server_id, item.host, item.admin_port)
        for item in servers
    )
    primary = (
        ""
        if server is servers[0]
        else "{}@{}:{}".format(
            servers[0].server_id, servers[0].host, servers[0].replication_port
        )
    )
    return """[server]
host = "0.0.0.0"
port = {client_port}
files_path = "files"
tls_cert_file = "certs/server.crt"
tls_key_file = "certs/server.key"
tls_ca_file = "certs/ca.crt"
registration_enabled = {registration}
server_id = {server_id}
role = {role}
peers = {peers}
primary = {primary}
replication_host = "0.0.0.0"
replication_port = {replication_port}
cluster_token = {token}
term = 1
replication_timeout = 2.0
heartbeat_interval = 0.5
failure_timeout = 2.0
election_timeout = 1.0
client_addresses = {client_addresses}
admin_enabled = true
admin_host = "0.0.0.0"
admin_port = {admin_port}
admin_addresses = {admin_addresses}
allow_admin_failover = true
admin_session_timeout = 3600.0
""".format(
        client_port=server.client_port,
        registration="true" if registration_enabled else "false",
        server_id=_toml_string(server.server_id),
        role=_toml_string("primary" if server is servers[0] else "secondary"),
        peers=_toml_string(peers),
        primary=_toml_string(primary),
        replication_port=server.replication_port,
        token=_toml_string(token),
        client_addresses=_toml_string(client_addresses),
        admin_port=server.admin_port,
        admin_addresses=_toml_string(admin_addresses),
    )


def _client_toml(client, servers):
    seeds = ",".join(
        "{}:{}".format(server.host, server.client_port) for server in servers
    )
    return """[client]
server = {server}
port = {port}
local_path = "client_files"
tls_ca_file = "certs/ca.crt"
tls_server_name = ""
state_dir = "state"
peers = {peers}
""".format(
        server=_toml_string(servers[0].host),
        port=servers[0].client_port,
        peers=_toml_string(seeds),
    )


def _write_executable(path, content):
    path.write_text(content, encoding="utf-8")
    path.chmod(0o700)


def _copy_certificates(output, server_directories, client_directories):
    cert_dir = output / "certs"
    if not (cert_dir / "ca.crt").exists():
        return
    for directory in server_directories:
        target = directory / "certs"
        target.mkdir(parents=True, exist_ok=True)
        for name in ("ca.crt", "server.crt", "server.key"):
            destination = target / name
            destination.write_bytes((cert_dir / name).read_bytes())
            if name == "server.key":
                destination.chmod(0o600)
    for directory in client_directories:
        target = directory / "certs"
        target.mkdir(parents=True, exist_ok=True)
        (target / "ca.crt").write_bytes((cert_dir / "ca.crt").read_bytes())


def _runbook(servers, clients, admin_password, token, output, registration_enabled):
    admin_urls = "\n".join(
        "- `https://{}:{}/`".format(server.host, server.admin_port)
        for server in servers
    )
    server_rows = "\n".join(
        "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
            server.server_id,
            server.host,
            server.client_port,
            server.replication_port,
            server.admin_port,
            "primary" if server is servers[0] else "secondary",
        )
        for server in servers
    )
    client_rows = "\n".join(
        "| `{}` | `{}` |".format(client.name, client.host) for client in clients
    )
    quorum = len(servers) // 2 + 1
    return """# Cloud File Service LAN Demo

Generated layout: **{server_count} server(s), {client_count} client(s)**.

## Network

| Server | Host | Client | Replication | Admin | Role |
| --- | --- | ---: | ---: | ---: | --- |
{server_rows}

| Client | Host |
| --- | --- |
{client_rows}

Quorum for **{server_count}** server(s): **{quorum}**.

## Certificates

The generated CA and server certificate include all server hostnames/IPs.

- Copy each `server-*` directory and the server bundle to the corresponding PC.
- Copy each `client-*` directory and the GUI bundle to the corresponding client PC.
- Import `certs/ca.crt` into the browser used for the admin panel.
- Keep `server.key` on the server PCs only.

## Start a server

Set `CLOUDFS_SERVER_BUNDLE` to the extracted server bundle directory, then:

```sh
cd server-server1
./run-server.sh
```

Repeat with the corresponding generated server directory on each server PC.
Start the primary first, then the secondaries.

The bootstrap administrator password is:

```text
{admin_password}
```

The cluster token is generated in `cluster-token.txt`.

## Start a client

Set `CLOUDFS_CLIENT_GUI_BUNDLE` to the extracted GUI bundle directory, then:

```sh
cd client-alice
./run-client.sh
```

For a CLI client use:

```sh
CLOUDFS_CLIENT_BUNDLE=/path/to/cloud-file-client ./run-client-cli.sh
```

The generated client configurations use relative paths, so run each script from
its generated directory.

## Admin panel

{admin_urls}

Open any node, log in as `sar` or `sza`, and use the panel to create the demo
accounts listed in `demo-accounts.txt`. Registration is **{registration}**.
Mutations on a secondary redirect to the current primary; after a failover,
open the new primary or use a secondary redirect.

## Accounts

Create the accounts below in the admin panel before starting the clients:

```text
see demo-accounts.txt
```

## Network check

Run from each PC:

```sh
python scripts/demo_lan_check.py \\
  --server {server_specs}
```

The checker tests TCP, TLS, `/healthz`, and `PRIM` from the current machine.

## Firewall

Allow these ports on the server PCs from the lab subnet:

- client: {client_ports}
- replication: {replication_ports}
- admin: {admin_ports}

On Ubuntu, check `ufw`/`nft`; on Windows, check Windows Firewall.

## Failover demo

1. Open the admin panel and show the three-node status.
2. Start the two clients and synchronize a file.
3. Stop the primary server process.
4. Wait for a secondary to become primary.
5. Upload after failover.
6. Restart the old primary and verify snapshot rejoin.

## Notes

- 1 server: standalone, no failover.
- 2 servers: quorum 2; there is no failover if one node stops.
- 3 servers: recommended.
- Even server counts work but do not improve fault tolerance over the previous odd count.
- Multiple roles can share a PC; use separate generated directories and bundle instances.
""".format(
        server_count=len(servers),
        client_count=len(clients),
        server_rows=server_rows,
        client_rows=client_rows,
        quorum=quorum,
        admin_password=admin_password,
        admin_urls=admin_urls,
        registration="enabled" if registration_enabled else "disabled",
        server_specs=" ".join(
            "--server {}".format(shlex.quote(_server_argument(server)))
            for server in servers
        ),
        client_ports=", ".join(str(server.client_port) for server in servers),
        replication_ports=", ".join(
            str(server.replication_port) for server in servers
        ),
        admin_ports=", ".join(str(server.admin_port) for server in servers),
    )


def _server_argument(server):
    return "{}@{}:{}:{}:{}".format(
        server.server_id,
        server.host,
        server.client_port,
        server.replication_port,
        server.admin_port,
    )


def _generate_certificates(output, hosts):
    command = [
        sys.executable,
        str(ROOT / "scripts" / "generate_dev_cert.py"),
        "--output",
        str(output / "certs"),
    ]
    for host in hosts:
        command.extend(["--host", host])
    subprocess.run(command, check=True)


def generate_layout(output, servers, clients, token, admin_password, registration_enabled, generate_certs=True, extra_hosts=()):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "certs").mkdir(exist_ok=True)
    (output / "cluster-token.txt").write_text(token + "\n", encoding="utf-8")
    hosts = []
    for host in [server.host for server in servers] + ["localhost", "127.0.0.1"] + list(extra_hosts):
        if host not in hosts:
            hosts.append(host)
    if generate_certs:
        _generate_certificates(output, hosts)

    server_directories = []
    for index, server in enumerate(servers):
        directory = output / "server-{}".format(server.server_id)
        directory.mkdir(exist_ok=True)
        (directory / "files").mkdir(exist_ok=True)
        (directory / "config.toml").write_text(
            _server_toml(server, servers, token, registration_enabled),
            encoding="utf-8",
        )
        _write_executable(
            directory / "run-server.sh",
            """#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export CONFIG_FILE="$PWD/config.toml"
export APP_PASSWORD_SAR={password}
export APP_PASSWORD_SZA={password}
exec "${{CLOUDFS_SERVER_BUNDLE:?Set CLOUDFS_SERVER_BUNDLE to the extracted server bundle}}/cloud-file-server"
""".format(password=shlex.quote(admin_password)),
        )
        server_directories.append(directory)

    client_directories = []
    accounts = []
    for client in clients:
        directory = output / "client-{}".format(client.name)
        directory.mkdir(exist_ok=True)
        (directory / "client_files").mkdir(exist_ok=True)
        (directory / "state").mkdir(exist_ok=True)
        (directory / "config.toml").write_text(
            _client_toml(client, servers), encoding="utf-8"
        )
        _write_executable(
            directory / "run-client.sh",
            """#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec "${{CLOUDFS_CLIENT_GUI_BUNDLE:?Set CLOUDFS_CLIENT_GUI_BUNDLE to the extracted GUI bundle}}/cloud-file-client-gui" --config "$PWD/config.toml"
""",
        )
        _write_executable(
            directory / "run-client-cli.sh",
            """#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec "${{CLOUDFS_CLIENT_BUNDLE:?Set CLOUDFS_CLIENT_BUNDLE to the extracted client bundle}}/cloud-file-client" --config "$PWD/config.toml"
""",
        )
        accounts.append("{}: {}".format(client.name, secrets.token_urlsafe(12)))
        client_directories.append(directory)

    _copy_certificates(output, server_directories, client_directories)
    (output / "demo-accounts.txt").write_text(
        "Create these users in the admin panel:\n"
        + "\n".join(accounts)
        + "\n\nAdmin: sar / sza password: {}\n".format(admin_password),
        encoding="utf-8",
    )
    (output / "RUNBOOK.md").write_text(
        _runbook(
            servers,
            clients,
            admin_password,
            token,
            output,
            registration_enabled,
        ),
        encoding="utf-8",
    )
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--server",
        action="append",
        required=True,
        dest="servers",
        help="id@host[:client[:replication[:admin]]]",
    )
    parser.add_argument(
        "--client",
        action="append",
        required=True,
        dest="clients",
        help="name@host (host is for the runbook)",
    )
    parser.add_argument("--output", type=Path, default=Path("demo/lan"))
    parser.add_argument("--token", default=None)
    parser.add_argument("--admin-password", default=None)
    parser.add_argument("--extra-cert-host", action="append", default=[])
    parser.add_argument("--no-registration", action="store_true")
    parser.add_argument("--no-certs", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    try:
        servers = parse_server_specs(args.servers)
        clients = parse_client_specs(args.clients)
        output = Path(args.output)
        if output.exists() and any(output.iterdir()) and not args.force:
            raise ValueError(
                "Output directory is not empty: {} (use --force)".format(output)
            )
        token = args.token or secrets.token_urlsafe(32)
        password = args.admin_password or secrets.token_urlsafe(18)
        generate_layout(
            output,
            servers,
            clients,
            token,
            password,
            not args.no_registration,
            generate_certs=not args.no_certs,
            extra_hosts=args.extra_cert_host,
        )
    except (ValueError, subprocess.CalledProcessError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 2
    print("Generated LAN demo layout in {}".format(output))
    print("Read {}/RUNBOOK.md".format(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
