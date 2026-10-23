# M2 Implementation Plan — Reconciliation and Conflicts

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

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

- [ ] Add `meta(key, value)` table.
- [ ] Add stable `client_id` property backed by `uuid.uuid4().hex`.
- [ ] Add `clear_outbox()`.
- [ ] Add `delete_file(owner, path)` and `delete_tree(owner, prefix)`.
- [ ] Add tests for stable id, clearing the outbox, and deleting a state subtree.
- [ ] Commit: `feat: add stable client identity and state cleanup`.

### Task 2: FileStore conflict copies

**Files:** `file_store.py`, `tests/test_file_store.py`

- [ ] Add `_conflict_path(owner, path, client_id)`.
- [ ] Add `put_with_conflict(owner, path, data, expected_rev, client_id)`.
- [ ] Add `delete_with_conflict(owner, path, expected_rev, client_id)`.
- [ ] Preserve the current server version as a conflict copy when the revision is stale.
- [ ] Do not create a conflict for a tombstone or missing file.
- [ ] Add tests for stale upload, stale delete, tombstone, and unique names.
- [ ] Commit: `feat: preserve conflict copies for stale mutations`.

### Task 3: Server mutation responses

**Files:** `server_runtime.py`, `tests/test_server_runtime.py`

- [ ] Parse `client` in `UPLO` and `rev`/`client` in `DELE`.
- [ ] Use `put_with_conflict` and `delete_with_conflict`.
- [ ] Return `OK<rev>` or `OK<rev>\t<encoded conflict path>`.
- [ ] Keep legacy requests without revisions working.
- [ ] Add integration tests for stale upload and delete.
- [ ] Commit: `feat: return revision and conflict paths from mutations`.

### Task 4: ClientSession typed results

**Files:** `client_session.py`, `tests/test_client_session.py`

- [ ] Add `UploadResult` and `DeleteResult` dataclasses.
- [ ] Parse optional revision and conflict path from responses.
- [ ] Add `client_id` to `upload`, and `rev`/`client_id` to `delete`.
- [ ] Add tests.
- [ ] Commit: `feat: return typed upload and delete results`.

### Task 5: SyncWorker reconciliation

**Files:** `sync_client.py`, `tests/test_reconcile.py`, `tests/test_client_session.py`

- [ ] `start()` connects, logs in, reconciles, then starts the observer and worker.
- [ ] Build local, remote, and state maps.
- [ ] Apply the reconciliation decision table.
- [ ] Download remote files atomically and ignore their watcher events.
- [ ] Upload local files with the state revision; handle conflict copies.
- [ ] Delete local files on remote tombstones; delete remote files for local deletions.
- [ ] Do not propagate deletes for never-synced files.
- [ ] Use `state.delete_tree` for directory deletions.
- [ ] Clear the outbox only after a successful reconciliation.
- [ ] Add reconciliation tests.
- [ ] Commit: `feat: reconcile local and remote state on startup`.

### Task 6: Docs and acceptance

**Files:** `docs/protocol.md`, `docs/architecture.md`, `docs/limitations.md`, `AGENTS.md`, roadmap, this plan.

- [ ] Document revisions, conflict responses, naming, and reconciliation.
- [ ] Run full tests, Ruff, and strict docs.
- [ ] Verify `site/ref` and `site/superpowers` are absent.
- [ ] Commit: `docs: document reconciliation and conflict copies`.

## Acceptance

- [ ] Startup uploads only local files when the server is empty.
- [ ] Startup downloads remote files missing locally.
- [ ] Equal hashes cause no transfer.
- [ ] Concurrent local/remote changes preserve both versions.
- [ ] Local deletion propagates.
- [ ] Remote deletion removes the local copy.
- [ ] Tombstones do not resurrect files.
- [ ] Restart after a successful upload does not duplicate a conflict.
- [ ] Deleting a never-synced local file sends no `DELE`.
- [ ] `python -m unittest discover -s tests -v` passes.
- [ ] `python -m ruff check .` passes.
- [ ] `mkdocs build --strict` passes.
