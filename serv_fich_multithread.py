#!/usr/bin/env python3

from config import load_config
from server_runtime import create_server
from version import __version__


def main():
    config = load_config()
    runtime = create_server(config)
    runtime.start()
    print(
        "Servidor TLS {} escuchando en el puerto {} (rol {}).".format(
            __version__, runtime.port, config.server.role
        )
    )
    try:
        runtime.serve_forever()
    except KeyboardInterrupt:
        runtime.stop()
    finally:
        runtime.store.close()


if __name__ == "__main__":
    main()
