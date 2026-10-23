"""Cross-platform autostart helpers for the GUI."""

import os
import sys
from pathlib import Path

APP_NAME = "cloud-file-service"


def _command():
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve().parent / "gui_fich.py")]


def _linux_desktop_path():
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / "{}.desktop".format(APP_NAME)


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
    return _linux_desktop_path().is_file()


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
    path = _linux_desktop_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    command = " ".join(_command())
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Cloud File Service\n"
        "Comment=Synchronize the local cloud folder\n"
        "Exec={} --minimized\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n".format(command),
        encoding="utf-8",
    )


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
        _linux_desktop_path().unlink()
    except FileNotFoundError:
        pass
