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
`CLIENT_TLS_CA_FILE`, `CLIENT_TLS_SERVER_NAME`, and `CLIENT_STATE_DIR`.

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
| `MAX_FILE_SIZE` | 10 MiB | Maximum upload size. |
| `SPACE_MARGIN` | 50 MiB | Required free-space margin. |

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
