"""Real private filesystem tests; no resident state or corpus is used."""

import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import siahistoryblock as blocks
from tests.test_history_block import digest


class HistoryBlockStore(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("siahistoryblockstore")
        self.temp = tempfile.TemporaryDirectory(prefix="sia-history-block-store-")
        self.addCleanup(self.temp.cleanup)
        self.directory = self.temp.name
        entry = {"source_returns": {}, "expected_source_returns_sha256": "a" * 64,
                 "event_batches": []}
        self.block = blocks.prepare(epoch_id="fixture", entry=entry,
                                    expected_entry_sha256=digest(entry),
                                    source_batch_sha256="b" * 64, observed_at=100,
                                    parent=None, expected_parent_sha256=None)

    def retain(self, block=None):
        value = self.block if block is None else block
        return self.api.retain(directory=self.directory, block=value,
                               expected_block_sha256=digest(value))

    def test_retain_read_and_idempotent_replay(self):
        receipt = self.retain()
        path = Path(self.directory, digest(self.block) + ".json")
        original = path.stat()
        self.assertEqual(receipt["status"], "retained-not-adopted")
        self.assertEqual(self.api.read(directory=self.directory,
                                      expected_block_sha256=digest(self.block)), self.block)
        self.assertEqual(self.retain(), receipt)
        self.assertEqual(path.stat().st_ino, original.st_ino)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_different_existing_bytes_are_not_replaced(self):
        path = Path(self.directory, digest(self.block) + ".json")
        path.write_bytes(b"different")
        path.chmod(0o600)
        with self.assertRaises(ValueError):
            self.retain()
        self.assertEqual(path.read_bytes(), b"different")

    def test_missing_parent_refuses_before_child_write(self):
        child = blocks.prepare(epoch_id="fixture", entry=self.block["entry"],
                               expected_entry_sha256=self.block["entry_sha256"],
                               source_batch_sha256="c" * 64, observed_at=101,
                               parent=self.block, expected_parent_sha256=digest(self.block))
        with self.assertRaises(ValueError):
            self.retain(child)
        self.assertFalse(Path(self.directory, digest(child) + ".json").exists())
        self.retain()
        self.retain(child)
        self.assertEqual(self.api.read(directory=self.directory,
                                      expected_block_sha256=digest(child)), child)

    def test_symlink_and_hardlink_targets_refuse(self):
        for kind in ("symbolic", "hard"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(dir=self.directory) as directory:
                outside = Path(directory, "original")
                outside.write_bytes(blocks._wire(self.block))
                outside.chmod(0o600)
                target = Path(directory, digest(self.block) + ".json")
                if kind == "symbolic":
                    target.symlink_to(outside)
                else:
                    os.link(outside, target)
                with self.assertRaises((ValueError, OSError)):
                    self.api.retain(directory=directory, block=self.block,
                                    expected_block_sha256=digest(self.block))
                self.assertEqual(outside.read_bytes(), blocks._wire(self.block))

    def test_crash_after_target_publish_recovers_exact_bytes(self):
        class Crash(BaseException):
            pass

        def crash(name):
            if name == "target-published":
                raise Crash()

        with mock.patch.object(self.api.queue, "_publish_boundary", side_effect=crash):
            with self.assertRaises(Crash):
                self.retain()
        self.assertEqual(self.retain()["block_sha256"], digest(self.block))

    def test_input_mutation_at_publish_refuses_without_adoption(self):
        pin = digest(self.block)

        def mutate(name):
            if name == "target-published":
                self.block["status"] = "published"

        with mock.patch.object(self.api.queue, "_publish_boundary", side_effect=mutate):
            with self.assertRaises(ValueError):
                self.api.retain(directory=self.directory, block=self.block,
                                expected_block_sha256=pin)
        self.assertEqual(self.api.read(directory=self.directory,
                                      expected_block_sha256=pin)["status"], "linked-not-published")

    def test_target_appearing_at_publication_is_not_overwritten(self):
        target = Path(self.directory, digest(self.block) + ".json")
        original = self.api.queue.fixed_atomic_publish

        def competing(*args, **kwargs):
            target.write_bytes(b"competing bytes")
            target.chmod(0o600)
            return original(*args, **kwargs)

        with mock.patch.object(self.api.queue, "fixed_atomic_publish", side_effect=competing):
            with self.assertRaises(ValueError):
                self.retain()
        self.assertEqual(target.read_bytes(), b"competing bytes")

    def test_public_or_symlink_directory_refuses(self):
        with tempfile.TemporaryDirectory(dir=self.directory) as directory:
            os.chmod(directory, 0o755)
            with self.assertRaises(ValueError):
                self.api.retain(directory=directory, block=self.block,
                                expected_block_sha256=digest(self.block))
            os.chmod(directory, 0o700)
            alias = Path(self.directory, "alias")
            alias.symlink_to(directory, target_is_directory=True)
            with self.assertRaises((ValueError, OSError)):
                self.api.retain(directory=str(alias), block=self.block,
                                expected_block_sha256=digest(self.block))
