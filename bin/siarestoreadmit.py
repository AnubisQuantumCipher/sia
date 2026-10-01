"""Early restore-debt admission for SIA runtime startup.

This module is deliberately state-free.  A dynamically loaded ``sialib``
instance passes itself in, so tests and installed launchers validate the same
paths and helpers without creating a second core module or a circular import.
"""

import fcntl
import datetime
import hashlib
import json
import os
import re
import stat
import sys


_APPLY_BINDING_FIELDS = frozenset({
    "prepared_id", "snapshot_id", "capsule_id", "manifest_sha256",
    "identity_key_file", "repository", "environment_file", "repository_id",
    "configured_at", "target_public_key", "restored_public_key",
    "request_device", "request_inode", "accepted_ledger_head",
    "confirmation_sha256", "adoption_order", "adoption_record_id", "target",
})
_HEX_BINDING_FIELDS = frozenset({
    "manifest_sha256", "repository_id", "target_public_key",
    "restored_public_key", "accepted_ledger_head", "confirmation_sha256",
    "adoption_record_id",
})
_REQUEST_ARGUMENT_FIELDS = frozenset({
    "prepared_id", "snapshot_id", "capsule_id", "manifest_sha256",
    "confirmation", "identity_key_file", "repository", "environment_file",
    "repository_id", "configured_at", "target_public_key",
    "restored_public_key", "adoption",
})
_STATUS_FIELDS = frozenset({
    "schema_version", "state", "detail", "repository_display", "latest",
    "prepared", "operation", "updated_at",
})
_LATEST_FIELDS = frozenset({
    "snapshot_id", "created_at", "verified", "readiness", "profile",
    "identity_matches",
})
_PREPARED_FIELDS = frozenset({
    "prepared_id", "snapshot_id", "created_at", "readiness", "profile",
    "ledger_head", "identity_matches",
})
_OPERATION_FIELDS = frozenset({
    "request_id", "kind", "prepared_id", "phase", "ready",
    "sia_ledger_verified",
})
_STATUS_STATES = frozenset({
    "unconfigured", "queued", "capturing", "uploading", "checking",
    "preparing", "prepared", "restoring", "verified", "recovery-only",
    "failed", "blocked",
})
_OPERATION_KINDS = frozenset({
    "backup-setup", "backup-connect", "backup-upload", "backup-check",
    "restore-prepare", "restore-apply", "restore-recover",
})
_OPERATION_PHASES = frozenset({
    "accepted", "running", "verified", "failed", "blocked",
})
_SNAPSHOT_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.([0-9]{1,9}))?(Z|[+-][0-9]{2}:[0-9]{2})")


def _bounded_text(core, value, *, allow_empty=False):
    return isinstance(value, str) \
        and (allow_empty or bool(value)) \
        and len(value.encode("utf-8", "strict")) <= core.MAX_CONFIG_BYTES \
        and not any(marker in value for marker in ("\0", "\n", "\r"))


def _hex_exact(value, length):
    return isinstance(value, str) \
        and len(value) == length \
        and re.fullmatch(r"[0-9a-f]+", value) is not None


def _valid_target(value):
    if not isinstance(value, dict) \
            or set(value) != {
                "corpus_root", "receipt_sha256", "receipt_mode"}:
        return False
    root = value.get("corpus_root")
    return isinstance(root, dict) \
        and set(root) == {"device", "inode", "mode", "owner"} \
        and all(type(root.get(key)) is int
                for key in ("device", "inode", "mode", "owner")) \
        and _hex_exact(value.get("receipt_sha256"), 64) \
        and type(value.get("receipt_mode")) is int


def _status_text(core, value, *, nonempty=False):
    maximum = getattr(
        core, "MAX_CONFIG_TEXT_CHARS", core.MAX_CONFIG_BYTES)
    return isinstance(value, str) \
        and (bool(value) or not nonempty) \
        and len(value) <= maximum \
        and all(" " <= character <= "~" for character in value)


def _canonical_timestamp(core, value):
    try:
        return core._canonical_utc_timestamp(value) == value
    except (TypeError, ValueError):
        return False


def _snapshot_timestamp(value):
    if not isinstance(value, str):
        return False
    match = _SNAPSHOT_TIMESTAMP.fullmatch(value)
    if match is None:
        return False
    fraction, zone = match.groups()
    if fraction is not None and fraction.endswith("0"):
        return False
    if zone in {"+00:00", "-00:00"}:
        return False
    source = value[:-1] + "+00:00" if zone == "Z" else value
    try:
        parsed = datetime.datetime.fromisoformat(source)
    except ValueError:
        return False
    return parsed.utcoffset() is not None


