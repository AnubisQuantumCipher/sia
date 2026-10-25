"""Account-guard policy tests; kernel/inference evidence is a separate lane."""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import copy
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "siaollamaguard", ROOT / "bin/siaollamaguard.py")
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


def observed_table():
    return json.loads((ROOT / "tests/fixtures/ollama-owner-table-v1.json").read_bytes())


def encode(value):
    return json.dumps(value).encode()


def identity(uid):
    """Only the guard sees this identity; stdlib os stays untouched."""
    return SimpleNamespace(getuid=lambda: uid, geteuid=lambda: uid)


class Configuration(unittest.TestCase):
    def test_canonical_uid_and_maximum(self):
        for uid in (0, 1, 1000, 100000, 4294967294):
            self.assertEqual(GUARD.owner_uid(f"{uid}\n".encode()), uid)

    def test_noncanonical_or_reserved_uid_refuses(self):
        for raw in (b"", b"0", b"01\n", b"-1\n", b"+1\n", b" 1\n",
                    b"1 \n", b"1\r\n", b"1\n2\n", b"4294967295\n",
                    b"10000000000\n", b"\xff\n", b"true\n"):
            with self.subTest(raw=raw), self.assertRaises(GUARD.Refusal):
                GUARD.owner_uid(raw)

    def test_root_unit_and_helper_bound(self):
        self.assertEqual((ROOT / "systemd/sia-ollama-guard.service").read_text(),
                         GUARD.ROOT_UNIT)
        self.assertLessEqual((ROOT / "bin/siaollamaguard.py").stat().st_size, 32768)

    def test_checker_delegation_has_no_wildcards_or_apply_authority(self):
        self.assertEqual(GUARD.sudoers_rule(1000),
                         b"#1000 ALL=(root) NOPASSWD: NOSETENV: /usr/bin/python3 "
                         b"-I -S -B /usr/local/libexec/sia-ollama-guard check-kernel\n")

    def test_unprivileged_parent_and_symlink_refuse(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "owner"
            path.write_text("1000\n")
            link = Path(root) / "link"
            link.symlink_to(path)
            for candidate in (path, link):
                with self.assertRaises((OSError, GUARD.Refusal)):
                    GUARD._root_file(str(candidate), 11)

    def test_root_apply_required(self):
        with mock.patch.object(GUARD, "os", identity(1000)):
            with self.assertRaises(GUARD.Refusal):
                GUARD.apply(1000)


class KernelShape(unittest.TestCase):
    def test_pre_dnat_filter_priority_is_refused(self):
        for index in (2, 3):
            changed = observed_table()
            changed["nftables"][index]["chain"]["prio"] = -150
            self.assertFalse(GUARD.table_matches(encode(changed), 0))

    def test_observed_nft_117_output(self):
        self.assertTrue(GUARD.table_matches(encode(observed_table()), 0))
        self.assertFalse(GUARD.table_matches(encode(observed_table()), 1000))

    def test_each_rule_and_closed_shape_are_required(self):
        original = observed_table()
        for index in range(1, len(original["nftables"])):
            changed = copy.deepcopy(original)
            del changed["nftables"][index]
            self.assertFalse(GUARD.table_matches(encode(changed), 0))
        changed = copy.deepcopy(original)
        changed["nftables"][4]["rule"]["expr"][2]["match"]["op"] = "=="
        self.assertFalse(GUARD.table_matches(encode(changed), 0))
        changed = copy.deepcopy(original)
        changed["nftables"][4]["rule"]["expr"][-1] = {"accept": None}
        self.assertFalse(GUARD.table_matches(encode(changed), 0))
        changed = copy.deepcopy(original)
        changed["nftables"][5]["rule"]["expr"][0]["match"]["right"] = "::2"
        self.assertFalse(GUARD.table_matches(encode(changed), 0))
        changed = copy.deepcopy(original)
        changed["nftables"][6]["rule"]["expr"][1]["match"]["right"] = "eth0"
        self.assertFalse(GUARD.table_matches(encode(changed), 0))

    def test_unknown_fields_duplicate_keys_and_bool_integers_refuse(self):
        changed = observed_table()
        changed["nftables"][1]["table"]["extra"] = True
        self.assertFalse(GUARD.table_matches(encode(changed), 0))
        changed = observed_table()
        changed["nftables"][4]["rule"]["expr"][2]["match"]["right"] = False
        self.assertFalse(GUARD.table_matches(encode(changed), 0))
        for raw in (b'{"nftables":[],"nftables":[]}', b"null", b"[]",
                    b'{"nftables":[0,0,0,0,0,0,0]}', b"[" * 4000,
                    b"x" * (GUARD.LIMIT + 1)):
            self.assertFalse(GUARD.table_matches(raw, 0))

    def test_existing_mismatch_is_never_replaced(self):
        with mock.patch.object(GUARD, "os", identity(0)), \
             mock.patch.object(GUARD, "_run", return_value=(0, b"{}")) as run:
            with self.assertRaises(GUARD.Refusal):
                GUARD.apply(1000)
            self.assertEqual(run.call_count, 1)

    def test_successful_command_with_wrong_readback_refuses(self):
        with mock.patch.object(GUARD, "os", identity(0)), \
             mock.patch.object(GUARD, "_run",
                               side_effect=[(1, b"absent"), (0, b""), (0, b"{}")]):
            with self.assertRaises(GUARD.Refusal):
                GUARD.apply(1000)


class ProcessBoundary(unittest.TestCase):
    def test_gate_rejects_stale_service_success_when_kernel_check_fails(self):
        source = (ROOT / "bin/siaollamaguard.py").read_bytes()
        files = {GUARD.CONFIG: b"1000\n", GUARD.HELPER: source,
                 GUARD.UNIT: GUARD.ROOT_UNIT.encode()}
        with mock.patch.object(GUARD, "_root_file", side_effect=lambda p, limit: files[p]), \
             mock.patch.object(GUARD, "os", identity(1000)), \
             mock.patch.object(GUARD, "_manager_matches", return_value=True), \
             mock.patch.object(GUARD, "_run", side_effect=[(0, b"active"), (1, b"drift")]) as run:
            with self.assertRaisesRegex(GUARD.Refusal, "fresh administrator kernel check"):
                GUARD.gate()
        self.assertEqual(run.call_args.args[0],
                         ["/usr/bin/sudo", "-n", "--", "/usr/bin/python3", "-I", "-S",
                          "-B", GUARD.HELPER, "check-kernel"])

    def test_output_overflow_terminates_child(self):
        with self.assertRaisesRegex(GUARD.Refusal, "exceeded"):
            GUARD._run([sys.executable, "-I", "-S", "-c",
                        "import os; os.write(1, b'x' * 32768)"])

    def test_exit_status_is_not_hidden(self):
        code, output = GUARD._run([sys.executable, "-I", "-S", "-c",
                                  "import sys; print('failure'); sys.exit(7)"])
        self.assertEqual(code, 7)
        self.assertEqual(output, b"failure\n")

    def test_ambient_bus_and_python_overrides_are_removed(self):
        with mock.patch.dict(os.environ, {"DBUS_SYSTEM_BUS_ADDRESS": "bad",
                                          "PYTHONPATH": "/untrusted"}):
            code, output = GUARD._run(
                [sys.executable, "-I", "-S", "-c",
                 "import os; print('DBUS_SYSTEM_BUS_ADDRESS' in os.environ); "
                 "print('PYTHONPATH' in os.environ)"])
        self.assertEqual((code, output), (0, b"False\nFalse\n"))

    def test_manager_requires_exact_success_and_persistence(self):
        properties = {
            "LoadState": "loaded", "ActiveState": "active", "SubState": "exited",
            "Result": "success", "ExecMainStatus": "0", "DropInPaths": "",
            "FragmentPath": GUARD.UNIT, "NeedDaemonReload": "no",
            "UnitFileState": "enabled",
        }
        raw = "\n".join(k + "=" + v for k, v in properties.items()).encode()
        self.assertTrue(GUARD._manager_matches(raw))
        for key, value in properties.items():
            changed = raw.replace((key + "=" + value).encode(),
                                  (key + "=unexpected").encode())
            self.assertFalse(GUARD._manager_matches(changed))
        self.assertFalse(GUARD._manager_matches(raw + b"\nActiveState=active"))


class IntegrationWiring(unittest.TestCase):
    def test_standalone_snapshot_keeps_the_guard_runbook_and_links(self):
        installer = (ROOT / "install.sh").read_text()
        start = installer.index("release_source_frontdoor() {")
        end = installer.index("\n}\n\nSIA_RELEASE_FILES", start) + 3
        frontdoor = installer[start:end] + '\nrelease_source_frontdoor "$@"'
        roster = shlex.split(installer.split("SIA_RELEASE_FILES=(", 1)[1]
                             .split("\n)", 1)[0])
        self.assertLessEqual(len(roster), 256)
        start = installer.index("  PLUGIN_ROOT_FILES=(")
        end = installer.index('  PLUGIN_RESULT="$(atomic_install_tree', start)
        staging = 'REPO="$1"\nSIA_PLUGIN_STAGE="$2"\n' + installer[start:end]
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot"
            plugin = Path(directory) / "plugin"
            plugin.mkdir()
            try:
                commands = [
                    ["bash", "-eu", "-c", frontdoor, "guard-snapshot",
                     "snapshot", str(ROOT), str(snapshot), *roster],
                    ["bash", "-eu", "-c", frontdoor, "guard-snapshot",
                     "verify", str(ROOT), str(snapshot), *roster],
                    ["bash", "-eu", "-c", staging, "guard-staging",
                     str(snapshot), str(plugin)],
                ]
                for command in commands:
                    result = subprocess.run(command, capture_output=True,
                                            timeout=30, check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)
                runbook = "docs/OLLAMA-ACCOUNT-GUARD.md"
                self.assertEqual((plugin / runbook).read_bytes(),
                                 (ROOT / runbook).read_bytes())
                for name, link in (
                        ("README.md", runbook), ("SECURITY.md", runbook),
                        ("docs/MANUAL.md", "OLLAMA-ACCOUNT-GUARD.md")):
                    document = plugin / name
                    self.assertIn("(" + link + ")", document.read_text())
                    self.assertEqual((document.parent / link).resolve(),
                                     (plugin / runbook).resolve())
            finally:
                subprocess.run(["chmod", "-R", "u+w", "--", directory],
                               capture_output=True, timeout=10, check=True)

    def test_every_ollama_start_is_gated_before_exec(self):
        unit = (ROOT / "systemd/sia-ollama.service").read_text()
        self.assertLess(unit.index("ExecStartPre="), unit.index("ExecStart="))
        self.assertIn("/usr/local/libexec/sia-ollama-guard gate", unit)
        lines = [line.strip() for line in unit.splitlines()]
        pre = [line for line in lines if line.startswith("ExecStartPre=")]
        start = [line for line in lines if line.startswith("ExecStart=")]
        self.assertEqual(len(start), 1)
        self.assertEqual(pre, ["ExecStartPre=/usr/bin/python3 -I -S -B "
                               "/usr/local/libexec/sia-ollama-guard gate"])

    def test_installer_guard_precedes_mutations_and_override(self):
        installer = (ROOT / "install.sh").read_text()
        check = installer.index('python3 -I -S "$REPO/bin/siaollamaguard.py" gate')
        self.assertLess(check, installer.index('SIA_INSTALL_TMP="$(mktemp'))
        self.assertLess(check, installer.index("SIA_ALLOW_UNPINNED_OLLAMA"))
        self.assertIn("bin/siaollamaguard.py systemd/sia-ollama-guard.service", installer)
        published = installer.split("SIA_RELEASE_FILES=(", 1)[1].split("\n)", 1)[0]
        self.assertIn("docs/OLLAMA-ACCOUNT-GUARD.md", published)

    def test_uninstall_does_not_remove_root_guard(self):
        uninstall = (ROOT / "uninstall.sh").read_text()
        self.assertNotIn("/usr/local/libexec/sia-ollama-guard", uninstall)
        self.assertNotIn("/etc/sia/ollama-owner", uninstall)
        self.assertIn("Ollama (including its service/model) is left installed.", uninstall)


if __name__ == "__main__":
    unittest.main()
