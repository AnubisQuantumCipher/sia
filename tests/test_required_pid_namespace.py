"""Deterministic namespace-required launch routing; no child execution.

Popen is intercepted in every launch test. These controls check admission and
exact launcher selection, not actual namespace creation/private procfs or
host descendant containment. Existing real namespace controls remain separate.
"""

import importlib
import os
import subprocess
import unittest
from unittest import mock

from tests import sia_test_home
from tests import test_raw_vector_transport as transport_tests


class _LaunchObserved(RuntimeError):
    """The mock intercepted Popen before any external process executed."""


class RequiredPidNamespace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.process = importlib.import_module("siaprocess")
        cls.lib = importlib.import_module("sialib")

    def setUp(self):
        self.assertEqual(self.lib.SHARE, os.path.join(
            sia_test_home.ISOLATED_HOME, ".local/share/sia"))

    def _run(self, *, isolation="pid-namespace", **options):
        return self.process.run_bounded_text_process(
            ["fixture-command", "fixture-argument"], env={}, timeout=1,
            cwd="/", limits={
                "MAX_SOURCE_NAME_CHARS": self.lib.MAX_SOURCE_NAME_CHARS,
                "MAX_EXTERNAL_OUTPUT_BYTES": self.lib.MAX_EXTERNAL_OUTPUT_BYTES,
                "MAX_STATE_JSON_BYTES": self.lib.MAX_STATE_JSON_BYTES,
                "MAX_CONFIG_BYTES": self.lib.MAX_CONFIG_BYTES,
                "JOURNAL_TIMEOUT_SECONDS": self.lib.JOURNAL_TIMEOUT_SECONDS},
            isolation=isolation, await_exit=mock.Mock(), reap_group=mock.Mock(),
            **options)

    def test_required_namespace_selects_exact_launcher_without_execution(self):
        with mock.patch.object(self.process.subprocess, "Popen",
                               side_effect=_LaunchObserved) as launch, \
                self.assertRaises(_LaunchObserved):
            self._run(isolate_process_tree=True, require_pid_namespace=True)
        launch.assert_called_once()
        self.assertEqual(launch.call_args.args[0], [
            self.process.UNSHARE, "--user", "--map-root-user", "--pid",
            "--fork", "--kill-child", "--mount-proc", "--",
            "fixture-command", "fixture-argument"])
        self.assertIs(launch.call_args.kwargs["start_new_session"], True)
        self.assertIs(launch.call_args.kwargs["close_fds"], True)
        self.assertEqual(launch.call_args.kwargs["pass_fds"], ())
        self.assertEqual(launch.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_required_namespace_unavailable_or_malformed_refuses_before_popen(self):
        modes = ("process-group", "", "PID-namespace", None, True, 1,
                 b"pid-namespace", [], {})
        for mode in modes:
            with self.subTest(mode=mode), mock.patch.object(
                    self.process.subprocess, "Popen") as launch, \
                    self.assertRaisesRegex(ValueError,
                                           "requires PID-namespace isolation"):
                self._run(isolation=mode, isolate_process_tree=True,
                          require_pid_namespace=True)
            launch.assert_not_called()

    def test_required_namespace_refuses_disabled_isolation_before_popen(self):
        with mock.patch.object(self.process.subprocess, "Popen") as launch, \
                self.assertRaisesRegex(ValueError,
                                       "requires PID-namespace isolation"):
            self._run(isolate_process_tree=False, require_pid_namespace=True)
        launch.assert_not_called()

    def test_namespace_requirement_is_strict_boolean_before_popen(self):
        for required in (None, 0, 1, "true", [], {}):
            with self.subTest(required=required), mock.patch.object(
                    self.process.subprocess, "Popen") as launch, \
                    self.assertRaisesRegex(ValueError,
                                           "PID-namespace requirement is invalid"):
                self._run(isolate_process_tree=True,
                          require_pid_namespace=required)
            launch.assert_not_called()

    def test_default_optional_fallback_and_unisolated_routes_are_unchanged(self):
        for isolated, mode in ((True, "process-group"), (False, "pid-namespace")):
            with self.subTest(isolated=isolated, mode=mode), mock.patch.object(
                    self.process.subprocess, "Popen",
                    side_effect=_LaunchObserved) as launch, \
                    self.assertRaises(_LaunchObserved):
                self._run(isolation=mode, isolate_process_tree=isolated)
            launch.assert_called_once()
            self.assertEqual(launch.call_args.args[0],
                             ["fixture-command", "fixture-argument"])

    def test_wrapper_forwards_required_namespace_and_exact_selected_mode(self):
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(self.lib, "process_tree_isolation",
                               return_value="pid-namespace") as mode, \
                mock.patch.object(self.process, "run_bounded_text_process",
                                  return_value=completed) as bounded:
            result = self.lib._run_bounded_text_process(
                ["fixture-command"], env={}, timeout=1, cwd="/",
                isolate_process_tree=True, require_pid_namespace=True)
        self.assertIs(result, completed)
        mode.assert_called_once_with()
        self.assertIs(bounded.call_args.kwargs["isolate_process_tree"], True)
        self.assertIs(bounded.call_args.kwargs["require_pid_namespace"], True)
        self.assertEqual(bounded.call_args.kwargs["isolation"], "pid-namespace")

    def test_wrapper_default_does_not_probe_or_require_namespace(self):
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(self.lib, "process_tree_isolation") as mode, \
                mock.patch.object(self.process, "run_bounded_text_process",
                                  return_value=completed) as bounded:
            result = self.lib._run_bounded_text_process(
                ["fixture-command"], env={}, timeout=1, cwd="/")
        self.assertIs(result, completed)
        mode.assert_not_called()
        self.assertIs(bounded.call_args.kwargs["isolate_process_tree"], False)
        self.assertIs(bounded.call_args.kwargs["require_pid_namespace"], False)
        self.assertEqual(bounded.call_args.kwargs["isolation"], "process-group")


class RequiredNamespaceVectorTransport(unittest.TestCase):
    _invoke = transport_tests.RawVectorTransport._invoke

    def setUp(self):
        transport_tests.RawVectorTransport.setUp(self)
        self.assertEqual(self.vector.sialib.SHARE, os.path.join(
            sia_test_home.ISOLATED_HOME, ".local/share/sia"))

    def test_vector_request_requires_namespace_and_keeps_strong_receipt(self):
        # Mocked runner checks the requested contract; no adapter executes.
        def observe(command, **kwargs):
            self.assertIs(kwargs.get("isolate_process_tree"), True)
            self.assertIs(kwargs.get("require_pid_namespace"), True)
            return subprocess.CompletedProcess(command, 0, '{"ok":true}\n', '')

        with mock.patch.object(self.vector.sialib, "_run_bounded_text_process",
                               side_effect=observe):
            result = self._invoke()
        self.assertEqual(result["payload"], {"ok": True})
        self.assertEqual(result["launch_contract"]["process_containment"],
                         "user-pid-namespace-private-proc")

    def test_vector_fallback_refuses_before_child_launch(self):
        # On old code the sentinel is caught, then assert_not_called fails.
        # That yields an assertion-bearing baseline negative, never a child.
        with mock.patch.object(self.vector.sialib, "process_tree_isolation",
                               return_value="process-group") as mode, \
                mock.patch.object(subprocess, "Popen",
                                  side_effect=_LaunchObserved) as launch, \
                self.assertRaises((self.vector.VectorRefusal,
                                   _LaunchObserved)) as refusal:
            self._invoke()
        mode.assert_called_once_with()
        launch.assert_not_called()
        self.assertIsInstance(refusal.exception, self.vector.VectorRefusal)
        self.assertIsInstance(refusal.exception.__cause__, ValueError)
        self.assertIn("requires PID-namespace isolation",
                      str(refusal.exception.__cause__))


if __name__ == "__main__":
    unittest.main()
