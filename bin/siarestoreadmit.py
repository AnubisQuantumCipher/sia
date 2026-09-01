"""Early restore-debt admission for SIA runtime startup.

This module is deliberately state-free.  A dynamically loaded ``sialib``
instance passes itself in, so tests and installed launchers validate the same
paths and helpers without creating a second core module or a circular import.
"""

import fcntl
import os
import re
import stat
import sys


_APPLY_BINDING_FIELDS = frozenset({
    "prepared_id", "snapshot_id", "capsule_id", "manifest_sha256",
    "repository", "environment_file", "repository_id", "configured_at",
    "target_public_key", "restored_public_key",
})
_HEX_BINDING_FIELDS = frozenset({
    "prepared_id", "snapshot_id", "capsule_id", "manifest_sha256",
    "repository_id", "target_public_key", "restored_public_key",
})


def _bounded_text(core, value, *, allow_empty=False):
    return isinstance(value, str) \
        and (allow_empty or bool(value)) \
        and len(value.encode("utf-8", "strict")) <= core.MAX_CONFIG_BYTES \
        and not any(marker in value for marker in ("\0", "\n", "\r"))


def _private_json(core, path, label):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError(f"SIA {label} is unsafe")
    return core.read_state_json(path, {}, label)


def restore_barrier_active(core):
    """Fail closed on core or supervisor restore debt, including bad bytes."""
    active = False
    for path, label in (
            (core.RESTORE_BARRIER_PATH, "restore barrier"),
            (core.RESTORE_MASK_PATH, "restore runtime-mask debt"),
            (core.RESTORE_SUPERVISOR_PATH, "restore supervisor debt")):
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
                or info.st_nlink != 1 \
                or stat.S_IMODE(info.st_mode) != 0o600:
            raise RuntimeError(f"SIA {label} is unsafe")
        if path == core.RESTORE_MASK_PATH:
            flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                     | getattr(os, "O_NOFOLLOW", 0))
            descriptor = os.open(path, flags)
            try:
                expected = b"sia-continuity-runtime-mask-v1\n"
                if info.st_size != len(expected) \
                        or os.read(descriptor, len(expected)) != expected:
                    raise RuntimeError(
                        "SIA restore runtime-mask debt is malformed")
            finally:
                os.close(descriptor)
        active = True
    return active


def _brainstem_restore_restart_admitted(core):
    if os.path.lexists(core.RESTORE_BARRIER_PATH) \
            or os.path.lexists(core.RESTORE_MASK_PATH):
        return False
    debt = _private_json(
        core, core.RESTORE_SUPERVISOR_PATH, "restore supervisor debt")
    required = {
        "schema", "kind", "request_path", "request_id", "prepared_id",
        "snapshot_id", "capsule_id", "manifest_sha256", "phase",
        "child_code", "restart_pid", "runtime_path", "runtime_device",
        "runtime_inode", *_APPLY_BINDING_FIELDS,
    }
    if not isinstance(debt, dict) or set(debt) != required \
            or debt.get("schema") != "sia-restore-supervisor-v1" \
            or debt.get("kind") not in {"restore-apply", "restore-recover"} \
            or debt.get("phase") != "restart-starting" \
            or not _bounded_text(core, debt.get("request_id")) \
            or re.fullmatch(r"[0-9a-f]+", debt["request_id"]) is None \
            or debt.get("child_code") != "0" \
            or debt.get("restart_pid") != "pending" \
            or not isinstance(debt.get("runtime_path"), str) \
            or os.path.abspath(debt["runtime_path"]) != os.path.abspath(
                os.path.join(core.BIN, "sia-cli")) \
            or not isinstance(debt.get("runtime_device"), str) \
            or not debt["runtime_device"].isascii() \
            or not debt["runtime_device"].isdigit() \
            or not isinstance(debt.get("runtime_inode"), str) \
            or not debt["runtime_inode"].isascii() \
            or not debt["runtime_inode"].isdigit():
        raise RuntimeError("SIA restore supervisor restart is not admissible")

    if debt["kind"] == "restore-apply":
        expected_request = os.path.join(
            os.path.dirname(core.RESTORE_SUPERVISOR_PATH), "requests",
            debt["request_id"] + ".json")
        if any(not _bounded_text(core, debt.get(key))
               for key in _APPLY_BINDING_FIELDS - {"environment_file"}) \
                or any(re.fullmatch(r"[0-9a-f]+", debt[key]) is None
                       for key in _HEX_BINDING_FIELDS) \
                or not _bounded_text(
                    core, debt.get("environment_file"), allow_empty=True) \
                or (debt["environment_file"]
                    and (not os.path.isabs(debt["environment_file"])
                         or os.path.abspath(debt["environment_file"])
                            != debt["environment_file"])) \
                or not isinstance(debt.get("request_path"), str) \
                or os.path.abspath(debt["request_path"]) != os.path.abspath(
                    expected_request):
            raise RuntimeError(
                "SIA restore supervisor apply binding is malformed")
        try:
            request = _private_json(
                core, expected_request, "restore request binding")
        except FileNotFoundError:
            request = None
        if request is not None:
            args = request.get("args") if isinstance(request, dict) else None
            if set(request) != {
                    "schema", "id", "created_at", "action", "args"} \
                    or request.get("schema") != \
                       "sia-continuity-request-v1" \
                    or request.get("id") != debt["request_id"] \
                    or request.get("action") != "apply" \
                    or not isinstance(args, dict) \
                    or set(args) != _APPLY_BINDING_FIELDS | {
                        "confirmation", "identity_key_file"} \
                    or any(args.get(key) != debt[key]
                           for key in _APPLY_BINDING_FIELDS):
                raise RuntimeError("SIA restore request binding changed")
        else:
            status_path = os.path.join(
                os.path.dirname(core.RESTORE_SUPERVISOR_PATH), "status.json")
            status = _private_json(
                core, status_path, "restore replay status")
            operation = status.get("operation") \
                if isinstance(status, dict) else None
            if not isinstance(operation, dict) \
                    or operation.get("request_id") != debt["request_id"] \
                    or operation.get("kind") != "restore-apply" \
                    or operation.get("prepared_id") != debt["prepared_id"] \
                    or operation.get("phase") not in {
                        "running", "verified", "blocked"} \
                    or not isinstance(operation.get("ready"), bool) \
                    or operation.get("sia_ledger_verified") is not True:
                raise RuntimeError("SIA restore replay is uncorrelated")
    elif any(debt.get(key) != ""
             for key in _APPLY_BINDING_FIELDS | {"request_path"}):
        raise RuntimeError("SIA restore recovery binding is malformed")

    runtime = os.lstat(debt["runtime_path"])
    if not stat.S_ISREG(runtime.st_mode) or runtime.st_uid != os.geteuid() \
            or str(runtime.st_dev) != debt["runtime_device"] \
            or str(runtime.st_ino) != debt["runtime_inode"]:
        raise RuntimeError("SIA restore runtime generation changed")
    return True


