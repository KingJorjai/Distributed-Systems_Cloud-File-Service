"""Multithreaded TLS server runtime and client session state machine."""

import hashlib
import shutil
import socket
import ssl
import threading
from pathlib import Path
from urllib.parse import parse_qs

import szasar
from auth import validate_password, validate_username
from file_store import (
    AccessDeniedError,
    ConflictError,
    FileStore,
    InvalidPasswordError,
    InvalidPathError,
    NotFoundError,
    UserDisabledError,
    UserExistsError,
    UserNotFoundError,
)
from replication import (
    NoQuorumError,
    ReplicationLog,
    ReplicationServer,
    Replicator,
)
from tls import server_context


class NotPrimaryError(Exception):
    """Raised when a mutation is sent to a secondary."""


class State:
    """States used by one client session."""

    Identification, Authentication, Main, Downloading, Uploading = range(5)


def sendOK(s, params=""):
    """Send a successful protocol response with optional parameters."""
    s.sendall(("OK{}\r\n".format(params)).encode("ascii"))


def sendER(s, code=1):
    """Send a protocol error response with an error code."""
    s.sendall(("ER{}\r\n".format(code)).encode("ascii"))


def _split_target(user, payload):
    """Resolve a raw payload into ``(owner, path)``.

    A leading ``@`` marks a shared-file address. Ordinary paths that begin with
    ``@`` are encoded by the client, so they never reach this function raw.
    """
    if payload.startswith("@"):
        owner, separator, encoded_path = payload[1:].partition("/")
        if not separator or not owner or not encoded_path:
            raise InvalidPathError("Invalid shared path.")
        return owner, szasar.decode_path(encoded_path)
    return user, szasar.decode_path(payload)


def _parse_upload(payload):
    encoded_target, separator, query = payload.partition("?")
    if not separator:
        raise ValueError("Missing upload parameters.")
    parameters = parse_qs(query, keep_blank_values=True)
    if "size" in parameters:
        filesize = int(parameters["size"][0])
    elif query.isdigit():
        filesize = int(query)
    else:
        raise ValueError("Missing upload size.")
    revision = int(parameters["rev"][0]) if "rev" in parameters else None
    digest = parameters.get("hash", [None])[0]
    client_id = parameters.get("client", [None])[0]
    return encoded_target, filesize, revision, digest, client_id


def _parse_delete(payload):
    encoded_target, separator, query = payload.partition("?")
    parameters = parse_qs(query, keep_blank_values=True) if separator else {}
    revision = int(parameters["rev"][0]) if "rev" in parameters else None
    client_id = parameters.get("client", [None])[0]
    return encoded_target, revision, client_id


