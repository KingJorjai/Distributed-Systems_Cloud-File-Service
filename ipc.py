"""Authenticated local IPC for the client daemon and frontends."""

import hashlib
import json
import os
import secrets
import threading
from multiprocessing.connection import AuthenticationError, Client, Listener
from pathlib import Path


def ipc_address(state_dir):
    """Return the per-user local IPC address for a state directory."""
    state = Path(state_dir).resolve()
    state.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        digest = hashlib.sha256(
            "{}:{}".format(os.environ.get("USERNAME", ""), state).encode("utf-8")
        ).hexdigest()[:16]
        return r"\\.\pipe\cloudfs-" + digest
    return str(state / "daemon.sock")


def ipc_key(state_dir):
    """Read or create the shared IPC authentication key."""
    state = Path(state_dir).resolve()
    state.mkdir(parents=True, exist_ok=True)
    path = state / "daemon.key"
    try:
        return path.read_bytes()
    except FileNotFoundError:
        key = secrets.token_bytes(32)
        descriptor = os.open(
            str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        with os.fdopen(descriptor, "wb") as key_file:
            key_file.write(key)
        return key


class IpcServer:
    """Accept local IPC connections and dispatch them to a handler."""

    def __init__(self, address, key, handler):
        self.address = address
        self.key = key
        self.handler = handler
        self._listener = None
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        if isinstance(self.address, str) and not self.address.startswith("\\\\"):
            try:
                os.unlink(self.address)
            except FileNotFoundError:
                pass
        self._listener = Listener(self.address, authkey=self.key)
        self._thread = threading.Thread(
            target=self._accept, name="ipc-server", daemon=True
        )
        self._thread.start()

    def _accept(self):
        while not self._stop.is_set():
            try:
                connection = self._listener.accept()
            except AuthenticationError:
                continue
            except (OSError, EOFError):
                break
            thread = threading.Thread(
                target=self._serve, args=(connection,), daemon=True
            )
            thread.start()

    def _serve(self, connection):
        try:
            self.handler(connection)
        except (OSError, EOFError, ValueError, json.JSONDecodeError):
            pass
        finally:
            try:
                connection.close()
            except OSError:
                pass

    def close(self):
        self._stop.set()
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass
            self._listener = None
        if self._thread is not None:
            self._thread.join(timeout=2)
        if isinstance(self.address, str) and not self.address.startswith("\\\\"):
            try:
                os.unlink(self.address)
            except FileNotFoundError:
                pass


class IpcClient:
    """Synchronous frontend connection to the daemon."""

    def __init__(self, address, key, timeout=5):
        self.connection = Client(address, authkey=key)
        self.timeout = timeout

    def request(self, message):
        self.connection.send(message)
        if not self.connection.poll(self.timeout):
            raise TimeoutError("The daemon did not answer in time.")
        response = self.connection.recv()
        if not isinstance(response, dict):
            raise ValueError("Malformed daemon response.")
        return response

    def send(self, message):
        self.connection.send(message)

    def recv(self):
        return self.connection.recv()

    def close(self):
        try:
            self.connection.close()
        except OSError:
            pass
