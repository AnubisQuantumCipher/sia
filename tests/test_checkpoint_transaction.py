"""Actual root capture prepares durable artifacts without adopting authority."""

import copy
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import siahistoryroot as roots
import siasourcecheckpoint as checkpoint
from tests import test_checkpoint_delivery_capture as fixtures


class CheckpointTransaction(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("siacheckpointtransaction")
        self.case = fixtures.CheckpointDeliveryCapture(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def invoke(self, f, owner, directory, root):
        return self.api.prepare_root(vars(owner), memo=f.case.live.memo,
            admitted_status=f.status, directory=directory, expected_root_sha256=root["root_sha256"],
            observed_at=f.request["observed_at"], journal_limits=f.request["journal_limits"],
            expected_journal_limits_sha256=f.request["expected_journal_limits_sha256"],
            expected_adoption_sha256=f.request["expected_adoption_sha256"])

    def test_actual_capture_retains_complete_package_before_manifest(self):
        self.exercise()

    def test_manifest_interruption_does_not_adopt_retained_members(self):
        self.exercise(interrupt=True)

    def exercise(self, *, interrupt=False, fenced=False):
        fixture = self.case.case
        with fixture.prepared(nonidle=not fenced) as f, tempfile.TemporaryDirectory(prefix="sia-checkpoint-transaction-") as directory:
            root = roots.prepare(vars(f.case.lib), memo=f.case.live.memo, admitted_status=f.status, directory=directory)
            if fenced:
                f.case.lib._mark_notify_baseline_attempt(f.case.live.memo)
            before = copy.deepcopy(f.case.live.memo)
            with fixture.capture_owner(f) as owner:
                owner._load_live_publication()
                actual_publish = self.api.queue.fixed_atomic_publish
                attempts = []

                def publish(path, raw, **kwargs):
                    if Path(path).name.startswith("transaction-"):
                        value = json.loads(raw)
                        for name, pin in value["artifacts"].items():
                            stored = Path(directory) / (("" if name == "block" else name + "-") + pin + ".json")
                            self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), pin)
                        attempts.append({"manifest": value, "manifest_sha256": hashlib.sha256(raw).hexdigest()})
                        self.assertEqual(f.case.live.memo, before)
                        if interrupt:
                            raise OSError("controlled manifest interruption")
                    return actual_publish(path, raw, **kwargs)

                with mock.patch.object(self.api.queue, "fixed_atomic_publish", side_effect=publish):
                    if interrupt:
                        with self.assertRaisesRegex(OSError, "controlled manifest interruption"):
                            self.invoke(f, owner, directory, root)
                        result = attempts[0]
                    else:
                        result = self.invoke(f, owner, directory, root)
                self.assertEqual(attempts, [result])
                manifest = result["manifest"]
                self.assertEqual(manifest["status"], "retained-not-activated")
                artifacts = {}
                for name, pin in manifest["artifacts"].items():
                    raw = (Path(directory) / (("" if name == "block" else name + "-") + pin + ".json")).read_bytes()
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), pin)
                    artifacts[name] = json.loads(raw)
                checkpoint.validate_capture(vars(owner), artifacts["capture"], manifest["source_batch_sha256"])
                self.assertEqual(artifacts["checkpoint"], artifacts["capture"]["intake_projection"]["checkpoint"])
                self.assertEqual(artifacts["candidate"]["prepare_inputs"]["intake"], artifacts["checkpoint"]["intake"])
                self.assertEqual(artifacts["block"]["source_batch_sha256"], manifest["source_batch_sha256"])
                self.assertEqual(manifest["predecessor"], f.committed)
                path = Path(directory) / ("transaction-" + result["manifest_sha256"] + ".json")
                if interrupt:
                    self.assertFalse(path.exists())
                else:
                    raw = path.read_bytes()
                    self.assertEqual(json.loads(raw), manifest)
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), result["manifest_sha256"])
            self.assertEqual(f.case.live.memo, before)
            self.assertFalse((Path(directory) / "head.json").exists())

    def test_replaced_retained_capture_refuses_before_manifest(self):
        fixture = self.case.case
        with fixture.prepared(nonidle=True) as f, tempfile.TemporaryDirectory(prefix="sia-checkpoint-rebind-") as directory:
            root = roots.prepare(vars(f.case.lib), memo=f.case.live.memo, admitted_status=f.status, directory=directory)
            before = copy.deepcopy(f.case.live.memo)
            with fixture.capture_owner(f) as owner:
                owner._load_live_publication()
                actual_publish = self.api.queue.fixed_atomic_publish
                captured = []

                def publish(path, raw, **kwargs):
                    result = actual_publish(path, raw, **kwargs)
                    if Path(path).name.startswith("capture-"):
                        captured.append(Path(path))
                    if Path(path).name.startswith("candidate-"):
                        self.assertTrue(captured)
                        captured[0].write_bytes(captured[0].read_bytes() + b" ")
                    return result

                with mock.patch.object(self.api.queue, "fixed_atomic_publish", side_effect=publish):
                    with self.assertRaises(ValueError):
                        self.invoke(f, owner, directory, root)
                self.assertTrue(captured)
            self.assertEqual(f.case.live.memo, before)
            self.assertEqual(list(Path(directory).glob("transaction-*.json")), [])
