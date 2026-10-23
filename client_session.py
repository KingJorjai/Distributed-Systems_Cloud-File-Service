"""Client-side protocol session shared by the CLI, worker, and future GUI."""

import socket
import ssl
import threading
from dataclasses import dataclass
from urllib.parse import quote

import szasar
from file_store import ManifestEntry
from tls import client_context


class SyncError(Exception):
    """Raised when the server rejects a synchronization request."""

    def __init__(self, code, message=""):
        self.code = int(code)
        super().__init__(message or "ER{}".format(self.code))


class NoServerError(Exception):
    """Raised when none of the configured client endpoints is reachable."""


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int


@dataclass(frozen=True)
class ShareInfo:
    owner: str
    path: str
    grantee: str
    access: str


@dataclass(frozen=True)
class RemoteUpdate:
    owner: str
    path: str
    rev: int
    digest: str
    size: int
    op: str
    access: str
    client_id: str


def parse_client_endpoints(value, default_host, default_port):
    """Parse ``host:port,...`` or fall back to the configured single server."""
    endpoints = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        host, port = item.rsplit(":", 1)
        endpoints.append(Endpoint(host, int(port)))
    if not endpoints:
        endpoints.append(Endpoint(default_host, int(default_port)))
    return endpoints


@dataclass(frozen=True)
class FileStat:
    rev: int
    digest: str
    size: int


@dataclass(frozen=True)
class UploadResult:
    rev: int | None
    conflict_path: str | None


@dataclass(frozen=True)
class DeleteResult:
    rev: int | None
    conflict_path: str | None


