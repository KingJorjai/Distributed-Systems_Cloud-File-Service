#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

DEMO_DIR="${DEMO_DIR:-$(mktemp -d -t cloudfs-docker-demo-XXXXXX)}"
export SERVER1_DATA_PATH="$DEMO_DIR/server1"
export SERVER2_DATA_PATH="$DEMO_DIR/server2"
export SERVER3_DATA_PATH="$DEMO_DIR/server3"
export CLIENT_DATA_PATH="$DEMO_DIR/client"
export CERTS_PATH="$DEMO_DIR/certs"
mkdir -p "$SERVER1_DATA_PATH" "$SERVER2_DATA_PATH" "$SERVER3_DATA_PATH" "$CLIENT_DATA_PATH"

cleanup() {
  if [[ "${DEMO_KEEP:-0}" != "1" ]]; then
    docker compose down >/dev/null 2>&1 || true
    rm -rf "$DEMO_DIR"
  else
    echo "Kept demo directory: $DEMO_DIR"
  fi
}
trap cleanup EXIT

echo "Cloud File Service Docker demo: $DEMO_DIR"
python scripts/generate_dev_cert.py --output "$CERTS_PATH" \
  --host server1 --host server2 --host server3 \
  --host localhost --host 127.0.0.1 >/dev/null

echo "Starting the three-server cluster"
docker compose up -d --build server1 server2 server3

for _ in $(seq 1 40); do
  statuses="$(docker compose ps --format '{{.Service}} {{.Health}}')"
  if grep -q 'server1 healthy' <<<"$statuses" \
    && grep -q 'server2 healthy' <<<"$statuses" \
    && grep -q 'server3 healthy' <<<"$statuses"; then
    break
  fi
  sleep 1
done

hash_of() {
  docker compose exec -T "$1" python -c \
    "from file_store import FileStore; print(FileStore('/app/files').state_hash())" | tr -d '\r'
}

wait_equal() {
  local expected="$1"
  shift
  for _ in $(seq 1 15); do
    local ok=1
    for service in "$@"; do
      if [[ "$(hash_of "$service")" != "$expected" ]]; then
        ok=0
        break
      fi
    done
    if [[ "$ok" == "1" ]]; then
      return 0
    fi
    sleep 1
  done
  echo "Replicas did not converge:" >&2
  for service in "$@"; do
    echo "  $service $(hash_of "$service")" >&2
  done
  return 1
}

echo "Registering alice and bob and uploading the initial file"
docker compose run --rm --no-deps --entrypoint python client -c '
import time
from config import load_config
from client_session import ClientSession, SyncError
c = load_config().client
s = ClientSession(c); s.connect()
for user, password in (("alice", "password-alice"), ("bob", "password-bob")):
    try:
        s.register(user, password)
    except SyncError:
        pass
s.close()
s = ClientSession(c); s.connect_and_login("alice", "password-alice")
s.upload("alice", "demo.txt", b"before failover\n")
s.share("demo.txt", "bob", "rw")
s.close()
print("initial upload and share complete")
'

initial_hash="$(hash_of server1)"
wait_equal "$initial_hash" server1 server2 server3
echo "Initial state: $initial_hash"

echo "Stopping the primary (server1)"
docker compose stop server1 >/dev/null
sleep 4

echo "Uploading through the new primary"
docker compose run --rm --no-deps --entrypoint python client -c '
import time
from config import load_config
from client_session import ClientSession
c = load_config().client
for _ in range(20):
    try:
        s = ClientSession(c); s.connect_and_login("alice", "password-alice")
        s.upload("alice", "after.txt", b"after failover\n")
        s.close()
        print("post-failover upload complete")
        break
    except Exception as error:
        time.sleep(1)
else:
    raise SystemExit("no primary available after failover")
'

after_hash="$(hash_of server2)"
wait_equal "$after_hash" server2 server3
echo "State while server1 is stopped: $after_hash"

echo "Restarting the old primary"
docker compose start server1 >/dev/null
for _ in $(seq 1 20); do
  if [[ "$(hash_of server1)" == "$after_hash" ]]; then
    break
  fi
  sleep 1
done
wait_equal "$after_hash" server1 server2 server3
echo "State after rejoin: $after_hash"
echo "Docker demo complete"
