"""Isolated exec fixture with controlled and real signed-settlement lanes."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from unittest import mock


def runtime():
    home = os.environ.get("HOME", "")
    if not home or os.environ.get("SIA_EXEC_FIXTURE_HOME") != home:
        raise RuntimeError("explicit isolated fixture home required")
    if (Path(home) / ".sia-exec-fixture").read_text() != "disposable-test-home\n":
        raise RuntimeError("fixture home marker differs")
    path = Path(__file__).resolve().parents[1] / "bin" / "sialib.py"
    spec = importlib.util.spec_from_file_location("consolidation_exec_lib", path)
    lib = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lib)
    lib.BIN = str(path.parent)
    lib.siamind.EPISODIC_DAYS = 1
    return lib


def prepare(lib):
    Path(lib.STATE).mkdir(parents=True)
    Path(lib.CORPUS).mkdir(parents=True)
    subprocess.run(["git", "init", "-q", lib.CORPUS], check=True, timeout=10)
    stamp = lib.datetime.datetime.fromisoformat("2026-01-05T12:00:00+00:00")
    lib.update_day_page("org", "2026-01-05", [
        lib.Event("org", stamp, "obs", "OBS:exec recovery fixture",
                  occurrence="exec-recovery:1")])
    subprocess.run(["git", "-C", lib.CORPUS, "add", "events/org/2026-01-05.md"],
                   check=True, timeout=10)
    subprocess.run(["git", "-C", lib.CORPUS, "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@invalid",
                    "commit", "-qm", "isolated recovery source"],
                   check=True, timeout=10)
    lib._mark_consolidation_pending({})


def kill_after_apply(lib):
    apply = lib._mark_consolidation_applied

    def cut(memo):
        apply(memo)
        os.kill(os.getpid(), signal.SIGKILL)

    with mock.patch.object(lib, "_mark_consolidation_applied", cut):
        lib._recover_pending_consolidation(lib.load_memo())
    raise AssertionError("applied cut was not reached")


def recover(lib):
    expected = (False, "corpus consolidation recovery is pending")
    if lib.memory_readiness() != expected:
        raise AssertionError("unsettled transaction did not block readiness")

    def settle(memo):
        # Controlled durable observation of the requested binding, not signing.
        lib.atomic_write(str(Path(lib.STATE) / "settlement-witness.json"),
                         json.dumps(memo["consolidation_pending"], sort_keys=True))

    with mock.patch.object(lib, "consolidate_corpus",
                           side_effect=AssertionError("applied work repeated")), \
            mock.patch.object(lib, "_settle_consolidation_ledger", settle):
        lib._recover_pending_consolidation(lib.load_memo())


def prepare_signed(lib):
    prepare(lib)
    subprocess.run([sys.executable, str(Path(lib.BIN) / "sia-ledger"),
                    "init", lib.SHARE], check=True, timeout=30)


def recover_signed(lib, *, kill=False):
    memo = lib.load_memo()
    marker = memo["consolidation_pending"]
    if lib.memory_readiness() != (False, "corpus consolidation recovery is pending"):
        raise AssertionError("unsettled transaction did not block readiness")
    original = lib._settle_consolidation_ledger

    def settle(state):
        result = original(state)
        if kill:
            os.kill(os.getpid(), signal.SIGKILL)
        return result

    with mock.patch.object(lib, "consolidate_corpus",
                           side_effect=AssertionError("applied work repeated")), \
            mock.patch.object(lib, "_settle_consolidation_ledger", settle):
        lib._recover_pending_consolidation(memo)
    ledger = marker["ledger"]
    if not lib.ledger_contains(ledger["action"], ledger["arg1"], ledger["arg2"],
                               ledger["content"], ledger["record_id"]):
        raise AssertionError("exact signed occurrence missing after recovery")
    subprocess.run([sys.executable, str(Path(lib.BIN) / "sia-ledger"),
                    "verify", lib.SHARE], check=True, timeout=30)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in (
            "prepare", "kill", "recover", "prepare-signed",
            "kill-settled", "recover-signed"):
        raise ValueError("expected one known fixture phase")
    lib = runtime()
    with mock.patch.object(lib.siamind, "pending_user_pin_slugs",
                           return_value={"events/org/2026-01-05"}):
        if sys.argv[1] == "prepare":
            prepare(lib)
        elif sys.argv[1] == "kill":
            kill_after_apply(lib)
        elif sys.argv[1] == "prepare-signed":
            prepare_signed(lib)
        elif sys.argv[1] == "kill-settled":
            recover_signed(lib, kill=True)
        elif sys.argv[1] == "recover-signed":
            recover_signed(lib)
        else:
            recover(lib)


if __name__ == "__main__":
    main()
