"""Private RED contract for fenced successor WAL retention and adoption.

Root alone runs this module, sequentially. The fixture completes the real
source/effects/archive ACK transaction, runs the real recurring dispatcher
until its clock boundary AFTER sequence reservation, creates the real
notification acquisition marker, and captures an admitted successor through
the existing source front door. It does not fabricate source-v3 availability.

These local storage checks do not establish complete history, notification
delivery, a writer lease, source truth, biological cognition or a held-out
retrieval win. They preserve the strict legacy entrypoints. In particular a
crash after pending-memo replacement is a pending transaction, not permission
to recover using a manufactured old completed memo.
"""

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import contextlib
import copy
import hashlib
import importlib
import inspect
import os
from pathlib import Path
import stat
import unittest
from unittest import mock

from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_capture as capture_tests
from tests import test_controller_source_rollover_storage as rollover_tests
from tests import test_event_page_plan as page_tests


RETAIN_PARAMETERS = (
    "owner", "memo", "admitted_status", "retained_batch", "committed",
    "batch", "expected_batch_sha256", "seq",
    "notification_baseline_attempt",
    "expected_notification_baseline_attempt_sha256",
)
RECOVER_PARAMETERS = (
    "owner", "memo", "admitted_status", "retained_batch", "committed", "seq",
    "notification_baseline_attempt",
    "expected_notification_baseline_attempt_sha256",
)
OTHER_PENDING_KEYS = (
    "controller_source_pending", "controller_source_live_pending",
    "pulse_status_effects_pending", "controller_source_effects_pending",
    "controller_source_effects_committed", "live_loop_pending",
    "source_replay_pending", "pulse_publication", "dream_publication",
    "consolidation_pending", "brainstem_failure_pending",
)
REFUSALS = (ValueError, RuntimeError, OSError)


class _ReservedAtClock(BaseException):
    pass


