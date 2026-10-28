import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from config import _read_toml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "demo_lan_config.py"


class DemoLanConfigTests(unittest.TestCase):
    def run_generator(self, directory, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def test_generates_flexible_layout_with_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_generator(
                directory,
                "--server",
                "server1@10.0.0.101:50012:60012:50080",
                "--server",
                "server2@10.0.0.102:50012:60012:50080",
                "--server",
                "server3@10.0.0.103:50012:60012:50080",
                "--server",
                "server4@10.0.0.104:50012:60012:50080",
                "--client",
                "alice@10.0.0.111",
                "--client",
                "bob@10.0.0.112",
                "--client",
                "carol@10.0.0.113",
                "--output",
                directory,
                "--no-certs",
                "--token",
                "test-token",
                "--admin-password",
                "test-admin",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            server = _read_toml(Path(directory) / "server-server1" / "config.toml")
            self.assertEqual(server["server"]["role"], "primary")
            self.assertIn("server2@10.0.0.102:60012", server["server"]["peers"])
            self.assertIn("server3@10.0.0.103:60012", server["server"]["peers"])
            self.assertIn("server4@10.0.0.104:60012", server["server"]["peers"])
            self.assertEqual(
                server["server"]["admin_addresses"],
                "server1@10.0.0.101:50080,server2@10.0.0.102:50080,"
                "server3@10.0.0.103:50080,server4@10.0.0.104:50080",
            )
            secondary = _read_toml(
                Path(directory) / "server-server2" / "config.toml"
            )
            self.assertEqual(secondary["server"]["role"], "secondary")
            self.assertEqual(
                secondary["server"]["primary"],
                "server1@10.0.0.101:60012",
            )
            client = _read_toml(Path(directory) / "client-alice" / "config.toml")
            self.assertEqual(client["client"]["local_path"], "client_files")
            self.assertEqual(client["client"]["state_dir"], "state")
            self.assertEqual(
                client["client"]["peers"],
                "10.0.0.101:50012,10.0.0.102:50012,"
                "10.0.0.103:50012,10.0.0.104:50012",
            )
            self.assertTrue((Path(directory) / "RUNBOOK.md").is_file())
            self.assertTrue((Path(directory) / "demo-accounts.txt").is_file())
            self.assertTrue((Path(directory) / "server-server1" / "run-server.sh").is_file())
            self.assertTrue((Path(directory) / "client-alice" / "run-client.sh").is_file())
            self.assertTrue(
                (Path(directory) / "client-alice" / "run-client-cli.sh").is_file()
            )

    def test_rejects_duplicate_addresses(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_generator(
                directory,
                "--server",
                "server1@10.0.0.101",
                "--server",
                "server2@10.0.0.101",
                "--client",
                "alice@10.0.0.111",
                "--output",
                directory,
                "--no-certs",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Duplicate client address", result.stderr)

    def test_single_server_is_standalone(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_generator(
                directory,
                "--server",
                "server1@10.0.0.101",
                "--client",
                "alice@10.0.0.111",
                "--output",
                directory,
                "--no-certs",
                "--token",
                "test-token",
                "--admin-password",
                "test-admin",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            config = _read_toml(Path(directory) / "server-server1" / "config.toml")
            self.assertEqual(config["server"]["peers"], "")
            self.assertEqual(config["server"]["role"], "primary")
            self.assertIn("Quorum for **1**", (Path(directory) / "RUNBOOK.md").read_text())


if __name__ == "__main__":
    unittest.main()
