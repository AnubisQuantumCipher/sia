"""Installed Python runtime dependency closure.

The installer publishes one sibling runtime tree and immediately signs its
member set.  Every repository-local module imported by any staged Python
entrypoint or module must therefore be present in both the release snapshot
and that staged, receipt-covered tree.  Lazy imports count: a repository test
environment is not a substitute for an installable resident runtime.
"""

import ast
import importlib.util
from pathlib import Path
import re
import shlex
import unittest


REPO = Path(__file__).resolve().parents[1]
INSTALLER = (REPO / "install.sh").read_text(encoding="utf-8")
RUNTIME = INSTALLER.split(
    '\nstep "3/9 runtime"\n', 1)[1].split(
        "\nSTAGED_RUNTIME_DIGEST=", 1)[0]


def _words(pattern, text):
    match = re.search(pattern, text, flags=re.DOTALL)
    if match is None:
        raise AssertionError("installer runtime roster could not be parsed")
    return shlex.split(match.group(1).replace("\\\n", " "))


def _runtime_modules():
    return _words(r"for runtime_module in (.*?); do", RUNTIME)


def _runtime_members():
    modules = _runtime_modules()
    commands = _words(r"for runtime_command in (.*?); do", RUNTIME)
    return tuple(modules + commands + [
        "sia-brainstem", "sia-brainstem.py", "sia-cli",
    ])


def _release_files():
    body = INSTALLER.split("SIA_RELEASE_FILES=(", 1)[1].split("\n)", 1)[0]
    return set(shlex.split(body.replace("\\\n", " ")))


def _imports(path, local):
    result = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module.split(".")[0]]
        result.update(name for name in names if name in local)
    return result


def _release_authority():
    path = REPO / "bin/siarelease.py"
    spec = importlib.util.spec_from_file_location(
        "sia_runtime_closure_release", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeModuleClosure(unittest.TestCase):
    def test_staged_runtime_is_transitively_import_closed(self):
        local = {path.stem: path for path in (REPO / "bin").glob("sia*.py")}
        staged = {Path(name).stem for name in _runtime_modules()}
        entrypoints = [REPO / "bin" / name for name in (
            "sia", "sia-brainstem", "sia-ledger", "sia-mcp",
            "sia-continuity-worker",
        )]
        pending = list(staged)
        dependencies = set(staged)
        for path in entrypoints:
            for dependency in _imports(path, local):
                if dependency not in dependencies:
                    dependencies.add(dependency)
                    pending.append(dependency)
        while pending:
            name = pending.pop()
            path = local.get(name)
            if path is None:
                continue
            for dependency in _imports(path, local):
                if dependency not in dependencies:
                    dependencies.add(dependency)
                    pending.append(dependency)
        self.assertEqual(
            sorted(dependencies - staged), [],
            "repository-local imports omitted from installed runtime")

    def test_every_staged_source_is_in_the_bounded_release_snapshot(self):
        release = _release_files()
        required = {"bin/" + name for name in _runtime_modules()}
        required.update("bin/" + name for name in (
            "sia", "sia-brainstem", "sia-ledger", "sia-mcp",
            "sia-continuity-worker",
        ))
        self.assertEqual(sorted(required - release), [])

    def test_latest_receipt_rung_is_exactly_the_staged_tree(self):
        members = _runtime_members()
        self.assertEqual(len(members), len(set(members)))
        authority = _release_authority()
        authority.validate_runtime_ladder()
        self.assertEqual(set(authority.RUNTIME_LADDER[0][1]), set(members))


if __name__ == "__main__":
    unittest.main()
