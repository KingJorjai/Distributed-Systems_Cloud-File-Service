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
    if not os.environ.get("CONFIG_FILE"):
        for candidate in (Path("config") / "server.toml", Path("config.toml")):
            if candidate.is_file():
                os.environ["CONFIG_FILE"] = str(candidate.resolve())
                break
    config = load_config(kind="server")
    runtime = create_server(config)
    runtime.start()
    message = "TLS server {} listening on port {} (role {}).".format(
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
