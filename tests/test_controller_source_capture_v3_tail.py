"""Source-v3 final-tail regressions over the actual acknowledged fixture.

These controls keep the real source capture, epoch/journal descriptors and
their normal exits. They mutate only detached process values through the
existing copy/exit seams, not disk authority or manufactured source history.
Root alone runs this module sequentially; these are local lifetime contracts,
not source truth, durability, output permission or cognitive evidence.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import copy
import unittest
from unittest import mock

from tests import test_controller_source_capture_v3 as capture_tests


class ControllerSourceCaptureV3Tail(unittest.TestCase):
    def setUp(self):
        # Compose the real fixture without subclassing it or importing its
        # TestCase into this module's discovery namespace.
        self.fixture = capture_tests.ControllerSourceCaptureV3(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    def test_detached_result_mutation_during_epoch_exit_refuses_before_final_sweep(self):
        case = self.fixture
        with case.prepared() as f, case.capture_owner(f) as owner:
            before = case.images(f)
            copied = []
            changed = []
            trace = None

            def change_after_final_copy():
                if changed:
                    return
                self.assertIsNotNone(trace)
                self.assertTrue(trace.active_epochs)
                self.assertFalse(trace.active_journals)
                self.assertFalse(trace.swept)
                self.assertTrue(copied, "epoch exited before actual source-v3 detachment")
                # This is the exact object returned by the real final copy,
                # not the source input, wrapper builder's output or a fake
                # v3 predecessor. Preserve its old pin to expose stale output.
                detached = copied[-1]
                self.assertEqual(detached["status"], "captured-not-published")
                detached["status"] = "mutated-during-epoch-exit"
                changed.append(True)

            with case.no_effects(f, owner):
                descriptors = case.fd_fixture.fds()
                with case.lifetime(f, at_epoch_exit=change_after_final_copy) as trace:
                    actual_copy = copy.deepcopy

                    def retain_copy(value, *args, **kwargs):
                        self.assertFalse(trace.swept, "copy followed the final named sweep")
                        result = actual_copy(value, *args, **kwargs)
                        if type(value) is dict and value.get("schema") == capture_tests.SCHEMA:
                            self.assertIsNot(result, value)
                            copied.append(result)
                        return result

                    with mock.patch.object(copy, "deepcopy", retain_copy), \
                            self.assertRaises(capture_tests.REFUSALS):
                        case.operation(owner.__dict__, **f.request)
                self.assertEqual(case.fd_fixture.fds(), descriptors)
            self.assertTrue(changed, "the real final epoch-exit mutation did not run")
            self.assertFalse(trace.swept, "mutated detached output reached the final sweep")
            self.assertEqual(case.images(f), before)

    def test_owner_scalar_drift_during_post_exit_epoch_serialization_refuses(self):
        case = self.fixture
        for selected in ("CONTROLLER_DELIVERY_EPOCH_ROOT", "MAX_STATE_JSON_BYTES",
                         "NOTIFY_BASELINE_ATTEMPT_KEY"):
            with self.subTest(selected=selected), case.prepared() as f, \
                    case.capture_owner(f) as owner:
                before = case.images(f)
                original_value = getattr(owner, selected)
                replacement = owner.MAX_CONFIG_BYTES if selected == "MAX_STATE_JSON_BYTES" \
                    else original_value + "-unadmitted-tail"
                self.assertNotEqual(original_value, replacement)
                changed = []
                original_native = case.source.native_bytes

                with case.no_effects(f, owner):
                    descriptors = case.fd_fixture.fds()
                    with case.lifetime(f) as trace:

                        def native_then_change(owner_map, value, ceiling=None):
                            self.assertFalse(trace.swept,
                                "serialization followed the final named sweep")
                            raw = original_native(owner_map, value, ceiling=ceiling)
                            if not changed and value is f.request["epoch"] \
                                    and "copy-v3" in trace.steps \
                                    and not trace.active_epochs and not trace.active_journals:
                                # Require actual retirement, not just the
                                # fixture wrapper's removal from its roster.
                                for held in (*trace.epochs, *trace.journals):
                                    with self.assertRaises(capture_tests.REFUSALS):
                                        held.current()
                                self.assertIs(owner_map, owner.__dict__)
                                self.assertEqual(getattr(owner, selected), original_value)
                                setattr(owner, selected, replacement)
                                changed.append(True)
                            return raw

                        # Restore the owner before fixture observations or
                        # cleanup, even when the expected RED lacks refusal.
                        with mock.patch.object(owner, selected, original_value), \
                                mock.patch.object(case.source, "native_bytes",
                                                  native_then_change), \
                                self.assertRaises(capture_tests.REFUSALS):
                            case.operation(owner.__dict__, **f.request)
                    self.assertEqual(case.fd_fixture.fds(), descriptors)
                self.assertTrue(changed,
                    "the real post-exit epoch serialization did not reach the injection")
                self.assertFalse(trace.swept, "owner drift reached the final named sweep")
                self.assertEqual(getattr(owner, selected), original_value)
                self.assertEqual(case.images(f), before)


if __name__ == "__main__":
    unittest.main()
