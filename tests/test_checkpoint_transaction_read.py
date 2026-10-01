"""Recover retained package meaning without reacquiring source observations."""

import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

import siacheckpointtransaction as api
from tests import test_checkpoint_transaction as fixtures


class CheckpointTransactionRead(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(getattr(api, "read_prepared", None)), "missing prepared package reader")
        self.case = fixtures.CheckpointTransaction(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_real_package_replays_without_collection_and_resealed_candidate_refuses(self):
        prepare = api.prepare_root

        def inspect(owner, **kwargs):
            result = prepare(owner, **kwargs)
            before = copy.deepcopy(kwargs["memo"])
            request = dict(directory=kwargs["directory"], expected_manifest_sha256=result["manifest_sha256"],
                           expected_root_sha256=kwargs["expected_root_sha256"])
            with mock.patch.object(api.checkpoint, "capture_root_delivery", side_effect=AssertionError("reader collected sources")), \
                    mock.patch.object(api.ack, "read_completed", side_effect=AssertionError("reader claimed authority")), \
                    mock.patch.object(api.queue, "fixed_atomic_publish", side_effect=AssertionError("reader published")):
                view = api.read_prepared(owner, **request)
                self.assertEqual(view["status"], "verified-retained-not-authorized")
                self.assertEqual(view["manifest"], result["manifest"])
                self.assertEqual(view["artifacts"]["capture"]["batch_sha256"], result["manifest"]["source_batch_sha256"])
                self.assertEqual(kwargs["memo"], before)
                with self.assertRaises(ValueError):
                    api.read_prepared(owner, **{**request, "expected_root_sha256": "f" * 64})
                candidate_path = Path(kwargs["directory"]) / ("candidate-" + result["manifest"]["artifacts"]["candidate"] + ".json")
                original_raw = candidate_path.read_bytes()
                pulse = api.live.prepare_pulse

                def rebind(**arguments):
                    transition = pulse(**arguments)
                    candidate_path.write_bytes(original_raw + b" ")
                    return transition

                try:
                    with mock.patch.object(api.live, "prepare_pulse", side_effect=rebind):
                        with self.assertRaises(ValueError):
                            api.read_prepared(owner, **request)
                finally:
                    candidate_path.write_bytes(original_raw)
                candidate = copy.deepcopy(view["artifacts"]["candidate"])
                candidate["expected_prepare_inputs_sha256"] = "f" * 64
                raw = api.checkpoint._wire(owner, candidate)
                pin = hashlib.sha256(raw).hexdigest()
                directory = Path(kwargs["directory"])
                path = directory / ("candidate-" + pin + ".json")
                path.write_bytes(raw)
                path.chmod(0o600)
                manifest = copy.deepcopy(result["manifest"])
                manifest["artifacts"]["candidate"] = pin
                raw = api.checkpoint._wire(owner, manifest)
                manifest_pin = hashlib.sha256(raw).hexdigest()
                path = directory / ("transaction-" + manifest_pin + ".json")
                path.write_bytes(raw)
                path.chmod(0o600)
                with self.assertRaises(ValueError):
                    api.read_prepared(owner, **{**request, "expected_manifest_sha256": manifest_pin})
            return result

        with mock.patch.object(api, "prepare_root", side_effect=inspect):
            self.case.exercise()
