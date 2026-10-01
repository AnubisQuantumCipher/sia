#!/usr/bin/env python3
"""Explicit legacy-output regeneration contracts; private fixture roots only.

The parent runs these sequentially.  Nothing here exercises the resident CLI,
corpus, graph, keeper, model service, daemon, or database.
"""

import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import unittest
from unittest import mock

try:
    import test_cortex_repair_command as commands
except ModuleNotFoundError:
    from tests import test_cortex_repair_command as commands


PUBLICATION_V2 = "sia-cortex-boundary-publication-v2"
LEGACY_SCHEMA = "sia-cortex-boundary-legacy-graph-v1"
PRESERVED_LEAF = "cortex-boundary-legacy-graph.json"
FRESH_PUBLICATION_ID = "b" * 32


class CortexLegacyGraphRepair(unittest.TestCase):
    def setUp(self):
        # Composition deliberately avoids rerunning the inherited command suite.
        self.fx = commands.CortexRepairCommand(methodName="runTest")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.core = self.fx.core
        self.repair = self.fx.repair
        self.graph_path = Path(self.core.GRAPH_PATH)
        self.preserved = self.fx.state / PRESERVED_LEAF
        self.legacy = {
            "v": 2, "ts": self.core.iso(), "nodes": [], "edges": [],
            "pages_total": 0, "pages_total_complete": True,
            "snapshot": {
                "complete": True, "truncated": 0, "omitted_nodes": 0,
                "omitted_edges": 0, "omissions_imply_absence": False,
                "aged_out": 0, "counts_by_kind": {}, "failed_ops": [],
                "window_days": 14}}
        # Preserve this noncanonical whitespace, not a JSON reconstruction.
        self.legacy_raw = ("\n " + json.dumps(self.legacy, indent=2) + "\n\n").encode()
        self.graph_path.write_bytes(self.legacy_raw)
        self.graph_path.chmod(0o600)
        self.fresh = {**copy.deepcopy(self.legacy),
                      "publication_id": FRESH_PUBLICATION_ID}
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(
            self.core, "_require_recoverable_graph_snapshot", side_effect=self._strict_graph))
        self.stack.enter_context(mock.patch.object(
            self.fx, "_publications", side_effect=self._publications))
        self.stack.enter_context(mock.patch.object(
            self.core, "_export_graph_publication", side_effect=self._export))

    def _strict_graph(self, value):
        if self.core._recoverable_graph_snapshot(value) is None \
                or value["snapshot"]["complete"] is not True:
            raise RuntimeError("fixture strict canonical graph refusal")
        return value

    def _publications(self):
        return (self.fx.fixture._state_records(commands.PUBLICATION_SCHEMA)
                + self.fx.fixture._state_records(PUBLICATION_V2))

    def _publication(self):
        rows = self._publications()
        self.assertEqual(len(rows), 1)
        return rows[0][1]

    def _run(self, *, enabled=True):
        return self.repair.repair_cortex_boundary(
            self.core, regenerate_legacy_graph=enabled)

    def _export(self):
        publication = self._publication()
        self.assertEqual(publication["schema"], PUBLICATION_V2)
        self.assertEqual(self.preserved.read_bytes(), self.legacy_raw,
                         "legacy source must be durable before graph replacement")
        self.assertNotIn("publication_id", json.loads(self.preserved.read_bytes()))
        self.fx._graph()
        self.fx._write_json(self.graph_path, self.fresh)
        return 0, 0, 0

    def _refuses_readonly(self, *, enabled=True):
        before = self.fx._snapshot()
        counts = (self.fx.keeper.call_count, self.fx.sync.call_count)
        with self.assertRaises((RuntimeError, ValueError)):
            self._run(enabled=enabled)
        self.assertEqual(self.fx._snapshot(), before)
        self.assertEqual((self.fx.keeper.call_count, self.fx.sync.call_count), counts)

    def _interrupt_sync(self):
        with mock.patch.object(self.core, "brain_sync", return_value=(False, "fixture interruption")):
            with self.assertRaisesRegex(RuntimeError, "sync"):
                self._run()
        self.assertTrue(self.core.load_memo().get("sync_needed"))
        self.assertEqual(self.core.load_memo()["ready"], self.fx.memo["ready"])
        self.assertEqual(self._publication()["phase"], "pending")
        self.assertIsNone(self._publication()["graph_regeneration"])
        self.assertEqual(self.preserved.read_bytes(), self.legacy_raw)

    def test_legacy_shape_classifier_does_not_weaken_current_read_authority(self):
        self.assertIsNone(self.core._recoverable_graph_snapshot(self.legacy))
        self.assertIsNotNone(self.core._recoverable_graph_snapshot(self.fresh))
        classify = getattr(self.core, "_legacy_graph_snapshot_body_valid", None)
        self.assertTrue(callable(classify), "pure legacy graph-body classifier is missing")
        before = copy.deepcopy(self.legacy)
        self.assertIs(classify(self.legacy), True)
        self.assertEqual(self.legacy, before, "classification manufactured graph identity")
        self.assertIs(classify(self.fresh), False)
        for identity in (None, "", "unbound"):
            with self.subTest(identity=identity):
                value = {**self.legacy, "publication_id": identity}
                self.assertIs(classify(value), False)

    def test_legacy_classifier_reuses_complete_canonical_body_invariants(self):
        classify = getattr(self.core, "_legacy_graph_snapshot_body_valid", None)
        self.assertTrue(callable(classify), "pure legacy graph-body classifier is missing")
        variants = []
        value = copy.deepcopy(self.legacy)
        value["extra"] = "not an installed producer field"
        variants.append(value)
        value = copy.deepcopy(self.legacy)
        value["pages_total"] = 1
        variants.append(value)
        value = copy.deepcopy(self.legacy)
        value["pages_total"] = True
        variants.append(value)
        value = copy.deepcopy(self.legacy)
        value["snapshot"].update(complete=False, failed_ops=["scan refused"])
        variants.append(value)
        value = copy.deepcopy(self.legacy)
        value["snapshot"]["omissions_imply_absence"] = True
        variants.append(value)
        value = copy.deepcopy(self.legacy)
        value["snapshot"]["counts_by_kind"] = {"organ": 1}
        variants.append(value)
        value = copy.deepcopy(self.legacy)
        value["edges"] = [{"s": "sia/cortex", "d": "sia/cortex", "t": "link", "why": ""}]
        variants.append(value)
        value = copy.deepcopy(self.legacy)
        value["ts"] = "not canonical time"
        variants.append(value)
        for value in variants:
            with self.subTest(value=value):
                self.assertIs(classify(value), False)

    def test_default_command_still_refuses_legacy_graph_without_any_write(self):
        self.fx._refuses_without_mutation()

    def test_explicit_public_flag_dispatches_without_a_pulse_or_mind_migration(self):
        with mock.patch.object(self.core, "_lifecycle_reader", return_value=contextlib.nullcontext()), \
                mock.patch.dict(sys.modules, {"sialib": self.core, "siacortexrepair": self.repair}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            status = self.fx.cli.main([
                "sia", "repair-cortex-boundary", "--regenerate-legacy-graph", "--json"])
        self.assertEqual(status, 0, output.getvalue())
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "repaired")
        self.assertTrue(result["non_claims"])
        self.assertLessEqual(len(output.getvalue().encode()), self.core.MAX_CONFIG_BYTES)
        self.assertEqual(Path(self.core.siamind.MIND_PATH).read_bytes(), self.fx.mind_before)
        for forbidden in self.fx.forbidden:
            forbidden.assert_not_called()

    def test_preserves_exact_legacy_bytes_and_records_actual_new_graph_before_ready(self):
        actual_write_memo = self.core._write_memo

        def write_memo(value):
            if value.get("sync_needed"):
                self.assertEqual(self.preserved.read_bytes(), self.legacy_raw,
                                 "legacy source must be preserved before publication debt")
                self.assertEqual(self._publication()["schema"], PUBLICATION_V2)
            if value.get("ready") != self.fx.memo["ready"]:
                publication = self._publication()
                self.assertEqual(publication["phase"], "ready")
                fresh_raw = self.graph_path.read_bytes()
                self.assertEqual(publication["graph_regeneration"], {
                    "publication_id": FRESH_PUBLICATION_ID,
                    "sha256": hashlib.sha256(fresh_raw).hexdigest(),
                    "bytes": len(fresh_raw),
                    "generation": publication["graph_dirty"]["generation"]})
                self._strict_graph(json.loads(fresh_raw))
            return actual_write_memo(value)

        with mock.patch.object(self.core, "_write_memo", side_effect=write_memo):
            self.assertEqual(self._run()["status"], "repaired")
        publication = self._publication()
        self.assertEqual(publication["schema"], PUBLICATION_V2)
        self.assertEqual(publication["phase"], "complete")
        self.assertEqual(publication["legacy_graph"], {
            "schema": LEGACY_SCHEMA, "path": PRESERVED_LEAF,
            "sha256": hashlib.sha256(self.legacy_raw).hexdigest(),
            "bytes": len(self.legacy_raw), "authority": "legacy-shape-only-not-ranking"})
        self.assertEqual(self.preserved.read_bytes(), self.legacy_raw)
        self.assertEqual(stat.S_IMODE(self.preserved.stat().st_mode), 0o600)
        self.assertEqual(self.preserved.stat().st_nlink, 1)
        self.assertNotIn("publication_id", json.loads(self.preserved.read_bytes()))
        self.assertEqual(self.fx.cortex.read_bytes(), self.fx.target)
        self.assertEqual(Path(self.core.siamind.MIND_PATH).read_bytes(), self.fx.mind_before)
        self.assertEqual(self.core.load_memo()["retained_operator_field"],
                         self.fx.memo["retained_operator_field"])
        self.assertNotIn("sync_needed", self.core.load_memo())

    def test_explicit_mode_refuses_malformed_legacy_graph_without_any_write(self):
        value = copy.deepcopy(self.legacy)
        value["snapshot"]["counts_by_kind"] = {"organ": 1}
        self.fx._write_json(self.graph_path, value)
        self._refuses_readonly()

    def test_unwitnessed_existing_preservation_file_is_not_adopted(self):
        self.preserved.write_bytes(self.legacy_raw)
        self.preserved.chmod(0o600)
        self._refuses_readonly()

    def test_legacy_source_alias_or_hardlink_refuses_before_any_write(self):
        retained = self.fx.home / "fixture-source-graph.json"
        self.graph_path.rename(retained)
        self.graph_path.symlink_to(retained)
        self._refuses_readonly()
        self.graph_path.unlink()
        os.link(retained, self.graph_path)
        self._refuses_readonly()

    def test_explicit_mode_is_not_a_graph_only_regeneration_frontdoor(self):
        with mock.patch.object(self.core, "_cortex_boundary_status", return_value=(True, "")):
            self._refuses_readonly()

    def test_raw_graph_ceiling_precedes_json_materialization_or_preservation(self):
        oversized = b" " * 4096 + self.legacy_raw
        self.graph_path.write_bytes(oversized)
        actual_parse = self.core._strict_json_loads

        def parse(raw):
            encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
            self.assertNotEqual(encoded, oversized,
                                "oversized legacy graph reached JSON materialization")
            return actual_parse(raw)

        with mock.patch.object(self.core, "MAX_STATE_JSON_BYTES", 4096), \
                mock.patch.object(self.core, "_strict_json_loads", side_effect=parse):
            self._refuses_readonly()
        self.assertFalse(self.preserved.exists())

    def test_interruption_after_journal_before_preservation_resumes_exact_source(self):
        with mock.patch.object(self.repair, "_preserve_legacy_graph", create=True,
                               side_effect=RuntimeError("fixture preservation interruption")):
            with self.assertRaisesRegex(RuntimeError, "preservation interruption"):
                self._run()
        publication = self._publication()
        self.assertEqual(publication["schema"], PUBLICATION_V2)
        self.assertEqual(self.graph_path.read_bytes(), self.legacy_raw)
        self.assertFalse(self.preserved.exists())
        self.assertEqual(self.fx.cortex.read_bytes(), self.fx.original)
        self.assertEqual(self.core.load_memo(), self.fx.memo)
        self.assertEqual(self._run()["status"], "repaired")

    def test_source_substitution_after_journal_does_not_authorize_new_legacy_bytes(self):
        actual_save = self.repair._save_publication
        replacement = b"\n\n" + self.legacy_raw

        def save(core, expected, value):
            result = actual_save(core, expected, value)
            if expected is None:
                self.graph_path.write_bytes(replacement)
            return result

        with mock.patch.object(self.repair, "_save_publication", side_effect=save):
            with self.assertRaises((RuntimeError, ValueError)):
                self._run()
        self.assertEqual(self._publication()["legacy_graph"]["sha256"],
                         hashlib.sha256(self.legacy_raw).hexdigest())
        self.assertEqual(self.graph_path.read_bytes(), replacement)
        self.assertEqual(self.fx.cortex.read_bytes(), self.fx.original)
        self.assertEqual(self.core.load_memo(), self.fx.memo)
        self.assertFalse(self.preserved.exists())
        self.fx.keeper.assert_not_called()

    def test_sync_interruption_retains_old_graph_and_exact_resume_requires_flag(self):
        self._interrupt_sync()
        self.assertEqual(self.graph_path.read_bytes(), self.legacy_raw)
        self._refuses_readonly(enabled=False)
        self.assertEqual(self._run()["status"], "repaired")
        self.assertEqual(len(self.fx.signed), 1)
        self.assertEqual(self._run()["status"], "already-ready")

    def test_preserved_byte_substitution_on_resume_refuses_before_mutation(self):
        self._interrupt_sync()
        self.preserved.write_bytes(b"\n" + self.legacy_raw)
        self._refuses_readonly()

    def test_preserved_alias_or_hardlink_on_resume_refuses_before_mutation(self):
        self._interrupt_sync()
        retained = self.fx.home / "fixture-retained-graph.json"
        self.preserved.rename(retained)
        self.preserved.symlink_to(retained)
        self._refuses_readonly()
        self.preserved.unlink()
        os.link(retained, self.preserved)
        self._refuses_readonly()

    def test_export_without_fresh_publication_identity_never_issues_readiness(self):
        def export():
            self.fx._graph()
            # Producer returning without replacing the old output is not success.
            return 0, 0, 0

        with mock.patch.object(self.core, "_export_graph_publication", side_effect=export):
            with self.assertRaises((RuntimeError, ValueError)):
                self._run()
        self.assertTrue(self.core.load_memo().get("sync_needed"))
        self.assertEqual(self.core.load_memo()["ready"], self.fx.memo["ready"])
        self.assertIsNone(self._publication()["graph_regeneration"])
        self.assertEqual(self.preserved.read_bytes(), self.legacy_raw)

    def test_explicit_partial_export_is_retained_and_rebuilt_before_readiness(self):
        partial = copy.deepcopy(self.fresh)
        partial["snapshot"].update(complete=False, failed_ops=["fixture interrupted scan"])

        def export_partial():
            self.fx._assert_owned()
            self.fx._write_json(self.graph_path, partial)
            raise RuntimeError("fixture interrupted graph export")

        with mock.patch.object(self.core, "_export_graph_publication", side_effect=export_partial):
            with self.assertRaises((RuntimeError, ValueError)):
                self._run()
        self.assertEqual(json.loads(self.graph_path.read_bytes()), partial)
        self.assertTrue(self.core.load_memo().get("sync_needed"))
        self.assertIsNone(self._publication()["graph_regeneration"])
        self.assertEqual(self.preserved.read_bytes(), self.legacy_raw)
        self.assertEqual(self._run()["status"], "repaired")

    def test_new_graph_replaced_after_receipt_write_cannot_publish_readiness(self):
        actual_save = self.repair._save_publication
        replacement = {**self.fresh, "publication_id": "c" * 32}

        def save(core, expected, value):
            result = actual_save(core, expected, value)
            if value["phase"] == "ready":
                self.fx._write_json(self.graph_path, replacement)
            return result

        with mock.patch.object(self.repair, "_save_publication", side_effect=save):
            with self.assertRaises((RuntimeError, ValueError)):
                self._run()
        self.assertTrue(self.core.load_memo().get("sync_needed"))
        self.assertEqual(self.core.load_memo()["ready"], self.fx.memo["ready"])
        self.assertNotEqual(self._publication()["graph_regeneration"]["publication_id"],
                            replacement["publication_id"])


if __name__ == "__main__":
    unittest.main()
