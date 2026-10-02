# Protocol

The service uses a simple line-based TCP protocol. Every command ends with `CRLF` (`\\r\\n`) and every response starts with `OK` or `ER`.

## Commands

| Command | Purpose |
| --- | --- |
| `USERname` | Select a user. |
| `PASSpassword` | Authenticate the user. |
| `DOWNfilename` | Prepare a file download. |
| `DOW2` | Request the prepared file bytes. |
| `UPLOfilename?size` | Prepare an upload. |
| `UPL2` | Send the upload bytes after the server accepts them. |
| `MKDRdirname` | Create a directory. |
| `RMDRdirname` | Delete a directory and its contents. |
| `DELEfilename` | Delete a file. |
| `EXIT` | Close the session. |

Commands use the four-character prefixes defined in `szasar.Command`. The protocol does not add spaces between a command prefix and its arguments. There is no `LIST` command in the current implementation; clients must know a path before requesting it with `DOWN`.

## Upload flow

```text
Client                         Server
  | USER + username               |
  |------------------------------>|
  | PASS + password               |
  |------------------------------>|
  | UPLOfilename?size             |
  |------------------------------>|
  |              OK               |
  |<------------------------------|
  | UPL2 + CRLF + file bytes      |
  |------------------------------>|
  |              OK               |
  |<------------------------------|
```

The server validates permissions, size, available space, and the target path before accepting the bytes.

## Responses

- `OK` means the command was accepted.
- `OK<size>` announces the size of a file prepared for download.
- `ER<code>` reports a protocol or filesystem error. The client maps these codes to user-facing messages.
