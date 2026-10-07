# Cloud File Service server

1. Copy `config.toml.example` to `config.toml` if you want file-based
   configuration.
2. Set `APP_PASSWORD_SAR` and `APP_PASSWORD_SZA` in the environment.
3. Run `cloud-file-server.exe` on Windows or `./cloud-file-server` on Linux.

The server listens on port `50012` by default and stores synchronized files in
the `files` directory. Keep this directory backed up.

The package is self-contained: Python and the required libraries are included.
No Python installation or dependency download is required.
