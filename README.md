# Cloud File Service

Automatic one-way file synchronization from a local client folder to a multithreaded server.

## Quick start

From the project directory, create the virtual environment and install the dependency:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Start the server in one terminal:

```sh
source .venv/bin/activate
python serv_fich_multithread.py
```

Start the client in another terminal:

```sh
source .venv/bin/activate
python cli_fich.py localhost 6012 client_files
```

The client arguments are `server`, `port`, and `local_folder`. The default local folder is `client_files`.

The client automatically uploads created, modified, renamed, and deleted files. Existing files are uploaded when it starts. Changes made directly on the server are not synchronized back to the client.
