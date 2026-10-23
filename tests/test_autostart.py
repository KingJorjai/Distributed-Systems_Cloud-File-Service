import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import autostart


class AutostartTests(unittest.TestCase):
    def test_linux_desktop_entry_round_trip(self):
        if os.name == "nt" or os.uname().sysname == "Darwin":
            self.skipTest("Linux-specific test")
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
                self.assertFalse(autostart.is_enabled())
                autostart.enable()
                path = Path(directory) / "autostart" / "cloud-file-service.desktop"
                self.assertTrue(path.is_file())
                self.assertIn("--minimized", path.read_text())
                self.assertTrue(autostart.is_enabled())
                autostart.disable()
                self.assertFalse(autostart.is_enabled())


if __name__ == "__main__":
    unittest.main()