class ClientSession:
    """Manage one authenticated TLS connection to the file server."""

    def __init__(self, config):
        self.config = config
        self.endpoints = parse_client_endpoints(
            getattr(config, "peers", ""), config.server, config.port
        )
        self.endpoint_index = 0
        self.current_endpoint = None
        self.socket = None
        self.reader = None
        self.username = None
        self._close_lock = threading.Lock()

    def _connect_endpoint(self, endpoint):
        raw = socket.create_connection((endpoint.host, endpoint.port), timeout=10)
        server_name = self.config.tls_server_name or endpoint.host
        context = client_context(self.config.tls_ca_file)
        self.socket = context.wrap_socket(raw, server_hostname=server_name)
        self.reader = szasar.SocketReader(self.socket)
        self.current_endpoint = endpoint

    def connect(self):
        """Open a verified TLS connection to one of the configured servers."""
        last_error = None
        for _ in range(len(self.endpoints)):
            endpoint = self.endpoints[self.endpoint_index]
            try:
                self._connect_endpoint(endpoint)
                return
            except OSError as error:
                last_error = error
                self._advance_endpoint()
        if last_error is not None:
            raise last_error
        raise NoServerError("No client endpoint is configured.")

    def _advance_endpoint(self):
        self.endpoint_index = (self.endpoint_index + 1) % len(self.endpoints)

    def resolve_primary(self):
        """Connect to a seed and follow ``PRIM`` to the current primary."""
        self.connect()
        for _ in range(3):
            response = self._command(szasar.Command.Prim)
            host, port = response.rsplit(":", 1)
            endpoint = Endpoint(host, int(port))
            if endpoint == self.current_endpoint:
                return
            self.socket.close()
            self.socket = None
            self.reader = None
            self._connect_endpoint(endpoint)
        raise NoServerError("Too many primary redirects.")

    def connect_and_login(self, username, password):
        """Find the current primary, log in, and retry other seeds if needed."""
        last_error = None
        for _ in range(len(self.endpoints)):
            try:
                self.resolve_primary()
                self.login(username, password)
                return
            except SyncError as error:
                self.close()
                if error.code == 13:
                    last_error = error
                    self._advance_endpoint()
                    continue
                raise
            except OSError as error:
                self.close()
                last_error = error
                self._advance_endpoint()
        raise NoServerError("No primary available: {}".format(last_error))

    def close(self):
        """Close the connection, notifying the server when possible."""
        with self._close_lock:
            if self.socket is None:
                return
            if self.reader is not None:
                try:
                    self._command(szasar.Command.Exit)
                except (OSError, EOFError, ssl.SSLError, SyncError, AttributeError):
                    pass
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None
            self.reader = None

    def _read_response(self):
        response = self.reader.readline().decode("ascii")
        if response.startswith("ER"):
            raise SyncError(response[2:])
        if not response.startswith("OK"):
            raise SyncError(1, "Respuesta inesperada: {}".format(response))
        return response[2:]

    def _command(self, command):
        self.socket.sendall((command + "\r\n").encode("ascii"))
        return self._read_response()

    def _address(self, owner, path):
        encoded = szasar.encode_path(path)
        if owner == self.username:
            return encoded
        return "@{}/{}".format(owner, encoded)

    def _parse_mutation(self, response):
        if not response:
            return None, None
        parts = response.split("\t", 1)
        rev = int(parts[0]) if parts[0] else None
        conflict = szasar.decode_path(parts[1]) if len(parts) > 1 else None
        return rev, conflict

    def register(self, username, password):
        """Register an open account and leave the connection unauthenticated."""
        encoded = quote(password, safe="")
        self._command("{}{}?{}".format(szasar.Command.Register, username, encoded))

    def login(self, username, password):
        """Authenticate the connection as ``username``."""
        self._command(szasar.Command.User + username)
        self._command(szasar.Command.Password + password)
        self.username = username

    def sync(self):
        """Return the authenticated user's current manifest."""
        count = int(self._command(szasar.Command.Sync))
        entries = []
        for _ in range(count):
            line = self.reader.readline().decode("ascii")
            owner, path, rev, digest, size, deleted, access = line.split("\t")
            entries.append(
                ManifestEntry(
                    owner=owner,
                    path=szasar.decode_path(path),
                    rev=int(rev),
                    digest=digest,
                    size=int(size),
                    deleted=bool(int(deleted)),
                    access=access,
                )
            )
        if self.reader.readline() != b"END":
            raise SyncError(1, "Manifest terminator missing.")
        return entries

    def stat(self, owner, path):
        response = self._command(
            "{}{}".format(szasar.Command.Stat, self._address(owner, path))
        )
        rev, digest, size = response.split("\t")
        return FileStat(int(rev), digest, int(size))

    def upload(
        self, owner, path, data, rev=None, digest=None, client_id=None
    ):
        query = "size={}".format(len(data))
        if rev is not None:
            query += "&rev={}".format(rev)
        if digest is not None:
            query += "&hash={}".format(digest)
        if client_id is not None:
            query += "&client={}".format(quote(client_id, safe=""))
        self._command(
            "{}{}?{}".format(
                szasar.Command.Upload, self._address(owner, path), query
            )
        )
        self.socket.sendall((szasar.Command.Upload2 + "\r\n").encode("ascii"))
        self.socket.sendall(data)
        return UploadResult(*self._parse_mutation(self._read_response()))

    def download(self, owner, path):
        size = int(
            self._command(
                "{}{}".format(
                    szasar.Command.Download, self._address(owner, path)
                )
            )
        )
        self.socket.sendall((szasar.Command.Download2 + "\r\n").encode("ascii"))
        self._read_response()
        return self.reader.read_exact(size)

    def delete(self, owner, path, rev=None, client_id=None):
        query = []
        if rev is not None:
            query.append("rev={}".format(rev))
        if client_id is not None:
            query.append("client={}".format(quote(client_id, safe="")))
        suffix = "?" + "&".join(query) if query else ""
        return DeleteResult(
            *self._parse_mutation(
                self._command(
                    "{}{}{}".format(
                        szasar.Command.Delete,
                        self._address(owner, path),
                        suffix,
                    )
                )
            )
        )

    def mkdir(self, owner, path):
        self._command(
            "{}{}".format(szasar.Command.MakeDir, self._address(owner, path))
        )

    def rmdir(self, owner, path):
        self._command(
            "{}{}".format(szasar.Command.RemoveDir, self._address(owner, path))
        )

    def subscribe(self, client_id):
        self._command("{}{}".format(szasar.Command.Subscribe, client_id))

    def read_notification(self):
        line = self.reader.readline().decode("ascii")
        if line.startswith("ER"):
            raise SyncError(line[2:])
        if not line.startswith("UPDT"):
            raise SyncError(1, "Unexpected notification: {}".format(line))
        fields = line[4:].split("\t")
        if len(fields) != 8:
            raise SyncError(1, "Malformed notification: {}".format(line))
        owner, path, rev, digest, size, op, access, client_id = fields
        return RemoteUpdate(
            owner=owner,
            path=szasar.decode_path(path),
            rev=int(rev),
            digest=digest,
            size=int(size),
            op=op,
            access=access,
            client_id=client_id,
        )

    def shares(self):
        count = int(self._command(szasar.Command.Shares))
        shares = []
        for _ in range(count):
            owner, path, grantee, access = (
                self.reader.readline().decode("ascii").split("\t")
            )
            shares.append(
                ShareInfo(owner, szasar.decode_path(path), grantee, access)
            )
        if self.reader.readline() != b"END":
            raise SyncError(1, "Share list terminator missing.")
        return shares

    def share(self, path, grantee, access):
        self._command(
            "{}{}?{}?{}".format(
                szasar.Command.Share,
                szasar.encode_path(path),
                grantee,
                access,
            )
        )

    def unshare(self, path, grantee):
        self._command(
            "{}{}?{}".format(
                szasar.Command.Unshare,
                szasar.encode_path(path),
                grantee,
            )
        )

    def users(self):
        count = int(self._command(szasar.Command.Users))
        names = [self.reader.readline().decode("ascii") for _ in range(count)]
        if self.reader.readline() != b"END":
            raise SyncError(1, "User list terminator missing.")
        return names

    def change_password(self, old_password, new_password):
        encoded_old = quote(old_password, safe="")
        encoded_new = quote(new_password, safe="")
        self._command(
            "{}{}?{}".format(
                szasar.Command.ChangePassword, encoded_old, encoded_new
            )
        )
