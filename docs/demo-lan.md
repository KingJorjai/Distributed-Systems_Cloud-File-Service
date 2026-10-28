# LAN Demo

This guide runs the distributed demo on several laboratory PCs with the
self-contained Linux bundles. The Ubuntu 22.04 demo uses Python 3.10.12, but the
bundles include their own interpreter and do not require Python on the demo PCs.

## Layout

The default laboratory layout uses three servers and two clients on four PCs:

| PC | Roles |
| --- | --- |
| PC1 | `server1`, primary |
| PC2 | `server2`, secondary |
| PC3 | `server3`, secondary |
| PC4 | `client1` (`alice`), `client2` (`bob`), admin browser |

The generator supports any number of servers and clients, and several
processes may share a PC. Use different generated directories, ports, data
directories, and client state directories when roles share a machine.

For the smaller single-ZIP client/server kit, see the
[Offline Kit](offline-kit.md).

## Build the demo bundles

The generator and certificate step require the repository, Python 3.10.12, and
`requirements-dev.txt` (`trustme`). The bundle build requires Docker.

Build the Linux server, CLI client, and GUI client bundles on Ubuntu 22.04:

```sh
scripts/build_demo_bundles.sh
```

The bundles are written to `demo/bundles/`. Do not use a Linux bundle built on a
newer distribution for Ubuntu 22.04 without testing it first.

Extract the bundles on the demo PCs:

```sh
mkdir -p ~/cloudfs-demo
tar -xzf demo/bundles/server/cloud-file-server.tar.gz -C ~/cloudfs-demo
tar -xzf demo/bundles/client/cloud-file-client.tar.gz -C ~/cloudfs-demo
tar -xzf demo/bundles/client-gui/cloud-file-client-gui.tar.gz -C ~/cloudfs-demo
```

Set the bundle paths in each shell:

```sh
export CLOUDFS_SERVER_BUNDLE=~/cloudfs-demo/cloud-file-server
export CLOUDFS_CLIENT_BUNDLE=~/cloudfs-demo/cloud-file-client
export CLOUDFS_CLIENT_GUI_BUNDLE=~/cloudfs-demo/cloud-file-client-gui
```

## Generate the LAN configuration

Choose fixed IPs for the server PCs and list the client PCs. The generator
creates certificates with every server IP as a SAN, server/client
configurations, startup scripts, a token, demo passwords, and a runbook.

```sh
python scripts/demo_lan_config.py \
  --server server1@192.168.1.101:50012:60012:50080 \
  --server server2@192.168.1.102:50012:60012:50080 \
  --server server3@192.168.1.103:50012:60012:50080 \
  --client alice@192.168.1.111 \
  --client bob@192.168.1.112 \
  --output demo/lan
```

For several servers on one PC, give each instance different client,
replication, and admin ports. For example:

```sh
--server server1@192.168.1.101:50012:60012:50080 \
--server server2@192.168.1.101:50013:60013:50081
```

The generated layout contains:

- `certs/`: CA, server certificate, and server key;
- `server-<id>/`: `config.toml`, `files/`, certificates, and `run-server.sh`;
- `client-<name>/`: `config.toml`, `client_files/`, `state/`, CA, and run scripts;
- `RUNBOOK.md`;
- `demo-accounts.txt`;
- `cluster-token.txt`.

Do not commit `demo/lan/`: it contains private keys and demo passwords.

## Certificates

Import `certs/ca.crt` into the browser used for the admin panel. Copy only
`client-*/certs/ca.crt` to client PCs. Keep each `server.key` only on its server
PC.

## Start the servers

On each server PC, copy the corresponding generated `server-<id>` directory and
run:

```sh
export CLOUDFS_SERVER_BUNDLE=/path/to/cloud-file-server
cd server-server1
./run-server.sh
```

Start the primary first, then the secondaries. The startup script sets
`CONFIG_FILE` and the bootstrap administrator passwords from the generated
layout.

## Start the clients

On each client PC, copy the corresponding generated `client-<name>` directory
and run:

```sh
export CLOUDFS_CLIENT_GUI_BUNDLE=/path/to/cloud-file-client-gui
cd client-alice
./run-client.sh
```

The GUI starts the local daemon and can be closed to the system tray. Use
`run-client-cli.sh` for a CLI-only client:

```sh
export CLOUDFS_CLIENT_BUNDLE=/path/to/cloud-file-client
cd client-alice
./run-client-cli.sh
```

