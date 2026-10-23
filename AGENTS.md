# AGENTS.md

## Project

One-way file synchronization: a `watchdog` client watches a local folder and pushes changes to a multithreaded TLS server. Python 3.10+ (uses `str | PathLike` syntax and the `tomli` fallback below 3.11).

Entrypoints:
- `serv_fich_multithread.py` — server entrypoint; delegates to `ServerRuntime`.
- `cli_fich.py` — CLI frontend; controls the background daemon over local IPC.
- `gui_fich.py`/`gui_app.py` — Tkinter desktop frontend and tray.
- `daemon_service.py`/`client_daemon.py` — background daemon owning `ClientSession` and `SyncWorker`.
- `ipc.py` — authenticated Unix socket/named-pipe IPC.
- `server_runtime.py` — TLS listener, session threads, protocol state machine, replication wiring.
- `admin_service.py` / `server_admin.py` — replicated admin operations and the HTTPS admin panel.
- `replication.py` — peer parsing, durable log, mTLS replication server/client, quorum coordinator.
- `election.py` — heartbeats, persistent terms, election, fencing, and leader client endpoints.
- `notification_hub.py` — per-user subscriptions and `UPDT` delivery on the primary.
- `remote_watcher.py` — client notification connection that feeds remote updates into `SyncWorker`.
- `file_store.py` — SQLite metadata, users/shares/settings, filesystem storage, ACLs.
- `client_session.py` — TLS client protocol session used by the daemon and CLI/GUI frontends.
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
- Cluster settings: `SERVER_ID`, `SERVER_ROLE=primary|secondary`, `SERVER_PEERS=id@host:port,...` (all other nodes), `SERVER_PRIMARY`, `SERVER_REPLICATION_PORT`, `SERVER_CLIENT_ADDRESSES`, `CLUSTER_TOKEN`, `SERVER_TERM`, `REPLICATION_TIMEOUT`, `HEARTBEAT_INTERVAL`, `FAILURE_TIMEOUT`, `ELECTION_TIMEOUT`. Replication uses a separate mTLS listener; an empty `SERVER_PEERS` keeps a standalone primary with quorum 1.
- Admin settings: `SERVER_ADMIN_ENABLED` (default false), `SERVER_ADMIN_HOST`, `SERVER_ADMIN_PORT`, `SERVER_ADMIN_ADDRESSES`, `ALLOW_ADMIN_FAILOVER`, `ADMIN_SESSION_TIMEOUT`. The panel is HTTPS-only and admin mutations require primary quorum.
- Client discovery: `CLIENT_PEERS=host:port,...` are seeds; `PRIM` returns the current primary client endpoint. Leave `CLIENT_TLS_SERVER_NAME` empty when endpoints differ.
- `python scripts/generate_dev_cert.py --output certs` creates a development CA, server certificate, and key. `certs/` is gitignored.
- `APP_PASSWORD_SAR` / `APP_PASSWORD_SZA` bootstrap admin accounts; an empty value disables that account. `anonimous` is passwordless and read-only.
- Registered users and shares live in `files/.cloudfs.sqlite3`; registration is controlled by `ALLOW_REGISTRATION`.
- `load_config()` is called from `main()`; importing the server no longer loads configuration or binds a port.
- Client configuration defaults to the standard per-user config directory (`%APPDATA%\CloudFileService` on Windows, `$XDG_CONFIG_HOME/cloudfs` on Linux); `CONFIG_FILE` overrides it.
- The GUI/CLI daemon uses local IPC with an authkey file mode `0600`; passwords are memory-only.

## Protocol constraints

