"""Cluster membership, durable replication log, and replication transports."""

import hmac
import json
import socket
import sqlite3
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import szasar
from tls import client_context, server_context


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

    def advance_term(self, term):
        with self._lock:
            if term > self.term():
                self._connection.execute(
                    "INSERT INTO meta(key, value) VALUES ('term', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(term),),
                )
                self._connection.execute(
                    "INSERT INTO meta(key, value) VALUES ('voted_for', '') "
                    "ON CONFLICT(key) DO UPDATE SET value = ''"
                )
                self._connection.commit()

    def voted_for(self):
        return self.get_meta("voted_for", "") or None

    def set_voted_for(self, server_id):
        self.set_meta("voted_for", server_id or "")

    def commit_index(self):
        return int(self.get_meta("commit_index", "0"))

    def last_index(self):
        with self._lock:
            row = self._connection.execute(
                "SELECT MAX(idx) FROM entries"
            ).fetchone()
            entry_index = int(row[0]) if row[0] is not None else 0
        return max(entry_index, int(self.get_meta("last_index", "0")))

    def last_term(self):
        with self._lock:
            row = self._connection.execute(
                "SELECT term FROM entries ORDER BY idx DESC LIMIT 1"
            ).fetchone()
            entry_term = int(row[0]) if row is not None else 0
        return max(entry_term, int(self.get_meta("last_term", "0")))

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
            else:
                self._connection.execute(
                    "INSERT INTO entries(term, idx, payload, committed) VALUES (?, ?, ?, ?)",
                    (term, index, payload, 1 if committed else 0),
                )
                self._connection.commit()
            if index > int(self.get_meta("last_index", "0")):
                self.set_meta("last_index", index)
                self.set_meta("last_term", term)

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
            row = self._connection.execute(
                "SELECT MAX(idx) FROM entries"
            ).fetchone()
            remaining = int(row[0]) if row[0] is not None else 0
            self._connection.execute(
                "INSERT INTO meta(key, value) VALUES ('last_index', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(max(remaining, self.commit_index())),),
            )
            self._connection.commit()

    def reset_to(self, term, index):
        with self._lock:
            self._connection.execute("DELETE FROM entries")
            self._connection.execute(
                "INSERT INTO meta(key, value) VALUES ('term', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(term),),
            )
            for key in ("commit_index", "last_applied", "last_index"):
                self._connection.execute(
                    "INSERT INTO meta(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(index)),
                )
            self._connection.execute(
                "INSERT INTO meta(key, value) VALUES ('last_term', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(term),),
            )
            self._connection.execute(
                "INSERT INTO meta(key, value) VALUES ('voted_for', '') "
                "ON CONFLICT(key) DO UPDATE SET value = ''"
            )
            self._connection.commit()


MAX_REPLICATION_MESSAGE = 64 * 1024 * 1024


class ReplicationError(Exception):
    """Raised for invalid or rejected replication messages."""


def _encode(message):
    return (json.dumps(message, separators=(",", ":")) + "\r\n").encode("utf-8")


class PeerConnection:
    """One outbound replication connection from the primary to a peer."""

    def __init__(self, config, peer, hello=None):
        self.config = config
        self.peer = peer
        self.hello = hello
        self.socket = None
        self.reader = None

    def connect(self):
        raw = socket.create_connection(
            (self.peer.host, self.peer.port),
            timeout=self.config.replication_timeout,
        )
        context = client_context(
            self.config.tls_ca_file,
            self.config.tls_cert_file,
            self.config.tls_key_file,
        )
        self.socket = context.wrap_socket(raw, server_hostname=self.peer.host)
        self.reader = szasar.SocketReader(
            self.socket, max_line=MAX_REPLICATION_MESSAGE
        )
        hello = self.hello or {
            "id": self.config.server_id,
            "role": "primary",
            "term": self.config.term,
            "last_index": 0,
            "commit_index": 0,
            "token": self.config.cluster_token,
        }
        self.send({"type": "HELLO", **hello})
        response = self.recv()
        if response.get("type") != "HELLO_OK":
            self.close()
            raise ReplicationError(
                "Replication handshake failed: {}".format(response)
            )
        self.remote = response

    def send(self, message):
        self.socket.sendall(_encode(message))

    def recv(self):
        line = self.reader.readline()
        if not line:
            raise ReplicationError("Replication connection closed.")
        return json.loads(line.decode("utf-8"))

    def close(self):
        if self.socket is not None:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None


