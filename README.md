# Cloud File Service

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Ruff](https://img.shields.io/badge/code%20style-Ruff-D7FF64?logo=ruff&logoColor=111111)](https://docs.astral.sh/ruff/)
[![watchdog](https://img.shields.io/pypi/v/watchdog?logo=pypi&logoColor=white)](https://pypi.org/project/watchdog/)

Automatic file synchronization from a local folder to a TLS server, with a desktop client, CLI, and replicated fault-tolerant backend.

Watch the repository locally with `watchdog`, then send file changes to the server over TCP.

Read the full documentation at [kingjorjai.github.io/Distributed-Systems_Cloud-File-Service](https://kingjorjai.github.io/Distributed-Systems_Cloud-File-Service/). The [final report](https://kingjorjai.github.io/Distributed-Systems_Cloud-File-Service/report/) and the [reproducible demo](https://kingjorjai.github.io/Distributed-Systems_Cloud-File-Service/demo/) are part of it.

Docker deployment is documented in the [Docker guide](https://kingjorjai.github.io/Distributed-Systems_Cloud-File-Service/docker/).

Docker images are published to [GitHub Container Registry](https://github.com/KingJorjai?tab=packages) from `main`.

Tagged releases use `MAJOR.MINOR.PATCH`; the current development release is
`v0.11.2`. A new minor is added for each milestone, patches are used for fixes,
and `v1.0.0` is reserved for the final validated delivery. Build numbers stay
outside the tag. See [Release and Versioning](docs/release.md).

Tagged releases publish self-contained server, CLI client, and GUI client
bundles for Windows x64 and Linux x64. They include the Python runtime and
dependencies, so the target machine does not need Python, `pip`, or additional
downloads. The GUI uses a background daemon and a system tray. The server exposes an optional HTTPS admin panel.
Download them from the repository's [Releases](https://github.com/KingJorjai/Distributed-Systems_Cloud-File-Service/releases) page.

## Build the documentation

Install the development dependencies and build the HTML documentation:

```sh
python -m pip install -r requirements-dev.txt
mkdocs build --strict
```

To also generate the printable PDF with its cover page and contents (without the
source-code API sections):

```sh
npm install --global @mermaid-js/mermaid-cli@11.4.1
python scripts/build_pdf.py
```

The PDF is written to `site/cloud-file-service.pdf`. Its review date is generated
automatically each time the command runs. If several Node installations are
present, set `MERMAID_CLI_ROOT` to the global `node_modules` directory that
contains `@mermaid-js/mermaid-cli`.

## Quick start

From the project directory, create the virtual environment and install the dependency:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Create a development certificate (the `certs/` directory is ignored by Git):

```sh
python scripts/generate_dev_cert.py --output certs
```

Start the server in one terminal:

```sh
source .venv/bin/activate
export TLS_CERT_FILE=certs/server.crt
export TLS_KEY_FILE=certs/server.key
export APP_PASSWORD_SAR='set-a-local-password'
export APP_PASSWORD_SZA='set-another-local-password'
python serv_fich_multithread.py
```

Start the client in another terminal:

```sh
source .venv/bin/activate
export CLIENT_TLS_CA_FILE=certs/ca.crt
python cli_fich.py localhost 50012 client_files
```

### Windows

From PowerShell, create and activate a Windows virtual environment:

```powershell
py -3.10 -m venv .venv-win
.\.venv-win\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python scripts/generate_dev_cert.py --output certs
```

Start the server in one PowerShell window:

```powershell
cd C:\Users\<usuario>\DS\Distributed-Systems_Cloud-File-Service
.\.venv-win\Scripts\Activate.ps1
$env:TLS_CERT_FILE = "certs/server.crt"
$env:TLS_KEY_FILE = "certs/server.key"
$env:APP_PASSWORD_SAR = "set-a-local-password"
$env:APP_PASSWORD_SZA = "set-another-local-password"
python serv_fich_multithread.py
```

Start the client in another PowerShell window:

```powershell
cd C:\Users\<usuario>\DS\Distributed-Systems_Cloud-File-Service
.\.venv-win\Scripts\Activate.ps1
$env:CLIENT_TLS_CA_FILE = "certs/ca.crt"
python cli_fich.py localhost 50012 client_files
```

The client arguments are `server`, `port`, and `local_folder`. The default local folder is `client_files`.

The client reconciles with the server at startup, uploads new or locally modified files, downloads missing or remotely modified files, propagates deletes, and preserves conflict copies when both sides changed. Pending changes are kept in a local outbox and retried after a restart. Active clients receive server notifications through a separate subscription connection; shared files are mounted under `shared/<owner>/`.
