import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(relative):
    with open(os.path.join(REPO, relative), encoding="utf-8") as stream:
        return stream.read()


def _bounded_and_metadata(installer):
    bounded = "bounded_command_capture() {" + installer.split(
        "bounded_command_capture() {", 1)[1].split(
            "\nowned_metadata() {", 1)[0]
    body = installer.split("owned_metadata() {", 1)[1].split(
        "\n}\n\nwrite_lifecycle_tombstone", 1)[0]
    return bounded + "\nowned_metadata() {" + body + "\n}\n"


def _tree_frontdoor(installer):
    return ("owned_tree_cas() {" + installer.split(
        "owned_tree_cas() {", 1)[1].split(
            "\n}\n\nowned_tree_generation()", 1)[0] +
            '\n}\nowned_tree_generation() { '
            'owned_tree_cas generation "$1"; }\n')


def _bootstrap_functions(installer):
    return "durable_fixed_metadata_stage() {" + installer.split(
        "durable_fixed_metadata_stage() {", 1)[1].split(
            "\n}\n\nruntime_tree_digest()", 1)[0] + "\n}\n"


class InstallerCapabilityPreflight(unittest.TestCase):
    def test_python_kernel_crypto_and_managed_filesystem_probes(self):
        installer = _read("install.sh")
        ledger = _read("bin/sia-ledger")
        python_probe = "preflight_python_capabilities() {" + installer.split(
            "preflight_python_capabilities() {", 1)[1].split(
                "\n}\n\n# Exercise the Linux/filesystem", 1)[0] + "\n}\n"
        filesystem_probe = (
            "preflight_managed_filesystem_capabilities() {" +
            installer.split(
                "preflight_managed_filesystem_capabilities() {", 1)[1].split(
                    "\n}\n\n# External inspectors", 1)[0] + "\n}\n")

        self.assertNotIn("private_bytes_raw", ledger)
        self.assertNotIn("public_bytes_raw", ledger)
        self.assertIn("serialization.PrivateFormat.Raw", ledger)
        self.assertIn("serialization.PublicFormat.Raw", ledger)
        self.assertIn("serialization.NoEncryption()", ledger)

        normal = subprocess.run(
            ["bash", "-c", "set -euo pipefail\n" + python_probe +
             "\npreflight_python_capabilities"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False)
        self.assertEqual(normal.returncode, 0, normal.stderr)

        no_pidfd = python_probe.replace(
            'if not hasattr(os, "pidfd_open"):', "if True:", 1)
        refused = subprocess.run(
            ["bash", "-c", "set -euo pipefail\n" + no_pidfd +
             "\npreflight_python_capabilities"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("os.pidfd_open is required", refused.stderr)
        self.assertIn("os.pidfd_open(process.pid, 0)", python_probe)
        self.assertIn("watcher.select(2)", python_probe)

        with tempfile.TemporaryDirectory() as root:
            command = ("set -euo pipefail\n" + filesystem_probe +
                       "\npreflight_managed_filesystem_capabilities " +
                       shlex.quote(root) + " " + shlex.quote(root))
            working = subprocess.run(
                ["bash", "-c", command], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(working.returncode, 0, working.stderr)
            self.assertFalse(any(
                name.startswith(".sia-capability-")
                for name in os.listdir(root)))

            no_tmpfile = filesystem_probe.replace(
                'tmpfile = getattr(os, "O_TMPFILE", 0)', "tmpfile = 0", 1)
            unsupported = subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + no_tmpfile +
                 "\npreflight_managed_filesystem_capabilities " +
                 shlex.quote(root) + " " + shlex.quote(root)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False)
            self.assertNotEqual(unsupported.returncode, 0)
            self.assertIn("O_TMPFILE support is required", unsupported.stderr)
            self.assertFalse(any(
                name.startswith(".sia-capability-")
                for name in os.listdir(root)))

            no_rename = filesystem_probe.replace(
                "renameat2 = libc.renameat2",
                'raise AttributeError("fixture renameat2 unavailable")', 1)
            unsupported = subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + no_rename +
                 "\npreflight_managed_filesystem_capabilities " +
                 shlex.quote(root) + " " + shlex.quote(root)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False)
            self.assertNotEqual(unsupported.returncode, 0)
            self.assertIn("renameat2 and linkat are required", unsupported.stderr)


class GbrainBootstrapRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.installer = _read("install.sh")
        cls.functions = (_bounded_and_metadata(cls.installer) +
                         _tree_frontdoor(cls.installer) +
                         _bootstrap_functions(cls.installer))

    def _fake_gbrain(self, home):
        path = os.path.join(home, "fake-gbrain")
        script = r'''#!/usr/bin/env python3
import json
import os
import sys

home = os.environ["GBRAIN_HOME"]
store = os.path.join(home, ".gbrain")
if sys.argv[1:2] == ["init"]:
    database = os.path.join(store, "brain.pglite")
    os.makedirs(database, exist_ok=True)
    with open(os.path.join(database, "producer"), "w", encoding="utf-8") as stream:
        stream.write("gbrain bootstrap\n")
    if os.environ.get("FAKE_GBRAIN_FAIL_INIT") == "1":
        with open(os.path.join(database, "partial"), "w", encoding="utf-8") as stream:
            stream.write("interrupted\n")
        raise SystemExit(19)
    with open(os.path.join(store, "config.json"), "w", encoding="utf-8") as stream:
        json.dump({
            "engine": "pglite",
            "database_path": database,
            "fixture_extra": {"preserve": True},
        }, stream)
        stream.write("\n")
    os.chmod(os.path.join(store, "config.json"), 0o600)
    raise SystemExit(0)
if sys.argv[1:] == ["engine", "status", "--probe", "--json"]:
    config_path = os.path.join(store, "config.json")
    if not os.path.isfile(config_path):
        raise SystemExit(20)
    with open(config_path, encoding="utf-8") as stream:
        config = json.load(stream)
    database = config.get("database_path")
    if config.get("engine") != "pglite" \
            or not isinstance(database, str) \
            or not os.path.isfile(os.path.join(database, "producer")):
        raise SystemExit(20)
    if os.environ.get("FAKE_GBRAIN_MUTATE_PROBE") == "1":
        with open(os.path.join(database, "probe-mutation"), "a",
                  encoding="utf-8") as stream:
            stream.write("probe\n")
    print(json.dumps({
        "schema_version": 1,
        "effective_engine": "pglite",
        "config_file_engine": "pglite",
        "database_path": database,
        "thin_client": False,
        "probe": {"ok": True},
    }))
    raise SystemExit(0)
raise SystemExit(21)
'''
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(script)
        os.chmod(path, 0o755)
        return path

    def _run(self, home, *, functions=None, environment=None):
        share = os.path.join(home, "share")
        state = os.path.join(home, "state")
        managed = os.path.join(state, "managed-install")
        os.makedirs(share, exist_ok=True)
        os.makedirs(managed, exist_ok=True)
        fake = self._fake_gbrain(home)
        variables = textwrap.dedent(f'''
            SHARE={shlex.quote(share)}
            STATE={shlex.quote(state)}
            MANAGED_DIR={shlex.quote(managed)}
            GBRAIN_BIN={shlex.quote(fake)}
            GBRAIN_BOOTSTRAP_INTENT="$MANAGED_DIR/gbrain-bootstrap"
            GBRAIN_BOOTSTRAP_HOME="$SHARE/.gbrain-bootstrap-home"
            GBRAIN_BOOTSTRAP_STAGE="$SHARE/.gbrain-bootstrap-tree"
            GBRAIN_BOOTSTRAP_BACKUP="$SHARE/.gbrain-bootstrap-prior"
            SIA_GBRAIN_BOOTSTRAP_NEEDED=0
            preflight_gbrain_bootstrap
            if [ "$SIA_GBRAIN_BOOTSTRAP_NEEDED" -eq 1 ]; then
              complete_gbrain_bootstrap
            fi
        ''')
        active_environment = os.environ.copy()
        if environment:
            active_environment.update(environment)
        script_path = None
        try:
            with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", dir=home,
                    prefix=".gbrain-bootstrap-test-", suffix=".sh",
                    delete=False) as stream:
                script_path = stream.name
                stream.write("set -euo pipefail\n")
                stream.write(functions or self.functions)
                stream.write(variables)
            return subprocess.run(
                ["bash", "-c", 'source "$1"',
                 "gbrain-bootstrap-test", script_path],
                env=active_environment, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False, timeout=30)
        finally:
            if script_path is not None:
                os.unlink(script_path)

    def _bootstrap_paths(self, home):
        share = os.path.join(home, "share")
        target = os.path.join(share, ".gbrain")
        return {
            "share": share,
            "target": target,
            "config": os.path.join(target, "config.json"),
            "database": os.path.join(target, "brain.pglite"),
            "stale_database": os.path.join(
                share, ".gbrain-bootstrap-home", ".gbrain",
                "brain.pglite"),
            "bootstrap_home": os.path.join(
                share, ".gbrain-bootstrap-home"),
            "stage": os.path.join(
                target, ".config.json.sia-bootstrap-stage"),
            "retired": os.path.join(
                target, ".config.json.sia-bootstrap-stage.retired"),
            "intent": os.path.join(
                home, "state", "managed-install", "gbrain-bootstrap"),
        }

    def _load_config(self, path):
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)

    def _cas_artifacts(self, paths, prefix):
        return sorted(
            os.path.join(paths["target"], name)
            for name in os.listdir(paths["target"])
            if name.startswith(prefix))

    def _inject_after_bound_snapshot_link(self, body):
        needle = (
            '            try:\n'
            '                link_descriptor_noreplace('
            'snapshot_fd, target_name)\n'
            '                sync_parent()\n')
        self.assertIn(needle, self.functions)
        return self.functions.replace(needle, needle + body, 1)

    def _interrupt_after_probing_intent(self):
        needle = ('  set_gbrain_bootstrap_intent probing "$installed" '
                  '|| return 1')
        position = self.functions.rfind(needle)
        self.assertGreaterEqual(position, 0)
        end = position + len(needle)
        return self.functions[:end] + "\n  return 1" + self.functions[end:]

    def test_partial_external_init_is_retried_from_exact_intent(self):
        with tempfile.TemporaryDirectory() as home:
            failed = self._run(
                home, environment={"FAKE_GBRAIN_FAIL_INIT": "1"})
            self.assertNotEqual(failed.returncode, 0)
            target = os.path.join(home, "share", ".gbrain")
            intent = os.path.join(
                home, "state", "managed-install", "gbrain-bootstrap")
            self.assertFalse(os.path.lexists(target))
            self.assertTrue(os.path.isfile(intent))

            resumed = self._run(home)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertTrue(os.path.isdir(
                os.path.join(target, "brain.pglite")))
            paths = self._bootstrap_paths(home)
            config = self._load_config(paths["config"])
            self.assertEqual(config["database_path"], paths["database"])
            self.assertEqual(config["fixture_extra"], {"preserve": True})
            self.assertEqual(
                stat.S_IMODE(os.stat(paths["config"]).st_mode), 0o600)
            self.assertFalse(os.path.lexists(paths["stage"]))
            self.assertFalse(os.path.lexists(intent))
            self.assertFalse(any(
                name.startswith(".gbrain-bootstrap-")
                for name in os.listdir(os.path.join(home, "share"))))
            again = self._run(home)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(
                self._load_config(paths["config"]), config)

    def test_post_publish_crash_recovers_only_matching_tree(self):
        needle = ('  set_gbrain_bootstrap_intent probing "$installed" '
                  '|| return 1')
        self.assertIn(needle, self.functions)
        interrupted = self.functions.replace(
            needle, "  return 1\n" + needle, 1)
        with tempfile.TemporaryDirectory() as home:
            failed = self._run(home, functions=interrupted)
            self.assertNotEqual(failed.returncode, 0)
            paths = self._bootstrap_paths(home)
            self.assertTrue(os.path.isdir(paths["target"]))
            with open(paths["intent"], encoding="utf-8") as stream:
                self.assertIn("phase=publishing\n", stream.read())
            self.assertEqual(
                self._load_config(paths["config"])["database_path"],
                paths["stale_database"])
            resumed = self._run(home)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(
                self._load_config(paths["config"])["database_path"],
                paths["database"])

    def test_reported_probing_state_rebinds_after_bootstrap_home_is_gone(self):
        interrupted = self._interrupt_after_probing_intent()
        with tempfile.TemporaryDirectory() as home:
            failed = self._run(home, functions=interrupted)
            self.assertNotEqual(failed.returncode, 0)
            paths = self._bootstrap_paths(home)
            with open(paths["intent"], encoding="utf-8") as stream:
                self.assertIn("phase=probing\n", stream.read())
            config = self._load_config(paths["config"])
            self.assertEqual(config["database_path"], paths["stale_database"])
            self.assertTrue(os.path.isfile(
                os.path.join(paths["database"], "producer")))
            os.rmdir(paths["bootstrap_home"])

            resumed = self._run(home)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            rebound = self._load_config(paths["config"])
            self.assertEqual(rebound["database_path"], paths["database"])
            self.assertEqual(
                rebound["fixture_extra"], config["fixture_extra"])
            self.assertFalse(os.path.lexists(paths["intent"]))
            self.assertFalse(os.path.lexists(paths["stage"]))

    def test_prepared_config_stage_is_replayed(self):
        needle = ('      publish)\n'
                  '        [ -n "$expected" ] && '
                  '[ -n "$staged_generation" ] || return 1')
        self.assertIn(needle, self.functions)
        interrupted = self.functions.replace(
            needle, '      publish)\n        return 1\n'
            '        [ -n "$expected" ] && '
            '[ -n "$staged_generation" ] || return 1',
            1)
        with tempfile.TemporaryDirectory() as home:
            failed = self._run(home, functions=interrupted)
            self.assertNotEqual(failed.returncode, 0)
            paths = self._bootstrap_paths(home)
            self.assertEqual(
                self._load_config(paths["config"])["database_path"],
                paths["stale_database"])
            self.assertEqual(
                self._load_config(paths["stage"])["database_path"],
                paths["database"])

            resumed = self._run(home)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(
                self._load_config(paths["config"])["database_path"],
                paths["database"])
            self.assertFalse(os.path.lexists(paths["stage"]))

    def test_rebind_cas_refuses_target_replacement_after_classifier(self):
        needle = (
            '        if ! owned_file_cas publish "$stage" "$config" '
            '"$expected" \\\n'
            '            "$bound_tree" "$staged_generation" '
            '>/dev/null; then')
        self.assertIn(needle, self.functions)
        replacement = (
            '        mv -- "$config" "$config.operator-prior"\n'
            '        printf \'%s\\n\' target-race > "$config"\n'
            '        chmod 0600 -- "$config"\n' + needle)
        interrupted = self.functions.replace(needle, replacement, 1)
        with tempfile.TemporaryDirectory() as home:
            refused = self._run(home, functions=interrupted)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("CAS target changed before operation", refused.stderr)
            paths = self._bootstrap_paths(home)
            with open(paths["config"], "rb") as stream:
                self.assertEqual(stream.read(), b"target-race\n")
            self.assertEqual(
                self._load_config(paths["config"] + ".operator-prior")[
                    "database_path"],
                paths["stale_database"])
            self.assertEqual(
                self._load_config(paths["stage"])["database_path"],
                paths["database"])
            self.assertTrue(os.path.isfile(paths["intent"]))

    def test_rebind_cas_refuses_stage_replacement_after_classifier(self):
        needle = (
            '        if ! owned_file_cas publish "$stage" "$config" '
            '"$expected" \\\n'
            '            "$bound_tree" "$staged_generation" '
            '>/dev/null; then')
        self.assertIn(needle, self.functions)
        replacement = (
            '        mv -- "$stage" "$stage.operator-prior"\n'
            '        printf \'%s\\n\' stage-race > "$stage"\n'
            '        chmod 0600 -- "$stage"\n' + needle)
        interrupted = self.functions.replace(needle, replacement, 1)
        with tempfile.TemporaryDirectory() as home:
            refused = self._run(home, functions=interrupted)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("CAS stage changed before operation", refused.stderr)
            paths = self._bootstrap_paths(home)
            self.assertEqual(
                self._load_config(paths["config"])["database_path"],
                paths["stale_database"])
            with open(paths["stage"], "rb") as stream:
                self.assertEqual(stream.read(), b"stage-race\n")
            self.assertEqual(
                self._load_config(paths["stage"] + ".operator-prior")[
                    "database_path"],
                paths["database"])
            self.assertTrue(os.path.isfile(paths["intent"]))

    def test_bound_root_replacement_is_refused_before_recovery_or_cas(self):
        recover = '  owned_file_cas recover "$config" "$bound_tree" || return 1'
        publish = (
            '        if ! owned_file_cas publish "$stage" "$config" '
            '"$expected" \\\n'
            '            "$bound_tree" "$staged_generation" '
            '>/dev/null; then')
        self.assertIn(recover, self.functions)
        self.assertIn(publish, self.functions)
        for seam, needle in (("recovery", recover), ("cas", publish)):
            with self.subTest(seam=seam), tempfile.TemporaryDirectory() as home:
                commands = (
                    f'  mv -- "$root" "$root.operator-prior"\n'
                    f'  mkdir -m 0700 -- "$root"\n'
                    f'  printf \'%s\\n\' root-{seam}-race > "$root/operator"\n'
                    + needle)
                interrupted = self.functions.replace(needle, commands, 1)
                refused = self._run(home, functions=interrupted)
                self.assertNotEqual(refused.returncode, 0)
                self.assertIn(
                    "CAS parent does not match its bound tree root",
                    refused.stderr)
                paths = self._bootstrap_paths(home)
                with open(os.path.join(paths["target"], "operator"),
                          encoding="utf-8") as stream:
                    self.assertEqual(stream.read(), f"root-{seam}-race\n")
                prior = paths["target"] + ".operator-prior"
                self.assertEqual(
                    self._load_config(os.path.join(prior, "config.json"))[
                        "database_path"],
                    paths["stale_database"])
                self.assertTrue(os.path.isfile(paths["intent"]))

    def test_predecessor_cleanup_refuses_target_replacement(self):
        needle = (
            '        remove_retired_stage(\n'
            '            directory, os.path.basename(staged), '
            'os.path.basename(retired),\n'
            '            stage_info,\n'
            '            "config.json", target_info)')
        self.assertIn(needle, self.functions)
        replacement = (
            '        os.rename(\n'
            '            "config.json", ".config.json.operator-prior",\n'
            '            src_dir_fd=directory, dst_dir_fd=directory)\n'
            '        replacement = os.open(\n'
            '            "config.json",\n'
            '            os.O_WRONLY | os.O_CREAT | os.O_EXCL\n'
            '            | getattr(os, "O_CLOEXEC", 0),\n'
            '            0o600, dir_fd=directory)\n'
            '        try:\n'
            '            os.write(replacement, b"cleanup-target-race\\n")\n'
            '            os.fsync(replacement)\n'
            '        finally:\n'
            '            os.close(replacement)\n'
            '        os.fsync(directory)\n' + needle)
        interrupted = self.functions.replace(needle, replacement, 1)
        with tempfile.TemporaryDirectory() as home:
            refused = self._run(home, functions=interrupted)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn(
                "gbrain config changed before claim retirement",
                refused.stderr)
            paths = self._bootstrap_paths(home)
            with open(paths["config"], "rb") as stream:
                self.assertEqual(stream.read(), b"cleanup-target-race\n")
            self.assertEqual(
                self._load_config(os.path.join(
                    paths["target"], ".config.json.operator-prior"))[
                        "database_path"],
                paths["database"])
            self.assertEqual(
                self._load_config(paths["retired"])["database_path"],
                paths["stale_database"])
            self.assertFalse(os.path.lexists(paths["stage"]))
            self.assertTrue(os.path.isfile(paths["intent"]))

    def test_predecessor_retirement_preserves_new_public_stage(self):
        needle = (
            '    if stage_exists(directory, public_name):\n'
            '        raise ValueError('
            '"gbrain config stage appeared during retirement")\n'
            '    os.unlink(retired_name, dir_fd=directory)')
        self.assertEqual(self.functions.count(needle), 1)
        collision = (
            '    if stage_exists(directory, public_name):\n'
            '        raise ValueError('
            '"gbrain config stage appeared during retirement")\n'
            '    independent = os.open(\n'
            '        public_name,\n'
            '        os.O_WRONLY | os.O_CREAT | os.O_EXCL\n'
            '        | getattr(os, "O_CLOEXEC", 0)\n'
            '        | getattr(os, "O_NOFOLLOW", 0),\n'
            '        0o600, dir_fd=directory)\n'
            '    try:\n'
            '        os.write(independent, b"retirement-stage-race\\n")\n'
            '        os.fsync(independent)\n'
            '    finally:\n'
            '        os.close(independent)\n'
            '    os.fsync(directory)\n'
            '    os.unlink(retired_name, dir_fd=directory)')
        interrupted = self.functions.replace(needle, collision, 1)
        with tempfile.TemporaryDirectory() as home:
            refused = self._run(home, functions=interrupted)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn(
                "gbrain config stage appeared after retirement",
                refused.stderr)
            paths = self._bootstrap_paths(home)
            with open(paths["stage"], "rb") as stream:
                self.assertEqual(
                    stream.read(), b"retirement-stage-race\n")
            self.assertFalse(os.path.lexists(paths["retired"]))
            self.assertEqual(
                self._load_config(paths["config"])["database_path"],
                paths["database"])
            self.assertTrue(os.path.isfile(paths["intent"]))

    def test_predecessor_retirement_crash_is_recovered(self):
        needle = (
            '    rename_noreplace(directory, name, retired_name)\n'
            '    os.fsync(directory)\n'
            '    try:\n')
        self.assertEqual(self.functions.count(needle), 1)
        interrupted = self.functions.replace(
            needle,
            '    rename_noreplace(directory, name, retired_name)\n'
            '    os.fsync(directory)\n'
            '    os._exit(os.EX_SOFTWARE)\n'
            '    try:\n',
            1)
        with tempfile.TemporaryDirectory() as home:
            crashed = self._run(home, functions=interrupted)
            self.assertNotEqual(crashed.returncode, 0)
            paths = self._bootstrap_paths(home)
            self.assertFalse(os.path.lexists(paths["stage"]))
            self.assertEqual(
                self._load_config(paths["retired"])["database_path"],
                paths["stale_database"])
            self.assertEqual(
                self._load_config(paths["config"])["database_path"],
                paths["database"])
            self.assertTrue(os.path.isfile(paths["intent"]))

            resumed = self._run(home)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertFalse(os.path.lexists(paths["stage"]))
            self.assertFalse(os.path.lexists(paths["retired"]))
            self.assertFalse(os.path.lexists(paths["intent"]))
            self.assertEqual(
                self._load_config(paths["config"])["database_path"],
                paths["database"])

    def test_probing_rebind_refuses_overflow_exponent(self):
        interrupted = self._interrupt_after_probing_intent()
        with tempfile.TemporaryDirectory() as home:
            failed = self._run(home, functions=interrupted)
            self.assertNotEqual(failed.returncode, 0)
            paths = self._bootstrap_paths(home)
            payload = (
                '{"engine":"pglite","database_path":'
                + json.dumps(paths["stale_database"])
                + ',"overflow":1e999}\n').encode("utf-8")
            with open(paths["config"], "wb") as stream:
                stream.write(payload)

            refused = self._run(home)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("non-finite number", refused.stderr)
            with open(paths["config"], "rb") as stream:
                self.assertEqual(stream.read(), payload)
            self.assertFalse(os.path.lexists(paths["stage"]))
            self.assertTrue(os.path.isfile(paths["intent"]))

    def test_bound_cas_restores_post_claim_target_replacement(self):
        needle = (
            '            if expected != "absent":\n'
            '                rename_noreplace(target_name, archive_name)\n')
        self.assertEqual(self.functions.count(needle), 1)
        replacement = (
            '            if expected != "absent":\n'
            '                rename_noreplace(\n'
            '                    target_name,\n'
            '                    ".config.json.fixture-original")\n'
            '                independent = os.open(\n'
            '                    target_name,\n'
            '                    os.O_WRONLY | os.O_CREAT | os.O_EXCL\n'
            '                    | getattr(os, "O_CLOEXEC", 0)\n'
            '                    | getattr(os, "O_NOFOLLOW", 0),\n'
            '                    0o600, dir_fd=parent_fd)\n'
            '                try:\n'
            '                    os.write(\n'
            '                        independent,\n'
            '                        b"post-claim-target-race\\n")\n'
            '                    os.fsync(independent)\n'
            '                finally:\n'
            '                    os.close(independent)\n'
            '                sync_parent()\n'
            '                rename_noreplace(target_name, archive_name)\n')
        interrupted = self.functions.replace(needle, replacement, 1)
        with tempfile.TemporaryDirectory() as home:
            refused = self._run(home, functions=interrupted)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn(
                "CAS archived generation did not match preflight",
                refused.stderr)
            paths = self._bootstrap_paths(home)
            with open(paths["config"], "rb") as stream:
                self.assertEqual(
                    stream.read(), b"post-claim-target-race\n")
            expected_source = (json.dumps({
                "engine": "pglite",
                "database_path": paths["database"],
                "fixture_extra": {"preserve": True},
            }, indent=2, ensure_ascii=False, allow_nan=False) +
                "\n").encode("utf-8")
            with open(paths["stage"], "rb") as stream:
                self.assertEqual(stream.read(), expected_source)
            original = os.path.join(
                paths["target"], ".config.json.fixture-original")
            self.assertEqual(
                self._load_config(original)["database_path"],
                paths["stale_database"])
            self.assertFalse(
                self._cas_artifacts(paths, ".sia-cas-claim-"))
            self.assertFalse(
                self._cas_artifacts(paths, ".sia-cas-prior."))
            self.assertFalse(
                self._cas_artifacts(paths, ".sia-cas-journal-"))
            self.assertTrue(os.path.isfile(paths["intent"]))

    def test_bound_snapshot_isolated_from_claimed_source_mutation(self):
        mutation = (
            '                mutation = os.open(\n'
            '                    claim_name,\n'
            '                    os.O_WRONLY | os.O_TRUNC\n'
            '                    | getattr(os, "O_CLOEXEC", 0)\n'
            '                    | getattr(os, "O_NOFOLLOW", 0),\n'
            '                    dir_fd=parent_fd)\n'
            '                try:\n'
            '                    os.write(\n'
            '                        mutation, b"claimed-source-mutation\\n")\n'
            '                    os.fsync(mutation)\n'
            '                finally:\n'
            '                    os.close(mutation)\n')
        interrupted = self._inject_after_bound_snapshot_link(mutation)
        with tempfile.TemporaryDirectory() as home:
            refused = self._run(home, functions=interrupted)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("bound CAS source claim changed", refused.stderr)
            paths = self._bootstrap_paths(home)
            canonical = self._load_config(paths["config"])
            self.assertEqual(canonical["database_path"], paths["database"])
            self.assertEqual(canonical["fixture_extra"], {"preserve": True})
            claims = self._cas_artifacts(paths, ".sia-cas-claim-")
            self.assertEqual(len(claims), 1)
            with open(claims[0], "rb") as stream:
                self.assertEqual(
                    stream.read(), b"claimed-source-mutation\n")
            self.assertEqual(
                self._load_config(paths["stage"])["database_path"],
                paths["stale_database"])
            self.assertEqual(
                len(self._cas_artifacts(paths, ".sia-cas-journal-")), 1)
            self.assertTrue(os.path.isfile(paths["intent"]))

    def test_bound_finalization_preserves_independent_public_stage(self):
        collision = (
            '                independent = os.open(\n'
            '                    staged_name,\n'
            '                    os.O_WRONLY | os.O_CREAT | os.O_EXCL\n'
            '                    | getattr(os, "O_CLOEXEC", 0)\n'
            '                    | getattr(os, "O_NOFOLLOW", 0),\n'
            '                    0o600, dir_fd=parent_fd)\n'
            '                try:\n'
            '                    os.write(\n'
            '                        independent, b"independent-public-stage\\n")\n'
            '                    os.fsync(independent)\n'
            '                finally:\n'
            '                    os.close(independent)\n'
            '                sync_parent()\n')
        interrupted = self._inject_after_bound_snapshot_link(collision)
        with tempfile.TemporaryDirectory() as home:
            refused = self._run(home, functions=interrupted)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn(
                "bound CAS found an independently occupied backup path",
                refused.stderr)
            paths = self._bootstrap_paths(home)
            with open(paths["stage"], "rb") as stream:
                self.assertEqual(
                    stream.read(), b"independent-public-stage\n")
            self.assertEqual(
                self._load_config(paths["config"])["database_path"],
                paths["database"])
            self.assertEqual(
                len(self._cas_artifacts(paths, ".sia-cas-claim-")), 1)
            self.assertEqual(
                len(self._cas_artifacts(paths, ".sia-cas-journal-")), 1)
            self.assertTrue(os.path.isfile(paths["intent"]))

    def test_bound_recovery_does_not_unlink_independent_public_stage(self):
        interrupted = self._inject_after_bound_snapshot_link(
            '                raise SystemExit('
            '"fixture crash after canonical link")\n')
        with tempfile.TemporaryDirectory() as home:
            crashed = self._run(home, functions=interrupted)
            self.assertNotEqual(crashed.returncode, 0)
            paths = self._bootstrap_paths(home)
            self.assertFalse(os.path.lexists(paths["stage"]))
            with open(paths["stage"], "wb") as stream:
                stream.write(b"independent-recovery-stage\n")
            os.chmod(paths["stage"], 0o600)

            refused = self._run(home)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn(
                "bound CAS found an independently occupied backup path",
                refused.stderr)
            with open(paths["stage"], "rb") as stream:
                self.assertEqual(
                    stream.read(), b"independent-recovery-stage\n")
            self.assertEqual(
                self._load_config(paths["config"])["database_path"],
                paths["database"])
            self.assertEqual(
                len(self._cas_artifacts(paths, ".sia-cas-claim-")), 1)
            self.assertEqual(
                len(self._cas_artifacts(paths, ".sia-cas-journal-")), 1)
            self.assertTrue(os.path.isfile(paths["intent"]))

    def test_bound_cas_crash_boundaries_converge_without_loss(self):
        journal = '            write_journal(record)\n'
        claim = (
            '            try:\n'
            '                rename_noreplace(staged_name, claim_name)\n'
            '                sync_parent()\n')
        archive = (
            '            if expected != "absent":\n'
            '                rename_noreplace(target_name, archive_name)\n'
            '                sync_parent()\n')
        canonical = (
            '            try:\n'
            '                link_descriptor_noreplace('
            'snapshot_fd, target_name)\n'
            '                sync_parent()\n')
        prior_return = (
            '            try:\n'
            '                rename_noreplace(archive, prior_stage)\n'
            '                sync_parent()\n')
        claim_retirement = '            unlink_child(claim_name)\n'
        seams = {
            "v2-journal": (journal, '            '),
            "source-claim": (claim, '                '),
            "target-archive": (archive, '                '),
            "canonical-link": (canonical, '                '),
            "prior-return": (prior_return, '                '),
            "claim-retirement": (claim_retirement, '            '),
        }
        expected_states = {
            "v2-journal": ("stale", "canonical", False, False),
            "source-claim": ("stale", None, True, False),
            "target-archive": (None, None, True, True),
            "canonical-link": ("canonical", None, True, True),
            "prior-return": ("canonical", "stale", True, False),
            "claim-retirement": ("canonical", "stale", False, False),
        }
        for seam, (needle, indentation) in seams.items():
            with self.subTest(seam=seam), tempfile.TemporaryDirectory() as home:
                self.assertIn(needle, self.functions)
                crash = (needle + indentation + 'raise SystemExit('
                         + json.dumps("fixture crash at " + seam) + ')\n')
                interrupted = self.functions.replace(needle, crash, 1)
                failed = self._run(home, functions=interrupted)
                self.assertNotEqual(failed.returncode, 0)
                paths = self._bootstrap_paths(home)
                target_state, stage_state, has_claim, has_archive = \
                    expected_states[seam]
                if target_state is None:
                    self.assertFalse(os.path.lexists(paths["config"]))
                else:
                    expected_path = (paths["database"]
                                     if target_state == "canonical"
                                     else paths["stale_database"])
                    self.assertEqual(
                        self._load_config(paths["config"])["database_path"],
                        expected_path)
                if stage_state is None:
                    self.assertFalse(os.path.lexists(paths["stage"]))
                else:
                    expected_path = (paths["database"]
                                     if stage_state == "canonical"
                                     else paths["stale_database"])
                    self.assertEqual(
                        self._load_config(paths["stage"])["database_path"],
                        expected_path)
                self.assertEqual(
                    bool(self._cas_artifacts(paths, ".sia-cas-claim-")),
                    has_claim)
                self.assertEqual(
                    bool(self._cas_artifacts(paths, ".sia-cas-prior.")),
                    has_archive)
                self.assertEqual(
                    len(self._cas_artifacts(paths, ".sia-cas-journal-")), 1)
                self.assertTrue(os.path.isfile(paths["intent"]))

                resumed = self._run(home)
                self.assertEqual(resumed.returncode, 0, resumed.stderr)
                config = self._load_config(paths["config"])
                self.assertEqual(config["database_path"], paths["database"])
                self.assertEqual(
                    config["fixture_extra"], {"preserve": True})
                self.assertTrue(os.path.isfile(
                    os.path.join(paths["database"], "producer")))
                self.assertFalse(os.path.lexists(paths["stage"]))
                self.assertFalse(os.path.lexists(paths["intent"]))
                for prefix in (
                        ".sia-cas-claim-", ".sia-cas-journal-",
                        ".sia-cas-prior."):
                    self.assertFalse(self._cas_artifacts(paths, prefix))

    def test_published_config_with_retained_predecessor_is_reconciled(self):
        needle = (
            '        if ! owned_file_cas publish "$stage" "$config" '
            '"$expected" \\\n'
            '            "$bound_tree" "$staged_generation" '
            '>/dev/null; then\n'
            '          echo "gbrain config changed during database-path '
            'rebind; preserved" >&2\n'
            '          return 1\n'
            '        fi')
        self.assertIn(needle, self.functions)
        interrupted = self.functions.replace(
            needle, needle + "\n        return 1", 1)
        with tempfile.TemporaryDirectory() as home:
            failed = self._run(home, functions=interrupted)
            self.assertNotEqual(failed.returncode, 0)
            paths = self._bootstrap_paths(home)
            self.assertEqual(
                self._load_config(paths["config"])["database_path"],
                paths["database"])
            self.assertEqual(
                self._load_config(paths["stage"])["database_path"],
                paths["stale_database"])

            resumed = self._run(home)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertFalse(os.path.lexists(paths["stage"]))

    def test_rebound_config_resumes_before_the_final_probe(self):
        needle = '  gbrain_frontdoor_valid "$SHARE" || {'
        position = self.functions.rfind(needle)
        self.assertGreaterEqual(position, 0)
        interrupted = (self.functions[:position] + "  return 1\n" +
                       self.functions[position:])
        with tempfile.TemporaryDirectory() as home:
            failed = self._run(home, functions=interrupted)
            self.assertNotEqual(failed.returncode, 0)
            paths = self._bootstrap_paths(home)
            self.assertEqual(
                self._load_config(paths["config"])["database_path"],
                paths["database"])
            with open(paths["intent"], encoding="utf-8") as stream:
                self.assertIn("phase=probing\n", stream.read())

            resumed = self._run(home)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertFalse(os.path.lexists(paths["intent"]))

    def test_probing_rebind_refuses_a_foreign_database_path(self):
        interrupted = self._interrupt_after_probing_intent()
        with tempfile.TemporaryDirectory() as home:
            failed = self._run(home, functions=interrupted)
            self.assertNotEqual(failed.returncode, 0)
            paths = self._bootstrap_paths(home)
            foreign = os.path.join(home, "operator-brain.pglite")
            os.makedirs(foreign)
            with open(os.path.join(foreign, "producer"), "w",
                      encoding="utf-8") as stream:
                stream.write("operator data\n")
            config = self._load_config(paths["config"])
            config["database_path"] = foreign
            with open(paths["config"], "w", encoding="utf-8") as stream:
                json.dump(config, stream)
                stream.write("\n")
            with open(paths["config"], "rb") as stream:
                before = stream.read()

            refused = self._run(home)
            self.assertNotEqual(refused.returncode, 0)
            with open(paths["config"], "rb") as stream:
                self.assertEqual(stream.read(), before)
            self.assertTrue(os.path.isfile(paths["intent"]))
            self.assertFalse(os.path.lexists(paths["stage"]))

    def test_probing_rebind_refuses_unsafe_or_ambiguous_config(self):
        interrupted = self._interrupt_after_probing_intent()
        for shape in ("duplicate", "wrong-mode", "hardlink", "symlink",
                      "stage-collision"):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as home:
                failed = self._run(home, functions=interrupted)
                self.assertNotEqual(failed.returncode, 0)
                paths = self._bootstrap_paths(home)
                if shape == "duplicate":
                    with open(paths["config"], "w", encoding="utf-8") as stream:
                        stream.write(
                            '{"engine":"pglite","engine":"pglite",'
                            f'"database_path":{json.dumps(paths["stale_database"])}'
                            '}\n')
                elif shape == "wrong-mode":
                    os.chmod(paths["config"], 0o644)
                elif shape == "hardlink":
                    os.link(paths["config"], paths["config"] + ".operator")
                elif shape == "symlink":
                    prior = paths["config"] + ".operator"
                    os.rename(paths["config"], prior)
                    os.symlink(os.path.basename(prior), paths["config"])
                else:
                    with open(paths["stage"], "w", encoding="utf-8") as stream:
                        stream.write("{}\n")
                    os.chmod(paths["stage"], 0o600)

                refused = self._run(home)
                self.assertNotEqual(refused.returncode, 0)
                self.assertTrue(os.path.isfile(paths["intent"]))

    def test_published_intent_rejects_a_different_healthy_store(self):
        needle = "  remove_empty_gbrain_bootstrap_home || return 1"
        position = self.functions.rfind(needle)
        self.assertGreaterEqual(position, 0)
        interrupted = (self.functions[:position] + "  return 1\n" +
                       self.functions[position:])
        with tempfile.TemporaryDirectory() as home:
            failed = self._run(home, functions=interrupted)
            self.assertNotEqual(failed.returncode, 0)
            share = os.path.join(home, "share")
            target = os.path.join(share, ".gbrain")
            intent = os.path.join(
                home, "state", "managed-install", "gbrain-bootstrap")
            with open(intent, encoding="utf-8") as stream:
                self.assertIn("phase=published\n", stream.read())

            os.rename(target, os.path.join(share, ".operator-prior-gbrain"))
            database = os.path.join(target, "brain.pglite")
            os.makedirs(database)
            marker = os.path.join(database, "producer")
            with open(marker, "w", encoding="utf-8") as stream:
                stream.write("independent healthy replacement\n")
            with open(os.path.join(target, "config.json"), "w",
                      encoding="utf-8") as stream:
                stream.write("{}\n")

            refused = self._run(home)
            self.assertNotEqual(refused.returncode, 0)
            self.assertTrue(os.path.isfile(intent))
            with open(marker, encoding="utf-8") as stream:
                self.assertEqual(
                    stream.read(), "independent healthy replacement\n")

    def test_prepared_intent_does_not_claim_an_appeared_workspace(self):
        interrupted = self.functions.replace(
            "complete_gbrain_bootstrap() {",
            "complete_gbrain_bootstrap() {\n  return 1", 1)
        with tempfile.TemporaryDirectory() as home:
            failed = self._run(home, functions=interrupted)
            self.assertNotEqual(failed.returncode, 0)
            workspace = os.path.join(
                home, "share", ".gbrain-bootstrap-home")
            os.makedirs(workspace)
            marker = os.path.join(workspace, "operator")
            with open(marker, "w", encoding="utf-8") as stream:
                stream.write("independent workspace\n")

            refused = self._run(home)
            self.assertNotEqual(refused.returncode, 0)
            with open(marker, encoding="utf-8") as stream:
                self.assertEqual(stream.read(), "independent workspace\n")

    def test_probe_mutation_resumes_from_the_bound_root_then_rebinds(self):
        needle = ('  set_gbrain_bootstrap_intent published "$current" '
                  '|| return 1')
        position = self.functions.rfind(needle)
        self.assertGreaterEqual(position, 0)
        interrupted = (self.functions[:position] + "  return 1\n" +
                       self.functions[position:])
        environment = {"FAKE_GBRAIN_MUTATE_PROBE": "1"}
        with tempfile.TemporaryDirectory() as home:
            failed = self._run(
                home, functions=interrupted, environment=environment)
            self.assertNotEqual(failed.returncode, 0)
            intent = os.path.join(
                home, "state", "managed-install", "gbrain-bootstrap")
            with open(intent, encoding="utf-8") as stream:
                self.assertIn("phase=probing\n", stream.read())

            resumed = self._run(home, environment=environment)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertFalse(os.path.lexists(intent))
            mutation = os.path.join(
                home, "share", ".gbrain", "brain.pglite",
                "probe-mutation")
            with open(mutation, encoding="utf-8") as stream:
                self.assertGreaterEqual(len(stream.readlines()), 2)

    def test_unattributed_or_concurrently_appeared_store_is_preserved(self):
        with tempfile.TemporaryDirectory() as home:
            target = os.path.join(home, "share", ".gbrain")
            os.makedirs(os.path.join(target, "brain.pglite"))
            marker = os.path.join(target, "brain.pglite", "operator")
            with open(marker, "w", encoding="utf-8") as stream:
                stream.write("operator bytes\n")
            refused = self._run(home)
            self.assertNotEqual(refused.returncode, 0)
            with open(marker, encoding="utf-8") as stream:
                self.assertEqual(stream.read(), "operator bytes\n")

        needle = '  [ "$phase" = publishing ] || return 1'
        self.assertIn(needle, self.functions)
        raced = self.functions.replace(
            needle, needle + '\n  mkdir -p "$SHARE/.gbrain"\n'
            '  printf "%s\\n" concurrent > "$SHARE/.gbrain/operator"', 1)
        with tempfile.TemporaryDirectory() as home:
            refused = self._run(home, functions=raced)
            self.assertNotEqual(refused.returncode, 0)
            marker = os.path.join(home, "share", ".gbrain", "operator")
            with open(marker, encoding="utf-8") as stream:
                self.assertEqual(stream.read(), "concurrent\n")


if __name__ == "__main__":
    unittest.main()
