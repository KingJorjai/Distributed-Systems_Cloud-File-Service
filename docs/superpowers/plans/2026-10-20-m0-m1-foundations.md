# M0 + M1 Implementation Plan — Baseline, TLS, and Foundations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reproducible baseline with mandatory TLS, buffered framing, registration/authentication, SQLite-backed users/files/shares/settings, and persistent client state.

**Architecture:** Client and server speak the existing line protocol over native TLS. `FileStore` owns SQLite metadata, filesystem storage, and ACLs. `ServerRuntime` owns socket acceptance and sessions. `ClientSession` unifies register/login/sync for the CLI and the future GUI. Replication is intentionally deferred to M3.

**Tech stack:** Python 3.10+, stdlib `unittest`, `socket`, `ssl`, `sqlite3`, `watchdog`, `trustme` (dev/test only).

---

## Plan index

| Plan | Milestone | Deliverable | Depends on |
| --- | --- | --- | --- |
| 00 | M0 | Baseline, Git, CI, references | — |
| 01 | M1a | TLS, framing, path encoding | M0 |
| 02 | M1b | Auth and `FileStore` | M1a |
| 03 | M1c | `ServerRuntime` and protocol commands | M1b |
| 04 | M1d | `ClientState`, outbox, `ClientSession`, CLI | M1c |
| 05 | M1e | Integration, docs, acceptance | M1d |
| 06–13 | M2–M9 | Reconciliation, replication, failover, shares, GUI, web admin, distribution | Separate plans |

Do not start M2 until M1e is green.

## M0 — Baseline

- [x] Create `feat/final-project`.
- [x] Add `docs/ref/README.md` and commit course references, internal plan, and `AGENTS.md`.
- [x] Exclude `ref/` and `superpowers/` from MkDocs.
- [x] Add `.github/workflows/tests.yml` for unittest, Ruff, and strict docs.
- [x] Add `trustme` to development dependencies.
- [x] Ignore local `certs/`.
- [x] Verify baseline and commit.
- [x] Create the M1 worktree from `feat/final-project`.

## M1a — TLS, framing, paths

### Config

Add to `ClientConfig`: `tls_ca_file`, `tls_server_name`, `state_dir`.
Add to `ServerConfig`: `host`, `tls_cert_file`, `tls_key_file`, `tls_ca_file`, `registration_enabled`.
Environment overrides: `CLIENT_TLS_CA_FILE`, `CLIENT_TLS_SERVER_NAME`,
`CLIENT_STATE_DIR`, `SERVER_HOST`, `TLS_CERT_FILE`, `TLS_KEY_FILE`,
`TLS_CA_FILE`, `ALLOW_REGISTRATION`.

### TLS helpers (`tls.py`)

- `server_context(cert_file, key_file, ca_file=None, require_client_cert=False)`
- `client_context(ca_file=None)`
- TLS 1.2 minimum, certificate verification always enabled.
- No plaintext fallback.

### Framing (`szasar.py`)

- `SocketReader(sock, max_line=8192)` with `readline()` and `read_exact()`.
- `LineTooLong` for oversized command lines.
- `recvline` keeps byte-by-byte compatibility and gains `max_length`.
- `encode_path`/`decode_path` using URL quoting with `/` safe.

### Protocol constants

Add `SYNC`, `STAT`, `REGI`, `CHPW`, `USRS`.

### Development certificates

`scripts/generate_dev_cert.py` writes `ca.crt`, `server.crt`, and `server.key`
using `trustme`, defaulting to `certs/`.

## M1b — Auth and FileStore

### Auth (`auth.py`)

- PBKDF2-HMAC-SHA256, 200,000 iterations, 16-byte random salt.
- Constant-time verification.
- Username regex `^[A-Za-z0-9_-]{3,32}$`.
- Minimum password length 8.
- Reserved names: `anonimous`, `sar`, `sza`.

### SQLite schema

- `users(username, password_hash, salt, iterations, role, disabled, created_at)`
- `files(owner, path, rev, hash, size, mtime_ns, deleted)` with `(owner, path)` key.
- `shares(owner, path, grantee, access, created_at)` with `CHECK (owner <> grantee)`.
- `settings(key, value)`.

### FileStore contract

