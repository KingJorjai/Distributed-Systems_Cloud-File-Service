"""Client-side subscription loop for server notifications."""

import socket
import threading
import time

from client_session import ClientSession, NoServerError, SyncError


class RemoteWatcher:
    """Keep a notification connection open and enqueue remote updates."""

    def __init__(self, worker):
        self.worker = worker
        self.stop_event = threading.Event()
        self.session = None
        self.thread = threading.Thread(
            target=self._run, name="remote-watcher", daemon=True
        )

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)

    def _run(self):
        while not self.stop_event.is_set():
            session = ClientSession(self.worker.config)
            self.session = session
            try:
                session.connect_and_login(
                    self.worker.username, self.worker.password
                )
                session.subscribe(self.worker.state.client_id)
                session.socket.settimeout(1.0)
                self.worker.remote_changes.put({"action": "reconcile"})
                while not self.stop_event.is_set():
                    try:
                        update = session.read_notification()
                    except socket.timeout:
                        continue
                    self.worker.remote_changes.put(update)
            except (OSError, EOFError, SyncError, NoServerError):
                if not self.stop_event.is_set():
                    time.sleep(1)
            finally:
                session.close()
                self.session = None
