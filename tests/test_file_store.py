import os
import tempfile
import unittest
from pathlib import Path

from file_store import (
    AccessDeniedError,
    ConflictError,
    FileStore,
    InvalidPathError,
    NotFoundError,
    SelfShareError,
    ShareExistsError,
    UserExistsError,
)


class FileStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "files"
        self.store = FileStore(self.root)
        self.addCleanup(self.store.close)
        self.store.create_user("alice", "password-alice")
        self.store.create_user("bob", "password-bob")

    def test_creates_and_reads_file(self):
        record = self.store.put("alice", "docs/a.txt", b"hello")
        data, current = self.store.get("alice", "docs/a.txt")

        self.assertEqual(record.rev, 1)
        self.assertEqual(data, b"hello")
        self.assertEqual(current.digest, record.digest)

    def test_revision_increments(self):
        first = self.store.put("alice", "a.txt", b"one")
        second = self.store.put("alice", "a.txt", b"two")

        self.assertEqual(first.rev, 1)
        self.assertEqual(second.rev, 2)

    def test_revision_conflict(self):
        self.store.put("alice", "a.txt", b"one")

        with self.assertRaises(ConflictError):
            self.store.put("alice", "a.txt", b"two", expected_rev=0)

    def test_delete_creates_tombstone(self):
        self.store.put("alice", "a.txt", b"one")
        record = self.store.delete("alice", "a.txt")

        self.assertTrue(record.deleted)
        self.assertEqual(record.rev, 2)
        with self.assertRaises(NotFoundError):
            self.store.get("alice", "a.txt")
        manifest = self.store.manifest("alice")
        self.assertEqual(len(manifest), 1)
        self.assertTrue(manifest[0].deleted)

    def test_rejects_path_traversal(self):
        with self.assertRaises(InvalidPathError):
            self.store.put("alice", "../outside.txt", b"nope")
        with self.assertRaises(InvalidPathError):
            self.store.stat("alice", "/absolute.txt")

    def test_rejects_symlink_escape(self):
        outside = Path(self.directory.name) / "outside.txt"
        outside.write_bytes(b"secret")
        link = self.root / "alice" / "escape"
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available")

        with self.assertRaises(InvalidPathError):
            self.store.put("alice", "escape", b"nope")

    def test_manifest_includes_owned_and_shared(self):
        self.store.put("alice", "docs/a.txt", b"a")
        self.store.put("alice", "docs/b.txt", b"b")
        self.store.create_share("alice", "docs", "bob", "ro")

        entries = self.store.manifest("bob")

        self.assertEqual({entry.path for entry in entries}, {"docs/a.txt", "docs/b.txt"})
        self.assertTrue(all(entry.owner == "alice" for entry in entries))
        self.assertTrue(all(entry.access == "ro" for entry in entries))

    def test_owner_has_implicit_write_access(self):
        self.store.put("alice", "a.txt", b"a")

        self.assertEqual(self.store.access_for("alice", "alice", "a.txt", write=True), "rw")

    def test_read_only_share_cannot_write(self):
        self.store.put("alice", "a.txt", b"a")
        self.store.create_share("alice", "a.txt", "bob", "ro")

        self.assertEqual(self.store.access_for("bob", "alice", "a.txt"), "ro")
        with self.assertRaises(AccessDeniedError):
            self.store.access_for("bob", "alice", "a.txt", write=True)

    def test_self_share_is_rejected(self):
        self.store.put("alice", "a.txt", b"a")

        with self.assertRaises(SelfShareError):
            self.store.create_share("alice", "a.txt", "alice", "rw")

    def test_duplicate_share_is_rejected(self):
        self.store.put("alice", "a.txt", b"a")
        self.store.create_share("alice", "a.txt", "bob", "ro")

        with self.assertRaises(ShareExistsError):
            self.store.create_share("alice", "a.txt", "bob", "rw")

    def test_backfill_scans_existing_files(self):
        existing = self.root / "alice" / "legacy.txt"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_bytes(b"legacy")

        self.store.backfill()

        record = self.store.stat("alice", "legacy.txt")
        self.assertIsNotNone(record)
        self.assertEqual(record.rev, 1)

    def test_users_are_isolated(self):
        self.store.put("alice", "a.txt", b"a")

        self.assertIsNone(self.store.stat("bob", "a.txt"))

    def test_duplicate_user_is_rejected(self):
        with self.assertRaises(UserExistsError):
            self.store.create_user("alice", "another-password")

    def test_settings_round_trip(self):
        self.assertIsNone(self.store.get_setting("registration_enabled"))
        self.store.set_setting("registration_enabled", "false")
        self.assertEqual(self.store.get_setting("registration_enabled"), "false")


if __name__ == "__main__":
    unittest.main()
