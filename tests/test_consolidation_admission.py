"""Journal-prefix exception tests; not a power-loss or resident campaign."""
import importlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from tests import test_epoch_exemplar_coverage as fixture_module


class ConsolidationAdmission(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.EpochExemplarCoverage(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.lib.CORPUS_OWNER_LOCK = str(Path(self.lib.STATE) / "corpus-owner.lock")
        self.admission = importlib.import_module("siaconsolidationadmission")
        self.fixture._day("2026-01-05", ("OBS",))
        self.fixture._commit()
        commit = subprocess.check_output(
            ["git", "-C", self.lib.CORPUS, "rev-parse", "HEAD"],
            text=True, timeout=10).strip()
        self.request = {"generation": "a" * 32, "transaction": "b" * 64,
                        "cutoff": "2026-10-06", "commit": commit}
        self.journal = Path(self.lib.STATE) / "consolidation-snapshot-admission.json"
        self.ref = "refs/sia/consolidation/" + self.request["generation"]

    def cut_and_resume(self, cut, expected_phase):
        def fail(stage):
            if stage == cut:
                raise RuntimeError("injected admission cut")

        with mock.patch.object(self.admission, "_boundary", fail):
            with self.assertRaisesRegex(RuntimeError, "injected admission cut"):
                self.admission.admit(self.lib, **self.request)
        retained = json.loads(self.journal.read_text())
        self.assertEqual(retained["phase"], expected_phase)
        for key, value in self.request.items():
            self.assertEqual(retained[key], value)
        recovered = self.admission.admit(self.lib, **self.request)
        self.assertEqual(recovered, dict(retained, phase="admitted"))
        original = self.journal.read_bytes()
        self.assertEqual(self.admission.admit(self.lib, **self.request), recovered)
        self.assertEqual(self.journal.read_bytes(), original)

    def test_resume_after_plan(self):
        self.cut_and_resume("planned-persisted", "planned")

    def test_resume_after_pin(self):
        self.cut_and_resume("pin-retained", "planned")

    def test_resume_after_admission(self):
        self.cut_and_resume("admission-persisted", "admitted")

    def test_missing_admitted_pin_is_not_recreated(self):
        self.admission.admit(self.lib, **self.request)
        before = self.journal.read_bytes()
        subprocess.run(["git", "-C", self.lib.CORPUS, "update-ref", "-d",
                        self.ref, self.request["commit"]], check=True, timeout=10)
        with self.assertRaisesRegex(ValueError, "missing or differs"):
            self.admission.admit(self.lib, **self.request)
        self.assertEqual(self.journal.read_bytes(), before)
        absent = subprocess.run(["git", "-C", self.lib.CORPUS, "rev-parse",
                                 "--verify", "--quiet", self.ref],
                                capture_output=True, timeout=10)
        self.assertEqual(absent.returncode, 1)

    def test_conflicting_request_preserves_journal_and_pin(self):
        self.admission.admit(self.lib, **self.request)
        before = self.journal.read_bytes()
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.admission.admit(self.lib, **dict(self.request, transaction="c" * 64))
        self.assertEqual(self.journal.read_bytes(), before)
        self.assertEqual(self.admission.admit(
            self.lib, **self.request)["phase"], "admitted")

    def test_malformed_retained_state_is_not_repaired(self):
        record = self.admission.admit(self.lib, **self.request)
        variants = [
            dict(record, phase=[]), dict(record, phase="complete"),
            dict(record, generation="HEAD"), dict(record, commit="HEAD"),
            dict(record, cutoff="2026-02-30"), dict(record, extra=True),
        ]
        for value in variants:
            with self.subTest(value=value):
                self.lib.atomic_write(str(self.journal), json.dumps(value))
                before = self.journal.read_bytes()
                with self.assertRaises(ValueError):
                    self.admission.admit(self.lib, **self.request)
                self.assertEqual(self.journal.read_bytes(), before)
                pin = self.admission.snapshot.check_pin(
                    self.lib._run_bounded_text_process, self.lib.CORPUS,
                    self.request["generation"], self.request["commit"])
                self.assertEqual(pin["commit"], self.request["commit"])


if __name__ == "__main__":
    unittest.main()
