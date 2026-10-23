# Protocol

The service uses a line-based TCP protocol **over TLS**. Every command ends with
`CRLF` (`\r\n`) and every response starts with `OK` or `ER`. Plaintext
connections are rejected: there is no insecure fallback.

## TLS

The server requires `TLS_CERT_FILE` and `TLS_KEY_FILE`. The client verifies the
server certificate against the system CA store, or against `CLIENT_TLS_CA_FILE`
for a private/development CA. Hostname verification is always enabled.

## Commands

| Command | Purpose |
| --- | --- |
| `USERname` | Select a user. |
| `PASSpassword` | Authenticate the user. |
| `REGIusername?password` | Register a new account. The password is URL-encoded. |
| `CHPWold?new` | Change the current user's password. Both values are URL-encoded. |
| `USRS` | List enabled users that can be selected as share grantees. |
| `SYNC` | Return the current manifest of owned and shared files. |
| `STATpath` | Return `rev`, hash, and size for one owned path. |
| `DOWNfilename` | Prepare a file download. |
| `DOW2` | Request the prepared file bytes. |
| `UPLOfilename?size` | Prepare an upload (legacy form). |
| `UPLOfilename?size=<n>&rev=<n>&hash=<hex>&client=<id>` | Prepare an upload with revision metadata. |
| `UPL2` | Send the upload bytes after the server accepts them. |
| `MKDRdirname` | Create a directory. |
| `RMDRdirname` | Delete a directory and its contents. |
| `DELEfilename?rev=<n>&client=<id>` | Delete a file with revision metadata. |
| `EXIT` | Close the session. |

Commands use the four-character prefixes defined in `szasar.Command`. The
protocol does not add spaces between a command prefix and its arguments. There
is no `LIST` command.

Paths are encoded with `urllib.parse.quote(path, safe="/")`; clients decode
them with `urllib.parse.unquote`. This keeps tabs, newlines, and question marks
out of the line framing.

A path prefixed with `@owner/` addresses a shared file. Owned paths never start
with a raw `@` because the client encodes it as `%40`.

## Manifest

`SYNC` returns:

```text
OK<count>\r\n
<owner>\t<encoded path>\t<rev>\t<hash>\t<size>\t<deleted>\t<access>\r\n
...
END\r\n
```

- `access` is `rw` or `ro`.
- `deleted=1` is a tombstone.
- `count` is the number of following entries.

`STATpath` returns `OK<rev>\t<hash>\t<size>` or `ER5`.

## Upload flow

```text
Client                              Server
  | UPLOfilename?size=5&rev=0&hash=...&client=... |
  |------------------------------------------------>|
  |                       OK                       |
  |<------------------------------------------------|
  | UPL2 + CRLF + file bytes                        |
  |------------------------------------------------>|
  | OK<rev> or OK<rev>\t<encoded conflict path>     |
  |<------------------------------------------------|
```

The server validates authentication, ACL, size, free space, and the target
path before accepting the bytes. Uploads are written to a temporary file and
moved into place atomically.

When the base revision is stale, the server keeps the current version as a
conflict copy and accepts the incoming upload as the official version. The
response includes the conflict path after a tab. `DELE` follows the same
pattern: a stale delete preserves the current server version as a conflict copy
and tombstones the official path.

Conflict copies are named:

```text
<stem> (conflict <client id> <UTC YYYYmmdd-HHMMSS>)<suffix>
```

A numeric suffix is added if the name already exists.

## Reconciliation

On startup the client requests `SYNC`, compares the manifest with its local
state and filesystem, and then:

- uploads only new or locally modified files;
- downloads new or remotely modified files;
- propagates local deletes only for paths previously synchronized;
- deletes local files when the manifest contains a tombstone;
- preserves both versions when local and remote content changed.

## Authentication and registration

`USERname` only selects the account; `PASSpassword` verifies it. `anonimous`
has no password and is read-only. Registration is controlled by
`ALLOW_REGISTRATION`; passwords are stored as PBKDF2-HMAC-SHA256 hashes.

`REGI` is accepted only before authentication. `CHPW` requires an authenticated
session.

## Responses

- `OK` means the command was accepted.
- `OK<size>` announces the size of a file prepared for download.
- `ER<code>` reports a protocol or filesystem error.

| Code | Meaning |
| ---: | --- |
| 1 | Unknown or unexpected command |
| 2 | Unknown user |
| 3 | Incorrect password |
| 5 | File/directory not found |
| 7 | Anonymous user lacks permission |
| 8 | File too large |
| 9 | Insufficient free space |
| 10 | Upload preparation/receive error |
| 11 | Delete/directory error |
| 12 | No quorum |
| 13 | This server is not the primary |
| 14 | Cannot share with yourself |
| 15 | Registration disabled |
| 16 | Invalid registration data |
| 17 | User disabled |
| 18 | User already exists |
| 19 | Protocol line too long |
| 20 | Revision conflict |

## Server-to-server replication

Replication uses a separate TLS/mTLS listener and one JSON object per CRLF line.
The primary connects to each peer and sends `HELLO`; the peer replies
`HELLO_OK`. Mutations are sent as `RB` with `term`, `index`, and `operation`.
Each secondary stores the proposal and replies `ACK`. Once a majority has
acknowledged, the primary commits, applies locally, and sends `COMMIT`.
Secondaries apply committed entries in order and reply `COMMITTED`. If quorum is
not reached, the primary sends `ABORT` and truncates the proposal.

```text
HELLO    {id, role, term, last_index, commit_index, token}
HELLO_OK {id, term, last_index, commit_index}
RB       {term, index, operation}
ACK      {term, index, id, status}
COMMIT   {term, index}
COMMITTED{term, index}
ABORT    {term, index}
SNAP     {term, index, snapshot}
```

`SNAP` replaces the local state during replica recovery. Automatic rejoin and
snapshot transfer on reconnect are M4.

## Client state

The client stores the last known remote metadata and a durable outbox in
SQLite. Pending operations are replayed after a restart, so closing the client
does not lose queued changes.
