"""RED release-closure contract for the source-controller runtime rung.

Runtime v9 is cumulative: it adds the epoch transaction and its admitted
runner without changing any byte of the accepted v1-v8 membership history.
Both files must cross the release-source front door, enter the installed
runtime tree, participate in its receipt digest, and remain covered by the
uninstaller's launch fence.  A partial v9 tree cannot fall back to v8.
"""

import json
import os
import shlex
import subprocess
import tempfile
import unittest

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

from tests import test_release as release


V9_ADDITIONS = (
    "siacontrollerepoch.py",
    "siacontrollersourcerunner.py",
)

# Independent expected-current roster.  Do not derive this from production's
# RUNTIME_LADDER or from install.sh: agreement among those is what is tested.
EXPECTED_V9_RUNTIME_NAMES = (
    "sia-brainstem", "sia-brainstem.py", "sia-cli", "sia-ledger",
    "sia-mcp", "siabench.py", "sialib.py", "siamind.py", "siaqueue.py",
    "siatakes.py", "siasenses.py", "siacapsule.py", "siabackup.py",
    "siarestoreadmit.py", "sia-continuity-worker", "siagraph.py",
    "siathought.py", "siaactivation.py", "siacognitivebaseline.py",
    "siacognitivecommand.py", "siacognitivehistory.py",
    "siacognitiveselect.py", "siacontrollerliveinput.py",
    "siacontrollerstatus.py", "siacoretrieval.py", "siacortexrepair.py",
    "siaencoding.py", "siaeventintake.py", "siaeventplan.py", "siagist.py",
    "siajournalcapture.py", "sialivegist.py", "sialiveloop.py",
    "sialivepublication.py", "siasourcebatch.py", "siasourcepublication.py",
    "siavector.py", "siavectoradmit.py", "siavectormodel.py",
    "siavectorprepare.py", "siavectorrun.py", "siaworkspace.py",
    "siasourceack.py", "siasourceeffects.py", "siasourceengine.py",
    "siasourcegit.py", "siacontrollerepoch.py",
    "siacontrollersourcerunner.py",
)
EXPECTED_V9_TREE_DIGEST = (
    "8f68448335643681bebf024dd14fa946280f5d888e24d5d0c55688931fadb524")
EXPECTED_V8_TREE_DIGEST = (
    "0225ff0d0a864a8f26ad75f37afb92ced45ef5966ad2c17b7343e5081a8ebcfc")
HISTORICAL_LABELS = ("v8", "v7", "v6", "v5", "v4", "v3", "v2", "v1")
HISTORICAL_SELECTORS = {
    "v8": (
        "siasourceack.py", "siasourceeffects.py", "siasourceengine.py",
        "siasourcegit.py"),
    "v7": ("sialiveloop.py",),
    "v6": ("siathought.py",),
    "v5": ("siagraph.py",),
    "v4": ("siacapsule.py", "siabackup.py", "sia-continuity-worker"),
    "v3": ("siasenses.py",),
    "v2": ("sia-brainstem.py", "sia-cli"),
    "v1": (),
}


