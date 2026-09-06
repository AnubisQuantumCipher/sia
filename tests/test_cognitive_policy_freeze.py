"""The initial history-selection policy is explicit before any real tuning."""

import json
from pathlib import Path
import unittest


POLICY = Path(__file__).resolve().parents[1] / "benchmarks" / "cognitive" / "selection-policy-v1.json"
EXPECTED = {
    "schema": "sia-cognitive-selection-policy-v1",
    "seed": "sia-recorded-history-query-holdout-v1",
    "split": {"kind": "grouped-query-v1", "group_key": "chain-raw-subject-v1",
              "calibration_modulus": 5, "calibration_residue": 0},
    "pages": {"order": "seeded-slug-sha256-v1", "title": "slug-v1",
              "max_pages": 256, "max_page_bytes": 131072,
              "max_total_page_bytes": 4194304, "max_chunks": 4096},
    "queries": {"templates": "signed-history-tasks-v1",
                "max_groups_per_class": 64, "max_queries": 64},
    "protocol": {"chunking": "utf8-contiguous-codepoint-v1", "max_chunk_bytes": 2048,
                 "page_pooling": "single-chunk-per-slug", "max_query_bytes": 8000},
    "required_classes": ["recency-heavy", "repetition-heavy", "novelty"],
}
METRIC_POLICY = POLICY.with_name('retrieval-policy-v1.json')
EXPECTED_METRIC_POLICY = {
    'schema': 'sia-cognitive-retrieval-policy-v1', 'cutoffs': [1, 3, 5, 10],
    'targets': 'signed-answer-occurrences-v1',
    'matching': 'exact-selected-source-chunk-and-native-excerpt-v1',
    'recall': 'distinct-target-union-at-k-v1',
    'reciprocal_rank': 'first-any-target-row-at-k-v1',
    'aggregation': 'macro-query-within-class-v1',
    'duplicates': 'refuse-invalid-raw-roster-v1',
    'origins': 'preserve-source-labels-no-promotion-v1',
    'missing': 'zero-hit-no-denominator-shrink-v1',
    'dependence': 'chain-raw-subject-groups-and-shared-pages-v1',
    'chronology': 'externally-pinned-before-heldout-v1',
}
LATENCY_POLICY = POLICY.with_name('latency-policy-v1.json')
EXPECTED_LATENCY_POLICY = {
    'schema': 'sia-cognitive-latency-policy-v1',
    'samples': 'adapter-query-embedding-search-v1',
    'aggregation': 'macro-query-within-class-v1',
    'numbers': 'retained-json-roundtrip-decimal-as-given-v1',
    'units': 'producer-ms-no-conversion-v1',
    'roster': 'same-admitted-query-roster-v1',
    'missing': 'refuse-sample-drop-v1',
    'operation_timings': 'retain-separate-no-query-allocation-v1',
    'chronology': 'externally-pinned-before-heldout-v1',
}
EVENT_POLICY = POLICY.with_name('selection-policy-v2.json')
EXPECTED_EVENT_POLICY = {
    **EXPECTED, 'schema': 'sia-cognitive-selection-policy-v2',
    'queries': {
        **EXPECTED['queries'], 'templates': 'signed-history-event-recency-v2',
        'recency': {
            'population': 'complete-chain-exact-action-raw-subject-v1',
            'time': 'canonical-native-event-time-utc-v1',
            'target': 'unique-maximum-event-time-v1',
            'contrast': 'nearest-strictly-older-global-v1',
            'contrast_ties': 'highest-signed-sequence-v1',
            'page_relation': 'distinct-target-contrast-source-pages-v1',
            'witnesses': 'target-and-contrast-required-no-substitution-v1',
        },
    },
}


class CognitivePolicyFreeze(unittest.TestCase):
    def test_initial_policy_is_explicit_and_matches_the_frozen_protocol(self):
        self.assertTrue(POLICY.is_file(), "initial pre-tuning selection policy is missing")
        # These are declared protocol choices and existing representation
        # ceilings, not calculated metrics or fitted mechanism parameters.
        self.assertEqual(json.loads(POLICY.read_text(encoding="utf-8")), EXPECTED)

    def test_initial_retrieval_metric_policy_is_explicit_before_results(self):
        self.assertTrue(METRIC_POLICY.is_file(), 'initial pre-results retrieval metric policy is missing')
        # Cutoffs are declared retrieval windows, not derived measurements.
        self.assertEqual(json.loads(METRIC_POLICY.read_text(encoding='utf-8')),
                         EXPECTED_METRIC_POLICY)

    def test_initial_latency_policy_preserves_reported_timing_domains(self):
        self.assertTrue(LATENCY_POLICY.is_file(), 'pre-results latency policy is missing')
        self.assertEqual(json.loads(LATENCY_POLICY.read_text(encoding='utf-8')),
                         EXPECTED_LATENCY_POLICY)

    def test_event_time_task_is_a_separately_frozen_policy_with_unchanged_split(self):
        self.assertTrue(EVENT_POLICY.is_file(), 'separate pre-results event-recency policy is missing')
        self.assertEqual(json.loads(EVENT_POLICY.read_text(encoding='utf-8')),
                         EXPECTED_EVENT_POLICY)


if __name__ == "__main__":
    unittest.main()
