class Command:
    """Commands supported by the line-based file service protocol."""

    User, Password, Download, Download2, Upload, Upload2, Delete, Exit = (
        "USER",
        "PASS",
        "DOWN",
        "DOW2",
        "UPLO",
        "UPL2",
        "DELE",
        "EXIT",
    )


def recvline(s, removeEOL=True):
    """Read one CRLF-terminated line from a socket.

    Args:
        s: Socket from which to read.
        removeEOL: Whether to omit the trailing CRLF from the result.

    Returns:
        The received line as bytes.

    Raises:
        EOFError: If the peer closes the connection before sending CRLF.
    """
    line = b""
    CRreceived = False
    while True:
        c = s.recv(1)
        if c == b"":
            raise EOFError("Connection closed by the peer before receiving an EOL.")
        line += c
        if c == b"\r":
            CRreceived = True
        elif c == b"\n" and CRreceived:
            if removeEOL:
                return line[:-2]
            else:
                return line
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
