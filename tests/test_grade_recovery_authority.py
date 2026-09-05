"""A retained grade must be admitted before it can ask for a signature."""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home


REPO = Path(__file__).resolve().parents[1]


class GradeRecoveryAuthority(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sia-grade-authority-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        spec = importlib.util.spec_from_file_location(
            "siatakes_grade_recovery_authority", REPO / "bin/siatakes.py")
        self.lib = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.lib)
        self.lib.TAKES_DIR = str(self.root / "takes")
        self.lib.INTENTS_DIR = str(self.root / "intents")
        self.lib.GRADE_TX_DIR = str(self.root / "grades")
        self.lib.TAKE_MIGRATION_TX_DIR = str(self.root / "migrations")
        self.signatures = []
        self.notifications = []
        self.keeper = types.SimpleNamespace(
            ledger_contains=lambda *row: row in self.signatures,
            ledger_append=self._append)

    def _append(self, *row, required=False):
        self.assertTrue(required)
        self.signatures.append(row)

    def _prepare_take(self):
        self.lib.create_take("retain this grade", deadline="2099-01-01")
        take = self.lib.load_takes()[0]
        source = Path(take["path"]).read_text(encoding="utf-8")
        take.update({
            "status": "resolved-true", "outcome": 1, "brier": 0.09,
            "graded": "2026-08-30T12:00:00Z", "judge_model": "fixture",
            "_grade_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        })
        path, source, target = self.lib._render_take_page(
            take, "TRUE", "retained fixture justification")
        return take, path, source, target

    def _write_unprojected_take_page(self, take_id):
        source = self.page.read_text(encoding="utf-8")
        replacement_id = "f" * 20 if take_id != "f" * 20 else "e" * 20
        target = source.replace(take_id, replacement_id)
        metadata_line = next(line for line in target.splitlines()
                             if line.startswith("sia_take: "))
        metadata = json.loads(metadata_line.removeprefix("sia_take: "))
        path = Path(self.lib.TAKES_DIR) / (
            metadata["created"][:10] + "-" + replacement_id + ".md")
        path.write_text(target, encoding="utf-8")
        observed = self.lib._history_page_metadata(
            "take", str(path), path.read_text(encoding="utf-8"))
        self.assertEqual(observed["id"], replacement_id)
        self.assertIsNone(self.lib._history_direct("take", replacement_id))
        return path, replacement_id

    def _stage_grade(self, *, with_event=True):
        take, path, source, target = self._prepare_take()
        value = self.lib._grade_tx_payload(take, path, source, target)
        if with_event:
            value["history_event"] = self._event(
                take, path, target, "grade", signed_grade=True)
        self.journal = Path(self.lib.GRADE_TX_DIR) / (take["id"] + ".json")
        self.page = Path(path)
        self.recover = self.lib.recover_grade_transactions
        return self._save(value)

    def _stage_migration(self, *, grade_observed=False, legacy_journal=False,
                         with_event=True):
        take, path, _source, resolved = self._prepare_take()
        legacy = resolved.replace("origin: model\n", "", 1).replace(
            "Model justification (inert prose): retained fixture justification",
            "retained fixture justification", 1)
        Path(path).write_text(legacy, encoding="utf-8")
        candidate = self.lib._take_migration_candidate(
            "takes/" + Path(path).stem, path)
        self.assertIsNotNone(candidate)
        take, source, target, migration_kind = candidate
        self.assertIsNotNone(target)
        if legacy_journal:
            value = {
                "schema": self.lib.TAKE_MIGRATION_SCHEMA,
                "take_id": take["id"], "migration_kind": migration_kind,
                "path": path,
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "target_sha256": hashlib.sha256(target.encode()).hexdigest(),
                "target_size": len(target.encode()), "target_text": target,
                "grade_observed": grade_observed,
            }
        else:
            value = self.lib._take_migration_payload(
                take, source, target, migration_kind,
                grade_observed=grade_observed)
        if with_event:
            value["history_event"] = self._event(
                take, path, target, "legacy-migration",
                signed_grade=grade_observed)
        self.journal = Path(self.lib.TAKE_MIGRATION_TX_DIR) / (take["id"] + ".json")
        self.page = Path(path)
        self.migration_source = source
        self.recover = self.lib.recover_take_migrations
        return self._save(value)

    def _signed_source(self, value):
        row = ("GRADE:take", value["take_id"], "resolved-true",
               self.migration_source)
        self.signatures.append(row)
        return row

    def _settle_authority(self):
        state = self.lib._load_history_state("take")
        self.lib._history_begin_authority(state)
        self.lib._save_history_state("take", state)
        with mock.patch.dict(sys.modules, {"sialib": self.keeper}):
            for _attempt in range(self.lib.MAX_HISTORY_BASELINE_SCAN):
                if not self.lib.natural_history_debt("take"):
                    break
                _migrated, errors = self.lib.migrate_legacy_take_pages()
                self.assertEqual(errors, [])
            else:
                self.fail("quiescent migration authority did not settle")

    def _simulate_legacy_event_reservation(self, *, catalog_new=False):
        state = self.lib._load_history_state("take", create=True)
        sequence = state["next_event"]
        catalog_index = state["next_catalog"] if catalog_new else None
        self.lib._history_begin_authority(state)
        state["next_event"] += 1
        if catalog_new:
            state["next_catalog"] += 1
        self.lib._save_history_state("take", state)
        return sequence, catalog_index

    def _interrupt_after_migration_page(self, value):
        with mock.patch.object(
                self.lib, "_history_project_event",
                side_effect=RuntimeError("fixture after page publication")):
            recovered, errors = self._run_recovery()
        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("fixture after page publication", errors[0]["error"])
        self.assertEqual(self.page.read_text(encoding="utf-8"),
                         value["target_text"])
        self.assertTrue(self.journal.exists())
        self.notifications.clear()

    def _event(self, take, path, target, operation, *, signed_grade):
        existing = self.lib._history_direct("take", take["id"])
        return self.lib._history_event(
            "take", operation, path, target, before=existing,
            after=self.lib._history_page_metadata("take", path, target),
            signed_grade=signed_grade, catalog_new=existing is None)

    def _save(self, value):
        value = copy.deepcopy(value)
        event = value.get("history_event", value.get("event"))
        if event is not None:
            event.pop("event_id", None)
            event["event_id"] = hashlib.sha256(json.dumps(
                event, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False).encode()).hexdigest()
        self.journal.parent.mkdir(mode=0o700, exist_ok=True)
        self.journal.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        self.journal.chmod(0o600)
        return value

    def _run_recovery(self):
        with mock.patch.dict(sys.modules, {"sialib": self.keeper}):
            return self.recover(before_publish=lambda:
                                self.notifications.append("publication"))

    def _refuses_before_mutation(self, value, *, kind="take"):
        value = self._save(value)
        state_path = Path(self.lib._history_paths(kind)["state"])
        state_before = state_path.read_bytes()
        page_before = self.page.read_bytes()
        journal_before = self.journal.read_bytes()
        signatures_before = list(self.signatures)

        recovered, errors = self._run_recovery()

        self.assertEqual(recovered, [])
        self.assertTrue(errors, "inconsistent retained authority was accepted")
        self.assertEqual(self.signatures, signatures_before,
                         "invalid authority reached the signing seam")
        self.assertEqual(self.notifications, [])
        self.assertEqual(self.page.read_bytes(), page_before)
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual(self.journal.read_bytes(), journal_before)

    def test_private_directory_repreparation_preserves_its_generation(self):
        private = self.root / "private"
        self.lib._ensure_private_durable_directory(
            str(private), "fixture private directory")
        before = self.lib._history_directory_identity(str(private))

        original_os = self.lib.os

        class OsShim:
            def __init__(self):
                self.fchmod = mock.Mock(wraps=original_os.fchmod)
                self.fsync = mock.Mock(wraps=original_os.fsync)

            def __getattr__(self, name):
                return getattr(original_os, name)

        observed_os = OsShim()

        with mock.patch.object(
                self.lib, "os", observed_os):
            self.lib._ensure_private_durable_directory(
                str(private), "fixture private directory")

        self.assertEqual(
            self.lib._history_directory_identity(str(private)), before)
        observed_os.fchmod.assert_not_called()
        self.assertEqual(observed_os.fsync.call_count, 2)

    def test_state_creation_builds_a_missing_store_parent_hierarchy(self):
        corpus = self.root / "missing" / "corpus"
        self.lib.INTENTS_DIR = str(corpus / "intents")
        self.assertFalse(corpus.exists())

        state = self.lib._load_history_state("intent", create=True)

        self.assertTrue(corpus.is_dir())
        self.assertTrue(Path(self.lib.INTENTS_DIR).is_dir())
        self.assertTrue(state["authority"]["complete"])
        self.assertEqual(
            state["authority"]["checkpoint"],
            self.lib._history_directory_identity(self.lib.INTENTS_DIR))

    def test_state_creation_materializes_and_pins_the_empty_store(self):
        store = Path(self.lib.INTENTS_DIR)
        self.assertFalse(store.exists())

        state = self.lib._load_history_state("intent", create=True)

        self.assertTrue(store.is_dir())
        self.assertTrue(state["authority"]["complete"])
        self.assertEqual(
            state["authority"]["checkpoint"],
            self.lib._history_directory_identity(str(store)))
        made = self.lib.create_intent("first intent", "2099-01-01")
        self.assertIsNotNone(self.lib._history_direct("intent", made["id"]))
        self.assertFalse(self.lib.natural_history_debt("intent"))

    def test_valid_grade_recovers_and_does_not_sign_twice(self):
        value = self._stage_grade()
        recovered, errors = self._run_recovery()
        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertEqual(self.page.read_text(encoding="utf-8"), value["target_text"])
        signatures = list(self.signatures)
        self.assertTrue(signatures)
        self.assertEqual(self._run_recovery(), ([], []))
        self.assertEqual(self.signatures, signatures)

    def test_valid_grade_journal_is_durably_enriched_before_publication(self):
        value = self._stage_grade(with_event=False)
        self.assertNotIn("history_event", value)

        def interrupt():
            raise RuntimeError("fixture after grade event reservation")

        with mock.patch.dict(sys.modules, {"sialib": self.keeper}):
            recovered, errors = self.recover(before_publish=interrupt)
        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("fixture after grade event reservation", errors[0]["error"])
        enriched = json.loads(self.journal.read_text(encoding="utf-8"))
        event = enriched["history_event"]
        transition = self.lib._load_history_state("take")["authority"]["transition"]
        self.assertEqual(transition["event_id"], event["event_id"])
        signatures = list(self.signatures)

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertEqual(self.signatures, signatures)

    def test_grade_enrichment_reuses_a_legacy_reserved_sequence(self):
        value = self._stage_grade(with_event=False)
        sequence, _catalog_index = self._simulate_legacy_event_reservation()

        def interrupt():
            raise RuntimeError("fixture after legacy grade reservation")

        with mock.patch.dict(sys.modules, {"sialib": self.keeper}):
            recovered, errors = self.recover(before_publish=interrupt)
        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("fixture after legacy grade reservation",
                      errors[0]["error"])
        enriched = json.loads(self.journal.read_text(encoding="utf-8"))
        event = enriched["history_event"]
        self.assertEqual(event["sequence"], sequence)
        self.assertNotIn("authority_basis", event)
        state = self.lib._load_history_state("take")
        self.assertEqual(state["next_event"], sequence + 1)
        signatures = list(self.signatures)

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertEqual(self.signatures, signatures)
        self.assertTrue(self.lib.natural_history_debt("take"))

    def test_legacy_missing_event_refuses_an_ambiguous_pending_journal(self):
        value = self._stage_grade(with_event=False)
        self._simulate_legacy_event_reservation()
        migration_dir = Path(self.lib.TAKE_MIGRATION_TX_DIR)
        migration_dir.mkdir(mode=0o700, exist_ok=True)
        competing = migration_dir / "competing.json"
        competing.write_text("{}", encoding="utf-8")
        competing.chmod(0o600)

        self._refuses_before_mutation(value)

    def test_legacy_reservation_counts_a_generic_take_wal_as_ambiguous(self):
        value = self._stage_grade(with_event=False)
        self._simulate_legacy_event_reservation()
        generic = Path(self.lib._history_paths("take")["pending"])
        generic.write_text("{}", encoding="utf-8")
        generic.chmod(0o600)

        self._refuses_before_mutation(value)

    def test_missing_event_cannot_discard_an_unexplained_transition(self):
        value = self._stage_grade(with_event=False)
        state = self.lib._load_history_state("take")
        state["authority"]["transition"] = {
            "sequence": state["next_event"],
            "event_id": "f" * 64,
            "authority_basis": None,
        }
        self.lib._save_history_state("take", state)

        self._refuses_before_mutation(value)

    def _assert_missing_event_cannot_bootstrap_missing_history(self, value):
        history_root = Path(self.lib._history_paths("take")["root"])
        shutil.rmtree(history_root)
        page_before = self.page.read_bytes()
        journal_before = self.journal.read_bytes()

        recovered, errors = self._run_recovery()

        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn(
            "missing history event has no durable history state",
            errors[0]["error"])
        self.assertEqual(self.signatures, [])
        self.assertEqual(self.notifications, [])
        self.assertEqual(self.page.read_bytes(), page_before)
        self.assertEqual(self.journal.read_bytes(), journal_before)
        self.assertFalse(history_root.exists())

    def test_grade_missing_event_cannot_bootstrap_missing_history(self):
        value = self._stage_grade(with_event=False)

        self._assert_missing_event_cannot_bootstrap_missing_history(value)

    def test_migration_missing_event_cannot_bootstrap_missing_history(self):
        value = self._stage_migration(with_event=False)

        self._assert_missing_event_cannot_bootstrap_missing_history(value)
        self.assertFalse(Path(self.lib._take_provenance_root()).exists())

    def test_grade_restoration_claim_is_admitted_before_signing(self):
        value = self._stage_grade()
        self.assertTrue(value["history_event"]["authority_restore"])
        state = self.lib._load_history_state("take")
        self.lib._history_begin_authority(state)
        self.lib._save_history_state("take", state)

        self._refuses_before_mutation(value)

    def test_stale_grade_wal_cannot_certify_an_unprojected_page(self):
        value = self._stage_grade()
        unprojected, unprojected_id = self._write_unprojected_take_page(
            value["take_id"])

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertFalse(self.journal.exists())
        self.assertTrue(unprojected.exists())
        self.assertIsNone(self.lib._history_direct("take", unprojected_id))
        self.assertTrue(self.lib.natural_history_debt("take"),
                        "stale grade WAL restored take authority")

    def test_embedded_metadata_conflict_refuses_before_signing(self):
        value = self._stage_grade()
        value["history_event"]["after"]["metadata"]["claim"] = "another claim"
        self._refuses_before_mutation(value)

    def test_top_level_status_must_match_target_and_history_event(self):
        value = self._stage_grade()
        value["status"] = "resolved-false"
        self._refuses_before_mutation(value)

    def test_history_event_cannot_change_operation_to_authority_update(self):
        value = self._stage_grade()
        value["history_event"]["operation"] = "authority-update"
        self._refuses_before_mutation(value)

    def test_embedded_target_path_cannot_name_another_take(self):
        value = self._stage_grade()
        value["history_event"]["path"] = str(self.page.with_name("other.md"))
        self._refuses_before_mutation(value)

    def test_unparsed_target_cannot_be_signed_before_metadata_refusal(self):
        value = self._stage_grade(with_event=False)
        target = "unparsed retained payload\n"
        value.update(target_text=target, target_size=len(target.encode()),
                     target_sha256=hashlib.sha256(target.encode()).hexdigest())
        self._refuses_before_mutation(value)

    def test_before_side_cannot_substitute_a_different_predecessor(self):
        value = self._stage_grade()
        value["history_event"]["before"]["metadata"]["claim"] = "other predecessor"
        self._refuses_before_mutation(value)

    def test_grade_cannot_change_confidence_hidden_by_visible_rounding(self):
        value = self._stage_grade()
        target = value["target_text"]
        metadata_line = next(line for line in target.splitlines()
                             if line.startswith("sia_take: "))
        metadata = json.loads(metadata_line.removeprefix("sia_take: "))
        metadata["confidence"] = "0.701"
        target = target.replace(
            metadata_line, "sia_take: " + json.dumps(metadata, sort_keys=True), 1)
        observed = self.lib._history_page_metadata(
            "take", str(self.page), target)
        value.update(target_text=target, target_size=len(target.encode()),
                     target_sha256=hashlib.sha256(target.encode()).hexdigest())
        value["history_event"]["page_sha256"] = value["target_sha256"]
        value["history_event"]["after"]["metadata"] = observed

        self._refuses_before_mutation(value)

    def test_grade_partial_direct_projection_recovers_without_double_signing(self):
        value = self._stage_grade()
        with mock.patch.object(
                self.lib, "_history_apply_domain",
                side_effect=RuntimeError("fixture after direct publication")):
            recovered, errors = self._run_recovery()
        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("fixture after direct publication", errors[0]["error"])
        direct = self.lib._history_direct("take", value["take_id"])
        self.assertEqual(direct["event_id"], value["history_event"]["event_id"])
        signatures_before = list(self.signatures)

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertEqual(self.signatures, signatures_before)
        report = self.lib.calibration_report()["overall"]
        self.assertEqual(report["resolved"], 1)
        self.assertEqual(report["open"], 0)

    def test_valid_unsigned_migration_remains_recoverable(self):
        value = self._stage_migration()
        recovered, errors = self._run_recovery()
        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertEqual(self.page.read_text(encoding="utf-8"), value["target_text"])
        direct = self.lib._history_direct("take", value["take_id"])
        self.assertFalse(direct["signed_grade"])

    def test_absent_migration_grade_witness_retains_unsigned_compatibility(self):
        value = self._stage_migration(with_event=False)
        value.pop("grade_observed")
        value = self._save(value)

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        direct = self.lib._history_direct("take", value["take_id"])
        self.assertFalse(direct["signed_grade"])

    def test_valid_migration_journal_is_durably_enriched_before_publication(self):
        value = self._stage_migration(with_event=False)
        self.assertNotIn("history_event", value)

        def interrupt():
            raise RuntimeError("fixture after migration event reservation")

        with mock.patch.dict(sys.modules, {"sialib": self.keeper}):
            recovered, errors = self.recover(before_publish=interrupt)
        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn(
            "fixture after migration event reservation", errors[0]["error"])
        enriched = json.loads(self.journal.read_text(encoding="utf-8"))
        event = enriched["history_event"]
        transition = self.lib._load_history_state("take")["authority"]["transition"]
        self.assertEqual(transition["event_id"], event["event_id"])
        signatures = list(self.signatures)

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertEqual(self.signatures, signatures)

    def test_migration_enrichment_reuses_a_legacy_reserved_catalog_slot(self):
        value = self._stage_migration(with_event=False)
        shutil.rmtree(self.lib._history_paths("take")["root"])
        sequence, catalog_index = self._simulate_legacy_event_reservation(
            catalog_new=True)

        def interrupt():
            raise RuntimeError("fixture after legacy migration reservation")

        with mock.patch.dict(sys.modules, {"sialib": self.keeper}):
            recovered, errors = self.recover(before_publish=interrupt)
        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("fixture after legacy migration reservation",
                      errors[0]["error"])
        enriched = json.loads(self.journal.read_text(encoding="utf-8"))
        event = enriched["history_event"]
        self.assertEqual(event["sequence"], sequence)
        self.assertEqual(event["catalog_index"], catalog_index)
        self.assertNotIn("authority_basis", event)
        state = self.lib._load_history_state("take")
        self.assertEqual(state["next_event"], sequence + 1)
        self.assertEqual(state["next_catalog"], catalog_index + 1)
        signatures = list(self.signatures)

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertEqual(self.signatures, signatures)
        direct = self.lib._history_direct("take", value["take_id"])
        self.assertEqual(direct["catalog_index"], catalog_index)
        self.assertTrue(self.lib.natural_history_debt("take"))

    def test_migration_restoration_claim_is_admitted_before_signing(self):
        value = self._stage_migration()
        self.assertTrue(value["history_event"]["authority_restore"])
        state = self.lib._load_history_state("take")
        self.lib._history_begin_authority(state)
        self.lib._save_history_state("take", state)

        self._refuses_before_mutation(value)
        self.assertFalse(Path(self.lib._take_provenance_root()).exists())

    def test_stale_migration_wal_cannot_certify_an_unprojected_page(self):
        value = self._stage_migration()
        unprojected, unprojected_id = self._write_unprojected_take_page(
            value["take_id"])

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertFalse(self.journal.exists())
        self.assertTrue(unprojected.exists())
        self.assertIsNone(self.lib._history_direct("take", unprojected_id))
        self.assertTrue(self.lib.natural_history_debt("take"),
                        "stale migration WAL restored take authority")

    def test_migration_metadata_conflict_refuses_before_signing(self):
        value = self._stage_migration()
        value["history_event"]["after"]["metadata"]["claim"] = "another claim"
        self._refuses_before_mutation(value)

    def test_migration_kind_must_match_the_admitted_source_transform(self):
        value = self._stage_migration()
        self.assertEqual(value["migration_kind"], "model-inert-v1")
        value["migration_kind"] = "legacy-v1-normalize"

        self._refuses_before_mutation(value)

    def test_migration_cannot_add_active_links_to_an_otherwise_valid_target(self):
        value = self._stage_migration()
        target = value["target_text"] + "\n[[model/forged-migration-link]]\n"
        self.lib._history_page_metadata("take", str(self.page), target)
        value.update(target_text=target, target_size=len(target.encode()),
                     target_sha256=hashlib.sha256(target.encode()).hexdigest())
        value["history_event"]["page_sha256"] = value["target_sha256"]

        self._refuses_before_mutation(value)

    def test_migration_grade_flag_is_not_a_signed_grade_witness(self):
        value = self._stage_migration(grade_observed=True)
        self._refuses_before_mutation(value)

    def test_published_migration_cannot_use_unwitnessed_cached_grade_flag(self):
        value = self._stage_migration(grade_observed=True)
        self.signatures.append((
            "MIGRATE:take-origin", value["take_id"], value["migration_kind"],
            value["target_text"]))
        self.page.write_text(value["target_text"], encoding="utf-8")
        self._refuses_before_mutation(value)

    def test_signed_migration_survives_later_authority_reconciliation(self):
        value = self._stage_migration(grade_observed=True)
        self._signed_source(value)

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertTrue(self.lib._history_direct(
            "take", value["take_id"])["signed_grade"])
        self._settle_authority()
        direct = self.lib._history_direct("take", value["take_id"])
        self.assertTrue(direct["signed_grade"],
                        "authority discarded the witnessed legacy grade")
        report = self.lib.calibration_report()["overall"]
        self.assertEqual(report["resolved"], 1)
        self.assertEqual(report["invalid_resolved"], 0)

    def test_signed_migration_replays_after_source_page_is_replaced(self):
        value = self._stage_migration(grade_observed=True)
        self._signed_source(value)
        self._interrupt_after_migration_page(value)
        signatures_before = list(self.signatures)

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertEqual(self.signatures, signatures_before)
        self.assertFalse(self.journal.exists())
        self._settle_authority()
        self.assertTrue(self.lib._history_direct(
            "take", value["take_id"])["signed_grade"])

    def test_published_migration_rechecks_its_original_grade_signature(self):
        value = self._stage_migration(grade_observed=True)
        source_signature = self._signed_source(value)
        self._interrupt_after_migration_page(value)
        self.signatures.remove(source_signature)
        retained = json.loads(self.journal.read_text(encoding="utf-8"))

        self._refuses_before_mutation(retained)

    def test_legacy_journal_is_enriched_while_exact_source_remains(self):
        value = self._stage_migration(
            grade_observed=True, legacy_journal=True)
        self._signed_source(value)
        self._interrupt_after_migration_page(value)
        signatures_before = list(self.signatures)

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertEqual(self.signatures, signatures_before)
        self._settle_authority()
        self.assertTrue(self.lib._history_direct(
            "take", value["take_id"])["signed_grade"])

    def test_legacy_published_journal_without_source_witness_refuses(self):
        value = self._stage_migration(
            grade_observed=True, legacy_journal=True)
        self._signed_source(value)
        self.signatures.append((
            "MIGRATE:take-origin", value["take_id"], value["migration_kind"],
            value["target_text"]))
        self.page.write_text(value["target_text"], encoding="utf-8")

        self._refuses_before_mutation(value)

    def test_maximum_legacy_source_remains_migratable_and_recoverable(self):
        fixture_spec = importlib.util.spec_from_file_location(
            "calibration_legacy_capacity_fixtures",
            REPO / "tests/test_calibration_benchmark.py")
        fixtures = importlib.util.module_from_spec(fixture_spec)
        fixture_spec.loader.exec_module(fixtures)
        marker = "capacity/domain"
        _take, path, source = fixtures.JudgeIsolation()._head_v1_take(
            self.lib.TAKES_DIR, claim="retain maximum legacy provenance",
            deadline="2026-08-30", domain=marker,
            justification="capacity witness")
        self.assertGreater(source.count(marker), 0)
        remaining = self.lib.MAX_LEGACY_TAKE_PAGE_BYTES - len(source.encode())
        source = source.replace(
            marker, marker + "x" * (remaining // source.count(marker)))
        source = source[:-1] + "p" * (
            self.lib.MAX_LEGACY_TAKE_PAGE_BYTES - len(source.encode())) + "\n"
        self.assertEqual(len(source.encode()),
                         self.lib.MAX_LEGACY_TAKE_PAGE_BYTES)
        Path(path).write_text(source, encoding="utf-8")
        candidate = self.lib._take_migration_candidate(
            "takes/" + Path(path).stem, path)
        self.assertIsNotNone(candidate)
        take, admitted_source, target, migration_kind = candidate
        self.assertEqual(admitted_source, source)
        self.assertIsNotNone(target)
        self.assertLessEqual(len(target.encode()), self.lib.MAX_TAKE_PAGE_BYTES)
        self.signatures.append(("GRADE:take", take["id"], take["status"], source))
        self.lib._load_history_state("take", create=True)
        value = self.lib._take_migration_payload(
            take, source, target, migration_kind, grade_observed=True)
        self.journal = Path(self.lib.TAKE_MIGRATION_TX_DIR) / (take["id"] + ".json")
        self.page = Path(path)
        self.recover = self.lib.recover_take_migrations
        self._save(value)

        self._interrupt_after_migration_page(value)
        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [take["id"]])
        self._settle_authority()
        self.assertTrue(self.lib._history_direct(
            "take", take["id"])["signed_grade"])

    def test_exact_maximum_grade_journal_remains_recoverable(self):
        value = self._stage_grade()
        raw = json.dumps(value, sort_keys=True)
        padding = self.lib.MAX_TRANSACTION_JOURNAL_BYTES - len(raw.encode())
        self.assertGreaterEqual(padding, 0)
        self.journal.write_text(raw + " " * padding, encoding="utf-8")
        self.journal.chmod(0o600)

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertFalse(self.journal.exists())

    def test_exact_maximum_no_event_grade_journal_enriches_and_recovers(self):
        value = self._stage_grade(with_event=False)
        raw = self.journal.read_text(encoding="utf-8")
        padding = self.lib.MAX_TRANSACTION_JOURNAL_BYTES - len(raw.encode())
        self.assertGreaterEqual(padding, 0)
        self.journal.write_text(raw + " " * padding, encoding="utf-8")
        self.journal.chmod(0o600)

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertFalse(self.journal.exists())

    def test_grade_journal_rejects_an_unknown_top_level_member(self):
        value = self._stage_grade(with_event=False)
        value["ignored_extension"] = "retained but unauthorised"

        self._refuses_before_mutation(value)

    def test_migration_journal_rejects_an_unknown_top_level_member(self):
        value = self._stage_migration(with_event=False)
        value["ignored_extension"] = "retained but unauthorised"

        self._refuses_before_mutation(value)
        self.assertFalse(Path(self.lib._take_provenance_root()).exists())

    def test_grade_journal_rejects_a_null_history_event(self):
        value = self._stage_grade(with_event=False)
        value["history_event"] = None

        self._refuses_before_mutation(value)

    def test_migration_journal_rejects_a_null_history_event(self):
        value = self._stage_migration(with_event=False)
        value["history_event"] = None

        self._refuses_before_mutation(value)
        self.assertFalse(Path(self.lib._take_provenance_root()).exists())

    def _assert_enrichment_over_limit_refuses_unchanged(
            self, value, *, operation, signed_grade):
        _after, event = self.lib._admit_take_transaction_target(
            value, operation, signed_grade, str(self.journal))
        enriched = dict(value)
        enriched["history_event"] = event
        encoded = json.dumps(
            enriched, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False).encode("utf-8")
        limit = len(encoded) - 1
        self.assertLessEqual(len(self.journal.read_bytes()), limit)
        state_path = Path(self.lib._history_paths("take")["state"])
        state_before = state_path.read_bytes()
        page_before = self.page.read_bytes()
        journal_before = self.journal.read_bytes()
        signatures_before = list(self.signatures)

        with mock.patch.object(
                self.lib, "MAX_TRANSACTION_JOURNAL_BYTES", limit):
            recovered, errors = self._run_recovery()

        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn(
            "enriched transaction journal exceeds its bounded size",
            errors[0]["error"])
        self.assertEqual(self.signatures, signatures_before)
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual(self.page.read_bytes(), page_before)
        self.assertEqual(self.journal.read_bytes(), journal_before)

    def test_grade_enrichment_refuses_an_over_limit_result_unchanged(self):
        value = self._stage_grade(with_event=False)

        self._assert_enrichment_over_limit_refuses_unchanged(
            value, operation="grade", signed_grade=True)

    def test_migration_enrichment_refuses_an_over_limit_result_unchanged(self):
        value = self._stage_migration(with_event=False)

        self._assert_enrichment_over_limit_refuses_unchanged(
            value, operation="legacy-migration", signed_grade=False)
        self.assertFalse(Path(self.lib._take_provenance_root()).exists())

    def test_over_limit_grade_journal_refuses_before_mutation(self):
        value = self._stage_grade()
        raw = json.dumps(value, sort_keys=True)
        padding = self.lib.MAX_TRANSACTION_JOURNAL_BYTES - len(raw.encode())
        self.assertGreaterEqual(padding, 0)
        self.journal.write_text(raw + " " * (padding + 1), encoding="utf-8")
        self.journal.chmod(0o600)
        state_path = Path(self.lib._history_paths("take")["state"])
        state_before = state_path.read_bytes()
        page_before = self.page.read_bytes()
        journal_before = self.journal.read_bytes()

        recovered, errors = self._run_recovery()

        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("exceeds its bounded size", errors[0]["error"])
        self.assertEqual(self.signatures, [])
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual(self.page.read_bytes(), page_before)
        self.assertEqual(self.journal.read_bytes(), journal_before)

    def test_over_limit_legacy_source_refuses_before_migration(self):
        take, path, _source, _target = self._prepare_take()
        page = Path(path)
        oversized = b"x" * (self.lib.MAX_LEGACY_TAKE_PAGE_BYTES + 1)
        page.write_bytes(oversized)
        state_path = Path(self.lib._history_paths("take")["state"])
        state_before = state_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "exceeds its bounded size"):
            self.lib._take_migration_candidate("takes/" + page.stem, str(page))

        self.assertEqual(page.read_bytes(), oversized)
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual(self.signatures, [])

    def test_corpus_provenance_survives_a_fresh_history_projection(self):
        value = self._stage_migration(grade_observed=True)
        self._signed_source(value)
        recovered, errors = self._run_recovery()
        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])

        with mock.patch.object(
                self.lib, "_history_root",
                side_effect=lambda kind: str(self.root / ("rebuilt-" + kind))):
            self.lib._load_history_state("take", create=True)
            self._settle_authority()
            direct = self.lib._history_direct("take", value["take_id"])
            self.assertTrue(direct["signed_grade"])
            self.assertEqual(self.lib.calibration_report()["overall"]["resolved"], 1)

    def _git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.root, check=True,
            text=True, capture_output=True, timeout=30)

    def test_migration_source_artifacts_are_non_pages_tracked_by_corpus_git(self):
        self._git("init", "-q")
        value = self._stage_migration(grade_observed=True)
        self._signed_source(value)
        recovered, errors = self._run_recovery()
        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        provenance = self.root / ".sia-take-provenance"
        files = sorted(path for path in provenance.rglob("*") if path.is_file())
        self.assertTrue(files, "signed migration left no corpus-owned provenance")
        self.assertTrue(all(path.suffix != ".md" for path in files))
        self.assertIn(self.migration_source.encode(),
                      [path.read_bytes() for path in files])

        self._git("add", "-A")
        self._git("-c", "user.name=SIA", "-c", "user.email=sia@omarchy.local",
                  "commit", "-q", "-m", "fixture: retain migration authority")

        for path in files:
            self._git("ls-files", "--error-unmatch", "--",
                      str(path.relative_to(self.root)))
        self.assertEqual(self._git("status", "--porcelain").stdout, "")

    def test_ignored_provenance_refuses_without_overriding_git_policy(self):
        self._git("init", "-q")
        ignore = self.root / ".gitignore"
        ignore.write_text(".sia-take-provenance/\n", encoding="utf-8")
        value = self._stage_migration(grade_observed=True)
        self._signed_source(value)

        self._refuses_before_mutation(value)

        self.assertEqual(ignore.read_text(encoding="utf-8"),
                         ".sia-take-provenance/\n")

    def test_signed_capsule_retains_portable_migration_provenance(self):
        fixture_spec = importlib.util.spec_from_file_location(
            "capsule_grade_provenance_fixtures",
            REPO / "tests/test_backup_restore.py")
        fixtures = importlib.util.module_from_spec(fixture_spec)
        fixture_spec.loader.exec_module(fixtures)
        capsule = fixtures.CapsuleBoundaryTests()
        capsule.setUp()
        self.addCleanup(capsule.tearDown)
        self.root = Path(capsule.corpus)
        self.lib.TAKES_DIR = str(self.root / "takes")
        self._git("init", "-q")
        value = self._stage_migration(grade_observed=True)
        self._signed_source(value)
        recovered, errors = self._run_recovery()
        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])

        path, frozen = capsule._freeze()
        verified = fixtures.siacapsule.verify(path)

        self.assertEqual(frozen["capsule_id"], verified["capsule_id"])
        copied_corpus = Path(path) / "payload/share/corpus"
        sources = [entry.read_bytes() for entry in
                   (copied_corpus / ".sia-take-provenance").rglob("*")
                   if entry.is_file()]
        self.assertIn(self.migration_source.encode(), sources)
        relocated = Path(self.temp.name) / "relocated-corpus"
        shutil.copytree(copied_corpus, relocated)
        self.lib.TAKES_DIR = str(relocated / "takes")
        self.lib._load_history_state("take", create=True)
        self._settle_authority()
        direct = self.lib._history_direct("take", value["take_id"])
        self.assertTrue(direct["signed_grade"])
        self.assertEqual(direct["metadata"]["path"],
                         str(relocated / "takes" / self.page.name))

    def test_migration_debt_precedes_corpus_provenance_publication(self):
        value = self._stage_migration(grade_observed=True)
        self._signed_source(value)
        atomic = self.lib._atomic_text
        seen = []
        provenance = self.root / ".sia-take-provenance"

        def observed_write(path, text, *args, **kwargs):
            if Path(path).is_relative_to(provenance):
                self.assertTrue(self.notifications,
                                "corpus provenance preceded publication debt")
                self.assertEqual(self.page.read_text(encoding="utf-8"),
                                 self.migration_source)
                seen.append(Path(path))
            return atomic(path, text, *args, **kwargs)

        with mock.patch.object(self.lib, "_atomic_text", side_effect=observed_write):
            recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        self.assertTrue(seen, "migration did not publish recoverable provenance")

    def test_failed_migration_debt_does_not_publish_corpus_provenance(self):
        value = self._stage_migration(grade_observed=True)
        self._signed_source(value)
        with mock.patch.dict(sys.modules, {"sialib": self.keeper}):
            recovered, errors = self.recover(before_publish=mock.Mock(
                side_effect=RuntimeError("fixture publication debt unavailable")))

        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("fixture publication debt unavailable", errors[0]["error"])
        self.assertEqual(self.page.read_text(encoding="utf-8"), self.migration_source)
        self.assertFalse((self.root / ".sia-take-provenance").exists())
        self.assertTrue(self.journal.exists())

    def _source_artifact_after_migration(self):
        value = self._stage_migration(grade_observed=True)
        self._signed_source(value)
        recovered, errors = self._run_recovery()
        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["take_id"]])
        artifacts = [path for path in
                     (self.root / ".sia-take-provenance").rglob("*")
                     if path.is_file() and path.read_bytes() == self.migration_source.encode()]
        self.assertTrue(artifacts, "migration source is not retained in corpus authority")
        return value, artifacts[0]

    def _assert_provenance_reconciliation_refused(self, value):
        direct_before = self.lib._history_direct("take", value["take_id"])
        state = self.lib._load_history_state("take")
        overall_before = copy.deepcopy(state["overall"])
        self.lib._history_begin_authority(state)
        self.lib._save_history_state("take", state)
        with mock.patch.dict(sys.modules, {"sialib": self.keeper}):
            _changed, errors = self.lib.migrate_legacy_take_pages()
        self.assertTrue(errors, "unavailable provenance was silently reclassified")
        self.assertTrue(self.lib.natural_history_debt("take"))
        self.assertEqual(self.lib._history_direct("take", value["take_id"]),
                         direct_before)
        self.assertEqual(self.lib._load_history_state("take")["overall"],
                         overall_before)

    def test_missing_source_artifact_cannot_silently_demote_signed_grade(self):
        value, artifact = self._source_artifact_after_migration()
        artifact.rename(self.root / "retained-provenance-source")

        self._assert_provenance_reconciliation_refused(value)

    def test_changed_source_artifact_refuses_authority_reconciliation(self):
        value, artifact = self._source_artifact_after_migration()
        artifact.write_text(self.migration_source + "changed\n", encoding="utf-8")

        self._assert_provenance_reconciliation_refused(value)

    def test_symlink_source_artifact_refuses_authority_reconciliation(self):
        value, artifact = self._source_artifact_after_migration()
        retained = self.root / "retained-provenance-source"
        artifact.rename(retained)
        artifact.symlink_to(retained)

        self._assert_provenance_reconciliation_refused(value)

    def test_removed_provenance_marker_refuses_despite_retained_witness(self):
        value, _artifact = self._source_artifact_after_migration()
        target = self.page.read_text(encoding="utf-8")
        lines = target.splitlines(keepends=True)
        self.assertTrue(any(line.startswith("sia_take_provenance: ") for line in lines))
        self.page.write_text("".join(
            line for line in lines if not line.startswith("sia_take_provenance: ")),
            encoding="utf-8")

        self._assert_provenance_reconciliation_refused(value)

    def test_changed_provenance_marker_cannot_pass_a_fresh_projection(self):
        value, _artifact = self._source_artifact_after_migration()
        target = self.page.read_text(encoding="utf-8")
        marker = next(line for line in target.splitlines()
                      if line.startswith("sia_take_provenance: "))
        declaration = json.loads(marker.removeprefix("sia_take_provenance: "))
        declaration["source_sha256"] = "f" * 64
        self.page.write_text(target.replace(
            marker, "sia_take_provenance: " + json.dumps(declaration, sort_keys=True), 1),
            encoding="utf-8")
        with mock.patch.object(
                self.lib, "_history_root",
                side_effect=lambda kind: str(self.root / ("rebuilt-" + kind))):
            self.lib._load_history_state("take", create=True)

            self._assert_provenance_reconciliation_refused(value)

    def test_recurring_audit_rechecks_provenance_outside_the_take_page_directory(self):
        value, artifact = self._source_artifact_after_migration()
        self._settle_authority()
        self.lib._load_history_state("intent", create=True)
        artifact.rename(self.root / "retained-provenance-source")

        with mock.patch.dict(sys.modules, {"sialib": self.keeper}):
            changed, errors, _inspected = self.lib.audit_natural_history_authority("take")

        self.assertEqual(errors, [])
        self.assertIn(value["take_id"], changed)
        self.assertTrue(self.lib.natural_history_debt("take"),
                        "page-only audit certified unavailable provenance")

    def _stage_intent_transition(self, *, retirement=False,
                                 authority_incomplete=False):
        made = self.lib.create_intent("retain original predecessor", "2099-01-01")
        intent = self.lib.get_intent(made["id"])
        if authority_incomplete:
            state = self.lib._load_history_state("intent")
            self.lib._history_begin_authority(state)
            self.lib._save_history_state("intent", state)

        def stage():
            with mock.patch.object(
                    self.lib, "_finish_history_tx",
                    side_effect=RuntimeError("fixture after history WAL")):
                with self.assertRaisesRegex(
                        RuntimeError, "fixture after history WAL"):
                    if retirement:
                        direct = self.lib._history_direct("intent", intent["id"])
                        event = self.lib._history_retire_event("intent", direct)
                        self.lib._commit_history_retirement("intent", event)
                    else:
                        self.lib.close_intent(intent["id"], "completed")

        if authority_incomplete:
            # Construct a lower-layer WAL while bypassing only the public
            # readiness guard; recovery admission is the contract under test.
            with mock.patch.object(
                    self.lib, "natural_history_debt", return_value=False):
                stage()
        else:
            stage()
        self.journal = Path(self.lib._history_paths("intent")["pending"])
        self.page = Path(intent["path"])
        self.recover = self.lib.recover_natural_history_transactions
        return json.loads(self.journal.read_text(encoding="utf-8"))

    def _crash_page_at_target_published(self, value):
        class SimulatedPowerLoss(BaseException):
            pass

        atomic = self.lib._atomic_text

        def crash_page(path, text, *args, **kwargs):
            if Path(path) != self.page:
                return atomic(path, text, *args, **kwargs)

            def stop(boundary):
                if boundary == "target-published":
                    raise SimulatedPowerLoss(boundary)

            with mock.patch.object(
                    self.lib.siaqueue, "_publish_boundary",
                    side_effect=stop):
                return atomic(path, text, *args, **kwargs)

        with mock.patch.dict(sys.modules, {"sialib": self.keeper}), \
                mock.patch.object(
                    self.lib, "_atomic_text", side_effect=crash_page), \
                self.assertRaises(SimulatedPowerLoss):
            self.recover()

        self.assertEqual(
            self.page.read_text(encoding="utf-8"), value["target_text"])
        self.assertTrue(self.journal.exists())

    def _recover_after_page_crash_requires_durable_target(
            self, value, *, kind):
        atomic = self.lib._atomic_text
        unlink = self.lib._unlink_durable
        admitted = []

        def observe_atomic(path, text, *args, **kwargs):
            result = atomic(path, text, *args, **kwargs)
            if Path(path) == self.page and kwargs.get("exclusive") is True:
                self.assertEqual(result, "existing")
                admitted.append(result)
            return result

        def observe_unlink(path):
            if Path(path) == self.journal:
                self.assertEqual(admitted, ["existing"])
            return unlink(path)

        signatures = list(self.signatures)
        with mock.patch.dict(sys.modules, {"sialib": self.keeper}), \
                mock.patch.object(
                    self.lib, "_atomic_text", side_effect=observe_atomic), \
                mock.patch.object(
                    self.lib, "_unlink_durable", side_effect=observe_unlink):
            recovered, errors = self.recover()

        event = value.get("history_event", value.get("event"))
        expected = value.get("take_id") \
            or event["after"]["metadata"]["id"]
        self.assertEqual(errors, [])
        self.assertEqual(recovered, [expected])
        self.assertEqual(admitted, ["existing"])
        self.assertEqual(self.signatures, signatures)
        self.assertFalse(self.journal.exists())
        self.assertTrue(self.lib.natural_history_debt(kind))

    def _write_unprojected_intent_page(self):
        text = self.page.read_text(encoding="utf-8")
        marker = next(line for line in text.splitlines()
                      if line.startswith("sia_intent: "))
        metadata = json.loads(marker.removeprefix("sia_intent: "))
        metadata["id"] = "f" * 10
        metadata["text"] = "valid unprojected intent"
        replacement = "sia_intent: " + json.dumps(metadata, sort_keys=True)
        path = Path(self.lib.INTENTS_DIR) / "2099-01-01-ffffffffff.md"
        path.write_text(text.replace(marker, replacement, 1), encoding="utf-8")
        observed = self.lib._history_page_metadata(
            "intent", str(path), path.read_text(encoding="utf-8"))
        self.assertEqual(observed["id"], metadata["id"])
        self.assertIsNone(self.lib._history_direct("intent", metadata["id"]))
        return path, metadata["id"]

    def test_ordinary_history_rejects_a_substituted_before_side(self):
        value = self._stage_intent_transition()
        value["event"]["before"]["metadata"]["text"] = "unobserved predecessor"

        self._refuses_before_mutation(value, kind="intent")

    def test_ordinary_history_cannot_erase_its_required_predecessor(self):
        value = self._stage_intent_transition()
        value["event"]["before"] = None

        self._refuses_before_mutation(value, kind="intent")

    def test_ordinary_history_rejects_a_hashed_unknown_event_field(self):
        value = self._stage_intent_transition()
        value["event"]["ignored_extension"] = "distinct identity"

        self._refuses_before_mutation(value, kind="intent")

    def test_ordinary_history_rejects_an_unknown_transaction_field(self):
        value = self._stage_intent_transition()
        value["ignored_extension"] = "retained but unauthorised"

        self._refuses_before_mutation(value, kind="intent")

    def test_retirement_rejects_an_unknown_transaction_field(self):
        value = self._stage_intent_transition(retirement=True)
        self.page = self.page.rename(self.root / "retained-intent-source")
        value["ignored_extension"] = "retained but unauthorised"

        self._refuses_before_mutation(value, kind="intent")

    def test_ordinary_history_rejects_a_null_authority_generation(self):
        value = self._stage_intent_transition()
        value["event"]["authority_generation"] = None

        self._refuses_before_mutation(value, kind="intent")

    def test_ordinary_history_cannot_forge_authority_restoration(self):
        value = self._stage_intent_transition(authority_incomplete=True)
        self.assertFalse(value["event"]["authority_restore"])
        value["event"]["authority_restore"] = True
        value["event"]["authority_basis"] = \
            self.lib._history_directory_identity(self.lib.INTENTS_DIR)

        self._refuses_before_mutation(value, kind="intent")

    def test_reserved_ordinary_event_cannot_be_rehashed_on_replay(self):
        value = self._stage_intent_transition()
        interrupted = []

        def interrupt():
            interrupted.append("publication")
            raise RuntimeError("fixture after event reservation")

        recovered, errors = self.recover(before_publish=interrupt)
        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("fixture after event reservation", errors[0]["error"])
        self.assertEqual(interrupted, ["publication"])
        self.assertTrue(self.journal.exists())

        value["event"]["record_key"] = "f" * 10

        self._refuses_before_mutation(value, kind="intent")

    def test_stale_ordinary_wal_cannot_certify_an_unprojected_page(self):
        value = self._stage_intent_transition()
        self.assertTrue(value["event"]["authority_restore"])
        unprojected, unprojected_id = self._write_unprojected_intent_page()

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["event"]["after"]["metadata"]["id"]])
        self.assertFalse(self.journal.exists())
        self.assertTrue(unprojected.exists())
        self.assertIsNone(self.lib._history_direct("intent", unprojected_id))
        self.assertTrue(self.lib.natural_history_debt("intent"),
                        "stale directory authority was restored on replay")

    def test_legacy_restore_wal_recovers_without_restoring_authority(self):
        value = self._stage_intent_transition()
        value["event"].pop("authority_basis")
        value = self._save(value)

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["event"]["after"]["metadata"]["id"]])
        self.assertFalse(self.journal.exists())
        self.assertTrue(self.lib.natural_history_debt("intent"))

    def test_current_reserved_state_requires_its_transition_marker(self):
        value = self._stage_intent_transition()
        self.lib._reserve_history_event(
            value["event"], journal_path=str(self.journal), journal_value=value)
        state = self.lib._load_history_state("intent")
        state["authority"].pop("transition")
        self.lib._save_history_state("intent", state)

        self._refuses_before_mutation(value, kind="intent")

    def test_legacy_reserved_state_recovers_without_restoring_authority(self):
        value = self._stage_intent_transition()
        self.lib._reserve_history_event(
            value["event"], journal_path=str(self.journal), journal_value=value)
        state = self.lib._load_history_state("intent")
        state["authority"].pop("transition")
        self.lib._save_history_state("intent", state)
        value["event"].pop("authority_basis")
        value = self._save(value)

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["event"]["after"]["metadata"]["id"]])
        self.assertFalse(self.journal.exists())
        self.assertTrue(self.lib.natural_history_debt("intent"))

    def test_applied_legacy_restore_replay_invalidates_old_readiness(self):
        value = self._stage_intent_transition()
        event = value["event"]
        self.assertTrue(event["authority_restore"])
        event.pop("authority_basis")
        value = self._save(value)
        event = value["event"]
        state = self.lib._load_history_state("intent")
        self.lib._history_begin_authority(state)
        state["next_event"] += 1
        self.lib._save_history_state("intent", state)
        self.lib._atomic_text(str(self.page), value["target_text"])
        self.lib._history_project_event(event)
        direct_path = self.lib._history_record_path(
            "intent", event["after"]["metadata"]["id"])
        direct = json.loads(Path(direct_path).read_text(encoding="utf-8"))
        direct.pop("authority_checkpoint")
        self.lib._atomic_text(
            direct_path, json.dumps(
                direct, sort_keys=True, separators=(",", ":")),
            mode=0o600)
        state = self.lib._load_history_state("intent")
        state["authority"].update({
            "complete": True,
            "phase": "ready",
            "cursor": {},
            "catalog_cursor": 0,
            "catalog_limit": 0,
            "audit_cursor": 0,
            "audit_limit": 0,
            "checkpoint": self.lib._history_directory_identity(
                self.lib.INTENTS_DIR),
        })
        state["authority"].pop("transition", None)
        state["authority"].pop("audit_cycle", None)
        state["authority"].pop("error", None)
        self.lib._save_history_state("intent", state)

        def interrupt():
            raise RuntimeError("fixture after legacy readiness invalidation")

        recovered, errors = self.recover(before_publish=interrupt)

        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("fixture after legacy readiness invalidation",
                      errors[0]["error"])
        self.assertTrue(self.journal.exists())
        invalidated = self.lib._load_history_state("intent")["authority"]
        self.assertFalse(invalidated["complete"])
        self.assertEqual(invalidated["phase"], "scan")
        self.assertEqual(
            invalidated.get("error"),
            "legacy restoration event " + event["event_id"]
            + " requires authority reconciliation")
        self.assertTrue(self.lib.natural_history_debt("intent"))

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(
            recovered, [event["after"]["metadata"]["id"]])
        self.assertFalse(self.journal.exists())
        self.assertTrue(self.lib.natural_history_debt("intent"))

    def test_page_added_after_publish_cannot_enter_the_ready_checkpoint(self):
        value = self._stage_intent_transition()
        original_atomic = self.lib._atomic_text
        injected = []

        def publish(path, text, *args, **kwargs):
            result = original_atomic(path, text, *args, **kwargs)
            if path == str(self.page) and not injected:
                injected.append(self._write_unprojected_intent_page())
            return result

        with mock.patch.object(self.lib, "_atomic_text", side_effect=publish):
            recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["event"]["after"]["metadata"]["id"]])
        self.assertEqual(len(injected), 1)
        unprojected, unprojected_id = injected[0]
        self.assertTrue(unprojected.exists())
        self.assertIsNone(self.lib._history_direct("intent", unprojected_id))
        self.assertTrue(self.lib.natural_history_debt("intent"),
                        "late sibling entered the publication checkpoint")

    def test_ordinary_replay_fsyncs_a_visible_target_before_wal_cleanup(self):
        value = self._stage_intent_transition()

        self._crash_page_at_target_published(value)
        self._recover_after_page_crash_requires_durable_target(
            value, kind="intent")

    def test_grade_replay_fsyncs_a_visible_target_before_wal_cleanup(self):
        value = self._stage_grade()

        self._crash_page_at_target_published(value)
        self._recover_after_page_crash_requires_durable_target(
            value, kind="take")

    def test_migration_replay_fsyncs_a_visible_target_before_wal_cleanup(self):
        value = self._stage_migration()

        self._crash_page_at_target_published(value)
        self._recover_after_page_crash_requires_durable_target(
            value, kind="take")

    def test_authority_reconciliation_writes_a_readable_direct_record(self):
        made = self.lib.create_intent("authority source", "2099-01-01")
        intent = self.lib.get_intent(made["id"])
        page = Path(intent["path"])
        text = page.read_text(encoding="utf-8")
        marker = next(line for line in text.splitlines()
                      if line.startswith("sia_intent: "))
        metadata = json.loads(marker.removeprefix("sia_intent: "))
        metadata["text"] = "externally changed authority source"
        page.write_text(text.replace(
            marker, "sia_intent: " + json.dumps(metadata, sort_keys=True), 1),
            encoding="utf-8")
        state = self.lib._load_history_state("intent")
        self.lib._history_begin_authority(state)
        self.lib._save_history_state("intent", state)

        changed, errors = self.lib.advance_natural_history_authority("intent")

        self.assertEqual(errors, [])
        self.assertIn(page.name, changed)
        direct = self.lib._history_direct("intent", made["id"])
        self.assertEqual(direct["metadata"]["text"], metadata["text"])
        self.assertIsNone(direct.get("authority_checkpoint"))

    def test_ordinary_history_cannot_forge_signed_resolution_authority(self):
        take, path, _source, target = self._prepare_take()
        self.page = Path(path)
        self.page.write_text(target, encoding="utf-8")
        event = self._event(take, path, target, "authority-update", signed_grade=True)
        value = self.lib._history_tx_payload(
            "take", event, target,
            source_sha256=hashlib.sha256(target.encode()).hexdigest())
        self.journal = Path(self.lib._history_paths("take")["pending"])
        self.recover = self.lib.recover_natural_history_transactions

        self._refuses_before_mutation(value)

    def test_retirement_predecessor_refusal_precedes_sequence_reservation(self):
        value = self._stage_intent_transition(retirement=True)
        value["event"]["before"]["metadata"]["text"] = "unobserved predecessor"

        self._refuses_before_mutation(value, kind="intent")

    def test_retirement_of_authoritative_page_refuses_before_reservation(self):
        value = self._stage_intent_transition(retirement=True)

        self._refuses_before_mutation(value, kind="intent")

    def test_retirement_cannot_allocate_a_catalog_slot(self):
        value = self._stage_intent_transition(retirement=True)
        missing = self.page
        self.page = self.page.rename(self.root / "retained-intent-source")
        value["event"]["catalog_index"] = self.lib._load_history_state("intent")["next_catalog"]

        self._refuses_before_mutation(value, kind="intent")

        self.assertFalse(missing.exists())

    def test_retirement_cannot_claim_authority_restoration(self):
        value = self._stage_intent_transition(retirement=True)
        self.page = self.page.rename(self.root / "retained-intent-source")
        value["event"]["authority_restore"] = True

        self._refuses_before_mutation(value, kind="intent")

    def test_reserved_retirement_event_cannot_be_rehashed_on_replay(self):
        value = self._stage_intent_transition(retirement=True)
        self.page = self.page.rename(self.root / "retained-intent-source")
        interrupted = []

        def interrupt():
            interrupted.append("publication")
            raise RuntimeError("fixture after retirement reservation")

        recovered, errors = self.recover(before_publish=interrupt)
        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("fixture after retirement reservation", errors[0]["error"])
        self.assertEqual(interrupted, ["publication"])
        value["event"].pop("authority_basis")

        self._refuses_before_mutation(value, kind="intent")

    def test_retirement_cannot_prove_absence_using_another_page_path(self):
        value = self._stage_intent_transition(retirement=True)
        value["event"]["path"] = str(self.page.with_name("unrelated-absent.md"))

        self._refuses_before_mutation(value, kind="intent")

    def test_partial_retirement_projection_retains_idempotent_recovery(self):
        value = self._stage_intent_transition(retirement=True)
        self.page.rename(self.root / "retained-intent-source")
        with mock.patch.object(
                self.lib, "_history_apply_stats_transition",
                side_effect=RuntimeError("fixture after tombstone publication")):
            recovered, errors = self._run_recovery()
        self.assertEqual(recovered, [])
        self.assertTrue(errors)
        self.assertIn("fixture after tombstone publication", errors[0]["error"])
        direct = self.lib._history_direct("intent", value["event"]["record_key"])
        self.assertTrue(direct["tombstone"])

        recovered, errors = self._run_recovery()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["event"]["record_key"]])
        self.assertFalse(self.journal.exists())
        self.assertFalse(self.lib._load_history_state("intent")["open"])


if __name__ == "__main__":
    unittest.main()
