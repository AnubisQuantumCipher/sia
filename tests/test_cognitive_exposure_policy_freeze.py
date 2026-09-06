"""Declared event-exposure comparison grid, frozen before real model results."""

import hashlib
import json
from pathlib import Path
import unittest


POLICY = Path(__file__).resolve().parents[1] / "benchmarks" / "cognitive" / "event-exposure-policy-v1.json"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


ACTIVATION = {
    "v": 1, "algorithm": "log-sum-power-law-v1", "time_unit": "unix-seconds-integer",
    "age_offset_seconds": 0, "tie_break": "stable-input-order",
    "unavailable": "last", "max_uses": 4096, "max_total_uses": 4096,
    "max_candidates": 256,
}
# The ordered values are declared comparison choices, not fitted optima.
GRID = [{"policy": {**ACTIVATION, "decay": decay},
         "policy_sha256": digest({**ACTIVATION, "decay": decay})}
        for decay in (0.5, 1.0)]
EXPECTED = {
    "schema": "sia-cognitive-event-exposure-policy-v1",
    "exposures": "retained-native-excerpt-in-returned-chunk-v1",
    "cue_parser": "signed-history-exact-clause-v1",
    "timestamp_source": "signed-event-time-utc-v1",
    # Read from date +%s before any calibration model run or score inspection.
    # This is not inferred from the newest event or selected to alter ranking.
    "observed_at": 1788663128,
    "ablation_roster": ["raw-original", "cue-only", "cue-event-exposure"],
    "ordering": "cue-presence-activation-raw-rank-v1",
    "unavailable": "preserve-raw-order-v1",
    "overflow": "refuse-complete-run-v1",
    "activation_grid": GRID,
    "activation_grid_sha256": digest(GRID),
    "calibration_objective": {
        "metric_protocol_sha256": "52b9820c7fbb2e2ff1f556edd319d4ea0a446c3695917fe285de33176cf9ffe7",
        "class": "recency-heavy", "metric": "recall_at_k", "cutoff": 1,
        "tie_break": "activation-grid-order-v1",
    },
    "resources": {
        "max_queries": 64, "max_source_events": 65536, "max_grid_policies": 64,
        "max_input_bytes": 16777216, "max_trace_bytes": 2097152,
        "max_output_bytes": 16777216,
    },
}
ORDERED_POLICY = POLICY.with_name("ordered-measurement-policy-v1.json")
COMPOUND_POLICY = POLICY.with_name("event-exposure-policy-v2.json")
COMPOUND_ORDERED_POLICY = POLICY.with_name("ordered-measurement-policy-v2.json")
EXPECTED_ORDERED = {
    "schema": "sia-cognitive-ordered-measurement-policy-v1",
    "exposure_schema": "sia-cognitive-event-exposure-v1",
    "metric_protocol_sha256": "52b9820c7fbb2e2ff1f556edd319d4ea0a446c3695917fe285de33176cf9ffe7",
    "arms": ["raw-original", "cue-only", "cue-event-exposure"],
    "ordering": "replayed-row-reference-bijection-v1",
    "targets": "replayed-raw-native-occurrence-coverage-v1",
    "queries": "complete-observed-split-roster-v1",
    "summaries": "frozen-retrieval-policy-cutoffs-and-class-means-v1",
    "latencies": "retain-raw-no-rerank-timing-v1",
    "resources": {"max_input_bytes": 16777216, "max_output_bytes": 16777216,
                  "max_queries": 64},
}


class CognitiveExposurePolicyFreeze(unittest.TestCase):
    def test_complete_ordered_grid_clock_and_objective_precede_results(self):
        self.assertTrue(POLICY.is_file(), "pre-results event-exposure grid is missing")
        self.assertEqual(json.loads(POLICY.read_text(encoding="utf-8")), EXPECTED)
        self.assertEqual(digest(json.loads(POLICY.read_text(encoding="utf-8"))), digest(EXPECTED))

    def test_fixed_arm_measurement_rules_are_frozen_before_metric_inspection(self):
        self.assertTrue(ORDERED_POLICY.is_file(), "pre-metric ordered measurement policy is missing")
        self.assertEqual(json.loads(ORDERED_POLICY.read_text(encoding="utf-8")), EXPECTED_ORDERED)

    def test_compound_exposure_policy_changes_only_version_and_envelope_admission(self):
        self.assertTrue(COMPOUND_POLICY.is_file(), "explicit compound exposure policy is missing")
        expected = {**EXPECTED, "schema": "sia-cognitive-event-exposure-policy-v2",
                    "resources": {**EXPECTED["resources"], "max_input_bytes": 67108864,
                                  "max_document_bytes": 16777216}}
        self.assertEqual(json.loads(COMPOUND_POLICY.read_text(encoding="utf-8")), expected)

    def test_compound_ordered_policy_preserves_every_frozen_metric_and_arm_rule(self):
        self.assertTrue(COMPOUND_ORDERED_POLICY.is_file(), "explicit compound ordered policy is missing")
        expected = {**EXPECTED_ORDERED, "schema": "sia-cognitive-ordered-measurement-policy-v2",
                    "resources": {**EXPECTED_ORDERED["resources"], "max_input_bytes": 67108864,
                                  "max_document_bytes": 16777216}}
        self.assertEqual(json.loads(COMPOUND_ORDERED_POLICY.read_text(encoding="utf-8")), expected)


if __name__ == "__main__":
    unittest.main()
