"""Final-copy authority and whole-request capacity for capture-only reads.

Fixture mutations affect temporary files only. They exercise local lifetime
checks, not hostile same-user immutability, machine truth or cognitive wins.
"""

import contextlib
import copy
import errno
import os
import unittest
from unittest import mock

from tests import test_source_capturable_predecessor as capture_tests


def descriptors():
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


class SourceCapturablePredecessorTail(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        case = capture_tests.SourceCapturablePredecessor(methodName="runTest")
        try:
            case.setUp()
            yield case
        finally:
            case.doCleanups()

    @contextlib.contextmanager
    def at_result(self, case, action):
        actual = case.source_module.native_bytes
        touched = []

        def serialize(owner, value, ceiling=None):
            raw = actual(owner, value, ceiling=ceiling)
            if not touched and type(value) is dict \
                    and value.get("schema") == capture_tests.SCHEMA:
                touched.append(True)
                action(value)
            return raw

        with mock.patch.object(case.source_module, "native_bytes", serialize):
            yield
        self.assertTrue(touched, "complete result was not bounded/serialized")

    def test_all_authority_descriptors_survive_complete_result_serialization(self):
        with self.fixture() as case:
            before = descriptors()
            paths = {
                str(case.case.archive_path()), str(case.case.effects_archive_path()),
                *(str(case.case.live.paths[name]) for name in (
                    "MEMO_PATH", "STATUS_PATH", "GRAPH_PATH",
                    "LIVE_CANDIDATE_PATH", "LIVE_STATE_PATH")),
            }

            def held(_value):
                self.assertTrue(paths.issubset({row[-1] for row in descriptors().values()}),
                                "capture authority closed before final copy")

            with case.no_effects(), self.at_result(case, held):
                case.assert_view(case.read())
            self.assertEqual(descriptors(), before)

    def test_same_bytes_replacement_at_result_refuses_and_closes_owned_fds(self):
        for selected in ("MEMO_PATH", "STATUS_PATH", "GRAPH_PATH",
                         "LIVE_CANDIDATE_PATH", "LIVE_STATE_PATH",
                         "source-archive", "effects-archive"):
            with self.subTest(selected=selected), self.fixture() as case:
                path = case.case.archive_path() if selected == "source-archive" \
                    else case.case.effects_archive_path() if selected == "effects-archive" \
                    else case.case.live.paths[selected]
                before = descriptors()

                def replace(_value):
                    case.case.replace_same_bytes(path)

                with case.no_effects(), self.at_result(case, replace):
                    with self.assertRaises(capture_tests.REFUSALS):
                        case.read()
                self.assertEqual(descriptors(), before)

    def test_caller_request_mutation_at_result_refuses(self):
        for selected in ("memo", "status", "committed", "marker"):
            with self.subTest(selected=selected), self.fixture() as case:
                target = case.case.live.memo if selected == "memo" \
                    else getattr(case, selected)
                before = descriptors()

                def mutate(_value):
                    target["late-caller-drift"] = True

                with case.no_effects(), self.at_result(case, mutate):
                    with self.assertRaises(capture_tests.REFUSALS):
                        case.read()
                self.assertEqual(descriptors(), before)

    def test_whole_request_capacity_is_checked_before_any_deepcopy(self):
        with self.fixture() as case:
            memo_raw = case.source_module.native_bytes(case.owner, case.case.live.memo)
            with case.no_effects(), \
                    mock.patch.object(case.lib, "MAX_MEMO_BYTES", len(memo_raw)), \
                    mock.patch.object(case.lib, "MAX_STATE_JSON_BYTES", len(memo_raw)), \
                    mock.patch.object(copy, "deepcopy", side_effect=AssertionError(
                        "over-budget compound request copied before admission")):
                with self.assertRaises(capture_tests.REFUSALS):
                    case.read()


if __name__ == "__main__":
    unittest.main(verbosity=2)
