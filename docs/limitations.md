# Limitations

The current synchronization design intentionally keeps the scope small.

- Synchronization is one-way: client to server. Server-side changes are not
  pushed back to clients yet.
- Conflict copies are implemented for file uploads and deletes. Conflict
  handling for directory removal is coarse: a stale directory delete removes
  the remote tree without creating per-file conflict copies.
- Version history is not implemented. Conflict copies are ordinary files and
  are not garbage-collected.
- The client reconciles owned files at startup. Shared files and server push
  notifications arrive in M5.
- A local delete is never sent for a file that was never synchronized, so a new
  local file created and removed while offline leaves no remote trace.
- Passive replication and quorum are implemented. Automatic primary election,
  failover, and client redirection are M4.
- A new or restarted secondary does not automatically request a snapshot yet;
  snapshot export/import exists but automatic rejoin is M4.
- Secondary reads may lag behind the primary.
- If the primary loses quorum, uncommitted proposals are aborted; a secondary
  that was unreachable may retain an uncommitted proposal until rejoin.
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
