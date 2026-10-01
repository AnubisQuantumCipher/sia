"""Actual resident-v3 continuation beneath a retained notification fence.

The selected native notification collector is genuinely captured and ACKed
first. Actual delivery-epoch preparation then precedes the actual notification
marker operation. That marker is a real retained acquisition fence; this
fixture does NOT erase an acknowledged cursor or claim that a fresh
first-baseline callback was triggered inside the resident successor capture.

Positive paths execute the real capture-only predecessor/epoch/storage APIs,
native collector, WAL, generation publication and ACK. The composed resident
fixture supplies controlled external Git/index observations only. No source
success, generation, ACK, journal record or readiness result is invented.
These are local orchestration contracts, not live deployment, complete machine
history, source truth, output receipt, biological cognition, JACKAL assurance
or a held-out retrieval win. Root alone executes tests sequentially.
"""

import contextlib
import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import test_controller_delivery_epoch as epoch_tests
from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_resident_v3 as resident_tests


class _CaptureDeath(KeyboardInterrupt):
    pass


class ControllerSourceResidentV3Fenced(unittest.TestCase):
    def setUp(self):
        self.resident = resident_tests.ControllerSourceResidentV3(methodName="runTest")
        self.addCleanup(self.resident.doCleanups)
        # The composed fixture checks both missing APIs before source setup.
        self.resident.setUp()
        self.capture = self.resident.capture
        self.source = self.resident.source
        self.epoch = self.resident.epoch
        self.ack = self.resident.rollover.ack
        self.publication = self.resident.rollover.publication

    @contextlib.contextmanager
    def fenced_parent(self):
        with self.capture.notify_completed() as (
                case, retained, committed, status, generation, root):
            self.assertIsNotNone(retained["notification_baseline_attempt"])
            key = case.lib.NOTIFY_BASELINE_ATTEMPT_KEY
            self.assertNotIn(key, case.live.memo)
            adopted = self.epoch.prepare(case, retained, committed, status)
            before = copy.deepcopy(case.live.memo)
            cursors = ack_tests._path_image(Path(case.lib.CURSORS_PATH))
            # This is the real durable marker primitive, after actual source
            # ACK and adoption. No memo filtering or cursor rewriting occurs.
            with self.epoch.idle.source_owner(case), case.lib.brainstem_owner(), \
                    case.lib.corpus_owner():
                marker = copy.deepcopy(case.lib._mark_notify_baseline_attempt(case.live.memo))
            self.assertEqual(case.lib.load_memo(), {**before, key: marker})
            self.assertEqual(case.live.memo, case.lib.load_memo())
            self.assertEqual(ack_tests._path_image(Path(case.lib.CURSORS_PATH)), cursors)
            yield SimpleNamespace(case=case, retained=retained, committed=committed,
                status=status, generation=generation, root=root, adopted=adopted,
                marker=marker, nonidle=False, notifications=True,
                owner=case.source.lib.__dict__, batch=None, request=None,
                cursor_image=cursors, notification_key=key)

    @contextlib.contextmanager
    def fenced_calls(self, f, trace, *, recovery=False):
        """Observe full real requests; forbid current-readiness substitution."""
        owner = trace.owner
        trace.capturable_reads, trace.capturable_retains = [], []
        trace.capturable_recoveries, trace.native_collectors = [], []
        read = self.ack.read_capturable_predecessor
        retain = self.publication.retain_capturable_successor
        recover = self.publication.recover_capturable_successor
        collector = self.source._collector_result
        key = f.notification_key
        marker_raw = self.source.native_bytes(owner.__dict__, f.marker)
        marker_pin = self.source.native_sha(owner.__dict__, f.marker)

        def actual_fenced_request(actual_owner, kwargs):
            self.assertIs(actual_owner, owner.__dict__)
            self.assertEqual(trace.active_scopes, ["brainstem", "corpus"])
            memo = kwargs["memo"]
            durable = owner.load_memo()
            raw = self.source.native_bytes(actual_owner, memo)
            self.assertEqual(raw, self.source.native_bytes(actual_owner, durable))
            self.assertEqual(memo["controller_source_committed"], f.committed)
            self.assertEqual(kwargs["admitted_status"], f.status)
            self.assertEqual(self.source.native_bytes(actual_owner, memo[key]), marker_raw)
            self.assertEqual(self.source.native_bytes(
                actual_owner, kwargs["notification_baseline_attempt"]), marker_raw)
            self.assertEqual(kwargs["expected_notification_baseline_attempt_sha256"], marker_pin)
            self.assertEqual(memo[epoch_tests.MARKER_KEY]["adoption_sha256"],
                             f.adopted["expected_adoption_sha256"])
            return raw

        def unchanged(actual_owner, memo, raw):
            self.assertEqual(self.source.native_bytes(actual_owner, memo), raw)
            self.assertEqual(self.source.native_bytes(actual_owner, owner.load_memo()), raw)

        def read_parent(actual_owner, **kwargs):
            before = actual_fenced_request(actual_owner, kwargs)
            result = read(actual_owner, **kwargs)
            unchanged(actual_owner, kwargs["memo"], before)
            self.assertEqual(result["schema"], "sia-controller-source-capturable-predecessor-v1")
            self.assertEqual(result["status"], "capturable-not-ready")
            self.assertEqual(result["batch"], f.retained)
            self.assertEqual(result["committed"], f.committed)
            self.assertEqual(result["notification_baseline_attempt"], f.marker)
            self.assertEqual(result["non_claims"], list(self.ack.CAPTURE_NON_CLAIMS))
            trace.capturable_reads.append((before, copy.deepcopy(result)))
            return result

        def retain_batch(actual_owner, **kwargs):
            if recovery:
                raise AssertionError("fenced fixed-WAL retry retained another source capture")
            before = actual_fenced_request(actual_owner, kwargs)
            self.assertEqual(kwargs["batch"], f.batch)
            result = retain(actual_owner, **kwargs)
            self.assertIsNone(result)
            unchanged(actual_owner, kwargs["memo"], before)
            trace.capturable_retains.append(Path(owner.CONTROLLER_SOURCE_BATCH_PATH).read_bytes())
            return result

        def recover_batch(actual_owner, **kwargs):
            before = actual_fenced_request(actual_owner, kwargs)
            result = recover(actual_owner, **kwargs)
            self.assertIs(type(result), bool)
            if result:
                self.assertNotIn("controller_source_committed", kwargs["memo"])
                self.assertIn("controller_source_pending", kwargs["memo"])
                self.assertEqual(kwargs["memo"][key], f.marker)
                self.assertEqual(kwargs["memo"], owner.load_memo())
            else:
                unchanged(actual_owner, kwargs["memo"], before)
            trace.capturable_recoveries.append((before, result,
                self.source.native_bytes(actual_owner, kwargs["memo"])))
            return result

        def native_collect(*args, **kwargs):
            if recovery:
                raise AssertionError("fenced fixed-WAL retry invoked a native collector")
            self.assertEqual(trace.active_scopes, ["brainstem", "corpus"])
            selected = args[2]
            self.assertEqual(selected["collector"], "sense_notify")
            result = collector(*args, **kwargs)
            trace.native_collectors.append(copy.deepcopy(selected))
            return result

        def strict_guard(actual, name):
            def call(*args, **kwargs):
                # Inspect actual durable state, not the supplied memo: a
                # caller must not evade this guard by removing the fence.
                durable = owner.load_memo()
                if "controller_source_committed" in durable and key in durable:
                    raise AssertionError("fenced predecessor reached strict " + name)
                return actual(*args, **kwargs)
            return call

        forbidden = self.resident.forbidden("fenced path used ordinary preparation/storage/readiness")
        with contextlib.ExitStack() as stack:
            for module, name, replacement in (
                    (self.ack, "read_capturable_predecessor", read_parent),
                    (self.publication, "retain_capturable_successor", retain_batch),
                    (self.publication, "recover_capturable_successor", recover_batch),
                    (self.source, "_collector_result", native_collect),
                    (self.ack, "read_completed", strict_guard(self.ack.read_completed, "completed reader")),
                    (owner, "_read_committed_controller_source_batch", strict_guard(
                        owner._read_committed_controller_source_batch, "owner completed reader")),
                    (owner, "_acknowledge_controller_source_batch", strict_guard(
                        owner._acknowledge_controller_source_batch, "completed ACK")),
                    (self.capture.epoch_module, "prepare_epoch", forbidden),
                    (self.publication, "retain_successor", forbidden),
                    (self.publication, "recover_successor", forbidden),
                    (owner, "memory_readiness", forbidden)):
                stack.enter_context(mock.patch.object(module, name, replacement))
            yield
        forbidden.assert_not_called()

    def assert_fenced_completion(self, f, status, trace):
        durable = self.resident.assert_completed(f, status, trace)
        self.assertIsNone(f.batch["event_closure"])
        self.assertEqual(f.gist_plan["target_versions"], [])
        receipt = f.case.memo_before_ack["controller_source_effects_committed"]
        self.assertIsNone(receipt["corpus_generation"])
        self.assertIsNone(receipt["sync_generation"])
        self.assertEqual(receipt["target_manifest"], [])
        self.assertEqual(trace.effects[-1]["trace"], [
            "graph", "pending", "live-stage", "live-publish", "receipt"])
        self.assertNotIn(f.notification_key, durable)
        self.assertEqual(f.batch["notification_baseline_attempt"], f.marker)
        view = f.batch["delivery_input"]["epoch_view"]
        self.assertEqual(view["schema"], "sia-controller-delivery-epoch-capture-view-v1")
        self.assertEqual(view["status"], "held-capturable-not-ready")
        self.assertEqual(view["notification_baseline_attempt"], f.marker)
        self.assertEqual(trace.prepares, [])
        self.assertNotIn("ack-completed", trace.stages)
        self.assertTrue(trace.capturable_reads)
        self.assertTrue(any(result for _, result, _ in trace.capturable_recoveries))
        return durable

    def test_retained_notification_fence_survives_actual_v3_wal_death_and_no_acquisition_retry(self):
        with self.fenced_parent() as f:
            adoption_files = epoch_tests._tree(f.root)
            parent_archive = ack_tests._path_image(f.case.archive_path(f.retained))
            original_adoption = copy.deepcopy(f.adopted)
            with self.resident.instrument(f, crash_wal=True) as first, \
                    self.fenced_calls(f, first), self.assertRaises(resident_tests._WalDeath):
                first.invoke(original_adoption["expected_adoption_sha256"])
            retained_raw = Path(f.case.producer.source_path).read_bytes()
            retained_batch = copy.deepcopy(f.batch)
            reserved = copy.deepcopy(f.case.live.memo)
            self.assertEqual(first.capturable_retains, [retained_raw])
            self.assertEqual(first.captures, [f.batch])
            self.assertEqual(first.native_collectors, f.retained["epoch"]["source_catalog"]["sources"])
            self.assertEqual(first.effects, [])
            self.assertEqual(first.acknowledgments, [])
            self.assertEqual(reserved[f.notification_key], f.marker)
            self.assertEqual(reserved["controller_source_committed"], f.committed)
            self.assertNotIn("controller_source_pending", reserved)
            self.assertEqual(ack_tests._path_image(Path(f.case.lib.CURSORS_PATH)), f.cursor_image)
            with self.resident.instrument(f, recovery=True) as retry, self.fenced_calls(f, retry, recovery=True):
                status = retry.invoke(original_adoption["expected_adoption_sha256"])
            durable = self.assert_fenced_completion(f, status, retry)
            self.assertEqual(f.batch, retained_batch)
            self.assertEqual(f.case.archive_path(f.batch).read_bytes(), retained_raw)
            self.assertEqual(durable["pulse_seq"], reserved["pulse_seq"])
            self.assertEqual(f.adopted, original_adoption)
            self.assertEqual(epoch_tests._tree(f.root), adoption_files)
            self.assertEqual(ack_tests._path_image(f.case.archive_path(f.retained)), parent_archive)
            self.assertEqual(retry.captures, [])
            self.assertEqual(retry.retained, [])
            self.assertEqual(retry.capturable_retains, [])
            self.assertEqual(retry.native_collectors, [])
            self.assertNotIn("reserve", retry.stages)
            self.assertNotIn("clock", retry.stages)

    def test_fenced_capture_death_before_wal_releases_holds_and_retries_actual_capture(self):
        with self.fenced_parent() as f:
            adoption_files = epoch_tests._tree(f.root)
            parent_archive = ack_tests._path_image(f.case.archive_path(f.retained))
            original_adoption = copy.deepcopy(f.adopted)
            before = copy.deepcopy(f.case.live.memo)
            descriptors = self.capture.fd_fixture.fds()
            death = _CaptureDeath("actual delivery wrapper completed before any source WAL")

            def cut_after_actual_wrapper():
                raise death

            with self.resident.instrument(f) as first, self.fenced_calls(f, first), \
                    self.capture.lifetime(f, at_build=cut_after_actual_wrapper) as lifetime, \
                    self.assertRaises(_CaptureDeath) as caught:
                first.invoke(original_adoption["expected_adoption_sha256"])
            self.assertIs(caught.exception, death)
            self.assertEqual(self.capture.fd_fixture.fds(), descriptors)
            self.assertEqual(first.scope_events,
                             ["brainstem-enter", "corpus-enter", "corpus-exit", "brainstem-exit"])
            self.assertEqual(first.active_scopes, [])
            self.assertEqual(first.native_collectors, f.retained["epoch"]["source_catalog"]["sources"])
            self.assertTrue(lifetime.collected)
            self.assertTrue(lifetime.journals)
            self.assertIn("wrapper", lifetime.steps)
            self.assertFalse(lifetime.swept)
            self.assertIsNone(f.batch)
            self.assertFalse(Path(f.case.producer.source_path).exists())
            self.assertEqual(first.captures, [])
            self.assertEqual(first.capturable_retains, [])
            self.assertEqual(first.effects, [])
            self.assertEqual(first.acknowledgments, [])
            reserved = copy.deepcopy(f.case.live.memo)
            self.assertEqual(reserved, {**before, "pulse_seq": reserved["pulse_seq"]})
            self.assertGreater(reserved["pulse_seq"], before["pulse_seq"])
            self.assertEqual(reserved[f.notification_key], f.marker)
            self.assertEqual(reserved["controller_source_committed"], f.committed)
            self.assertNotIn("controller_source_pending", reserved)
            self.assertEqual(ack_tests._path_image(Path(f.case.lib.CURSORS_PATH)), f.cursor_image)
            self.assertEqual(epoch_tests._tree(f.root), adoption_files)
            self.assertEqual(ack_tests._path_image(f.case.archive_path(f.retained)), parent_archive)

            # A completed predecessor with no WAL must acquire a genuine new
            # successor. The durable fence selects capture-only admission;
            # it cannot be hidden merely to reuse ordinary preparation.
            with self.resident.instrument(f) as retry, self.fenced_calls(f, retry):
                status = retry.invoke(original_adoption["expected_adoption_sha256"])
            durable = self.assert_fenced_completion(f, status, retry)
            self.assertEqual(retry.captures, [f.batch])
            self.assertEqual(retry.native_collectors, f.retained["epoch"]["source_catalog"]["sources"])
            self.assertEqual(retry.capturable_retains, [f.case.archive_path(f.batch).read_bytes()])
            self.assertIn("reserve", retry.stages)
            self.assertIn("clock", retry.stages)
            self.assertGreater(durable["pulse_seq"], reserved["pulse_seq"])
            self.assertEqual(f.adopted, original_adoption)
            self.assertEqual(epoch_tests._tree(f.root), adoption_files)
            self.assertEqual(ack_tests._path_image(f.case.archive_path(f.retained)), parent_archive)


if __name__ == "__main__":
    unittest.main()
