"""Contract for explicit, descriptive power-law use-trace ranking.

Literature: Anderson & Schunn (2000), "Implications of the ACT-R Learning
Theory: No Magic Bullets", manuscript p. 8, Base-Level Equation:
https://act-r.psy.cmu.edu/wordpress/wp-content/uploads/2012/12/39jra_cds_2000_a.pdf
The sum includes every past presentation's decaying contribution, then takes
the natural logarithm. Context spreading, noise, thresholds and latency are
separate mechanisms, not silently included in this component.

Numeric fixture inputs below were routed through JACKAL before writing. The
retained rational sums have status=exact, outside the Lean certificate chain;
the subsequent ln(x) enclosures have status=formal-bounded/checker ACCEPT for
those supplied rational inputs. Neither status is the software's assurance.
"""

import copy
from fractions import Fraction
import hashlib
import importlib
import inspect
import json
import math
from pathlib import Path
import sys
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "bin"))

# Explicit test policies, not selected production parameters or defaults.
# Capacity ceilings reuse admitted local protocol bounds as engineering limits.
POLICY = {
    "v": 1, "algorithm": "log-sum-power-law-v1", "time_unit": "unix-seconds-integer",
    "decay": 1, "age_offset_seconds": 0, "tie_break": "stable-input-order",
    "unavailable": "last", "max_uses": 4096, "max_total_uses": 4096,
    "max_candidates": 256,
}
NON_CLAIMS = [
    "computed-unverified is a local floating-point software result, not a JACKAL assurance class or proof.",
    "Trace completeness is a caller admission premise; hashes bind supplied records but do not authenticate their history.",
    "Positive age offsets are an explicit engineering regularization, not the strict positive-age literature equation.",
    "The component changes only candidate order; it does not rewrite original content or origin labels.",
    "No human-memory mechanism, retrieval probability, latency prediction, or held-out retrieval improvement is established.",
]
EXACT_NON_CLAIMS = [
    "NOT formal-bounded: this lane carries no Lean-checked certificate",
    "The epistemic class above is the STRONGEST claim this result supports",
    "exact rational arithmetic (not yet checker-covered)",
]
LN_NON_CLAIMS = [
    "NOT universal correctness across all operators or expressions",
    "ln_rat admits ONLY the exact form `ln(x)` on a canonical rational interval with 0 < lo",
    "Nonpositive lower endpoints FAIL CLOSED (log domain)",
    "Every other transcendental operator FAIL CLOSED on this variant",
    "The Python ln_rat producer is untrusted; formal release requires independent checker ACCEPT",
    "SHA-256 identifies bytes; it does NOT authenticate an author",
    "The artifact is unsigned and has not received an independent external proof audit",
]
FIXTURES = {
    "uneven": {"parsed": "(100-96)^-1+(100-99)^-1", "exact": "5/4",
               "lo": "111571775157/500000000000", "hi": "111571776157/500000000000",
               "receipt_sha256": "03056e81a13d80498e2cb558f186b648e0bad418f9397cb4c14927d6c0780605"},
    "older": {"parsed": "(100-96)^-1", "exact": "1/4",
              "lo": "-34657359053/25000000000", "hi": "-34657359003/25000000000",
              "receipt_sha256": "ccdd49e874345b468379b52283dd9ae215e4b297b91f8d0ba530d97495c977ad"},
    "more": {"parsed": "(100-96)^-1+(100-96)^-1", "exact": "1/2",
             "lo": "-17328679539/25000000000", "hi": "-17328679489/25000000000",
             "receipt_sha256": "bd3a66e91a0add13f85a8887aad1e3c79a75436f4e7c8ded2c505462ccde6465"},
    "recent": {"parsed": "(100-99)^-1", "exact": "1",
               "lo": "-1/1000000000", "hi": "1/1000000000",
               "receipt_sha256": "473d0cef25779ea257a4faad652a4586fdc92393964c0d6c259dc23eee8b509f"},
    "decay_two": {"parsed": "(100-96)^-2+(100-99)^-2", "exact": "17/16",
                  "lo": "3789038801/62500000000", "hi": "1894519463/31250000000",
                  "receipt_sha256": "47c8843082dc404504fda3f99a4a780aaf1b9e443d17be9380c46b10bb9a2d4d"},
    "offset": {"parsed": "(100-100+1)^-1", "exact": "1",
               "lo": "-1/1000000000", "hi": "1/1000000000",
               "receipt_sha256": "f94e7299d450b0e931b055bc7638964f65dbda84d6f81f7768a3d91323512833"},
}


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _trace(times, subject="events/alpha"):
    return {"v": 1, "subject": subject, "complete": True,
            "uses": [{"id": f"delivery-{index}", "timestamp": stamp} for index, stamp in enumerate(times)]}


