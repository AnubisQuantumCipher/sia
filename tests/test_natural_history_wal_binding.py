#!/usr/bin/env python3
"""Focused checks that history allocation is bound to durable intent."""

import contextlib
import copy
import hashlib
import importlib.util
import json
import os
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
sys.path.insert(0, BIN)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


siatakes = _load(
    "siatakes_wal_binding", os.path.join(BIN, "siatakes.py"))


class NaturalHistoryWalBinding(unittest.TestCase):
    def test_open_take_projection_preserves_legacy_identity_contract(self):
        projection = {
            "due": "2099-01-01", "path": "/fixture/take.md",
            "page_sha256": "a" * 64, "device": 1, "inode": 1,
            "size": 1, "mtime_ns": 1, "ctime_ns": 1,
        }
        for key in ("b" * 10, "c" * 20):
            with self.subTest(key=key):
                current = {**projection, "key": key}
                self.assertEqual(
                    siatakes._validate_history_open_projection(
                        current, key, "take"), current)
        for key in ("b" * 11, "c" * 19, "g" * 10):
            with self.subTest(key=key), self.assertRaises(ValueError):
                siatakes._validate_history_open_projection(
                    {**projection, "key": key}, key, "take")

    @contextlib.contextmanager
    def projection_roots(self, root):
        with mock.patch.object(
                siatakes, "TAKES_DIR", os.path.join(root, "takes")), \
                mock.patch.object(
                    siatakes, "INTENTS_DIR", os.path.join(root, "intents")), \
                mock.patch.object(
                    siatakes, "GRADE_TX_DIR", os.path.join(root, "grades")), \
                mock.patch.object(
                    siatakes, "TAKE_MIGRATION_TX_DIR",
                    os.path.join(root, "migrations")):
            yield

    def staged_intent(self):
        real_finish = siatakes._finish_history_tx
        with mock.patch.object(
                siatakes, "_finish_history_tx", return_value=None) as finish:
            siatakes.create_intent("durable intent binding", "2099-01-01")
        kind, journal, value = finish.call_args.args
        self.assertEqual(kind, "intent")
        return real_finish, journal, value

    def test_missing_wal_cannot_reserve_or_publish_event(self):
        with tempfile.TemporaryDirectory() as root, self.projection_roots(root):
            finish, journal, value = self.staged_intent()
            state_before = copy.deepcopy(
                siatakes._load_history_state("intent"))
            page = value["event"]["path"]
            os.unlink(journal)

            with self.assertRaises(FileNotFoundError):
                finish("intent", journal, value)

            self.assertEqual(
                siatakes._load_history_state("intent"), state_before)
            self.assertFalse(os.path.exists(page))

    def test_finish_refuses_event_not_bound_by_durable_wal(self):
        with tempfile.TemporaryDirectory() as root, self.projection_roots(root):
            finish, journal, durable = self.staged_intent()
            state_before = copy.deepcopy(
                siatakes._load_history_state("intent"))
            substituted = copy.deepcopy(durable)
            substituted["event"]["operation"] = "legacy-baseline"
            basis = dict(substituted["event"])
            basis.pop("event_id")
            substituted["event"]["event_id"] = hashlib.sha256(json.dumps(
                basis, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False).encode()).hexdigest()

            with self.assertRaisesRegex(
                    ValueError, "transaction journal changed before reservation"):
                finish("intent", journal, substituted)

            self.assertEqual(
                siatakes._load_history_state("intent"), state_before)
            self.assertTrue(os.path.exists(journal))
            self.assertFalse(os.path.exists(substituted["event"]["path"]))


if __name__ == "__main__":
    unittest.main()
