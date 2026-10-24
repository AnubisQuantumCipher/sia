"""Detachable cockpit dispatch, acknowledgment and single-instance contracts."""
from tests import sia_test_home  # noqa: F401 -- isolate before runtime import

import contextlib
import importlib.machinery
import importlib.util
import io
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from tests.test_cockpit_boundary_horizon import _qml_element, _qml_function


REPO = Path(__file__).resolve().parent.parent


def load_cli():
    loader = importlib.machinery.SourceFileLoader(
        "sia_cockpit_window_test", str(REPO / "bin/sia"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class CockpitWindowCliTests(unittest.TestCase):
    def setUp(self):
        self.cli = load_cli()
        self.active = False
        self.events = []

    @contextlib.contextmanager
    def lease(self):
        self.active = True
        self.events.append("enter")
        try:
            yield
        finally:
            self.events.append("leave")
            self.active = False

    def invoke(self, arguments, result=None, error=None):
        def call(command, **options):
            self.assertTrue(self.active)
            self.events.append("ipc")
            self.assertEqual(command[:5], [
                "omarchy-shell", "shell", "call", "khephri.sia",
                "showPresentation"])
            self.assertEqual(options["output_limit"], 4096)
            self.assertEqual(options["timeout"], 6)
            self.assertNotIn("shell", options)
            if error is not None:
                raise error
            return result

        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(self.cli.sialib, "_lifecycle_reader", self.lease), \
                mock.patch.object(self.cli.sialib, "_run_bounded_text_process",
                                  side_effect=call) as ipc, \
                mock.patch.object(self.cli.sialib, "memory_readiness",
                                  side_effect=AssertionError("UI is recovery-readable")), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = self.cli.main(["sia", "cockpit", *arguments])
        return code, output.getvalue(), errors.getvalue(), ipc

    def test_each_presentation_uses_one_call_inside_the_lifecycle_lease(self):
        for args, mode in (([], "overlay"), (["--overlay"], "overlay"),
                           (["--window"], "window")):
            with self.subTest(args=args):
                self.events.clear()
                response = subprocess.CompletedProcess(
                    [], 0, "sia-cockpit-v1:" + mode + "\n", "")
                code, output, errors, ipc = self.invoke(args, response)
                self.assertEqual((code, errors), (0, ""))
                self.assertIn(mode + " requested", output)
                self.assertEqual(ipc.call_args.args[0][-1], mode)
                self.assertEqual(ipc.call_count, 1)
                self.assertEqual(self.events, ["enter", "ipc", "leave"])

    def test_bad_arguments_never_reach_ipc(self):
        for args in (["--window", "--window"], ["--window", "--overlay"],
                     ["--unknown"], ["window"], ["--window", "extra"]):
            with self.subTest(args=args):
                code, output, errors, ipc = self.invoke(args)
                self.assertEqual(code, 2)
                self.assertEqual(output, "")
                self.assertIn("usage:", errors)
                ipc.assert_not_called()

    def test_exact_receipt_and_success_status_are_both_required(self):
        for status, text in ((0, "ok"), (0, "unknown"), (0, ""),
                             (0, "sia-cockpit-v1:overlay"),
                             (0, "sia-cockpit-v2:window"),
                             (1, "sia-cockpit-v1:window"),
                             (0, "sia-cockpit-v1:window\nextra")):
            with self.subTest(status=status, text=text):
                response = subprocess.CompletedProcess([], status, text, "")
                code, output, errors, ipc = self.invoke(["--window"], response)
                self.assertEqual(code, 1)
                self.assertEqual(output, "")
                self.assertIn("not confirmed", errors)
                self.assertEqual(ipc.call_count, 1)

    def test_failures_and_uncertain_timeouts_are_not_retried(self):
        for error in (FileNotFoundError(), OverflowError(),
                      UnicodeError(), RuntimeError(),
                      subprocess.TimeoutExpired("fixture", 6)):
            with self.subTest(error=type(error).__name__):
                code, output, errors, ipc = self.invoke(["--window"], error=error)
                self.assertEqual(code, 1)
                self.assertEqual(output, "")
                self.assertIn("may still have opened", errors)
                self.assertEqual(ipc.call_count, 1)


class CockpitWindowStructureTests(unittest.TestCase):
    """Wiring controls; actual window lifecycle needs the Quickshell smoke test."""

    def test_one_visual_tree_and_existing_reader(self):
        source = (REPO / "Cockpit.qml").read_text(encoding="utf-8")
        self.assertEqual(source.count('import "Model.js" as Model'), 1)
        self.assertEqual(source.count("id: keyCatcher"), 1)
        self.assertEqual(source.count("id: liveLoopView"), 1)
        content = _qml_element(source, "id: keyCatcher")
        self.assertIn("parent: root.windowed ? detachedWindow.contentItem"
                      " : win.contentItem", content)
        native = _qml_element(source, "id: detachedWindow")
        self.assertIn("root.dismiss()", native)
        overlay = _qml_element(source, "id: win")
        self.assertIn("visible: root.cockpitVisible && !root.windowed", overlay)
        self.assertIn("visible: root.cockpitVisible && root.windowed", native)

    def test_repeat_presentation_does_not_reset_operation_state(self):
        source = (REPO / "Cockpit.qml").read_text(encoding="utf-8")
        method = _qml_function(source, "showPresentation")
        self.assertIn('presentation !== "window" && presentation !== "overlay"',
                      method)
        self.assertIn("if (!root.opened)", method)
        self.assertNotIn("root.close(", method)
        self.assertNotIn("root.open(", method)
        self.assertNotIn("restoreRequestId =", method)
        self.assertNotIn("restoreConfirmOpen =", method)
        self.assertNotIn("execDetached", method)
