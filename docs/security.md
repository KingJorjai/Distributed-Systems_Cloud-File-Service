# Security

## Transport

All client and server traffic uses TLS. The server refuses to start without
`TLS_CERT_FILE` and `TLS_KEY_FILE`. Client connections verify the certificate
chain and the server hostname; there is no option to disable verification.

For local development:

```sh
python -m pip install -r requirements-dev.txt
python scripts/generate_dev_cert.py --output certs
export TLS_CERT_FILE=certs/server.crt
export TLS_KEY_FILE=certs/server.key
export CLIENT_TLS_CA_FILE=certs/ca.crt
```

`scripts/generate_dev_cert.py` creates a private CA, a server certificate for
`localhost` and `127.0.0.1`, and the matching key. The `certs/` directory is
ignored by Git.

For a networked deployment use a certificate issued by a public CA. A reverse
proxy such as Caddy can terminate TLS and proxy to the service, or the
certificate can be mounted directly:

```sh
export TLS_CERT_FILE=/etc/cloudfs/fullchain.pem
export TLS_KEY_FILE=/etc/cloudfs/privkey.pem
```

When using a private CA, distribute `ca.crt` to clients and set
`CLIENT_TLS_CA_FILE`. Do not commit private keys.

## Passwords

- Registration passwords are hashed with PBKDF2-HMAC-SHA256 (200,000
  iterations, random 16-byte salt).
- Password verification uses a constant-time comparison.
- Passwords are sent inside the TLS channel and are never logged or stored in
  plaintext.
- Bootstrap administrator passwords come from `APP_PASSWORD_SAR` and
  `APP_PASSWORD_SZA`; an empty value disables that account.

## Current limitations

- No TLS certificate rotation or automatic renewal is built in; use a reverse
  proxy or renew the mounted certificate.
- No rate limiting or account lockout yet.
- No email verification or self-service password reset. An administrator can
  change a password through the future admin interface.
- `anonimous` is read-only and cannot be used as a share grantee.
