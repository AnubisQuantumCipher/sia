#!/usr/bin/env python3
"""Behavior contracts for SIA's bounded attention and novelty policies."""

import copy
import os
import sys
import tempfile
import unittest

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "bin"))

import siamind


class AttentionWindowContract(unittest.TestCase):
    """The component selects and broadcasts a bounded window, not consciousness."""

    @staticmethod
    def _mind(order, *, incumbent=()):
        nodes = {}
        for slug in order:
            nodes[slug] = {
                "n": 1.0,
                "t0": 100.0,
                "rt": [[100.0, 1.0]],
            }
        return {"nodes": nodes, "workspace": list(incumbent)}

    def test_selection_is_inspectable_and_broadcast_to_named_consumers(self):
        slugs = [
            "events/alpha/one",
            "events/alpha/two",
            "events/alpha/three",
            "packages/four",
        ]
        mind = self._mind(slugs)
        before = copy.deepcopy(mind)
        result = siamind.attention_window_broadcast(
            mind, {"alpha": 0.5},
            consumers=("resident-status", "context-selection"),
            as_of=100.0)

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["as_of"], 100.0)
        self.assertLessEqual(len(result["slots"]), siamind.WORKSPACE_K)
        self.assertLessEqual(
            sum(slug.startswith("events/alpha/")
                for slug in result["slots"]), 2)
        self.assertEqual(
            result["broadcast"],
            {"resident-status": result["slots"],
             "context-selection": result["slots"]})
        self.assertEqual(mind, before, "selection must be side-effect free")
        self.assertEqual(
            {row["slug"] for row in result["candidates"]}, set(slugs))
        self.assertTrue(all(
            set(row) == {"slug", "bucket", "score", "incumbent_gain",
                         "adjusted_score", "ignited", "selected"}
            for row in result["candidates"]))

    def test_wrapper_persists_exact_selected_window(self):
        mind = self._mind(["packages/b", "units/a"])
        expected = siamind.attention_window_broadcast(
            mind, {}, consumers=("resident-status",), as_of=100.0)["slots"]
        self.assertEqual(
            siamind.rebuild_workspace(mind, {}, now=100.0), expected)
        self.assertEqual(mind["workspace"], expected)

    def test_global_window_ceiling_excludes_later_eligible_candidates(self):
        slugs = [
            f"source-{index}/item"
            for index in range(siamind.WORKSPACE_K + 3)
        ]
        result = siamind.attention_window_broadcast(
            self._mind(slugs), {}, consumers=("resident-status",),
            as_of=100.0)

        self.assertEqual(len(result["slots"]), siamind.WORKSPACE_K)
        self.assertEqual(
            sum(row["selected"] for row in result["candidates"]),
            siamind.WORKSPACE_K,
        )
        self.assertTrue(any(
            row["ignited"] and not row["selected"]
            for row in result["candidates"]
        ))

    def test_invalid_broadcast_contract_refuses_without_mutation(self):
        mind = self._mind(["units/a"])
        before = copy.deepcopy(mind)
        for consumers in (("status", "status"), ("",), (None,)):
            with self.subTest(consumers=consumers), \
                    self.assertRaises(ValueError):
                siamind.attention_window_broadcast(
                    mind, {}, consumers=consumers, as_of=100.0)
            self.assertEqual(mind, before)