class ReplicationServer:
    """Secondary-side listener for replication messages."""

    def __init__(self, config, store, log, cluster=None):
        self.config = config
        self.store = store
        self.log = log
        self.cluster = cluster
        self._socket = None
        self._stop = threading.Event()
        self._connections = set()
        self._lock = threading.Lock()
        self._apply_lock = threading.Lock()
        self.port = None

    def start(self):
        context = server_context(
            self.config.tls_cert_file,
            self.config.tls_key_file,
            self.config.tls_ca_file,
            require_client_cert=True,
        )
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(
            (
                self.config.replication_host or self.config.host,
                self.config.replication_port,
            )
        )
        listener.listen(5)
        listener.settimeout(0.2)
        self._context = context
        self._socket = listener
        self.port = listener.getsockname()[1]

    def serve_forever(self):
        while not self._stop.is_set():
            try:
                connection, _ = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                connection = self._context.wrap_socket(
                    connection, server_side=True
                )
            except (OSError, ssl.SSLError):
                connection.close()
                continue
            with self._lock:
                self._connections.add(connection)
            thread = threading.Thread(
                target=self._handle, args=(connection,), daemon=True
            )
            thread.start()

    def stop(self):
        self._stop.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        with self._lock:
            connections = list(self._connections)
        for connection in connections:
            try:
                connection.close()
            except OSError:
                pass

    def _send(self, connection, message):
        connection.sendall(_encode(message))

    def _handle(self, connection):
        reader = szasar.SocketReader(
            connection, max_line=MAX_REPLICATION_MESSAGE
        )
        try:
            hello = json.loads(reader.readline().decode("utf-8"))
            if hello.get("type") != "HELLO":
                self._send(connection, {"type": "HELLO_ERROR"})
                return
            expected = self.config.cluster_token
            if expected and not hmac.compare_digest(
                expected, str(hello.get("token", ""))
            ):
                self._send(connection, {"type": "HELLO_ERROR"})
                return
            if self.cluster is not None and int(hello.get("term", 0)) > self.log.term():
                self.cluster.observe_term(int(hello["term"]))
            self._send(
                connection,
                {
                    "type": "HELLO_OK",
                    "id": self.config.server_id,
                    "role": self.cluster.role if self.cluster else self.config.role,
                    "term": self.log.term(),
                    "last_term": self.log.last_term(),
                    "last_index": self.log.last_index(),
                    "commit_index": self.log.commit_index(),
                },
            )
            while not self._stop.is_set():
                line = reader.readline()
                if not line:
                    return
                message = json.loads(line.decode("utf-8"))
                message_type = message.get("type")
                if message_type == "RB":
                    self._handle_rb(connection, message)
                elif message_type == "COMMIT":
                    self._handle_commit(connection, message)
                elif message_type == "ABORT":
                    self._handle_abort(connection, message)
                elif message_type == "SNAP":
                    self._handle_snap(connection, message)
                elif message_type == "HB":
                    self._handle_hb(connection, message)
                elif message_type == "VOTE":
                    self._handle_vote(connection, message)
                elif message_type == "COORD":
                    self._handle_coord(connection, message)
                elif message_type == "PING":
                    self._send(connection, {"type": "PONG"})
                else:
                    self._send(
                        connection,
                        {
                            "type": "ERROR",
                            "message": "Unknown message type",
                        },
                    )
        except (EOFError, OSError, ssl.SSLError, json.JSONDecodeError):
            return
        finally:
            with self._lock:
                self._connections.discard(connection)
            try:
                connection.close()
            except OSError:
                pass

    def _handle_rb(self, connection, message):
        term = int(message["term"])
        index = int(message["index"])
        if term < self.log.term():
            self._send(connection, {"type": "ERROR", "message": "stale term"})
            return
        if self.cluster is not None:
            self.cluster.observe_leader(term, message.get("leader"))
        payload = json.dumps(message["op"], separators=(",", ":"))
        self.log.append(term, index, payload)
        self._send(
            connection,
            {
                "type": "ACK",
                "term": term,
                "index": index,
                "id": self.config.server_id,
                "status": "ok",
            },
        )

    def _handle_commit(self, connection, message):
        term = int(message["term"])
        index = int(message["index"])
        if term < self.log.term():
            self._send(connection, {"type": "ERROR", "message": "stale term"})
            return
        if self.cluster is not None:
            self.cluster.observe_leader(term, message.get("leader"))
        with self._apply_lock:
            last_applied = int(self.log.get_meta("last_applied", "0"))
            try:
                for current in range(last_applied + 1, index + 1):
                    entry = self.log.get(term, current)
                    if entry is None:
                        raise ReplicationError(
                            "Missing entry {} for commit.".format(current)
                        )
                    self.store.apply_operation(entry["payload"])
                    self.log.mark_committed(term, current)
                    self.log.set_meta("last_applied", current)
            except Exception as error:
                self._send(
                    connection,
                    {"type": "ERROR", "message": str(error)},
                )
                return
            self.log.set_meta("commit_index", index)
            self._send(
                connection,
                {"type": "COMMITTED", "term": term, "index": index},
            )

    def _handle_abort(self, connection, message):
        term = int(message["term"])
        index = int(message["index"])
        if term < self.log.term():
            self._send(connection, {"type": "ERROR", "message": "stale term"})
            return
        self.log.truncate_from(term, index)
        self._send(
            connection,
            {"type": "ABORTED", "term": term, "index": index},
        )

    def _handle_snap(self, connection, message):
        term = int(message["term"])
        index = int(message["index"])
        if term < self.log.term():
            self._send(connection, {"type": "ERROR", "message": "stale term"})
            return
        if self.cluster is not None:
            self.cluster.observe_leader(term, message.get("leader"))
        with self._apply_lock:
            last_applied = int(self.log.get_meta("last_applied", "0"))
            if index > last_applied:
                self.store.import_snapshot(message["snapshot"])
                self.log.reset_to(term, index)
        self._send(
            connection,
            {"type": "SNAP_OK", "term": term, "index": index},
        )

    def _handle_hb(self, connection, message):
        accepted = self.cluster.handle_hb(message) if self.cluster else True
        if accepted:
            self._send(
                connection,
                {
                    "type": "HB_OK",
                    "term": self.log.term(),
                    "id": self.config.server_id,
                    "commit_index": self.log.commit_index(),
                    "last_index": self.log.last_index(),
                },
            )
        else:
            self._send(
                connection,
                {"type": "HB_ERROR", "term": self.log.term()},
            )

    def _handle_vote(self, connection, message):
        granted = self.cluster.handle_vote(message) if self.cluster else False
        self._send(
            connection,
            {
                "type": "VOTE_OK",
                "term": self.log.term(),
                "id": self.config.server_id,
                "granted": bool(granted),
            },
        )

    def _handle_coord(self, connection, message):
        accepted = self.cluster.handle_coord(message) if self.cluster else True
        self._send(
            connection,
            {
                "type": "COORD_OK" if accepted else "COORD_ERROR",
                "term": self.log.term(),
            },
        )


