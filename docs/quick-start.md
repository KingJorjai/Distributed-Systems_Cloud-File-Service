# Quick Start

## Requirements

- Python 3.11 or newer.
- A virtual environment.
- A local TCP port available for the server.

## Install

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

The second requirements file is only needed to build this documentation locally.

## Start the server

In the first terminal:

```sh
source .venv/bin/activate
python serv_fich_multithread.py
```

The server listens on port `6012` by default.

## Start the client

In a second terminal:

```sh
source .venv/bin/activate
python cli_fich.py localhost 6012 client_files
```

The arguments are:

1. `server`: server hostname or IP address.
2. `port`: server TCP port.
3. `local_folder`: local folder to watch.

The default local folder is `client_files`.

## Verify synchronization

1. Authenticate as `sar` with password `sar`, or `sza` with password `sza`.
2. Create or edit a file in `client_files`.
3. Wait briefly for the file to stabilize.
4. Check the corresponding file under `files/<user>/` on the server.

The anonymous user can list and download files but cannot upload or delete them.
