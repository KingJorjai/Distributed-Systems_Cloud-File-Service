# Reproducible Demo

The demonstration shows three servers, two clients, a shared file, a primary
failure, election, a post-failover upload, and rejoin. Two variants are
provided: a fast local script and a real Docker Compose cluster.

## Prerequisites

- Python 3.10+ and the project virtual environment.
- Development dependencies (`trustme`) for certificate generation.
- Docker Engine with Compose v2 for the container demo.
- Chromium and Mermaid CLI only if you also build the documentation PDF.

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
```

## Local demo

```sh
python scripts/demo_failover.py
```

The script prints each milestone:

1. start `server2` and `server3`;
2. start `server1` as primary;
3. register `alice` and `bob`;
4. start two synchronization workers;
5. upload `docs/readme.txt` from alice;
6. share `docs` with bob as `rw` and wait for his local copy;
7. modify the shared file from bob and verify alice's server copy;
8. compare the three state hashes;
9. stop the primary and wait for election;
10. upload after failover;
11. restart the old primary and wait for snapshot convergence;
12. print the final state hash on all three servers.

A successful run ends with `Demo complete` and three identical short hashes.
Use `--keep` to retain the temporary directory for inspection.

## Docker demo

```sh
scripts/demo_docker.sh
```

The script:

- creates temporary server/client data directories and development
  certificates;
- starts `server1`, `server2`, and `server3` with `docker compose`;
- waits for all three health checks;
- registers `alice` and `bob`, uploads `demo.txt`, and shares it;
- verifies the initial `state_hash` on all three nodes;
- stops `server1`, waits for the election, and uploads `after.txt` through the
  new primary;
- verifies convergence on the two remaining nodes;
- restarts `server1`, waits for rejoin, and verifies all three hashes;
- removes the containers and temporary data unless `DEMO_KEEP=1`.

Set `DEMO_KEEP=1` to keep the containers and print the temporary directory.
After inspecting the result, clean up with:

```sh
docker compose down
```

## Admin panel demo

With the Docker cluster running:

```text
https://localhost:50080/
https://localhost:50081/
https://localhost:50082/
```

Log in as `sar` or `sza` using `APP_PASSWORD_SAR` / `APP_PASSWORD_SZA` from
`.env`. The primary has write actions; secondary panels show status and redirect
actions to the primary. `ALLOW_ADMIN_FAILOVER=1` exposes the demo step-down
button.

## GUI demo

The desktop client can be demonstrated on a graphical session:

```sh
python gui_fich.py --config /tmp/cloudfs-demo/config.toml
```

Register or log in, choose the local folder, and synchronize. Close the window
to hide it in the tray; synchronization continues in the daemon. Use the tray
menu to show the window, pause/resume, or quit. A second user can run with a
different `CONFIG_FILE` and `CLIENT_STATE_DIR` to demonstrate sharing.
