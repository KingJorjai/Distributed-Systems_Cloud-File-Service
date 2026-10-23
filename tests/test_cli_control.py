import contextlib
import io
import unittest

from cli_fich import _parse_options, _run_command


class FakeClient:
    def __init__(self):
        self.requests = []

    def request(self, message):
        self.requests.append(message)
        return {"ok": True, "data": {"action": message["action"]}}


class CliControlTests(unittest.TestCase):
    def test_parse_options(self):
        self.assertEqual(
            _parse_options(["--config", "x.toml", "--foreground", "status"]),
            ("x.toml", True, ["status"]),
        )

    def test_runs_share_command(self):
        client = FakeClient()
        with contextlib.redirect_stdout(io.StringIO()):
            _run_command(client, ["share", "docs", "bob", "ro"])

        self.assertEqual(
            client.requests[-1],
            {"action": "share", "path": "docs", "grantee": "bob", "access": "ro"},
        )

    def test_runs_pause_command(self):
        client = FakeClient()
        with contextlib.redirect_stdout(io.StringIO()):
            _run_command(client, ["pause"])

        self.assertEqual(client.requests[-1]["action"], "stop")


if __name__ == "__main__":
    unittest.main()
