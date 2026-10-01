#!/usr/bin/env python3
"""Single-source regressions for calibration gating and the scored window.

Two defects of the same shape: a rule that must hold in one place was
written down twice, so the copies could drift without anything failing.
These tests pin the single source of truth rather than the value it
currently produces -- a value assertion would pass again the moment a
second copy reappeared beside the first.
"""

import inspect
import os
import sys
import unittest
from decimal import Decimal
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")
sys.path.insert(0, BIN)

import siabench
import siatakes


def _take(confidence, outcome, domain="general"):
    return {"status": "resolved-true" if outcome == 1 else "resolved-false",
            "confidence": confidence, "outcome": outcome,
            "domain": domain, "brier": 999}


def _stats(pairs):
    """Fold the same population into streaming natural-history counters.

    The streaming reader never sees rows, only running sums, so this is
    how the identical population reaches the other classification site.
    """
    stats = siatakes._empty_history_stats()
    for confidence, outcome in pairs:
        p = Decimal(confidence)
        o = Decimal(outcome)
        stats["resolved"] += 1
        stats["true" if outcome == 1 else "false"] += 1
        if (o == 1) == (p >= Decimal("0.5")):
            stats["hits"] += 1
        stats["sum_p"] = str(Decimal(stats["sum_p"]) + p)
        stats["sum_o"] = str(Decimal(stats["sum_o"]) + o)
        stats["sum_brier"] = str(
            Decimal(stats["sum_brier"]) + (p - o) ** 2)
        for entry, (_label, lo, hi) in zip(stats["bins"],
                                           siatakes.CALIBRATION_BINS):
            if lo <= p < hi:
                entry["n"] += 1
                entry["sum_p"] = str(Decimal(entry["sum_p"]) + p)
                entry["sum_o"] = str(Decimal(entry["sum_o"]) + o)
    return stats


POPULATIONS = {
    "no-resolved-outcomes": [],
    "single-case": [("0.9", 1)],
    "descriptive-series": [("0.8", 1), ("0.2", 0), ("0.7", 1)],
    "outcome-imbalanced": [("0.8", 1)] * 30,
    "monitoring-population": [("0.8", 1)] * 15 + [("0.2", 0)] * 15,
}


class CalibrationPopulationClassifierIsShared(unittest.TestCase):
    """FINDING 28: one display-gate cascade, two calibration readers."""

    def test_both_reports_route_through_the_one_classifier(self):
        # The biting assertion: patching the single classifier must move
        # BOTH surfaces.  When either reader carries its own inlined copy
        # of the cascade, this cannot pass -- either the shared symbol is
        # absent, or the untouched copy keeps emitting the real status.
        sentinel = ("wired-through-shared-helper", False,
                    "one cascade, one set of thresholds")
        with mock.patch.object(siatakes, "_calibration_population_status",
                               return_value=sentinel) as classifier:
            streaming = siatakes._history_stats_report(
                _stats(POPULATIONS["single-case"]))
            supplied = siatakes._calibration_population(
                [_take("0.9", 1)])
        for report in (streaming, supplied):
            self.assertEqual(report["population_status"], sentinel[0])
            self.assertEqual(report["monitoring_display_eligible"],
                             sentinel[1])
            self.assertEqual(report["reason"], sentinel[2])
        self.assertEqual(classifier.call_count, 2)
        self.assertEqual({call.args for call in classifier.call_args_list},
                         {(1, 1, 0)})

    def test_streaming_and_supplied_reports_agree_on_every_class(self):
        # A drifted threshold literal in one copy would show up here as
        # two different descriptions of one population.
        for expected, pairs in sorted(POPULATIONS.items()):
            with self.subTest(population=expected):
                streaming = siatakes._history_stats_report(_stats(pairs))
                supplied = siatakes._calibration_population(
                    [_take(confidence, outcome)
                     for confidence, outcome in pairs])
                self.assertEqual(streaming["population_status"], expected)
                self.assertEqual(streaming, supplied)

    def test_thresholds_are_read_from_the_declared_policy_constants(self):
        # The gate published in calibration_report()["policy"] must be the
        # gate actually applied, on both sides.
        with mock.patch.object(siatakes, "CALIBRATION_MIN_RESOLVED", 3):
            pairs = POPULATIONS["descriptive-series"]
            self.assertEqual(
                siatakes._history_stats_report(
                    _stats(pairs))["population_status"],
                "outcome-imbalanced")
            self.assertEqual(
                siatakes._calibration_population(
                    [_take(c, o) for c, o in pairs])["population_status"],
                "outcome-imbalanced")


def _witness_question(slug, excerpt):
    normalized = siabench._normalize_witness_excerpt(excerpt)
    return {"id": "scored-window", "question": "scored window",
            "category": "information-extraction",
            "sources": [slug], "answer": "witnessed",
            "answer_witness": {
                "schema": siabench.ANSWER_WITNESS_SCHEMA,
                "match": "any-excerpt",
                "excerpts": [{"slug": slug, "excerpt": normalized,
                              "sha256": siabench._sha_text(normalized)}]}}


def _results(witness_rank, total, slug, excerpt):
    rows = []
    for position in range(1, total + 1):
        if position == witness_rank:
            rows.append({"slug": slug, "score": 1.0,
                         "chunk_text": "prefix " + excerpt + " suffix"})
        else:
            rows.append({"slug": f"events/fixture/miss-{position}",
                         "score": 1.0, "chunk_text": "unrelated chunk"})
    return rows


class ScoredWindowFollowsTopK(unittest.TestCase):
    """FINDING 29: generation and scoring share one retrieval window."""

    SLUG = "events/fixture/day"
    EXCERPT = "the witnessed line"

    def test_no_import_time_default_freezes_the_window(self):
        # A `k=TOP_K` default is evaluated once, at def time.  Generation
        # reads the global when it builds questions, so a bound default is
        # exactly how the two sides come to disagree.
        self.assertIsNone(
            inspect.signature(siabench._evidence_rank)
            .parameters["k"].default)

    def test_narrowed_top_k_narrows_scoring_too(self):
        question = _witness_question(self.SLUG, self.EXCERPT)
        results = _results(3, 3, self.SLUG, self.EXCERPT)
        self.assertEqual(
            siabench._evidence_rank(question, results), 3)
        with mock.patch.object(siabench, "TOP_K", 1):
            # Generation would refuse to emit a question whose witnesses
            # cannot fit a window of 1; the scorer must not then peer past
            # it and credit a rank the run never admitted.
            self.assertIsNone(
                siabench._evidence_rank(question, results))

    def test_widened_top_k_widens_scoring_too(self):
        question = _witness_question(self.SLUG, self.EXCERPT)
        results = _results(7, 7, self.SLUG, self.EXCERPT)
        self.assertIsNone(siabench._evidence_rank(question, results))
        with mock.patch.object(siabench, "TOP_K", 10):
            self.assertEqual(
                siabench._evidence_rank(question, results), 7)

    def test_explicit_k_still_overrides_the_global(self):
        question = _witness_question(self.SLUG, self.EXCERPT)
        results = _results(3, 3, self.SLUG, self.EXCERPT)
        self.assertIsNone(
            siabench._evidence_rank(question, results, k=2))
        self.assertEqual(
            siabench._evidence_rank(question, results, k=3), 3)


if __name__ == "__main__":
    unittest.main()
