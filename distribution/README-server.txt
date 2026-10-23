# Cloud File Service server

1. Copy `config.toml.example` to `config.toml` if you want file-based
   configuration.
2. Provide a TLS certificate and key, either through `TLS_CERT_FILE` and
   `TLS_KEY_FILE` or the TOML file.
3. Set `APP_PASSWORD_SAR` and `APP_PASSWORD_SZA` in the environment.
4. For a replicated cluster, set `SERVER_ID`, `SERVER_ROLE`, `SERVER_PEERS`,
   `SERVER_REPLICATION_PORT`, `SERVER_PRIMARY`, and `CLUSTER_TOKEN`.
5. Run `cloud-file-server.exe` on Windows or `./cloud-file-server` on Linux.

The server listens on port `50012` by default and stores synchronized files in
the `files` directory. It refuses plaintext connections. Keep this directory
backed up.

The package is self-contained: Python and the required libraries are included.
No Python installation or dependency download is required.