- Commands are 4-character prefixes from `szasar.Command` concatenated directly with arguments (no spaces), terminated by CRLF; responses start with `OK` or `ER<code>`. Paths are URL-encoded with `szasar.encode_path`/`decode_path`.
- Upload/download are two-step handshakes: `UPLOfilename?size[&rev=&hash=&client=]` → `OK`, then `UPL2\r\n` + raw bytes; the final response is `OK<rev>` or `OK<rev>\t<conflict path>`. `DOWNfilename` → `OK<size>`, then `DOW2\r\n` → `OK` + raw bytes.
- `SYNC` returns `OK<count>`, tab-separated manifest lines, and `END`. `STATpath` returns `OK<rev>\t<hash>\t<size>`.
- Replication messages are one JSON object per CRLF line over mTLS: `HELLO`, `HELLO_OK`, `HB`, `HB_OK`, `VOTE`, `VOTE_OK`, `COORD`, `RB`, `ACK`, `COMMIT`, `COMMITTED`, `ABORT`, `SNAP`. The primary commits after a 2/3 quorum; secondaries apply only committed entries.
- `PRIM` is accepted before authentication and returns `OKhost:port` for the current primary or `ER13` when no leader is known.
- Sharing commands: `SHAR<path>?<grantee>?<ro|rw>`, `UNSH<path>?<grantee>`, and `SHRS` for grantee shares. `SUBS<client_id>` opens a notification stream; `UPDT` carries owner/path/rev/hash/size/op/access/client id.
- New commands: `REGI`, `CHPW`, `USRS`, `SYNC`, `STAT`. `DELEpath?rev=&client=` returns a revision and optional conflict path. Error codes 14–20 cover sharing, registration, users, long lines, and revision conflicts.
- There is no `LIST` command. Keep protocol changes in sync across `szasar.py`, `server_runtime.py`, `client_session.py`, and `docs/protocol.md`.
- Preserve `safe_path` traversal/symlink checks and atomic upload (`tempfile` + `os.replace`); uploads are limited by `MAX_FILE_SIZE` and `SPACE_MARGIN`.

## Behavior boundaries

- At startup the client reconciles the server manifest with its state and local files, so it can download remote changes and apply tombstones. Active clients receive `UPDT` notifications through a separate subscription connection; offline clients converge on the next reconciliation. Conflict copies are implemented; version history and garbage collection are not.
- `server1` starts as primary in Compose. If it stops, `server2`/`server3` elect a new primary; clients use `PRIM` to redirect. A restarted old primary becomes a follower and receives a snapshot. Secondaries serve reads but reject mutations with `ER13` while they are followers.
- Admin web actions are replicated; secondary panels redirect mutations to the primary admin URL. `sar`/`sza` are the bootstrap admins; self-disable and disabling the last enabled admin are rejected.
- Shared files are mounted locally under `shared/<owner>/<path>`; owned files stay at the root. `ro` local edits are preserved as local conflict copies and the remote version is restored. Notifications require an active client; offline clients reconcile on the next start.
- Renames are modeled as delete + upload (recursive for directories). Startup reconciliation uploads only new/modified local files and downloads missing/remote-modified files.
- The client opens two TLS connections per run: the interactive login connection plus `SyncWorker`'s own authenticated connection.
- Changes are persisted in the client outbox before execution and replayed after restart. Startup reconciliation handles offline changes before the watcher starts; uploads wait for size/mtime to stabilize (roughly 0.7 s).

## Docs and release

- Versioning: `MAJOR.MINOR.PATCH` tags, current `v0.11.3`; minor per milestone, patch for fixes, `v1.0.0` only after final validated delivery. Build metadata stays outside tags.
- Final report: `docs/report.md`; demo: `docs/demo.md`; Beamer slides: `docs/presentation/slides.tex`; local/Docker demos: `scripts/demo_failover.py` and `scripts/demo_docker.sh`.
- Build slides with `scripts/build_slides.sh` (two `pdflatex` passes, output `site/presentation.pdf`).

```sh
mkdocs build --strict                 # outputs site/
python scripts/build_pdf.py           # needs Chromium + mermaid-cli@11.4.1
```

- PDF sections are an explicit list in `scripts/build_pdf.py` (`PAGES`); adding a docs page requires updating it. Cover metadata is `docs/pdf-metadata.json`.
- `scripts/build_release_bundle.py <server|client> --output DIR --archive-format zip|gztar` builds PyInstaller onedir bundles; component entrypoints, executable names, and bundled READMEs are defined in `COMPONENTS`.
- Release workflow runs on `v*` tags (or manual dispatch with an existing tag) and also publishes a Compose package and `SHA256SUMS`.

## Docker

- Generate certificates with `python scripts/generate_dev_cert.py --output certs --host server --host localhost --host 127.0.0.1` before Compose.
- `compose.yaml` runs `server1`, `server2`, `server3`, and `client`; bind-mounts `./files/server1..3`, `./client_files`, and `./certs`; uses host `DOCKER_UID`/`DOCKER_GID`, `CLUSTER_TOKEN`, and client seed endpoints. Admin ports 50080/50081/50082 are published for the demo.
- Generate certs for `server1`, `server2`, `server3`, `localhost`, and `127.0.0.1`.
- `compose.registry.yaml` only sets `build: null` — use it as an override to pull images from GHCR.
- `SERVER_PUBLISHED_PORT` is the host port; `SERVER_INTERNAL_PORT` changes the internal client port. Replication uses `60012` inside the Compose network.
