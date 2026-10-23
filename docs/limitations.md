# Limitations

The current synchronization design intentionally keeps the scope small.

- Synchronization is one-way: client to server. Server-side changes are not
  pushed back to clients yet.
- Conflicts and version history are not implemented yet. Revision metadata is
  recorded and stale uploads are rejected with `ER20`, but conflict copies
  arrive in M2.
- The event queue is durable on the client, but reconciliation on startup is
  still limited to uploading local files. Full manifest reconciliation is M2.
- The server does not replicate yet; passive replication, quorum, election, and
  failover are M3–M4.
- Sharing is modelled in the database, but `SHAR`/`UNSH` commands and
  notifications arrive in M5.
- The client is supported on Windows x64 and Linux x64. macOS is out of scope.
- Release bundles are portable and unsigned; Windows SmartScreen may warn.
  There is no installer, uninstaller, auto-update, or tray icon yet.
- TLS requires a certificate. A private CA certificate must be distributed to
  clients; there is no “ignore certificate” option.
- There is no rate limiting, email verification, or self-service password
  reset.
- The development protocol uses TLS but no application-level end-to-end
  encryption; the server can read file contents.

For a production deployment, the next security steps would be certificate
rotation, rate limiting, account recovery, and stronger credential management.