class SourceCapturableSuccessorStorage(unittest.TestCase):
    def setUp(self):
        self.publication = importlib.import_module("siasourcepublication")
        self.source = importlib.import_module("siasourcebatch")
        self.ack = importlib.import_module("siasourceack")
        self.runner = importlib.import_module("siacontrollersourcerunner")
        self.retain_operation = getattr(
            self.publication, "retain_capturable_successor", None)
        self.recover_operation = getattr(
            self.publication, "recover_capturable_successor", None)
        self.assertTrue(callable(self.retain_operation),
                        "missing fenced successor retention")
        self.assertTrue(callable(self.recover_operation),
                        "missing fenced successor recovery")
        self.fixture = rollover_tests.ControllerSourceRolloverStorage(
            methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    @contextlib.contextmanager
    def prepared(self):
        with self.fixture.completed() as (
                case, retained, committed, admitted_status):
            owner = case.lib.__dict__
            predecessor_memo = copy.deepcopy(case.live.memo)
            predecessor_generation = ack_tests._path_image(
                case.live.paths["LIVE_STATE_PATH"])
            written = []
            original_write = case.lib._write_memo

            def reserve_write(value):
                result = original_write(value)
                written.append(copy.deepcopy(value))
                return result

            def reserved_clock():
                self.assertTrue(written)
                durable = case.live._read("MEMO_PATH")
                self.assertEqual(durable, written[-1])
                self.assertGreater(durable["pulse_seq"],
                                   predecessor_memo["pulse_seq"])
                raise _ReservedAtClock()

            operation = mock.Mock(side_effect=AssertionError(
                "successor reservation invoked initial capture"))
            with mock.patch.object(case.lib, "_write_memo",
                                   side_effect=reserve_write), \
                    self.assertRaises(_ReservedAtClock):
                self.runner.run_v2(owner, operation=operation,
                                   clock=reserved_clock)
            operation.assert_not_called()
            durable = case.live._read("MEMO_PATH")
            case.live.memo.clear()
            case.live.memo.update(copy.deepcopy(durable))
            expected_reserved = copy.deepcopy(predecessor_memo)
            expected_reserved["pulse_seq"] = durable["pulse_seq"]
            self.assertEqual(durable, expected_reserved)
            self.assertEqual(ack_tests._path_image(
                case.live.paths["LIVE_STATE_PATH"]), predecessor_generation)
            self.assertEqual(case.live._read("STATUS_PATH"), admitted_status)

            marker = copy.deepcopy(case.lib._mark_notify_baseline_attempt(
                case.live.memo))
            marker_sha = self.source.native_sha(owner, marker)
            request = self.fixture.build_request(case, retained, committed)
            batch = self.fixture.capture(case, retained, committed, request)
            self.assertEqual(batch["notification_baseline_attempt"], marker)
            self.assertEqual(case.live._read("MEMO_PATH"), case.live.memo)
            self.assertEqual(case.live.memo["controller_source_committed"],
                             committed)
            self.assertEqual(case.live.memo["ready"], predecessor_memo["ready"])
            self.assertFalse(Path(case.producer.source_path).exists())
            arguments = {
                "memo": case.live.memo,
                "admitted_status": admitted_status,
                "retained_batch": retained,
                "committed": committed,
                "seq": durable["pulse_seq"],
                "notification_baseline_attempt": marker,
                "expected_notification_baseline_attempt_sha256": marker_sha,
            }
            view = self.ack.read_capturable_predecessor(
                owner, memo=case.live.memo, admitted_status=admitted_status,
                committed=committed, notification_baseline_attempt=marker,
                expected_notification_baseline_attempt_sha256=marker_sha)
            self.assertEqual(view["status"], "capturable-not-ready")
            self.assertEqual(view["batch"], retained)
            self.assertEqual(view["committed"], committed)
            yield case, arguments, batch

    def retain(self, case, arguments, batch, **changes):
        selected = dict(arguments, batch=batch,
                        expected_batch_sha256=batch["batch_sha256"])
        selected.update(changes)
        return self.retain_operation(case.lib.__dict__, **selected)

    def recover(self, case, arguments, **changes):
        selected = dict(arguments)
        selected.update(changes)
        return self.recover_operation(case.lib.__dict__, **selected)

    def images(self, case):
        result = case.images()
        result["effects-archive"] = ack_tests._path_image(
            case.effects_archive_path())
        result["effects-archive-dir"] = ack_tests._path_image(
            case.effects_archive_dir)
        return result

    @contextlib.contextmanager
    def no_collect(self, case):
        """No source/epoch acquisition or unrelated publication after setup."""
        forbidden = mock.Mock(side_effect=AssertionError(
            "successor storage crossed an acquisition/unrelated effect"))
        with contextlib.ExitStack() as stack:
            for module in (case.lib, case.source.lib):
                for name in (
                        "sense_custom", "sense_aegis", "iso", "utcnow",
                        "_mark_notify_baseline_attempt",
                        "_clear_notify_baseline_attempt",
                        "_recover_notify_baseline_attempt", "_write_memo",
                        "save_cursors", "_commit_sense_cursors",
                        "_discard_pending_cursor_renames",
                        "_settle_source_refusals", "_settle_source_record_refusals",
                        "_settle_source_entry_refusals", "export_status",
                        "export_graph", "_publish_event_page_batch_closure",
                        "_stage_live_generation", "_publish_staged_live_generation",
                        "brain_sync", "gbrain", "gbrain_call"):
                    if hasattr(module, name):
                        stack.enter_context(mock.patch.object(
                            module, name, forbidden))
            for module, name in (
                    (self.fixture.epoch, "build_successor"),
                    (self.source, "capture_successor"),
                    (self.source, "capture")):
                stack.enter_context(mock.patch.object(module, name, forbidden))
            yield
        forbidden.assert_not_called()

    def assert_unchanged_refusal(self, case, callback):
        before = self.images(case)
        memo_before = copy.deepcopy(case.live.memo)
        with self.no_collect(case), case.forbid_ack_effects(), \
                self.assertRaises(REFUSALS):
            callback()
        self.assertEqual(self.images(case), before)
        self.assertEqual(case.live.memo, memo_before)

    def expected_pending(self, arguments, batch):
        raw = capture_tests.canonical(batch)
        receipt = {
            "schema": "sia-controller-source-pending-v1",
            "epoch_id": batch["epoch"]["epoch_id"],
            "batch_id": batch["batch_id"],
            "epoch_sha256": batch["epoch_sha256"],
            "batch_sha256": batch["batch_sha256"],
            "batch_wire_sha256": hashlib.sha256(raw).hexdigest(),
            "batch_bytes": len(raw),
            "parent_batch_sha256": arguments["retained_batch"]["batch_sha256"],
        }
        result = copy.deepcopy(arguments["memo"])
        result.pop("controller_source_committed")
        result.pop("ready")
        result["controller_source_pending"] = receipt
        return result

    def test_closed_additive_signatures(self):
        for operation, names in (
                (self.retain_operation, RETAIN_PARAMETERS),
                (self.recover_operation, RECOVER_PARAMETERS)):
            with self.subTest(operation=operation.__name__):
                parameters = inspect.signature(operation).parameters
                self.assertEqual(tuple(parameters), names)
                self.assertEqual(parameters["owner"].kind,
                                 inspect.Parameter.POSITIONAL_OR_KEYWORD)
                for name in names[1:]:
                    self.assertEqual(parameters[name].kind,
                                     inspect.Parameter.KEYWORD_ONLY)
                    self.assertIs(parameters[name].default,
                                  inspect.Parameter.empty)

    def test_real_reserved_fence_wal_then_exact_pending_adoption(self):
        with self.prepared() as (case, arguments, batch):
            before = self.images(case)
            frozen_arguments = copy.deepcopy(arguments)
            expected = self.expected_pending(arguments, batch)
            with self.no_collect(case):
                self.assertIsNone(self.retain(case, arguments, batch))
            retained = self.images(case)
            for name in before:
                if name != "source":
                    self.assertEqual(retained[name], before[name], name)
            self.assertEqual(arguments, frozen_arguments)
            self.assertEqual(Path(case.producer.source_path).read_bytes(),
                             capture_tests.canonical(batch))
            with self.no_collect(case):
                self.assertIsNone(self.retain(case, arguments, batch))
            self.assertEqual(self.images(case), retained)

            fresh = case.lib.load_memo()
            with self.no_collect(case):
                self.assertIs(self.recover(case, arguments, memo=fresh), True)
            self.assertEqual(fresh, expected)
            self.assertEqual(case.live._read("MEMO_PATH"), expected)
            self.assertEqual(arguments, frozen_arguments)
            after = self.images(case)
            for name in retained:
                if name != "memo":
                    self.assertEqual(after[name], retained[name], name)
            self.assertEqual(fresh[case.lib.NOTIFY_BASELINE_ATTEMPT_KEY],
                             arguments["notification_baseline_attempt"])
            pending = self.publication.read_pending(case.lib.__dict__, memo=fresh)
            self.assertEqual(pending["status"], "pending")
            self.assertEqual(pending["batch"], batch)
            self.assertEqual(pending["receipt"], expected["controller_source_pending"])

    def test_absent_fixed_wal_returns_false_without_effect(self):
        with self.prepared() as (case, arguments, _batch):
            before = self.images(case)
            frozen = copy.deepcopy(arguments)
            with self.no_collect(case), case.forbid_ack_effects():
                self.assertIs(self.recover(case, arguments), False)
            self.assertEqual(self.images(case), before)
            self.assertEqual(arguments, frozen)

    def test_legacy_completed_entrypoints_still_refuse_fence(self):
        with self.prepared() as (case, arguments, batch):
            callbacks = (
                lambda: self.ack.read_completed(
                    case.lib.__dict__, memo=arguments["memo"],
                    admitted_status=arguments["admitted_status"]),
                lambda: self.publication.retain_successor(
                    case.lib.__dict__, memo=arguments["memo"],
                    retained_batch=arguments["retained_batch"],
                    committed=arguments["committed"], batch=batch,
                    expected_batch_sha256=batch["batch_sha256"],
                    seq=arguments["seq"]),
                lambda: self.publication.recover_successor(
                    case.lib.__dict__, memo=arguments["memo"],
                    retained_batch=arguments["retained_batch"],
                    committed=arguments["committed"], seq=arguments["seq"]),
            )
            for callback in callbacks:
                self.assert_unchanged_refusal(case, callback)

    def test_explicit_marker_and_digest_are_required_not_inferred(self):
        with self.prepared() as (case, arguments, batch):
            for operation, full in (
                    (self.retain_operation, dict(arguments, batch=batch,
                        expected_batch_sha256=batch["batch_sha256"])),
                    (self.recover_operation, dict(arguments))):
                for name in ("notification_baseline_attempt",
                             "expected_notification_baseline_attempt_sha256"):
                    missing = dict(full)
                    missing.pop(name)
                    before = self.images(case)
                    with self.no_collect(case), case.forbid_ack_effects(), \
                            self.assertRaises(TypeError):
                        operation(case.lib.__dict__, **missing)
                    self.assertEqual(self.images(case), before)
                    for bad in (None, "not-an-admitted-pin"):
                        changed = dict(full, **{name: bad})
                        self.assert_unchanged_refusal(case, lambda: operation(
                            case.lib.__dict__, **changed))

    def test_wrong_explicit_batch_and_valid_but_different_marker_refuse(self):
        with self.prepared() as (case, arguments, batch):
            self.assert_unchanged_refusal(case, lambda: self.retain(
                case, arguments, batch,
                expected_batch_sha256=arguments["retained_batch"]["batch_sha256"]))
            different = copy.deepcopy(arguments["notification_baseline_attempt"])
            different["started_at"] = arguments["admitted_status"]["ts"]
            self.assertNotEqual(different, arguments["notification_baseline_attempt"])
            self.assertIsNotNone(case.lib._pending_notify_baseline_attempt({
                case.lib.NOTIFY_BASELINE_ATTEMPT_KEY: different}))
            changes = {
                "notification_baseline_attempt": different,
                "expected_notification_baseline_attempt_sha256":
                    self.source.native_sha(case.lib.__dict__, different),
            }
            self.assert_unchanged_refusal(case, lambda: self.retain(
                case, arguments, batch, **changes))
            self.assert_unchanged_refusal(case, lambda: self.recover(
                case, arguments, **changes))
            wrong_digest = arguments["retained_batch"]["batch_sha256"]
            self.assertNotEqual(wrong_digest,
                                arguments["expected_notification_baseline_attempt_sha256"])
            self.assert_unchanged_refusal(case, lambda: self.retain(
                case, arguments, batch,
                expected_notification_baseline_attempt_sha256=wrong_digest))
            self.assert_unchanged_refusal(case, lambda: self.recover(
                case, arguments,
                expected_notification_baseline_attempt_sha256=wrong_digest))

    def test_batch_cannot_silently_drop_the_actual_acquisition_fence(self):
        with self.prepared() as (case, arguments, batch):
            unfenced = copy.deepcopy(batch)
            unfenced["notification_baseline_attempt"] = None
            unfenced["batch_sha256"] = capture_tests.own(unfenced, "batch_sha256")
            self.source.validate_batch(case.lib.__dict__, unfenced,
                                       unfenced["batch_sha256"])
            self.assert_unchanged_refusal(case, lambda: self.retain(
                case, arguments, unfenced))
            fixed = Path(case.producer.source_path)
            fixed.write_bytes(capture_tests.canonical(unfenced))
            fixed.chmod(0o600)
            self.assert_unchanged_refusal(case, lambda: self.recover(
                case, arguments))

    def test_actual_completed_status_and_sequence_joins_are_required(self):
        with self.prepared() as (case, arguments, batch):
            bad_commit = copy.deepcopy(arguments["committed"])
            bad_commit["source_batch_sha256"] = batch["batch_sha256"]
            for changes in (
                    {"admitted_status": None},
                    {"committed": bad_commit},
                    {"seq": arguments["admitted_status"]["pulse_seq"]},
                    {"retained_batch": batch}):
                self.assert_unchanged_refusal(case, lambda: self.retain(
                    case, arguments, batch, **changes))
                self.assert_unchanged_refusal(case, lambda: self.recover(
                    case, arguments, **changes))

    def test_other_pending_membership_and_none_marker_refuse(self):
        with self.prepared() as (case, arguments, batch):
            original = copy.deepcopy(arguments["memo"])
            for key in OTHER_PENDING_KEYS:
                with self.subTest(key=key):
                    changed = copy.deepcopy(original)
                    changed[key] = None
                    case.lib._write_memo(changed)
                    arguments["memo"].clear()
                    arguments["memo"].update(changed)
                    self.assert_unchanged_refusal(case, lambda: self.retain(
                        case, arguments, batch))
                    self.assert_unchanged_refusal(case, lambda: self.recover(
                        case, arguments))
            changed = copy.deepcopy(original)
            changed.pop(case.lib.NOTIFY_BASELINE_ATTEMPT_KEY)
            case.lib._write_memo(changed)
            arguments["memo"].clear()
            arguments["memo"].update(changed)
            self.assert_unchanged_refusal(case, lambda: self.retain(
                case, arguments, batch))
            self.assert_unchanged_refusal(case, lambda: self.recover(case, arguments))
            changed = copy.deepcopy(original)
            changed[case.lib.NOTIFY_BASELINE_ATTEMPT_KEY] = None
            case.lib._write_memo(changed)
            arguments["memo"].clear()
            arguments["memo"].update(changed)
            self.assert_unchanged_refusal(case, lambda: self.retain(
                case, arguments, batch))
            self.assert_unchanged_refusal(case, lambda: self.recover(case, arguments))

    def test_complete_request_and_prospective_memo_bounded_before_wal(self):
        with self.prepared() as (case, arguments, batch):
            # A batch can fit while the complete represented storage request
            # does not. This is a wire-capacity check, not a heap measurement.
            with mock.patch.object(case.lib, "MAX_STATE_JSON_BYTES",
                                   len(capture_tests.canonical(batch))):
                self.assert_unchanged_refusal(case, lambda: self.retain(
                    case, arguments, batch))
            pending = self.expected_pending(arguments, batch)
            current_bytes = case.lib._memo_text(arguments["memo"]).encode("utf-8")
            pending_bytes = case.lib._memo_text(pending).encode("utf-8")
            self.assertGreater(len(pending_bytes), len(current_bytes))
            with mock.patch.object(case.lib, "MAX_MEMO_BYTES", len(current_bytes)):
                self.assert_unchanged_refusal(case, lambda: self.retain(
                    case, arguments, batch))

    def test_forged_fixed_wal_is_not_overwritten_or_adopted(self):
        with self.prepared() as (case, arguments, batch):
            fixed = Path(case.producer.source_path)
            fixed.write_bytes(capture_tests.canonical(arguments["retained_batch"]))
            fixed.chmod(0o600)
            self.assert_unchanged_refusal(case, lambda: self.retain(
                case, arguments, batch))
            self.assert_unchanged_refusal(case, lambda: self.recover(case, arguments))

    def test_request_drift_after_wal_refuses_before_memo_adoption(self):
        for field in ("admitted_status", "retained_batch",
                      "notification_baseline_attempt"):
            with self.subTest(field=field), self.prepared() as (
                    case, arguments, batch):
                self.assertIsNone(self.retain(case, arguments, batch))
                before_memo = ack_tests._path_image(case.live.paths["MEMO_PATH"])
                fixed_before = ack_tests._path_image(case.producer.source_path)
                original = case.lib.siaqueue.fixed_atomic_publish

                def mutate(*args, **kwargs):
                    result = original(*args, **kwargs)
                    arguments[field]["late-unadmitted-field"] = True
                    return result

                with self.no_collect(case), mock.patch.object(
                        case.lib.siaqueue, "fixed_atomic_publish", side_effect=mutate), \
                        mock.patch.object(case.lib, "atomic_write", side_effect=
                                          AssertionError("drift reached memo adoption")), \
                        self.assertRaises(REFUSALS):
                    self.recover(case, arguments)
                self.assertEqual(ack_tests._path_image(case.live.paths["MEMO_PATH"]),
                                 before_memo)
                self.assertEqual(ack_tests._path_image(case.producer.source_path),
                                 fixed_before)

    def test_current_artifact_name_substitution_after_wal_refuses(self):
        for target in ("memo", "status", "graph", "candidate", "generation",
                       "archive", "effects-archive"):
            with self.subTest(target=target), self.prepared() as (
                    case, arguments, batch):
                self.assertIsNone(self.retain(case, arguments, batch))
                paths = {
                    "memo": Path(case.live.paths["MEMO_PATH"]),
                    "status": Path(case.live.paths["STATUS_PATH"]),
                    "graph": Path(case.live.paths["GRAPH_PATH"]),
                    "candidate": Path(case.live.paths["LIVE_CANDIDATE_PATH"]),
                    "generation": Path(case.live.paths["LIVE_STATE_PATH"]),
                    "archive": case.archive_path(),
                    "effects-archive": case.effects_archive_path(),
                }
                before_memo_raw = Path(case.live.paths["MEMO_PATH"]).read_bytes()
                fixed_before = ack_tests._path_image(case.producer.source_path)
                original = case.lib.siaqueue.fixed_atomic_publish

                def substitute(*args, **kwargs):
                    result = original(*args, **kwargs)
                    case.replace_same_bytes(paths[target])
                    return result

                with self.no_collect(case), mock.patch.object(
                        case.lib.siaqueue, "fixed_atomic_publish", side_effect=substitute), \
                        mock.patch.object(case.lib, "atomic_write", side_effect=
                                          AssertionError("substitution reached memo adoption")), \
                        self.assertRaises(REFUSALS):
                    self.recover(case, arguments)
                self.assertEqual(Path(case.live.paths["MEMO_PATH"]).read_bytes(),
                                 before_memo_raw)
                self.assertEqual(ack_tests._path_image(case.producer.source_path),
                                 fixed_before)

    def test_wal_crash_prefixes_retry_exact_bytes_without_recollection(self):
        for phase in ("payload-fsynced", "target-published",
                      "target-directory-fsynced"):
            with self.subTest(phase=phase), self.prepared() as (
                    case, arguments, batch):
                memo_before = ack_tests._path_image(case.live.paths["MEMO_PATH"])
                original_memo = copy.deepcopy(arguments["memo"])
                fixed = Path(case.producer.source_path)

                def stop(name):
                    if name == phase:
                        raise KeyboardInterrupt("controlled WAL crash: " + phase)

                with self.no_collect(case), mock.patch.object(
                        case.lib.siaqueue, "_publish_boundary", side_effect=stop), \
                        self.assertRaises(KeyboardInterrupt):
                    self.retain(case, arguments, batch)
                self.assertEqual(ack_tests._path_image(case.live.paths["MEMO_PATH"]),
                                 memo_before)
                self.assertEqual(arguments["memo"], original_memo)
                fresh = case.lib.load_memo()
                if phase == "payload-fsynced":
                    self.assertFalse(fixed.exists())
                    with self.no_collect(case):
                        self.assertIs(self.recover(case, arguments, memo=fresh), False)
                        self.assertIsNone(self.retain(case, arguments, batch, memo=fresh))
                else:
                    self.assertEqual(fixed.read_bytes(), capture_tests.canonical(batch))
                fixed_before = ack_tests._path_image(fixed)
                directory = fixed.parent.stat()
                events = []
                original_fsync = os.fsync
                original_write = case.lib.atomic_write

                def fsync(descriptor):
                    info = os.fstat(descriptor)
                    result = original_fsync(descriptor)
                    if stat.S_ISDIR(info.st_mode) and (
                            info.st_dev, info.st_ino) == (
                            directory.st_dev, directory.st_ino):
                        events.append("wal-parent-synced")
                    return result

                def write(path, data, **kwargs):
                    if str(path) == case.live.paths["MEMO_PATH"]:
                        self.assertIn("wal-parent-synced", events)
                        events.append("memo-replacement")
                    return original_write(path, data, **kwargs)

                # Observe the real replay publisher and its owning helpers,
                # without altering os.fsync for unrelated test infrastructure.
                with self.no_collect(case), mock.patch.object(
                        self.publication, "os", page_tests._ModuleShim(
                            self.publication.os, fsync=fsync)), mock.patch.object(
                        case.lib, "os", page_tests._ModuleShim(
                            case.lib.os, fsync=fsync)), mock.patch.object(
                        case.lib.siaqueue, "os", page_tests._ModuleShim(
                            case.lib.siaqueue.os, fsync=fsync)), mock.patch.object(
                        case.lib, "atomic_write", side_effect=write):
                    self.assertIs(self.recover(case, arguments, memo=fresh), True)
                self.assertIn("memo-replacement", events)
                self.assertEqual(ack_tests._path_image(fixed), fixed_before)
                self.assertEqual(case.live._read("MEMO_PATH"), fresh)
                self.assertEqual(fresh[case.lib.NOTIFY_BASELINE_ATTEMPT_KEY],
                                 arguments["notification_baseline_attempt"])

    def test_pre_memo_replace_failure_retries_from_actual_completed_state(self):
        with self.prepared() as (case, arguments, batch):
            self.assertIsNone(self.retain(case, arguments, batch))
            before = self.images(case)
            memo_before = copy.deepcopy(arguments["memo"])
            with self.no_collect(case), mock.patch.object(
                    case.lib, "atomic_write", side_effect=OSError(
                        "controlled failure before pending memo replace")), \
                    self.assertRaises(OSError):
                self.recover(case, arguments)
            self.assertEqual(self.images(case), before)
            self.assertEqual(arguments["memo"], memo_before)
            fresh = case.lib.load_memo()
            expected = self.expected_pending(arguments, batch)
            with self.no_collect(case):
                self.assertIs(self.recover(case, arguments, memo=fresh), True)
            self.assertEqual(fresh, expected)

    def test_post_memo_rename_crash_is_pending_not_completed_retry(self):
        with self.prepared() as (case, arguments, batch):
            self.assertIsNone(self.retain(case, arguments, batch))
            expected = self.expected_pending(arguments, batch)
            before_caller = copy.deepcopy(arguments["memo"])
            fixed_before = ack_tests._path_image(case.producer.source_path)
            active = []
            original = case.lib.siaqueue.fixed_atomic_publish

            def publication(path, data, **kwargs):
                active.append(str(path))
                try:
                    return original(path, data, **kwargs)
                finally:
                    active.pop()

            def stop(name):
                if active and active[-1] == case.live.paths["MEMO_PATH"] \
                        and name == "target-published":
                    raise KeyboardInterrupt("controlled pending memo rename crash")

            with self.no_collect(case), mock.patch.object(
                    case.lib.siaqueue, "fixed_atomic_publish", side_effect=publication), \
                    mock.patch.object(case.lib.siaqueue, "_publish_boundary",
                                      side_effect=stop), \
                    self.assertRaises(KeyboardInterrupt):
                self.recover(case, arguments)
            self.assertEqual(arguments["memo"], before_caller)
            fresh = case.lib.load_memo()
            self.assertEqual(fresh, expected)
            self.assertEqual(ack_tests._path_image(case.producer.source_path), fixed_before)
            self.assert_unchanged_refusal(case, lambda: self.recover(
                case, arguments, memo=fresh))
            self.assert_unchanged_refusal(case, lambda: self.recover(case, arguments))
            with self.no_collect(case), case.forbid_ack_effects():
                pending = self.publication.read_pending(case.lib.__dict__, memo=fresh)
            self.assertEqual(pending["status"], "pending")
            self.assertEqual(pending["batch"], batch)
            # Readability here deliberately does not claim that a pending
            # replay has repaired the interrupted memo-parent fsync.


if __name__ == "__main__":
    unittest.main()