class UseTraceActivation(unittest.TestCase):
    def setUp(self):
        try:
            self.component = importlib.import_module("siaactivation")
        except ModuleNotFoundError as exc:
            self.fail(f"explicit power-law use-trace component must exist: {exc}")

    def _evaluate(self, trace, *, observed_at=100, policy=None):
        # This test helper's convenience values are never production defaults.
        return self.component.evaluate_trace(trace, observed_at=observed_at,
                                             policy=copy.deepcopy(POLICY) if policy is None else policy)

    def _enclosed(self, result, name):
        self.assertEqual(result["status"], "computed-unverified")
        self.assertIs(type(result["score"]), float)
        self.assertTrue(math.isfinite(result["score"]))
        score = Fraction.from_float(result["score"])
        self.assertGreaterEqual(score, Fraction(FIXTURES[name]["lo"]))
        self.assertLessEqual(score, Fraction(FIXTURES[name]["hi"]))

    def test_public_api_requires_observation_time_and_every_policy_field(self):
        for name in ("evaluate_trace", "rank_traces"):
            signature = inspect.signature(getattr(self.component, name))
            for parameter in ("observed_at", "policy"):
                self.assertIs(signature.parameters[parameter].default, inspect.Parameter.empty)
                self.assertEqual(signature.parameters[parameter].kind, inspect.Parameter.KEYWORD_ONLY)
        for key in POLICY:
            policy = copy.deepcopy(POLICY)
            del policy[key]
            with self.subTest(missing=key), self.assertRaises(self.component.ActivationRefusal):
                self._evaluate(_trace([96]), policy=policy)

    def test_sum_of_every_actual_use_is_logged_without_tail_or_last_use_approximation(self):
        trace = _trace([96, 99])
        result = self._evaluate(trace)
        self._enclosed(result, "uneven")
        self.assertEqual(set(result), {"v", "component", "status", "subject", "observed_at", "score",
                                      "reason", "uses_count", "trace_sha256", "policy_sha256", "variant", "non_claims"})
        self.assertEqual(result["component"], "usage-salience")
        self.assertEqual(result["subject"], trace["subject"])
        self.assertEqual(result["uses_count"], len(trace["uses"]))
        self.assertEqual(result["trace_sha256"], _sha(trace))
        self.assertEqual(result["policy_sha256"], _sha(POLICY))
        self.assertEqual(result["observed_at"], 100)
        self.assertEqual(result["variant"], "strict-positive-age")
        self.assertIsNone(result["reason"])
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertNotIn("ACT-R", json.dumps(result))

    def test_frequency_and_recency_have_separate_causal_effects(self):
        older = self._evaluate(_trace([96]))
        more = self._evaluate(_trace([96, 96]))
        recent = self._evaluate(_trace([99]))
        for name, result in (("older", older), ("more", more), ("recent", recent)):
            self._enclosed(result, name)
        self.assertGreater(more["score"], older["score"])
        self.assertGreater(recent["score"], older["score"])

    def test_declared_decay_changes_the_actual_power_law_not_an_additive_bonus(self):
        trace = _trace([96, 99])
        policy = {**POLICY, "decay": 2}
        result = self._evaluate(trace, policy=policy)
        self._enclosed(result, "decay_two")
        self.assertEqual(result["policy_sha256"], _sha(policy))
        self.assertNotEqual(result["policy_sha256"], _sha(POLICY))
        self.assertLess(result["score"], self._evaluate(trace)["score"])

    def test_no_trace_has_no_finite_activation_and_incomplete_trace_is_not_zero_use(self):
        trace = _trace([])
        result = self._evaluate(trace)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["score"])
        self.assertEqual(result["reason"], "no-use-history")
        self.assertEqual(result["uses_count"], len(trace["uses"]))
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        for uses in ([], [{"id": "known-use", "timestamp": 96}]):
            for complete in (False, None, 1, "true"):
                bad = {**trace, "uses": uses, "complete": complete}
                with self.subTest(complete=complete), self.assertRaises(self.component.ActivationRefusal):
                    self._evaluate(bad)

    def test_zero_age_refuses_without_offset_and_positive_offset_is_explicitly_distinguished(self):
        with self.assertRaisesRegex(self.component.ActivationRefusal, "zero-age"):
            self._evaluate(_trace([100]))
        policy = {**POLICY, "age_offset_seconds": 1}
        result = self._evaluate(_trace([100]), policy=policy)
        self._enclosed(result, "offset")
        self.assertEqual(result["variant"], "positive-age-offset")
        self.assertEqual(result["policy_sha256"], _sha(policy))
        # JACKAL status=exact parsed=100+1 exact=101; offset cannot excuse future input.
        with self.assertRaisesRegex(self.component.ActivationRefusal, "future"):
            self._evaluate(_trace([101]), policy=policy)

    def test_observation_and_use_times_reject_ambiguity_before_numerical_work(self):
        # JACKAL status=exact parsed=9007199254740991+1 exact=9007199254740992.
        bad_times = (True, 100.0, "100", "2026-09-05T01:00:00", "2026-09-05T01:00:00Z",
                     None, -1, float("inf"), float("nan"), 9007199254740992)
        for value in bad_times:
            with self.subTest(value=repr(value)):
                with self.assertRaises(self.component.ActivationRefusal):
                    self._evaluate(_trace([96]), observed_at=value)
                with self.assertRaises(self.component.ActivationRefusal):
                    self._evaluate(_trace([value]))

    def test_duplicate_identity_reverse_order_and_aggregate_or_weighted_histories_refuse(self):
        duplicate = _trace([96, 96])
        duplicate["uses"][1]["id"] = duplicate["uses"][0]["id"]
        weighted = _trace([96])
        weighted["uses"][0]["weight"] = 2
        for trace in (duplicate, _trace([99, 96]), weighted,
                      {**_trace([96]), "total_count": 2}, {**_trace([96]), "tail_weight": 1},
                      {**_trace([96]), "uses": [96]}, {**_trace([96]), "origin": "evidence"},
                      {**_trace([96]), "text": "content is outside this rank-only component"}):
            before = copy.deepcopy(trace)
            with self.subTest(trace=trace), self.assertRaises(self.component.ActivationRefusal):
                self._evaluate(trace)
            self.assertEqual(trace, before)
        self._enclosed(self._evaluate(_trace([96, 96])), "more")

    def test_numeric_policies_are_finite_positive_and_bounded_without_noise_or_intercept(self):
        changes = (("decay", 0), ("decay", -1), ("decay", True), ("decay", "1"),
                   ("decay", float("nan")), ("decay", float("inf")), ("decay", 1e308),
                   ("age_offset_seconds", -1), ("age_offset_seconds", True),
                   ("age_offset_seconds", float("inf")), ("age_offset_seconds", 1e308),
                   ("time_unit", "milliseconds"), ("tie_break", "slug"), ("unavailable", "finite-sentinel"),
                   ("noise", 0), ("intercept", 0), ("v", True), ("algorithm", "last-use-only"),
                   ("max_uses", True), ("max_uses", 0), ("max_total_uses", 0), ("max_candidates", 0))
        for key, value in changes:
            with self.subTest(key=key, value=repr(value)), self.assertRaises(self.component.ActivationRefusal):
                self._evaluate(_trace([96]), policy={**POLICY, key: value})

    def test_capacity_refusal_is_not_truncation_or_approximation(self):
        # JACKAL status=exact parsed=4096+1 exact=4097; parsed=256+1 exact=257.
        for policy in ({**POLICY, "max_uses": 4097}, {**POLICY, "max_candidates": 257}):
            with self.assertRaises(self.component.ActivationRefusal):
                self._evaluate(_trace([96]), policy=policy)
        with self.assertRaises(self.component.ActivationRefusal):
            self._evaluate(_trace([96, 99]), policy={**POLICY, "max_uses": 1})
        with self.assertRaises(self.component.ActivationRefusal):
            self.component.rank_traces([_trace([96], "events/a"), _trace([99], "events/b")],
                                       observed_at=100, policy={**POLICY, "max_total_uses": 1})
        with self.assertRaises(self.component.ActivationRefusal):
            self.component.rank_traces([_trace([], "events/a"), _trace([], "events/b")],
                                       observed_at=100, policy={**POLICY, "max_candidates": 1})

    def test_rank_only_has_explicit_stable_ties_and_never_rewrites_source_content_or_origin(self):
        pages = {"events/z": {"text": "Original é漢😀 bytes.\n", "origin": "evidence"},
                 "events/a": {"text": "An attributed note.\n", "origin": "model"},
                 "events/absent": {"text": "No use history.\n", "origin": "derived"},
                 "events/recent": {"text": "Recently used.\n", "origin": "legacy-unlabeled"}}
        traces = [_trace([96], "events/z"), _trace([], "events/absent"),
                  _trace([96], "events/a"), _trace([99], "events/recent")]
        before = copy.deepcopy((pages, traces, POLICY))
        result = self.component.rank_traces(traces, observed_at=100, policy=POLICY)
        self.assertEqual(result["order"], ["events/recent", "events/z", "events/a", "events/absent"])
        self.assertEqual(set(result), {"v", "component", "status", "observed_at", "policy_sha256",
                                      "trace_set_sha256", "order", "activations", "non_claims"})
        self.assertEqual(result["status"], "computed-unverified")
        self.assertEqual(result["trace_set_sha256"], _sha(traces))
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertEqual([row["subject"] for row in result["activations"]], [trace["subject"] for trace in traces])
        reordered = [pages[subject] for subject in result["order"]]
        self.assertEqual(reordered[0], pages["events/recent"])
        self.assertEqual((pages, traces, POLICY), before)
        result["activations"][0]["non_claims"].clear()
        result["order"].clear()
        self.assertEqual((pages, traces, POLICY), before)

    def test_any_malformed_candidate_refuses_before_partial_rank_or_numeric_work(self):
        good = _trace([96], "events/a")
        bad = _trace([101], "events/b")
        before = copy.deepcopy((good, bad))
        with mock.patch.object(self.component.math, "log", side_effect=AssertionError("computed before admission")):
            with self.assertRaises(self.component.ActivationRefusal):
                self.component.rank_traces([good, bad], observed_at=100, policy=POLICY)
        self.assertEqual((good, bad), before)
        with self.assertRaises(self.component.ActivationRefusal):
            self.component.rank_traces([good, copy.deepcopy(good)], observed_at=100, policy=POLICY)

    def test_input_and_output_are_detached_and_observation_identity_is_not_ambient_clock_time(self):
        trace, policy = _trace([96, 99]), copy.deepcopy(POLICY)
        before = copy.deepcopy((trace, policy))
        result = self._evaluate(trace, policy=policy)
        other = self._evaluate(trace, observed_at=99, policy={**policy, "age_offset_seconds": 1})
        self.assertEqual(other["observed_at"], 99)
        self.assertNotEqual(other["policy_sha256"], result["policy_sha256"])
        result["non_claims"].clear()
        self.assertEqual((trace, policy), before)


if __name__ == "__main__":
    unittest.main()
