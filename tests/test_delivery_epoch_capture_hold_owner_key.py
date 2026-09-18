"""Lifetime regression for the capture hold's notification-key basis.

The module-qualified fixture completes actual source ACK and epoch adoption
in temporary storage, then creates its real notification fence. During each
held lifetime only the owner's notification-key name changes. The memo,
marker, request, archive and epoch files remain untouched.

The same immutable owner basis must govern current(), read(), and normal
exit. This does not test hostile namespace injection, notification cursor
correctness, source-v3 output authority or any cognitive claim.
"""

import contextlib
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock


try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
from tests import test_delivery_epoch_capture_hold as capture_tests


class DeliveryEpochCaptureHoldOwnerKey(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        case = capture_tests.ControllerDeliveryEpochCaptureHold(methodName="runTest")
        try:
            case.setUp()
            with case.fenced() as fenced:
                yield case, fenced
        finally:
            case.doCleanups()

    def test_owner_notification_key_drift_refuses_at_every_held_boundary(self):
        with self.fixture() as (case, f):
            original_key = f.case.lib.NOTIFY_BASELINE_ATTEMPT_KEY
            alternate_key = "private_fixture_absent_notification_key"
            self.assertNotEqual(alternate_key, original_key)
            self.assertNotIn(alternate_key, f.case.live.memo)
            self.assertEqual(f.case.live.memo[original_key], f.marker)
            before = (case.images(f), copy.deepcopy(f.request))

            # Keep an independent caller file descriptor as well as the
            # caller's ordinary corpus-owner descriptor across every refusal.
            with Path(f.case.live.paths["MEMO_PATH"]).open("rb") as caller_file, \
                    case.no_effects(f):
                scope_fd = f.case.lib._CORPUS_OWNER_FD.get()
                scope_depth = f.case.lib._CORPUS_OWNER_DEPTH.get()
                self.assertIs(type(scope_fd), int)
                caller_fds = {
                    descriptor: capture_tests._scope_identity(descriptor)
                    for descriptor in (scope_fd, caller_file.fileno())
                }
                descriptors = case.fixture.fds()
                for boundary in ("current", "read", "normal-exit"):
                    with self.subTest(boundary=boundary):
                        held = None
                        try:
                            if boundary == "normal-exit":
                                with mock.patch.object(
                                        f.case.lib, "NOTIFY_BASELINE_ATTEMPT_KEY", original_key):
                                    with self.assertRaises(case.module.ControllerDeliveryEpochRefusal):
                                        with case.hold(f) as held:
                                            self.assertEqual(held.read(), f.expected)
                                            f.case.lib.NOTIFY_BASELINE_ATTEMPT_KEY = alternate_key
                                            # No explicit current/read after drift:
                                            # ordinary exit itself must detect it.
                            else:
                                with case.hold(f) as held:
                                    self.assertEqual(held.read(), f.expected)
                                    with mock.patch.object(
                                            f.case.lib, "NOTIFY_BASELINE_ATTEMPT_KEY", alternate_key):
                                        with self.assertRaises(case.module.ControllerDeliveryEpochRefusal):
                                            getattr(held, boundary)()
                                    # Restore only the owner name before this
                                    # case's otherwise ordinary context exit.
                                    self.assertEqual(
                                        f.case.lib.NOTIFY_BASELINE_ATTEMPT_KEY, original_key)
                        finally:
                            self.assertEqual(
                                f.case.lib.NOTIFY_BASELINE_ATTEMPT_KEY, original_key)
                            self.assertEqual(f.case.lib._CORPUS_OWNER_FD.get(), scope_fd)
                            self.assertEqual(f.case.lib._CORPUS_OWNER_DEPTH.get(), scope_depth)
                            for descriptor, identity in caller_fds.items():
                                self.assertEqual(capture_tests._scope_identity(descriptor), identity)
                            if held is not None:
                                case.fixture.closed(held)
                            self.assertEqual(case.fixture.fds(), descriptors)
                self.assertFalse(caller_file.closed)
            self.assertEqual((case.images(f), f.request), before)
            self.assertEqual(f.case.live.memo[original_key], f.marker)
            self.assertNotIn(alternate_key, f.case.live.memo)


if __name__ == "__main__":
    unittest.main()
