"""Additive release closure for observable idle replay and claim admission.

The live-loop helpers already exist in the repository. They must also cross
the release-source snapshot and installed receipt boundary. Every new member
selects v10, so an incomplete current tree cannot inherit a historical v9
receipt. The accepted v1-v9 membership, order, selectors and fixture digests
remain unchanged.

The digest reference below hashes a declared artificial tree: each file's
bytes are its basename followed by LF. It does not execute production digest
code, import a production roster, or learn an expected value from the result
under test. Existing literal historical fixture digests check the reference.
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
    from tests import sia_test_home  # type: ignore

from tests import test_release as release
from tests import test_runtime_v9_source_controller as v9


V10_ADDITIONS = (
    "siacognitiveregistry.py",
    "siacontrolleridle.py",
    "sialiveidle.py",
    "sialiveview.py",
    "siasourcegist.py",
)
EXPECTED_V10_RUNTIME_NAMES = v9.EXPECTED_V9_RUNTIME_NAMES + V10_ADDITIONS
V10_SALT = b"sia-runtime-v10\0"
HISTORICAL_LABELS = ("v9",) + v9.HISTORICAL_LABELS
HISTORICAL_SELECTORS = {"v9": v9.V9_ADDITIONS, **v9.HISTORICAL_SELECTORS}


def reference_fixture_digest(salt, names):
    framed = salt + b"".join(
        name.encode("utf-8") + b"\0"
        + hashlib.sha256((name + "\n").encode("utf-8")).digest()
        for name in names)
    return hashlib.sha256(framed).hexdigest()


class RuntimeV10LiveLoop(unittest.TestCase):
    shell_digest = staticmethod(v9.RuntimeV9SourceController.shell_digest)
    fence_paths = staticmethod(v9.RuntimeV9SourceController.fence_paths)
    publish_fence = staticmethod(v9.RuntimeV9SourceController.publish_fence)
    fence_result = staticmethod(v9.RuntimeV9SourceController.fence_result)

    def test_v10_exact_roster_preserves_every_historical_contract(self):
        authority = release.SIARELEASE
        authority.validate_runtime_ladder()
        v10_index = next(index for index, rung in enumerate(authority.RUNTIME_LADDER)
                         if rung[0] == V10_SALT)
        self.assertEqual(authority.RUNTIME_LADDER[v10_index], (
            V10_SALT, EXPECTED_V10_RUNTIME_NAMES, V10_ADDITIONS))
        fixtures = {
            label: (salt, names, digest)
            for label, salt, names, digest in release.RUNTIME_RUNG_FIXTURES
        }
        expected_history = tuple(
            (fixtures[label][0], fixtures[label][1],
             HISTORICAL_SELECTORS[label])
            for label in HISTORICAL_LABELS)
        self.assertEqual(authority.RUNTIME_LADDER[v10_index + 1:], expected_history)
        self.assertEqual(EXPECTED_V10_RUNTIME_NAMES[:-len(V10_ADDITIONS)],
                         v9.EXPECTED_V9_RUNTIME_NAMES)
        for label in HISTORICAL_LABELS:
            salt, names, digest = fixtures[label]
            with self.subTest(historical_reference=label):
                self.assertEqual(reference_fixture_digest(salt, names), digest)
        with tempfile.TemporaryDirectory() as runtime:
            release._plant_runtime_tree(runtime, EXPECTED_V10_RUNTIME_NAMES)
            self.assertEqual(authority.runtime_rung(runtime),
                             (V10_SALT, EXPECTED_V10_RUNTIME_NAMES))
            self.assertEqual(authority.runtime_tree_digest(runtime),
                             reference_fixture_digest(
                                 V10_SALT, EXPECTED_V10_RUNTIME_NAMES))

    def test_release_snapshot_and_install_stage_every_v10_member_once(self):
        installer = release._read("install.sh")
        release_files = tuple(shlex.split(installer.split(
            "SIA_RELEASE_FILES=(", 1)[1].split("\n)", 1)[0]))
        staged = release._staged_runtime_members(installer)
        self.assertEqual(len(staged), len(set(staged)))
        # Exact current-stage closure belongs to the latest rung's test and
        # RuntimeModuleClosure. Historical v10 members still occur once each.
        for name in EXPECTED_V10_RUNTIME_NAMES:
            with self.subTest(historical_member=name):
                self.assertEqual(staged.count(name), 1)
        for name in V10_ADDITIONS:
            with self.subTest(member=name):
                self.assertEqual(staged.count(name), 1)
                self.assertEqual(release_files.count("bin/" + name), 1)
                self.assertTrue(os.path.isfile(os.path.join(
                    release.REPO, "bin", name)))

    def test_install_uninstall_accept_exact_v10_and_refuse_every_partial_tree(self):
        digest_functions = tuple(
            (site, release._runtime_tree_digest_shell(release._read(site + ".sh")))
            for site in ("install", "uninstall"))
        fence = release._uninstaller_fenced_runtime_shell(
            release._read("uninstall.sh"))
        expected_digest = reference_fixture_digest(
            V10_SALT, EXPECTED_V10_RUNTIME_NAMES)
        with tempfile.TemporaryDirectory() as root:
            runtime = os.path.join(root, "runtime")
            release._plant_runtime_tree(runtime, EXPECTED_V10_RUNTIME_NAMES)
            paths = self.fence_paths(root, runtime)
            for site, function in digest_functions:
                with self.subTest(site=site, state="complete-v10"):
                    result = self.shell_digest(function, runtime)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), expected_digest)
            self.publish_fence(paths, expected_digest)
            accepted = self.fence_result(fence, paths)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.publish_fence(paths, v9.EXPECTED_V9_TREE_DIGEST)
            self.assertNotEqual(self.fence_result(fence, paths).returncode, 0)
            for missing in V10_ADDITIONS:
                with self.subTest(missing=missing):
                    path = os.path.join(runtime, missing)
                    os.unlink(path)
                    self.assertEqual(release.SIARELEASE.runtime_rung(runtime),
                                     (V10_SALT, EXPECTED_V10_RUNTIME_NAMES))
                    with self.assertRaises(FileNotFoundError):
                        release.SIARELEASE.runtime_tree_digest(runtime)
                    for _site, function in digest_functions:
                        self.assertNotEqual(
                            self.shell_digest(function, runtime).returncode, 0)
                    for receipt in (expected_digest, v9.EXPECTED_V9_TREE_DIGEST):
                        self.publish_fence(paths, receipt)
                        self.assertNotEqual(
                            self.fence_result(fence, paths).returncode, 0)
                    release._write(path, missing + "\n", 0o644)
            self.publish_fence(paths, expected_digest)
            self.assertEqual(self.fence_result(fence, paths).returncode, 0)

    def test_each_new_marker_selects_v10_without_its_missing_peers(self):
        for marker in V10_ADDITIONS:
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as root:
                runtime = os.path.join(root, "runtime")
                release._plant_runtime_tree(runtime, v9.EXPECTED_V9_RUNTIME_NAMES)
                release._write(os.path.join(runtime, marker), marker + "\n", 0o644)
                self.assertEqual(release.SIARELEASE.runtime_rung(runtime),
                                 (V10_SALT, EXPECTED_V10_RUNTIME_NAMES))
                with self.assertRaises(FileNotFoundError):
                    release.SIARELEASE.runtime_tree_digest(runtime)

    def test_uninstall_launch_fence_covers_each_new_mode_zero_member(self):
        fence = release._uninstaller_fenced_runtime_shell(
            release._read("uninstall.sh"))
        expected_digest = reference_fixture_digest(
            V10_SALT, EXPECTED_V10_RUNTIME_NAMES)
        with tempfile.TemporaryDirectory() as root:
            runtime = os.path.join(root, "runtime")
            release._plant_runtime_tree(runtime, EXPECTED_V10_RUNTIME_NAMES)
            paths = self.fence_paths(root, runtime)
            for member in V10_ADDITIONS:
                with self.subTest(member=member):
                    target = os.path.join(runtime, member)
                    before = os.stat(target, follow_symlinks=False)
                    entry = {
                        "path": target, "device": before.st_dev,
                        "inode": before.st_ino, "mode": stat.S_IMODE(before.st_mode),
                        "sha256": hashlib.sha256(
                            (member + "\n").encode("utf-8")).hexdigest(),
                    }
                    self.publish_fence(paths, expected_digest)
                    with open(paths["journal"], encoding="utf-8") as stream:
                        journal = json.load(stream)
                    journal["entries"] = [entry]
                    release._write(paths["journal"], json.dumps(
                        journal, sort_keys=True, separators=(",", ":")) + "\n", 0o600)
                    os.chmod(target, 0)
                    try:
                        accepted = self.fence_result(fence, paths)
                        self.assertEqual(accepted.returncode, 0, accepted.stderr)
                        self.publish_fence(paths, expected_digest)
                        self.assertNotEqual(
                            self.fence_result(fence, paths).returncode, 0)
                    finally:
                        os.chmod(target, stat.S_IMODE(before.st_mode))

    def test_historical_v9_tree_and_uninstall_receipt_remain_accepted(self):
        fence = release._uninstaller_fenced_runtime_shell(
            release._read("uninstall.sh"))
        with tempfile.TemporaryDirectory() as root:
            runtime = os.path.join(root, "runtime")
            release._plant_runtime_tree(runtime, v9.EXPECTED_V9_RUNTIME_NAMES)
            self.assertEqual(release.SIARELEASE.runtime_rung(runtime),
                             (b"sia-runtime-v9\0", v9.EXPECTED_V9_RUNTIME_NAMES))
            self.assertEqual(release.SIARELEASE.runtime_tree_digest(runtime),
                             v9.EXPECTED_V9_TREE_DIGEST)
            paths = self.fence_paths(root, runtime)
            self.publish_fence(paths, v9.EXPECTED_V9_TREE_DIGEST)
            accepted = self.fence_result(fence, paths)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)


if __name__ == "__main__":
    unittest.main()
