# Quick Start

## Requirements

- Python 3.10 or newer.
- A virtual environment.
- A local TCP port available for the server.
- A TLS certificate and key.

## Install

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

The second requirements file is needed for the development certificate
generator and the documentation tooling.

## Create development certificates

```sh
python scripts/generate_dev_cert.py --output certs
export TLS_CERT_FILE=certs/server.crt
export TLS_KEY_FILE=certs/server.key
export CLIENT_TLS_CA_FILE=certs/ca.crt
```

## Start the server

In the first terminal:

```sh
source .venv/bin/activate
export TLS_CERT_FILE=certs/server.crt
export TLS_KEY_FILE=certs/server.key
export APP_PASSWORD_SAR='set-a-local-password'
export APP_PASSWORD_SZA='set-another-local-password'
python serv_fich_multithread.py
```

The server listens on port `50012` by default. It refuses plaintext
connections.

## Start the client

In a second terminal:

```sh
source .venv/bin/activate
export CLIENT_TLS_CA_FILE=certs/ca.crt
python cli_fich.py localhost 50012 client_files
```

The arguments are:

1. `server`: server hostname or IP address.
2. `port`: server TCP port.
3. `local_folder`: local folder to watch.

The default local folder is `client_files`.

## Register an account

The CLI currently authenticates existing accounts. Use the GUI (M6) or the
protocol to register:

```text
REGIalice?password123
USERalice
PASSpassword123
```

Registration is enabled by default and can be disabled with
`ALLOW_REGISTRATION=false`.

## Verify synchronization

1. Authenticate with a registered account or one of the bootstrap passwords.
2. Create or edit a file in `client_files`.
3. Wait briefly for the file to stabilize.
4. Check the corresponding file under `files/<user>/` on the server.

The anonymous user can download known files but cannot upload, create
directories, share files, or delete files. File listing is not currently
implemented by the server.
