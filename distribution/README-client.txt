# Cloud File Service client

1. Copy `config.toml.example` to `config.toml` if you want file-based
   configuration.
2. Run `cloud-file-client.exe` on Windows or `./cloud-file-client` on Linux.
3. Optionally provide `server`, `port`, and `local_folder` as arguments.

The client watches `client_files` by default and connects to `localhost:50012`.
It asks for credentials interactively and does not store passwords in the
package.

The package is self-contained: Python and the required libraries are included.
No Python installation or dependency download is required.
