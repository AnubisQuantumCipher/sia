#!/usr/bin/env python3
"""Regression guard against tests touching the resident SIA instance."""

import ast
import importlib.util
import os
import sys
import unittest
from pathlib import Path

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "bin"
sys.path.insert(0, str(BIN))
RUNTIME_MODULES = (
    "sialib", "siasenses", "siagraph", "siarestoreadmit", "siamind",
    "siatakes", "siabench", "siaqueue")
RUNTIME_FILES = tuple(name + ".py" for name in RUNTIME_MODULES)


def _load(name):
    path = BIN / (name + ".py")
    spec = importlib.util.spec_from_file_location(
        "state_isolation_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_under(test, path):
    root = os.path.realpath(sia_test_home.ISOLATED_HOME)
    candidate = os.path.realpath(path)
    test.assertEqual(os.path.commonpath((root, candidate)), root, candidate)


class RuntimeStateIsolation(unittest.TestCase):
    def test_all_import_time_mutable_paths_use_the_temporary_home(self):
        sialib = _load("sialib")
        siamind = _load("siamind")
        siatakes = _load("siatakes")
        siabench = _load("siabench")

        for name in (
                "HOME", "SHARE", "STATE", "CORPUS", "BIN", "TOOLCHAIN",
                "GBRAIN", "GBRAIN_OWNER_LOCK", "CORPUS_OWNER_LOCK",
                "BRAINSTEM_OWNER_LOCK", "LIFECYCLE_LOCK",
                "LIFECYCLE_TOMBSTONE", "THOUGHT_INBOX_PATH",
                "THOUGHT_INBOX_LOCK", "THOUGHT_INBOX_CLAIM", "ATTEST",
                "BUN_DIR", "CONFIG_PATH", "CURSORS_PATH", "THOUGHTS_PATH",
                "STATUS_PATH", "GRAPH_PATH", "MEMO_PATH"):
            with self.subTest(module="sialib", path=name):
                _assert_under(self, getattr(sialib, name))
        _assert_under(self, sialib.GBRAIN_ENV["GBRAIN_HOME"])

        for name in (
                "STATE", "CORPUS", "MIND_PATH", "TOUCH_QUEUE",
                "RECOVERY_UNPIN_QUEUE"):
            with self.subTest(module="siamind", path=name):
                _assert_under(self, getattr(siamind, name))

        for name in (
                "HOME", "CORPUS", "TAKES_DIR", "GRADE_TX_DIR",
                "TAKE_MIGRATION_TX_DIR", "NATURAL_HISTORY_DIR",
                "INTENTS_DIR", "_DEFAULT_TAKES_DIR", "_DEFAULT_GRADE_TX_DIR",
                "_DEFAULT_TAKE_MIGRATION_TX_DIR"):
            with self.subTest(module="siatakes", path=name):
                _assert_under(self, getattr(siatakes, name))
        _assert_under(self, siabench.CORPUS)

    def test_every_runtime_loading_test_activates_isolation_first(self):
        for path in sorted((REPO / "tests").glob("test_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            imports = []
            runtime_reference = False
            isolation_line = None
            first_runtime_line = None
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name for alias in node.names}
                    imports.extend(names)
                    if "sia_test_home" in names:
                        isolation_line = min(
                            isolation_line or node.lineno, node.lineno)
                    if names.intersection(RUNTIME_MODULES):
                        runtime_reference = True
                        first_runtime_line = min(
                            first_runtime_line or node.lineno, node.lineno)
                elif isinstance(node, ast.ImportFrom):
                    names = {alias.name for alias in node.names}
                    if node.module == "tests" and "sia_test_home" in names:
                        isolation_line = min(
                            isolation_line or node.lineno, node.lineno)
                    if node.module in RUNTIME_MODULES:
                        runtime_reference = True
                        first_runtime_line = min(
                            first_runtime_line or node.lineno, node.lineno)
                elif isinstance(node, ast.Constant) \
                        and isinstance(node.value, str) \
                        and os.path.basename(node.value) in RUNTIME_FILES:
                    runtime_reference = True
                    first_runtime_line = min(
                        first_runtime_line or node.lineno, node.lineno)
            if not runtime_reference:
                continue
            with self.subTest(path=path.name):
                self.assertIsNotNone(isolation_line)
                self.assertLess(isolation_line, first_runtime_line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
