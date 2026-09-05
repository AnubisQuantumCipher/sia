#!/usr/bin/env python3
"""Falsifiable contracts for SIA's optional associative components.

The tests use SIA product vocabulary in public names.  ACT-R, Hebbian, and
PageRank ancestry is recorded only in descriptions; none of those labels is a
claim that these bounded desktop proxies reproduce a human cognitive system.
"""

import copy
import importlib.util
import math
import os
import sys
import unittest

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")
sys.path.insert(0, BIN)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


siamind = _load(
    "siamind_cognitive_components", os.path.join(BIN, "siamind.py"))


def _usage_node(stamps, *, total_weight, stability=30.0,
                last_touch=None):
    stamps = list(stamps)
    first = stamps[0]
    latest = stamps[-1]
    return {
        "n": total_weight,
        "t0": first,
        "rt": [[stamp, 1.0] for stamp in stamps],
        "s": stability,
        "last_touch": latest if last_touch is None else last_touch,
        "pins": [],
    }


def _graph(slugs, edges, origins=None):
    origins = origins or {}
    return {
        "nodes": [
            {"id": slug, "t": "event-day",
             "origin": origins.get(slug, "evidence")}
            for slug in slugs
        ],
        "edges": [
            {"s": source, "d": target, "t": "mentions"}
            for source, target in edges
        ],
    }


def _rows_by_slug(result):
    rows = result["rows"]
    indexed = {row["slug"]: row for row in rows}
    if len(indexed) != len(rows):
        raise AssertionError("component output contains duplicate candidates")
    return indexed


class UsageActivationComponent(unittest.TestCase):
    """The ACT-R-derived score has explicit availability and bounded input."""

    def test_old_available_score_cannot_alias_the_unavailable_sentinel(self):
        as_of = 10_000_000_000.0
        old = _usage_node([0.0], total_weight=1.0)
        unknown = {"n": 0.0, "t0": 0.0, "rt": []}
        old_before = copy.deepcopy(old)
        unknown_before = copy.deepcopy(unknown)

        available = siamind.usage_activation_snapshot(old, as_of)
        unavailable = siamind.usage_activation_snapshot(unknown, as_of)

        fields = {
            "status", "score", "as_of", "exact_recent_weight",
            "tail_weight", "reason",
        }
        self.assertEqual(set(available), fields)
        self.assertEqual(set(unavailable), fields)
        self.assertEqual(available["status"], "available")
        self.assertIsNone(available["reason"])
        self.assertIsInstance(available["score"], float)
        self.assertTrue(math.isfinite(available["score"]))
        self.assertLess(
            available["score"], -10.0,
            "a valid old trace may score below the retired numeric sentinel")
        self.assertEqual(unavailable, {
            "status": "unavailable",
            "score": None,
            "as_of": as_of,
            "exact_recent_weight": 0.0,
            "tail_weight": 0.0,
            "reason": "no-usage-history",
        })
        self.assertEqual(old, old_before)
        self.assertEqual(unknown, unknown_before)

    def test_more_and_fresher_usage_independently_raise_the_score(self):
        as_of = 1_000.0
        baseline = {
            "n": 1.0, "t0": 100.0, "rt": [[100.0, 1.0]],
        }
        more_used = {
            "n": 2.0, "t0": 100.0,
            "rt": [[100.0, 1.0], [100.0, 1.0]],
        }
        more_recent = {
            "n": 1.0, "t0": 100.0, "rt": [[900.0, 1.0]],
        }
        before = copy.deepcopy((baseline, more_used, more_recent))

        baseline_result = siamind.usage_activation_snapshot(baseline, as_of)
        more_used_result = siamind.usage_activation_snapshot(more_used, as_of)
        more_recent_result = siamind.usage_activation_snapshot(
            more_recent, as_of)

        self.assertEqual(baseline_result["status"], "available")
        self.assertEqual(more_used_result["status"], "available")
        self.assertEqual(more_recent_result["status"], "available")
        self.assertGreater(
            more_used_result["score"], baseline_result["score"])
        self.assertGreater(
            more_recent_result["score"], baseline_result["score"])
        self.assertEqual((baseline, more_used, more_recent), before)

    def test_unbounded_or_nonchronological_usage_state_is_refused(self):
        as_of = 100.0
        cases = {
            "recent-window-over-bound": {
                "n": 6.0, "t0": 1.0,
                "rt": [[stamp, 1.0]
                       for stamp in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)],
            },
            "reverse-chronology": {
                "n": 2.0, "t0": 1.0,
                "rt": [[2.0, 1.0], [1.0, 1.0]],
            },
            "before-creation": {
                "n": 1.0, "t0": 2.0, "rt": [[1.0, 1.0]],
            },
            "future-use": {
                "n": 1.0, "t0": 1.0, "rt": [[101.0, 1.0]],
            },
            "negative-weight": {
                "n": 1.0, "t0": 1.0, "rt": [[1.0, -1.0]],
            },
            "recent-weight-exceeds-total": {
                "n": 0.5, "t0": 1.0, "rt": [[1.0, 1.0]],
            },
        }
        for label, node in cases.items():
            before = copy.deepcopy(node)
            with self.subTest(label=label), self.assertRaises(ValueError):
                siamind.usage_activation_snapshot(node, as_of)
            self.assertEqual(node, before)


