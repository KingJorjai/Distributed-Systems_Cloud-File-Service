# Cloud File Service

Automatic one-way file synchronization from a local client folder to a multithreaded server.

[Get started](quick-start.md){ .md-button .md-button--primary }
[Explore the architecture](architecture.md){ .md-button }

## What it does

The client watches a local folder with [`watchdog`](https://python-watchdog.readthedocs.io/) and sends file changes to the server over TCP. The server stores each authenticated user's files in a separate directory.

## Key properties

- Client-to-server synchronization.
- Separate TCP connection for automatic synchronization.
- Debounced file events and retries after transient connection failures.
- Atomic server-side uploads.
- Manual file operations remain available through the interactive client.

!!! warning
    Changes made directly on the server are not synchronized back to the client. Bidirectional conflict resolution is outside the current scope.

## Documentation map

| Section | Covers |
| --- | --- |
| [Quick Start](quick-start.md) | Install and run the service. |
| [Configuration](configuration.md) | Ports, folders, users, and limits. |
| [Architecture](architecture.md) | Watcher, queue, network worker, and server. |
| [Protocol](protocol.md) | TCP commands and transfer flow. |
| [API Reference](api/sync-client.md) | Python classes and functions generated from docstrings. |
