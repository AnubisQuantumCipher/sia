"""Additive candidate/source-delivery runtime closure; never an installation.

Expected membership is independent of the production ladder and installer.
The artificial file bytes are each basename plus LF, using the existing
independent fixture digest reference. No new digest is learned from production.
"""

import hashlib
import json
import os
import shlex
import stat
import tempfile
import unittest

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_release as release
from tests import test_runtime_v10_live_loop as v10


V11_ADDITIONS = (
    "siacontrollercandidate.py",
    "siacontrollerdeliveryepoch.py",
    "siacontrollerdeliveryinput.py",
    "siacontrollerdeliverywrapper.py",
    "siadelivery.py",
)
EXPECTED_V11_RUNTIME_NAMES = v10.EXPECTED_V10_RUNTIME_NAMES + V11_ADDITIONS
V11_SALT = b"sia-runtime-v11\0"


class RuntimeV11DeliveryClosure(unittest.TestCase):
    shell_digest = staticmethod(v10.RuntimeV10LiveLoop.shell_digest)
    fence_paths = staticmethod(v10.RuntimeV10LiveLoop.fence_paths)
    publish_fence = staticmethod(v10.RuntimeV10LiveLoop.publish_fence)
    fence_result = staticmethod(v10.RuntimeV10LiveLoop.fence_result)

    def test_exact_v11_roster_remains_in_the_complete_historical_ladder(self):
        authority = release.SIARELEASE
        authority.validate_runtime_ladder()
        self.assertEqual(authority.RUNTIME_LADDER[2], (
            V11_SALT, EXPECTED_V11_RUNTIME_NAMES, V11_ADDITIONS))
        fixtures = {label: (salt, names, digest)
                    for label, salt, names, digest in release.RUNTIME_RUNG_FIXTURES}
        expected_history = ((v10.V10_SALT, v10.EXPECTED_V10_RUNTIME_NAMES,
                             v10.V10_ADDITIONS),) + tuple(
            (fixtures[label][0], fixtures[label][1], v10.HISTORICAL_SELECTORS[label])
            for label in v10.HISTORICAL_LABELS)
        self.assertEqual(authority.RUNTIME_LADDER[3:], expected_history)
        with tempfile.TemporaryDirectory() as runtime:
            release._plant_runtime_tree(runtime, EXPECTED_V11_RUNTIME_NAMES)
            self.assertEqual(authority.runtime_rung(runtime),
                             (V11_SALT, EXPECTED_V11_RUNTIME_NAMES))
            self.assertEqual(authority.runtime_tree_digest(runtime),
                             v10.reference_fixture_digest(V11_SALT, EXPECTED_V11_RUNTIME_NAMES))

    def test_release_snapshot_and_stage_retain_the_complete_v11_roster(self):
        installer = release._read("install.sh")
        release_files = tuple(shlex.split(installer.split(
            "SIA_RELEASE_FILES=(", 1)[1].split("\n)", 1)[0]))
        staged = release._staged_runtime_members(installer)
        self.assertEqual(len(staged), len(set(staged)))
        self.assertTrue(set(EXPECTED_V11_RUNTIME_NAMES).issubset(staged))
        for name in V11_ADDITIONS:
            with self.subTest(member=name):
                self.assertEqual(staged.count(name), 1)
                self.assertEqual(release_files.count("bin/" + name), 1)
                self.assertTrue(os.path.isfile(os.path.join(release.REPO, "bin", name)))

    def test_each_new_child_selects_current_before_any_peer_exists(self):
        for marker in V11_ADDITIONS:
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as runtime:
                release._plant_runtime_tree(runtime, v10.EXPECTED_V10_RUNTIME_NAMES)
                release._write(os.path.join(runtime, marker), marker + "\n", 0o644)
                self.assertEqual(release.SIARELEASE.runtime_rung(runtime),
                                 (V11_SALT, EXPECTED_V11_RUNTIME_NAMES))
                with self.assertRaises(FileNotFoundError):
                    release.SIARELEASE.runtime_tree_digest(runtime)

    def test_install_uninstall_and_fence_refuse_every_missing_current_child(self):
        functions = tuple((site, release._runtime_tree_digest_shell(release._read(site + ".sh")))
                          for site in ("install", "uninstall"))
        fence = release._uninstaller_fenced_runtime_shell(release._read("uninstall.sh"))
        current_digest = v10.reference_fixture_digest(V11_SALT, EXPECTED_V11_RUNTIME_NAMES)
        prior_digest = v10.reference_fixture_digest(v10.V10_SALT, v10.EXPECTED_V10_RUNTIME_NAMES)
        with tempfile.TemporaryDirectory() as root:
            runtime = os.path.join(root, "runtime")
            release._plant_runtime_tree(runtime, EXPECTED_V11_RUNTIME_NAMES)
            paths = self.fence_paths(root, runtime)
            for site, function in functions:
                with self.subTest(site=site, state="complete"):
                    result = self.shell_digest(function, runtime)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), current_digest)
            self.publish_fence(paths, current_digest)
            result = self.fence_result(fence, paths)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.publish_fence(paths, prior_digest)
            self.assertNotEqual(self.fence_result(fence, paths).returncode, 0)
            for member in V11_ADDITIONS:
                with self.subTest(missing=member):
                    path = os.path.join(runtime, member)
                    os.unlink(path)
                    self.assertEqual(release.SIARELEASE.runtime_rung(runtime),
                                     (V11_SALT, EXPECTED_V11_RUNTIME_NAMES))
                    with self.assertRaises(FileNotFoundError):
                        release.SIARELEASE.runtime_tree_digest(runtime)
                    for _site, function in functions:
                        self.assertNotEqual(self.shell_digest(function, runtime).returncode, 0)
                    for receipt in (current_digest, prior_digest):
                        self.publish_fence(paths, receipt)
                        self.assertNotEqual(self.fence_result(fence, paths).returncode, 0)
                    release._write(path, member + "\n", 0o644)

    def test_each_new_mode_zero_member_requires_its_exact_fence_entry(self):
        fence = release._uninstaller_fenced_runtime_shell(release._read("uninstall.sh"))
        current_digest = v10.reference_fixture_digest(V11_SALT, EXPECTED_V11_RUNTIME_NAMES)
        with tempfile.TemporaryDirectory() as root:
            runtime = os.path.join(root, "runtime")
            release._plant_runtime_tree(runtime, EXPECTED_V11_RUNTIME_NAMES)
            paths = self.fence_paths(root, runtime)
            for member in V11_ADDITIONS:
                with self.subTest(member=member):
                    target = os.path.join(runtime, member)
                    before = os.stat(target, follow_symlinks=False)
                    entry = {"path": target, "device": before.st_dev, "inode": before.st_ino,
                             "mode": stat.S_IMODE(before.st_mode),
                             "sha256": hashlib.sha256((member + "\n").encode("utf-8")).hexdigest()}
                    self.publish_fence(paths, current_digest)
                    with open(paths["journal"], encoding="utf-8") as stream:
                        journal = json.load(stream)
                    journal["entries"] = [entry]
                    release._write(paths["journal"], json.dumps(
                        journal, sort_keys=True, separators=(",", ":")) + "\n", 0o600)
                    os.chmod(target, 0)
                    try:
                        result = self.fence_result(fence, paths)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.publish_fence(paths, current_digest)
                        self.assertNotEqual(self.fence_result(fence, paths).returncode, 0)
                    finally:
                        os.chmod(target, stat.S_IMODE(before.st_mode))

    def test_complete_old_tree_and_receipt_still_work_without_any_new_selector(self):
        digest = v10.reference_fixture_digest(v10.V10_SALT, v10.EXPECTED_V10_RUNTIME_NAMES)
        fence = release._uninstaller_fenced_runtime_shell(release._read("uninstall.sh"))
        with tempfile.TemporaryDirectory() as root:
            runtime = os.path.join(root, "runtime")
            release._plant_runtime_tree(runtime, v10.EXPECTED_V10_RUNTIME_NAMES)
            self.assertEqual(release.SIARELEASE.runtime_rung(runtime),
                             (v10.V10_SALT, v10.EXPECTED_V10_RUNTIME_NAMES))
            self.assertEqual(release.SIARELEASE.runtime_tree_digest(runtime), digest)
            for site in ("install", "uninstall"):
                function = release._runtime_tree_digest_shell(release._read(site + ".sh"))
                result = self.shell_digest(function, runtime)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), digest)
            paths = self.fence_paths(root, runtime)
            self.publish_fence(paths, digest)
            result = self.fence_result(fence, paths)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