class NoveltyEncodingContract(unittest.TestCase):
    """Stored-prediction mismatch changes encoding strength and then learns."""

    @staticmethod
    def _graph(nodes, *, pages_total=None, aged_out=0, truncated=0,
               omitted_nodes=0, complete=True):
        pages_total = len(nodes) + aged_out if pages_total is None \
            else pages_total
        counts = {}
        for node in nodes:
            counts[node["t"]] = counts.get(node["t"], 0) + 1
        return {
            "nodes": copy.deepcopy(nodes),
            "pages_total": pages_total,
            "pages_total_complete": complete,
            "snapshot": {
                "complete": complete,
                "truncated": truncated,
                "omitted_nodes": omitted_nodes,
                "omitted_edges": 0,
                "omissions_imply_absence": False,
                "aged_out": aged_out,
                "counts_by_kind": counts,
                "failed_ops": [] if complete else ["list_pages"],
                "window_days": 14,
            },
        }

    def test_missing_mind_cannot_claim_complete_familiarity(self):
        with tempfile.TemporaryDirectory() as root:
            previous = siamind.MIND_PATH
            siamind.MIND_PATH = os.path.join(root, "missing-mind.json")
            try:
                mind = siamind.load_mind(now=100.0)
            finally:
                siamind.MIND_PATH = previous
        self.assertEqual(mind["seen"], {})
        self.assertFalse(mind["familiarity_complete"])
        self.assertTrue(mind["familiarity_bootstrap_pending"])

    def test_exhaustive_history_free_bootstrap_enables_real_first_claims(self):
        known = "units/known"
        novel = "units/novel"
        mind = siamind._empty_mind()
        mind["familiarity_complete"] = False
        mind["familiarity_bootstrap_pending"] = True
        graph = self._graph([{"id": known, "t": "unit"}])

        self.assertEqual(
            siamind.baseline_graph_familiarity(
                mind, graph, observed_at=100.0),
            1,
        )
        self.assertEqual(mind["seen"], {known: 100.0})
        self.assertTrue(mind["familiarity_complete"])
        self.assertFalse(mind["familiarity_bootstrap_pending"])

        result = siamind.novelty_encoding_gate(
            mind, "organ", "kind", [novel], ["kind"],
            observed_at=200.0,
        )
        self.assertEqual(result["familiarity_status"], "complete")
        self.assertTrue(any(
            reason == f"first recorded occurrence of {novel}"
            for reason in result["reasons"]
        ))
        self.assertIn("new event shape organ/kind", result["reasons"])

    def test_history_bearing_inventory_cannot_complete_bootstrap(self):
        for page_kind, slug in (
                ("event-day", "events/organ/day"),
                ("epoch", "epochs/organ/week")):
            with self.subTest(page_kind=page_kind):
                mind = siamind._empty_mind()
                mind["familiarity_complete"] = False
                mind["familiarity_bootstrap_pending"] = True
                graph = self._graph([{"id": slug, "t": page_kind}])

                self.assertEqual(
                    siamind.baseline_graph_familiarity(
                        mind, graph, observed_at=100.0),
                    1,
                )
                self.assertEqual(mind["seen"], {slug: 100.0})
                self.assertFalse(mind["familiarity_complete"])
                self.assertFalse(mind["familiarity_bootstrap_pending"])

    def test_history_namespace_disguised_as_note_cannot_complete_bootstrap(self):
        for slug in ("events/organ/day", "epochs/organ/week"):
            with self.subTest(slug=slug):
                mind = siamind._empty_mind()
                mind["familiarity_complete"] = False
                mind["familiarity_bootstrap_pending"] = True
                graph = self._graph([{"id": slug, "t": "note"}])
                siamind.baseline_graph_familiarity(
                    mind, graph, observed_at=100.0)
                self.assertFalse(mind["familiarity_complete"])
                self.assertFalse(mind["familiarity_bootstrap_pending"])

    def test_admitted_graph_omissions_terminally_withhold_completeness(self):
        base = self._graph([{"id": "units/visible", "t": "unit"}])
        cases = []
        aged = copy.deepcopy(base)
        aged["pages_total"] = 2
        aged["snapshot"]["aged_out"] = 1
        cases.append(aged)
        truncated = copy.deepcopy(base)
        truncated["pages_total"] = 2
        truncated["snapshot"]["truncated"] = 1
        truncated["snapshot"]["omitted_nodes"] = 1
        cases.append(truncated)
        omitted_edges = copy.deepcopy(base)
        omitted_edges["snapshot"]["omitted_edges"] = 1
        cases.append(omitted_edges)

        for graph in cases:
            mind = siamind._empty_mind()
            mind["familiarity_complete"] = False
            mind["familiarity_bootstrap_pending"] = True
            with self.subTest(snapshot=graph["snapshot"]):
                self.assertEqual(
                    siamind.baseline_graph_familiarity(
                        mind, graph, observed_at=100.0),
                    1,
                )
                self.assertEqual(mind["seen"], {"units/visible": 100.0})
                self.assertFalse(mind["familiarity_complete"])
                self.assertFalse(mind["familiarity_bootstrap_pending"])

    def test_unadmitted_or_malformed_graph_refuses_bootstrap_atomically(self):
        base = self._graph([{"id": "units/visible", "t": "unit"}])
        cases = []
        partial = copy.deepcopy(base)
        partial["pages_total_complete"] = False
        partial["snapshot"]["complete"] = False
        partial["snapshot"]["failed_ops"] = ["list_pages"]
        cases.append(partial)
        inconsistent = copy.deepcopy(base)
        inconsistent["snapshot"]["failed_ops"] = ["list_pages"]
        cases.append(inconsistent)
        wrong_total = copy.deepcopy(base)
        wrong_total["pages_total"] = 2
        cases.append(wrong_total)
        wrong_omission = copy.deepcopy(base)
        wrong_omission["snapshot"]["omitted_nodes"] = 1
        cases.append(wrong_omission)

        for graph in cases:
            mind = siamind._empty_mind()
            mind["familiarity_complete"] = False
            mind["familiarity_bootstrap_pending"] = True
            before = copy.deepcopy(mind)
            with self.subTest(graph=graph), self.assertRaisesRegex(
                    ValueError, "graph familiarity"):
                siamind.baseline_graph_familiarity(
                    mind, graph, observed_at=100.0)
            self.assertEqual(mind, before)

    def test_settled_familiarity_never_rebaselines_or_refreshes(self):
        graph = self._graph([{"id": "units/new", "t": "unit"}])
        for complete, seen in (
                (True, {"units/known": 50.0}),
                (False, {})):
            mind = siamind._empty_mind()
            mind["familiarity_complete"] = complete
            mind["familiarity_bootstrap_pending"] = False
            mind["seen"] = copy.deepcopy(seen)
            before = copy.deepcopy(mind)
            with self.subTest(complete=complete):
                self.assertEqual(
                    siamind.baseline_graph_familiarity(
                        mind, graph, observed_at=100.0),
                    0,
                )
                self.assertEqual(mind, before)

    def test_pending_bootstrap_requires_an_empty_familiarity_map(self):
        mind = siamind._empty_mind()
        mind["familiarity_complete"] = False
        mind["familiarity_bootstrap_pending"] = True
        mind["seen"] = {"units/known": 50.0}
        before = copy.deepcopy(mind)
        with self.assertRaisesRegex(ValueError, "bootstrap requires"):
            siamind.baseline_graph_familiarity(
                mind,
                self._graph([{"id": "units/new", "t": "unit"}]),
                observed_at=100.0,
            )
        self.assertEqual(mind, before)

    def test_pending_bootstrap_cannot_observe_before_graph_admission(self):
        mind = siamind._empty_mind()
        mind["familiarity_complete"] = False
        mind["familiarity_bootstrap_pending"] = True
        before = copy.deepcopy(mind)
        with self.assertRaisesRegex(ValueError, "bootstrap is pending"):
            siamind.novelty_encoding_gate(
                mind, "organ", "kind", ["units/example"], ["kind"],
                observed_at=100.0,
            )
        self.assertEqual(mind, before)

    def test_bounded_graph_cannot_mint_first_or_new_shape_claims(self):
        visible = "units/visible"
        missing = "units/aged-out"
        mind = siamind._empty_mind()
        mind["familiarity_complete"] = False
        mind["familiarity_bootstrap_pending"] = True
        graph = self._graph(
            [{"id": visible, "t": "unit"}], pages_total=2, aged_out=1)

        self.assertEqual(
            siamind.baseline_graph_familiarity(
                mind, graph, observed_at=100.0),
            1,
        )
        self.assertEqual(mind["seen"], {visible: 100.0})
        self.assertFalse(mind["familiarity_complete"])
        self.assertFalse(mind["familiarity_bootstrap_pending"])
        result = siamind.novelty_encoding_gate(
            mind, "organ", "kind", [visible, missing], ["kind"],
            observed_at=200.0,
        )
        self.assertFalse(any(
            "first recorded occurrence" in reason
            or "new event shape" in reason
            for reason in result["reasons"]
        ))
        self.assertEqual(result["familiarity_status"], "incomplete")

    def test_first_mismatch_repeat_and_return_are_explicit(self):
        mind = siamind._empty_mind()
        first = siamind.novelty_encoding_gate(
            mind, "organ", "kind", ["units/example"], ["kind"],
            observed_at=1_000_000_000.0)
        repeated = siamind.novelty_encoding_gate(
            mind, "organ", "kind", ["units/example"], ["kind"],
            observed_at=1_000_003_600.0)
        returned = siamind.novelty_encoding_gate(
            mind, "organ", "kind", ["units/example"], ["kind"],
            observed_at=1_004_000_000.0)

        for result in (first, repeated, returned):
            self.assertEqual(
                set(result),
                {"status", "mismatch", "score", "encoding_gain",
                 "reasons", "observed_at", "familiarity_status"})
            self.assertEqual(result["status"], "observed")
            self.assertEqual(result["familiarity_status"], "complete")
            self.assertEqual(result["score"], result["encoding_gain"])
        self.assertTrue(first["mismatch"])
        self.assertFalse(repeated["mismatch"])
        self.assertTrue(returned["mismatch"])
        self.assertGreater(first["encoding_gain"], repeated["encoding_gain"])
        self.assertGreater(returned["encoding_gain"], repeated["encoding_gain"])

    def test_older_observation_cannot_move_familiarity_backward(self):
        latest = 1_004_000_000.0
        older = 1_000_000_000.0
        follow_up = 1_004_000_100.0
        entity = "units/example"
        pair = "pair:organ:kind"
        mind = {"seen": {entity: latest, pair: latest}}

        siamind.novelty_encoding_gate(
            mind, "organ", "kind", [entity], ["kind"],
            observed_at=older)

        self.assertEqual(mind["seen"][entity], latest)
        self.assertEqual(mind["seen"][pair], latest)
        result = siamind.novelty_encoding_gate(
            mind, "organ", "kind", [entity], ["kind"],
            observed_at=follow_up)
        self.assertFalse(any(
            "observation gap" in reason for reason in result["reasons"]))
        self.assertEqual(result["encoding_gain"], 0.0)

        self.assertEqual(mind["seen"][entity], follow_up)
        self.assertEqual(mind["seen"][pair], follow_up)

    def test_compaction_cannot_mint_a_first_observation_claim(self):
        organ = "o" * siamind.MAX_FAMILIARITY_TOKEN_CHARS
        kind = "k" * siamind.MAX_FAMILIARITY_TOKEN_CHARS
        entity = "units/" + "e" * siamind.MAX_FAMILIARITY_LEAF_BYTES
        pair = f"pair:{organ}:{kind}"
        retained = "zz-retained"
        mind = siamind._empty_mind()
        mind["familiarity_complete"] = True
        mind["seen"].update({
            pair: 100.0,
            entity: 100.0,
            retained: 100.0,
        })
        expected = copy.deepcopy(mind)
        expected["seen"] = {retained: 100.0}
        expected["familiarity_complete"] = False
        expected["capacity"] = {
            "evicted_edges": 0,
            "evicted_nodes": 0,
            "evicted_safety_edges": 0,
            "evicted_safety_nodes": 0,
            "evicted_cache_entries": 2,
        }
        limit = len(siamind._mind_text(expected).encode("utf-8"))

        removed = siamind.compact_mind_for_persistence(
            mind, max_bytes=limit)

        self.assertEqual(removed["cache_entries"], 2)
        self.assertEqual(mind["seen"], {retained: 100.0})
        self.assertFalse(mind["familiarity_complete"])
        graph = {"nodes": [{"id": entity}], "edges": []}
        siamind.sync_graph_state(mind, graph, now=200.0)
        self.assertIn(entity, mind["nodes"])
        fully_evicted = copy.deepcopy(mind)
        fully_evicted["seen"].clear()
        self.assertEqual(
            siamind.baseline_graph_familiarity(
                fully_evicted, graph, observed_at=200.0),
            0)
        self.assertEqual(fully_evicted["seen"], {})
        result = siamind.novelty_encoding_gate(
            mind, organ, kind, [entity], [kind],
            observed_at=200.0)
        self.assertEqual(result["familiarity_status"], "incomplete")
        self.assertFalse(result["mismatch"])
        self.assertEqual(result["encoding_gain"], 0.0)
        self.assertFalse(any(
            "first recorded occurrence" in reason
            or "new event shape" in reason
            for reason in result["reasons"]))
        self.assertIn(entity, mind["seen"])
        self.assertIn(pair, mind["seen"])
        self.assertFalse(mind["familiarity_complete"])

    def test_incomplete_familiarity_retains_recurrence_without_minting_firsts(
            self):
        retained = "units/retained"
        missing = "units/missing"
        organ = "organ"
        kind = "kind"
        pair = f"pair:{organ}:{kind}"
        mind = siamind._empty_mind()
        mind["seen"] = {retained: 100.0}
        mind["familiarity_complete"] = False

        result = siamind.novelty_encoding_gate(
            mind, organ, kind, [retained, missing], [],
            observed_at=100.0 + 31 * 86400)

        self.assertEqual(result["familiarity_status"], "incomplete")
        self.assertTrue(any(
            "observation gap" in reason for reason in result["reasons"]))
        self.assertFalse(any(
            "first recorded occurrence" in reason
            or "new event shape" in reason
            for reason in result["reasons"]))
        self.assertIn(missing, mind["seen"])
        self.assertIn(pair, mind["seen"])
        self.assertFalse(mind["familiarity_complete"])

    def test_encoding_gain_changes_existing_trace_strength(self):
        ordinary = siamind._empty_mind()
        enhanced = siamind._empty_mind()
        siamind.touch(ordinary, "events/o/day", ts=100.0, src="organ")
        siamind.touch(enhanced, "events/o/day", ts=100.0, src="organ")

        siamind.touch(
            ordinary, "events/o/day", ts=200.0, src="organ",
            novelty_score=0.0)
        siamind.touch(
            enhanced, "events/o/day", ts=200.0, src="organ",
            novelty_score=1.0)
        self.assertGreater(
            enhanced["nodes"]["events/o/day"]["s"],
            ordinary["nodes"]["events/o/day"]["s"])

    def test_novelty_input_changes_existing_learned_edge_stability(self):
        ordinary = siamind._empty_mind()
        enhanced = siamind._empty_mind()
        left = "events/o/day"
        right = "units/example"
        key = f"{left}|{right}"
        siamind.hebb(ordinary, left, right, ts=100.0)
        siamind.hebb(enhanced, left, right, ts=100.0)

        siamind.hebb(
            ordinary, left, right, ts=200.0, novelty_score=0.0)
        siamind.hebb(
            enhanced, left, right, ts=200.0, novelty_score=1.0)

        self.assertEqual(
            enhanced["edges"][key]["w"], ordinary["edges"][key]["w"])
        self.assertGreater(
            enhanced["edges"][key]["s"], ordinary["edges"][key]["s"])

    def test_invalid_observation_refuses_atomically(self):
        mind = {
            "seen": {"existing": 100.0},
            "familiarity_complete": True,
        }
        before = copy.deepcopy(mind)
        bad_cases = [
            ("", "kind", ["units/example"], ["kind"], 200.0),
            ("organ", "", ["units/example"], ["kind"], 200.0),
            ("organ", "kind", [None], ["kind"], 200.0),
            ("organ", "kind", ["units/example"], [None], 200.0),
            ("organ", "kind", ["units/example"], ["kind"], float("inf")),
        ]
        for organ, kind, entities, surround, observed_at in bad_cases:
            with self.subTest(organ=organ, kind=kind, entities=entities,
                              surround=surround, observed_at=observed_at), \
                    self.assertRaises(ValueError):
                siamind.novelty_encoding_gate(
                    mind, organ, kind, entities, surround,
                    observed_at=observed_at)
            self.assertEqual(mind, before)

    def test_noncanonical_familiarity_identities_refuse_atomically(self):
        cases = (
            ("UPPER", "kind", ["units/example"]),
            ("organ", "kind:extra", ["units/example"]),
            ("organ", "kind", ["../escape"]),
            ("organ", "kind", ["units//ambiguous"]),
        )
        for organ, kind, entities in cases:
            mind = siamind._empty_mind()
            before = copy.deepcopy(mind)
            with self.subTest(organ=organ, kind=kind, entities=entities), \
                    self.assertRaisesRegex(ValueError, "familiarity"):
                siamind.novelty_encoding_gate(
                    mind, organ, kind, entities, [kind], observed_at=100.0)
            self.assertEqual(mind, before)

        mind = siamind._empty_mind()
        mind["familiarity_complete"] = False
        mind["familiarity_bootstrap_pending"] = True
        before = copy.deepcopy(mind)
        graph = self._graph([{"id": "../escape", "t": "unit"}])
        with self.assertRaisesRegex(ValueError, "familiarity"):
            siamind.baseline_graph_familiarity(
                mind, graph, observed_at=100.0)
        self.assertEqual(mind, before)


if __name__ == "__main__":
    unittest.main()
