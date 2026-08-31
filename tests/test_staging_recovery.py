#!/usr/bin/env python3
"""Fixed-slot publication and torn touch-queue recovery invariants."""

import hashlib
import json
import os
import stat
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

import siaqueue
import siamind
import sialib
import siatakes
import siabench


class SimulatedPowerLoss(BaseException):
    pass


class FixedSlotPublication(unittest.TestCase):
    BOUNDARIES = (
        "payload-fsynced", "payload-linked", "target-published",
        "target-directory-fsynced", "staging-clean-fsynced")

    def test_replace_recovers_every_publication_boundary(self):
        for boundary in self.BOUNDARIES:
            with self.subTest(boundary=boundary), \
                    tempfile.TemporaryDirectory() as root:
                authority = os.path.join(root, "authority")
                staging = os.path.join(root, "staging")
                os.mkdir(authority)
                target = os.path.join(authority, "state.json")

                def stop(name):
                    if name == boundary:
                        raise SimulatedPowerLoss(name)

                with mock.patch.object(
                        siaqueue, "_publish_boundary", side_effect=stop):
                    with self.assertRaises(SimulatedPowerLoss):
                        siaqueue.fixed_atomic_publish(
                            target, b"durable\n", staging_dir=staging)

                # A killed writer can leave only the fixed lock/payload slots;
                # it never creates a sibling in the authoritative directory.
                self.assertLessEqual(
                    set(os.listdir(staging)),
                    {siaqueue.STAGING_LOCK_NAME,
                     siaqueue.STAGING_PAYLOAD_NAME})
                self.assertTrue(set(os.listdir(authority)) <= {"state.json"})
                siaqueue.fixed_atomic_publish(
                    target, b"durable\n", staging_dir=staging)
                with open(target, "rb") as stream:
                    self.assertEqual(stream.read(), b"durable\n")
                self.assertEqual(
                    set(os.listdir(staging)), {siaqueue.STAGING_LOCK_NAME})

    def test_repeated_prepublication_crashes_do_not_grow_namespaces(self):
        with tempfile.TemporaryDirectory() as root:
            authority = os.path.join(root, "authority")
            staging = os.path.join(root, "staging")
            os.mkdir(authority)
            target = os.path.join(authority, "state.json")

            def stop(name):
                if name == "payload-fsynced":
                    raise SimulatedPowerLoss(name)

            with mock.patch.object(
                    siaqueue, "_publish_boundary", side_effect=stop):
                for _attempt in range(5):
                    with self.assertRaises(SimulatedPowerLoss):
                        siaqueue.fixed_atomic_publish(
                            target, b"same\n", staging_dir=staging)
                    self.assertEqual(os.listdir(authority), [])
                    self.assertEqual(
                        set(os.listdir(staging)),
                        {siaqueue.STAGING_LOCK_NAME,
                         siaqueue.STAGING_PAYLOAD_NAME})
            siaqueue.fixed_atomic_publish(
                target, b"same\n", staging_dir=staging)
            self.assertEqual(os.listdir(authority), ["state.json"])

    def test_exclusive_retry_fsyncs_exact_publication_and_never_clobbers(self):
        with tempfile.TemporaryDirectory() as root:
            authority = os.path.join(root, "authority")
            staging = os.path.join(root, "staging")
            os.mkdir(authority)
            target = os.path.join(authority, "intent.json")

            def stop(name):
                if name == "target-published":
                    raise SimulatedPowerLoss(name)

            with mock.patch.object(
                    siaqueue, "_publish_boundary", side_effect=stop):
                with self.assertRaises(SimulatedPowerLoss):
                    siaqueue.fixed_atomic_publish(
                        target, b"intent\n", exclusive=True,
                        staging_dir=staging)

            observed = []
            with mock.patch.object(
                    siaqueue, "_publish_boundary",
                    side_effect=observed.append):
                result = siaqueue.fixed_atomic_publish(
                    target, b"intent\n", exclusive=True,
                    staging_dir=staging)
            self.assertEqual(result, "existing")
            self.assertIn("target-directory-fsynced", observed)
            with self.assertRaises(FileExistsError):
                siaqueue.fixed_atomic_publish(
                    target, b"different\n", exclusive=True,
                    staging_dir=staging)
            with open(target, "rb") as stream:
                self.assertEqual(stream.read(), b"intent\n")

    def test_exclusive_recovers_every_publication_boundary(self):
        for boundary in self.BOUNDARIES:
            with self.subTest(boundary=boundary), \
                    tempfile.TemporaryDirectory() as root:
                authority = os.path.join(root, "authority")
                staging = os.path.join(root, "staging")
                os.mkdir(authority)
                target = os.path.join(authority, "intent.json")

                def stop(name):
                    if name == boundary:
                        raise SimulatedPowerLoss(name)

                with mock.patch.object(
                        siaqueue, "_publish_boundary", side_effect=stop):
                    with self.assertRaises(SimulatedPowerLoss):
                        siaqueue.fixed_atomic_publish(
                            target, b"intent\n", exclusive=True,
                            staging_dir=staging)
                siaqueue.fixed_atomic_publish(
                    target, b"intent\n", exclusive=True,
                    staging_dir=staging)
                with open(target, "rb") as stream:
                    self.assertEqual(stream.read(), b"intent\n")
                self.assertEqual(
                    set(os.listdir(staging)), {siaqueue.STAGING_LOCK_NAME})

    def test_nested_authority_uses_outer_sibling_on_same_filesystem(self):
        with tempfile.TemporaryDirectory() as root:
            outer = os.path.join(root, "share")
            inner = os.path.join(outer, "corpus")
            os.makedirs(inner)
            target = os.path.join(inner, "page.md")
            staging = siaqueue.staging_dir_for(
                target, authority_roots=(inner, outer))
            self.assertNotEqual(
                os.path.commonpath((staging, outer)), outer)
            siaqueue.fixed_atomic_publish(
                target, b"page\n", staging_dir=staging)
            self.assertEqual(
                os.stat(staging).st_dev, os.stat(inner).st_dev)

    def test_unsafe_directory_hardlink_and_split_lock_are_refused(self):
        with tempfile.TemporaryDirectory() as root:
            authority = os.path.join(root, "authority")
            staging = os.path.join(root, "staging")
            os.mkdir(authority)
            target = os.path.join(authority, "state")
            os.chmod(authority, 0o770)
            with self.assertRaisesRegex(ValueError, "owner-private"):
                siaqueue.fixed_atomic_publish(
                    target, b"x", staging_dir=staging)
            os.chmod(authority, 0o700)
            with open(target, "wb") as stream:
                stream.write(b"old")
            os.link(target, os.path.join(root, "alias"))
            with self.assertRaisesRegex(ValueError, "owned regular"):
                siaqueue.fixed_atomic_publish(
                    target, b"new", staging_dir=staging)
            os.unlink(os.path.join(root, "alias"))
            os.unlink(target)

            real_flock = siaqueue.fcntl.flock
            replaced = False

            def replace_lock(descriptor, operation):
                nonlocal replaced
                if operation & siaqueue.fcntl.LOCK_EX and not replaced:
                    replaced = True
                    lock = os.path.join(staging, siaqueue.STAGING_LOCK_NAME)
                    os.unlink(lock)
                    with open(lock, "wb"):
                        pass
                return real_flock(descriptor, operation)

            with mock.patch.object(
                    siaqueue.fcntl, "flock", side_effect=replace_lock):
                with self.assertRaisesRegex(ValueError, "lock changed"):
                    siaqueue.fixed_atomic_publish(
                        target, b"new", staging_dir=staging)

    def test_runtime_adapters_leave_no_random_authority_siblings(self):
        with tempfile.TemporaryDirectory() as root:
            share = os.path.join(root, "share", "sia")
            corpus = os.path.join(share, "corpus")
            state = os.path.join(root, "state", "sia")
            event_dir = os.path.join(corpus, "events", "test")
            os.makedirs(event_dir)
            os.makedirs(state)
            path = os.path.join(event_dir, "day.md")
            with mock.patch.multiple(
                    sialib, SHARE=share, CORPUS=corpus, STATE=state):
                sialib.atomic_write(path, "memory\n")
            self.assertEqual(os.listdir(event_dir), ["day.md"])

            takes = os.path.join(root, "takes")
            intents = os.path.join(root, "intents")
            os.makedirs(takes)
            os.makedirs(intents)
            page = os.path.join(takes, "take.md")
            with mock.patch.multiple(
                    siatakes, CORPUS=root, TAKES_DIR=takes,
                    INTENTS_DIR=intents):
                siatakes._atomic_text(page, "take\n", exclusive=True)
                siatakes._atomic_text(page, "take\n", exclusive=True)
                with self.assertRaises(FileExistsError):
                    siatakes._atomic_text(
                        page, "changed\n", exclusive=True)
            self.assertEqual(os.listdir(takes), ["take.md"])

            report_dir = os.path.join(root, "benchmark")
            os.mkdir(report_dir)
            report = os.path.join(report_dir, "report.json")
            siabench._atomic_text(report, "{}\n", mode=0o600)
            self.assertFalse(any(name.startswith(".sia-bench-")
                                 for name in os.listdir(report_dir)))
            self.assertEqual(
                set(os.listdir(os.path.join(
                    report_dir, siaqueue.STAGING_DIR_SUFFIX))),
                {siaqueue.STAGING_LOCK_NAME})

            mind_state = os.path.join(root, "mind-state")
            os.mkdir(mind_state)
            mind_path = os.path.join(mind_state, "mind.json")
            with mock.patch.object(siamind, "STATE", mind_state):
                siamind._atomic_state_text(mind_path, "{}")
            self.assertEqual(os.listdir(mind_state), ["mind.json"])


