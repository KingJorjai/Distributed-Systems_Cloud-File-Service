#!/usr/bin/env python3

from config import load_config
from file_store import FileStore
from server_runtime import ServerRuntime


def main():
    config = load_config()
    store = FileStore(config.server.files_path)
    store.ensure_bootstrap_user("sar", config.passwords["sar"], "admin")
    store.ensure_bootstrap_user("sza", config.passwords["sza"], "admin")
    store.backfill()

    runtime = ServerRuntime(config.server, store)
    runtime.start()
    print("Servidor TLS escuchando en el puerto {}.".format(runtime.port))
    try:
        runtime.serve_forever()
    except KeyboardInterrupt:
        runtime.stop()
    finally:
        store.close()


if __name__ == "__main__":
    main()
