"""Causal contracts for direct cue fan association and typed graph propagation.

Primary source: Marewski & Mehlhorn (2011), section 4.2, equations 3 and 4:
https://dlab.sauder.ubc.ca/sjdm/journal/11/101112/jdm101112.html
The direct single-cue term is W * (S - ln fan), where fan counts associated
chunks. More competitors weaken a target association with W and S fixed.
Its signed value is not a probability and is not clipped at zero.

The separate finite-hop normalized pulse contract below is an engineering
extension, NOT that published equation or a complete cognitive architecture.
Its full-fan-before-cap rule makes the competing-fan prediction falsifiable.
It has no restart distribution, implicit reverse edges, or seed reinjection.

All derived numeric fixture values were routed through JACKAL before writing.
The exact rational lane is outside the Lean certificate chain. The ln(x)
enclosure is formal-bounded; transforming its endpoints used the exact lane,
not a new checked composition certificate. None certifies this Python code.
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

# Explicit fixture policies, not defaults, fitted parameters, or claimed wins.
POLICY = {
    "v": 1, "algorithm": "typed-fan-pulse-v1", "steps": 2,
    "hop_attenuation": 0.5, "type_gains": {"mentions": 1, "coreturn": 1},
    "fanout_limit": 256, "fanout_order": "edge-id",
    "score_mode": "received-sum", "candidate_scope": "positive-received",
    "tie_break": "node-input-order", "max_nodes": 256, "max_edges": 4096,
    "max_seeds": 256, "max_transfers": 4096,
}
COMMON_NON_CLAIMS = [
    "computed-unverified is a local floating-point software result, not a JACKAL assurance class or proof.",
    "Completeness is a caller admission premise; hashes bind supplied records but do not authenticate their history.",
    "Scores and transfer paths are retrieval-only signals, not evidence for the content or truth of a node.",
    "Original content and origin labels are not rewritten by this component.",
    "No human-memory mechanism or held-out retrieval improvement is established.",
]
DIRECT_NON_CLAIMS = COMMON_NON_CLAIMS + [
    "The signed direct-cue fan term is not a probability, latency prediction, or complete cognitive architecture.",
]
SPREAD_NON_CLAIMS = COMMON_NON_CLAIMS + [
    "Finite-hop normalization is an engineering extension, not the published W * (S - ln fan) association equation.",
    "Attenuation, edge-type gains, work caps, and tie policy are explicit engineering choices, not fitted cognitive parameters.",
    "Learned or retrieval-only adjacency remains retrieval-only even when it reaches an evidence-origin node.",
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
LN_FIXTURE = {
    "expression": "ln(x)", "canonical_lo": "2", "canonical_hi": "2",
    "status": "formal-bounded", "checker_rerun": "ACCEPT",
    "lo": "17328679489/25000000000", "hi": "17328679539/25000000000",
    "receipt_sha256": "f23796f6939b180674b8e5dbe9d85f660f9b65daf72a82e079766eb0224d297b",
}
# Endpoint transforms: status=exact, not formal-bounded composition claims.
DIRECT_FIXTURES = {
    "negative": {
        "parsed_lo": "0-17328679539/25000000000", "lo": "-17328679539/25000000000",
        "parsed_hi": "0-17328679489/25000000000", "hi": "-17328679489/25000000000",
    },
    "half_source": {
        "parsed_lo": "1/2*(0-17328679539/25000000000)", "lo": "-17328679539/50000000000",
        "parsed_hi": "1/2*(0-17328679489/25000000000)", "hi": "-17328679489/50000000000",
    },
    "positive_strength": {
        "parsed_lo": "1-17328679539/25000000000", "lo": "7671320461/25000000000",
        "parsed_hi": "1-17328679489/25000000000", "hi": "7671320511/25000000000",
    },
}
PULSE_FIXTURES = [
    {"parsed": "1*(1/2)*1/1", "exact": "1/2", "approx": "0.5"},
    {"parsed": "1*(1/2)*1/(1+1)", "exact": "1/4", "approx": "0.25"},
    {"parsed": "1*(1/2)*1/(1+1)*(1/2)", "exact": "1/8", "approx": "0.125"},
    {"parsed": "1/8+1/8", "exact": "1/4", "approx": "0.25"},
    {"parsed": "1*(1/2)*1/(1+3)", "exact": "1/8", "approx": "0.125"},
    {"parsed": "1*(1/2)*3/(1+3)", "exact": "3/8", "approx": "0.375"},
    {"parsed": "1/(1+1)", "exact": "1/2", "approx": "0.5"},
    {"parsed": "3/(1+3)", "exact": "3/4", "approx": "0.75"},
    {"parsed": "1*(1/2)*1/1*(1/2)*1/1", "exact": "1/4", "approx": "0.25"},
    {"parsed": "1*(1/2)-1/4", "exact": "1/4", "approx": "0.25"},
    {"parsed": "2*(1/2)*1/1", "exact": "1", "approx": "1"},
    {"parsed": "1*(1/2)*1/1+1*(1/2)*1/1", "exact": "1", "approx": "1"},
    {"parsed": "1+1", "exact": "2"}, {"parsed": "1+3", "exact": "4"},
    {"parsed": "32+1", "exact": "33"},
    {"parsed": "4096+1", "exact": "4097"},
    {"parsed": "256+1", "exact": "257"},
]


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _fan(targets):
    return {"v": 1, "cue": "concepts/cue", "complete": True, "targets": targets}


def _node(identity, origin="evidence"):
    return {"id": identity, "origin": origin}


def _edge(identity, source, target, *, kind="mentions", weight=1,
          provenance="factual-graph", scope="corpus-graph"):
    return {"id": identity, "s": source, "d": target, "t": kind, "weight": weight,
            "provenance": provenance, "scope": scope}


def _graph(nodes, edges):
    return {"v": 1, "complete": True, "nodes": nodes, "edges": edges}


def _seeds(*identities):
    return [{"id": identity, "activation": 1, "source_sha256": _sha({"source": identity})}
            for identity in identities]


class TypedSpreadingContract(unittest.TestCase):
    def setUp(self):
        try:
            self.component = importlib.import_module("siaspreading")
        except ModuleNotFoundError as exc:
            self.fail(f"separate direct-fan and typed-spreading contracts must exist: {exc}")

    def _cue(self, fan, **changes):
        values = {"target": "events/a", "source_activation": 1,
                  "max_associative_strength": 0, "max_targets": 256}
        values.update(changes)
        return self.component.cue_association(fan, **values)

    def _spread(self, graph, seeds=None, **policy_changes):
        policy = copy.deepcopy(POLICY)
        policy.update(policy_changes)
        return self.component.spread(graph, _seeds("events/seed") if seeds is None else seeds,
                                     policy=policy)

    def _enclosed(self, result, name):
        self.assertEqual(result["status"], "computed-unverified")
        self.assertIs(type(result["score"]), float)
        self.assertTrue(math.isfinite(result["score"]))
        score = Fraction.from_float(result["score"])
        self.assertGreaterEqual(score, Fraction(DIRECT_FIXTURES[name]["lo"]))
        self.assertLessEqual(score, Fraction(DIRECT_FIXTURES[name]["hi"]))

    def test_api_has_no_implicit_source_strength_or_engineering_policy(self):
        direct = inspect.signature(self.component.cue_association)
        for parameter in ("target", "source_activation", "max_associative_strength", "max_targets"):
            self.assertIs(direct.parameters[parameter].default, inspect.Parameter.empty)
            self.assertEqual(direct.parameters[parameter].kind, inspect.Parameter.KEYWORD_ONLY)
        spreading = inspect.signature(self.component.spread)
        self.assertIs(spreading.parameters["policy"].default, inspect.Parameter.empty)
        self.assertEqual(spreading.parameters["policy"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_direct_fan_association_keeps_published_signed_term_without_clipping(self):
        fan = _fan(["events/a", "events/b"])
        result = self._cue(fan)
        self._enclosed(result, "negative")
        self.assertLess(result["score"], 0)
        self.assertEqual(set(result), {"v", "component", "status", "scope", "cue", "target",
                                      "fan_count", "source_activation", "max_associative_strength",
                                      "score", "fan_sha256", "policy_sha256", "non_claims"})
        self.assertEqual(result["component"], "cue-fan-association")
        self.assertEqual(result["scope"], "retrieval-only")
        self.assertEqual(result["cue"], fan["cue"])
        self.assertEqual(result["target"], "events/a")
        self.assertEqual(result["fan_count"], len(fan["targets"]))
        self.assertEqual(result["source_activation"], 1)
        self.assertEqual(result["max_associative_strength"], 0)
        self.assertEqual(result["fan_sha256"], _sha(fan))
        self.assertEqual(result["policy_sha256"], _sha({"source_activation": 1,
                         "max_associative_strength": 0, "max_targets": 256}))
        self.assertEqual(result["non_claims"], DIRECT_NON_CLAIMS)
        self.assertNotIn("ACT-R", json.dumps(result))
        self.assertNotIn("HippoRAG", json.dumps(result))

    def test_direct_competing_fan_lowers_association_with_source_and_strength_fixed(self):
        single = self._cue(_fan(["events/a"]))
        competing = self._cue(_fan(["events/a", "events/b"]))
        self._enclosed(competing, "negative")
        self.assertLess(competing["score"], single["score"])
        # Changing only W or S must change the literal term, not a bonus label.
        self._enclosed(self._cue(_fan(["events/a", "events/b"]), source_activation=0.5), "half_source")
        self._enclosed(self._cue(_fan(["events/a", "events/b"]), max_associative_strength=1),
                       "positive_strength")

    def test_direct_complete_unique_target_fan_cannot_be_aggregated_or_truncated(self):
        valid = _fan(["events/a", "events/b"])
        malformed = [
            _fan([]), _fan(["events/a", "events/a"]), _fan(["events/b"]),
            {**valid, "complete": False}, {**valid, "complete": 1},
            {**valid, "fan_count": 2}, {**valid, "targets": {"events/a": 1}},
            {**valid, "targets": ["events/a", {"id": "events/b", "weight": 1}]},
            {**valid, "v": True}, {**valid, "origin": "evidence"},
        ]
        for fan in malformed:
            before = copy.deepcopy(fan)
            with self.subTest(fan=fan), mock.patch.object(self.component.math, "log", side_effect=AssertionError("computed before admission")):
                with self.assertRaises(self.component.SpreadingRefusal):
                    self._cue(fan)
            self.assertEqual(fan, before)
        with self.assertRaises(self.component.SpreadingRefusal):
            self._cue(valid, max_targets=1)

    def test_direct_numeric_bounds_and_capacity_are_explicit_before_serialization(self):
        for key, values in (("source_activation", (-1, True, "1", float("nan"), float("inf"), 1e308)),
                            ("max_associative_strength", (True, "1", float("nan"), float("inf"), 1e308)),
                            ("max_targets", (True, 0, 257, "256"))):
            for value in values:
                with self.subTest(key=key, value=repr(value)), self.assertRaises(self.component.SpreadingRefusal):
                    self._cue(_fan(["events/a"]), **{key: value})
        with mock.patch.object(self.component.json, "dumps", side_effect=AssertionError("serialized before admission")):
            with self.assertRaises(self.component.SpreadingRefusal):
                self._cue(_fan(["events/a", "events/b"]), max_targets=1)

    def test_direct_inputs_and_output_are_detached_and_signed_strength_is_admitted(self):
        fan = _fan(["events/a", "events/b"])
        before = copy.deepcopy(fan)
        result = self._cue(fan, max_associative_strength=-1)
        self.assertLess(result["score"], self._cue(fan)["score"])
        result["non_claims"].clear()
        self.assertEqual(fan, before)
        self.assertEqual(self._cue(fan)["non_claims"], DIRECT_NON_CLAIMS)

    def test_engineering_spread_reaches_unseeded_multihop_candidate_and_keeps_origin(self):
        graph = _graph([_node("events/seed"), _node("events/c", "model"),
                        _node("events/b", "derived"), _node("events/a")],
                       [_edge("seed-a", "events/seed", "events/a"),
                        _edge("seed-b", "events/seed", "events/b"),
                        _edge("a-c", "events/a", "events/c"),
                        _edge("b-c", "events/b", "events/c")])
        seeds = _seeds("events/seed")
        before = copy.deepcopy((graph, seeds, POLICY))
        result = self._spread(graph, seeds)
        self.assertEqual(result["order"], ["events/c", "events/b", "events/a"])
        self.assertEqual(result["rows"], [
            {"subject": "events/c", "origin": "model", "score": 0.25, "scope": "retrieval-only", "in_seed": False},
            {"subject": "events/b", "origin": "derived", "score": 0.25, "scope": "retrieval-only", "in_seed": False},
            {"subject": "events/a", "origin": "evidence", "score": 0.25, "scope": "retrieval-only", "in_seed": False},
        ])
        self.assertEqual([transfer["activation"] for transfer in result["rounds"][1]["transfers"]], [0.125, 0.125])
        self.assertEqual(result["graph_sha256"], _sha(graph))
        self.assertEqual(result["seeds_sha256"], _sha(seeds))
        self.assertEqual(result["policy_sha256"], _sha(POLICY))
        self.assertEqual((graph, seeds, POLICY), before)

    def test_engineering_competing_fan_lowers_target_before_work_cap_and_drops_omitted_mass(self):
        nodes = [_node("events/seed"), _node("events/b"), _node("events/a")]
        solo = _graph(nodes, [_edge("a-edge", "events/seed", "events/a")])
        competing = _graph(nodes, [_edge("z-edge", "events/seed", "events/b"),
                                   _edge("a-edge", "events/seed", "events/a")])
        self.assertEqual(self._spread(solo, steps=1)["rows"][0]["score"], 0.5)
        full = self._spread(competing, steps=1)
        capped = self._spread(competing, steps=1, fanout_limit=1)
        self.assertEqual(full["order"], ["events/b", "events/a"])
        self.assertEqual(capped["order"], ["events/a"])
        self.assertEqual(capped["rows"][0]["score"], 0.25)
        self.assertEqual(capped["rounds"][0]["fan_caps"], [
            {"source": "events/seed", "full_fan_count": 2, "emitted_count": 1, "dropped_activation": 0.25}])
        transfer = capped["rounds"][0]["transfers"][0]
        self.assertEqual(transfer["edge_id"], "a-edge")
        self.assertEqual(transfer["full_fan_count"], 2)
        self.assertEqual(transfer["full_fan_weight"], 2.0)
        self.assertEqual(transfer["normalized_share"], 0.5)
        self.assertEqual(transfer["source_activation"], 1.0)
        self.assertEqual(transfer["activation"], 0.25)
        self.assertEqual(transfer["s"], "events/seed")
        self.assertEqual(transfer["d"], "events/a")

    def test_declared_type_gain_changes_full_fan_weights_and_is_not_just_metadata(self):
        graph = _graph([_node("events/seed"), _node("events/a"), _node("events/b")],
                       [_edge("a-edge", "events/seed", "events/a"),
                        _edge("b-edge", "events/seed", "events/b", kind="coreturn",
                              provenance="learned-coreturn", scope="retrieval-only")])
        result = self._spread(graph, steps=1, type_gains={"mentions": 1, "coreturn": 3})
        self.assertEqual(result["order"], ["events/b", "events/a"])
        self.assertEqual([row["score"] for row in result["rows"]], [0.375, 0.125])
        transfers = result["rounds"][0]["transfers"]
        self.assertEqual([row["full_fan_weight"] for row in transfers], [4.0, 4.0])
        self.assertEqual([row["normalized_share"] for row in transfers], [0.25, 0.75])
        disabled = self._spread(graph, steps=1, type_gains={"mentions": 1, "coreturn": 0})
        self.assertEqual(disabled["order"], ["events/a"])
        self.assertEqual(disabled["rows"][0]["score"], 0.5)

    def test_directed_edges_sink_termination_and_bounded_hops_have_no_restart(self):
        chain = _graph([_node("events/seed"), _node("events/a"), _node("events/b")],
                       [_edge("a-edge", "events/seed", "events/a"),
                        _edge("b-edge", "events/a", "events/b")])
        self.assertEqual(self._spread(chain, steps=1)["order"], ["events/a"])
        forward = self._spread(chain)
        self.assertEqual(forward["order"], ["events/a", "events/b"])
        self.assertEqual([row["score"] for row in forward["rows"]], [0.5, 0.25])
        reverse = self._spread(chain, _seeds("events/b"))
        self.assertEqual(reverse["order"], [])
        self.assertEqual(reverse["rounds"][0]["sinks"], [{"source": "events/b", "activation": 1.0}])
        self.assertEqual(reverse["rounds"][1]["sinks"], [])
        cycle = _graph(chain["nodes"], [_edge("a-edge", "events/seed", "events/a"),
                                         _edge("return-edge", "events/a", "events/seed")])
        result = self._spread(cycle)
        self.assertEqual(result["order"], ["events/a", "events/seed"])
        self.assertEqual([row["score"] for row in result["rows"]], [0.5, 0.25])
        self.assertTrue(result["rows"][1]["in_seed"])

    def test_explicit_source_amplitude_and_multiple_sources_are_not_renormalized(self):
        graph = _graph([_node("events/seed"), _node("events/other"), _node("events/a")],
                       [_edge("a-edge", "events/seed", "events/a"),
                        _edge("other-edge", "events/other", "events/a")])
        baseline = self._spread(graph, steps=1)
        amplified_seeds = [{**_seeds("events/seed")[0], "activation": 2}]
        amplified = self._spread(graph, amplified_seeds, steps=1)
        combined = self._spread(graph, _seeds("events/seed", "events/other"), steps=1)
        self.assertEqual(baseline["rows"][0]["score"], 0.5)
        self.assertEqual(amplified["rows"][0]["score"], 1.0)
        self.assertEqual(combined["rows"][0]["score"], 1.0)
        self.assertNotEqual(amplified["seeds_sha256"], baseline["seeds_sha256"])

    def test_learned_adjacency_never_promotes_provenance_to_evidence(self):
        learned = _edge("learned-edge", "events/seed", "events/a", kind="coreturn",
                        provenance="learned-coreturn", scope="retrieval-only")
        graph = _graph([_node("events/seed", "model"), _node("events/a", "evidence")], [learned])
        result = self._spread(graph, steps=1)
        self.assertEqual(result["rows"][0]["origin"], "evidence")
        self.assertEqual(result["rows"][0]["scope"], "retrieval-only")
        transfer = result["rounds"][0]["transfers"][0]
        self.assertEqual(transfer["provenance"], "learned-coreturn")
        self.assertEqual(transfer["edge_scope"], "retrieval-only")
        for scope in ("corpus-graph", "evidence"):
            with self.subTest(scope=scope), self.assertRaises(self.component.SpreadingRefusal):
                self._spread(_graph(graph["nodes"], [{**learned, "scope": scope}]))

    def test_explicit_closed_policy_refuses_missing_defaulted_or_unbounded_controls(self):
        graph = _graph([_node("events/seed")], [])
        for key in POLICY:
            policy = copy.deepcopy(POLICY)
            del policy[key]
            with self.subTest(missing=key), self.assertRaises(self.component.SpreadingRefusal):
                self.component.spread(graph, _seeds("events/seed"), policy=policy)
        changes = (("steps", True), ("steps", 0), ("steps", 33), ("steps", 1.0),
                   ("hop_attenuation", -1), ("hop_attenuation", 2), ("hop_attenuation", True),
                   ("hop_attenuation", float("nan")), ("type_gains", {"mentions": -1}),
                   ("type_gains", {"mentions": float("inf")}), ("type_gains", {"mentions": 1e308}),
                   ("max_nodes", 257), ("max_edges", 4097), ("max_seeds", 257),
                   ("max_transfers", 4097), ("fanout_limit", 0), ("fanout_limit", 257),
                   ("fanout_order", "score"), ("tie_break", "slug"), ("restart", 0),
                   ("score_mode", "probability"), ("candidate_scope", "seeds-only"),
                   ("algorithm", "ppr"), ("v", True))
        for key, value in changes:
            with self.subTest(key=key, value=repr(value)), self.assertRaises(self.component.SpreadingRefusal):
                self._spread(graph, **{key: value})

    def test_any_malformed_node_edge_or_seed_refuses_whole_observation_before_serialization(self):
        good = _graph([_node("events/seed"), _node("events/a")],
                      [_edge("a-edge", "events/seed", "events/a")])
        bad_graphs = [
            {**good, "complete": False}, {**good, "complete": 1},
            {**good, "nodes": good["nodes"] + [_node("events/a")]},
            {**good, "nodes": [_node("events/seed"), _node("events/a", "verified")]},
            {**good, "edges": good["edges"] + [good["edges"][0]]},
            {**good, "edges": good["edges"] + [{**good["edges"][0], "id": "duplicate-pair"}]},
            {**good, "edges": good["edges"] + [_edge("late-edge", "events/a", "events/missing")]},
            {**good, "edges": [{**good["edges"][0], "t": "undeclared"}]},
            {**good, "edges": [{**good["edges"][0], "weight": 0}]},
            {**good, "edges": [{**good["edges"][0], "weight": float("nan")}]},
            {**good, "edges": [{**good["edges"][0], "weight": True}]},
            {**good, "text": "content is outside this rank-only API"},
        ]
        admitted_seeds = _seeds("events/seed")
        for graph in bad_graphs:
            with self.subTest(graph=repr(graph)), mock.patch.object(self.component.json, "dumps", side_effect=AssertionError("serialized before admission")):
                with self.assertRaises(self.component.SpreadingRefusal):
                    self._spread(graph, admitted_seeds)
        bad_seeds = [_seeds("events/missing"), _seeds("events/seed", "events/seed"),
                     [{**_seeds("events/seed")[0], "activation": -1}],
                     [{**_seeds("events/seed")[0], "activation": True}],
                     [{**_seeds("events/seed")[0], "activation": float("inf")}],
                     [{**_seeds("events/seed")[0], "source_sha256": "unbound"}]]
        for seeds in bad_seeds:
            with self.subTest(seeds=repr(seeds)), self.assertRaises(self.component.SpreadingRefusal):
                self._spread(good, seeds)

    def test_resource_limits_refuse_instead_of_silently_truncating_graph_or_observation(self):
        graph = _graph([_node("events/seed"), _node("events/a"), _node("events/b")],
                       [_edge("a-edge", "events/seed", "events/a"),
                        _edge("b-edge", "events/a", "events/b")])
        for change in ({"max_nodes": 1}, {"max_edges": 1}, {"max_transfers": 1}):
            with self.subTest(change=change), self.assertRaises(self.component.SpreadingRefusal):
                self._spread(graph, **change)
        with self.assertRaises(self.component.SpreadingRefusal):
            self._spread(graph, _seeds("events/seed", "events/a"), max_seeds=1)

    def test_empty_source_has_no_fabricated_seed_boost_and_results_do_not_alias_inputs(self):
        pages = {"events/seed": {"text": "Original é漢😀 bytes.\n", "origin": "evidence"},
                 "events/a": {"text": "Agent prose remains agent prose.\n", "origin": "model"}}
        graph = _graph([_node(subject, page["origin"]) for subject, page in pages.items()],
                       [_edge("a-edge", "events/seed", "events/a")])
        seeds = _seeds("events/seed")
        before = copy.deepcopy((pages, graph, seeds, POLICY))
        empty = self._spread(graph, [])
        self.assertEqual(empty["rows"], [])
        self.assertEqual(empty["order"], [])
        result = self._spread(graph, seeds)
        self.assertEqual(set(result), {"v", "component", "status", "scope", "graph_sha256",
                                      "seeds_sha256", "policy_sha256", "order", "rows", "rounds", "non_claims"})
        self.assertEqual(result["component"], "typed-fan-spreading")
        self.assertEqual(result["status"], "computed-unverified")
        self.assertEqual(result["scope"], "retrieval-only")
        self.assertEqual(result["non_claims"], SPREAD_NON_CLAIMS)
        self.assertNotIn("ACT-R", json.dumps(result))
        self.assertNotIn("HippoRAG", json.dumps(result))
        reordered = [pages[subject] for subject in result["order"]]
        self.assertEqual(reordered, [pages["events/a"]])
        result["rounds"][0]["transfers"].clear()
        result["non_claims"].clear()
        result["rows"][0]["origin"] = "rewritten-output"
        self.assertEqual((pages, graph, seeds, POLICY), before)
        self.assertEqual(self._spread(graph, seeds)["non_claims"], SPREAD_NON_CLAIMS)


if __name__ == "__main__":
    unittest.main()
