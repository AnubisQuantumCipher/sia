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


if __name__ == "__main__":
    unittest.main()
