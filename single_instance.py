"""Cross-platform single-instance lock using an exclusive file."""

import os
from pathlib import Path


class AlreadyRunningError(Exception):
    """Raised when another process owns the instance lock."""


class InstanceLock:
    """Hold an exclusive lock file for the lifetime of a process."""

    def __init__(self, path):
        self.path = Path(path)
        self._held = False

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(
                str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
        except FileExistsError as error:
            raise AlreadyRunningError(str(self.path)) from error
        with os.fdopen(descriptor, "w") as lock_file:
            lock_file.write(str(os.getpid()))
        self._held = True
        return self

    def release(self):
        if not self._held:
            return
        self._held = False
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc, traceback):
        self.release()
