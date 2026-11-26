#!/usr/bin/env python3
"""Unified offline entrypoint for the server and desktop client."""

import os
import sys
from pathlib import Path


def _chdir_to_exe():
    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).resolve().parent)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] == "--daemon":
        from client_daemon import main as daemon_main

        return daemon_main(args[1:])

    if not args:
        args = ["client"]

    command = args[0]
    rest = args[1:]

    if command == "setup":
        from setup import main as setup_main

        return setup_main(rest)

    if command == "status":
        from status import main as status_main

        return status_main(rest)

    if command == "server":
        _chdir_to_exe()
        # Allow --config to be passed through to the server.
        config_path = None
        filtered = []
        i = 0
        while i < len(rest):
            if rest[i] == "--config" and i + 1 < len(rest):
                config_path = rest[i + 1]
                i += 2
                continue
            filtered.append(rest[i])
            i += 1
        if config_path is not None:
            os.environ["CONFIG_FILE"] = str(Path(config_path).resolve())
        from serv_fich_multithread import main as server_main

        return server_main()

    if command == "client":
        _chdir_to_exe()
        from gui_fich import main as client_main

        return client_main(rest)

    if command in {"-h", "--help"}:
        print("Usage: cloudfs {setup|server|client|status} [options]")
        return 0

    # Backwards compatibility: treat unknown first token as client args.
    _chdir_to_exe()
    from gui_fich import main as client_main

    return client_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
