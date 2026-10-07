#!/usr/bin/env python3

import signal
import socket
import sys
import time

import szasar
from config import ConfigurationError, load_config, validate_port
from sync_client import SyncError, SyncWorker

# TODO Generales
# 1. Eliminar el comando de listar, ya no es necesario ✔️
# 2. Cambios a upload (Estan comentados mas abajo)
# 3. Eliminar el menu, ya no es necesario. Solo dejar logearse ✔️
# 4. Mensaje Update para que el servidor informe al cliente de cambios en el servidor
#   4.1 El Cliente mira los cambios y elimina ficheros o descarga ficheros (nuevos o modificados)
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
    else:
        return False


def int2bytes(n):
    """Format a byte count using a human-readable binary unit."""
    if n < 1 << 10:
        return str(n) + " B  "
    elif n < 1 << 20:
        return str(round(n / (1 << 10))) + " KiB"
    elif n < 1 << 30:
        return str(round(n / (1 << 20))) + " MiB"
    else:
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


if __name__ == "__main__":
    config = load_config().client
    server, port, local_path = parse_client_args(sys.argv, config)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((server, port))

    while True:
        user = input("Introduce el nombre de usuario: ")
        message = "{}{}\r\n".format(szasar.Command.User, user)
        s.sendall(message.encode("ascii"))
        message = szasar.recvline(s).decode("ascii")
        if iserror(message):
            continue

        password = input("Introduce la contraseña: ")
        message = "{}{}\r\n".format(szasar.Command.Password, password)
        s.sendall(message.encode("ascii"))
        message = szasar.recvline(s).decode("ascii")
        if not iserror(message):
            break

    sync_worker = SyncWorker(local_path, server, port, user, password)
    try:
        sync_worker.start()
    except (OSError, EOFError, socket.timeout, SyncError) as error:
        print("No se ha podido iniciar la sincronización automática: {}".format(error))
        sync_worker = None

    signal.signal(signal.SIGINT, handler)
    print("\nLogged in")
    while running:
        time.sleep(1)
    s.close()