class CoreturnLearningComponent(unittest.TestCase):
    """The Hebbian-derived proxy learns only exact delivered co-returns."""

    @staticmethod
    def _mind():
        return {"v": siamind.MIND_VERSION, "nodes": {}, "edges": {}}

    @staticmethod
    def _record(slugs, record_id="delivery-a"):
        return {
            "id": record_id,
            "ts": 1_000.0,
            "src": "user-ask",
            "slugs": list(slugs),
        }

    def test_replay_receipts_are_defaulted_validated_and_preserved(self):
        self.assertEqual(siamind._empty_mind()["coreturn_applied"], {})
        digest = "a" * 64
        migrated = siamind.migrate_mind({
            "nodes": {}, "edges": {},
            "coreturn_applied": {"delivery-a": digest},
        }, now=1_000.0)
        self.assertEqual(
            migrated["coreturn_applied"], {"delivery-a": digest})

        for malformed in (
                [], {"": digest}, {"delivery-a": "not-a-digest"}):
            candidate = {"nodes": {}, "edges": {},
                         "coreturn_applied": malformed}
            with self.subTest(value=malformed), self.assertRaises(ValueError):
                siamind.migrate_mind(candidate, now=1_000.0)

    def test_unique_delivery_applies_one_canonical_unordered_pair(self):
        left = "events/alpha/2026-01-01"
        right = "events/zeta/2026-01-01"
        forward_mind = self._mind()
        reverse_mind = self._mind()

        forward = siamind.apply_coreturn_record(
            forward_mind, self._record([right, left]))
        reverse = siamind.apply_coreturn_record(
            reverse_mind, self._record([left, right]))

        expected = {
            "status": "applied",
            "record_id": "delivery-a",
            "node_deltas": {left: 1.0, right: 1.0},
            "unordered_pair_deltas": {f"{left}|{right}": 1.0},
        }
        self.assertEqual(forward, expected)
        self.assertEqual(reverse, expected)
        self.assertEqual(forward_mind, reverse_mind)
        self.assertEqual(set(forward_mind["edges"]), {f"{left}|{right}"})

    def test_distinct_deliveries_reinforce_the_same_stored_pair(self):
        left = "events/alpha/2026-01-01"
        right = "events/zeta/2026-01-01"
        key = f"{left}|{right}"
        mind = self._mind()
        first = self._record([left, right], record_id="delivery-a")
        second = self._record([right, left], record_id="delivery-b")

        first_result = siamind.apply_coreturn_record(mind, first)
        first_weight = mind["edges"][key]["w"]
        second_result = siamind.apply_coreturn_record(mind, second)

        self.assertEqual(first_result["status"], "applied")
        self.assertEqual(second_result["status"], "applied")
        self.assertEqual(
            second_result["unordered_pair_deltas"], {key: 1.0})
        self.assertGreater(mind["edges"][key]["w"], first_weight)
        self.assertEqual(
            set(mind["coreturn_applied"]), {"delivery-a", "delivery-b"})

    def test_retry_is_an_idempotent_no_op(self):
        mind = self._mind()
        record = self._record([
            "events/alpha/2026-01-01", "events/zeta/2026-01-01"])
        siamind.apply_coreturn_record(mind, record)
        after_first = copy.deepcopy(mind)

        replay = siamind.apply_coreturn_record(mind, record)

        self.assertEqual(replay, {
            "status": "already-applied",
            "record_id": "delivery-a",
            "node_deltas": {},
            "unordered_pair_deltas": {},
        })
        self.assertEqual(mind, after_first)

    def test_duplicate_slug_delivery_is_refused_atomically(self):
        mind = self._mind()
        siamind.touch(
            mind, "events/existing/2026-01-01", ts=900.0,
            src="user-ask")
        before = copy.deepcopy(mind)
        duplicate = self._record([
            "events/alpha/2026-01-01",
            "events/alpha/2026-01-01",
            "events/zeta/2026-01-01",
        ], record_id="delivery-duplicate")

        with self.assertRaises(ValueError):
            siamind.apply_coreturn_record(mind, duplicate)
        self.assertEqual(mind, before)

    def test_malformed_delivery_cannot_apply_a_valid_prefix(self):
        mind = self._mind()
        siamind.touch(
            mind, "events/existing/2026-01-01", ts=900.0,
            src="user-ask")
        before = copy.deepcopy(mind)
        malformed = self._record([
            "events/alpha/2026-01-01", "../outside",
        ], record_id="delivery-malformed")

        with self.assertRaises(ValueError):
            siamind.apply_coreturn_record(mind, malformed)
        self.assertEqual(mind, before)


