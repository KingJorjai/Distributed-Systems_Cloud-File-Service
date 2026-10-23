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

    def test_stale_upload_creates_conflict_copy(self):
        self.store.put("alice", "a.txt", b"server")

        record, conflict = self.store.put_with_conflict(
            "alice", "a.txt", b"client", expected_rev=0, client_id="client-1"
        )

        self.assertEqual(record.rev, 2)
        self.assertIsNotNone(conflict)
        self.assertIn("conflict client-1", conflict.path)
        self.assertEqual(self.store.get("alice", conflict.path)[0], b"server")
        self.assertEqual(self.store.get("alice", "a.txt")[0], b"client")

    def test_stale_delete_creates_conflict_copy(self):
        self.store.put("alice", "a.txt", b"server")

        tombstone, conflict = self.store.delete_with_conflict(
            "alice", "a.txt", expected_rev=0, client_id="client-1"
        )

        self.assertTrue(tombstone.deleted)
        self.assertIsNotNone(conflict)
        self.assertEqual(self.store.get("alice", conflict.path)[0], b"server")
        with self.assertRaises(NotFoundError):
            self.store.get("alice", "a.txt")

    def test_delete_of_tombstone_has_no_conflict(self):
        self.store.put("alice", "a.txt", b"server")
        self.store.delete("alice", "a.txt")

        tombstone, conflict = self.store.delete_with_conflict(
            "alice", "a.txt", expected_rev=0, client_id="client-1"
        )

        self.assertTrue(tombstone.deleted)
        self.assertIsNone(conflict)

    def test_conflict_names_are_unique(self):
        self.store.put("alice", "a.txt", b"server")
        _, first = self.store.put_with_conflict(
            "alice", "a.txt", b"one", expected_rev=0, client_id="client-1"
        )
        self.store.put("alice", "a.txt", b"server-2")
        _, second = self.store.put_with_conflict(
            "alice", "a.txt", b"two", expected_rev=1, client_id="client-1"
        )

        self.assertNotEqual(first.path, second.path)

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

    def test_plan_put_does_not_change_state(self):
        self.store.create_user("carol", "password-carol")
        operations, record, conflict = self.store.plan_put_with_conflict(
            "carol", "a.txt", b"hello", expected_rev=0, client_id="client-1"
        )

        self.assertIsNone(self.store.stat("carol", "a.txt"))
        self.store.apply_operation({"operations": operations})
        self.assertEqual(self.store.stat("carol", "a.txt").rev, record.rev)
        self.assertIsNone(conflict)

    def test_apply_operation_uses_given_revision(self):
        self.store.create_user("carol", "password-carol")
        self.store.apply_operation(
            {
                "operations": [
                    {
                        "kind": "file",
                        "owner": "carol",
                        "path": "a.txt",
                        "rev": 7,
                        "hash": "abc",
                        "size": 3,
                        "mtime_ns": 123,
                        "deleted": False,
                        "data_b64": "YWJj",
                    }
                ]
            }
        )

        self.assertEqual(self.store.stat("carol", "a.txt").rev, 7)

    def test_state_hash_changes_on_mutation(self):
        self.store.create_user("carol", "password-carol")
        before = self.store.state_hash()
        operations, _, _ = self.store.plan_put_with_conflict(
            "carol", "a.txt", b"hello"
        )
        self.store.apply_operation({"operations": operations})

        self.assertNotEqual(self.store.state_hash(), before)

    def test_snapshot_round_trip(self):
        self.store.create_user("carol", "password-carol")
        self.store.put("alice", "a.txt", b"hello")
        self.store.create_share("alice", "a.txt", "bob", "ro")
        self.store.set_setting("registration_enabled", "false")
        snapshot = self.store.export_snapshot()

        with tempfile.TemporaryDirectory() as directory:
            restored = FileStore(Path(directory) / "files")
            self.addCleanup(restored.close)
            restored.import_snapshot(snapshot)

            self.assertEqual(restored.state_hash(), self.store.state_hash())
            self.assertEqual(restored.get("alice", "a.txt")[0], b"hello")
            self.assertEqual(restored.get_setting("registration_enabled"), "false")

    def test_settings_round_trip(self):
        self.assertIsNone(self.store.get_setting("registration_enabled"))
        self.store.set_setting("registration_enabled", "false")
        self.assertEqual(self.store.get_setting("registration_enabled"), "false")


if __name__ == "__main__":
    unittest.main()
