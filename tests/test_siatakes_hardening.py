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
    def test_blocked_legacy_retention_refuses_without_capping_valid_deadlines(self):
        take = {"created": "2026-08-01T00:00:00Z", "deadline": "9999-12-31",
                "claim": "journal grows"}
        with mock.patch.object(siatakes, "natural_history_debt", return_value=False), \
                mock.patch.object(siatakes, "_history_open_rows", return_value=[take]):
            self.assertEqual(siatakes.open_take_evidence_windows()[0][2],
                             "9999-12-31")
            take["legacy_v1"] = {"deadline_state": "invalid-open-blocked"}
            with self.assertRaisesRegex(siatakes.GradingEvidenceUnavailable,
                                        "blocked legacy take"):
                siatakes.open_take_evidence_windows()

    def test_grading_retries_rotate_past_permanently_refusing_takes(self):
        due = [{"id": key} for key in ("a", "b", "c", "d", "e")]
        first = siatakes.next_grade_batch(due)
        second = siatakes.next_grade_batch(due, first[-1]["id"])
        self.assertEqual([row["id"] for row in first], ["a", "b", "c"])
        self.assertEqual([row["id"] for row in second], ["d", "e", "a"])
        self.assertEqual(siatakes.next_grade_batch([], "c"), [])
        with self.assertRaisesRegex(ValueError, "cursor"):
            siatakes.next_grade_batch(due, {})

    def test_dated_grade_receives_all_window_days_and_full_hourly_evidence(self):
        take = {"claim": "journal will exceed the hourly threshold",
                "created": "2026-08-01T12:00:00Z", "deadline": "2026-08-05",
                "confidence": 0.7, "status": "open"}
        slug = "events/journal/2026-08-02"
        with tempfile.TemporaryDirectory() as corpus:
            for day in ("2026-07-31", "2026-08-01", "2026-08-02",
                        "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"):
                _write(os.path.join(corpus, "events/journal", day + ".md"),
                       "---\ntype: event-day\n---\n" + "context " * 100 +
                       f" Hourly evidence for {day}: 13:00 threshold exceeded.")
            _write(os.path.join(corpus, "epochs/journal/2026-w32.md"),
                   "weekly exemplars")
            with mock.patch.object(siatakes, "CORPUS", corpus), \
                    mock.patch.object(siatakes, "_recall", return_value=
                                      siatakes.RecallEvidence(True, "", frozenset())), \
                    mock.patch.object(siatakes, "_judge_run", return_value=(
                        f"VERDICT: TRUE\nJUSTIFICATION: [{slug}] records the hour.",
                        None, "fixture")) as judge:
                persist = mock.Mock()
                result = siatakes.grade_take(take, persist=persist)
            prompt = judge.call_args.args[0]
            for day in ("01", "02", "03", "04", "05"):
                self.assertIn(f"Hourly evidence for 2026-08-{day}", prompt)
            self.assertNotIn("2026-07-31", prompt)
            self.assertNotIn("2026-08-06", prompt)
            self.assertEqual(result["status"], "resolved-true")
            self.assertTrue(persist.call_args.args[3])

    def test_complete_window_over_budget_refuses_before_judge(self):
        with tempfile.TemporaryDirectory() as corpus:
            _write(os.path.join(corpus, "events/journal/2026-08-02.md"),
                   "evidence " * 100)
            with mock.patch.object(siatakes, "CORPUS", corpus), \
                    mock.patch.object(siatakes, "MAX_WINDOW_EVIDENCE_BYTES", 20), \
                    mock.patch.object(siatakes, "_recall", return_value=
                                      siatakes.RecallEvidence(True, "", frozenset())), \
                    mock.patch.object(siatakes, "_judge_run") as judge, \
                    self.assertRaisesRegex(siatakes.GradingEvidenceUnavailable,
                                           "byte budget"):
                siatakes._grading_evidence(
                    "journal", created="2026-08-01T00:00:00Z", deadline="2026-08-03")
            judge.assert_not_called()

    def test_window_append_between_selection_and_snapshot_is_not_partial_evidence(self):
        with tempfile.TemporaryDirectory() as corpus:
            path = os.path.join(corpus, "events/journal/2026-08-02.md")
            _write(path, "original hour")
            read = siatakes._read_regular_text
            calls = []

            def append_before_second_read(filename):
                calls.append(filename)
                if len(calls) == 2:
                    _write(path, "original hour plus later hour")
                return read(filename)

            with mock.patch.object(siatakes, "CORPUS", corpus), \
                    mock.patch.object(siatakes, "_read_regular_text",
                                      side_effect=append_before_second_read), \
                    mock.patch.object(siatakes, "_recall", return_value=
                                      siatakes.RecallEvidence(True, "", frozenset())), \
                    self.assertRaisesRegex(siatakes.GradingEvidenceUnavailable,
                                           "changed while reading"):
                siatakes._grading_evidence(
                    "journal", created="2026-08-01T00:00:00Z", deadline="2026-08-03")

    def test_judge_failure_preserves_reason_and_never_persists(self):
        for output, error, expected in (
                (None, "service not ready", "service not ready"),
                ("malformed", None, "missing exact verdict")):
            with self.subTest(error=error), \
                    mock.patch.object(siatakes, "_grading_evidence",
                                      return_value=("", set(), [])), \
                    mock.patch.object(siatakes, "_judge_run",
                                      return_value=(output, error, "fixture")), \
                    self.assertRaisesRegex(siatakes.GradingJudgeUnavailable, expected):
                persist = mock.Mock()
                try:
                    siatakes.grade_take({"claim": "a claim", "deadline": "2026-08-03"},
                                       persist=persist)
                finally:
                    persist.assert_not_called()

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
        with open(os.path.join(REPO, "config.example.json"), encoding="utf-8") as stream:
            example = json.load(stream)
        self.assertEqual(set(example) - siatakes.CONFIG_TOP_LEVEL_KEYS, set())
        self.assertEqual(sialib._CONFIG_TOP_LEVEL_KEYS - siatakes.CONFIG_TOP_LEVEL_KEYS,
                         set())

    def test_unrecallable_claim_reports_a_read_that_did_not_complete(self):
        """A claim the engine CLI would read as a flag is never sent to it, and
        the recall is reported as NOT completed.

        This assertion is the inverse of the one it replaces, which required
        `completed is True` for a corpus search that never ran.  That closed the
        take as UNRESOLVABLE on half an evidence lane, while the published page
        still said it had been judged against a signed evidence snapshot.
        `GradingEvidenceUnavailable` states the rule: "only a completed evidence
        read may be judged UNRESOLVABLE"."""
        with mock.patch.object(sialib, "gbrain",
                               side_effect=AssertionError("engine queried")):
            for claim in ("--help", "  -h", "", "   "):
                recall = siatakes._recall(claim)
                self.assertFalse(recall.completed, claim)
                self.assertEqual(recall.text, "")
                self.assertEqual(recall.citations, frozenset())
                self.assertTrue(recall.reason, claim)

    def test_a_negative_number_claim_still_reaches_the_engine(self):
        """`-1 regressions will land by March` is a legitimate take, which
        `sia take -- …` exists to let a caller register, and the engine runs it
        as an ordinary search.  The guard used to reject every claim opening
        with a dash, silently removing the semantic recall lane from takes the
        CLI deliberately supports."""
        self.assertFalse(siatakes._option_shaped("-1 regressions will land"))
        self.assertFalse(siatakes._option_shaped("-.5 drop in latency"))
        self.assertTrue(siatakes._option_shaped("--help"))
        self.assertTrue(siatakes._option_shaped("  -h"))

        seen = []

        def _fake_gbrain(args, **kw):
            seen.append(args)
            raise RuntimeError("stop after dispatch")

        with mock.patch.object(sialib, "gbrain", _fake_gbrain):
            siatakes._recall("-1 regressions will land by March")
        self.assertTrue(seen, "the claim must reach the engine")
        self.assertIn("-1 regressions will land by March", seen[0])

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
