#!/usr/bin/env python3
"""Known old explanation bytes are preservation-only, never read authority.

The inspected installed producer used whitespace collapse, then strip, then
[:90], without inert_summary, and omitted publication_id. This compatibility
contract admits only that bounded explanation shape in the already-explicit
legacy regeneration transaction. It does not authenticate a historical
producer, change content/origin, or authorize an old graph for ranking.

Root runs these tests sequentially. Every mutable path and public-command
dependency below comes from the existing isolated repair fixture; no resident
corpus, CLI, graph, keeper, model, daemon, or database is used.
"""

import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

try:
    import test_cortex_legacy_graph_repair as legacy
except ModuleNotFoundError:
    from tests import test_cortex_legacy_graph_repair as legacy


OPAQUE_WHY = "See [[sia/cortex]] | <b>opaque</b> `context` *only*"
# Routed before writing these derived fixtures. Exact is not formal-bounded
# and does not establish correctness of the graph or compatibility code.
JACKAL_FIXTURES = [
    {"parsed": "1+1", "exact": "2", "status": "exact"},
    {"parsed": "90-1", "exact": "89", "status": "exact"},
    {"parsed": "90+1", "exact": "91", "status": "exact"},
]
JACKAL_NON_CLAIMS = [
    "NOT formal-bounded: this lane carries no Lean-checked certificate",
    "The epistemic class above is the STRONGEST claim this result supports",
    "exact rational arithmetic (not yet checker-covered)",
]


