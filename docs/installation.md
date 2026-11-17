# Installation Guide

This guide installs Cloud File Service on independent machines. It covers a
single server and a replicated cluster. It does not assume a fixed layout,
fixed IP addresses, or any particular number of nodes.

The guide targets Ubuntu 22.04 and Python 3.10.12. Python 3.10 is
end-of-life, so this guide is intended for the demonstration environment. A
production deployment must migrate to a supported Python release.

## Prerequisites

- Ubuntu 22.04 on each machine.
- The self-contained Linux bundles, or the repository and a Python 3.10.12
  virtual environment.
- A fixed IP address or hostname for each server.
- Open firewall ports between the machines.
- A browser that can import a private CA, or a browser where the certificate
  warning can be accepted once.
- No Internet access is required after the bundles, certificates, and
  configuration are copied.

## Network layout

Choose one of these layouts.

### Single node

```text
server1: 192.168.1.101
client1: 192.168.1.111
```

The server runs in standalone mode with quorum 1.

### Multi-node cluster

```text
server1: 192.168.1.101   primary
server2: 192.168.1.102   secondary
server3: 192.168.1.103   secondary
client1: 192.168.1.111
client2: 192.168.1.112
```

Replace every example IP with the real machine addresses. The same steps work
for one server and one client, or for more nodes.

## Firewall

Allow these ports from the trusted network on each server:

```sh
sudo ufw allow from 192.168.1.0/24 to any port 50012 proto tcp
sudo ufw allow from 192.168.1.0/24 to any port 60012 proto tcp
sudo ufw allow from 192.168.1.0/24 to any port 50080 proto tcp
```

| Port | Purpose |
| ---: | --- |
| `50012` | Client protocol |
| `60012` | Replication |
| `50080` | HTTPS admin panel |

On Windows, create equivalent inbound rules with `New-NetFirewallRule`.

## Certificates

Generate one CA and one server certificate with every server address as a SAN:

```sh
python scripts/generate_dev_cert.py --output certs \
  --host server1.example.com \
  --host server2.example.com \
  --host server3.example.com \
  --host 192.168.1.101 \
  --host 192.168.1.102 \
  --host 192.168.1.103 \
  --host localhost \
  --host 127.0.0.1
```

Copy to each server:

```text
certs/ca.crt
certs/server.crt
certs/server.key
```

Copy only `certs/ca.crt` to each client. Keep `server.key` only on the servers.

If the addresses change, regenerate the certificate. The development CA is intended for the demonstration; use a public CA for a
real deployment.

## Server configuration

### Single server

```toml
[server]
host = "0.0.0.0"
port = 50012
files_path = "files"
tls_cert_file = "certs/server.crt"
tls_key_file = "certs/server.key"
tls_ca_file = "certs/ca.crt"
registration_enabled = true
server_id = "server1"
role = "primary"
peers = ""
primary = ""
replication_host = "0.0.0.0"
replication_port = 60012
cluster_token = ""
term = 1
replication_timeout = 2.0
heartbeat_interval = 0.5
failure_timeout = 2.0
election_timeout = 1.0
client_addresses = ""
admin_enabled = true
admin_host = "0.0.0.0"
admin_port = 50080
admin_addresses = ""
allow_admin_failover = false
admin_session_timeout = 3600.0
```

### Primary of a three-server cluster

```toml
[server]
host = "0.0.0.0"
port = 50012
files_path = "files"
tls_cert_file = "certs/server.crt"
tls_key_file = "certs/server.key"
tls_ca_file = "certs/ca.crt"
registration_enabled = true
server_id = "server1"
role = "primary"
peers = "server2@192.168.1.102:60012,server3@192.168.1.103:60012"
primary = ""
replication_host = "0.0.0.0"
replication_port = 60012
cluster_token = "shared-secret"
term = 1
replication_timeout = 2.0
heartbeat_interval = 0.5
failure_timeout = 2.0
election_timeout = 1.0
client_addresses = "server1@192.168.1.101:50012,server2@192.168.1.102:50012,server3@192.168.1.103:50012"
admin_enabled = true
admin_host = "0.0.0.0"
admin_port = 50080
admin_addresses = "server1@192.168.1.101:50080,server2@192.168.1.102:50080,server3@192.168.1.103:50080"
allow_admin_failover = true
admin_session_timeout = 3600.0
```

### Secondary

Use the same template with these changes:

