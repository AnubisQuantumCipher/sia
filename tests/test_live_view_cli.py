"""Public CLI visibility for the source-authorized live-loop view -- RED.

The CLI uses the composed acknowledged-source fixture, not an invented view.
Its JSON endpoint remains readable during recovery, under the lifecycle lease,
and reports named refusal when source authority cannot be rejoined. Ordinary
status/think text exposes the retained workspace and selection reasons while
keeping the existing generated-entry output and its origins.

This is CLI dispatch/rendering evidence, not QML rendering, live deployment,
human receipt, biological cognition or a held-out retrieval result. Root alone
runs this module sequentially under the mission memory cap.
"""

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

import contextlib
import importlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest import mock

from tests import test_live_view as view_tests


REPO = Path(__file__).resolve().parent.parent


def _load_cli():
    loader = importlib.machinery.SourceFileLoader(
        "sia_live_view_cli_test", str(REPO / "bin/sia"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class LiveViewCli(unittest.TestCase):
    def setUp(self):
        self.cli = _load_cli()
        self.view = importlib.import_module("sialiveview")
        self.fixture = view_tests.SourceAuthorizedLiveView(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)

    @contextlib.contextmanager
    def completed(self):
        with self.fixture.completed() as case, \
                mock.patch.object(self.cli, "sialib", case.lib), \
                self.fixture.read_only(case):
            yield case

    def invoke(self, arguments):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = self.cli.main(["sia", *arguments])
        return result, output.getvalue(), errors.getvalue()

    def render(self, operation):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            result = operation()
        return result, output.getvalue(), errors.getvalue()

    def publish_cache(self, case):
        # The shared completed() fixture forbids every writer after ACK. The
        # cache publisher itself is exercised by test_live_view; CLI tests
        # seed those exact admitted bytes without crossing an ACK boundary.
        value = self.view.read_view(case.lib.__dict__)
        case.live._write(
            str(Path(case.lib.STATE) / self.view.CACHE_BASENAME), value)
        return value

    def test_live_json_keeps_lifecycle_lease_without_general_readiness_gate(self):
        with self.completed() as case:
            events = []
            active = []
            self.publish_cache(case)

            @contextlib.contextmanager
            def lifecycle():
                events.append("lifecycle-enter")
                active.append(True)
                try:
                    yield
                finally:
                    active.pop()
                    events.append("lifecycle-exit")

            original = self.view.read_cached_view

            def inspect(owner):
                self.assertTrue(active, "source inspection must hold lifecycle ownership")
                self.assertIs(owner, case.lib.__dict__)
                events.append("live-read")
                return original(owner)

            with mock.patch.object(case.lib, "_lifecycle_reader", lifecycle), \
                    mock.patch.object(self.view, "read_cached_view", side_effect=inspect), \
                    mock.patch.object(case.lib, "memory_readiness", side_effect=AssertionError(
                        "live inspection is recovery-readable")):
                result, text, errors = self.invoke(["live", "--json"])
            self.assertEqual(result, 0, text + errors)
            self.assertEqual(events, ["lifecycle-enter", "live-read", "lifecycle-exit"])
            self.assertEqual(json.loads(text)["status"], "available")
            self.assertNotIn("live", self.cli.READINESS_GATED_COMMANDS)
            self.assertIn("ask", self.cli.READINESS_GATED_COMMANDS)
            self.assertNotIn("think", self.cli.READINESS_GATED_COMMANDS)

    def test_live_json_returns_the_exact_revalidated_view_without_extra_stdout(self):
        with self.completed() as case:
            expected = self.view.read_view(case.lib.__dict__)
            self.publish_cache(case)
            before = self.fixture.images(case)
            with mock.patch.object(case.lib, "_lifecycle_reader", contextlib.nullcontext):
                result, text, errors = self.invoke(["live", "--json"])
            self.assertEqual(result, 0, text + errors)
            self.assertEqual(json.loads(text), expected)
            self.assertEqual(errors, "")
            self.assertEqual(self.fixture.images(case), before)

    def test_live_json_reads_published_cache_without_corpus_owner(self):
        self.assertTrue(callable(getattr(self.view, "publish_cache", None)),
                        "missing source-authorized live-view cache publisher")
        self.assertTrue(callable(getattr(self.view, "read_cached_view", None)),
                        "missing nonblocking live-view cache reader")
        with self.completed() as case:
            expected = self.publish_cache(case)
            with mock.patch.object(
                    case.lib, "corpus_owner", side_effect=AssertionError(
                        "live JSON reacquired the resident writer lease")), \
                    mock.patch.object(
                        self.view, "read_view", side_effect=AssertionError(
                            "live JSON bypassed the published view cache")):
                result, text, errors = self.invoke(["live", "--json"])
            self.assertEqual(result, 0, text + errors)
            self.assertEqual(json.loads(text), expected)
            self.assertEqual(errors, "")

    def test_live_unknown_duplicate_and_extra_arguments_refuse_before_source_read(self):
        for arguments in (["live", "--unknown"], ["live", "--json", "--json"],
                          ["live", "--json", "extra"], ["live", "--unsafe"]):
            with self.subTest(arguments=arguments), \
                    mock.patch.object(self.cli.sialib, "_lifecycle_reader", contextlib.nullcontext), \
                    mock.patch.object(self.view, "read_cached_view", side_effect=AssertionError(
                        "invalid arguments reached source inspection")):
                result, text, _errors = self.invoke(arguments)
            self.assertEqual(result, 2)
            self.assertIn("usage: sia live", text)

    def test_live_json_refusal_remains_machine_readable_and_carries_boundary(self):
        refusal = self.view.LiveViewRefusal("fixture-source-authority-refused")
        with mock.patch.object(self.cli.sialib, "_lifecycle_reader", contextlib.nullcontext), \
                mock.patch.object(self.view, "read_cached_view", side_effect=refusal):
            result, text, _errors = self.invoke(["live", "--json"])
        self.assertEqual(result, 1)
        value = json.loads(text)
        self.assertEqual(value["schema"], "sia-controller-live-view-refusal-v1")
        self.assertEqual(value["status"], "refused")
        self.assertEqual(value["reason"], refusal.reason)
        self.assertEqual(value["non_claims"], list(self.view.NON_CLAIMS))
        self.assertNotIn("workspace", value)
        self.assertNotIn("generation", value)

    def test_live_json_lifecycle_refusal_is_closed_and_does_not_expose_exception_text(self):
        private = "private-fixture-path-and-secret-shaped-error"
        with mock.patch.object(self.cli.sialib, "_lifecycle_reader", side_effect=RuntimeError(private)), \
                mock.patch.object(self.view, "read_cached_view", side_effect=AssertionError(
                    "failed lifecycle reached source inspection")):
            result, text, errors = self.invoke(["live", "--json"])
        self.assertEqual(result, 1)
        value = json.loads(text)
        self.assertEqual(value["status"], "refused")
        self.assertEqual(value["reason"], "lifecycle-unavailable")
        self.assertEqual(value["non_claims"], list(self.view.NON_CLAIMS))
        self.assertNotIn(private, text + errors)

    def assert_workspace_text(self, text, expected):
        self.assertIn("live", text.lower())
        self.assertIn("workspace", text.lower())
        self.assertIn("retained", text.lower())
        self.assertIn("computed-unverified", text)
        self.assertIn(expected["workspace"]["transition"], text)
        self.assertIn(str(expected["as_of"]), text)
        for subject in expected["workspace"]["slots"]:
            self.assertIn(subject, text)
        self.assertNotIn("artifact_json", text)
        self.assertNotIn("payload_json", text)
        self.assertNotIn("final_counts", text)

    def test_status_includes_source_workspace_and_selection_reason(self):
        with self.completed() as case, \
                mock.patch.object(case.lib, "memory_readiness", return_value=(True, "")):
            expected = self.view.read_view(case.lib.__dict__)
            self.publish_cache(case)
            result, text, errors = self.render(self.cli.cmd_status)
            self.assertEqual(result, 0, text + errors)
            self.assert_workspace_text(text, expected)
            self.assertIn("readiness READY", text)

    def test_status_during_resident_pulse_returns_cached_workspace_without_waiting(self):
        with self.completed() as case:
            expected = self.publish_cache(case)
            with mock.patch.object(
                    self.cli, "_corpus_owner_nowait",
                    side_effect=case.lib.OwnerBusy("fixture resident pulse")), \
                    mock.patch.object(
                        case.lib, "corpus_owner", side_effect=AssertionError(
                            "busy status waited for the resident writer lease")):
                result, text, errors = self.render(self.cli.cmd_status)
            self.assertEqual(result, 0, text + errors)
            self.assertIn("resident pulse in progress", text)
            self.assertIn("readiness check deferred", text)
            self.assert_workspace_text(text, expected)

    def test_think_includes_same_workspace_and_keeps_generated_entry_origin(self):
        thought = {"ts": "2026-09-06T12:00:03Z", "kind": "note",
                   "text": "fixture generated entry", "origin": "model", "urgent": False}
        with self.completed() as case, \
                mock.patch.object(case.lib, "load_thoughts", return_value={"thoughts": [thought]}):
            expected = self.view.read_view(case.lib.__dict__)
            self.publish_cache(case)
            result, text, errors = self.render(self.cli.cmd_think)
            self.assertEqual(result, 0, text + errors)
            self.assert_workspace_text(text, expected)
            self.assertIn("[origin:model]", text)
            self.assertIn(thought["text"], text)

    def test_status_and_think_do_not_fill_refused_source_view_from_legacy_workspace(self):
        for operation_name in ("cmd_status", "cmd_think"):
            with self.subTest(operation=operation_name), self.completed() as case:
                status = case.admitted_status()
                stale = "events/legacy-policy-stale"
                status["workspace"] = [stale]
                case.live._write(case.live.paths["STATUS_PATH"], status)
                with mock.patch.object(case.lib, "memory_readiness", return_value=(False, "fixture pending")), \
                        mock.patch.object(case.lib, "load_thoughts", return_value={"thoughts": []}):
                    _result, text, errors = self.render(getattr(self.cli, operation_name))
                self.assertIn("live", text.lower())
                self.assertIn("refused", text.lower())
                self.assertNotIn(stale, text + errors)


if __name__ == "__main__":
    unittest.main()
