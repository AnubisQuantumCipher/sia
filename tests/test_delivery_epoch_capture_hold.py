"""Targeted additive held-epoch observation after a real notification fence.

Module-qualified fixtures supply real source ACK and durable delivery-epoch preparation in
temporary storage. The actual notification marker operation then creates
the legal post-collection memo image; no filtered memo copy or fake parent
completion is used. Observation remains effectless and not ready.

These tests neither run the full inherited suites nor fabricate a source-v3
completion, writer permit, output receipt, machine history or cognitive win.
"""

import contextlib
import copy
import importlib
import inspect
import os
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import test_controller_delivery_epoch_hold as hold_tests
from tests import test_controller_delivery_epoch as epoch_tests
from tests import test_controller_source_ack as ack_tests


SCHEMA = "sia-controller-delivery-epoch-capture-view-v1"
BASE_PARAMETERS = (
    "owner", "memo", "admitted_status", "retained_batch", "committed",
    "journal_limits", "expected_journal_limits_sha256",
    "expected_adoption_sha256",
)
FENCE_PARAMETERS = (
    "notification_baseline_attempt",
    "expected_notification_baseline_attempt_sha256",
)
VIEW_KEYS = {
    "schema", "status", "epoch_adoption", "parent_committed",
    "parent_generation", "expected_parent_generation_sha256",
    "records_directory", "records_identity", "non_claims",
    "notification_baseline_attempt",
    "expected_notification_baseline_attempt_sha256",
}


class CallerFailure(RuntimeError):
    pass


def _scope_identity(descriptor):
    info = os.fstat(descriptor)
    # Read-only fixture snapshots can update atime; it is not lease identity.
    return (info.st_dev, info.st_ino, info.st_mode,
            info.st_uid, info.st_gid, info.st_nlink)