class NoQuorumError(Exception):
    """Raised when fewer than a majority of replicas acknowledge an operation."""


class Replicator:
    """Primary-side reliable broadcast and quorum coordinator."""

    def __init__(self, config, log):
        self.config = config
        self.log = log
        self.peers = parse_peers(config.peers)
        self.quorum = (1 + len(self.peers)) // 2 + 1
        self._lock = threading.RLock()

    def replicate(self, operation):
        """Replicate one operation and return its committed log index."""
        with self._lock:
            term = self.log.term()
            index = self.log.next_index()
            message = {
                "type": "RB",
                "term": term,
                "index": index,
                "leader": self.config.server_id,
                "op": operation,
            }
            payload = json.dumps(operation, separators=(",", ":"))
            acknowledged, connections = self._broadcast(message)
            if 1 + acknowledged < self.quorum:
                for connection in connections:
                    try:
                        connection.send(
                            {"type": "ABORT", "term": term, "index": index}
                        )
                    except (OSError, ReplicationError):
                        pass
                    finally:
                        connection.close()
                raise NoQuorumError(index)
            self.log.append(term, index, payload, committed=True)
            self.log.set_meta("commit_index", index)
            for connection in connections:
                try:
                    connection.send(
                        {
                            "type": "COMMIT",
                            "term": term,
                            "index": index,
                            "leader": self.config.server_id,
                        }
                    )
                except (OSError, ReplicationError):
                    pass
                finally:
                    connection.close()
            return index

    def _broadcast(self, message):
        acknowledged = 0
        connections = []
        if not self.peers:
            return acknowledged, connections
        with ThreadPoolExecutor(max_workers=len(self.peers)) as executor:
            results = list(
                executor.map(
                    lambda peer: (peer, self._send_to_peer(peer, message)),
                    self.peers,
                )
            )
        for _, connection in results:
            if connection is not None:
                acknowledged += 1
                connections.append(connection)
        return acknowledged, connections

    def _send_to_peer(self, peer, message):
        for _ in range(2):
            connection = PeerConnection(self.config, peer)
            try:
                connection.connect()
                connection.send(message)
                response = connection.recv()
                if (
                    response.get("type") == "ACK"
                    and int(response.get("index", -1)) == int(message["index"])
                ):
                    return connection
            except (OSError, ReplicationError, json.JSONDecodeError):
                pass
            connection.close()
        return None