class AgentQueueStaging(unittest.TestCase):
    def test_enqueue_uses_private_fixed_stage_outside_authority(self):
        with tempfile.TemporaryDirectory() as state:
            receipt = siaqueue.enqueue_note(state, "agent", "remember")
            queue_dir = os.path.join(state, siaqueue.QUEUE_DIRNAME)
            names = os.listdir(queue_dir)
            self.assertTrue(any(name.endswith(
                receipt["request_id"] + ".json") for name in names))
            self.assertFalse(any(name.startswith(".enqueue-")
                                 for name in names))
            staging = os.path.join(state, siaqueue.STAGING_DIR_SUFFIX)
            self.assertEqual(
                set(os.listdir(staging)), {siaqueue.STAGING_LOCK_NAME})

    def test_bounded_retries_remove_legacy_enqueue_orphans(self):
        with tempfile.TemporaryDirectory() as state:
            queue_dir = os.path.join(state, siaqueue.QUEUE_DIRNAME)
            os.mkdir(queue_dir)
            for index in range(7):
                with open(os.path.join(
                        queue_dir, f".enqueue-legacy{index}"), "wb"):
                    pass
            with mock.patch.object(siaqueue, "MAX_QUEUE_SCAN_ENTRIES", 3):
                for _attempt in range(8):
                    _rows, errors = siaqueue.pending(state)
                    if not errors:
                        break
                else:
                    self.fail("bounded legacy cleanup did not converge")
            self.assertFalse(any(name.startswith(".enqueue-")
                                 for name in os.listdir(queue_dir)))

    def test_hardlinked_request_and_path_replacement_are_refused(self):
        with tempfile.TemporaryDirectory() as state:
            siaqueue.enqueue_note(state, "agent", "original")
            queue_dir = os.path.join(state, siaqueue.QUEUE_DIRNAME)
            request = next(
                os.path.join(queue_dir, name) for name in os.listdir(queue_dir)
                if name.endswith(".json") and not name.startswith("."))
            alias = os.path.join(state, "request-alias")
            os.link(request, alias)
            rows, errors = siaqueue.pending(state)
            self.assertEqual(rows, [])
            self.assertTrue(any("unsafe authoritative" in row["error"]
                                for row in errors))
            os.unlink(alias)

            name = os.path.basename(request)
            real_lstat = siaqueue.os.lstat
            calls = 0

            def replace_on_final_stat(path):
                nonlocal calls
                if os.path.abspath(path) == os.path.abspath(request):
                    calls += 1
                    if calls == 2:
                        with open(request, "rb") as stream:
                            raw = stream.read()
                        replacement = request + ".replacement"
                        with open(replacement, "wb") as stream:
                            stream.write(raw)
                        os.chmod(replacement, 0o600)
                        os.replace(replacement, request)
                return real_lstat(path)

            with mock.patch.object(
                    siaqueue.os, "lstat", side_effect=replace_on_final_stat):
                with self.assertRaisesRegex(ValueError, "changed while"):
                    siaqueue._read_open_request(request, name)
            self.assertTrue(os.path.exists(request))

    def test_queue_lock_hardlink_and_path_replacement_are_refused(self):
        with tempfile.TemporaryDirectory() as state:
            queue_dir = siaqueue._ensure_queue_dir(state)
            lock = os.path.join(queue_dir, ".queue.lock")
            with open(lock, "wb"):
                pass
            os.chmod(lock, 0o600)
            alias = os.path.join(state, "lock-alias")
            os.link(lock, alias)
            with self.assertRaisesRegex(ValueError, "owned regular"):
                with siaqueue._queue_lock(queue_dir):
                    pass
            os.unlink(alias)

            real_flock = siaqueue.fcntl.flock
            replaced = False

            def replace_lock(descriptor, operation):
                nonlocal replaced
                if operation & siaqueue.fcntl.LOCK_EX and not replaced:
                    replaced = True
                    os.unlink(lock)
                    with open(lock, "wb"):
                        pass
                return real_flock(descriptor, operation)

            with mock.patch.object(
                    siaqueue.fcntl, "flock", side_effect=replace_lock):
                with self.assertRaisesRegex(ValueError, "lock changed"):
                    with siaqueue._queue_lock(queue_dir):
                        pass


