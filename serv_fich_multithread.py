#!/usr/bin/env python3

import logging
import os
import sys
from pathlib import Path

from app_logging import configure
from config import load_config
from server_runtime import create_server
from version import __version__


def main():
    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).resolve().parent)
    configure("server")
    log = logging.getLogger("server")
    if not os.environ.get("CONFIG_FILE") and Path("config.toml").is_file():
        os.environ["CONFIG_FILE"] = str(Path("config.toml").resolve())
    config = load_config()
    runtime = create_server(config)
    runtime.start()
    message = "Servidor TLS {} escuchando en el puerto {} (rol {}).".format(
        __version__, runtime.port, config.server.role
    )
    print(message)
    log.info(message)
    try:
        runtime.serve_forever()
    except KeyboardInterrupt:
        log.info("server interrupted")
        runtime.stop()
    finally:
        runtime.store.close()


if __name__ == "__main__":
    main()
