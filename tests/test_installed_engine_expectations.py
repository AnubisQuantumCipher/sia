"""Installed overlay selection observation for the future recall front door.

The fixture contains actual regular pin, managed-receipt, runtime-receipt and
ELF files.  Their bytes are fixture premises, not build provenance or a live
deployment claim.  This contract requires one closed, descriptor-checked
expectations observation before the existing installed-engine verifier may be
entered; it does not run gbrain, touch the index, or authorize cognition.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import copy
import importlib
import inspect
import os
from pathlib import Path
import subprocess
import time
import unittest
from unittest import mock

from tests import test_installed_engine_boundary as boundary_tests
from tests import test_controller_source_engine_generation as engine_tests


RESULT_KEYS = {
    "schema", "status", "expectations", "expected_expectations_sha256",
    "non_claims", "observation_sha256",
}


class InstalledEngineExpectations(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("siainstalledexpectations")
        except ModuleNotFoundError as error:
            if error.name != "siainstalledexpectations":
                raise
            self.fail("missing installed-engine expectations observer")
        self.observe = getattr(
            self.module, "observe_installed_expectations", None)
        self.assertTrue(callable(self.observe),
                        "missing installed-engine expectations API")
        self.fixture = boundary_tests.InstalledEngineBoundary(
            methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.core = self.fixture.core

    def call(self):
        with self.core.corpus_owner():
            return self.observe(self.core.__dict__)

    def test_exact_api_and_closed_observation_match_independent_fixture(self):
        parameters = inspect.signature(self.observe).parameters
        self.assertEqual(tuple(parameters), ("owner",))
        self.assertEqual(
            parameters["owner"].kind, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        expected = copy.deepcopy(self.fixture.expectations)
        result = self.call()
        self.assertEqual(set(result), RESULT_KEYS)
        self.assertEqual(result["schema"],
                         "sia-installed-overlay-engine-expectations-observation-v1")
        self.assertEqual(result["status"], "observed-local-install-selection")
        self.assertEqual(result["expectations"], expected)
        self.assertEqual(
            result["expected_expectations_sha256"],
            engine_tests._digest(expected))
        self.assertEqual(
            result["observation_sha256"],
            engine_tests._digest({key: value for key, value in result.items()
                                  if key != "observation_sha256"}))
        prose = " ".join(result["non_claims"]).lower()
        for term in ("local", "selection", "receipt", "hostile same-user",
                     "engine", "output", "cognition", "held-out"):
            self.assertIn(term, prose)

    def test_observer_has_no_process_network_clock_or_index_boundary(self):
        observed_paths = (
            self.fixture.fixture.pin,
            self.fixture.fixture.pin_receipt,
            self.fixture.fixture.release_receipt,
            self.fixture.fixture.engine_bin,
        )
        before = {
            str(path): (path.read_bytes(), tuple(getattr(path.stat(), field)
                                                for field in (
                                                    "st_dev", "st_ino", "st_mode",
                                                    "st_size", "st_mtime_ns", "st_ctime_ns")))
            for path in observed_paths
        }
        with mock.patch.object(
                self.core, "_run_bounded_text_process",
                side_effect=AssertionError("process execution")), \
                mock.patch.object(subprocess, "run",
                                  side_effect=AssertionError("process execution")), \
                mock.patch.object(time, "time",
                                  side_effect=AssertionError("clock read")):
            result = self.call()
        self.assertEqual(result["expectations"], self.fixture.expectations)
        after = {
            str(path): (path.read_bytes(), tuple(getattr(path.stat(), field)
                                                for field in (
                                                    "st_dev", "st_ino", "st_mode",
                                                    "st_size", "st_mtime_ns", "st_ctime_ns")))
            for path in observed_paths
        }
        self.assertEqual(after, before)
        self.assertEqual(
            list(self.fixture.fixture.state.glob("sia-installed-projection-*")), [])

    def test_missing_overlay_selection_refuses_even_with_matching_local_receipts(self):
        pin = self.fixture.fixture.pin
        pin_receipt = self.fixture.fixture.pin_receipt
        runtime_receipt = self.fixture.fixture.release_receipt
        pin_text = "\n".join(
            line for line in pin.read_text(encoding="utf-8").splitlines()
            if not line.startswith(("overlay_sha256=", "overlay_tree_oid="))) + "\n"
        pin.write_text(pin_text, encoding="utf-8")
        pin_receipt.write_text(
            "managed-by=khephri.sia\nkind=gbrain-pin\npath=" + str(pin)
            + "\nsha256=" + boundary_tests.sha(pin.read_bytes()) + "\n",
            encoding="utf-8")
        runtime_receipt.write_text(
            "managed-by=khephri.sia\ncommit=" + engine_tests.PINNED_COMMIT
            + "\nversion=" + engine_tests.VERSION
            + "\nbun_lock_sha256=" + engine_tests.LOCK_SHA256
            + "\nbinary_sha256="
            + boundary_tests.sha(self.fixture.fixture.engine_bin.read_bytes())
            + "\n", encoding="utf-8")
        with self.assertRaises(self.module.InstalledExpectationsRefusal):
            self.call()

    def test_receipt_or_executable_disagreement_refuses_wholly(self):
        changes = (
            (self.fixture.fixture.pin_receipt, b"changed managed receipt\n"),
            (self.fixture.fixture.release_receipt, b"changed runtime receipt\n"),
            (self.fixture.fixture.engine_bin, b"\x7fELFchanged executable"),
        )
        for path, replacement in changes:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(replacement)
                try:
                    with self.assertRaises(
                            self.module.InstalledExpectationsRefusal):
                        self.call()
                finally:
                    path.write_bytes(original)

    def test_return_is_detached_and_owner_or_result_shape_cannot_self_authorize(self):
        result = self.call()
        changed = copy.deepcopy(result)
        changed["expectations"]["overlay_sha256"] = "0" * 64
        self.assertNotEqual(changed, result)
        self.assertEqual(result["expectations"], self.fixture.expectations)
        with self.assertRaises(self.module.InstalledExpectationsRefusal):
            self.observe(None)
        wrong_owner = dict(self.core.__dict__)
        wrong_owner["GBRAIN"] = str(Path(self.core.GBRAIN).with_name("foreign"))
        with self.assertRaises(self.module.InstalledExpectationsRefusal):
            with self.core.corpus_owner():
                self.observe(wrong_owner)


if __name__ == "__main__":
    unittest.main(verbosity=2)
