#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="${TMPDIR:-/tmp}/cloudfs-kit-stage"
OUT="${1:-$ROOT/demo/CloudFS-Offline-0.12.0-linux-x64.zip}"

rm -rf "$STAGE"
mkdir -p "$STAGE/CloudFS"
KIT="$STAGE/CloudFS"

# Binaries and shared libraries.
cp -a "$ROOT/demo/bundles/cloudfs/." "$KIT/"
# The bundle ships a README; replace it with the kit one below.
rm -f "$KIT/README-client-gui.txt"

# Layout.
mkdir -p "$KIT/config" "$KIT/certs" "$KIT/data" "$KIT/state" "$KIT/logs" \
         "$KIT/packaging" "$KIT/docs"

# Packaging helpers and units.
cp -a "$ROOT/packaging/." "$KIT/packaging/"

# Documentation.
if [[ -f "$ROOT/site/cloud-file-service.pdf" ]]; then
    cp "$ROOT/site/cloud-file-service.pdf" "$KIT/docs/installation.pdf"
fi
if [[ -f "$ROOT/site/lab-walkthrough.pdf" ]]; then
    cp "$ROOT/site/lab-walkthrough.pdf" "$KIT/docs/lab-walkthrough.pdf"
fi

cat > "$KIT/README.txt" <<'README_EOF'
Cloud File Service - offline kit for Linux x64
University of the Basque Country (UPV/EHU) - Distributed Systems
================================================

Self-contained: no Internet, Python or root access required.

1. Extract this ZIP into a folder (it creates a "CloudFS" folder).
2. Open a terminal in that folder.
3. First run only:
       ./cloudfs setup
   This creates config/, certs/, data/ and prints the administrator
   credentials. Keep the password safe.
4. Start the server:
       ./cloudfs server
5. Open the admin panel:
       https://<your-ip>:50080/
6. Start the desktop client (another terminal):
       ./cloudfs client

For a replicated cluster (three machines):
       ./cloudfs setup --cluster 192.168.1.101,192.168.1.102,192.168.1.103
   then copy each cluster/serverN directory to its machine.

Verify the installation:
       ./cloudfs status

Logs:   logs/
Data:   data/
Certs:  certs/   (the CA private key is removed after setup)

Do not publish this folder: it contains the server key and your data.
README_EOF

# Ensure the binary is executable.
chmod +x "$KIT/cloudfs"

OUT="$(realpath -m "$OUT")"
mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"
(cd "$STAGE" && zip -9 -r -q "$OUT" CloudFS)
echo "Offline kit written to $OUT"
ls -lh "$OUT"