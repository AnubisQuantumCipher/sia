"""Disposable admission-journal worker; no resident or power-loss claim."""
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from unittest import mock

from consolidation_exec_worker import prepare, runtime


def prepare_request(lib):
    prepare(lib)
    commit = subprocess.check_output(
        ["git", "-C", lib.CORPUS, "rev-parse", "HEAD"],
        text=True, timeout=10).strip()
    # Fixed fixture identities are not authenticated transaction production.
    request = {"generation": "a" * 32, "transaction": "b" * 64,
               "cutoff": "2026-10-06", "commit": commit}
    lib.atomic_write(str(Path(lib.STATE) / "admission-fixture-request.json"),
                     json.dumps(request, sort_keys=True))


def execute(lib, phase):
    admission = importlib.import_module("siaconsolidationadmission")
    request = lib.read_state_json(
        str(Path(lib.STATE) / "admission-fixture-request.json"), None,
        "fixture request", expected_type=dict)
    if not isinstance(request, dict):
        raise ValueError("fixture request is missing")
    cuts = {"kill-planned": "planned-persisted",
            "kill-pin": "pin-retained", "kill-admitted": "admission-persisted"}

    def boundary(stage):
        if stage == cuts.get(phase):
            os.kill(os.getpid(), signal.SIGKILL)

    with mock.patch.object(admission, "_boundary", boundary):
        record = admission.admit(lib, **request)
    if phase in cuts:
        raise AssertionError("requested admission cut was not reached")
    expected = dict(request, schema=admission.SCHEMA, phase="admitted")
    if record != expected:
        raise AssertionError("recovered admission differs from exact request")
    print(json.dumps(record, sort_keys=True))


def main():
    phases = {"prepare", "kill-planned", "kill-pin", "kill-admitted", "recover"}
    if len(sys.argv) != 2 or sys.argv[1] not in phases:
        raise ValueError("expected one known admission fixture phase")
    # The shared fixture checks explicit disposable HOME before importing SIA.
    lib = runtime()
    if sys.argv[1] == "prepare":
        prepare_request(lib)
    else:
        execute(lib, sys.argv[1])


if __name__ == "__main__":
    main()
