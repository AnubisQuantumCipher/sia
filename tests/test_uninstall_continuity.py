#!/usr/bin/env python3
"""Focused continuity-unit and current-runtime uninstall regressions."""

import json
import os
import subprocess
import tempfile
import unittest

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore

try:
    from test_release import (  # type: ignore
        REPO,
        SIARELEASE,
        _fake_command,
        _managed_cli_runtime,
        _managed_file_receipt,
        _owned_metadata_shell,
        _read,
        _read_path,
        _runtime_digest,
        _runtime_tree_digest_shell,
        _uninstaller_fenced_runtime_shell,
        _write,
    )
except ModuleNotFoundError:
    from tests.test_release import (  # type: ignore
        REPO,
        SIARELEASE,
        _fake_command,
        _managed_cli_runtime,
        _managed_file_receipt,
        _owned_metadata_shell,
        _read,
        _read_path,
        _runtime_digest,
        _runtime_tree_digest_shell,
        _uninstaller_fenced_runtime_shell,
        _write,
    )


CONTINUITY_UNITS = (
    ("sia-backup.timer", "backup-timer"),
    ("sia-backup-check.timer", "backup-check-timer"),
    ("sia-backup.service", "backup-unit"),
    ("sia-backup-check.service", "backup-check-unit"),
)
BACKUP_TIMER, _BACKUP_CHECK_TIMER, BACKUP_SERVICE, _BACKUP_CHECK_SERVICE = \
    CONTINUITY_UNITS

MODERN_V4_NAMES = SIARELEASE.MODERN_V4_RUNTIME_NAMES
MODERN_V5_NAMES = SIARELEASE.MODERN_V5_RUNTIME_NAMES
MODERN_V6_NAMES = SIARELEASE.MODERN_V6_RUNTIME_NAMES
MODERN_V7_NAMES = SIARELEASE.MODERN_V7_RUNTIME_NAMES
MODERN_V8_NAMES = SIARELEASE.MODERN_V8_RUNTIME_NAMES
MODERN_V9_NAMES = SIARELEASE.MODERN_V9_RUNTIME_NAMES

# Members each rung added over its predecessor.  A rung is only pinned when
# every one of them is load-bearing, including each marker whose presence
# selects newer ground; shedding a marker must never leave an older receipt
# authorized for the mutated tree.
V4_NEW_MEMBERS = (
    "siacapsule.py", "siabackup.py", "siarestoreadmit.py",
    "sia-continuity-worker",
)
V5_NEW_MEMBERS = V4_NEW_MEMBERS + ("siagraph.py",)
V6_NEW_MEMBERS = V5_NEW_MEMBERS + ("siathought.py",)
V7_NEW_MEMBERS = V6_NEW_MEMBERS + (
    "siaactivation.py", "siacognitivebaseline.py",
    "siacognitivecommand.py", "siacognitivehistory.py",
    "siacognitiveselect.py", "siacontrollerliveinput.py",
    "siacontrollerstatus.py", "siacoretrieval.py",
    "siacortexrepair.py", "siaencoding.py", "siaeventintake.py",
    "siaeventplan.py", "siagist.py", "siajournalcapture.py",
    "sialivegist.py", "sialiveloop.py", "sialivepublication.py",
    "siasourcebatch.py", "siasourcepublication.py", "siavector.py",
    "siavectoradmit.py", "siavectormodel.py", "siavectorprepare.py",
    "siavectorrun.py", "siaworkspace.py",
)
V8_NEW_MEMBERS = V7_NEW_MEMBERS + (
    "siasourceack.py", "siasourceeffects.py", "siasourceengine.py",
    "siasourcegit.py",
)
V9_NEW_MEMBERS = V8_NEW_MEMBERS + (
    "siacontrollerepoch.py", "siacontrollersourcerunner.py",
)


