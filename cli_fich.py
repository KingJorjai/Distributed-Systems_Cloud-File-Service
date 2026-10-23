#!/usr/bin/env python3

import signal
import sys
import time
from dataclasses import replace

from client_session import ClientSession, SyncError
from config import ConfigurationError, load_config, validate_port
from sync_client import SyncWorker

ER_MSG = (
    "Correcto.",
    "Comando desconocido o inesperado.",
    "Usuario desconocido.",
    "Clave de paso o password incorrecto.",
    "Error al crear la lista de ficheros.",
    "El fichero no existe.",
    "Error al bajar el fichero.",
    "Un usuario anonimo no tiene permisos para esta operacion.",
    "El fichero es demasiado grande.",
    "Error al preparar el fichero para subirlo.",
    "Error al subir el fichero.",
    "Error al borrar el fichero.",
    "No se puede compartir un fichero con uno mismo.",
    "El registro está desactivado.",
    "Datos de registro no válidos.",
    "El usuario está deshabilitado.",
    "El usuario ya existe.",
    "La línea del protocolo es demasiado larga.",
    "Conflicto de revisión.",
)
running = True


def handler(signum, frame):
    global running
    print("\nCtrl+C received — shutting down gracefully")
    running = False


def iserror(message):
    """Print the protocol error message and return whether a response failed."""
    if message.startswith("ER"):
        code = int(message[2:])
        print(ER_MSG[code])
        return True
    return False


def int2bytes(n):
    """Format a byte count using a human-readable binary unit."""
    if n < 1 << 10:
        return str(n) + " B  "
    if n < 1 << 20:
        return str(round(n / (1 << 10))) + " KiB"
    if n < 1 << 30:
        return str(round(n / (1 << 20))) + " MiB"
    return str(round(n / (1 << 30))) + " GiB"


def parse_client_args(argv, config):
    """Parse ``[servidor [puerto [carpeta-local]]]`` CLI arguments."""
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


def main():
    config = load_config().client
    server, port, local_path = parse_client_args(sys.argv, config)
    config = replace(config, server=server, port=port, local_path=local_path)

    session = ClientSession(config)
    while True:
        user = input("Introduce el nombre de usuario: ")
        password = input("Introduce la contraseña: ")
        try:
            session.connect()
            session.login(user, password)
        except (OSError, EOFError, SyncError) as error:
            if isinstance(error, SyncError) and error.code < len(ER_MSG):
                print(ER_MSG[error.code])
            else:
                print("No se ha podido iniciar sesión: {}".format(error))
            session.close()
            continue
        break

    session.close()
    sync_worker = SyncWorker(local_path, config, user, password)
    try:
        sync_worker.start()
    except (OSError, EOFError, SyncError) as error:
        print("No se ha podido iniciar la sincronización automática: {}".format(error))
        return

    signal.signal(signal.SIGINT, handler)
    print("\nLogged in")
    while running:
        time.sleep(1)
    sync_worker.stop()


if __name__ == "__main__":
    main()
