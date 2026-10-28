#!/usr/bin/env python3
"""Unified offline entrypoint for the server and desktop client."""

import os
import sys
from pathlib import Path


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).resolve().parent)
    if not args:
        args = ["client"]
        config = Path("client/config.toml")
        if config.is_file():
            args.extend(["--config", str(config.resolve())])
    if args[0] == "--daemon":
        from client_daemon import main as daemon_main

        return daemon_main(args[1:])
    if args[0] not in {"server", "client"}:
        print("Uso: cloudfs server | cloudfs client [opciones]", file=sys.stderr)
        return 2
    mode = args[0]
    if mode == "server":
        from serv_fich_multithread import main as server_main

        return server_main()
    from gui_fich import main as client_main

    return client_main(args[1:])


if __name__ == "__main__":
    raise SystemExit(main())
