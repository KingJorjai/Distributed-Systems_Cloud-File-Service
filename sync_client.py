import hashlib
import queue
import socket
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import szasar
from db_manager import ClientDB  


class SyncError(Exception):
    """Raised when the server rejects a synchronization request."""
    pass


class SyncConnection:
    """Manage the TCP connection used by the automatic synchronizer."""

    def __init__(self, server, port, user, password):
        """Initialize a connection configuration."""
        self.server = server
        self.port = port
        self.user = user
        self.password = password
        self.socket = None
        self.db = ClientDB() 

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

    def upload(self, filename, data):
        """Upload file data with revision control and conflict resolution."""
        
        info = self.db.get_file_info(filename)
        rev_local = info[0] if info else 0

        cmd = "{}{}?{}?{}\r\n".format(szasar.Command.Upload, filename, len(data), rev_local)
        self.socket.sendall(cmd.encode("ascii"))
        
        response = szasar.recvline(self.socket).decode("ascii")
        if response.startswith("ER"):
            raise SyncError(response)

        conflicto = None

        if response.startswith("CNFL"):
            conflicto = response[4:] 
            print(f"[!] Conflicto detectado en '{filename}'. Copia remota guardada como '{conflicto}'.")
            
            self._send_upload2(data)
            
            nuevo_hash = hashlib.sha256(data).hexdigest()
            self.db.update_file_info(filename, rev_local + 1, nuevo_hash)

        elif response.startswith("HASH"):
            hash_local = hashlib.sha256(data).hexdigest()
            self.socket.sendall(f"HASH{hash_local}\r\n".encode("ascii"))
            
            resp_hash = szasar.recvline(self.socket).decode("ascii")
            
            if resp_hash.startswith("OK_UP_TO_DATE"):
                return
            elif resp_hash.startswith("OK"):
                self._send_upload2(data)
                
                self.db.update_file_info(filename, rev_local + 1, hash_local)
            else:
                raise SyncError(f"Respuesta inesperada al enviar HASH: {resp_hash}")
                
        elif response.startswith("OK"):
            self._send_upload2(data)
            nuevo_hash = hashlib.sha256(data).hexdigest()
            self.db.update_file_info(filename, rev_local + 1, nuevo_hash)
            
        else:
            raise SyncError(f"Respuesta inesperada en Upload: {response}")

        if conflicto:
            self.download_conflict(conflicto)

    def _send_upload2(self, data):
        """Helper para enviar los datos reales del archivo."""
        self.socket.sendall((szasar.Command.Upload2 + "\r\n").encode("ascii"))
        self.socket.sendall(data)
        self._read_response()

    def download_conflict(self, filename_conflicto):
        """Descarga el fichero en conflicto."""
        print(f"[*] Pendiente descargar fichero en conflicto: {filename_conflicto}")
        pass

    def delete(self, filename):
        """Delete a file from the authenticated user's server directory."""
        self._command(szasar.Command.Delete + filename)
        # Opcional: borrar de la BD local si quieres mantenerla limpia

    def mkdir(self, dirname):
        """Create a directory in the authenticated user's server directory."""
        self._command(szasar.Command.MakeDir + dirname)

    def rmdir(self, dirname):
        """Delete a directory and its contents from the server directory."""
        self._command(szasar.Command.RemoveDir + dirname)

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
                elif action == "mkdir":
                    self.connection.mkdir(filename)
                elif action == "rmdir":
                    self.connection.rmdir(filename)
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