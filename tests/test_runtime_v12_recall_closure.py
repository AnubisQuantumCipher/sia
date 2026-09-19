"""Complete recall-front-door runtime closure without installation.

Expected membership is independent of the production ladder and installer.
Artificial member bytes are each basename plus LF, reusing the existing
independent fixture digest implementation rather than production hashing.
"""

import os
import shlex
import tempfile
import unittest

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_release as release
from tests import test_runtime_v10_live_loop as v10
from tests import test_runtime_v11_delivery_closure as v11


V12_ADDITIONS = (
    "siacontrollerdeliverywriter.py", "siacontrollerrecallprojection.py",
    "siacontrollerrecalloutput.py", "siacontrollerrecallcli.py",
    "siagetrenderadmit.py", "siainstalledengine.py",
    "siainstalledexpectations.py",
)
EXPECTED_V12_RUNTIME_NAMES = v11.EXPECTED_V11_RUNTIME_NAMES + V12_ADDITIONS
V12_SALT = b"sia-runtime-v12\0"


class RuntimeV12RecallClosure(unittest.TestCase):
    shell_digest = staticmethod(v11.RuntimeV11DeliveryClosure.shell_digest)
    fence_paths = staticmethod(v11.RuntimeV11DeliveryClosure.fence_paths)
    publish_fence = staticmethod(v11.RuntimeV11DeliveryClosure.publish_fence)
    fence_result = staticmethod(v11.RuntimeV11DeliveryClosure.fence_result)

    def test_exact_current_roster_preserves_every_historical_rung(self):
        authority = release.SIARELEASE
        authority.validate_runtime_ladder()
        # Located by salt, as the v9 and v10 closures already do: a fixed
        # index asserts how many newer rungs exist, which is not what
        # "preserves every historical rung" means.
        v12_index = next(index for index, rung in enumerate(authority.RUNTIME_LADDER)
                         if rung[0] == V12_SALT)
        self.assertEqual(authority.RUNTIME_LADDER[v12_index], (
            V12_SALT, EXPECTED_V12_RUNTIME_NAMES, V12_ADDITIONS))
        self.assertEqual(authority.RUNTIME_LADDER[v12_index + 1], (
            v11.V11_SALT, v11.EXPECTED_V11_RUNTIME_NAMES,
            v11.V11_ADDITIONS))
        fixtures = {label: (salt, names, digest)
                    for label, salt, names, digest
                    in release.RUNTIME_RUNG_FIXTURES}
        expected_tail = ((v10.V10_SALT, v10.EXPECTED_V10_RUNTIME_NAMES,
                          v10.V10_ADDITIONS),) + tuple(
            (fixtures[label][0], fixtures[label][1],
             v10.HISTORICAL_SELECTORS[label])
            for label in v10.HISTORICAL_LABELS)
        self.assertEqual(authority.RUNTIME_LADDER[v12_index + 2:], expected_tail)
        with tempfile.TemporaryDirectory() as runtime:
            release._plant_runtime_tree(runtime, EXPECTED_V12_RUNTIME_NAMES)
            self.assertEqual(authority.runtime_rung(runtime),
                             (V12_SALT, EXPECTED_V12_RUNTIME_NAMES))
            self.assertEqual(
                authority.runtime_tree_digest(runtime),
                v10.reference_fixture_digest(
                    V12_SALT, EXPECTED_V12_RUNTIME_NAMES))

    def test_release_snapshot_and_stage_are_exactly_the_v12_roster(self):
        installer = release._read("install.sh")
        release_files = tuple(shlex.split(installer.split(
            "SIA_RELEASE_FILES=(", 1)[1].split("\n)", 1)[0]))
        staged = release._staged_runtime_members(installer)
        self.assertEqual(len(staged), len(set(staged)))
        self.assertTrue(set(EXPECTED_V12_RUNTIME_NAMES).issubset(staged))
        for name in V12_ADDITIONS:
            with self.subTest(member=name):
                self.assertEqual(staged.count(name), 1)
                self.assertEqual(release_files.count("bin/" + name), 1)
                self.assertTrue(os.path.isfile(
                    os.path.join(release.REPO, "bin", name)))

    def test_each_v12_selector_refuses_an_incomplete_peer_set(self):
        for marker in V12_ADDITIONS:
            with self.subTest(marker=marker), \
                    tempfile.TemporaryDirectory() as runtime:
                release._plant_runtime_tree(
                    runtime, v11.EXPECTED_V11_RUNTIME_NAMES)
                release._write(
                    os.path.join(runtime, marker), marker + "\n", 0o644)
                self.assertEqual(release.SIARELEASE.runtime_rung(runtime),
                                 (V12_SALT, EXPECTED_V12_RUNTIME_NAMES))
                with self.assertRaises(FileNotFoundError):
                    release.SIARELEASE.runtime_tree_digest(runtime)

    def test_install_uninstall_and_fence_refuse_every_missing_v12_child(self):
        functions = tuple(
            (site, release._runtime_tree_digest_shell(
                release._read(site + ".sh")))
            for site in ("install", "uninstall"))
        fence = release._uninstaller_fenced_runtime_shell(
            release._read("uninstall.sh"))
        current_digest = v10.reference_fixture_digest(
            V12_SALT, EXPECTED_V12_RUNTIME_NAMES)
        prior_digest = v10.reference_fixture_digest(
            v11.V11_SALT, v11.EXPECTED_V11_RUNTIME_NAMES)
        with tempfile.TemporaryDirectory() as root:
            runtime = os.path.join(root, "runtime")
            release._plant_runtime_tree(runtime, EXPECTED_V12_RUNTIME_NAMES)
            paths = self.fence_paths(root, runtime)
            for site, function in functions:
                with self.subTest(site=site, state="complete"):
                    result = self.shell_digest(function, runtime)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), current_digest)
            self.publish_fence(paths, current_digest)
            self.assertEqual(
                self.fence_result(fence, paths).returncode, 0)
            self.publish_fence(paths, prior_digest)
            self.assertNotEqual(
                self.fence_result(fence, paths).returncode, 0)
            for member in V12_ADDITIONS:
                with self.subTest(missing=member):
                    path = os.path.join(runtime, member)
                    os.unlink(path)
                    self.assertEqual(release.SIARELEASE.runtime_rung(runtime),
                                     (V12_SALT, EXPECTED_V12_RUNTIME_NAMES))
                    with self.assertRaises(FileNotFoundError):
                        release.SIARELEASE.runtime_tree_digest(runtime)
                    for _site, function in functions:
                        self.assertNotEqual(
                            self.shell_digest(function, runtime).returncode, 0)
                    for receipt in (current_digest, prior_digest):
                        self.publish_fence(paths, receipt)
                        self.assertNotEqual(
                            self.fence_result(fence, paths).returncode, 0)
                    release._write(path, member + "\n", 0o644)

    def test_complete_v11_tree_and_receipt_remain_recognized(self):
        digest = v10.reference_fixture_digest(
            v11.V11_SALT, v11.EXPECTED_V11_RUNTIME_NAMES)
        fence = release._uninstaller_fenced_runtime_shell(
            release._read("uninstall.sh"))
        with tempfile.TemporaryDirectory() as root:
            runtime = os.path.join(root, "runtime")
            release._plant_runtime_tree(
                runtime, v11.EXPECTED_V11_RUNTIME_NAMES)
            self.assertEqual(release.SIARELEASE.runtime_rung(runtime),
                             (v11.V11_SALT,
                              v11.EXPECTED_V11_RUNTIME_NAMES))
            self.assertEqual(
                release.SIARELEASE.runtime_tree_digest(runtime), digest)
            for site in ("install", "uninstall"):
                function = release._runtime_tree_digest_shell(
                    release._read(site + ".sh"))
                result = self.shell_digest(function, runtime)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), digest)
            paths = self.fence_paths(root, runtime)
            self.publish_fence(paths, digest)
            result = self.fence_result(fence, paths)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
