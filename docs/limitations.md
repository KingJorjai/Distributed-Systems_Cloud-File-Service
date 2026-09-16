# Limitations

The current synchronization design intentionally keeps the scope small.

- Synchronization is one-way: client to server.
- Server-side changes are not pushed back to clients.
- Conflicts and version history are not implemented.
- The watcher is non-recursive and monitors files directly inside the configured local folder.
- The event queue is in memory, so queued changes are lost when the client exits unexpectedly.
- The development protocol uses plain TCP and simple credentials; it does not provide encryption.
- The server keeps the existing educational authentication model.

For a production deployment, the next security steps would be TLS, stronger credential management, path and filename policy hardening, and a durable synchronization queue.
