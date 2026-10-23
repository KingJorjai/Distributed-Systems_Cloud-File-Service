# Cloud File Service client

1. Copy `config.toml.example` to `config.toml` if you want file-based
   configuration.
2. Set `CLIENT_TLS_CA_FILE` if the server uses a private CA; otherwise the
   operating system trust store is used.
3. For a replicated cluster, set `CLIENT_PEERS` to the seed endpoints; the
   client uses `PRIM` to find the current primary.
4. Run `cloud-file-client.exe` on Windows or `./cloud-file-client` on Linux.
5. Optionally provide `server`, `port`, and `local_folder` as arguments.

The client watches `client_files` by default and connects to `localhost:50012`
over TLS. It asks for credentials interactively and does not store passwords in
the package.

The package is self-contained: Python and the required libraries are included.
No Python installation or dependency download is required.