def session(sock, runtime):
    """Serve one authenticated client session until it disconnects."""
    reader = szasar.SocketReader(sock)
    config = runtime.config
    store = runtime.store
    state = State.Identification
    user = ""
    owner = ""
    filename = ""
    filesize = 0
    revision = None
    expected_digest = None
    client_id = None
    download_data = b""

    while True:
        try:
            raw_message = reader.readline()
        except (EOFError, OSError, ssl.SSLError):
            try:
                sock.close()
            except OSError:
                pass
            return
        except szasar.LineTooLong:
            try:
                sendER(sock, 19)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
            return

        if raw_message == b"":
            sock.close()
            return
        try:
            message = raw_message.decode("ascii")
        except UnicodeDecodeError:
            sendER(sock, 1)
            continue

        if message.startswith(szasar.Command.User):
            if state != State.Identification:
                sendER(sock)
                continue
            candidate = message[4:]
            if not candidate:
                sendER(sock, 2)
                continue
            if candidate == "anonimous":
                user = candidate
                sendOK(sock)
                state = State.Authentication
                continue
            record = store.get_user(candidate)
            if record is None:
                sendER(sock, 2)
            elif record.disabled:
                sendER(sock, 17)
            else:
                user = candidate
                sendOK(sock)
                state = State.Authentication

        elif message.startswith(szasar.Command.Register):
            if state != State.Identification:
                sendER(sock)
                continue
            if runtime.config.role != "primary":
                sendER(sock, 13)
                continue
            if not config.registration_enabled:
                sendER(sock, 15)
                continue
            username, separator, encoded_password = message[4:].partition("?")
            if not separator:
                sendER(sock, 16)
                continue
            password = szasar.decode_path(encoded_password)
            if not validate_username(username) or not validate_password(password):
                sendER(sock, 16)
                continue
            try:
                operation = store.plan_user_create(username, password)
                runtime.commit_operation({"operations": [operation]})
            except UserExistsError:
                sendER(sock, 18)
            except NoQuorumError:
                sendER(sock, 12)
            except NotPrimaryError:
                sendER(sock, 13)
            except Exception:
                sendER(sock, 16)
            else:
                sendOK(sock)

        elif message.startswith(szasar.Command.Password):
            if state != State.Authentication:
                sendER(sock)
                continue
            password = message[4:]
            try:
                if user == "anonimous":
                    if password:
                        raise InvalidPasswordError(user)
                else:
                    store.authenticate(user, password)
            except UserDisabledError:
                sendER(sock, 17)
                state = State.Identification
            except (UserNotFoundError, InvalidPasswordError):
                sendER(sock, 3)
                state = State.Identification
            else:
                sendOK(sock)
                state = State.Main

        elif message.startswith(szasar.Command.Sync):
            if state != State.Main:
                sendER(sock)
                continue
            entries = store.manifest(user)
            sendOK(sock, len(entries))
            for entry in entries:
                line = "{}\t{}\t{}\t{}\t{}\t{}\t{}\r\n".format(
                    entry.owner,
                    szasar.encode_path(entry.path),
                    entry.rev,
                    entry.digest,
                    entry.size,
                    int(entry.deleted),
                    entry.access,
                )
                sock.sendall(line.encode("ascii"))
            sock.sendall(b"END\r\n")

        elif message.startswith(szasar.Command.Stat):
            if state != State.Main:
                sendER(sock)
                continue
            try:
                target_owner, target_path = _split_target(user, message[4:])
                store.access_for(user, target_owner, target_path)
                record = store.stat(target_owner, target_path)
                if record is None or record.deleted:
                    raise NotFoundError(target_path)
            except (InvalidPathError, AccessDeniedError, NotFoundError):
                sendER(sock, 5)
            else:
                sendOK(
                    sock,
                    "{}\t{}\t{}".format(record.rev, record.digest, record.size),
                )

        elif message.startswith(szasar.Command.Users):
            if state != State.Main:
                sendER(sock)
                continue
            users = [
                record.username
                for record in store.list_users()
                if not record.disabled and record.username != "anonimous"
            ]
            sendOK(sock, len(users))
            for username in users:
                sock.sendall((username + "\r\n").encode("ascii"))
            sock.sendall(b"END\r\n")

        elif message.startswith(szasar.Command.ChangePassword):
            if state != State.Main:
                sendER(sock)
                continue
            if runtime.config.role != "primary":
                sendER(sock, 13)
                continue
            if user == "anonimous":
                sendER(sock, 7)
                continue
            old_encoded, separator, new_encoded = message[4:].partition("?")
            if not separator:
                sendER(sock, 16)
                continue
            old_password = szasar.decode_path(old_encoded)
            new_password = szasar.decode_path(new_encoded)
            if not validate_password(new_password):
                sendER(sock, 16)
                continue
            try:
                store.authenticate(user, old_password)
                operation = store.plan_user_password(user, new_password)
                runtime.commit_operation({"operations": [operation]})
            except (UserNotFoundError, UserDisabledError):
                sendER(sock, 17)
            except NoQuorumError:
                sendER(sock, 12)
            except NotPrimaryError:
                sendER(sock, 13)
            except Exception:
                sendER(sock, 3)
            else:
                sendOK(sock)

        elif message.startswith(szasar.Command.Upload):
            if state != State.Main:
                sendER(sock)
                continue
            if runtime.config.role != "primary":
                sendER(sock, 13)
                continue
            if user == "anonimous":
                sendER(sock, 7)
                continue
            try:
                (
                    encoded_target,
                    filesize,
                    revision,
                    expected_digest,
                    client_id,
                ) = _parse_upload(message[4:])
                owner, filename = _split_target(user, encoded_target)
                store.access_for(user, owner, filename, write=True)
            except (InvalidPathError, AccessDeniedError, ValueError, IndexError):
                sendER(sock, 10)
                continue
            if filesize < 0 or filesize > config.max_file_size:
                sendER(sock, 8)
                continue
            try:
                free = shutil.disk_usage(store.root).free
            except OSError:
                sendER(sock, 9)
                continue
            if filesize + config.space_margin > free:
                sendER(sock, 9)
                continue
            sendOK(sock)
            state = State.Uploading

        elif message.startswith(szasar.Command.Upload2):
            if state != State.Uploading:
                sendER(sock)
                continue
            state = State.Main
            if runtime.config.role != "primary":
                sendER(sock, 13)
                continue
            try:
                data = reader.read_exact(filesize)
                if expected_digest is not None:
                    actual = hashlib.sha256(data).hexdigest()
                    if actual != expected_digest:
                        raise ValueError("Hash mismatch.")
                operations, record, conflict = store.plan_put_with_conflict(
                    owner,
                    filename,
                    data,
                    expected_rev=revision,
                    client_id=client_id,
                )
                runtime.commit_operation({"operations": operations})
            except ConflictError:
                sendER(sock, 20)
            except NoQuorumError:
                sendER(sock, 12)
            except NotPrimaryError:
                sendER(sock, 13)
            except (OSError, EOFError, ValueError, AccessDeniedError):
                sendER(sock, 10)
            else:
                response = str(record.rev)
                if conflict is not None:
                    response += "\t" + szasar.encode_path(conflict.path)
                sendOK(sock, response)

        elif message.startswith(szasar.Command.Download):
            if state != State.Main:
                sendER(sock)
                continue
            try:
                owner, filename = _split_target(user, message[4:])
                store.access_for(user, owner, filename)
                data, record = store.get(owner, filename)
            except (InvalidPathError, AccessDeniedError, NotFoundError, ValueError):
                sendER(sock, 5)
                continue
            download_data = data
            sendOK(sock, len(download_data))
            state = State.Downloading

        elif message.startswith(szasar.Command.Download2):
            if state != State.Downloading:
                sendER(sock)
                continue
            state = State.Main
            sendOK(sock)
            sock.sendall(download_data)

        elif message.startswith(szasar.Command.MakeDir):
            if state != State.Main:
                sendER(sock)
                continue
            if runtime.config.role != "primary":
                sendER(sock, 13)
                continue
            if user == "anonimous":
                sendER(sock, 7)
                continue
            try:
                owner, filename = _split_target(user, message[4:])
                store.access_for(user, owner, filename, write=True)
                operations = store.plan_mkdir(owner, filename)
                runtime.commit_operation({"operations": operations})
            except (InvalidPathError, AccessDeniedError, OSError):
                sendER(sock, 11)
            except NoQuorumError:
                sendER(sock, 12)
            except NotPrimaryError:
                sendER(sock, 13)
            else:
                sendOK(sock)

        elif message.startswith(szasar.Command.RemoveDir):
            if state != State.Main:
                sendER(sock)
                continue
            if runtime.config.role != "primary":
                sendER(sock, 13)
                continue
            if user == "anonimous":
                sendER(sock, 7)
                continue
            try:
                owner, filename = _split_target(user, message[4:])
                store.access_for(user, owner, filename, write=True)
                operations = store.plan_rmdir(owner, filename)
                runtime.commit_operation({"operations": operations})
            except (InvalidPathError, AccessDeniedError, OSError):
                sendER(sock, 11)
            except NoQuorumError:
                sendER(sock, 12)
            except NotPrimaryError:
                sendER(sock, 13)
            else:
                sendOK(sock)

        elif message.startswith(szasar.Command.Delete):
            if state != State.Main:
                sendER(sock)
                continue
            if runtime.config.role != "primary":
                sendER(sock, 13)
                continue
            if user == "anonimous":
                sendER(sock, 7)
                continue
            try:
                encoded_target, revision, client_id = _parse_delete(message[4:])
                owner, filename = _split_target(user, encoded_target)
                store.access_for(user, owner, filename, write=True)
                operations, record, conflict = store.plan_delete_with_conflict(
                    owner,
                    filename,
                    expected_rev=revision,
                    client_id=client_id,
                )
                runtime.commit_operation({"operations": operations})
            except (InvalidPathError, AccessDeniedError, OSError, ValueError):
                sendER(sock, 11)
            except NoQuorumError:
                sendER(sock, 12)
            except NotPrimaryError:
                sendER(sock, 13)
            else:
                response = str(record.rev)
                if conflict is not None:
                    response += "\t" + szasar.encode_path(conflict.path)
                sendOK(sock, response)

        elif message.startswith(szasar.Command.Exit):
            sendOK(sock)
            sock.close()
            return

        else:
            sendER(sock)


