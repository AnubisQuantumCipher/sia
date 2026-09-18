"""Real source/journal output composition with authored process premises.

The source generation, ACK, adoption, local artifact admission, entered
handles, ranking and journal write/flush are real controlled-fixture work.
The bounded child provider alone supplies GET/projection stdout: these are
not real indexed-page observations or gbrain execution. No result is a
machine-history benchmark, deployed CLI proof or cognitive warrant.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import contextlib
import copy
import importlib
import inspect
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


PARAMETERS = (
    "owner", "memo", "admitted_status", "retained_batch", "committed",
    "journal_limits", "expected_journal_limits_sha256", "expected_adoption_sha256",
    "engine_expectations", "expected_engine_expectations_sha256", "render_config",
    "expected_render_config_sha256", "subject", "timeout", "observed_at",
    "request_id", "binary_sink", "clock",
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))


GET_PREMISE = "Supplied caf\u00e9\x00 / cafe\u0301\u200b\n\tretained whitespace\r\n"
GET_GOLDEN = "Supplied caf\u00e9 / cafe\u0301\n\tretained whitespace\r\n"


class ControllerRecallOutput(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("siacontrollerrecalloutput")
        except ModuleNotFoundError as error:
            if error.name != "siacontrollerrecalloutput":
                raise
            self.fail("missing source-bound recall output compositor")
        self.call = getattr(self.module, "recall_and_deliver", None)
        self.assertTrue(callable(self.call), "missing recall-and-deliver API")
        self.projection_tests = importlib.import_module("tests.test_controller_recall_projection")
        self.journal_tests = importlib.import_module("tests.test_delivery_journal")
        self.writer_tests = importlib.import_module("tests.test_controller_delivery_writer")
        self.fixture = self.projection_tests.ControllerRecallProjection(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.writer = importlib.import_module("siacontrollerdeliverywriter")

    @contextlib.contextmanager
    def prepared(self):
        # Reuse only actual source/artifact setup. The projection fixture's
        # joined() intentionally forbids rank/output and is not used here.
        with self.fixture.completed() as f, self.fixture.source_owner(f) as core, \
                self.fixture.installed_paths(core) as (artifacts, expectations):
            state = f.generation["transition"]["state"]
            pages = [page for page in state["intake"]["pages"]
                     if page["version_sha256"] in state["intake"]["current_versions"]
                     and page["content"] and page["subject"] != "sia/cortex"]
            self.assertTrue(pages, "genuine current source required; do not invent an authority page")
            page = copy.deepcopy(pages[0])
            self.assertFalse(core._contains_legacy_jackal_assurance(page["content"]))
            limits = copy.deepcopy(self.fixture.rollover.epoch.limits)
            config = {"schema": "sia-controller-delivery-render-config-v1",
                      "selection": "rank-prefix-v1", "display_limit": 1,
                      "max_body_bytes": limits["max_body_bytes"]}
            request = {
                "memo": f.case.live.memo, "admitted_status": f.status,
                "retained_batch": f.retained, "committed": f.committed,
                "journal_limits": limits,
                "expected_journal_limits_sha256": self.fixture.live._sha(limits),
                "expected_adoption_sha256": f.adopted["expected_adoption_sha256"],
                "engine_expectations": expectations,
                "expected_engine_expectations_sha256": self.projection_tests.sha(
                    self.projection_tests.native(expectations)),
                "render_config": config,
                "expected_render_config_sha256": self.fixture.live._sha(config),
                "subject": page["subject"], "timeout": self.fixture.boundary_tests.TIMEOUT,
                "observed_at": state["observed_at"], "request_id": self.journal_tests.REQUEST_A,
            }
            j = SimpleNamespace(core=core, owner=core.__dict__, f=f, page=page,
                artifacts=artifacts, expectations=expectations, calls=[], requests=[],
                response_change=None, provider_stop=None, get_stdout=GET_PREMISE,
                request=request, active_epochs=[], active_engines=[], active_projections=[],
                projections=[], completions=[], after_exit=None, stderr="")
            j.projection_receipt = self.fixture.premise_tests.projection_premise(page, get_stdout=GET_PREMISE)
            j.body = ("[origin:" + page["origin"] + "] " + page["subject"] + "\n" + GET_GOLDEN).encode("utf-8")
            j.records = self.fixture.rollover.epoch.paths(f.retained, f.root)[-1]
            self.assertLess(request["observed_at"], self.writer_tests.COMPLETED_AT)
            with self.observed_scopes(j):
                yield j
            self.assertIsNone(core._CORPUS_OWNER_FD.get())
            self.assertIsNone(core._GBRAIN_OWNER_FD.get())
            self.assertIsNone(core._BRAINSTEM_OWNER_FD.get())

    @contextlib.contextmanager
    def observed_scopes(self, j):
        epoch_api, engine_api = self.fixture.epoch_api, self.fixture.engine_api
        projection_api = self.fixture.module
        original_epoch = epoch_api.hold_epoch
        original_engine = engine_api.hold_overlay_engine
        original_projection = projection_api.hold_recall_projection
        original_render = self.writer.render_and_deliver
        original_corpus = j.core.corpus_owner

        @contextlib.contextmanager
        def corpus(*args, **kwargs):
            outer = j.core._CORPUS_OWNER_FD.get() is None
            with original_corpus(*args, **kwargs) as held:
                yield held
            if outer and j.after_exit is not None:
                self.assertIsNone(j.core._CORPUS_OWNER_FD.get())
                j.after_exit("corpus")

        @contextlib.contextmanager
        def epoch(*args, **kwargs):
            with original_epoch(*args, **kwargs) as held:
                outer = not j.active_epochs
                if outer:
                    j.epoch = held
                    j.corpus_fd = j.core._CORPUS_OWNER_FD.get()
                j.active_epochs.append(held)
                try:
                    yield held
                finally:
                    j.active_epochs.remove(held)
            if outer and j.after_exit is not None:
                j.after_exit("epoch")

        @contextlib.contextmanager
        def engine(*args, **kwargs):
            with original_engine(*args, **kwargs) as held:
                j.engine = held
                j.active_engines.append(held)
                try:
                    yield held
                finally:
                    j.active_engines.remove(held)
            if j.after_exit is not None:
                j.after_exit("engine")

        @contextlib.contextmanager
        def projection(*args, **kwargs):
            with original_projection(*args, **kwargs) as held:
                j.active_projections.append(held)
                j.projections.append(held)
                try:
                    yield held
                finally:
                    j.active_projections.remove(held)
            if j.after_exit is not None:
                j.after_exit("projection")

        def render(*args, **kwargs):
            self.assert_active(j)
            self.assertEqual(kwargs["consumer"], "cli.recall")
            self.assertEqual(kwargs["committed"], j.f.committed)
            self.assertEqual(kwargs["expected_adoption_sha256"], j.request["expected_adoption_sha256"])
            result = original_render(*args, **kwargs)
            j.completions.append(result)
            return result

        def provider(*args, **kwargs):
            result = self.fixture.provider(j, *args, **kwargs)
            if args[0][1] == "get":
                result.stderr = j.stderr
            return result

        forbidden = mock.Mock(side_effect=AssertionError("recall output entered source writer or legacy path"))
        with contextlib.ExitStack() as stack:
            for owner in (j.core, j.f.case.lib):
                for name in ("brainstem_owner", "_write_memo", "save_cursors",
                             "_commit_sense_cursors", "_mark_notify_baseline_attempt",
                             "_clear_notify_baseline_attempt", "_acknowledge_controller_source_batch",
                             "export_status", "export_graph", "utcnow", "gbrain", "gbrain_call"):
                    stack.enter_context(mock.patch.object(owner, name, forbidden))
            for owner, name in ((epoch_api, "prepare_epoch"), (epoch_api, "hold_capturable_epoch"),
                                (self.fixture.source, "capture"),
                                (self.fixture.source, "capture_successor_v3"),
                                (self.writer, "deliver")):
                stack.enter_context(mock.patch.object(owner, name, forbidden))
            stack.enter_context(mock.patch.object(epoch_api, "hold_epoch", epoch))
            stack.enter_context(mock.patch.object(engine_api, "hold_overlay_engine", engine))
            stack.enter_context(mock.patch.object(projection_api, "hold_recall_projection", projection))
            stack.enter_context(mock.patch.object(self.writer, "render_and_deliver", render))
            stack.enter_context(mock.patch.object(j.core, "corpus_owner", corpus))
            stack.enter_context(mock.patch.object(j.core, "_run_bounded_text_process", side_effect=provider))
            yield
        forbidden.assert_not_called()

    def assert_active(self, j):
        self.assertTrue(j.active_epochs)
        self.assertTrue(j.active_engines)
        self.assertTrue(j.active_projections)
        for held in (*j.active_epochs, *j.active_engines, *j.active_projections):
            self.assertIsNone(held.current())
        os.fstat(j.corpus_fd)
        self.assertEqual(j.core._CORPUS_OWNER_FD.get(), j.corpus_fd)
        self.assertIsNone(j.core._BRAINSTEM_OWNER_FD.get())

    def invoke(self, j, sink, clock, **changes):
        return self.call(j.owner, **{**j.request, "binary_sink": sink, "clock": clock, **changes})

    def inspected(self, j):
        return self.fixture.rollover.capture.journal.inspect_deliveries(
            directory=str(j.records), epoch_id=j.f.generation["epoch_id"],
            limits=j.request["journal_limits"])

    def test_exact_mandatory_contract_and_no_new_completion_claim(self):
        parameters = inspect.signature(self.call).parameters
        self.assertEqual(tuple(parameters), PARAMETERS)
        for name, parameter in parameters.items():
            self.assertIs(parameter.default, inspect.Parameter.empty)
            self.assertEqual(parameter.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD
                             if name == "owner" else inspect.Parameter.KEYWORD_ONLY)
        prose = " ".join(self.module.NON_CLAIMS).lower()
        for expression in ("get", "origin", "journal", "human", "clock", "stderr", "held-out", "jackal"):
            self.assertIn(expression, prose)

    def test_actual_output_is_exact_origin_preserving_and_completed_retry_does_not_resend(self):
        with self.prepared() as j:
            case = self
            class Sink(self.journal_tests.ByteSink):
                def write(self, value):
                    case.assert_active(j)
                    return super().write(value)
                def flush(self):
                    case.assert_active(j)
                    return super().flush()
            sink = Sink(short=True)
            clocks = []
            def clock():
                self.assert_active(j)
                self.assertEqual(bytes(sink.body), j.body)
                self.assertEqual(sink.events[-1], "flush")
                clocks.append("actual-post-flush")
                return self.writer_tests.COMPLETED_AT
            authority = j.f.case.images()
            result = self.invoke(j, sink, clock)
            self.assertEqual(bytes(sink.body), j.body)
            self.assertEqual(clocks, ["actual-post-flush"])
            self.assertEqual(set(result), self.journal_tests.COMPLETION_KEYS)
            self.assertEqual(result["status"], "service-output-completed")
            self.assertEqual(result["boundary"], "write-all-and-flush-returned")
            self.assertEqual(result["non_claims"], list(self.fixture.rollover.capture.journal.NON_CLAIMS))
            self.assertEqual(result, j.completions[-1])
            record = result["record"]
            self.assertEqual(record["origin"], "derived")
            self.assertEqual(record["rows"], [{"row_ref": j.page["version_sha256"],
                "version_sha256": j.page["version_sha256"], "row": {
                    "slug": j.page["subject"], "origin": j.page["origin"],
                    "chunk_text": j.page["content"]}}])
            self.assertEqual(record["state_sha256"], j.f.generation["state_sha256"])
            before = self.inspected(j)
            self.assertIs(before["complete"], True)
            j.completions.clear()
            retry_sink, retry_clock = mock.Mock(), mock.Mock(side_effect=AssertionError("completed retry sampled clock"))
            retried = self.invoke(j, retry_sink, retry_clock)
            self.assertEqual(retried, result)
            self.assertEqual(j.completions, [result])
            retry_sink.write.assert_not_called()
            retry_sink.flush.assert_not_called()
            retry_clock.assert_not_called()
            self.assertEqual(self.inspected(j), before)
            self.assertEqual(j.f.case.images(), authority)

    def test_wrong_external_pin_or_nonempty_sanitized_stderr_cannot_write(self):
        with self.prepared() as j:
            before = self.inspected(j)
            for mode in ("engine-pin", "render-pin", "stderr"):
                with self.subTest(mode=mode):
                    sink, clock = mock.Mock(), mock.Mock(side_effect=AssertionError("refused body sampled clock"))
                    changes = {}
                    if mode == "engine-pin":
                        changes["expected_engine_expectations_sha256"] = self.projection_tests.sha(b"wrong external engine pin")
                    elif mode == "render-pin":
                        changes["expected_render_config_sha256"] = self.projection_tests.sha(b"wrong external render pin")
                    else:
                        j.stderr = "Retained engine warning\n"
                    try:
                        with self.assertRaises(self.module.ControllerRecallOutputRefusal) as caught:
                            self.invoke(j, sink, clock, **changes)
                    finally:
                        j.stderr = ""
                    self.assertEqual(caught.exception.output_state, "not-started")
                    sink.write.assert_not_called()
                    sink.flush.assert_not_called()
                    clock.assert_not_called()
                    self.assertEqual(self.inspected(j), before)


if __name__ == "__main__":
    unittest.main()
