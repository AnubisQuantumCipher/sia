"""Causal contracts for joint-activity updates and explicit retrieval hygiene.

Primary author source: Gerstner, Kistler, Naud & Paninski, Neuronal Dynamics,
section 19.2.1, equation 19.3 and the paragraph following equation 19.4:
https://neuronaldynamics.epfl.ch/online/Ch19.S2.html
The local bilinear term requires joint pre/post activity. The basic positive
rule does not itself weaken weights. Applying its product to a delivered
result set is an explicit event discretization, not neural measurement.

Discrete elapsed-period retention, thresholds, exclusions, and symmetric
degree caps are separate engineering hygiene, not continuous learning
dynamics. These tests establish neither biology nor a held-out retrieval win.

Derived numeric fixtures below were routed through JACKAL before writing;
status=exact is rational arithmetic outside the Lean certificate chain.
Local floating-point software output does not inherit that assurance.
"""

import copy
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

# Explicit fixture choices, not production defaults or tuned parameters.
POLICY = {
    "v": 1, "algorithm": "joint-activity-product-v1",
    "time_unit": "unix-seconds-integer", "learning_rate": 0.5,
    "excluded_subjects": [],
    "hygiene": {"algorithm": "elapsed-period-retention-v1", "period_seconds": 2,
                "retention_per_period": 0.5, "weight_floor": 0,
                "degree_cap": 256, "cap_order": "weight-desc-pair-id"},
    "max_nodes": 256, "max_deliveries": 4096, "max_activities_per_delivery": 256,
    "max_total_activities": 4096, "max_pair_updates": 4096,
    "max_pairs": 4096, "max_graph_edges": 4096,
}
SPREAD_POLICY = {
    "v": 1, "algorithm": "typed-fan-pulse-v1", "steps": 1,
    "hop_attenuation": 0.5, "type_gains": {"coreturn": 1},
    "fanout_limit": 256, "fanout_order": "edge-id", "score_mode": "received-sum",
    "candidate_scope": "positive-received", "tie_break": "node-input-order",
    "max_nodes": 256, "max_edges": 4096, "max_seeds": 256, "max_transfers": 4096,
}
COMMON_NON_CLAIMS = [
    "computed-unverified is a local floating-point software result, not a JACKAL assurance class or proof.",
    "Supplied delivery completeness, activity values, and timestamps are caller premises; hashes do not authenticate them.",
    "Learned co-retrieval adjacency is retrieval-only and does not establish the truth or origin of any page.",
    "Original content and origin labels remain unchanged.",
    "No biological learning mechanism or held-out retrieval improvement is established.",
]
DIRECT_NON_CLAIMS = COMMON_NON_CLAIMS + [
    "Joint-activity multiplication supplies only a local positive update, not a complete learning or forgetting model.",
]
LEARNING_NON_CLAIMS = COMMON_NON_CLAIMS + [
    "Mapping delivered activity to symmetric pair updates is an engineering event discretization, not measured neural activity.",
    "Floor-period retention, pruning thresholds, exclusions, and degree caps are explicit engineering hygiene, not the published continuous learning dynamics.",
    "Only the complete supplied delivery trace is reconstructed; no hidden initial weights or unreported history are included.",
    "The emitted graph is the complete policy-retained learned projection, not the factual corpus graph or the unpruned association population.",
]
EXACT_NON_CLAIMS = [
    "NOT formal-bounded: this lane carries no Lean-checked certificate",
    "The epistemic class above is the STRONGEST claim this result supports",
    "exact rational arithmetic (not yet checker-covered)",
]
JACKAL_FIXTURES = [
    {
        "approx": "0.5",
        "exact": "1/2",
        "parsed": "1/2*1*1",
        "status": "exact"
    },
    {
        "approx": "0.25",
        "exact": "1/4",
        "parsed": "1/2*1*(1/2)",
        "status": "exact"
    },
    {
        "approx": "0",
        "exact": "0",
        "parsed": "1/2*0*1",
        "status": "exact"
    },
    {
        "approx": "0",
        "exact": "0",
        "parsed": "1/2*1*0",
        "status": "exact"
    },
    {
        "approx": "2",
        "exact": "2",
        "parsed": "(100-96)/2",
        "status": "exact"
    },
    {
        "approx": "1",
        "exact": "1",
        "parsed": "(98-96)/2",
        "status": "exact"
    },
    {
        "approx": "0",
        "exact": "0",
        "parsed": "(100-100)/2",
        "status": "exact"
    },
    {
        "approx": "1",
        "exact": "1",
        "parsed": "(100-98)/2",
        "status": "exact"
    },
    {
        "approx": "0.125",
        "exact": "1/8",
        "parsed": "1/2*(1/2)^2",
        "status": "exact"
    },
    {
        "approx": "0.25",
        "exact": "1/4",
        "parsed": "1/2*(1/2)^1",
        "status": "exact"
    },
    {
        "approx": "0.5",
        "exact": "1/2",
        "parsed": "1/2*(1/2)^0",
        "status": "exact"
    },
    {
        "approx": "1",
        "exact": "1",
        "parsed": "1/2+1/2",
        "status": "exact"
    },
    {
        "approx": "0.25",
        "exact": "1/4",
        "parsed": "1/8+1/8",
        "status": "exact"
    },
    {
        "approx": "1",
        "exact": "1",
        "parsed": "1/2*1*2",
        "status": "exact"
    },
    {
        "approx": "2",
        "exact": "2",
        "parsed": "1/2*2*2",
        "status": "exact"
    },
    {
        "approx": "257",
        "exact": "257",
        "parsed": "256+1",
        "status": "exact"
    },
    {
        "approx": "4097",
        "exact": "4097",
        "parsed": "4096+1",
        "status": "exact"
    },
    {
        "approx": "9007199254740992.0",
        "exact": "9007199254740992",
        "parsed": "9007199254740991+1",
        "status": "exact"
    },
    {
        "approx": "4",
        "exact": "4",
        "parsed": "100-96",
        "status": "exact"
    },
    {
        "approx": "2",
        "exact": "2",
        "parsed": "100-98",
        "status": "exact"
    },
    {
        "approx": "0",
        "exact": "0",
        "parsed": "100-100",
        "status": "exact"
    },
    {
        "approx": "0.25",
        "exact": "1/4",
        "parsed": "(1/2)^2",
        "status": "exact"
    },
    {
        "approx": "0.5",
        "exact": "1/2",
        "parsed": "(1/2)^1",
        "status": "exact"
    },
    {
        "approx": "1",
        "exact": "1",
        "parsed": "(1/2)^0",
        "status": "exact"
    },
    {
        "approx": "0.25",
        "exact": "1/4",
        "parsed": "1/2*1/2",
        "status": "exact"
    },
    {
        "approx": "0",
        "exact": "1/10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
        "parsed": "(1/10^200)^2",
        "status": "exact"
    },
    {
        "approx": "0",
        "exact": "1/10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
        "parsed": "1/10^200*1/10^200*1",
        "status": "exact"
    },
    {
        "approx": "9007199254740990",
        "exact": "9007199254740990",
        "parsed": "9007199254740991-1",
        "status": "exact"
    },
    {
        "approx": "1",
        "exact": "1",
        "parsed": "9007199254740991-9007199254740990",
        "status": "exact"
    },
    {
        "approx": "101",
        "exact": "101",
        "parsed": "100+1",
        "status": "exact"
    },
    {
        "approx": "0.25",
        "exact": "1/4",
        "parsed": "1*(1/2)*1/(1+1)",
        "status": "exact"
    }
]


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _delivery(identity, timestamp, activities):
    return {"id": identity, "timestamp": timestamp, "complete": True,
            "source_sha256": _sha({"delivery": identity}),
            "activities": [{"id": subject, "activation": activity} for subject, activity in activities.items()]}


