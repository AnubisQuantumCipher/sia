"""Retained recovery bytes must be admitted before any target publication."""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home


REPO = Path(__file__).resolve().parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, REPO / "bin" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NaturalHistoryRecoveryAdmission(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lib = _load("siatakes_recovery_admission", "siatakes.py")
        self.lib.TAKES_DIR = str(self.root / "takes")
        self.lib.INTENTS_DIR = str(self.root / "intents")
        self.lib.GRADE_TX_DIR = str(self.root / "grades")
        self.lib.TAKE_MIGRATION_TX_DIR = str(self.root / "migrations")

    def _stage_real_create(self):
        with mock.patch.object(
                self.lib, "_finish_history_tx",
                side_effect=RuntimeError("fixture crash after WAL")):
            with self.assertRaisesRegex(RuntimeError, "fixture crash after WAL"):
                self.lib.create_intent("retain this commitment", "2026-12-01")
        paths = self.lib._history_paths("intent")
        self.journal = Path(paths["pending"])
        self.state_path = Path(paths["state"])
        value = json.loads(self.journal.read_text(encoding="utf-8"))
        self.assertFalse(Path(value["event"]["path"]).exists())
        return value

    def _save_changed_journal(self, value):
        value = copy.deepcopy(value)
        event = value["event"]
        event.pop("event_id")
        event["event_id"] = hashlib.sha256(json.dumps(
            event, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False).encode()).hexdigest()
        self.journal.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        self.journal.chmod(0o600)
        return value

    def _assert_refused_before_publication(self, value, target):
        self._save_changed_journal(value)
        state_before = self.state_path.read_bytes()
        pending_before = self.journal.read_bytes()
        notified = []

        recovered, errors = self.lib.recover_natural_history_transactions(
            before_publish=lambda: notified.append("publication"))

        self.assertEqual(recovered, [])
        self.assertTrue(errors, "invalid retained target must refuse recovery")
        self.assertFalse(target.exists(), "recovery wrote a refused target")
        self.assertEqual(notified, [], "refusal followed publication notification")
        self.assertEqual(self.state_path.read_bytes(), state_before,
                         "invalid target consumed a history sequence")
        self.assertEqual(self.journal.read_bytes(), pending_before)

    def test_retained_destination_outside_kind_store_is_refused_before_write(self):
        value = self._stage_real_create()
        target = self.root / "outside-intent-store.md"
        value["event"]["path"] = str(target)
        self._assert_refused_before_publication(value, target)

    def test_retained_destination_traversal_is_refused_before_write(self):
        value = self._stage_real_create()
        target = self.root / "outside-by-traversal.md"
        value["event"]["path"] = str(
            self.root / "intents" / ".." / target.name)
        self._assert_refused_before_publication(value, target)

    def test_retained_target_metadata_mismatch_is_refused_before_write(self):
        value = self._stage_real_create()
        target = Path(value["event"]["path"])
        value["event"]["after"]["metadata"]["text"] = "a different commitment"
        self._assert_refused_before_publication(value, target)

    def test_retained_legacy_flat_filename_remains_recoverable(self):
        value = self._stage_real_create()
        target = self.root / "intents" / "legacy-retained-name.md"
        value["event"]["path"] = str(target)
        value["event"]["after"]["metadata"].update({
            "path": str(target), "slug": "intents/legacy-retained-name"})
        value = self._save_changed_journal(value)

        recovered, errors = self.lib.recover_natural_history_transactions()

        self.assertEqual(errors, [])
        self.assertEqual(recovered, [value["event"]["after"]["metadata"]["id"]])
        self.assertEqual(target.read_text(encoding="utf-8"), value["target_text"])
        self.assertFalse(self.journal.exists())

    def test_authority_invalid_record_preserves_opaque_page(self):
        self.lib._load_history_state("intent", create=True)
        directory = Path(self.lib.INTENTS_DIR)
        directory.mkdir(exist_ok=True)
        target = directory / "legacy-invalid-page.md"
        text = "A damaged page retained for an explicit invalid-record row.\n"
        target.write_text(text, encoding="utf-8")
        key, metadata = self.lib._history_authoritative_metadata(
            "intent", str(target), text)
        self.assertEqual(metadata["status"], "invalid-record")
        event = self.lib._history_event(
            "intent", "authority-update", str(target), text,
            after=metadata, record_key=key, catalog_new=True)

        self.lib._commit_history_tx(
            "intent", event, text,
            source_sha256=hashlib.sha256(text.encode()).hexdigest())

        self.assertEqual(target.read_text(encoding="utf-8"), text)
        direct = self.lib._history_direct("intent", key)
        self.assertEqual(direct["metadata"], metadata)


class ThoughtRecoveryNamespaceAdmission(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lib = _load("sialib_thought_namespace_admission", "sialib.py")
        state = self.root / "state"
        corpus = self.root / "corpus"
        state.mkdir()
        corpus.mkdir()
        self.lib.STATE = str(state)
        self.lib.CORPUS = str(corpus)
        for name, filename in (
                ("CORPUS_OWNER_LOCK", "corpus-owner.lock"),
                ("THOUGHTS_PATH", "thoughts.json"),
                ("MEMO_PATH", "memo.json"),
                ("THOUGHT_INBOX_PATH", "thought-inbox.json"),
                ("THOUGHT_INBOX_LOCK", "thought-inbox.lock"),
                ("LIFECYCLE_LOCK", "lifecycle.lock"),
                ("LIFECYCLE_TOMBSTONE", "lifecycle-removed")):
            setattr(self.lib, name, str(state / filename))
        prior_mind = self.lib.siamind.MIND_PATH
        self.addCleanup(setattr, self.lib.siamind, "MIND_PATH", prior_mind)
        self.lib.siamind.MIND_PATH = str(state / "mind.json")
        self.lib._save_thought_legacy_scan({
            "schema": self.lib.THOUGHT_LEGACY_SCAN_SCHEMA,
            "phase": "complete", "after": "", "unindexed": 0,
            "indexed": 0, "cookie": 0, "directory": None,
            "discarded": [], "reset_id": None})

    def _stage_record(self, slug):
        record = self.lib._thought_recovery_record({
            "ts": "2026-01-05T12:00:00Z", "kind": "note",
            "text": "retain this exact thought", "links": ["sia/cortex"],
            "urgent": False, "origin": "model", "slug": "thoughts/fixture"})
        record["page"]["slug"] = slug
        record["record_id"] = hashlib.sha256(json.dumps(
            record["page"], sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        directory = Path(self.lib._thought_recovery_dir())
        directory.mkdir(mode=0o700, exist_ok=True)
        path = directory / (record["record_id"] + ".json")
        path.write_text(json.dumps(
            record, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        path.chmod(0o600)
        return record, path

    def test_retained_thought_cannot_materialize_in_event_namespace(self):
        slug = "events/org/2026-01-05"
        _record, pending = self._stage_record(slug)
        store = self.lib.load_thoughts()
        before = copy.deepcopy(store)

        with self.assertRaises((ValueError, RuntimeError)):
            self.lib.reconcile_thought_pages(store)

        self.assertFalse(Path(self.lib.corpus_path(slug)).exists())
        self.assertEqual(store, before)
        self.assertTrue(pending.exists())

    def test_retained_thought_cannot_introduce_nested_thought_namespace(self):
        slug = "thoughts/unscanned/nested"
        _record, pending = self._stage_record(slug)

        with self.assertRaises((ValueError, RuntimeError)):
            self.lib.reconcile_thought_pages(self.lib.load_thoughts())

        self.assertFalse(Path(self.lib.corpus_path(slug)).exists())
        self.assertTrue(pending.exists())

    def test_legacy_flat_thought_name_remains_recoverable(self):
        record, _pending = self._stage_record("thoughts/legacy-retained-name")
        store = self.lib.load_thoughts()

        self.lib.reconcile_thought_pages(store)

        text = self.lib._read_thought_page_text(record["page"]["slug"])
        self.assertEqual(self.lib._decode_exact_thought_page(
            record["page"]["slug"], text), record["page"])
        self.assertIn(record["page"], store["thoughts"])


if __name__ == "__main__":
    unittest.main()