class CortexLegacyExplanationCompatibility(unittest.TestCase):
    def setUp(self):
        # Compose, rather than inherit and rerun, the existing repair suite.
        self.fx = legacy.CortexLegacyGraphRepair(methodName="runTest")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.core = self.fx.core
        self.graph = copy.deepcopy(self.fx.legacy)
        self.graph.update(
            nodes=[{"id": "sia/cortex", "t": "organ", "title": "Cortex",
                    "ts": self.graph["ts"], "origin": "derived",
                    "din": 1, "dout": 1, "deg": 2}],
            edges=[{"s": "sia/cortex", "d": "sia/cortex", "t": "mentions",
                    "why": OPAQUE_WHY}],
            pages_total=1,
        )
        self.graph["snapshot"]["counts_by_kind"] = {"organ": 1}
        self._install(self.graph)

    def _install(self, graph):
        self.fx.legacy = copy.deepcopy(graph)
        # Noncanonical JSON whitespace and original UTF-8 survive verbatim.
        self.fx.legacy_raw = ("\n " + json.dumps(
            graph, indent=2, ensure_ascii=False) + "\n\n").encode("utf-8")
        self.fx.graph_path.write_bytes(self.fx.legacy_raw)
        self.fx.graph_path.chmod(0o600)

    def _with_why(self, why):
        graph = copy.deepcopy(self.graph)
        graph["edges"][0]["why"] = why
        return graph

    def _current(self, graph):
        return {**copy.deepcopy(graph), "publication_id": legacy.FRESH_PUBLICATION_ID}

    def _public(self, *, explicit):
        arguments = ["sia", "repair-cortex-boundary", "--json"]
        if explicit:
            arguments.append("--regenerate-legacy-graph")
        stdout = io.StringIO()
        with mock.patch.object(self.core, "_lifecycle_reader", return_value=contextlib.nullcontext()), \
                mock.patch.dict(sys.modules, {"sialib": self.core, "siacortexrepair": self.fx.repair}), \
                contextlib.redirect_stdout(stdout):
            status = self.fx.fx.cli.main(arguments)
        return status, json.loads(stdout.getvalue()), stdout.getvalue()

    def test_known_old_markup_is_boolean_classification_only_and_exact_bytes_are_untouched(self):
        canonical = self._current(self._with_why(self.core.inert_summary(OPAQUE_WHY)))
        self.assertIsNotNone(self.core._recoverable_graph_snapshot(canonical),
                             "control graph must satisfy every non-explanation invariant")
        for why in (OPAQUE_WHY, "[[sia/cortex]]", "[label](target)", "<b>é</b>", "`code` | *markup*"):
            graph = self._with_why(why)
            before = copy.deepcopy(graph)
            with self.subTest(why=why):
                self.assertIsNone(self.core._recoverable_graph_snapshot(graph))
                self.assertIsNone(self.core._recoverable_graph_snapshot(self._current(graph)),
                                  "a valid publication ID must not excuse active explanation markup")
                self.assertIs(self.core._legacy_graph_snapshot_body_valid(graph), True)
                self.assertIs(self.core._legacy_graph_snapshot_body_valid(self._current(graph)), False)
                self.assertEqual(graph, before, "classification sanitized or manufactured history")
        self.assertEqual(self.fx.graph_path.read_bytes(), self.fx.legacy_raw)
        self.assertFalse(self.fx.preserved.exists())

    def test_old_character_ceiling_allows_only_the_actual_post_strip_clipping_boundary(self):
        # The old Python slice was by characters, and could expose a final
        # normalized space after stripping the untruncated context first.
        boundary_space = "x" * 89 + " "
        for why in ("é" * 90, "[" * 90, boundary_space):
            graph = self._with_why(why)
            with self.subTest(why=repr(why)):
                self.assertIs(self.core._legacy_graph_snapshot_body_valid(graph), True)
                self.assertEqual(graph["edges"][0]["why"], why)
        self.assertIsNone(self.core._recoverable_graph_snapshot(
            self._current(self._with_why(boundary_space))))

    def test_legacy_explanation_admission_is_not_a_general_text_normalizer(self):
        malformed = [" leading", "trailing ", "repeated  space", "\tleading",
                     "line\nbreak", "return\rbreak", "nonbreaking\u00a0space",
                     "wide\u2003space", "escape\x1b[0m", "format\u202etext",
                     "nul\x00text", "surrogate\ud800", "x" * 91,
                     None, False, [], {"text": OPAQUE_WHY}]
        for why in malformed:
            graph = self._with_why(why)
            before = copy.deepcopy(graph)
            with self.subTest(why=repr(why)):
                self.assertIs(self.core._legacy_graph_snapshot_body_valid(graph), False)
                self.assertIsNone(self.core._recoverable_graph_snapshot(self._current(graph)))
                self.assertEqual(graph, before)

    def test_all_non_explanation_invariants_still_refuse_with_old_markup(self):
        variants = []

        def change(label, mutation):
            graph = copy.deepcopy(self.graph)
            mutation(graph)
            variants.append((label, graph))

        change("unknown top-level authority", lambda g: g.update(extra=True))
        change("malformed publication identity", lambda g: g.update(publication_id=None))
        change("page count", lambda g: g.update(pages_total=2))
        change("Boolean page count", lambda g: g.update(pages_total=True))
        change("unknown origin", lambda g: g["nodes"][0].update(origin="trusted"))
        change("active node title", lambda g: g["nodes"][0].update(title="[[Cortex]]"))
        change("inexact degree", lambda g: g["nodes"][0].update(deg=2.0))
        change("wrong degree", lambda g: g["nodes"][0].update(deg=1))
        change("wrong incoming degree", lambda g: g["nodes"][0].update(din=0))
        change("Boolean outgoing degree", lambda g: g["nodes"][0].update(dout=True))
        change("foreign endpoint", lambda g: g["edges"][0].update(d="sia/missing"))
        change("invalid relation", lambda g: g["edges"][0].update(t="[[mentions]]"))
        change("duplicate edge", lambda g: g["edges"].append(copy.deepcopy(g["edges"][0])))
        change("duplicate node", lambda g: g["nodes"].append(copy.deepcopy(g["nodes"][0])))
        change("kind count", lambda g: g["snapshot"].update(counts_by_kind={"organ": 2}))
        change("omission claims absence", lambda g: g["snapshot"].update(omissions_imply_absence=True))
        change("incomplete body", lambda g: g["snapshot"].update(complete=False, failed_ops=["scan refused"]))
        change("incomplete page count", lambda g: g.update(pages_total_complete=False))
        change("window policy", lambda g: g["snapshot"].update(window_days=True))
        change("bad snapshot timestamp", lambda g: g.update(ts="not canonical time"))
        change("future node timestamp", lambda g: g["nodes"][0].update(ts="9999-12-31T23:59:59Z"))
        for label, graph in variants:
            with self.subTest(label=label):
                self.assertIs(self.core._legacy_graph_snapshot_body_valid(graph), False)
                self._install(graph)
                self.fx._refuses_readonly()
                self.assertFalse(self.fx.preserved.exists())

    def test_public_default_does_not_adopt_or_preserve_old_markup(self):
        before = self.fx.fx._snapshot()
        status, result, _stdout = self._public(explicit=False)
        self.assertEqual(status, 1)
        self.assertEqual(result["status"], "refused")
        self.assertEqual(self.fx.fx._snapshot(), before)
        self.assertFalse(self.fx.preserved.exists())
        self.fx.fx.keeper.assert_not_called()
        self.fx.fx.sync.assert_not_called()

    def test_explicit_public_repair_preserves_opaque_bytes_before_fresh_inert_ready_graph(self):
        original = self.fx.legacy_raw
        status, result, stdout = self._public(explicit=True)
        self.assertEqual(status, 0, stdout)
        self.assertEqual(result["status"], "repaired")
        self.assertEqual(self.fx.preserved.read_bytes(), original)
        preserved = json.loads(self.fx.preserved.read_bytes())
        self.assertEqual(preserved["edges"][0]["why"], OPAQUE_WHY)
        self.assertEqual(preserved["nodes"][0]["origin"], "derived")
        self.assertNotIn("publication_id", preserved)
        witness = self.fx._publication()
        self.assertEqual(witness["schema"], legacy.PUBLICATION_V2)
        self.assertEqual(witness["legacy_graph"]["authority"], "legacy-shape-only-not-ranking")
        self.assertEqual(witness["legacy_graph"]["sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(witness["phase"], "complete")
        fresh = json.loads(self.fx.graph_path.read_bytes())
        self.assertIsNotNone(self.core._recoverable_graph_snapshot(fresh))
        self.assertEqual(fresh, self.fx.fresh)
        self.assertNotIn("sync_needed", self.core.load_memo())
        self.assertNotEqual(self.core.load_memo()["ready"], self.fx.fx.memo["ready"])
        self.assertEqual(Path(self.core.siamind.MIND_PATH).read_bytes(), self.fx.fx.mind_before)
        self.assertNotIn(OPAQUE_WHY, stdout, "opaque legacy text leaked through the public receipt")
        for forbidden in self.fx.fx.forbidden:
            forbidden.assert_not_called()

    def test_explicit_flag_cannot_treat_a_current_marked_up_graph_as_legacy(self):
        self._install(self._current(self.graph))
        self.fx._refuses_readonly()
        self.assertFalse(self.fx.preserved.exists())

    def test_fresh_export_with_markup_does_not_inherit_legacy_permission_or_issue_readiness(self):
        self.fx.fresh = self._current(self.graph)
        self.assertIsNone(self.core._recoverable_graph_snapshot(self.fx.fresh))
        with mock.patch.object(self.core, "_export_graph_publication", side_effect=self.fx._export) as exported:
            with self.assertRaises((RuntimeError, ValueError)):
                self.fx._run()
        exported.assert_called_once()  # Refusal must occur after export, not preflight.
        self.assertEqual(self.fx.preserved.read_bytes(), self.fx.legacy_raw)
        self.assertEqual(json.loads(self.fx.graph_path.read_bytes()), self.fx.fresh)
        self.assertTrue(self.core.load_memo().get("sync_needed"))
        self.assertEqual(self.core.load_memo()["ready"], self.fx.fx.memo["ready"])
        self.assertIsNone(self.fx._publication()["graph_regeneration"])


if __name__ == "__main__":
    unittest.main()
