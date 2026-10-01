"""Held publication directories remain owned by their callers."""

import os
from pathlib import Path
import sys
import tempfile
import unittest

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")
sys.path.insert(0, BIN)

import siaqueue


class FixedDestination(unittest.TestCase):
    def test_success_and_exact_retry_keep_the_callers_descriptor_open(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "destination"
            directory.mkdir(mode=0o700)
            descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                original = os.fstat(descriptor)
                target = directory / "page.md"
                self.assertEqual(siaqueue.fixed_atomic_publish(
                    target, b"derived page\n", exclusive=True,
                    destination_dir_fd=descriptor), "published")
                page = target.stat()
                self.assertEqual(siaqueue.fixed_atomic_publish(
                    target, b"derived page\n", exclusive=True,
                    destination_dir_fd=descriptor), "existing")
                current = target.stat()
                for field in ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns"):
                    self.assertEqual(getattr(current, field), getattr(page, field))
                self.assertEqual(os.fstat(descriptor).st_ino, original.st_ino)
                self.assertFalse(os.get_inheritable(descriptor))
            finally:
                os.close(descriptor)

    def test_mismatched_directory_refuses_before_staging_and_preserves_descriptor(self):
        with tempfile.TemporaryDirectory() as root:
            held = Path(root) / "held"
            named = Path(root) / "named"
            held.mkdir(mode=0o700)
            named.mkdir(mode=0o700)
            descriptor = os.open(held, os.O_RDONLY | os.O_DIRECTORY)
            stage = Path(root) / "stage"
            try:
                with self.assertRaises(ValueError):
                    siaqueue.fixed_atomic_publish(
                        named / "page.md", b"derived page\n", exclusive=True,
                        staging_dir=stage, destination_dir_fd=descriptor)
                self.assertFalse(stage.exists())
                self.assertEqual(list(named.iterdir()), [])
                self.assertEqual(os.fstat(descriptor).st_ino, held.stat().st_ino)
            finally:
                os.close(descriptor)

    def test_descriptor_kind_and_permissions_refuse_without_stage_effect(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "destination"
            directory.mkdir(mode=0o700)
            regular = Path(root) / "regular"
            regular.write_bytes(b"ordinary file\n")
            regular_fd = os.open(regular, os.O_RDONLY)
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            stage = Path(root) / "stage"
            try:
                for descriptor in (True, -1, regular_fd):
                    with self.subTest(descriptor=descriptor), self.assertRaises(ValueError):
                        siaqueue.fixed_atomic_publish(
                            directory / "page.md", b"derived page\n", exclusive=True,
                            staging_dir=stage, destination_dir_fd=descriptor)
                    self.assertFalse(stage.exists())
                directory.chmod(0o777)
                with self.assertRaises(ValueError):
                    siaqueue.fixed_atomic_publish(
                        directory / "page.md", b"derived page\n", exclusive=True,
                        staging_dir=stage, destination_dir_fd=directory_fd)
                self.assertFalse(stage.exists())
                self.assertEqual(os.fstat(regular_fd).st_ino, regular.stat().st_ino)
                self.assertEqual(os.fstat(directory_fd).st_ino, directory.stat().st_ino)
            finally:
                directory.chmod(0o700)
                os.close(directory_fd)
                os.close(regular_fd)