class AssociativeRetrievalComponent(unittest.TestCase):
    """The PageRank-derived proxy exposes, rather than hides, each factor."""

    def test_component_names_generic_retrieval_input_not_dense_evidence(self):
        seed = "events/alpha/2026-01-01"
        connected = "events/beta/2026-01-01"
        result = siamind.associative_components(
            _graph([seed, connected], [(seed, connected)]),
            [(seed, 1.0)], expand_candidates=True)
        self.assertEqual(
            result["candidate_scope"],
            "retrieval-plus-reachable-graph")
        rows = _rows_by_slug(result)
        self.assertIn("retrieval_score", rows[seed])
        self.assertNotIn("dense", rows[seed])

    def test_expansion_can_introduce_a_reachable_unscored_candidate(self):
        seed = "events/alpha/2026-01-01"
        connected = "events/beta/2026-01-01"

        result = siamind.associative_components(
            _graph([seed, connected], [(seed, connected)]),
            [(seed, 1.0)], expand_candidates=True)

        self.assertEqual(result["status"], "applied")
        self.assertEqual(
            result["candidate_scope"],
            "retrieval-plus-reachable-graph")
        rows = _rows_by_slug(result)
        self.assertEqual(set(rows), {seed, connected})
        self.assertIsNone(rows[connected]["retrieval_score"])
        self.assertGreater(rows[connected]["propagation"], 0.0)
        self.assertGreater(rows[connected]["final"], 0.0)

    def test_zero_connected_seed_mass_is_explicitly_unavailable(self):
        a = "events/alpha/2026-01-01"
        b = "events/beta/2026-01-01"
        result = siamind.associative_components(
            _graph([a, b], [(a, b)]), [(a, 0.0), (b, 0.0)])

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "zero-connected-seed-mass")
        self.assertEqual(result["candidate_scope"], "retrieval-window")
        self.assertEqual(result["rows"], [])

    def test_dangling_mass_is_visible_and_conserved(self):
        a = "events/alpha/2026-01-01"
        b = "events/beta/2026-01-01"
        dangling = "events/dangling/2026-01-01"
        result = siamind.associative_components(
            _graph([a, b, dangling], [(a, b)]),
            [(a, 1.0), (b, 0.5), (dangling, 0.25)])

        self.assertEqual(result["status"], "applied")
        self.assertIsNone(result["reason"])
        self.assertEqual(result["candidate_scope"], "retrieval-window")
        rows = _rows_by_slug(result)
        required = {
            "slug", "retrieval_score", "origin", "retention", "propagation",
            "usage", "final",
        }
        for row in rows.values():
            self.assertTrue(required.issubset(row))
        self.assertAlmostEqual(
            math.fsum(row["propagation"] for row in rows.values()),
            1.0, places=9)
        self.assertGreater(rows[dangling]["propagation"], 0.0)

    def test_active_learned_pair_is_retrieval_only_adjacency(self):
        a = "events/alpha/2026-01-01"
        b = "events/beta/2026-01-01"
        c = "events/gamma/2026-01-01"
        as_of = 2_000.0
        graph = _graph([a, b, c], [(a, c)])
        mind = {
            "nodes": {},
            "edges": {
                f"{a}|{b}": {
                    "w": 2.0,
                    "s": siamind.EDGE_STABILITY_DAYS,
                    "last_touch": as_of,
                    "pins": [],
                },
            },
        }
        hits = [(a, 1.0), (b, 0.5), (c, 0.25)]
        graph_before = copy.deepcopy(graph)
        mind_before = copy.deepcopy(mind)

        structural = siamind.associative_components(
            graph, hits, mind=mind, as_of=as_of, include_learned=False)
        augmented = siamind.associative_components(
            graph, hits, mind=mind, as_of=as_of, include_learned=True)

        self.assertEqual(structural["status"], "applied")
        self.assertEqual(augmented["status"], "applied")
        structural_rows = _rows_by_slug(structural)
        augmented_rows = _rows_by_slug(augmented)
        self.assertNotEqual(
            [structural_rows[slug]["propagation"] for slug in (a, b, c)],
            [augmented_rows[slug]["propagation"] for slug in (a, b, c)])
        learned = [
            edge for edge in augmented["retrieval_adjacency"]
            if edge.get("provenance") == "learned-coreturn"
        ]
        self.assertEqual(len(learned), 1)
        self.assertEqual({learned[0]["s"], learned[0]["d"]}, {a, b})
        self.assertEqual(learned[0]["scope"], "retrieval-only")
        self.assertEqual(graph, graph_before)
        self.assertEqual(mind, mind_before)
        self.assertNotIn({"s": a, "d": b, "t": "mentions"},
                         graph["edges"])

    def test_delivered_coreturn_is_consumed_as_retrieval_only_adjacency(self):
        a = "events/alpha/2026-01-01"
        b = "events/beta/2026-01-01"
        observed_at = 2_000.0
        graph = _graph([a, b], [])
        mind = {"v": siamind.MIND_VERSION, "nodes": {}, "edges": {}}
        record = {
            "id": "delivery-integration",
            "ts": observed_at,
            "src": "user-ask",
            "slugs": [b, a],
        }

        applied = siamind.apply_coreturn_record(mind, record)
        without_learned = siamind.associative_components(
            graph, [(a, 1.0), (b, 0.5)], mind=mind,
            as_of=observed_at, include_learned=False)
        with_learned = siamind.associative_components(
            graph, [(a, 1.0), (b, 0.5)], mind=mind,
            as_of=observed_at, include_learned=True)

        self.assertEqual(applied["status"], "applied")
        self.assertEqual(without_learned["status"], "unavailable")
        self.assertEqual(
            without_learned["reason"], "graph-has-no-usable-edges")
        self.assertEqual(with_learned["status"], "applied")
        learned = [
            edge for edge in with_learned["retrieval_adjacency"]
            if edge["provenance"] == "learned-coreturn"
        ]
        self.assertEqual(len(learned), 1)
        self.assertEqual({learned[0]["s"], learned[0]["d"]}, {a, b})
        self.assertGreater(learned[0]["weight"], 0.0)
        self.assertEqual(learned[0]["scope"], "retrieval-only")

    def test_component_changes_do_not_bleed_into_other_fields(self):
        a = "events/alpha/2026-01-01"
        b = "events/beta/2026-01-01"
        as_of = 1_000_000.0
        graph = _graph([a, b], [(a, b)])
        baseline_mind = {
            "nodes": {
                a: _usage_node([900_000.0], total_weight=1.0,
                               last_touch=as_of),
                b: _usage_node([900_000.0], total_weight=1.0,
                               last_touch=as_of),
            },
            "edges": {},
        }
        hits = [(a, 1.0), (b, 1.0)]
        base = _rows_by_slug(siamind.associative_components(
            graph, hits, mind=baseline_mind, as_of=as_of))[a]

        origin_graph = copy.deepcopy(graph)
        origin_graph["nodes"][0]["origin"] = "model"
        changed_origin = _rows_by_slug(siamind.associative_components(
            origin_graph, hits, mind=baseline_mind, as_of=as_of))[a]
        self.assertNotEqual(changed_origin["origin"], base["origin"])
        for field in (
                "retrieval_score", "retention", "propagation", "usage"):
            self.assertEqual(changed_origin[field], base[field], field)
        self.assertNotEqual(changed_origin["final"], base["final"])

        usage_mind = copy.deepcopy(baseline_mind)
        usage_mind["nodes"][a].update({
            "n": 2.0,
            "t0": 800_000.0,
            "rt": [[800_000.0, 1.0], [900_000.0, 1.0]],
        })
        changed_usage = _rows_by_slug(siamind.associative_components(
            graph, hits, mind=usage_mind, as_of=as_of))[a]
        self.assertNotEqual(changed_usage["usage"], base["usage"])
        for field in (
                "retrieval_score", "origin", "retention", "propagation"):
            self.assertEqual(changed_usage[field], base[field], field)
        self.assertNotEqual(changed_usage["final"], base["final"])

        retention_mind = copy.deepcopy(baseline_mind)
        retention_mind["nodes"][a].update({
            "s": 1.0,
            "last_touch": 900_000.0,
        })
        changed_retention = _rows_by_slug(siamind.associative_components(
            graph, hits, mind=retention_mind, as_of=as_of))[a]
        self.assertNotEqual(changed_retention["retention"], base["retention"])
        for field in (
                "retrieval_score", "origin", "propagation", "usage"):
            self.assertEqual(changed_retention[field], base[field], field)
        self.assertNotEqual(changed_retention["final"], base["final"])