class LegacyOrphanRecovery(unittest.TestCase):
    def test_corpus_scan_bounded_retries_remove_old_random_temps(self):
        with tempfile.TemporaryDirectory() as root:
            corpus = os.path.join(root, "corpus")
            event_dir = os.path.join(corpus, "events", "organ")
            os.makedirs(event_dir)
            with open(os.path.join(event_dir, "day.md"), "wb") as stream:
                stream.write(b"authoritative")
            for index in range(7):
                with open(os.path.join(
                        event_dir, f".day.md.legacy{index}.new"), "wb"):
                    pass
            with mock.patch.multiple(
                    sialib, CORPUS=corpus, MAX_SOURCE_SCAN_ENTRIES=3):
                for _attempt in range(8):
                    try:
                        entries = sialib._bounded_event_directory_snapshot(
                            event_dir, cleanup_legacy_atomic=True)
                    except RuntimeError:
                        continue
                    break
                else:
                    self.fail("bounded corpus orphan cleanup did not converge")
            self.assertEqual([entry["name"] for entry in entries], ["day.md"])
            self.assertEqual(os.listdir(event_dir), ["day.md"])

    def test_transaction_scan_bounded_retries_remove_old_random_temps(self):
        with tempfile.TemporaryDirectory() as directory:
            for index in range(7):
                with open(os.path.join(
                        directory,
                        f".journal.json.{index:032x}.new"), "wb"):
                    pass
            with mock.patch.object(
                    siatakes, "MAX_TRANSACTION_RECOVERY_BATCH", 3):
                for _attempt in range(8):
                    try:
                        pending = siatakes._transaction_pending(
                            directory, "grade transaction")
                    except ValueError as exc:
                        self.assertIn("directory-entry scan", str(exc))
                        continue
                    self.assertFalse(pending)
                    break
                else:
                    self.fail("bounded transaction orphan cleanup did not converge")
            self.assertEqual(os.listdir(directory), [])


