"""Per-user subscription registry for server-to-client change notifications."""

import threading
from dataclasses import dataclass

import szasar


@dataclass
class Subscription:
    """One notification connection."""

    username: str
    client_id: str
    socket: object
    lock: threading.Lock

    def send(self, message):
        with self.lock:
            self.socket.sendall(message)


class NotificationHub:
    """Route file and share changes to connected users."""

    def __init__(self, store):
        self.store = store
        self._lock = threading.RLock()
        self._subscriptions = []

    def subscribe(self, username, client_id, socket):
        subscription = Subscription(
            username=username,
            client_id=client_id or "",
            socket=socket,
            lock=threading.Lock(),
        )
        with self._lock:
            self._subscriptions.append(subscription)
        return subscription

    def unsubscribe(self, subscription):
        with self._lock:
            if subscription in self._subscriptions:
                self._subscriptions.remove(subscription)

    def close(self):
        with self._lock:
            subscriptions = list(self._subscriptions)
            self._subscriptions.clear()
        for subscription in subscriptions:
            try:
                subscription.socket.close()
            except OSError:
                pass

    def publish_operation(self, operation, origin_client_id=None):
        for item in operation.get("operations", []):
            kind = item.get("kind")
            if kind == "file":
                self.publish_file(
                    item["owner"],
                    item["path"],
                    item.get("rev", 0),
                    item.get("hash", ""),
                    item.get("size", 0),
                    bool(item.get("deleted", False)),
                    origin_client_id,
                )
            elif kind == "share":
                self.publish_share(
                    item["owner"],
                    item["path"],
                    item["grantee"],
                    item["access"] if item.get("action") == "create" else "ro",
                    item.get("action") == "revoke",
                    origin_client_id,
                )

    def publish_file(
        self,
        owner,
        path,
        rev,
        digest,
        size,
        deleted,
        origin_client_id=None,
    ):
        recipients = {owner: "rw"}
        for share in self.store.list_shares(owner=owner):
            if path == share.path or path.startswith(share.path + "/"):
                current = recipients.get(share.grantee, "ro")
                recipients[share.grantee] = (
                    "rw" if share.access == "rw" or current == "rw" else "ro"
                )
        op = "D" if deleted else "U"
        self._broadcast_file(
            recipients,
            owner,
            path,
            rev,
            digest,
            size,
            op,
            origin_client_id,
        )

    def publish_share(
        self, owner, path, grantee, access, revoked, origin_client_id=None
    ):
        op = "R" if revoked else "S"
        message = "UPDT{}\t{}\t0\t\t0\t{}\t{}\t{}\r\n".format(
            owner,
            szasar.encode_path(path),
            op,
            access,
            origin_client_id or "",
        ).encode("ascii")
        with self._lock:
            subscriptions = list(self._subscriptions)
        for subscription in subscriptions:
            if subscription.username != grantee:
                continue
            if origin_client_id and subscription.client_id == origin_client_id:
                continue
            try:
                subscription.send(message)
            except OSError:
                self.unsubscribe(subscription)

    def _broadcast_file(
        self,
        recipients,
        owner,
        path,
        rev,
        digest,
        size,
        op,
        origin_client_id,
    ):
        with self._lock:
            subscriptions = list(self._subscriptions)
        for subscription in subscriptions:
            if subscription.username not in recipients:
                continue
            if origin_client_id and subscription.client_id == origin_client_id:
                continue
            message = "UPDT{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\r\n".format(
                owner,
                szasar.encode_path(path),
                rev,
                digest,
                size,
                op,
                recipients[subscription.username],
                origin_client_id or "",
            ).encode("ascii")
            try:
                subscription.send(message)
            except OSError:
                self.unsubscribe(subscription)
