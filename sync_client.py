import queue
import socket
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import szasar


class SyncError(Exception):
    """Raised when the server rejects a synchronization request."""

    pass

# TODO Generales
# 1. Implementar DB del cliente (fichero | rev | hash)
# 2. Cambios a upload (Estan comentados mas abajo)
class SyncConnection:
    """Manage the TCP connection used by the automatic synchronizer."""

    def __init__(self, server, port, user, password):
        """Initialize a connection configuration.

        Args:
            server: Server hostname or IP address.
            port: Server TCP port.
            user: Username used for authentication.
            password: Password used for authentication.
        """
        self.server = server
        self.port = port
        self.user = user
        self.password = password
        self.socket = None

    def connect(self):
        """Open the socket and authenticate with the server."""
        self.socket = socket.create_connection((self.server, self.port), timeout=10)
        self._command(szasar.Command.User + self.user)
        self._command(szasar.Command.Password + self.password)

    def close(self):
        """Close the connection, notifying the server when possible."""
        if self.socket is not None:
            try:
                self._command(szasar.Command.Exit)
            except (OSError, EOFError, SyncError):
                pass
            self.socket.close()
            self.socket = None
    # Modificaciones TODO a upload
    # 1. Enviar el rev del fichero al servidor
    # 2. Esperar respuesta
    # 3. En caso de conflicto
    #   3.1 Almacenar el nombre del fichero en conflicto y, al final descargarlo
    # 4. Mandar hash del fichero
    # 5. Esperar respuesta
    # 6. Si da permiso el servidor subir archivo
    # 7. Si ha habido conflicto descargar fichero en conflicto
    def upload(self, filename, data):
        """Upload file data to the authenticated user's server directory."""
        self._command("{}{}?{}".format(szasar.Command.Upload, filename, len(data)))
        self.socket.sendall((szasar.Command.Upload2 + "\r\n").encode("ascii"))
        self.socket.sendall(data)
        self._read_response()

    def delete(self, filename):
        """Delete a file from the authenticated user's server directory."""
        self._command(szasar.Command.Delete + filename)

    def _command(self, command):
        """Send a line-based protocol command and validate its response."""
        self.socket.sendall((command + "\r\n").encode("ascii"))
        self._read_response()

    def _read_response(self):
        """Read one server response and raise for errors."""
        response = szasar.recvline(self.socket).decode("ascii")
        if response.startswith("ER"):
            raise SyncError(response)
        if not response.startswith("OK"):
            raise SyncError("Respuesta inesperada: {}".format(response))
        return response


class ChangeHandler(FileSystemEventHandler):
    """Convert local filesystem events into synchronization queue entries."""

    def __init__(self, root, changes, is_ignored):
        """Initialize an event handler for a local synchronization root."""
        self.root = Path(root).resolve()
        self.changes = changes
        self.is_ignored = is_ignored

    def on_created(self, event):
        """Queue a newly created file for upload."""
        self._enqueue_upload(event)

    def on_modified(self, event):
        """Queue a modified file for upload."""
        self._enqueue_upload(event)

    def on_deleted(self, event):
        """Queue deletion of a removed file."""
        if not event.is_directory and not self.is_ignored(
            self._relative(event.src_path)
        ):
            self.changes.put(("delete", self._relative(event.src_path)))

    def on_moved(self, event):
        """Queue the source deletion and destination upload of a rename."""
        if event.is_directory:
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

    def __init__(self, root, server, port, user, password):
        """Initialize the watcher, event queue, and network worker."""
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
        """Start watching the folder and queue existing files for upload."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.connection.connect()
        self.observer.schedule(self.handler, str(self.root), recursive=False)
        self.observer.start()
        for path in self.root.iterdir():
            if path.is_file():
                self.changes.put(("upload", path.name))
        self.worker.start()

    def stop(self):
        """Stop the watcher and close the synchronization connection."""
        self.stop_event.set()
        self.observer.stop()
        self.observer.join(timeout=5)
        self.worker.join(timeout=5)
        self.connection.close()

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
        self.connection.upload(filename, path.read_bytes())
