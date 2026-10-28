# Limitations

The current synchronization design intentionally keeps the scope small.

- Synchronization converges both ways for owned and shared files, but active
  push notifications require a running client; offline changes are applied on
  the next startup reconciliation.
- Conflict copies are implemented for file uploads and deletes. Conflict
  handling for directory removal is coarse: a stale directory delete removes
  the remote tree without creating per-file conflict copies.
- Version history is not implemented. Conflict copies are ordinary files and
  are not garbage-collected.
- The client reconciles owned and shared files at startup. Active clients receive
  server push notifications; offline clients do not.
- A local delete is never sent for a file that was never synchronized, so a new
  local file created and removed while offline leaves no remote trace.
- Passive replication, quorum, heartbeats, election, client redirection, and
  automatic snapshot rejoin are implemented.
- Shares support file and directory prefixes with `ro`/`rw` access. There are no
  groups, inherited per-file ACLs, or share expiration.
- Notifications require an active client connection. A closed client discovers
  changes on its next startup reconciliation; there is no offline push.
- The GUI requires Tkinter and a desktop session. The tray depends on the
  platform's status-notifier support; if it is unavailable, the window is
  minimized instead.
- The daemon keeps passwords in memory only. After a daemon restart, the user
  must log in again.
- The admin panel has no login rate limiting, password reset email, user
  deletion, or historical audit persistence; the audit log is in memory.
- Admin mutations require the primary and quorum; secondary panels are
  read-only and redirect actions when the primary admin URL is configured.
- A local edit to an `ro` share is preserved as a local conflict copy while the
  remote version is restored.
- Secondary reads may lag behind the primary.
- Snapshots are transferred as one JSON message and are limited by the 64 MiB
  replication line limit; a very large file store needs chunked snapshots.
- The cluster tolerates crash-stop failures, not Byzantine nodes or arbitrary
  network partitions. A leader that cannot obtain a majority steps down.
- A node that was unreachable during an aborted proposal may retain an
  uncommitted entry until the next heartbeat/snapshot.
- The client is supported on Windows x64 and Linux x64. macOS is out of scope.
- The offline demo kit targets Ubuntu 22.04 and Python 3.10.12. Python 3.10 is
  end-of-life, so the kit is intended only for the LAN demonstration; a
  production deployment must migrate to a supported Python release.
- Release bundles are portable and unsigned; Windows SmartScreen may warn.
  There is no installer, uninstaller, or auto-update yet.
- TLS requires a certificate. A private CA certificate must be distributed to
  clients; there is no “ignore certificate” option.
- There is no rate limiting, email verification, or self-service password
  reset.
- The development protocol uses TLS but no application-level end-to-end
  encryption; the server can read file contents.

For a production deployment, the next security steps would be certificate
rotation, rate limiting, account recovery, and stronger credential management.
