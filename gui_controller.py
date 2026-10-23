"""GUI-facing controller for the synchronization daemon."""

import queue
import threading
from pathlib import Path

from config import ClientConfig, default_config_path, load_config, save_client_config
from daemon_client import connect, ensure_daemon


class GuiController:
    """Translate GUI actions into daemon IPC requests."""

    def __init__(self, config_path=None):
        self.config_path = Path(config_path or default_config_path())
        self.events = queue.Queue()
        self.client = None
        self.subscriber = None
        self._subscriber_thread = None
        self._stop = threading.Event()

    def start_daemon(self):
        if self.client is None:
            self.client = ensure_daemon(self.config_path)
        return self.client

    def _request(self, action, **data):
        if self.client is None:
            self.start_daemon()
        message = {"action": action}
        message.update(data)
        response = self.client.request(message)
        if not response.get("ok"):
            raise RuntimeError(response.get("message", response.get("error", "error")))
        return response.get("data")

    def status(self):
        return self._request("status")

    def login(self, username, password):
        return self._request("login", username=username, password=password)

    def register(self, username, password):
        return self._request("register", username=username, password=password)

    def logout(self):
        return self._request("logout")

    def start_sync(self):
        return self._request("start")

    def stop_sync(self):
        return self._request("stop")

    def shares(self):
        return self._request("shares")

    def users(self):
        return self._request("users")

    def share(self, path, grantee, access):
        return self._request(
            "share", path=path, grantee=grantee, access=access
        )

    def unshare(self, path, grantee):
        return self._request("unshare", path=path, grantee=grantee)

    def change_password(self, old_password, new_password):
        return self._request(
            "password", old_password=old_password, new_password=new_password
        )

    def save_settings(self, **values):
        current = load_config(self.config_path).client
        updated = ClientConfig(
            server=values.get("server", current.server),
            port=int(values.get("port", current.port)),
            local_path=values.get("local_path", current.local_path),
            tls_ca_file=values.get("tls_ca_file", current.tls_ca_file),
            tls_server_name=values.get("tls_server_name", current.tls_server_name),
            state_dir=values.get("state_dir", current.state_dir),
            peers=values.get("peers", current.peers),
        )
        save_client_config(self.config_path, updated)
        if self.client is not None:
            self._request("reload")
        return updated

    def subscribe(self):
        if self._subscriber_thread is not None:
            return
        self._subscriber_thread = threading.Thread(
            target=self._subscribe_loop, name="gui-events", daemon=True
        )
        self._subscriber_thread.start()

    def _subscribe_loop(self):
        while not self._stop.is_set():
            subscriber = None
            try:
                subscriber = connect(self.config_path, timeout=5)
                self.subscriber = subscriber
                subscriber.send({"action": "subscribe"})
                while not self._stop.is_set():
                    if not subscriber.connection.poll(1):
                        continue
                    message = subscriber.recv()
                    if message.get("ok") and "data" in message:
                        self.events.put(("status", message["data"]))
                    elif "event" in message:
                        self.events.put((message["event"], message.get("data")))
            except Exception:
                if not self._stop.is_set():
                    self.events.put(("disconnected", None))
                    threading.Event().wait(1)
            finally:
                if subscriber is not None:
                    subscriber.close()
                self.subscriber = None

    def poll_events(self):
        drained = []
        while True:
            try:
                drained.append(self.events.get_nowait())
            except queue.Empty:
                return drained

    def shutdown(self):
        try:
            self._request("shutdown")
        except Exception:
            pass
        self.close()

    def close(self):
        self._stop.set()
        if self.client is not None:
            self.client.close()
            self.client = None
        if self.subscriber is not None:
            self.subscriber.close()
            self.subscriber = None
