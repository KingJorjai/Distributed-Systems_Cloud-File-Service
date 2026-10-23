import tempfile
import unittest
from pathlib import Path

from single_instance import AlreadyRunningError, InstanceLock


class InstanceLockTests(unittest.TestCase):
    def test_lock_is_exclusive_and_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.lock"
            first = InstanceLock(path)
            first.acquire()
            second = InstanceLock(path)
            with self.assertRaises(AlreadyRunningError):
                second.acquire()

            first.release()
            second.acquire()
            second.release()


if __name__ == "__main__":
    unittest.main()