def _validated_restore_finalizer(core):
    abi = os.environ.get(core._RESTORE_FINALIZE_ABI_ENV)
    raw = os.environ.get(core._RESTORE_FINALIZE_ADMIN_FD_ENV)
    if abi is None and raw is None:
        return False
    exact_argv = (
        (len(sys.argv) == 3
         and sys.argv[1] in {
             "_continuity-restore-complete",
             "_continuity-restore-restart-failed"}
         and os.path.isabs(sys.argv[2]))
        or (len(sys.argv) == 2
            and sys.argv[1] in {
                "_continuity-recovery-complete",
                "_continuity-recovery-restart-failed",
                "_continuity-supervisor-reconcile"}))
    if abi != core._RESTORE_FINALIZE_ABI or raw is None \
            or not raw.isascii() or not raw.isdigit() or not exact_argv \
            or os.environ.get(core._RESTORE_LAUNCH_ABI_ENV) is not None:
        raise RuntimeError("invalid SIA restore-finalizer handoff")
    descriptor = int(raw)
    path = os.path.join(core.HOME, ".local", "state",
                        "sia.lifecycle-admin.lock")
    try:
        inherited = os.fstat(descriptor)
        target = os.lstat(path)
    except (OSError, ValueError) as exc:
        raise RuntimeError("invalid SIA restore-finalizer handoff") from exc
    if not stat.S_ISREG(inherited.st_mode) \
            or inherited.st_uid != os.geteuid() \
            or not stat.S_ISREG(target.st_mode) \
            or target.st_uid != os.geteuid() \
            or (inherited.st_dev, inherited.st_ino) != \
               (target.st_dev, target.st_ino):
        raise RuntimeError("restore-finalizer admin lease changed")
    flags = (os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0))
    probe = os.open(path, flags)
    try:
        try:
            fcntl.flock(probe, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(probe, fcntl.LOCK_UN)
            raise RuntimeError(
                "restore-finalizer admin lease is not exclusive")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "restore-finalizer does not own admin EX") from exc
    finally:
        os.close(probe)
    return True


def require_restore_admission(core):
    if not restore_barrier_active(core):
        return
    if os.environ.get(core._RESTORE_LAUNCH_ABI_ENV) == \
            core._RESTORE_LAUNCH_ABI \
            and core._validated_inherited_lifecycle_fd() is not None:
        return
    if _validated_restore_finalizer(core):
        return
    launcher = core._installed_launcher_context()
    brainstem_target = os.path.abspath(
        os.path.join(core.BIN, "sia-brainstem.py"))
    if launcher is not None and launcher[1] == brainstem_target:
        if _brainstem_restore_restart_admitted(core):
            return
        raise SystemExit(0)
    raise RuntimeError(
        "SIA restore is interrupted; run `sia restore recover`")
