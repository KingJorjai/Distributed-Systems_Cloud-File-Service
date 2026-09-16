# Configuration

The current implementation keeps its main settings as module constants and command-line arguments.

## Client arguments

```sh
python cli_fich.py [server [port [local_folder]]]
```

| Setting | Default | Description |
| --- | --- | --- |
| `server` | `localhost` | Server hostname or IP address. |
| `port` | `6012` | Server TCP port. |
| `local_folder` | `client_files` | Folder watched by the automatic synchronizer. |

## Server settings

`serv_fich_multithread.py` uses:

| Setting | Value | Description |
| --- | --- | --- |
| `PORT` | `6012` | Listening TCP port. |
| `FILES_PATH` | `files` | Root storage directory. |
| `MAX_FILE_SIZE` | 10 MiB | Maximum upload size. |
| `SPACE_MARGIN` | 50 MiB | Required free-space margin. |

## Development users

| User | Password | Permissions |
| --- | --- | --- |
| `anonimous` | empty | List and download. |
| `sar` | `sar` | Full file operations. |
| `sza` | `sza` | Full file operations. |

These credentials are part of the current educational implementation and must be replaced before production use.

## Local data

`client_files/`, `files/`, `.venv/`, `__pycache__/`, and Ruff's cache are local or generated data and should not be committed.
