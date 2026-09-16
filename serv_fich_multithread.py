#!/usr/bin/env python3

import os
import socket
import tempfile
import threading

import szasar

PORT = 6012
FILES_PATH = "files"
MAX_FILE_SIZE = 10 * 1 << 20  # 10 MiB
SPACE_MARGIN = 50 * 1 << 20  # 50 MiB
USERS = ("anonimous", "sar", "sza")
PASSWORDS = ("", "sar", "sza")

# TODO Generales
# 1. Eliminar el comando de listar, ya no es necesario
# 2. Cambios a upload (Estan comentados mas abajo)
class State:
    """States used by one client session in the multithreaded server."""

    Identification, Authentication, Main, Downloading, Uploading = range(5)


def sendOK(s, params=""):
    """Send a successful protocol response with optional parameters."""
    s.sendall(("OK{}\r\n".format(params)).encode("ascii"))


def sendER(s, code=1):
    """Send a protocol error response with an error code."""
    s.sendall(("ER{}\r\n".format(code)).encode("ascii"))


def safe_path(root, filename):
    """Resolve a filename while preventing access outside the user's root."""
    if not filename or os.path.isabs(filename):
        raise ValueError("Ruta no válida")
    root = os.path.abspath(root)
    target = os.path.abspath(os.path.join(root, filename))
    if os.path.commonpath((root, target)) != root:
        raise ValueError("Ruta no válida")
    return target


def session(s):
    """Serve one authenticated client session until it disconnects."""
    state = State.Identification
    
    while True:
        try:
            message = szasar.recvline(s).decode("ascii")
        except EOFError:
            return
        # 		print( "---SERVER: Leido msg {} {}\r\n.".format( message[0:4], message[4:] ) )
        if not message:
            return

        if message.startswith(szasar.Command.User):
            if state != State.Identification:
                sendER(s)
                continue
            try:
                user = USERS.index(message[4:])
            except ValueError:
                sendER(s, 2)
            else:
                sendOK(s)
                state = State.Authentication

        elif message.startswith(szasar.Command.Password):
            if state != State.Authentication:
                sendER(s)
                continue
            if user == 0 or PASSWORDS[user] == message[4:]:
                sendOK(s)
                filespath = os.path.join(FILES_PATH, USERS[user])
                os.makedirs(filespath, exist_ok=True)
                state = State.Main
            else:
                sendER(s, 3)
                state = State.Identification

        elif message.startswith(szasar.Command.List):
            if state != State.Main:
                sendER(s)
                continue
            try:
                message = "OK\r\n"
                for filename in os.listdir(filespath):
                    filesize = os.path.getsize(os.path.join(filespath, filename))
                    message += "{}?{}\r\n".format(filename, filesize)
                message += "\r\n"
            except OSError:
                sendER(s, 4)
            else:
                s.sendall(message.encode("ascii"))

        elif message.startswith(szasar.Command.Download):
            if state != State.Main:
                sendER(s)
                continue
            try:
                filename = safe_path(filespath, message[4:])
            except ValueError:
                sendER(s, 5)
                continue
            try:
                filesize = os.path.getsize(filename)
            except OSError:
                sendER(s, 5)
                continue
            else:
                sendOK(s, filesize)
                state = State.Downloading

        elif message.startswith(szasar.Command.Download2):
            if state != State.Downloading:
                sendER(s)
                continue
            state = State.Main
            try:
                with open(filename, "rb") as f:
                    filedata = f.read()
            except OSError:
                sendER(s, 6)
            else:
                sendOK(s)
                s.sendall(filedata)
        # Modificaciones TODO a upload
        # 1. Cada vez que el cliente quiere subir un archivo, el servidor manda el rev del archivo
        # 2. Si la rev es distinta, hay un conflicto (alguien ha modificado el archivo en el servidor)
        # 3. En caso de conflicto estrategia update
        #   3.1 Cambiar el nombre del fichero en el servidor a fichero(copia en conflicto XX).extension, siendo XX el numero de copia
        #   3.2 La copia nueva pasa a ser la oficial
        #   3.3 Sincronizar la copia en conflicto con el cliente (enviar nombre del fichero en conflicto). El usuario decidira que hacer con eso
        # 4. Si la rev es igual el cliente manda el hash del fichero y el servidor lo compara con el hash en la base de datos
        # 5. Si son iguales rechaza (positivo) la subida
        elif message.startswith(szasar.Command.Upload):
            if state != State.Main:
                sendER(s)
                continue
            if user == 0:
                sendER(s, 7)
                continue
            try:
                filename, filesize = message[4:].split("?")
                filesize = int(filesize)
                target = safe_path(filespath, filename)
            except (ValueError, TypeError):
                sendER(s, 10)
                continue
            if filesize > MAX_FILE_SIZE:
                sendER(s, 8)
                continue
            svfs = os.statvfs(filespath)
            if filesize + SPACE_MARGIN > svfs.f_bsize * svfs.f_bavail:
                sendER(s, 9)
                continue
            sendOK(s)
            state = State.Uploading

        elif message.startswith(szasar.Command.Upload2):
            if state != State.Uploading:
                sendER(s)
                continue
            state = State.Main
            tempname = None
            try:
                filedata = szasar.recvall(s, filesize)
                fd, tempname = tempfile.mkstemp(prefix=".upload-", dir=filespath)
                with os.fdopen(fd, "wb") as f:
                    f.write(filedata)
                os.replace(tempname, target)
            except (OSError, EOFError):
                if tempname is not None:
                    try:
                        os.unlink(tempname)
                    except OSError:
                        pass
                sendER(s, 10)
            else:
                sendOK(s)

        elif message.startswith(szasar.Command.Delete):
            if state != State.Main:
                sendER(s)
                continue
            if user == 0:
                sendER(s, 7)
                continue
            try:
                os.remove(safe_path(filespath, message[4:]))
            except FileNotFoundError:
                sendOK(s)
            except (OSError, ValueError):
                sendER(s, 11)
            else:
                sendOK(s)

        elif message.startswith(szasar.Command.Exit):
            sendOK(s)
            s.close()
            return

        else:
            sendER(s)

if __name__ == "__main__":
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    s.bind(("", PORT))
    s.listen(5)

    # 	signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    threads = []
    dialog = []

    while True:
        sc, address = s.accept()
        print("Conexión aceptada del socket {0[0]}:{0[1]}.".format(address))
        dialog.append(sc)
        t = threading.Thread(target=session, args=(dialog[-1],))
        threads.append(t)
        t.start()
