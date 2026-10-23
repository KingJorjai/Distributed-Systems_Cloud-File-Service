"""Persistent client-side synchronization state and outbox."""

import hashlib
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    owner   TEXT NOT NULL,
    path    TEXT NOT NULL,
    rev     INTEGER NOT NULL,
    hash    TEXT NOT NULL,
    size    INTEGER NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (owner, path)
);

CREATE TABLE IF NOT EXISTS outbox (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    action     TEXT NOT NULL,
    owner      TEXT NOT NULL,
    path       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def default_state_dir():
    """Return the platform-appropriate directory for client state."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(
            os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")
        )
    return base / "cloudfs"


class ClientState:
    """Store the last known remote state and pending local changes."""

    def __init__(self, username, server, port, root, state_dir=None):
        self.username = username
        self.server = server
        self.port = int(port)
        self.root = Path(root).resolve()
        base = Path(state_dir) if state_dir else default_state_dir()
        base.mkdir(parents=True, exist_ok=True)
        identity = "{}:{}:{}:{}".format(
            username, self.server, self.port, self.root
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        self.db_path = base / "{}.sqlite3".format(digest)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            str(self.db_path), check_same_thread=False
        )
        self._connection.executescript(SCHEMA)
        self._connection.commit()

    def close(self):
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def set_file(self, entry):
        with self._lock:
            self._connection.execute(
                "INSERT INTO files(owner, path, rev, hash, size, deleted) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(owner, path) DO UPDATE SET "
                "rev = excluded.rev, hash = excluded.hash, size = excluded.size, "
                "deleted = excluded.deleted",
                (
                    entry.owner,
                    entry.path,
                    entry.rev,
                    entry.digest,
                    entry.size,
                    1 if entry.deleted else 0,
                ),
            )
            self._connection.commit()

    def get_file(self, owner, path):
        with self._lock:
            row = self._connection.execute(
                "SELECT owner, path, rev, hash, size, deleted "
                "FROM files WHERE owner = ? AND path = ?",
                (owner, path),
            ).fetchone()
        if row is None:
            return None
        return {
            "owner": row[0],
            "path": row[1],
            "rev": row[2],
            "digest": row[3],
            "size": row[4],
            "deleted": bool(row[5]),
        }

    def list_files(self):
        with self._lock:
            rows = self._connection.execute(
                "SELECT owner, path, rev, hash, size, deleted FROM files"
            ).fetchall()
        return [
            {
                "owner": row[0],
                "path": row[1],
                "rev": row[2],
                "digest": row[3],
                "size": row[4],
                "deleted": bool(row[5]),
            }
            for row in rows
        ]

    def enqueue(self, action, owner, path):
        with self._lock:
            cursor = self._connection.execute(
                "INSERT INTO outbox(action, owner, path, created_at) VALUES (?, ?, ?, ?)",
                (
                    action,
                    owner,
                    path,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self._connection.commit()
            return cursor.lastrowid

    def pending(self):
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, action, owner, path FROM outbox ORDER BY id"
            ).fetchall()
        return [
            {
                "id": row[0],
                "action": row[1],
                "owner": row[2],
                "path": row[3],
            }
            for row in rows
        ]

    def ack(self, change_id):
        with self._lock:
            self._connection.execute(
                "DELETE FROM outbox WHERE id = ?", (change_id,)
            )
            self._connection.commit()
