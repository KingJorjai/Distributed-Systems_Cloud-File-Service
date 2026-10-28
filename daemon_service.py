"""Background synchronization daemon controlled over local IPC."""

import logging
import threading
import time
from pathlib import Path

from client_session import ClientSession, NoServerError, SyncError
from client_state import default_state_dir
from config import default_config_path, load_config
from ipc import IpcServer, ipc_address, ipc_key
from single_instance import InstanceLock
from sync_client import SyncWorker

logger = logging.getLogger(__name__)


class DaemonService:
    """Own the single synchronization worker and serve IPC requests."""

    def __init__(self, config_path=None):
        self.config_path = Path(config_path or default_config_path())
        self.config = load_config(self.config_path).client
        self.state_dir = Path(self.config.state_dir or default_state_dir())
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.lock = InstanceLock(self.state_dir / "daemon.lock")
        self.server = IpcServer(
            ipc_address(self.state_dir), ipc_key(self.state_dir), self._handle
        )
        self.worker = None
        self.session = None
        self.username = None
        self.password = None
        self.last_error = None
        self._subscribers = []
        self._subscribers_lock = threading.RLock()
        self._lock = threading.RLock()
        self._stop = threading.Event()

    def start(self):
        self.lock.acquire()
        self.server.start()

    def serve_forever(self):
        while not self._stop.is_set():
            time.sleep(0.5)

    def stop(self):
        self._stop.set()
        self._stop_worker()
        if self.session is not None:
            self.session.close()
            self.session = None
        if self.server is not None:
            self.server.close()
        self.lock.release()

    def _stop_worker(self):
        if self.worker is not None:
            self.worker.stop()
            self.worker = None

    def _make_worker(self):
        if self.username is None or self.password is None:
            raise SyncError(2, "Not logged in.")
        worker = SyncWorker(
            self.config.local_path, self.config, self.username, self.password
        )
        worker.event_callback = self._on_worker_event
        return worker

    def _on_worker_event(self, event):
        self._broadcast({"event": "worker", "data": event})
        self._broadcast({"event": "status", "data": self.status()})

    def status(self):
        with self._lock:
            worker_status = self.worker.status() if self.worker is not None else {}
            return {
                "logged_in": self.username is not None,
                "username": self.username,
                "running": bool(worker_status.get("running", False)),
                "endpoint": worker_status.get("endpoint"),
                "pending": int(worker_status.get("pending", 0)),
                "local_path": self.config.local_path,
                "last_error": self.last_error,
                "config_path": str(self.config_path),
            }

    def _management_session(self):
        if self.username is None or self.password is None:
            raise SyncError(2, "Not logged in.")
        if self.session is None:
            self.session = ClientSession(self.config)
        if self.session.socket is None:
            self.session.connect_and_login(self.username, self.password)
        return self.session

    def login(self, username, password):
        self._stop_worker()
        if self.session is not None:
            self.session.close()
        session = ClientSession(self.config)
        session.connect_and_login(username, password)
        logger.info("daemon login user=%s", username)
        self.session = session
        self.username = username
        self.password = password
        worker = self._make_worker()
        worker.start()
        self.worker = worker
        return self.status()

    def register(self, username, password):
        session = ClientSession(self.config)
        try:
            session.resolve_primary()
            session.register(username, password)
        finally:
            session.close()
        return {"registered": username}

    def logout(self):
        self._stop_worker()
        if self.session is not None:
            self.session.close()
        self.session = None
        logger.info("daemon logout")
        self.username = None
        self.password = None
        return self.status()

    def start_sync(self):
        with self._lock:
            if self.worker is not None and not self.worker.stop_event.is_set():
                return self.status()
            self.worker = self._make_worker()
            self.worker.start()
        return self.status()

    def stop_sync(self):
        self._stop_worker()
        return self.status()

    def shares(self):
        return [
            {
                "owner": share.owner,
                "path": share.path,
                "grantee": share.grantee,
                "access": share.access,
            }
            for share in self._management_session().shares()
        ]

    def users(self):
        return self._management_session().users()

    def share(self, path, grantee, access):
        self._management_session().share(path, grantee, access)
        return self.shares()

    def unshare(self, path, grantee):
        self._management_session().unshare(path, grantee)
        return self.shares()

    def change_password(self, old_password, new_password):
        self._management_session().change_password(old_password, new_password)
        self.password = new_password
        if self.worker is not None:
            self.worker.password = new_password
        return {"changed": True}

    def reload(self):
        self.config = load_config(self.config_path).client
        if self.worker is not None:
            self._stop_worker()
            self.worker = self._make_worker()
            self.worker.start()
        return self.status()

    def _handle(self, connection):
        while not self._stop.is_set():
            try:
                request = connection.recv()
            except (EOFError, OSError):
                return
            if not isinstance(request, dict):
                connection.send({"ok": False, "error": "invalid-request"})
                continue
            if request.get("action") == "subscribe":
                connection.send({"ok": True, "data": self.status()})
                self._subscribe(connection)
                return
            try:
                response = self.dispatch(request)
            except SyncError as error:
                response = {
                    "ok": False,
                    "error": "ER{}".format(error.code),
                    "message": str(error),
                }
            except (OSError, EOFError, NoServerError) as error:
                response = {"ok": False, "error": "connection", "message": str(error)}
            except Exception as error:
                response = {"ok": False, "error": "error", "message": str(error)}
            connection.send(response)

    def dispatch(self, request):
        action = request.get("action")
        if action == "status":
            return {"ok": True, "data": self.status()}
        if action == "login":
            return {
                "ok": True,
                "data": self.login(request["username"], request["password"]),
            }
        if action == "register":
            return {
                "ok": True,
                "data": self.register(request["username"], request["password"]),
            }
        if action == "logout":
            return {"ok": True, "data": self.logout()}
        if action == "start":
            return {"ok": True, "data": self.start_sync()}
        if action == "stop":
            return {"ok": True, "data": self.stop_sync()}
        if action == "shares":
            return {"ok": True, "data": self.shares()}
        if action == "users":
            return {"ok": True, "data": self.users()}
        if action == "share":
            return {
                "ok": True,
                "data": self.share(
                    request["path"], request["grantee"], request["access"]
                ),
            }
        if action == "unshare":
            return {
                "ok": True,
                "data": self.unshare(request["path"], request["grantee"]),
            }
        if action == "password":
            return {
                "ok": True,
                "data": self.change_password(
                    request["old_password"], request["new_password"]
                ),
            }
        if action == "reload":
            return {"ok": True, "data": self.reload()}
        if action == "shutdown":
            threading.Thread(target=self.stop, daemon=True).start()
            return {"ok": True, "data": {"shutdown": True}}
        return {"ok": False, "error": "unknown-action"}

    def _subscribe(self, connection):
        subscription = (connection, threading.Lock())
        with self._subscribers_lock:
            self._subscribers.append(subscription)
        try:
            while not self._stop.is_set():
                if connection.poll(0.5):
                    request = connection.recv()
                    if request.get("action") == "unsubscribe":
                        break
        except (EOFError, OSError):
            pass
        finally:
            with self._subscribers_lock:
                if subscription in self._subscribers:
                    self._subscribers.remove(subscription)

    def _broadcast(self, message):
        with self._subscribers_lock:
            subscribers = list(self._subscribers)
        for connection, lock in subscribers:
            try:
                with lock:
                    connection.send(message)
            except (OSError, EOFError):
                with self._subscribers_lock:
                    if (connection, lock) in self._subscribers:
                        self._subscribers.remove((connection, lock))
