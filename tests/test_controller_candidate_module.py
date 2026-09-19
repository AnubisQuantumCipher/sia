"""Retained-source candidate extraction preserves explicit owner and lifetime.

The positive uses the existing actual captured/staged-source fixture and real
pure preparation. Alias controls deliberately refuse at the first source read;
they do not fabricate successful source authority. Root alone runs the tests.
"""

import ast
import contextlib
import importlib
import importlib.util
import inspect
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_controller_source_live_transaction as producer_tests
from tests import test_pulse_sync as pulse_tests


NAME = "siacontrollercandidate"
FACADE = "_prepare_controller_source_live_candidate"
REPO = Path(__file__).resolve().parents[1]


class _ReadStopped(BaseException):
    pass


class ControllerCandidateModule(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(NAME),
                             "missing extracted controller candidate component")
        self.child = importlib.import_module(NAME)
        self.assertTrue(callable(getattr(self.child, "prepare", None)),
                        "missing explicit-owner candidate preparation")

    def test_exact_owner_api_and_source_component_ownership(self):
        signature = inspect.signature(self.child.prepare)
        self.assertEqual(tuple(signature.parameters),
                         ("owner", "memo", "admitted_status"))
        self.assertEqual(signature.parameters["owner"].kind,
                         inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for name in ("memo", "admitted_status"):
            self.assertEqual(signature.parameters[name].kind,
                             inspect.Parameter.KEYWORD_ONLY)
        for parameter in signature.parameters.values():
            self.assertIs(parameter.default, inspect.Parameter.empty)
        self.assertFalse(inspect.isgeneratorfunction(self.child.prepare))
        self.assertFalse(inspect.iscoroutinefunction(self.child.prepare))
        tree = ast.parse(Path(self.child.__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertNotIn("sialib", imported)
        self.assertTrue({"siacontrollerliveinput", "sialiveloop", "siasourcebatch"}
                        .issubset(imported))
        core_tree = ast.parse((REPO / "bin/sialib.py").read_text(encoding="utf-8"))
        facade = next(node for node in core_tree.body
                      if isinstance(node, ast.FunctionDef) and node.name == FACADE)
        self.assertFalse(any(isinstance(node, (ast.Yield, ast.YieldFrom))
                             for node in ast.walk(facade)))
        # The algorithm has one owner; this cannot pass by appending a duplicate
        # child while leaving the file-size regression in the original core.
        self.assertFalse(any(
            isinstance(node, ast.Attribute) and node.attr in {
                "prepare_inputs", "prepare_inputs_v3", "prepare_inputs_v4", "prepare_pulse"}
            for node in ast.walk(facade)))

    def test_actual_retained_batch_builds_inside_existing_owner_scopes_and_keeps_its_result(self):
        case = producer_tests.ControllerSourceLiveProducer(methodName="runTest")
        self.addCleanup(case.doCleanups)
        case.setUp()
        retained = case._stage(case._capture(empty=True))
        original = self.child.prepare
        calls = []
        borrowed = case.lib._CORPUS_OWNER_FD.get()
        borrowed_info = os.fstat(borrowed)
        before_brainstem = case.lib._BRAINSTEM_OWNER_FD.get()

        def observed(owner, *, memo, admitted_status):
            self.assertIs(owner, case.lib.__dict__)
            self.assertIs(memo, case.live.memo)
            self.assertIs(admitted_status, case.live.status)
            self.assertIsNotNone(case.lib._BRAINSTEM_OWNER_FD.get())
            os.fstat(case.lib._BRAINSTEM_OWNER_FD.get())
            self.assertEqual(case.lib._CORPUS_OWNER_FD.get(), borrowed)
            result = original(owner, memo=memo, admitted_status=admitted_status)
            self.assertIsNotNone(case.lib._BRAINSTEM_OWNER_FD.get())
            self.assertEqual(case.lib._CORPUS_OWNER_FD.get(), borrowed)
            calls.append(result)
            return result

        facade = getattr(case.lib, FACADE)
        self.assertEqual(tuple(inspect.signature(facade).parameters),
                         ("memo", "admitted_status"))
        for parameter in inspect.signature(facade).parameters.values():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)
        with mock.patch.object(self.child, "prepare", side_effect=observed):
            result = case._prepare_candidate()
        self.assertEqual(calls, [result])
        self.assertIs(result, calls[0])
        self.assertEqual(result["prepare_inputs"], case._expected_inputs(retained))
        self.assertEqual(case.lib._CORPUS_OWNER_FD.get(), borrowed)
        after_info = os.fstat(borrowed)
        self.assertEqual((after_info.st_dev, after_info.st_ino),
                         (borrowed_info.st_dev, borrowed_info.st_ino))
        self.assertIs(case.lib._BRAINSTEM_OWNER_FD.get(), before_brainstem)

    def test_alias_callbacks_remain_owner_local_and_arbitrary_refusal_releases_owned_scopes(self):
        first = pulse_tests._load("sialib_candidate_first", str(REPO / "bin/sialib.py"))
        second = pulse_tests._load("sialib_candidate_second", str(REPO / "bin/sialib.py"))
        with tempfile.TemporaryDirectory(prefix="sia-candidate-owners-") as directory, \
                contextlib.ExitStack() as stack:
            root = Path(directory)
            for label, core in (("first", first), ("second", second)):
                state = root / label
                state.mkdir(mode=0o700)
                stack.enter_context(mock.patch.multiple(core,
                    STATE=str(state), CORPUS_OWNER_LOCK=str(state / "corpus-owner.lock"),
                    BRAINSTEM_OWNER_LOCK=str(state / "brainstem-owner.lock")))
            memo, status = {}, {}
            first_stop, second_stop = _ReadStopped("first reader"), _ReadStopped("second reader")
            events = []

            def reader(core, stop):
                def read(*, memo):
                    self.assertIsNotNone(core._BRAINSTEM_OWNER_FD.get())
                    self.assertIsNotNone(core._CORPUS_OWNER_FD.get())
                    os.fstat(core._BRAINSTEM_OWNER_FD.get())
                    os.fstat(core._CORPUS_OWNER_FD.get())
                    events.append(core)
                    raise stop
                return read

            stack.enter_context(mock.patch.object(first, "_read_pending_controller_source_batch",
                                                  side_effect=reader(first, first_stop)))
            stack.enter_context(mock.patch.object(second, "_read_pending_controller_source_batch",
                                                  side_effect=reader(second, second_stop)))
            for core, stop in ((first, first_stop), (second, second_stop), (first, first_stop)):
                self.assertIsNone(core._CORPUS_OWNER_FD.get())
                self.assertIsNone(core._BRAINSTEM_OWNER_FD.get())
                with self.assertRaises(_ReadStopped) as raised:
                    getattr(core, FACADE)(memo=memo, admitted_status=status)
                self.assertIs(raised.exception, stop)
                self.assertIsNone(core._CORPUS_OWNER_FD.get())
                self.assertIsNone(core._BRAINSTEM_OWNER_FD.get())
            self.assertEqual(events, [first, second, first])


if __name__ == "__main__":
    unittest.main()
