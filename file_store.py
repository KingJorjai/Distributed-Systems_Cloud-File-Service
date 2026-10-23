"""SQLite metadata and filesystem storage for the file service."""

import hashlib
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from auth import hash_password, validate_password, validate_username, verify_password

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    iterations    INTEGER NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    disabled      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    owner     TEXT NOT NULL,
    path      TEXT NOT NULL,
    rev       INTEGER NOT NULL,
    hash      TEXT NOT NULL,
    size      INTEGER NOT NULL,
    mtime_ns  INTEGER NOT NULL,
    deleted   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (owner, path),
    FOREIGN KEY (owner) REFERENCES users (username)
);

CREATE TABLE IF NOT EXISTS shares (
    owner      TEXT NOT NULL,
    path       TEXT NOT NULL,
    grantee    TEXT NOT NULL,
    access     TEXT NOT NULL CHECK (access IN ('ro', 'rw')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (owner, path, grantee),
    CHECK (owner <> grantee),
    FOREIGN KEY (owner) REFERENCES users (username),
    FOREIGN KEY (grantee) REFERENCES users (username)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class StoreError(Exception):
    """Base class for file store errors."""


class InvalidPathError(StoreError):
    """Raised when a path escapes its root or is malformed."""


class UserExistsError(StoreError):
    """Raised when a username is already registered."""


class UserNotFoundError(StoreError):
    """Raised when a user does not exist."""


class UserDisabledError(StoreError):
    """Raised when a disabled user tries to authenticate."""


class InvalidPasswordError(StoreError):
    """Raised when authentication fails."""


class NotFoundError(StoreError):
    """Raised when a file does not exist."""


class AccessDeniedError(StoreError):
    """Raised when a user cannot access a path."""


class ConflictError(StoreError):
    """Raised when a revision precondition fails."""

    def __init__(self, current):
        super().__init__("Revision conflict.")
        self.current = current


class ShareExistsError(StoreError):
    """Raised when the same share already exists."""


class SelfShareError(StoreError):
    """Raised when a user tries to share with themselves."""


@dataclass(frozen=True)
class User:
    username: str
    role: str
    disabled: bool


@dataclass(frozen=True)
class FileRecord:
    owner: str
    path: str
    rev: int
    digest: str
    size: int
    mtime_ns: int
    deleted: bool


@dataclass(frozen=True)
class Share:
    owner: str
    path: str
    grantee: str
    access: str


@dataclass(frozen=True)
class ManifestEntry:
    owner: str
    path: str
    rev: int
    digest: str
    size: int
    deleted: bool
    access: str


def _now():
    return datetime.now(timezone.utc).isoformat()


def _normalize_path(path: str) -> str:
    if not isinstance(path, str) or not path:
        raise InvalidPathError("Path is empty.")
    if any(character in path for character in ("\x00", "\r", "\n")):
        raise InvalidPathError("Path contains a control character.")
    normalized = path.replace("\\", "/")
    if (
        normalized.startswith("/")
        or normalized == ".."
        or normalized.startswith("../")
        or re.match(r"^[A-Za-z]:", normalized)
    ):
        raise InvalidPathError("Path must be relative.")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise InvalidPathError("Path must stay inside the user root.")
    return "/".join(parts)


def safe_path(root, filename):
    """Resolve a relative filename while preventing access outside root."""
    try:
        normalized = _normalize_path(filename)
    except InvalidPathError:
        raise
    root_path = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root_path, normalized))
    if os.path.commonpath((os.path.normcase(root_path), os.path.normcase(target))) != os.path.normcase(root_path):
        raise InvalidPathError("Path must stay inside the user root.")
    return target


