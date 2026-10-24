#!/usr/bin/env python3
"""Bounded-input Python review inventory; never a compliance verdict.

Does not import inspected code. AST parsing still uses CPython allocation;
source/node caps are operational limits, not a proof of memory consumption.
Paths are operator-selected, not an authenticated or hostile-path interface.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

MAX_FILES = 128
MAX_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 16 * MAX_BYTES
MAX_NODES = 200_000
DYNAMIC = {"eval", "exec", "getattr", "setattr", "globals", "locals", "__import__"}


def read_source(path):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise ValueError("source must be a bounded regular file")
        raw = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > MAX_BYTES or (
            before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError("source changed or exceeded byte bound")
    return raw


def observations(tree):
    findings = []
    for index, node in enumerate(ast.walk(tree)):
        if index >= MAX_NODES:
            raise ValueError("AST node bound exceeded")
        item = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            span = node.end_lineno - node.lineno + 1
            if span > 60:
                item = {"rule": 4, "kind": "physical-span-over-60",
                        "name": node.name, "span": span}
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            item = {"rule": 6, "kind": "expanded-mutable-scope",
                    "names": node.names}
        elif isinstance(node, ast.While):
            item = {"rule": 2, "kind": "while-bound-review"}
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in DYNAMIC:
                item = {"rules": [1, 8, 9], "kind": "dynamic-call-review",
                        "name": node.func.id}
        if item is not None:
            findings.append(dict(item, line=node.lineno))
    return sorted(findings, key=lambda item: (item["line"], item["kind"]))


def inventory(paths):
    if not paths or len(paths) > MAX_FILES or len(set(paths)) != len(paths):
        raise ValueError("source list is empty, duplicate or exceeds bound")
    records, total = [], 0
    for path in paths:
        raw = read_source(path)
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("aggregate source byte bound exceeded")
        tree = ast.parse(raw, filename=str(path))
        records.append({"path": str(path),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "findings": observations(tree)})
    return {"status": "inventory-only", "files": records,
            "limitations": [
                "Physical spans are not normalized statement counts.",
                "Direct syntax only; aliases, indirect calls and loop bounds are unresolved.",
                "No absence-of-findings or exit status establishes rule compliance."]}


def main():
    try:
        result = inventory([Path(value) for value in sys.argv[1:]])
        print(json.dumps(result, sort_keys=True, indent=2))
    except (OSError, ValueError, SyntaxError, RecursionError, MemoryError) as error:
        print("inventory refused: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
