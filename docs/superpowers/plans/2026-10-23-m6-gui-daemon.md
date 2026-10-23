# M6 Implementation Plan — Daemon, IPC, CLI Control, and Tkinter GUI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** A single background daemon owns synchronization; a Tkinter GUI and a CLI control the same daemon over authenticated local IPC. The GUI supports first-run setup, registration/login, settings, shares, status, tray, and autostart.

**Architecture:** `DaemonService` loads standard per-user configuration, owns `ClientSession`, `SyncWorker`, and `RemoteWatcher`, and exposes requests/events over `multiprocessing.connection` on a Unix socket or Windows named pipe. GUI and CLI are thin frontends. Close-to-tray hides the GUI; tray Quit stops both GUI and daemon.

**Tech Stack:** Python 3.10+, Tkinter/ttk, `pystray`, `Pillow`, `multiprocessing.connection`, `unittest`, TLS, PyInstaller.

## Decisions

1. Standard per-OS config path; `CONFIG_FILE` overrides.
2. Local IPC only: Unix socket or Windows named pipe, JSON messages, authkey file mode 0600.
3. One daemon and one GUI instance per user/state directory.
4. CLI controls the daemon; `--foreground` remains for direct debugging.
5. GUI close hides to tray; tray Quit stops GUI and daemon.
6. Passwords live only in daemon memory; settings never store them.
7. Share commands go through the daemon.
8. Packaging keeps CLI and GUI executables; `--daemon` mode runs from either bundle without a window.

## Task 1: Standard config and IPC

**Files:** `config.py`, `ipc.py`, tests

- [x] Add `default_config_path()` for Windows, Linux, and a sensible fallback.
- [x] `load_config()` uses the standard path when no path/`CONFIG_FILE` is given.
- [x] Add `save_client_config(path, client)` preserving `[server]`.
- [x] Add `ipc_address(state_dir)` and `ipc_key(state_dir)`.
- [x] Add `IpcServer`/`IpcClient` using `multiprocessing.connection` with authkey.
- [x] JSON request/response helpers; reject missing/invalid authkey.
- [x] Tests: config path, config save, socket/token, auth failure.
- [x] Commit: `feat: add standard config paths and local IPC`.

## Task 2: Daemon service

**Files:** `daemon_service.py`, `client_daemon.py`, tests

- [x] `DaemonService` owns config, `ClientSession`, `SyncWorker`, and event subscribers.
- [x] Actions: `status`, `login`, `register`, `logout`, `start`, `stop`, `shares`, `users`, `share`, `unshare`, `password`, `reload`, `shutdown`.
- [x] Thread-safe event broadcast with `subscribe` connections.
- [x] Single-instance lock; create/remove IPC socket and token.
- [x] `client_daemon.py` starts the service; supports `--config`, `--daemon`.
- [x] Tests with a real TLS server and temporary state/config.
- [x] Commit: `feat: add the synchronization daemon and IPC service`.

## Task 3: CLI control

**Files:** `cli_fich.py`, tests

- [x] `ensure_daemon()` starts `sys.executable --daemon` if IPC is unavailable.
- [x] Interactive default: login prompt, then status/event stream.
- [x] Commands: `status`, `login`, `logout`, `pause`, `resume`, `shares`, `share`, `unshare`, `password`, `quit`.
- [x] `--foreground` runs a direct debug worker; `--daemon` runs the daemon.
- [x] Keep `parse_client_args` compatibility for tests/legacy.
- [x] Tests for command parsing and fake daemon responses.
- [x] Commit: `feat: control the daemon from the CLI`.

## Task 4: GUI controller

**Files:** `gui_controller.py`, tests

- [x] `ensure_daemon()` and `IpcClient` connection.
- [x] Login/register/settings/share/pause actions in background threads.
- [x] Event subscription thread feeds a `queue.Queue`.
- [x] Standard config read/write.
- [x] Tests with a fake IPC client.
- [x] Commit: `feat: add the GUI controller`.

## Task 5: Tkinter, tray, autostart

**Files:** `gui_fich.py`, `gui_app.py`, `tray.py`, `autostart.py`, `single_instance.py`, assets

- [x] First-run/login/register view.
- [x] Settings and main status/share/log views.
- [x] Pause/resume/open folder/password actions.
- [x] Tray icon and menu: Show, Open folder, Pause/Resume, Quit.
- [x] Autostart Linux `.desktop` and Windows Run key.
- [x] Single instance for GUI.
- [x] Headless tests for lock/autostart; manual UI checklist.
- [x] Commit: `feat: add Tkinter GUI, tray, and autostart`.

## Task 6: Packaging, docs, verification

**Files:** `scripts/build_release_bundle.py`, `.github/workflows/release.yml`, `requirements.txt`, docs, `AGENTS.md`

- [x] Add `pystray` and `Pillow`.
- [x] Add `client-gui` component with `gui_fich.py`, `cloud-file-client-gui`, windowed mode.
- [x] Add GUI to release matrix; Linux needs `python3-tk`.
- [x] Ensure `--daemon` works from both bundles.
- [x] Document daemon/IPC, tray, autostart, config path, close vs quit, CLI commands.
- [x] Verify tests, Ruff, docs, Compose, PyInstaller local build.
- [x] Commit: `docs: document the daemon and desktop GUI`.

## Acceptance

- [x] GUI and CLI control the same daemon.
- [x] IPC is local and authenticated.
- [x] Close hides to tray; Quit stops GUI and daemon.
- [x] Login/register/settings/shares/status work from GUI.
- [x] CLI commands work against the daemon.
- [x] GUI bundle builds for Windows/Linux; Linux Tk dependency documented.
- [x] Tests, Ruff, docs, Docker, and PyInstaller build pass.