class FileStore:
    """Store file bytes under per-user roots and metadata in SQLite."""

    def __init__(self, root, db_path=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path) if db_path is not None else self.root / ".cloudfs.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            str(self.db_path), check_same_thread=False
        )
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(SCHEMA)
        self._connection.commit()

    def close(self):
        with self._lock:
            self._connection.close()

    def _owner_root(self, owner):
        if not isinstance(owner, str) or not owner:
            raise InvalidPathError("Owner is invalid.")
        if owner == "anonimous":
            raise InvalidPathError("Anonymous users cannot own files.")
        path = safe_path(self.root, owner)
        os.makedirs(path, exist_ok=True)
        return path

    def _file_path(self, owner, path):
        return safe_path(self._owner_root(owner), path)

    def _row_to_record(self, row):
        return FileRecord(
            owner=row[0],
            path=row[1],
            rev=row[2],
            digest=row[3],
            size=row[4],
            mtime_ns=row[5],
            deleted=bool(row[6]),
        )

    def create_user(
        self,
        username,
        password,
        role="user",
        disabled=False,
        allow_reserved=False,
    ):
        """Create a user, hashing the password with PBKDF2."""
        if not allow_reserved and not validate_username(username):
            raise StoreError("Invalid username.")
        if not allow_reserved and not validate_password(password):
            raise StoreError("Password must be at least 8 characters.")
        if role not in {"admin", "user"}:
            raise StoreError("Invalid role.")
        digest, salt, iterations = hash_password(password)
        with self._lock:
            try:
                self._connection.execute(
                    "INSERT INTO users(username, password_hash, salt, iterations, role, disabled, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        username,
                        digest,
                        salt,
                        iterations,
                        role,
                        1 if disabled else 0,
                        _now(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise UserExistsError(username) from error
            self._connection.commit()
        return User(username, role, bool(disabled))

    def ensure_bootstrap_user(self, username, password, role="admin"):
        """Create a bootstrap user if missing and apply the disabled flag."""
        with self._lock:
            existing = self.get_user(username)
            if existing is None:
                digest, salt, iterations = hash_password(password or "disabled-account")
                self._connection.execute(
                    "INSERT INTO users(username, password_hash, salt, iterations, role, disabled, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        username,
                        digest,
                        salt,
                        iterations,
                        role,
                        0 if password else 1,
                        _now(),
                    ),
                )
                self._connection.commit()
            elif not password:
                self._connection.execute(
                    "UPDATE users SET disabled = 1 WHERE username = ?", (username,)
                )
                self._connection.commit()

    def get_user(self, username):
        with self._lock:
            row = self._connection.execute(
                "SELECT username, role, disabled FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            return None
        return User(row[0], row[1], bool(row[2]))

    def list_users(self):
        with self._lock:
            rows = self._connection.execute(
                "SELECT username, role, disabled FROM users ORDER BY username"
            ).fetchall()
        return [User(row[0], row[1], bool(row[2])) for row in rows]

    def set_user_disabled(self, username, disabled):
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE users SET disabled = ? WHERE username = ?",
                (1 if disabled else 0, username),
            )
            self._connection.commit()
        if cursor.rowcount == 0:
            raise UserNotFoundError(username)

    def set_password(self, username, password):
        if not validate_password(password):
            raise StoreError("Password must be at least 8 characters.")
        digest, salt, iterations = hash_password(password)
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE users SET password_hash = ?, salt = ?, iterations = ? WHERE username = ?",
                (digest, salt, iterations, username),
            )
            self._connection.commit()
        if cursor.rowcount == 0:
            raise UserNotFoundError(username)

    def authenticate(self, username, password):
        """Return a user when credentials are valid and the account is active."""
        with self._lock:
            row = self._connection.execute(
                "SELECT username, password_hash, salt, iterations, role, disabled "
                "FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            raise UserNotFoundError(username)
        if row[5]:
            raise UserDisabledError(username)
        if not verify_password(password, row[1], row[2], row[3]):
            raise InvalidPasswordError(username)
        return User(row[0], row[4], False)

    def create_share(self, owner, path, grantee, access):
        if owner == grantee:
            raise SelfShareError("A user cannot share with themselves.")
        if access not in {"ro", "rw"}:
            raise StoreError("Share access must be 'ro' or 'rw'.")
        normalized = _normalize_path(path)
        with self._lock:
            if self.get_user(owner) is None:
                raise UserNotFoundError(owner)
            if self.get_user(grantee) is None:
                raise UserNotFoundError(grantee)
            try:
                self._connection.execute(
                    "INSERT INTO shares(owner, path, grantee, access, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (owner, normalized, grantee, access, _now()),
                )
            except sqlite3.IntegrityError as error:
                raise ShareExistsError("Share already exists.") from error
            self._connection.commit()

    def revoke_share(self, owner, path, grantee):
        normalized = _normalize_path(path)
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM shares WHERE owner = ? AND path = ? AND grantee = ?",
                (owner, normalized, grantee),
            )
            self._connection.commit()
        if cursor.rowcount == 0:
            raise NotFoundError("Share does not exist.")

    def list_shares(self, owner=None, grantee=None):
        query = "SELECT owner, path, grantee, access FROM shares"
        clauses = []
        parameters = []
        if owner is not None:
            clauses.append("owner = ?")
            parameters.append(owner)
        if grantee is not None:
            clauses.append("grantee = ?")
            parameters.append(grantee)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY owner, path, grantee"
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [Share(*row) for row in rows]

    def access_for(self, user, owner, path, write=False):
        """Return 'rw', 'ro', or None; raise when write access is required."""
        normalized = _normalize_path(path)
        if user == owner:
            return "rw"
        with self._lock:
            rows = self._connection.execute(
                "SELECT path, access FROM shares WHERE owner = ? AND grantee = ?",
                (owner, user),
            ).fetchall()
        best = None
        best_length = -1
        for share_path, access in rows:
            if normalized == share_path or normalized.startswith(share_path + "/"):
                if len(share_path) > best_length:
                    best = access
                    best_length = len(share_path)
        if write and best != "rw":
            raise AccessDeniedError("Write access is required.")
        return best

    def put(self, owner, path, data, expected_rev=None):
        """Store bytes atomically and return the new file record."""
        normalized = _normalize_path(path)
        target = self._file_path(owner, normalized)
        with self._lock:
            current = self.stat(owner, normalized)
            current_rev = current.rev if current is not None else 0
            if expected_rev is not None and expected_rev != current_rev:
                raise ConflictError(current)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(
                prefix=".upload-", dir=os.path.dirname(target)
            )
            try:
                with os.fdopen(descriptor, "wb") as temporary_file:
                    temporary_file.write(data)
                os.replace(temporary, target)
            except OSError:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
                raise
            digest = hashlib.sha256(data).hexdigest()
            rev = current_rev + 1
            mtime_ns = time.time_ns()
            self._connection.execute(
                "INSERT INTO files(owner, path, rev, hash, size, mtime_ns, deleted) "
                "VALUES (?, ?, ?, ?, ?, ?, 0) "
                "ON CONFLICT(owner, path) DO UPDATE SET "
                "rev = excluded.rev, hash = excluded.hash, size = excluded.size, "
                "mtime_ns = excluded.mtime_ns, deleted = 0",
                (owner, normalized, rev, digest, len(data), mtime_ns),
            )
            self._connection.commit()
        return FileRecord(owner, normalized, rev, digest, len(data), mtime_ns, False)


    def _conflict_path(self, owner, path, client_id):
        candidate = PurePosixPath(path)
        safe_client = re.sub(r"[^A-Za-z0-9_-]", "", client_id or "")[:16] or "client"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        stem = candidate.stem[:120]
        suffix = candidate.suffix
        counter = 1
        while True:
            marker = "conflict {}{}".format(
                safe_client, "" if counter == 1 else "-{}".format(counter)
            )
            name = "{} ({} {}){}".format(stem, marker, stamp, suffix)
            conflict = str(candidate.with_name(name))
            if self.stat(owner, conflict) is None:
                return conflict
            counter += 1

    def put_with_conflict(
        self, owner, path, data, expected_rev=None, client_id=None
    ):
        """Store bytes, preserving the current version if the revision is stale."""
        normalized = _normalize_path(path)
        current = self.stat(owner, normalized)
        current_rev = current.rev if current is not None else 0
        if expected_rev is not None and expected_rev != current_rev:
            conflict = None
            if current is not None and not current.deleted:
                current_data, _ = self.get(owner, normalized)
                conflict = self.put(
                    owner,
                    self._conflict_path(owner, normalized, client_id),
                    current_data,
                )
            record = self.put(
                owner, normalized, data, expected_rev=current_rev
            )
            return record, conflict
        return self.put(
            owner, normalized, data, expected_rev=expected_rev
        ), None

    def delete_with_conflict(
        self, owner, path, expected_rev=None, client_id=None
    ):
        """Delete a file, preserving the current version if the revision is stale."""
        normalized = _normalize_path(path)
        current = self.stat(owner, normalized)
        current_rev = current.rev if current is not None else 0
        if expected_rev is not None and expected_rev != current_rev:
            conflict = None
            if current is not None and not current.deleted:
                current_data, _ = self.get(owner, normalized)
                conflict = self.put(
                    owner,
                    self._conflict_path(owner, normalized, client_id),
                    current_data,
                )
            return self.delete(owner, normalized), conflict
        return self.delete(owner, normalized), None

    def get(self, owner, path):
        """Return ``(bytes, FileRecord)`` for an existing file."""
        normalized = _normalize_path(path)
        record = self.stat(owner, normalized)
        if record is None or record.deleted:
            raise NotFoundError(normalized)
        target = self._file_path(owner, normalized)
        try:
            data = Path(target).read_bytes()
        except OSError as error:
            raise NotFoundError(normalized) from error
        return data, record

    def stat(self, owner, path):
        normalized = _normalize_path(path)
        with self._lock:
            row = self._connection.execute(
                "SELECT owner, path, rev, hash, size, mtime_ns, deleted "
                "FROM files WHERE owner = ? AND path = ?",
                (owner, normalized),
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def delete(self, owner, path):
        normalized = _normalize_path(path)
        target = self._file_path(owner, normalized)
        with self._lock:
            current = self.stat(owner, normalized)
            if current is not None and current.deleted:
                return current
            rev = (current.rev + 1) if current is not None else 1
            try:
                os.remove(target)
            except FileNotFoundError:
                pass
            except OSError as error:
                raise StoreError("Could not delete file.") from error
            digest = hashlib.sha256(b"").hexdigest()
            mtime_ns = time.time_ns()
            self._connection.execute(
                "INSERT INTO files(owner, path, rev, hash, size, mtime_ns, deleted) "
                "VALUES (?, ?, ?, ?, 0, ?, 1) "
                "ON CONFLICT(owner, path) DO UPDATE SET "
                "rev = excluded.rev, hash = excluded.hash, size = 0, "
                "mtime_ns = excluded.mtime_ns, deleted = 1",
                (owner, normalized, rev, digest, mtime_ns),
            )
            self._connection.commit()
        return FileRecord(owner, normalized, rev, digest, 0, mtime_ns, True)

    def mkdir(self, owner, path):
        normalized = _normalize_path(path)
        target = self._file_path(owner, normalized)
        os.makedirs(target, exist_ok=True)

    def rmdir(self, owner, path):
        normalized = _normalize_path(path)
        target = self._file_path(owner, normalized)
        with self._lock:
            try:
                shutil.rmtree(target)
            except FileNotFoundError:
                pass
            except OSError as error:
                raise StoreError("Could not delete directory.") from error
            rows = self._connection.execute(
                "SELECT path, rev FROM files WHERE owner = ? AND (path = ? OR path LIKE ?)",
                (owner, normalized, normalized + "/%"),
            ).fetchall()
            for row_path, revision in rows:
                self._connection.execute(
                    "UPDATE files SET rev = ?, deleted = 1, size = 0 WHERE owner = ? AND path = ?",
                    (revision + 1, owner, row_path),
                )
            self._connection.commit()

    def manifest(self, user):
        """Return owned and shared files visible to a user."""
        with self._lock:
            owned = self._connection.execute(
                "SELECT owner, path, rev, hash, size, deleted FROM files WHERE owner = ?",
                (user,),
            ).fetchall()
            shares = self._connection.execute(
                "SELECT owner, path, access FROM shares WHERE grantee = ?",
                (user,),
            ).fetchall()

        entries = {}
        for row in owned:
            entries[(row[0], row[1])] = ManifestEntry(
                owner=row[0],
                path=row[1],
                rev=row[2],
                digest=row[3],
                size=row[4],
                deleted=bool(row[5]),
                access="rw",
            )

        for owner, share_path, access in shares:
            with self._lock:
                rows = self._connection.execute(
                    "SELECT owner, path, rev, hash, size, deleted FROM files WHERE owner = ?",
                    (owner,),
                ).fetchall()
            for row in rows:
                path = row[1]
                if path != share_path and not path.startswith(share_path + "/"):
                    continue
                key = (row[0], row[1])
                previous = entries.get(key)
                effective = "rw" if access == "rw" else "ro"
                if previous is None or (previous.access == "ro" and effective == "rw"):
                    entries[key] = ManifestEntry(
                        owner=row[0],
                        path=row[1],
                        rev=row[2],
                        digest=row[3],
                        size=row[4],
                        deleted=bool(row[5]),
                        access=effective,
                    )
        return sorted(entries.values(), key=lambda entry: (entry.owner, entry.path))

    def backfill(self, users=None):
        """Import files already present on disk with revision 1."""
        owners = [user.username for user in self.list_users()] if users is None else users
        for owner in owners:
            owner_root = self._owner_root(owner)
            for target in sorted(Path(owner_root).rglob("*")):
                if not target.is_file():
                    continue
                relative = target.relative_to(owner_root)
                if any(part.startswith(".") for part in relative.parts):
                    continue
                path = relative.as_posix()
                with self._lock:
                    existing = self.stat(owner, path)
                    if existing is not None:
                        continue
                    data = target.read_bytes()
                    digest = hashlib.sha256(data).hexdigest()
                    mtime_ns = target.stat().st_mtime_ns
                    self._connection.execute(
                        "INSERT INTO files(owner, path, rev, hash, size, mtime_ns, deleted) "
                        "VALUES (?, ?, 1, ?, ?, ?, 0)",
                        (owner, path, digest, len(data), mtime_ns),
                    )
                    self._connection.commit()

    def get_setting(self, key, default=None):
        with self._lock:
            row = self._connection.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row[0] if row is not None else default

    def set_setting(self, key, value):
        with self._lock:
            self._connection.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._connection.commit()
