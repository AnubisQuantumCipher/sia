"""Bounded FIFO refusals at the actual extracted installer front doors.

These isolated subprocess cases do not execute the complete installer, Bun,
or the real engine. Existing overlay tests retain the regular-file positives.
"""

import os
import subprocess
import sys
import tempfile
import unittest

from tests import test_gbrain_overlay as overlay


def _identity(path):
    info = os.lstat(path)
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class GbrainFrontdoorFifo(unittest.TestCase):
    def _refused_without_change(self, program, arguments, path, label, files):
        before = _identity(path)
        contents = {name: overlay._read(name) for name in files}
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-W", "error", "-c", program, *arguments],
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                timeout=3, check=False)
        finally:
            self.assertEqual(_identity(path), before)
            self.assertEqual({name: overlay._read(name) for name in files}, contents)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), label + " is not an admitted regular file")

    def test_pin_frontdoor_refuses_fifo_pin_and_overlay_without_writer(self):
        program = overlay._embedded_python(overlay._installer(), "gbrain_pin_frontdoor")
        for target, label in (("pin", "GBRAIN_PIN"), ("patch", "GBRAIN_OVERLAY.patch")):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as root:
                paths = {"pin": os.path.join(root, "GBRAIN_PIN"),
                         "patch": os.path.join(root, "overlay.patch")}
                overlay._write(paths["pin"], overlay._read(overlay.PIN_PATH))
                overlay._write(paths["patch"], overlay._read(overlay.OVERLAY_PATH))
                os.unlink(paths[target])
                os.mkfifo(paths[target], 0o600)
                other = paths["patch" if target == "pin" else "pin"]
                self._refused_without_change(
                    program, [paths["pin"], paths["patch"]], paths[target], label, [other])

    def test_overlay_frontdoor_refuses_fifo_inputs_before_git_mutation(self):
        program = overlay._embedded_python(overlay._installer(), "gbrain_overlay_frontdoor")
        for target, label in (("patch", "GBRAIN_OVERLAY.patch"),
                              ("bun.lock", "gbrain bun.lock"),
                              ("package.json", "gbrain package.json")):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as root:
                fixture = overlay._make_overlay_fixture(root)
                source = overlay._clone_detached(fixture, root, "candidate")
                path = fixture["patch"] if target == "patch" else os.path.join(source, target)
                unchanged = [os.path.join(source, "src", "value.ts"),
                             os.path.join(source, ".git", "HEAD"),
                             os.path.join(source, ".git", "index")]
                # Git's index is binary: compare its hash separately.
                index = unchanged.pop()
                index_before = overlay._sha256(index)
                os.unlink(path)
                os.mkfifo(path, 0o600)
                try:
                    self._refused_without_change(
                        program, overlay._apply_arguments(fixture, source),
                        path, label, unchanged)
                finally:
                    self.assertEqual(overlay._sha256(index), index_before)


if __name__ == "__main__":
    unittest.main()
