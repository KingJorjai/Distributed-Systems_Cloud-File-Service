"""Application logging setup shared by server and client entrypoints."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def _level():
    name = os.environ.get("CLOUDFS_LOG_LEVEL", "INFO").upper()
    return getattr(logging, name, logging.INFO)


def default_log_file(component):
    configured = os.environ.get("CLOUDFS_LOG_FILE")
    if configured:
        return Path(configured)
    return Path("logs") / "{}.log".format(component)


def configure(component):
    """Configure console and rotating-file logging once per process."""
    root = logging.getLogger()
    if getattr(root, "_cloudfs_configured", False):
        return default_log_file(component)
    path = default_log_file(component)
    path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_FORMAT)
    root.setLevel(_level())
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    root.addHandler(stream)
    try:
        file_handler = RotatingFileHandler(
            str(path), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        pass
    root._cloudfs_configured = True
    root.info("logging configured at %s", path)
    return path
