#!/usr/bin/env python3

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

from app_logging import configure
from client_session import ClientSession, NoServerError, SyncError
from config import ConfigurationError, load_config, validate_port
from daemon_client import ensure_daemon
from error_messages import message as error_message
from sync_client import SyncWorker
from version import __version__

running = True


def handler(signum, frame):
    global running
    print("\nCtrl+C received — shutting down gracefully")
    running = False


def iserror(text):
    if text.startswith("ER"):
        print(error_message(text[2:]))
        return True
    return False


def int2bytes(n):
    if n < 1 << 10:
        return str(n) + " B  "
    if n < 1 << 20:
        return str(round(n / (1 << 10))) + " KiB"
    if n < 1 << 30:
        return str(round(n / (1 << 20))) + " MiB"
    return str(round(n / (1 << 30))) + " GiB"


def parse_client_args(argv, config):
    """Parse ``[servidor [puerto [carpeta-local]]]`` legacy arguments."""
    server = config.server
    port = config.port
    local_path = config.local_path
    if len(argv) > 4:
        print("Uso: {} [<servidor> [<puerto> [<carpeta-local>]]]".format(argv[0]))
        raise SystemExit(2)
    if len(argv) >= 2:
        server = argv[1]
    if len(argv) >= 3:
        try:
            port = validate_port(argv[2])
        except ConfigurationError as error:
            print(f"Puerto inválido: {error}")
            raise SystemExit(2)
    if len(argv) == 4:
        local_path = argv[3]
    return server, port, local_path


def _print_response(response):
    if response.get("ok"):
        data = response.get("data")
        if data is not None:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    error = response.get("error", "error")
    if isinstance(error, str) and error.startswith("ER"):
        print(error_message(error[2:]))
    else:
        print(response.get("message", error))
    return 1


def _parse_options(argv):
    config_path = None
    foreground = False
    remaining = []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--foreground":
            foreground = True
        elif item == "--config" and index + 1 < len(argv):
            index += 1
            config_path = argv[index]
        elif item.startswith("--config="):
            config_path = item.split("=", 1)[1]
        else:
            remaining.append(item)
        index += 1
    return config_path, foreground, remaining


def _prompt_login(client):
    username = input("Usuario: ").strip()
    password = input("Contraseña: ")
    return client.request(
        {"action": "login", "username": username, "password": password}
    )


def _interactive(client):
    print("Conectado al daemon. Comandos: status, shares, share, unshare, pause, resume, logout, shutdown, quit.")
    response = _prompt_login(client)
    _print_response(response)
    if not response.get("ok"):
        return 0

    while True:
        try:
            command = input("cloudfs> ").strip()
        except EOFError:
            return 0
        if not command:
            continue
        words = command.split()
        result = _run_command(client, words)
        if words[0] in {"quit", "shutdown"}:
            return result


def _run_command(client, command):
    action = command[0]
    if action == "status":
        return _print_response(client.request({"action": "status"}))
    if action == "login":
        username = command[1] if len(command) > 1 else input("Usuario: ").strip()
        password = (
            command[2] if len(command) > 2 else input("Contraseña: ")
        )
        return _print_response(
            client.request(
                {"action": "login", "username": username, "password": password}
            )
        )
    if action == "logout":
        return _print_response(client.request({"action": "logout"}))
    if action == "pause":
        return _print_response(client.request({"action": "stop"}))
    if action == "resume":
        return _print_response(client.request({"action": "start"}))
    if action == "shares":
        return _print_response(client.request({"action": "shares"}))
    if action == "users":
        return _print_response(client.request({"action": "users"}))
    if action == "share" and len(command) == 4:
        return _print_response(
            client.request(
                {
                    "action": "share",
                    "path": command[1],
                    "grantee": command[2],
                    "access": command[3],
                }
            )
        )
    if action == "unshare" and len(command) == 3:
        return _print_response(
            client.request(
                {
                    "action": "unshare",
                    "path": command[1],
                    "grantee": command[2],
                }
            )
        )
    if action == "password":
        old = command[1] if len(command) > 1 else input("Contraseña actual: ")
        new = command[2] if len(command) > 2 else input("Contraseña nueva: ")
        return _print_response(
            client.request(
                {
                    "action": "password",
                    "old_password": old,
                    "new_password": new,
                }
            )
        )
    if action in {"shutdown", "quit"}:
        if action == "shutdown":
            _print_response(client.request({"action": "shutdown"}))
        return 0
    print("Comando desconocido.")
    return 2


def _foreground(config_path):
    config = load_config(config_path).client
    session = ClientSession(config)
    while True:
        username = input("Introduce el nombre de usuario: ")
        password = input("Introduce la contraseña: ")
        try:
            session.connect_and_login(username, password)
        except (OSError, EOFError, SyncError, NoServerError) as error:
            if isinstance(error, SyncError):
                print(error_message(error.code))
            else:
                print("No se ha podido iniciar sesión: {}".format(error))
            session.close()
            continue
        break
    session.close()
    worker = SyncWorker(config.local_path, config, username, password)
    worker.start()
    signal.signal(signal.SIGINT, handler)
    print("Logged in")
    while running:
        time.sleep(1)
    worker.stop()
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--version" in argv:
        print("cloud-file-client {}".format(__version__))
        return 0
    if "--daemon" in argv:
        from client_daemon import main as daemon_main

        return daemon_main([item for item in argv if item != "--daemon"])

    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).resolve().parent)
    configure("client")
    logging.getLogger("client").info("CLI started")
    config_path, foreground, command = _parse_options(argv)
    if config_path is None and getattr(sys, "frozen", False):
        candidate = Path("config.toml")
        if candidate.is_file():
            config_path = str(candidate.resolve())
    if foreground:
        return _foreground(config_path)
    try:
        client = ensure_daemon(config_path)
    except TimeoutError as error:
        print(error)
        return 1
    try:
        if not command:
            return _interactive(client)
        return _run_command(client, command)
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
