import queue
import socket
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import szasar


class SyncError(Exception):
    pass


class SyncConnection:
    def __init__(self, server, port, user, password):
        self.server = server
        self.port = port
        self.user = user
        self.password = password
        self.socket = None

    def connect(self):
        self.socket = socket.create_connection((self.server, self.port), timeout=10)
        self._command(szasar.Command.User + self.user)
        self._command(szasar.Command.Password + self.password)

    def close(self):
        if self.socket is not None:
            try:
                self._command(szasar.Command.Exit)
            except (OSError, EOFError, SyncError):
                pass
            self.socket.close()
            self.socket = None

    def upload(self, filename, data):
        self._command("{}{}?{}".format(szasar.Command.Upload, filename, len(data)))
        self.socket.sendall((szasar.Command.Upload2 + "\r\n").encode("ascii"))
        self.socket.sendall(data)
        self._read_response()

    def delete(self, filename):
        self._command(szasar.Command.Delete + filename)

    def _command(self, command):
        self.socket.sendall((command + "\r\n").encode("ascii"))
        self._read_response()

    def _read_response(self):
        response = szasar.recvline(self.socket).decode("ascii")
        if response.startswith("ER"):
            raise SyncError(response)
        if not response.startswith("OK"):
            raise SyncError("Respuesta inesperada: {}".format(response))
        return response


class ChangeHandler(FileSystemEventHandler):
    def __init__(self, root, changes, is_ignored):
        self.root = Path(root).resolve()
        self.changes = changes
        self.is_ignored = is_ignored

    def on_created(self, event):
        self._enqueue_upload(event)

    def on_modified(self, event):
        self._enqueue_upload(event)

    def on_deleted(self, event):
        if not event.is_directory and not self.is_ignored(
            self._relative(event.src_path)
        ):
            self.changes.put(("delete", self._relative(event.src_path)))

    def on_moved(self, event):
        if event.is_directory:
            return
        self.changes.put(("delete", self._relative(event.src_path)))
        self.changes.put(("upload", self._relative(event.dest_path)))

    def _enqueue_upload(self, event):
        if not event.is_directory and not self.is_ignored(
            self._relative(event.src_path)
        ):
            self.changes.put(("upload", self._relative(event.src_path)))

    def _relative(self, path):
        return Path(path).resolve().relative_to(self.root).as_posix()


class SyncWorker:
    def __init__(self, root, server, port, user, password):
        self.root = Path(root).resolve()
        self.connection = SyncConnection(server, port, user, password)
        self.changes = queue.Queue()
        self.ignored = {}
        self.ignored_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.worker = threading.Thread(
            target=self._run, name="sync-worker", daemon=True
        )
        self.observer = Observer()
        self.handler = ChangeHandler(self.root, self.changes, self._is_ignored)

    def start(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.connection.connect()
        self.observer.schedule(self.handler, str(self.root), recursive=False)
        self.observer.start()
        for path in self.root.iterdir():
            if path.is_file():
                self.changes.put(("upload", path.name))
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.observer.stop()
        self.observer.join(timeout=5)
        self.worker.join(timeout=5)
        self.connection.close()

    def ignore(self, filename):
        with self.ignored_lock:
            self.ignored[filename] = time.monotonic() + 2

    def _is_ignored(self, filename):
        with self.ignored_lock:
            expires = self.ignored.get(filename)
            if expires is None:
                return False
            if expires < time.monotonic():
                del self.ignored[filename]
                return False
            return True

    def _run(self):
        while not self.stop_event.is_set():
            try:
                action, filename = self.changes.get(timeout=0.2)
            except queue.Empty:
                continue
            time.sleep(0.5)
            action, filename = self._latest_for(filename, action)
            try:
                if action == "upload":
                    self._upload_when_stable(filename)
                else:
                    self.connection.delete(filename)
            except (OSError, EOFError, socket.timeout, SyncError):
                if not self.stop_event.is_set():
                    self.connection.close()
                    try:
                        self.connection.connect()
                    except (OSError, EOFError, socket.timeout, SyncError):
                        pass
                    self.changes.put((action, filename))
                    time.sleep(1)

    def _latest_for(self, filename, action):
        pending = []
        try:
            while True:
                next_action, next_filename = self.changes.get_nowait()
                if next_filename == filename:
                    action = next_action
                else:
                    pending.append((next_action, next_filename))
        except queue.Empty:
            for change in pending:
                self.changes.put(change)
        return action, filename

    def _upload_when_stable(self, filename):
        path = self.root / filename
        if not path.is_file():
            return
        first = path.stat()
        time.sleep(0.2)
        second = path.stat()
        if (first.st_size, first.st_mtime_ns) != (second.st_size, second.st_mtime_ns):
            self.changes.put(("upload", filename))
            return
        self.connection.upload(filename, path.read_bytes())