def _trace(deliveries):
    return {"v": 1, "complete": True,
            "nodes": [{"id": "events/a", "origin": "evidence"},
                      {"id": "events/b", "origin": "model"},
                      {"id": "events/c", "origin": "derived"}],
            "deliveries": deliveries}


def _policy(*, hygiene=None, **changes):
    policy = copy.deepcopy(POLICY)
    if hygiene is not None:
        policy["hygiene"].update(hygiene)
    policy.update(changes)
    return policy


class CoretrievalLearningContract(unittest.TestCase):
    def setUp(self):
        try:
            self.component = importlib.import_module("siacoretrieval")
        except ModuleNotFoundError as exc:
            self.fail(f"joint-activity and discrete hygiene component must exist: {exc}")

    def _learn(self, trace, *, observed_at=100, policy=None):
        return self.component.learn_coretrieval(trace, observed_at=observed_at,
                                               policy=copy.deepcopy(POLICY) if policy is None else policy)

    def _increment(self, **changes):
        values = {"learning_rate": 0.5, "pre_activity": 1, "post_activity": 1}
        values.update(changes)
        return self.component.pair_increment(**values)

    def test_public_contract_has_no_hidden_rate_clock_history_or_hygiene_defaults(self):
        signature = inspect.signature(self.component.pair_increment)
        for name in ("learning_rate", "pre_activity", "post_activity"):
            self.assertIs(signature.parameters[name].default, inspect.Parameter.empty)
            self.assertEqual(signature.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)
        signature = inspect.signature(self.component.learn_coretrieval)
        for name in ("observed_at", "policy"):
            self.assertIs(signature.parameters[name].default, inspect.Parameter.empty)
            self.assertEqual(signature.parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)
        for key in POLICY:
            policy = _policy()
            del policy[key]
            with self.subTest(missing=key), self.assertRaises(self.component.CoretrievalRefusal):
                self._learn(_trace([]), policy=policy)
        for key in POLICY["hygiene"]:
            policy = _policy()
            del policy["hygiene"][key]
            with self.subTest(missing_hygiene=key), self.assertRaises(self.component.CoretrievalRefusal):
                self._learn(_trace([]), policy=policy)

    def test_literal_joint_activity_product_requires_both_sides_and_keeps_input_binding(self):
        result = self._increment()
        self.assertEqual(result["delta"], 0.5)
        self.assertIs(type(result["delta"]), float)
        self.assertEqual(result["status"], "computed-unverified")
        self.assertEqual(set(result), {"v", "component", "status", "delta", "input_sha256", "non_claims"})
        self.assertEqual(result["component"], "joint-activity-increment")
        self.assertEqual(result["input_sha256"], _sha({"learning_rate": 0.5, "pre_activity": 1, "post_activity": 1}))
        self.assertEqual(result["non_claims"], DIRECT_NON_CLAIMS)
        self.assertEqual(self._increment(pre_activity=0)["delta"], 0.0)
        self.assertEqual(self._increment(post_activity=0)["delta"], 0.0)
        self.assertEqual(self._increment(post_activity=0.5)["delta"], 0.25)
        self.assertEqual(self._increment(pre_activity=2, post_activity=2)["delta"], 2.0)
        self.assertNotEqual(self._increment(pre_activity=1.0)["input_sha256"], result["input_sha256"])
        self.assertNotIn("Hebbian", json.dumps(result))

    def test_same_delivery_creates_symmetric_new_pair_and_distinct_repetition_strengthens(self):
        event = _delivery("delivery-one", 100, {"events/b": 1, "events/a": 1})
        once = self._learn(_trace([event]), policy=_policy(hygiene={"retention_per_period": 1}))
        twice_trace = _trace([event, _delivery("delivery-two", 100, {"events/a": 1, "events/b": 1})])
        twice = self._learn(twice_trace, policy=_policy(hygiene={"retention_per_period": 1}))
        self.assertEqual(once["pairs"][0]["raw_weight"], 0.5)
        self.assertEqual(twice["pairs"][0]["raw_weight"], 1.0)
        self.assertEqual(twice["pairs"][0]["weight"], 1.0)
        self.assertGreater(twice["pairs"][0]["weight"], once["pairs"][0]["weight"])
        pair = twice["pairs"][0]
        self.assertEqual((pair["a"], pair["b"]), ("events/a", "events/b"))
        self.assertEqual([item["delivery_id"] for item in pair["contributions"]], ["delivery-one", "delivery-two"])
        self.assertEqual({(edge["s"], edge["d"], edge["weight"]) for edge in twice["graph"]["edges"]},
                         {("events/a", "events/b", 1.0), ("events/b", "events/a", 1.0)})
        self.assertEqual(len({edge["id"] for edge in twice["graph"]["edges"]}), len(twice["graph"]["edges"]))

    def test_unilateral_different_deliveries_and_zero_activity_do_not_invent_joint_use(self):
        deliveries = [_delivery("only-a", 96, {"events/a": 1}),
                      _delivery("only-b", 96, {"events/b": 1}),
                      _delivery("zero-b", 98, {"events/a": 1, "events/b": 0}),
                      _delivery("empty", 100, {})]
        result = self._learn(_trace(deliveries))
        self.assertEqual(result["pairs"], [])
        self.assertEqual(result["graph"]["edges"], [])
        self.assertEqual([row["id"] for row in result["delivery_witnesses"]], [row["id"] for row in deliveries])
        self.assertEqual([row["delivery_sha256"] for row in result["delivery_witnesses"]], [_sha(row) for row in deliveries])
        self.assertEqual(result["delivery_witnesses"][2]["zero_subjects"], ["events/b"])
        self.assertEqual(result["delivery_witnesses"][2]["eligible_subjects"], ["events/a"])
        self.assertEqual(result["delivery_witnesses"][3]["eligible_subjects"], [])

    def test_elapsed_hygiene_is_discrete_and_replay_depends_on_observation_not_call_count(self):
        event = _delivery("old", 96, {"events/a": 1, "events/b": 1})
        trace = _trace([event])
        before = copy.deepcopy(trace)
        at_delivery = self._learn(trace, observed_at=96)
        later = self._learn(trace, observed_at=98)
        latest = self._learn(trace, observed_at=100)
        self.assertEqual(at_delivery["pairs"][0]["weight"], 0.5)
        self.assertEqual(later["pairs"][0]["weight"], 0.25)
        self.assertEqual(latest["pairs"][0]["weight"], 0.125)
        within_period = self._learn(trace, observed_at=99)["pairs"][0]
        self.assertEqual(within_period["weight"], later["pairs"][0]["weight"])
        self.assertEqual(within_period["contributions"][0]["elapsed_periods"],
                         later["pairs"][0]["contributions"][0]["elapsed_periods"])
        self.assertEqual(self._learn(trace, observed_at=100), latest)
        self.assertEqual(trace, before)
        self.assertEqual(latest["pairs"][0]["contributions"], [{
            "delivery_id": "old", "delivery_sha256": _sha(event), "timestamp": 96,
            "age_seconds": 4, "elapsed_periods": 2, "raw_increment": 0.5,
            "retention_multiplier": 0.25, "increment": 0.125,
        }])

    def test_frequency_and_recency_remain_separate_causes_under_fixed_hygiene(self):
        old = _delivery("old", 96, {"events/a": 1, "events/b": 1})
        repeated = _delivery("again", 96, {"events/a": 1, "events/b": 1})
        recent = _delivery("recent", 98, {"events/a": 1, "events/b": 1})
        baseline = self._learn(_trace([old]))
        frequency = self._learn(_trace([old, repeated]))
        recency = self._learn(_trace([recent]))
        self.assertEqual(frequency["pairs"][0]["weight"], 0.25)
        self.assertEqual(recency["pairs"][0]["weight"], 0.25)
        self.assertGreater(frequency["pairs"][0]["weight"], baseline["pairs"][0]["weight"])
        self.assertGreater(recency["pairs"][0]["weight"], baseline["pairs"][0]["weight"])

    def test_complete_witness_roster_binds_policy_trace_graph_and_all_pair_contributions(self):
        event = _delivery("joint", 100, {"events/a": 1, "events/b": 1})
        trace = _trace([event])
        result = self._learn(trace)
        self.assertEqual(set(result), {"v", "component", "status", "observed_at", "trace_sha256",
                                      "policy_sha256", "graph", "graph_sha256", "pairs", "delivery_witnesses", "non_claims"})
        self.assertEqual(result["component"], "co-retrieval-strengthening")
        self.assertEqual(result["status"], "computed-unverified")
        self.assertEqual(result["observed_at"], 100)
        self.assertEqual(result["trace_sha256"], _sha(trace))
        self.assertEqual(result["policy_sha256"], _sha(POLICY))
        self.assertEqual(result["graph_sha256"], _sha(result["graph"]))
        self.assertEqual(result["non_claims"], LEARNING_NON_CLAIMS)
        self.assertEqual(result["delivery_witnesses"], [{
            "id": "joint", "timestamp": 100, "delivery_sha256": _sha(event),
            "eligible_subjects": ["events/a", "events/b"], "zero_subjects": [],
            "excluded_subjects": [], "pairs": [["events/a", "events/b"]],
        }])
        pair = result["pairs"][0]
        self.assertEqual(set(pair), {"a", "b", "raw_weight", "weight", "last_use", "contributions", "retained", "reason"})
        self.assertTrue(pair["retained"])
        self.assertIsNone(pair["reason"])
        self.assertEqual(pair["last_use"], 100)
        self.assertNotIn("Hebbian", json.dumps(result))

    def test_floor_prunes_only_after_complete_sum_and_records_nonretained_weight(self):
        first = _delivery("old-one", 96, {"events/a": 1, "events/b": 1})
        second = _delivery("old-two", 96, {"events/a": 1, "events/b": 1})
        policy = _policy(hygiene={"weight_floor": 0.25})
        one = self._learn(_trace([first]), policy=policy)
        two = self._learn(_trace([first, second]), policy=policy)
        self.assertEqual(one["graph"]["edges"], [])
        self.assertEqual(one["pairs"][0]["weight"], 0.125)
        self.assertFalse(one["pairs"][0]["retained"])
        self.assertEqual(one["pairs"][0]["reason"], "below-floor")
        self.assertEqual(two["pairs"][0]["weight"], 0.25)
        self.assertTrue(two["pairs"][0]["retained"])
        self.assertIsNone(two["pairs"][0]["reason"])

    def test_degree_cap_is_symmetric_weight_first_stable_on_ties_and_keeps_pruned_witness(self):
        weak = _delivery("weak-first", 100, {"events/a": 1, "events/c": 1})
        strong = _delivery("strong-later", 100, {"events/a": 1, "events/b": 2})
        policy = _policy(hygiene={"degree_cap": 1})
        result = self._learn(_trace([weak, strong]), policy=policy)
        self.assertEqual({(edge["s"], edge["d"]) for edge in result["graph"]["edges"]},
                         {("events/a", "events/b"), ("events/b", "events/a")})
        rejected = next(pair for pair in result["pairs"] if pair["b"] == "events/c")
        self.assertEqual(rejected["reason"], "degree-cap")
        self.assertEqual(rejected["weight"], 0.5)
        self.assertEqual(rejected["contributions"][0]["delivery_id"], "weak-first")
        tied = _delivery("tie-later", 100, {"events/a": 1, "events/b": 1})
        forward = self._learn(_trace([weak, tied]), policy=policy)
        reverse = self._learn(_trace([tied, weak]), policy=policy)
        self.assertEqual(forward["graph"], reverse["graph"])
        self.assertEqual({edge["d"] for edge in forward["graph"]["edges"]}, {"events/a", "events/b"})

    def test_exclusions_preserve_every_delivery_boundary_and_the_entire_original_node_roster(self):
        event = _delivery("excluded", 100, {"events/a": 1, "events/b": 1, "events/c": 0})
        trace = _trace([event])
        result = self._learn(trace, policy=_policy(excluded_subjects=["events/b"]))
        self.assertEqual(result["pairs"], [])
        self.assertEqual(result["graph"]["edges"], [])
        self.assertEqual(result["graph"]["nodes"], trace["nodes"])
        self.assertEqual(result["delivery_witnesses"], [{
            "id": "excluded", "timestamp": 100, "delivery_sha256": _sha(event),
            "eligible_subjects": ["events/a"], "zero_subjects": ["events/c"],
            "excluded_subjects": ["events/b"], "pairs": [],
        }])

    def test_learned_only_connection_changes_later_reachability_without_origin_promotion(self):
        spreading = importlib.import_module("siaspreading")
        seeds = [{"id": "events/a", "activation": 1, "source_sha256": _sha({"seed": "events/a"})}]
        empty = self._learn(_trace([]))
        learned = self._learn(_trace([_delivery("joint", 100, {"events/a": 1, "events/b": 1})]))
        self.assertEqual(spreading.spread(empty["graph"], seeds, policy=SPREAD_POLICY)["order"], [])
        result = spreading.spread(learned["graph"], seeds, policy=SPREAD_POLICY)
        self.assertEqual(result["order"], ["events/b"])
        self.assertEqual(result["rows"][0]["origin"], "model")
        self.assertEqual(result["rows"][0]["scope"], "retrieval-only")
        self.assertIs(learned["graph"]["complete"], True)
        for edge in learned["graph"]["edges"]:
            self.assertEqual(edge["t"], "coreturn")
            self.assertEqual(edge["provenance"], "learned-coreturn")
            self.assertEqual(edge["scope"], "retrieval-only")

    def test_duplicate_or_incomplete_delivery_identity_cannot_be_silently_deduped(self):
        event = _delivery("delivery", 96, {"events/a": 1, "events/b": 1})
        variants = [
            _trace([event, copy.deepcopy(event)]),
            _trace([event, {**copy.deepcopy(event), "timestamp": 98}]),
            _trace([{**event, "complete": False}]), _trace([{**event, "complete": 1}]),
            {**_trace([event]), "complete": False},
            {**_trace([event]), "initial_weights": {"events/a|events/b": 1}},
            {**_trace([event]), "nodes": [{"id": "events/a", "origin": "verified"}]},
            _trace([{**event, "weight": 2}]),
            _trace([{**event, "source_sha256": "unbound"}]),
            _trace([{**event, "activities": event["activities"] + [event["activities"][0]]}]),
        ]
        for trace in variants:
            with self.subTest(trace=repr(trace)), self.assertRaises(self.component.CoretrievalRefusal):
                self._learn(trace)

    def test_all_timestamps_are_exact_nonfuture_seconds_and_integer_subtraction_precedes_float(self):
        for value in (True, 100.0, "100", "2026-09-05T01:00:00", None, -1,
                      float("nan"), float("inf"), 9007199254740992):
            with self.subTest(value=repr(value)):
                with self.assertRaises(self.component.CoretrievalRefusal):
                    self._learn(_trace([]), observed_at=value)
                with self.assertRaises(self.component.CoretrievalRefusal):
                    self._learn(_trace([_delivery("bad", value, {"events/a": 1, "events/b": 1})]))
        future = _trace([_delivery("future", 101, {"events/a": 1, "events/b": 1})])
        reversed_time = _trace([_delivery("later", 98, {}), _delivery("earlier", 96, {})])
        for trace in (future, reversed_time):
            with self.assertRaises(self.component.CoretrievalRefusal):
                self._learn(trace)
        event = _delivery("near-limit", 9007199254740990, {"events/a": 1, "events/b": 1})
        result = self._learn(_trace([event]), observed_at=9007199254740991,
                             policy=_policy(hygiene={"period_seconds": 1}))
        self.assertEqual(result["pairs"][0]["weight"], 0.25)
        self.assertEqual(result["pairs"][0]["contributions"][0]["age_seconds"], 1)

    def test_bounded_finite_policy_and_activity_validation_occurs_before_copy_or_serialization(self):
        for parameter in ("learning_rate", "pre_activity", "post_activity"):
            for value in (-1, True, "1", float("nan"), float("inf"), 1e308):
                with self.subTest(parameter=parameter, value=repr(value)), self.assertRaises(self.component.CoretrievalRefusal):
                    self._increment(**{parameter: value})
        with self.assertRaises(self.component.CoretrievalRefusal):
            self._increment(learning_rate=0)
        event = _delivery("good", 96, {"events/a": 1, "events/b": 1})
        invalid = _delivery("late-invalid", 98, {"events/a": 1, "events/b": 1})
        invalid["activities"][1]["activation"] = float("nan")
        policy = _policy()
        with mock.patch.object(self.component.json, "dumps", side_effect=AssertionError("serialized before complete admission")):
            with self.assertRaises(self.component.CoretrievalRefusal):
                self.component.learn_coretrieval(_trace([event, invalid]), observed_at=100, policy=policy)
        for key, value in (("period_seconds", 0), ("period_seconds", True), ("period_seconds", 1.0),
                           ("retention_per_period", 0), ("retention_per_period", -1), ("retention_per_period", 2),
                           ("retention_per_period", float("nan")), ("weight_floor", -1),
                           ("weight_floor", float("inf")), ("degree_cap", 0), ("degree_cap", 257),
                           ("cap_order", "arrival-order"), ("algorithm", "per-call-decay")):
            with self.subTest(hygiene=key, value=repr(value)), self.assertRaises(self.component.CoretrievalRefusal):
                self._learn(_trace([event]), policy=_policy(hygiene={key: value}))
        for exclusions in (["events/b", "events/b"], ["events/unknown"], "events/b", [True]):
            with self.subTest(exclusions=exclusions), self.assertRaises(self.component.CoretrievalRefusal):
                self._learn(_trace([event]), policy=_policy(excluded_subjects=exclusions))

    def test_positive_retention_and_joint_update_underflow_refuse_even_if_floor_would_drop_pair(self):
        # Exact rational fixtures are nonzero; their approximate field is zero.
        # Python binary floats are separately unverified inputs, not those exact rationals.
        with self.assertRaisesRegex(self.component.CoretrievalRefusal, "underflow"):
            self._increment(learning_rate=1e-200, pre_activity=1e-200)
        trace = _trace([_delivery("old", 96, {"events/a": 1, "events/b": 1})])
        with self.assertRaisesRegex(self.component.CoretrievalRefusal, "underflow"):
            self._learn(trace, policy=_policy(hygiene={"retention_per_period": 1e-200, "weight_floor": 1}))

    def test_complete_capacity_refuses_before_truncation_including_reciprocal_graph_projection(self):
        event = _delivery("one", 100, {"events/a": 1, "events/b": 1})
        next_event = _delivery("two", 100, {"events/a": 1, "events/c": 1})
        for key, value in (("max_nodes", 257), ("max_deliveries", 4097),
                           ("max_activities_per_delivery", 257), ("max_total_activities", 4097),
                           ("max_pair_updates", 4097), ("max_pairs", 4097), ("max_graph_edges", 4097)):
            with self.subTest(key=key), self.assertRaises(self.component.CoretrievalRefusal):
                self._learn(_trace([]), policy=_policy(**{key: value}))
        for changes in ({"max_nodes": 1}, {"max_deliveries": 1}, {"max_activities_per_delivery": 1},
                        {"max_total_activities": 2}, {"max_pair_updates": 1}, {"max_pairs": 1},
                        {"max_graph_edges": 1}):
            with self.subTest(changes=changes), self.assertRaises(self.component.CoretrievalRefusal):
                self._learn(_trace([event, next_event]), policy=_policy(**changes))

    def test_entire_original_content_origin_and_input_policy_are_immutable_and_results_detached(self):
        pages = {"events/a": {"text": "Original é漢😀 bytes.\n", "origin": "evidence"},
                 "events/b": {"text": "An attributed agent statement.\n", "origin": "model"},
                 "events/c": {"text": "Derived content stays derived.\n", "origin": "derived"}}
        trace = _trace([_delivery("delivery", 100, {"events/a": 1, "events/b": 1})])
        policy = _policy()
        before = copy.deepcopy((pages, trace, policy))
        result = self._learn(trace, policy=policy)
        self.assertEqual(result["graph"]["nodes"], trace["nodes"])
        result["graph"]["nodes"][0]["origin"] = "rewritten-output"
        result["pairs"][0]["contributions"].clear()
        result["delivery_witnesses"][0]["eligible_subjects"].clear()
        result["non_claims"].clear()
        self.assertEqual((pages, trace, policy), before)
        self.assertEqual(self._learn(trace, policy=policy)["non_claims"], LEARNING_NON_CLAIMS)


if __name__ == "__main__":
    unittest.main()
