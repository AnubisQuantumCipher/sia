#!/usr/bin/env python3
"""Release-shape and installer supply-chain regression tests."""

import hashlib
import fcntl
import importlib.machinery
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(relative):
    with open(os.path.join(REPO, relative), encoding="utf-8") as stream:
        return stream.read()


def _read_path(path):
    with open(path, encoding="utf-8") as stream:
        return stream.read()


def _write(path, content, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(content)
    if mode is not None:
        os.chmod(path, mode)


def _fake_command(directory, name, body):
    _write(os.path.join(directory, name), "#!/bin/sh\n" + body, 0o755)


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ABSENT_USER_UNIT = (
    'if [ "$1 $2" = "--user show" ]; then\n'
    '  echo "LoadState=not-found"; echo "ActiveState=inactive"\n'
    '  echo "FragmentPath="; echo "UnitFileState="\n'
    '  echo "DropInPaths="; echo "MainPID=0"\n'
    '  exit 0\n'
    'fi\n'
    'exit 0\n')


def _managed_file_receipt(path, kind):
    with open(path, "rb") as stream:
        digest = hashlib.sha256(stream.read()).hexdigest()
    return ("managed-by=khephri.sia\n"
            f"kind={kind}\npath={path}\nsha256={digest}\n")


def _runtime_digest(root):
    legacy_names = ("sia-brainstem", "sia-ledger", "sia-mcp", "siabench.py",
                    "sialib.py", "siamind.py", "siaqueue.py", "siatakes.py")
    modern_names = ("sia-brainstem", "sia-brainstem.py", "sia-cli",
                    "sia-ledger", "sia-mcp", "siabench.py", "sialib.py",
                    "siamind.py", "siaqueue.py", "siatakes.py")
    modern = any(os.path.lexists(os.path.join(root, name))
                 for name in ("sia-brainstem.py", "sia-cli"))
    names = modern_names if modern else legacy_names
    digest = hashlib.sha256(
        b"sia-runtime-v2\0" if modern else b"sia-runtime-v1\0")
    for name in names:
        with open(os.path.join(root, name), "rb") as stream:
            content = stream.read()
        digest.update(name.encode() + b"\0" + hashlib.sha256(content).digest())
    return digest.hexdigest()


def _managed_cli_runtime(home):
    runtime = os.path.join(home, ".local/share/sia/bin")
    for name in ("sia-brainstem", "sia-ledger", "sia-mcp", "siabench.py",
                 "sialib.py", "siamind.py", "siaqueue.py", "siatakes.py"):
        _write(os.path.join(runtime, name), name + "\n")
    cli = os.path.join(home, ".local/bin/sia")
    _write(cli, "managed cli\n")
    managed = os.path.join(home, ".local/state/sia/managed-install")
    _write(os.path.join(managed, "sia-cli"),
           _managed_file_receipt(cli, "sia-cli"))
    _write(os.path.join(managed, "runtime"),
           "managed-by=khephri.sia\nkind=runtime\n"
           f"path={runtime}\nsha256={_runtime_digest(runtime)}\n")
    return cli, runtime


def _mcp_guard_contents(home, client, reason):
    runtime = os.path.join(home, ".local/share/sia/bin")
    return (
        "guarded-by=khephri.sia\n"
        "kind=external-mcp-consumer\n"
        f"consumer={client}\n"
        "ownership=external\n"
        "command=python3\n"
        f"arg={runtime}/sia-mcp\n"
        f"reason={reason}\n"
    )


def _generate_stable_launcher(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    installer = _read("install.sh")
    body = installer.split("write_stable_generation_launcher() {", 1)[1] \
        .split("\n}\n\npreflight_owned_file", 1)[0]
    function = "write_stable_generation_launcher() {" + body + "\n}\n"
    result = subprocess.run(
        ["bash", "-c", function + '\nwrite_stable_generation_launcher "$1"',
         "launcher-test", path], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr)


def _bounded_commands_shell(script):
    return "bounded_command_capture() {" + script.split(
        "bounded_command_capture() {", 1)[1].split(
        "\nowned_metadata() {", 1)[0]


def _owned_metadata_shell(script):
    bounded = _bounded_commands_shell(script)
    body = script.split("owned_metadata() {", 1)[1].split(
        "\n}\n\nwrite_lifecycle_tombstone", 1)[0]
    return bounded + "\nowned_metadata() {" + body + "\n}\n"


def _owned_metadata_python(script):
    return script.split("owned_metadata() {\n"
                        "  python3 - \"$@\" <<'PY'\n", 1)[1].split(
                            "\nPY\n}", 1)[0]


class ReleaseContract(unittest.TestCase):
    def test_manifest_entrypoints_and_versions_are_consistent(self):
        manifest = json.loads(_read("manifest.json"))
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertRegex(manifest["id"], r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$")
        for relative in manifest["entryPoints"].values():
            self.assertTrue(os.path.isfile(os.path.join(REPO, relative)),
                            relative)
        version = manifest["version"]
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertIn(f'VERSION = "{version}"', _read("bin/sialib.py"))
        self.assertIn(f'SERVER_VERSION = "{version}"',
                      _read("bin/sia-mcp"))
        self.assertIn(f"## {version} —", _read("CHANGELOG.md"))

    def test_marketplace_documentation_and_license_are_present(self):
        readme = _read("README.md").casefold()
        self.assertTrue(os.path.isfile(os.path.join(REPO, "LICENSE")))
        self.assertIn("install", readme)
        self.assertIn("remove", readme)
        self.assertIn("uninstall.sh", readme)
        self.assertIn("--purge", readme)
        for dependency in ("python", "git", "curl", "tar", "unzip",
                           "sha256sum", "zstd", "systemctl", "flock",
                           "iproute2"):
            self.assertIn(dependency, readme)

    def test_operator_docs_state_installer_and_removal_boundaries(self):
        readme = _read("README.md")
        manual = _read("docs/MANUAL.md")
        for document in (readme, manual):
            self.assertIn("# SIA corpus — this machine's memory", document)
            self.assertIn("bin/sia-ledger verify", document)
            self.assertIn("does not attest to extra entries", document)
            self.assertIn("not byte-for-byte intact", document)
            self.assertIn("not transactional", document)
            self.assertIn("unrelated mismatched", document)
            self.assertIn("Python-cryptography", document)
        self.assertIn("malformed/non-list JSON", readme)
        self.assertIn("valid top-level-list JSON", manual)
        self.assertIn("SIA does not silently delete", manual)
        self.assertIn("SIA does not guess", manual)
        self.assertIn("For a standalone install", _read("skill/SKILL.md"))
        self.assertIn("not access-control or egress controls",
                      _read("SECURITY.md"))
        config = json.loads(_read("config.example.json"))
        boundary = config["_egress_trust_boundary"]
        self.assertIn("MCP client", boundary)
        self.assertIn("CLI", boundary)

    def test_generalized_publication_and_legacy_upgrade_are_documented(self):
        documents = {
            relative: _read(relative)
            for relative in (
                "README.md", "docs/MANUAL.md", "docs/WHITEPAPER.md",
                "CHANGELOG.md", "SECURITY.md",
            )
        }
        contract_terms = (
            "MIGRATE:take-origin",
            "model-inert-v1",
            "legacy-v1-normalize",
            "origin: derived",
            "origin: model",
            "take-migrations",
            "sync_needed",
        )
        for relative, document in documents.items():
            with self.subTest(document=relative):
                for term in contract_terms:
                    self.assertIn(term, document)
                folded = " ".join(document.casefold().split())
                for term in (
                    "publication debt",
                    "grade-transactions",
                    "same corpus generation",
                    "pulse sequence",
                    "returned result",
                    "memory-backed",
                ):
                    self.assertIn(term, folded)
                for writer in (
                    "`pulse`", "`dream`", "`take`", "`intent`",
                    "`grade`", "`ponder`",
                ):
                    self.assertIn(writer, document)
                for surface in ("git", "PGLite", "graph"):
                    self.assertIn(surface, document)

        for relative in ("README.md", "docs/MANUAL.md", "CHANGELOG.md"):
            document = documents[relative]
            with self.subTest(first_light_document=relative):
                self.assertIn("first-light pulse", document)
                self.assertIn("successful `sia pulse`", document)
                self.assertIn("last-published", document)

        for relative in ("README.md", "docs/MANUAL.md"):
            self.assertIn("SIA memory read refused", documents[relative])
            self.assertIn("readiness line", documents[relative])

        for relative in ("docs/WHITEPAPER.md", "SECURITY.md"):
            document = documents[relative].casefold()
            with self.subTest(non_claim_document=relative):
                self.assertIn("not prove", document)
                self.assertIn("verdict", document)
                self.assertIn("access-control boundary", document)
                self.assertIn("gbrain", document)
                self.assertIn("raw corpus", document)

    def test_default_configuration_requires_explicit_judge_consent(self):
        config = json.loads(_read("config.example.json"))
        self.assertEqual(config["judge"]["backend"], "none")
        self.assertEqual(config["judge"]["model"], "")

    def test_installer_uses_full_pins_and_verified_downloads(self):
        installer = _read("install.sh")
        flattened_installer = re.sub(r"\\\n\s*", " ", installer)
        ordered_installer = re.sub(r"\s+", " ", flattened_installer)
        pins = dict(line.split("=", 1)
                    for line in _read("GBRAIN_PIN").splitlines()
                    if "=" in line and not line.startswith("#"))
        self.assertRegex(pins["commit"], r"^[0-9a-f]{40}$")
        self.assertRegex(pins["bun_lock_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn('[[ "$PIN" =~ ^[0-9a-f]{40}$ ]]', installer)
        self.assertIn('git -C "$GBRAIN_SOURCE" rev-parse HEAD', installer)
        self.assertRegex(
            flattened_installer,
            r'run_with_deadline 1800 "\$BUN_BIN" install\s+'
            r'--cwd "\$GBRAIN_SOURCE"\s+--frozen-lockfile')
        self.assertIn('--production --ignore-scripts --no-progress', installer)
        self.assertRegex(
            flattened_installer,
            r'run_with_deadline 1800 "\$BUN_BIN" build\s+'
            r'--compile\s+--outfile')
        self.assertIn(
            'GBRAIN_VERSION_OUTPUT="$(bounded_command_capture', installer)
        self.assertIn('GBRAIN_BIN="$GBRAIN_ROOT/bin/gbrain"', installer)
        self.assertNotIn('bun install -g', installer)
        self.assertNotIn('$HOME/.bun', installer)
        self.assertIn("sha256sum -c -", installer)
        self.assertNotIn("releases/latest", installer)
        self.assertNotRegex(installer,
                            r"curl[^\n]*\|\s*(?:ba)?sh(?:\s|$)")
        self.assertIn("--max-filesize 2147483648", installer)
        self.assertIn("run_with_deadline 300 unzip -q", installer)
        self.assertIn("run_with_deadline 300 tar --zstd", installer)
        checksums = re.findall(r"^\s*[A-Z0-9_]+_SHA256=([0-9a-f]+)$",
                              installer, re.MULTILINE)
        self.assertTrue(checksums)
        self.assertTrue(all(len(value) == 64 for value in checksums))
        self.assertIn('siabench.py siaqueue.py', installer)
        self.assertIn('SIA_INSTALL_KEYBINDING:-0', installer)
        self.assertIn('SIA_BRAINSTEM_WAS_ACTIVE=1', installer)
        self.assertIn('SIA_INSTALL_MUTATED=1', installer)
        self.assertIn('"INSTALL:runtime"', installer)
        self.assertIn('"INSTALL:index"', installer)
        self.assertGreaterEqual(installer.count("sialib.durable_ledger_append"),
                                2)
        bun_mutation = installer.index('SIA_INSTALL_MUTATED=1',
                                       installer.index('BUN_VERSION='))
        self.assertLess(bun_mutation,
                        installer.index('atomic_install_tree "$SIA_BUN_STAGE"'))
        self.assertIn('install failed after mutation; sia-brainstem was disabled and stopped',
                      installer)
        self.assertIn('SIA_RUNTIME_STAGE="$(mktemp -d '
                      '"$SHARE/.bin.stage.XXXXXX")"', installer)
        self.assertIn('atomic_install_tree "$SIA_RUNTIME_STAGE" "$BINDIR"',
                      installer)
        self.assertIn('SIA_LAUNCHER_ABI', installer)
        self.assertIn('"$SIA_RUNTIME_STAGE/sia-brainstem.py"', installer)
        self.assertIn('"$SIA_RUNTIME_STAGE/sia-cli"', installer)
        self.assertIn('drain_legacy_launchers', installer)
        self.assertIn('previous runtime tree retained', installer)
        self.assertNotIn('cp "$REPO"/bin/sialib.py', installer)
        self.assertIn('export GBRAIN_SKIP_STARTUP_HOOKS=1', installer)
        self.assertLess(installer.index('export GBRAIN_SKIP_STARTUP_HOOKS=1'),
                        installer.index('"$GBRAIN_BIN" --version'))
        self.assertIn('[ "$GBRAIN_VERSION_OUTPUT" = "gbrain $PIN_VERSION" ]',
                      installer)
        self.assertNotIn('gbrain config set self_upgrade.mode off', installer)
        self.assertIn('self_upgrade["mode"] = "off"', installer)
        self.assertIn('"$GBRAIN_BIN" config get self_upgrade.mode', installer)
        self.assertIn('[ "$GBRAIN_SELF_UPGRADE_MODE" = "off" ]', installer)
        self.assertIn('"$GBRAIN_BIN" sources list --json', installer)
        self.assertNotIn(
            'gbrain sources add sia --path "$SHARE/corpus" 2>/dev/null || true',
            installer)
        self.assertNotIn(
            'gbrain schema validate sia-pack >/dev/null && gbrain schema use',
            installer)
        self.assertIn('SIA_CANONICAL_HOME="$(cd -P -- "$HOME"', installer)
        self.assertIn('HOME resolves to /', installer)
        self.assertIn('LIFECYCLE_LOCK="$HOME/.local/state/sia.lifecycle.lock"',
                      installer)
        self.assertIn('acquire_owner_lock "$STATE/corpus-owner.lock"',
                      installer)
        self.assertIn('preflight_corpus', installer)
        cli_preflight = installer.index(
            'preflight_owned_file "$SIA_STABLE_LAUNCHER" "$CLI_PATH"')
        runtime_exchange = installer.index(
            'atomic_install_tree "$SIA_RUNTIME_STAGE" "$BINDIR"')
        self.assertLess(cli_preflight, runtime_exchange)
        self.assertIn('[[ "$digest" =~ ^[0-9a-f]{64}$ ]]', installer)
        self.assertIn("MAX_METADATA_BYTES = 65_536", installer)
        self.assertIn('getattr(os, "O_NOFOLLOW", 0)', installer)
        self.assertIn("finish_stable(path, descriptor, before)", installer)
        self.assertIn('owned_metadata managed-file "$receipt" "$kind"',
                      installer)
        self.assertNotIn('contents="$(cat -- "$receipt")"', installer)
        self.assertIn("DropInPaths", installer)
        self.assertIn("is not running the exact managed runtime", installer)
        self.assertNotIn('SIA_BACKFILL=1 "$HOME/.local/bin/sia" pulse || true',
                         installer)
        first_light = installer.index(
            'SIA_BACKFILL=1 python3 "$BINDIR/sia-cli" pulse')
        brainstem_release = installer.index(
            'flock -u "$SIA_BRAINSTEM_LOCK_FD"')
        brainstem_reacquire = installer.index(
            '"brainstem after first light"')
        self.assertLess(brainstem_release, first_light)
        self.assertLess(first_light, brainstem_reacquire)
        first_light_block = installer[
            installer.index('step "7/9 first light'):
            installer.index('step "8/9 desktop')]
        self.assertIn('SIA_INHERITED_LIFECYCLE_FD="$SIA_INSTALL_LOCK_FD"',
                      first_light_block)
        self.assertNotIn('clear_lifecycle_tombstone', first_light_block)
        self.assertNotIn('write_lifecycle_tombstone', first_light_block)
        self.assertNotIn('flock -s "$SIA_INSTALL_LOCK_FD"',
                         first_light_block)
        self.assertIn('flock -n "$SIA_INSTALL_LOCK_FD"', installer)
        self.assertNotIn('flock "$SIA_INSTALL_LOCK_FD"', installer)
        runtime_mask = ordered_installer.index(
            'systemctl --user mask --runtime --now sia-brainstem.service')
        lifecycle_acquire = ordered_installer.index(
            'acquire_install_lifecycle ')
        final_lifecycle_release = ordered_installer.rindex(
            'flock -u "$SIA_INSTALL_LOCK_FD"')
        runtime_unmask = ordered_installer.rindex(
            'remove_install_brainstem_runtime_mask')
        final_start = ordered_installer.rindex(
            'systemctl --user start sia-brainstem.service')
        self.assertLess(runtime_mask, lifecycle_acquire)
        self.assertLess(final_lifecycle_release, runtime_unmask)
        self.assertLess(runtime_unmask, final_start)

    def test_installer_rejects_home_that_resolves_to_root(self):
        environment = os.environ.copy()
        environment["HOME"] = "/tmp/.."
        result = subprocess.run(
            ["bash", os.path.join(REPO, "install.sh")],
            cwd=REPO, env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("HOME resolves to /", result.stderr)

    def test_owned_metadata_rejects_nonexact_and_unstable_files(self):
        for relative in ("install.sh", "uninstall.sh"):
            with self.subTest(script=relative), tempfile.TemporaryDirectory() as root:
                function = _owned_metadata_shell(_read(relative))
                target = os.path.join(root, "target")
                receipt = os.path.join(root, "receipt")
                _write(target, "managed target\n")
                exact = _managed_file_receipt(target, "sia-cli")
                command = (function +
                           '\nowned_metadata managed-file "$1" sia-cli "$2"')

                _write(receipt, exact)
                valid = subprocess.run(
                    ["bash", "-c", command, "metadata-test", receipt, target],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                self.assertEqual(valid.returncode, 0, valid.stderr.decode())

                with open(receipt, "wb") as stream:
                    stream.write(exact.encode() + b"\0ignored")
                nul = subprocess.run(
                    ["bash", "-c", command, "metadata-test", receipt, target],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                self.assertNotEqual(nul.returncode, 0)

                with open(receipt, "wb") as stream:
                    stream.write(b"x" * 65_537)
                oversized = subprocess.run(
                    ["bash", "-c", command, "metadata-test", receipt, target],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                self.assertNotEqual(oversized.returncode, 0)

                os.unlink(receipt)
                replacement = os.path.join(root, "replacement")
                _write(replacement, exact)
                os.symlink(replacement, receipt)
                linked = subprocess.run(
                    ["bash", "-c", command, "metadata-test", receipt, target],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                self.assertNotEqual(linked.returncode, 0)

        installer = _read("install.sh")
        python_source = _owned_metadata_python(installer)
        with tempfile.TemporaryDirectory() as root:
            receipt = os.path.join(root, "receipt")
            replacement = os.path.join(root, "replacement")
            _write(receipt, "managed-by=khephri.sia\n")
            _write(replacement, "managed-by=khephri.sia\n")
            real_stat = os.stat
            replaced = False

            def replacing_stat(path, *args, **kwargs):
                nonlocal replaced
                if path == receipt and not replaced:
                    os.replace(replacement, receipt)
                    replaced = True
                return real_stat(path, *args, **kwargs)

            with mock.patch.object(sys, "argv", [
                    "owned-metadata", "exact", receipt,
                    "managed-by=khephri.sia"]), \
                    mock.patch.object(os, "stat", replacing_stat):
                with self.assertRaises(SystemExit) as stopped:
                    exec(compile(python_source, "owned-metadata", "exec"), {})
            self.assertNotEqual(stopped.exception.code, 0)

            _write(receipt, "managed-by=khephri.sia\n")
            real_fstat = os.fstat
            inspections = 0

            def mutating_fstat(descriptor):
                nonlocal inspections
                inspections += 1
                if inspections == 2:
                    with open(receipt, "ab") as stream:
                        stream.write(b"changed")
                return real_fstat(descriptor)

            with mock.patch.object(sys, "argv", [
                    "owned-metadata", "exact", receipt,
                    "managed-by=khephri.sia"]), \
                    mock.patch.object(os, "fstat", mutating_fstat):
                with self.assertRaises(SystemExit) as stopped:
                    exec(compile(python_source, "owned-metadata", "exec"), {})
            self.assertNotEqual(stopped.exception.code, 0)

    def test_lifecycle_lease_blocks_install_and_uninstall(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            os.makedirs(fake_bin)
            _fake_command(fake_bin, "systemctl", ABSENT_USER_UNIT)
            _fake_command(fake_bin, "sleep", "exit 0\n")
            lock_path = os.path.join(home, ".local/state/sia.lifecycle.lock")
            _write(lock_path, "")
            environment = os.environ.copy()
            environment.update({
                "HOME": home,
                "PATH": fake_bin + os.pathsep + environment["PATH"],
            })
            with open(lock_path, "a+") as lease:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                for script in ("install.sh", "uninstall.sh"):
                    result = subprocess.run(
                        ["bash", os.path.join(REPO, script)],
                        cwd=REPO, env=environment, text=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        check=False)
                    self.assertNotEqual(result.returncode, 0, script)
                    self.assertIn("active SIA clients did not leave",
                                  result.stderr, script)

    def test_uninstaller_fences_legacy_launchers_before_integration_mutation(self):
        uninstaller = _read("uninstall.sh")
        lifecycle = uninstaller.index("acquire_uninstall_lifecycle || exit 1")
        recovery = uninstaller.index(
            "recover_publication_receipts_from_fence || {", lifecycle)
        first_drain = uninstaller.index(
            "drain_legacy_launchers || {", recovery)
        tombstone = uninstaller.index(
            "write_lifecycle_tombstone || {", first_drain)
        fence = uninstaller.index(
            "arm_uninstall_launch_fence || {", tombstone)
        second_drain = uninstaller.index(
            "drain_legacy_launchers || {", fence)
        plugin_mutation = uninstaller.index(
            "omarchy plugin disable khephri.sia", second_drain)
        mcp_mutation = uninstaller.index(
            "remove_managed_mcp claude", second_drain)
        unit_mutation = uninstaller.index(
            'owned_file_cas archive "$UNIT_BACKUP"', second_drain)
        cli_mutation = uninstaller.index(
            'attempt "remove SIA CLI" remove_owned_cli', second_drain)
        purge_mutation = uninstaller.index(
            'attempt "purge retained SIA state"', second_drain)
        self.assertEqual(
            sorted((lifecycle, recovery, first_drain, tombstone, fence,
                    second_drain, plugin_mutation, mcp_mutation,
                    unit_mutation, cli_mutation, purge_mutation)),
            [lifecycle, recovery, first_drain, tombstone, fence,
             second_drain, plugin_mutation, mcp_mutation,
             unit_mutation, cli_mutation, purge_mutation])
        fence_body = uninstaller.split(
            "arm_uninstall_launch_fence() {", 1)[1].split(
                "\n}\n\nrestore_runtime_archive_fence_modes", 1)[0]
        self.assertLess(fence_body.index("os.fsync(stream.fileno())"),
                        fence_body.index("os.fchmod(descriptor, 0)"))
        self.assertIn("os.fsync(directory)", fence_body)
        self.assertIn("os.fsync(descriptor)", fence_body)

    def test_uninstaller_drains_legacy_mcp_then_mutates_behind_durable_fence(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            waiting = os.path.join(root, "drain-waiting")
            allow_drain = os.path.join(root, "allow-drain")
            legacy_started = os.path.join(root, "legacy-started")
            release_legacy = os.path.join(root, "release-legacy")
            mcp_removed = os.path.join(root, "mcp-removed")
            mcp_mutated = os.path.join(root, "mcp-mutated")
            os.makedirs(fake_bin)
            cli, runtime = _managed_cli_runtime(home)
            legacy_mcp = os.path.join(runtime, "sia-mcp")
            _write(
                legacy_mcp,
                "#!/usr/bin/env python3\n"
                "import os, sys, time\n"
                "open(sys.argv[1], 'w', encoding='utf-8').close()\n"
                "while not os.path.exists(sys.argv[2]):\n"
                "    time.sleep(0.01)\n",
                0o755)
            runtime_receipt = os.path.join(
                home, ".local/state/sia/managed-install/runtime")
            _write(
                runtime_receipt,
                "managed-by=khephri.sia\nkind=runtime\n"
                f"path={runtime}\nsha256={_runtime_digest(runtime)}\n")
            _write(
                os.path.join(home, ".local/state/sia/managed-mcp/claude"),
                "managed-by=khephri.sia\ncommand=python3\n"
                f"arg={legacy_mcp}\n")
            _fake_command(fake_bin, "systemctl", ABSENT_USER_UNIT)
            _fake_command(
                fake_bin, "sleep",
                ': > "$DRAIN_WAITING"\n'
                'while [ ! -e "$ALLOW_DRAIN" ]; do '
                '/usr/bin/sleep 0.01; done\n')
            _fake_command(
                fake_bin, "claude",
                'test -f "$HOME/.local/state/sia.lifecycle-removed" '
                '|| exit 90\n'
                'test -f "$HOME/.local/state/sia/managed-install/'
                'launch-fence.json" || exit 91\n'
                'test "$(stat -c %a "$HOME/.local/bin/sia")" = 0 '
                '|| exit 92\n'
                'test "$(stat -c %a "$HOME/.local/share/sia/bin/sia-mcp")" '
                '= 0 || exit 93\n'
                'if [ "$1 $2 $3" = "mcp get sia" ]; then\n'
                '  if [ -e "$MCP_REMOVED" ]; then\n'
                '    echo "No MCP server named sia" >&2; exit 1\n'
                '  fi\n'
                '  echo "sia:"\n'
                '  echo "  Scope: User config (available in all your projects)"\n'
                '  echo "  Status: Connected"\n'
                '  echo "  Type: stdio"\n'
                '  echo "  Command: python3"\n'
                '  echo "  Args: $HOME/.local/share/sia/bin/sia-mcp"\n'
                '  echo "  Environment:"\n'
                '  echo\n'
                '  exit 0\n'
                'fi\n'
                'if [ "$1 $2" = "mcp remove" ]; then\n'
                '  : > "$MCP_REMOVED"; : > "$MCP_MUTATED"; exit 0\n'
                'fi\n'
                'exit 1\n')
            _fake_command(
                fake_bin, "codex",
                'echo "No MCP server named sia" >&2\nexit 1\n')
            _fake_command(fake_bin, "grok", 'echo "[]"\n')
            environment = os.environ.copy()
            environment.update({
                "HOME": home,
                "PATH": fake_bin + os.pathsep + environment["PATH"],
                "DRAIN_WAITING": waiting,
                "ALLOW_DRAIN": allow_drain,
                "MCP_REMOVED": mcp_removed,
                "MCP_MUTATED": mcp_mutated,
            })
            legacy = subprocess.Popen(
                [sys.executable, legacy_mcp, legacy_started, release_legacy],
                env=environment, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True)
            uninstaller = None
            try:
                deadline = time.monotonic() + 30
                while not os.path.exists(legacy_started):
                    if legacy.poll() is not None:
                        stdout, stderr = legacy.communicate()
                        self.fail("legacy MCP exited before drain: "
                                  f"{stdout}\n{stderr}")
                    if time.monotonic() >= deadline:
                        self.fail("legacy MCP did not start")
                    time.sleep(0.01)
                uninstaller = subprocess.Popen(
                    ["bash", os.path.join(REPO, "uninstall.sh")],
                    cwd=REPO, env=environment, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                while not os.path.exists(waiting):
                    if uninstaller.poll() is not None:
                        stdout, stderr = uninstaller.communicate()
                        self.fail("uninstaller did not wait for legacy MCP: "
                                  f"{stdout}\n{stderr}")
                    if time.monotonic() >= deadline:
                        self.fail("uninstaller did not enter legacy drain")
                    time.sleep(0.01)
                self.assertFalse(os.path.exists(mcp_mutated))
                self.assertFalse(os.path.exists(os.path.join(
                    home, ".local/state/sia.lifecycle-removed")))
                self.assertFalse(os.path.exists(os.path.join(
                    home, ".local/state/sia/managed-install/launch-fence.json")))

                _write(release_legacy, "release\n")
                legacy_stdout, legacy_stderr = legacy.communicate(timeout=30)
                self.assertEqual(legacy.returncode, 0,
                                 legacy_stdout + legacy_stderr)
                _write(allow_drain, "continue\n")
                stdout, stderr = uninstaller.communicate(timeout=30)
                self.assertEqual(uninstaller.returncode, 0, stderr)
                self.assertFalse(os.path.exists(mcp_mutated))
                self.assertTrue(os.path.lexists(cli))
                self.assertTrue(os.path.lexists(runtime))
                self.assertFalse(os.path.isfile(os.path.join(
                    home, ".local/state/sia.lifecycle-removed")))
                self.assertFalse(os.path.lexists(os.path.join(
                    home,
                    ".local/state/sia/managed-install/launch-fence.json")))
                self.assertIn("uninstall completed successfully", stdout)
            finally:
                for process in (uninstaller, legacy):
                    if process is not None and process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=30)

    def test_uninstaller_recovers_interrupted_install_publication_receipts(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            runtime = os.path.join(home, ".local/share/sia/bin")
            cli = os.path.join(home, ".local/bin/sia")
            managed = os.path.join(
                home, ".local/state/sia/managed-install")
            journal = os.path.join(managed, "launch-fence.json")
            tombstone = os.path.join(
                home, ".local/state/sia.lifecycle-removed")
            os.makedirs(fake_bin)
            for name in (
                    "sia-brainstem", "sia-brainstem.py", "sia-cli",
                    "sia-ledger", "sia-mcp", "siabench.py", "sialib.py",
                    "siamind.py", "siaqueue.py", "siatakes.py"):
                _write(os.path.join(runtime, name), name + "\n", 0o755)
            _write(cli, "new stable launcher\n", 0o755)
            with open(cli, "rb") as stream:
                cli_digest = hashlib.sha256(stream.read()).hexdigest()
            payload = {
                "schema": "sia-launch-fence-v1",
                "runtime_before_digest": hashlib.sha256(
                    b"prior runtime").hexdigest(),
                "runtime_digest": _runtime_digest(runtime),
                "cli_digest": cli_digest,
                "entries": [],
            }
            _write(journal, json.dumps(
                payload, sort_keys=True, separators=(",", ":")) + "\n",
                0o600)
            _write(tombstone, "removed-by=khephri.sia\n", 0o600)
            _fake_command(fake_bin, "systemctl", ABSENT_USER_UNIT)
            for client in ("claude", "codex"):
                _fake_command(
                    fake_bin, client,
                    'echo "No MCP server named sia" >&2\nexit 1\n')
            _fake_command(fake_bin, "grok", 'echo "[]"\n')
            environment = os.environ.copy()
            environment.update({
                "HOME": home,
                "PATH": fake_bin + os.pathsep + environment["PATH"],
            })
            result = subprocess.run(
                ["bash", os.path.join(REPO, "uninstall.sh")],
                cwd=REPO, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("recovered exact runtime receipt", result.stdout)
            self.assertIn("recovered exact CLI receipt", result.stdout)
            self.assertFalse(os.path.lexists(cli))
            self.assertFalse(os.path.lexists(runtime))
            self.assertFalse(os.path.lexists(journal))
            self.assertEqual(_read_path(tombstone),
                             "removed-by=khephri.sia\n")

    def test_inherited_lifecycle_handoff_preserves_tombstone_and_nesting(self):
        cli = _load("sia_lifecycle_valid", os.path.join(REPO, "bin/sia"))
        library = _load(
            "sialib_lifecycle_valid", os.path.join(REPO, "bin/sialib.py"))
        with tempfile.TemporaryDirectory() as home:
            state = os.path.join(home, ".local/state")
            os.makedirs(state)
            lock = os.path.join(state, "sia.lifecycle.lock")
            tombstone = os.path.join(state, "sia.lifecycle-removed")
            _write(tombstone, "removed-by=khephri.sia\n", 0o600)
            descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                child_environment = os.environ.copy()
                child_environment["SIA_INHERITED_LIFECYCLE_FD"] = str(
                    descriptor)
                child_code = (
                    "import importlib.machinery, importlib.util, sys\n"
                    "loader = importlib.machinery.SourceFileLoader("
                    "'sia_handoff_child', sys.argv[1])\n"
                    "spec = importlib.util.spec_from_loader("
                    "'sia_handoff_child', loader)\n"
                    "module = importlib.util.module_from_spec(spec)\n"
                    "loader.exec_module(module)\n"
                    "with module._runtime_generation_lease(sys.argv[2]):\n"
                    "    print('inherited-exclusive-handoff')\n")
                child = subprocess.run(
                    [sys.executable, "-c", child_code,
                     os.path.join(REPO, "bin/sia"), home],
                    env=child_environment, pass_fds=(descriptor,), text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    check=False)
                self.assertEqual(child.returncode, 0, child.stderr)
                self.assertEqual(
                    child.stdout.strip(), "inherited-exclusive-handoff")
                with mock.patch.dict(
                        os.environ,
                        {"SIA_INHERITED_LIFECYCLE_FD": str(descriptor)}), \
                        mock.patch.object(library, "LIFECYCLE_LOCK", lock), \
                        mock.patch.object(
                            library, "LIFECYCLE_TOMBSTONE", tombstone):
                    with cli._runtime_generation_lease(home):
                        with library._lifecycle_reader():
                            with library._lifecycle_reader():
                                self.assertTrue(os.path.isfile(tombstone))
                    with self.assertRaisesRegex(RuntimeError, "first-light"):
                        with cli._runtime_generation_lease(home):
                            raise RuntimeError("first-light crash")
                self.assertEqual(
                    _read_path(tombstone), "removed-by=khephri.sia\n")
                probe = os.open(lock, os.O_RDWR)
                try:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(probe, fcntl.LOCK_SH | fcntl.LOCK_NB)
                finally:
                    os.close(probe)
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

    def test_inherited_lifecycle_handoff_rejects_spoof_and_shared_lock(self):
        cli = _load("sia_lifecycle_spoof", os.path.join(REPO, "bin/sia"))
        library = _load(
            "sialib_lifecycle_spoof", os.path.join(REPO, "bin/sialib.py"))
        with tempfile.TemporaryDirectory() as home:
            state = os.path.join(home, ".local/state")
            os.makedirs(state)
            lock = os.path.join(state, "sia.lifecycle.lock")
            owner = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
            spoof = os.open(lock, os.O_RDWR)
            try:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with mock.patch.dict(
                        os.environ,
                        {"SIA_INHERITED_LIFECYCLE_FD": str(spoof)}), \
                        mock.patch.object(library, "LIFECYCLE_LOCK", lock):
                    with self.assertRaisesRegex(
                            RuntimeError, "does not own the lease"):
                        cli._validated_inherited_lifecycle_fd(lock)
                    with self.assertRaisesRegex(
                            RuntimeError, "does not own the lease"):
                        library._validated_inherited_lifecycle_fd()

                fcntl.flock(owner, fcntl.LOCK_UN)
                fcntl.flock(spoof, fcntl.LOCK_SH | fcntl.LOCK_NB)
                with mock.patch.dict(
                        os.environ,
                        {"SIA_INHERITED_LIFECYCLE_FD": str(spoof)}), \
                        mock.patch.object(library, "LIFECYCLE_LOCK", lock):
                    with self.assertRaisesRegex(
                            RuntimeError, "not exclusively held"):
                        cli._validated_inherited_lifecycle_fd(lock)
                    with self.assertRaisesRegex(
                            RuntimeError, "not exclusively held"):
                        library._validated_inherited_lifecycle_fd()
                shared_probe = os.open(lock, os.O_RDWR)
                try:
                    fcntl.flock(
                        shared_probe, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    fcntl.flock(shared_probe, fcntl.LOCK_UN)
                finally:
                    os.close(shared_probe)

                fcntl.flock(spoof, fcntl.LOCK_UN)
                with mock.patch.dict(
                        os.environ,
                        {"SIA_INHERITED_LIFECYCLE_FD": str(spoof)}):
                    with self.assertRaisesRegex(
                            RuntimeError, "no conflicting lease"):
                        cli._validated_inherited_lifecycle_fd(lock)
            finally:
                fcntl.flock(owner, fcntl.LOCK_UN)
                os.close(spoof)
                os.close(owner)

    def test_stable_launcher_holds_generation_lease_across_exec(self):
        with tempfile.TemporaryDirectory() as home:
            runtime = os.path.join(home, ".local/share/sia/bin")
            launcher = os.path.join(home, ".local/bin/sia")
            target = os.path.join(runtime, "sia-cli")
            _generate_stable_launcher(launcher)
            _write(
                target,
                "import time\nprint('target-ready', flush=True)\n"
                "time.sleep(2)\n",
                0o644)
            environment = os.environ.copy()
            environment["HOME"] = home
            process = subprocess.Popen(
                [launcher], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                self.assertEqual(process.stdout.readline().strip(),
                                 "target-ready")
                lock = os.path.join(home, ".local/state/sia.lifecycle.lock")
                probe = os.open(lock, os.O_RDWR)
                try:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(probe)
            finally:
                process.terminate()
                process.communicate(timeout=2)

            _write(target, _read("bin/sia"), 0o644)
            for name in ("sialib.py", "siamind.py", "siatakes.py",
                         "siaqueue.py"):
                _write(os.path.join(runtime, name), _read("bin/" + name),
                       0o644)
            result = subprocess.run(
                [launcher, "status"], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("SIA has no status yet", result.stdout)
            self.assertNotIn("stable-launcher handoff", result.stderr)

            tombstone = os.path.join(
                home, ".local/state/sia.lifecycle-removed")
            _write(tombstone, "removed-by=khephri.sia\n", 0o600)
            removed = subprocess.run(
                [launcher, "status"], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(removed.returncode, 0)
            self.assertIn("runtime was removed", removed.stderr)

    def test_stable_launcher_handoff_rejects_unlocked_and_wrong_target_fds(self):
        cli = _load("sia_launcher_spoof", os.path.join(REPO, "bin/sia"))
        with tempfile.TemporaryDirectory() as root:
            lock = os.path.join(root, "lifecycle.lock")
            wrong = os.path.join(root, "wrong-target")
            _write(wrong, "wrong\n", 0o600)
            lifecycle_fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
            target_fd = os.open(os.path.join(REPO, "bin/sia"), os.O_RDONLY)
            wrong_fd = os.open(wrong, os.O_RDONLY)
            base = {
                "SIA_LAUNCHER_ABI": "sia-launch-v1",
                "SIA_LAUNCHER_LIFECYCLE_FD": str(lifecycle_fd),
                "SIA_LAUNCHER_TARGET_FD": str(target_fd),
                "SIA_LAUNCHER_TARGET_PATH": os.path.join(REPO, "bin/sia"),
            }
            try:
                with mock.patch.dict(os.environ, base):
                    with self.assertRaisesRegex(RuntimeError,
                                                "holds no shared lease"):
                        cli._validated_launcher_lifecycle_fd(
                            lock, os.path.join(REPO, "bin/sia"))
                fcntl.flock(lifecycle_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                wrong_environment = dict(base)
                wrong_environment["SIA_LAUNCHER_TARGET_FD"] = str(wrong_fd)
                with mock.patch.dict(os.environ, wrong_environment):
                    with self.assertRaisesRegex(RuntimeError,
                                                "changed generation"):
                        cli._validated_launcher_lifecycle_fd(
                            lock, os.path.join(REPO, "bin/sia"))
                with mock.patch.dict(os.environ, base):
                    self.assertEqual(
                        cli._validated_launcher_lifecycle_fd(
                            lock, os.path.join(REPO, "bin/sia")),
                        lifecycle_fd)
            finally:
                fcntl.flock(lifecycle_fd, fcntl.LOCK_UN)
                os.close(wrong_fd)
                os.close(target_fd)
                os.close(lifecycle_fd)

    def test_new_sialib_rejects_loaded_old_installed_launchers(self):
        with tempfile.TemporaryDirectory() as home:
            runtime = os.path.join(home, ".local/share/sia/bin")
            for name in ("sialib.py", "siamind.py", "siatakes.py",
                         "siaqueue.py"):
                _write(os.path.join(runtime, name), _read("bin/" + name),
                       0o644)
            environment = os.environ.copy()
            environment["HOME"] = home
            for launcher in (
                    os.path.join(home, ".local/bin/sia"),
                    os.path.join(runtime, "sia-brainstem")):
                with self.subTest(launcher=launcher):
                    _write(
                        launcher,
                        "import sys\n"
                        f"sys.path.insert(0, {runtime!r})\n"
                        "import sialib\n",
                        0o755)
                    result = subprocess.run(
                        [sys.executable, launcher], env=environment, text=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        check=False)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("did not pin its runtime", result.stderr)

    def test_uninstaller_owner_lock_open_failure_is_aggregated(self):
        uninstaller = _read("uninstall.sh")
        body = uninstaller.split("acquire_owner_lock() {", 1)[1].split(
            "\n}\n\nfor dependency", 1)[0]
        function = "acquire_owner_lock() {" + body + "\n}\n"
        with tempfile.TemporaryDirectory() as root:
            script = function + r'''
set -u
failed() { printf 'failed: %s\n' "$1" >&2; }
LOCK_FD=""
if acquire_owner_lock "$WORK/missing/owner.lock" LOCK_FD corpus; then
  exit 9
fi
printf 'failure aggregated\n'
'''
            environment = os.environ.copy()
            environment["WORK"] = root
            result = subprocess.run(
                ["bash", "-c", script], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("failure aggregated", result.stdout)
            self.assertIn("failed: open corpus lock", result.stderr)
            self.assertNotIn("unbound variable", result.stderr)

    def test_managed_root_symlinks_are_refused_before_external_mutation(self):
        for relative in (".config/hypr", ".claude",
                         ".local/state/sia/managed-install",
                         ".local/state/sia/managed-mcp",
                         ".local/share/sia/.gbrain/schema-packs",
                         ".local/state/sia/model-manifest-backups"):
            with self.subTest(relative=relative), \
                    tempfile.TemporaryDirectory() as root:
                home = os.path.join(root, "home")
                outside = os.path.join(root, "outside")
                os.makedirs(outside)
                sentinel = os.path.join(outside, "sentinel")
                _write(sentinel, "unchanged\n")
                target = os.path.join(home, relative)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                os.symlink(outside, target)
                environment = os.environ.copy()
                environment["HOME"] = home
                scripts = ("install.sh", "uninstall.sh") \
                    if relative in (".config/hypr", ".claude",
                                    ".local/state/sia/managed-install",
                                    ".local/state/sia/managed-mcp") \
                    else ("install.sh",)
                for script in scripts:
                    result = subprocess.run(
                        ["bash", os.path.join(REPO, script)],
                        cwd=REPO, env=environment, text=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        check=False)
                    self.assertNotEqual(result.returncode, 0, script)
                    self.assertEqual(_read_path(sentinel), "unchanged\n")

    def test_installer_refuses_nonempty_unowned_corpus(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            os.makedirs(fake_bin)
            _fake_command(fake_bin, "systemctl", ABSENT_USER_UNIT)
            foreign = os.path.join(
                home, ".local/share/sia/corpus/foreign.txt")
            _write(foreign, "operator data\n")
            environment = os.environ.copy()
            environment["HOME"] = home
            environment["PATH"] = fake_bin + os.pathsep + environment["PATH"]
            result = subprocess.run(
                ["bash", os.path.join(REPO, "install.sh")],
                cwd=REPO, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing nonempty corpus", result.stderr)
            self.assertEqual(_read_path(foreign), "operator data\n")

    def test_failure_cleanup_stops_mutated_runtime_without_restart(self):
        installer = _read("install.sh")
        body = installer.split("sia_install_cleanup() {", 1)[1].split(
            "\n}\ntrap sia_install_cleanup EXIT", 1)[0]
        function = (_bounded_commands_shell(installer) +
                    "\nsia_install_cleanup() {" + body + "\n}\n")
        with tempfile.TemporaryDirectory() as root:
            trace = os.path.join(root, "trace")
            script = function + r'''
run_with_deadline() { shift; "$@"; }
systemctl() {
  printf '%s\n' "$*" >> "$TRACE"
  return 0
}
SIA_INSTALL_TMP="$WORK/install-tmp"
SIA_OLLAMA_STAGE=""
SIA_PLUGIN_STAGE=""
SIA_RUNTIME_STAGE=""
SIA_BUN_STAGE=""
SIA_GBRAIN_STAGE=""
SIA_INSTALL_MUTATED=1
SIA_RESTORE_LIFECYCLE_TOMBSTONE=0
SIA_LIFECYCLE_TOMBSTONE_CLEARED=0
SIA_BRAINSTEM_FINAL_UNMASKED=0
SIA_BRAINSTEM_RUNTIME_MASKED=0
SIA_KEEP_BRAINSTEM_RUNTIME_MASK=0
SIA_BRAINSTEM_WAS_ACTIVE=1
SIA_BRAINSTEM_WAS_ENABLED=1
SIA_OLLAMA_SERVICE_MUTATED=1
SIA_OLLAMA_WAS_ACTIVE=0
SIA_OLLAMA_WAS_ENABLED=0
mkdir -p "$SIA_INSTALL_TMP"
false
sia_install_cleanup
'''
            environment = os.environ.copy()
            environment.update({"TRACE": trace, "WORK": root})
            result = subprocess.run(
                ["bash", "-c", script], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(result.returncode, 0)
            calls = _read_path(trace)
            self.assertIn("--user disable --now sia-brainstem.service", calls)
            self.assertNotIn("--user start sia-brainstem.service", calls)
            self.assertIn("--user disable --now ollama.service", calls)
            self.assertIn("install failed after mutation", result.stderr)

    def test_final_activation_failure_rearms_mask_before_disable(self):
        installer = _read("install.sh")
        body = installer.split("sia_install_cleanup() {", 1)[1].split(
            "\n}\ntrap sia_install_cleanup EXIT", 1)[0]
        function = (_bounded_commands_shell(installer) +
                    "\nsia_install_cleanup() {" + body + "\n}\n")
        with tempfile.TemporaryDirectory() as root:
            trace = os.path.join(root, "trace")
            script = function + r'''
run_with_deadline() { shift; "$@"; }
install_brainstem_runtime_mask() {
  echo mask >> "$TRACE"
  SIA_BRAINSTEM_RUNTIME_MASKED=1
}
verify_install_brainstem_runtime_mask() { echo verify >> "$TRACE"; }
remove_install_brainstem_runtime_mask() {
  echo unmask >> "$TRACE"
  SIA_BRAINSTEM_RUNTIME_MASKED=0
}
systemctl() { printf 'systemctl %s\n' "$*" >> "$TRACE"; }
SIA_INSTALL_TMP="$WORK/install-tmp"
mkdir -p "$SIA_INSTALL_TMP"
SIA_OLLAMA_STAGE="" SIA_PLUGIN_STAGE="" SIA_RUNTIME_STAGE=""
SIA_BUN_STAGE="" SIA_GBRAIN_STAGE=""
SIA_INSTALL_MUTATED=1 SIA_OLLAMA_SERVICE_MUTATED=0
SIA_RESTORE_LIFECYCLE_TOMBSTONE=0 SIA_LIFECYCLE_TOMBSTONE_CLEARED=0
SIA_BRAINSTEM_FINAL_UNMASKED=1 SIA_BRAINSTEM_RUNTIME_MASKED=0
SIA_KEEP_BRAINSTEM_RUNTIME_MASK=0
SIA_GBRAIN_LOCK_FD="" SIA_CORPUS_LOCK_FD=""
SIA_BRAINSTEM_LOCK_FD="" SIA_INSTALL_LOCK_FD=""
false
sia_install_cleanup
'''
            environment = os.environ.copy()
            environment.update({"TRACE": trace, "WORK": root})
            result = subprocess.run(
                ["bash", "-c", script], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(result.returncode, 0)
            calls = _read_path(trace).splitlines()
            mask = calls.index("mask")
            disable = calls.index(
                "systemctl --user disable --now sia-brainstem.service")
            self.assertLess(mask, disable)
            self.assertNotIn("unmask", calls)
            self.assertIn("re-established sia-brainstem runtime mask",
                          result.stderr)
            self.assertIn("disabled and stopped", result.stderr)
            self.assertIn("remains runtime-masked", result.stderr)

    def test_ollama_runtime_and_model_store_are_fail_closed(self):
        installer = _read("install.sh")
        flattened_installer = re.sub(r"\\\n\s*", " ", installer)
        self.assertIn("https://github.com/ollama/ollama/releases/tag/v0.33.2",
                      installer)
        self.assertIn("https://registry.ollama.ai/v2/library/"
                      "nomic-embed-text/manifests/v1.5", installer)
        self.assertIn("OLLAMA_VERSION=0.33.2", installer)
        self.assertIn("SIA_ALLOW_UNPINNED_OLLAMA", installer)
        self.assertIn("effective_ollama_models_dir", installer)
        self.assertIn('open(f"/proc/{pid}/environ", "rb")', installer)
        self.assertIn('environment.get(b"OLLAMA_MODELS"', installer)
        self.assertIn('environment.get(b"HOME"', installer)
        self.assertIn('pwd.getpwuid(os.stat(f"/proc/{pid}").st_uid).pw_dir',
                      installer)
        model_dir_function = installer.split(
            "effective_ollama_models_dir()", 1)[1].split(
                "verify_ollama_model_store()", 1)[0]
        self.assertIn('python3 - "$daemon_pid"', model_dir_function)
        self.assertNotIn('python3 - "$daemon_pid" "$HOME"',
                         model_dir_function)
        self.assertIn("verify_ollama_model_store", installer)
        self.assertNotIn("rollback_model_manifest() {", installer)
        self.assertIn("rejected v1.5 manifest preserved", installer)
        self.assertIn("rejected compatibility alias preserved", installer)
        self.assertNotIn(
            'rollback_model_manifest "$NOMIC_MANIFEST"', installer)
        self.assertNotIn(
            'rollback_model_manifest "$NOMIC_ALIAS_MANIFEST"', installer)
        self.assertIn("ollama_runtime_receipt_valid", installer)
        self.assertIn("binary_sha256=", installer)
        self.assertIn('OLLAMA_RECEIPT_EXPECTED="managed-by=khephri.sia',
                      installer)
        replacement_gate = installer.split(
            "if ! ollama_runtime_receipt_valid; then", 1)[1].split(
                "  download_verified", 1)[0]
        self.assertIn('[ "${SIA_REPLACE_OLLAMA_RUNTIME:-0}" != "1" ]',
                      replacement_gate)
        self.assertNotIn("grep -q '^binary_sha256=", replacement_gate)
        self.assertIn('sha256sum "/proc/$OLLAMA_DAEMON_PID/exe"', installer)
        self.assertIn("is not running SIA's verified Ollama binary", installer)
        self.assertIn("blob size mismatch", installer)
        self.assertIn("blob digest mismatch", installer)
        self.assertIn("MAX_MODEL_MANIFEST_BYTES = 1_048_576", installer)
        self.assertIn("read_stable_bounded_regular", installer)
        self.assertIn("exceeds its byte ceiling", installer)
        self.assertIn("changed while reading", installer)
        self.assertIn("NOMIC_MANIFEST_SHA256="
                      "0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f",
                      installer)
        self.assertIn("NOMIC_MODEL=nomic-embed-text:v1.5", installer)
        self.assertIn("NOMIC_COMPAT_ALIAS=nomic-embed-text:latest", installer)
        self.assertRegex(
            flattened_installer,
            r'run_with_deadline 1800 "\$OLLAMA_BIN" cp\s+'
            r'"\$NOMIC_MODEL" "\$NOMIC_COMPAT_ALIAS"')
        self.assertIn("SIA_REPLACE_NOMIC_LATEST", installer)
        self.assertIn("--embedding-model ollama:nomic-embed-text:v1.5",
                      installer)
        self.assertNotRegex(installer,
                            r'pull\s+(?:"?nomic-embed-text"?)(?:\s|$)')

    def test_ollama_runtime_receipt_binds_owner_and_current_binary(self):
        installer = _read("install.sh")
        metadata_function = _owned_metadata_shell(installer)
        version_body = installer.split("ollama_client_version() {", 1)[1].split(
            "\n}\n\neffective_ollama_models_dir", 1)[0]
        version_function = "ollama_client_version() {" + version_body + "\n}\n"
        body = installer.split("ollama_runtime_receipt_valid() {", 1)[1].split(
            "\n}\n\ninspect_user_unit ollama.service", 1)[0]
        function = "ollama_runtime_receipt_valid() {" + body + "\n}\n"
        with tempfile.TemporaryDirectory() as root:
            binary = os.path.join(root, "bin/ollama")
            receipt = os.path.join(root, ".sia-release")
            sentinel = os.path.join(root, "executed")
            _write(binary, "#!/bin/sh\n"
                   ': > "${SENTINEL:?}"\n'
                   "printf 'Warning: client version is %s\\n' "
                   '"$FAKE_VERSION"\n', 0o755)
            with open(binary, "rb") as stream:
                binary_digest = hashlib.sha256(stream.read()).hexdigest()
            expected_prefix = (
                "managed-by=khephri.sia\n"
                "version=0.33.2\n"
                "asset=ollama-linux-amd64.tar.zst\n"
                "sha256=" + "0" * 64)
            script = metadata_function + version_function + function + r'''
ollama_runtime_receipt_valid
'''
            environment = os.environ.copy()
            environment.update({
                "OLLAMA_BIN": binary,
                "OLLAMA_RECEIPT": receipt,
                "OLLAMA_VERSION": "0.33.2",
                "OLLAMA_RECEIPT_EXPECTED": expected_prefix,
                "SENTINEL": sentinel,
                "FAKE_VERSION": "0.33.2",
            })

            _write(receipt, "managed-by=khephri.sia\n")
            invalid = subprocess.run(
                ["bash", "-c", script], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertFalse(os.path.exists(sentinel))

            _write(receipt, expected_prefix +
                   f"\nbinary_sha256={binary_digest}\n")
            valid = subprocess.run(
                ["bash", "-c", script], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertTrue(os.path.exists(sentinel))
            os.unlink(sentinel)

            _write(receipt, expected_prefix.split("\n", 1)[1] +
                   f"\nbinary_sha256={binary_digest}\n")
            unmarked = subprocess.run(
                ["bash", "-c", script], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(unmarked.returncode, 0)
            self.assertFalse(os.path.exists(sentinel))

            _write(receipt, expected_prefix +
                   f"\nbinary_sha256={binary_digest}\n")
            _write(binary, "locally modified runtime\n", 0o755)
            modified = subprocess.run(
                ["bash", "-c", script], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(modified.returncode, 0)
            self.assertFalse(os.path.exists(sentinel))

    def test_toolchain_receipts_are_validated_before_execution(self):
        installer = _read("install.sh")
        metadata_function = _owned_metadata_shell(installer)
        cases = (
            (
                "bun",
                "bun_runtime_receipt_valid",
                "\n}\nif ! bun_runtime_receipt_valid",
                {
                    "BUN_VERSION": "1.2.3",
                    "BUN_ASSET": "bun-linux-x64.zip",
                    "BUN_SHA256": "a" * 64,
                },
                "managed-by=khephri.sia\nversion=1.2.3\n"
                "asset=bun-linux-x64.zip\nsha256=" + "a" * 64,
                "1.2.3",
            ),
            (
                "gbrain",
                "gbrain_runtime_receipt_valid",
                "\n}\nif ! gbrain_runtime_receipt_valid",
                {
                    "PIN": "b" * 40,
                    "PIN_VERSION": "4.5.6",
                    "PIN_LOCK_SHA256": "c" * 64,
                },
                "managed-by=khephri.sia\ncommit=" + "b" * 40 +
                "\nversion=4.5.6\nbun_lock_sha256=" + "c" * 64,
                "gbrain 4.5.6",
            ),
        )
        for label, function_name, end_marker, variables, prefix, version in cases:
            with self.subTest(tool=label), tempfile.TemporaryDirectory() as root:
                body = installer.split(function_name + "() {", 1)[1].split(
                    end_marker, 1)[0]
                function = function_name + "() {" + body + "\n}\n"
                binary = os.path.join(root, "bin", label)
                receipt = os.path.join(root, ".sia-release")
                sentinel = os.path.join(root, "executed")
                _write(binary, "#!/bin/sh\n"
                       ': > "${SENTINEL:?}"\n'
                       "printf '%s\\n' \"$FAKE_VERSION\"\n", 0o755)
                with open(binary, "rb") as stream:
                    digest = hashlib.sha256(stream.read()).hexdigest()
                environment = os.environ.copy()
                environment.update(variables)
                environment.update({
                    function_name.split("_runtime", 1)[0].upper() + "_BIN":
                        binary,
                    function_name.split("_runtime", 1)[0].upper() +
                    "_RECEIPT": receipt,
                    "SENTINEL": sentinel,
                    "FAKE_VERSION": version,
                })
                script = (metadata_function + function + "\n" +
                          function_name + "\n")

                _write(receipt, "managed-by=khephri.sia\n")
                invalid = subprocess.run(
                    ["bash", "-c", script], env=environment, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                self.assertNotEqual(invalid.returncode, 0)
                self.assertFalse(os.path.exists(sentinel))

                _write(receipt, prefix + f"\nbinary_sha256={digest}\n")
                valid = subprocess.run(
                    ["bash", "-c", script], env=environment, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                self.assertEqual(valid.returncode, 0, valid.stderr)
                self.assertTrue(os.path.exists(sentinel))

        bun_gate = installer.split(
            "if ! bun_runtime_receipt_valid; then", 1)[1].split(
                "  download_verified", 1)[0]
        gbrain_gate = installer.split(
            "if ! gbrain_runtime_receipt_valid; then", 1)[1].split(
                "  GBRAIN_SOURCE=", 1)[0]
        for gate in (bun_gate, gbrain_gate):
            self.assertIn("SIA_REPLACE_TOOLCHAIN", gate)
            self.assertNotIn("grep -qx 'managed-by=khephri.sia'", gate)

    def test_standalone_plugin_snapshot_is_allowlisted_and_atomic(self):
        installer = _read("install.sh")
        desktop = installer.split('step "8/9 desktop', 1)[1].split(
            'step "9/9 agents', 1)[0]
        for relative in (
                "manifest.json", "preview.png", "Panel.qml", "Cockpit.qml", "Model.js",
                "README.md", "LICENSE", "SECURITY.md", "CHANGELOG.md",
                "GBRAIN_PIN", "config.example.json", "install.sh",
                "uninstall.sh", "assets", "bin", "docs", "schema-pack",
                "skill", "systemd"):
            self.assertIn(relative, desktop)
        self.assertIn(".khephri.sia.stage.XXXXXX", desktop)
        self.assertIn("atomic_install_tree", desktop)
        self.assertNotIn("RENAME_EXCHANGE", installer)
        self.assertIn("rename_noreplace(target_name, archive)", installer)
        self.assertIn("SIA_REPLACE_PLUGIN", desktop)
        self.assertIn("previous plugin tree retained", desktop)
        self.assertIn("__pycache__", desktop)
        self.assertNotIn('"$REPO/.git"', desktop)
        self.assertNotIn('"$REPO/tests"', desktop)
        self.assertNotIn('"$REPO/.local"', desktop)
        self.assertIn("omarchy plugin enable khephri.sia", desktop)
        self.assertNotIn("omarchy plugin enable khephri.sia 2>/dev/null || true",
                         desktop)
        self.assertIn('[ "$SIA_ORIGINAL_REPO" != "$PLUGDIR" ]', desktop)
        self.assertNotIn('[ "$REPO" != "$PLUGDIR" ]', desktop)
        self.assertIn('SIA_ORIGINAL_REPO="$REPO"', installer)
        self.assertLess(
            installer.index("release_source_frontdoor snapshot"),
            installer.index("prepare_and_lock_install\n"))
        self.assertIn('release_source_frontdoor verify "$SIA_ORIGINAL_REPO"',
                      installer)

    def test_release_source_snapshot_is_bounded_and_churn_safe(self):
        installer = _read("install.sh")
        body = installer.split("release_source_frontdoor() {", 1)[1].split(
            "\n}\n\nSIA_RELEASE_FILES", 1)[0]
        function = "release_source_frontdoor() {" + body + "\n}\n"
        self.assertIn("MAX_SOURCE_FILE_BYTES = 16_777_216", function)
        self.assertIn("MAX_SOURCE_TOTAL_BYTES = 67_108_864", function)
        self.assertIn("open_absolute_directory", function)
        self.assertIn("dir_fd=parent_fd", function)
        self.assertIn("source_tree.require_unchanged()", function)
        self.assertNotIn("__pycache__", installer.split(
            "SIA_RELEASE_FILES=(", 1)[1].split("\n)", 1)[0])
        self.assertIn('chmod -R u+w -- "$SIA_INSTALL_TMP"', installer)

        with tempfile.TemporaryDirectory() as root:
            source = os.path.join(root, "source")
            snapshot = os.path.join(root, "snapshot")
            _write(os.path.join(source, "one"), "first\n")
            _write(os.path.join(source, "nested/two"), "second\n")
            _write(os.path.join(source, "unlisted"), "ignored\n")
            command = (function +
                       '\nrelease_source_frontdoor snapshot "$1" "$2" '
                       'one nested/two')
            captured = subprocess.run(
                ["bash", "-c", command, "snapshot-test", source, snapshot],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False)
            self.assertEqual(captured.returncode, 0, captured.stderr)
            self.assertEqual(_read_path(os.path.join(snapshot, "one")),
                             "first\n")
            self.assertFalse(os.path.lexists(
                os.path.join(snapshot, "unlisted")))

            _write(os.path.join(source, "one"), "concurrent update\n")
            verified = subprocess.run(
                ["bash", "-c", function +
                 '\nrelease_source_frontdoor verify "$1" "$2" '
                 'one nested/two', "snapshot-test", source, snapshot],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False)
            self.assertNotEqual(verified.returncode, 0)
            cleanup = subprocess.run(
                ["bash", "-c", 'chmod -R u+w -- "$1" && rm -rf -- "$1"',
                 "snapshot-cleanup", snapshot], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(cleanup.returncode, 0, cleanup.stderr)
            self.assertFalse(os.path.lexists(snapshot))

        with tempfile.TemporaryDirectory() as root:
            real_source = os.path.join(root, "real-source")
            linked_source = os.path.join(root, "linked-source")
            snapshot = os.path.join(root, "snapshot")
            _write(os.path.join(real_source, "one"), "source\n")
            os.symlink(real_source, linked_source)
            linked = subprocess.run(
                ["bash", "-c", function +
                 '\nrelease_source_frontdoor snapshot "$1" "$2" one',
                 "snapshot-test", linked_source, snapshot], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(linked.returncode, 0)

            os.unlink(linked_source)
            with open(os.path.join(real_source, "one"), "wb") as stream:
                stream.truncate(16_777_217)
            oversized = subprocess.run(
                ["bash", "-c", function +
                 '\nrelease_source_frontdoor snapshot "$1" "$2" one',
                 "snapshot-test", real_source, snapshot], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(oversized.returncode, 0)

        python_source = installer.split(
            "release_source_frontdoor() {\n"
            "  python3 - \"$@\" <<'PY'\n", 1)[1].split("\nPY\n}", 1)[0]
        with tempfile.TemporaryDirectory() as root:
            source = os.path.join(root, "source")
            snapshot = os.path.join(root, "snapshot")
            replacement = os.path.join(root, "replacement")
            _write(os.path.join(source, "one"), "stable bytes\n")
            _write(replacement, "stable bytes\n")
            real_stat = os.stat
            inspections = 0

            def replacing_stat(path, *args, **kwargs):
                nonlocal inspections
                if path == "one" and kwargs.get("dir_fd") is not None:
                    inspections += 1
                    if inspections == 3:
                        os.replace(replacement, os.path.join(source, "one"))
                return real_stat(path, *args, **kwargs)

            with mock.patch.object(sys, "argv", [
                    "release-source", "snapshot", source, snapshot, "one"]), \
                    mock.patch.object(os, "stat", replacing_stat):
                with self.assertRaises(SystemExit) as stopped:
                    exec(compile(python_source, "release-source", "exec"), {})
            self.assertNotEqual(stopped.exception.code, 0)
            if os.path.isdir(snapshot):
                subprocess.run(["chmod", "-R", "u+w", snapshot], check=True)

    def test_gbrain_config_update_is_bounded_nofollow_and_strict(self):
        installer = _read("install.sh")
        marker = ('python3 - "$GBRAIN_CONFIG_PATH" '
                  '"$GBRAIN_CONFIG_STAGE" <<\'PY\'\n')
        program = installer.split(marker, 1)[1].split("\nPY\n", 1)[0]
        self.assertIn("O_NOFOLLOW", program)
        self.assertIn("MAX_BYTES = 1_048_576", program)
        self.assertIn("generation(before) != generation(after)", program)
        self.assertIn("object_pairs_hook=unique_object", program)
        self.assertIn("allow_nan=False", program)
        block = installer.split("GBRAIN_CONFIG_EXPECTED=", 1)[1].split(
            "if ! GBRAIN_SELF_UPGRADE_MODE=", 1)[0]
        self.assertIn("owned_metadata generation", block)
        self.assertIn("owned_file_cas publish", block)
        self.assertNotIn("os.replace", program)

        with tempfile.TemporaryDirectory() as root:
            config = os.path.join(root, "config.json")
            stage = os.path.join(root, "stage")
            _write(config, '{"self_upgrade":{"mode":"auto"},"kept":1}\n',
                   0o600)
            _write(stage, "", 0o600)
            prepared = subprocess.run(
                [sys.executable, "-c", program, config, stage], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            self.assertEqual(prepared.stdout.strip(), "publish")
            value = json.loads(_read_path(stage))
            self.assertEqual(value["self_upgrade"]["mode"], "off")
            self.assertEqual(value["kept"], 1)
            self.assertEqual(os.stat(stage).st_mode & 0o777, 0o600)
            self.assertEqual(
                json.loads(_read_path(config))["self_upgrade"]["mode"],
                "auto")

            _write(config, '{"self_upgrade":{"mode":"off"}}\n', 0o600)
            _write(stage, "", 0o600)
            unchanged = subprocess.run(
                [sys.executable, "-c", program, config, stage], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(unchanged.returncode, 0, unchanged.stderr)
            self.assertEqual(unchanged.stdout.strip(), "unchanged")

            _write(config, '{"duplicate":1,"duplicate":2}\n', 0o600)
            _write(stage, "", 0o600)
            duplicate = subprocess.run(
                [sys.executable, "-c", program, config, stage], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("duplicate gbrain config key", duplicate.stderr)

            outside = os.path.join(root, "outside.json")
            _write(outside, '{"self_upgrade":{"mode":"auto"}}\n', 0o600)
            os.unlink(config)
            os.symlink(outside, config)
            _write(stage, "", 0o600)
            linked = subprocess.run(
                [sys.executable, "-c", program, config, stage], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(linked.returncode, 0)
            self.assertEqual(
                json.loads(_read_path(outside))["self_upgrade"]["mode"],
                "auto")

    def test_corpus_bootstrap_is_crash_resumable_and_no_clobber(self):
        installer = _read("install.sh")
        functions = ("durable_fixed_metadata_stage() {" + installer.split(
            "durable_fixed_metadata_stage() {", 1)[1].split(
                "\n}\n\nruntime_tree_digest()", 1)[0] + "\n}\n")
        tree = ("owned_tree_cas() {" + installer.split(
            "owned_tree_cas() {", 1)[1].split(
                "\n}\n\nowned_tree_generation()", 1)[0] +
                '\n}\nowned_tree_generation() { '
                'owned_tree_cas generation "$1"; }\n')
        block = ('step "4/9' + installer.split(
            'step "4/9', 1)[1].split('\nstep "5/9', 1)[0] + "\n")
        prefix = (_owned_metadata_shell(installer) + tree + functions +
                  "\nstep() { :; }\n")

        def run(home, selected_block=block, selected_functions=None,
                extra_environment=None):
            share = os.path.join(home, "share")
            state = os.path.join(home, "state")
            managed = os.path.join(state, "managed-install")
            os.makedirs(share, exist_ok=True)
            os.makedirs(managed, exist_ok=True)
            active_prefix = (_owned_metadata_shell(installer) + tree +
                             (selected_functions
                              if selected_functions is not None else functions) +
                             "\nstep() { :; }\n")
            variables = f'''
SHARE={shlex.quote(share)}
STATE={shlex.quote(state)}
MANAGED_DIR={shlex.quote(managed)}
REPO={shlex.quote(REPO)}
CORPUS_RECEIPT="$MANAGED_DIR/corpus"
CORPUS_BOOTSTRAP_INTENT="$MANAGED_DIR/corpus-bootstrap"
CORPUS_ADOPTION_INTENT="$MANAGED_DIR/corpus-adoption"
SIA_CORPUS_NEEDS_RECEIPT=0
SIA_CORPUS_BOOTSTRAP_NEEDED=0
SIA_CORPUS_ADOPTION_NEEDED=0
SIA_INSTALL_LOCK_FD=installer-test
SIA_CORPUS_LOCK_FD=corpus-test
SIA_CORPUS_RECEIPT_LOCKS_HELD=1
preflight_corpus locked
'''
            environment = os.environ.copy()
            if extra_environment:
                environment.update(extra_environment)
            return subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + active_prefix +
                 variables + selected_block, "corpus-bootstrap-test"],
                env=environment, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False, timeout=30)

        with tempfile.TemporaryDirectory() as home:
            installed = run(home)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            corpus = os.path.join(home, "share", "corpus")
            self.assertEqual(
                _read_path(os.path.join(corpus, "README.md")),
                "# SIA corpus — this machine's memory\n")
            self.assertEqual(subprocess.run(
                ["git", "-C", corpus, "show", "HEAD:README.md"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False).stdout,
                "# SIA corpus — this machine's memory\n")
            self.assertEqual(run(home).returncode, 0)

        boundaries = (
            "# Durable bootstrap boundary: target directory creation is replayable.",
            "# Durable bootstrap boundary: hardened git initialization is replayable.",
            "# Durable bootstrap boundary: the exact narrow index update is replayable.",
            "# Durable bootstrap boundary: the exact genesis commit is replayable.",
            "# Durable bootstrap/adoption boundary: receipt publication is replayable.",
        )
        for boundary in boundaries:
            with self.subTest(boundary=boundary), \
                    tempfile.TemporaryDirectory() as home:
                interrupted = block.replace(boundary, "false", 1)
                failed = run(home, interrupted)
                self.assertNotEqual(failed.returncode, 0)
                resumed = run(home)
                self.assertEqual(resumed.returncode, 0, resumed.stderr)
                managed = os.path.join(home, "state", "managed-install")
                self.assertTrue(os.path.isfile(os.path.join(managed, "corpus")))
                self.assertFalse(os.path.lexists(
                    os.path.join(managed, "corpus-bootstrap")))
                self.assertFalse(any(
                    name.endswith(".stage") for name in os.listdir(managed)))

        intent_boundary = (
            "  # The durable intent precedes off-path construction.")
        self.assertIn(intent_boundary, block)
        with tempfile.TemporaryDirectory() as home:
            interrupted = block.replace(
                intent_boundary, "  false\n" + intent_boundary, 1)
            failed = run(home, interrupted)
            self.assertNotEqual(failed.returncode, 0)
            corpus = os.path.join(home, "share", "corpus")
            os.mkdir(corpus, 0o700)
            foreign = os.stat(corpus)

            refused = run(home)
            self.assertNotEqual(refused.returncode, 0)
            current = os.stat(corpus)
            self.assertEqual(
                (current.st_dev, current.st_ino),
                (foreign.st_dev, foreign.st_ino))
            managed = os.path.join(home, "state", "managed-install")
            self.assertTrue(os.path.isfile(os.path.join(
                managed, "corpus-bootstrap")))
            self.assertFalse(os.path.lexists(os.path.join(
                managed, "corpus")))

        with tempfile.TemporaryDirectory() as home:
            corpus = os.path.join(home, "share", "corpus")
            os.makedirs(corpus)
            interrupted = block.replace(
                intent_boundary, "  false\n" + intent_boundary, 1)
            failed = run(home, interrupted)
            self.assertNotEqual(failed.returncode, 0)
            prior = corpus + ".operator-prior"
            os.rename(corpus, prior)
            os.mkdir(corpus, 0o700)
            replacement = os.stat(corpus)

            refused = run(home)
            self.assertNotEqual(refused.returncode, 0)
            current = os.stat(corpus)
            self.assertEqual(
                (current.st_dev, current.st_ino),
                (replacement.st_dev, replacement.st_ino))
            self.assertFalse(os.path.lexists(os.path.join(
                home, "state", "managed-install", "corpus")))

        root_boundaries = (
            "# Durable corpus-root boundary: the intent-bound off-path tree exists.",
            "# Durable corpus-root boundary: the exact staged generation is authorized.",
            "# Durable corpus-root boundary: the no-clobber canonical rename is synced.",
            "# Durable corpus-root boundary: the canonical root identity is bound.",
        )
        for boundary in root_boundaries:
            with self.subTest(root_boundary=boundary), \
                    tempfile.TemporaryDirectory() as home:
                self.assertIn(boundary, functions)
                interrupted_functions = functions.replace(
                    boundary, "return 1\n    " + boundary, 1)
                failed = run(
                    home, selected_functions=interrupted_functions)
                self.assertNotEqual(failed.returncode, 0)

                resumed = run(home)
                self.assertEqual(resumed.returncode, 0, resumed.stderr)
                managed = os.path.join(home, "state", "managed-install")
                self.assertTrue(os.path.isfile(os.path.join(
                    managed, "corpus")))
                self.assertFalse(os.path.lexists(os.path.join(
                    managed, "corpus-bootstrap")))
                self.assertFalse(os.path.lexists(os.path.join(
                    home, "share", ".corpus-bootstrap-tree")))

        init_boundary = (
            "# Durable bootstrap boundary: hardened git initialization is replayable.")
        with tempfile.TemporaryDirectory() as home:
            raced = block.replace(
                init_boundary,
                init_boundary + '\nprintf "%s\\n" "concurrent README" > '
                '"$SHARE/corpus/README.md"', 1)
            refused = run(home, raced)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(_read_path(os.path.join(
                home, "share", "corpus", "README.md")),
                "concurrent README\n")

        with tempfile.TemporaryDirectory() as home:
            raced = block.replace(
                init_boundary,
                init_boundary + '\nprintf "%s\\n" "concurrent memory" > '
                '"$SHARE/corpus/operator.md"', 1)
            refused = run(home, raced)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(_read_path(os.path.join(
                home, "share", "corpus", "operator.md")),
                "concurrent memory\n")

        publish = ('  if ! installed="$(owned_file_cas publish "$stage" \\\n'
                   '      "$CORPUS_BOOTSTRAP_INTENT" absent)"; then')
        self.assertIn(publish, functions)
        interrupted_functions = functions.replace(
            publish, "  return 1\n" + publish, 1)
        with tempfile.TemporaryDirectory() as home:
            for _attempt in ("first", "second"):
                self.assertNotEqual(
                    run(home, selected_functions=interrupted_functions).returncode,
                    0)
            managed = os.path.join(home, "state", "managed-install")
            self.assertEqual(
                [name for name in os.listdir(managed)
                 if name == ".corpus-bootstrap.intent.stage"],
                [".corpus-bootstrap.intent.stage"])
            resumed = run(home)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)

        with tempfile.TemporaryDirectory() as home:
            directory_failure = block.replace(boundaries[0], "false", 1)
            self.assertNotEqual(run(home, directory_failure).returncode, 0)
            corpus = os.path.join(home, "share", "corpus")
            subprocess.run(
                ["git", "-C", corpus, "init", "-q", "-b", "sia-genesis",
                 "--template="], check=True)
            sentinel = os.path.join(home, "hook-executed")
            hook = os.path.join(corpus, ".git", "hooks", "pre-commit")
            _write(hook, "#!/bin/sh\n: > " + shlex.quote(sentinel) + "\n",
                   0o755)
            refused = run(home)
            self.assertNotEqual(refused.returncode, 0)
            self.assertFalse(os.path.exists(sentinel))
            self.assertTrue(os.path.isfile(hook))

        with tempfile.TemporaryDirectory() as home:
            directory_failure = block.replace(boundaries[0], "false", 1)
            self.assertNotEqual(run(home, directory_failure).returncode, 0)
            corpus = os.path.join(home, "share", "corpus")
            subprocess.run(
                ["git", "-C", corpus, "init", "-q", "-b", "sia-genesis",
                 "--template="], check=True)
            config = os.path.join(corpus, ".git", "config")
            malicious = (
                "[core]\n\trepositoryformatversion = 0\n\tbare = false\n"
                "\tfsmonitor = !touch " +
                os.path.join(home, "config-executed") + "\n")
            _write(config, malicious)
            refused = run(home)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(_read_path(config), malicious)
            self.assertFalse(os.path.exists(
                os.path.join(home, "config-executed")))

        with tempfile.TemporaryDirectory() as home:
            directory_failure = block.replace(boundaries[0], "false", 1)
            self.assertNotEqual(run(home, directory_failure).returncode, 0)
            corpus = os.path.join(home, "share", "corpus")
            subprocess.run(
                ["git", "-C", corpus, "init", "-q", "-b", "sia-genesis",
                 "--template="], check=True)
            readme = os.path.join(corpus, "README.md")
            _write(readme, "# SIA corpus — this machine's memory\n")
            subprocess.run(["git", "-C", corpus, "add", "README.md"], check=True)
            subprocess.run(
                ["git", "-C", corpus, "-c", "user.name=Other",
                 "-c", "user.email=other@localhost", "commit", "-qm",
                 "not genesis"], check=True)
            prior = subprocess.run(
                ["git", "-C", corpus, "rev-parse", "HEAD"], text=True,
                stdout=subprocess.PIPE, check=True).stdout
            refused = run(home)
            self.assertNotEqual(refused.returncode, 0)
            current = subprocess.run(
                ["git", "-C", corpus, "rev-parse", "HEAD"], text=True,
                stdout=subprocess.PIPE, check=True).stdout
            self.assertEqual(current, prior)

        receipt_publish = (
            '  if ! installed="$(owned_file_cas publish "$stage" '
            '"$CORPUS_RECEIPT" \\\n      absent)"; then')
        self.assertIn(receipt_publish, functions)
        interrupted_receipt = functions.replace(
            receipt_publish, "  return 1\n" + receipt_publish, 1)
        with tempfile.TemporaryDirectory() as home:
            for _attempt in ("first", "second"):
                self.assertNotEqual(run(
                    home, selected_functions=interrupted_receipt).returncode, 0)
            managed = os.path.join(home, "state", "managed-install")
            self.assertEqual(
                [name for name in os.listdir(managed)
                 if name == ".corpus.receipt.stage"],
                [".corpus.receipt.stage"])
            resumed = run(home)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)

        def make_operator_corpus(home):
            corpus = os.path.join(home, "share", "corpus")
            os.makedirs(corpus, exist_ok=True)
            subprocess.run(["git", "init", "-q", corpus], check=True)
            _write(os.path.join(corpus, "operator.md"), "operator memory\n")
            subprocess.run(
                ["git", "-C", corpus, "add", "operator.md"], check=True)
            subprocess.run(
                ["git", "-C", corpus, "-c", "user.name=Operator",
                 "-c", "user.email=operator@localhost", "commit", "-qm",
                 "operator genesis"], check=True)
            return corpus

        with tempfile.TemporaryDirectory() as home:
            corpus = make_operator_corpus(home)
            consent = {"SIA_ADOPT_EXISTING_CORPUS": "1"}
            interrupted = run(home, "false\n", extra_environment=consent)
            self.assertNotEqual(interrupted.returncode, 0)
            intent = os.path.join(
                home, "state", "managed-install", "corpus-adoption")
            self.assertTrue(os.path.isfile(intent))
            resumed = run(home)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(
                _read_path(os.path.join(corpus, "operator.md")),
                "operator memory\n")

        with tempfile.TemporaryDirectory() as home:
            corpus = make_operator_corpus(home)
            consent = {"SIA_ADOPT_EXISTING_CORPUS": "1"}
            interrupted = block.replace(boundaries[-1], "false", 1)
            failed = run(home, interrupted, extra_environment=consent)
            self.assertNotEqual(failed.returncode, 0)
            managed = os.path.join(home, "state", "managed-install")
            self.assertTrue(os.path.isfile(os.path.join(managed, "corpus")))
            self.assertTrue(os.path.isfile(os.path.join(
                managed, "corpus-adoption")))

            prior = corpus + ".adoption-prior"
            os.rename(corpus, prior)
            replacement = make_operator_corpus(home)
            replacement_info = os.stat(replacement)
            refused = run(home)
            self.assertNotEqual(refused.returncode, 0)
            current = os.stat(replacement)
            self.assertEqual(
                (current.st_dev, current.st_ino),
                (replacement_info.st_dev, replacement_info.st_ino))
            self.assertTrue(os.path.isfile(os.path.join(
                managed, "corpus-adoption")))

        with tempfile.TemporaryDirectory() as home:
            corpus = make_operator_corpus(home)
            consent = {"SIA_ADOPT_EXISTING_CORPUS": "1"}
            self.assertNotEqual(
                run(home, "false\n", extra_environment=consent).returncode, 0)
            _write(os.path.join(corpus, "later.md"), "later memory\n")
            refused = run(home)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(
                _read_path(os.path.join(corpus, "later.md")), "later memory\n")
            self.assertFalse(os.path.exists(os.path.join(
                home, "state", "managed-install", "corpus")))

        adoption_publish = (
            '  if ! installed="$(owned_file_cas publish "$stage" \\\n'
            '      "$CORPUS_ADOPTION_INTENT" absent)"; then')
        self.assertIn(adoption_publish, functions)
        interrupted_adoption = functions.replace(
            adoption_publish, "  return 1\n" + adoption_publish, 1)
        with tempfile.TemporaryDirectory() as home:
            make_operator_corpus(home)
            consent = {"SIA_ADOPT_EXISTING_CORPUS": "1"}
            for _attempt in ("first", "second"):
                self.assertNotEqual(run(
                    home, selected_functions=interrupted_adoption,
                    extra_environment=consent).returncode, 0)
            managed = os.path.join(home, "state", "managed-install")
            self.assertEqual(
                [name for name in os.listdir(managed)
                 if name == ".corpus-adoption.intent.stage"],
                [".corpus-adoption.intent.stage"])
            resumed = run(home, extra_environment=consent)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)

    def test_corpus_receipt_v2_is_root_bound_and_lock_migrated(self):
        installer = _read("install.sh")
        metadata = _owned_metadata_shell(installer)
        tree = ("owned_tree_cas() {" + installer.split(
            "owned_tree_cas() {", 1)[1].split(
                "\n}\n\nowned_tree_generation()", 1)[0] +
                '\n}\nowned_tree_generation() { '
                'owned_tree_cas generation "$1"; }\n')
        functions = ("durable_fixed_metadata_stage() {" + installer.split(
            "durable_fixed_metadata_stage() {", 1)[1].split(
                "\n}\n\nruntime_tree_digest()", 1)[0] + "\n}\n")

        early = installer.index("preflight_corpus read-only")
        lifecycle = installer.index("acquire_install_lifecycle", early)
        corpus_lock = installer.index(
            'acquire_owner_lock "$STATE/corpus-owner.lock"', lifecycle)
        lock_state = installer.index(
            "SIA_CORPUS_RECEIPT_LOCKS_HELD=1", corpus_lock)
        migration = installer.index("migrate_legacy_corpus_receipt", lock_state)
        locked = installer.index("preflight_corpus locked", migration)
        self.assertLess(early, lifecycle)
        self.assertLess(lifecycle, corpus_lock)
        self.assertLess(corpus_lock, lock_state)
        self.assertLess(lock_state, migration)
        self.assertLess(migration, locked)
        read_only = installer.split("preflight_corpus_read_only() {", 1)[1] \
            .split("\n}\n\npreflight_corpus()", 1)[0]
        self.assertNotIn("owned_file_cas", read_only)
        self.assertNotIn("retire_corpus", read_only)
        self.assertNotIn("write_corpus", read_only)

        def prepare(home):
            share = os.path.join(home, "share")
            managed = os.path.join(home, "state", "managed-install")
            corpus = os.path.join(share, "corpus")
            os.makedirs(corpus, mode=0o700)
            os.makedirs(managed)
            receipt = os.path.join(managed, "corpus")
            legacy = ("managed-by=khephri.sia\nkind=corpus\n"
                      f"path={corpus}\n")
            _write(receipt, legacy, 0o600)
            return share, managed, corpus, receipt, legacy

        def run(home, command, *, locked=False, selected_metadata=metadata,
                selected_functions=functions):
            share = os.path.join(home, "share")
            managed = os.path.join(home, "state", "managed-install")
            variables = f'''
SHARE={shlex.quote(share)}
STATE={shlex.quote(os.path.join(home, "state"))}
MANAGED_DIR={shlex.quote(managed)}
CORPUS_RECEIPT="$MANAGED_DIR/corpus"
CORPUS_BOOTSTRAP_INTENT="$MANAGED_DIR/corpus-bootstrap"
CORPUS_ADOPTION_INTENT="$MANAGED_DIR/corpus-adoption"
CORPUS_BOOTSTRAP_STAGE="$SHARE/.corpus-bootstrap-tree"
SIA_INSTALL_LOCK_FD={"installer-test" if locked else ""}
SIA_CORPUS_LOCK_FD={"corpus-test" if locked else ""}
SIA_CORPUS_RECEIPT_LOCKS_HELD={1 if locked else 0}
SIA_CORPUS_EARLY_RECEIPT_STATE=absent
SIA_CORPUS_EARLY_RECEIPT_ROOT=""
SIA_CORPUS_EARLY_RECEIPT_GENERATION=""
SIA_CORPUS_EARLY_RECEIPT_JOURNAL_STATE=absent
'''
            locked_preflight = "preflight_corpus read-only\n" if locked else ""
            return subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + selected_metadata +
                 tree + selected_functions + variables + locked_preflight +
                 command,
                 "corpus-receipt-test"], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                timeout=30)

        with tempfile.TemporaryDirectory() as home:
            _, managed, corpus, receipt, legacy = prepare(home)
            observed = os.stat(corpus)
            expected = (
                "managed-by=khephri.sia\nkind=corpus-v2\n"
                f"path={corpus}\nroot={observed.st_dev}:{observed.st_ino}:"
                f"{observed.st_mode}:{observed.st_uid}\n")

            recognized = run(
                home,
                'preflight_corpus read-only\n'
                'test "$SIA_CORPUS_EARLY_RECEIPT_STATE" = legacy\n'
                'test -n "$SIA_CORPUS_EARLY_RECEIPT_ROOT"\n'
                'test -n "$SIA_CORPUS_EARLY_RECEIPT_GENERATION"\n')
            self.assertEqual(recognized.returncode, 0, recognized.stderr)
            self.assertEqual(_read_path(receipt), legacy)
            self.assertFalse(os.path.lexists(os.path.join(
                managed, ".corpus.receipt.stage")))

            unlocked = run(home, "migrate_legacy_corpus_receipt\n")
            self.assertNotEqual(unlocked.returncode, 0)
            self.assertEqual(_read_path(receipt), legacy)

            migrated = run(
                home, "migrate_legacy_corpus_receipt\ncorpus_receipt_valid\n",
                locked=True)
            self.assertEqual(migrated.returncode, 0, migrated.stderr)
            self.assertEqual(_read_path(receipt), expected)
            self.assertFalse(os.path.lexists(os.path.join(
                managed, ".corpus.receipt.stage")))

            _write(os.path.join(corpus, "ordinary-memory.md"), "changed\n")
            still_valid = run(home, "corpus_receipt_valid\n")
            self.assertEqual(still_valid.returncode, 0, still_valid.stderr)

            prior = corpus + ".operator-prior"
            os.rename(corpus, prior)
            os.mkdir(corpus, 0o700)
            replacement = os.stat(corpus)
            refused = run(home, "corpus_receipt_valid\n")
            self.assertNotEqual(refused.returncode, 0)
            refused = run(
                home, "migrate_legacy_corpus_receipt\n", locked=True)
            self.assertNotEqual(refused.returncode, 0)
            current = os.stat(corpus)
            self.assertEqual((current.st_dev, current.st_ino),
                             (replacement.st_dev, replacement.st_ino))
            self.assertEqual(_read_path(receipt), expected)

        with tempfile.TemporaryDirectory() as home:
            _, _, corpus, receipt, legacy = prepare(home)
            prior = corpus + ".prelock-observed"
            replaced = run(
                home,
                f'mv -- {shlex.quote(corpus)} {shlex.quote(prior)}\n'
                f'mkdir -m 700 -- {shlex.quote(corpus)}\n'
                'migrate_legacy_corpus_receipt\n',
                locked=True)
            self.assertNotEqual(replaced.returncode, 0)
            self.assertEqual(_read_path(receipt), legacy)
            self.assertTrue(os.path.isdir(corpus))
            self.assertFalse(os.path.lexists(os.path.join(
                home, "state", "managed-install", ".corpus.receipt.stage")))

        with tempfile.TemporaryDirectory() as home:
            _, managed, _, receipt, legacy = prepare(home)
            observed_receipt = receipt + ".prelock-observed"
            disappeared = run(
                home,
                f'mv -- {shlex.quote(receipt)} '
                f'{shlex.quote(observed_receipt)}\n'
                'migrate_legacy_corpus_receipt\n',
                locked=True)
            self.assertNotEqual(disappeared.returncode, 0)
            self.assertFalse(os.path.lexists(receipt))
            self.assertEqual(_read_path(observed_receipt), legacy)
            self.assertFalse(os.path.lexists(os.path.join(
                managed, ".corpus.receipt.stage")))

        continuity_boundary = (
            "  # Locked corpus-receipt boundary: continuity remains the "
            "publication baseline.")
        self.assertIn(continuity_boundary, functions)
        swapped_functions = functions.replace(
            continuity_boundary,
            '  cp -- "$CORPUS_RECEIPT" "$CORPUS_RECEIPT.swap"\n'
            '  chmod 0600 "$CORPUS_RECEIPT.swap"\n'
            '  mv -- "$CORPUS_RECEIPT.swap" "$CORPUS_RECEIPT"\n' +
            continuity_boundary, 1)
        with tempfile.TemporaryDirectory() as home:
            _, managed, _, receipt, legacy = prepare(home)
            swapped = run(
                home, "migrate_legacy_corpus_receipt\n", locked=True,
                selected_functions=swapped_functions)
            self.assertNotEqual(swapped.returncode, 0)
            self.assertEqual(_read_path(receipt), legacy)
            self.assertFalse(os.path.lexists(os.path.join(
                managed, ".corpus.receipt.stage")))

        with tempfile.TemporaryDirectory() as home:
            share = os.path.join(home, "share")
            managed = os.path.join(home, "state", "managed-install")
            corpus = os.path.join(share, "corpus")
            os.makedirs(corpus, mode=0o700)
            os.makedirs(managed)
            appeared = run(
                home,
                'payload="$(corpus_v2_receipt_payload '
                '\"$(corpus_root_identity)\")"\n'
                'durable_fixed_metadata_stage "$CORPUS_RECEIPT" "$payload"\n'
                'migrate_legacy_corpus_receipt\n',
                locked=True)
            self.assertNotEqual(appeared.returncode, 0)
            self.assertIn("kind=corpus-v2\n", _read_path(os.path.join(
                managed, "corpus")))

        with tempfile.TemporaryDirectory() as home:
            _, _, _, receipt, _ = prepare(home)
            migrated = run(
                home, "migrate_legacy_corpus_receipt\n", locked=True)
            self.assertEqual(migrated.returncode, 0, migrated.stderr)
            observed_receipt = receipt + ".prelock-observed"
            disappeared = run(
                home,
                f'mv -- {shlex.quote(receipt)} '
                f'{shlex.quote(observed_receipt)}\n'
                'migrate_legacy_corpus_receipt\n',
                locked=True)
            self.assertNotEqual(disappeared.returncode, 0)
            self.assertFalse(os.path.lexists(receipt))
            self.assertIn("kind=corpus-v2\n", _read_path(observed_receipt))

        with tempfile.TemporaryDirectory() as home:
            _, _, _, receipt, _ = prepare(home)
            migrated = run(
                home, "migrate_legacy_corpus_receipt\n", locked=True)
            self.assertEqual(migrated.returncode, 0, migrated.stderr)
            replacement = receipt + ".replacement"
            replaced = run(
                home,
                f'cp -- {shlex.quote(receipt)} {shlex.quote(replacement)}\n'
                f'chmod 0600 -- {shlex.quote(replacement)}\n'
                f'mv -- {shlex.quote(replacement)} {shlex.quote(receipt)}\n'
                'migrate_legacy_corpus_receipt\n',
                locked=True)
            self.assertNotEqual(replaced.returncode, 0)
            self.assertIn("kind=corpus-v2\n", _read_path(receipt))

        with tempfile.TemporaryDirectory() as home:
            _, _, corpus, receipt, _ = prepare(home)
            migrated = run(
                home, "migrate_legacy_corpus_receipt\n", locked=True)
            self.assertEqual(migrated.returncode, 0, migrated.stderr)
            bound = _read_path(receipt)
            os.chmod(corpus, 0o770)
            self.assertNotEqual(
                run(home, "corpus_receipt_valid\n").returncode, 0)
            self.assertNotEqual(run(
                home, "migrate_legacy_corpus_receipt\n",
                locked=True).returncode, 0)
            self.assertEqual(_read_path(receipt), bound)

        crash_point = (
            "            rename_noreplace(target_name, archive_name)\n"
            "            sync_parent()\n"
            "            archived = token(archive_name)")
        self.assertIn(crash_point, metadata)
        interrupted_metadata = metadata.replace(
            crash_point,
            "            rename_noreplace(target_name, archive_name)\n"
            "            sync_parent()\n"
            "            raise SystemExit('fixture crash after archival')\n"
            "            archived = token(archive_name)", 1)
        with tempfile.TemporaryDirectory() as home:
            _, managed, _, receipt, _ = prepare(home)
            interrupted = run(
                home, "migrate_legacy_corpus_receipt\n", locked=True,
                selected_metadata=interrupted_metadata)
            self.assertNotEqual(interrupted.returncode, 0)
            self.assertFalse(os.path.lexists(receipt))
            stage = os.path.join(managed, ".corpus.receipt.stage")
            self.assertTrue(os.path.isfile(stage))

            inspected = run(home, "preflight_corpus read-only\n")
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertFalse(os.path.lexists(receipt))
            self.assertTrue(os.path.isfile(stage))

            resumed = run(
                home, "migrate_legacy_corpus_receipt\ncorpus_receipt_valid\n",
                locked=True)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertTrue(os.path.isfile(receipt))
            self.assertFalse(os.path.lexists(stage))

        boundary = (
            "  # Durable corpus-receipt migration boundary: v2 is canonical.")
        self.assertIn(boundary, functions)
        interrupted_functions = functions.replace(
            boundary, "  return 1\n" + boundary, 1)
        with tempfile.TemporaryDirectory() as home:
            _, managed, _, receipt, legacy = prepare(home)
            interrupted = run(
                home, "migrate_legacy_corpus_receipt\n", locked=True,
                selected_functions=interrupted_functions)
            self.assertNotEqual(interrupted.returncode, 0)
            self.assertIn("kind=corpus-v2\n", _read_path(receipt))
            stage = os.path.join(managed, ".corpus.receipt.stage")
            self.assertEqual(_read_path(stage), legacy)

            inspected = run(home, "preflight_corpus read-only\n")
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertEqual(_read_path(stage), legacy)

            archive_crash_point = (
                "        rename_noreplace(archive_name, staged_name)\n"
                "        sync_parent()\n"
                "        if not moved_token_matches(token(staged_name), expected)")
            self.assertIn(archive_crash_point, metadata)
            archive_interrupted_metadata = metadata.replace(
                archive_crash_point,
                "        rename_noreplace(archive_name, staged_name)\n"
                "        sync_parent()\n"
                "        raise SystemExit('fixture crash after archive')\n"
                "        if not moved_token_matches(token(staged_name), expected)",
                1)
            retired = os.path.join(managed, ".corpus.receipt.retired")
            retirement_interrupted = run(
                home, "migrate_legacy_corpus_receipt\n", locked=True,
                selected_metadata=archive_interrupted_metadata)
            self.assertNotEqual(retirement_interrupted.returncode, 0)
            self.assertFalse(os.path.lexists(stage))
            self.assertEqual(_read_path(retired), legacy)
            inspected = run(home, "preflight_corpus read-only\n")
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertEqual(_read_path(retired), legacy)

            resumed = run(
                home, "migrate_legacy_corpus_receipt\ncorpus_receipt_valid\n",
                locked=True)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertFalse(os.path.lexists(stage))
            self.assertFalse(os.path.lexists(retired))

        with tempfile.TemporaryDirectory() as home:
            _, managed, _, _, _ = prepare(home)
            interrupted = run(
                home, "migrate_legacy_corpus_receipt\n", locked=True,
                selected_functions=interrupted_functions)
            self.assertNotEqual(interrupted.returncode, 0)
            stage = os.path.join(managed, ".corpus.receipt.stage")
            _write(stage, "independent stage\n", 0o600)
            refused = run(
                home, "migrate_legacy_corpus_receipt\n", locked=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(_read_path(stage), "independent stage\n")

        with tempfile.TemporaryDirectory() as home:
            share = os.path.join(home, "share")
            managed = os.path.join(home, "state", "managed-install")
            corpus = os.path.join(share, "corpus")
            os.makedirs(corpus, mode=0o700)
            os.makedirs(managed)
            fresh = run(
                home, "write_corpus_receipt\ncorpus_receipt_valid\n",
                locked=True)
            self.assertEqual(fresh.returncode, 0, fresh.stderr)
            self.assertIn("kind=corpus-v2\n", _read_path(os.path.join(
                managed, "corpus")))

        fresh_crash_point = (
            "        write_journal(record)\n"
            "        if expected != \"absent\":")
        self.assertIn(fresh_crash_point, metadata)
        fresh_interrupted_metadata = metadata.replace(
            fresh_crash_point,
            "        write_journal(record)\n"
            "        raise SystemExit('fixture crash after fresh journal')\n"
            "        if expected != \"absent\":", 1)
        with tempfile.TemporaryDirectory() as home:
            share = os.path.join(home, "share")
            managed = os.path.join(home, "state", "managed-install")
            corpus = os.path.join(share, "corpus")
            os.makedirs(corpus, mode=0o700)
            os.makedirs(managed)
            receipt = os.path.join(managed, "corpus")
            interrupted = run(
                home, "write_corpus_receipt\n", locked=True,
                selected_metadata=fresh_interrupted_metadata)
            self.assertNotEqual(interrupted.returncode, 0)
            self.assertFalse(os.path.lexists(receipt))
            stage = os.path.join(managed, ".corpus.receipt.stage")
            self.assertTrue(os.path.isfile(stage))

            inspected = run(home, "preflight_corpus read-only\n")
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertFalse(os.path.lexists(receipt))
            self.assertTrue(os.path.isfile(stage))
            resumed = run(
                home,
                "migrate_legacy_corpus_receipt\n"
                "write_corpus_receipt\ncorpus_receipt_valid\n",
                locked=True)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertTrue(os.path.isfile(receipt))
            self.assertFalse(os.path.lexists(stage))

        with tempfile.TemporaryDirectory() as home:
            _, managed, _, receipt, legacy = prepare(home)
            adoption = os.path.join(managed, "corpus-adoption")
            intent_stage = os.path.join(managed, ".hidden-intent.stage")
            _write(adoption, "operator intent\n", 0o600)
            _write(intent_stage, "replacement intent\n", 0o600)
            hidden = run(
                home,
                'expected="$(owned_metadata generation '
                '\"$CORPUS_ADOPTION_INTENT\")"\n'
                'owned_file_cas publish "$MANAGED_DIR/.hidden-intent.stage" '
                '"$CORPUS_ADOPTION_INTENT" "$expected"\n',
                selected_metadata=interrupted_metadata)
            self.assertNotEqual(hidden.returncode, 0)
            self.assertFalse(os.path.lexists(adoption))

            refused = run(
                home, "migrate_legacy_corpus_receipt\n", locked=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(_read_path(receipt), legacy)
            self.assertEqual(_read_path(adoption), "operator intent\n")
            self.assertFalse(os.path.lexists(os.path.join(
                managed, ".corpus.receipt.stage")))

    def test_plugin_rescan_discovers_exact_id_before_enablement(self):
        installer = _read("install.sh")
        desktop = installer.split('step "8/9 desktop', 1)[1].split(
            'step "9/9 agents', 1)[0]
        self.assertIn("omarchy-shell shell rescanPlugins", desktop)
        self.assertIn("omarchy plugin list --json", desktop)
        self.assertIn("attempt < 40", desktop)
        self.assertIn("sleep 0.05", desktop)
        self.assertIn('plugin.get("id") == plugin_id', desktop)
        self.assertLess(desktop.index("rescan_and_verify_omarchy_plugin khephri.sia"),
                        desktop.index("omarchy plugin enable khephri.sia"))

        functions = _bounded_commands_shell(installer) + \
            "\nplugin_id_is_discovered() {" + installer.split(
            "plugin_id_is_discovered() {", 1)[1].split(
                "\nbinding_block_state()", 1)[0]
        with tempfile.TemporaryDirectory() as root:
            fake_bin = os.path.join(root, "bin")
            trace = os.path.join(root, "trace")
            seen = os.path.join(root, "seen")
            os.makedirs(fake_bin)
            _fake_command(
                fake_bin, "omarchy-shell",
                'echo "omarchy-shell $*" >> "$TRACE"\nexit 0\n')
            _fake_command(
                fake_bin, "omarchy",
                'echo "omarchy $*" >> "$TRACE"\n'
                'if [ "$1 $2 $3" = "plugin list --json" ]; then\n'
                '  if [ -e "$SEEN" ]; then\n'
                '    echo \'[{"id":"khephri.sia"}]\'\n'
                '  else\n'
                '    : > "$SEEN"\n'
                '    echo \'[{"id":"khephri.sia-extra"}]\'\n'
                '  fi\n'
                'fi\n')
            _fake_command(
                fake_bin, "sleep",
                'echo "sleep $*" >> "$TRACE"\nexit 0\n')
            environment = os.environ.copy()
            environment.update({
                "PATH": fake_bin + os.pathsep + environment["PATH"],
                "TRACE": trace,
                "SEEN": seen,
            })
            result = subprocess.run(
                ["bash", "-c", functions +
                 "\nrescan_and_verify_omarchy_plugin khephri.sia"],
                env=environment, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = _read_path(trace).splitlines()
            self.assertEqual(calls[0],
                             "omarchy-shell shell rescanPlugins")
            self.assertEqual(calls[1], "omarchy plugin list --json")
            self.assertEqual(calls[2], "sleep 0.05")
            self.assertEqual(calls[3], "omarchy plugin list --json")

    def test_keybinding_mutations_are_atomic_and_refuse_open_blocks(self):
        installer = _read("install.sh")
        uninstaller = _read("uninstall.sh")
        self.assertIn("binding_block_state()", installer)
        self.assertIn("binding_block_state()", uninstaller)
        self.assertIn("incomplete, duplicated, or malformed", installer)
        self.assertIn("incomplete, duplicated, or malformed", uninstaller)
        self.assertIn(".bindings.lua.sia-stage.XXXXXX", installer)
        self.assertIn("restored the original bindings", installer)
        self.assertNotIn('cat >> "$BINDINGS"', installer)
        self.assertNotIn("sed -i '/-- BEGIN SIA/,/-- END SIA/d'", uninstaller)
        self.assertIn('owned_file_cas publish "$stage" "$bindings"',
                      installer)
        self.assertIn('owned_file_cas publish "$stage" "$bindings"',
                      uninstaller)

    def test_owned_file_cas_preserves_concurrent_generations(self):
        installer = _read("install.sh")
        metadata = _owned_metadata_shell(installer)
        body = installer.split("owned_file_cas() {", 1)[1].split(
            "\n}\n\nwrite_lifecycle_tombstone", 1)[0]
        function = "owned_file_cas() {" + body + "\n}\n"
        python_source = installer.split(
            "owned_file_cas() {\n  python3 - \"$@\" <<'PY'\n", 1)[1].split(
                "\nPY\n}", 1)[0]
        self.assertNotIn("RENAME_EXCHANGE", python_source)
        self.assertNotIn("os.replace", python_source)
        self.assertIn("rename_noreplace(target_name, archive_name)",
                      python_source)
        self.assertIn("rename_noreplace(staged_name, target_name)",
                      python_source)
        self.assertIn("recover_journal()", python_source)

        def generation(path):
            result = subprocess.run(
                ["bash", "-c", metadata +
                 '\nowned_metadata generation "$1"', "cas-test", path],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, "bindings.lua")
            stage = os.path.join(root, ".stage")
            _write(target, "operator original\n")
            _write(stage, "installer desired\n")
            expected = generation(target)
            _write(target, "concurrent before publish\n")
            refused = subprocess.run(
                ["bash", "-c", function +
                 '\nowned_file_cas publish "$1" "$2" "$3"',
                 "cas-test", stage, target, expected], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(refused.returncode, 0)
            self.assertEqual(_read_path(target), "concurrent before publish\n")

            _write(target, "operator original\n")
            _write(stage, "installer desired\n")
            expected = generation(target)
            intruder = os.path.join(root, "intruder")
            _write(intruder, "concurrent canonical generation\n")
            publish_needle = (
                "            rename_noreplace(staged_name, target_name)\n"
                "            sync_parent()")
            self.assertIn(publish_needle, python_source)
            displaced_source = python_source.replace(
                publish_needle, publish_needle +
                '\n            os.rename(os.environ["CAS_INTRUDER"], target)',
                1)
            with mock.patch.object(sys, "argv", [
                    "owned-file-cas", "publish", stage, target, expected]), \
                    mock.patch.dict(os.environ, {"CAS_INTRUDER": intruder}):
                with self.assertRaises(SystemExit) as stopped:
                    exec(compile(displaced_source, "owned-file-cas", "exec"), {})
            self.assertNotEqual(stopped.exception.code, 0)
            self.assertEqual(_read_path(target),
                             "concurrent canonical generation\n")
            self.assertFalse(os.path.lexists(stage))
            retained = [name for name in os.listdir(root)
                        if name.startswith(".sia-cas-prior.")]
            self.assertEqual(len(retained), 1)
            self.assertEqual(_read_path(os.path.join(root, retained[0])),
                             "operator original\n")

        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, "bindings.lua")
            stage = os.path.join(root, ".stage")
            _write(target, "operator original\n")
            _write(stage, "installer desired\n")
            expected = generation(target)
            archive_needle = (
                "            rename_noreplace(target_name, archive_name)\n"
                "            sync_parent()")
            self.assertIn(archive_needle, python_source)
            crashed_source = python_source.replace(
                archive_needle, archive_needle +
                '\n            raise RuntimeError("simulated crash")', 1)
            with mock.patch.object(sys, "argv", [
                    "owned-file-cas", "publish", stage, target, expected]), \
                    self.assertRaises(RuntimeError):
                exec(compile(crashed_source, "owned-file-cas", "exec"), {})
            self.assertFalse(os.path.lexists(target))
            recovered = subprocess.run(
                ["bash", "-c", function +
                 '\nowned_file_cas recover "$1"', "cas-test", target],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False)
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertEqual(_read_path(target), "operator original\n")
            self.assertFalse([
                name for name in os.listdir(root)
                if name.startswith(".sia-cas-journal-")])

        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, "bindings.lua")
            stage = os.path.join(root, ".stage")
            _write(target, "operator original\n")
            _write(stage, "installer desired\n")
            expected = generation(target)
            original_write = os.write
            writes = {"count": 0}

            def short_write(descriptor, data):
                writes["count"] += 1
                if writes["count"] == 1:
                    return original_write(descriptor, data[:1])
                return 0

            with mock.patch.object(sys, "argv", [
                    "owned-file-cas", "publish", stage, target, expected]), \
                    mock.patch("os.write", side_effect=short_write), \
                    self.assertRaises(OSError):
                exec(compile(python_source, "owned-file-cas", "exec"), {})
            self.assertEqual(_read_path(target), "operator original\n")
            self.assertEqual(_read_path(stage), "installer desired\n")
            self.assertFalse([
                name for name in os.listdir(root)
                if name.startswith(".sia-cas-journal-")])
            self.assertFalse([
                name for name in os.listdir(root)
                if name.startswith(".sia-cas-journal-stage.")])

    def test_owned_tree_cas_is_generation_bound_and_crash_recoverable(self):
        installer = _read("install.sh")
        body = installer.split("owned_tree_cas() {", 1)[1].split(
            "\n}\n\nowned_tree_generation()", 1)[0]
        function = "owned_tree_cas() {" + body + "\n}\n"
        python_source = installer.split(
            "owned_tree_cas() {\n  python3 - \"$@\" <<'PY'\n", 1)[1].split(
                "\nPY\n}", 1)[0]
        self.assertNotIn("RENAME_EXCHANGE", python_source)
        self.assertNotIn("os.replace", python_source)
        for call in (
                '"$TOOLCHAIN/.bun.previous.XXXXXX" "$BUN_TREE_EXPECTED"',
                '"$TOOLCHAIN/.gbrain.previous.XXXXXX" "$GBRAIN_TREE_EXPECTED"',
                '"$OLLAMA_TREE_EXPECTED"',
                '"$SHARE/.bin.previous.XXXXXX" "$SIA_RUNTIME_TREE_EXPECTED"',
                '"$PLUGIN_TREE_EXPECTED"'):
            self.assertIn(call, installer)

        def generation(path):
            result = subprocess.run(
                ["bash", "-c", function +
                 '\nowned_tree_cas generation "$1"', "tree-cas-test", path],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, "runtime")
            stage = os.path.join(root, ".stage")
            backup = os.path.join(root, ".backup")
            intruder = os.path.join(root, ".intruder")
            os.mkdir(target)
            os.mkdir(stage)
            os.mkdir(intruder)
            _write(os.path.join(target, "value"), "operator original\n")
            _write(os.path.join(stage, "value"), "installer desired\n")
            _write(os.path.join(intruder, "value"), "concurrent tree\n")
            expected = generation(target)
            archive_needle = (
                "        rename_noreplace(target_name, archive)\n"
                "        sync_parent()")
            self.assertIn(archive_needle, python_source)
            raced_source = python_source.replace(
                archive_needle, archive_needle +
                '\n        os.rename(os.environ["TREE_INTRUDER"], target)', 1)
            with mock.patch.object(sys, "argv", [
                    "owned-tree-cas", "publish", stage, target, backup,
                    expected]), mock.patch.dict(
                        os.environ, {"TREE_INTRUDER": intruder}):
                with self.assertRaises(SystemExit) as stopped:
                    exec(compile(raced_source, "owned-tree-cas", "exec"), {})
            self.assertNotEqual(stopped.exception.code, 0)
            self.assertEqual(
                _read_path(os.path.join(target, "value")),
                "concurrent tree\n")
            retained = [name for name in os.listdir(root)
                        if name.startswith(".sia-tree-cas-prior.")]
            self.assertEqual(len(retained), 1)
            self.assertEqual(
                _read_path(os.path.join(root, retained[0], "value")),
                "operator original\n")

        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, "runtime")
            stage = os.path.join(root, ".stage")
            backup = os.path.join(root, ".backup")
            os.mkdir(target)
            os.mkdir(stage)
            _write(os.path.join(target, "value"), "operator original\n")
            _write(os.path.join(stage, "value"), "installer desired\n")
            expected = generation(target)
            crashed_source = python_source.replace(
                archive_needle, archive_needle +
                '\n        raise RuntimeError("simulated tree crash")', 1)
            with mock.patch.object(sys, "argv", [
                    "owned-tree-cas", "publish", stage, target, backup,
                    expected]), self.assertRaises(RuntimeError):
                exec(compile(crashed_source, "owned-tree-cas", "exec"), {})
            self.assertFalse(os.path.lexists(target))
            recovered = subprocess.run(
                ["bash", "-c", function +
                 '\nowned_tree_cas recover "$1"', "tree-cas-test", target],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False)
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertEqual(
                _read_path(os.path.join(target, "value")),
                "operator original\n")
            self.assertFalse([
                name for name in os.listdir(root)
                if name.startswith(".sia-tree-cas-journal-")])

    def test_uninstall_archives_are_generation_bound_and_preserve_writers(self):
        uninstaller = _read("uninstall.sh")
        metadata = _owned_metadata_shell(uninstaller)
        file_body = uninstaller.split("owned_file_cas() {", 1)[1].split(
            "\n}\n\n# Descriptor-rooted, generation-bound archival", 1)[0]
        file_function = "owned_file_cas() {" + file_body + "\n}\n"
        file_source = uninstaller.split(
            "owned_file_cas() {\n  python3 - \"$@\" <<'PY'\n", 1)[1].split(
                "\nPY\n}", 1)[0]
        tree_body = uninstaller.split("owned_tree_cas() {", 1)[1].split(
            "\n}\n\nowned_tree_generation()", 1)[0]
        tree_function = "owned_tree_cas() {" + tree_body + "\n}\n"
        tree_source = uninstaller.split(
            "owned_tree_cas() {\n  python3 - \"$@\" <<'PY'\n", 1)[1].split(
                "\nPY\n}", 1)[0]

        self.assertNotIn("mv -T", uninstaller)
        self.assertNotIn("RENAME_EXCHANGE", tree_source)
        self.assertNotIn("os.replace", tree_source)
        self.assertIn('owned_file_cas archive "$UNIT_BACKUP"', uninstaller)
        self.assertIn('owned_file_cas archive "$backup" "$CLI_PATH"',
                      uninstaller)
        self.assertIn('owned_tree_cas archive "$RUNTIME_BIN_DIR"',
                      uninstaller)
        self.assertIn('owned_tree_cas archive "$PLUGIN_DIR"', uninstaller)
        self.assertIn('"$UNIT_RECEIPT" "$UNIT_RECEIPT_EXPECTED"',
                      uninstaller)

        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, "sia")
            intruder = os.path.join(root, "intruder")
            backup = os.path.join(root, ".removed")
            _write(target, "managed cli\n")
            digest = hashlib.sha256(b"managed cli\n").hexdigest()
            os.chmod(target, 0)
            expected_result = subprocess.run(
                ["bash", "-c", metadata +
                 '\nowned_metadata fenced-generation "$1" "$2"',
                 "uninstall-file-cas", target, digest], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(expected_result.returncode, 0,
                             expected_result.stderr)
            expected = expected_result.stdout.strip()
            _write(intruder, "concurrent cli\n")
            archive_needle = (
                "        rename_noreplace(target_name, archive_name)\n"
                "        sync_parent()")
            self.assertIn(archive_needle, file_source)
            raced_source = file_source.replace(
                archive_needle, archive_needle +
                '\n        os.rename(os.environ["CAS_INTRUDER"], target)', 1)
            with mock.patch.object(sys, "argv", [
                    "owned-file-cas", "archive", backup, target, expected]), \
                    mock.patch.dict(os.environ, {"CAS_INTRUDER": intruder}):
                with self.assertRaises(SystemExit) as stopped:
                    exec(compile(raced_source, "uninstall-file-cas", "exec"), {})
            self.assertNotEqual(stopped.exception.code, 0)
            self.assertEqual(_read_path(target), "concurrent cli\n")
            retained = [name for name in os.listdir(root)
                        if name.startswith(".sia-cas-prior.")]
            self.assertEqual(len(retained), 1)
            os.chmod(os.path.join(root, retained[0]), 0o600)
            self.assertEqual(_read_path(os.path.join(root, retained[0])),
                             "managed cli\n")

        def tree_generation(function, path):
            result = subprocess.run(
                ["bash", "-c", function +
                 '\nowned_tree_cas generation "$1"',
                 "uninstall-tree-cas", path], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, "runtime")
            intruder = os.path.join(root, "intruder")
            backup = os.path.join(root, ".runtime.removed")
            os.mkdir(target)
            os.mkdir(intruder)
            _write(os.path.join(target, "member"), "managed runtime\n")
            _write(os.path.join(intruder, "member"), "concurrent runtime\n")
            expected = tree_generation(tree_function, target)
            archive_needle = (
                "    rename_noreplace(target_name, archive)\n"
                "    sync_parent()")
            self.assertIn(archive_needle, tree_source)
            raced_source = tree_source.replace(
                archive_needle, archive_needle +
                '\n    os.rename(os.environ["TREE_INTRUDER"], target)', 1)
            with mock.patch.object(sys, "argv", [
                    "owned-tree-cas", "archive", target, backup, expected]), \
                    mock.patch.dict(os.environ, {"TREE_INTRUDER": intruder}):
                with self.assertRaises(SystemExit) as stopped:
                    exec(compile(raced_source, "uninstall-tree-cas", "exec"), {})
            self.assertNotEqual(stopped.exception.code, 0)
            self.assertEqual(
                _read_path(os.path.join(target, "member")),
                "concurrent runtime\n")
            self.assertEqual(
                _read_path(os.path.join(backup, "member")),
                "managed runtime\n")

        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, "plugin")
            backup = os.path.join(root, ".plugin.removed")
            os.mkdir(target)
            _write(os.path.join(target, "member"), "managed plugin\n")
            expected = tree_generation(tree_function, target)
            crashed_source = tree_source.replace(
                archive_needle, archive_needle +
                '\n    raise RuntimeError("simulated archive crash")', 1)
            with mock.patch.object(sys, "argv", [
                    "owned-tree-cas", "archive", target, backup, expected]), \
                    self.assertRaises(RuntimeError):
                exec(compile(crashed_source, "uninstall-tree-cas", "exec"), {})
            self.assertFalse(os.path.lexists(target))
            recovered = subprocess.run(
                ["bash", "-c", tree_function +
                 '\nowned_tree_cas recover "$1"',
                 "uninstall-tree-cas", target], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertFalse(os.path.lexists(target))
            self.assertEqual(_read_path(os.path.join(backup, "member")),
                             "managed plugin\n")
            self.assertFalse([
                name for name in os.listdir(root)
                if name.startswith(".sia-tree-cas-journal-")])

    def test_gbrain_pin_retirement_requires_exact_target_and_receipt(self):
        uninstaller = _read("uninstall.sh")
        authority_functions = "managed_receipt_matches() {" + \
            uninstaller.split("managed_receipt_matches() {", 1)[1].split(
                "\n\ncapture_cli_removal_authority", 1)[0]
        metadata_function = "remove_managed_metadata() {" + \
            uninstaller.split("remove_managed_metadata() {", 1)[1].split(
                "\n}\nruntime_tree_digest()", 1)[0] + "\n}\n"
        pin_function = "remove_owned_gbrain_pin() {" + uninstaller.split(
            "remove_owned_gbrain_pin() {", 1)[1].split(
                "\n}\n\nmcp_marker_state()", 1)[0] + "\n}\n"
        functions = (_owned_metadata_shell(uninstaller) + "\n" +
                     authority_functions + "\n" + metadata_function +
                     "\n" + pin_function)
        self.assertIn(
            'owned_file_cas archive "$backup" "$GBRAIN_PIN_PATH"',
            pin_function)
        self.assertIn("remove_managed_metadata", pin_function)
        self.assertIn(
            '"$GBRAIN_PIN_RECEIPT" "$receipt_expected"', pin_function)

        def run(function_text, root):
            share = os.path.join(root, "share")
            managed = os.path.join(root, "managed")
            target = os.path.join(share, "GBRAIN_PIN")
            receipt = os.path.join(managed, "gbrain-pin")
            script = ("set -u\n" + function_text +
                      f"\nSHARE_DIR={share!r}\n"
                      f"GBRAIN_PIN_PATH={target!r}\n"
                      f"GBRAIN_PIN_RECEIPT={receipt!r}\n"
                      "remove_owned_gbrain_pin\n")
            result = subprocess.run(
                ["bash", "-c", script], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            return result, target, receipt

        with tempfile.TemporaryDirectory() as root:
            share = os.path.join(root, "share")
            managed = os.path.join(root, "managed")
            target = os.path.join(share, "GBRAIN_PIN")
            receipt = os.path.join(managed, "gbrain-pin")
            _write(target, "managed pin\n")
            exact_receipt = _managed_file_receipt(target, "gbrain-pin")
            _write(receipt, exact_receipt)
            _write(target, "operator-modified pin\n")
            result, target, receipt = run(functions, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(_read_path(target), "operator-modified pin\n")
            self.assertEqual(_read_path(receipt), exact_receipt)

        race_needle = (
            '  if ! archived="$(owned_file_cas archive "$backup" '
            '"$GBRAIN_PIN_PATH"')
        self.assertIn(race_needle, pin_function)
        raced_pin_function = pin_function.replace(
            race_needle,
            '  replacement="$SHARE_DIR/.GBRAIN_PIN.concurrent"\n'
            '  printf "%s\\n" "concurrent pin" > "$replacement"\n'
            '  mv -T -- "$replacement" "$GBRAIN_PIN_PATH"\n' +
            race_needle, 1)
        raced_functions = (_owned_metadata_shell(uninstaller) + "\n" +
                           authority_functions + "\n" + metadata_function +
                           "\n" + raced_pin_function)
        with tempfile.TemporaryDirectory() as root:
            share = os.path.join(root, "share")
            managed = os.path.join(root, "managed")
            target = os.path.join(share, "GBRAIN_PIN")
            receipt = os.path.join(managed, "gbrain-pin")
            _write(target, "managed pin\n")
            exact_receipt = _managed_file_receipt(target, "gbrain-pin")
            _write(receipt, exact_receipt)
            result, target, receipt = run(raced_functions, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(_read_path(target), "concurrent pin\n")
            self.assertEqual(_read_path(receipt), exact_receipt)

    def test_binding_and_skill_callers_preserve_concurrent_writes(self):
        installer = _read("install.sh")
        uninstaller = _read("uninstall.sh")
        race_wrapper = r'''
eval "$(declare -f owned_file_cas | sed '1s/^owned_file_cas/real_owned_file_cas/')"
owned_file_cas() {
  if [ "$3" = "$RACE_TARGET" ]; then
    printf '%s\n' 'concurrent writer' > "$3"
  fi
  real_owned_file_cas "$@"
}
'''

        install_binding = "binding_block_state() {" + installer.split(
            "binding_block_state() {", 1)[1].split(
                "\nif have omarchy; then", 1)[0]
        uninstall_binding = "binding_block_state() {" + uninstaller.split(
            "binding_block_state() {", 1)[1].split(
                "\nif have systemctl; then", 1)[0]
        install_skill_body = installer.split(
            "install_agent_skill() {", 1)[1].split(
                "\n}\ninstall_agent_skill", 1)[0]
        install_skill = "install_agent_skill() {" + install_skill_body + "\n}\n"
        uninstall_skill_body = uninstaller.split(
            "remove_managed_skill() {", 1)[1].split(
                "\n}\n\nbinding_block_state", 1)[0]
        uninstall_skill = ("remove_managed_skill() {" +
                           uninstall_skill_body + "\n}\n")

        with tempfile.TemporaryDirectory() as root:
            bindings = os.path.join(root, "bindings.lua")
            _write(bindings, "-- operator binding\n")
            script = (_owned_metadata_shell(installer) + install_binding +
                      race_wrapper + r'''
have() { return 1; }
SIA_INSTALL_KEYBINDING=1
install_sia_keybinding "$1"
''')
            result = subprocess.run(
                ["bash", "-c", script, "binding-install-race", bindings],
                env={**os.environ, "RACE_TARGET": bindings}, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(_read_path(bindings), "concurrent writer\n")

            _write(bindings, "-- operator binding\n\n"
                   "-- BEGIN SIA (managed by khephri.sia/install.sh)\n"
                   "managed line\n-- END SIA\n")
            script = (_owned_metadata_shell(uninstaller) + uninstall_binding +
                      race_wrapper + r'''
FAILURES=()
failed() { FAILURES+=("$1"); }
have() { return 1; }
remove_managed_binding "$1"
[ "${#FAILURES[@]}" -gt 0 ]
''')
            result = subprocess.run(
                ["bash", "-c", script, "binding-uninstall-race", bindings],
                env={**os.environ, "RACE_TARGET": bindings}, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(_read_path(bindings), "concurrent writer\n")

        with tempfile.TemporaryDirectory() as root:
            skill_dir = os.path.join(root, "agent-skill")
            skill = os.path.join(skill_dir, "SKILL.md")
            marker = os.path.join(skill_dir, ".sia-managed")
            release = os.path.join(root, "release")
            source_skill = os.path.join(release, "skill/SKILL.md")
            _write(skill, "old managed skill\n")
            with open(skill, "rb") as stream:
                digest = hashlib.sha256(stream.read()).hexdigest()
            _write(marker, "managed-by=khephri.sia\n"
                   f"skill_sha256={digest}\n")
            _write(source_skill, "new release skill\n")
            script = (_owned_metadata_shell(installer) + install_skill +
                      race_wrapper + r'''
atomic_install_file() { cp -- "$1" "$2" && chmod "$3" "$2"; }
SKILL_DIR="$1"
SKILL_FILE="$SKILL_DIR/SKILL.md"
SKILL_MARKER="$SKILL_DIR/.sia-managed"
REPO="$2"
SIA_ORIGINAL_REPO="$REPO"
install_agent_skill
''')
            result = subprocess.run(
                ["bash", "-c", script, "skill-install-race", skill_dir,
                 release], env={**os.environ, "RACE_TARGET": skill},
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(_read_path(skill), "concurrent writer\n")

            _write(skill, "old managed skill\n")
            with open(skill, "rb") as stream:
                digest = hashlib.sha256(stream.read()).hexdigest()
            _write(marker, "managed-by=khephri.sia\n"
                   f"skill_sha256={digest}\n")
            marker_race_wrapper = r'''
eval "$(declare -f owned_file_cas | sed '1s/^owned_file_cas/real_owned_file_cas/')"
owned_file_cas() {
  if [ "$1" = publish ] && [ "$3" = "$RACE_MARKER" ]; then
    printf '%s\n' 'concurrent across marker publication' > "$RACE_SKILL"
  fi
  real_owned_file_cas "$@"
}
'''
            script = (_owned_metadata_shell(installer) + install_skill +
                      marker_race_wrapper + r'''
atomic_install_file() { cp -- "$1" "$2" && chmod "$3" "$2"; }
SKILL_DIR="$1"
SKILL_FILE="$SKILL_DIR/SKILL.md"
SKILL_MARKER="$SKILL_DIR/.sia-managed"
REPO="$2"
SIA_ORIGINAL_REPO="$REPO"
install_agent_skill
''')
            result = subprocess.run(
                ["bash", "-c", script, "skill-marker-race", skill_dir,
                 release], env={**os.environ, "RACE_MARKER": marker,
                                "RACE_SKILL": skill}, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(
                _read_path(skill), "concurrent across marker publication\n")
            self.assertFalse(os.path.lexists(marker))

            _write(skill, "old managed skill\n")
            with open(skill, "rb") as stream:
                digest = hashlib.sha256(stream.read()).hexdigest()
            _write(marker, "managed-by=khephri.sia\n"
                   f"skill_sha256={digest}\n")
            script = (_owned_metadata_shell(uninstaller) + uninstall_skill +
                      race_wrapper + r'''
SKILL_DIR="$1"
SKILL_FILE="$SKILL_DIR/SKILL.md"
SKILL_MARKER="$SKILL_DIR/.sia-managed"
remove_managed_skill
''')
            result = subprocess.run(
                ["bash", "-c", script, "skill-uninstall-race", skill_dir],
                env={**os.environ, "RACE_TARGET": skill}, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(_read_path(skill), "concurrent writer\n")
            retained = [name for name in os.listdir(skill_dir)
                        if name.startswith(".sia-managed.removed.")]
            self.assertTrue(retained)

    def test_agent_config_mutations_are_owned_and_fail_visibly(self):
        installer = _read("install.sh")
        agents = installer.split('step "9/9 agents', 1)[1]
        self.assertIn('SKILL_MARKER="$SKILL_DIR/.sia-managed"', agents)
        self.assertIn("managed-by=khephri.sia", agents)
        self.assertIn("skill_sha256=", agents)
        self.assertIn("SIA_REPLACE_AGENT_SKILL", agents)
        self.assertIn('atomic_install_file "$REPO/skill/SKILL.md"', agents)
        self.assertIn('owned_file_cas publish "$skill_stage" "$SKILL_FILE"',
                      agents)
        self.assertIn('owned_file_cas publish "$marker_stage"',
                      agents)
        self.assertIn("existing agent skill preserved", agents)
        self.assertIn("exact owned $harness MCP registration recovered", agents)
        self.assertIn("exact unmarked $harness MCP registration is user-owned; preserved",
                      agents)
        self.assertIn("state=committed", agents)
        self.assertNotIn('write_mcp_marker "$harness" pending-add', agents)
        self.assertNotIn("add_mcp_server()", agents)
        self.assertNotIn("rollback_added_mcp", agents)
        self.assertIn("no compare-and-add API is available", agents)
        self.assertIn("not installed; MCP registration skipped", agents)
        self.assertIn('MCP_MARKER_DIR="$STATE/managed-mcp"', agents)
        self.assertIn('MCP_GUARD_DIR="$STATE/mcp-consumer-guards"', agents)
        self.assertIn("external MCP clients can preserve the CLI/runtime",
                      agents)
        self.assertIn('write_mcp_marker "$harness" committed', agents)
        self.assertIn("claude mcp add --scope user sia -- python3", agents)
        self.assertIn("codex mcp add sia -- python3", agents)
        self.assertIn("grok mcp add --scope user sia -- python3", agents)
        self.assertNotIn("mcp add --scope user sia -- python3 "
                         '"$BINDIR/sia-mcp" 2>/dev/null || true', agents)
        self.assertNotIn("mcp_servers.sia", agents)
        uninstaller = _read("uninstall.sh")
        self.assertIn("remove_managed_mcp claude", uninstaller)
        self.assertIn("MCP registration still references SIA",
                      uninstaller)

    def test_mcp_transaction_metadata_is_storage_durable(self):
        installer = _read("install.sh")
        uninstaller = _read("uninstall.sh")
        for script in (installer, uninstaller):
            durable = script.split("durable_replace_file() {", 1)[1].split(
                "\n}\n", 1)[0]
            self.assertIn("owned_file_cas publish", durable)
            self.assertNotIn("os.replace", durable)
            self.assertIn('"$3"', durable)
        marker_writer = installer.split("write_mcp_marker() {", 1)[1].split(
            "\n}\n", 1)[0]
        install_guard_writer = installer.split(
            "write_mcp_consumer_guard() {", 1)[1].split("\n}\n", 1)[0]
        uninstall_guard_writer = uninstaller.split(
            "write_mcp_consumer_guard() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("durable_replace_file", marker_writer)
        self.assertIn("durable_replace_file", install_guard_writer)
        self.assertIn("durable_replace_file", uninstall_guard_writer)

    def test_external_inspection_capture_is_bounded(self):
        for script_name in ("install.sh", "uninstall.sh"):
            script = _read(script_name)
            body = script.split("bounded_command_capture() {", 1)[1].split(
                "\n}\n", 1)[0]
            function = "bounded_command_capture() {" + body + "\n}\n"
            self.assertIn("MAX_CAPTURE_BYTES = 1_048_576", function)
            self.assertIn("subprocess.DEVNULL", function)
            self.assertIn('arguments[:1] == ["--stdin"]', function)
            self.assertIn("start_new_session=True", function)
            self.assertIn("os.killpg(process.pid, signal.SIGKILL)", function)
            self.assertIn("os.pidfd_open(process.pid, 0)", function)
            self.assertIn("os.WNOWAIT", function)
            self.assertLess(
                function.index("kill_group()\n    status = process.wait()"),
                function.index("selector.close()"))
            self.assertIn('b"\\0" in content', function)
            self.assertIn('decode("utf-8", "strict")', function)
            overflow = subprocess.run(
                ["bash", "-c", function +
                 '\nbounded_command_capture "$1" -c "$2"',
                 "bounded-inspector", sys.executable,
                 "import os; os.write(1, b'x' * 1048577)"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False)
            self.assertNotEqual(overflow.returncode, 0, script_name)
            self.assertEqual(overflow.stdout, "", script_name)
            self.assertIn("exceeded its output byte ceiling",
                          overflow.stderr, script_name)

            accepted = subprocess.run(
                ["bash", "-c", function +
                 '\nbounded_command_capture "$1" -c "$2"',
                 "bounded-inspector", sys.executable,
                 "print('bounded output')"], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(accepted.stdout, "bounded output\n")
            self.assertNotIn('inspection="$("$harness" mcp get', script)
            self.assertNotIn('inspection="$("$client" mcp get', script)
            self.assertNotIn('inspection="$(grok mcp list', script)
            self.assertIn("bounded_command_capture", script.split(
                "inspect_mcp_server() {", 1)[1])

    def test_command_runners_kill_descendants_before_reaping_leader(self):
        child_program = (
            "import os,time\n"
            "child=os.fork()\n"
            "if child == 0:\n"
            "    time.sleep(300)\n"
            "else:\n"
            "    print(child, flush=True)\n")

        def non_zombie(pid):
            try:
                with open(f"/proc/{pid}/stat", encoding="ascii") as stream:
                    fields = stream.read().split()
            except FileNotFoundError:
                return False
            return len(fields) > 2 and fields[2] != "Z"

        for script_name in ("install.sh", "uninstall.sh"):
            script = _read(script_name)
            bounded_body = script.split(
                "bounded_command_capture() {", 1)[1].split("\n}\n", 1)[0]
            bounded = "bounded_command_capture() {" + bounded_body + "\n}\n"
            deadline_body = script.split(
                "run_with_deadline() {", 1)[1].split("\n}\n", 1)[0]
            deadline = "run_with_deadline() {" + deadline_body + "\n}\n"
            self.assertIn("os.WNOWAIT", deadline)
            self.assertIn("os.pidfd_open(process.pid, 0)", deadline)
            self.assertLess(
                deadline.index("kill_group()\n    status = process.wait()"),
                deadline.index("selector.close()"))
            cases = (
                (bounded,
                 '\nbounded_command_capture "$1" -c "$2"'),
                (deadline,
                 '\nrun_with_deadline 120 "$1" -c "$2"'),
            )
            for function, invocation in cases:
                with self.subTest(script=script_name,
                                  runner=invocation.split()[0]):
                    result = subprocess.run(
                        ["bash", "-c", function + invocation,
                         "runner-descendant-test", sys.executable,
                         child_program], text=True, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    child_pid = int(result.stdout.strip())
                    # status=exact parsed=1/(1/100) exact=100 and
                    # parsed=1/100 exact=1/100; not formal-bounded.
                    for _ in range(100):
                        if not non_zombie(child_pid):
                            break
                        time.sleep(0.01)
                    self.assertFalse(non_zombie(child_pid))

    def test_external_mcp_shapes_create_durable_nonownership_guards(self):
        installer = _read("install.sh")
        agents = installer.split('step "9/9 agents', 1)[1]
        functions = _owned_metadata_shell(installer) + \
            "durable_replace_file() {" + agents.split(
            "durable_replace_file() {", 1)[1].split(
                "\nregister_mcp_server claude", 1)[0]
        fixtures = {
            ("claude", "exact-unmarked"): (
                'echo "sia:"\n'
                'echo "  Scope: User config (available in all your projects)"\n'
                'echo "  Status: Disconnected"\n'
                'echo "  Type: stdio"\n'
                'echo "  Command: python3"\n'
                'echo "  Args: $HOME/.local/share/sia/bin/sia-mcp"\n'
                'echo "  Environment:"\n'
                'echo\n'),
            ("claude", "modified-reference"): (
                'echo "sia:"\n'
                'echo "  Scope: User config (available in all your projects)"\n'
                'echo "  Status: Connected"\n'
                'echo "  Type: stdio"\n'
                'echo "  Command: python3"\n'
                'echo "  Args: $HOME/.local/share/sia/bin/sia-mcp"\n'
                'echo "  Environment:"\n'
                'echo "    SIA_EXTERNAL: true"\n'
                'echo\n'),
            ("codex", "exact-unmarked"): (
                'echo "sia"\n'
                'echo "  enabled: true"\n'
                'echo "  transport: stdio"\n'
                'echo "  command: python3"\n'
                'echo "  args: $HOME/.local/share/sia/bin/sia-mcp"\n'
                'echo "  cwd: -"\n'
                'echo "  env: -"\n'),
            ("codex", "modified-reference"): (
                'echo "sia"\n'
                'echo "  enabled: true"\n'
                'echo "  transport: stdio"\n'
                'echo "  command: python3"\n'
                'echo "  args: $HOME/.local/share/sia/bin/sia-mcp"\n'
                'echo "  cwd: /tmp"\n'
                'echo "  env: -"\n'),
            ("grok", "exact-unmarked"): (
                'printf \'[{"name":"sia","command":"python3",'
                '"args":["%s"],"enabled":true,"scope":"user"}]\\n\' '
                '"$HOME/.local/share/sia/bin/sia-mcp"\n'),
            ("grok", "modified-reference"): (
                'printf \'[{"name":"sia","command":"python3",'
                '"args":["%s","--external"],"enabled":true,'
                '"scope":"user"}]\\n\' '
                '"$HOME/.local/share/sia/bin/sia-mcp"\n'),
        }
        for (client, reason), inspection in fixtures.items():
            with self.subTest(client=client, reason=reason), \
                    tempfile.TemporaryDirectory() as root:
                home = os.path.join(root, "home")
                fake_bin = os.path.join(root, "bin")
                trace = os.path.join(root, "trace")
                marker_dir = os.path.join(
                    home, ".local/state/sia/managed-mcp")
                guard_dir = os.path.join(
                    home, ".local/state/sia/mcp-consumer-guards")
                runtime = os.path.join(home, ".local/share/sia/bin")
                os.makedirs(fake_bin)
                os.makedirs(marker_dir)
                os.makedirs(guard_dir)
                _fake_command(
                    fake_bin, client,
                    f'echo "{client} $*" >> "$TRACE"\n' + inspection)
                environment = os.environ.copy()
                environment.update({
                    "HOME": home,
                    "PATH": fake_bin + os.pathsep + environment["PATH"],
                    "TRACE": trace,
                })
                script = (
                    "set -euo pipefail\n"
                    f"MCP_MARKER_DIR={marker_dir!r}\n"
                    f"MCP_GUARD_DIR={guard_dir!r}\n"
                    f"BINDIR={runtime!r}\n"
                    "have() { command -v \"$1\" >/dev/null 2>&1; }\n" +
                    functions + f"\nregister_mcp_server {client}\n")
                result = subprocess.run(
                    ["bash", "-c", script], env=environment, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                guard = os.path.join(guard_dir, client)
                self.assertEqual(_read_path(guard),
                                 _mcp_guard_contents(home, client, reason))
                self.assertFalse(os.path.lexists(
                    os.path.join(marker_dir, client)))
                calls = _read_path(trace)
                self.assertNotIn("mcp add", calls)
                self.assertNotIn("mcp remove", calls)

    def test_pending_mcp_reference_cannot_launder_owned_add_into_guard(self):
        installer = _read("install.sh")
        agents = installer.split('step "9/9 agents', 1)[1]
        functions = _owned_metadata_shell(installer) + \
            "durable_replace_file() {" + agents.split(
            "durable_replace_file() {", 1)[1].split(
                "\nregister_mcp_server claude", 1)[0]
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            trace = os.path.join(root, "trace")
            added = os.path.join(root, "added")
            marker_dir = os.path.join(
                home, ".local/state/sia/managed-mcp")
            guard_dir = os.path.join(
                home, ".local/state/sia/mcp-consumer-guards")
            runtime = os.path.join(home, ".local/share/sia/bin")
            os.makedirs(fake_bin)
            os.makedirs(marker_dir)
            os.makedirs(guard_dir)
            _fake_command(
                fake_bin, "claude",
                'echo "claude $*" >> "$TRACE"\n'
                'if [ "$1 $2 $3" = "mcp get sia" ]; then\n'
                '  if [ ! -e "$ADDED" ]; then\n'
                '    echo "No MCP server named sia" >&2\n'
                '    exit 1\n'
                '  fi\n'
                '  echo "sia:"\n'
                '  echo "  Scope: User config (available in all your projects)"\n'
                '  echo "  Status: Connected"\n'
                '  echo "  Type: stdio"\n'
                '  echo "  Command: python3"\n'
                '  echo "  Args: $HOME/.local/share/sia/bin/sia-mcp"\n'
                '  echo "  Environment:"\n'
                '  echo "  New Field: benign display-format drift"\n'
                '  echo\n'
                '  exit 0\n'
                'fi\n'
                'if [ "$1 $2 $3 $4 $5" = "mcp add --scope user sia" ]; then\n'
                '  : > "$ADDED"\n'
                '  exit 0\n'
                'fi\n'
                'exit 1\n')
            environment = os.environ.copy()
            environment.update({
                "HOME": home,
                "PATH": fake_bin + os.pathsep + environment["PATH"],
                "TRACE": trace,
                "ADDED": added,
            })
            script = (
                "set -euo pipefail\n"
                f"MCP_MARKER_DIR={marker_dir!r}\n"
                f"MCP_GUARD_DIR={guard_dir!r}\n"
                f"BINDIR={runtime!r}\n"
                "have() { command -v \"$1\" >/dev/null 2>&1; }\n" +
                functions +
                "\nfirst=accepted\n"
                "register_mcp_server claude || first=refused\n"
                "second=accepted\n"
                "register_mcp_server claude || second=refused\n"
                "printf 'first=%s second=%s\\n' \"$first\" \"$second\"\n")
            result = subprocess.run(
                ["bash", "-c", script], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout.endswith(
                "first=accepted second=accepted\n"), result.stdout)
            marker = os.path.join(marker_dir, "claude")
            self.assertFalse(os.path.lexists(marker))
            self.assertFalse(os.path.lexists(
                os.path.join(guard_dir, "claude")))
            self.assertFalse(os.path.lexists(added))
            self.assertEqual(
                _read_path(trace),
                "claude mcp get sia\n"
                "claude mcp get sia\n")

    def test_committed_and_legacy_mcp_references_retain_owned_markers(self):
        installer = _read("install.sh")
        agents = installer.split('step "9/9 agents', 1)[1]
        functions = _owned_metadata_shell(installer) + \
            "\ndurable_replace_file() {" + agents.split(
            "durable_replace_file() {", 1)[1].split(
                "\nregister_mcp_server claude", 1)[0]
        marker_bodies = {
            "committed": (
                "managed-by=khephri.sia\nstate=committed\n"
                "command=python3\narg={runtime}/sia-mcp\n"),
            "legacy": (
                "managed-by=khephri.sia\ncommand=python3\n"
                "arg={runtime}/sia-mcp\n"),
        }
        for marker_state, template in marker_bodies.items():
            with self.subTest(marker_state=marker_state), \
                    tempfile.TemporaryDirectory() as root:
                home = os.path.join(root, "home")
                fake_bin = os.path.join(root, "bin")
                trace = os.path.join(root, "trace")
                marker_dir = os.path.join(
                    home, ".local/state/sia/managed-mcp")
                guard_dir = os.path.join(
                    home, ".local/state/sia/mcp-consumer-guards")
                runtime = os.path.join(home, ".local/share/sia/bin")
                os.makedirs(fake_bin)
                os.makedirs(marker_dir)
                os.makedirs(guard_dir)
                marker = os.path.join(marker_dir, "claude")
                expected_marker = template.format(runtime=runtime)
                _write(marker, expected_marker)
                _fake_command(
                    fake_bin, "claude",
                    'echo "claude $*" >> "$TRACE"\n'
                    'echo "sia:"\n'
                    'echo "  Scope: User config (available in all your projects)"\n'
                    'echo "  Status: Connected"\n'
                    'echo "  Type: stdio"\n'
                    'echo "  Command: python3"\n'
                    'echo "  Args: $HOME/.local/share/sia/bin/sia-mcp"\n'
                    'echo "  Environment:"\n'
                    'echo "  New Field: benign display-format drift"\n'
                    'echo\n')
                environment = os.environ.copy()
                environment.update({
                    "HOME": home,
                    "PATH": fake_bin + os.pathsep + environment["PATH"],
                    "TRACE": trace,
                })
                script = (
                    "set -euo pipefail\n"
                    f"MCP_MARKER_DIR={marker_dir!r}\n"
                    f"MCP_GUARD_DIR={guard_dir!r}\n"
                    f"BINDIR={runtime!r}\n"
                    "have() { command -v \"$1\" >/dev/null 2>&1; }\n" +
                    functions +
                    "\nresult=accepted\n"
                    "register_mcp_server claude || result=refused\n"
                    "printf 'result=%s\\n' \"$result\"\n")
                result = subprocess.run(
                    ["bash", "-c", script], env=environment, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "result=refused\n")
                self.assertEqual(_read_path(marker), expected_marker)
                self.assertFalse(os.path.lexists(
                    os.path.join(guard_dir, "claude")))
                self.assertEqual(_read_path(trace), "claude mcp get sia\n")

    def test_uninstaller_preserves_state_and_reports_each_integration(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            trace = os.path.join(root, "trace")
            os.makedirs(fake_bin)
            for client in ("claude", "codex"):
                if client == "claude":
                    inspection = (
                        '  echo "sia:"\n'
                        '  echo "  Scope: User config (available in all your projects)"\n'
                        '  echo "  Status: Connected"\n'
                        '  echo "  Type: stdio"\n'
                        '  echo "  Command: python3"\n'
                        '  echo "  Args: $HOME/.local/share/sia/bin/sia-mcp"\n'
                        '  echo "  Environment:"\n'
                        '  echo\n')
                else:
                    inspection = (
                        '  echo "sia"\n'
                        '  echo "  enabled: true"\n'
                        '  echo "  transport: stdio"\n'
                        '  echo "  command: python3"\n'
                        '  echo "  args: $HOME/.local/share/sia/bin/sia-mcp"\n'
                        '  echo "  cwd: -"\n'
                        '  echo "  env: -"\n')
                _fake_command(
                    fake_bin, client,
                    'echo "' + client + ' $*" >> "$TRACE"\n'
                    'if [ "$1 $2 $3" = "mcp get sia" ]; then\n'
                    '  if [ -f "$HOME/.' + client + '-removed" ]; then\n'
                    '    echo "No MCP server named sia" >&2\n'
                    '    exit 1\n'
                    '  fi\n' + inspection +
                    '  exit 0\n'
                    'fi\n'
                    'if [ "$1 $2" = "mcp remove" ]; then\n'
                    '  touch "$HOME/.' + client + '-removed"\n'
                    'fi\n'
                    'exit 0\n')
            _fake_command(
                fake_bin, "grok",
                'echo "grok $*" >> "$TRACE"\n'
                'if [ "$1 $2 $3" = "mcp list --json" ]; then\n'
                '  if [ -f "$HOME/.grok-removed" ]; then echo "[]"; exit 0; fi\n'
                '  echo "[{\\"name\\":\\"sia\\",\\"command\\":\\"python3\\",'
                '\\"args\\":[\\"$HOME/.local/share/sia/bin/sia-mcp\\"],'
                '\\"enabled\\":true,\\"scope\\":\\"user\\"}]"\n'
                '  exit 0\n'
                'fi\n'
                'if [ "$1 $2" = "mcp remove" ]; then touch "$HOME/.grok-removed"; fi\n'
                'exit 0\n')
            _fake_command(
                fake_bin, "systemctl",
                'echo "systemctl $*" >> "$TRACE"\n'
                'if [ "$1 $2" = "--user show" ]; then\n'
                '  if [ -f "$HOME/.brainstem-masked" ]; then\n'
                '    echo "LoadState=masked"; echo "ActiveState=inactive"\n'
                '    echo "UnitFileState=masked-runtime"\n'
                '    fragment=/dev/null; main_pid=0\n'
                '  elif [ -f "$HOME/.brainstem-disabled" ]; then\n'
                '    echo "LoadState=loaded"\n'
                '    echo "ActiveState=inactive"; echo "UnitFileState=disabled"\n'
                '    fragment=$HOME/.config/systemd/user/sia-brainstem.service\n'
                '    main_pid=0\n'
                '  else\n'
                '    echo "LoadState=loaded"\n'
                '    echo "ActiveState=active"; echo "UnitFileState=enabled"\n'
                '    fragment=$HOME/.config/systemd/user/sia-brainstem.service\n'
                '    main_pid=123\n'
                '  fi\n'
                '  echo "FragmentPath=$fragment"\n'
                '  echo "DropInPaths="; echo "MainPID=$main_pid"\n'
                '  exit 0\n'
                'fi\n'
                'if [ "$1 $2 $3" = "--user mask --runtime" ]; then\n'
                '  touch "$HOME/.brainstem-masked" "$HOME/.brainstem-disabled"\n'
                'fi\n'
                'if [ "$1 $2 $3" = "--user unmask --runtime" ]; then\n'
                '  mv "$HOME/.brainstem-masked" "$HOME/.brainstem-unmasked"\n'
                'fi\n'
                'if [ "$1 $2 $3" = "--user disable --now" ]; then\n'
                '  touch "$HOME/.brainstem-disabled"\n'
                'fi\n'
                'exit 0\n')
            _fake_command(fake_bin, "omarchy",
                          'echo "omarchy $*" >> "$TRACE"\nexit 0\n')
            _fake_command(fake_bin, "hyprctl",
                          'echo "hyprctl $*" >> "$TRACE"\nexit 0\n')

            paths = {
                "corpus": ".local/share/sia/corpus/memory.md",
                "runtime": ".local/share/sia/bin/sialib.py",
                "pin": ".local/share/sia/GBRAIN_PIN",
                "queue": ".local/state/sia/agent-queue/request.json",
                "config": ".config/sia/config.json",
                "cli": ".local/bin/sia",
                "unit": ".config/systemd/user/sia-brainstem.service",
                "skill": ".claude/skills/sia/SKILL.md",
                "plugin": ".config/omarchy/plugins/khephri.sia/local.txt",
            }
            for relative in paths.values():
                _write(os.path.join(home, relative), relative + "\n")
            runtime_dir = os.path.join(home, ".local/share/sia/bin")
            for name in ("sia-brainstem", "sia-ledger", "sia-mcp",
                         "siabench.py", "sialib.py", "siamind.py",
                         "siaqueue.py", "siatakes.py"):
                runtime_path = os.path.join(runtime_dir, name)
                if not os.path.exists(runtime_path):
                    _write(runtime_path, name + "\n")
            managed_dir = os.path.join(
                home, ".local/state/sia/managed-install")
            unit_path = os.path.join(home, paths["unit"])
            cli_path = os.path.join(home, paths["cli"])
            _write(os.path.join(managed_dir, "sia-brainstem.service"),
                   _managed_file_receipt(unit_path, "brainstem-unit"))
            _write(os.path.join(managed_dir, "sia-cli"),
                   _managed_file_receipt(cli_path, "sia-cli"))
            _write(
                os.path.join(managed_dir, "runtime"),
                "managed-by=khephri.sia\nkind=runtime\n"
                f"path={runtime_dir}\nsha256={_runtime_digest(runtime_dir)}\n")
            skill_path = os.path.join(home, paths["skill"])
            skill_hash = hashlib.sha256(
                _read_path(skill_path).encode("utf-8")).hexdigest()
            _write(os.path.join(home, ".claude/skills/sia/.sia-managed"),
                   "managed-by=khephri.sia\n"
                   f"skill_sha256={skill_hash}\n")
            for client in ("claude", "codex", "grok"):
                _write(os.path.join(
                    home, ".local/state/sia/managed-mcp", client),
                    "managed-by=khephri.sia\ncommand=python3\n"
                    f"arg={home}/.local/share/sia/bin/sia-mcp\n")
            bindings = os.path.join(home, ".config/hypr/bindings.lua")
            _write(bindings, "before\n-- BEGIN SIA\nmanaged\n-- END SIA\nafter\n")

            environment = os.environ.copy()
            environment.update({
                "HOME": home,
                "PATH": fake_bin + os.pathsep + environment["PATH"],
                "TRACE": trace,
                "HYPRLAND_INSTANCE_SIGNATURE": "test-instance",
            })
            result = subprocess.run(
                ["bash", os.path.join(REPO, "uninstall.sh")],
                cwd=REPO, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

            for key in ("corpus", "queue", "config"):
                self.assertTrue(os.path.exists(os.path.join(home, paths[key])))
            for key in ("unit", "skill", "plugin"):
                self.assertFalse(os.path.exists(os.path.join(home, paths[key])))
            for key in ("runtime", "pin", "cli"):
                self.assertTrue(os.path.exists(os.path.join(home, paths[key])))
            plugin_parent = os.path.join(home, ".config/omarchy/plugins")
            backups = [name for name in os.listdir(plugin_parent)
                       if name.startswith(".khephri.sia.removed.")]
            self.assertEqual(len(backups), 1)
            self.assertTrue(os.path.isfile(os.path.join(
                plugin_parent, backups[0], "local.txt")))
            self.assertEqual(_read_path(bindings), "before\nafter\n")
            calls = _read_path(trace)
            self.assertNotIn("mcp remove", calls)
            self.assertIn("no compare-and-remove API", result.stdout)
            self.assertIn("systemctl --user daemon-reload", calls)
            self.assertIn("hyprctl reload", calls)
            self.assertIn("hyprctl configerrors", calls)
            self.assertIn("uninstall completed successfully", result.stdout)

    def test_uninstaller_holds_owner_leases_through_verified_purge(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            purge_entered = os.path.join(root, "purge-entered")
            purge_continue = os.path.join(root, "purge-continue")
            contender_attempted = os.path.join(root, "contender-attempted")
            contender_acquired = os.path.join(root, "contender-acquired")
            os.makedirs(fake_bin)
            _write(os.path.join(
                home, ".local/share/sia/corpus/memory.md"), "retained\n")
            _fake_command(fake_bin, "systemctl", ABSENT_USER_UNIT)
            for client in ("claude", "codex"):
                _fake_command(
                    fake_bin, client,
                    'echo "No MCP server named sia" >&2\nexit 1\n')
            _fake_command(fake_bin, "grok", 'echo "[]"\n')
            _fake_command(
                fake_bin, "rm",
                'if [ "$#" -eq 3 ] && [ "$1" = -rf ] && [ "$2" = -- ] '
                '&& [ "$3" = "$HOME/.local/state/sia" ]; then\n'
                '  : > "$PURGE_ENTERED"\n'
                '  while [ ! -e "$PURGE_CONTINUE" ]; do /usr/bin/sleep 0.01; done\n'
                'fi\n'
                'exec /usr/bin/rm "$@"\n')
            environment = os.environ.copy()
            environment.update({
                "HOME": home,
                "PATH": fake_bin + os.pathsep + environment["PATH"],
                "PURGE_ENTERED": purge_entered,
                "PURGE_CONTINUE": purge_continue,
            })
            uninstaller = subprocess.Popen(
                ["bash", os.path.join(REPO, "uninstall.sh"), "--purge"],
                cwd=REPO, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            contender = None
            try:
                deadline = time.monotonic() + 30
                while not os.path.exists(purge_entered):
                    if uninstaller.poll() is not None:
                        stdout, stderr = uninstaller.communicate()
                        self.fail(
                            "uninstaller exited before purge gate: "
                            f"{stdout}\n{stderr}")
                    if time.monotonic() >= deadline:
                        self.fail("uninstaller did not reach the purge gate")
                    time.sleep(0.01)

                lock_path = os.path.join(
                    home, ".local/state/sia/corpus-owner.lock")
                probe = subprocess.run(
                    ["flock", "-n", lock_path, "true"],
                    env=environment, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, check=False)
                self.assertNotEqual(
                    probe.returncode, 0,
                    "corpus owner lease was released before purge")

                contender_code = (
                    "import fcntl, os, sys\n"
                    "fd = os.open(sys.argv[1], os.O_RDWR)\n"
                    "open(sys.argv[2], 'w').close()\n"
                    "fcntl.flock(fd, fcntl.LOCK_EX)\n"
                    "state = 'after-purge' if all("
                    "not os.path.lexists(path) for path in sys.argv[4:]) "
                    "else 'before-purge'\n"
                    "with open(sys.argv[3], 'w', encoding='utf-8') as stream:\n"
                    "    stream.write(state + '\\n')\n")
                contender = subprocess.Popen(
                    [sys.executable, "-c", contender_code, lock_path,
                     contender_attempted, contender_acquired,
                     os.path.join(home, ".local/state/sia"),
                     os.path.join(home, ".local/share/sia"),
                     os.path.join(home, ".config/sia")],
                    env=environment, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True)
                while not os.path.exists(contender_attempted):
                    if contender.poll() is not None:
                        stdout, stderr = contender.communicate()
                        self.fail(
                            "owner-lock contender exited before flock: "
                            f"{stdout}\n{stderr}")
                    if time.monotonic() >= deadline:
                        self.fail("owner-lock contender did not start")
                    time.sleep(0.01)
                self.assertFalse(os.path.exists(contender_acquired))

                _write(purge_continue, "continue\n")
                stdout, stderr = uninstaller.communicate(timeout=30)
                self.assertEqual(uninstaller.returncode, 0, stderr)
                self.assertIn("purge verified:", stdout)
                contender_stdout, contender_stderr = contender.communicate(
                    timeout=30)
                self.assertEqual(contender.returncode, 0,
                                 contender_stdout + contender_stderr)
                self.assertEqual(_read_path(contender_acquired),
                                 "after-purge\n")
            finally:
                if not os.path.exists(purge_continue):
                    _write(purge_continue, "continue\n")
                for process in (contender, uninstaller):
                    if process is not None and process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=30)

    def test_uninstaller_preserves_unowned_mcp_registration(self):
        uninstaller = _read("uninstall.sh")
        self.assertIn('marker="$MCP_MARKER_DIR/$client"', uninstaller)
        marker_guard = uninstaller.split("remove_managed_mcp()", 1)[1].split(
            "remove_managed_skill()", 1)[0]
        self.assertIn("exact unowned $client MCP registration preserved",
                      marker_guard)
        self.assertIn("RUNTIME_NEEDED_BY_MCP=1", marker_guard)

    def test_uninstaller_behavior_preserves_exact_unmarked_mcp_runtime(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            trace = os.path.join(root, "trace")
            os.makedirs(fake_bin)
            cli, runtime = _managed_cli_runtime(home)
            _fake_command(fake_bin, "systemctl", ABSENT_USER_UNIT)
            _fake_command(
                fake_bin, "claude",
                'echo "claude $*" >> "$TRACE"\n'
                'echo "sia:"\n'
                'echo "  Scope: User config (available in all your projects)"\n'
                'echo "  Status: Disconnected"\n'
                'echo "  Type: stdio"\n'
                'echo "  Command: python3"\n'
                'echo "  Args: $HOME/.local/share/sia/bin/sia-mcp"\n'
                'echo "  Environment:"\n'
                'echo\n')
            _fake_command(
                fake_bin, "codex",
                'echo "No MCP server named sia" >&2\nexit 1\n')
            _fake_command(fake_bin, "grok", 'echo "[]"\n')
            environment = os.environ.copy()
            environment.update({"HOME": home,
                                "PATH": fake_bin + os.pathsep
                                + environment["PATH"],
                                "TRACE": trace})
            result = subprocess.run(
                ["bash", os.path.join(REPO, "uninstall.sh")],
                cwd=REPO, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.isfile(cli))
            self.assertTrue(os.path.isdir(runtime))
            self.assertIn("exact unowned claude MCP registration preserved",
                          result.stdout)
            calls = _read_path(trace) if os.path.exists(trace) else ""
            self.assertNotIn("mcp remove", calls)
            guard = os.path.join(
                home, ".local/state/sia/mcp-consumer-guards/claude")
            self.assertEqual(
                _read_path(guard),
                _mcp_guard_contents(home, "claude", "exact-unmarked"))

    def test_uninstaller_keeps_owned_markers_on_mcp_format_drift(self):
        marker_bodies = {
            "pending": (
                "managed-by=khephri.sia\nstate=pending-add\n"
                "command=python3\narg={runtime}/sia-mcp\n"),
            "committed": (
                "managed-by=khephri.sia\nstate=committed\n"
                "command=python3\narg={runtime}/sia-mcp\n"),
            "legacy": (
                "managed-by=khephri.sia\ncommand=python3\n"
                "arg={runtime}/sia-mcp\n"),
            "invalid": "invalid ownership marker\n",
        }
        for marker_state, template in marker_bodies.items():
            with self.subTest(marker_state=marker_state), \
                    tempfile.TemporaryDirectory() as root:
                home = os.path.join(root, "home")
                fake_bin = os.path.join(root, "bin")
                trace = os.path.join(root, "trace")
                os.makedirs(fake_bin)
                cli, runtime = _managed_cli_runtime(home)
                marker = os.path.join(
                    home, ".local/state/sia/managed-mcp/claude")
                expected_marker = template.format(runtime=runtime)
                _write(marker, expected_marker)
                _fake_command(fake_bin, "systemctl", ABSENT_USER_UNIT)
                _fake_command(
                    fake_bin, "claude",
                    'echo "claude $*" >> "$TRACE"\n'
                    'echo "sia:"\n'
                    'echo "  Scope: User config (available in all your projects)"\n'
                    'echo "  Status: Connected"\n'
                    'echo "  Type: stdio"\n'
                    'echo "  Command: python3"\n'
                    'echo "  Args: $HOME/.local/share/sia/bin/sia-mcp"\n'
                    'echo "  Environment:"\n'
                    'echo "  New Field: benign display-format drift"\n'
                    'echo\n')
                _fake_command(
                    fake_bin, "codex",
                    'echo "No MCP server named sia" >&2\nexit 1\n')
                _fake_command(fake_bin, "grok", 'echo "[]"\n')
                environment = os.environ.copy()
                environment.update({
                    "HOME": home,
                    "PATH": fake_bin + os.pathsep + environment["PATH"],
                    "TRACE": trace,
                })
                result = subprocess.run(
                    ["bash", os.path.join(REPO, "uninstall.sh")],
                    cwd=REPO, env=environment, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(os.path.isfile(cli))
                self.assertTrue(os.path.isdir(runtime))
                self.assertEqual(_read_path(marker), expected_marker)
                self.assertFalse(os.path.lexists(os.path.join(
                    home,
                    ".local/state/sia/mcp-consumer-guards/claude")))
                self.assertNotIn("mcp remove", _read_path(trace))
                if marker_state == "invalid":
                    self.assertIn("invalid claude MCP ownership marker",
                                  result.stderr)
                else:
                    self.assertIn(
                        "registration references SIA but no longer verifies exactly; owned marker retained",
                        result.stderr)

    def test_uninstaller_guard_overrides_stale_ownership_marker(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            trace = os.path.join(root, "trace")
            os.makedirs(fake_bin)
            cli, runtime = _managed_cli_runtime(home)
            _write(os.path.join(
                home, ".local/state/sia/managed-mcp/claude"),
                "managed-by=khephri.sia\nstate=committed\ncommand=python3\n"
                f"arg={runtime}/sia-mcp\n")
            guard = os.path.join(
                home, ".local/state/sia/mcp-consumer-guards/claude")
            _write(guard, _mcp_guard_contents(
                home, "claude", "modified-reference"))
            _fake_command(fake_bin, "systemctl", ABSENT_USER_UNIT)
            _fake_command(
                fake_bin, "claude",
                'echo "claude $*" >> "$TRACE"\n'
                'echo "sia:"\n'
                'echo "  Scope: User config (available in all your projects)"\n'
                'echo "  Status: Connected"\n'
                'echo "  Type: stdio"\n'
                'echo "  Command: python3"\n'
                'echo "  Args: $HOME/.local/share/sia/bin/sia-mcp"\n'
                'echo "  Environment:"\n'
                'echo\n')
            _fake_command(
                fake_bin, "codex",
                'echo "No MCP server named sia" >&2\nexit 1\n')
            _fake_command(fake_bin, "grok", 'echo "[]"\n')
            environment = os.environ.copy()
            environment.update({
                "HOME": home,
                "PATH": fake_bin + os.pathsep + environment["PATH"],
                "TRACE": trace,
            })
            result = subprocess.run(
                ["bash", os.path.join(REPO, "uninstall.sh")],
                cwd=REPO, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.isfile(cli))
            self.assertTrue(os.path.isdir(runtime))
            self.assertTrue(os.path.isfile(guard))
            self.assertTrue(os.path.isfile(os.path.join(
                home, ".local/state/sia/managed-mcp/claude")))
            calls = _read_path(trace) if os.path.exists(trace) else ""
            self.assertNotIn("mcp remove", calls)
            self.assertIn("preserved by its durable non-ownership guard",
                          result.stdout)

    def test_generic_external_mcp_guard_preserves_cli_and_runtime(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            os.makedirs(fake_bin)
            cli, runtime = _managed_cli_runtime(home)
            generic_guard = os.path.join(
                home,
                ".local/state/sia/mcp-consumer-guards/my-resident-agent")
            _write(generic_guard, "operator guard: external MCP consumer\n")
            _fake_command(fake_bin, "systemctl", ABSENT_USER_UNIT)
            for client in ("claude", "codex"):
                _fake_command(
                    fake_bin, client,
                    'echo "No MCP server named sia" >&2\nexit 1\n')
            _fake_command(fake_bin, "grok", 'echo "[]"\n')
            environment = os.environ.copy()
            environment.update({
                "HOME": home,
                "PATH": fake_bin + os.pathsep + environment["PATH"],
            })
            result = subprocess.run(
                ["bash", os.path.join(REPO, "uninstall.sh")],
                cwd=REPO, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.isfile(cli))
            self.assertTrue(os.path.isdir(runtime))
            self.assertTrue(os.path.isfile(generic_guard))
            self.assertIn("durable external MCP consumer guard(s)",
                          result.stdout)

    def test_uninstaller_preserves_runtime_when_systemd_is_indeterminate(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            os.makedirs(fake_bin)
            cli, runtime = _managed_cli_runtime(home)
            _fake_command(fake_bin, "systemctl",
                          'echo "user manager unavailable" >&2\nexit 1\n')
            for client in ("claude", "codex"):
                _fake_command(
                    fake_bin, client,
                    'echo "No MCP server named sia" >&2\nexit 1\n')
            _fake_command(fake_bin, "grok", 'echo "[]"\n')
            environment = os.environ.copy()
            environment.update({"HOME": home,
                                "PATH": fake_bin + os.pathsep
                                + environment["PATH"]})
            result = subprocess.run(
                ["bash", os.path.join(REPO, "uninstall.sh"), "--purge"],
                cwd=REPO, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(os.path.isfile(cli))
            self.assertTrue(os.path.isdir(runtime))
            self.assertIn("inspect sia-brainstem.service state",
                          result.stderr)
            self.assertIn("purge blocked", result.stderr)

    def test_plugin_disable_failure_preserves_plugin_binding_cli_and_runtime(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            os.makedirs(fake_bin)
            cli, runtime = _managed_cli_runtime(home)
            plugin = os.path.join(
                home, ".config/omarchy/plugins/khephri.sia")
            binding = os.path.join(home, ".config/hypr/bindings.lua")
            _write(os.path.join(plugin, "manifest.json"), "{}\n")
            _write(binding, "before\n-- BEGIN SIA\nmanaged\n-- END SIA\n")
            _fake_command(fake_bin, "systemctl", ABSENT_USER_UNIT)
            _fake_command(fake_bin, "omarchy", "exit 1\n")
            for client in ("claude", "codex"):
                _fake_command(
                    fake_bin, client,
                    'echo "No MCP server named sia" >&2\nexit 1\n')
            _fake_command(fake_bin, "grok", 'echo "[]"\n')
            environment = os.environ.copy()
            environment.update({"HOME": home,
                                "PATH": fake_bin + os.pathsep
                                + environment["PATH"]})
            result = subprocess.run(
                ["bash", os.path.join(REPO, "uninstall.sh")],
                cwd=REPO, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(os.path.isdir(plugin))
            self.assertEqual(_read_path(binding),
                             "before\n-- BEGIN SIA\nmanaged\n-- END SIA\n")
            self.assertTrue(os.path.isfile(cli))
            self.assertTrue(os.path.isdir(runtime))
            self.assertIn("disable Omarchy plugin", result.stderr)

    def test_uninstaller_preserves_unmanaged_agent_skill(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            os.makedirs(fake_bin)
            _fake_command(
                fake_bin, "systemctl", ABSENT_USER_UNIT)
            skill_path = os.path.join(
                home, ".claude/skills/sia/SKILL.md")
            _write(skill_path, "user-owned skill\n")
            environment = os.environ.copy()
            environment.update({
                "HOME": home,
                "PATH": fake_bin + os.pathsep + environment["PATH"],
            })
            result = subprocess.run(
                ["bash", os.path.join(REPO, "uninstall.sh")],
                cwd=REPO, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.isfile(skill_path))
            self.assertIn("agent skill preserved", result.stdout)

    def test_uninstaller_returns_nonzero_and_names_failures(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            trace = os.path.join(root, "trace")
            os.makedirs(fake_bin)
            _fake_command(fake_bin, "systemctl", ABSENT_USER_UNIT)
            _fake_command(fake_bin, "hyprctl",
                          '[ "$1" != configerrors ]\n')
            bindings = os.path.join(home, ".config/hypr/bindings.lua")
            _write(bindings, "-- BEGIN SIA\nmanaged\n-- END SIA\n")
            environment = os.environ.copy()
            environment.update({
                "HOME": home,
                "PATH": fake_bin + os.pathsep + environment["PATH"],
                "TRACE": trace,
                "HYPRLAND_INSTANCE_SIGNATURE": "test-instance",
            })
            result = subprocess.run(
                ["bash", os.path.join(REPO, "uninstall.sh")],
                cwd=REPO, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("validate Hyprland configuration", result.stderr)
            self.assertIn("uninstall completed with", result.stderr)
            self.assertEqual(
                _read_path(bindings),
                "-- BEGIN SIA\nmanaged\n-- END SIA\n")

    def test_uninstaller_blocks_purge_when_brainstem_cannot_stop(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            trace = os.path.join(root, "trace")
            os.makedirs(fake_bin)
            _fake_command(
                fake_bin, "systemctl",
                'echo "$*" >> "$TRACE"\n'
                'if [ "$1 $2" = "--user show" ]; then\n'
                '  echo "LoadState=loaded"; echo "ActiveState=active"\n'
                '  echo "FragmentPath=$HOME/.config/systemd/user/sia-brainstem.service"\n'
                '  echo "UnitFileState=enabled"; echo "DropInPaths="\n'
                '  echo "MainPID=123"; exit 0\n'
                'fi\n'
                'case "$*" in *"mask --runtime --now sia-brainstem.service"*) '
                'exit 1;; esac\nexit 0\n')
            retained = (
                ".local/share/sia/bin/sialib.py",
                ".local/share/sia/corpus/memory.md",
                ".local/state/sia/queue/request.json",
                ".config/sia/config.json",
                ".config/systemd/user/sia-brainstem.service",
            )
            for relative in retained:
                _write(os.path.join(home, relative), "must survive\n")
            unit = os.path.join(home, retained[-1])
            _write(os.path.join(
                home, ".local/state/sia/managed-install/"
                "sia-brainstem.service"),
                _managed_file_receipt(unit, "brainstem-unit"))
            environment = os.environ.copy()
            environment.update({
                "HOME": home,
                "PATH": fake_bin + os.pathsep + environment["PATH"],
                "TRACE": trace,
            })
            result = subprocess.run(
                ["bash", os.path.join(REPO, "uninstall.sh"), "--purge"],
                cwd=REPO, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(result.returncode, 0)
            for relative in retained:
                self.assertTrue(os.path.isfile(os.path.join(home, relative)),
                                relative)
            self.assertIn("runtime preserved", result.stderr)
            self.assertIn("purge blocked", result.stderr)
            self.assertIn(
                "--user mask --runtime --now sia-brainstem.service",
                _read_path(trace))

    def test_uninstaller_preserves_incomplete_keybinding_block_and_tail(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "home")
            fake_bin = os.path.join(root, "bin")
            os.makedirs(fake_bin)
            _fake_command(
                fake_bin, "systemctl", ABSENT_USER_UNIT)
            bindings = os.path.join(home, ".config/hypr/bindings.lua")
            original = ("before\n-- BEGIN SIA "
                        "(managed by khephri.sia/install.sh)\n"
                        "managed\nuser tail must survive\n")
            _write(bindings, original)
            environment = os.environ.copy()
            environment.update({
                "HOME": home,
                "PATH": fake_bin + os.pathsep + environment["PATH"],
            })
            result = subprocess.run(
                ["bash", os.path.join(REPO, "uninstall.sh")],
                cwd=REPO, env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(_read_path(bindings), original)
            self.assertIn("malformed SIA keybinding markers preserved",
                          result.stderr)
            self.assertIn("uninstall completed with", result.stderr)

    def test_repository_contains_no_symlinks(self):
        for root, dirs, files in os.walk(REPO):
            if ".git" in dirs:
                dirs.remove(".git")
            for name in dirs + files:
                path = os.path.join(root, name)
                self.assertFalse(os.path.islink(path),
                                 os.path.relpath(path, REPO))

    def test_ci_discovers_the_tests_directory_and_promotes_resource_leaks(self):
        workflow = _read(".github/workflows/ci.yml")
        self.assertRegex(workflow, r"(?m)^permissions:\n  contents: read$")
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("unittest discover -s tests -v", workflow)
        self.assertIn("PYTHONWARNINGS: error::ResourceWarning", workflow)
        self.assertIn("python3 -m json.tool manifest.json", workflow)
        self.assertIn("python3 -m json.tool config.example.json", workflow)
        self.assertIn("test -s schema-pack/pack.yaml", workflow)
        self.assertIn("test -s preview.png", workflow)
        self.assertIn("git diff --check", workflow)
        self.assertIn("koalaman/shellcheck-alpine@sha256:", workflow)
        self.assertIn("--network none --cap-drop all", workflow)
        self.assertIn("shellcheck /mnt/install.sh /mnt/uninstall.sh", workflow)
        uses = re.findall(r"uses:\s+([^@\s]+)@([^\s#]+)", workflow)
        self.assertTrue(uses)
        for action, revision in uses:
            self.assertRegex(revision, r"^[0-9a-f]{40}$", action)
        self.assertIn("actions/checkout@"
                      "3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
                      workflow)
        self.assertIn("actions/setup-python@"
                      "5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0",
                      workflow)
        self.assertNotIn("pip install cryptography", workflow)
        self.assertIn("cryptography==50.0.1", workflow)
        self.assertIn("cffi==2.0.0", workflow)
        self.assertIn("pycparser==3.0", workflow)
        self.assertIn("--only-binary=:all: --require-hashes", workflow)
        self.assertIn(
            "ff838d62ec1bfce4f9ba7fa16f4a7b554cd8d0c299e6be37502161a660c84eef",
            workflow)
        self.assertIn("https://pypi.org/pypi/cryptography/50.0.1/json",
                      workflow)

    def test_cockpit_and_bar_share_the_configured_stale_threshold(self):
        cockpit = _read("Cockpit.qml")
        panel = _read("Panel.qml")
        model = _read("Model.js")
        manifest = json.loads(_read("manifest.json"))
        defaults = manifest["barWidget"]["defaults"]
        self.assertIn("staleAfterSec", defaults)
        schema = next(item for item in manifest["barWidget"]["schema"]
                      if item["key"] == "staleAfterSec")
        self.assertEqual(defaults["staleAfterSec"], schema["defaultValue"])
        for function, expected in (
                ("staleAfterMinSec", schema["min"]),
                ("staleAfterMaxSec", schema["max"]),
                ("staleAfterDefaultSec", schema["defaultValue"])):
            self.assertRegex(
                model,
                rf"function {function}\(\) \{{ return {expected} \}}")
        self.assertIn("validStaleAfterSec", cockpit)
        self.assertIn("validStaleAfterSec", panel)
        self.assertIn("root.shell.shellConfig", cockpit)
        self.assertIn("root.staleAfterSec * 1000", cockpit)
        self.assertIn("root.staleAfterSec * 1000", panel)
        self.assertNotRegex(cockpit, r">\s*240\s*\*\s*1000")

    def test_recovery_boundaries_are_operator_visible(self):
        readme = _read("README.md")
        manual = _read("docs/MANUAL.md")
        changelog = _read("CHANGELOG.md")
        for document in (readme, manual, changelog):
            self.assertIn("corpus-bootstrap", document)
            self.assertIn("corpus-adoption", document)
            self.assertIn("GENESIS:init", document)
            self.assertIn("gbrain-bootstrap", document)
        for document in (readme, manual):
            self.assertIn("prepared", document)
            self.assertIn("publishing", document)
            self.assertIn("published", document)
            self.assertIn("valid preexisting database", document)
        self.assertIn("`key.hex`, then the matching `pub.hex`", readme)
        self.assertIn("one canonical signed", readme)
        self.assertIn("`GENESIS:init` row in `ledger.tsv`", readme)
        self.assertIn("then the matching `head.pin`", readme)
        self.assertNotIn("before it begins mutation", readme)
        self.assertNotIn("Before mutation, the installer", manual)
        self.assertNotRegex(
            manual,
            r"(?m)^\s*(?:rm|mv)\s+[^\n]*[.]gbrain(?:/|\s|$)")

    def test_agent_note_privacy_boundary_is_consistent(self):
        readme = _read("README.md")
        manual = _read("docs/MANUAL.md")
        skill = _read("skill/SKILL.md")
        mcp = _read("bin/sia-mcp")
        for document in (readme, manual, skill, mcp):
            self.assertIn("credentials", document)
            self.assertIn("persist", document.lower())
        self.assertIn("secrecy guarantee", readme)
        self.assertIn("secrecy guarantee", manual)
        self.assertIn("no cloud or external network calls", skill)
        self.assertIn("no cloud or external network calls", manual)


if __name__ == "__main__":
    unittest.main(verbosity=2)
