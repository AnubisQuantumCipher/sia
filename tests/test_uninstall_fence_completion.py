"""Final uninstall status and durable-marker controls using private files."""

import hashlib
import json
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "uninstall.sh"
INJECTOR = """
import os, signal, stat, sys
injected_fault = sys.argv.pop(1)
sys.argv = sys.argv[1:]
original_chmod, original_fsync, original_unlink = os.chmod, os.fsync, os.unlink
def chmod(path, permissions, **kwargs):
    if injected_fault == 'chmod-error':
        raise OSError('injected chmod failure')
    if injected_fault == 'chmod-signal':
        os.kill(os.getpid(), signal.SIGTERM)
    return original_chmod(path, permissions, **kwargs)
def fsync(fd):
    directory = stat.S_ISDIR(os.fstat(fd).st_mode)
    if injected_fault == 'file-sync-error' and not directory:
        raise OSError('injected file fsync failure')
    if injected_fault == 'directory-sync-error' and directory:
        raise OSError('injected directory fsync failure')
    return original_fsync(fd)
def unlink(path, **kwargs):
    if injected_fault == 'journal-unlink-error' and str(path).endswith('fence.json'):
        raise OSError('injected journal unlink failure')
    if injected_fault == 'marker-unlink-error' and str(path).endswith('removed'):
        raise OSError('injected marker unlink failure')
    return original_unlink(path, **kwargs)
os.chmod, os.fsync, os.unlink = chmod, fsync, unlink
source = sys.stdin.read(1048577)
if len(source) > 1048576:
    raise ValueError('fixture helper exceeds bound')
exec(compile(source, '<exact uninstall helper>', 'exec'))
"""


def shell_function(source, name, successor):
    start = source.index(name + "() {")
    end = source.index("\n" + successor + "() {", start)
    return source[start:end]


def finalization_shell():
    source = SOURCE.read_text()
    clear = shell_function(source, "clear_lifecycle_tombstone", "write_managed_receipt")
    complete = shell_function(source, "complete_uninstall_launch_fence", "remove_owned_cli")
    # The real caller puts completion on the left of ||. Test that context with
    # errexit enabled: an unchecked inner failure must not turn into success.
    return "\n".join((
        "set -euo pipefail", clear, complete,
        'CLI_PATH="$1"; RUNTIME_BIN_DIR="$2"; LAUNCH_FENCE_JOURNAL="$3"',
        'LIFECYCLE_TOMBSTONE="$4"; SIA_LAUNCH_FENCE_ARMED=1',
        'result=0; complete_uninstall_launch_fence || result=$?',
        'printf "return=%s armed=%s\\n" "$result" "$SIA_LAUNCH_FENCE_ARMED"',
        'exit "$result"',
    ))


