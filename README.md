# Cloud File Service

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Ruff](https://img.shields.io/badge/code%20style-Ruff-D7FF64?logo=ruff&logoColor=111111)](https://docs.astral.sh/ruff/)
[![watchdog](https://img.shields.io/pypi/v/watchdog?logo=pypi&logoColor=white)](https://pypi.org/project/watchdog/)

Automatic one-way file synchronization from a local client folder to a multithreaded server.

Watch the repository locally with `watchdog`, then send file changes to the server over TCP.

Read the full documentation at [kingjorjai.github.io/Distributed-Systems_Cloud-File-Service](https://kingjorjai.github.io/Distributed-Systems_Cloud-File-Service/).

Docker deployment is documented in the [Docker guide](https://kingjorjai.github.io/Distributed-Systems_Cloud-File-Service/docker/).

Docker images are published to [GitHub Container Registry](https://github.com/KingJorjai?tab=packages) from `main`.

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
automatically each time the command runs.

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
export APP_PASSWORD_SAR='set-a-local-password'
export APP_PASSWORD_SZA='set-another-local-password'
python serv_fich_multithread.py
```

Start the client in another terminal:

```sh
source .venv/bin/activate
python cli_fich.py localhost 50012 client_files
```

### Windows

From PowerShell, create and activate a Windows virtual environment:

```powershell
py -3.10 -m venv .venv-win
.\.venv-win\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Start the server in one PowerShell window:

```powershell
cd C:\Users\<usuario>\DS\Distributed-Systems_Cloud-File-Service
.\.venv-win\Scripts\Activate.ps1
$env:APP_PASSWORD_SAR = "set-a-local-password"
$env:APP_PASSWORD_SZA = "set-another-local-password"
python serv_fich_multithread.py
```

Start the client in another PowerShell window:

```powershell
cd C:\Users\<usuario>\DS\Distributed-Systems_Cloud-File-Service
.\.venv-win\Scripts\Activate.ps1
python cli_fich.py localhost 50012 client_files
```

The client arguments are `server`, `port`, and `local_folder`. The default local folder is `client_files`.

The client automatically uploads created, modified, renamed, and deleted files. Existing files are uploaded when it starts. Changes made directly on the server are not synchronized back to the client.
