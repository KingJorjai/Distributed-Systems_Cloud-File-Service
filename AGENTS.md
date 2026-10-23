# AGENTS.md

## Project

One-way file synchronization: a `watchdog` client watches a local folder and pushes changes to a multithreaded TCP server. Python 3.10+ (uses `str | PathLike` syntax and the `tomli` fallback below 3.11).

Entrypoints:
- `serv_fich_multithread.py` — server, one thread per connection.
- `cli_fich.py` — client CLI; authenticates interactively, then starts `SyncWorker`.
- `sync_client.py` — watcher, debounce/coalescing queue, upload/delete worker.
- `szasar.py` — protocol constants and `recvline`/`recvall`.
- `config.py` — TOML + environment configuration.

Server files live under `files/<username>/`; client default is `client_files/`. Both are gitignored.

## Commands

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
```

```sh
python -m unittest discover -s tests -v   # all tests
python -m unittest tests.test_config.LoadConfigTests.test_environment_overrides_toml -v
python -m ruff check .                    # enforced lint
```

- Tests are stdlib `unittest`, not pytest. They require `requirements.txt` because importing `cli_fich` pulls in `watchdog`.
- Tests assert server defaults (`SERVER_PORT=50012`, `files`) at import time: run from the repo root with no `config.toml` and no `SERVER_PORT`/`SERVER_FILES_PATH` overrides.
- `ruff check` passes; `ruff format --check` currently fails on most source files. Do not run `ruff format .` wholesale unless asked — it creates a large unrelated diff.
- No CI runs tests or lint; only docs, Docker publishing, and releases have workflows.

## Configuration

Precedence: CLI args > environment > `config.toml` > defaults. `CONFIG_FILE` selects the TOML file. Copy `config.toml.example`; `config.toml` is gitignored.

- `APP_PASSWORD_SAR` / `APP_PASSWORD_SZA` are environment-only. An empty privileged password disables that user; `anonimous` is always passwordless and read-only (download only).
- The server calls `load_config()` at module import, so changing env/TOML after import has no effect.
- Users are indexed by position in `USERS = ("anonimous", "sar", "sza")`; adding a user requires updating `USERS` and `PASSWORDS` together.

## Protocol constraints

- Commands are 4-character prefixes from `szasar.Command` concatenated directly with arguments (no spaces), terminated by CRLF; responses start with `OK` or `ER<code>`.
- Upload/download are two-step handshakes: `UPLOfilename?size` → `OK`, then `UPL2\r\n` + raw bytes; `DOWNfilename` → `OK<size>`, then `DOW2\r\n` → `OK` + raw bytes.
- There is no `LIST` command. Keep protocol changes in sync across `szasar.py`, `serv_fich_multithread.py`, `sync_client.py`, and `docs/protocol.md`.
- Preserve `safe_path` traversal checks and atomic upload (`tempfile` + `os.replace`); uploads are also limited by `MAX_FILE_SIZE` and `SPACE_MARGIN`.

## Behavior boundaries

- Synchronization is client→server only; server-side changes are never pushed back. Conflicts/versioning are in `TODO.md`, not implemented.
- Renames are modeled as delete + upload (recursive for directories). Initial startup uploads every existing local file/folder.
- The client opens two server connections per run: the interactive login connection plus `SyncWorker`'s own authenticated connection.
- The change queue is in memory and files are uploaded only after size/mtime stabilize (roughly 0.7 s), so manual sync tests need short waits.

## Docs and release

```sh
mkdocs build --strict                 # outputs site/
python scripts/build_pdf.py           # needs Chromium + mermaid-cli@11.4.1
```

- PDF sections are an explicit list in `scripts/build_pdf.py` (`PAGES`); adding a docs page requires updating it. Cover metadata is `docs/pdf-metadata.json`.
- `scripts/build_release_bundle.py <server|client> --output DIR --archive-format zip|gztar` builds PyInstaller onedir bundles; component entrypoints, executable names, and bundled READMEs are defined in `COMPONENTS`.
- Release workflow runs on `v*` tags (or manual dispatch with an existing tag) and also publishes a Compose package and `SHA256SUMS`.

## Docker

- `compose.yaml` builds both images and bind-mounts `./files` and `./client_files`; uses host `DOCKER_UID`/`DOCKER_GID` from `.env`.
- `compose.registry.yaml` only sets `build: null` — use it as an override to pull images from GHCR.
- `SERVER_PUBLISHED_PORT` is the host port; `SERVER_INTERNAL_PORT` changes the container/client port. Set both together.
