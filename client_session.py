"""Client-side protocol session shared by the CLI, worker, and future GUI."""

import socket
import ssl
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


@dataclass(frozen=True)
class FileStat:
    rev: int
    digest: str
    size: int


class ClientSession:
    """Manage one authenticated TLS connection to the file server."""

    def __init__(self, config):
        self.config = config
        self.socket = None
        self.reader = None
        self.username = None

    def connect(self):
        """Open a verified TLS connection to the configured server."""
        raw = socket.create_connection(
            (self.config.server, self.config.port), timeout=10
        )
        server_name = self.config.tls_server_name or self.config.server
        context = client_context(self.config.tls_ca_file)
        self.socket = context.wrap_socket(raw, server_hostname=server_name)
        self.reader = szasar.SocketReader(self.socket)

    def close(self):
        """Close the connection, notifying the server when possible."""
        if self.socket is not None:
            try:
                self._command(szasar.Command.Exit)
            except (OSError, EOFError, ssl.SSLError, SyncError):
                pass
            self.socket.close()
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

    def upload(self, owner, path, data, rev=None, digest=None):
        query = "size={}".format(len(data))
        if rev is not None:
            query += "&rev={}".format(rev)
        if digest is not None:
            query += "&hash={}".format(digest)
        self._command(
            "{}{}?{}".format(
                szasar.Command.Upload, self._address(owner, path), query
            )
        )
        self.socket.sendall((szasar.Command.Upload2 + "\r\n").encode("ascii"))
        self.socket.sendall(data)
        self._read_response()

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

    def delete(self, owner, path):
        self._command(
            "{}{}".format(szasar.Command.Delete, self._address(owner, path))
        )

    def mkdir(self, owner, path):
        self._command(
            "{}{}".format(szasar.Command.MakeDir, self._address(owner, path))
        )

    def rmdir(self, owner, path):
        self._command(
            "{}{}".format(szasar.Command.RemoveDir, self._address(owner, path))
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
