# M7 Implementation Plan — HTTPS Web Administration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** HTTPS-only admin panel served by each node, with admin login, user management, share revocation, registration settings, replication status, active sessions, and demo-only step-down.

**Architecture:** `AdminService` is the sole mutation path for the web UI and calls `ServerRuntime.commit_operation`, so admin actions replicate and require quorum. `AdminServer` uses stdlib `ThreadingHTTPServer` and the existing server TLS certificate. Sessions are server-side; cookies are `HttpOnly`/`SameSite=Strict`/`Secure`; POSTs require CSRF. Secondary nodes are read-only and redirect mutations to the primary admin URL.

**Tech Stack:** Python 3.10+, stdlib `http.server`, `ssl`, `http.cookies`, `hmac`, SQLite, `unittest`, `trustme`, Docker Compose.

## Decisions

1. Admin web disabled by default; enable with `SERVER_ADMIN_ENABLED=true`.
2. HTTPS only; bind `127.0.0.1` by default, `0.0.0.0` in Docker.
3. Only `role=admin` accounts can log in.
4. Admin mutations use the replicated operation path and quorum.
5. Secondary nodes show status and redirect mutations to the primary admin URL.
6. `step_down` requires `ALLOW_ADMIN_FAILOVER=1`.
7. Disabling a user blocks subsequent client commands.
8. No file contents or password hashes are exposed.
9. Registration toggle is a replicated setting.
10. Bootstrap admins remain `sar`/`sza`.

## Task 1: Config, operations, AdminService

**Files:** `config.py`, `file_store.py`, `admin_service.py`, tests

- [x] Add `admin_enabled`, `admin_host`, `admin_port`, `admin_addresses`, `allow_admin_failover`, `admin_session_timeout` to `ServerConfig`.
- [x] Add env: `SERVER_ADMIN_ENABLED`, `SERVER_ADMIN_HOST`, `SERVER_ADMIN_PORT`, `SERVER_ADMIN_ADDRESSES`, `ALLOW_ADMIN_FAILOVER`, `ADMIN_SESSION_TIMEOUT`.
- [x] Add `FileStore.plan_user_disabled`, `plan_setting`; apply `user_state`/`setting`.
- [x] Add `registration_enabled(default)` helper.
- [x] Add `AdminService` with `authenticate`, `status`, `users`, `create_user`, `set_user_disabled`, `reset_password`, `shares`, `revoke_share`, `set_registration`, `step_down`, `audit`.
- [x] Prevent self-disable and disabling the last enabled admin.
- [x] Admin mutations call `runtime.commit_operation`; follower/no-quorum errors propagate.
- [x] Tests for operations, settings replication, last-admin protection.
- [x] Commit: `feat: add admin operations and replicated settings`.

## Task 2: HTTPS admin server, sessions, CSRF

**Files:** `server_admin.py`, tests

- [x] Add `AdminServer` wrapping `ThreadingHTTPServer` with TLS.
- [x] Add `AdminSessions` with expiry, cookie flags, and CSRF tokens.
- [x] Add login/logout, dashboard, users, shares, settings, step-down, APIs, health.
- [x] Escape HTML, set CSP/nosniff/no-referrer/no-store.
- [x] Secondary mutations redirect to primary admin URL or return 409.
- [x] Tests: HTTPS login, cookie flags, plaintext rejection, role check, CSRF, user actions, share revoke, registration toggle, redirects, step-down disabled.
- [x] Commit: `feat: add HTTPS admin server with sessions and CSRF`.

## Task 3: Runtime integration and status

**Files:** `server_runtime.py`, `election.py`, tests

- [x] Create `AdminService`/`AdminServer` when enabled.
- [x] Add active-session counter and status fields.
- [x] Add `ClusterNode.step_down()`.
- [x] Reject disabled users before Main commands; disconnect their subscriptions.
- [x] Registration uses replicated setting with config fallback.
- [x] Tests: status, disabled user, step-down election, replicated user creation.
- [x] Commit: `feat: expose admin status and step-down control`.

## Task 4: Docker, TLS, docs, verification

**Files:** `docker/server.Dockerfile`, `compose.yaml`, `.env.example`, docs, `AGENTS.md`

- [x] Copy `server_admin.py` in the server image.
- [x] Compose admin env and primary published port; `SERVER_ADMIN_ADDRESSES`.
- [x] Document admin URL, login, security, step-down, self-signed cert warning.
- [x] Add page to MkDocs/PDF.
- [x] Verify tests, Ruff, docs, Compose, Docker, and browser manual checklist.
- [x] Commit: `docs: document HTTPS server administration`.

## Acceptance

- [x] HTTPS-only admin panel.
- [x] Admin-only login and CSRF-protected writes.
- [x] User create/disable/enable/reset, share revoke, registration toggle.
- [x] Status includes role, term, primary, indexes, sessions, users, shares.
- [x] Secondary actions redirect to primary.
- [x] Step-down disabled by default.
- [x] Disabled users cannot continue commands.
- [x] Admin mutations replicate and respect quorum.
- [x] Tests, Ruff, docs, Docker, and manual browser checks pass.
