import os
import shlex
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
database = os.path.join(store, "brain.pglite")
if sys.argv[1:2] == ["init"]:
    os.makedirs(database, exist_ok=True)
    with open(os.path.join(database, "producer"), "w", encoding="utf-8") as stream:
        stream.write("gbrain bootstrap\n")
    if os.environ.get("FAKE_GBRAIN_FAIL_INIT") == "1":
        with open(os.path.join(database, "partial"), "w", encoding="utf-8") as stream:
            stream.write("interrupted\n")
        raise SystemExit(19)
    with open(os.path.join(store, "config.json"), "w", encoding="utf-8") as stream:
        json.dump({"engine": "pglite", "database_path": database}, stream)
        stream.write("\n")
    raise SystemExit(0)
if sys.argv[1:] == ["engine", "status", "--probe", "--json"]:
    if not os.path.isfile(os.path.join(store, "config.json")) \
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
            self.assertFalse(os.path.lexists(intent))
            self.assertFalse(any(
                name.startswith(".gbrain-bootstrap-")
                for name in os.listdir(os.path.join(home, "share"))))
            again = self._run(home)
            self.assertEqual(again.returncode, 0, again.stderr)

    def test_post_publish_crash_recovers_only_matching_tree(self):
        needle = ('  set_gbrain_bootstrap_intent probing "$installed" '
                  '|| return 1')
        self.assertIn(needle, self.functions)
        interrupted = self.functions.replace(
            needle, "  return 1\n" + needle, 1)
        with tempfile.TemporaryDirectory() as home:
            failed = self._run(home, functions=interrupted)
            self.assertNotEqual(failed.returncode, 0)
            target = os.path.join(home, "share", ".gbrain")
            self.assertTrue(os.path.isdir(target))
            resumed = self._run(home)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)

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
