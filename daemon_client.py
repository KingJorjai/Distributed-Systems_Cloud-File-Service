"""Start and talk to the client synchronization daemon."""

import subprocess
import sys
import time
from pathlib import Path

from client_state import default_state_dir
from config import load_config
from ipc import IpcClient, ipc_address, ipc_key


def state_directory(config_path=None):
    config = load_config(config_path).client
    return Path(config.state_dir or default_state_dir())


def connect(config_path=None, timeout=2):
    state = state_directory(config_path)
    return IpcClient(ipc_address(state), ipc_key(state), timeout=timeout)


def ensure_daemon(config_path=None, timeout=6):
    """Return a client for a running daemon, starting it when necessary."""
    try:
        client = connect(config_path)
        client.request({"action": "status"})
        return client
    except Exception:
        pass

    root = Path(__file__).resolve().parent
    command = [
        sys.executable,
        "--daemon",
    ]
    if getattr(sys, "frozen", False):
        pass
    else:
        command = [sys.executable, str(root / "client_daemon.py")]
    if config_path:
        command.extend(["--config", str(config_path)])
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        creationflags=creationflags,
        cwd=str(root),
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            client = connect(config_path)
            client.request({"action": "status"})
            return client
        except Exception:
            time.sleep(0.1)
    raise TimeoutError("The synchronization daemon did not start.")