SYSTEMCTL_FIXTURE = r'''
echo "systemctl $*" >> "$TRACE"
emit_absent() {
  echo "LoadState=not-found"; echo "ActiveState=inactive"
  echo "FragmentPath="; echo "UnitFileState="
  echo "DropInPaths="; echo "MainPID=0"
  echo "RefuseManualStart=no"; echo "Job="
}
if [ "$1 $2" = "--user show" ]; then
  name=$3
  path=$HOME/.config/systemd/user/$name
  if [ "$name" = sia-brainstem.service ] || [ ! -f "$path" ]; then
    emit_absent
    exit 0
  fi
  marker=$HOME/.${name}.quiesced
  job=
  pending_job=
  if [ "${PENDING_JOB_UNIT:-}" = "$name" ] \
      || [ "${STICKY_JOB_UNIT:-}" = "$name" ]; then
    pending_job=yes
    if [ "${STICKY_JOB_UNIT:-}" = "$name" ] || [ ! -f "$marker" ]; then
      job=/org/freedesktop/systemd1/job/fixture
    fi
  fi
  echo "LoadState=loaded"
  echo "FragmentPath=$path"
  echo "DropInPaths="; echo "RefuseManualStart=no"
  case "$name" in
    *.timer)
      if [ -f "$marker" ]; then
        echo "ActiveState=inactive"; echo "UnitFileState=disabled"
      elif [ -n "$pending_job" ]; then
        echo "ActiveState=inactive"; echo "UnitFileState=disabled"
      else
        echo "ActiveState=active"; echo "UnitFileState=enabled"
      fi
      echo "MainPID=0"
      ;;
    *.service)
      if [ -f "$marker" ]; then
        echo "ActiveState=inactive"; echo "MainPID=0"
      elif [ -n "$pending_job" ]; then
        echo "ActiveState=inactive"; echo "MainPID=0"
      elif [ "${TRANSITION_UNIT:-}" = "$name" ]; then
        echo "ActiveState=activating"; echo "MainPID=321"
        job=/org/freedesktop/systemd1/job/fixture
      else
        echo "ActiveState=active"; echo "MainPID=321"
      fi
      echo "UnitFileState=static"
      ;;
    *) exit 1 ;;
  esac
  echo "Job=$job"
  exit 0
fi
if [ "$1 $2 $3" = "--user disable --now" ]; then
  name=$4
  : > "$HOME/.${name}.quiesced"
  if [ -n "${RACE_UNIT:-}" ] && [ "$name" = "$RACE_UNIT" ]; then
    printf '\nlocally replaced during disable\n' >> \
      "$HOME/.config/systemd/user/$name"
  fi
  exit 0
fi
if [ "$1 $2" = "--user stop" ]; then
  : > "$HOME/.$3.quiesced"
  exit 0
fi
exit 0
'''


