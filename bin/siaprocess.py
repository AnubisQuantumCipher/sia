"""Bounded child processes, refusal naming and the retained-status rule.

Extracted from the resident library without behavioural change. The
marketplace per-file scan guard refuses a library above its headroom and
says extraction is the repair, not a raised threshold, so these moved out
whole rather than being trimmed.

Every function here is pure with respect to the library: byte ceilings, the
journal timeout, the probed isolation mode, the reaper callbacks and the
text sanitizer are caller-supplied, so this module owns the mechanics, not
the policy. The library keeps the original private names and delegates to
them, so every caller and every test that patches those names still binds
the call.
"""

import math
import os
import re
import selectors
import subprocess
import sys
import time

UNSHARE = "/usr/bin/unshare"


def probe_pid_namespace(unshare=UNSHARE):
    """Whether an unprivileged user+PID namespace can be entered here.

    Ubuntu 24.04 and hardened kernels refuse unprivileged user namespaces
    (AppArmor ``userns`` restriction or ``kernel.unprivileged_userns_clone``),
    and ``unshare`` then exits nonzero before the child runs. The probe runs
    the exact namespace shape used for bounded children against ``/bin/true``
    and never inspects or reuses its output.
    """
    if not os.access(unshare, os.X_OK) or not os.access("/bin/true", os.X_OK):
        return False
    try:
        completed = subprocess.run(
            [unshare, "--user", "--map-root-user", "--pid", "--fork",
             "--kill-child", "--mount-proc", "--", "/bin/true"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=15, check=False,
            start_new_session=True, close_fds=True)
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def run_bounded_text_process(command, *, env, timeout, cwd, pass_fds=(),
                             label="subprocess", output_limit=None,
                             isolate_process_tree=False,
                             retain_output=True, progress_interval=None,
                             progress_label=None, limits, isolation,
                             await_exit, reap_group):
    """Run one external reader with bounded combined output and lifetime.

    Pure: ``limits`` carries the caller's byte and name ceilings plus the
    journal timeout, ``isolation`` is the caller's probed host mode, and the
    two reaper callbacks stay the caller's. The resident library keeps its
    original private name and delegates here.

    Drain both pipes concurrently in a fresh process group. Optional PID
    isolation also contains descendants that call ``setsid()`` where the host
    permits an unprivileged PID namespace (the caller probes and announces
    the process-group fallback). Retained bytes
    require strict UTF-8; discard mode only counts them. Progress output uses a
    constant caller label and never echoes child output.
    """
    if not isinstance(command, (list, tuple)) or not command \
            or any(not isinstance(part, (str, bytes, os.PathLike))
                   for part in command):
        raise ValueError("bounded subprocess command is invalid")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) \
            or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("bounded subprocess timeout is invalid")
    if not isinstance(label, str) or not label \
            or len(label) > limits["MAX_SOURCE_NAME_CHARS"]:
        raise ValueError("bounded subprocess label is invalid")
    if output_limit is None:
        output_limit = limits["MAX_EXTERNAL_OUTPUT_BYTES"]
    if isinstance(output_limit, bool) or not isinstance(output_limit, int) \
            or output_limit <= 0 or output_limit > limits["MAX_STATE_JSON_BYTES"]:
        raise ValueError("bounded subprocess output limit is invalid")
    if not isinstance(isolate_process_tree, bool):
        raise ValueError("bounded subprocess isolation mode is invalid")
    if not isinstance(retain_output, bool):
        raise ValueError("bounded subprocess output-retention mode is invalid")
    if progress_interval is not None and (
            isinstance(progress_interval, bool)
            or not isinstance(progress_interval, (int, float))
            or not math.isfinite(progress_interval) or progress_interval <= 0):
        raise ValueError("invalid progress interval")
    if (progress_interval is None) != (progress_label is None) or (
            progress_label is not None and (
                len(progress_label) > limits["MAX_SOURCE_NAME_CHARS"] or not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9 ._-]*", progress_label))):
        raise ValueError("invalid progress label")
    original_command = list(command)
    launch_command = original_command
    if isolate_process_tree and isolation == "pid-namespace":
        launch_command = [
            UNSHARE, "--user", "--map-root-user", "--pid",
            "--fork", "--kill-child", "--mount-proc", "--",
            *original_command]
    process = None
    group_reaped = False
    selector = selectors.DefaultSelector()
    streams = {}
    try:
        process = subprocess.Popen(
            launch_command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, cwd=cwd,
            pass_fds=tuple(pass_fds), close_fds=True,
            start_new_session=True, text=False)
        if process.stdout is None or process.stderr is None:
            raise RuntimeError("bounded subprocess did not provide output pipes")
        streams = {
            process.stdout: bytearray() if retain_output else None,
            process.stderr: bytearray() if retain_output else None,
        }
        for stream in streams:
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        next_progress = (time.monotonic() + progress_interval
                         if progress_interval is not None else None)
        captured = 0
        while selector.get_map():
            now = time.monotonic()
            remaining = deadline - now
            if remaining <= 0:
                raise subprocess.TimeoutExpired(original_command, timeout)
            if next_progress is not None and now >= next_progress:
                print(f"SIA: {progress_label} is still running", file=sys.stderr,
                      flush=True)
                next_progress = now + progress_interval
            wait = (min(remaining, max(0, next_progress - now))
                    if next_progress is not None else remaining)
            ready = selector.select(wait)
            if not ready:
                continue
            for key, _events in ready:
                stream = key.fileobj
                budget = output_limit - captured
                try:
                    block = os.read(
                        stream.fileno(), min(limits["MAX_CONFIG_BYTES"], budget + 1))
                except BlockingIOError:
                    continue
                if not block:
                    selector.unregister(stream)
                    stream.close()
                    continue
                if len(block) > budget:
                    raise OverflowError(
                        f"{label} output exceeded its combined byte limit")
                if retain_output:
                    streams[stream].extend(block)
                captured += len(block)
        await_exit(
            process, deadline, original_command, timeout)
        returncode = reap_group(
            process, limits["JOURNAL_TIMEOUT_SECONDS"])
        group_reaped = True
        if returncode is None:
            raise subprocess.TimeoutExpired(original_command, timeout)
        stdout = (bytes(streams[process.stdout]).decode(
            "utf-8", errors="strict") if retain_output else "")
        stderr = (bytes(streams[process.stderr]).decode(
            "utf-8", errors="strict") if retain_output else "")
        return subprocess.CompletedProcess(
            original_command, returncode, stdout=stdout, stderr=stderr)
    finally:
        selector.close()
        if process is not None and not group_reaped:
            # Signal while the unreaped leader still owns its PID/PGID.  This
            # avoids both descendant escape and a post-reap PID-reuse race.
            reap_group(
                process, limits["JOURNAL_TIMEOUT_SECONDS"])


def refusal_chain(exc, *, sanitize, limit=6):
    """Name a refusal and every upstream refusal it wraps, innermost last.

    Fail-closed layers wrap one another (source batch <- effects archive <-
    live publication ...). Each layer's typed ``reason`` code and ``detail``
    clause, or its clipped message, is listed so an operator sees WHICH gate
    refused instead of only the outermost wrapper. Text is redacted and
    clipped; nothing here is a claim about the cause.
    """
    parts = []
    seen = set()
    while exc is not None and len(parts) < limit and id(exc) not in seen:
        seen.add(id(exc))
        reason = getattr(exc, "reason", None)
        detail = getattr(exc, "detail", None)
        if isinstance(reason, str) and reason:
            part = reason + (" (" + detail + ")" if isinstance(detail, str)
                             and detail else "")
        else:
            part = sanitize(str(exc))
        if part and (not parts or parts[-1] != part):
            parts.append(part)
        upstream = getattr(exc, "upstream_reason", None)
        following = exc.__cause__ if exc.__cause__ is not None else exc.__context__
        if following is None:
            if isinstance(upstream, str) and upstream \
                    and (not parts or parts[-1] != upstream):
                parts.append(upstream)
            # The innermost refusal's code location (never data): which
            # module's gate spoke last.
            frames = []
            frame = exc.__traceback__
            while frame is not None:
                code = frame.tb_frame.f_code
                if not code.co_name.endswith("refuse"):
                    frames.append(os.path.basename(code.co_filename) + ":"
                                  + code.co_name + ":" + str(frame.tb_lineno))
                frame = frame.tb_next
            if frames:
                parts.append("at " + " < ".join(reversed(frames[-3:])))
        exc = following
    return parts


def status_version_admissible(value, *, current_version, release_tuple):
    """The current release, or an earlier canonical release.

    A retained status is the last publication of whichever runtime wrote it.
    After an update the first pulse republishes it under the new version; the
    retained one must stay admissible so that update can start at all, and
    so `sia status` keeps naming the last publication instead of calling it
    invalid. A status from a NEWER release than this runtime is refused: it
    would mean a rollback under a live publication, which this runtime cannot
    interpret.
    """
    if value == current_version:
        return True
    retained = release_tuple(value)
    current = release_tuple(current_version)
    return retained is not None and current is not None and retained < current


def pulse_failure_record(seq, detail, *, failed_at, schema, sanitize,
                         canonical_timestamp, now_timestamp):
    """Build the retained pulse-failure record (pure; the library writes it)."""
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise ValueError("pulse failure sequence must be a non-negative integer")
    if not isinstance(detail, str):
        raise TypeError("pulse failure detail must be text")
    when = (now_timestamp() if failed_at is None
            else canonical_timestamp(failed_at))
    return {"schema": schema, "v": 1, "pulse_seq": seq,
            "detail": sanitize(detail, 240), "failed_at": when,
            "non_claims": [
                "A retained pulse failure is a diagnostic clause, not "
                "memory, readiness, or proof of the failure's cause."]}


def parse_pulse_failure(record, *, schema, sanitize):
    """Return the operator view of a retained record, or None when unusable."""
    if record is None or record.get("schema") != schema \
            or not isinstance(record.get("pulse_seq"), int) \
            or isinstance(record.get("pulse_seq"), bool) \
            or not isinstance(record.get("detail"), str) \
            or not isinstance(record.get("failed_at"), str):
        return None
    return {"pulse_seq": record["pulse_seq"],
            "detail": sanitize(record["detail"], 240),
            "failed_at": sanitize(record["failed_at"], 40)}


def name_plan_capacity_refusal(exc, *, organ, date, events, event_type, ceiling):
    """Attach the overflowing day's numbers to a plan capacity refusal."""
    summary_bytes = sum(
        len(getattr(event, "summary", "").encode("utf-8", "replace"))
        for event in events if isinstance(event, event_type))
    named = ValueError(
        f"{exc} (organ {organ}, day {date}, {len(events)} events, "
        f"{summary_bytes} summary bytes; plan ceiling {ceiling} bytes)")
    named.non_claims = list(getattr(exc, "non_claims", ()))
    return named
