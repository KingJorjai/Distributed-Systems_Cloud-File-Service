"""Cluster membership, durable replication log, and replication transports."""

import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Peer:
    """One remote server in the replication cluster."""

    server_id: str
    host: str
    port: int


def parse_peers(value):
    """Parse ``id@host:port,...`` into a tuple of :class:`Peer`."""
    peers = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            server_id, address = item.split("@", 1)
            host, port = address.rsplit(":", 1)
            peers.append(Peer(server_id, host, int(port)))
        except (ValueError, TypeError) as error:
            raise ValueError("Invalid peer specification: {}".format(item)) from error
    return tuple(peers)


LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    term      INTEGER NOT NULL,
    idx       INTEGER NOT NULL,
    payload   TEXT NOT NULL,
    committed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (term, idx)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class ReplicationLog:
    """Durable operation log shared by the primary and secondaries."""

    def __init__(self, db_path, term=1):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            str(self.db_path), check_same_thread=False
        )
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(LOG_SCHEMA)
        if self.get_meta("term") is None:
            self.set_meta("term", str(term))
        if self.get_meta("commit_index") is None:
            self.set_meta("commit_index", "0")
        self._connection.commit()

    def close(self):
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def get_meta(self, key, default=None):
        with self._lock:
            row = self._connection.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
        return row[0] if row is not None else default

    def set_meta(self, key, value):
        with self._lock:
            self._connection.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
            self._connection.commit()

    def term(self):
        return int(self.get_meta("term", "1"))

    def set_term(self, term):
        self.set_meta("term", term)

    def commit_index(self):
        return int(self.get_meta("commit_index", "0"))

    def last_index(self):
        with self._lock:
            row = self._connection.execute(
                "SELECT MAX(idx) FROM entries"
            ).fetchone()
        return int(row[0]) if row[0] is not None else 0

    def next_index(self):
        return self.last_index() + 1

    def append(self, term, index, payload, committed=False):
        with self._lock:
            row = self._connection.execute(
                "SELECT payload FROM entries WHERE term = ? AND idx = ?",
                (term, index),
            ).fetchone()
            if row is not None:
                if row[0] != payload:
                    raise ValueError("Conflicting entry for term/index.")
                if committed and not self._connection.execute(
                    "SELECT committed FROM entries WHERE term = ? AND idx = ?",
                    (term, index),
                ).fetchone()[0]:
                    self._connection.execute(
                        "UPDATE entries SET committed = 1 WHERE term = ? AND idx = ?",
                        (term, index),
                    )
                    self._connection.commit()
                return
            self._connection.execute(
                "INSERT INTO entries(term, idx, payload, committed) VALUES (?, ?, ?, ?)",
                (term, index, payload, 1 if committed else 0),
            )
            self._connection.commit()

    def mark_committed(self, term, index):
        with self._lock:
            self._connection.execute(
                "UPDATE entries SET committed = 1 WHERE term = ? AND idx = ?",
                (term, index),
            )
            self._connection.commit()

    def get(self, term, index):
        with self._lock:
            row = self._connection.execute(
                "SELECT term, idx, payload, committed FROM entries "
                "WHERE term = ? AND idx = ?",
                (term, index),
            ).fetchone()
        if row is None:
            return None
        return {
            "term": row[0],
            "index": row[1],
            "payload": json.loads(row[2]),
            "committed": bool(row[3]),
        }

    def pending(self, term, after_index):
        with self._lock:
            rows = self._connection.execute(
                "SELECT term, idx, payload FROM entries "
                "WHERE term = ? AND idx > ? AND committed = 0 ORDER BY idx",
                (term, after_index),
            ).fetchall()
        return [
            {"term": row[0], "index": row[1], "payload": json.loads(row[2])}
            for row in rows
        ]

    def truncate_from(self, term, index):
        with self._lock:
            self._connection.execute(
                "DELETE FROM entries WHERE term = ? AND idx >= ? AND committed = 0",
                (term, index),
            )
            self._connection.commit()
