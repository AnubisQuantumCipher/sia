#!/usr/bin/env python3
"""Focused grading-boundary and calibration-display regressions."""

import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")
sys.path.insert(0, BIN)

import sialib
import siatakes


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(text)


class GradingEvidenceCanonicalization(unittest.TestCase):
    def test_only_canonical_real_event_and_epoch_paths_are_admitted(self):
        with tempfile.TemporaryDirectory() as corpus:
            _write(os.path.join(corpus, "events/journal/day.md"),
                   "observed event")
            _write(os.path.join(corpus, "takes/model.md"), "model prose")
            _write(os.path.join(corpus, "events/jackal/result.md"),
                   "unverified result")
            os.symlink("../takes", os.path.join(corpus, "events/alias"))

            with mock.patch.object(siatakes, "CORPUS", corpus):
                self.assertTrue(siatakes._admitted_evidence_slug(
                    "events/journal/day"))
                for slug in (
                        "events/./journal/day",
                        "events//journal/day",
                        "events/journal/day/",
                        "events/../takes/model",
                        "events/seen/../jackal/result",
                        "events/alias/model"):
                    with self.subTest(slug=slug):
                        self.assertFalse(
                            siatakes._admitted_evidence_slug(slug))

    def test_judge_config_roster_admits_every_shipped_top_level_key(self):
        """The judge reads config.json with its own top-level key roster and
        fails closed to no judge on any unknown key. The shipped example
        config carries a "mind" section the roster lacked, so grading
        silently never ran on the maintainer machine (and any machine on
        the example config): `sia grade` said "judge unavailable" with a
        working Claude CLI. The roster must admit every key the runtime's
        own loader admits and every key the example ships."""
        example = json.load(open(os.path.join(REPO, "config.example.json"),
                                 encoding="utf-8"))
        self.assertEqual(set(example) - siatakes.CONFIG_TOP_LEVEL_KEYS, set())
        self.assertEqual(sialib._CONFIG_TOP_LEVEL_KEYS - siatakes.CONFIG_TOP_LEVEL_KEYS,
                         set())

    def test_option_shaped_claim_is_never_sent_to_the_engine(self):
        """A take whose claim is "--help" (registered before `sia take --help`
        was refused) made the engine print its usage text instead of a
        result list; admission refused it and the take stayed due forever.
        The claim is not recalled at all: a completed recall with no
        admitted evidence lets the judge grade it UNRESOLVABLE."""
        with mock.patch.object(sialib, "gbrain",
                               side_effect=AssertionError("engine queried")):
            for claim in ("--help", "  -h", "", "   "):
                recall = siatakes._recall(claim)
                self.assertTrue(recall.completed, claim)
                self.assertEqual(recall.text, "")
                self.assertEqual(recall.citations, frozenset())
                self.assertEqual(recall.reason, "")

    def test_model_and_jackal_traversal_refuse_before_judging(self):
        aliases = (
            "events/../takes/model",
            "events/seen/../jackal/result",
        )
        with tempfile.TemporaryDirectory() as corpus:
            _write(os.path.join(corpus, "takes/model.md"), "model prose")
            _write(os.path.join(corpus, "events/jackal/result.md"),
                   "unverified result")
            for alias in aliases:
                row = json.dumps([
                    {"slug": alias, "chunk_text": "claimed witness"}
                ])
                engine = types.SimpleNamespace(
                    returncode=0, stdout=row, stderr="")
                take = {
                    "id": "fixture", "claim": "alias witness held",
                    "confidence": 0.8, "deadline": "2099-01-01",
                    "created": "2026-08-30T00:00:00Z", "status": "open",
                    "domain": "general", "source": "sia/cortex",
                }
                persisted = []
                with self.subTest(alias=alias), \
                        mock.patch.object(siatakes, "CORPUS", corpus), \
                        mock.patch.object(sialib, "gbrain",
                                          return_value=engine), \
                        mock.patch.object(siatakes, "_judge_run") as judge, \
                        self.assertRaises(
                            siatakes.GradingEvidenceUnavailable):
                    siatakes.grade_take(
                        take, persist=lambda *args: persisted.append(args))
                judge.assert_not_called()
                self.assertEqual(persisted, [])


class JudgmentResponseGrammar(unittest.TestCase):
    def test_exact_two_field_response_preserves_plain_justification(self):
        verdict, justification = siatakes._parse_judgment(
            "VERDICT: TRUE\n"
            "JUSTIFICATION: [events/journal/day] records the outcome. "
            "The bounded plain explanation remains readable.",
            {"events/journal/day"})
        self.assertEqual(verdict, "TRUE")
        self.assertIn("records the outcome", justification)
        self.assertIn("⟦events/journal/day⟧", justification)

    def test_ambiguous_or_noncanonical_responses_are_refused(self):
        responses = (
            "VERDICT: TRUE\nVERDICT: FALSE\n"
            "JUSTIFICATION: [events/journal/day] conflicts",
            "VERDICT: TRUE\nJUSTIFICATION: [events/journal/day] held\n"
            "JUSTIFICATION: duplicate",
            "preamble\nVERDICT: TRUE\n"
            "JUSTIFICATION: [events/journal/day] held",
            "VERDICT: TRUE\nJUSTIFICATION: [events/journal/day] held\n"
            "VERDICT: FALSE",
            "VERDICT: TRUE\nJUSTIFICATION: [events/journal/day] held\n"
            "CONFIDENCE: high",
            "VERDICT: MAYBE\nJUSTIFICATION: no allowed verdict",
        )
        for response in responses:
            with self.subTest(response=response):
                verdict, reason = siatakes._parse_judgment(
                    response, {"events/journal/day"})
                self.assertIsNone(verdict)
                self.assertEqual(
                    reason,
                    "judge response missing exact verdict/justification")


class CalibrationTextCompleteness(unittest.TestCase):
    def test_bounded_domain_page_names_its_omission_and_cursor(self):
        cursor = str(siatakes.DEFAULT_HISTORY_PAGE_LIMIT)
        report = {
            "overall": {"resolved": 0},
            "domains": {},
            "domain_next_cursor": cursor,
        }
        with mock.patch.object(siatakes, "calibration_report",
                               return_value=report):
            rendered = "\n".join(siatakes.calibration_text())
        self.assertIn(
            "additional calibration domain rows omitted", rendered)
        self.assertIn(f"next cursor {cursor}", rendered)
        self.assertIn("bounded CLI/MCP view", rendered)


if __name__ == "__main__":
    unittest.main()
