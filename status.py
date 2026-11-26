"""Health check for a running Cloud File Service instance."""

from __future__ import annotations

import argparse
import http.client
import socket
import ssl

from config import load_config


def _tls_context(ca_file: str):
    ctx = ssl.create_default_context(cafile=ca_file) if ca_file else ssl.create_default_context()
    ctx.check_hostname = False
    return ctx


def _target(value):
    return value if value and value != "0.0.0.0" else "127.0.0.1"


def run_status(config_path=None, kind="server") -> int:
    config = load_config(config_path, kind=kind)
    server = config.server
    client = config.client

    failures = 0

    host = _target(client.server or server.host)
    port = server.port or client.port

    # 1. PRIM over TLS.
    try:
        ctx = _tls_context(client.tls_ca_file or server.tls_ca_file)
        with socket.create_connection((host, port), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=client.tls_server_name or None) as tls_sock:
                tls_sock.sendall(b"PRIM\r\n")
                response = b""
                while b"\n" not in response and len(response) < 256:
                    chunk = tls_sock.recv(64)
                    if not chunk:
                        break
                    response += chunk
        print("PRIM:      {}".format(response.decode("utf-8", "replace").strip()))
    except Exception as error:
        print("PRIM:      FAILED ({})".format(error))
        failures += 1

    # 2. Admin panel.
    try:
        ctx = _tls_context(client.tls_ca_file or server.tls_ca_file)
        conn = http.client.HTTPSConnection(
            _target(server.admin_host or client.server),
            server.admin_port,
            context=ctx,
            timeout=5,
        )
        conn.request("GET", "/")
        reply = conn.getresponse()
        print("Panel:     HTTP {} {}".format(reply.status, reply.reason))
        conn.close()
        if reply.status >= 400 and reply.status != 303:
            failures += 1
    except Exception as error:
        print("Panel:     FAILED ({})".format(error))
        failures += 1

    print("Server:    {}:{}".format(host, port))
    print("Admin:     {}:{}".format(_target(server.admin_host or client.server), server.admin_port))

    return 1 if failures else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cloudfs status", description="Check a Cloud File Service instance.")
    parser.add_argument("--config", default=None, help="Path to a TOML config file.")
    parser.add_argument("--kind", default="server", choices=("server", "client"))
    args = parser.parse_args(argv)
    return run_status(args.config, args.kind)


if __name__ == "__main__":
    raise SystemExit(main())
