#!/usr/bin/env python3
"""Purge coverage for fixed publication slots outside SIA authority roots."""

import fcntl
import os
import subprocess
import tempfile
import unittest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _uninstaller():
    with open(os.path.join(REPO, "uninstall.sh"), encoding="utf-8") as stream:
        return stream.read()


def _purge_function(script):
    body = script.split("purge_fixed_publication_stages() {", 1)[1] \
        .split("\nsafe_remove_tree() {", 1)[0]
    return "purge_fixed_publication_stages() {" + body


def _stage(path, names=("publish.lock", "payload")):
    os.makedirs(path, mode=0o700)
    os.chmod(path, 0o700)
    for name in names:
        with open(os.path.join(path, name), "wb") as stream:
            stream.write(b"retained payload" if name == "payload" else b"")
        os.chmod(os.path.join(path, name), 0o600)


class FixedPublicationStagePurge(unittest.TestCase):
    def _paths(self, root):
        state = os.path.join(root, ".local", "state", ".sia.sia-stage")
        share = os.path.join(root, ".local", "share", ".sia.sia-stage")
        os.makedirs(os.path.dirname(state), mode=0o700)
        os.makedirs(os.path.dirname(share), mode=0o700)
        return state, share

    def _run(self, state, share):
        function = _purge_function(_uninstaller())
        command = (
            "set -uo pipefail\n"
            f"STATE_PUBLICATION_STAGE={state!r}\n"
            f"SHARE_PUBLICATION_STAGE={share!r}\n"
            f"{function}\n"
            "purge_fixed_publication_stages "
            '"$STATE_PUBLICATION_STAGE" "$SHARE_PUBLICATION_STAGE"\n')
        return subprocess.run(
            ["bash", "-c", command], cwd=REPO, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    def test_exact_stages_and_payloads_are_removed(self):
        with tempfile.TemporaryDirectory() as root:
            state, share = self._paths(root)
            _stage(state)
            _stage(share)
            result = self._run(state, share)
            self.assertEqual(result.returncode, 0, result.stderr)
            for path in (state, share):
                self.assertFalse(os.path.lexists(path))
                self.assertFalse(os.path.lexists(path + ".purging"))

    def test_all_stages_preflight_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            state, share = self._paths(root)
            _stage(state)
            _stage(share)
            with open(os.path.join(state, "unexpected"), "wb"):
                pass
            result = self._run(state, share)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(os.path.isdir(state))
            self.assertTrue(os.path.isdir(share))
            self.assertTrue(os.path.isfile(os.path.join(share, "payload")))

    def test_only_exact_owned_private_single_link_entries_are_removed(self):
        mutations = ("linked-lock", "linked-payload", "unsafe-mode",
                     "payload-without-lock", "stage-symlink")
        for mutation in mutations:
            with self.subTest(mutation=mutation), \
                    tempfile.TemporaryDirectory() as root:
                state, share = self._paths(root)
                _stage(state)
                if mutation == "linked-lock":
                    os.link(os.path.join(state, "publish.lock"),
                            os.path.join(root, "lock-alias"))
                elif mutation == "linked-payload":
                    os.link(os.path.join(state, "payload"),
                            os.path.join(root, "payload-alias"))
                elif mutation == "unsafe-mode":
                    os.chmod(os.path.join(state, "payload"), 0o640)
                elif mutation == "payload-without-lock":
                    os.unlink(os.path.join(state, "publish.lock"))
                else:
                    for name in ("payload", "publish.lock"):
                        os.unlink(os.path.join(state, name))
                    os.rmdir(state)
                    os.symlink(root, state)
                result = self._run(state, share)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(os.path.lexists(state))

    def test_interrupted_purge_states_resume_without_payload_loss(self):
        for names in ((), ("publish.lock",),
                      ("publish.lock", "payload")):
            with self.subTest(names=names), \
                    tempfile.TemporaryDirectory() as root:
                state, share = self._paths(root)
                _stage(state + ".purging", names=names)
                result = self._run(state, share)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(os.path.lexists(state))
                self.assertFalse(os.path.lexists(state + ".purging"))

    def test_live_stage_lock_is_preserved_and_refused(self):
        with tempfile.TemporaryDirectory() as root:
            state, share = self._paths(root)
            _stage(state)
            descriptor = os.open(os.path.join(state, "publish.lock"),
                                 os.O_RDWR)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = self._run(state, share)
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(os.path.isfile(os.path.join(state, "payload")))

    def test_purge_gate_precedes_recursive_authority_removal(self):
        script = _uninstaller()
        call = script.index(
            "elif ! purge_fixed_publication_stages")
        state = script.index(
            'attempt "purge retained SIA state"', call)
        share = script.index(
            'attempt "purge retained SIA memory"', call)
        self.assertLess(call, state)
        self.assertLess(call, share)
        for path in ("$STATE_PUBLICATION_STAGE",
                     "$STATE_PUBLICATION_STAGE.purging",
                     "$SHARE_PUBLICATION_STAGE",
                     "$SHARE_PUBLICATION_STAGE.purging"):
            self.assertIn(path, script[state:])


if __name__ == "__main__":
    unittest.main()
