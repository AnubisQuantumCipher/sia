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
    "siatakes", "siabench", "siaqueue", "siacapsule", "siabackup",
    "siasourceack", "siasourceeffects", "siasourceengine",
    "siasourcegit")
# The managed runtime is not only importable modules.  These five entry
# points carry no ".py", so a guard that derived its file set purely from
# module names could not see them at all: tests/test_ledger_init_recovery.py
# exec_module()s bin/sia-ledger at import time, activates no isolation, and
# the guard stayed green through every run.  Name them explicitly.
#
# The match stays deliberately coarse: naming a runtime file is enough, and
# the guard does not try to tell a load from a text read.  That already was
# the rule for ".py" members -- test_release.py's _read("bin/sialib.py")
# counts -- and it is the only shape that survives a path spelled as one
# absolute literal instead of an os.path.join.  Narrowing it to "looks like
# a load" would reopen the gap this guard exists to close.
RUNTIME_ENTRY_POINTS = (
    "sia", "sia-brainstem", "sia-continuity-worker", "sia-ledger",
    "sia-mcp")
RUNTIME_FILES = tuple(name + ".py" for name in RUNTIME_MODULES) \
    + RUNTIME_ENTRY_POINTS

_ISOLATION_REMEDY = (
    "the one-line fix is to add the standard isolation import above the "
    "first runtime reference, before any other bin/ import:\n"
    "    try:\n"
    "        import sia_test_home  # test-only import-time path isolation\n"
    "    except ModuleNotFoundError:\n"
    "        from tests import sia_test_home  # type: ignore")


def _load(name):
    path = BIN / (name + ".py")
    spec = importlib.util.spec_from_file_location(
        "state_isolation_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _path_join_constants(tree):
    """Line/column of every string handed to an ``os.path.join``.

    A bare ``"sia"`` is ambiguous: it is the runtime entry point, but it is
    also SIA's corpus source id and its own argv[0], so matching the bare
    name everywhere would flag ``["sia", "ponder", ...]`` and
    ``--source sia`` in half the suite.  An extension-less entry point only
    counts as a runtime reference when it is being assembled into a
    filesystem path, which is exactly the join argument position.
    """
    positions = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) \
                or not isinstance(node.func, ast.Attribute) \
                or node.func.attr != "join":
            continue
        for argument in node.args:
            if isinstance(argument, ast.Constant) \
                    and isinstance(argument.value, str):
                positions.add((argument.lineno, argument.col_offset))
    return positions


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
                "GBRAIN", "GBRAIN_PIN", "GBRAIN_PIN_RECEIPT",
                "GBRAIN_RUNTIME_RECEIPT", "GBRAIN_OWNER_LOCK",
                "CORPUS_OWNER_LOCK",
                "BRAINSTEM_OWNER_LOCK", "LIFECYCLE_LOCK",
                "LIFECYCLE_TOMBSTONE", "THOUGHT_INBOX_PATH",
                "THOUGHT_INBOX_LOCK", "THOUGHT_INBOX_CLAIM", "ATTEST",
                "BUN_DIR", "CONFIG_PATH", "CURSORS_PATH", "THOUGHTS_PATH",
                "STATUS_PATH", "GRAPH_PATH", "MEMO_PATH",
                "CONTROLLER_SOURCE_BATCH_PATH",
                "CONTROLLER_SOURCE_ARCHIVE_DIR"):
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

        # siacapsule and siabackup reach their absolute paths at import time
        # too, today by way of sialib.HOME.  Pin them directly: routing one
        # of these through os.environ["HOME"] or a literal instead would
        # escape the expanduser patch that isolation is built on, and the
        # continuity lane is precisely where an escape writes to the
        # operator's real repository key and restic snapshots.
        siacapsule = _load("siacapsule")
        siabackup = _load("siabackup")
        for name in (
                "CONFIG_ROOT", "CONTINUITY_ROOT", "RESTORE_BARRIER",
                "MANAGED_ROOT", "CORPUS_RECEIPT", "SCHEMA_PACK_RECEIPT",
                "LEDGER_KEY", "LEDGER_PUBLIC"):
            with self.subTest(module="siacapsule", path=name):
                _assert_under(self, getattr(siacapsule, name))
        for name in (
                "ROOT", "CONFIG_PATH", "KEY_PATH", "STATUS_PATH",
                "REQUESTS_DIR", "CAPSULES_DIR", "REQUEST_LOCK",
                "WORKER_LOCK", "RESTIC_PATH", "STABLE_CLI_PATH",
                "SYSTEMD_USER_DIR", "MANAGED_INSTALL_DIR"):
            with self.subTest(module="siabackup", path=name):
                _assert_under(self, getattr(siabackup, name))

    def test_every_runtime_loading_test_activates_isolation_first(self):
        for path in sorted((REPO / "tests").glob("test_*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            joined = _path_join_constants(tree)
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
                        and isinstance(node.value, str):
                    base = os.path.basename(node.value)
                    if base not in RUNTIME_FILES:
                        continue
                    if base == node.value \
                            and base in RUNTIME_ENTRY_POINTS \
                            and (node.lineno, node.col_offset) not in joined:
                        continue
                    runtime_reference = True
                    first_runtime_line = min(
                        first_runtime_line or node.lineno, node.lineno)
            if not runtime_reference:
                continue
            with self.subTest(path=path.name):
                where = f"{path.name}:{first_runtime_line}"
                self.assertIsNotNone(
                    isolation_line,
                    f"{where} reaches SIA runtime code but the file never "
                    f"activates test-home isolation; {_ISOLATION_REMEDY}")
                self.assertLess(
                    isolation_line, first_runtime_line,
                    f"{where} reaches SIA runtime code before isolation is "
                    f"activated at line {isolation_line}; "
                    f"{_ISOLATION_REMEDY}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
