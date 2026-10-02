# Configuration

The application loads its settings from `config.toml`. Copy `config.toml.example` to
`config.toml` for local changes; the file is ignored by Git.

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

[server]
port = 50012
files_path = "files"
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

The corresponding environment variables are `CLIENT_SERVER`, `CLIENT_PORT`, and
`CLIENT_LOCAL_PATH`.

## Server settings

`serv_fich_multithread.py` uses:

| Setting | Value | Description |
| --- | --- | --- |
| `SERVER_PORT` | `50012` | Listening TCP port. |
| `SERVER_FILES_PATH` | `files` | Root storage directory. |
| `MAX_FILE_SIZE` | 10 MiB | Maximum upload size. |
| `SPACE_MARGIN` | 50 MiB | Required free-space margin. |

## Development users

| User | Password source | Permissions |
| --- | --- | --- |
| `anonimous` | empty | Download known files only. |
| `sar` | `APP_PASSWORD_SAR` | Full file operations. |
| `sza` | `APP_PASSWORD_SZA` | Full file operations. |

Set `APP_PASSWORD_SAR` and `APP_PASSWORD_SZA` in the environment. They are intentionally
not stored in `config.toml`, `.env.example`, Dockerfiles, or the repository.

## Local data

`client_files/`, `files/`, `.venv/`, `__pycache__/`, and Ruff's cache are local or generated data and should not be committed.