class TouchTailRecovery(unittest.TestCase):
    @staticmethod
    def _touch_row(record_id, slug):
        return json.dumps({
            "id": record_id, "ts": 10, "src": "user-recall",
            "slugs": [slug]}, separators=(",", ":"),
            ensure_ascii=False).encode("utf-8") + b"\n"

    def test_torn_suffix_is_recorded_repaired_and_prefix_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            prefix = self._touch_row("old", "events/old")
            suffix = b'{"id":"torn"'
            with open(path, "wb") as stream:
                stream.write(prefix + suffix)

            self.assertTrue(siamind.queue_touches(
                ["events/new"], "user-recall", ts=11,
                queue_path=path, record_id="new"))
            with open(path, "rb") as stream:
                repaired = stream.read()
            self.assertTrue(repaired.startswith(prefix))
            self.assertNotIn(suffix, repaired)
            self.assertTrue(repaired.endswith(b"\n"))
            usage = siamind.touch_queue_usage(path)
            self.assertEqual(usage["refusal_count"], 1)
            self.assertEqual(usage["last_refusal"], "unterminated-suffix")
            self.assertEqual(siamind.touch_queue_usage(path), usage)
            health = {}
            sialib._record_touch_queue_health(health, usage)
            self.assertIn("touch_queue_tail_refusal", health)
            self.assertIn("unterminated-suffix",
                          health["touch_queue_tail_refusal"])

            refusal_path = os.path.join(
                root, siamind.TOUCH_QUEUE_REFUSAL_NAME)
            with open(refusal_path, encoding="utf-8") as stream:
                refusal = json.load(stream)
            last = refusal["last"]
            self.assertEqual(last["complete_offset"], len(prefix))
            self.assertEqual(
                last["suffix_sha256"], hashlib.sha256(suffix).hexdigest())
            self.assertEqual(
                last["generation"]["sha256"],
                hashlib.sha256(prefix + suffix).hexdigest())

            mind = {"nodes": {}, "edges": {}}
            self.assertEqual(
                siamind.drain_touch_queue(mind, now=12, queue_path=path), 2)
            self.assertEqual(set(mind["nodes"]),
                             {"events/old", "events/new"})
            self.assertTrue(siamind.queue_pin(
                "events/old", False, ts=13, queue_path=path))
            self.assertEqual(
                siamind.drain_touch_queue(mind, now=14, queue_path=path), 1)

    def test_touch_rmw_retries_every_fixed_publication_boundary_once(self):
        for boundary in FixedSlotPublication.BOUNDARIES:
            with self.subTest(boundary=boundary), \
                    tempfile.TemporaryDirectory() as root:
                path = os.path.join(root, "touches.jsonl")
                self.assertTrue(siamind.queue_touches(
                    ["events/old"], "user-recall", ts=10,
                    queue_path=path, record_id="old"))

                def stop(name):
                    if name == boundary:
                        raise SimulatedPowerLoss(name)

                with mock.patch.object(
                        siamind.siaqueue, "_publish_boundary",
                        side_effect=stop):
                    with self.assertRaises(SimulatedPowerLoss):
                        siamind.queue_touches(
                            ["events/new"], "user-recall", ts=11,
                            queue_path=path, record_id="new")
                retry_boundaries = []
                with mock.patch.object(
                        siamind.siaqueue, "_publish_boundary",
                        side_effect=retry_boundaries.append):
                    self.assertTrue(siamind.queue_touches(
                        ["events/new"], "user-recall", ts=11,
                        queue_path=path, record_id="new"))
                self.assertIn(
                    "target-directory-fsynced", retry_boundaries)
                mind = {"nodes": {}, "edges": {}}
                self.assertEqual(
                    siamind.drain_touch_queue(
                        mind, now=12, queue_path=path), 2)
                self.assertEqual(set(mind["nodes"]),
                                 {"events/old", "events/new"})

    def test_crash_after_refusal_before_repair_retries_idempotently(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            original = self._touch_row("old", "events/old") + b"partial"
            with open(path, "wb") as stream:
                stream.write(original)
            real_publish = siamind.siaqueue.fixed_atomic_publish

            def stop_queue(target, data, **kwargs):
                if os.path.abspath(target) == os.path.abspath(path):
                    raise SimulatedPowerLoss("before queue tail repair")
                return real_publish(target, data, **kwargs)

            with mock.patch.object(
                    siamind.siaqueue, "fixed_atomic_publish",
                    side_effect=stop_queue):
                with self.assertRaises(SimulatedPowerLoss):
                    siamind.touch_queue_usage(path)
            with open(path, "rb") as stream:
                self.assertEqual(stream.read(), original)

            usage = siamind.touch_queue_usage(path)
            self.assertEqual(usage["refusal_count"], 1)
            with open(path, "rb") as stream:
                self.assertEqual(
                    stream.read(), self._touch_row("old", "events/old"))

    def test_two_lane_interleaving_does_not_double_count_a_retry(self):
        with tempfile.TemporaryDirectory() as root:
            first = os.path.join(root, "touches.jsonl")
            second = os.path.join(root, "recovery.jsonl")
            for path, suffix in ((first, b"first"), (second, b"second")):
                with open(path, "wb") as stream:
                    stream.write(self._touch_row("old", "events/old")
                                 + suffix)
            real_publish = siamind.siaqueue.fixed_atomic_publish

            def stop_first(target, data, **kwargs):
                if os.path.abspath(target) == os.path.abspath(first):
                    raise SimulatedPowerLoss("first lane remains torn")
                return real_publish(target, data, **kwargs)

            with mock.patch.object(
                    siamind.siaqueue, "fixed_atomic_publish",
                    side_effect=stop_first):
                with self.assertRaises(SimulatedPowerLoss):
                    siamind.touch_queue_usage(first)
            self.assertEqual(
                siamind.touch_queue_usage(second)["refusal_count"], 2)
            self.assertEqual(
                siamind.touch_queue_usage(first)["refusal_count"], 2)

    def test_complete_malformed_record_is_retained_as_claim_debt(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            raw = self._touch_row("old", "events/old") + b"{broken}\n"
            with open(path, "wb") as stream:
                stream.write(raw)
            with self.assertRaisesRegex(ValueError, "malformed JSON"):
                siamind.drain_touch_queue(
                    {"nodes": {}, "edges": {}}, now=12,
                    queue_path=path)
            with open(path + ".draining", "rb") as stream:
                self.assertEqual(stream.read(), raw)
            self.assertFalse(os.path.exists(os.path.join(
                root, siamind.TOUCH_QUEUE_REFUSAL_NAME)))

    def test_unicode_line_separator_is_data_not_a_physical_boundary(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            row = {
                "id": "one\u2028identity", "ts": 10,
                "src": "user-recall", "slugs": ["events/one"]}
            with open(path, "wb") as stream:
                stream.write((json.dumps(
                    row, ensure_ascii=False, separators=(",", ":"))
                    + "\n").encode("utf-8"))
            mind = {"nodes": {}, "edges": {}}
            self.assertEqual(
                siamind.drain_touch_queue(mind, now=12, queue_path=path), 1)
            self.assertIn("events/one", mind["nodes"])

    def test_generation_change_after_refusal_never_truncates_replacement(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            old = self._touch_row("old", "events/old") + b"partial"
            replacement = self._touch_row("new", "events/new")
            with open(path, "wb") as stream:
                stream.write(old)
            real_record = siamind._record_touch_tail_refusal_locked

            def replace_after_record(*args, **kwargs):
                value = real_record(*args, **kwargs)
                swap = path + ".swap"
                with open(swap, "wb") as stream:
                    stream.write(replacement)
                os.replace(swap, path)
                return value

            with mock.patch.object(
                    siamind, "_record_touch_tail_refusal_locked",
                    side_effect=replace_after_record):
                with self.assertRaisesRegex(ValueError, "changed before"):
                    siamind.touch_queue_usage(path)
            with open(path, "rb") as stream:
                self.assertEqual(stream.read(), replacement)

    def test_record_cap_is_aggregate_across_active_and_draining(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            row = self._touch_row("one", "events/one")
            with open(path, "wb") as stream:
                stream.write(row)
            with open(path + ".draining", "wb") as stream:
                stream.write(row.replace(b'"one"', b'"two"', 1))
            with mock.patch.object(siamind, "MAX_TOUCH_QUEUE_RECORDS", 1):
                with self.assertRaisesRegex(ValueError, "record limit"):
                    siamind.touch_queue_usage(path)
                self.assertFalse(siamind.queue_touches(
                    ["events/three"], "user-recall", ts=12,
                    queue_path=path, record_id="three"))

    def test_touch_lock_hardlink_and_path_replacement_are_refused(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "touches.jsonl")
            lock = path + ".lock"
            with open(lock, "wb"):
                pass
            alias = os.path.join(root, "lock-alias")
            os.link(lock, alias)
            with self.assertRaisesRegex(ValueError, "owned regular"):
                with siamind._touch_queue_lock(path):
                    pass
            os.unlink(alias)

            real_flock = siamind.fcntl.flock
            replaced = False

            def replace_lock(descriptor, operation):
                nonlocal replaced
                if operation & siamind.fcntl.LOCK_EX and not replaced:
                    replaced = True
                    os.unlink(lock)
                    with open(lock, "wb"):
                        pass
                return real_flock(descriptor, operation)

            with mock.patch.object(
                    siamind.fcntl, "flock", side_effect=replace_lock):
                with self.assertRaisesRegex(ValueError, "lock changed"):
                    with siamind._touch_queue_lock(path):
                        pass


if __name__ == "__main__":
    unittest.main()
