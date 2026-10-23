# Changelog

All notable changes are recorded here. The project uses `MAJOR.MINOR.PATCH`:

- `0.x.y` while it is a proof of concept;
- a new minor for each milestone;
- a patch for fixes and maintenance;
- `1.0.0` only when the final delivery is validated end to end.

Build metadata is kept outside Git tags, for example
`cloud-file-service-...-v0.11.3-build.42.zip`.

## [0.11.3] - 2026-10-23

- Include `version.py` in the server and client Docker images.
- Verify the Docker failover, post-failover upload, and rejoin demo again.
- Fall back to minimizing the window when the Linux tray cannot dock.

## [0.11.2] - 2026-10-23

- Stabilize the replication convergence test timings on slow CI runners.

## [0.11.1] - 2026-10-23

M8 delivery fixes.

- Serialize replication snapshots with applied commits so a transient
  heartbeat snapshot cannot erase newer replica state.
- Ignore snapshots at or below a replica's already applied index.
- Make replication tests deterministic under slower CI runners.
- Close failed runtimes and stores before temporary-directory cleanup on
  Windows.
- Pin `pymdown-extensions` to a version compatible with the installed
  `mkdocstrings` release.

## [0.11.0] - 2026-10-23

M8 — final delivery preparation.

- Final English report with architecture, decisions, tests, results, and
  pending work.
- Beamer presentation and `scripts/build_slides.sh`.
- Reproducible local and Docker failover demos.
- Documentation/PDF integration for report, demo, and presentation.
- Versioning policy and release checks.

## [0.10.0] - 2026-10-23

M7 — HTTPS server administration.

- Replicated admin operations for users, shares, registration settings, and
  demo step-down.
- HTTPS panel with server-side sessions, CSRF protection, audit log, and
  secondary redirects.
- Disabled-user enforcement and active-session status.

## [0.9.0] - 2026-10-23

M6 — desktop client and daemon.

- Tkinter GUI, tray, autostart, and single-instance handling.
- Background daemon over authenticated Unix socket/named pipe IPC.
- CLI control of the same daemon.
- Portable GUI/client/server bundles.

## [0.8.0] - 2026-10-23

M5 — shares and notifications.

- Cross-user `ro`/`rw` shares and directory prefixes.
- `SHAR`, `UNSH`, `SHRS`, `SUBS`, and `UPDT`.
- Shared local namespace, conflict copies, revocation, and reconnect
  reconciliation.

## [0.7.0] - 2026-10-23

M4 — election, failover, and rejoin.

- Heartbeats, persistent terms, majority election, and fencing.
- `PRIM` client redirection and post-failover reconciliation.
- Automatic snapshot rejoin for returning nodes.

## [0.6.0] - 2026-10-23

M3 — passive replication.

- Deterministic operations, durable `(term, index)` log, and 2/3 quorum.
- mTLS replication, commit/apply separation, and snapshot foundations.
- Three-server Docker cluster.

## [0.5.0] - 2026-10-23

M2 — reconciliation and conflicts.

- Startup manifest reconciliation and tombstones.
- Conflict copies for stale uploads and deletes.
- Durable client identity and local conflict preservation.

## [0.4.0] - 2026-10-23

M1 — foundations.

- TLS transport, strict certificate verification, and development cert script.
- SQLite users/files/shares/settings with ACLs.
- Registration, login, manifest, client state, and durable outbox.

## [0.3.0] - 2026-10-20

M0 — baseline.

- Course references and internal roadmap.
- MkDocs exclusions and CI baseline.
- Reproducible development environment.

## [0.2.1] - 2026-10-07

- Fix client CLI ignoring the port with three arguments.

## [0.2.0] - 2026-10-07

- Self-contained client/server bundles and release pipeline.

## [0.1.0] - 2026-10-02

- Initial documented synchronization client/server baseline.
