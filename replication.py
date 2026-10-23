"""Cluster membership, durable replication log, and replication transports."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Peer:
    """One remote server in the replication cluster."""

    server_id: str
    host: str
    port: int


def parse_peers(value):
    """Parse ``id@host:port,...`` into a tuple of :class:`Peer`."""
    peers = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            server_id, address = item.split("@", 1)
            host, port = address.rsplit(":", 1)
            peers.append(Peer(server_id, host, int(port)))
        except (ValueError, TypeError) as error:
            raise ValueError("Invalid peer specification: {}".format(item)) from error
    return tuple(peers)
