import hashlib
import os
import queue
import shutil
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
from remote_watcher import RemoteWatcher


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
        self.remote_changes = queue.Queue()
        self.ignored = {}
        self.ignored_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.worker = threading.Thread(
            target=self._run, name="sync-worker", daemon=True
        )
        self.observer = Observer()
        self.handler = ChangeHandler(self.root, self.changes, self._is_ignored)
        self.share_accesses = {}
        self.watcher = RemoteWatcher(self)

    def start(self):
        """Reconcile once with the server, then watch for new changes."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.session.connect_and_login(self.username, self.password)
        self._load_shares()
        self.reconcile()
        self.observer.schedule(self.handler, str(self.root), recursive=True)
        self.observer.start()
        self.worker.start()
        self.watcher.start()

    def stop(self):
        """Stop the watcher and close the synchronization connection."""
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        self.watcher.stop()
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

    def _local_path(self, owner, path):
        if owner == self.username:
            return self.root / path
        return self.root / "shared" / owner / path

    def _owner_path(self, local_relative):
        parts = Path(local_relative).parts
        if len(parts) >= 3 and parts[0] == "shared":
            return parts[1], "/".join(parts[2:])
        return self.username, local_relative

    def _load_shares(self):
        self.share_accesses = {
            (owner, path): access
            for owner, path, access in self.session.shares()
        }

    def _share_access(self, owner, path):
        if owner == self.username:
            return "rw"
        best = None
        best_length = -1
        for (share_owner, share_path), access in self.share_accesses.items():
            if share_owner == owner and (
                path == share_path or path.startswith(share_path + "/")
            ):
                if len(share_path) > best_length:
                    best = access
                    best_length = len(share_path)
        return best

    def _local_files(self):
        result = {}
        for path in self.root.rglob("*"):
            if not path.is_file() or path.name.startswith(".download-"):
                continue
            relative = path.relative_to(self.root).as_posix()
            owner, file_path = self._owner_path(relative)
            data = path.read_bytes()
            result[(owner, file_path)] = {
                "digest": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "local": relative,
            }
        return result

    def reconcile(self):
        """Apply the manifest, local files, and last known state."""
        self._load_shares()
        remote = {
            (entry.owner, entry.path): entry for entry in self.session.sync()
        }
        local = self._local_files()
        state = {
            (entry["owner"], entry["path"]): entry
            for entry in self.state.list_files()
        }
        for key in sorted(set(remote) | set(local) | set(state)):
            owner, path = key
            self._reconcile_path(
                owner, path, remote.get(key), local.get(key), state.get(key)
            )
        self.state.clear_outbox()

    def _reconcile_path(self, owner, path, remote_entry, local_entry, state_entry):
        access = self._share_access(owner, path)
        if access is None and owner == self.username:
            access = "rw"
        if access is None and remote_entry is not None:
            access = remote_entry.access
        if access is None:
            access = "ro"

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
                    if access == "ro":
                        self._preserve_local_conflict(owner, path)
                        self._download(remote_entry)
                    else:
                        self._upload(owner, path, 0)
                elif local_entry["digest"] != state_entry["digest"]:
                    if access == "ro":
                        self._preserve_local_conflict(owner, path)
                        self._download(remote_entry)
                    else:
                        self._upload(owner, path, state_entry["rev"])
                elif remote_entry.rev != state_entry["rev"]:
                    self._download(remote_entry)
                else:
                    self.state.set_file(remote_entry)
                return

            if state_entry is None or state_entry["deleted"]:
                self._download(remote_entry)
            elif access == "ro":
                self._download(remote_entry)
            else:
                self._delete_remote(owner, path, state_entry)
            return

        if remote_entry is not None and remote_entry.deleted:
            if local_entry is not None:
                if state_entry is None or state_entry["deleted"]:
                    if access == "ro":
                        self._delete_local(owner, path, remote_entry)
                    else:
                        expected = state_entry["rev"] if state_entry else 0
                        self._upload(owner, path, expected)
                elif local_entry["digest"] == state_entry["digest"]:
                    self._delete_local(owner, path, remote_entry)
                elif access == "ro":
                    self._preserve_local_conflict(owner, path)
                    self._delete_local(owner, path, remote_entry)
                else:
                    self._upload(owner, path, state_entry["rev"])
            else:
                self.state.set_file(remote_entry)
            return

        if local_entry is not None:
            if owner != self.username and access is None:
                self._local_path(owner, path).unlink(missing_ok=True)
                self.state.delete_file(owner, path)
            elif owner != self.username and access == "ro":
                self._local_path(owner, path).unlink(missing_ok=True)
                self.state.delete_file(owner, path)
            else:
                expected = state_entry["rev"] if state_entry else 0
                self._upload(owner, path, expected)
        elif state_entry is not None:
            self.state.delete_file(owner, path)

    def _upload(self, owner, path, expected_rev):
        data = self._local_path(owner, path).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        result = self.session.upload(
            owner,
            path,
            data,
            rev=expected_rev,
            digest=digest,
            client_id=self.state.client_id,
        )
        self._apply_upload_result(owner, path, digest, len(data), result)

    def _apply_upload_result(self, owner, path, digest, size, result):
        state_entry = self.state.get_file(owner, path)
        revision = result.rev
        if revision is None:
            revision = state_entry["rev"] + 1 if state_entry else 1
        access = self._share_access(owner, path) or "rw"
        self.state.set_file(
            ManifestEntry(
                owner=owner,
                path=path,
                rev=revision,
                digest=digest,
                size=size,
                deleted=False,
                access=access,
            )
        )
        if result.conflict_path is not None:
            owner_of_conflict = owner
            self._save_conflict(owner_of_conflict, result.conflict_path)

    def _save_conflict(self, owner, conflict_path):
        data = self.session.download(owner, conflict_path)
        target = self._local_path(owner, conflict_path)
        if target.exists() and target.read_bytes() != data:
            target = self._local_conflict_path(owner, conflict_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(".download-" + target.name)
        temporary.write_bytes(data)
        os.replace(temporary, target)
        local_relative = target.relative_to(self.root).as_posix()
        self.ignore(local_relative)
        if target == self._local_path(owner, conflict_path):
            try:
                remote = self.session.stat(owner, conflict_path)
            except SyncError:
                return
            self.state.set_file(
                ManifestEntry(
                    owner=owner,
                    path=conflict_path,
                    rev=remote.rev,
                    digest=remote.digest,
                    size=remote.size,
                    deleted=False,
                    access=self._share_access(owner, conflict_path) or "rw",
                )
            )

    def _local_conflict_path(self, owner, path):
        target = self._local_path(owner, path)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        client = self.state.client_id[:8]
        name = "{} (local conflict {} {}){}".format(
            target.stem, client, stamp, target.suffix
        )
        result = target.with_name(name)
        counter = 1
        while result.exists():
            name = "{} (local conflict {} {}-{}){}".format(
                target.stem, client, stamp, counter, target.suffix
            )
            result = target.with_name(name)
            counter += 1
        return result

    def _preserve_local_conflict(self, owner, path):
        target = self._local_path(owner, path)
        if not target.is_file():
            return
        alternate = self._local_conflict_path(owner, path)
        shutil.copy2(target, alternate)
        self.ignore(alternate.relative_to(self.root).as_posix())

    def _download(self, entry):
        data = self.session.download(entry.owner, entry.path)
        target = self._local_path(entry.owner, entry.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(".download-" + target.name)
        temporary.write_bytes(data)
        os.replace(temporary, target)
        self.state.set_file(entry)
        self.ignore(target.relative_to(self.root).as_posix())

    def _delete_remote(self, owner, path, state_entry):
        result = self.session.delete(
            owner,
            path,
            rev=state_entry["rev"],
            client_id=self.state.client_id,
        )
        revision = result.rev
        if revision is None:
            revision = state_entry["rev"] + 1
        self.state.set_file(
            ManifestEntry(
                owner=owner,
                path=path,
                rev=revision,
                digest=hashlib.sha256(b"").hexdigest(),
                size=0,
                deleted=True,
                access=state_entry.get("access", "rw"),
            )
        )
        if result.conflict_path is not None:
            self._save_conflict(owner, result.conflict_path)

    def _delete_local(self, owner, path, remote_entry):
        target = self._local_path(owner, path)
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        self.state.set_file(remote_entry)
        self.ignore(target.relative_to(self.root).as_posix())
        self._remove_empty_parents(target.parent)

    def _remove_empty_parents(self, directory):
        shared_root = self.root / "shared"
        while directory != self.root and self.root in directory.parents:
            if directory == shared_root or directory.parent == shared_root:
                return
            try:
                directory.rmdir()
            except OSError:
                return
            directory = directory.parent

    def _run(self):
        """Consume queued changes and retry transient network failures."""
        while not self.stop_event.is_set():
            try:
                remote = self.remote_changes.get_nowait()
            except queue.Empty:
                remote = None
            if remote is not None:
                try:
                    if isinstance(remote, dict) and remote.get("action") == "reconcile":
                        self.reconcile()
                    else:
                        self._apply_remote(remote)
                except (OSError, EOFError, socket.timeout, ssl.SSLError, SyncError):
                    self._reconnect()
                continue

            pending = self.state.pending()
            if pending:
                change = pending[0]
                action = change["action"]
                owner = change["owner"]
                path = change["path"]
                change_id = change["id"]
            else:
                try:
                    action, local_relative = self.changes.get(timeout=0.2)
                except queue.Empty:
                    continue
                time.sleep(0.5)
                action, local_relative = self._latest_for(local_relative, action)
                owner, path = self._owner_path(local_relative)
                change_id = self.state.enqueue(action, owner, path)

            try:
                self._perform(action, owner, path)
            except (OSError, EOFError, socket.timeout, ssl.SSLError, SyncError):
                if not self.stop_event.is_set():
                    self._reconnect()
                    time.sleep(1)
            else:
                self.state.ack(change_id)

    def _apply_remote(self, update):
        owner = update.owner
        path = update.path
        access = update.access
        local_path = self._local_path(owner, path)
        if update.op == "D":
            try:
                local_path.unlink()
            except FileNotFoundError:
                pass
            self.state.set_file(
                ManifestEntry(
                    owner=owner,
                    path=path,
                    rev=update.rev,
                    digest=update.digest,
                    size=0,
                    deleted=True,
                    access=access,
                )
            )
            self.ignore(local_path.relative_to(self.root).as_posix())
            self._remove_empty_parents(local_path.parent)
            return

        if update.op != "U":
            self.reconcile()
            return

        state_entry = self.state.get_file(owner, path)
        digest = None
        if local_path.is_file():
            digest = hashlib.sha256(local_path.read_bytes()).hexdigest()
        if digest == update.digest:
            self.state.set_file(
                ManifestEntry(
                    owner=owner,
                    path=path,
                    rev=update.rev,
                    digest=update.digest,
                    size=update.size,
                    deleted=False,
                    access=access,
                )
            )
            return
        if local_path.is_file() and state_entry is not None:
            if digest != state_entry["digest"]:
                self._preserve_local_conflict(owner, path)
        self._download(
            ManifestEntry(
                owner=owner,
                path=path,
                rev=update.rev,
                digest=update.digest,
                size=update.size,
                deleted=False,
                access=access,
            )
        )

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

    def _perform(self, action, owner, path):
        state_entry = self.state.get_file(owner, path)
        access = self._share_access(owner, path)
        if access is None and state_entry is not None:
            access = state_entry.get("access")
        if access is None:
            access = "rw" if owner == self.username else "ro"
        if action == "upload":
            if access != "ro":
                self._upload_when_stable(owner, path)
        elif action == "mkdir":
            if access != "ro":
                self.session.mkdir(owner, path)
        elif action == "rmdir":
            if access != "ro":
                self._remove_remote_tree(owner, path)
        else:
            if access != "ro":
                self._remove_local_file(owner, path)

    def _remove_remote_tree(self, owner, prefix):
        matches = [
            entry
            for entry in self.state.list_files()
            if entry["owner"] == owner
            and (entry["path"] == prefix or entry["path"].startswith(prefix + "/"))
        ]
        if not matches:
            return
        self.session.rmdir(owner, prefix)
        self.state.delete_tree(owner, prefix)

    def _remove_local_file(self, owner, path):
        state_entry = self.state.get_file(owner, path)
        if state_entry is None or state_entry["deleted"]:
            return
        self._delete_remote(owner, path, state_entry)

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

    def _upload_when_stable(self, owner, path):
        """Upload a file only after two stable filesystem observations."""
        local_path = self._local_path(owner, path)
        if not local_path.is_file():
            return
        first = local_path.stat()
        time.sleep(0.2)
        second = local_path.stat()
        if (first.st_size, first.st_mtime_ns) != (second.st_size, second.st_mtime_ns):
            self.changes.put(("upload", local_path.relative_to(self.root).as_posix()))
            return
        data = local_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        state_entry = self.state.get_file(owner, path)
        if (
            state_entry is not None
            and not state_entry["deleted"]
            and state_entry["digest"] == digest
        ):
            return
        expected_rev = state_entry["rev"] if state_entry else 0
        result = self.session.upload(
            owner,
            path,
            data,
            rev=expected_rev,
            digest=digest,
            client_id=self.state.client_id,
        )
        self._apply_upload_result(owner, path, digest, len(data), result)
