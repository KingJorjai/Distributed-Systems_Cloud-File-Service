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

"$PYTHON" scripts/generate_dev_cert.py \
  --output "$KIT/server/certs" \
  --host localhost --host 127.0.0.1 >/dev/null
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
client_addresses = "server1@127.0.0.1:50012"
admin_enabled = true
admin_host = "0.0.0.0"
admin_port = 50080
admin_addresses = ""
allow_admin_failover = false
admin_session_timeout = 3600.0
TOML

cat > "$KIT/client/config.toml" <<'TOML'
[client]
server = "127.0.0.1"
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
Cloud File Service - kit offline para Linux x64
================================================

No hace falta Internet, Python ni terminal.

1. Descomprime este ZIP en una carpeta.
2. Para arrancar el servidor, abre la carpeta server y ejecuta
   start-server.sh (o CloudFS-Server.desktop).
   El servidor escucha en el puerto 50012.
3. Para arrancar el cliente, ejecuta cloudfs (sin argumentos) o
   CloudFS-Client.desktop. También puedes usar client/start-client.sh.
4. El cliente ya trae la CA y la configuración del servidor local.
   Si el servidor está en otro PC, cambia "Servidor" en la pantalla
   de acceso del cliente.
5. Registra una cuenta desde el cliente o usa el panel admin:
   https://localhost:50080/
   Usuario: sar
   Contraseña: $ADMIN_PASSWORD

Los logs están en logs/.
Los datos del servidor están en server/files.
La clave TLS del servidor está en server/certs/server.key.
No publiques esta carpeta: contiene la clave y la contraseña de demo.
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
