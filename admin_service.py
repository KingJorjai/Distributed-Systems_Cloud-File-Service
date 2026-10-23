"""Administrative operations shared by the HTTPS admin panel."""

import threading
from datetime import datetime, timezone

from file_store import StoreError


class AdminError(Exception):
    """Raised when an administrative operation is rejected."""


class AdminService:
    """Validate admin requests and commit them through replication."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.store = runtime.store
        self._audit = []
        self._lock = threading.RLock()

    def _record(self, actor, action, target=""):
        with self._lock:
            self._audit.append(
                {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "actor": actor,
                    "action": action,
                    "target": target,
                }
            )
            self._audit = self._audit[-200:]

    def audit(self):
        with self._lock:
            return list(reversed(self._audit))

    def authenticate(self, username, password):
        try:
            user = self.store.authenticate(username, password)
        except StoreError as error:
            raise AdminError(str(error)) from error
        if user.role != "admin":
            raise AdminError("Administrator role required.")
        return user

    def is_admin(self, username):
        user = self.store.get_user(username)
        return user is not None and user.role == "admin" and not user.disabled

    def status(self):
        if hasattr(self.runtime, "admin_status"):
            return self.runtime.admin_status()
        cluster = self.runtime.cluster
        return {
            "server_id": self.runtime.config.server_id,
            "role": cluster.role,
            "term": self.runtime.log.term(),
            "primary": cluster.current_leader,
            "commit_index": self.runtime.log.commit_index(),
            "last_index": self.runtime.log.last_index(),
            "peers": [peer.server_id for peer in cluster.peers],
            "active_sessions": 0,
            "users": len(self.store.list_users()),
            "shares": len(self.store.list_shares()),
            "registration_enabled": self.store.registration_enabled(
                self.runtime.config.registration_enabled
            ),
            "is_primary": self.runtime.is_primary(),
        }

    def users(self):
        return [
            {
                "username": user.username,
                "role": user.role,
                "disabled": user.disabled,
            }
            for user in self.store.list_users()
        ]

    def create_user(self, username, password, actor="system"):
        try:
            operation = self.store.plan_user_create(username, password, "user")
            self.runtime.commit_operation({"operations": [operation]})
        except StoreError as error:
            raise AdminError(str(error)) from error
        self._record(actor, "create_user", username)
        return {"username": username, "role": "user", "disabled": False}

    def set_user_disabled(self, username, disabled, actor):
        user = self.store.get_user(username)
        if user is None:
            raise AdminError("User not found.")
        if disabled and username == actor:
            raise AdminError("You cannot disable your own account.")
        if disabled and user.role == "admin":
            enabled_admins = [
                item
                for item in self.store.list_users()
                if item.role == "admin" and not item.disabled
            ]
            if len(enabled_admins) <= 1:
                raise AdminError("The last enabled administrator cannot be disabled.")
        try:
            operation = self.store.plan_user_disabled(username, disabled)
            self.runtime.commit_operation({"operations": [operation]})
        except StoreError as error:
            raise AdminError(str(error)) from error
        if disabled:
            self.runtime.notification_hub.disconnect_user(username)
        self._record(actor, "disable_user" if disabled else "enable_user", username)
        return {"username": username, "disabled": bool(disabled)}

    def reset_password(self, username, password, actor):
        if self.store.get_user(username) is None:
            raise AdminError("User not found.")
        try:
            operation = self.store.plan_user_password(username, password)
            self.runtime.commit_operation({"operations": [operation]})
        except StoreError as error:
            raise AdminError(str(error)) from error
        self._record(actor, "reset_password", username)
        return {"username": username}

    def shares(self):
        return [
            {
                "owner": share.owner,
                "path": share.path,
                "grantee": share.grantee,
                "access": share.access,
            }
            for share in self.store.list_shares()
        ]

    def revoke_share(self, owner, path, grantee, actor):
        try:
            operation = self.store.plan_share_revoke(owner, path, grantee)
            self.runtime.commit_operation({"operations": [operation]})
        except StoreError as error:
            raise AdminError(str(error)) from error
        self._record(actor, "revoke_share", "{}:{}:{}".format(owner, path, grantee))
        return {"owner": owner, "path": path, "grantee": grantee}

    def set_registration(self, enabled, actor):
        operation = self.store.plan_setting(
            "registration_enabled", "true" if enabled else "false"
        )
        self.runtime.commit_operation({"operations": [operation]})
        self._record(
            actor, "registration_on" if enabled else "registration_off"
        )
        return {"registration_enabled": bool(enabled)}

    def step_down(self, actor):
        if not self.runtime.config.allow_admin_failover:
            raise AdminError("Step-down is disabled.")
        if not self.runtime.is_primary():
            raise AdminError("This node is not the primary.")
        self.runtime.cluster.step_down()
        self._record(actor, "step_down")
        return {"step_down": True}
