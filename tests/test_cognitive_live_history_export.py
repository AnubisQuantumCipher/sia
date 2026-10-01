"""Front-door export of retained live cognition history -- RED contract.

The signed-ledger cognitive capture does not contain controller uses,
deliveries, encoding observations, or the complete live policy.  This additive
private artifact must come from the same source-authorized generation used by
the live view, under the corpus owner.  It is experiment input, not a result or
cognitive claim.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import contextlib
import copy
import importlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from tests import test_calibration_benchmark as ledger_tests
from tests import test_live_view as live_view_tests


class CognitiveLiveHistoryExport(unittest.TestCase):
    def setUp(self):
        self.bench = ledger_tests.siabench
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self._state, self.corpus, self.registry = ledger_tests._signed_fixture(
            self.temp.name)

    @contextlib.contextmanager
    def completed_live(self):
        fixture = live_view_tests.SourceAuthorizedLiveView(methodName="runTest")
        with fixture.completed() as case:
            yield fixture, case

    def signed_bundle(self):
        return self.bench.build_ledger_dataset(
            corpus=self.corpus, chain_registry=self.registry,
            cognitive_history=True)

    def test_source_authorized_reader_returns_exact_detached_live_capture(self):
        module = importlib.import_module("sialiveview")
        self.assertTrue(callable(getattr(module, "read_history_capture", None)),
                        "missing source-authorized live-history reader")
        with self.completed_live() as (fixture, case), fixture.read_only(case):
            expected = copy.deepcopy(
                case.generation["transition"]["history_capture"])
            result = module.read_history_capture(case.lib.__dict__)
            self.assertEqual(result, expected)
            self.assertEqual(
                case.generation["transition"]["history_capture_sha256"],
                result["capture_sha256"])
            result["uses"].clear()
            self.assertEqual(
                module.read_history_capture(case.lib.__dict__), expected)

    def test_private_export_preserves_and_admits_both_history_captures(self):
        live_loop = importlib.import_module("sialiveloop")
        with self.completed_live() as (_fixture, case):
            live_capture = copy.deepcopy(
                case.generation["transition"]["history_capture"])
        bundle = self.signed_bundle()
        bundle["live_history"] = live_capture
        output = self.root / "joined"
        self.bench.write_dataset(bundle, str(output), corpus=self.corpus)
        artifact = output / "live-history.json"
        info = artifact.lstat()
        self.assertTrue(stat.S_ISREG(info.st_mode))
        self.assertEqual(info.st_uid, os.geteuid())
        self.assertEqual(info.st_nlink, 1)
        self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
        retained = json.loads(artifact.read_bytes())
        self.assertEqual(retained, live_capture)
        self.assertEqual(live_loop.admit_history_capture(
            retained, expected_capture_sha256=retained["capture_sha256"]),
            live_capture)
        self.assertTrue((output / "cognitive-history.json").is_file())

    def test_invalid_live_capture_refuses_before_publication(self):
        with self.completed_live() as (_fixture, case):
            live_capture = copy.deepcopy(
                case.generation["transition"]["history_capture"])
        live_capture["uses"].clear()
        bundle = self.signed_bundle()
        bundle["live_history"] = live_capture
        output = self.root / "invalid"
        with self.assertRaises(self.bench.BenchmarkRefusal):
            self.bench.write_dataset(bundle, str(output), corpus=self.corpus)
        self.assertFalse(output.exists() and any(output.iterdir()))

    def test_cli_captures_live_and_signed_history_inside_one_owner(self):
        module = importlib.import_module("sialiveview")
        with self.completed_live() as (_fixture, case):
            live_capture = copy.deepcopy(
                case.generation["transition"]["history_capture"])
        signed = self.signed_bundle()
        held = {"value": False}

        @contextlib.contextmanager
        def owner():
            self.assertFalse(held["value"])
            held["value"] = True
            try:
                yield
            finally:
                held["value"] = False

        def build(**kwargs):
            self.assertTrue(held["value"])
            self.assertIs(kwargs.get("cognitive_history"), True)
            return copy.deepcopy(signed)

        def capture(_owner):
            self.assertTrue(held["value"])
            return copy.deepcopy(live_capture)

        output = self.root / "cli"
        stdout = io.StringIO()
        with mock.patch.object(self.bench.sialib, "corpus_owner", side_effect=owner), \
                mock.patch.object(self.bench, "build_ledger_dataset", side_effect=build), \
                mock.patch.object(module, "read_history_capture", side_effect=capture), \
                contextlib.redirect_stdout(stdout):
            result = self.bench.main([
                "generate", "--cognitive-history", "--live-history",
                "--out", str(output)])
        self.assertEqual(result, 0)
        self.assertFalse(held["value"])
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["live_history"],
                         "live-history.json (mode 0600)")
        self.assertEqual(report["live_capture_sha256"],
                         live_capture["capture_sha256"])
        self.assertEqual(json.loads((output / "live-history.json").read_bytes()),
                         live_capture)

    def test_live_history_flag_requires_signed_cognitive_capture(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = self.bench.main([
                "generate", "--live-history", "--out", str(self.root / "bad")])
        self.assertEqual(result, 1)
        self.assertIn(
            "REFUSED: live history export requires --cognitive-history",
            stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
