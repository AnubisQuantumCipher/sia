"""Additive capture-only predecessor observation with a real pending fence.

Bounded capture contract: each fixture
first completes the real source/effects/archive ACK transaction, then calls
the actual notification-baseline marker operation.  Only that fixture setup
may write.  The operation under test must retain the complete fenced memo,
join the prior archives and actual live publication, and return a detached
capturable-not-ready view without authorizing capture or output.

This contract deliberately does not change the general completed/ACK reader,
adopt a different orphan fixed slot, establish cursor correctness, authorize
a writer, prove complete history, or claim a cognitive benchmark win.
"""

import contextlib
import copy
import importlib
import inspect
import os
from pathlib import Path
import re
import unittest
from unittest import mock

from tests import test_controller_source_ack as ack_tests
from tests import test_controller_source_capture as capture_tests


SCHEMA = "sia-controller-source-capturable-predecessor-v1"
RESULT_KEYS = {
    "schema", "status", "batch", "committed",
    "notification_baseline_attempt",
    "expected_notification_baseline_attempt_sha256", "non_claims",
}
API_PARAMETERS = (
    "owner", "memo", "admitted_status", "committed",
    "notification_baseline_attempt",
    "expected_notification_baseline_attempt_sha256",
)
# Independent roster: membership, not the truthiness of a pending payload,
# excludes every other currently admitted controller/recovery authority.
OTHER_PENDING_KEYS = (
    "controller_source_pending", "controller_source_live_pending",
    "controller_source_effects_pending",
    "controller_source_effects_committed", "pulse_status_effects_pending",
    "live_loop_pending", "source_replay_pending", "pulse_publication",
    "dream_publication", "consolidation_pending",
    "brainstem_failure_pending",
)
REFUSALS = (ValueError, RuntimeError, OSError)


