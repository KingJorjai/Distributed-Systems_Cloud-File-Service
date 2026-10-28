"""Run the background synchronization daemon."""

import argparse
import logging
import signal
import sys

from app_logging import configure
from daemon_service import DaemonService
from single_instance import AlreadyRunningError


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)
    configure("daemon")
    log = logging.getLogger("daemon")
    service = DaemonService(args.config)
    try:
        service.start()
    except AlreadyRunningError:
        print("The synchronization daemon is already running.", file=sys.stderr)
        return 1

    def stop(signum, frame):
        service.stop()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    log.info("daemon started")
    try:
        service.serve_forever()
    finally:
        log.info("daemon stopped")
        service.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
