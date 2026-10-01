"""Freeze the independently staged fixture contracts before heldout execution."""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "cognitive"
# Literal copies of the staged closed contracts keep this policy milestone
# independent of uncommitted behavior modules or their test imports.
EXPECTED_FIDELITY = json.loads(r'''{
  "schema": "sia-cognitive-memory-fidelity-policy-v1",
  "ordered_schema": "sia-cognitive-ordered-measurement-plan-v1",
  "metric_protocol_sha256": "52b9820c7fbb2e2ff1f556edd319d4ea0a446c3695917fe285de33176cf9ffe7",
  "arms": [
    "raw-original",
    "cue-only",
    "cue-event-exposure"
  ],
  "predicates": [
    "complete-captured-source-bindings",
    "complete-returned-candidate-membership",
    "unchanged-raw-chunk-and-score-values",
    "unchanged-source-origins",
    "complete-exposure-and-activation-traces",
    "unchanged-native-targets-and-coverage",
    "complete-fixed-arm-permutations",
    "complete-upstream-nonclaims"
  ],
  "scope": {
    "sources": "admitted-captured-history-only",
    "candidates": "returned-raw-candidate-roster-only",
    "storage": "identity-references-not-a-source-archive",
    "resident_state": "not-observed"
  },
  "replay": "complete-independent-ordered-replay-v1",
  "references": "complete-documents-and-subtrees-no-archive-claim-v1",
  "chronology": "externally-pinned-before-heldout-v1",
  "overflow": "refuse-complete-artifact-v1",
  "resources": {
    "max_input_bytes": 67108864,
    "max_document_bytes": 16777216,
    "max_output_bytes": 16777216,
    "max_queries": 64,
    "max_source_events": 65536,
    "max_source_pages": 4096,
    "max_candidates_per_query": 256,
    "max_trace_bytes": 2097152
  }
}''')
EXPECTED_TIMING = json.loads(r'''{
  "schema": "sia-cognitive-event-exposure-timing-policy-v1",
  "exposure_schema": "sia-cognitive-event-exposure-v1",
  "metric_protocol_sha256": "52b9820c7fbb2e2ff1f556edd319d4ea0a446c3695917fe285de33176cf9ffe7",
  "arms": [
    "raw-original",
    "cue-only",
    "cue-event-exposure"
  ],
  "schedule": "query-major-fixed-arm-order-once-v1",
  "clock": "time.perf_counter_ns",
  "unit": "ns",
  "worker_scope": "admitted-target-blind-arm-call-through-return-v1",
  "pipeline_scope": "not-measured-v1",
  "admission": "complete-before-first-clock-v1",
  "pre_observation": "complete-untimed-exposure-replay-v1",
  "warmup": "no-additional-warmup-cache-state-uncontrolled-v1",
  "aggregation": "macro-query-within-class-v1",
  "numbers": "bounded-json-integer-endpoints-unevaluated-difference-v1",
  "raw_timings": "retain-original-separate-no-total-composition-v1",
  "missing": "refuse-complete-run-v1",
  "chronology": "externally-pinned-before-heldout-v1",
  "resources": {
    "max_input_bytes": 67108864,
    "max_document_bytes": 16777216,
    "max_output_bytes": 16777216,
    "max_queries": 64,
    "max_clock_ns": 9007199254740991
  }
}''')


class CognitiveFidelityTimingPolicyFreeze(unittest.TestCase):
    def test_complete_memory_fidelity_contract_is_frozen_before_heldout(self):
        path = ROOT / "memory-fidelity-policy-v1.json"
        self.assertTrue(path.is_file(), "pre-heldout fidelity policy is missing")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), EXPECTED_FIDELITY)

    def test_complete_new_replay_worker_timing_contract_is_frozen_before_heldout(self):
        path = ROOT / "event-exposure-timing-policy-v1.json"
        self.assertTrue(path.is_file(), "pre-heldout timed-replay policy is missing")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), EXPECTED_TIMING)


if __name__ == "__main__":
    unittest.main()
