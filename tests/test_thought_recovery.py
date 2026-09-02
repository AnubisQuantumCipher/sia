#!/usr/bin/env python3
"""Bounded, crash-safe thought-page recovery invariants."""

import contextlib
import importlib.util
import json
import os
import tempfile
import time
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
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ThoughtRecovery(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.sialib = _load(
            "sialib_thought_recovery_test", os.path.join(BIN, "sialib.py"))
        self.state = os.path.join(self.root.name, "state")
        self.corpus = os.path.join(self.root.name, "corpus")
        os.makedirs(self.state)
        os.makedirs(self.corpus)
        self.sialib.STATE = self.state
        self.sialib.CORPUS = self.corpus
        self.sialib.CORPUS_OWNER_LOCK = os.path.join(
            self.state, "corpus-owner.lock")
        self.sialib.THOUGHTS_PATH = os.path.join(self.state, "thoughts.json")
        self.sialib.MEMO_PATH = os.path.join(self.state, "memo.json")
        self.sialib.THOUGHT_INBOX_PATH = os.path.join(
            self.state, "thought-inbox.json")
        self.sialib.THOUGHT_INBOX_LOCK = os.path.join(
            self.state, "thought-inbox.lock")
        self.sialib.siamind.MIND_PATH = os.path.join(self.state, "mind.json")
        self.sialib.LIFECYCLE_LOCK = os.path.join(
            self.state, "lifecycle.lock")
        self.sialib.LIFECYCLE_TOMBSTONE = os.path.join(
            self.state, "lifecycle-removed")

    def tearDown(self):
        self.root.cleanup()

    def _complete_legacy_scan(self):
        self.sialib._save_thought_legacy_scan({
            "schema": self.sialib.THOUGHT_LEGACY_SCAN_SCHEMA,
            "phase": "complete", "after": "", "unindexed": 0,
            "indexed": 0, "cookie": 0, "directory": None,
            "discarded": [], "reset_id": None})

    def _page_record(self, slug, stamp, text):
        return self.sialib._canonical_thought_page_record({
            "ts": stamp, "kind": "note", "text": text,
            "links": ["sia/cortex"], "urgent": False,
            "origin": "model", "slug": slug})

    def _write_exact_page_without_intent(self, record):
        frontmatter, body = self.sialib._thought_page_parts(record)
        self.sialib.write_page(record["slug"], frontmatter, body)

    def _write_pending_thought_producers(self, queue_ids):
        rows = [{
            "kind": "note", "text": f"producer {queue_id}",
            "links": ["mind/native"], "urgent": False,
            "origin": "model", "_queue_id": queue_id,
            "_queued_at": "2026-01-02T03:04:05Z",
        } for queue_id in queue_ids]
        self.sialib.atomic_write(
            self.sialib.THOUGHT_INBOX_PATH,
            json.dumps(rows, separators=(",", ":")))

    def test_agent_queue_snapshot_does_not_reenter_its_lease(self):
        """The native-replay finalizer must let ``pending`` own queue locking.

        Linux ``flock`` leases are attached to open file descriptions.  A
        second exclusive lock opened by the same process blocks rather than
        acting re-entrant, so make a nested acquisition fail immediately in
        this regression test instead of allowing a test runner to hang.
        """
        receipt = self.sialib.siaqueue.enqueue_note(
            self.state, "test agent", "preserve this queue identity")
        held = []

        @contextlib.contextmanager
        def non_reentrant_queue_lock(queue_dir):
            if held:
                raise AssertionError("agent queue lease was re-entered")
            held.append(queue_dir)
            try:
                yield
            finally:
                held.pop()

        with mock.patch.object(
                self.sialib.siaqueue, "_queue_lock",
                non_reentrant_queue_lock):
            observed = self.sialib._pending_external_thought_queue_ids()

        self.assertEqual(observed, {receipt["request_id"]})
        self.assertEqual(held, [])

    def test_legacy_thought_inbox_upgrade_is_stable_across_claim_rename(self):
        rows = [
            {"kind": "note", "text": "legacy note",
             "links": ["mind/native"], "urgent": True},
            {"kind": "ponder", "text": "legacy ponder",
             "links": [], "urgent": False},
            {"kind": "take", "text": "legacy take proposal",
             "links": ["sia/cortex"], "urgent": False},
        ]
        self.sialib.atomic_write(
            self.sialib.THOUGHT_INBOX_PATH,
            json.dumps(rows, separators=(",", ":")))
        before = os.stat(self.sialib.THOUGHT_INBOX_PATH)
        expected_queued_at = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(before.st_mtime))

        first = self.sialib._read_thought_inbox(
            self.sialib.THOUGHT_INBOX_PATH)
        second = self.sialib._read_thought_inbox(
            self.sialib.THOUGHT_INBOX_PATH)
        claim = self.sialib._thought_inbox_claim_path()
        os.replace(self.sialib.THOUGHT_INBOX_PATH, claim)
        claimed = self.sialib._read_thought_inbox(claim)

        self.assertEqual(first, second)
        self.assertEqual(first, claimed)
        self.assertEqual(
            len({row["_queue_id"] for row in first}), len(first))
        self.assertTrue(all(
            row["_queued_at"] == expected_queued_at for row in first))
        self.assertTrue(all(row["origin"] == "model" for row in first))

    def test_legacy_thought_inbox_partial_metadata_is_refused(self):
        for metadata in (
                {"_queue_id": "a" * 32},
                {"_queued_at": "2026-01-02T03:04:05Z"}):
            with self.subTest(metadata=metadata):
                row = {"kind": "note", "text": "legacy",
                       "links": [], "urgent": False, **metadata}
                self.sialib.atomic_write(
                    self.sialib.THOUGHT_INBOX_PATH,
                    json.dumps([row], separators=(",", ":")))
                with self.assertRaisesRegex(
                        ValueError, "thought inbox metadata is incomplete"):
                    self.sialib._read_thought_inbox(
                        self.sialib.THOUGHT_INBOX_PATH)

    def test_modern_thought_inbox_metadata_remains_authoritative(self):
        modern = {
            "kind": "note", "text": "modern", "links": [],
            "urgent": False, "origin": "model", "_queue_id": "b" * 32,
            "_queued_at": "2026-01-02T03:04:05Z",
        }
        self.sialib.atomic_write(
            self.sialib.THOUGHT_INBOX_PATH,
            json.dumps([modern], separators=(",", ":")))
        with mock.patch.object(
                self.sialib.time, "gmtime",
                side_effect=AssertionError("modern queue entered migration")):
            self.assertEqual(
                self.sialib._read_thought_inbox(
                    self.sialib.THOUGHT_INBOX_PATH)[0]["_queue_id"],
                modern["_queue_id"])
        modern["_queue_id"] = "not-canonical"
        self.sialib.atomic_write(
            self.sialib.THOUGHT_INBOX_PATH,
            json.dumps([modern], separators=(",", ":")))
        with self.assertRaisesRegex(
                ValueError, "thought queue identity is invalid"):
            self.sialib._read_thought_inbox(
                self.sialib.THOUGHT_INBOX_PATH)

    def _index_partial_legacy_page(self, record):
        """Durably index one page while leaving the baseline incomplete."""
        self._write_exact_page_without_intent(record)
        thought_dir = os.path.join(self.corpus, "thoughts")
        directory_info = os.stat(thought_dir)
        page_name = os.path.basename(self.sialib.corpus_path(record["slug"]))
        page_info = os.stat(self.sialib.corpus_path(record["slug"]))
        observed = {"name": page_name, "mode": page_info.st_mode,
                    "device": page_info.st_dev, "inode": page_info.st_ino,
                    "size": page_info.st_size,
                    "mtime_ns": page_info.st_mtime_ns,
                    "ctime_ns": page_info.st_ctime_ns}
        generation = self.sialib._thought_directory_generation(
            directory_info)
        entries = [observed]
        page = (entries, False, generation["inode"], generation,
                len(entries))
        with self.sialib.corpus_owner(), mock.patch.object(
                self.sialib, "_read_legacy_thought_directory_page",
                return_value=page):
            self.assertIsNone(self.sialib._prepare_thought_recovery_claim())
        self.assertEqual(
            self.sialib._load_thought_legacy_scan()["phase"], "index")

    def _index_complete_legacy_pages(self, records):
        """Build one complete catalog without yet preparing its first claim."""
        for record in records:
            self._write_exact_page_without_intent(record)
        thought_dir = os.path.join(self.corpus, "thoughts")
        generation = self.sialib._thought_directory_generation(
            os.stat(thought_dir))
        entries = []
        for record in records:
            path = self.sialib.corpus_path(record["slug"])
            info = os.stat(path)
            entries.append({
                "name": os.path.basename(path), "mode": info.st_mode,
                "device": info.st_dev, "inode": info.st_ino,
                "size": info.st_size, "mtime_ns": info.st_mtime_ns,
                "ctime_ns": info.st_ctime_ns})
        page = (entries, True, 0, generation, len(entries))
        with self.sialib.corpus_owner(), self.sialib._owner_lease(
                self.sialib._thought_recovery_lock_path(),
                "thought recovery test"), mock.patch.object(
                    self.sialib, "_read_legacy_thought_directory_page",
                    return_value=page):
            state = self.sialib._index_legacy_thought_batch_locked(
                self.sialib._load_thought_legacy_scan())
        self.assertEqual(state["phase"], "apply")
        return state

    def _schedule_reset_after_page_mutation(self):
        with self.sialib.corpus_owner():
            with self.assertRaisesRegex(
                    RuntimeError, "durable reset scheduled"):
                self.sialib._prepare_thought_recovery_claim()
        self.assertEqual(
            self.sialib._load_thought_legacy_scan()["phase"], "reset")

    def _backfill_thought_recovery(self, store=None):
        store = {"v": 1, "thoughts": []} if store is None else store
        with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
            with self.sialib.corpus_owner():
                self.sialib._recover_pending_thought_projection(
                    {"sync_needed": False}, store)
        self.assertEqual(
            self.sialib._load_thought_legacy_scan()["phase"], "complete")
        return store

    def test_replay_intent_crash_retries_from_unapplied_mind(self):
        record = self._page_record(
            "thoughts/intent-boundary", "2026-01-02T03:04:05Z",
            "intent before mind")
        self._index_complete_legacy_pages([record])
        original = self.sialib._thought_mind_replay_intent

        def fail_after_intent(claim):
            original(claim)
            raise OSError("crash after replay intent")

        with self.sialib.corpus_owner(), mock.patch.object(
                self.sialib, "_thought_mind_replay_intent",
                side_effect=fail_after_intent):
            with self.assertRaisesRegex(OSError, "after replay intent"):
                self.sialib._settle_thought_page_signals(
                    {"v": 1, "thoughts": []},
                    mind=self.sialib.siamind._empty_mind())
        self.assertTrue(os.path.isfile(
            self.sialib._thought_mind_replay_path()))
        self.assertTrue(os.path.isfile(
            self.sialib._thought_recovery_claim_path()))

        store = {"v": 1, "thoughts": []}
        with self.sialib.corpus_owner():
            self.sialib._settle_thought_page_signals(store)
        mind = self.sialib.siamind.load_mind()
        self.assertIn("sia/cortex", mind["nodes"])
        self.assertFalse(os.path.lexists(
            self.sialib._thought_mind_replay_path()))

    def test_mind_save_crash_uses_claim_receipt_before_applied_commit(self):
        record = self._page_record(
            "thoughts/mind-save-boundary", "2026-01-02T03:04:05Z",
            "mind durable before journal commit")
        self._index_complete_legacy_pages([record])
        store = {"v": 1, "thoughts": []}
        with self.sialib.corpus_owner(), mock.patch.object(
                self.sialib, "_mark_thought_mind_replay_applied_locked",
                side_effect=OSError("crash before applied-page commit")):
            with self.assertRaisesRegex(OSError, "before applied-page commit"):
                self.sialib._settle_thought_page_signals(
                    store, mind=self.sialib.siamind._empty_mind())
        saved_before_retry = self.sialib.siamind.load_mind()
        self.assertTrue(os.path.isfile(
            self.sialib._thought_recovery_claim_path()))

        retry_store = self.sialib.load_thoughts()
        with self.sialib.corpus_owner(), mock.patch.object(
                self.sialib.siamind, "apply_exact_thought_reinforcement",
                wraps=self.sialib.siamind.apply_exact_thought_reinforcement
                ) as apply_exact:
            self.sialib._settle_thought_page_signals(retry_store)
        apply_exact.assert_not_called()
        self.assertEqual(
            self.sialib.siamind.load_mind()["nodes"],
            saved_before_retry["nodes"])
        self.assertFalse(os.path.lexists(
            self.sialib._thought_mind_replay_path()))

    def test_intent_is_durable_before_page_and_recreates_failed_write(self):
        store = {"v": 1, "thoughts": []}
        observed = []

        def fail_after_intent(*_args, **_kwargs):
            observed.extend(os.listdir(self.sialib._thought_recovery_dir()))
            raise OSError("page write interrupted")

        with mock.patch.object(
                self.sialib, "write_page", side_effect=fail_after_intent):
            with self.assertRaisesRegex(OSError, "page write interrupted"):
                self.sialib.add_thought(
                    store, "note", "redo me", ["sia/cortex"],
                    thought_ts="2026-01-02T03:04:05Z", origin="model")
        self.assertTrue(observed)
        self.assertEqual(store["thoughts"], [])

        mind = self.sialib.siamind._empty_mind()
        with self.sialib.corpus_owner():
            recovered, reinforced = \
                self.sialib._settle_thought_page_signals(store, mind=mind)
        self.assertTrue(recovered)
        self.assertTrue(reinforced)
        self.assertTrue(os.path.exists(
            self.sialib.corpus_path(store["thoughts"][0]["slug"])))
        self.assertFalse(os.path.exists(
            self.sialib._thought_recovery_claim_path()))
        self.assertEqual(os.listdir(self.sialib._thought_recovery_dir()), [])

    def test_one_saved_projection_retries_without_mind_duplication(self):
        self._complete_legacy_scan()
        store = {"v": 1, "thoughts": []}
        thought = self.sialib.add_thought(
            store, "note", "two-state commit", ["sia/cortex"],
            thought_ts="2026-01-02T03:04:05Z", origin="model")
        with self.sialib.corpus_owner(), mock.patch.object(
                self.sialib, "export_thoughts",
                side_effect=OSError("thought state fsync interrupted")):
            with self.assertRaisesRegex(OSError, "fsync interrupted"):
                self.sialib._settle_thought_page_signals(
                    store, mind=self.sialib.siamind._empty_mind())
        first_mind = self.sialib.siamind.load_mind()
        first_count = first_mind["nodes"]["sia/cortex"]["n"]
        self.assertTrue(os.path.exists(
            self.sialib._thought_recovery_claim_path()))

        retry_store = {"v": 1, "thoughts": []}
        with self.sialib.corpus_owner():
            self.sialib._settle_thought_page_signals(retry_store)
        second_mind = self.sialib.siamind.load_mind()
        self.assertEqual(second_mind["nodes"]["sia/cortex"]["n"], first_count)
        self.assertEqual(retry_store["thoughts"][0]["slug"], thought["slug"])
        self.assertFalse(os.path.exists(
            self.sialib._thought_recovery_claim_path()))

    def test_native_page_receipt_survives_claim_ack_until_producer_ack(self):
        self._complete_legacy_scan()
        queue_id = "a" * 32
        store = {"v": 1, "thoughts": []}
        thought = self.sialib.add_thought(
            store, "note", "native producer retry", ["mind/native"],
            queue_id=queue_id, thought_ts="2026-01-02T03:04:05Z",
            origin="model")
        with self.sialib.corpus_owner():
            self.sialib._settle_thought_page_signals(
                store, mind=self.sialib.siamind._empty_mind())
        first_mind = self.sialib.siamind.load_mind()
        first_projection = json.loads(json.dumps(
            first_mind["nodes"]["mind/native"]))
        self.assertFalse(os.path.lexists(
            self.sialib._thought_recovery_claim_path()))
        self.assertTrue(os.path.isfile(
            self.sialib._thought_mind_replay_path()))

        # Model the exact crash window: claim/source projections committed,
        # but the originating inbox or agent request was not acknowledged.
        # Its deterministic queue ID therefore recreates a new claim UUID for
        # the same exact page record on the next transaction.
        replayed = self.sialib.add_thought(
            store, "note", "native producer retry", ["mind/native"],
            queue_id=queue_id, thought_ts="2026-01-02T03:04:05Z",
            origin="model")
        self.assertEqual(replayed["slug"], thought["slug"])
        with self.sialib.corpus_owner(), mock.patch.object(
                self.sialib.siamind,
                "apply_exact_thought_reinforcement",
                wraps=self.sialib.siamind.apply_exact_thought_reinforcement
                ) as apply_exact:
            self.sialib._settle_thought_page_signals(store)
        apply_exact.assert_not_called()
        self.assertEqual(
            self.sialib.siamind.load_mind()["nodes"]["mind/native"],
            first_projection)
        self.assertTrue(os.path.isfile(
            self.sialib._thought_mind_replay_path()))

        # This models the final durable producer acknowledgment/memo image.
        self.sialib._finalize_native_thought_mind_replay()
        self.assertFalse(os.path.lexists(
            self.sialib._thought_mind_replay_path()))
        self.assertEqual(self.sialib._thought_recovery_debt(), "")

    def test_native_pre_admission_retires_full_batch_after_old_acks(self):
        self._complete_legacy_scan()
        queue_ids = ["a" * 32, "b" * 32, "c" * 32]
        store = {"v": 1, "thoughts": []}
        with mock.patch.object(
                self.sialib, "MAX_THOUGHT_RECOVERY_RECORDS", 2):
            for queue_id in queue_ids[:2]:
                self.sialib.add_thought(
                    store, "note", f"producer {queue_id}",
                    ["mind/native"], queue_id=queue_id,
                    thought_ts="2026-01-02T03:04:05Z", origin="model")
            with self.sialib.corpus_owner():
                self.sialib._settle_thought_page_signals(
                    store, mind=self.sialib.siamind._empty_mind())
            # Model a crash after both old producers were acknowledged but
            # before the end-of-pulse finalizer. Their applied table is still
            # full when a newer producer arrives.
            self._write_pending_thought_producers([queue_ids[2]])
            admitted = self.sialib.add_thought(
                store, "note", f"producer {queue_ids[2]}",
                ["mind/native"], queue_id=queue_ids[2],
                thought_ts="2026-01-02T03:04:05Z", origin="model")
            # Pre-admission retirement inside replay intent frees the absent
            # rows before enforcing capacity and protects this active claim.
            with self.sialib.corpus_owner():
                self.sialib._settle_thought_page_signals(store)
        self.assertEqual(admitted["queue_id"], queue_ids[2])

    def test_dream_finalization_retains_retryable_pulse_producer(self):
        self._complete_legacy_scan()
        queue_id = "d" * 32
        store = {"v": 1, "thoughts": []}
        self.sialib.add_thought(
            store, "note", "pulse producer", ["mind/pulse"],
            queue_id=queue_id, thought_ts="2026-01-02T03:04:05Z",
            origin="model")
        with self.sialib.corpus_owner():
            self.sialib._settle_thought_page_signals(
                store, mind=self.sialib.siamind._empty_mind())
        first = json.loads(json.dumps(
            self.sialib.siamind.load_mind()["nodes"]["mind/pulse"]))
        self._write_pending_thought_producers([queue_id])

        # This is the same selective finalizer DREAM invokes after its ready
        # memo. The earlier pulse producer still exists, so its receipt lives.
        self.sialib._finalize_native_thought_mind_replay()
        self.assertTrue(os.path.isfile(
            self.sialib._thought_mind_replay_path()))
        self.sialib.add_thought(
            store, "note", "pulse producer", ["mind/pulse"],
            queue_id=queue_id, thought_ts="2026-01-02T03:04:05Z",
            origin="model")
        with self.sialib.corpus_owner(), mock.patch.object(
                self.sialib.siamind,
                "apply_exact_thought_reinforcement",
                wraps=self.sialib.siamind.apply_exact_thought_reinforcement
                ) as apply_exact:
            self.sialib._settle_thought_page_signals(store)
        apply_exact.assert_not_called()
        self.assertEqual(
            self.sialib.siamind.load_mind()["nodes"]["mind/pulse"], first)

        os.unlink(self.sialib.THOUGHT_INBOX_PATH)
        self.sialib._finalize_native_thought_mind_replay()
        self.assertFalse(os.path.lexists(
            self.sialib._thought_mind_replay_path()))

    def test_first_light_resumes_batches_and_records_metadata_less_pages(self):
        legacy = "thoughts/000-legacy"
        self.sialib.write_page(
            legacy, ["type: thought", "title: legacy"], "# legacy\n")
        self._write_exact_page_without_intent(self._page_record(
            "thoughts/100-described", "2026-01-02T03:04:05Z", "first"))
        self._write_exact_page_without_intent(self._page_record(
            "thoughts/200-described", "2026-01-02T03:04:06Z", "second"))
        store = {"v": 1, "thoughts": []}
        with mock.patch.object(
                self.sialib, "MAX_THOUGHT_RECOVERY_RECORDS", 2), \
                mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}), \
                mock.patch.object(self.sialib, "log") as log:
            with self.sialib.corpus_owner():
                self.sialib._recover_pending_thought_projection(
                    {"sync_needed": False}, store)
        scan = self.sialib._load_thought_legacy_scan()
        self.assertEqual(scan["phase"], "complete")
        self.assertEqual(scan["after"], "")
        self.assertEqual(scan["unindexed"], 1)
        self.assertEqual(scan["indexed"], 0)
        self.assertEqual(scan["cookie"], 0)
        self.assertEqual(len(store["thoughts"]), 2)
        self.assertTrue(any(legacy in str(call) for call in log.call_args_list))

    def test_directory_cookie_refuses_then_rebuilds_after_mutation(self):
        thought_dir = os.path.join(self.corpus, "thoughts")
        os.makedirs(thought_dir)
        for position in range(201):
            open(os.path.join(
                thought_dir, f"noise-{position:03d}"), "wb").close()

        calls = []
        original_readdir = self.sialib._THOUGHT_RECOVERY_LIBC.readdir

        def counted_readdir(pointer):
            calls.append(None)
            return original_readdir(pointer)

        with mock.patch.object(
                self.sialib, "MAX_THOUGHT_RECOVERY_RECORDS", 2), \
                mock.patch.object(
                    self.sialib._THOUGHT_RECOVERY_LIBC, "readdir",
                    side_effect=counted_readdir):
            with self.sialib.corpus_owner():
                self.assertIsNone(
                    self.sialib._prepare_thought_recovery_claim())
        self.assertLessEqual(len(calls), 2)
        scan = self.sialib._load_thought_legacy_scan()
        self.assertEqual(scan["phase"], "index")
        self.assertGreater(scan["cookie"], 0)

        overlay = self._page_record(
            "thoughts/appeared-behind-cookie",
            "2026-01-02T03:04:05Z", "mutation overlay")
        self._write_exact_page_without_intent(overlay)
        with self.sialib.corpus_owner():
            with self.assertRaisesRegex(
                    RuntimeError, "durable reset scheduled"):
                self.sialib._prepare_thought_recovery_claim()
        reset = self.sialib._load_thought_legacy_scan()
        self.assertEqual(reset["phase"], "reset")
        self.assertEqual(reset["reset_id"], reset["discarded"][-1])

        store = {"v": 1, "thoughts": []}
        with mock.patch.object(
                self.sialib, "MAX_THOUGHT_RECOVERY_RECORDS", 2), \
                mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
            with self.sialib.corpus_owner():
                self.sialib._recover_pending_thought_projection(
                    {"sync_needed": False}, store)
        settled = self.sialib._load_thought_legacy_scan()
        self.assertEqual(settled["phase"], "complete")
        self.assertIsNone(settled["reset_id"])
        self.assertEqual(store["thoughts"][0]["slug"], overlay["slug"])
        self.assertEqual(self.sialib._thought_recovery_debt(), "")

    def test_reset_replays_unseen_older_page_without_losing_mind_edges(self):
        newer = self._page_record(
            "thoughts/newer-shared-links", "2026-01-02T03:04:10Z",
            "newer shared links")
        newer["links"] = ["mind/a", "mind/b"]
        tail = self._page_record(
            "thoughts/newest-tail", "2026-01-02T03:04:11Z",
            "tail keeps baseline partial")
        tail["links"] = ["mind/tail"]
        self._index_complete_legacy_pages([newer, tail])
        store = {"v": 1, "thoughts": []}
        with mock.patch.object(
                self.sialib, "MAX_THOUGHT_RECOVERY_RECORDS", 1), \
                self.sialib.corpus_owner():
            with self.assertRaises(self.sialib.ThoughtRecoveryPending):
                self.sialib._settle_thought_page_signals(
                    store, mind=self.sialib.siamind._empty_mind())
        self.assertEqual(
            [row["slug"] for row in store["thoughts"]], [newer["slug"]])
        self.assertTrue(os.path.isfile(
            self.sialib._thought_mind_replay_path()))

        older = self._page_record(
            "thoughts/older-behind-prefix", "2026-01-02T03:04:05Z",
            "older unseen links")
        older["links"] = ["mind/a", "mind/c"]
        self._write_exact_page_without_intent(older)
        self._schedule_reset_after_page_mutation()

        claim_path = self.sialib._thought_recovery_claim_path()
        original_unlink = self.sialib.os.unlink
        interrupted = {"value": False}

        def fail_first_claim_unlink(path, *args, **kwargs):
            if path == claim_path and not interrupted["value"]:
                interrupted["value"] = True
                raise OSError("crash after applied-page commit")
            return original_unlink(path, *args, **kwargs)

        with mock.patch.object(
                self.sialib, "MAX_THOUGHT_RECOVERY_RECORDS", 1), \
                mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}), \
                mock.patch.object(
                    self.sialib.os, "unlink",
                    side_effect=fail_first_claim_unlink):
            with self.sialib.corpus_owner():
                with self.assertRaisesRegex(
                        OSError, "after applied-page commit"):
                    self.sialib._recover_pending_thought_projection(
                        {"sync_needed": False}, store)
        mind_after_commit = self.sialib.siamind.load_mind()
        older_projection = {
            "a": json.loads(json.dumps(mind_after_commit["nodes"]["mind/a"])),
            "c": json.loads(json.dumps(mind_after_commit["nodes"]["mind/c"])),
            "edge": json.loads(json.dumps(
                mind_after_commit["edges"]["mind/a|mind/c"]))}
        self.assertEqual(
            mind_after_commit["nodes"]["mind/c"]["signals"]["thought"],
            self.sialib._thought_reinforcement_ts(older))
        self.assertEqual(
            mind_after_commit["edges"]["mind/a|mind/c"]["last_touch"],
            self.sialib._thought_reinforcement_ts(older))

        with mock.patch.object(
                self.sialib, "MAX_THOUGHT_RECOVERY_RECORDS", 1), \
                mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
            with self.sialib.corpus_owner():
                self.sialib._recover_pending_thought_projection(
                    {"sync_needed": False}, store)
        settled_mind = self.sialib.siamind.load_mind()
        self.assertEqual(settled_mind["nodes"]["mind/a"],
                         older_projection["a"])
        self.assertEqual(settled_mind["nodes"]["mind/c"],
                         older_projection["c"])
        self.assertEqual(settled_mind["edges"]["mind/a|mind/c"],
                         older_projection["edge"])
        self.assertEqual(
            [row["slug"] for row in store["thoughts"]],
            [older["slug"], newer["slug"], tail["slug"]])
        self.assertFalse(os.path.lexists(
            self.sialib._thought_mind_replay_path()))
        self.assertEqual(self.sialib._thought_recovery_debt(), "")

    def test_legacy_cursor_waits_for_catalog_commit_and_retry_is_exact(self):
        record = self._page_record(
            "thoughts/crash-boundary", "2026-01-02T03:04:05Z",
            "catalog before cursor")
        self._write_exact_page_without_intent(record)
        with self.sialib.corpus_owner(), mock.patch.object(
                self.sialib, "_save_thought_legacy_scan",
                side_effect=OSError("cursor fsync interrupted")):
            with self.assertRaisesRegex(OSError, "fsync interrupted"):
                self.sialib._prepare_thought_recovery_claim()
        self.assertFalse(os.path.exists(
            self.sialib._thought_legacy_scan_path()))
        self.assertTrue(os.path.exists(
            self.sialib._thought_legacy_catalog_path()))
        self.assertTrue(os.listdir(
            self.sialib._thought_legacy_index_dir()))

        store = {"v": 1, "thoughts": []}
        with self.sialib.corpus_owner():
            self.sialib._settle_thought_page_signals(
                store, mind=self.sialib.siamind._empty_mind())
        self.assertEqual(store["thoughts"][0]["slug"], record["slug"])
        self.assertEqual(
            self.sialib._load_thought_legacy_scan()["phase"], "complete")

    def test_reset_archives_partial_index_and_catalog_before_restart(self):
        first = self._page_record(
            "thoughts/partial-before-reset", "2026-01-02T03:04:05Z",
            "partial generation")
        self._index_partial_legacy_page(first)
        self.assertTrue(os.path.isdir(
            self.sialib._thought_legacy_index_dir()))
        self.assertTrue(os.path.isfile(
            self.sialib._thought_legacy_catalog_path()))

        overlay = self._page_record(
            "thoughts/overlay-after-reset", "2026-01-02T03:04:06Z",
            "new generation")
        self._write_exact_page_without_intent(overlay)
        with self.sialib.corpus_owner():
            with self.assertRaisesRegex(
                    RuntimeError, "durable reset scheduled"):
                self.sialib._prepare_thought_recovery_claim()
        reset = self.sialib._load_thought_legacy_scan()
        reset_id = reset["reset_id"]

        store = {"v": 1, "thoughts": []}
        with mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
            with self.sialib.corpus_owner():
                self.sialib._recover_pending_thought_projection(
                    {"sync_needed": False}, store)
        self.assertTrue(os.path.isdir(
            self.sialib._thought_legacy_index_dir()
            + ".discarded-" + reset_id))
        self.assertTrue(os.path.isfile(
            self.sialib._thought_legacy_catalog_path()
            + ".discarded-" + reset_id))
        self.assertEqual(
            [row["slug"] for row in store["thoughts"]],
            [first["slug"], overlay["slug"]])
        self.assertEqual(
            self.sialib._load_thought_legacy_scan()["phase"], "complete")

    def test_reset_discards_deleted_uncommitted_page_and_converges(self):
        stale = self._page_record(
            "thoughts/deleted-during-baseline", "2026-01-02T03:04:05Z",
            "stale deletion")
        self._index_partial_legacy_page(stale)
        os.unlink(self.sialib.corpus_path(stale["slug"]))

        self._schedule_reset_after_page_mutation()
        store = self._backfill_thought_recovery()

        self.assertEqual(store["thoughts"], [])
        self.assertEqual(self.sialib._thought_recovery_debt(), "")

    def test_reset_discards_renamed_uncommitted_page_and_converges(self):
        stale = self._page_record(
            "thoughts/renamed-before-reset", "2026-01-02T03:04:05Z",
            "renamed current authority")
        self._index_partial_legacy_page(stale)
        os.unlink(self.sialib.corpus_path(stale["slug"]))
        current = self._page_record(
            "thoughts/renamed-after-reset", stale["ts"], stale["text"])
        self._write_exact_page_without_intent(current)

        self._schedule_reset_after_page_mutation()
        store = self._backfill_thought_recovery()

        self.assertEqual(
            [row["slug"] for row in store["thoughts"]], [current["slug"]])
        self.assertEqual(self.sialib._thought_recovery_debt(), "")

    def test_reset_discards_modified_uncommitted_page_and_converges(self):
        stale = self._page_record(
            "thoughts/modified-during-baseline", "2026-01-02T03:04:05Z",
            "stale content")
        self._index_partial_legacy_page(stale)
        current = self._page_record(
            stale["slug"], stale["ts"], "current replacement")
        self._write_exact_page_without_intent(current)

        self._schedule_reset_after_page_mutation()
        store = self._backfill_thought_recovery()

        self.assertEqual(store["thoughts"][0]["text"], current["text"])
        self.assertEqual(self.sialib._thought_recovery_debt(), "")

    def test_legacy_symlink_and_post_index_change_fail_closed(self):
        thought_dir = os.path.join(self.corpus, "thoughts")
        os.makedirs(thought_dir)
        target = os.path.join(self.root.name, "outside")
        with open(target, "wb") as stream:
            stream.write(b"outside")
        os.symlink(target, os.path.join(thought_dir, "linked.md"))
        with self.sialib.corpus_owner():
            with self.assertRaisesRegex(ValueError, "not a regular file"):
                self.sialib._prepare_thought_recovery_claim()
        with open(target, "rb") as stream:
            self.assertEqual(stream.read(), b"outside")

        os.unlink(os.path.join(thought_dir, "linked.md"))
        record = self._page_record(
            "thoughts/changed", "2026-01-02T03:04:05Z", "original")
        self._write_exact_page_without_intent(record)
        with self.sialib.corpus_owner(), self.sialib._owner_lease(
                self.sialib._thought_recovery_lock_path(),
                "thought recovery test"):
            state = self.sialib._index_legacy_thought_batch_locked(
                self.sialib._load_thought_legacy_scan())
        self.assertEqual(state["phase"], "apply")
        path = self.sialib.corpus_path(record["slug"])
        with open(path, "r+b") as stream:
            content = stream.read()
            stream.seek(0)
            stream.write(content.replace(b"original", b"tampered"))
            stream.flush()
            os.fsync(stream.fileno())
        with self.sialib.corpus_owner():
            with self.assertRaisesRegex(ValueError, "changed after indexing"):
                self.sialib._prepare_thought_recovery_claim()

    def test_readiness_refuses_baseline_intent_and_claim_debt(self):
        memo = {"sync_needed": False, "ready": {
            "v": 1, "completed_at": "2026-01-02T03:04:05Z",
            "kind": "recovery", "identity": "0" * 32}}
        patches = (
            mock.patch.object(self.sialib, "load_memo", return_value=memo),
            mock.patch.object(
                self.sialib.siatakes, "grade_recovery_required",
                return_value=False),
            mock.patch.object(
                self.sialib.siatakes, "take_migration_required",
                return_value=False),
        )
        with patches[0], patches[1], patches[2]:
            ready, reason = self.sialib.memory_readiness()
            self.assertFalse(ready)
            self.assertIn("baseline", reason)
            self._complete_legacy_scan()
            record = self._page_record(
                "thoughts/pending", "2026-01-02T03:04:05Z", "pending")
            self.sialib._queue_thought_recovery(record)
            ready, reason = self.sialib.memory_readiness()
            self.assertFalse(ready)
            self.assertIn("intents", reason)
            with self.sialib.corpus_owner():
                claim = self.sialib._prepare_thought_recovery_claim()
            ready, reason = self.sialib.memory_readiness()
            self.assertFalse(ready)
            self.assertIn("claim", reason)
            self.assertIsNotNone(claim)


if __name__ == "__main__":
    unittest.main(verbosity=2)
