# M2 Implementation Plan — Reconciliation and Conflicts

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** On startup, reconcile the local folder with the server manifest, download missing files, propagate local deletes, apply remote tombstones, and preserve both versions on conflicts.

**Architecture:** `SyncWorker.start()` performs a synchronous reconciliation using `ClientState` (last known revision/hash) and `SYNC`. The watcher starts afterwards for new changes. The server resolves stale uploads/deletes by saving the current server version as a conflict copy and returning its path.

**Tech stack:** Python 3.10+, stdlib `unittest`, SQLite, TLS, `watchdog`, `trustme`.

## Conflict policy

1. Stale upload: incoming version becomes official; the current server version is stored as a conflict copy.
2. Stale delete: deletion becomes official; the current server version is stored as a conflict copy.
3. First run, local and remote differ: upload local with `expected_rev=0`, creating a conflict copy of the remote.
4. Local hash equals remote hash: adopt remote state without transferring.
5. Remote delete + local modification: upload local; the deletion is superseded.
6. Local delete + remote modification: delete with stale revision; remote data is preserved as a conflict copy.
7. Local delete of a never-synced file: do not send `DELE`.
8. Conflict name: `<stem> (conflict <client_id> <UTC YYYYmmdd-HHMMSS>)<suffix>`, with a counter if needed.

## Tasks

### Task 1: ClientState identity and cleanup

**Files:** `client_state.py`, `tests/test_client_state.py`

- [x] Add `meta(key, value)` table.
- [x] Add stable `client_id` property backed by `uuid.uuid4().hex`.
- [x] Add `clear_outbox()`.
- [x] Add `delete_file(owner, path)` and `delete_tree(owner, prefix)`.
- [x] Add tests for stable id, clearing the outbox, and deleting a state subtree.
- [x] Commit: `feat: add stable client identity and state cleanup`.

### Task 2: FileStore conflict copies

**Files:** `file_store.py`, `tests/test_file_store.py`

- [x] Add `_conflict_path(owner, path, client_id)`.
- [x] Add `put_with_conflict(owner, path, data, expected_rev, client_id)`.
- [x] Add `delete_with_conflict(owner, path, expected_rev, client_id)`.
- [x] Preserve the current server version as a conflict copy when the revision is stale.
- [x] Do not create a conflict for a tombstone or missing file.
- [x] Add tests for stale upload, stale delete, tombstone, and unique names.
- [x] Commit: `feat: preserve conflict copies for stale mutations`.

### Task 3: Server mutation responses

**Files:** `server_runtime.py`, `tests/test_server_runtime.py`

- [x] Parse `client` in `UPLO` and `rev`/`client` in `DELE`.
- [x] Use `put_with_conflict` and `delete_with_conflict`.
- [x] Return `OK<rev>` or `OK<rev>\t<encoded conflict path>`.
- [x] Keep legacy requests without revisions working.
- [x] Add integration tests for stale upload and delete.
- [x] Commit: `feat: return revision and conflict paths from mutations`.

### Task 4: ClientSession typed results

**Files:** `client_session.py`, `tests/test_client_session.py`

- [x] Add `UploadResult` and `DeleteResult` dataclasses.
- [x] Parse optional revision and conflict path from responses.
- [x] Add `client_id` to `upload`, and `rev`/`client_id` to `delete`.
- [x] Add tests.
- [x] Commit: `feat: return typed upload and delete results`.

### Task 5: SyncWorker reconciliation

**Files:** `sync_client.py`, `tests/test_reconcile.py`, `tests/test_client_session.py`

- [x] `start()` connects, logs in, reconciles, then starts the observer and worker.
- [x] Build local, remote, and state maps.
- [x] Apply the reconciliation decision table.
- [x] Download remote files atomically and ignore their watcher events.
- [x] Upload local files with the state revision; handle conflict copies.
- [x] Delete local files on remote tombstones; delete remote files for local deletions.
- [x] Do not propagate deletes for never-synced files.
- [x] Use `state.delete_tree` for directory deletions.
- [x] Clear the outbox only after a successful reconciliation.
- [x] Add reconciliation tests.
- [x] Commit: `feat: reconcile local and remote state on startup`.

### Task 6: Docs and acceptance

**Files:** `docs/protocol.md`, `docs/architecture.md`, `docs/limitations.md`, `AGENTS.md`, roadmap, this plan.

- [x] Document revisions, conflict responses, naming, and reconciliation.
- [x] Run full tests, Ruff, and strict docs.
- [x] Verify `site/ref` and `site/superpowers` are absent.
- [x] Commit: `docs: document reconciliation and conflict copies`.

## Acceptance

- [x] Startup uploads only local files when the server is empty.
- [x] Startup downloads remote files missing locally.
- [x] Equal hashes cause no transfer.
- [x] Concurrent local/remote changes preserve both versions.
- [x] Local deletion propagates.
- [x] Remote deletion removes the local copy.
- [x] Tombstones do not resurrect files.
- [x] Restart after a successful upload does not duplicate a conflict.
- [x] Deleting a never-synced local file sends no `DELE`.
- [x] `python -m unittest discover -s tests -v` passes.
- [x] `python -m ruff check .` passes.
- [x] `mkdocs build --strict` passes.