Each client directory has its own local folder and state directory, so two
clients can run on the same PC.

## Accounts

Open the admin panel on any server, log in as `sar` or `sza` with the password
in `RUNBOOK.md`, and create the users listed in `demo-accounts.txt`. Registration
remains enabled for the demo. The accounts are replicated to all servers.

## Admin panel

The generated `RUNBOOK.md` lists all admin URLs:

```text
https://192.168.1.101:50080/
https://192.168.1.102:50080/
https://192.168.1.103:50080/
```

Any PC on the LAN can open any node. A secondary shows the cluster status and
redirects mutations to the current primary. After a failover, open the new
primary or use a secondary redirect and log in again. Admin sessions are local
to each node.

## Network check

Run the checker from each PC:

```sh
python scripts/demo_lan_check.py \
  --server server1@192.168.1.101:50012:60012:50080 \
  --server server2@192.168.1.102:50012:60012:50080 \
  --server server3@192.168.1.103:50012:60012:50080 \
  --ca demo/lan/certs/ca.crt
```

It checks TCP, TLS, the admin `/healthz` endpoint, and `PRIM` from the machine
where it runs. Use `--client-cert` and `--client-key` to also test the
replication handshake:

```sh
python scripts/demo_lan_check.py \
  --server server1@192.168.1.101:50012:60012:50080 \
  --server server2@192.168.1.102:50012:60012:50080 \
  --server server3@192.168.1.103:50012:60012:50080 \
  --ca demo/lan/certs/ca.crt \
  --client-cert demo/lan/server-server1/certs/server.crt \
  --client-key demo/lan/server-server1/certs/server.key \
  --token "$(cat demo/lan/cluster-token.txt)"
```

## Firewall

Allow these ports on each server PC from the laboratory subnet:

| Port | Purpose |
| ---: | --- |
| `50012+` | client protocol |
| `60012+` | replication |
| `50080+` | HTTPS admin panel |

On Ubuntu, check `ufw` or `nft`. For example, for the usual `192.168.1.0/24`
laboratory subnet:

```sh
sudo ufw allow from 192.168.1.0/24 to any port 50012:50020 proto tcp
sudo ufw allow from 192.168.1.0/24 to any port 60012:60020 proto tcp
sudo ufw allow from 192.168.1.0/24 to any port 50080:50090 proto tcp
```

On Windows:

```powershell
New-NetFirewallRule -DisplayName "CloudFS client" -Direction Inbound `
  -Protocol TCP -LocalPort 50012-50020 -RemoteAddress 192.168.1.0/24 -Action Allow
New-NetFirewallRule -DisplayName "CloudFS replication" -Direction Inbound `
  -Protocol TCP -LocalPort 60012-60020 -RemoteAddress 192.168.1.0/24 -Action Allow
New-NetFirewallRule -DisplayName "CloudFS admin" -Direction Inbound `
  -Protocol TCP -LocalPort 50080-50090 -RemoteAddress 192.168.1.0/24 -Action Allow
```

The demo does not require Internet access.

## Demo script

1. Start the three servers and verify the admin panel.
2. Create `alice` and `bob` in the admin panel.
3. Log in as `alice` on `client1` and upload a file.
4. Log in as `bob` on `client2`.
5. Share the file or directory with `bob` and verify the local copy.
6. Modify the shared file from `bob` and verify the notification in `alice`.
7. Compare the three server state hashes from the admin panel.
8. Stop the primary server.
9. Wait for the new primary and upload after failover.
10. Restart the old primary and verify snapshot rejoin.
11. Repeat the demo from a clean `files/` and client state.

## Quorum and server counts

The quorum is `floor(N / 2) + 1` for `N` servers:

- 1 server: standalone, no failover;
- 2 servers: quorum 2, so there is no failover when one node stops;
- 3 servers: recommended for the demo;
- more servers: supported, but use an odd number for the best fault tolerance.

## Troubleshooting

- **TLS error:** verify the server IP is in the certificate SAN and the client
  uses the generated `ca.crt`.
- **Name resolution:** use fixed IP addresses in the generated configurations.
- **Connection refused:** check the server process, firewall, and that the
  generated ports match.
- **Secondary admin redirect:** set the generated `admin_addresses` and make
  the primary URL reachable from the browser.
- **Bundle fails on Ubuntu 22.04:** rebuild it with
  `scripts/build_demo_bundles.sh`; do not use a bundle built on a newer glibc.
