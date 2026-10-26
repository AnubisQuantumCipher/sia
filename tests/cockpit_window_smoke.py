#!/usr/bin/env python3
"""Opt-in, disposable Wayland cockpit/CLI test; not an installed-runtime claim."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def prepare(output, actual_host=False):
    output.mkdir(mode=0o700)
    shutil.copyfile(Path(__file__), output / "runner.py")
    home = output / "home"
    home.mkdir(mode=0o700)
    runtime = output / "runtime"
    runtime.mkdir(mode=0o700)
    config = output / "shell"
    if actual_host:
        shutil.copytree("/usr/share/omarchy/shell", config)
        plugin = home / ".config/omarchy/plugins/khephri.sia"
    else:
        config.mkdir()
        plugin = config / "plugin"
    plugin.mkdir(parents=True)
    source = [*ROOT.glob("*.qml"), ROOT / "Model.js", ROOT / "manifest.json"]
    for path in source:
        shutil.copyfile(path, plugin / path.name)
    if not actual_host:
        shutil.copyfile(ROOT / "tests/fixtures/cockpit-window/shell.qml",
                        config / "shell.qml")
        for part in ("Commons", "Ui"):
            shutil.copytree(Path("/usr/share/omarchy/shell") / part, config / part)
    fake = home / ".local/bin/sia"
    fake.parent.mkdir(parents=True)
    fake.write_text("#!/bin/sh\nexit 1\n")
    fake.chmod(0o700)
    (output / "bin").mkdir()
    for path in [*ROOT.glob("bin/*.py"), ROOT / "bin/sia"]:
        shutil.copyfile(path, output / "bin" / path.name)
    seed_display(home, output)
    return output, home, runtime, config


def launch_environment(home, runtime):
    # No inherited provider keys, session bus, compositor address or user
    # startup configuration. Host binaries/libraries remain test assumptions.
    return {
        "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
        "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_RUNTIME_DIR": str(runtime), "QT_QPA_PLATFORM": "wayland",
        "QT_QUICK_BACKEND": "software", "QSG_RENDER_LOOP": "basic",
        "WLR_BACKENDS": "headless", "WLR_RENDERER": "pixman",
        "WLR_LIBINPUT_NO_DEVICES": "1",
    }


def seed_display(home, output):
    """Existing deterministic test data, never a copy of private live state."""
    sys.path.insert(0, str(ROOT))
    from tests.test_cockpit_boundary_horizon import CockpitBoundaryHorizonTests
    from tests.test_cockpit_integrity_boundaries import CockpitIntegrityBoundaries
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    version = json.loads((ROOT / "manifest.json").read_text())["version"]
    graph = CockpitIntegrityBoundaries._graph()
    graph["ts"] = now
    graph["nodes"][0].update({"ts": now, "title": "FIXTURE — SIA"})
    status = CockpitBoundaryHorizonTests()._snapshot(
        version=version, ts=now, day=now[:10], state="ok", pages=1,
        graph_nodes=1, graph_edges=0, graph_publication_id=graph["publication_id"])
    status["integrity"]["checked_at"] = now
    state = home / ".local/state/sia"
    state.mkdir(parents=True)
    for name, value in (("status.json", status), ("graph.json", graph),
                        ("thoughts.json", [])):
        (state / name).write_text(json.dumps(value))
    completion = state / "managed-install"
    completion.mkdir()
    (completion / "first-light.json").write_text(json.dumps({
        "v": 1, "version": version, "state": "ready"}))
    for name in ("test_cockpit_boundary_horizon.py", "test_cockpit_integrity_boundaries.py"):
        shutil.copyfile(ROOT / "tests" / name, output / name)


def run_wayland(output, config, home, component_runner):
    with tempfile.TemporaryDirectory(prefix="sia-win-") as short_runtime:
        environment = launch_environment(home, Path(short_runtime))
        environment["OMARCHY_PATH"] = str(output)
        sway_config = output / "sway.conf"
        sway_config.write_text(
            'swaybg_command -\nxwayland disable\noutput HEADLESS-1 mode 1280x800\n'
            'for_window [title="^SIA — Omarchy Brain$"] floating enable\n')
        with (output / "sway.log").open("wb") as log:
            compositor = subprocess.Popen(
                ["/usr/bin/sway", "--config", str(sway_config)],
                env=environment, stdout=log, stderr=subprocess.STDOUT)
            try:
                for _ in range(80):
                    displays = list(Path(short_runtime).glob("wayland-*"))
                    displays = [p for p in displays if p.is_socket()]
                    sockets = list(Path(short_runtime).glob("sway-ipc.*.sock"))
                    if len(displays) == len(sockets) == 1:
                        environment["WAYLAND_DISPLAY"] = displays[0].name
                        environment["SWAYSOCK"] = str(sockets[0])
                        return component_runner(output, config, environment)
                    if compositor.poll() is not None:
                        return compositor.returncode
                    time.sleep(0.05)
                return 124
            finally:
                retire(compositor)


def run_public_cli(output, environment):
    with (output / "cli.log").open("wb") as log:
        result = subprocess.run(
            [sys.executable, str(output / "bin/sia"), "cockpit", "--window"],
            env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=8,
            check=False)
    return result.returncode == 0 and \
        "SIA cockpit window requested" in (output / "cli.log").read_text()


def compositor_command(output, environment, action, name):
    with (output / name).open("wb") as receipt:
        result = subprocess.run(
            ["/usr/bin/swaymsg", "-s", environment["SWAYSOCK"],
             '[title="^SIA — Omarchy Brain$"] ' + action],
            env=environment, stdout=receipt, stderr=subprocess.STDOUT,
            timeout=2, check=False)
    if (output / name).stat().st_size > 4096:
        return False
    rows = json.loads((output / name).read_text())
    return result.returncode == 0 and isinstance(rows, list) and bool(rows) and all(
        isinstance(row, dict) and row.get("success") is True for row in rows)


def resized_client(output, environment):
    if not compositor_command(output, environment,
                              "resize set width 1024 px height 700 px",
                              "compositor-resize.json"):
        return False
    with (output / "compositor-tree.json").open("wb") as log:
        result = subprocess.run(
            ["/usr/bin/swaymsg", "-s", environment["SWAYSOCK"], "-t", "get_tree"],
            env=environment, stdout=log, stderr=subprocess.STDOUT,
            timeout=2, check=False)
    path = output / "compositor-tree.json"
    if result.returncode != 0 or path.stat().st_size > 65536:
        return False
    pending = [json.loads(path.read_text())]
    for _ in range(128):
        if not pending:
            return False
        node = pending.pop()
        if node.get("name") == "SIA — Omarchy Brain":
            outer, client = node["rect"], node["window_rect"]
            # sway-ipc(7): rect includes borders but excludes decorations;
            # window_rect is the actual Qt client area. The resize command
            # sizes the decorated floating container.
            decorated_height = outer["height"] + node["deco_rect"]["height"]
            if (outer["width"], decorated_height) != (1024, 700):
                return False
            result = subprocess.run(
                ["/usr/bin/quickshell", "ipc", "-n", "-p", str(output / "shell"),
                 "call", "--", "fixture", "observedSize",
                 str(client["width"]), str(client["height"])],
                env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=2, check=False, text=True)
            return result.returncode == 0 and result.stdout.strip() == "ok"
        pending.extend(node.get("nodes", []) + node.get("floating_nodes", []))
        if len(pending) > 128:
            return False
    return False


def capture_window(output, environment, name="fixture-window.png"):
    return subprocess.run(
        ["/usr/bin/grim", str(output / name)], env=environment,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=3, check=False).returncode == 0


def mapped_window(text):
    pending = [json.loads(text)]
    matches = 0
    for _ in range(128):
        if not pending:
            return matches == 1
        node = pending.pop()
        if node.get("name") == "SIA — Omarchy Brain" and node.get("visible") is True:
            matches += 1
        pending.extend(node.get("nodes", []) + node.get("floating_nodes", []))
        if len(pending) > 128:
            return False
    return False


def await_mapped_window(output, environment):
    # An acknowledged open precedes asynchronous Wayland mapping. Observe
    # that mapping before sending the one compositor close; never retry close.
    for attempt in range(20):
        path = output / f"before-close-{attempt}.json"
        with path.open("wb") as log:
            result = subprocess.run(
                ["/usr/bin/swaymsg", "-s", environment["SWAYSOCK"], "-t", "get_tree"],
                env=environment, stdout=log, stderr=subprocess.STDOUT,
                timeout=2, check=False)
        if result.returncode != 0 or path.stat().st_size > 65536:
            return False
        if mapped_window(path.read_text()):
            return True
        time.sleep(0.02)
    return False


def retire(process):
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def monitor_component(process, output, environment):
    closed = cli_called = captured = resized = resize_requested = False
    cli_ok = close_ok = capture_ok = resize_ok = resize_command_ok = False
    for _ in range(500):
        if (output / "runtime.log").stat().st_size > 1048576:
            return 1
        text = (output / "runtime.log").read_text(errors="replace")
        if "Configuration Loaded" in text and not cli_called:
            cli_called = True
            cli_ok = run_public_cli(output, environment)
        if '"label":"window-open","pass":true' in text and not captured:
            captured = True
            capture_ok = capture_window(output, environment)
        if "SIA-WINDOW-RESIZED" in text and not resized:
            resized = True
            resize_ok = capture_window(output, environment, "fixture-resized.png")
        if "SIA-WINDOW-AWAIT-COMPOSITOR-RESIZE" in text and not resize_requested:
            resize_requested = True
            resize_command_ok = resized_client(output, environment)
        if "SIA-WINDOW-AWAIT-COMPOSITOR-CLOSE" in text and not closed:
            closed = True
            close_ok = (await_mapped_window(output, environment) and
                        compositor_command(
                            output, environment, "kill", "compositor-close.json"))
        if process.poll() is not None:
            status = process.wait()
            okay = cli_ok and close_ok and capture_ok and resize_ok and resize_command_ok
            return status if okay else 1
        time.sleep(0.05)
    return 124


def run_component(output, config, environment):
    command = ["timeout", "--kill-after=5s", "20s", "/usr/bin/quickshell",
               "--no-color", "-p", str(config)]
    with (output / "runtime.log").open("wb") as log:
        process = subprocess.Popen(command, env=environment, stdout=log,
                                   stderr=subprocess.STDOUT)
        try:
            return monitor_component(process, output, environment)
        finally:
            retire(process)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    output, home, _runtime, config = prepare(options.output.resolve())
    files = sorted(path for path in output.rglob("*") if path.is_file())
    if len(files) > 512:
        raise ValueError("fixture file capacity")
    receipt = {"status": "UNRUN", "scope": "disposable-headless-wayland-full-component",
               "files": {
                   str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in files}}
    receipt["tools"] = {
        path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
        for path in ("/usr/bin/quickshell", "/usr/bin/sway", "/usr/bin/omarchy-shell",
                     "/usr/bin/swaymsg", "/usr/bin/grim", sys.executable)}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    try:
        status = run_wayland(output, config, home, run_component)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError) as error:
        status = 1
        receipt["failure_type"] = type(error).__name__
    log = output / "runtime.log"
    text = log.read_text(errors="replace") if log.exists() else ""
    passed = status == 0 and "SIA-WINDOW-RESULT TESTED" in text
    receipt.update({"status": "TESTED" if passed else "FAILED",
                    "exit": status})
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "exit": status,
                      "output": str(output)}))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
