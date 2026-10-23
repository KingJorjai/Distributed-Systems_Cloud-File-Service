import tempfile
import unittest
from pathlib import Path

from config import ClientConfig, load_config, save_client_config
from gui_controller import GuiController


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def request(self, message):
        self.requests.append(message)
        return self.responses.get(message["action"], {"ok": False, "message": "no"})

    def close(self):
        pass


class GuiControllerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "config.toml"
        save_client_config(
            self.path,
            ClientConfig(
                server="old",
                port=50012,
                local_path="old-files",
                state_dir=str(Path(self.directory.name) / "state"),
            ),
        )
        self.controller = GuiController(self.path)
        self.addCleanup(self.controller.close)

    def test_save_settings_preserves_and_updates(self):
        updated = self.controller.save_settings(
            server="new", port=60012, local_path="new-files"
        )
        restored = load_config(self.path).client

        self.assertEqual(updated.server, "new")
        self.assertEqual(restored.server, "new")
        self.assertEqual(restored.port, 60012)
        self.assertEqual(restored.local_path, "new-files")

    def test_request_uses_actions(self):
        self.controller.client = FakeClient(
            {
                "status": {"ok": True, "data": {"running": True}},
                "login": {"ok": True, "data": {"logged_in": True}},
            }
        )
        self.assertEqual(self.controller.status(), {"running": True})
        self.assertEqual(
            self.controller.login("alice", "password"), {"logged_in": True}
        )

    def test_poll_events(self):
        self.controller.events.put(("status", {"running": True}))
        self.controller.events.put(("worker", {"event": "upload"}))
        self.assertEqual(
            self.controller.poll_events(),
            [("status", {"running": True}), ("worker", {"event": "upload"})],
        )
        self.assertEqual(self.controller.poll_events(), [])


if __name__ == "__main__":
    unittest.main()
