#!/usr/bin/env python3
"""Marketplace guided first-light and runtime-generation contract."""

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = Path(__file__).resolve().parent.parent
RELEASE_VERSION = "1.7.0"


def _read(relative):
    return (REPO / relative).read_text(encoding="utf-8")


def _balanced_body(source, marker):
    """Return the brace-balanced body following *marker*."""
    start = source.index(marker) + len(marker)
    opening = source.index("{", start)
    depth = 0
    quote = None
    escaped = False
    for index in range(opening, len(source)):
        char = source[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:index]
    raise AssertionError(f"unterminated body after {marker!r}")


def _completed_handlers(source):
    """Extract Component.onCompleted handlers, including one-line forms."""
    handlers = []
    pattern = re.compile(r"Component\.onCompleted\s*:\s*")
    for match in pattern.finditer(source):
        remainder = source[match.end():]
        if remainder.startswith("{"):
            handlers.append(_balanced_body(source, match.group(0)))
        else:
            handlers.append(remainder.splitlines()[0])
    return handlers


def _load_sialib():
    path = REPO / "bin" / "sialib.py"
    name = "sialib_marketplace_first_light_test"
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    bin_path = str(path.parent)
    sys.path.insert(0, bin_path)
    try:
        loader.exec_module(module)
    finally:
        sys.path.remove(bin_path)
    return module


