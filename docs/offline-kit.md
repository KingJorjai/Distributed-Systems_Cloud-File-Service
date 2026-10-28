# Offline Kit

The offline kit is a single ZIP for Ubuntu 22.04 containing a portable server
and desktop client. It needs no Internet, no Python installation, and no
terminal for the client.

Build it from the repository after building the demo bundles:

```sh
scripts/build_demo_bundles.sh
scripts/build_offline_kit.sh
```

The result is:

```text
demo/CloudFS-Offline-0.11.3-linux-x64.zip
```

The generated ZIP is around 13 MB, below the usual Outlook attachment limit.

## What it contains

```text
CloudFS-Offline/
  cloudfs
  _internal/
  server/
    config.toml
    certs/
    files/
    start-server.sh
  client/
    config.toml
    certs/ca.crt
    client_files/
    state/
    start-client.sh
  CloudFS-Server.desktop
  CloudFS-Client.desktop
  README.txt
```

The server and client configurations are separate. The client configuration
already includes the server address, CA certificate, local folder, and state
directory.

## Run the client

Extract the ZIP and double-click `cloudfs` or `CloudFS-Client.desktop`. The
client opens with the bundled configuration and no terminal. Register or log in
from the GUI.

The compact kit does not include the optional system tray. Closing the window
minimizes it to the taskbar. The full GUI bundle still contains the tray.

## Run the server

The server needs a console process. Use:

```sh
cd CloudFS-Offline/server
./start-server.sh
```

The script sets `CONFIG_FILE` and the bootstrap administrator password and
starts the server on port `50012`. The admin panel is at
`https://localhost:50080/` with user `sar`; the generated password is printed in
the kit `README.txt`.

The first server start creates `server/files` and replication metadata. Server
logs are written to `logs/server.log`.

## Certificates

The kit includes a private CA and a server certificate for `localhost` and
`127.0.0.1`. The client trusts the CA automatically. The admin browser needs the
CA imported once if it is used, or the browser will show the normal private-CA
warning.

For a different server address, change the server field in the client Settings
tab. For a remote server, the certificate must include that address and the
client must receive that CA.

## Logs

Server and daemon logs are written to `logs/`:

- `logs/server.log`
- `logs/daemon.log`
- `logs/gui.log`

The GUI has an **Abrir logs** button. Logs rotate at 5 MiB with three backups.

## Size and email

The ZIP is self-contained and has no external download step. Keep it below the
mail attachment limit; do not add development files, databases, or test data.
If a future build exceeds the limit, split server and client into separate
ZIPs rather than a larger archive.

## Rebuild

The kit is generated from the current `cloudfs` bundle and a development CA.
Use the same Ubuntu 22.04 build environment as the demo bundles. The source
tree is not required on the target PC.