def _status_identifier(value):
    return isinstance(value, str) \
        and 0 < len(value) <= 64 \
        and re.fullmatch(r"[0-9a-f]+", value) is not None


def _valid_latest(value):
    return isinstance(value, dict) \
        and set(value) == _LATEST_FIELDS \
        and _status_identifier(value.get("snapshot_id")) \
        and _snapshot_timestamp(value.get("created_at")) \
        and type(value.get("verified")) is bool \
        and value.get("readiness") in {"ready", "recovery-only", "unknown"} \
        and value.get("profile") == "signed portable capsule" \
        and type(value.get("identity_matches")) is bool \
        and (value["readiness"] != "unknown" or not value["verified"])


def _valid_prepared(core, value):
    return isinstance(value, dict) \
        and set(value) == _PREPARED_FIELDS \
        and _hex_exact(value.get("prepared_id"), 32) \
        and _status_identifier(value.get("snapshot_id")) \
        and _canonical_timestamp(core, value.get("created_at")) \
        and value.get("readiness") in {"ready", "recovery-only"} \
        and value.get("profile") == "signed portable capsule" \
        and _hex_exact(value.get("ledger_head"), 64) \
        and type(value.get("identity_matches")) is bool


def _valid_operation(value):
    if not isinstance(value, dict) or set(value) != _OPERATION_FIELDS \
            or not _hex_exact(value.get("request_id"), 32) \
            or value.get("kind") not in _OPERATION_KINDS \
            or not (value.get("prepared_id") == ""
                    or _hex_exact(value.get("prepared_id"), 32)) \
            or value.get("phase") not in _OPERATION_PHASES \
            or type(value.get("ready")) is not bool \
            or type(value.get("sia_ledger_verified")) is not bool:
        return False
    kind = value["kind"]
    phase = value["phase"]
    prepared_id = value["prepared_id"]
    if kind == "restore-apply":
        if not prepared_id:
            return False
    elif kind == "restore-prepare":
        if bool(prepared_id) != (phase == "verified"):
            return False
    elif prepared_id:
        return False
    if kind not in {"restore-apply", "restore-recover"} \
            and (value["ready"] or value["sia_ledger_verified"]):
        return False
    if phase in {"accepted", "failed"} \
            and (value["ready"] or value["sia_ledger_verified"]):
        return False
    if kind in {"restore-apply", "restore-recover"}:
        if phase == "running" \
                and value["ready"] != value["sia_ledger_verified"]:
            return False
        if phase == "verified" \
                and not (value["ready"]
                         and value["sia_ledger_verified"]):
            return False
    return True


def _valid_status_operation_pair(value):
    state = value["state"]
    operation = value.get("operation")
    if operation is None:
        return state in {"unconfigured", "verified", "recovery-only"}
    kind = operation["kind"]
    phase = operation["phase"]
    if state == "queued":
        return (phase == "accepted"
                and kind in _OPERATION_KINDS - {"restore-apply",
                                                "restore-recover"}) \
            or (phase == "running"
                and kind in {"backup-setup", "backup-connect"})
    if state in {"capturing", "uploading"}:
        return kind == "backup-upload" and phase == "running"
    if state == "checking":
        return kind == "backup-check" and phase == "running"
    if state == "preparing":
        return kind == "restore-prepare" and phase == "running"
    if state == "prepared":
        prepared = value.get("prepared")
        return isinstance(prepared, dict) \
            and kind == "restore-prepare" \
            and phase == "verified" \
            and operation["prepared_id"] == prepared.get("prepared_id")
    if state == "restoring":
        return (kind == "restore-apply"
                and phase in {"accepted", "running"}) \
            or (kind == "restore-recover" and phase == "running")
    if state in {"verified", "recovery-only"}:
        return phase == "verified" and kind != "restore-prepare"
    if state == "failed":
        return phase == "failed"
    if state == "blocked":
        return phase == "blocked"
    return False


