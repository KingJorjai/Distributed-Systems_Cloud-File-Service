# M3 Implementation Plan — Passive Replication, Durable Log, and Quorum

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Three servers apply the same mutations in the same order. The primary commits only after a 2/3 quorum; secondaries apply committed operations and reject client mutations.

**Architecture:** A dedicated replication listener uses mutual TLS. The primary plans each mutation as deterministic low-level operations, broadcasts `RB` over persistent TLS connections, waits for majority `ACK`, appends a committed log entry, applies locally, and sends `COMMIT`. Secondaries store proposals, apply only committed entries, and reply `ER13` to client mutations.

**Tech Stack:** Python 3.10+, `unittest`, TLS/mTLS, SQLite, sockets, `trustme`, Docker Compose.

## Decisions

1. Separate replication port, mTLS, `CLUSTER_TOKEN`.
2. Primary connects to secondaries; secondaries only listen.
3. Quorum 2/3. A single down secondary does not block; both down returns `ER12`.
4. Primary applies only after quorum. No quorum means `ER12`, `ABORT`, and no local apply.
5. Operations are deterministic: primary plans revisions, hashes, `mtime_ns`, conflict paths, and data before replication.
6. Durable log keyed by `(term, idx)` with persisted `commit_index`.
7. Standalone mode (`SERVER_PEERS` empty) has quorum 1 and no network replication.
8. Snapshot export/import and the `SNAP` message are implemented in M3; automatic rejoin is M4.

## Task 1: Cluster configuration

**Files:** `config.py`, `config.toml.example`, `tests/test_config.py`, `replication.py`

- [x] Add `server_id`, `role`, `peers`, `primary`, `replication_host`, `replication_port`, `cluster_token`, `term`, `replication_timeout`.
- [x] Environment: `SERVER_ID`, `SERVER_ROLE`, `SERVER_PEERS`, `SERVER_PRIMARY`, `SERVER_REPLICATION_HOST`, `SERVER_REPLICATION_PORT`, `CLUSTER_TOKEN`, `SERVER_TERM`, `REPLICATION_TIMEOUT`.
- [x] Validate role and ports.
- [x] Add `Peer` dataclass and `parse_peers`.
- [x] Tests for TOML/env, invalid role, peers, standalone.
- [x] Commit: `feat: add replication cluster configuration`.

## Task 2: Durable log and deterministic operations

**Files:** `replication.py`, `file_store.py`, `tests/test_replication.py`, `tests/test_file_store.py`

- [x] Add `ReplicationLog` with `entries(term, idx, payload, committed)` and `meta`.
- [x] Methods: `next_index`, `append`, `mark_committed`, `get`, `pending`, `truncate_from`, `get_meta`, `set_meta`, `term`, `commit_index`, `last_index`.
- [x] Add `FileStore.plan_put_with_conflict`, `plan_delete_with_conflict`, `plan_user_create`, `plan_user_password`, `plan_mkdir`, `plan_rmdir`.
- [x] Add `FileStore.apply_operation` handling `file`, `user`, `share`, `setting`, `mkdir`, `rmdir`.
- [x] Add `state_hash`, `export_snapshot`, `import_snapshot`.
- [x] Tests for log persistence/idempotency, deterministic plans, exact apply, state hash, snapshot round trip.
- [x] Commit: `feat: add durable replication log and deterministic operations`.

## Task 3: Mutual TLS and replication protocol

**Files:** `tls.py`, `replication.py`, `tests/test_replication.py`

- [x] Extend `client_context(ca_file, cert_file, key_file)`.
- [x] Add JSON-line messages: `HELLO`, `HELLO_OK`, `RB`, `ACK`, `COMMIT`, `COMMITTED`, `ABORT`, `SNAP`.
- [x] Add `ReplicationServer` with mTLS, token validation, proposal storage, ordered commit, abort, snapshot import.
- [x] Retransmit proposals after transient failure.
- [x] Tests: mTLS round trip, plaintext rejected, bad token, duplicate RB, ordered commit.
- [x] Commit: `feat: add mutual TLS replication protocol`.

## Task 4: Primary and quorum

**Files:** `replication.py`, `tests/test_replication.py`

- [x] Add `NoQuorumError`.
- [x] Add `Replicator.replicate(operation)` with quorum, ACKs, timeout, retry, commit, abort.
- [x] Persist committed entries and `commit_index`.
- [x] Tests: 2/3 commit, one secondary down, no quorum, no local apply without quorum, retransmission.
- [x] Commit: `feat: require quorum before committing mutations`.

## Task 5: Server runtime integration

**Files:** `server_runtime.py`, `serv_fich_multithread.py`, `cli_fich.py`, `tests/test_server_runtime.py`, `tests/test_replication_integration.py`

- [x] `ServerRuntime(config, store, log)` creates `Replicator`/`ReplicationServer`.
- [x] Add `commit_operation` and `require_primary`.
- [x] Handlers use `plan_*` + `commit_operation`.
- [x] Secondary rejects `REGI`, `CHPW`, `UPLO`, `UPL2`, `DELE`, `MKDR`, `RMDR` with `ER13`.
- [x] Reads and login work on secondaries.
- [x] Add error codes 12 (no quorum) and 13 (not primary).
- [x] `serv_fich_multithread.py` uses `create_server(config)`.
- [x] Integration tests with three runtimes, 20 mutations, state hash convergence, one secondary down, no quorum, secondary rejection, restart.
- [x] Commit: `feat: wire replication into the server runtime`.

## Task 6: Docker and documentation

**Files:** `compose.yaml`, `compose.registry.yaml`, `.env.example`, docs, `AGENTS.md`

- [x] Compose: `server1` primary, `server2`/`server3` secondaries; ports 50012/60012 internally; only primary client port published.
- [x] Volumes `files/server1..3`; cert SANs for `server1..3`, `localhost`, `127.0.0.1`.
- [x] `CLUSTER_TOKEN`, `SERVER_PEERS`, `SERVER_PRIMARY`.
- [x] Document protocol, quorum, deterministic operations, snapshots, limitations.
- [x] Verify tests, Ruff, docs, `docker compose config`, `docker compose build`.
- [x] Commit: `docs: document replication, quorum, and cluster deployment`.

## Acceptance

- [x] Three replicas converge to the same `state_hash`.
- [x] Twenty mutations apply in the same order.
- [x] One secondary down does not block.
- [x] No quorum returns `ER12` and does not apply locally.
- [x] Secondary client mutations return `ER13`.
- [x] Replication requires TLS/mTLS.
- [x] Log survives restart.
- [x] Tests, Ruff, docs, Docker pass.