class ContinuityUninstall(unittest.TestCase):
    def _environment(
            self, root, *, pending_job_unit="", race_unit="",
            sticky_job_unit="", transition_unit=""):
        home = os.path.join(root, "home")
        fake_bin = os.path.join(root, "bin")
        runtime_dir = os.path.join(root, "runtime")
        trace = os.path.join(root, "trace")
        os.makedirs(home)
        os.makedirs(fake_bin)
        os.makedirs(runtime_dir, mode=0o700)
        os.chmod(runtime_dir, 0o700)
        _fake_command(fake_bin, "systemctl", SYSTEMCTL_FIXTURE)
        for client in ("claude", "codex"):
            _fake_command(
                fake_bin, client,
                'echo "No MCP server named sia" >&2\nexit 1\n')
        _fake_command(fake_bin, "grok", 'echo "[]"\n')
        environment = os.environ.copy()
        environment.update({
            "HOME": home,
            "PATH": fake_bin + os.pathsep + environment["PATH"],
            "PENDING_JOB_UNIT": pending_job_unit,
            "TRACE": trace,
            "XDG_RUNTIME_DIR": runtime_dir,
            "RACE_UNIT": race_unit,
            "STICKY_JOB_UNIT": sticky_job_unit,
            "TRANSITION_UNIT": transition_unit,
        })
        return home, trace, environment

    def _install_unit(self, home, name, kind):
        path = os.path.join(home, ".config/systemd/user", name)
        receipt = os.path.join(
            home, ".local/state/sia/managed-install", name)
        _write(path, f"exact managed {name}\n", 0o644)
        _write(receipt, _managed_file_receipt(path, kind), 0o600)
        return path, receipt

    def _run(self, environment, *, purge=False):
        command = ["bash", os.path.join(REPO, "uninstall.sh")]
        if purge:
            command.append("--purge")
        return subprocess.run(
            command, cwd=REPO, env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    def _interrupt_pair_after_unit_archive(
            self, environment, home, name, kind, path, receipt):
        uninstaller = _read("uninstall.sh")
        cas_body = uninstaller.split("owned_file_cas() {", 1)[1].split(
            "\n}\n\n# Descriptor-rooted", 1)[0]
        cas_function = "owned_file_cas() {" + cas_body + "\n}\n"
        intent_body = uninstaller.split(
            "continuity_archive_intent() {", 1)[1].split(
                "\n}\n\ncontinuity_archive_intent_fields", 1)[0]
        intent_function = (
            "continuity_archive_intent() {" + intent_body + "\n}\n")
        managed = os.path.dirname(receipt)
        intent = os.path.join(managed, f".{name}.archive-intent.json")
        unit_archive = os.path.join(
            os.path.dirname(path), f".{name}.removed.interrupted")
        receipt_archive = os.path.join(
            managed, f".{name}.receipt.removed.interrupted")
        script = _owned_metadata_shell(uninstaller) + cas_function \
            + intent_function + r'''
set -u
unit_expected="$(owned_metadata generation "$TEST_UNIT")"
receipt_expected="$(owned_metadata generation "$TEST_RECEIPT")"
continuity_archive_intent create "$TEST_INTENT" \
  "$TEST_NAME" "$TEST_KIND" "$TEST_UNIT" "$TEST_RECEIPT" \
  "$TEST_UNIT_ARCHIVE" "$TEST_RECEIPT_ARCHIVE" \
  "$unit_expected" "$receipt_expected"
owned_file_cas archive "$TEST_UNIT_ARCHIVE" "$TEST_UNIT" \
  "$unit_expected" >/dev/null
'''
        interrupted_environment = environment.copy()
        interrupted_environment.update({
            "TEST_INTENT": intent,
            "TEST_KIND": kind,
            "TEST_NAME": name,
            "TEST_RECEIPT": receipt,
            "TEST_RECEIPT_ARCHIVE": receipt_archive,
            "TEST_UNIT": path,
            "TEST_UNIT_ARCHIVE": unit_archive,
        })
        _write(os.path.join(home, f".{name}.quiesced"), "", 0o600)
        result = subprocess.run(
            ["bash", "-c", script], cwd=REPO,
            env=interrupted_environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(os.path.lexists(path))
        self.assertTrue(os.path.isfile(receipt))
        self.assertTrue(os.path.isfile(intent))
        self.assertTrue(os.path.isfile(unit_archive))
        self.assertFalse(os.path.lexists(receipt_archive))
        return intent, unit_archive, receipt_archive

    def test_exact_units_are_quiesced_and_cas_archived_with_receipts(self):
        with tempfile.TemporaryDirectory() as root:
            home, trace, environment = self._environment(
                root, transition_unit="sia-backup.service")
            originals = {}
            for name, kind in CONTINUITY_UNITS:
                path, receipt = self._install_unit(home, name, kind)
                originals[name] = (_read_path(path), _read_path(receipt))

            result = self._run(environment)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = _read_path(trace)
            for name, _kind in CONTINUITY_UNITS:
                path = os.path.join(home, ".config/systemd/user", name)
                receipt = os.path.join(
                    home, ".local/state/sia/managed-install", name)
                self.assertFalse(os.path.lexists(path), name)
                self.assertFalse(os.path.lexists(receipt), name)
                unit_archives = [
                    entry for entry in os.listdir(os.path.dirname(path))
                    if entry.startswith(f".{name}.removed.")]
                receipt_archives = [
                    entry for entry in os.listdir(os.path.dirname(receipt))
                    if entry.startswith(f".{name}.receipt.removed.")]
                self.assertEqual(len(unit_archives), 1, name)
                self.assertEqual(len(receipt_archives), 1, name)
                self.assertEqual(
                    _read_path(os.path.join(
                        os.path.dirname(path), unit_archives[0])),
                    originals[name][0])
                self.assertEqual(
                    _read_path(os.path.join(
                        os.path.dirname(receipt), receipt_archives[0])),
                    originals[name][1])
            for name, _kind in CONTINUITY_UNITS:
                if name.endswith(".timer"):
                    self.assertIn(
                        f"systemctl --user disable --now {name}", calls)
                else:
                    self.assertIn(f"systemctl --user stop {name}", calls)
                    self.assertNotIn(
                        f"systemctl --user disable --now {name}", calls)
            self.assertIn("systemctl --user daemon-reload", calls)

    def test_pending_job_alone_triggers_quiescence_before_archival(self):
        cases = (
            (BACKUP_TIMER, "systemctl --user disable --now"),
            (BACKUP_SERVICE, "systemctl --user stop"),
        )
        for (name, kind), command in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as root:
                home, trace, environment = self._environment(
                    root, pending_job_unit=name)
                path, receipt = self._install_unit(home, name, kind)

                result = self._run(environment)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(os.path.lexists(path))
                self.assertFalse(os.path.lexists(receipt))
                self.assertIn(f"{command} {name}", _read_path(trace))

    def test_persistent_pending_job_blocks_archive_after_stop(self):
        with tempfile.TemporaryDirectory() as root:
            name, kind = BACKUP_SERVICE
            home, trace, environment = self._environment(
                root, sticky_job_unit=name)
            path, receipt = self._install_unit(home, name, kind)
            original_unit = _read_path(path)
            original_receipt = _read_path(receipt)

            result = self._run(environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(_read_path(path), original_unit)
            self.assertEqual(_read_path(receipt), original_receipt)
            self.assertIn(
                f"systemctl --user stop {name}", _read_path(trace))
            self.assertFalse(any(
                entry.startswith(f".{name}.removed.")
                for entry in os.listdir(os.path.dirname(path))))
            self.assertIn("quiesce exact SIA continuity", result.stderr)

    def test_locally_modified_unit_is_preserved_without_systemctl_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            home, trace, environment = self._environment(root)
            cli, runtime = _managed_cli_runtime(home)
            name, kind = CONTINUITY_UNITS[0]
            path, receipt = self._install_unit(home, name, kind)
            original_receipt = _read_path(receipt)
            _write(path, "operator-owned timer replacement\n", 0o644)

            result = self._run(environment, purge=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(_read_path(path), "operator-owned timer replacement\n")
            self.assertEqual(_read_path(receipt), original_receipt)
            calls = _read_path(trace)
            self.assertNotIn(f"disable --now {name}", calls)
            self.assertTrue(os.path.isfile(cli))
            self.assertTrue(os.path.isdir(runtime))
            self.assertIn("preserve unowned or modified", result.stderr)
            self.assertIn("purge blocked", result.stderr)

    def test_disable_race_preserves_changed_unit_receipt_and_runtime(self):
        with tempfile.TemporaryDirectory() as root:
            name, kind = CONTINUITY_UNITS[0]
            home, trace, environment = self._environment(
                root, race_unit=name)
            cli, runtime = _managed_cli_runtime(home)
            path, receipt = self._install_unit(home, name, kind)
            original_receipt = _read_path(receipt)

            result = self._run(environment, purge=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("locally replaced during disable", _read_path(path))
            self.assertEqual(_read_path(receipt), original_receipt)
            self.assertFalse(any(
                entry.startswith(f".{name}.removed.")
                for entry in os.listdir(os.path.dirname(path))))
            self.assertIn(f"disable --now {name}", _read_path(trace))
            self.assertTrue(os.path.isfile(cli))
            self.assertTrue(os.path.isdir(runtime))
            self.assertIn("quiesce exact SIA continuity", result.stderr)
            self.assertIn("purge blocked", result.stderr)

    def test_interrupted_unit_archive_resumes_receipt_pair_on_retry(self):
        with tempfile.TemporaryDirectory() as root:
            home, trace, environment = self._environment(root)
            name, kind = CONTINUITY_UNITS[0]
            path, receipt = self._install_unit(home, name, kind)
            original_unit = _read_path(path)
            original_receipt = _read_path(receipt)
            intent, unit_archive, receipt_archive = \
                self._interrupt_pair_after_unit_archive(
                    environment, home, name, kind, path, receipt)

            result = self._run(environment)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(os.path.lexists(path))
            self.assertFalse(os.path.lexists(receipt))
            self.assertFalse(os.path.lexists(intent))
            self.assertEqual(_read_path(unit_archive), original_unit)
            self.assertEqual(_read_path(receipt_archive), original_receipt)
            self.assertIn("systemctl --user daemon-reload", _read_path(trace))

    def test_interrupted_pair_with_changed_receipt_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            home, _trace, environment = self._environment(root)
            cli, runtime = _managed_cli_runtime(home)
            name, kind = CONTINUITY_UNITS[0]
            path, receipt = self._install_unit(home, name, kind)
            intent, unit_archive, receipt_archive = \
                self._interrupt_pair_after_unit_archive(
                    environment, home, name, kind, path, receipt)
            with open(receipt, "a", encoding="utf-8") as stream:
                stream.write("locally changed after interruption\n")

            result = self._run(environment, purge=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(os.path.lexists(path))
            self.assertTrue(os.path.isfile(receipt))
            self.assertTrue(os.path.isfile(intent))
            self.assertTrue(os.path.isfile(unit_archive))
            self.assertFalse(os.path.lexists(receipt_archive))
            self.assertTrue(os.path.isfile(cli))
            self.assertTrue(os.path.isdir(runtime))
            self.assertIn("ambiguous archive recovery retained", result.stderr)
            self.assertIn("purge blocked", result.stderr)

    def _fence_script(self):
        uninstaller = _read("uninstall.sh")
        digest_function = _runtime_tree_digest_shell(uninstaller)
        fence_function = _uninstaller_fenced_runtime_shell(uninstaller)
        # "set -eu", not "set -u": under plain -u a failed digest comparison
        # is discarded and the script's status comes from the fence alone, so
        # the rung/salt half of the ladder was asserted by a line that could
        # not fail the test.  Both functions are a single python3 heredoc, so
        # -e adds no spurious early exit.
        return digest_function + fence_function + r'''
set -eu
LAUNCH_FENCE_JOURNAL="$TEST_JOURNAL"
LIFECYCLE_TOMBSTONE="$TEST_TOMBSTONE"
RUNTIME_RECEIPT="$TEST_RECEIPT"
RUNTIME_BIN_DIR="$TEST_RUNTIME"
[ "$(runtime_tree_digest "$RUNTIME_BIN_DIR")" = "$TEST_DIGEST" ]
fenced_runtime_authorized
'''

    def _assert_rung_pins_every_member(
            self, script, names, added, promotion=None):
        with tempfile.TemporaryDirectory() as root:
            runtime = os.path.join(root, "runtime")
            managed = os.path.join(root, "managed")
            receipt = os.path.join(managed, "runtime")
            journal = os.path.join(managed, "launch-fence.json")
            tombstone = os.path.join(root, "sia.lifecycle-removed")
            for name in names:
                _write(os.path.join(runtime, name), name + "\n", 0o644)
            digest = _runtime_digest(runtime)
            _write(
                receipt,
                "managed-by=khephri.sia\nkind=runtime\n"
                f"path={runtime}\nsha256={digest}\n",
                0o600)
            _write(
                journal,
                json.dumps({
                    "schema": "sia-launch-fence-v1",
                    "runtime_before_digest": digest,
                    "runtime_digest": digest,
                    "cli_digest": "",
                    "entries": [],
                }, sort_keys=True, separators=(",", ":")) + "\n",
                0o600)
            _write(tombstone, "removed-by=khephri.sia\n", 0o600)
            environment = os.environ.copy()
            environment.update({
                "TEST_JOURNAL": journal,
                "TEST_TOMBSTONE": tombstone,
                "TEST_RECEIPT": receipt,
                "TEST_RUNTIME": runtime,
                "TEST_DIGEST": digest,
            })

            def authorize():
                return subprocess.run(
                    ["bash", "-c", script], env=environment, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    check=False)

            result = authorize()
            self.assertEqual(result.returncode, 0, result.stderr)
            for name in added:
                with self.subTest(missing=name):
                    path = os.path.join(runtime, name)
                    os.unlink(path)
                    self.assertNotEqual(authorize().returncode, 0)
                    _write(path, name + "\n", 0o644)
            self.assertEqual(authorize().returncode, 0)
            if promotion is not None:
                # Dropping a later rung's member into an earlier rung's tree
                # re-selects the ladder: the receipt was signed under the
                # older salt and member list and must stop authorizing.
                _write(
                    os.path.join(runtime, promotion),
                    promotion + "\n", 0o644)
                self.assertNotEqual(authorize().returncode, 0, promotion)

    def test_current_runtime_digest_and_fence_require_every_new_member(self):
        script = self._fence_script()
        for rung, names, added, promotion in (
                ("v4", MODERN_V4_NAMES, V4_NEW_MEMBERS, "siagraph.py"),
                ("v5", MODERN_V5_NAMES, V5_NEW_MEMBERS, "siathought.py"),
                ("v6", MODERN_V6_NAMES, V6_NEW_MEMBERS, "sialiveloop.py"),
                ("v7", MODERN_V7_NAMES, V7_NEW_MEMBERS,
                 "siasourceack.py"),
                ("v8", MODERN_V8_NAMES, V8_NEW_MEMBERS,
                 "siacontrollerepoch.py"),
                ("v9", MODERN_V9_NAMES, V9_NEW_MEMBERS, None)):
            with self.subTest(rung=rung):
                self._assert_rung_pins_every_member(
                    script, names, added, promotion)

    def test_release_authority_fd_survives_plugin_archive_and_closes(self):
        uninstaller = _read("uninstall.sh")
        hold = "hold_release_authority() {" + uninstaller.split(
            "hold_release_authority() {", 1)[1].split(
                "\n}\n\nclose_release_authority", 1)[0] + "\n}\n"
        close = "close_release_authority() {" + uninstaller.split(
            "close_release_authority() {", 1)[1].split(
                "\n}\n\nhold_release_authority", 1)[0] + "\n}\n"
        with tempfile.TemporaryDirectory() as root:
            plugin = os.path.join(root, "plugin")
            archive = os.path.join(root, "plugin-archive")
            source = os.path.join(plugin, "bin", "siarelease.py")
            runtime = os.path.join(root, "runtime")
            _write(source, _read("bin/siarelease.py"), 0o600)
            for name in MODERN_V6_NAMES:
                _write(os.path.join(runtime, name), name + "\n", 0o644)
            digest = _runtime_digest(runtime)
            script = hold + close + r'''
set -eu
SIA_RELEASE_AUTHORITY=""
SIA_RELEASE_AUTHORITY_FD=""
hold_release_authority "$TEST_SOURCE"
held="$SIA_RELEASE_AUTHORITY"
mv -- "$TEST_PLUGIN" "$TEST_ARCHIVE"
[ ! -e "$TEST_SOURCE" ]
[ "$(python3 "$SIA_RELEASE_AUTHORITY" runtime-tree-digest \
  "$TEST_RUNTIME")" = "$TEST_DIGEST" ]
close_release_authority
[ -z "$SIA_RELEASE_AUTHORITY_FD" ]
[ ! -e "$held" ]
'''
            environment = os.environ.copy()
            environment.update({
                "TEST_ARCHIVE": archive,
                "TEST_DIGEST": digest,
                "TEST_PLUGIN": plugin,
                "TEST_RUNTIME": runtime,
                "TEST_SOURCE": source,
            })
            result = subprocess.run(
                ["bash", "-c", script], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_purge_removes_continuity_secrets_but_normal_uninstall_retains_them(self):
        for purge in (False, True):
            with self.subTest(purge=purge), tempfile.TemporaryDirectory() as root:
                home, _trace, environment = self._environment(root)
                continuity = os.path.join(
                    home, ".local/state/sia-continuity")
                key = os.path.join(continuity, "repository.key")
                _write(key, "fixture repository secret\n", 0o600)

                result = self._run(environment, purge=purge)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(os.path.lexists(key), not purge)
                self.assertEqual(os.path.lexists(continuity), not purge)


if __name__ == "__main__":
    unittest.main(verbosity=2)
