"""Text publication can retain an admitted destination directory descriptor."""

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import sialib


class AtomicWriteDestination(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.directory = self.root / "destination"
        self.directory.mkdir(mode=0o700)
        self.descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.descriptor)
        self.identity = os.fstat(self.descriptor)
        for name in ("CORPUS", "STATE", "SHARE"):
            self.enterContext(mock.patch.object(sialib, name, str(self.root)))

    def assert_caller_open(self):
        current = os.fstat(self.descriptor)
        self.assertEqual((current.st_dev, current.st_ino),
                         (self.identity.st_dev, self.identity.st_ino))

    def test_bound_text_publication_preserves_caller_descriptor(self):
        target = self.directory / "memo.json"
        self.assertIsNone(sialib.atomic_write(
            target, '{"marker":"fenced"}', mode=0o600,
            destination_dir_fd=self.descriptor))
        self.assertEqual(target.read_text(), '{"marker":"fenced"}')
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assert_caller_open()

    def test_mismatched_named_parent_refuses_before_publication(self):
        named = self.root / "other"
        named.mkdir(mode=0o700)
        before = sorted(self.root.iterdir())
        with self.assertRaises(ValueError):
            sialib.atomic_write(named / "memo.json", "{}", mode=0o600,
                                destination_dir_fd=self.descriptor)
        self.assertEqual(sorted(self.root.iterdir()), before)
        self.assertEqual(list(named.iterdir()), [])
        self.assertEqual(list(self.directory.iterdir()), [])
        self.assert_caller_open()

    def test_parent_replacement_cannot_redirect_bound_publication(self):
        target = self.directory / "memo.json"
        moved = self.root / "admitted-directory"
        substituted = []

        def boundary(name):
            if name == "payload-fsynced":
                self.directory.rename(moved)
                self.directory.mkdir(mode=0o700)
                substituted.append(name)

        with mock.patch.object(sialib.siaqueue, "_publish_boundary",
                               side_effect=boundary):
            sialib.atomic_write(target, '{"pending":true}', mode=0o600,
                                destination_dir_fd=self.descriptor)
        self.assertEqual(substituted, ["payload-fsynced"])
        self.assertFalse(target.exists())
        self.assertEqual((moved / "memo.json").read_text(), '{"pending":true}')
        self.assert_caller_open()
        # The caller still owns named-path revalidation. This lower-level
        # primitive proves destination binding, not successful transaction ACK.

    def test_default_text_and_mode_contract_remains_unchanged(self):
        target = self.directory / "legacy.txt"
        target.write_text("old")
        target.chmod(0o640)
        self.assertIsNone(sialib.atomic_write(target, "new"))
        self.assertEqual(target.read_text(), "new")
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        with self.assertRaises(TypeError):
            sialib.atomic_write(target, b"not text")
        with self.assertRaises(ValueError):
            sialib.atomic_write(target, "new", mode=True)
        self.assertEqual(target.read_text(), "new")
        self.assert_caller_open()
