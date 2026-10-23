"""Protocol constants, framing helpers, and path encoding."""

from urllib.parse import quote, unquote

DEFAULT_MAX_LINE = 8192


class LineTooLong(ValueError):
    """Raised when a protocol line exceeds the configured maximum length."""


class Command:
    """Commands supported by the line-based file service protocol."""

    (
        User,
        Password,
        Download,
        Download2,
        Upload,
        Upload2,
        MakeDir,
        RemoveDir,
        Delete,
        Exit,
        Sync,
        Stat,
        Register,
        ChangePassword,
        Users,
        Prim,
    ) = (
        "USER",
        "PASS",
        "DOWN",
        "DOW2",
        "UPLO",
        "UPL2",
        "MKDR",
        "RMDR",
        "DELE",
        "EXIT",
        "SYNC",
        "STAT",
        "REGI",
        "CHPW",
        "USRS",
        "PRIM",
    )


def encode_path(path: str) -> str:
    """Encode a relative path so tabs, newlines, and question marks are safe."""
    return quote(path, safe="/")


def decode_path(value: str) -> str:
    """Decode a path previously produced by :func:`encode_path`."""
    return unquote(value)


class SocketReader:
    """Buffered reader shared by protocol lines and raw payloads."""

    def __init__(self, sock, max_line=DEFAULT_MAX_LINE):
        self.sock = sock
        self.max_line = max_line
        self.buffer = bytearray()

    def _fill(self):
        chunk = self.sock.recv(65536)
        if chunk == b"":
            raise EOFError("Connection closed before a complete message.")
        self.buffer.extend(chunk)

    def readline(self, remove_eol=True):
        """Read one CRLF-terminated line, raising when it exceeds max_line."""
        while True:
            index = self.buffer.find(b"\r\n")
            if index >= 0:
                if index > self.max_line:
                    raise LineTooLong(
                        "Line exceeds {} bytes.".format(self.max_line)
                    )
                line = bytes(self.buffer[:index])
                del self.buffer[: index + 2]
                return line if remove_eol else line + b"\r\n"
            if len(self.buffer) > self.max_line:
                raise LineTooLong("Line exceeds {} bytes.".format(self.max_line))
            self._fill()

    def read_exact(self, size):
        """Read exactly ``size`` bytes, using buffered data when available."""
        while len(self.buffer) < size:
            self._fill()
        data = bytes(self.buffer[:size])
        del self.buffer[:size]
        return data


def recvline(s, removeEOL=True, max_length=DEFAULT_MAX_LINE):
    """Read one CRLF-terminated line from a socket.

    Args:
        s: Socket from which to read.
        removeEOL: Whether to omit the trailing CRLF from the result.
        max_length: Maximum accepted line length in bytes.

    Returns:
        The received line as bytes.

    Raises:
        EOFError: If the peer closes the connection before sending CRLF.
        LineTooLong: If the line exceeds ``max_length`` bytes.
    """
    line = bytearray()
    CRreceived = False
    while True:
        c = s.recv(1)
        if c == b"":
            raise EOFError("Connection closed by the peer before receiving an EOL.")
        line += c
        if len(line) > max_length + 2:
            raise LineTooLong("Line exceeds {} bytes.".format(max_length))
        if c == b"\r":
            CRreceived = True
        elif c == b"\n" and CRreceived:
            if removeEOL:
                return bytes(line[:-2])
            return bytes(line)
        else:
            CRreceived = False


def recvall(s, size):
    """Read exactly ``size`` bytes from a socket.

    Args:
        s: Socket from which to read.
        size: Number of bytes required.

    Returns:
        The received bytes.

    Raises:
        EOFError: If the peer closes the connection before enough data arrives.
    """
    message = b""
    while len(message) < size:
        chunk = s.recv(size - len(message))
        if chunk == b"":
            raise EOFError(
                "Connection closed by the peer before receiving the requested {} bytes.".format(
                    size
                )
            )
        message += chunk
    return message
