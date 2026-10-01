"""Actual output cuts and enclosing exits keep their original outcome.

Compose the root's acknowledged source/artifact/journal fixture. Process
stdout remains explicitly authored. Faults mutate retained plain caller
inputs only after the real selected sink operation or context exit; no
source, journal completion or success handle is manufactured.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import copy
import importlib
import unittest
from unittest import mock


class ControllerRecallOutputTail(unittest.TestCase):
    def setUp(self):
        primary = importlib.import_module("tests.test_controller_recall_output")
        self.primary = primary.ControllerRecallOutput(methodName="runTest")
        self.addCleanup(self.primary.doCleanups)
        self.primary.setUp()
        self.module = self.primary.module

    def cut(self, phase):
        primary = self.primary
        with primary.prepared() as j:
            initial = primary.inspected(j)
            authority = j.f.case.images()
            config = j.request["render_config"]
            original = copy.deepcopy(config)
            mutations = []
            case = self
            def mutate():
                case.assertEqual(mutations, [])
                # Exact native Boolean alias after a genuine sink operation.
                # Do not change source storage, output bytes or a test oracle.
                config["display_limit"] = True
                mutations.append(phase)
            class Sink(primary.journal_tests.ByteSink):
                def write(self, value):
                    result = super().write(value)
                    if phase == "write":
                        mutate()
                    return result
                def flush(self):
                    result = super().flush()
                    if phase == "flush":
                        mutate()
                    return result
            sink = Sink()
            clock = mock.Mock(side_effect=AssertionError("changed input sampled completion clock"))
            try:
                with self.assertRaises(self.module.ControllerRecallOutputRefusal) as caught:
                    primary.invoke(j, sink, clock)
            finally:
                config.clear()
                config.update(original)
            self.assertEqual(mutations, [phase])
            self.assertEqual(bytes(sink.body), j.body)
            self.assertEqual(sink.events, ["write"] if phase == "write" else ["write", "flush"])
            self.assertEqual(caught.exception.output_state,
                             "unknown" if phase == "write" else "completed-unrecorded")
            clock.assert_not_called()
            pending = primary.inspected(j)
            self.assertIs(pending["complete"], False)
            self.assertEqual(pending["records"], initial["records"])
            self.assertEqual(pending["pending"], [j.request["request_id"]])
            retry_sink = mock.Mock()
            retry_clock = mock.Mock(side_effect=AssertionError("pending retry sampled clock"))
            with self.assertRaises(self.module.ControllerRecallOutputRefusal):
                primary.invoke(j, retry_sink, retry_clock)
            retry_sink.write.assert_not_called()
            retry_sink.flush.assert_not_called()
            retry_clock.assert_not_called()
            self.assertEqual(primary.inspected(j), pending)
            self.assertEqual(j.f.case.images(), authority)

    def test_actual_write_then_changed_input_remains_unknown_without_resend(self):
        self.cut("write")

    def test_actual_flush_then_changed_input_remains_unrecorded_without_resend(self):
        self.cut("flush")

    def test_completed_retry_catches_later_projection_engine_epoch_and_corpus_exit_mutations(self):
        primary = self.primary
        with primary.prepared() as j:
            sink = primary.journal_tests.ByteSink()
            result = primary.invoke(j, sink, lambda: primary.writer_tests.COMPLETED_AT)
            self.assertEqual(bytes(sink.body), j.body)
            self.assertEqual(primary.inspected(j)["records"], [result["record"]])
            journal_before = primary.inspected(j)
            authority = j.f.case.images()
            config = j.request["render_config"]
            original = copy.deepcopy(config)
            for target in ("projection", "engine", "epoch", "corpus"):
                with self.subTest(target=target):
                    reached = []
                    j.completions.clear()
                    def after_exit(phase):
                        if phase == target:
                            self.assertEqual(reached, [])
                            self.assertEqual(j.completions, [result])
                            config["display_limit"] = True
                            reached.append(phase)
                    j.after_exit = after_exit
                    retry_sink = mock.Mock()
                    retry_clock = mock.Mock(side_effect=AssertionError("complete retry sampled clock"))
                    try:
                        with self.assertRaises(self.module.ControllerRecallOutputRefusal) as caught:
                            primary.invoke(j, retry_sink, retry_clock)
                    finally:
                        j.after_exit = None
                        config.clear()
                        config.update(original)
                    self.assertEqual(reached, [target])
                    self.assertEqual(j.completions, [result])
                    self.assertEqual(caught.exception.output_state, "completed-unrecorded")
                    retry_sink.write.assert_not_called()
                    retry_sink.flush.assert_not_called()
                    retry_clock.assert_not_called()
                    self.assertEqual(primary.inspected(j), journal_before)
                    self.assertEqual(j.f.case.images(), authority)


if __name__ == "__main__":
    unittest.main()
