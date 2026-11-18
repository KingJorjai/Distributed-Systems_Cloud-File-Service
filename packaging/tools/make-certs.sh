#!/usr/bin/env bash
# Generate a development CA and server certificate for Cloud File Service.
# The server certificate contains every --host value as a SAN (IP or DNS).
# Usage:
#   ./make-certs.sh --out certs --host 192.168.1.101 --host server1.example.com
set -euo pipefail

OUT="certs"
HOSTS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --out) OUT="$2"; shift 2 ;;
        --host) HOSTS+=("$2"); shift 2 ;;
        -h|--help)
            sed -n '2,8p' "$0"
            exit 0
            ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [[ ${#HOSTS[@]} -eq 0 ]]; then
    HOSTS=(localhost 127.0.0.1)
fi

mkdir -p "$OUT"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# --- CA ---
openssl genrsa -out "$OUT/ca.key" 2048 >/dev/null 2>&1
openssl req -x509 -new -nodes -key "$OUT/ca.key" -sha256 -days 3650 \
    -subj "/CN=Cloud File Service Development CA" \
    -out "$OUT/ca.crt" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "subjectKeyIdentifier=hash" >/dev/null 2>&1

# --- server key and request ---
openssl genrsa -out "$OUT/server.key" 2048 >/dev/null 2>&1

ALT="$TMPDIR/alt.cnf"
{
    echo "[req]"
    echo "distinguished_name = req_distinguished_name"
    echo "req_extensions = v3_req"
    echo "prompt = no"
    echo "[req_distinguished_name]"
    echo "CN = Cloud File Service"
    echo "[v3_req]"
    echo "keyUsage = critical, digitalSignature, keyEncipherment"
    echo "extendedKeyUsage = serverAuth, clientAuth"
    echo "basicConstraints = critical, CA:FALSE"
    echo "subjectKeyIdentifier = hash"
    echo "subjectAltName = @alt_names"
    echo "[v3_cert]"
    echo "keyUsage = critical, digitalSignature, keyEncipherment"
    echo "extendedKeyUsage = serverAuth, clientAuth"
    echo "basicConstraints = critical, CA:FALSE"
    echo "subjectKeyIdentifier = hash"
    echo "authorityKeyIdentifier = keyid,issuer"
    echo "subjectAltName = @alt_names"
    echo "[alt_names]"
    i=1
    for h in "${HOSTS[@]}"; do
        if [[ "$h" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "IP.$i = $h"
        else
            echo "DNS.$i = $h"
        fi
        i=$((i + 1))
    done
} > "$ALT"

openssl req -new -key "$OUT/server.key" -out "$TMPDIR/server.csr" \
    -config "$ALT" >/dev/null 2>&1

openssl x509 -req -in "$TMPDIR/server.csr" \
    -CA "$OUT/ca.crt" -CAkey "$OUT/ca.key" -CAcreateserial \
    -out "$OUT/server.crt" -days 825 -sha256 \
    -extfile "$ALT" -extensions v3_cert >/dev/null 2>&1

chmod 600 "$OUT/server.key" "$OUT/ca.key"
rm -f "$OUT/ca.srl"

echo "Generated:"
echo "  $OUT/ca.crt"
echo "  $OUT/server.crt"
echo "  $OUT/server.key"
echo "SANs: ${HOSTS[*]}"
