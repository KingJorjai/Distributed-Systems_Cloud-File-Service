#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

OUTPUT="${1:-demo/bundles}"
mkdir -p "$OUTPUT"
OUTPUT="$(cd "$OUTPUT" && pwd)"

docker run --rm \
  -v "$PWD:/src:ro" \
  -v "$OUTPUT:/out" \
  --env HOST_UID="$(id -u)" \
  --env HOST_GID="$(id -g)" \
  -w /tmp \
  ubuntu:22.04 \
  bash -lc '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip python3-tk libpython3.10 build-essential
python3 --version
python3 -m venv /venv
. /venv/bin/activate
python -m pip install --no-cache-dir -r /src/requirements.txt -r /src/requirements-release.txt
cp -a /src /work
cd /work
export PYTHONDONTWRITEBYTECODE=1
for component in server client client-gui client-gui-lite cloudfs; do
  python scripts/build_release_bundle.py "$component" \
    --output "/out/$component" \
    --archive-format gztar
done
chown -R "$HOST_UID:$HOST_GID" /out
'

echo "Demo bundles written to $OUTPUT"
find "$OUTPUT" -maxdepth 2 -type f -name '*.tar.gz' -printf '%p\n'
