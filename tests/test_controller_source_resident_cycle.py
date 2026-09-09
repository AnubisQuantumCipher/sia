#!/usr/bin/env python3
"""RED contract for public, recurring controller-source pulse dispatch.

The public CLI and resident daemon must recognize an existing controller
transaction (including the fixed-slot orphan image) before touching the
legacy pulse recovery or sequence allocator.  A clean pre-controller install
continues through the established pulse path even when ``SIA_BACKFILL`` is
set; controller activation is a separate explicit, durable configuration
decision.  Startup readiness, failure reporting, and legacy DREAM must not
cross retained controller-source authority.

The scripts are loaded as modules under the process-wide isolated test home.
Their ``main`` blocks therefore never execute and no resident process starts.
"""

import ast
import contextlib
import datetime
import importlib.machinery
import importlib.util
import inspect
import io
import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIA_PATH = os.path.join(REPO, "bin", "sia")
BRAINSTEM_PATH = os.path.join(REPO, "bin", "sia-brainstem")


def _load_script(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


sia = _load_script("sia_controller_source_resident_cli_test", SIA_PATH)
brainstem = _load_script(
    "sia_controller_source_resident_brainstem_test", BRAINSTEM_PATH)


SOURCE_STATUS = {
    "state": "ok",
    "pulse_seq": 8,
    "events_pulse": 1,
    "pages": 1,
    "graph_nodes": 1,
    "graph_edges": 0,
    "graph_publication_id": "b" * 32,
    "integrity": {"verdict": "pass"},
    "errors": {},
}

SOURCE_MEMO_AUTHORITIES = {
    "prefix": "controller_source_pending",
    "live-prefix": "controller_source_live_pending",
    "effects-pending": "controller_source_effects_pending",
    "effects-committed": "controller_source_effects_committed",
    "completed": "controller_source_committed",
}
SOURCE_AUTHORITY_KINDS = tuple(SOURCE_MEMO_AUTHORITIES) + ("orphan",)


def _explode(label):
    def refused(*_args, **_kwargs):
        raise AssertionError(label + " ran before the controller source cycle")
    return refused


def _write_private_orphan(path):
    with open(path, "wb") as stream:
        stream.write(b"retained-controller-source-batch\n")
    os.chmod(path, 0o600)


def _function_tree(path, name):
    with open(path, encoding="utf-8") as stream:
        tree = ast.parse(stream.read(), filename=path)
    matches = [node for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name == name]
    if len(matches) != 1:
        raise AssertionError(f"expected one {name} definition")
    return matches[0]


def _direct_call_lines(function, name):
    return [node.lineno for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "sialib"
            and node.func.attr == name]


class ResidentSourceCycleContract(unittest.TestCase):
    def _memo(self, source_kind):
        memo = {"pulse_seq": 7, "sync_needed": False, "dream": {}}
        authority_key = SOURCE_MEMO_AUTHORITIES.get(source_kind)
        if authority_key is not None:
            memo[authority_key] = {"retained": True}
        return memo

    @contextlib.contextmanager
    def _source_authority(self, runtime, source_kind):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "controller-source-batch.json")
            if source_kind == "orphan":
                _write_private_orphan(path)
            with mock.patch.object(
                    runtime, "CONTROLLER_SOURCE_BATCH_PATH", path):
                yield self._memo(source_kind)

    def _generic_sentinels(self, runtime):
        names = (
            "_settle_pending_brainstem_failure_publication",
            "_require_status_memo_fields",
            "load_cursors",
            "_recover_notify_baseline_attempt",
            "_pending_source_replay_marker",
            "_authorize_pending_source_replay",
            "_pending_pulse_marker",
            "_pending_pulse_status_effects",
            "_require_status_sequence_not_ahead",
            "_write_memo",
            "_pulse_transaction",
        )
        stack = ExitStack()
        for name in names:
            if hasattr(runtime, name):
                stack.enter_context(mock.patch.object(
                    runtime, name, side_effect=_explode(name)))
        return stack

    def test_exact_zero_argument_resident_cycle_api(self):
        cycle = getattr(sia.sialib, "_run_controller_source_cycle", None)
        self.assertTrue(callable(cycle),
                        "missing public resident controller-source cycle API")
        self.assertEqual(list(inspect.signature(cycle).parameters), [])
        self.assertIs(brainstem.sialib._run_controller_source_cycle, cycle)

    def test_effects_prefixes_are_controller_source_authority(self):
        for source_kind in ("effects-pending", "effects-committed"):
            with self.subTest(source_kind=source_kind):
                with self._source_authority(
                        sia.sialib, source_kind) as memo:
                    self.assertTrue(
                        sia.sialib._controller_source_present(memo))

    def test_manual_pulse_dispatches_prefix_and_fixed_orphan_before_legacy(self):
        for source_kind in ("prefix", "orphan"):
            with self.subTest(source_kind=source_kind):
                with self._source_authority(
                        sia.sialib, source_kind) as memo, \
                        self._generic_sentinels(sia.sialib), \
                        mock.patch.object(
                            sia.sialib, "corpus_owner",
                            return_value=contextlib.nullcontext()), \
                        mock.patch.object(
                            sia.sialib, "load_memo", return_value=memo), \
                        mock.patch.object(
                            sia.sialib, "_run_controller_source_cycle",
                            create=True,
                            return_value=dict(SOURCE_STATUS)) as cycle, \
                        contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(sia._cmd_pulse_owned(), 0)
                cycle.assert_called_once_with()
                rendered = json.loads(output.getvalue())
                self.assertEqual(rendered, {
                    key: SOURCE_STATUS[key] for key in
                    ("state", "events_pulse", "pages", "graph_nodes",
                     "graph_edges", "integrity")
                })

    def test_daemon_dispatches_prefix_and_fixed_orphan_before_legacy(self):
        for source_kind in ("prefix", "orphan"):
            with self.subTest(source_kind=source_kind):
                with self._source_authority(
                        brainstem.sialib, source_kind) as memo, \
                        self._generic_sentinels(brainstem.sialib), \
                        mock.patch.object(
                            brainstem.sialib, "corpus_owner",
                            return_value=contextlib.nullcontext()), \
                        mock.patch.object(
                            brainstem.sialib, "load_memo", return_value=memo), \
                        mock.patch.object(
                            brainstem, "_pending_failure_publication",
                            side_effect=_explode(
                                "generic failure publication recovery")), \
                        mock.patch.object(
                            brainstem.sialib, "_run_controller_source_cycle",
                            create=True,
                            return_value=dict(SOURCE_STATUS)) as cycle:
                    result = brainstem._reserved_pulse()
                cycle.assert_called_once_with()
                self.assertEqual(result, SOURCE_STATUS)

    def _legacy_runtime(self, runtime, memo, status):
        admitted = object()
        stack = ExitStack()
        root = stack.enter_context(tempfile.TemporaryDirectory())
        stack.enter_context(mock.patch.object(
            runtime, "CONTROLLER_SOURCE_BATCH_PATH",
            os.path.join(root, "absent-source-slot")))
        stack.enter_context(mock.patch.object(
            runtime, "load_memo", return_value=memo))
        stack.enter_context(mock.patch.object(
            runtime, "_run_controller_source_cycle", create=True,
            side_effect=AssertionError(
                "clean legacy pulse entered the controller source cycle")))
        for name in (
                "_settle_pending_brainstem_failure_publication",
                "_require_status_memo_fields",
                "_recover_notify_baseline_attempt",
                "_pending_pulse_marker", "_pending_pulse_status_effects"):
            if hasattr(runtime, name):
                stack.enter_context(mock.patch.object(runtime, name))
        if hasattr(runtime, "_pending_failure_publication"):
            stack.enter_context(mock.patch.object(
                runtime, "_pending_failure_publication", return_value=None))
        stack.enter_context(mock.patch.object(
            runtime, "load_cursors", return_value={}))
        stack.enter_context(mock.patch.object(
            runtime, "_pending_source_replay_marker", return_value=None))
        stack.enter_context(mock.patch.object(
            runtime, "_require_status_sequence_not_ahead",
            return_value=admitted))
        write = stack.enter_context(mock.patch.object(runtime, "_write_memo"))
        pulse = stack.enter_context(mock.patch.object(
            runtime, "_pulse_transaction", return_value=dict(status)))
        stack.enter_context(mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}))
        return stack, admitted, write, pulse

    def test_clean_backfill_install_preserves_manual_legacy_pulse(self):
        for policy in (None, False):
            with self.subTest(controller_source=policy):
                memo = self._memo("clean")
                stack, admitted, write, pulse = self._legacy_runtime(
                    sia.sialib, memo, SOURCE_STATUS)
                config = ({} if policy is None else
                          {"mind": {"controller_source": policy}})
                stack.enter_context(mock.patch.object(
                    sia.sialib, "CONFIG", config))
                with stack, mock.patch.object(
                        sia.sialib, "corpus_owner",
                        return_value=contextlib.nullcontext()), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(sia._cmd_pulse_owned(), 0)
                write.assert_called_once()
                expected_seq = memo["pulse_seq"]
                self.assertEqual(
                    expected_seq, write.call_args.args[0]["pulse_seq"])
                pulse.assert_called_once_with(
                    expected_seq, admitted_status=admitted)

    def test_clean_backfill_install_preserves_daemon_legacy_pulse(self):
        for policy in (None, False):
            with self.subTest(controller_source=policy):
                memo = self._memo("clean")
                stack, admitted, write, pulse = self._legacy_runtime(
                    brainstem.sialib, memo, SOURCE_STATUS)
                config = ({} if policy is None else
                          {"mind": {"controller_source": policy}})
                stack.enter_context(mock.patch.object(
                    brainstem.sialib, "CONFIG", config))
                with stack, mock.patch.object(
                        brainstem.sialib, "corpus_owner",
                        return_value=contextlib.nullcontext()):
                    result = brainstem._reserved_pulse()
                self.assertEqual(result, SOURCE_STATUS)
                write.assert_called_once()
                expected_seq = memo["pulse_seq"]
                self.assertEqual(
                    expected_seq, write.call_args.args[0]["pulse_seq"])
                pulse.assert_called_once_with(
                    expected_seq, admitted_status=admitted)

    def test_explicit_config_activates_clean_manual_source_cycle(self):
        with self._source_authority(sia.sialib, "clean") as memo, \
                self._generic_sentinels(sia.sialib), \
                mock.patch.object(
                    sia.sialib, "CONFIG",
                    {"mind": {"controller_source": True}}), \
                mock.patch.object(sia.sialib, "CONFIG_ERRORS", []), \
                mock.patch.object(
                    sia.sialib, "corpus_owner",
                    return_value=contextlib.nullcontext()), \
                mock.patch.object(
                    sia.sialib, "load_memo", return_value=memo), \
                mock.patch.object(
                    sia.sialib, "_run_controller_source_cycle",
                    return_value=dict(SOURCE_STATUS)) as cycle, \
                mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sia._cmd_pulse_owned(), 0)
        cycle.assert_called_once_with()

    def test_explicit_config_activates_clean_daemon_source_cycle(self):
        with self._source_authority(brainstem.sialib, "clean") as memo, \
                self._generic_sentinels(brainstem.sialib), \
                mock.patch.object(
                    brainstem.sialib, "CONFIG",
                    {"mind": {"controller_source": True}}), \
                mock.patch.object(brainstem.sialib, "CONFIG_ERRORS", []), \
                mock.patch.object(
                    brainstem.sialib, "corpus_owner",
                    return_value=contextlib.nullcontext()), \
                mock.patch.object(
                    brainstem.sialib, "load_memo", return_value=memo), \
                mock.patch.object(
                    brainstem, "_pending_failure_publication",
                    side_effect=_explode(
                        "generic failure publication recovery")), \
                mock.patch.object(
                    brainstem.sialib, "_run_controller_source_cycle",
                    return_value=dict(SOURCE_STATUS)) as cycle, \
                mock.patch.dict(os.environ, {"SIA_BACKFILL": "1"}):
            result = brainstem._reserved_pulse()
        cycle.assert_called_once_with()
        self.assertEqual(result, SOURCE_STATUS)

    def test_controller_source_config_policy_is_a_closed_boolean(self):
        runtime = sia.sialib
        old_path = runtime.CONFIG_PATH
        old_errors = list(runtime.CONFIG_ERRORS)
        old_loaded = runtime._LAST_LOADED_CONFIG
        old_valid = runtime._LAST_CONFIG_LOAD_VALID
        with tempfile.TemporaryDirectory() as root:
            config_path = os.path.join(root, "config.json")
            runtime.CONFIG_PATH = config_path
            try:
                for enabled in (False, True):
                    with self.subTest(enabled=enabled):
                        configured = {
                            "mind": {"controller_source": enabled}}
                        with open(config_path, "w", encoding="utf-8") \
                                as stream:
                            json.dump(configured, stream)
                        self.assertEqual(runtime.load_config(), configured)
                        self.assertEqual(runtime.CONFIG_ERRORS, [])
                        self.assertTrue(runtime._LAST_CONFIG_LOAD_VALID)

                malformed = (
                    ({"mind": []}, "mind-must-be-object"),
                    ({"mind": {"controller_source": "true"}},
                     "mind-controller-source-must-be-bool"),
                    ({"mind": {"controller_soruce": True}},
                     "mind-unknown-key"),
                )
                for configured, reason in malformed:
                    with self.subTest(reason=reason):
                        with open(config_path, "w", encoding="utf-8") \
                                as stream:
                            json.dump(configured, stream)
                        self.assertEqual(runtime.load_config(), configured)
                        self.assertEqual(runtime.CONFIG_ERRORS, [{
                            "config": "config.json", "error": reason}])
            finally:
                runtime.CONFIG_PATH = old_path
                runtime._LAST_LOADED_CONFIG = old_loaded
                runtime._LAST_CONFIG_LOAD_VALID = old_valid
                runtime.CONFIG_ERRORS[:] = old_errors

    def test_daemon_startup_recovers_source_before_generic_failure_and_ready(self):
        trace = []

        with self._source_authority(brainstem.sialib, "prefix") as memo:
            def source_cycle():
                trace.append("source-cycle")
                memo["pulse_seq"] = SOURCE_STATUS["pulse_seq"]
                memo.pop("controller_source_pending", None)
                memo["controller_source_committed"] = {"retained": True}
                return dict(SOURCE_STATUS)

            def systemd_ready():
                trace.append("READY")
                brainstem._stop = True

            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(
                    brainstem, "_stop", False))
                stack.enter_context(mock.patch.object(
                    brainstem.signal, "signal"))
                stack.enter_context(mock.patch.object(
                    brainstem.sialib, "CONFIG", {}))
                stack.enter_context(mock.patch.object(
                    brainstem.sialib, "load_memo", return_value=memo))
                pending_failure = stack.enter_context(mock.patch.object(
                    brainstem, "_pending_failure_publication",
                    return_value=None))
                stack.enter_context(mock.patch.object(
                    brainstem.sialib, "_require_status_memo_fields"))
                stack.enter_context(mock.patch.object(
                    brainstem.sialib, "load_cursors", return_value={}))
                stack.enter_context(mock.patch.object(
                    brainstem.sialib, "_recover_notify_baseline_attempt"))
                stack.enter_context(mock.patch.object(
                    brainstem.sialib, "_pending_source_replay_marker",
                    return_value=None))
                stack.enter_context(mock.patch.object(
                    brainstem.sialib, "_pending_pulse_marker"))
                stack.enter_context(mock.patch.object(
                    brainstem.sialib, "_pending_pulse_status_effects"))
                stack.enter_context(mock.patch.object(
                    brainstem.sialib,
                    "_require_status_sequence_not_ahead"))
                stack.enter_context(mock.patch.object(
                    brainstem.sialib, "ensure_dirs"))
                stack.enter_context(mock.patch.object(
                    brainstem.sialib, "recover_ledger_transitions",
                    return_value=([], [])))
                stack.enter_context(mock.patch.object(
                    brainstem.sialib, "durable_ledger_append"))
                ready = stack.enter_context(mock.patch.object(
                    brainstem, "_systemd_ready",
                    side_effect=systemd_ready))
                stack.enter_context(mock.patch.object(
                    brainstem.sialib, "corpus_owner",
                    return_value=contextlib.nullcontext()))
                cycle = stack.enter_context(mock.patch.object(
                    brainstem.sialib, "_run_controller_source_cycle",
                    side_effect=source_cycle))
                stack.enter_context(mock.patch.object(
                    brainstem.sialib, "log"))
                publish = stack.enter_context(mock.patch.object(
                    brainstem, "_publish_failure"))
                result = brainstem._run_owned()

        self.assertEqual(result, 0)
        self.assertEqual(trace, ["source-cycle", "READY"])
        pending_failure.assert_not_called()
        cycle.assert_called_once_with()
        ready.assert_called_once_with()
        publish.assert_not_called()

    def test_daemon_ready_does_not_wait_for_a_completed_source_cycle(self):
        trace = []
        memo = self._memo("completed")

        def systemd_ready():
            trace.append("READY")
            brainstem._stop = True

        with self._source_authority(brainstem.sialib, "completed"), \
                ExitStack() as stack:
            stack.enter_context(mock.patch.object(brainstem, "_stop", False))
            stack.enter_context(mock.patch.object(brainstem.signal, "signal"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "CONFIG",
                {"mind": {"controller_source": True}}))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "load_memo", return_value=memo))
            stack.enter_context(mock.patch.object(
                brainstem, "_pending_failure_publication",
                return_value=None))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_require_status_memo_fields"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "load_cursors", return_value={}))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_recover_notify_baseline_attempt"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_pending_source_replay_marker",
                return_value=None))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_pending_pulse_marker"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_pending_pulse_status_effects"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib,
                "_require_status_sequence_not_ahead"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_run_controller_source_cycle",
                side_effect=AssertionError(
                    "new source cycle ran before READY")))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "ensure_dirs"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "recover_ledger_transitions",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "durable_ledger_append"))
            ready = stack.enter_context(mock.patch.object(
                brainstem, "_systemd_ready", side_effect=systemd_ready))
            stack.enter_context(mock.patch.object(brainstem.sialib, "log"))
            publish = stack.enter_context(mock.patch.object(
                brainstem, "_publish_failure"))

            result = brainstem._run_owned()

        self.assertEqual(result, 0)
        self.assertEqual(trace, ["READY"])
        ready.assert_called_once_with()
        publish.assert_not_called()

    def test_failed_pulse_refreshes_durable_sequence_before_reporting(self):
        initial = {"pulse_seq": 7, "sync_needed": False, "dream": {}}
        durable = {"pulse_seq": 8, "sync_needed": False, "dream": {}}
        allocated = {"durable": False}
        detail = "failure after durable allocation"

        def load_memo():
            selected = durable if allocated["durable"] else initial
            return {
                "pulse_seq": selected["pulse_seq"],
                "sync_needed": selected["sync_needed"],
                "dream": {},
            }

        def failed_pulse():
            allocated["durable"] = True
            brainstem._stop = True
            raise RuntimeError(detail)

        with ExitStack() as stack:
            stack.enter_context(self._source_authority(
                brainstem.sialib, "clean"))
            stack.enter_context(mock.patch.object(
                brainstem, "_stop", False))
            stack.enter_context(mock.patch.object(
                brainstem.signal, "signal"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "CONFIG", {}))
            durable_load = stack.enter_context(mock.patch.object(
                brainstem.sialib, "load_memo", side_effect=load_memo))
            stack.enter_context(mock.patch.object(
                brainstem, "_pending_failure_publication",
                return_value=None))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_require_status_memo_fields"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "load_cursors", return_value={}))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_recover_notify_baseline_attempt"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_pending_source_replay_marker",
                return_value=None))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_pending_pulse_marker"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_pending_pulse_status_effects"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_require_status_sequence_not_ahead"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "ensure_dirs"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "recover_ledger_transitions",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "durable_ledger_append"))
            stack.enter_context(mock.patch.object(
                brainstem, "_systemd_ready"))
            stack.enter_context(mock.patch.object(
                brainstem, "_reserved_pulse", side_effect=failed_pulse))
            stack.enter_context(mock.patch.object(
                brainstem, "_safe_failure_detail", return_value=detail))
            stack.enter_context(mock.patch.object(
                brainstem, "_durable_dream_day", return_value=""))
            stack.enter_context(mock.patch.object(
                brainstem, "_dream_due", return_value=False))
            log = stack.enter_context(mock.patch.object(
                brainstem.sialib, "log"))
            publish = stack.enter_context(mock.patch.object(
                brainstem, "_publish_failure"))
            self.assertEqual(brainstem._run_owned(), 0)

        self.assertGreaterEqual(durable_load.call_count, 2)
        publish.assert_called_once_with(durable["pulse_seq"], detail)
        self.assertIn(
            f"pulse {durable['pulse_seq']} FAILED: {detail}",
            [call.args[0] for call in log.call_args_list if call.args])

    def test_manual_legacy_dream_never_runs_under_source_authority(self):
        for source_kind in SOURCE_AUTHORITY_KINDS:
            with self.subTest(source_kind=source_kind):
                with self._source_authority(
                        sia.sialib, source_kind) as memo, \
                        mock.patch.object(
                            sia.sialib, "load_memo", return_value=memo), \
                        mock.patch.object(
                            sia.sialib, "brainstem_owner",
                            return_value=contextlib.nullcontext()), \
                        mock.patch.object(
                            sia.sialib, "dream", return_value=None) as dream, \
                        contextlib.redirect_stdout(io.StringIO()):
                    try:
                        sia.cmd_dream()
                    except (RuntimeError, ValueError):
                        pass
                dream.assert_not_called()

    def test_scheduled_legacy_dream_never_runs_under_source_authority(self):
        now = datetime.datetime(2026, 9, 6, 3, 0)
        for source_kind in SOURCE_AUTHORITY_KINDS:
            with self.subTest(source_kind=source_kind):
                with self._source_authority(
                        brainstem.sialib, source_kind) as memo, \
                        mock.patch.object(
                            brainstem.sialib, "load_memo",
                            return_value=memo), \
                        mock.patch.object(
                            brainstem.sialib, "dream",
                            return_value=None) as dream, \
                        mock.patch.object(
                            brainstem, "_durable_dream_day",
                            return_value=""), \
                        mock.patch.object(
                            brainstem, "_durable_failure_detail",
                            return_value="source authority retained"), \
                        mock.patch.object(brainstem.sialib, "log"):
                    try:
                        brainstem._attempt_dream(now, "")
                    except (RuntimeError, ValueError):
                        pass
                dream.assert_not_called()

    def test_daemon_loop_refreshes_sequence_from_durable_memo(self):
        initial = {"pulse_seq": 7, "sync_needed": False, "dream": {}}
        durable = {"pulse_seq": 12, "sync_needed": False, "dream": {}}
        status = dict(SOURCE_STATUS, pulse_seq=durable["pulse_seq"])

        def one_cycle(*_args, **_kwargs):
            brainstem._stop = True
            return status

        ledger = mock.Mock(side_effect=(None, RuntimeError("halt refused")))
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                brainstem, "_stop", False))
            stack.enter_context(mock.patch.object(
                brainstem.signal, "signal"))
            load_memo = stack.enter_context(mock.patch.object(
                brainstem.sialib, "load_memo",
                side_effect=(initial, durable)))
            stack.enter_context(mock.patch.object(
                brainstem, "_pending_failure_publication",
                return_value=None))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_require_status_memo_fields"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "load_cursors", return_value={}))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_recover_notify_baseline_attempt"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_pending_source_replay_marker",
                return_value=None))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_pending_pulse_marker"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_pending_pulse_status_effects"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "_require_status_sequence_not_ahead"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "ensure_dirs"))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "recover_ledger_transitions",
                return_value=([], [])))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "durable_ledger_append", ledger))
            stack.enter_context(mock.patch.object(
                brainstem, "_systemd_ready"))
            pulse = stack.enter_context(mock.patch.object(
                brainstem, "_reserved_pulse", side_effect=one_cycle))
            stack.enter_context(mock.patch.object(
                brainstem, "_durable_dream_day", return_value=""))
            stack.enter_context(mock.patch.object(
                brainstem, "_dream_due", return_value=False))
            stack.enter_context(mock.patch.object(
                brainstem.sialib, "log"))
            stack.enter_context(mock.patch.object(
                brainstem, "_durable_failure_detail",
                return_value="halt refused"))
            publish = stack.enter_context(mock.patch.object(
                brainstem, "_publish_failure"))
            self.assertEqual(brainstem._run_owned(), 1)
        pulse.assert_called_once_with()
        self.assertGreaterEqual(load_memo.call_count, 2)
        publish.assert_called_once_with(
            durable["pulse_seq"], "halt refused")

    def test_generic_failure_status_is_withheld_for_every_source_authority(self):
        for source_kind in SOURCE_AUTHORITY_KINDS:
            with self.subTest(source_kind=source_kind):
                with self._source_authority(
                        brainstem.sialib, source_kind) as memo, \
                        mock.patch.object(
                            brainstem.sialib, "load_memo", return_value=memo), \
                        mock.patch.object(
                            brainstem, "_pending_failure_publication",
                            side_effect=_explode(
                                "generic failure publication recovery")), \
                        mock.patch.object(
                            brainstem.sialib, "read_json",
                            side_effect=_explode(
                                "generic failure STATUS read")), \
                        mock.patch.object(
                            brainstem.sialib, "_write_memo",
                            side_effect=_explode(
                                "generic failure memo write")), \
                        mock.patch.object(
                            brainstem.sialib, "export_status",
                            side_effect=_explode(
                                "generic failure STATUS export")), \
                        mock.patch.object(brainstem.sialib, "log") as log:
                    result = brainstem._publish_failure_owned(
                        memo["pulse_seq"], RuntimeError(
                            "source-owned failure"))
                self.assertFalse(result)
                self.assertTrue(any(
                    "controller" in str(call).lower()
                    for call in log.call_args_list))

    def test_dispatch_calls_are_structurally_ahead_of_legacy_boundaries(self):
        cases = (
            (SIA_PATH, "_cmd_pulse_owned",
             "_settle_pending_brainstem_failure_publication"),
            (BRAINSTEM_PATH, "_reserved_pulse", "_require_status_memo_fields"),
        )
        for path, function_name, first_legacy in cases:
            with self.subTest(function=function_name):
                function = _function_tree(path, function_name)
                present = _direct_call_lines(
                    function, "_controller_source_present")
                cycle = _direct_call_lines(
                    function, "_run_controller_source_cycle")
                legacy = _direct_call_lines(function, first_legacy)
                allocation = _direct_call_lines(function, "_write_memo")
                self.assertEqual(len(present), 1)
                self.assertEqual(len(cycle), 1)
                self.assertEqual(len(legacy), 1)
                self.assertEqual(len(allocation), 1)
                self.assertLess(present[0], legacy[0])
                self.assertLess(cycle[0], legacy[0])
                self.assertLess(cycle[0], allocation[0])


if __name__ == "__main__":
    unittest.main()
