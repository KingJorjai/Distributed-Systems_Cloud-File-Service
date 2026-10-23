# AGENTS.md

## Project

One-way file synchronization: a `watchdog` client watches a local folder and pushes changes to a multithreaded TLS server. Python 3.10+ (uses `str | PathLike` syntax and the `tomli` fallback below 3.11).

Entrypoints:
- `serv_fich_multithread.py` — server entrypoint; delegates to `ServerRuntime`.
- `cli_fich.py` — client CLI; authenticates interactively, then starts `SyncWorker`.
- `server_runtime.py` — TLS listener, session threads, protocol state machine.
- `file_store.py` — SQLite metadata, users/shares/settings, filesystem storage, ACLs.
- `client_session.py` — TLS client protocol session used by CLI and future GUI.
- `client_state.py` — client metadata and durable outbox.
- `sync_client.py` — watcher, debounce/coalescing queue, upload/delete worker.
- `szasar.py` — protocol constants, `SocketReader`, path encoding, `recvline`/`recvall`.
- `config.py` — TOML + environment configuration.
- `tls.py` — strict server/client TLS contexts.

Server files live under `files/<username>/`; client default is `client_files/`. Both are gitignored. Roadmap: `docs/superpowers/plans/` (internal). `docs/ref/` is committed course material and excluded from MkDocs.

## Commands

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
```

```sh
python -m unittest discover -s tests -v   # all tests
python -m unittest tests.test_file_store.FileStoreTests.test_revision_increments -v
python -m ruff check .                    # enforced lint
mkdocs build --strict                     # docs
```

- Tests are stdlib `unittest`, not pytest. They require `requirements.txt` because importing `cli_fich` pulls in `watchdog`; TLS tests require `trustme` from `requirements-dev.txt`.
- Tests use temporary directories and ephemeral ports; they do not depend on a global `config.toml`.
- `ruff check` passes; `ruff format --check` currently fails on most source files. Do not run `ruff format .` wholesale unless asked.
- `.github/workflows/tests.yml` runs tests and lint on Ubuntu/Windows and strict docs on Linux.

## Configuration and TLS

Precedence: CLI args > environment > `config.toml` > defaults. `CONFIG_FILE` selects the TOML file. Copy `config.toml.example`; `config.toml` is gitignored.

- TLS is mandatory. The server refuses to start without `TLS_CERT_FILE`/`TLS_KEY_FILE`; there is no plaintext fallback. Clients verify hostnames and use the system CA or `CLIENT_TLS_CA_FILE`.
- `python scripts/generate_dev_cert.py --output certs` creates a development CA, server certificate, and key. `certs/` is gitignored.
- `APP_PASSWORD_SAR` / `APP_PASSWORD_SZA` bootstrap admin accounts; an empty value disables that account. `anonimous` is passwordless and read-only.
- Registered users and shares live in `files/.cloudfs.sqlite3`; registration is controlled by `ALLOW_REGISTRATION`.
- `load_config()` is called from `main()`; importing the server no longer loads configuration or binds a port.

## Protocol constraints

- Commands are 4-character prefixes from `szasar.Command` concatenated directly with arguments (no spaces), terminated by CRLF; responses start with `OK` or `ER<code>`. Paths are URL-encoded with `szasar.encode_path`/`decode_path`.
- Upload/download are two-step handshakes: `UPLOfilename?size[&rev=&hash=]` → `OK`, then `UPL2\r\n` + raw bytes; `DOWNfilename` → `OK<size>`, then `DOW2\r\n` → `OK` + raw bytes.
- `SYNC` returns `OK<count>`, tab-separated manifest lines, and `END`. `STATpath` returns `OK<rev>\t<hash>\t<size>`.
- New commands: `REGI`, `CHPW`, `USRS`, `SYNC`, `STAT`. Error codes 14–20 cover sharing, registration, users, long lines, and revision conflicts.
- There is no `LIST` command. Keep protocol changes in sync across `szasar.py`, `server_runtime.py`, `client_session.py`, and `docs/protocol.md`.
- Preserve `safe_path` traversal/symlink checks and atomic upload (`tempfile` + `os.replace`); uploads are limited by `MAX_FILE_SIZE` and `SPACE_MARGIN`.

## Behavior boundaries

- Synchronization is client→server only; server-side changes are not pushed back yet. Conflicts/versioning are in `TODO.md` and the roadmap, not implemented.
- Renames are modeled as delete + upload (recursive for directories). Initial startup uploads every existing local file/folder; full manifest reconciliation is M2.
- The client opens two TLS connections per run: the interactive login connection plus `SyncWorker`'s own authenticated connection.
- Changes are persisted in the client outbox before execution and replayed after restart; uploads still wait for size/mtime to stabilize (roughly 0.7 s).
- Sharing schema/ACL exists, but `SHAR`/`UNSH` and notifications arrive in M5.

## Docs and release

```sh
mkdocs build --strict                 # outputs site/
python scripts/build_pdf.py           # needs Chromium + mermaid-cli@11.4.1
```

- PDF sections are an explicit list in `scripts/build_pdf.py` (`PAGES`); adding a docs page requires updating it. Cover metadata is `docs/pdf-metadata.json`.
- `scripts/build_release_bundle.py <server|client> --output DIR --archive-format zip|gztar` builds PyInstaller onedir bundles; component entrypoints, executable names, and bundled READMEs are defined in `COMPONENTS`.
- Release workflow runs on `v*` tags (or manual dispatch with an existing tag) and also publishes a Compose package and `SHA256SUMS`.

## Docker

- Generate certificates with `python scripts/generate_dev_cert.py --output certs --host server --host localhost --host 127.0.0.1` before Compose.
- `compose.yaml` builds both images, bind-mounts `./files`, `./client_files`, and `./certs`; uses host `DOCKER_UID`/`DOCKER_GID` from `.env`.
- `compose.registry.yaml` only sets `build: null` — use it as an override to pull images from GHCR.
- `SERVER_PUBLISHED_PORT` is the host port; `SERVER_INTERNAL_PORT` changes the container/client port. Set both together.
