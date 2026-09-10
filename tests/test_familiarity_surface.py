#!/usr/bin/env python3
"""Novelty-detector availability must survive every resident status surface."""

import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

from tests.test_cli import (
    _current_graph_fixture,
    _current_status_fixture,
    sia,
)
from tests.test_cockpit_boundary_horizon import _JsRunner, _qml_element

import siamind


REPO = Path(__file__).resolve().parent.parent
FAMILIARITY_STATES = ("complete", "incomplete", "bootstrap-pending")


def _status(familiarity="incomplete"):
    status = _current_status_fixture()
    status["v"] = 2
    status["mind"]["familiarity_status"] = familiarity
    return status


class FamiliaritySummarySurface(unittest.TestCase):
    def test_summary_preserves_detector_availability_without_mutating_state(self):
        cases = (
            (True, False, "complete"),
            (False, False, "incomplete"),
            (False, True, "bootstrap-pending"),
        )
        for complete, pending, expected in cases:
            mind = siamind._empty_mind()
            mind["familiarity_complete"] = complete
            mind["familiarity_bootstrap_pending"] = pending
            before = copy.deepcopy(mind)
            with self.subTest(expected=expected):
                summary = siamind.memory_summary_view(mind, now=100.0)
                self.assertEqual(summary.get("familiarity_status"), expected)
                self.assertEqual(mind, before)

    def test_resident_validator_admits_each_explicit_detector_state(self):
        for familiarity in FAMILIARITY_STATES:
            with self.subTest(familiarity=familiarity):
                self.assertEqual(
                    sia.sialib._recoverable_status_integrity(
                        _status(familiarity)), "pass")

    def test_resident_validator_rejects_missing_or_malformed_detector_state(self):
        missing = _status()
        del missing["mind"]["familiarity_status"]
        self.assertIsNone(sia.sialib._recoverable_status_integrity(missing))
        for bad in (None, True, 0, [], {}, "", "unknown", "Complete"):
            with self.subTest(bad=bad):
                self.assertIsNone(
                    sia.sialib._recoverable_status_integrity(_status(bad)))

    def test_legacy_status_cannot_smuggle_current_detector_authority(self):
        legacy = _current_status_fixture()
        self.assertEqual(
            sia.sialib._recoverable_status_integrity(legacy), "pass")
        legacy["mind"]["familiarity_status"] = "complete"
        self.assertIsNone(sia.sialib._recoverable_status_integrity(legacy))


class FamiliarityCliSurface(unittest.TestCase):
    def _render(self, status):
        output = io.StringIO()
        with mock.patch.object(
                sia.sialib, "corpus_owner",
                return_value=contextlib.nullcontext()), \
                mock.patch.object(
                    sia.sialib, "read_state_json",
                    side_effect=(status, _current_graph_fixture(), None)), \
                mock.patch.object(
                    sia.sialib, "_recoverable_status_integrity",
                    return_value="pass"), \
                mock.patch.object(
                    sia.sialib, "memory_readiness",
                    return_value=(True, "")), \
                contextlib.redirect_stdout(output):
            code = sia.cmd_status()
        self.assertEqual(code, 0)
        return output.getvalue()

    def test_ready_corpus_does_not_hide_incomplete_familiarity(self):
        rendered = self._render(_status("incomplete"))
        self.assertIn("readiness READY", rendered)
        self.assertIn("familiarity incomplete", rendered)
        self.assertIn("first/new-shape claims withheld", rendered)

    def test_pending_bootstrap_is_not_reported_as_complete(self):
        rendered = self._render(_status("bootstrap-pending"))
        self.assertIn("familiarity bootstrap pending", rendered)
        self.assertIn("baseline not admitted", rendered)
        self.assertIn("first/new-shape claims withheld", rendered)

    def test_complete_familiarity_names_its_scoped_capability(self):
        rendered = self._render(_status("complete"))
        self.assertIn("familiarity complete", rendered)
        self.assertIn("first/new-shape detection available", rendered)

    def test_legacy_status_does_not_imply_complete_familiarity(self):
        rendered = self._render(_current_status_fixture())
        self.assertIn("familiarity unavailable", rendered)
        self.assertIn("legacy status", rendered)


class FamiliarityCockpitSurface(unittest.TestCase):
    def setUp(self):
        self.node = shutil.which("node")
        if self.node is None:
            self.skipTest("Node is unavailable for executable cockpit logic")

    def _model(self, function, value):
        result = subprocess.run(
            [self.node, "-e", _JsRunner.SCRIPT,
             json.dumps([str(REPO / "Model.js")]), "", function,
             json.dumps([value], separators=(",", ":"))],
            cwd=REPO, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_current_model_admits_each_explicit_detector_state(self):
        for familiarity in FAMILIARITY_STATES:
            with self.subTest(familiarity=familiarity):
                self.assertTrue(self._model(
                    "residentStatusShape", _status(familiarity)))

    def test_current_model_requires_exact_current_shape_and_detector_state(self):
        mutations = []
        missing = _status()
        del missing["mind"]["familiarity_status"]
        mutations.append(missing)
        versionless = _status()
        del versionless["version"]
        mutations.append(versionless)
        unbound_graph = _status()
        del unbound_graph["graph_publication_id"]
        mutations.append(unbound_graph)
        for bad in (None, True, 0, [], {}, "", "unknown", "Complete"):
            mutations.append(_status(bad))
        for status in mutations:
            with self.subTest(status=status):
                self.assertFalse(self._model("residentStatusShape", status))

    def test_legacy_model_keeps_its_own_mind_roster(self):
        legacy = _current_status_fixture()
        self.assertTrue(self._model("residentStatusShape", legacy))
        legacy["mind"]["familiarity_status"] = "complete"
        self.assertFalse(self._model("residentStatusShape", legacy))

    def test_memory_lens_renders_scoped_availability_in_plain_text(self):
        expected = {
            "complete": "complete · first/new-shape detection available",
            "incomplete": "incomplete · first/new-shape claims withheld",
            "bootstrap-pending": (
                "bootstrap pending · baseline not admitted; "
                "first/new-shape claims withheld"),
        }
        for familiarity, label in expected.items():
            with self.subTest(familiarity=familiarity):
                self.assertEqual(self._model(
                    "familiarityStatusText",
                    {"familiarity_status": familiarity}), label)
        legacy = self._model("familiarityStatusText", {})
        self.assertIn("unavailable", legacy)
        self.assertIn("legacy status", legacy)
        cockpit = (REPO / "Cockpit.qml").read_text(encoding="utf-8")
        lens = _qml_element(cockpit, "id: memoryLens")
        self.assertIn("Model.familiarityStatusText(memoryLens.mind)", lens)
        familiarity = _qml_element(lens, "id: familiarityValue")
        self.assertIn("textFormat: Text.PlainText", familiarity)
        self.assertIn("wrapMode: Text.WordWrap", familiarity)


if __name__ == "__main__":
    unittest.main()
