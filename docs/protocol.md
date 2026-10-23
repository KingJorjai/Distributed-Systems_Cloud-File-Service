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
| `UPLOfilename?size=<n>&rev=<n>&hash=<hex>` | Prepare an upload with revision metadata. |
| `UPL2` | Send the upload bytes after the server accepts them. |
| `MKDRdirname` | Create a directory. |
| `RMDRdirname` | Delete a directory and its contents. |
| `DELEfilename` | Delete a file. |
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
  | UPLOfilename?size=5&rev=0&hash=... |
  |----------------------------------->|
  |                 OK                |
  |<-----------------------------------|
  | UPL2 + CRLF + file bytes           |
  |----------------------------------->|
  |                 OK                |
  |<-----------------------------------|
```

The server validates authentication, ACL, size, free space, and the target
path before accepting the bytes. Uploads are written to a temporary file and
moved into place atomically.

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
| 14 | Cannot share with yourself |
| 15 | Registration disabled |
| 16 | Invalid registration data |
| 17 | User disabled |
| 18 | User already exists |
| 19 | Protocol line too long |
| 20 | Revision conflict |

## Client state

The client stores the last known remote metadata and a durable outbox in
SQLite. Pending operations are replayed after a restart, so closing the client
does not lose queued changes.
