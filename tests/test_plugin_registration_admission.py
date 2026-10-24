"""Actual resident registration observer with private Linux files and faults."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home


SOURCE = Path(__file__).resolve().parents[1] / "bin/sia-brainstem"
WORKER = """
import importlib.machinery, importlib.util, json, os, sys
from unittest.mock import patch
loader = importlib.machinery.SourceFileLoader('registration_test', sys.argv[1])
spec = importlib.util.spec_from_loader(loader.name, loader)
brainstem = importlib.util.module_from_spec(spec)
loader.exec_module(brainstem)
home, fault, component = sys.argv[2:]
opened = []
real_open, real_fstat, real_stat = os.open, os.fstat, os.stat
def open_path(path, flags, *args, **kwargs):
    fd = real_open(path, flags, *args, **kwargs)
    if path == component:
        opened.append(fd)
    return fd
def fail():
    if fault.endswith('interrupt'):
        raise KeyboardInterrupt('injected registration metadata failure')
    raise OSError('injected registration metadata failure')
def fstat(fd):
    if fault.startswith('fstat-') and fd in opened:
        fail()
    return real_fstat(fd)
def named_stat(path, *args, **kwargs):
    if fault.startswith('stat-') and path == component:
        fail()
    return real_stat(path, *args, **kwargs)
before = len(os.listdir('/proc/self/fd'))
try:
    with patch.object(os, 'open', open_path), patch.object(os, 'fstat', fstat), \
            patch.object(os, 'stat', named_stat):
        outcome = brainstem._plugin_registration_present(home)
except (RuntimeError, KeyboardInterrupt) as error:
    outcome = type(error).__name__
after = len(os.listdir('/proc/self/fd'))
print(json.dumps({'outcome': outcome, 'before': before, 'after': after,
                  'fault_target_opened': len(opened)}))
"""


class PluginRegistrationAdmission(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=sia_test_home.ISOLATED_HOME)
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.plugin = self.home / ".config/omarchy/plugins/khephri.sia"
        self.plugin.mkdir(parents=True, mode=0o700)
        self.manifest = self.plugin / "manifest.json"

    def observe(self, expected, fault="", component=""):
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-W", "error::ResourceWarning", "-c",
             WORKER, str(SOURCE), str(self.home), fault, component],
            env=dict(os.environ, HOME=str(self.home)), capture_output=True,
            text=True, timeout=5, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        self.assertEqual(report["outcome"], expected)
        self.assertEqual(report["before"], report["after"])
        if fault:
            self.assertEqual(report["fault_target_opened"], 1)

    def test_fifo_without_writer_refuses_and_closes_descriptors(self):
        os.mkfifo(self.manifest, 0o600)
        self.observe("RuntimeError")

    def test_fifo_with_peer_refuses_without_reading_stream(self):
        os.mkfifo(self.manifest, 0o600)
        peer = os.open(self.manifest, os.O_RDWR | os.O_NONBLOCK)
        self.addCleanup(os.close, peer)
        payload = b'{"id":"khephri.sia","version":"test"}'
        self.assertEqual(os.write(peer, payload), len(payload))
        self.observe("RuntimeError")
        self.assertEqual(os.read(peer, len(payload)), payload)

    def test_directory_and_symlink_refuse(self):
        self.manifest.mkdir()
        self.observe("RuntimeError")
        self.manifest.rmdir()
        self.manifest.symlink_to(self.home / "missing")
        self.observe("RuntimeError")

    def test_absence_returns_false(self):
        self.observe(False)

    def test_regular_wrong_plugin_is_not_registration(self):
        self.manifest.write_text('{"id":"another-plugin","version":"test"}')
        self.manifest.chmod(0o600)
        self.observe(False)

    def test_acquired_child_closes_after_metadata_error_or_interrupt(self):
        for component in (".config", "omarchy", "plugins", "khephri.sia"):
            for fault, expected in (("fstat-error", "RuntimeError"),
                                    ("stat-error", "RuntimeError"),
                                    ("fstat-interrupt", "KeyboardInterrupt"),
                                    ("stat-interrupt", "KeyboardInterrupt")):
                with self.subTest(component=component, fault=fault):
                    self.observe(expected, fault, component)


if __name__ == "__main__":
    unittest.main()
