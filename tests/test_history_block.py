"""Storage-free history links; fixtures are not machine evidence."""

import copy
import hashlib
import importlib
import json
import unittest
from unittest import mock


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()


class HistoryBlock(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("siahistoryblock")
        self.entry = {"source_returns": {"fixture": "not evidence"},
                      "expected_source_returns_sha256": "a" * 64,
                      "event_batches": []}
        self.entry_pin = digest(self.entry)

    def prepare(self, parent=None, **changes):
        arguments = dict(epoch_id="fixture-epoch", entry=self.entry,
                         expected_entry_sha256=self.entry_pin,
                         source_batch_sha256="b" * 64, observed_at=100,
                         parent=parent,
                         expected_parent_sha256=None if parent is None else digest(parent))
        arguments.update(changes)
        return self.api.prepare(**arguments)

    def test_link_preserves_entry_without_embedding_prefix(self):
        first = self.prepare()
        second = self.prepare(first, observed_at=101, source_batch_sha256="c" * 64)
        self.assertEqual(second["entry"], self.entry)
        self.assertEqual(second["parent_sha256"], digest(first))
        self.assertNotIn("parent", second)
        self.assertNotIn("history", second)
        self.assertEqual(second["status"], "linked-not-published")
        self.assertEqual(second["non_claims"], list(self.api.NON_CLAIMS))
        self.assertEqual(first["entry"], self.entry)
        second["entry"]["source_returns"]["fixture"] = "changed detached output"
        self.assertNotEqual(second["entry"], self.entry)

    def test_wrong_external_pins_and_missing_parent_refuse(self):
        first = self.prepare()
        for changes in ({"expected_entry_sha256": "d" * 64},
                        {"parent": first, "expected_parent_sha256": "d" * 64},
                        {"expected_parent_sha256": digest(first)}):
            with self.subTest(changes=changes):
                with self.assertRaises(self.api.HistoryBlockRefusal):
                    self.prepare(**changes)

    def test_parent_epoch_clock_and_duplicate_capture_refuse(self):
        first = self.prepare()
        for changes in ({"epoch_id": "another-epoch"}, {"observed_at": 99},
                        {"source_batch_sha256": "b" * 64}):
            with self.subTest(changes=changes):
                with self.assertRaises(self.api.HistoryBlockRefusal):
                    self.prepare(first, **{"source_batch_sha256": "c" * 64, **changes})

    def test_parent_contract_is_not_just_a_self_hash(self):
        first = self.prepare()
        for field, value in (("status", "published"), ("non_claims", []),
                             ("entry_sha256", "d" * 64), ("extra", True)):
            parent = copy.deepcopy(first)
            parent[field] = value
            with self.subTest(field=field), self.assertRaises(self.api.HistoryBlockRefusal):
                self.prepare(parent, source_batch_sha256="c" * 64)

    def test_original_document_cap_applies_before_serialization(self):
        entry = copy.deepcopy(self.entry)
        entry["source_returns"]["fixture"] = "x" * self.api.MAX_DOCUMENT_BYTES
        with mock.patch.object(self.api.json, "dumps", side_effect=AssertionError("oversized serialization")):
            with self.assertRaises(self.api.HistoryBlockRefusal):
                self.prepare(entry=entry, expected_entry_sha256="d" * 64)

    def test_entry_mutation_during_detachment_refuses(self):
        original = self.api.json.loads

        def changing(raw):
            result = original(raw)
            self.entry["source_returns"]["fixture"] = "mutation"
            return result

        with mock.patch.object(self.api.json, "loads", side_effect=changing):
            with self.assertRaises(self.api.HistoryBlockRefusal):
                self.prepare()

    def test_long_chain_never_copies_transitive_prefix(self):
        parent = None
        for index in range(100):
            block = self.prepare(parent, source_batch_sha256=digest({"fixture_capture": index}))
            self.assertEqual(block["entry"], self.entry)
            self.assertEqual(set(block), set(self.api._KEYS))
            self.assertEqual(block["parent_sha256"], None if parent is None else digest(parent))
            parent = block

    def test_parent_mutation_during_detachment_refuses(self):
        parent = self.prepare()
        original = self.api.json.loads

        def changing(raw):
            result = original(raw)
            parent["status"] = "published"
            return result

        with mock.patch.object(self.api.json, "loads", side_effect=changing):
            with self.assertRaises(self.api.HistoryBlockRefusal):
                self.prepare(parent, source_batch_sha256="c" * 64)

    def test_actual_fixture_capture_extraction_replays_source_validator(self):
        from tests import test_controller_source_capture as capture_tests

        case = capture_tests.ControllerSourceCapture(methodName="runTest")
        try:
            case.setUp()
            captured = case.capture()
            before = copy.deepcopy(captured)
            block = self.api.prepare_captured(
                vars(case.lib), batch=captured,
                expected_batch_sha256=captured["batch_sha256"],
                parent=None, expected_parent_sha256=None)
            self.assertEqual(block["entry"]["source_returns"], captured["source_returns"])
            self.assertEqual(block["source_batch_sha256"], captured["batch_sha256"])
            self.assertEqual(block["observed_at"], captured["observed_at"])
            self.assertEqual(captured, before)
            corrupted = copy.deepcopy(captured)
            corrupted["intake_projection"]["status"] = "published"
            with self.assertRaises(ValueError):
                self.api.prepare_captured(
                    vars(case.lib), batch=corrupted,
                    expected_batch_sha256=captured["batch_sha256"],
                    parent=None, expected_parent_sha256=None)
        finally:
            case.doCleanups()
