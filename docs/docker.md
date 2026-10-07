# Docker Deployment

Docker Compose runs the multithreaded server and the automatic synchronization client as separate services.

```mermaid
flowchart LR
    Host[Host filesystem] -->|./files| S[server container]
    Host -->|./client_files| C[client container]
    C -->|server:50012| S
```

## Requirements

- Docker Engine with Compose v2.
- A free host port, `50012` by default.

## Configure permissions

The containers use the host UID and GID for the bind-mounted data directories. Create a local `.env` file from the example:

```sh
cp .env.example .env
sed -i "s/^DOCKER_UID=.*/DOCKER_UID=$(id -u)/; s/^DOCKER_GID=.*/DOCKER_GID=$(id -g)/" .env
```

`.env` is local configuration and must not be committed.
Set `APP_PASSWORD_SAR` and `APP_PASSWORD_SZA` in `.env` before starting the
server if authenticated users are required.

## Build the images

```sh
docker compose build
```

The server image contains `serv_fich_multithread.py`. The client image contains the authentication prompt and automatic synchronizer based on `watchdog`.

## Use published images

The `main` branch publishes both images to GitHub Container Registry:

```text
ghcr.io/kingjorjai/distributed-systems-cloud-file-service-server:latest
ghcr.io/kingjorjai/distributed-systems-cloud-file-service-client:latest
```

To use a published version instead of building locally, use the registry override and set the image prefix and tag:

```sh
export IMAGE_PREFIX=ghcr.io/kingjorjai/distributed-systems-cloud-file-service
export IMAGE_TAG=latest
docker compose -f compose.yaml -f compose.registry.yaml pull
docker compose -f compose.yaml -f compose.registry.yaml up -d server
docker compose -f compose.yaml -f compose.registry.yaml run --rm client
```

Version tags such as `v1.0.0` are also published when pushed to GitHub.

## Downloadable standalone bundles

Pushing a tag such as `v1.0.0` also creates a GitHub Release with independent
server and client bundles for Windows x64 and Linux x64. Each bundle contains
the application executable, its Python runtime and dependencies,
`config.toml.example`, a short README, and an empty data directory.

The target machine does not need Python, `pip`, Docker, or an additional
dependency download. Choose the asset matching the operating system and
component, extract it, configure the environment variables or TOML file, and
run the executable from the extracted directory:

```text
cloud-file-service-server-windows-x64-v1.0.0.zip
cloud-file-service-client-windows-x64-v1.0.0.zip
cloud-file-service-server-linux-x64-v1.0.0.tar.gz
cloud-file-service-client-linux-x64-v1.0.0.tar.gz
```

The release also contains `SHA256SUMS` and a Compose package. Verify the
checksum before extracting an asset. Standalone bundles are built with
PyInstaller in folder mode; they are intentionally not a single executable so
that configuration, documentation, and data directories remain visible.

## Start the server

```sh
docker compose up -d server
docker compose ps
docker compose logs -f server
```

The server is exposed at `localhost:50012` on the host and at `server:50012` inside the Compose network by default.
`SERVER_PUBLISHED_PORT` changes the host port, while `SERVER_INTERNAL_PORT`
changes the container and client port. Set both when moving the complete service
to another port.

## Start the client

Run the client interactively from a second terminal:

```sh
docker compose run --rm client
```

The client connects to the Compose service name `server` and watches `/data`, which is mapped to the host's `client_files/` directory.

Authenticate with one of the passwords configured in `.env`. Then create or modify
a file in `client_files/` on the host. It should appear under `files/<user>/` after
synchronization.

## Stop the services

```sh
docker compose down
```

The bind-mounted files remain on the host after containers stop. Use `docker compose down --rmi local` to also remove the locally built images.

## Troubleshooting

Inspect the server logs when the client cannot connect:

```sh
docker compose logs server
```

If a bind-mounted directory is not writable, check `.env` and confirm that `DOCKER_UID` and `DOCKER_GID` match `id -u` and `id -g` on the host.
