import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import ClientConfig
from sync_client import SyncWorker


class SyncCacheTests(unittest.TestCase):
    def test_unchanged_files_are_not_read_again(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "client"
            root.mkdir()
            (root / "a.txt").write_bytes(b"cached")
            worker = SyncWorker(
                str(root),
                ClientConfig(
                    server="localhost",
                    port=50012,
                    local_path=str(root),
                    state_dir=str(base / "state"),
                ),
                "alice",
                "password-alice",
            )
            self.addCleanup(worker.state.close)
            original = Path.read_bytes
            calls = []

            def counting(path):
                calls.append(path)
                return original(path)

            with patch("pathlib.Path.read_bytes", counting):
                first = worker._local_files()
                second = worker._local_files()

            self.assertEqual(first, second)
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