class SourceCapturablePredecessor(unittest.TestCase):
    def setUp(self):
        self.ack = importlib.import_module("siasourceack")
        self.source_module = importlib.import_module("siasourcebatch")
        self.operation = getattr(self.ack, "read_capturable_predecessor", None)
        self.assertTrue(callable(self.operation),
                        "missing additive capture-only predecessor reader")
        # Compose, do not inherit or import a TestCase symbol: private
        # discovery must not repeat the repository fixture's whole suite.
        self.case = ack_tests.ControllerSourceAcknowledgment(
            methodName="runTest")
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.case.start_empty()
        self.assertIsNone(self.case.acknowledge())
        self.case.assert_final()
        self.lib = self.case.lib
        self.owner = self.lib.__dict__
        self.status = copy.deepcopy(self.case.admitted_status())
        self.committed = copy.deepcopy(
            self.case.live.memo["controller_source_committed"])
        self.old_ready = copy.deepcopy(self.case.live.memo["ready"])
        self.key = self.lib.NOTIFY_BASELINE_ATTEMPT_KEY
        self.assertNotIn(self.key, self.case.live.memo)
        # This is the real legal memo transition, before no-effect guards.
        marker = self.lib._mark_notify_baseline_attempt(self.case.live.memo)
        self.marker = copy.deepcopy(marker)
        self.marker_sha = self.source_module.native_sha(
            self.owner, self.marker)
        self.assertEqual(self.case.live._read("MEMO_PATH"),
                         self.case.live.memo)
        self.assertEqual(self.case.live.memo[self.key], self.marker)
        self.assertEqual(self.case.live.memo["controller_source_committed"],
                         self.committed)
        self.assertEqual(self.case.live.memo["ready"], self.old_ready)
        self.initial_memo = copy.deepcopy(self.case.live.memo)

    def read(self, **changes):
        arguments = {
            "memo": self.case.live.memo,
            "admitted_status": self.status,
            "committed": self.committed,
            "notification_baseline_attempt": self.marker,
            "expected_notification_baseline_attempt_sha256": self.marker_sha,
        }
        arguments.update(changes)
        return self.operation(self.owner, **arguments)

    def images(self):
        result = self.case.images()
        result["effects-archive-dir"] = ack_tests._path_image(
            self.case.effects_archive_dir)
        result["effects-archive"] = ack_tests._path_image(
            self.case.effects_archive_path())
        return result

    def persist_memo(self, memo):
        self.case.live._write(self.case.live.paths["MEMO_PATH"], memo)
        self.case.live.memo.clear()
        self.case.live.memo.update(copy.deepcopy(memo))

    @contextlib.contextmanager
    def no_effects(self):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("capture-only predecessor crossed an effect")

        with contextlib.ExitStack() as stack:
            stack.enter_context(self.case.forbid_ack_effects())
            for name in (
                    "_write_memo", "_mark_notify_baseline_attempt",
                    "_clear_notify_baseline_attempt",
                    "_recover_notify_baseline_attempt", "iso", "utcnow",
                    "_recover_pending_live_generation",
                    "_stage_live_generation", "_publish_staged_live_generation",
                    "_stage_controller_source_batch",
                    "_publish_controller_source_effects",
                    "_recover_pending_controller_source_batch"):
                if hasattr(self.lib, name):
                    stack.enter_context(mock.patch.object(
                        self.lib, name, side_effect=forbidden))
            stack.enter_context(mock.patch.object(
                self.source_module, "_collect", side_effect=forbidden))
            yield

    def assert_readonly_refusal(self, **changes):
        before = self.images()
        inputs = copy.deepcopy({
            "memo": self.case.live.memo, "status": self.status,
            "committed": self.committed, "marker": self.marker,
            "changes": changes,
        })
        with self.no_effects(), self.assertRaises(REFUSALS):
            self.read(**changes)
        self.assertEqual(self.images(), before)
        self.assertEqual({
            "memo": self.case.live.memo, "status": self.status,
            "committed": self.committed, "marker": self.marker,
            "changes": changes,
        }, inputs)

    def assert_view(self, view):
        self.assertIs(type(view), dict)
        self.assertEqual(set(view), RESULT_KEYS)
        self.assertEqual(view["schema"], SCHEMA)
        self.assertEqual(view["status"], "capturable-not-ready")
        self.assertEqual(view["batch"], self.case.batch)
        self.assertEqual(view["committed"], self.committed)
        self.assertEqual(view["notification_baseline_attempt"], self.marker)
        self.assertEqual(view["expected_notification_baseline_attempt_sha256"],
                         self.marker_sha)
        claims = getattr(self.ack, "CAPTURE_NON_CLAIMS", None)
        self.assertIsNotNone(claims, "missing capture-only consequence limits")
        self.assertEqual(view["non_claims"], list(claims))

    def test_exact_additive_keyword_api_and_explicit_non_claims(self):
        parameters = inspect.signature(self.operation).parameters
        self.assertEqual(tuple(parameters), API_PARAMETERS)
        self.assertEqual(parameters["owner"].kind,
                         inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for name in API_PARAMETERS:
            self.assertIs(parameters[name].default, inspect.Parameter.empty)
            if name != "owner":
                self.assertEqual(parameters[name].kind,
                                 inspect.Parameter.KEYWORD_ONLY)
        claims = getattr(self.ack, "CAPTURE_NON_CLAIMS", None)
        self.assertIsInstance(claims, (list, tuple))
        self.assertTrue(claims)
        self.assertTrue(all(type(row) is str and row.strip() for row in claims))
        # Semantic denials, deliberately no invented exact wording.
        negative = re.compile(r"\b(?:not|no|never|cannot|neither|without)\b")
        for concept in (
                r"readiness|\bready\b", r"acknowledg|\back\b",
                r"output|delivery|delivered", r"writer|writ(?:e|ing) authority",
                r"complete.{0,32}history|history.{0,32}complete",
                r"cognitive.{0,32}win|held.out.{0,32}win"):
            with self.subTest(concept=concept):
                self.assertTrue(any(
                    re.search(concept, row.lower()) and negative.search(row.lower())
                    for row in claims), "missing consequence denial: " + concept)

    def test_real_fenced_predecessor_is_detached_and_effectless(self):
        pending, temporary, destination = \
            self.case.seed_unrelated_pending_rename()
        before = self.images()
        queue_before = (
            ack_tests._path_image(temporary),
            ack_tests._path_image(destination), copy.deepcopy(pending))
        seen = []
        actual = self.lib._read_committed_live_generation

        def inspect_real_parent(*, memo, admitted_status):
            # An implementation must not suppress the marker in a memo copy
            # to obtain a readiness/completed view through a different lane.
            self.assertEqual(memo, self.initial_memo)
            self.assertEqual(memo[self.key], self.marker)
            self.assertEqual(admitted_status, self.status)
            seen.append(copy.deepcopy(memo))
            return actual(memo=memo, admitted_status=admitted_status)

        with self.no_effects(), mock.patch.object(
                self.lib, "PENDING_CURSOR_RENAMES", pending), \
                mock.patch.object(self.lib, "_read_committed_live_generation",
                                  side_effect=inspect_real_parent):
            first = self.read()
            self.assert_view(first)
            self.assertTrue(seen, "actual committed live parent was not read")
            first["batch"]["epoch"]["epoch_id"] = "caller-mutated-view"
            first["committed"]["source_batch_sha256"] = "0" * 64
            first["notification_baseline_attempt"]["id"] = "0" * 32
            first["non_claims"].append("caller-only text")
            self.assert_view(self.read())
            self.assertIs(self.lib.PENDING_CURSOR_RENAMES, pending)
        self.assertEqual(self.images(), before)
        self.assertEqual((ack_tests._path_image(temporary),
                          ack_tests._path_image(destination), pending), queue_before)
        self.assertEqual(self.case.live.memo, self.initial_memo)
        self.assertEqual(self.case.live.memo["ready"], self.old_ready)

    def test_general_completed_reader_and_ack_still_refuse_same_fence(self):
        with self.no_effects():
            self.assert_view(self.read())
        before = self.images()
        with self.no_effects():
            with self.assertRaises(REFUSALS):
                self.ack.read_completed(
                    self.owner, memo=self.case.live.memo,
                    admitted_status=self.status)
            with self.assertRaises(REFUSALS):
                self.case.acknowledge()
        self.assertEqual(self.images(), before)
        self.assertEqual(self.case.live.memo, self.initial_memo)

    def test_absent_none_and_malformed_durable_fence_refuse(self):
        malformed = (
            None, False, [], {},
            dict(self.marker, v=True),
            dict(self.marker, id="not-a-marker-id"),
            dict(self.marker, started_at="not-a-canonical-timestamp"),
            dict(self.marker, unadmitted=True),
        )
        absent = copy.deepcopy(self.initial_memo)
        absent.pop(self.key)
        self.persist_memo(absent)
        self.assert_readonly_refusal()
        for marker in malformed:
            with self.subTest(marker=marker):
                changed = copy.deepcopy(self.initial_memo)
                changed[self.key] = copy.deepcopy(marker)
                self.persist_memo(changed)
                # Re-pin each malformed image so shape admission is required,
                # not merely failure to match the original marker digest.
                self.assert_readonly_refusal(
                    notification_baseline_attempt=copy.deepcopy(marker),
                    expected_notification_baseline_attempt_sha256=
                        self.source_module.native_sha(self.owner, marker))

    def test_external_fence_image_and_pin_are_independently_required(self):
        other = dict(self.marker, id="0" * 32)
        self.assertNotEqual(other, self.marker)
        for changes in (
                {"notification_baseline_attempt": None},
                {"notification_baseline_attempt": other},
                {"notification_baseline_attempt": other,
                 "expected_notification_baseline_attempt_sha256":
                     self.source_module.native_sha(self.owner, other)},
                {"expected_notification_baseline_attempt_sha256": None},
                {"expected_notification_baseline_attempt_sha256": "0" * 64},
                {"expected_notification_baseline_attempt_sha256": "bad-pin"}):
            with self.subTest(changes=changes):
                self.assert_readonly_refusal(**changes)

    def test_independent_committed_must_equal_actual_durable_predecessor(self):
        for key in ack_tests.COMMITTED_KEYS:
            with self.subTest(key=key):
                changed = copy.deepcopy(self.committed)
                changed[key] = "0" * 64
                self.assertNotEqual(changed, self.committed)
                self.assert_readonly_refusal(committed=changed)
        for value in (None, {}, dict(self.committed, foreign="0" * 64)):
            with self.subTest(shape=value):
                self.assert_readonly_refusal(committed=value)

    def test_every_other_pending_authority_refuses_even_present_none(self):
        for key in OTHER_PENDING_KEYS:
            for value in (None, {"private-fixture-pending": True}):
                with self.subTest(key=key, value=value):
                    changed = copy.deepcopy(self.initial_memo)
                    changed[key] = value
                    self.persist_memo(changed)
                    self.assert_readonly_refusal()
        self.persist_memo(self.initial_memo)
        with self.no_effects():
            self.assert_view(self.read())

    def test_caller_durable_status_and_historical_ready_drift_refuse(self):
        caller = copy.deepcopy(self.initial_memo)
        caller["private-fixture-drift"] = True
        self.assert_readonly_refusal(memo=caller)
        self.case.live._write(self.case.live.paths["MEMO_PATH"], caller)
        self.assert_readonly_refusal()
        self.persist_memo(self.initial_memo)
        changed_status = dict(self.status, sync_note="changed admitted fixture")
        self.assert_readonly_refusal(admitted_status=changed_status)
        status_path = Path(self.case.live.paths["STATUS_PATH"])
        original_status_raw = status_path.read_bytes()
        try:
            self.case.live._write(status_path, changed_status)
            self.assert_readonly_refusal()
        finally:
            status_path.write_bytes(original_status_raw)
        changed = copy.deepcopy(self.initial_memo)
        changed["ready"]["identity"] = "0" * 32
        self.persist_memo(changed)
        self.assert_readonly_refusal()

    def test_missing_changed_source_and_effects_archives_refuse(self):
        for path in (self.case.archive_path(), self.case.effects_archive_path()):
            with self.subTest(path=path.name):
                hidden = path.with_name(path.name + ".fixture-held")
                os.replace(path, hidden)
                try:
                    self.assert_readonly_refusal()
                finally:
                    os.replace(hidden, path)
                raw = path.read_bytes()
                try:
                    path.write_bytes(raw + b" ")
                    self.assert_readonly_refusal()
                finally:
                    path.write_bytes(raw)

    def test_rehashed_archived_effects_cannot_relabel_source_or_live_join(self):
        original_path = self.case.effects_archive_path()
        receipt = self.case.memo_before_ack["controller_source_effects_committed"]
        for field in ("source_batch_sha256", "source_batch_wire_sha256",
                      "prepare_inputs_sha256", "state_sha256",
                      "transition_sha256"):
            with self.subTest(field=field):
                changed = copy.deepcopy(receipt)
                changed[field] = "0" * 64
                self.assertNotEqual(changed[field], receipt[field])
                payload = {key: value for key, value in changed.items()
                           if key != "receipt_sha256"}
                changed["receipt_sha256"] = self.source_module.native_sha(
                    self.owner, payload)
                path = original_path.with_name(changed["receipt_sha256"] + ".json")
                self.assertFalse(path.exists())
                path.write_bytes(capture_tests.canonical(changed))
                path.chmod(0o600)
                supplied = copy.deepcopy(self.committed)
                supplied["source_effects_receipt_sha256"] = changed["receipt_sha256"]
                memo = copy.deepcopy(self.initial_memo)
                memo["controller_source_committed"] = copy.deepcopy(supplied)
                self.persist_memo(memo)
                before = ack_tests._path_image(path)
                try:
                    self.assert_readonly_refusal(committed=supplied)
                    self.assertEqual(ack_tests._path_image(path), before)
                finally:
                    path.unlink()
                    self.persist_memo(self.initial_memo)

    def test_changed_graph_candidate_and_generation_refuse(self):
        for name in ("GRAPH_PATH", "LIVE_CANDIDATE_PATH", "LIVE_STATE_PATH"):
            with self.subTest(name=name):
                path = Path(self.case.live.paths[name])
                raw = path.read_bytes()
                changed = self.case.live._read(name)
                changed["publication_id"] = "0" * 32
                try:
                    self.case.live._write(path, changed)
                    self.assert_readonly_refusal()
                finally:
                    path.write_bytes(raw)

    def test_unrelated_orphan_fixed_slot_is_neither_adopted_nor_interpreted(self):
        path = Path(self.case.producer.source_path)
        self.assertFalse(path.exists())
        # Deliberately not a batch: archive-only predecessor observation must
        # not infer, parse, recover, stage, or certify this unrelated object.
        path.write_bytes(b'{"private-unrelated-orphan":true}\n')
        path.chmod(0o600)
        before = self.images()
        with self.no_effects():
            self.assert_view(self.read())
        self.assertEqual(self.images(), before)
        self.assertEqual(self.case.live.memo, self.initial_memo)

    def test_late_caller_durable_and_held_archive_drift_refuse(self):
        actual = self.lib._read_committed_live_generation
        for selected in ("caller", "durable", "source-archive", "effects-archive"):
            with self.subTest(selected=selected):
                self.persist_memo(self.initial_memo)
                touched = []
                mutation_image = []

                def after_real_parent(*, memo, admitted_status):
                    result = actual(memo=memo, admitted_status=admitted_status)
                    if not touched:
                        touched.append(selected)
                        if selected == "caller":
                            self.case.live.memo["private-late-drift"] = True
                        elif selected == "durable":
                            changed = dict(self.initial_memo, private_late_drift=True)
                            self.case.live._write(
                                self.case.live.paths["MEMO_PATH"], changed)
                        else:
                            path = self.case.archive_path() if selected == "source-archive" \
                                else self.case.effects_archive_path()
                            self.case.replace_same_bytes(path)
                        mutation_image.append(self.images())
                    return result

                with self.no_effects(), mock.patch.object(
                        self.lib, "_read_committed_live_generation",
                        side_effect=after_real_parent), self.assertRaises(REFUSALS):
                    self.read()
                self.assertTrue(touched, "late-mutation checkpoint was not reached")
                self.assertEqual(self.images(), mutation_image[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
