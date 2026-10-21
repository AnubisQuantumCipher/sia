"""R37: exercise the exact installer launcher writer under bounded syscall faults."""

import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SOURCE_LIMIT = 1048576
INJECTOR = r"""
import errno
import hashlib
import json
import os
import sys

program = sys.stdin.read(1048577)
if len(program.encode("utf-8")) > 1048576:
    raise AssertionError("writer program exceeds source budget")
mode, target = sys.argv[1:]
if mode not in ("normal", "short", "zero", "raise"):
    raise AssertionError("unexpected writer fault mode")
original_write, original_chmod, original_sync = os.write, os.fchmod, os.fsync
writes, modes, syncs, completion_events = [], [], [], []


def write(descriptor, content):
    result = {"remaining": len(content), "written": None}
    writes.append(result)
    if mode == "raise":
        raise OSError(errno.EIO, "injected launcher write failure")
    if mode == "zero":
        count = 0
    elif mode == "short":
        count = original_write(descriptor, content[:max(1, len(content) // 2)])
    else:
        count = original_write(descriptor, content)
    result["written"] = count
    return count


def completed_at_event(kind, descriptor):
    with open(target, "rb") as stream:
        content = stream.read(1048577)
        observed = os.fstat(stream.fileno())
    actual = os.fstat(descriptor)
    if (actual.st_dev, actual.st_ino) != (observed.st_dev, observed.st_ino):
        raise AssertionError("completion snapshot is not writer inode")
    return {"kind": kind, "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "literal_equal": content == namespace["source"].encode("utf-8")}


def chmod(descriptor, value):
    completion_events.append(completed_at_event("chmod", descriptor))
    modes.append(value)
    return original_chmod(descriptor, value)


def sync(descriptor):
    completion_events.append(completed_at_event("fsync", descriptor))
    syncs.append(True)
    return original_sync(descriptor)


os.umask(0o077)
os.write, os.fchmod, os.fsync = write, chmod, sync
sys.argv = ["installer-launcher-writer", target]
namespace, error = {}, None
try:
    exec(compile(program, "install.sh:launcher-writer", "exec"), namespace)
except OSError as exc:
    error = {"type": type(exc).__name__, "errno": exc.errno, "message": str(exc)}
finally:
    os.write, os.fchmod, os.fsync = original_write, original_chmod, original_sync
try:
    os.fstat(namespace["descriptor"])
    closed = False
except OSError as exc:
    closed = exc.errno == errno.EBADF
print(json.dumps({"error": error, "writes": writes, "modes": modes,
                  "syncs": syncs, "closed": closed,
                  "completion_events": completion_events}))
"""


def _writer_program():
    with (REPO / "install.sh").open("rb") as stream:
        installer = stream.read(SOURCE_LIMIT + 1)
    if len(installer) > SOURCE_LIMIT:
        raise AssertionError("installer exceeds source budget")
    start = ('write_stable_generation_launcher() {\n  local target="$1"\n'
             '  python3 - "$target" <<\'PY\'\n')
    end = "\nPY\n}\n\npreflight_owned_file() {"
    source = installer.decode("utf-8")
    if source.count(start) != 1:
        raise AssertionError("launcher writer marker is not unique")
    program, separator, _tail = source.partition(start)[2].partition(end)
    if not separator:
        raise AssertionError("launcher writer terminator is absent")
    nodes = [node for node in ast.parse(program).body
             if isinstance(node, ast.Assign)
             and any(isinstance(name, ast.Name) and name.id == "source"
                     for name in node.targets)]
    if len(nodes) != 1 or not isinstance(nodes[0].value, ast.Constant) \
            or not isinstance(nodes[0].value.value, str):
        raise AssertionError("launcher source is not one literal")
    return program, nodes[0].value.value.encode("utf-8")


class StableLauncherWriter(unittest.TestCase):
    def setUp(self):
        self.program, self.expected = _writer_program()
        temporary = tempfile.TemporaryDirectory(prefix="sia-launcher-writer-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / "sia"

    def _run_writer(self, mode):
        result = subprocess.run(
            [sys.executable, "-I", "-W", "error", "-c", INJECTOR,
             mode, str(self.target)], input=self.program, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            timeout=3, cwd=self.root,
            env={"HOME": str(self.root), "TMPDIR": str(self.root),
                 "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        receipt = json.loads(result.stdout)
        self.assertTrue(receipt["closed"], receipt)
        self.assertEqual(self.target.stat().st_uid, os.geteuid())
        return receipt

    def _assert_complete(self, receipt):
        self.assertIsNone(receipt["error"])
        self.assertEqual(self.target.read_bytes(), self.expected)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o755)
        self.assertEqual(receipt["modes"], [0o755])
        self.assertEqual(receipt["syncs"], [True])
        expected = {"bytes": len(self.expected),
                    "sha256": hashlib.sha256(self.expected).hexdigest(),
                    "literal_equal": True}
        self.assertEqual(receipt["completion_events"], [
            {"kind": "chmod", **expected}, {"kind": "fsync", **expected}])

    def test_normal_write_preserves_full_literal_mode_and_sync(self):
        receipt = self._run_writer("normal")
        self._assert_complete(receipt)
        self.assertEqual(receipt["writes"], [
            {"remaining": len(self.expected), "written": len(self.expected)}])

    def test_short_writes_complete_full_literal_before_activation(self):
        receipt = self._run_writer("short")
        self._assert_complete(receipt)
        self.assertGreater(len(receipt["writes"]), 1)
        remaining = len(self.expected)
        for write in receipt["writes"]:
            self.assertEqual(write["remaining"], remaining)
            self.assertGreater(write["written"], 0)
            self.assertLessEqual(write["written"], remaining)
            remaining -= write["written"]
        self.assertEqual(remaining, 0)

    def test_zero_write_refuses_before_activation_or_sync(self):
        receipt = self._run_writer("zero")
        self.assertIsNotNone(receipt["error"])
        self.assertEqual(receipt["error"]["type"], "OSError")
        self.assertEqual(receipt["error"]["message"], "short stable launcher write")
        self.assertEqual(receipt["writes"], [
            {"remaining": len(self.expected), "written": 0}])
        self.assertEqual(receipt["modes"], [])
        self.assertEqual(receipt["syncs"], [])
        self.assertEqual(receipt["completion_events"], [])
        self.assertEqual(self.target.read_bytes(), b"")
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)

    def test_write_oserror_refuses_before_activation_or_sync(self):
        receipt = self._run_writer("raise")
        self.assertIsNotNone(receipt["error"])
        self.assertEqual(receipt["error"]["type"], "OSError")
        self.assertEqual(receipt["error"]["message"],
                         "[Errno 5] injected launcher write failure")
        self.assertEqual(receipt["modes"], [])
        self.assertEqual(receipt["syncs"], [])
        self.assertEqual(receipt["completion_events"], [])
        self.assertEqual(self.target.read_bytes(), b"")
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)


if __name__ == "__main__":
    unittest.main()
