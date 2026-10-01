"""First-copy owner-basis regression and aggregate wire controls.

Compose the real acknowledged/fenced temporary predecessor fixture without
discovering its TestCase again. Only the first-copy test changes an owner
name, and only to a different absent canonical path in that fixture. Reads,
historical joins and the actual caller data are not replaced or fabricated.

Capacity controls account for the explicitly declared retained wire images:
the complete request, held current file bodies, source/effects archive bodies
and complete result envelope. Every individual representation fits the test
ceiling. This tests byte-budget enforcement, not Python heap consumption,
process memory, historical truth or cognitive performance.
"""

import contextlib
import copy
import errno
import os
from pathlib import Path
import sys
import unittest
from unittest import mock


try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
from tests import test_source_capturable_predecessor as capture_tests


REQUEST_KEYS = {
    "memo", "admitted_status", "committed", "notification_baseline_attempt",
    "expected_notification_baseline_attempt_sha256",
}
CURRENT_FILES = (
    "MEMO_PATH", "STATUS_PATH", "GRAPH_PATH",
    "LIVE_CANDIDATE_PATH", "LIVE_STATE_PATH",
)


def _descriptors():
    result = {}
    for leaf in os.listdir("/proc/self/fd"):
        descriptor = int(leaf)
        try:
            info = os.fstat(descriptor)
            target = os.readlink("/proc/self/fd/" + leaf)
        except OSError as exc:
            if exc.errno not in (errno.EBADF, errno.ENOENT):
                raise
            continue
        result[descriptor] = (info.st_dev, info.st_ino, info.st_mode, target)
    return result