```toml
server_id = "server2"
role = "secondary"
peers = "server1@192.168.1.101:60012,server3@192.168.1.103:60012"
primary = "server1@192.168.1.101:60012"
```

### Client

```toml
[client]
server = "192.168.1.101"
port = 50012
local_path = "client_files"
tls_ca_file = "certs/ca.crt"
tls_server_name = ""
state_dir = "state"
peers = "192.168.1.101:50012,192.168.1.102:50012,192.168.1.103:50012"
```

Leave `tls_server_name` empty when the endpoints use different hostnames or IP
addresses. The certificate must contain each server address as a SAN.

## Start the server

```sh
export CLOUDFS_SERVER_BUNDLE=/path/to/cloud-file-server
cd /path/to/server
export CONFIG_FILE="$PWD/config.toml"
export APP_PASSWORD_SAR='set-a-local-password'
export APP_PASSWORD_SZA='set-another-local-password'
./cloud-file-server
```

Expected output:

```text
Servidor TLS 0.11.3 escuchando en el puerto 50012 (rol primary).
```

For a secondary:

```text
Servidor TLS 0.11.3 escuchando en el puerto 50012 (rol secondary).
```

The server listens on port `50012` by default. It refuses plaintext
connections.

## Start the client

```sh
export CLOUDFS_CLIENT_GUI_BUNDLE=/path/to/cloud-file-client-gui
cd /path/to/client
./cloudfs
```

The client opens with the bundled configuration and CA. It starts the daemon if
it is not already running. Closing the window hides it to the system tray or
minimizes it if no tray is available.

## Accounts

Open the admin panel on any server:

```text
https://192.168.1.101:50080/
https://192.168.1.102:50080/
https://192.168.1.103:50080/
```

Log in as `sar` or `sza` using the passwords configured for that server. Create
`alice` and `bob` from the primary panel. Registration remains enabled by
default.

The admin panel on a secondary shows the cluster status and redirects mutations
to the primary admin URL. After a failover, open the new primary or use a
secondary redirect. Admin sessions are local to each node.

## Verification

Run from each client or server:

```sh
python scripts/demo_lan_check.py \
  --server server1@192.168.1.101:50012:60012:50080 \
  --server server2@192.168.1.102:50012:60012:50080 \
  --server server3@192.168.1.103:50012:60012:50080 \
  --ca demo/lan/certs/ca.crt
```

Expected result:

```text
[ok] server1 client tcp 192.168.1.101:50012
[ok] server1 client tls 192.168.1.101:50012: TLSv1.3
[ok] server1 PRIM 192.168.1.101:50012: OK192.168.1.101:50012
[ok] server1 replication tcp 192.168.1.101:60012
[ok] server1 admin 192.168.1.101:50080: HTTP/1.0 200 OK OK
...
All checks passed.
```

Use `--client-cert`, `--client-key`, and `--token` to also test the replication
handshake.

## Failover

1. Start all servers.
2. Start the clients.
3. Upload a file from `alice`.
4. Share the file or directory with `bob` as `rw`.
5. Verify that `bob` receives the shared file.
6. Modify the shared file from `bob`.
7. Verify that `alice` receives the notification.
8. Compare the three state hashes.
9. Stop the primary server.
10. Wait for election.
11. Upload after failover.
12. Restart the old primary.
13. Verify snapshot rejoin.

## Quorum and server counts

The quorum for `N` servers is `floor(N / 2) + 1`:

- 1 server: standalone, no failover;
- 2 servers: quorum 2, so there is no failover when one node stops;
- 3 servers: recommended;
- more than 3: supported, but use an odd number for the best fault tolerance.

## Troubleshooting

- **TLS error:** verify that every server address is in the certificate SAN and
  that the client uses the generated `ca.crt`.
- **Connection refused:** check the server process, firewall, and configured
  ports.
- **Secondary admin redirect:** set `admin_addresses` to browser-reachable URLs.
- **No primary:** check `PRIM`, server logs, and the cluster token.
- **Tray missing:** the compact kit minimizes to the taskbar; the full GUI
  bundle still contains the tray.
- **Bundle fails on Ubuntu 22.04:** rebuild it with
  `scripts/build_demo_bundles.sh`; do not use a bundle built on a newer glibc.

## Notes

- Python 3.10 is end-of-life. This guide targets the Ubuntu 22.04 laboratory
  environment only.
- The admin panel is HTTPS-only and uses the same server certificate.
- The offline kit is a separate single-ZIP variant for one machine.
