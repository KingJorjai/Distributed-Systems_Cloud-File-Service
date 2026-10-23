"""Desktop entrypoint for the Cloud File Service client."""

import argparse
import sys
from pathlib import Path

from client_state import default_state_dir
from config import load_config
from gui_controller import GuiController
from single_instance import AlreadyRunningError, InstanceLock


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--daemon" in argv:
        from client_daemon import main as daemon_main

        return daemon_main([item for item in argv if item != "--daemon"])

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--minimized", action="store_true")
    args = parser.parse_args(argv)

    config = load_config(args.config).client
    state = default_state_dir() if not config.state_dir else config.state_dir
    lock = InstanceLock(Path(state) / "gui.lock")
    try:
        lock.acquire()
    except AlreadyRunningError:
        print("The Cloud File Service GUI is already running.", file=sys.stderr)
        return 1

    controller = GuiController(args.config)
    try:
        controller.start_daemon()
    except Exception as error:
        print("No se pudo iniciar el daemon: {}".format(error), file=sys.stderr)
        lock.release()
        return 1

    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as error:
        print("No hay entorno gráfico disponible: {}".format(error), file=sys.stderr)
        controller.close()
        lock.release()
        return 1

    from gui_app import GuiApp

    GuiApp(
        root,
        controller,
        config_path=args.config,
        start_minimized=args.minimized,
    )
    try:
        root.mainloop()
    finally:
        controller.close()
        lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
