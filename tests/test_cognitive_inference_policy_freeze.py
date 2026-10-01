"""Pre-heldout claim criteria are declarations, not a statistical result.

The paired sign-test design follows NIST's sign-test description. It discards
ties only for the test denominator, never from retrieval means or reports.
The declared Bonferroni threshold was routed through JACKAL:
status=exact parsed=1/20/2 exact=1/40, formal=false. Nonclaims:
NOT formal-bounded: this lane carries no Lean-checked certificate
The epistemic class above is the STRONGEST claim this result supports
exact rational arithmetic (not yet checker-covered)
"""

import json
from pathlib import Path
import unittest


POLICY = Path(__file__).resolve().parents[1] / "benchmarks" / "cognitive" / "event-exposure-inference-policy-v1.json"
EXPECTED = {
    "schema": "sia-cognitive-event-exposure-inference-policy-v1",
    "protocol_sha256": "52b9820c7fbb2e2ff1f556edd319d4ea0a446c3695917fe285de33176cf9ffe7",
    "split": "heldout",
    "primary_class": "recency-heavy",
    "primary_metric": "recall_at_k",
    "primary_cutoff": 1,
    "mechanism_arm": "cue-event-exposure",
    "comparators": ["raw-original", "cue-only"],
    "effect_requirement": "positive-complete-class-mean-delta-against-every-comparator-v1",
    "test": "one-sided-positive-sign-exact-binomial-tail-v1",
    "alternative": "greater",
    "null_success_probability": "1/2",
    "familywise_alpha": "1/20",
    "per_comparison_alpha": "1/40",
    "multiplicity": "bonferroni-fixed-comparator-roster-v1",
    "paired_unit": "connected-native-group-and-target-support-page-component-v1",
    "component_metric": "macro-query-recall-within-complete-component-v1",
    "components": "complete-primary-class-before-arm-outcome-inspection-v1",
    "ties": "retain-in-descriptive-means-exclude-only-sign-test-denominator-v1",
    "no_nonties": "no-sign-evidence-no-win-v1",
    "model_assumptions": [
        "fixed admitted component roster",
        "independent component signs conditional on the null",
        "constant null positive-sign probability among non-ties",
        "one-sided exact tail convention",
    ],
    "assumption_boundary": "source-dependency-coalescence-does-not-verify-sampling-or-independence-v1",
    "secondary_metrics": "complete-frozen-cutoffs-and-classes-descriptive-only-v1",
    "fidelity_requirement": "complete-independently-replayed-policy-predicates-v1",
    "latency_requirement": "complete-new-timed-replay-and-separate-original-raw-observations-v1",
    "latency_claim": "descriptive-scope-separated-no-speedup-authorization-v1",
    "numeric_admission": "fresh-jackal-frontdoor-results-full-bindings-status-assumptions-nonclaims-v1",
    "missing_or_refused": "no-win-authorization-v1",
    "public_claim": "none-without-completed-mechanism-fidelity-latency-and-inference-admission-v1",
    "chronology": "freeze-before-heldout-results-no-heldout-tuning-v1",
    "source": "https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/signtest.htm",
    "non_claims": [
        "This policy is a frozen test design, not implemented verdict admission or a heldout result.",
        "A sign test addresses the declared component-sign model, not general cognition or a distribution-free mean-effect guarantee.",
        "Native groups and shared target/support pages define declared dependency blocks; their coalescence does not establish independent sampling or statistical power.",
        "Query-level heldout selection is not a source-page holdout; shared pages and authentication anchors remain disclosed.",
        "Calibration cue-only gains do not earn a power-law decay or frequency claim; the mechanism must improve against both fixed comparators.",
        "All fixed retrieval metrics, ties, losses, missing scopes and unavailable classes remain in the descriptive report; secondary outcomes do not substitute for the primary test.",
        "Exact arithmetic and model-based tail probabilities do not authenticate history, validate the test model, or authorize a cognitive name by themselves.",
        "No mechanism claim is authorized by this policy alone, and no latency superiority or end-to-end duration may be inferred from component spans.",
    ],
}


class CognitiveInferencePolicyFreeze(unittest.TestCase):
    def test_complete_primary_test_and_claim_boundaries_are_frozen_before_heldout(self):
        self.assertTrue(POLICY.is_file(), "pre-heldout inference policy is missing")
        self.assertEqual(json.loads(POLICY.read_text(encoding="utf-8")), EXPECTED)


if __name__ == "__main__":
    unittest.main()
