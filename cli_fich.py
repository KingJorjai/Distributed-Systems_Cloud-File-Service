#!/usr/bin/env python3

import os
import socket
import sys

import szasar
from sync_client import SyncError, SyncWorker
# TODO Generales
# 1. Eliminar el comando de listar, ya no es necesario ✔️
# 2. Cambios a upload (Estan comentados mas abajo)
# 3. Eliminar el menu, ya no es necesario. Solo dejar logearse ✔️
# 4. Mensaje Update para que el servidor informe al cliente de cambios en el servidor
#   4.1 El Cliente mira los cambios y elimina ficheros o descarga ficheros (nuevos o modificados)
SERVER = "localhost"
PORT = 6012
LOCAL_PATH = "client_files"
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


if __name__ == "__main__":
    if len(sys.argv) > 4:
        print("Uso: {} [<servidor> [<puerto> [<carpeta-local>]]]".format(sys.argv[0]))
        exit(2)

    if len(sys.argv) >= 2:
        SERVER = sys.argv[1]
    if len(sys.argv) == 3:
        PORT = int(sys.argv[2])
    if len(sys.argv) == 4:
        LOCAL_PATH = sys.argv[3]

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((SERVER, PORT))

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

    sync_worker = SyncWorker(LOCAL_PATH, SERVER, PORT, user, password)
    try:
        sync_worker.start()
    except (OSError, EOFError, socket.timeout, SyncError) as error:
        print("No se ha podido iniciar la sincronización automática: {}".format(error))
        sync_worker = None

    while True:
        option = -1
        if option == 1:
            filename = input("Indica el fichero que quieres bajar: ")
            message = "{}{}\r\n".format(szasar.Command.Download, filename)
            s.sendall(message.encode("ascii"))
            message = szasar.recvline(s).decode("ascii")
            if iserror(message):
                continue
            filesize = int(message[2:])
            message = "{}\r\n".format(szasar.Command.Download2)
            s.sendall(message.encode("ascii"))
            message = szasar.recvline(s).decode("ascii")
            if iserror(message):
                continue
            filedata = szasar.recvall(s, filesize)
            if sync_worker is not None:
                sync_worker.ignore(filename)
            try:
                with open(os.path.join(LOCAL_PATH, filename), "wb") as f:
                    f.write(filedata)
            except OSError:
                print("No se ha podido guardar el fichero en disco.")
            else:
                print("El fichero {} se ha descargado correctamente.".format(filename))

        elif option == 1:
            filename = input("Indica el fichero que quieres subir: ")
            try:
                filesize = os.path.getsize(os.path.join(LOCAL_PATH, filename))
                with open(os.path.join(LOCAL_PATH, filename), "rb") as f:
                    filedata = f.read()
            except OSError:
                print("No se ha podido acceder al fichero {}.".format(filename))
                continue

            message = "{}{}?{}\r\n".format(szasar.Command.Upload, filename, filesize)
            s.sendall(message.encode("ascii"))
            message = szasar.recvline(s).decode("ascii")
            if iserror(message):
                continue

            message = "{}\r\n".format(szasar.Command.Upload2)
            s.sendall(message.encode("ascii"))
            s.sendall(filedata)
            message = szasar.recvline(s).decode("ascii")
            if not iserror(message):
                print("El fichero {} se ha enviado correctamente.".format(filename))

        elif option == 1:
            filename = input("Indica el fichero que quieres borrar: ")
            message = "{}{}\r\n".format(szasar.Command.Delete, filename)
            s.sendall(message.encode("ascii"))
            message = szasar.recvline(s).decode("ascii")
            if not iserror(message):
                try:
                    os.remove(os.path.join(LOCAL_PATH, filename))
                except FileNotFoundError:
                    pass
                print("El fichero {} se ha borrado correctamente.".format(filename))

        elif option == 1:
            message = "{}\r\n".format(szasar.Command.Exit)
            s.sendall(message.encode("ascii"))
            message = szasar.recvline(s).decode("ascii")
            if sync_worker is not None:
                sync_worker.stop()
            break
    s.close()