class UninstallFenceCompletion(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cli = self.root / "sia"
        self.runtime = self.root / "runtime"
        self.journal = self.root / "fence.json"
        self.marker = self.root / "removed"
        self.cli.write_bytes(b"retained command\n")
        info = self.cli.stat()
        self.cli.chmod(0)
        self.addCleanup(self.restore_fixture_modes)
        self.marker.write_bytes(b"removed-by=khephri.sia\n")
        self.marker_identity = self.marker.stat()
        self.entry = {"path": str(self.cli), "device": info.st_dev,
                      "inode": info.st_ino, "mode": 0o700,
                      "sha256": hashlib.sha256(b"retained command\n").hexdigest()}
        self.payload = {"schema": "sia-launch-fence-v1", "entries": [self.entry],
                        "runtime_before_digest": "", "runtime_digest": "",
                        "cli_digest": ""}

    def restore_fixture_modes(self):
        for path in (self.cli, self.root / "later"):
            if path.exists():
                path.chmod(0o600)

    def write_journal(self):
        self.journal.write_text(json.dumps(self.payload))

    def invoke(self, fault=""):
        prefix = ""
        if fault:
            injector = self.root / "injector.py"
            injector.write_text(INJECTOR)
            prefix = ('python3() { ' + shlex.quote(sys.executable)
                      + ' -I -B ' + shlex.quote(str(injector)) + ' '
                      + shlex.quote(fault) + ' "$@"; }\n')
        return subprocess.run(
            ["/usr/bin/bash", "-c", prefix + finalization_shell(), "fence-test",
             str(self.cli), str(self.runtime), str(self.journal), str(self.marker)],
            env={"PATH": "/usr/bin:/bin", "HOME": str(self.root),
                 "LANG": "C", "LC_ALL": "C"},
            capture_output=True, text=True, timeout=5, check=False)

    def assert_refused(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "return=1 armed=1\n")
        self.assertNotEqual(result.stderr, "")
        self.assertEqual(self.marker.read_bytes(), b"removed-by=khephri.sia\n")
        current = self.marker.stat()
        self.assertEqual((current.st_dev, current.st_ino),
                         (self.marker_identity.st_dev, self.marker_identity.st_ino))

    def test_success_restores_survivor_and_retires_journal_and_marker(self):
        self.write_journal()
        result = self.invoke()
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "return=0 armed=0\n", ""))
        self.assertEqual(stat.S_IMODE(self.cli.stat().st_mode), 0o700)
        self.assertFalse(self.journal.exists())
        self.assertFalse(self.marker.exists())

    def test_absent_public_paths_keep_removal_marker(self):
        self.cli.unlink()
        result = self.invoke()
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "return=0 armed=0\n", ""))
        self.assertTrue(self.marker.exists())
        self.assertFalse(self.journal.exists())

    def test_survivor_without_journal_cannot_clear_marker(self):
        self.assert_refused(self.invoke())
        self.assertEqual(stat.S_IMODE(self.cli.stat().st_mode), 0)

    def test_invalid_journals_are_retained_without_completion(self):
        invalid = ({"schema": "wrong", "entries": []}, [],
                   {"schema": "sia-launch-fence-v1", "entries": [None]})
        for value in invalid:
            with self.subTest(value=value):
                self.journal.write_text(json.dumps(value))
                original = self.journal.read_bytes()
                self.assert_refused(self.invoke())
                self.assertEqual(self.journal.read_bytes(), original)
                self.assertEqual(stat.S_IMODE(self.cli.stat().st_mode), 0)
        self.journal.write_bytes(b"{")
        self.assert_refused(self.invoke())
        self.assertEqual(self.journal.read_bytes(), b"{")

    def test_changed_surviving_identity_retains_both_gates(self):
        self.entry["inode"] = 0
        self.write_journal()
        original = self.journal.read_bytes()
        self.assert_refused(self.invoke())
        self.assertEqual(self.journal.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(self.cli.stat().st_mode), 0)

    def test_partial_restoration_is_failure_with_recovery_marker(self):
        later = self.root / "later"
        later.write_bytes(b"later command\n")
        later.chmod(0)
        self.payload["entries"].append(dict(self.entry, path=str(later), inode=0))
        self.write_journal()
        original = self.journal.read_bytes()
        self.assert_refused(self.invoke())
        self.assertEqual(self.journal.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(self.cli.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(later.stat().st_mode), 0)

    def test_syscall_errors_and_interruption_do_not_report_completion(self):
        faults = (("chmod-error", "injected chmod failure"),
                  ("chmod-signal", "Terminated"),
                  ("file-sync-error", "injected file fsync failure"),
                  ("journal-unlink-error", "injected journal unlink failure"),
                  ("directory-sync-error", "injected directory fsync failure"))
        for fault, message in faults:
            with self.subTest(fault=fault):
                self.cli.chmod(0)
                self.write_journal()
                result = self.invoke(fault)
                self.assertIn(message, result.stderr)
                self.assert_refused(result)
                self.assertEqual(self.journal.exists(), fault != "directory-sync-error")

    def test_marker_removal_failure_keeps_completion_armed(self):
        self.write_journal()
        result = self.invoke("marker-unlink-error")
        self.assertIn("injected marker unlink failure", result.stderr)
        self.assert_refused(result)
        self.assertFalse(self.journal.exists())
        self.assertEqual(stat.S_IMODE(self.cli.stat().st_mode), 0o700)


if __name__ == "__main__":
    unittest.main()