def _valid_continuity_status(core, value):
    if not isinstance(value, dict) or set(value) != _STATUS_FIELDS \
            or type(value.get("schema_version")) is not int \
            or value.get("schema_version") != 2 \
            or value.get("state") not in _STATUS_STATES \
            or not _status_text(core, value.get("detail"), nonempty=True) \
            or value.get("repository_display") not in {
                "", "External recovery repository"} \
            or not _canonical_timestamp(core, value.get("updated_at")):
        return False
    latest = value.get("latest")
    prepared = value.get("prepared")
    operation = value.get("operation")
    if latest is not None and not _valid_latest(latest):
        return False
    if prepared is not None and not _valid_prepared(core, prepared):
        return False
    if operation is not None and not _valid_operation(operation):
        return False
    unconfigured = value["state"] == "unconfigured"
    if unconfigured != (value["repository_display"] == "") \
            or (unconfigured
                and (latest is not None or prepared is not None)):
        return False
    if value["state"] == "verified" \
            and not (_valid_latest(latest)
                     and latest["verified"]
                     and latest["readiness"] == "ready"
                     and latest["identity_matches"]):
        return False
    return _valid_status_operation_pair(value)


def _request_debt_binding(core, request, info):
    args = request.get("args") if isinstance(request, dict) else None
    confirmation = args.get("confirmation") if isinstance(args, dict) else None
    adoption = args.get("adoption") if isinstance(args, dict) else None
    target = adoption.get("target") if isinstance(adoption, dict) else None
    if not isinstance(request, dict) \
            or set(request) != {
                "schema", "id", "created_at", "action", "args"} \
            or request.get("schema") != "sia-continuity-request-v1" \
            or request.get("action") != "apply" \
            or not _hex_exact(request.get("id"), 32) \
            or core._canonical_utc_timestamp(request.get("created_at")) != \
                request.get("created_at") \
            or not isinstance(args, dict) \
            or set(args) != _REQUEST_ARGUMENT_FIELDS \
            or not _hex_exact(args.get("prepared_id"), 32) \
            or not _hex_exact(args.get("capsule_id"), 32) \
            or not _hex_exact(args.get("manifest_sha256"), 64) \
            or not _bounded_text(core, args.get("snapshot_id")) \
            or len(args["snapshot_id"]) > 64 \
            or re.fullmatch(r"[0-9a-f]+", args["snapshot_id"]) is None \
            or not _bounded_text(core, args.get("repository")) \
            or not _bounded_text(
                core, args.get("environment_file"), allow_empty=True) \
            or (args["environment_file"]
                and (not os.path.isabs(args["environment_file"])
                     or os.path.abspath(args["environment_file"]) !=
                        args["environment_file"])) \
            or not _hex_exact(args.get("repository_id"), 64) \
            or core._canonical_utc_timestamp(args.get("configured_at")) != \
                args.get("configured_at") \
            or not _hex_exact(args.get("target_public_key"), 64) \
            or not _hex_exact(args.get("restored_public_key"), 64) \
            or (args.get("identity_key_file") is not None
                and (not isinstance(args["identity_key_file"], str)
                     or not os.path.isabs(args["identity_key_file"])
                     or os.path.abspath(args["identity_key_file"]) !=
                        args["identity_key_file"])) \
            or not isinstance(confirmation, dict) \
            or set(confirmation) != {
                "schema_version", "phrase", "snapshot_id", "ledger_head",
                "corpus_receipt_re_adopt"} \
            or type(confirmation.get("schema_version")) is not int \
            or confirmation["schema_version"] != 1 \
            or confirmation.get("phrase") != "RESTORE" \
            or confirmation.get("snapshot_id") != args["snapshot_id"] \
            or not _hex_exact(confirmation.get("ledger_head"), 64) \
            or confirmation.get("corpus_receipt_re_adopt") is not True \
            or not isinstance(adoption, dict) \
            or set(adoption) != {"order", "record_id", "target"} \
            or type(adoption.get("order")) is not int \
            or adoption["order"] < 0 \
            or not _hex_exact(adoption.get("record_id"), 64) \
            or not _valid_target(target):
        raise RuntimeError("SIA restore request binding changed")
    confirmation_raw = (json.dumps(
        confirmation, ensure_ascii=True, sort_keys=True,
        separators=(",", ":")) + "\n").encode("utf-8")
    confirmation_sha256 = hashlib.sha256(confirmation_raw).hexdigest()
    content = json.dumps({
        "accepted_ledger_head": confirmation["ledger_head"],
        "confirmation_sha256": confirmation_sha256,
        "snapshot_id": args["snapshot_id"],
        "manifest_sha256": args["manifest_sha256"],
        "target": target,
        "receipt_re_adopted": True,
    }, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    basis = {
        "order": adoption["order"], "action": "RESTORE:adopt",
        "arg1": args["prepared_id"], "arg2": args["capsule_id"],
        "content": content,
    }
    record_id = hashlib.sha256(json.dumps(
        basis, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    if record_id != adoption["record_id"]:
        raise RuntimeError("SIA restore request binding changed")
    return {
        "prepared_id": args["prepared_id"],
        "snapshot_id": args["snapshot_id"],
        "capsule_id": args["capsule_id"],
        "manifest_sha256": args["manifest_sha256"],
        "identity_key_file": args["identity_key_file"] or "",
        "repository": args["repository"],
        "environment_file": args["environment_file"],
        "repository_id": args["repository_id"],
        "configured_at": args["configured_at"],
        "target_public_key": args["target_public_key"],
        "restored_public_key": args["restored_public_key"],
        "request_device": str(info.st_dev),
        "request_inode": str(info.st_ino),
        "accepted_ledger_head": confirmation["ledger_head"],
        "confirmation_sha256": confirmation_sha256,
        "adoption_order": str(adoption["order"]),
        "adoption_record_id": record_id,
        "target": target,
    }


def _private_json(core, path, label, *, return_info=False):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
        raise RuntimeError(f"SIA {label} is unsafe")
    value = core.read_state_json(path, {}, label)
    current = os.lstat(path)
    if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns) != (current.st_dev, current.st_ino,
                                  current.st_size, current.st_mtime_ns,
                                  current.st_ctime_ns):
        raise RuntimeError(f"SIA {label} changed while read")
    return (value, current) if return_info else value


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
            or not _hex_exact(debt.get("request_id"), 32) \
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
        if not _hex_exact(debt.get("prepared_id"), 32) \
                or not _hex_exact(debt.get("capsule_id"), 32) \
                or not _bounded_text(core, debt.get("snapshot_id")) \
                or len(debt["snapshot_id"]) > 64 \
                or re.fullmatch(r"[0-9a-f]+", debt["snapshot_id"]) is None \
                or any(not _hex_exact(debt.get(key), 64)
                       for key in _HEX_BINDING_FIELDS) \
                or not _bounded_text(core, debt.get("repository")) \
                or not _bounded_text(
                    core, debt.get("environment_file"), allow_empty=True) \
                or (debt["environment_file"]
                    and (not os.path.isabs(debt["environment_file"])
                         or os.path.abspath(debt["environment_file"])
                            != debt["environment_file"])) \
                or not _bounded_text(
                    core, debt.get("identity_key_file"), allow_empty=True) \
                or (debt["identity_key_file"]
                    and (not os.path.isabs(debt["identity_key_file"])
                         or os.path.abspath(debt["identity_key_file"])
                            != debt["identity_key_file"])) \
                or core._canonical_utc_timestamp(
                    debt.get("configured_at")) != debt.get("configured_at") \
                or not _bounded_text(core, debt.get("request_device")) \
                or not debt["request_device"].isascii() \
                or not debt["request_device"].isdigit() \
                or not _bounded_text(core, debt.get("request_inode")) \
                or not debt["request_inode"].isascii() \
                or not debt["request_inode"].isdigit() \
                or not _bounded_text(core, debt.get("adoption_order")) \
                or re.fullmatch(
                    r"0|[1-9][0-9]*", debt["adoption_order"]) is None \
                or not _valid_target(debt.get("target")) \
                or not isinstance(debt.get("request_path"), str) \
                or os.path.abspath(debt["request_path"]) != os.path.abspath(
                    expected_request):
            raise RuntimeError(
                "SIA restore supervisor apply binding is malformed")
        try:
            request, request_info = _private_json(
                core, expected_request, "restore request binding",
                return_info=True)
        except FileNotFoundError:
            request = None
        if request is not None:
            binding = _request_debt_binding(core, request, request_info)
            if request.get("id") != debt["request_id"] \
                    or any(binding[key] != debt[key]
                           for key in _APPLY_BINDING_FIELDS):
                raise RuntimeError("SIA restore request binding changed")
        else:
            status_path = os.path.join(
                os.path.dirname(core.RESTORE_SUPERVISOR_PATH), "status.json")
            status = _private_json(
                core, status_path, "restore replay status")
            operation = status.get("operation") \
                if isinstance(status, dict) else None
            if not _valid_continuity_status(core, status) \
                    or not isinstance(operation, dict) \
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
