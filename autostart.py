"""Cross-platform autostart helpers for the GUI."""

import os
import sys
from pathlib import Path

APP_NAME = "cloud-file-service"


def _command():
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve().parent / "gui_fich.py")]


def _linux_unit_path():
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "systemd" / "user" / "cloud-file-client.service"


def is_enabled():
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
            ) as key:
                winreg.QueryValueEx(key, "CloudFileService")
            return True
        except OSError:
            return False
    if os.uname().sysname == "Darwin":
        return False
    return _linux_unit_path().is_file()


def enable():
    if os.name == "nt":
        import winreg

        command = " ".join('"{}"'.format(part) for part in _command())
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        ) as key:
            winreg.SetValueEx(key, "CloudFileService", 0, winreg.REG_SZ, command)
        return
    if os.uname().sysname == "Darwin":
        return
    path = _linux_unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    command = " ".join(_command())
    path.write_text(
        "[Unit]\n"
        "Description=Cloud File Service client\n"
        "After=graphical-session.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        "ExecStart={} --minimized\n"
        "Restart=on-failure\n\n"
        "[Install]\n"
        "WantedBy=default.target\n".format(command),
        encoding="utf-8",
    )
    # Best-effort reload; ignore failures (no systemd in containers).
    try:
        import subprocess

        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def disable():
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, "CloudFileService")
        except OSError:
            pass
        return
    if os.uname().sysname == "Darwin":
        return
    try:
        _linux_unit_path().unlink()
    except FileNotFoundError:
        pass
