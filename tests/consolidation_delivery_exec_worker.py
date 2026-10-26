"""Actual process-death cuts for disposable discovery/live-claim staging."""
import importlib
import json
import os
from pathlib import Path
import signal
import sys
from unittest import mock

from consolidation_admission_exec_worker import prepare_request
from consolidation_exec_worker import runtime


def load_admission(lib):
    module = importlib.import_module("siaconsolidationadmission")
    retained = lib.read_state_json(
        str(Path(lib.STATE) / "consolidation-snapshot-admission.json"),
        None, "snapshot admission", expected_type=dict)
    return module.canonical(retained)


def prepare(lib):
    prepare_request(lib)
    module = importlib.import_module("siaconsolidationadmission")
    request = lib.read_state_json(
        str(Path(lib.STATE) / "admission-fixture-request.json"),
        None, "fixture request", expected_type=dict)
    return module.admit(lib, **request)


def execute(lib, phase):
    delivery = importlib.import_module("siaconsolidationdelivery")
    record = load_admission(lib)
    cuts = {"kill-batch": "batch-persisted", "kill-claims": "claims-persisted"}

    def boundary(stage):
        if stage == cuts.get(phase):
            os.kill(os.getpid(), signal.SIGKILL)

    with mock.patch.object(delivery, "_boundary", boundary):
        result = (delivery.offer(lib, record) if phase in {"offer", "kill-batch"}
                  else delivery.prepare_claims(lib, record))
    if phase in cuts:
        raise AssertionError("requested delivery cut was not reached")
    return result


def main():
    phases = {"prepare", "offer", "claim", "kill-batch", "kill-claims"}
    if len(sys.argv) != 2 or sys.argv[1] not in phases:
        raise ValueError("expected one known delivery fixture phase")
    lib = runtime()
    result = prepare(lib) if sys.argv[1] == "prepare" else execute(lib, sys.argv[1])
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
