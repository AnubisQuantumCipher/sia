"""Initial-capture history controls.

The current fixed pending slot has no committed source archive lifecycle.
These controls do not declare continuation permanently unavailable. They
require initial acquisition to refuse caller-supplied prior authority until
that separate durable continuation boundary exists.
"""

import contextlib
import copy
import functools
from pathlib import Path
import unittest
from unittest import mock

from tests import test_controller_source_capture as capture_tests


class ControllerSourceInitialHistory(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        case = capture_tests.ControllerSourceCapture(methodName="runTest")
        try:
            case.setUp()
            yield case
        finally:
            case.doCleanups()

    @contextlib.contextmanager
    def no_new_collector(self, case):
        @functools.wraps(case.lib.sense_aegis)
        def native(*_args, **_kwargs):
            raise AssertionError("unbound prior source authority reached native acquisition")

        @functools.wraps(case.lib.sense_custom)
        def custom(*_args, **_kwargs):
            raise AssertionError("unbound prior source authority reached custom acquisition")

        # Coherent, same-name initial runtime roster: a refusal cannot pass
        # merely because a patched exported collector differs from SENSES.
        with mock.patch.object(case.lib, "sense_aegis", native), \
                mock.patch.object(case.lib, "sense_custom", custom), \
                mock.patch.object(case.lib, "SENSES", [native, custom]):
            yield

    def test_initial_capture_refuses_complete_uncommitted_history_or_predecessor(self):
        for supplied in ("history", "predecessor", "both"):
            with self.subTest(supplied=supplied), self.fixture() as case:
                captured = case.capture()
                case.assert_batch(captured)
                assembled = case.assembled_request(captured)
                # The predecessor history is a complete actual capture's
                # already-admitted pure request, not malformed placeholder
                # records or a fabricated collector-success claim.
                self.assertTrue(assembled["history"]["entries"])
                self.assertEqual(capture_tests.canonical(case.bridge.project(assembled)),
                                 capture_tests.canonical(captured["intake_projection"]))
                if supplied in ("history", "both"):
                    case.epoch["history"] = copy.deepcopy(assembled["history"])
                if supplied in ("predecessor", "both"):
                    case.epoch["predecessor"] = {
                        "source_batch_sha256": captured["batch_sha256"],
                        # Syntactically a digest, intentionally not an
                        # observed committed live-generation identity.
                        "live_generation_sha256": captured["intake_projection"]["intake_sha256"],
                    }
                case.reseal_epoch()
                before = case.inert_before()
                with self.no_new_collector(case):
                    error = case.assert_named_refusal(case.capture, phase="admit")
                self.assertEqual(error.reason, "unbound-prior-source-history")
                case.assert_inert(before)

    def test_caller_written_source_committed_marker_is_not_initial_history_authority(self):
        with self.fixture() as case:
            captured = case.capture()
            case.assert_batch(captured)
            case.memo["controller_source_committed"] = {
                "source_batch_sha256": captured["batch_sha256"],
                "live_generation_sha256": captured["intake_projection"]["intake_sha256"],
            }
            # Persist the same synthetic caller assertion so this control
            # does not depend on an incidental in-memory/durable mismatch.
            # No committed source archive or admitted live generation exists.
            Path(case.lib.MEMO_PATH).write_bytes(capture_tests.canonical(case.memo))
            before = case.inert_before()
            with self.no_new_collector(case):
                error = case.assert_named_refusal(case.capture, phase="admit")
            self.assertEqual(error.reason, "unbound-prior-source-history")
            case.assert_inert(before)
