#!/usr/bin/env python3
"""Generate a local development CA and server certificate."""

import argparse
from pathlib import Path

import trustme


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("certs"))
    parser.add_argument("--host", action="append", default=None)
    args = parser.parse_args()

    hosts = args.host or ["localhost", "127.0.0.1"]
    args.output.mkdir(parents=True, exist_ok=True)

    ca = trustme.CA()
    certificate = ca.issue_cert(*hosts)

    ca.cert_pem.write_to_path(args.output / "ca.crt")
    certificate.cert_chain_pems[0].write_to_path(args.output / "server.crt")
    certificate.private_key_pem.write_to_path(args.output / "server.key")


if __name__ == "__main__":
    main()
