"""Retain actual compact capture entries without changing source authority."""

import copy
import hashlib
import tempfile
import unittest

import siahistoryblock as blocks
import siahistoryblockstore as store
from tests import test_checkpoint_liveinput as fixtures


class CheckpointHistoryRetention(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(getattr(blocks, "prepare_checkpoint_capture", None)),
                        "missing compact capture history-block extraction")
        self.case = fixtures.CheckpointLiveInput(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def pin(self, value):
        return hashlib.sha256(blocks._wire(value)).hexdigest()

    def test_actual_capture_retains_exact_link_and_retries_without_ack(self):
        with self.case.captured(nonidle=True) as (f, owner, batch), tempfile.TemporaryDirectory(prefix="sia-checkpoint-chain-") as directory:
            before = copy.deepcopy(f.case.live.memo)
            parent = blocks.prepare_captured(owner, batch=f.retained,
                expected_batch_sha256=f.retained["batch_sha256"], parent=None, expected_parent_sha256=None)
            store.retain(directory=directory, block=parent, expected_block_sha256=self.pin(parent))
            block = blocks.prepare_checkpoint_capture(owner, batch=batch,
                expected_batch_sha256=batch["batch_sha256"], parent=parent, expected_parent_sha256=self.pin(parent))
            self.assertEqual(block["entry"]["source_returns"], batch["source_returns"])
            self.assertEqual([row["batch"] for row in block["entry"]["event_batches"]], batch["event_closure"]["batches"])
            self.assertEqual(block["parent_sha256"], self.pin(parent))
            self.assertNotIn("history", block)
            receipt = store.retain(directory=directory, block=block, expected_block_sha256=self.pin(block))
            self.assertEqual(receipt["status"], "retained-not-adopted")
            self.assertEqual(store.retain(directory=directory, block=block, expected_block_sha256=self.pin(block)), receipt)
            self.assertEqual(store.read(directory=directory, expected_block_sha256=self.pin(block)), block)
            self.assertEqual(store.read(directory=directory, expected_block_sha256=self.pin(parent)), parent)
            self.assertEqual(f.case.live.memo, before)
            changed = copy.deepcopy(parent)
            changed["source_batch_sha256"] = "f" * 64
            with self.assertRaises(ValueError):
                blocks.prepare_checkpoint_capture(owner, batch=batch,
                    expected_batch_sha256=batch["batch_sha256"], parent=changed, expected_parent_sha256=self.pin(changed))
            with self.assertRaises(ValueError):
                blocks.prepare_checkpoint_capture(owner, batch=batch,
                    expected_batch_sha256=batch["batch_sha256"], parent=None, expected_parent_sha256=None)