class MarketplaceFirstLightTests(unittest.TestCase):
    def _model_call(self, function_name, *arguments):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is unavailable for executable Model.js check")
        script = r'''
const fs = require("fs")
const vm = require("vm")
const source = fs.readFileSync(process.argv[1], "utf8")
  .replace(/^\.pragma library\s*$/m, "")
const context = {}
vm.createContext(context)
vm.runInContext(source, context)
const args = JSON.parse(process.argv[3])
process.stdout.write(String(context[process.argv[2]].apply(null, args)))
'''
        result = subprocess.run(
            [node, "-e", script, str(REPO / "Model.js"), function_name,
             json.dumps(arguments, separators=(",", ":"))],
            cwd=REPO, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def _model_lifecycle(self, status, plugin_version):
        return self._model_call(
            "runtimeLifecycle", status, plugin_version)

    def test_absent_and_mismatched_runtime_are_explicit_lifecycle_gates(self):
        self.assertEqual(
            self._model_lifecycle(None, RELEASE_VERSION), "setup")
        self.assertEqual(
            self._model_lifecycle({}, RELEASE_VERSION), "repair")
        legacy_status = {
            "v": 1,
            "ts": "2026-09-01T00:00:00Z",
            "state": "ready",
            "publication_id": "legacy-publication",
            "projection_debt": {"graph": "", "consolidation": ""},
            "mind": {
                "nodes": 0, "edges": 0, "decay_active": 0,
                "decay_demoted": 0, "rehearsal_eligible": 0,
                "rehearsal_due": 0, "pinned": 0},
            "agent_queue": {
                "materialized": 0, "refused": 0, "acknowledged": 0},
        }
        self.assertEqual(
            self._model_lifecycle(legacy_status, RELEASE_VERSION), "update")
        self.assertEqual(
            self._model_lifecycle({"version": "1.4.2"}, RELEASE_VERSION),
            "update")
        self.assertEqual(
            self._model_lifecycle(
                {"version": RELEASE_VERSION}, RELEASE_VERSION),
            "ready")
        self.assertEqual(
            self._model_lifecycle({"version": "1.7.1"}, RELEASE_VERSION),
            "ahead")
        self.assertEqual(
            self._model_lifecycle({"version": "1.5"}, RELEASE_VERSION),
            "repair")

        installing = {
            "v": 1, "version": RELEASE_VERSION, "state": "installing"}
        ready = {"v": 1, "version": RELEASE_VERSION, "state": "ready"}
        self.assertEqual(
            self._model_call(
                "guidedLifecycle", None, None, RELEASE_VERSION),
            "setup")
        self.assertEqual(
            self._model_call(
                "guidedLifecycle", None, ready, RELEASE_VERSION),
            "repair")
        self.assertEqual(
            self._model_call(
                "guidedLifecycle", None, installing, RELEASE_VERSION),
            "installing")
        self.assertEqual(
            self._model_call(
                "guidedLifecycle", {"version": "1.4.2"}, installing,
                RELEASE_VERSION),
            "installing")
        self.assertEqual(
            self._model_call(
                "guidedLifecycle", {"version": RELEASE_VERSION}, None,
                RELEASE_VERSION),
            "repair")
        self.assertEqual(
            self._model_call(
                "guidedLifecycle", {"version": RELEASE_VERSION}, ready,
                RELEASE_VERSION),
            "ready")
        self.assertEqual(
            self._model_call(
                "guidedLifecycle", {"version": "1.7.1"}, installing,
                RELEASE_VERSION),
            "ahead")
        newer_ready = {"v": 1, "version": "1.7.1", "state": "ready"}
        self.assertEqual(
            self._model_call(
                "guidedLifecycle", None, newer_ready, RELEASE_VERSION),
            "ahead")

        model = _read("Model.js")
        self.assertIn(
            f'function releaseVersion() {{ return "{RELEASE_VERSION}" }}',
            model)
        for surface in ("Panel.qml", "Cockpit.qml"):
            source = _read(surface)
            self.assertIn("Model.guidedLifecycle(", source, surface)
            self.assertIn('"setup"', source, surface)
            self.assertIn("update", source.casefold(), surface)
            self.assertIn("repair", source.casefold(), surface)
            self.assertIn("ahead", source.casefold(), surface)

    def test_every_published_brain_status_is_release_stamped(self):
        sialib = _load_sialib()
        self.assertEqual(sialib.VERSION, RELEASE_VERSION)
        with tempfile.TemporaryDirectory() as root:
            status_path = os.path.join(root, "status.json")
            with mock.patch.object(sialib, "STATUS_PATH", status_path):
                sialib.export_status({"state": "ok"})
            with open(status_path, encoding="utf-8") as stream:
                status = json.load(stream)
        self.assertEqual(status["version"], RELEASE_VERSION)

    def test_cockpit_unlock_requires_the_post_ready_completion_record(self):
        model = _read("Model.js")
        self.assertIn("function installCompletionReady(", model)
        for surface in ("Panel.qml", "Cockpit.qml"):
            source = _read(surface)
            self.assertIn("Model.guidedLifecycle(", source, surface)
            self.assertIn("managed-install/first-light.json", source, surface)
            self.assertIn("releaseLifecycle", source, surface)

        installer = _read("install.sh")
        installing = installer.index(
            'publish_first_light_state "$REPO/bin" installing')
        first_runtime_step = installer.index(
            'step "1/9 private restic + bun + pinned gbrain')
        final_ready = installer.rindex(
            'run_with_deadline 120 "$CLI_PATH" ready')
        completion = installer.rindex(
            'publish_first_light_state "$BINDIR" ready')
        self.assertLess(installing, first_runtime_step)
        self.assertLess(final_ready, completion)
        self.assertIn("mode=0o600", installer)
        self.assertIn(
            "stat.S_IMODE(published.st_mode) != 0o600", installer)
        self.assertIn("remove_first_light_completion", _read("uninstall.sh"))

    def test_completion_publication_replaces_a_permissive_mode_atomically(self):
        sialib = _load_sialib()
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            state = base / "state"
            managed = state / "managed-install"
            share = base / "share"
            corpus = share / "corpus"
            managed.mkdir(parents=True)
            corpus.mkdir(parents=True)
            target = managed / "first-light.json"
            target.write_text('{"state":"old"}', encoding="utf-8")
            target.chmod(0o644)
            with mock.patch.object(sialib, "STATE", str(state)), \
                    mock.patch.object(sialib, "SHARE", str(share)), \
                    mock.patch.object(sialib, "CORPUS", str(corpus)):
                sialib.atomic_write(
                    str(target), '{"state":"ready"}', mode=0o600)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(
                target.read_text(encoding="utf-8"), '{"state":"ready"}')

    def test_setup_launch_is_an_explicit_argv_only_cockpit_action(self):
        cockpit = _read("Cockpit.qml")
        panel = _read("Panel.qml")
        self.assertIn("readonly property string setupHelperPath:", cockpit)
        self.assertIn("/bin/sia-setup", cockpit)
        launch = _balanced_body(cockpit, "function launchSetup()")
        compact_launch = " ".join(launch.split())
        self.assertIn(
            '"/usr/bin/env", "-u", "BASH_ENV", "-u", "ENV",',
            compact_launch)
        self.assertIn('root.setupHelperPath, "launch"', compact_launch)
        self.assertNotRegex(launch, r"\b(?:ba)?sh\b")
        self.assertRegex(cockpit, r"onClicked\s*:\s*root\.launchSetup\(\)")
        self.assertIn(
            "if (!root.setupActionAllowed || root.setupLaunchRequested) return",
            cockpit)
        self.assertIn("!event.isAutoRepeat", cockpit)
        self.assertIn("visible: root.setupActionAllowed", cockpit)
        self.assertIn("enabled: !root.setupRequired", cockpit)
        self.assertIn("Accessible.name:", cockpit)
        self.assertIn("Model.guidedLifecycle(", cockpit)
        self.assertGreaterEqual(cockpit.count("onLoadFailed:"), 2)

        for surface in (panel, cockpit):
            for handler in _completed_handlers(surface):
                self.assertNotIn("launchSetup", handler)
                self.assertNotIn("execDetached", handler)
                self.assertNotIn("sia-setup", handler)
                self.assertNotIn("install.sh", handler)

    def test_setup_helper_opens_a_visible_locked_installer_without_shell_code(self):
        path = REPO / "bin" / "sia-setup"
        self.assertTrue(path.is_file())
        self.assertTrue(stat.S_IMODE(path.stat().st_mode) & stat.S_IXUSR)
        helper = path.read_text(encoding="utf-8")
        compact = " ".join(helper.split())

        syntax = subprocess.run(
            ["bash", "-n", str(path)], cwd=REPO, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        self.assertNotRegex(helper, r"(?m)(?:^|[;&|()\s])eval(?:\s|$)")
        self.assertNotRegex(helper, r"\b(?:bash|sh)\s+-c\b")
        self.assertIn("exec uwsm-app -- xdg-terminal-exec", compact)
        self.assertIn("--hold", helper)
        self.assertIn("XDG_RUNTIME_DIR", helper)
        self.assertNotIn("/tmp", helper)
        self.assertIn("install -d -m 0700", compact)
        self.assertIn("umask 077", compact)
        self.assertIn("flock -n", compact)
        self.assertRegex(helper, r'exec\s+"\$INSTALLER"')
        self.assertIn("unset BASH_ENV ENV", helper)

        consent_variables = (
            "SIA_ADOPT_EXISTING_CORPUS",
            "SIA_ALLOW_UNPINNED_OLLAMA",
            "SIA_INSTALL_KEYBINDING",
            "SIA_REPLACE_AGENT_SKILL",
            "SIA_REPLACE_BRAINSTEM_UNIT",
            "SIA_REPLACE_CONTINUITY_UNITS",
            "SIA_REPLACE_GBRAIN_PIN",
            "SIA_REPLACE_NOMIC_LATEST",
            "SIA_REPLACE_OLLAMA_RUNTIME",
            "SIA_REPLACE_OLLAMA_UNIT",
            "SIA_REPLACE_PLUGIN",
            "SIA_REPLACE_RUNTIME",
            "SIA_REPLACE_SCHEMA_PACK",
            "SIA_REPLACE_SIA_CLI",
            "SIA_REPLACE_TOOLCHAIN",
        )
        unset_at = helper.index("unset BASH_ENV ENV")
        exec_at = helper.index('exec "$INSTALLER"')
        self.assertLess(unset_at, exec_at)
        for variable in consent_variables:
            self.assertIn(variable, helper)

        with tempfile.TemporaryDirectory() as root:
            plugin = Path(root) / "plugin"
            helper_copy = plugin / "bin" / "sia-setup"
            helper_copy.parent.mkdir(parents=True)
            shutil.copy2(path, helper_copy)
            checker = plugin / "install.sh"
            checker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                + "names=(" + " ".join(consent_variables) + ")\n"
                + "for name in \"${names[@]}\"; do\n"
                + "  if [[ -v \"$name\" ]]; then exit 3; fi\n"
                + "done\n",
                encoding="utf-8")
            checker.chmod(0o700)
            bash_env = Path(root) / "bash-env"
            bash_env.write_text(
                "export SIA_REPLACE_RUNTIME=1\n", encoding="utf-8")
            home = Path(root) / "home"
            runtime = Path(root) / "runtime"
            home.mkdir()
            runtime.mkdir()
            environment = os.environ.copy()
            environment.update({name: "1" for name in consent_variables})
            environment.update({
                "HOME": str(home), "XDG_RUNTIME_DIR": str(runtime),
                "BASH_ENV": str(bash_env), "ENV": str(bash_env)})
            cleaned = subprocess.run(
                [str(helper_copy), "run"], cwd=plugin, env=environment,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False)
            self.assertEqual(cleaned.returncode, 0, cleaned.stderr)

        installer = _read("install.sh")
        desktop = installer.split('step "8/9 desktop', 1)[1].split(
            'step "9/9 agents', 1)[0]
        self.assertIn('"$SIA_PLUGIN_STAGE/bin/sia-setup"', desktop)

    def test_installer_authority_refuses_release_downgrades_under_lease(self):
        guard = REPO / "bin" / "siarelease.py"
        self.assertTrue(guard.is_file())
        installer = _read("install.sh")
        main = installer.split("SIA_RELEASE_FILES=(", 1)[1]
        acquire_at = main.index("acquire_install_lifecycle\n")
        guard_at = main.index(
            'run_with_deadline 120 python3 "$REPO/bin/siarelease.py"')
        mutation_at = main.index("SIA_INSTALL_MUTATED=1")
        self.assertLess(acquire_at, guard_at)
        self.assertLess(guard_at, mutation_at)
        self.assertIn("bin/siarelease.py", main.split("\n)", 1)[0])

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            source = base / "source.py"
            resident = base / "resident.py"
            completion = base / "first-light.json"

            def write_runtime(path, version):
                path.write_text(
                    f'VERSION = "{version}"\n', encoding="utf-8")
                path.chmod(0o600)

            def run_guard():
                return subprocess.run(
                    [sys.executable, str(guard), str(source), str(resident),
                     str(completion)],
                    cwd=REPO, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, check=False)

            write_runtime(source, RELEASE_VERSION)
            write_runtime(resident, "1.4.2")
            allowed = run_guard()
            self.assertEqual(allowed.returncode, 0, allowed.stderr)

            write_runtime(resident, "1.7.1")
            refused_runtime = run_guard()
            self.assertEqual(refused_runtime.returncode, 2)
            self.assertIn("release downgrade refused", refused_runtime.stderr)

            resident.unlink()
            completion.write_text(json.dumps({
                "v": 1, "version": "1.7.1", "state": "ready"}),
                encoding="utf-8")
            completion.chmod(0o600)
            refused_completion = run_guard()
            self.assertEqual(refused_completion.returncode, 2)
            self.assertIn("first-light completion", refused_completion.stderr)

    def test_cockpit_discloses_guided_install_effects_and_downgrade_refusal(self):
        cockpit = _read("Cockpit.qml")
        for phrase in (
                "download pinned restic, Bun, gbrain, and Ollama artifacts",
                "build gbrain",
                "pull the pinned local embedding model",
                "only when no owned brain exists",
                "install or restart user services"):
            self.assertIn(phrase, cockpit)
        self.assertIn("Installation is disabled to prevent a downgrade", cockpit)
        self.assertIn("omarchy plugin update khephri.sia", cockpit)


if __name__ == "__main__":
    unittest.main()