class ControllerDeliveryEpochCaptureHold(unittest.TestCase):
    def setUp(self):
        self.fixture = hold_tests.ControllerDeliveryEpochHold(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.module = self.fixture.module
        self.operation = getattr(self.module, "hold_capturable_epoch", None)
        self.assertTrue(callable(self.operation),
                        "missing additive capture-only delivery epoch hold")
        self.source = importlib.import_module("siasourcebatch")
        self.ack = importlib.import_module("siasourceack")

    @contextlib.contextmanager
    def fenced(self):
        with self.fixture.prepared() as values:
            case, retained, committed, status, generation, root, adopted = values
            old_request = self.fixture.request(
                case, retained, committed, status, adopted)
            key = case.lib.NOTIFY_BASELINE_ATTEMPT_KEY
            self.assertNotIn(key, case.live.memo)
            old_ready = copy.deepcopy(case.live.memo["ready"])
            # Actual admitted mutation, completed before any no-write spies.
            with self.fixture.epoch.idle.source_owner(case):
                marker = copy.deepcopy(case.lib._mark_notify_baseline_attempt(
                    case.live.memo))
            marker_sha = self.source.native_sha(case.lib.__dict__, marker)
            self.assertEqual(case.live._read("MEMO_PATH"), case.live.memo)
            self.assertEqual(case.live.memo[key], marker)
            self.assertEqual(case.live.memo["controller_source_committed"], committed)
            self.assertEqual(case.live.memo["ready"], old_ready)
            request = {
                **old_request,
                "notification_baseline_attempt": marker,
                "expected_notification_baseline_attempt_sha256": marker_sha,
            }
            expected = self.fixture.expected(
                retained, committed, generation, root, adopted)
            expected.update({
                "schema": SCHEMA, "status": "held-capturable-not-ready",
                "notification_baseline_attempt": copy.deepcopy(marker),
                "expected_notification_baseline_attempt_sha256": marker_sha,
                "non_claims": list(self.module.CAPTURE_HELD_NON_CLAIMS),
            })
            yield SimpleNamespace(
                case=case, retained=retained, committed=committed,
                status=status, generation=generation, root=root, adopted=adopted,
                key=key, marker=marker, marker_sha=marker_sha,
                old_request=old_request, request=request, expected=expected,
                memo=copy.deepcopy(case.live.memo), ready=old_ready)

    def images(self, f):
        return (f.case.images(), epoch_tests._tree(f.root),
                ack_tests._path_image(f.case.effects_archive_path()),
                copy.deepcopy(f.case.live.memo))

    @contextlib.contextmanager
    def no_effects(self, f):
        real_iso = f.case.lib.iso

        def format_retained_time(dt=None):
            if not isinstance(dt, f.case.lib.datetime.datetime):
                raise AssertionError("capture hold acquired a clock through iso")
            return real_iso(dt)

        with self.fixture.reader_scope(f.case), contextlib.ExitStack() as stack:
            for name in ("_mark_notify_baseline_attempt", "_clear_notify_baseline_attempt",
                         "_recover_notify_baseline_attempt", "utcnow"):
                stack.enter_context(mock.patch.object(
                    f.case.lib, name,
                    side_effect=AssertionError("capture hold attempted " + name)))
            stack.enter_context(mock.patch.object(
                f.case.lib, "iso", side_effect=format_retained_time))
            yield

    def hold(self, f, **changes):
        return self.operation(f.case.lib.__dict__, **{**f.request, **changes})

    def reject(self, f, **changes):
        before = (self.images(f), copy.deepcopy(f.request))
        with self.no_effects(f):
            descriptors = self.fixture.fds()
            with self.assertRaises(self.module.ControllerDeliveryEpochRefusal):
                with self.hold(f, **changes):
                    self.fail("non-authorizing capture epoch entered")
            self.assertEqual(self.fixture.fds(), descriptors)
        self.assertEqual((self.images(f), f.request), before)

    def test_additive_signature_and_distinct_consequence_contract(self):
        old = inspect.signature(self.module.hold_epoch).parameters
        prepare = inspect.signature(self.module.prepare_epoch).parameters
        actual = inspect.signature(self.operation).parameters
        self.assertEqual(tuple(old), BASE_PARAMETERS)
        self.assertEqual(tuple(prepare), BASE_PARAMETERS)
        self.assertEqual(tuple(actual), BASE_PARAMETERS + FENCE_PARAMETERS)
        for name, parameter in actual.items():
            self.assertIs(parameter.default, inspect.Parameter.empty)
            self.assertEqual(parameter.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD
                             if name == "owner" else inspect.Parameter.KEYWORD_ONLY)
        claims = getattr(self.module, "CAPTURE_HELD_NON_CLAIMS", None)
        self.assertIsInstance(claims, (list, tuple))
        self.assertTrue(claims)
        self.assertNotEqual(list(claims), list(self.module.HELD_NON_CLAIMS))
        self.assertTrue(all(type(claim) is str and claim.strip() for claim in claims))
        for subject in (r"readiness|\bready\b", r"acknowledg|\back\b",
                        r"durab|repair", r"writer", r"output|deliver",
                        r"complete.{0,32}histor|histor.{0,32}complete",
                        r"cognit|biolog", r"held[- ]?out"):
            with self.subTest(subject=subject):
                self.assertTrue(any(
                    re.search(subject, claim, re.I)
                    and re.search(r"\b(no|not|never|without|cannot)\b", claim, re.I)
                    for claim in claims), "missing capture-hold denial: " + subject)

    def test_real_fenced_parent_stays_not_ready_detached_and_effectless(self):
        with self.fenced() as f:
            before = (self.images(f), copy.deepcopy(f.request))
            actual = self.ack.read_capturable_predecessor
            seen = []

            def observe_parent(owner, **request):
                self.assertEqual(request["memo"], f.memo)
                self.assertEqual(request["memo"][f.key], f.marker)
                self.assertEqual(request["committed"], f.committed)
                self.assertEqual(request["notification_baseline_attempt"], f.marker)
                self.assertEqual(request["expected_notification_baseline_attempt_sha256"],
                                 f.marker_sha)
                seen.append(True)
                return actual(owner, **request)

            with self.no_effects(f), mock.patch.object(
                    self.ack, "read_capturable_predecessor", side_effect=observe_parent), \
                    mock.patch.object(self.ack, "read_completed", side_effect=AssertionError(
                        "capture hold substituted the general completed reader")):
                descriptors = self.fixture.fds()
                with self.hold(f) as held:
                    for method in (held.current, held.read):
                        self.assertEqual(dict(inspect.signature(method).parameters), {})
                    first = held.read()
                    self.assertEqual(set(first), VIEW_KEYS)
                    self.assertEqual(first, f.expected)
                    self.assertTrue(seen, "capture-only source parent was not admitted")
                    self.fixture.assert_authority_descriptors_held(f.case, f.retained, f.root)
                    first["notification_baseline_attempt"].clear()
                    first["epoch_adoption"]["birth"]["limits"].clear()
                    first["parent_generation"].clear()
                    first["parent_committed"].clear()
                    first["records_identity"].clear()
                    first["non_claims"].clear()
                    self.assertEqual(held.read(), f.expected)
                    held.current()
                self.fixture.closed(held)
                self.assertEqual(self.fixture.fds(), descriptors)
            self.assertEqual((self.images(f), f.request), before)
            self.assertEqual(f.case.live.memo["ready"], f.ready)

    def test_existing_prepare_and_hold_still_refuse_the_real_fence(self):
        with self.fenced() as f:
            before = self.images(f)
            with self.no_effects(f):
                with self.assertRaises(self.module.ControllerDeliveryEpochRefusal):
                    with self.module.hold_epoch(f.case.lib.__dict__, **f.old_request):
                        self.fail("ordinary hold accepted the notification fence")
            # Preparation ordinarily nests both owner scopes; allow those
            # normal entries but prohibit all storage, clock and recovery work.
            with self.fixture.epoch.idle.source_owner(f.case), \
                    f.case.lib.brainstem_owner(), f.case.lib.corpus_owner(), \
                    self.fixture.epoch.no_new_work(f.case), contextlib.ExitStack() as stack:
                for owner, name in (
                        (f.case.lib, "_write_memo"), (f.case.lib, "atomic_write"),
                        (f.case.lib, "_clear_notify_baseline_attempt"),
                        (f.case.lib, "_mark_notify_baseline_attempt"),
                        (self.fixture.epoch.queue, "fixed_atomic_publish"),
                        (os, "mkdir"), (os, "fsync")):
                    stack.enter_context(mock.patch.object(owner, name,
                        side_effect=AssertionError("strict preparation attempted " + name)))
                with self.assertRaises(self.module.ControllerDeliveryEpochRefusal):
                    self.module.prepare_epoch(f.case.lib.__dict__, **f.old_request)
            self.assertEqual(self.images(f), before)

    def test_marker_and_external_pins_are_mandatory_not_derived_from_memo(self):
        with self.fenced() as f:
            with self.no_effects(f):
                for name in FENCE_PARAMETERS:
                    request = {key: value for key, value in f.request.items() if key != name}
                    with self.subTest(missing=name), self.assertRaises(TypeError):
                        with self.operation(f.case.lib.__dict__, **request):
                            self.fail("omitted mandatory capture pin entered")
            other = dict(f.marker, id="0" * 32)
            self.assertNotEqual(other, f.marker)
            malformed = dict(f.marker, v=True)
            for changes in (
                    {"notification_baseline_attempt": None},
                    {"notification_baseline_attempt": malformed,
                     "expected_notification_baseline_attempt_sha256":
                         self.source.native_sha(f.case.lib.__dict__, malformed)},
                    {"notification_baseline_attempt": other,
                     "expected_notification_baseline_attempt_sha256":
                         self.source.native_sha(f.case.lib.__dict__, other)},
                    {"expected_notification_baseline_attempt_sha256": None},
                    {"expected_notification_baseline_attempt_sha256": "0" * 64},
                    {"expected_adoption_sha256": None},
                    {"expected_adoption_sha256": f.retained["batch_sha256"]}):
                with self.subTest(changes=changes):
                    self.reject(f, **changes)
            # No pending fence is not an implicit choice of ordinary hold.
            f.case.live.memo.pop(f.key)
            f.case.live._write(f.case.live.paths["MEMO_PATH"], f.case.live.memo)
            self.reject(f)

    def test_unentered_scope_refuses_before_acquisition_even_with_inherited_fd(self):
        with self.fenced() as f:
            lib = f.case.lib
            original_fd = lib._CORPUS_OWNER_FD.get()
            original_depth = lib._CORPUS_OWNER_DEPTH.get()
            original_identity = _scope_identity(original_fd)
            before = self.images(f)
            depth_token = lib._CORPUS_OWNER_DEPTH.set(0)
            fd_token = lib._CORPUS_OWNER_FD.set(None)
            inherited = mock.Mock(return_value=original_fd)
            try:
                with self.fixture.epoch.idle.source_owner(f.case), \
                        self.fixture.epoch.no_new_work(f.case), \
                        mock.patch.object(lib, "_validated_inherited_corpus_fd", inherited), \
                        contextlib.ExitStack() as stack:
                    for owner, name in (
                            (lib, "corpus_owner"), (lib, "brainstem_owner"),
                            (lib, "_owner_lease"), (lib, "ensure_dirs"),
                            (lib, "ensure_durable_directory"), (lib, "atomic_write"),
                            (lib, "_write_memo"), (os, "mkdir"), (os, "fsync")):
                        stack.enter_context(mock.patch.object(owner, name,
                            side_effect=AssertionError("unentered capture hold reached " + name)))
                    with self.assertRaises(self.module.ControllerDeliveryEpochRefusal):
                        with self.hold(f):
                            self.fail("capture hold acquired missing corpus scope")
            finally:
                lib._CORPUS_OWNER_FD.reset(fd_token)
                lib._CORPUS_OWNER_DEPTH.reset(depth_token)
            inherited.assert_not_called()
            self.assertEqual(lib._CORPUS_OWNER_FD.get(), original_fd)
            self.assertEqual(lib._CORPUS_OWNER_DEPTH.get(), original_depth)
            self.assertEqual(_scope_identity(original_fd), original_identity)
            self.assertEqual(self.images(f), before)

    def test_caller_durable_adoption_and_live_drift_remain_immutable(self):
        for selected in ("caller-marker", "durable-memo", "adoption", "live"):
            with self.subTest(selected=selected), self.fenced() as f:
                _key, _directory, _birth, adoption, _records = \
                    self.fixture.epoch.paths(f.retained, f.root)
                with self.no_effects(f):
                    descriptors = self.fixture.fds()
                    with self.assertRaises(self.module.ControllerDeliveryEpochRefusal):
                        with self.hold(f) as held:
                            self.assertEqual(held.read(), f.expected)
                            if selected == "caller-marker":
                                f.marker["id"] = "0" * 32
                            elif selected == "durable-memo":
                                path = Path(f.case.live.paths["MEMO_PATH"])
                                path.write_bytes(path.read_bytes() + b" ")
                            else:
                                path = adoption if selected == "adoption" \
                                    else Path(f.case.live.paths["LIVE_STATE_PATH"])
                                f.case.replace_same_bytes(path)
                            self.fixture.refuse(held.current)
                            self.fixture.refuse(held.read)
                    self.fixture.closed(held)
                    self.assertEqual(self.fixture.fds(), descriptors)

    def test_final_copy_rechecks_caller_fence_and_rejects_changed_detached_value(self):
        original_deepcopy = copy.deepcopy
        for selected in ("caller-fence", "returned-copy"):
            with self.subTest(selected=selected), self.fenced() as f:
                fired = []

                def copy_checkpoint(value, *args, **kwargs):
                    detached = original_deepcopy(value, *args, **kwargs)
                    if type(value) is dict and value.get("schema") == SCHEMA and not fired:
                        fired.append(selected)
                        if selected == "caller-fence":
                            f.marker["id"] = "0" * 32
                        else:
                            detached["expected_notification_baseline_attempt_sha256"] = "0" * 64
                    return detached

                with self.no_effects(f):
                    descriptors = self.fixture.fds()
                    exit_check = self.assertRaises(self.module.ControllerDeliveryEpochRefusal) \
                        if selected == "caller-fence" else contextlib.nullcontext()
                    with exit_check:
                        with self.hold(f) as held:
                            # Install only after entry: this is the public
                            # read() detachment boundary, not a setup copy.
                            with mock.patch.object(copy, "deepcopy", side_effect=copy_checkpoint):
                                self.fixture.refuse(held.read)
                            self.assertTrue(fired, "public read final copy was not exercised")
                    self.fixture.closed(held)
                    self.assertEqual(self.fixture.fds(), descriptors)

    def test_fixed_slot_must_be_absent_at_entry_and_through_held_lifetime(self):
        with self.fenced() as f:
            path = Path(f.case.producer.source_path)
            self.assertFalse(path.exists())
            path.write_bytes(b'{"unrelated-orphan":true}\n')
            path.chmod(0o600)
            self.reject(f)
        with self.fenced() as f:
            path = Path(f.case.producer.source_path)
            with self.no_effects(f):
                descriptors = self.fixture.fds()
                with self.assertRaises(self.module.ControllerDeliveryEpochRefusal):
                    with self.hold(f) as held:
                        self.assertEqual(held.read(), f.expected)
                        path.write_bytes(b'{"new-unrelated-orphan":true}\n')
                        path.chmod(0o600)
                        # No explicit current/read: normal exit itself must
                        # catch appearance and must not interpret or adopt it.
                self.fixture.closed(held)
                self.assertEqual(self.fixture.fds(), descriptors)

    def test_exceptional_exit_preserves_caller_error_and_only_retires_own_handles(self):
        with self.fenced() as f:
            sentinel_path = f.root.parent / "capture-hold-caller-sentinel"
            sentinel_path.write_bytes(b"caller-owned fixture\n")
            failure = CallerFailure("synthetic capture hold caller failure")
            with sentinel_path.open("rb") as sentinel, self.no_effects(f):
                sentinel_identity = os.fstat(sentinel.fileno())
                descriptors = self.fixture.fds()
                with self.assertRaises(CallerFailure) as caught:
                    with self.hold(f) as held:
                        self.fixture.assert_authority_descriptors_held(f.case, f.retained, f.root)
                        f.marker["id"] = "0" * 32
                        raise failure
                self.assertIs(caught.exception, failure)
                self.assertEqual(os.fstat(sentinel.fileno()), sentinel_identity)
                self.fixture.closed(held)
                self.assertEqual(self.fixture.fds(), descriptors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