class RuntimeV9SourceController(unittest.TestCase):
    @staticmethod
    def shell_digest(function, runtime):
        return subprocess.run(
            ["bash", "-c", function + '\nruntime_tree_digest "$1"\n',
             "runtime-v9-digest", runtime],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False)

    @staticmethod
    def fence_paths(root, runtime):
        managed = os.path.join(root, "managed")
        return {
            "journal": os.path.join(managed, "launch-fence.json"),
            "receipt": os.path.join(managed, "runtime"),
            "tombstone": os.path.join(root, "sia.lifecycle-removed"),
            "runtime": runtime,
        }

    @staticmethod
    def publish_fence(paths, digest):
        release._write(
            paths["receipt"],
            "managed-by=khephri.sia\nkind=runtime\n"
            f"path={paths['runtime']}\nsha256={digest}\n",
            0o600)
        release._write(
            paths["journal"],
            json.dumps({
                "schema": "sia-launch-fence-v1",
                "runtime_before_digest": digest,
                "runtime_digest": digest,
                "cli_digest": "",
                "entries": [],
            }, sort_keys=True, separators=(",", ":")) + "\n",
            0o600)
        release._write(
            paths["tombstone"], "removed-by=khephri.sia\n", 0o600)

    @staticmethod
    def fence_result(function, paths):
        script = function + r'''
set -u
LAUNCH_FENCE_JOURNAL="$TEST_JOURNAL"
LIFECYCLE_TOMBSTONE="$TEST_TOMBSTONE"
RUNTIME_RECEIPT="$TEST_RECEIPT"
RUNTIME_BIN_DIR="$TEST_RUNTIME"
fenced_runtime_authorized
'''
        environment = os.environ.copy()
        environment.update({
            "TEST_JOURNAL": paths["journal"],
            "TEST_TOMBSTONE": paths["tombstone"],
            "TEST_RECEIPT": paths["receipt"],
            "TEST_RUNTIME": paths["runtime"],
        })
        return subprocess.run(
            ["bash", "-c", script], env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    def test_v9_roster_is_exact_and_v1_through_v8_are_unchanged(self):
        authority = release.SIARELEASE
        authority.validate_runtime_ladder()
        expected_top = (
            b"sia-runtime-v9\0", EXPECTED_V9_RUNTIME_NAMES, V9_ADDITIONS)
        self.assertEqual(authority.RUNTIME_LADDER[0], expected_top)

        fixtures = {
            label: (salt, names, digest)
            for label, salt, names, digest in release.RUNTIME_RUNG_FIXTURES
        }
        expected_history = tuple(
            (fixtures[label][0], fixtures[label][1],
             HISTORICAL_SELECTORS[label])
            for label in HISTORICAL_LABELS)
        self.assertEqual(authority.RUNTIME_LADDER[1:], expected_history)
        self.assertEqual(
            EXPECTED_V9_RUNTIME_NAMES[:-len(V9_ADDITIONS)],
            fixtures["v8"][1])
        self.assertEqual(fixtures["v8"][2], EXPECTED_V8_TREE_DIGEST)

        with tempfile.TemporaryDirectory() as runtime:
            release._plant_runtime_tree(runtime, EXPECTED_V9_RUNTIME_NAMES)
            self.assertEqual(
                authority.runtime_rung(runtime), expected_top[:2])
            self.assertEqual(
                authority.runtime_tree_digest(runtime),
                EXPECTED_V9_TREE_DIGEST)

    def test_release_snapshot_and_installer_stage_every_v9_member_once(self):
        installer = release._read("install.sh")
        release_files = tuple(shlex.split(installer.split(
            "SIA_RELEASE_FILES=(", 1)[1].split("\n)", 1)[0]))
        staged = release._staged_runtime_members(installer)

        self.assertEqual(len(staged), len(set(staged)))
        self.assertEqual(set(staged), set(EXPECTED_V9_RUNTIME_NAMES))
        for name in V9_ADDITIONS:
            relative = "bin/" + name
            with self.subTest(member=name):
                self.assertEqual(staged.count(name), 1)
                self.assertEqual(release_files.count(relative), 1)
                self.assertTrue(os.path.isfile(os.path.join(
                    release.REPO, relative)))

    def test_install_uninstall_receipts_accept_v9_and_refuse_partial_v9(self):
        installer_digest = release._runtime_tree_digest_shell(
            release._read("install.sh"))
        uninstaller_digest = release._runtime_tree_digest_shell(
            release._read("uninstall.sh"))
        uninstall_fence = release._uninstaller_fenced_runtime_shell(
            release._read("uninstall.sh"))

        with tempfile.TemporaryDirectory() as root:
            runtime = os.path.join(root, "runtime")
            release._plant_runtime_tree(runtime, EXPECTED_V9_RUNTIME_NAMES)
            paths = self.fence_paths(root, runtime)

            for site, function in (
                    ("install", installer_digest),
                    ("uninstall", uninstaller_digest)):
                with self.subTest(site=site, state="exact-v9"):
                    result = self.shell_digest(function, runtime)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(
                        result.stdout.strip(), EXPECTED_V9_TREE_DIGEST)
            self.publish_fence(paths, EXPECTED_V9_TREE_DIGEST)
            accepted = self.fence_result(uninstall_fence, paths)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)

            # A v8 receipt is historical authority for a v8 tree, never a
            # way to call a complete v9 tree current.
            self.publish_fence(paths, EXPECTED_V8_TREE_DIGEST)
            stale = self.fence_result(uninstall_fence, paths)
            self.assertNotEqual(stale.returncode, 0)

            # Either new marker selects v9.  Therefore losing its peer is a
            # partial-current refusal, not silent fallback to the v8 roster.
            for missing in V9_ADDITIONS:
                with self.subTest(state="partial-v9", missing=missing):
                    os.unlink(os.path.join(runtime, missing))
                    salt, names = release.SIARELEASE.runtime_rung(runtime)
                    self.assertEqual(salt, b"sia-runtime-v9\0")
                    self.assertEqual(names, EXPECTED_V9_RUNTIME_NAMES)
                    with self.assertRaises(FileNotFoundError):
                        release.SIARELEASE.runtime_tree_digest(runtime)
                    for function in (installer_digest, uninstaller_digest):
                        self.assertNotEqual(
                            self.shell_digest(function, runtime).returncode, 0)
                    for digest in (
                            EXPECTED_V9_TREE_DIGEST,
                            EXPECTED_V8_TREE_DIGEST):
                        self.publish_fence(paths, digest)
                        self.assertNotEqual(
                            self.fence_result(
                                uninstall_fence, paths).returncode,
                            0)
                    release._write(
                        os.path.join(runtime, missing), missing + "\n", 0o644)

            self.publish_fence(paths, EXPECTED_V9_TREE_DIGEST)
            recovered = self.fence_result(uninstall_fence, paths)
            self.assertEqual(recovered.returncode, 0, recovered.stderr)

    def test_exact_v8_tree_and_receipt_remain_historical_authority(self):
        fence = release._uninstaller_fenced_runtime_shell(
            release._read("uninstall.sh"))
        with tempfile.TemporaryDirectory() as root:
            runtime = os.path.join(root, "runtime")
            release._plant_runtime_tree(runtime, release.MODERN_V8_RUNTIME_NAMES)
            self.assertEqual(
                release.SIARELEASE.runtime_rung(runtime),
                (b"sia-runtime-v8\0", release.MODERN_V8_RUNTIME_NAMES))
            self.assertEqual(
                release.SIARELEASE.runtime_tree_digest(runtime),
                EXPECTED_V8_TREE_DIGEST)
            paths = self.fence_paths(root, runtime)
            self.publish_fence(paths, EXPECTED_V8_TREE_DIGEST)
            accepted = self.fence_result(fence, paths)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)


if __name__ == "__main__":
    unittest.main()