class MusingUsageEligibility(unittest.TestCase):
    """The DMN-inspired walk may describe only known-usage endpoints."""

    @staticmethod
    def _fixture_graph():
        slugs = [f"region-{index}/node" for index in range(10)]
        return slugs, _graph(slugs, list(zip(slugs, slugs[1:])))

    def test_unknown_usage_is_not_promoted_as_high_activation(self):
        slugs, graph = self._fixture_graph()
        mind = {
            "nodes": {
                slugs[0]: _usage_node([900_000.0], total_weight=1.0),
            },
            "edges": {},
            "musing_day": "",
        }

        result = siamind.muse(
            mind, graph, "2026-01-01", "ledger-a", now=1_000_000.0)

        self.assertIsNone(result)

    def test_every_musing_endpoint_has_known_usage(self):
        slugs, graph = self._fixture_graph()
        known = {slugs[0], slugs[4]}
        mind = {
            "nodes": {
                slugs[0]: _usage_node([900_000.0], total_weight=1.0),
                slugs[4]: _usage_node([800_000.0], total_weight=1.0),
            },
            "edges": {},
            "musing_day": "",
        }

        result = siamind.muse(
            mind, graph, "2026-01-02", "ledger-b", now=1_000_000.0)

        self.assertIsNotNone(result)
        _text, links = result
        self.assertEqual(set(links), known)


if __name__ == "__main__":
    unittest.main(verbosity=2)
