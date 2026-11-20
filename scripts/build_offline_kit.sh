#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -x .venv/bin/python ]]; then
  PYTHON=.venv/bin/python
else
  PYTHON=python
fi
VERSION="$("$PYTHON" -c 'import version; print(version.__version__)')"
ROOT="$PWD"
HOSTS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) HOSTS+=("$2"); shift 2 ;;
        *) OUT="$1"; shift ;;
    esac
done
if [[ ${#HOSTS[@]} -eq 0 ]]; then
    HOSTS=(localhost 127.0.0.1)
fi
# Use the first non-localhost host as the primary address, or 127.0.0.1
PRIMARY_HOST="127.0.0.1"
for h in "${HOSTS[@]}"; do
    if [[ "$h" != "localhost" && "$h" != "127.0.0.1" ]]; then
        PRIMARY_HOST="$h"
        break
    fi
done
OUT="${1:-demo/CloudFS-Offline-${VERSION}-linux-x64.zip}"
STAGE="$(mktemp -d -t cloudfs-kit-XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT

if [[ ! -f demo/bundles/cloudfs/cloudfs.tar.gz ]]; then
  echo "Missing unified cloudfs bundle; run scripts/build_demo_bundles.sh." >&2
  exit 1
fi

tar -xzf demo/bundles/cloudfs/cloudfs.tar.gz -C "$STAGE"
KIT="$STAGE/CloudFS-Offline"
mkdir -p "$KIT/server/files" "$KIT/server/certs" \
  "$KIT/client/client_files" "$KIT/client/state" "$KIT/client/certs"
cp -a "$STAGE/cloudfs/." "$KIT/"
rm -rf "$KIT/files" "$KIT/client_files" 2>/dev/null || true

HOST_ARGS=()
for h in "${HOSTS[@]}"; do
    HOST_ARGS+=(--host "$h")
done
"$PYTHON" scripts/generate_dev_cert.py \
  --output "$KIT/server/certs" \
  "${HOST_ARGS[@]}" >/dev/null
cp "$KIT/server/certs/ca.crt" "$KIT/client/certs/ca.crt"
chmod 600 "$KIT/server/certs/server.key"

TOKEN="$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(32))')"
ADMIN_PASSWORD="$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(18))')"

cat > "$KIT/server/config.toml" <<TOML
[server]
host = "0.0.0.0"
port = 50012
files_path = "server/files"
tls_cert_file = "server/certs/server.crt"
tls_key_file = "server/certs/server.key"
tls_ca_file = "server/certs/ca.crt"
registration_enabled = true
server_id = "server1"
role = "primary"
peers = ""
primary = ""
replication_host = "0.0.0.0"
replication_port = 60012
cluster_token = "$TOKEN"
term = 1
replication_timeout = 2.0
heartbeat_interval = 0.5
failure_timeout = 2.0
election_timeout = 1.0
client_addresses = "server1@${PRIMARY_HOST}:50012"
admin_enabled = true
admin_host = "0.0.0.0"
admin_port = 50080
admin_addresses = ""
allow_admin_failover = false
admin_session_timeout = 3600.0
TOML

cat > "$KIT/client/config.toml" <<TOML
[client]
server = "${PRIMARY_HOST}"
port = 50012
local_path = "client/client_files"
tls_ca_file = "client/certs/ca.crt"
tls_server_name = ""
state_dir = "client/state"
peers = ""
TOML

cat > "$KIT/server/start-server.sh" <<SH
#!/usr/bin/env bash
set -euo pipefail
KIT_ROOT="\$(cd "\$(dirname "\$0")/.." && pwd)"
cd "\$KIT_ROOT"
export CONFIG_FILE="\$KIT_ROOT/server/config.toml"
export APP_PASSWORD_SAR=$(printf '%q' "$ADMIN_PASSWORD")
export APP_PASSWORD_SZA=$(printf '%q' "$ADMIN_PASSWORD")
exec ./cloudfs server
SH
chmod 700 "$KIT/server/start-server.sh"

cat > "$KIT/client/start-client.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
KIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$KIT_ROOT"
exec ./cloudfs client --config "$KIT_ROOT/client/config.toml"
SH
chmod 700 "$KIT/client/start-client.sh"

cat > "$KIT/README.txt" <<README_EOF
Cloud File Service - offline kit for Linux x64
University of the Basque Country (UPV/EHU) - Distributed Systems
================================================

No Internet, Python or terminal is required.

1. Extract this ZIP into a folder.
2. To start the server, open the server folder and run
   start-server.sh (o CloudFS-Server.desktop).
   The server listens on port 50012.
3. To start the client, run cloudfs (with no arguments) or
   CloudFS-Client.desktop. You can also use client/start-client.sh.
4. The client already includes the CA and the local server configuration.
   If the server runs on another PC, change "Server" on the client
   sign-in screen.
5. Register an account from the client or use the admin panel:
   https://localhost:50080/
   Username: sar
   Password: $ADMIN_PASSWORD

Logs are in logs/.
Server data is in server/files.
The server TLS key is in server/certs/server.key.
Do not publish this folder: it contains the key and the demo password.
README_EOF

cat > "$KIT/CloudFS-Client.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=CloudFS Client
Comment=Cloud File Service client
Exec=bash -c 'cd "$(dirname "%k")" && ./cloudfs client --config "$PWD/client/config.toml"'
Terminal=false
DESKTOP
chmod 755 "$KIT/CloudFS-Client.desktop"

mkdir -p "$KIT/docs" "$KIT/packaging"
cp -a "$ROOT/packaging/." "$KIT/packaging/"
if [[ -f "$ROOT/site/cloud-file-service.pdf" ]]; then
    cp "$ROOT/site/cloud-file-service.pdf" "$KIT/docs/installation.pdf"
fi

cat > "$KIT/CloudFS-Server.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=CloudFS Server
Comment=Cloud File Service server
Exec=bash -c 'cd "$(dirname "%k")" && ./server/start-server.sh'
Terminal=false
DESKTOP
chmod 755 "$KIT/CloudFS-Server.desktop"

OUT="$(realpath -m "$OUT")"
mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"
(cd "$KIT" && zip -9 -r -q "$OUT" .)
echo "Offline kit written to $OUT"
ls -lh "$OUT"
