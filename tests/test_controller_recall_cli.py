"""Front-door composition for one source-authorized ordinary CLI recall.

The source-v3 completion, live generation, installed engine expectations,
journal limits and literal render policy come from actual fixture state.  The
caller supplies only the CLI operation inputs and sink.  This does not alter
the installed runtime or claim a deployed live loop or cognitive win.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import importlib
import inspect
from pathlib import Path
import sys
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

PARAMETERS = (
    "owner", "subject", "timeout", "request_id", "binary_sink", "clock",
)


class ControllerRecallCli(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("siacontrollerrecallcli")
        except ModuleNotFoundError as error:
            if error.name != "siacontrollerrecallcli":
                raise
            self.fail("missing CLI recall authority compositor")
        self.run = getattr(self.module, "recall_from_current_source", None)
        self.assertTrue(callable(self.run), "missing CLI recall compositor API")
        output_tests = importlib.import_module("tests.test_controller_recall_output")
        self.output_test = output_tests.ControllerRecallOutput(methodName="runTest")
        self.addCleanup(self.output_test.doCleanups)
        self.output_test.setUp()
        self.output = self.output_test.module
        self.live = importlib.import_module("sialiveloop")
        self.journal = importlib.import_module("siadelivery")

    def invoke(self, j, sink, clock, **changes):
        request = {
            "owner": j.owner, "subject": j.page["subject"],
            "timeout": self.output_test.fixture.boundary_tests.TIMEOUT,
            "request_id": self.output_test.journal_tests.REQUEST_A,
            "binary_sink": sink, "clock": clock,
        }
        return self.run(**{**request, **changes})

    def test_exact_small_api_derives_and_joins_every_authority_input(self):
        self.assertEqual(tuple(inspect.signature(self.run).parameters), PARAMETERS)
        with self.output_test.prepared() as j:
            sink = self.output_test.journal_tests.ByteSink()
            original = self.output.recall_and_deliver
            calls = []

            def observed(*args, **kwargs):
                calls.append((args, kwargs))
                return original(*args, **kwargs)

            with mock.patch.object(
                    self.output, "recall_and_deliver", side_effect=observed):
                result = self.invoke(
                    j, sink, lambda: self.output_test.writer_tests.COMPLETED_AT)
            self.assertEqual(bytes(sink.body), j.body)
            self.assertEqual(len(calls), 1)
            args, supplied = calls[0]
            self.assertEqual(args, (j.owner,))
            self.assertEqual(set(supplied), {
                "memo", "admitted_status", "retained_batch", "committed",
                "journal_limits", "expected_journal_limits_sha256",
                "expected_adoption_sha256", "engine_expectations",
                "expected_engine_expectations_sha256", "render_config",
                "expected_render_config_sha256", "subject", "timeout",
                "observed_at", "request_id", "binary_sink", "clock",
            })
            self.assertEqual(supplied["memo"], j.f.case.live.memo)
            self.assertEqual(supplied["admitted_status"], j.f.status)
            self.assertEqual(supplied["retained_batch"], j.f.retained)
            self.assertEqual(supplied["committed"], j.f.committed)
            self.assertEqual(supplied["journal_limits"], self.journal._LIMITS)
            self.assertEqual(
                supplied["expected_journal_limits_sha256"],
                self.live._sha(self.journal._LIMITS))
            self.assertEqual(
                supplied["expected_adoption_sha256"],
                j.f.adopted["expected_adoption_sha256"])
            self.assertEqual(supplied["engine_expectations"], j.expectations)
            self.assertEqual(
                supplied["expected_engine_expectations_sha256"],
                self.live._sha(j.expectations))
            self.assertEqual(supplied["render_config"], {
                "schema": "sia-controller-delivery-render-config-v1",
                "selection": "rank-prefix-v1", "display_limit": 1,
                "max_body_bytes": self.journal._LIMITS["max_body_bytes"],
            })
            self.assertEqual(
                supplied["expected_render_config_sha256"],
                self.live._sha(supplied["render_config"]))
            self.assertEqual(
                supplied["observed_at"],
                j.f.generation["transition"]["state"]["observed_at"])
            self.assertEqual(supplied["subject"], j.page["subject"])
            self.assertIs(supplied["binary_sink"], sink)
            self.assertIs(result, j.completions[0])

    def test_incomplete_source_or_changed_installed_artifact_refuses_without_output(self):
        with self.output_test.prepared() as j:
            sink = mock.Mock()
            clock = mock.Mock()
            with mock.patch.object(
                    j.core, "load_memo", return_value={}), \
                    mock.patch.object(self.output, "recall_and_deliver") as output:
                with self.assertRaises(self.module.ControllerRecallCliRefusal):
                    self.invoke(j, sink, clock)
            output.assert_not_called()
            sink.write.assert_not_called()
            sink.flush.assert_not_called()
            clock.assert_not_called()

        with self.output_test.prepared() as j:
            j.artifacts.release_receipt.write_bytes(b"changed runtime receipt\n")
            sink = mock.Mock()
            clock = mock.Mock()
            with mock.patch.object(self.output, "recall_and_deliver") as output:
                with self.assertRaises(self.module.ControllerRecallCliRefusal):
                    self.invoke(j, sink, clock)
            output.assert_not_called()
            sink.write.assert_not_called()
            sink.flush.assert_not_called()
            clock.assert_not_called()

    def test_bad_caller_operation_contract_refuses_before_any_owner_or_output(self):
        owner = {"corpus_owner": mock.Mock()}
        for change in (
                {"owner": None}, {"subject": "../escape"}, {"timeout": True},
                {"request_id": "not-an-id"}, {"binary_sink": None},
                {"clock": None}):
            with self.subTest(change=change), \
                    mock.patch.object(self.output, "recall_and_deliver") as output:
                request = {
                    "owner": owner, "subject": "events/test/day", "timeout": 1,
                    "request_id": "0" * 32, "binary_sink": mock.Mock(
                        write=mock.Mock(), flush=mock.Mock()),
                    "clock": mock.Mock(),
                }
                request.update(change)
                with self.assertRaises(self.module.ControllerRecallCliRefusal):
                    self.run(**request)
                output.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
