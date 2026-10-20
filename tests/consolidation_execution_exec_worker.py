"""Disposable real-process cuts across staged execution and source cleanup."""
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from unittest import mock

from consolidation_admission_exec_worker import prepare_request
from consolidation_delivery_exec_worker import load_admission
from consolidation_exec_worker import runtime


def prepare(lib):
    prepare_request(lib)
    stamp = lib.datetime.datetime.fromisoformat("2026-01-06T12:00:00+00:00")
    lib.update_day_page("org", "2026-01-06", [
        lib.Event("org", stamp, "obs", "OBS:second execution source",
                  occurrence="execution-recovery:2")])
    if lib.corpus_commit("second execution source") != "committed":
        raise AssertionError("second fixture source was not committed")
    request = lib.read_state_json(
        str(Path(lib.STATE) / "admission-fixture-request.json"),
        None, "fixture request", expected_type=dict)
    request["commit"] = subprocess.check_output(
        ["git", "-C", lib.CORPUS, "rev-parse", "HEAD"],
        text=True, timeout=10).strip()
    admission = importlib.import_module("siaconsolidationadmission")
    delivery = importlib.import_module("siaconsolidationdelivery")
    record = admission.admit(lib, **request)
    delivery.offer(lib, record)
    return delivery.prepare_claims(lib, record)


def execute(lib, phase):
    delivery = importlib.import_module("siaconsolidationdelivery")
    if phase == "inspect":
        return delivery.inspect_outcomes(lib, load_admission(lib))
    cuts = {"kill-intent": "execution-persisted",
            "kill-return": "effects-returned",
            "kill-persisted": "effects-persisted"}

    def boundary(stage):
        if stage == cuts.get(phase):
            os.kill(os.getpid(), signal.SIGKILL)

    original_write = lib._write_bounded_epoch
    original_unlink = lib._unlink_consolidation_source

    def write(*args):
        result = original_write(*args)
        if phase == "kill-epoch":
            os.kill(os.getpid(), signal.SIGKILL)
        return result

    def unlink(item):
        result = original_unlink(item)
        if phase == "kill-unlink":
            os.kill(os.getpid(), signal.SIGKILL)
        return result

    with mock.patch.object(delivery, "_boundary", boundary), \
            mock.patch.object(lib, "_write_bounded_epoch", write), \
            mock.patch.object(lib, "_unlink_consolidation_source", unlink):
        result = delivery.execute_claims(lib, load_admission(lib))
    if phase != "recover":
        raise AssertionError("requested execution cut was not reached")
    return result


def main():
    phases = {"prepare", "recover", "inspect", "kill-intent", "kill-epoch",
              "kill-unlink", "kill-return", "kill-persisted"}
    if len(sys.argv) != 2 or sys.argv[1] not in phases:
        raise ValueError("expected one known execution fixture phase")
    lib = runtime()
    result = prepare(lib) if sys.argv[1] == "prepare" else execute(lib, sys.argv[1])
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
