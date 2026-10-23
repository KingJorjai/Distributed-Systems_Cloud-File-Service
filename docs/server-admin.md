# Server Administration

The server exposes an HTTPS administration panel. It is disabled by default and
must be enabled explicitly:

```sh
export SERVER_ADMIN_ENABLED=true
export SERVER_ADMIN_HOST=127.0.0.1
export SERVER_ADMIN_PORT=50080
```

The panel uses the same `TLS_CERT_FILE`/`TLS_KEY_FILE` as the file service. It
refuses to serve plaintext HTTP. With a development certificate, import
`certs/ca.crt` into the browser or accept the one-time certificate warning.

## Login

Only users with `role = admin` can log in. The bootstrap `sar` and `sza`
accounts are administrators; accounts created through open registration have
the `user` role.

Sessions are server-side. The cookie is `HttpOnly`, `SameSite=Strict`, and
`Secure`; all state-changing forms require a CSRF token. Passwords are never
stored or logged by the panel.

## Features

- **Status:** server id, role, term, primary, commit index, last index, peers,
  active client sessions, user/share counts, and registration state.
- **Users:** create regular users, disable/enable accounts, and reset passwords.
  The last enabled administrator and the current administrator cannot be
  disabled.
- **Shares:** list all owner/grantee shares and revoke them.
- **Settings:** enable or disable open registration. The setting is replicated.
- **Audit:** recent administrative actions in memory.
- **Step-down demo:** when `ALLOW_ADMIN_FAILOVER=1`, the primary can voluntarily
  step down, allowing the secondaries to elect a replacement.

The panel never exposes file contents or password hashes. Disabling a user
closes their notification subscription and rejects subsequent client commands.

## Replication and secondaries

Every node can serve the read-only status page. Mutations are sent through
`ServerRuntime.commit_operation`, so they require the primary and a 2/3 quorum.
On a secondary, actions redirect to the primary admin URL configured through
`SERVER_ADMIN_ADDRESSES`:

```text
server1@host1:50080,server2@host2:50080,server3@host3:50080
```

`SERVER_ADMIN_ADDRESSES` must contain browser-reachable URLs. In Docker Compose
the host ports are `50080`, `50081`, and `50082`; the mapping uses `localhost`.

## Docker

Compose enables the panel on all three nodes and publishes the three host
ports. The primary is at `https://localhost:50080/`; `server2` and `server3` are
read-only unless they become primary.

```sh
docker compose up -d server1 server2 server3
```

Set `APP_PASSWORD_SAR` and `APP_PASSWORD_SZA` in `.env`, then log in with `sar`
or `sza`. `ALLOW_ADMIN_FAILOVER=1` enables the demo step-down button; set it to
`0` outside the demonstration.

## Security notes

- Bind to `127.0.0.1` for a single-host deployment; only expose the panel on a
  trusted network or behind a reverse proxy.
- There is no HTTP fallback and no unauthenticated write endpoint.
- The development certificate is self-signed; browsers will warn until the CA
  is trusted.
- There is no login rate limiting yet; document or add a reverse proxy for a
  production deployment.
- `step_down` is a demo control, not a replacement for the automatic failure
  detector.