`create_user`, `get_user`, `list_users`, `set_user_disabled`, `set_password`,
`create_share`, `revoke_share`, `list_shares`, `access_for`, `put`, `get`,
`stat`, `delete`, `manifest`, `backfill`, `get_setting`, `set_setting`.

Rules:

- Paths are normalized and confined to `root/<owner>` with symlink-aware checks.
- Uploads use `tempfile.mkstemp` + `os.replace`.
- SHA-256 is stored; revisions increase on every mutation.
- Deletes create tombstones (`deleted=1`).
- Owner has implicit `rw`; grantees get `ro` or `rw` from the longest matching share.
- `backfill` imports existing files with `rev=1` and ignores the database and temp files.
- SQLite uses WAL, foreign keys, `check_same_thread=False`, and an `RLock`.

## M1c — Server runtime and protocol

### Runtime

`ServerRuntime(config, store)` with `start()`, `port`, `serve_forever()`, `stop()`.
The entrypoint `serv_fich_multithread.py` loads configuration, creates the store,
seeds bootstrap `sar`/`sza` users from environment passwords, and runs the runtime.

### Session state

`Identification -> Authentication -> Main`.

Commands:

| Command | State | Response |
| --- | --- | --- |
| `USERname` | Identification | `OK` / `ER2` |
| `REGIusername?<encoded password>` | Identification | `OK` / `ER15` / `ER16` / `ER18` |
| `PASSpassword` | Authentication | `OK` / `ER3` / `ER17` |
| `SYNC` | Main | `OK<count>` + manifest lines + `END` |
| `STAT<encoded path>` | Main | `OK<rev>\t<hash>\t<size>` / `ER5` |
| `USRS` | Main | `OK<count>` + users + `END` |
| `CHPW<encoded old>?<encoded new>` | Main | `OK` / `ER3` / `ER16` |
| `UPLO...` / `UPL2` | Main / Uploading | existing handshake over TLS |
| `DOWN...` / `DOW2` | Main / Downloading | existing handshake over TLS |
| `MKDR` / `RMDR` / `DELE` | Main | existing behavior over TLS |
| `EXIT` | Main | `OK` and close |

Manifest line:

```text
<owner>\t<encoded path>\t<rev>\t<hash>\t<size>\t<deleted>\t<access>
```

Upload syntax:

```text
UPLO<encoded path>?size=<n>&rev=<n>&hash=<hex>
```

Legacy `UPLO<path>?<n>` remains accepted. A stale `rev` returns `ER20`; conflict
copies are M2.

Error additions: 14 self-share, 15 registration disabled, 16 invalid registration,
17 disabled user, 18 duplicate user, 19 line too long, 20 revision conflict.

## M1d — Client state and session

### ClientState

SQLite tables `files` and `outbox`. Default state directory:

- Windows: `%LOCALAPPDATA%/cloudfs`
- Other: `$XDG_STATE_HOME/cloudfs` or `~/.local/state/cloudfs`

The database filename is derived from username, server, port, and local root.

### ClientSession

`connect`, `login`, `register`, `sync`, `stat`, `upload`, `download`, `delete`,
`mkdir`, `rmdir`, `close`. Uses strict TLS and `SocketReader`.

`SyncWorker` enqueues changes into the outbox before processing, acknowledges
successful operations, and replays pending changes on startup.

## M1e — Acceptance

- [ ] `python -m unittest discover -s tests -v`
- [ ] `python -m ruff check .`
- [ ] `mkdocs build --strict`
- [ ] `test ! -d site/ref`
- [ ] `test ! -d site/superpowers`
- [ ] Register/login over TLS.
- [ ] `SYNC` and `STAT` return correct metadata.
- [ ] Outbox survives client restart.
- [ ] Plaintext client is rejected.
- [ ] Path traversal and symlink escape are rejected.
- [ ] Dev certificate script works.

## Execution rules

- TDD: failing test, minimal implementation, passing test, commit.
- One commit per task.
- Python 3.10 compatible; no 3.11-only syntax.
- No new comments in source files.
- Run `ruff check`, not `ruff format`.
- Update protocol/configuration docs whenever behavior changes.
- Never commit passwords or real certificates.
- Tests run from the repository root and must not depend on a global `config.toml`.
