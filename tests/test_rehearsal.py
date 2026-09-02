#!/usr/bin/env python3
"""Stability-decay and SM-2 rehearsal invariants (stdlib-only)."""

import contextlib
import importlib.util
import importlib.machinery
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_script(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


siamind = _load("siamind_rehearsal", os.path.join(BIN, "siamind.py"))


class Migration(unittest.TestCase):
    def test_v1_weights_and_unknown_fields_survive(self):
        old = {"v": 1,
               "nodes": {"events/x/day": {"n": 2, "t0": 10,
                                             "rt": [20, [30, 1.0]],
                                             "future_key": "keep"}},
               "edges": {"events/x/day|organs/x": 4},
               "unknown_organ": {"x": 1}}
        got = siamind.migrate_mind(old, now=100)
        self.assertEqual(got["v"], siamind.MIND_VERSION)
        self.assertEqual(got["nodes"]["events/x/day"]["last_touch"], 30)
        self.assertEqual(got["nodes"]["events/x/day"]["future_key"], "keep")
        edge = got["edges"]["events/x/day|organs/x"]
        self.assertEqual(edge["w"], 4)
        self.assertEqual(edge["last_touch"], 100)
        self.assertEqual(got["unknown_organ"], {"x": 1})
        self.assertEqual(siamind.migrate_mind(got, now=200)["edges"]
                         ["events/x/day|organs/x"]["last_touch"], 100)

    def test_structurally_corrupt_rehearsal_state_refuses(self):
        node = {"n": 1, "t0": 10, "rt": [], "s": 7,
                "last_touch": 10, "arousal": 0.8, "novelty": 0.2}
        corrupt_fields = {
            "pins": "user",
            "signals": [],
            "review": "corrupt",
        }
        for field, value in corrupt_fields.items():
            with self.subTest(field=field):
                candidate = {"nodes": {"events/x/day": {
                    **node, field: value}}, "edges": {}}
                with self.assertRaises(ValueError):
                    siamind.migrate_mind(candidate, now=100)

        corrupt_edge = {
            "nodes": {},
            "edges": {"a|b": {
                "w": 1, "s": 7, "last_touch": 10, "pins": "user"}},
        }
        with self.assertRaises(ValueError):
            siamind.migrate_mind(corrupt_edge, now=100)

    def test_corrupt_mind_refuses_overwrite_and_retains_last_good(self):
        with tempfile.TemporaryDirectory() as state:
            old_path = siamind.MIND_PATH
            siamind.MIND_PATH = os.path.join(state, "mind.json")
            try:
                siamind.save_mind(
                    {"nodes": {}, "edges": {}, "marker": "first"})
                siamind.save_mind(
                    {"nodes": {}, "edges": {}, "marker": "second"})
                with open(siamind.MIND_PATH + ".last-good") as stream:
                    self.assertEqual(json.load(stream)["marker"], "first")
                with open(siamind.MIND_PATH, "w") as stream:
                    stream.write("{broken")
                with self.assertRaisesRegex(
                        ValueError, "mind state is unreadable or malformed"):
                    siamind.load_mind()
                with self.assertRaisesRegex(
                        ValueError,
                        "prior mind state is unreadable or malformed"):
                    siamind.save_mind({"nodes": {}, "edges": {}})
                with open(siamind.MIND_PATH) as stream:
                    self.assertEqual(stream.read(), "{broken")
            finally:
                siamind.MIND_PATH = old_path

    def test_parser_recursion_refuses_without_overwriting_or_echoing_detail(self):
        with tempfile.TemporaryDirectory() as state:
            old_path = siamind.MIND_PATH
            siamind.MIND_PATH = os.path.join(state, "mind.json")
            source = '{"nodes":{},"edges":{},"marker":"retained"}'
            try:
                with open(siamind.MIND_PATH, "w", encoding="utf-8") as stream:
                    stream.write(source)
                os.chmod(siamind.MIND_PATH, 0o600)
                with mock.patch.object(
                        siamind.json, "loads",
                        side_effect=RecursionError("private parser detail")), \
                        self.assertRaisesRegex(
                            ValueError,
                            "^mind state is unreadable or malformed$"):
                    siamind.load_mind()
                with mock.patch.object(
                        siamind.json, "loads",
                        side_effect=RecursionError("private parser detail")), \
                        self.assertRaisesRegex(
                            ValueError,
                            "^prior mind state is unreadable or malformed$"):
                    siamind.save_mind({"nodes": {}, "edges": {}})
                with open(siamind.MIND_PATH, encoding="utf-8") as stream:
                    self.assertEqual(stream.read(), source)
                self.assertFalse(os.path.exists(siamind.MIND_PATH + ".last-good"))
            finally:
                siamind.MIND_PATH = old_path

    def test_save_refuses_an_oversized_existing_mind_without_reading_it_all(self):
        with tempfile.TemporaryDirectory() as state:
            old_path = siamind.MIND_PATH
            siamind.MIND_PATH = os.path.join(state, "mind.json")
            limit = 4096
            oversized = b"x" * (limit + 1)
            try:
                with open(siamind.MIND_PATH, "wb") as stream:
                    stream.write(oversized)
                os.chmod(siamind.MIND_PATH, 0o600)
                with mock.patch.object(siamind, "MAX_MIND_BYTES", limit), \
                        self.assertRaisesRegex(ValueError, "bounded private"):
                    siamind.save_mind({"nodes": {}, "edges": {}})
                with open(siamind.MIND_PATH, "rb") as stream:
                    self.assertEqual(stream.read(), oversized)
            finally:
                siamind.MIND_PATH = old_path

    def test_mind_loader_refuses_symlinked_state(self):
        with tempfile.TemporaryDirectory() as state:
            target = os.path.join(state, "external.json")
            with open(target, "w") as stream:
                json.dump({"nodes": {}, "edges": {}, "marker": "followed"},
                          stream)
            os.chmod(target, 0o600)
            old_path = siamind.MIND_PATH
            siamind.MIND_PATH = os.path.join(state, "mind.json")
            os.symlink(target, siamind.MIND_PATH)
            try:
                with self.assertRaises(OSError):
                    siamind.load_mind()
            finally:
                siamind.MIND_PATH = old_path

    def test_owned_legacy_mind_permissions_are_normalized(self):
        with tempfile.TemporaryDirectory() as state:
            old_path = siamind.MIND_PATH
            siamind.MIND_PATH = os.path.join(state, "mind.json")
            try:
                with open(siamind.MIND_PATH, "w", encoding="utf-8") as stream:
                    json.dump({"nodes": {}, "edges": {},
                               "marker": "legacy"}, stream)
                os.chmod(siamind.MIND_PATH, 0o644)
                loaded = siamind.load_mind(now=100)
                self.assertEqual(loaded["marker"], "legacy")
                self.assertEqual(os.stat(siamind.MIND_PATH).st_mode & 0o777,
                                 0o600)
            finally:
                siamind.MIND_PATH = old_path

    def test_capacity_compaction_evicts_only_rebuildable_cache(self):
        mind = siamind._empty_mind()
        ordinary = siamind.touch(mind, "ordinary", ts=1, src="organ")
        ordinary["padding"] = "x" * 800
        safety = siamind.touch(
            mind, "safety", ts=2, src="organ", pin=True)
        safety["padding"] = "y" * 800
        user = siamind.touch(mind, "user", ts=3, src="organ")
        user["pins"] = ["user"]
        mind["workspace"] = ["ordinary", "safety", "user"]
        with mock.patch.object(siamind, "MAX_MIND_BYTES", 1000):
            removed = siamind.compact_mind_for_persistence(mind)
            self.assertLessEqual(
                len(siamind._mind_text(mind).encode("utf-8")),
                siamind.MAX_MIND_BYTES)
        self.assertGreaterEqual(removed["nodes"], 1)
        self.assertIn("user", mind["nodes"])
        self.assertNotIn("ordinary", mind["nodes"])
        self.assertNotIn("ordinary", mind["workspace"])
        self.assertTrue(set(mind["workspace"]).issubset(mind["nodes"]))
        self.assertGreaterEqual(
            mind["capacity"]["evicted_safety_nodes"], 1)

    def test_capacity_refuses_to_evict_operator_pins(self):
        mind = siamind._empty_mind()
        user = siamind.touch(mind, "user", ts=1, src="organ")
        user["pins"] = ["user"]
        user["padding"] = "x" * 2000
        with mock.patch.object(siamind, "MAX_MIND_BYTES", 1000), \
                self.assertRaisesRegex(ValueError, "persistence bound"):
            siamind.compact_mind_for_persistence(mind)
        self.assertIn("user", mind["nodes"])


class Stability(unittest.TestCase):
    def test_decay_is_a_lens_and_pin_prevents_decay(self):
        rec = {"s": 10, "last_touch": 0, "pins": []}
        early = siamind.retention(rec, now=siamind.SECONDS_PER_DAY)
        late = siamind.retention(rec, now=20 * siamind.SECONDS_PER_DAY)
        self.assertGreater(early, late)
        self.assertGreater(late, 0)
        rec["pins"] = ["user"]
        self.assertEqual(siamind.retention(rec, now=10**9), 1.0)

    def test_touch_reinforces_stability_and_records_source(self):
        mind = {"nodes": {}, "edges": {}}
        node = siamind.touch(mind, "x", ts=100, src="organ")
        initial = node["s"]
        node = siamind.touch(mind, "x", ts=200, src="user-recall")
        self.assertGreater(node["s"], initial)
        self.assertEqual(node["last_touch"], 200)
        self.assertEqual(node["signals"]["user-recall"], 200)

    def test_stability_is_finite_and_capped(self):
        mind = {"nodes": {"x": {
            "n": 1, "t0": 0, "rt": [],
            "s": siamind.MAX_STABILITY_DAYS,
            "last_touch": 0, "arousal": 0, "novelty": 0,
            "pins": [], "signals": {},
        }}, "edges": {}}
        siamind.touch(mind, "x", ts=1, src="user-recall")
        self.assertEqual(mind["nodes"]["x"]["s"],
                         siamind.MAX_STABILITY_DAYS)
        self.assertEqual(siamind.retention(
            {"s": float("nan"), "last_touch": 0, "pins": []}, now=1), 0)
        with self.assertRaisesRegex(ValueError, "finite"):
            siamind.migrate_mind({
                "nodes": {"x": {"s": float("nan")}}, "edges": {}}, now=1)

    def test_graph_discovery_is_not_a_touch(self):
        graph = {"nodes": [{"id": "a"}, {"id": "b"}],
                 "edges": [{"s": "a", "d": "b"}]}
        mind = {"nodes": {}, "edges": {}}
        siamind.sync_graph_state(mind, graph, now=50)
        self.assertEqual(mind["nodes"]["a"]["n"], 0)
        self.assertEqual(mind["nodes"]["a"]["rt"], [])
        self.assertIn("a|b", mind["edges"])

    def test_graph_edge_survives_hygiene_without_refreshing_stability(self):
        graph = {"nodes": [{"id": "a"}, {"id": "b"}],
                 "edges": [{"s": "a", "d": "b"}]}
        mind = {"nodes": {}, "edges": {
            "a|b": {"w": 0.1, "s": 7, "last_touch": 25, "pins": []}}}
        siamind.sync_graph_state(mind, graph, now=50)
        self.assertTrue(mind["edges"]["a|b"]["graph_discovered"])
        self.assertEqual(mind["edges"]["a|b"]["last_touch"], 25)
        siamind.hebb_hygiene(mind, now=100)
        self.assertIn("a|b", mind["edges"])
        self.assertEqual(mind["edges"]["a|b"]["w"], 0.0)
        self.assertEqual(mind["edges"]["a|b"]["last_touch"], 25)
        siamind.sync_graph_state(mind, graph, now=1000)
        self.assertEqual(mind["edges"]["a|b"]["last_touch"], 25)

    def test_demoted_edge_is_retained_in_state(self):
        edge = {"w": 2, "s": 1, "last_touch": 0, "pins": []}
        mind = {"nodes": {}, "edges": {"a|b": edge}}
        rep = siamind.decay_sweep(
            mind, now=10 * siamind.SECONDS_PER_DAY)
        self.assertEqual(rep["demoted_edges"], 1)
        self.assertIn("a|b", mind["edges"], "decay must never delete evidence")

    def test_summary_view_is_read_only_after_capacity_compaction(self):
        mind = siamind.migrate_mind({
            "nodes": {"important": {
                "n": 1, "t0": 0, "rt": [], "s": 1,
                "last_touch": 0, "arousal": 1, "novelty": 0,
                "pins": [], "signals": {}}},
            "edges": {"important|other": {
                "w": 1, "s": 1, "last_touch": 0, "pins": []}}}, now=1)
        siamind.memory_summary(mind, now=1)
        limit = len(json.dumps(mind, allow_nan=False).encode("utf-8")) - 1
        siamind.compact_mind_for_persistence(mind, max_bytes=limit)
        before = json.dumps(mind, allow_nan=False, sort_keys=True)
        summary = siamind.memory_summary_view(mind, now=1)
        after = json.dumps(mind, allow_nan=False, sort_keys=True)
        self.assertEqual(after, before)
        self.assertEqual(summary["edges"], len(mind["edges"]))
        self.assertEqual(summary["nodes"], len(mind["nodes"]))

    def test_node_decay_still_reranks_when_graph_is_unavailable(self):
        mind = {"nodes": {
            "stale": {"s": 1, "last_touch": 0, "pins": []},
            "fresh": {"s": 1, "last_touch": siamind.SECONDS_PER_DAY,
                      "pins": []}}, "edges": {}}
        ranked = siamind.ppr_rerank(
            {}, [("stale", 1.0), ("fresh", 1.0)], mind=mind,
            now=siamind.SECONDS_PER_DAY)
        self.assertEqual(ranked[0][0], "fresh")
        self.assertGreater(ranked[0][1], ranked[1][1])


class SM2(unittest.TestCase):
    def test_primary_intervals_and_lapse_restart(self):
        review = {"ef": 2.5, "reps": 0, "interval_days": 0,
                  "reviews": 0}
        siamind.sm2_update(review, 5, now=0)
        self.assertEqual(review["ef"], 2.6)
        self.assertEqual((review["reps"], review["interval_days"]), (1, 1))
        siamind.sm2_update(review, 5, now=siamind.SECONDS_PER_DAY)
        self.assertEqual((review["reps"], review["interval_days"]), (2, 6))
        siamind.sm2_update(review, 2, now=2 * siamind.SECONDS_PER_DAY)
        self.assertEqual((review["reps"], review["interval_days"]), (0, 1))
        self.assertAlmostEqual(review["ef"], 2.38)
        siamind.sm2_update(review, 5, now=3 * siamind.SECONDS_PER_DAY)
        self.assertEqual((review["reps"], review["interval_days"]), (1, 1))

    def test_later_interval_uses_pre_review_ease(self):
        review = {"ef": 2.5, "reps": 2, "interval_days": 6,
                  "reviews": 2}
        siamind.sm2_update(review, 5, now=0)
        self.assertEqual(review["interval_days"], 15)
        self.assertEqual(review["ef"], 2.6)

    def test_ease_floor(self):
        review = {"ef": 1.3, "reps": 0, "interval_days": 0,
                  "reviews": 0}
        siamind.sm2_update(review, 0, now=0)
        self.assertEqual(review["ef"], siamind.SM2_EF_FLOOR)

    def test_quality_is_highest_signal_since_review(self):
        node = {"signals": {"thought": 12, "user-ask": 13},
                "review": {"last_review": 10}}
        self.assertEqual(siamind.sm2_quality(node), 5)
        node["review"]["last_review"] = 13
        self.assertEqual(siamind.sm2_quality(node), 0)

    def test_quality_tiers_are_backed_by_real_touch_sources(self):
        node = {"signals": {"graph-query": 99, "traversal": 99},
                "review": {"last_review": 10}}
        self.assertEqual(siamind.sm2_quality(node), 0)
        node["signals"]["thought"] = 11
        self.assertEqual(siamind.sm2_quality(node), 4)
        node["signals"]["user-recall"] = 12
        self.assertEqual(siamind.sm2_quality(node), 5)

    def test_due_review_is_idempotent_and_reinforces_incident_edge(self):
        mind = siamind.migrate_mind({"nodes": {}, "edges": {}}, now=0)
        siamind.touch(mind, "important", ts=0, src="organ", arousal=0.8)
        siamind.touch(mind, "neighbor", ts=0, src="organ")
        siamind.hebb(mind, "important", "neighbor", ts=0)
        siamind.touch(mind, "important", ts=10, src="user-recall")
        before = mind["edges"]["important|neighbor"]["w"]
        snapshot = json.dumps(mind, sort_keys=True)
        planned = siamind.plan_rehearsal(mind, now=20)
        self.assertEqual(json.dumps(mind, sort_keys=True), snapshot)
        self.assertEqual(len(planned), 1)
        reviewed = siamind.apply_rehearsal(mind, planned[0], now=20)
        self.assertEqual(reviewed["quality"], 5)
        self.assertGreater(mind["edges"]["important|neighbor"]["w"], before)
        self.assertEqual(siamind.plan_rehearsal(mind, now=20), [])

    def test_unimportant_page_is_not_scheduled(self):
        mind = {"nodes": {}, "edges": {}}
        siamind.touch(mind, "routine", ts=0, src="organ", arousal=0.1)
        self.assertEqual(siamind.plan_rehearsal(mind, now=100), [])

    def test_unpin_removes_pin_only_review_eligibility(self):
        mind = {"nodes": {}, "edges": {}}
        node = siamind.set_user_pin(
            mind, "routine", True, ts=10, page_exists=lambda _slug: True)
        self.assertIn("review", node)
        self.assertTrue(siamind.is_important(node))
        siamind.set_user_pin(
            mind, "routine", False, ts=11, page_exists=lambda _slug: True)
        self.assertNotIn("review", node)
        self.assertFalse(siamind.is_important(node))
        self.assertEqual(siamind.plan_rehearsal(mind, now=12), [])


class Musing(unittest.TestCase):
    def test_musing_route_prefers_lower_learned_edge_traffic(self):
        adjacency = {
            "a": {"busy-a", "quiet-a"},
            "busy-a": {"a", "busy-b"},
            "busy-b": {"busy-a", "b"},
            "quiet-a": {"a", "quiet-b"},
            "quiet-b": {"quiet-a", "b"},
            "b": {"busy-b", "quiet-b"},
        }
        traffic = {
            "a|busy-a": 9.0,
            "busy-a|busy-b": 9.0,
            "b|busy-b": 9.0,
            "a|quiet-a": 1.0,
            "quiet-a|quiet-b": 1.0,
            "b|quiet-b": 1.0,
        }
        self.assertEqual(
            siamind._low_traffic_path(adjacency, traffic, "a", "b", 4),
            ["a", "quiet-a", "quiet-b", "b"])

    def test_seeded_musing_is_stable_across_python_hash_seeds(self):
        source = f"""
import importlib.util, json
spec = importlib.util.spec_from_file_location('mind', {os.path.join(BIN, 'siamind.py')!r})
mind_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mind_module)
node_ids = [f'r{{index}}/node' for index in range(10)]
graph = {{
    'nodes': [{{'id': slug}} for slug in node_ids],
    'edges': [
        {{'s': node_ids[index], 'd': node_ids[(index + 1) % len(node_ids)]}}
        for index in range(len(node_ids))
    ],
}}
state = {{'nodes': {{}}, 'edges': {{}}, 'musing_day': ''}}
print(json.dumps(mind_module.muse(
    state, graph, '2026-08-30', 'ledger-head', now=2000000000)))
"""
        outputs = []
        for seed in ("1", "2", "random"):
            env = dict(os.environ, PYTHONHASHSEED=seed,
                       PYTHONDONTWRITEBYTECODE="1")
            run = subprocess.run(
                [sys.executable, "-c", source], env=env,
                capture_output=True, text=True, check=True)
            outputs.append(run.stdout.strip())
        self.assertEqual(len(set(outputs)), 1)
        self.assertIsNotNone(json.loads(outputs[0]))


class Queue(unittest.TestCase):
    def test_unpin_uses_independent_recovery_lane(self):
        with tempfile.TemporaryDirectory() as root:
            old_queue = siamind.TOUCH_QUEUE
            siamind.TOUCH_QUEUE = os.path.join(root, "touches.jsonl")
            try:
                self.assertTrue(siamind.queue_pin("pinned/page", False, ts=10))
                recovery = siamind.recovery_unpin_queue_path()
                self.assertTrue(os.path.exists(recovery))
                self.assertFalse(os.path.exists(siamind.TOUCH_QUEUE))
                mind = {"nodes": {}, "edges": {}}
                drained, claim, refused = siamind.drain_touch_queue(
                    mind, now=12, queue_path=recovery, defer_ack=True,
                    claim_field="recovery_unpin_claim_sha256",
                    report_capacity=True)
                self.assertEqual((drained, refused), (0, 0))
                self.assertTrue(claim)
            finally:
                siamind.TOUCH_QUEUE = old_queue

    def test_pending_pin_snapshot_protects_both_queue_generations(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            self.assertTrue(siamind.queue_pin(
                "events/a/old", True, ts=10, queue_path=path))
            os.replace(path, path + ".draining")
            self.assertTrue(siamind.queue_pin(
                "events/b/old", True, ts=11, queue_path=path))
            self.assertTrue(siamind.queue_pin(
                "events/c/old", False, ts=12, queue_path=path))
            self.assertEqual(
                siamind.pending_user_pin_slugs(path, now=13),
                {"events/a/old", "events/b/old"})

    def test_overbound_claim_refuses_growth_without_head_of_line_block(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            mind = siamind._empty_mind()
            pinned = siamind.touch(mind, "existing", ts=1, src="organ")
            pinned["pins"] = ["user"]
            old_limit = siamind.MAX_MIND_BYTES
            siamind.MAX_MIND_BYTES = len(
                siamind._mind_text(mind).encode("utf-8")) + 1
            try:
                self.assertTrue(siamind.queue_pin(
                    "new-pin", True, ts=10, queue_path=path))
                drained, claim, refused = siamind.drain_touch_queue(
                    mind, now=12, queue_path=path, defer_ack=True,
                    page_exists=lambda _slug: True, report_capacity=True)
                self.assertEqual(drained, 0)
                self.assertEqual(refused, 1)
                self.assertNotIn("new-pin", mind["nodes"])
                siamind.acknowledge_touch_queue(claim, queue_path=path)
                self.assertFalse(os.path.exists(path + ".draining"))
            finally:
                siamind.MAX_MIND_BYTES = old_limit

    def test_touch_queue_capacity_refuses_and_reports_pressure(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            with open(path + ".draining", "wb") as stream:
                # A complete physical record remains capacity-bearing.  An
                # unterminated suffix is now durably refused and repaired.
                stream.write(b"\n")
            old_limit = siamind.MAX_TOUCH_QUEUE_BYTES
            siamind.MAX_TOUCH_QUEUE_BYTES = 1
            try:
                self.assertFalse(siamind.queue_touches(
                    ["x"], "user-recall", ts=10, queue_path=path))
                usage = siamind.touch_queue_usage(path)
                self.assertTrue(usage["at_capacity"])
            finally:
                siamind.MAX_TOUCH_QUEUE_BYTES = old_limit

    def test_malformed_touch_batch_is_retained_and_refused(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            with open(path, "w") as stream:
                stream.write("{broken\n")
            with self.assertRaisesRegex(ValueError, "malformed JSON"):
                siamind.drain_touch_queue(
                    {"nodes": {}, "edges": {}}, now=12,
                    queue_path=path)
            self.assertTrue(os.path.exists(path + ".draining"))

    def test_semantically_invalid_touch_retains_entire_unapplied_claim(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            rows = [
                {"id": "valid", "ts": 10, "src": "user-recall",
                 "slugs": ["events/valid"]},
                {"id": "invalid", "ts": 10, "src": "user-recall",
                 "slugs": "not-a-list"},
            ]
            with open(path, "w") as stream:
                for row in rows:
                    stream.write(json.dumps(row) + "\n")
            mind = {"nodes": {}, "edges": {}}
            with self.assertRaisesRegex(ValueError,
                                        "slugs must be a bounded list"):
                siamind.drain_touch_queue(mind, now=12, queue_path=path)
            self.assertTrue(os.path.exists(path + ".draining"))
            self.assertEqual(mind, {"nodes": {}, "edges": {}})

    def test_absent_unpin_never_creates_a_node(self):
        mind = {"nodes": {}, "edges": {}}
        self.assertIsNone(
            siamind.set_user_pin(mind, "does/not/exist", False, ts=10))
        self.assertEqual(mind["nodes"], {})

    def test_pin_and_recall_queue_drains_under_injected_clock(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            self.assertTrue(siamind.queue_pin("x", True, ts=10,
                                              queue_path=path))
            self.assertTrue(siamind.queue_touches(["x"], "user-recall",
                                                  ts=11, queue_path=path))
            mind = {"nodes": {}, "edges": {}}
            self.assertEqual(siamind.drain_touch_queue(
                mind, now=12, queue_path=path,
                page_exists=lambda _slug: True), 2)
            node = mind["nodes"]["x"]
            self.assertIn("user", node["pins"])
            self.assertEqual(node["signals"]["user-recall"], 11)
            self.assertEqual(siamind.sm2_quality(node), 5)

    def test_queued_absent_unpin_is_consumed_without_a_ghost_node(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            self.assertTrue(siamind.queue_pin("missing", False, ts=10,
                                              queue_path=path))
            mind = {"nodes": {}, "edges": {}}
            self.assertEqual(siamind.drain_touch_queue(
                mind, now=12, queue_path=path), 0)
            self.assertEqual(mind["nodes"], {})

    def test_claim_digest_makes_saved_batch_replay_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            mind_path = os.path.join(root, "mind.json")
            old_mind_path = siamind.MIND_PATH
            siamind.MIND_PATH = mind_path
            try:
                self.assertTrue(siamind.queue_touches(
                    ["x"], "user-recall", ts=10, queue_path=path,
                    record_id="same-generation"))
                mind = {"nodes": {}, "edges": {}}
                drained, claim = siamind.drain_touch_queue(
                    mind, now=11, queue_path=path, defer_ack=True)
                self.assertEqual(drained, 1)
                siamind.save_mind(mind)
                replayed = siamind.load_mind(now=11)
                replay_count, replay_claim = siamind.drain_touch_queue(
                    replayed, now=11, queue_path=path, defer_ack=True)
                self.assertEqual(replay_count, 0)
                self.assertEqual(replay_claim, claim)
                siamind.acknowledge_touch_queue(claim, queue_path=path)
                siamind.clear_touch_queue_claim(replayed)
                siamind.save_mind(replayed)
                persisted = siamind.load_mind(now=11)
                self.assertNotIn("touch_queue_applied", persisted)
                self.assertNotIn("touch_queue_claim_sha256", persisted)
            finally:
                siamind.MIND_PATH = old_mind_path

    def test_page_bound_thought_record_is_queue_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            kwargs = {"src": "thought", "ts": 10,
                      "queue_path": path, "record_id": "thought-stable"}
            self.assertTrue(siamind.queue_touches(["a", "b"], **kwargs))
            self.assertTrue(siamind.queue_touches(["a", "b"], **kwargs))
            with open(path) as stream:
                self.assertEqual(len(stream.read().splitlines()), 1)
            self.assertFalse(siamind.queue_touches(
                ["different"], **kwargs))

    def test_late_thought_retry_does_not_reinforce_twice(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            kwargs = {"src": "thought", "ts": 10,
                      "queue_path": path, "record_id": "thought-stable"}
            mind = {"nodes": {}, "edges": {}}
            self.assertTrue(siamind.queue_touches(["a", "b"], **kwargs))
            self.assertEqual(
                siamind.drain_touch_queue(mind, now=11, queue_path=path), 2)
            after_first = json.loads(json.dumps(mind))
            self.assertTrue(siamind.queue_touches(["a", "b"], **kwargs))
            self.assertEqual(
                siamind.drain_touch_queue(mind, now=11, queue_path=path), 0)
            self.assertEqual(mind, after_first)

    def test_acknowledged_generations_do_not_accumulate_replay_ids(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            mind_path = os.path.join(root, "mind.json")
            old_mind_path = siamind.MIND_PATH
            siamind.MIND_PATH = mind_path
            mind = {"nodes": {}, "edges": {}}
            try:
                for slug in ("first", "second", "third"):
                    self.assertTrue(siamind.queue_touches(
                        [slug], "user-recall", ts=10, queue_path=path,
                        record_id="reused-across-generations"))
                    drained, claim = siamind.drain_touch_queue(
                        mind, now=11, queue_path=path, defer_ack=True)
                    self.assertEqual(drained, 1)
                    siamind.save_mind(mind)
                    siamind.acknowledge_touch_queue(claim, queue_path=path)
                    siamind.clear_touch_queue_claim(mind)
                    siamind.save_mind(mind)
                    mind = siamind.load_mind(now=11)
                    self.assertNotIn("touch_queue_applied", mind)
                    self.assertNotIn("touch_queue_claim_sha256", mind)
                self.assertEqual(set(mind["nodes"]),
                                 {"first", "second", "third"})
            finally:
                siamind.MIND_PATH = old_mind_path


class MemoryReadiness(unittest.TestCase):
    @staticmethod
    def _ready_memo():
        return {"sync_needed": False, "ready": {
            "v": 1, "completed_at": "2026-08-30T12:00:00Z",
            "kind": "recovery", "identity": "0" * 32}}

    @staticmethod
    @contextlib.contextmanager
    def _without_unrelated_recovery_debt(runtime):
        """Keep grade-readiness tests independent of resident machine state."""
        with mock.patch.object(
                runtime, "_consolidation_scan_debt", return_value=""), \
                mock.patch.object(
                    runtime, "_thought_recovery_debt", return_value=""), \
                mock.patch.object(
                    runtime, "_graph_projection_debt", return_value=""), \
                mock.patch.object(
                    runtime.siamind, "load_mind", return_value={}), \
                mock.patch.object(
                    runtime.siatakes, "natural_history_recovery_required",
                    return_value=False), \
                mock.patch.object(
                    runtime.siatakes, "intent_history_required",
                    return_value=False):
            yield

    def test_marker_and_take_scan_share_the_corpus_transaction_lease(self):
        runtime = _load("sialib_readiness", os.path.join(BIN, "sialib.py"))
        held = {"value": False}
        trace = []

        @contextlib.contextmanager
        def owner():
            self.assertFalse(held["value"])
            held["value"] = True
            trace.append("enter")
            try:
                yield
            finally:
                trace.append("exit")
                held["value"] = False

        def load_memo():
            self.assertTrue(held["value"])
            trace.append("memo")
            return self._ready_memo()

        def migration_required():
            self.assertTrue(held["value"])
            trace.append("takes")
            return False

        def grade_required():
            self.assertTrue(held["value"])
            trace.append("grades")
            return False

        with self._without_unrelated_recovery_debt(runtime), \
                mock.patch.object(runtime, "corpus_owner", side_effect=owner), \
                mock.patch.object(runtime, "load_memo", side_effect=load_memo), \
                mock.patch.object(
                    runtime.siatakes, "grade_recovery_required",
                    side_effect=grade_required), \
                mock.patch.object(
                    runtime.siatakes, "take_migration_required",
                    side_effect=migration_required):
            self.assertEqual(runtime.memory_readiness(), (True, ""))
        self.assertEqual(trace,
                         ["enter", "memo", "grades", "takes", "exit"])

    def test_any_grade_journal_blocks_readiness_without_parsing_it(self):
        runtime = _load(
            "sialib_grade_readiness", os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as root:
            transactions = os.path.join(root, "grade-transactions")
            os.makedirs(transactions)
            with open(os.path.join(transactions, "malformed.json"), "w",
                      encoding="utf-8") as stream:
                stream.write("not a transaction")
            migration = mock.Mock(return_value=False)
            with self._without_unrelated_recovery_debt(runtime), \
                    mock.patch.object(
                    runtime, "corpus_owner",
                    return_value=contextlib.nullcontext()), \
                    mock.patch.object(runtime, "load_memo",
                                      return_value=self._ready_memo()), \
                    mock.patch.object(runtime.siatakes, "GRADE_TX_DIR",
                                      transactions), \
                    mock.patch.object(
                        runtime.siatakes, "take_migration_required",
                        migration):
                ready, reason = runtime.memory_readiness()
        self.assertFalse(ready)
        self.assertIn("grade transaction", reason)
        migration.assert_not_called()

    def test_symlinked_grade_transaction_store_blocks_readiness(self):
        runtime = _load(
            "sialib_symlink_grade_readiness", os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, "real-grade-transactions")
            linked = os.path.join(root, "grade-transactions")
            os.makedirs(target)
            os.symlink(target, linked)
            migration = mock.Mock(return_value=False)
            with self._without_unrelated_recovery_debt(runtime), \
                    mock.patch.object(
                    runtime, "corpus_owner",
                    return_value=contextlib.nullcontext()), \
                    mock.patch.object(runtime, "load_memo",
                                      return_value=self._ready_memo()), \
                    mock.patch.object(runtime.siatakes, "GRADE_TX_DIR",
                                      linked), \
                    mock.patch.object(
                        runtime.siatakes, "take_migration_required",
                        migration):
                ready, reason = runtime.memory_readiness()
        self.assertFalse(ready)
        self.assertIn("not a real directory", reason)
        migration.assert_not_called()


class CLI(unittest.TestCase):
    def test_installed_cli_resolves_runtime_modules_and_rejects_bad_slugs(self):
        cli = _load_script("sia_cli_paths", os.path.join(BIN, "sia"))
        with tempfile.TemporaryDirectory() as root:
            runtime = os.path.join(root, ".local/share/sia/bin")
            os.makedirs(runtime)
            with open(os.path.join(runtime, "sialib.py"), "w") as stream:
                stream.write("# runtime marker\n")
            self.assertEqual(
                cli._runtime_module_dir(
                    script_path=os.path.join(root, ".local/bin/sia"),
                    home=root),
                runtime)
        self.assertTrue(cli._canonical_slug("events/jackal/2026-08-30"))
        self.assertFalse(cli._canonical_slug("../../private"))
        self.assertFalse(cli._canonical_slug("UPPERCASE"))

    def test_no_touch_flags_reach_ask_and_recall(self):
        cli = _load_script("sia_cli_rehearsal", os.path.join(BIN, "sia"))
        seen = []
        cli.cmd_ask = lambda q, touch=True: seen.append(("ask", q, touch)) or 0
        cli.cmd_recall = lambda slug, touch=True: \
            seen.append(("recall", slug, touch)) or 0
        with mock.patch.object(
                cli.sialib, "memory_readiness", return_value=(True, "")):
            self.assertEqual(
                cli.main(["sia", "ask", "--no-touch", "old", "fix"]), 0)
            self.assertEqual(
                cli.main(["sia", "recall", "old/fix", "--no-touch"]), 0)
        self.assertEqual(seen, [("ask", "old fix", False),
                                ("recall", "old/fix", False)])

    def test_memory_commands_refuse_before_upgrade_reconciliation(self):
        cli = _load_script("sia_cli_migration_gate", os.path.join(BIN, "sia"))
        cli.cmd_ask = mock.Mock(return_value=0)
        output = io.StringIO()
        with mock.patch.object(
                cli.sialib, "memory_readiness",
                return_value=(False, "legacy migration pending")), \
                contextlib.redirect_stdout(output):
            result = cli.main(["sia", "ask", "old links"])
        self.assertEqual(result, 1)
        cli.cmd_ask.assert_not_called()
        self.assertIn("memory read refused", output.getvalue())

    def test_gbrain_read_uses_owner_locked_wrapper_and_retries(self):
        cli = _load_script("sia_cli_owner", os.path.join(BIN, "sia"))
        calls = []
        class Result:
            def __init__(self, rc, err=""):
                self.returncode, self.stdout, self.stderr = rc, "", err
        replies = [Result(1, "already open"), Result(0)]
        old_gbrain = cli.sialib.gbrain
        cli.sialib.gbrain = lambda args, timeout=0: \
            calls.append(args) or replies.pop(0)
        old_sleep = __import__("time").sleep
        __import__("time").sleep = lambda _: None
        try:
            got = cli._gbrain_read(["get", "x", "--source", "sia"])
        finally:
            __import__("time").sleep = old_sleep
            cli.sialib.gbrain = old_gbrain
        self.assertEqual(got.returncode, 0)
        self.assertEqual(calls, [["get", "x", "--source", "sia"]] * 2)


class DreamIntegration(unittest.TestCase):
    def test_due_page_is_reembedded_and_schedule_persisted(self):
        sialib = _load("sialib_rehearsal", os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as root:
            state = os.path.join(root, "state")
            corpus = os.path.join(root, "corpus")
            os.makedirs(os.path.join(corpus, "events/x"))
            os.makedirs(state)
            with open(os.path.join(corpus, "events/x/day.md"), "w") as page:
                page.write("# x\n")
            sialib.CORPUS = corpus
            sialib.GRAPH_PATH = os.path.join(state, "graph.json")
            sialib.siamind.MIND_PATH = os.path.join(state, "mind.json")
            sialib.atomic_write(sialib.GRAPH_PATH, json.dumps(
                {"nodes": [{"id": "events/x/day"}], "edges": []}))
            mind = {"nodes": {}, "edges": {}}
            sialib.siamind.touch(mind, "events/x/day", ts=0, src="organ",
                                 arousal=0.8)
            sialib.siamind.touch(mind, "events/x/day", ts=1,
                                 src="user-recall")
            sialib.siamind.save_mind(mind)

            calls = []
            class Result:
                returncode, stdout, stderr = 0, "", ""
            sialib.gbrain = lambda args, timeout=0: calls.append(args) or Result()
            report = sialib.rehearse_memories(now=2)
            self.assertEqual(report["embedded"], 1)
            self.assertEqual(
                calls, [["embed", "events/x/day", "--source", "sia"]])
            saved = sialib.siamind.load_mind(now=2)
            self.assertEqual(saved["nodes"]["events/x/day"]
                             ["review"]["last_quality"], 5)

    def test_embed_failure_or_missing_page_leaves_schedule_and_edges_due(self):
        sialib = _load("sialib_rehearsal_failure",
                       os.path.join(BIN, "sialib.py"))
        with tempfile.TemporaryDirectory() as root:
            state = os.path.join(root, "state")
            corpus = os.path.join(root, "corpus")
            os.makedirs(os.path.join(corpus, "events/x"))
            os.makedirs(state)
            with open(os.path.join(corpus, "events/x/day.md"), "w") as page:
                page.write("# x\n")
            sialib.CORPUS = corpus
            sialib.GRAPH_PATH = os.path.join(state, "graph.json")
            sialib.siamind.MIND_PATH = os.path.join(state, "mind.json")
            sialib.atomic_write(sialib.GRAPH_PATH, json.dumps(
                {"nodes": [{"id": "events/x/day"}, {"id": "neighbor"}],
                 "edges": [{"s": "events/x/day", "d": "neighbor"}]}))
            mind = {"nodes": {}, "edges": {}}
            sialib.siamind.touch(mind, "events/x/day", ts=0, src="organ",
                                 arousal=0.8)
            sialib.siamind.touch(mind, "neighbor", ts=0, src="organ")
            sialib.siamind.hebb(mind, "events/x/day", "neighbor", ts=0)
            sialib.siamind.touch(mind, "events/x/day", ts=1,
                                 src="user-recall")
            review_before = dict(mind["nodes"]["events/x/day"]["review"])
            edge_before = dict(mind["edges"]["events/x/day|neighbor"])
            sialib.siamind.save_mind(mind)

            class Result:
                returncode, stdout, stderr = 1, "", "embed failed"
            sialib.gbrain = lambda args, timeout=0: Result()
            report = sialib.rehearse_memories(now=2)
            self.assertEqual(report["embedded"], 0)
            self.assertEqual(report["failed"], 1)
            self.assertEqual(report["reviewed"], [])
            saved = sialib.siamind.load_mind(now=2)
            node = saved["nodes"]["events/x/day"]
            edge = saved["edges"]["events/x/day|neighbor"]
            self.assertEqual(node["review"], review_before)
            self.assertNotIn("review", node["signals"])
            self.assertEqual(edge["w"], edge_before["w"])
            self.assertEqual(edge["s"], edge_before["s"])
            self.assertEqual(edge["last_touch"], edge_before["last_touch"])
            self.assertEqual(len(sialib.siamind.plan_rehearsal(saved, now=2)),
                             1)

            os.unlink(os.path.join(corpus, "events/x/day.md"))
            missing = sialib.rehearse_memories(now=2)
            self.assertEqual(missing["missing"], 1)
            self.assertEqual(missing["reviewed"], [])
            saved_missing = sialib.siamind.load_mind(now=2)
            self.assertEqual(saved_missing["nodes"]["events/x/day"]["review"],
                             review_before)
            self.assertEqual(
                saved_missing["edges"]["events/x/day|neighbor"]["w"],
                edge_before["w"])
            self.assertEqual(len(sialib.siamind.plan_rehearsal(
                saved_missing, now=2)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
