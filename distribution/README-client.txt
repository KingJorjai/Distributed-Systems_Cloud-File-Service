# Cloud File Service client

1. Run `cloud-file-client.exe` on Windows or `./cloud-file-client` on Linux.
2. Use the CLI commands to log in, inspect status, and manage shares:
   `status`, `login`, `shares`, `share`, `unshare`, `pause`, `resume`, `quit`.
3. The CLI connects to the same background daemon as the GUI.

For a replicated cluster, set `CLIENT_PEERS` to the seed endpoints; the client
uses `PRIM` to find the current primary. `CLIENT_TLS_CA_FILE` is only needed for
a private CA.

The package is self-contained: Python and the required libraries are included.
No Python installation or dependency download is required.
