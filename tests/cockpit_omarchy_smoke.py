#!/usr/bin/env python3
"""Opt-in test of the packaged Omarchy loader in a disposable Wayland session."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests import cockpit_window_smoke as fixture


def configure(output, home):
    manifests = list((output / "shell/plugins").glob("**/manifest.json"))
    if len(manifests) > 128:
        raise ValueError("manifest capacity")
    disabled = [json.loads(path.read_text())["id"] for path in manifests]
    config = {
        "version": 1, "disabledPlugins": disabled, "plugins": [],
        "bar": {"position": "top", "layout": {
            "left": [], "center": [], "right": [{"id": "khephri.sia"}]}},
    }
    encoded = json.dumps(config, indent=2) + "\n"
    (home / ".config/omarchy/shell.json").write_text(encoded)
    defaults = output / "config/omarchy"
    defaults.mkdir(parents=True)
    (defaults / "shell.json").write_text(encoded)


def command(output, environment, name, arguments, limit=65536):
    path = output / name
    with path.open("wb") as log:
        result = subprocess.run(
            arguments, env=environment, stdout=log, stderr=subprocess.STDOUT,
            timeout=8, check=False)
    if path.stat().st_size > limit:
        raise ValueError("command output capacity")
    return result.returncode, path.read_text()


def ipc(output, environment, name, arguments):
    return command(output, environment, name,
                   ["/usr/bin/omarchy-shell", "shell", *arguments])


def window_nodes(output, environment, name):
    status, text = command(
        output, environment, name,
        ["/usr/bin/swaymsg", "-s", environment["SWAYSOCK"], "-t", "get_tree"])
    if status != 0:
        raise ValueError("compositor tree unavailable")
    pending, windows = [(json.loads(text), None)], []
    for _ in range(128):
        if not pending:
            return windows
        node, parent = pending.pop()
        if node.get("name") == "SIA — Omarchy Brain":
            windows.append((node, parent))
        pending.extend((child, node) for child in
                       node.get("nodes", []) + node.get("floating_nodes", []))
        if len(pending) > 128:
            break
    raise ValueError("compositor node capacity")


def await_windows(output, environment, name, count):
    for attempt in range(40):
        windows = window_nodes(output, environment, f"{name}-{attempt}.json")
        if len(windows) == count:
            return windows
        time.sleep(0.05)
    raise ValueError("window count deadline")


def public_cli(output, environment, name, mode):
    status, text = command(
        output, environment, name,
        [sys.executable, str(output / "bin/sia"), "cockpit", mode], limit=4096)
    if status != 0 or "requested in the running shell" not in text:
        raise ValueError("public CLI acknowledgment")


def await_loaded(output, environment):
    for attempt in range(40):
        status, text = ipc(output, environment, f"loader-{attempt}.json",
                           ["listPlugins"])
        if status == 0:
            rows = json.loads(text)
            if any(row["id"] == "khephri.sia" and row["enabled"] for row in rows):
                # Registration precedes asynchronous component loading. This
                # rejected mode has no presentation or operation side effects.
                code, answer = ipc(output, environment, f"mounted-{attempt}.log",
                                   ["call", "khephri.sia", "showPresentation", "invalid"])
                if code == 0 and answer.strip() == "invalid-presentation":
                    return
        time.sleep(0.05)
    raise ValueError("plugin load deadline")


def contained(rectangle, bounds):
    for key in ("x", "y", "width", "height"):
        if type(rectangle[key]) is not int or type(bounds[key]) is not int:
            return False
    return (rectangle["width"] > 0 and rectangle["height"] > 0 and
            bounds["width"] > 0 and bounds["height"] > 0 and
            rectangle["x"] >= bounds["x"] and rectangle["y"] >= bounds["y"] and
            rectangle["x"] + rectangle["width"] <= bounds["x"] + bounds["width"] and
            rectangle["y"] + rectangle["height"] <= bounds["y"] + bounds["height"])


def visible_geometry(node, parent):
    if not isinstance(parent, dict) or parent.get("type") != "workspace":
        return False
    outer, decoration = node["rect"], node["deco_rect"]
    workspace = parent["rect"]
    # sway-ipc(7): rect is absolute, deco_rect is relative to the parent.
    # For this direct floating child, the workspace also excludes the bar.
    absolute_decoration = {
        **decoration, "x": workspace["x"] + decoration["x"],
        "y": workspace["y"] + decoration["y"],
    }
    output = {"x": 0, "y": 0, "width": 1280, "height": 800}
    return (node.get("visible") is True and contained(workspace, output) and
            contained(outer, workspace) and contained(absolute_decoration, workspace))


def lifecycle(output, environment):
    await_loaded(output, environment)
    public_cli(output, environment, "window.log", "--window")
    first, parent = await_windows(output, environment, "opened", 1)[0]
    if not visible_geometry(first, parent):
        raise ValueError("opened window hidden or clipped")
    public_cli(output, environment, "repeat.log", "--window")
    repeated, _parent = await_windows(output, environment, "repeated", 1)[0]
    if (first["id"], first["pid"]) != (repeated["id"], repeated["pid"]):
        raise ValueError("repeat changed native window identity")
    if not fixture.capture_window(output, environment, "host-window.png"):
        raise ValueError("window capture")
    public_cli(output, environment, "overlay.log", "--overlay")
    await_windows(output, environment, "overlay", 0)
    public_cli(output, environment, "switch-back.log", "--window")
    await_windows(output, environment, "switched-back", 1)
    if not fixture.compositor_command(
            output, environment, "kill", "compositor-close.json"):
        raise ValueError("compositor close")
    await_windows(output, environment, "closed", 0)
    public_cli(output, environment, "reopen.log", "--window")
    reopened, _parent = await_windows(output, environment, "reopened", 1)[0]
    if first["pid"] != reopened["pid"]:
        raise ValueError("reopen changed shell process")
    status, text = ipc(output, environment, "disable.log",
                       ["setPluginEnabled", "khephri.sia", "false"])
    if status != 0 or text.strip() != "ok":
        raise ValueError("disable acknowledgment")
    await_windows(output, environment, "disabled", 0)
    status, _text = command(
        output, environment, "disabled-cli.log",
        [sys.executable, str(output / "bin/sia"), "cockpit", "--window"], limit=4096)
    if status == 0:
        raise ValueError("disabled plugin accepted window request")
    await_windows(output, environment, "still-disabled", 0)


def run_host(output, config, environment):
    with (output / "runtime.log").open("wb") as log:
        process = subprocess.Popen(
            ["timeout", "--kill-after=5s", "20s", "/usr/bin/quickshell",
             "--no-color", "-p", str(config)],
            env=environment, stdout=log, stderr=subprocess.STDOUT)
        try:
            lifecycle(output, environment)
            if process.poll() is not None:
                return 1
            return 0
        finally:
            fixture.retire(process)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    output, home, _runtime, config = fixture.prepare(
        options.output.resolve(), actual_host=True)
    shutil.copyfile(__file__, output / "host-runner.py")
    configure(output, home)
    files = sorted(path for path in output.rglob("*") if path.is_file())
    if len(files) > 512:
        raise ValueError("source file capacity")
    receipt = {"status": "UNRUN", "scope": "disposable-packaged-omarchy-loader",
               "files": {str(path.relative_to(output)):
                         hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in files}}
    receipt["tools"] = {
        path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
        for path in ("/usr/bin/quickshell", "/usr/bin/sway", "/usr/bin/omarchy-shell",
                     "/usr/bin/swaymsg", "/usr/bin/grim", sys.executable)}
    path = output / "receipt.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    try:
        status = fixture.run_wayland(output, config, home, run_host)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError) as error:
        status = 1
        receipt["failure_type"] = type(error).__name__
        receipt["failure_reason"] = str(error)[:2048]
    receipt.update({"status": "TESTED" if status == 0 else "FAILED", "exit": status})
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "exit": status,
                      "output": str(output)}))
    return status


if __name__ == "__main__":
    sys.exit(main())
