#!/usr/bin/env python3
"""Marketplace guided first-light and runtime-generation contract."""

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = Path(__file__).resolve().parent.parent
RELEASE_VERSION = "1.7.4"


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
            self._model_lifecycle({"version": "1.7.5"}, RELEASE_VERSION),
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
                "guidedLifecycle", {"version": "1.7.5"}, installing,
                RELEASE_VERSION),
            "ahead")
        newer_ready = {"v": 1, "version": "1.7.5", "state": "ready"}
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

    def test_ready_generation_stays_visible_during_file_refresh(self):
        for surface in ("Panel.qml", "Cockpit.qml"):
            source = _read(surface)
            self.assertIn("property bool statusResolved: false", source)
            self.assertIn(
                "property bool installCompletionResolved: false", source)

            status_view = source[
                source.index("id: statusFile"):
                source.index("id: statusApply")]
            self.assertIn("onLoaded:", status_view)
            self.assertIn("root.statusResolved = true", status_view)
            self.assertLess(
                status_view.index("root.applyStatus(text())"),
                status_view.index("root.statusResolved = true"))
            self.assertIn("onLoadFailed:", status_view)
            self.assertIn("onFileChanged:", status_view)
            self.assertIn("statusApply.restart()", status_view)
            self.assertNotIn("root.statusResolved = false", status_view)

            completion_view = source[
                source.index("id: installCompletionFile"):
                source.index("id: installCompletionApply")]
            self.assertIn("onLoaded:", completion_view)
            self.assertIn(
                "root.installCompletionResolved = true", completion_view)
            self.assertLess(
                completion_view.index("root.applyInstallCompletion(text())"),
                completion_view.index(
                    "root.installCompletionResolved = true"))
            self.assertIn("onLoadFailed:", completion_view)
            self.assertIn("root.installCompletion = null", completion_view)
            self.assertIn("onFileChanged:", completion_view)
            self.assertIn("installCompletionApply.restart()", completion_view)
            self.assertIn(
                "root.installCompletionResolved = false", completion_view)

        cockpit = _read("Cockpit.qml")
        open_body = _balanced_body(cockpit, "function open(payloadJson)")
        self.assertIn("statusFile.reload()", open_body)
        self.assertIn("installCompletionFile.reload()", open_body)
        self.assertNotIn("statusResolved = false", open_body)
        self.assertNotIn("installCompletionResolved = false", open_body)
        self.assertIn("function loadedReleaseVersion(ignored)", cockpit)
        self.assertIn("return Model.releaseVersion()", cockpit)

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
        self.assertIn("uwsm-app -- xdg-terminal-exec", compact)
        self.assertIn("--hold", helper)
        # No shipped surface may promise a window this cannot witness.
        for document in ("README.md", "SECURITY.md", "docs/MANUAL.md",
                         "docs/WHITEPAPER.md"):
            with self.subTest(document=document):
                self.assertNotIn("visible terminal", _read(document))
        self.assertIn("XDG_RUNTIME_DIR", helper)
        self.assertNotIn("/tmp", helper)
        self.assertIn("install -d -m 0700", compact)
        self.assertIn("umask 077", compact)
        self.assertIn("flock -n", compact)
        self.assertIn("unset BASH_ENV ENV", helper)
        # F3: visibility is SIA's to own.  xdg-terminal-exec drops --hold on a
        # terminal that declares no TerminalArgHold=, so neither stage may
        # hand its process image away and lose the ability to hold or report.
        self.assertNotIn("exec uwsm-app", compact)
        self.assertNotRegex(helper, r'exec\s+"\$INSTALLER"')
        self.assertRegex(helper, r'(?m)^\s*"\$INSTALLER" &$')
        self.assertRegex(helper, r'(?m)^\s*wait "\$setup_installer_pid"$')
        self.assertIn("trap hold_setup_terminal EXIT", helper)
        # Closing the first-light window delivers SIGHUP; untrapped, the hold
        # would announce a status the installer never produced.
        self.assertIn("trap 'setup_interrupted HUP 129' HUP", helper)
        self.assertIn("SETUP_PRESENT_SECONDS=20", helper)
        self.assertIn("if [ -t 0 ] && [ -t 1 ]; then", helper)
        self.assertRegex(helper, r"(?m)^\s*read -r \|\| true$")

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
        installer_at = helper.index('    "$INSTALLER"')
        publish_at = helper.index(
            'publish_setup_presentation "$setup_attempt"')
        self.assertLess(unset_at, installer_at)
        # The start is recorded before any installer byte runs, so a run
        # that refuses later still proves the run stage started.
        self.assertLess(publish_at, installer_at)
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

    def _first_light_rig(self, root, installer_body, present_seconds=None):
        """Stage a helper copy beside a scripted installer."""
        plugin = Path(root) / "plugin"
        helper = plugin / "bin" / "sia-setup"
        helper.parent.mkdir(parents=True)
        shutil.copy2(REPO / "bin" / "sia-setup", helper)
        if present_seconds is not None:
            source = helper.read_text(encoding="utf-8")
            shortened = source.replace(
                "SETUP_PRESENT_SECONDS=20",
                f"SETUP_PRESENT_SECONDS={present_seconds}")
            self.assertNotEqual(source, shortened)
            helper.write_text(shortened, encoding="utf-8")
        installer = plugin / "install.sh"
        installer.write_text(installer_body, encoding="utf-8")
        installer.chmod(0o700)
        home = Path(root) / "home"
        runtime = Path(root) / "runtime"
        home.mkdir()
        runtime.mkdir()
        environment = os.environ.copy()
        environment.update({
            "HOME": str(home), "XDG_RUNTIME_DIR": str(runtime)})
        return helper, runtime, environment

    # A terminal that gives its child no pty is not a terminal, so the
    # presenting stand-in allocates a real one and answers the hold; the
    # non-presenting one runs nothing at all.
    _PTY_TERMINAL = (
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "argv = sys.argv[1:]\n"
        "argv = argv[argv.index('--') + 1:] if '--' in argv else argv\n"
        "if os.fork():\n"
        "    raise SystemExit(0)\n"
        "os.setsid()\n"
        "leader, follower = os.openpty()\n"
        "if os.fork():\n"
        "    os.close(follower)\n"
        "    while True:\n"
        "        try:\n"
        "            if not os.read(leader, 65536):\n"
        "                break\n"
        "            os.write(leader, b'\\n')\n"
        "        except OSError:\n"
        "            break\n"
        "    raise SystemExit(0)\n"
        "os.close(leader)\n"
        "for stream in (0, 1, 2):\n"
        "    os.dup2(follower, stream)\n"
        "os.execvp(argv[0], argv)\n")

    def _stage_fake_terminal(self, root, environment, presents=True):
        """Stand in for uwsm-app and a terminal that ignores --hold."""
        fake_bin = Path(root) / "bin"
        fake_bin.mkdir()
        launcher = fake_bin / "uwsm-app"
        launcher.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'if [ "${1:-}" = "--" ]; then shift; fi\n'
            'exec "$@"\n', encoding="utf-8")
        launcher.chmod(0o700)
        body = self._PTY_TERMINAL if presents else (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "exit 0\n")
        terminal = fake_bin / "xdg-terminal-exec"
        terminal.write_text(body, encoding="utf-8")
        terminal.chmod(0o700)
        environment["PATH"] = (
            str(fake_bin) + os.pathsep + environment["PATH"])

    def test_setup_run_publishes_presentation_before_the_installer_runs(self):
        attempt = "0123456789abcdef" * 2
        with tempfile.TemporaryDirectory() as root:
            helper, _, environment = self._first_light_rig(
                root,
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                'first_light="$XDG_RUNTIME_DIR/khephri.sia-first-light"\n'
                'stat -c "%a:%h" -- "$first_light/terminal.json" \\\n'
                '  > "$SIA_TEST_REPORT"\n'
                'cat -- "$first_light/terminal.json" >> "$SIA_TEST_REPORT"\n'
                'if flock -n 9; then echo lock-free >> "$SIA_TEST_REPORT"\n'
                'else echo lock-held >> "$SIA_TEST_REPORT"\n'
                'fi 9>>"$first_light/install.lock"\n')
            report = Path(root) / "report"
            environment["SIA_TEST_REPORT"] = str(report)
            result = subprocess.run(
                [str(helper), "run", attempt], cwd=root, env=environment,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=120, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = report.read_text(encoding="utf-8").splitlines()
        # The marker is owner-private and singular exactly like install.lock,
        # and it already exists when the installer's first line runs.
        self.assertEqual(lines[0], "600:1")
        published = json.loads(lines[1])
        self.assertEqual(published["v"], 1)
        self.assertEqual(published["attempt"], attempt)
        self.assertFalse(published["tty"])
        self.assertIsInstance(published["ts"], int)
        self.assertIsInstance(published["pid"], int)
        # Dropping the exec must not drop the lock: this shell now holds the
        # advisory lock for the whole installer run.
        self.assertEqual(lines[2], "lock-held")

    def test_setup_run_propagates_the_installer_exit_status_without_a_hold(
            self):
        for expected in (0, 7):
            with tempfile.TemporaryDirectory() as root:
                helper, _, environment = self._first_light_rig(
                    root,
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    f"exit {expected}\n")
                result = subprocess.run(
                    [str(helper), "run"], cwd=root, env=environment,
                    text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, timeout=120, check=False)
            # Reporting the outcome must never replace it, and a run whose
            # stdin and stdout are pipes must never block on the hold.
            self.assertEqual(result.returncode, expected, result.stderr)
            self.assertIn(f"exit status {expected}", result.stdout)
            self.assertNotIn("Press Enter", result.stdout)

    def test_setup_run_holds_a_real_terminal_and_keeps_the_status(self):
        if not hasattr(os, "openpty"):
            self.skipTest("no pty support for the terminal hold check")
        with tempfile.TemporaryDirectory() as root:
            helper, _, environment = self._first_light_rig(
                root,
                "#!/usr/bin/env bash\nset -euo pipefail\nexit 3\n")
            leader, follower = os.openpty()
            try:
                process = subprocess.Popen(
                    [str(helper), "run"], cwd=root, env=environment,
                    stdin=follower, stdout=follower, stderr=follower,
                    close_fds=True)
                os.close(follower)
                try:
                    process.wait(timeout=5)
                    held = False
                except subprocess.TimeoutExpired:
                    held = True
                    os.write(leader, b"\n")
                    process.wait(timeout=30)
                transcript = b""
                os.set_blocking(leader, False)
                try:
                    while True:
                        chunk = os.read(leader, 65536)
                        if not chunk:
                            break
                        transcript += chunk
                except (BlockingIOError, OSError):
                    pass
            finally:
                os.close(leader)
        # A terminal is exactly where the operator must be able to read the
        # outcome, so the helper waits there and still exits 3.
        self.assertTrue(held)
        self.assertEqual(process.returncode, 3)
        self.assertIn(b"Press Enter when you have read this.", transcript)
        self.assertIn(b"exit status 3", transcript)

    def test_setup_launch_confirms_the_run_stage_actually_started(self):
        with tempfile.TemporaryDirectory() as root:
            helper, runtime, environment = self._first_light_rig(
                root,
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                'printf ran > "$SIA_TEST_REPORT"\n',
                present_seconds=10)
            environment["SIA_TEST_REPORT"] = str(Path(root) / "report")
            self._stage_fake_terminal(root, environment)
            result = subprocess.run(
                [str(helper), "launch"], cwd=root, env=environment,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=120, check=False)
            marker = json.loads(
                (runtime / "khephri.sia-first-light"
                 / "terminal.json").read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("the setup shell started", result.stdout)
        # The wait is bound to a fresh nonce, so an older marker can never
        # be read as this attempt's run stage.
        self.assertRegex(marker["attempt"], r"^[0-9a-f]{32}$")

    def test_setup_launch_refuses_when_the_run_stage_never_starts(self):
        with tempfile.TemporaryDirectory() as root:
            helper, _, environment = self._first_light_rig(
                root,
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                'printf ran > "$SIA_TEST_REPORT"\n',
                present_seconds=2)
            report = Path(root) / "report"
            environment["SIA_TEST_REPORT"] = str(report)
            self._stage_fake_terminal(root, environment, presents=False)
            result = subprocess.run(
                [str(helper), "launch"], cwd=root, env=environment,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=120, check=False)
            ran = report.exists()
        # Exiting 0 into silence was the defect: an unobserved run stage is
        # a named refusal, and in this rig no installer byte ran.
        self.assertEqual(result.returncode, 2)
        self.assertIn("no setup shell started", result.stderr)
        self.assertFalse(ran)

    def test_setup_refuses_a_hostile_pre_existing_presentation_marker(self):
        for stage in ("launch", "run"):
            for name, prepare in (
                    ("symlink", lambda target: target.symlink_to("/etc")),
                    ("mode", lambda target: (
                        target.write_text("{}", encoding="utf-8"),
                        target.chmod(0o644))),
                    ("links", lambda target: (
                        target.write_text("{}", encoding="utf-8"),
                        target.chmod(0o600),
                        os.link(target, target.parent / "shadow")))):
                with tempfile.TemporaryDirectory() as root:
                    helper, runtime, environment = self._first_light_rig(
                        root,
                        "#!/usr/bin/env bash\n"
                        "set -euo pipefail\n"
                        'printf ran > "$SIA_TEST_REPORT"\n',
                        present_seconds=2)
                    report = Path(root) / "report"
                    environment["SIA_TEST_REPORT"] = str(report)
                    self._stage_fake_terminal(root, environment)
                    first_light = runtime / "khephri.sia-first-light"
                    first_light.mkdir(mode=0o700)
                    prepare(first_light / "terminal.json")
                    result = subprocess.run(
                        [str(helper), stage], cwd=root, env=environment,
                        text=True, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, timeout=120, check=False)
                    ran = report.exists()
                label = f"{stage}/{name}"
                # A marker is only ever trusted or replaced under the same
                # ownership rules the install lock already enforces.
                self.assertEqual(result.returncode, 2, label)
                self.assertIn(
                    "presentation marker", result.stderr, label)
                self.assertFalse(ran, label)

    def test_setup_run_stops_the_installer_on_a_directed_signal(self):
        with tempfile.TemporaryDirectory() as root:
            done = Path(root) / "installer-finished"
            helper, _, environment = self._first_light_rig(
                root,
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "sleep 6\n"
                f"printf 'done\\n' > {done}\n")
            child = subprocess.Popen(
                [str(helper), "run", "b" * 32], cwd=root, env=environment,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.5)
            sent = time.monotonic()
            child.send_signal(signal.SIGTERM)
            status = child.wait(timeout=30)
            elapsed = time.monotonic() - sent
            finished = done.exists()
        # bash defers a trap until a foreground command returns, so the
        # installer is waited on: a signal is acted on now, and an install
        # that was stopped is never reported as one that ran.
        self.assertFalse(finished)
        self.assertLess(elapsed, 3.0)
        self.assertEqual(status, 143)

    def test_a_refused_second_attempt_keeps_the_first_attempt_proof(self):
        first = "0" * 31 + "1"
        second = "0" * 31 + "2"
        with tempfile.TemporaryDirectory() as root:
            helper, runtime, environment = self._first_light_rig(
                root,
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                'printf ready > "$SIA_TEST_GATE"\n'
                'while [ ! -e "$SIA_TEST_RELEASE" ]; do sleep 0.05; done\n')
            gate = Path(root) / "gate"
            release = Path(root) / "release"
            environment["SIA_TEST_GATE"] = str(gate)
            environment["SIA_TEST_RELEASE"] = str(release)
            holder = subprocess.Popen(
                [str(helper), "run", first], cwd=root, env=environment,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 30
                while not gate.exists():
                    if time.monotonic() > deadline:
                        self.fail("the first attempt never installed")
                    time.sleep(0.05)
                refused = subprocess.run(
                    [str(helper), "run", second], cwd=root,
                    env=environment, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, timeout=120, check=False)
                first_light = runtime / "khephri.sia-first-light"
                proof = first_light / ("terminal.json." + first)
                # The lock refused the second attempt.  That refusal must
                # not erase the running attempt's proof of presentation.
                self.assertEqual(refused.returncode, 2, refused.stderr)
                self.assertIn("another SIA installer is already running",
                              refused.stderr)
                self.assertTrue(proof.is_file())
                self.assertEqual(
                    json.loads(proof.read_text(encoding="utf-8"))["attempt"],
                    first)
            finally:
                release.write_text("go", encoding="utf-8")
                holder.wait(timeout=60)

    def test_setup_run_refuses_a_malformed_attempt_id(self):
        with tempfile.TemporaryDirectory() as root:
            helper, _, environment = self._first_light_rig(
                root,
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                'printf ran > "$SIA_TEST_REPORT"\n')
            report = Path(root) / "report"
            environment["SIA_TEST_REPORT"] = str(report)
            result = subprocess.run(
                [str(helper), "run", "../../etc"], cwd=root,
                env=environment, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=120, check=False)
            ran = report.exists()
        self.assertEqual(result.returncode, 2)
        self.assertIn("attempt id is malformed", result.stderr)
        self.assertFalse(ran)

    def test_cockpit_reports_presentation_instead_of_promising_it(self):
        cockpit = _read("Cockpit.qml")
        # The old copy promised something no desktop contract can deliver.
        self.assertNotIn("Installation runs visibly in a terminal", cockpit)
        self.assertNotIn("Setup terminal requested. Keep it open;", cockpit)
        self.assertNotIn("Open the visible SIA installer terminal", cockpit)
        self.assertIn(
            "Your click asks this desktop to open a terminal", cockpit)
        self.assertIn(
            "SIA holds that window open at the end, on success and on a "
            "named refusal", cockpit)
        self.assertIn(
            "Setup terminal requested, but SIA never observed the "
            "installer shell start.", cockpit)
        # The helper cannot kill the terminal it asked the session manager
        # for, so neither surface may claim a late window installed nothing.
        self.assertNotIn("nothing was installed", cockpit)
        self.assertNotIn("nothing is installed", cockpit)
        self.assertIn("Setup terminal started.", cockpit)
        # The retired vocabulary claimed a mapped window; the marker only
        # ever witnessed an installer shell starting with a tty attached.
        self.assertNotIn("Setup terminal presented", cockpit)
        self.assertNotIn("actually presented", cockpit)
        self.assertIn("readonly property string setupPresencePath:", cockpit)
        self.assertIn("khephri.sia-first-light/terminal.json", cockpit)
        self.assertIn("Model.setupTerminalPresented(", cockpit)

        presence = cockpit[
            cockpit.index("id: setupPresenceFile"):
            cockpit.index("id: setupPresenceApply")]
        self.assertIn("watchChanges: true", presence)
        self.assertIn("root.applySetupPresence(text())", presence)
        # Observing a marker must not become a second execution edge.
        self.assertNotIn("execDetached", presence)
        self.assertNotIn("Process", presence)
        launch = _balanced_body(cockpit, "function launchSetup()")
        self.assertIn("root.setupRequestedAtSec = ", launch)
        self.assertIn("root.setupAttemptId = Model.drawAttemptId()", launch)
        self.assertIn('root.setupHelperPath, "launch", root.setupAttemptId',
                      launch)
        self.assertIn("setupPresenceDeadline.restart()", launch)
        # An unrequested marker change is worth one reload, never a poll that
        # outlives the wait that asked for it.
        self.assertIn("setupPresenceDeadline.running", presence)
        # A terminal that presents late must not leave the operator with no
        # status at all.
        self.assertIn(
            "visible: root.setupLaunchRequested || root.setupTerminalMissing"
            "\n                || root.setupTerminalPresented", cockpit)

        # Presentation is bound to the id this click drew and to the run
        # stage's own report that it got a terminal.  Anything else — an
        # earlier attempt, a run with no tty, an unstamped marker — is not
        # this click's window.
        attempt = "a1b2c3d4" * 4
        other = "0" * 32
        base = {"v": 1, "ts": 1000, "tty": True, "attempt": attempt}
        for marker, requested, wanted, expected in (
                (base, 1000, attempt, "true"),
                (dict(base, ts=1001), 1000, attempt, "true"),
                (dict(base, ts=999), 1000, attempt, "false"),
                (dict(base, ts="1000"), 1000, attempt, "false"),
                (dict(base, v=2), 1000, attempt, "false"),
                ({"v": 1, "tty": True, "attempt": attempt}, 1000, attempt,
                 "false"),
                (dict(base, tty=False), 1000, attempt, "false"),
                (dict(base, attempt=other), 1000, attempt, "false"),
                (base, 1000, "not-hex", "false"),
                (base, 0, attempt, "false"),
                (None, 1000, attempt, "false")):
            self.assertEqual(
                self._model_call(
                    "setupTerminalPresented", marker, requested, wanted),
                expected, (marker, requested, wanted))
        # The id is drawn per click, so two clicks are never answered by one
        # marker.
        drawn = {self._model_call("drawAttemptId") for _ in range(3)}
        self.assertEqual(len(drawn), 3)
        for value in drawn:
            self.assertRegex(value, r"^[0-9a-f]{32}$")

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

            write_runtime(resident, "1.7.5")
            refused_runtime = run_guard()
            self.assertEqual(refused_runtime.returncode, 2)
            self.assertIn("release downgrade refused", refused_runtime.stderr)

            resident.unlink()
            completion.write_text(json.dumps({
                "v": 1, "version": "1.7.5", "state": "ready"}),
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
