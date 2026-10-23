import hashlib
import os
import queue
import socket
import ssl
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from client_session import ClientSession, NoServerError, SyncError
from client_state import ClientState
from file_store import ManifestEntry


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
        """Reconcile once with the server, then watch for new changes."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.session.connect_and_login(self.username, self.password)
        self.reconcile()
        self.observer.schedule(self.handler, str(self.root), recursive=True)
        self.observer.start()
        self.worker.start()

    def stop(self):
        """Stop the watcher and close the synchronization connection."""
        if self.stop_event.is_set():
            return
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

    def _local_files(self):
        result = {}
        for path in self.root.rglob("*"):
            if not path.is_file() or path.name.startswith(".download-"):
                continue
            relative = path.relative_to(self.root).as_posix()
            data = path.read_bytes()
            result[relative] = {
                "digest": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        return result

    def reconcile(self):
        """Apply the manifest, local files, and last known state."""
        remote = {
            entry.path: entry
            for entry in self.session.sync()
            if entry.owner == self.username
        }
        local = self._local_files()
        state = {
            entry["path"]: entry
            for entry in self.state.list_files()
            if entry["owner"] == self.username
        }
        for path in sorted(set(remote) | set(local) | set(state)):
            self._reconcile_path(
                path, remote.get(path), local.get(path), state.get(path)
            )
        self.state.clear_outbox()

    def _reconcile_path(self, path, remote_entry, local_entry, state_entry):
        if (
            remote_entry is not None
            and local_entry is not None
            and remote_entry.digest == local_entry["digest"]
        ):
            self.state.set_file(remote_entry)
            return

        if remote_entry is not None and not remote_entry.deleted:
            if local_entry is not None:
                if state_entry is None:
                    self._upload(path, 0)
                elif local_entry["digest"] != state_entry["digest"]:
                    self._upload(path, state_entry["rev"])
                elif remote_entry.rev != state_entry["rev"]:
                    self._download(remote_entry)
                else:
                    self.state.set_file(remote_entry)
                return

            if state_entry is None or state_entry["deleted"]:
                self._download(remote_entry)
            else:
                self._delete_remote(path, state_entry)
            return

        if remote_entry is not None and remote_entry.deleted:
            if local_entry is not None:
                if state_entry is None or state_entry["deleted"]:
                    expected = state_entry["rev"] if state_entry else 0
                    self._upload(path, expected)
                elif local_entry["digest"] == state_entry["digest"]:
                    self._delete_local(path, remote_entry)
                else:
                    self._upload(path, state_entry["rev"])
            else:
                self.state.set_file(remote_entry)
            return

        if local_entry is not None:
            expected = state_entry["rev"] if state_entry else 0
            self._upload(path, expected)
        elif state_entry is not None:
            self.state.delete_file(self.username, path)

    def _upload(self, path, expected_rev):
        data = (self.root / path).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        result = self.session.upload(
            self.username,
            path,
            data,
            rev=expected_rev,
            digest=digest,
            client_id=self.state.client_id,
        )
        self._apply_upload_result(path, digest, len(data), result)

    def _apply_upload_result(self, path, digest, size, result):
        state_entry = self.state.get_file(self.username, path)
        revision = result.rev
        if revision is None:
            revision = state_entry["rev"] + 1 if state_entry else 1
        self.state.set_file(
            ManifestEntry(
                owner=self.username,
                path=path,
                rev=revision,
                digest=digest,
                size=size,
                deleted=False,
                access="rw",
            )
        )
        if result.conflict_path is not None:
            self._save_conflict(result.conflict_path)

    def _save_conflict(self, conflict_path):
        data = self.session.download(self.username, conflict_path)
        target = self.root / conflict_path
        if target.exists() and target.read_bytes() != data:
            target = self._local_conflict_path(conflict_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(".download-" + target.name)
        temporary.write_bytes(data)
        os.replace(temporary, target)
        self.ignore(target.relative_to(self.root).as_posix())
        if target.relative_to(self.root).as_posix() != conflict_path:
            return
        try:
            remote = self.session.stat(self.username, conflict_path)
        except SyncError:
            return
        self.state.set_file(
            ManifestEntry(
                owner=self.username,
                path=conflict_path,
                rev=remote.rev,
                digest=remote.digest,
                size=remote.size,
                deleted=False,
                access="rw",
            )
        )

    def _local_conflict_path(self, path):
        candidate = Path(path)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        client = self.state.client_id[:8]
        name = "{} (local conflict {} {}){}".format(
            candidate.stem, client, stamp, candidate.suffix
        )
        result = candidate.with_name(name)
        counter = 1
        while (self.root / result).exists():
            name = "{} (local conflict {} {}-{}){}".format(
                candidate.stem, client, stamp, counter, candidate.suffix
            )
            result = candidate.with_name(name)
            counter += 1
        return result

    def _download(self, entry):
        data = self.session.download(self.username, entry.path)
        target = self.root / entry.path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(".download-" + target.name)
        temporary.write_bytes(data)
        os.replace(temporary, target)
        self.state.set_file(entry)
        self.ignore(entry.path)

    def _delete_remote(self, path, state_entry):
        result = self.session.delete(
            self.username,
            path,
            rev=state_entry["rev"],
            client_id=self.state.client_id,
        )
        revision = result.rev
        if revision is None:
            revision = state_entry["rev"] + 1
        self.state.set_file(
            ManifestEntry(
                owner=self.username,
                path=path,
                rev=revision,
                digest=hashlib.sha256(b"").hexdigest(),
                size=0,
                deleted=True,
                access="rw",
            )
        )
        if result.conflict_path is not None:
            self._save_conflict(result.conflict_path)

    def _delete_local(self, path, remote_entry):
        target = self.root / path
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        self.state.set_file(remote_entry)
        self.ignore(path)
        self._remove_empty_parents(target.parent)

    def _remove_empty_parents(self, directory):
        while directory != self.root and self.root in directory.parents:
            try:
                directory.rmdir()
            except OSError:
                return
            directory = directory.parent

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
            self.session.connect_and_login(self.username, self.password)
            self.reconcile()
        except (OSError, EOFError, ssl.SSLError, SyncError, NoServerError):
            pass

    def _perform(self, action, filename):
        if action == "upload":
            self._upload_when_stable(filename)
        elif action == "mkdir":
            self.session.mkdir(self.username, filename)
        elif action == "rmdir":
            self._remove_remote_tree(filename)
        else:
            self._remove_local_file(filename)

    def _remove_remote_tree(self, filename):
        prefix = filename.rstrip("/")
        matches = [
            entry
            for entry in self.state.list_files()
            if entry["owner"] == self.username
            and (entry["path"] == prefix or entry["path"].startswith(prefix + "/"))
        ]
        if not matches:
            return
        self.session.rmdir(self.username, prefix)
        self.state.delete_tree(self.username, prefix)

    def _remove_local_file(self, filename):
        state_entry = self.state.get_file(self.username, filename)
        if state_entry is None or state_entry["deleted"]:
            return
        self._delete_remote(filename, state_entry)

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
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        state_entry = self.state.get_file(self.username, filename)
        if (
            state_entry is not None
            and not state_entry["deleted"]
            and state_entry["digest"] == digest
        ):
            return
        expected_rev = state_entry["rev"] if state_entry else 0
        result = self.session.upload(
            self.username,
            filename,
            data,
            rev=expected_rev,
            digest=digest,
            client_id=self.state.client_id,
        )
        self._apply_upload_result(filename, digest, len(data), result)
