import queue
import socket
import ssl
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from client_session import ClientSession, SyncError
from client_state import ClientState


class ChangeHandler(FileSystemEventHandler):
    """Convert local filesystem events into synchronization queue entries."""

    def __init__(self, root, changes, is_ignored):
        """Initialize an event handler for a local synchronization root."""
        self.root = Path(root).resolve()
        self.changes = changes
        self.is_ignored = is_ignored

    def on_created(self, event):
        """Queue a newly created file or directory for synchronization."""
        if event.is_directory:
            self.changes.put(("mkdir", self._relative(event.src_path)))
            return
        self._enqueue_upload(event)

    def on_modified(self, event):
        """Queue a modified file for upload."""
        self._enqueue_upload(event)

    def on_deleted(self, event):
        """Queue deletion of a removed file or directory."""
        filename = self._relative(event.src_path)
        if event.is_directory:
            self.changes.put(("rmdir", filename))
        elif not self.is_ignored(filename):
            self.changes.put(("delete", filename))

    def on_moved(self, event):
        """Queue synchronization of a renamed file or directory."""
        if event.is_directory:
            self.changes.put(("rmdir", self._relative(event.src_path)))
            destination = Path(event.dest_path)
            self.changes.put(("mkdir", self._relative(event.dest_path)))
            for path in sorted(destination.rglob("*")):
                relative = self._relative(path)
                if path.is_dir():
                    self.changes.put(("mkdir", relative))
                elif path.is_file():
                    self.changes.put(("upload", relative))
            return
        self.changes.put(("delete", self._relative(event.src_path)))
        self.changes.put(("upload", self._relative(event.dest_path)))

    def _enqueue_upload(self, event):
        """Queue an upload unless the event belongs to an ignored file."""
        if not event.is_directory and not self.is_ignored(
            self._relative(event.src_path)
        ):
            self.changes.put(("upload", self._relative(event.src_path)))

    def _relative(self, path):
        """Return an event path relative to the synchronization root."""
        return Path(path).resolve().relative_to(self.root).as_posix()


class SyncWorker:
    """Watch a local folder and synchronize its changes with the server."""

    def __init__(self, root, config, username, password):
        """Initialize the watcher, persistent state, and network worker."""
        self.root = Path(root).resolve()
        self.config = config
        self.username = username
        self.password = password
        self.state = ClientState(
            username, config.server, config.port, self.root, config.state_dir
        )
        self.session = ClientSession(config)
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
        """Start watching the folder and queue existing files for upload."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.session.connect()
        self.session.login(self.username, self.password)
        self.observer.schedule(self.handler, str(self.root), recursive=True)
        self.observer.start()
        paths = sorted(self.root.rglob("*"))
        for path in paths:
            if path.is_dir():
                self.changes.put(("mkdir", path.relative_to(self.root).as_posix()))
        for path in paths:
            if path.is_file():
                self.changes.put(("upload", path.relative_to(self.root).as_posix()))
        self.worker.start()

    def stop(self):
        """Stop the watcher and close the synchronization connection."""
        self.stop_event.set()
        self.observer.stop()
        self.observer.join(timeout=5)
        self.worker.join(timeout=5)
        self.session.close()
        self.state.close()

    def ignore(self, filename):
        """Temporarily ignore events caused by a manual download."""
        with self.ignored_lock:
            self.ignored[filename] = time.monotonic() + 2

    def _is_ignored(self, filename):
        """Return whether a file is currently suppressed from synchronization."""
        with self.ignored_lock:
            expires = self.ignored.get(filename)
            if expires is None:
                return False
            if expires < time.monotonic():
                del self.ignored[filename]
                return False
            return True

    def _run(self):
        """Consume queued changes and retry transient network failures."""
        while not self.stop_event.is_set():
            pending = self.state.pending()
            if pending:
                change = pending[0]
                action = change["action"]
                filename = change["path"]
                change_id = change["id"]
            else:
                try:
                    action, filename = self.changes.get(timeout=0.2)
                except queue.Empty:
                    continue
                time.sleep(0.5)
                action, filename = self._latest_for(filename, action)
                change_id = self.state.enqueue(action, self.username, filename)

            try:
                self._perform(action, filename)
            except (OSError, EOFError, socket.timeout, ssl.SSLError, SyncError):
                if not self.stop_event.is_set():
                    self._reconnect()
                    time.sleep(1)
            else:
                self.state.ack(change_id)

    def _reconnect(self):
        try:
            self.session.close()
        except (OSError, EOFError, ssl.SSLError, SyncError):
            pass
        try:
            self.session.connect()
            self.session.login(self.username, self.password)
        except (OSError, EOFError, ssl.SSLError, SyncError):
            pass

    def _perform(self, action, filename):
        if action == "upload":
            self._upload_when_stable(filename)
        elif action == "mkdir":
            self.session.mkdir(self.username, filename)
        elif action == "rmdir":
            self.session.rmdir(self.username, filename)
        else:
            self.session.delete(self.username, filename)

    def _latest_for(self, filename, action):
        """Coalesce queued changes for one filename into its latest action."""
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
        """Upload a file only after two stable filesystem observations."""
        path = self.root / filename
        if not path.is_file():
            return
        first = path.stat()
        time.sleep(0.2)
        second = path.stat()
        if (first.st_size, first.st_mtime_ns) != (second.st_size, second.st_mtime_ns):
            self.changes.put(("upload", filename))
            return
        self.session.upload(self.username, filename, path.read_bytes())
