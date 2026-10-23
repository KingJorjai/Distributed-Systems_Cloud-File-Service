# Cloud File Service desktop client

1. Run `cloud-file-client-gui.exe` on Windows or `./cloud-file-client-gui` on Linux.
2. Enter the server, port, and optional CA certificate, then register or log in.
3. Choose the local folder and start synchronization.

The GUI starts a background daemon that keeps synchronizing when the window is
closed to the system tray. Use the tray menu to show the window, open the local
folder, pause/resume, or quit the daemon.

Configuration is stored in the standard per-user configuration directory:
`%APPDATA%\CloudFileService\config.toml` on Windows or
`$XDG_CONFIG_HOME/cloudfs/config.toml` on Linux. `CONFIG_FILE` can override it.
Passwords are not stored.

The package is self-contained: Python, Tkinter, and the required libraries are
included. No Python installation or dependency download is required.