class ServerRuntime:
    """Accept TLS connections and serve one session thread per client."""

    def __init__(self, config, store, log=None):
        self.config = config
        self.store = store
        self.log = log or ReplicationLog(
            Path(config.files_path) / ".replication.sqlite3",
            term=config.term,
        )
        self.replicator = None
        self.replication_server = None
        self._replication_thread = None
        self._socket = None
        self._stop = threading.Event()
        self.port = None

    def start(self):
        """Bind the listening socket and start the configured cluster role."""
        self._tls = server_context(
            self.config.tls_cert_file, self.config.tls_key_file
        )
        if self.config.role == "primary":
            self.replicator = Replicator(self.config, self.log)
        else:
            self.replication_server = ReplicationServer(
                self.config, self.store, self.log
            )
            self.replication_server.start()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.config.host, self.config.port))
        listener.listen(5)
        listener.settimeout(0.2)
        self._socket = listener
        self.port = listener.getsockname()[1]

    def serve_forever(self):
        """Accept connections until :meth:`stop` is called."""
        if self.replication_server is not None:
            self._replication_thread = threading.Thread(
                target=self.replication_server.serve_forever, daemon=True
            )
            self._replication_thread.start()
        while not self._stop.is_set():
            try:
                connection, _ = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                connection = self._tls.wrap_socket(connection, server_side=True)
            except (OSError, ssl.SSLError):
                connection.close()
                continue
            thread = threading.Thread(
                target=session, args=(connection, self), daemon=True
            )
            thread.start()

    def commit_operation(self, operation):
        """Commit a deterministic operation through replication and local apply."""
        if self.config.role != "primary":
            raise NotPrimaryError("This server is not the primary.")
        if self.replicator is not None:
            self.replicator.replicate(operation)
        self.store.apply_operation(operation)

    def require_primary(self):
        if self.config.role != "primary":
            raise NotPrimaryError("This server is not the primary.")

    def stop(self):
        """Stop accepting new connections."""
        self._stop.set()
        if self.replication_server is not None:
            self.replication_server.stop()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        if self.log is not None:
            self.log.close()


def create_server(config, passwords=None):
    """Build a runtime from an AppConfig or a ServerConfig."""
    server_config = getattr(config, "server", config)
    configured_passwords = passwords or getattr(config, "passwords", {})
    store = FileStore(server_config.files_path)
    if configured_passwords:
        for username in ("sar", "sza"):
            password = configured_passwords.get(username, "")
            salt = hashlib.sha256(
                "{}:{}:{}".format(
                    server_config.cluster_token, username, password or "disabled"
                ).encode("utf-8")
            ).digest()[:16]
            store.ensure_bootstrap_user(
                username,
                password,
                "admin",
                salt=salt,
                created_at="1970-01-01T00:00:00+00:00",
            )
    store.backfill()
    log = ReplicationLog(
        Path(server_config.files_path) / ".replication.sqlite3",
        term=server_config.term,
    )
    return ServerRuntime(server_config, store, log)