class SourceCapturablePredecessorBasisBudget(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        case = capture_tests.SourceCapturablePredecessor(methodName="runTest")
        try:
            case.setUp()
            yield case
        finally:
            case.doCleanups()

    def request(self, case):
        return {
            "memo": case.case.live.memo,
            "admitted_status": case.status,
            "committed": case.committed,
            "notification_baseline_attempt": case.marker,
            "expected_notification_baseline_attempt_sha256": case.marker_sha,
        }

    def wire_budget(self, case):
        # Admit the same actual fixture at its original capacity before
        # constraining it. This is an effectless positive control, not a
        # substitute decoder or an invented historical view.
        with case.no_effects():
            control = case.read()
            case.assert_view(control)
        serialize = case.source_module.native_bytes
        held = {"request": serialize(case.owner, self.request(case))}
        held.update({
            name: Path(case.case.live.paths[name]).read_bytes()
            for name in CURRENT_FILES
        })
        held["source-archive"] = case.case.archive_path().read_bytes()
        held["effects-archive"] = case.case.effects_archive_path().read_bytes()
        result_raw = serialize(case.owner, control)
        self.assertTrue(all(raw for raw in held.values()))
        self.assertTrue(result_raw)
        return held, result_raw

    def assert_individual_fit(self, case, held, result_raw, limit):
        self.assertLessEqual(limit, case.lib.MAX_STATE_JSON_BYTES,
                             "fixture must constrain, not expand, the original capacity")
        for name, raw in {**held, "result": result_raw}.items():
            self.assertLessEqual(len(raw), limit,
                                 "individual fixture representation exceeds capacity: " + name)
        self.assertLessEqual(len(held["MEMO_PATH"]), case.lib.MAX_MEMO_BYTES)
        self.assertLessEqual(len(held["effects-archive"]), case.lib.MAX_MEMO_BYTES)

    @contextlib.contextmanager
    def observe_result_without_copy(self, case):
        real_serialize = case.source_module.native_bytes
        real_copy = copy.deepcopy
        observed = {"serialized": [], "copied": []}

        def serialize(owner, value, ceiling=None):
            raw = real_serialize(owner, value, ceiling=ceiling)
            if type(value) is dict and value.get("schema") == capture_tests.SCHEMA:
                observed["serialized"].append(raw)
            return raw

        def detach(value, *args, **kwargs):
            if type(value) is dict and value.get("schema") == capture_tests.SCHEMA:
                observed["copied"].append(True)
                raise AssertionError("over-aggregate result copied before refusal")
            return real_copy(value, *args, **kwargs)

        with mock.patch.object(case.source_module, "native_bytes", serialize), \
                mock.patch.object(copy, "deepcopy", detach):
            yield observed

    def test_owner_path_mutation_during_first_request_copy_is_not_new_basis(self):
        with self.fixture() as case:
            original_path = case.lib.CONTROLLER_SOURCE_BATCH_PATH
            alternate = Path(original_path).with_name("changed-owner-source-slot.json")
            self.assertNotEqual(str(alternate), original_path)
            self.assertTrue(alternate.is_absolute())
            self.assertEqual(os.path.normpath(str(alternate)), str(alternate))
            self.assertFalse(alternate.exists())
            before = case.images()
            inputs = copy.deepcopy(self.request(case))
            descriptors = _descriptors()
            real_copy = copy.deepcopy
            touched = []

            def copy_and_change_owner(value, *args, **kwargs):
                detached = real_copy(value, *args, **kwargs)
                if not touched and type(value) is dict and set(value) == REQUEST_KEYS \
                        and value["memo"] is case.case.live.memo:
                    self.assertEqual(case.lib.CONTROLLER_SOURCE_BATCH_PATH, original_path)
                    # Real path selection remains visible to every subsequent
                    # reader. No stat/open/read function is mocked or redirected.
                    case.lib.CONTROLLER_SOURCE_BATCH_PATH = str(alternate)
                    touched.append(True)
                return detached

            with mock.patch.object(case.lib, "CONTROLLER_SOURCE_BATCH_PATH", original_path):
                with case.no_effects(), mock.patch.object(
                        copy, "deepcopy", copy_and_change_owner):
                    with self.assertRaises(case.source_module.SourceBatchRefusal):
                        case.read()
                self.assertTrue(touched, "first compound request copy was not reached")
                self.assertEqual(case.lib.CONTROLLER_SOURCE_BATCH_PATH, str(alternate))
            self.assertEqual(case.lib.CONTROLLER_SOURCE_BATCH_PATH, original_path)
            self.assertFalse(alternate.exists())
            self.assertEqual(case.images(), before)
            self.assertEqual(self.request(case), inputs)
            self.assertEqual(_descriptors(), descriptors)

    def test_held_aggregate_refuses_although_every_individual_wire_fits(self):
        with self.fixture() as case:
            held, result_raw = self.wire_budget(case)
            limit = max(len(raw) for raw in (*held.values(), result_raw))
            self.assert_individual_fit(case, held, result_raw, limit)
            self.assertGreater(sum(len(raw) for raw in held.values()), limit,
                               "fixture must exceed aggregate before result construction")
            before = case.images()
            inputs = copy.deepcopy(self.request(case))
            descriptors = _descriptors()
            with case.no_effects(), \
                    mock.patch.object(case.lib, "MAX_STATE_JSON_BYTES", limit), \
                    self.observe_result_without_copy(case) as observed:
                with self.assertRaises(case.source_module.SourceBatchRefusal) as caught:
                    case.read()
            self.assertEqual(caught.exception.reason, "ack-capturable-held-byte-capacity")
            self.assertEqual(observed["serialized"], [])
            self.assertEqual(observed["copied"], [])
            self.assertEqual(case.images(), before)
            self.assertEqual(self.request(case), inputs)
            self.assertEqual(_descriptors(), descriptors)

    def test_final_result_aggregate_refuses_after_held_budget_fits_exactly(self):
        with self.fixture() as case:
            held, result_raw = self.wire_budget(case)
            limit = sum(len(raw) for raw in held.values())
            self.assert_individual_fit(case, held, result_raw, limit)
            self.assertGreater(sum(len(raw) for raw in (*held.values(), result_raw)), limit)
            before = case.images()
            inputs = copy.deepcopy(self.request(case))
            descriptors = _descriptors()
            with case.no_effects(), \
                    mock.patch.object(case.lib, "MAX_STATE_JSON_BYTES", limit), \
                    self.observe_result_without_copy(case) as observed:
                with self.assertRaises(case.source_module.SourceBatchRefusal) as caught:
                    case.read()
            self.assertEqual(caught.exception.reason, "ack-capturable-result-byte-capacity")
            self.assertTrue(observed["serialized"],
                            "held aggregate refused before final result was admitted")
            self.assertTrue(all(raw == result_raw for raw in observed["serialized"]))
            self.assertEqual(observed["copied"], [])
            self.assertEqual(case.images(), before)
            self.assertEqual(self.request(case), inputs)
            self.assertEqual(_descriptors(), descriptors)


if __name__ == "__main__":
    unittest.main()
