"""Persistent teardown remains callable after the plugin checkout is gone."""

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import textwrap
import unittest

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_release as release
from tests import test_runtime_v12_recall_closure as v12


V13_ADDITIONS = ("sialifetime.py", "uninstall.sh")
EXPECTED_V13_RUNTIME_NAMES = v12.EXPECTED_V12_RUNTIME_NAMES + V13_ADDITIONS
V13_SALT = b"sia-runtime-v13\0"


class RuntimeV13PersistentUninstall(unittest.TestCase):
    shell_digest = staticmethod(v12.RuntimeV12RecallClosure.shell_digest)
    fence_paths = staticmethod(v12.RuntimeV12RecallClosure.fence_paths)
    publish_fence = staticmethod(v12.RuntimeV12RecallClosure.publish_fence)
    fence_result = staticmethod(v12.RuntimeV12RecallClosure.fence_result)

    def test_current_runtime_and_installer_ship_the_teardown_authority(self):
        # v13 is no longer the newest rung, so it is located by salt and
        # its relationship to v12 is asserted rather than an absolute
        # position. The exactness this test owns is v13's own roster and
        # additions, and that the installer still stages them; that the
        # staged tree equals the CURRENT rung exactly is owned by
        # test_latest_receipt_rung_is_exactly_the_staged_tree and is not
        # relaxed here.
        authority = release.SIARELEASE
        authority.validate_runtime_ladder()
        v13_index = next(index for index, rung in enumerate(authority.RUNTIME_LADDER)
                         if rung[0] == V13_SALT)
        self.assertEqual(authority.RUNTIME_LADDER[v13_index], (
            V13_SALT, EXPECTED_V13_RUNTIME_NAMES, V13_ADDITIONS))
        self.assertEqual(authority.RUNTIME_LADDER[v13_index + 1], (
            v12.V12_SALT, v12.EXPECTED_V12_RUNTIME_NAMES,
            v12.V12_ADDITIONS))
        installer = release._read("install.sh")
        release_files = tuple(shlex.split(installer.split(
            "SIA_RELEASE_FILES=(", 1)[1].split("\n)", 1)[0]))
        staged = release._staged_runtime_members(installer)
        self.assertEqual(len(staged), len(set(staged)))
        self.assertLessEqual(set(EXPECTED_V13_RUNTIME_NAMES), set(staged))
        self.assertEqual(release_files.count("bin/sialifetime.py"), 1)
        self.assertEqual(release_files.count("uninstall.sh"), 1)

    def test_each_v13_selector_refuses_an_incomplete_peer_set(self):
        for marker in V13_ADDITIONS:
            with self.subTest(marker=marker), \
                    tempfile.TemporaryDirectory() as runtime:
                release._plant_runtime_tree(
                    runtime, v12.EXPECTED_V12_RUNTIME_NAMES)
                release._write(
                    os.path.join(runtime, marker), marker + "\n", 0o500)
                self.assertEqual(release.SIARELEASE.runtime_rung(runtime),
                                 (V13_SALT, EXPECTED_V13_RUNTIME_NAMES))
                with self.assertRaises(FileNotFoundError):
                    release.SIARELEASE.runtime_tree_digest(runtime)

    def test_install_uninstall_and_fence_require_both_v13_members(self):
        functions = tuple(
            release._runtime_tree_digest_shell(
                release._read(site + ".sh"))
            for site in ("install", "uninstall"))
        fence = release._uninstaller_fenced_runtime_shell(
            release._read("uninstall.sh"))
        current_digest = v12.v10.reference_fixture_digest(
            V13_SALT, EXPECTED_V13_RUNTIME_NAMES)
        prior_digest = v12.v10.reference_fixture_digest(
            v12.V12_SALT, v12.EXPECTED_V12_RUNTIME_NAMES)
        with tempfile.TemporaryDirectory() as root:
            runtime = os.path.join(root, "runtime")
            release._plant_runtime_tree(runtime, EXPECTED_V13_RUNTIME_NAMES)
            paths = self.fence_paths(root, runtime)
            for function in functions:
                result = self.shell_digest(function, runtime)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), current_digest)
            self.publish_fence(paths, current_digest)
            self.assertEqual(
                self.fence_result(fence, paths).returncode, 0)
            self.publish_fence(paths, prior_digest)
            self.assertNotEqual(
                self.fence_result(fence, paths).returncode, 0)
            for member in V13_ADDITIONS:
                with self.subTest(missing=member):
                    path = os.path.join(runtime, member)
                    os.unlink(path)
                    self.assertEqual(
                        release.SIARELEASE.runtime_rung(runtime),
                        (V13_SALT, EXPECTED_V13_RUNTIME_NAMES))
                    with self.assertRaises(FileNotFoundError):
                        release.SIARELEASE.runtime_tree_digest(runtime)
                    for function in functions:
                        self.assertNotEqual(
                            self.shell_digest(function, runtime).returncode,
                            0)
                    for receipt in (current_digest, prior_digest):
                        self.publish_fence(paths, receipt)
                        self.assertNotEqual(
                            self.fence_result(fence, paths).returncode, 0)
                    release._write(path, member + "\n", 0o500)

    def test_stable_cli_routes_teardown_before_shared_lifecycle_lease(self):
        with tempfile.TemporaryDirectory(prefix="sia-persistent-uninstall-") as home:
            runtime = os.path.join(home, ".local", "share", "sia", "bin")
            launcher = os.path.join(home, ".local", "bin", "sia")
            marker = os.path.join(home, "invoked.json")
            poison = os.path.join(home, "poison")
            os.makedirs(poison)
            release._write(os.path.join(poison, "json.py"),
                           "raise RuntimeError('ambient import executed')\n")
            release._generate_stable_launcher(launcher)
            release._write(os.path.join(runtime, "uninstall.sh"),
                           "#!/usr/bin/env bash\nexit 99\n", 0o500)
            release._write(
                os.path.join(runtime, "sialifetime.py"),
                textwrap.dedent("""
                    import fcntl
                    import json
                    import os
                    import sys

                    home = os.environ["HOME"]
                    lock = os.path.join(home, ".local", "state",
                                        "sia.lifecycle.lock")
                    os.makedirs(os.path.dirname(lock), exist_ok=True)
                    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with open(os.environ["SIA_TEST_UNINSTALL_MARKER"], "w",
                              encoding="utf-8") as stream:
                        json.dump({"arguments": sys.argv[1:],
                                   "sia_keys": sorted(
                                       key for key in os.environ
                                       if key.startswith("SIA_") and key !=
                                       "SIA_TEST_UNINSTALL_MARKER"),
                                   "startup": [key for key in
                                               ("BASH_ENV", "ENV")
                                               if key in os.environ]}, stream)
                    print(open(os.environ["SIA_TEST_UNINSTALL_MARKER"],
                               encoding="utf-8").read())
                """).lstrip(), 0o500)
            environment = dict(
                os.environ, HOME=home, SIA_TEST_UNINSTALL_MARKER=marker,
                SIA_INHERITED_LIFECYCLE_FD="91", SIA_LAUNCHER_ABI="ambient",
                SIA_RESTORE_ADMIN_FD="92", SIA_SETUP_HANDOFF_ROOT_FD="93",
                SIA_LIFETIME_CONTROL_FD="94", BASH_ENV="/unsafe/bash",
                ENV="/unsafe/sh", PYTHONPATH=poison)

            result = subprocess.run(
                [launcher, "uninstall"], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            invocation = json.loads(result.stdout)
            arguments = invocation["arguments"]
            self.assertEqual(arguments[0:2], [
                "supervise-installed", "--caller"])
            self.assertTrue(arguments[2].isascii() and arguments[2].isdigit())
            self.assertEqual(arguments[3:], [
                os.path.join(runtime, "uninstall.sh")])
            self.assertEqual(invocation["sia_keys"], [])
            self.assertEqual(invocation["startup"], [])

            os.unlink(marker)
            purge = subprocess.run(
                [launcher, "uninstall", "--purge"], env=environment,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False)
            self.assertEqual(purge.returncode, 0, purge.stderr)
            purge_invocation = json.loads(purge.stdout)
            purge_arguments = purge_invocation["arguments"]
            self.assertEqual(purge_arguments[3:], [
                os.path.join(runtime, "uninstall.sh"), "--purge"])
            self.assertEqual(purge_invocation["sia_keys"], [])
            self.assertEqual(purge_invocation["startup"], [])

            os.unlink(marker)
            refused = subprocess.run(
                [launcher, "uninstall", "--unknown"], env=environment,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False)
            self.assertEqual(refused.returncode, 2)
            self.assertIn("usage: sia uninstall [--purge]", refused.stderr)
            self.assertFalse(os.path.exists(marker))

    def test_installed_lifetime_mode_seals_a_flat_runtime_source(self):
        with tempfile.TemporaryDirectory(
                prefix="sia-installed-lifetime-") as runtime:
            lifetime = os.path.join(runtime, "sialifetime.py")
            entry = os.path.join(runtime, "uninstall.sh")
            shutil.copy2(os.path.join(release.REPO, "bin", "sialifetime.py"),
                         lifetime)
            bootstrap = release._read("uninstall.sh").split(
                "# BEGIN SIA RELEASE LIFETIME\n", 1)[1].split(
                    "# END SIA RELEASE LIFETIME\n", 1)[0]
            release._write(
                entry,
                "#!/usr/bin/env bash\n" + bootstrap
                + "printf 'flat-installed-uninstall:%s\\n' \"${1:-none}\"\n",
                0o500)
            command = [
                "python3", "-I", lifetime, "supervise-installed",
                "--caller", str(os.getpid()), entry, "sentinel",
            ]
            result = subprocess.run(
                command, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout,
                             "flat-installed-uninstall:sentinel\n")

            ordinary = subprocess.run(
                ["python3", "-I", lifetime, "supervise", "--caller",
                 str(os.getpid()), entry, "sentinel"], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(ordinary.returncode, 0)
            self.assertIn("No such file or directory", ordinary.stderr)

            install_entry = os.path.join(runtime, "install.sh")
            release._write(install_entry, "#!/bin/sh\nexit 0\n", 0o500)
            wrong_entry = subprocess.run(
                ["python3", "-I", lifetime, "supervise-installed",
                 "--caller", str(os.getpid()), install_entry], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(wrong_entry.returncode, 0)
            self.assertIn("permits only uninstall", wrong_entry.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
