# Configuration

The application loads its settings from `config.toml`. Copy
`config.toml.example` to `config.toml` for local changes; the file is ignored by
Git.

Configuration precedence is:

1. Explicit client command-line arguments.
2. Environment variables.
3. Values in `config.toml`.
4. Built-in defaults.

The file can be selected with `CONFIG_FILE`.

## Application file

```toml
[client]
server = "localhost"
port = 50012
local_path = "client_files"
tls_ca_file = ""
tls_server_name = ""
state_dir = ""

[server]
host = ""
port = 50012
files_path = "files"
tls_cert_file = "certs/server.crt"
tls_key_file = "certs/server.key"
tls_ca_file = "certs/ca.crt"
registration_enabled = true
max_file_size = 10485760
space_margin = 52428800
```

## Client arguments

```sh
python cli_fich.py [server [port [local_folder]]]
```

| Setting | Default | Description |
| --- | --- | --- |
| `server` | `client.server` | Server hostname or IP address. |
| `port` | `client.port` | Server TCP port. |
| `local_folder` | `client.local_path` | Folder watched by the automatic synchronizer. |

Environment variables: `CLIENT_SERVER`, `CLIENT_PORT`, `CLIENT_LOCAL_PATH`,
`CLIENT_PEERS`, `CLIENT_TLS_CA_FILE`, `CLIENT_TLS_SERVER_NAME`, and
`CLIENT_STATE_DIR`.

`CLIENT_PEERS` is a comma-separated `host:port` list used as bootstrap seeds.
The client asks `PRIM` for the current primary and redirects if necessary. Leave
`CLIENT_TLS_SERVER_NAME` empty when the endpoints use different hostnames.

- `CLIENT_TLS_CA_FILE` empty means “use the operating system CA store”. Set it
  to the generated `ca.crt` when using a development certificate.
- `CLIENT_TLS_SERVER_NAME` overrides the hostname used for certificate
  verification. Usually it is empty and the server host is used.
- `CLIENT_STATE_DIR` overrides the platform-specific state directory.

## Server settings

`serv_fich_multithread.py` uses:

| Setting | Default | Description |
| --- | --- | --- |
| `SERVER_HOST` | all interfaces | Listening address. |
| `SERVER_PORT` | `50012` | Listening TCP port. |
| `SERVER_FILES_PATH` | `files` | Root storage directory. |
| `TLS_CERT_FILE` | `certs/server.crt` | PEM server certificate. |
| `TLS_KEY_FILE` | `certs/server.key` | PEM private key. |
| `TLS_CA_FILE` | `certs/ca.crt` | CA used by replication (reserved for M3). |
| `ALLOW_REGISTRATION` | `true` | Enables `REGI`. |
| `SERVER_ID` | `server1` | Cluster identity. |
| `SERVER_ROLE` | `primary` | `primary` or `secondary`. |
| `SERVER_PEERS` | empty | Comma-separated `id@host:port` replication peers. |
| `SERVER_PRIMARY` | empty | Primary address used by a secondary. |
| `SERVER_REPLICATION_HOST` | same as host | Replication listener address. |
| `SERVER_REPLICATION_PORT` | `60012` | Replication listener port. |
| `SERVER_CLIENT_ADDRESSES` | empty | `id@host:port,...` client endpoints used by `PRIM`. |
| `CLUSTER_TOKEN` | empty | Shared cluster handshake token. |
| `SERVER_TERM` | `1` | Initial replication term. |
| `REPLICATION_TIMEOUT` | `2.0` | Per-peer ACK timeout in seconds. |
| `HEARTBEAT_INTERVAL` | `0.5` | Leader heartbeat interval in seconds. |
| `FAILURE_TIMEOUT` | `2.0` | Time without heartbeat before election. |
| `ELECTION_TIMEOUT` | `1.0` | Base election retry interval. |
| `MAX_FILE_SIZE` | 10 MiB | Maximum upload size. |
| `SPACE_MARGIN` | 50 MiB | Required free-space margin. |

### Replication example

Primary:

```toml
[server]
server_id = "server1"
role = "primary"
peers = "server2@server2:60012,server3@server3:60012"
client_addresses = "server1@server1:50012,server2@server2:50012,server3@server3:50012"
cluster_token = "change-me"
```

Secondary:

```toml
[server]
server_id = "server2"
role = "secondary"
peers = "server1@server1:60012,server3@server3:60012"
client_addresses = "server1@server1:50012,server2@server2:50012,server3@server3:50012"
cluster_token = "change-me"
```

The replication listener requires mutual TLS. The server certificate and key are
also used as the client certificate when connecting to peers; the cluster CA is
`TLS_CA_FILE`. An empty `SERVER_PEERS` keeps a primary in standalone mode with
quorum 1. In a three-server cluster, every node lists the other two nodes in
`SERVER_PEERS`; `SERVER_CLIENT_ADDRESSES` lets `PRIM` return the current primary
client endpoint after a failover.

The server refuses to start without a valid certificate and key. There is no
plaintext mode.

## TLS certificates

For local development:

```sh
python -m pip install -r requirements-dev.txt
python scripts/generate_dev_cert.py --output certs
export TLS_CERT_FILE=certs/server.crt
export TLS_KEY_FILE=certs/server.key
export CLIENT_TLS_CA_FILE=certs/ca.crt
```

For a real deployment use a certificate from a public CA (for example through
Caddy, nginx, or Let’s Encrypt) and leave `CLIENT_TLS_CA_FILE` empty so clients
use the system trust store. See [Security](security.md).

## Users

| User | Password source | Permissions |
| --- | --- | --- |
| `anonimous` | empty | Download only; cannot upload, share, or change passwords. |
| `sar` | `APP_PASSWORD_SAR` | Bootstrap administrator. |
| `sza` | `APP_PASSWORD_SZA` | Bootstrap administrator. |

Registered accounts are stored in `files/.cloudfs.sqlite3`. An empty
`APP_PASSWORD_SAR`/`APP_PASSWORD_SZA` disables that bootstrap account.

## Local data

`client_files/`, `files/`, `certs/`, `.venv/`, `__pycache__/`, and Ruff’s cache
are local or generated data and should not be committed. Password hashes are
stored in the server database; passwords themselves are never stored.
