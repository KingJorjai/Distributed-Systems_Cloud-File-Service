#!/usr/bin/env python3
"""Check LAN connectivity and TLS for a generated demo layout."""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys

from demo_lan_config import parse_server_specs

DEFAULT_TIMEOUT = 5.0


def _tls_context(ca_file, cert_file=None, key_file=None):
    context = ssl.create_default_context(cafile=ca_file or None)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    if cert_file and key_file:
        context.load_cert_chain(cert_file, key_file)
    return context


def _readline(sock, limit=8192):
    data = bytearray()
    while len(data) <= limit:
        chunk = sock.recv(1)
        if not chunk:
            raise OSError("Connection closed.")
        data.extend(chunk)
        if data.endswith(b"\r\n"):
            return bytes(data[:-2])
    raise OSError("Line too long.")


def _tcp(host, port, timeout):
    with socket.create_connection((host, port), timeout=timeout):
        return True


def _tls(host, port, ca_file, timeout, cert_file=None, key_file=None):
    context = _tls_context(ca_file, cert_file, key_file)
    with socket.create_connection((host, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            return tls.version()


def _prim(host, port, ca_file, timeout):
    context = _tls_context(ca_file)
    with socket.create_connection((host, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            tls.sendall(b"PRIM\r\n")
            return _readline(tls).decode("ascii", "replace")


def _admin_health(host, port, ca_file, timeout):
    context = _tls_context(ca_file)
    with socket.create_connection((host, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            tls.sendall(
                "GET /healthz HTTP/1.0\r\nHost: {}:{}\r\n\r\n".format(
                    host, port
                ).encode("ascii")
            )
            data = bytearray()
            while True:
                chunk = tls.recv(4096)
                if not chunk:
                    break
                data.extend(chunk)
            text = bytes(data).decode("utf-8", "replace")
            status = text.split("\r\n", 1)[0]
            body = text.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in text else ""
            return status, body.strip()


def _replication_hello(host, port, ca_file, timeout, cert_file, key_file, token):
    context = _tls_context(ca_file, cert_file, key_file)
    payload = {
        "type": "HELLO",
        "id": "lan-check",
        "role": "primary",
        "term": 1,
        "last_index": 0,
        "commit_index": 0,
        "token": token,
    }
    with socket.create_connection((host, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            tls.sendall(
                (json.dumps(payload, separators=(",", ":")) + "\r\n").encode(
                    "utf-8"
                )
            )
            return json.loads(_readline(tls).decode("utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--server",
        action="append",
        required=True,
        dest="servers",
        help="id@host[:client[:replication[:admin]]]",
    )
    parser.add_argument("--ca", default="")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--client-cert", default="")
    parser.add_argument("--client-key", default="")
    parser.add_argument("--token", default="")
    args = parser.parse_args(argv)
    try:
        servers = parse_server_specs(args.servers)
    except ValueError as error:
        print("error: {}".format(error), file=sys.stderr)
        return 2

    failures = []

    def report(label, ok, detail=""):
        prefix = "ok" if ok else "FAIL"
        print("[{}] {}{}".format(prefix, label, ": " + detail if detail else ""))
        if not ok:
            failures.append(label)

    for server in servers:
        try:
            _tcp(server.host, server.client_port, args.timeout)
            report(
                "{} client tcp {}:{}".format(
                    server.server_id, server.host, server.client_port
                ),
                True,
            )
            version = _tls(
                server.host, server.client_port, args.ca, args.timeout
            )
            report(
                "{} client tls {}:{}".format(
                    server.server_id, server.host, server.client_port
                ),
                True,
                version,
            )
            prim = _prim(
                server.host, server.client_port, args.ca, args.timeout
            )
            report(
                "{} PRIM {}:{}".format(
                    server.server_id, server.host, server.client_port
                ),
                prim.startswith("OK"),
                prim,
            )
        except (OSError, ssl.SSLError, ValueError) as error:
            report(
                "{} client {}".format(server.server_id, server.host),
                False,
                str(error),
            )

        try:
            _tcp(server.host, server.replication_port, args.timeout)
            report(
                "{} replication tcp {}:{}".format(
                    server.server_id, server.host, server.replication_port
                ),
                True,
            )
            if args.client_cert and args.client_key:
                hello = _replication_hello(
                    server.host,
                    server.replication_port,
                    args.ca,
                    args.timeout,
                    args.client_cert,
                    args.client_key,
                    args.token,
                )
                report(
                    "{} replication mTLS {}:{}".format(
                        server.server_id, server.host, server.replication_port
                    ),
                    hello.get("type") == "HELLO_OK",
                    hello.get("type", ""),
                )
        except (OSError, ssl.SSLError, ValueError) as error:
            report(
                "{} replication {}".format(server.server_id, server.host),
                False,
                str(error),
            )

        try:
            status, body = _admin_health(
                server.host, server.admin_port, args.ca, args.timeout
            )
            report(
                "{} admin {}:{}".format(
                    server.server_id, server.host, server.admin_port
                ),
                status.startswith("HTTP/"),
                "{} {}".format(status, body),
            )
        except (OSError, ssl.SSLError, ValueError) as error:
            report(
                "{} admin {}".format(server.server_id, server.host),
                False,
                str(error),
            )

    if failures:
        print("\n{} check(s) failed.".format(len(failures)), file=sys.stderr)
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
