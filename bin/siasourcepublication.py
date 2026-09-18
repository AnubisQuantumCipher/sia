"""Fixed-slot source retention and its memo write-ahead bindings.

The pending slot is immutable except for an exact byte retry.  Retention is
inert.  A later binding operation may replay the pure retained-source live
producer, but its sole durable effect is a compact memo marker; it does not
publish a live generation, acknowledge a source, or create a history archive.
No current configuration, source collector, page renderer or downstream
publication effect runs here.

Recurring rollover reuses the fixed slot as the successor WAL only after the
predecessor has moved to its immutable digest archive.  Successor retention
leaves completed readiness intact; adoption is the single later memo swap to
the ordinary pending receipt consumed by the existing pipeline.

The additive capturable-successor entrypoints admit only the exact durable
notification acquisition fence over a fully revalidated historical source
completion. They retain that fence unchanged while writing the successor WAL
and adopting it as pending. They do not make the predecessor currently ready,
capture sources, enable delivery, or admit a different pending authority.
"""

import contextlib
import copy
import os
import re
import stat


RECEIPT_KEYS = frozenset({
    "schema", "epoch_id", "batch_id", "epoch_sha256", "batch_sha256",
    "batch_wire_sha256", "batch_bytes", "parent_batch_sha256",
})
LIVE_BINDING_KEYS = frozenset({
    "schema", "status", "seq", "publication_id", "publication_sha256",
    "source_pending_receipt", "source_batch_sha256",
    "source_batch_wire_sha256", "observed_at", "prepare_inputs_sha256",
    "state_sha256", "transition_sha256", "parent_generation_sha256",
    "parent_state_sha256", "event_closure_sha256",
    "admitted_status_sha256", "non_claims", "marker_sha256",
})
LIVE_BINDING_IDENTITY_KEYS = LIVE_BINDING_KEYS - frozenset({
    "schema", "publication_id", "publication_sha256", "marker_sha256",
})
COMMITTED_KEYS = frozenset({
    "source_batch_sha256", "live_generation_sha256",
    "source_effects_receipt_sha256",
})
SUPERSESSION_NON_CLAIMS = (
    "This receipt preserves one unpublished source batch whose pinned live policy differs from the explicitly admitted replacement policy; it does not publish, acknowledge, reinterpret or discard that batch.",
    "The superseded batch remains immutable and digest-addressed; no source cursor, corpus page, graph, live generation, origin label or external delivery is changed by this transition.",
    "Policy supersession permits a later fresh observation under the replacement policy; it does not claim the old observation was false, the replacement is cognitively valid, or either policy wins a held-out benchmark.",
)
SUPERSESSION_RECEIPT_KEYS = frozenset({
    "schema", "status", "reason", "source_pending_receipt",
    "source_batch_sha256", "source_batch_wire_sha256",
    "old_live_policy_sha256", "replacement_live_policy_sha256",
    "non_claims", "receipt_sha256",
})
SUPERSESSION_MARKER_KEYS = frozenset({
    "schema", "status", "source_batch_sha256", "receipt_sha256",
    "old_live_policy_sha256", "replacement_live_policy_sha256",
    "non_claims",
})
SUCCESSOR_PENDING_KEYS = frozenset({
    "controller_source_pending", "controller_source_live_pending",
    "pulse_status_effects_pending", "controller_source_effects_pending",
    "controller_source_effects_committed", "live_loop_pending",
    "source_replay_pending", "pulse_publication", "dream_publication",
    "consolidation_pending", "brainstem_failure_pending",
})
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _refuse(source, reason):
    source.refuse(reason, phase="stage")


def _wire(owner, source, value, *, memo=False):
    limit = owner["MAX_MEMO_BYTES"] if memo else owner["MAX_STATE_JSON_BYTES"]
    return source.native_bytes(owner, value, ceiling=limit)


def _private(source, held):
    if held.generation is not None and stat.S_IMODE(held.generation["mode"]) != 0o600:
        _refuse(source, "source-publication-file-not-private")


def _receipt(owner, source, batch, raw):
    predecessor = batch["epoch"]["predecessor"]
    return {
        "schema": "sia-controller-source-pending-v1",
        "epoch_id": batch["epoch"]["epoch_id"], "batch_id": batch["batch_id"],
        "epoch_sha256": batch["epoch_sha256"], "batch_sha256": batch["batch_sha256"],
        "batch_wire_sha256": owner["hashlib"].sha256(raw).hexdigest(),
        "batch_bytes": len(raw),
        "parent_batch_sha256": None if predecessor is None else predecessor["source_batch_sha256"],
    }


def _view(source, status, batch=None, receipt=None):
    return {"schema": "sia-controller-source-batch-view-v1", "status": status,
            "batch": batch, "receipt": receipt, "non_claims": list(source.NON_CLAIMS)}


def _authority(owner, source, memo, durable):
    if type(memo) is not dict or type(durable) is not dict \
            or _wire(owner, source, memo, memo=True) != _wire(owner, source, durable, memo=True):
        _refuse(source, "source-publication-memo-authority")
    # The initial fixed-slot increment cannot certify a historical source
    # archive from an invented memo row. Its explicit continuation comes with
    # the later matching live-commit/acknowledgment/archive transition.
    for key in ("source_replay_pending", "pulse_publication", "dream_publication",
                "consolidation_pending", "live_loop_pending",
                "controller_source_committed"):
        if key in memo:
            _refuse(source, "source-publication-other-recovery-authority")


def _successor_archive_path(owner, source, committed):
    directory = source._canonical_path(
        owner, owner["CONTROLLER_SOURCE_ARCHIVE_DIR"])
    return os.path.join(
        directory, committed["source_batch_sha256"] + ".json")


def _successor_predecessor_request(
        owner, source, *, memo, retained_batch, committed, seq):
    """Admit the complete caller-supplied compact predecessor image."""
    if type(memo) is not dict \
            or type(retained_batch) is not dict \
            or type(committed) is not dict \
            or set(committed) != COMMITTED_KEYS \
            or any(type(value) is not str or _HEX.fullmatch(value) is None
                   for value in committed.values()) \
            or type(seq) is not int \
            or not owner["_nonnegative_status_integer"](seq) \
            or memo.get("pulse_seq") != seq \
            or _wire(owner, source, memo.get(
                "controller_source_committed")) \
            != _wire(owner, source, committed) \
            or SUCCESSOR_PENDING_KEYS.intersection(memo):
        _refuse(source, "source-successor-completed-authority")
    if owner["NOTIFY_BASELINE_ATTEMPT_KEY"] in memo:
        _refuse(source, "source-successor-completed-authority")
    source.validate_batch(
        owner, retained_batch, committed["source_batch_sha256"])
    retained_raw = _wire(owner, source, retained_batch)
    try:
        ready = owner["_ready_receipt"](memo)
    except (TypeError, ValueError, RuntimeError, KeyError,
            OverflowError, RecursionError) as exc:
        source.refuse(
            "source-successor-readiness", phase="stage", upstream=exc)
    live = memo.get("live_loop_committed")
    if type(ready) is not dict or ready.get("kind") != "pulse" \
            or type(live) is not dict \
            or live.get("generation_sha256") \
            != committed["live_generation_sha256"] \
            or live.get("publication_id") != ready.get("identity"):
        _refuse(source, "source-successor-readiness")
    return retained_raw


def _completed_successor_authority(
        owner, source, *, memo, durable, retained_batch, committed,
        seq, predecessor):
    """Rejoin supplied predecessor values to the durable compact state."""
    retained_raw = _successor_predecessor_request(
        owner, source, memo=memo, retained_batch=retained_batch,
        committed=committed, seq=seq)
    if type(durable) is not dict \
            or _wire(owner, source, memo, memo=True) \
            != _wire(owner, source, durable, memo=True):
        _refuse(source, "source-successor-completed-authority")
    if predecessor.raw is None or type(predecessor.value) is not dict \
            or predecessor.raw != retained_raw \
            or stat.S_IMODE(predecessor.parent_generation["mode"]) != 0o700:
        _refuse(source, "source-successor-predecessor-archive")
    source.validate_batch(
        owner, predecessor.value, committed["source_batch_sha256"])
    if _wire(owner, source, predecessor.value) != predecessor.raw:
        _refuse(source, "source-successor-predecessor-canonical")
    return retained_raw


def _successor_material(
        owner, source, *, retained_batch, committed, batch,
        expected_batch_sha256):
    import siacontrollersourcerunner as runner

    runner.validate_successor_wal(
        owner, retained_batch=retained_batch, committed=committed,
        successor_batch=batch,
        expected_batch_sha256=expected_batch_sha256)
    raw = _wire(owner, source, batch)
    if type(batch) is not dict or batch.get("batch_sha256") \
            != expected_batch_sha256:
        _refuse(source, "source-successor-batch-pin")
    receipt = _receipt(owner, source, batch, raw)
    if type(receipt) is not dict or set(receipt) != RECEIPT_KEYS \
            or receipt["batch_sha256"] != expected_batch_sha256 \
            or receipt["parent_batch_sha256"] \
            != committed["source_batch_sha256"]:
        _refuse(source, "source-successor-receipt")
    _wire(owner, source, receipt)
    return raw, receipt


@contextlib.contextmanager
def _files(owner, source):
    with contextlib.ExitStack() as stack:
        files = {}

        def observe(name, path, ceiling):
            held = source.HeldFile(owner, path, ceiling, allow_absent=True)
            stack.callback(held.close)
            _private(source, held)
            files[name] = held
            return held

        observe("memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
        observe("batch", owner["CONTROLLER_SOURCE_BATCH_PATH"], owner["MAX_STATE_JSON_BYTES"])

        def named_current():
            for held in files.values():
                held.named_current()

        def current():
            for held in files.values():
                held.current()
            named_current()

        yield files, observe, current, named_current


def stage(owner, *, memo, batch, expected_batch_sha256):
    import siasourcebatch as source

    request = {"memo": memo, "batch": batch, "expected_batch_sha256": expected_batch_sha256}
    # Complete represented request admission precedes descriptor reads,
    # hashing, copies, semantic replay or publication.
    original = _wire(owner, source, request)
    source.validate_batch(owner, batch, expected_batch_sha256)
    raw = _wire(owner, source, batch)
    receipt = _receipt(owner, source, batch, raw)
    pending = dict(memo, controller_source_pending=receipt)
    pending.pop("ready", None)
    pending_raw = _wire(owner, source, pending, memo=True)
    owner["_memo_text"](pending)
    _wire(owner, source, _view(source, "pending", batch, receipt))
    if _wire(owner, source, request) != original:
        _refuse(source, "source-publication-input-changed")

    with _files(owner, source) as (files, observe, current, named_current):
        _authority(owner, source, memo, files["memo"].value)
        has_old_receipt = "controller_source_pending" in memo
        old_receipt = memo.get("controller_source_pending")
        if has_old_receipt and (
                type(old_receipt) is not dict or set(old_receipt) != RECEIPT_KEYS
                or _wire(owner, source, old_receipt) != _wire(owner, source, receipt)):
            _refuse(source, "source-publication-pending-receipt-differs")
        retained = files["batch"]
        if retained.raw is not None and retained.raw != raw:
            _refuse(source, "source-publication-immutable-slot-differs")
        if has_old_receipt and retained.raw is None:
            _refuse(source, "source-publication-pending-batch-missing")

        detached_batch = owner["copy"].deepcopy(batch)
        detached_pending = owner["copy"].deepcopy(pending)
        if _wire(owner, source, request) != original \
                or _wire(owner, source, detached_batch) != raw \
                or _wire(owner, source, pending, memo=True) != pending_raw \
                or _wire(owner, source, detached_pending, memo=True) != pending_raw:
            _refuse(source, "source-publication-detachment-changed")
        current()

        # Exclusive publication closes an exact orphan retry's directory
        # durability window without replacing its existing inode or bytes.
        owner["siaqueue"].fixed_atomic_publish(
            owner["CONTROLLER_SOURCE_BATCH_PATH"], raw, mode=0o600, exclusive=True,
            staging_dir=owner["siaqueue"].staging_dir_for(
                owner["CONTROLLER_SOURCE_BATCH_PATH"],
                authority_roots=(owner["CORPUS"], owner["STATE"], owner["SHARE"])))
        published = observe("batch", owner["CONTROLLER_SOURCE_BATCH_PATH"], owner["MAX_STATE_JSON_BYTES"])
        if published.parent_identity != retained.parent_identity:
            _refuse(source, "source-publication-parent-changed")
        if published.raw != raw:
            _refuse(source, "source-publication-retained-bytes-differ")
        if _wire(owner, source, request) != original \
                or _wire(owner, source, detached_pending, memo=True) != pending_raw:
            _refuse(source, "source-publication-input-changed-after-retention")
        current()
        owner["atomic_write"](owner["MEMO_PATH"], pending_raw.decode("utf-8"), mode=0o600)
        written_memo = observe("memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
        if written_memo.raw != pending_raw:
            _refuse(source, "source-publication-memo-bytes-differ")
        if _wire(owner, source, request) != original \
                or _wire(owner, source, detached_pending, memo=True) != pending_raw:
            _refuse(source, "source-publication-input-changed-after-memo")
        current()
        if _wire(owner, source, request) != original \
                or _wire(owner, source, detached_pending, memo=True) != pending_raw:
            _refuse(source, "source-publication-final-source-check-changed-input")
        named_current()
        memo.clear()
        memo.update(detached_pending)
        # No serialization, digest or caller copy follows the named sweep.
        named_current()
        return None


def recover_orphan(owner, *, memo):
    """Adopt one exact retained batch whose memo receipt did not publish."""
    import siasourcebatch as source

    original = _wire(owner, source, memo, memo=True)
    with _files(owner, source) as (files, observe, current, named_current):
        _authority(owner, source, memo, files["memo"].value)
        held = files["batch"]
        has_pending = "controller_source_pending" in memo
        if has_pending:
            pending = memo.get("controller_source_pending")
            if type(pending) is not dict or set(pending) != RECEIPT_KEYS \
                    or held.raw is None or type(held.value) is not dict:
                _refuse(source, "source-publication-pending-shape-or-file")
            source.validate_batch(
                owner, held.value, pending.get("batch_sha256"))
            raw = _wire(owner, source, held.value)
            if raw != held.raw \
                    or _wire(owner, source, _receipt(
                        owner, source, held.value, raw)) \
                    != _wire(owner, source, pending):
                _refuse(source, "source-publication-pending-receipt-differs")
            current()
            if _wire(owner, source, memo, memo=True) != original:
                _refuse(source, "source-publication-recovery-input-changed")
            named_current()
            # A prior memo replacement may have reached rename but not its
            # directory barrier. Complete that barrier on the admitted parent
            # without replacing the exact pending file or re-publishing WAL.
            os.fsync(files["memo"].directories.fd)
            current()
            if _wire(owner, source, memo, memo=True) != original:
                _refuse(source, "source-publication-recovery-input-changed")
            named_current()
            return False
        if held.raw is None:
            current()
            if _wire(owner, source, memo, memo=True) != original:
                _refuse(source, "source-publication-recovery-input-changed")
            named_current()
            return False
        if any(key in memo for key in (
                "controller_source_live_pending",
                "controller_source_effects_pending",
                "controller_source_effects_committed",
                "pulse_status_effects_pending")):
            _refuse(source, "source-publication-orphan-downstream-authority")
        batch = held.value
        if type(batch) is not dict \
                or type(batch.get("batch_sha256")) is not str:
            _refuse(source, "source-publication-orphan-batch-shape")
        source.validate_batch(owner, batch, batch["batch_sha256"])
        raw = _wire(owner, source, batch)
        if raw != held.raw:
            _refuse(source, "source-publication-orphan-batch-not-canonical")
        receipt = _receipt(owner, source, batch, raw)
        updated = dict(memo, controller_source_pending=receipt)
        updated.pop("ready", None)
        updated_raw = _wire(owner, source, updated, memo=True)
        owner["_memo_text"](updated)
        detached = owner["copy"].deepcopy(updated)
        if _wire(owner, source, detached, memo=True) != updated_raw \
                or _wire(owner, source, memo, memo=True) != original:
            _refuse(source, "source-publication-recovery-detachment-changed")
        current()
        memo_parent_identity = files["memo"].parent_identity
        owner["atomic_write"](
            owner["MEMO_PATH"], updated_raw.decode("utf-8"), mode=0o600)
        written = observe(
            "memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
        if written.parent_identity != memo_parent_identity \
                or written.raw != updated_raw:
            _refuse(source, "source-publication-recovery-memo-differs")
        current()
        if _wire(owner, source, memo, memo=True) != original \
                or _wire(owner, source, detached, memo=True) != updated_raw:
            _refuse(source, "source-publication-recovery-input-changed")
        named_current()
        memo.clear()
        memo.update(detached)
        named_current()
        return True


def read_pending(owner, *, memo):
    import siasourcebatch as source

    original = _wire(owner, source, memo, memo=True)
    with _files(owner, source) as (files, _observe, current, named_current):
        _authority(owner, source, memo, files["memo"].value)
        has_pending = "controller_source_pending" in memo
        pending = memo.get("controller_source_pending")
        held = files["batch"]
        if not has_pending:
            if held.raw is not None:
                _refuse(source, "source-publication-orphan-batch")
            result = _view(source, "absent")
        else:
            if type(pending) is not dict or set(pending) != RECEIPT_KEYS or held.raw is None:
                _refuse(source, "source-publication-pending-shape-or-file")
            batch = held.value
            if type(batch) is not dict:
                _refuse(source, "source-publication-batch-shape")
            source.validate_batch(owner, batch, pending["batch_sha256"])
            raw = _wire(owner, source, batch)
            if raw != held.raw:
                _refuse(source, "source-publication-batch-not-canonical")
            receipt = _receipt(owner, source, batch, raw)
            if _wire(owner, source, receipt) != _wire(owner, source, pending):
                _refuse(source, "source-publication-pending-receipt-differs")
            result = _view(source, "pending", batch, receipt)
        before = _wire(owner, source, result)
        detached = owner["copy"].deepcopy(result)
        if _wire(owner, source, result) != before or _wire(owner, source, detached) != before \
                or _wire(owner, source, memo, memo=True) != original:
            _refuse(source, "source-publication-read-detachment-changed")
        current()
        if _wire(owner, source, result) != before or _wire(owner, source, detached) != before \
                or _wire(owner, source, memo, memo=True) != original:
            _refuse(source, "source-publication-final-source-check-changed-view")
        named_current()
        return detached


def _supersession_marker(owner, source, value):
    if value is None:
        return None
    if type(value) is not dict or set(value) != SUPERSESSION_MARKER_KEYS \
            or value.get("schema") != "sia-controller-source-supersession-marker-v1" \
            or value.get("status") != "preserved-not-published" \
            or any(type(value.get(key)) is not str or _HEX.fullmatch(value[key]) is None
                   for key in ("source_batch_sha256", "receipt_sha256",
                               "old_live_policy_sha256",
                               "replacement_live_policy_sha256")) \
            or value.get("non_claims") != list(SUPERSESSION_NON_CLAIMS):
        _refuse(source, "source-supersession-prior-marker")
    _wire(owner, source, value)
    return value


def _supersession_receipt(owner, source, *, pending, batch,
                          replacement_live_policy_sha256):
    old_pin = batch["epoch"]["expected_live_policy_sha256"]
    body = {
        "schema": "sia-controller-source-supersession-receipt-v1",
        "status": "preserved-not-published",
        "reason": "live-policy-superseded-before-publication",
        "source_pending_receipt": copy.deepcopy(pending),
        "source_batch_sha256": batch["batch_sha256"],
        "source_batch_wire_sha256": pending["batch_wire_sha256"],
        "old_live_policy_sha256": old_pin,
        "replacement_live_policy_sha256": replacement_live_policy_sha256,
        "non_claims": list(SUPERSESSION_NON_CLAIMS),
    }
    body["receipt_sha256"] = source.native_sha(owner, body)
    if set(body) != SUPERSESSION_RECEIPT_KEYS:
        _refuse(source, "source-supersession-receipt-shape")
    return body


def supersede_policy(owner, *, memo, replacement_live_policy,
                     expected_replacement_live_policy_sha256):
    """Preserve and retire one unpublished batch pinned to an old policy.

    The fixed batch is atomically renamed to a private digest-addressed
    archive.  A deterministic refusal receipt is published next.  The memo is
    replaced last, so every interrupted prefix can be resumed without source
    recollection, cursor acknowledgment, content publication or data loss.
    """
    import sialiveloop as live
    import siasourcebatch as source

    request = {
        "memo": memo, "replacement_live_policy": replacement_live_policy,
        "expected_replacement_live_policy_sha256":
            expected_replacement_live_policy_sha256,
    }
    request_raw = _wire(owner, source, request)
    if type(memo) is not dict or type(replacement_live_policy) is not dict \
            or type(expected_replacement_live_policy_sha256) is not str \
            or _HEX.fullmatch(expected_replacement_live_policy_sha256) is None \
            or source._component_sha(owner, replacement_live_policy) \
               != expected_replacement_live_policy_sha256:
        _refuse(source, "source-supersession-replacement-policy-pin")
    try:
        live._policy(replacement_live_policy)
    except (TypeError, ValueError, RuntimeError, KeyError,
            OverflowError, RecursionError) as exc:
        source.refuse(
            "source-supersession-replacement-policy",
            phase="stage", upstream=exc)
    if _wire(owner, source, request) != request_raw:
        _refuse(source, "source-supersession-input-changed")

    with _files(owner, source) as (files, observe, _current, _named_current):
        _authority(owner, source, memo, files["memo"].value)
        forbidden = (SUCCESSOR_PENDING_KEYS - {"controller_source_pending"})
        if forbidden.intersection(memo) \
                or owner["NOTIFY_BASELINE_ATTEMPT_KEY"] in memo \
                or "controller_source_committed" in memo:
            _refuse(source, "source-supersession-downstream-authority")
        pending = memo.get("controller_source_pending")
        if type(pending) is not dict or set(pending) != RECEIPT_KEYS:
            _refuse(source, "source-supersession-pending-receipt")
        fixed = files["batch"]
        _supersession_marker(
            owner, source, memo.get("controller_source_superseded"))

        directory_path = source._canonical_path(
            owner, os.path.join(os.path.dirname(fixed.path),
                                "controller-source-superseded"))
        batch_path = source._canonical_path(
            owner, os.path.join(directory_path,
                                pending["batch_sha256"] + ".batch.json"))
        receipt_path = source._canonical_path(
            owner, os.path.join(directory_path,
                                pending["batch_sha256"] + ".receipt.json"))
        owner["ensure_durable_directory"](directory_path, mode=0o700)
        directory = source._DirectoryChain(
            owner, directory_path, private_terminal=True)
        try:
            archived = source.HeldFile(
                owner, batch_path, owner["MAX_STATE_JSON_BYTES"],
                allow_absent=True)
            try:
                _private(source, archived)
                if fixed.raw is not None and archived.raw is not None:
                    _refuse(source, "source-supersession-archive-state-ambiguous")
                if fixed.raw is None and archived.raw is None:
                    _refuse(source, "source-supersession-batch-absent")
                selected = fixed if fixed.raw is not None else archived
                batch = selected.value
                if type(batch) is not dict:
                    _refuse(source, "source-supersession-batch-shape")
                source.validate_batch(owner, batch, pending["batch_sha256"])
                raw = _wire(owner, source, batch)
                if raw != selected.raw \
                        or _wire(owner, source, _receipt(owner, source, batch, raw)) \
                           != _wire(owner, source, pending):
                    _refuse(source, "source-supersession-pending-join")
                old_pin = batch["epoch"].get("expected_live_policy_sha256")
                if type(old_pin) is not str or _HEX.fullmatch(old_pin) is None \
                        or old_pin == expected_replacement_live_policy_sha256:
                    _refuse(source, "source-supersession-policy-not-changed")
                receipt = _supersession_receipt(
                    owner, source, pending=pending, batch=batch,
                    replacement_live_policy_sha256=
                        expected_replacement_live_policy_sha256)
                receipt_raw = _wire(owner, source, receipt)
                marker = {
                    "schema": "sia-controller-source-supersession-marker-v1",
                    "status": receipt["status"],
                    "source_batch_sha256": receipt["source_batch_sha256"],
                    "receipt_sha256": receipt["receipt_sha256"],
                    "old_live_policy_sha256": receipt["old_live_policy_sha256"],
                    "replacement_live_policy_sha256":
                        receipt["replacement_live_policy_sha256"],
                    "non_claims": list(SUPERSESSION_NON_CLAIMS),
                }
                _supersession_marker(owner, source, marker)
                updated = copy.deepcopy(memo)
                updated.pop("controller_source_pending")
                updated.pop("ready", None)
                updated["controller_source_superseded"] = marker
                updated_raw = _wire(owner, source, updated, memo=True)
                owner["_memo_text"](updated)
                if _wire(owner, source, request) != request_raw:
                    _refuse(source, "source-supersession-input-changed")
                files["memo"].current()

                if fixed.raw is not None:
                    fixed.current()
                    archived.named_current()
                    try:
                        owner["siaqueue"]._rename_noreplace(
                            fixed.directories.fd, fixed.name,
                            directory.fd, os.path.basename(batch_path))
                    except (OSError, ValueError, RuntimeError) as exc:
                        source.refuse(
                            "source-supersession-archive-move",
                            phase="stage", upstream=exc)
                    os.fsync(fixed.directories.fd)
                    os.fsync(directory.fd)
                    archived.close()
                    archived = source.HeldFile(
                        owner, batch_path, owner["MAX_STATE_JSON_BYTES"],
                        allow_absent=False)
                    _private(source, archived)
                    if archived.raw != raw:
                        _refuse(source, "source-supersession-archive-bytes")
                else:
                    archived.current()
                owner["_controller_source_supersession_boundary"](
                    "archive-durable")

                owner["siaqueue"].fixed_atomic_publish(
                    receipt_path, receipt_raw, mode=0o600, exclusive=True,
                    destination_dir_fd=directory.fd,
                    staging_dir=owner["siaqueue"].staging_dir_for(
                        receipt_path, authority_roots=(
                            owner["CORPUS"], owner["STATE"], owner["SHARE"])))
                held_receipt = observe(
                    "supersession-receipt", receipt_path,
                    owner["MAX_STATE_JSON_BYTES"])
                if held_receipt.raw != receipt_raw:
                    _refuse(source, "source-supersession-receipt-bytes")
                archived.current()
                files["memo"].current()
                owner["_controller_source_supersession_boundary"](
                    "receipt-durable")

                owner["atomic_write"](
                    owner["MEMO_PATH"], updated_raw.decode("utf-8"), mode=0o600,
                    destination_dir_fd=files["memo"].directories.fd)
                published = observe(
                    "supersession-memo", owner["MEMO_PATH"],
                    owner["MAX_MEMO_BYTES"])
                if published.raw != updated_raw:
                    _refuse(source, "source-supersession-memo-bytes")
                archived.current()
                held_receipt.current()
                owner["_controller_source_supersession_boundary"]("memo-durable")
                memo.clear()
                memo.update(copy.deepcopy(updated))
                return copy.deepcopy(receipt)
            finally:
                archived.close()
        finally:
            directory.close()


def retain_successor(
        owner, *, memo, retained_batch, committed, batch,
        expected_batch_sha256, seq):
    """Durably retain one exact successor WAL without changing the memo.

    The predecessor's compact completion and readiness remain the only memo
    authority until :func:`recover_successor` adopts these fixed-slot bytes.
    An exact existing successor is an idempotent durability retry; any other
    fixed-slot image is refused.
    """
    import siasourcebatch as source

    _successor_predecessor_request(
        owner, source, memo=memo, retained_batch=retained_batch,
        committed=committed, seq=seq)
    original_memo = _wire(owner, source, memo, memo=True)
    original_retained = _wire(owner, source, retained_batch)
    original_committed = _wire(owner, source, committed)
    original_batch = _wire(owner, source, batch)
    raw, receipt = _successor_material(
        owner, source, retained_batch=retained_batch,
        committed=committed, batch=batch,
        expected_batch_sha256=expected_batch_sha256)
    if raw != original_batch \
            or _wire(owner, source, memo, memo=True) != original_memo \
            or _wire(owner, source, retained_batch) != original_retained \
            or _wire(owner, source, committed) != original_committed:
        _refuse(source, "source-successor-input-changed")
    # Prove that the eventual ordinary pending image fits before the WAL can
    # appear.  This is admission only; retain_successor never publishes it.
    pending = copy.deepcopy(memo)
    pending.pop("controller_source_committed", None)
    pending.pop("ready", None)
    pending["controller_source_pending"] = copy.deepcopy(receipt)
    _wire(owner, source, pending, memo=True)
    owner["_memo_text"](pending)

    def inputs_current():
        if _wire(owner, source, memo, memo=True) != original_memo \
                or _wire(owner, source, retained_batch) \
                != original_retained \
                or _wire(owner, source, committed) \
                != original_committed \
                or _wire(owner, source, batch) != original_batch \
                or batch.get("batch_sha256") != expected_batch_sha256 \
                or memo.get("pulse_seq") != seq:
            _refuse(source, "source-successor-input-changed")

    with _files(owner, source) as (
            files, observe, current, named_current):
        predecessor = observe(
            "predecessor",
            _successor_archive_path(owner, source, committed),
            owner["MAX_STATE_JSON_BYTES"])
        _completed_successor_authority(
            owner, source, memo=memo, durable=files["memo"].value,
            retained_batch=retained_batch, committed=committed, seq=seq,
            predecessor=predecessor)
        fixed = files["batch"]
        if fixed.raw is not None and fixed.raw != raw:
            _refuse(source, "source-successor-fixed-slot-differs")
        inputs_current()
        current()

        owner["siaqueue"].fixed_atomic_publish(
            owner["CONTROLLER_SOURCE_BATCH_PATH"], raw,
            mode=0o600, exclusive=True,
            staging_dir=owner["siaqueue"].staging_dir_for(
                owner["CONTROLLER_SOURCE_BATCH_PATH"],
                authority_roots=(owner["CORPUS"], owner["STATE"],
                                 owner["SHARE"])))
        published = observe(
            "batch", owner["CONTROLLER_SOURCE_BATCH_PATH"],
            owner["MAX_STATE_JSON_BYTES"])
        if published.parent_identity != fixed.parent_identity \
                or published.raw != raw:
            _refuse(source, "source-successor-retained-bytes-differ")
        inputs_current()
        if _wire(owner, source, files["memo"].value, memo=True) \
                != original_memo:
            _refuse(source, "source-successor-completed-memo-changed")
        current()
        inputs_current()
        named_current()
        return None


def recover_successor(
        owner, *, memo, retained_batch, committed, seq):
    """Adopt one exact successor fixed-slot WAL as ordinary pending state."""
    import siasourcebatch as source

    _successor_predecessor_request(
        owner, source, memo=memo, retained_batch=retained_batch,
        committed=committed, seq=seq)
    original_memo = _wire(owner, source, memo, memo=True)
    original_retained = _wire(owner, source, retained_batch)
    original_committed = _wire(owner, source, committed)

    def predecessor_inputs_current():
        if _wire(owner, source, memo, memo=True) != original_memo \
                or _wire(owner, source, retained_batch) \
                != original_retained \
                or _wire(owner, source, committed) \
                != original_committed \
                or memo.get("pulse_seq") != seq:
            _refuse(source, "source-successor-input-changed")

    with _files(owner, source) as (
            files, observe, current, named_current):
        predecessor = observe(
            "predecessor",
            _successor_archive_path(owner, source, committed),
            owner["MAX_STATE_JSON_BYTES"])
        _completed_successor_authority(
            owner, source, memo=memo, durable=files["memo"].value,
            retained_batch=retained_batch, committed=committed, seq=seq,
            predecessor=predecessor)
        fixed = files["batch"]
        predecessor_inputs_current()
        if fixed.raw is None:
            current()
            predecessor_inputs_current()
            named_current()
            return False
        successor = fixed.value
        if type(successor) is not dict \
                or type(successor.get("batch_sha256")) is not str \
                or _HEX.fullmatch(successor["batch_sha256"]) is None:
            _refuse(source, "source-successor-fixed-slot-shape")
        expected_batch_sha256 = successor["batch_sha256"]
        raw, receipt = _successor_material(
            owner, source, retained_batch=retained_batch,
            committed=committed, batch=successor,
            expected_batch_sha256=expected_batch_sha256)
        if raw != fixed.raw:
            _refuse(source, "source-successor-fixed-slot-not-canonical")

        updated = copy.deepcopy(memo)
        updated.pop("controller_source_committed", None)
        updated.pop("ready", None)
        updated["controller_source_pending"] = copy.deepcopy(receipt)
        updated_raw = _wire(owner, source, updated, memo=True)
        owner["_memo_text"](updated)
        detached = owner["copy"].deepcopy(updated)
        if _wire(owner, source, detached, memo=True) != updated_raw:
            _refuse(source, "source-successor-adoption-detachment")
        predecessor_inputs_current()
        current()

        # Replaying the exact exclusive publication fsyncs the destination
        # directory if a prior publisher died after linking the fixed WAL but
        # before reporting its durability boundary.
        owner["siaqueue"].fixed_atomic_publish(
            owner["CONTROLLER_SOURCE_BATCH_PATH"], raw,
            mode=0o600, exclusive=True,
            staging_dir=owner["siaqueue"].staging_dir_for(
                owner["CONTROLLER_SOURCE_BATCH_PATH"],
                authority_roots=(owner["CORPUS"], owner["STATE"],
                                 owner["SHARE"])))
        current()
        predecessor_inputs_current()

        memo_parent_identity = files["memo"].parent_identity
        owner["atomic_write"](
            owner["MEMO_PATH"], updated_raw.decode("utf-8"), mode=0o600)
        written = observe(
            "memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
        if written.parent_identity != memo_parent_identity \
                or written.raw != updated_raw:
            _refuse(source, "source-successor-adoption-memo-differs")
        current()
        if _wire(owner, source, memo, memo=True) != original_memo \
                or _wire(owner, source, detached, memo=True) != updated_raw:
            _refuse(source, "source-successor-adoption-input-changed")
        named_current()
        memo.clear()
        memo.update(detached)
        named_current()
        return True


class _CapturableSuccessor:
    """Keep a fenced completed predecessor pinned across its own WAL swap.

    The caller supplies its existing corpus ownership; this object acquires
    no owner and performs no capture. All named input files remain held until
    the outer operation closes. Only this transaction's successful fixed-slot
    and memo publications replace their respective held observations.
    """

    def __init__(self, owner, source, request, stack):
        self.owner, self.source, self.request, self.stack = (
            owner, source, request, stack)
        if type(owner) is not dict:
            _refuse(source, "source-capturable-owner-shape")
        # Select immutable scalar values before any serialization or copy.
        # A callback cannot change the paths/capacities and have those changed
        # values silently become the transaction's original authority basis.
        self.paths = {name: owner.get(name) for name in (
            "MEMO_PATH", "STATUS_PATH", "GRAPH_PATH",
            "LIVE_CANDIDATE_PATH", "LIVE_STATE_PATH",
            "CONTROLLER_SOURCE_BATCH_PATH", "CONTROLLER_SOURCE_ARCHIVE_DIR",
            "CONTROLLER_SOURCE_EFFECTS_ARCHIVE_DIR", "CORPUS", "STATE", "SHARE",
        )}
        self.capacities = {name: owner.get(name) for name in (
            "MAX_MEMO_BYTES", "MAX_STATE_JSON_BYTES", "MAX_CONFIG_PATH_CHARS",
            "MAX_CONFIG_TEXT_CHARS", "MAX_CONFIG_BYTES",
            "MAX_SOURCE_REPLAY_EVENTS", "MAX_SOURCE_REPLAY_SOURCES",
            "MAX_LEDGER_PENDING_RECORDS", "MAX_JSON_SAFE_INTEGER",
        )}
        self.notification_key = owner.get("NOTIFY_BASELINE_ATTEMPT_KEY")
        if any(type(value) is not int or value <= 0
               for value in self.capacities.values()) \
                or type(self.notification_key) is not str \
                or not self.notification_key:
            _refuse(source, "source-capturable-owner-contract")
        for path in self.paths.values():
            source._canonical_path(owner, path)
        self.basis_current()
        self.request_raw = self.wire(request)
        self.original_request_raw = self.request_raw
        self.basis_current()
        self.memo_raw = self.wire(request["memo"], memo=True)
        self.validate_request()
        self.basis_current()
        if self.wire(request) != self.request_raw:
            _refuse(source, "source-capturable-request-changed")
        self.admitted = copy.deepcopy(request)
        self.files, self.file_values = {}, {}
        self.capture_view = self.capture_view_raw = None
        self.successor = self.successor_raw = None
        self.pending = self.pending_raw = self.detached_pending = None
        self.final_request_raw = None
        self.inputs_current()

    def wire(self, value, *, memo=False, ceiling=None):
        if ceiling is None:
            ceiling = self.capacities[
                "MAX_MEMO_BYTES" if memo else "MAX_STATE_JSON_BYTES"]
        return self.source.native_bytes(self.owner, value, ceiling=ceiling)

    def basis_current(self):
        for name, expected in {**self.paths, **self.capacities,
                               "NOTIFY_BASELINE_ATTEMPT_KEY":
                                   self.notification_key}.items():
            actual = self.owner.get(name)
            if type(actual) is not type(expected) or actual != expected:
                _refuse(self.source, "source-capturable-owner-basis-changed")

    def validate_request(self):
        request = self.request
        memo, status, retained, committed, seq = (
            request[key] for key in (
                "memo", "admitted_status", "retained_batch", "committed", "seq"))
        if type(memo) is not dict or type(status) is not dict \
                or type(retained) is not dict or type(committed) is not dict \
                or set(committed) != COMMITTED_KEYS \
                or any(type(value) is not str or _HEX.fullmatch(value) is None
                       for value in committed.values()) \
                or type(seq) is not int or seq < 0 \
                or seq > self.capacities["MAX_JSON_SAFE_INTEGER"] \
                or type(memo.get("pulse_seq")) is not int \
                or memo["pulse_seq"] != seq \
                or SUCCESSOR_PENDING_KEYS.intersection(memo) \
                or self.wire(memo.get("controller_source_committed")) \
                   != self.wire(committed):
            _refuse(self.source, "source-capturable-completed-authority")
        attempt = request["notification_baseline_attempt"]
        pin = request["expected_notification_baseline_attempt_sha256"]
        if type(attempt) is not dict or type(pin) is not str \
                or _HEX.fullmatch(pin) is None \
                or self.notification_key not in memo \
                or memo[self.notification_key] is None:
            _refuse(self.source, "source-capturable-notification-fence")
        actual = self.owner["_pending_notify_baseline_attempt"](memo)
        if type(actual) is not dict or self.wire(actual) != self.wire(attempt) \
                or self.owner["hashlib"].sha256(self.wire(attempt)).hexdigest() != pin:
            _refuse(self.source, "source-capturable-notification-fence")

    def inputs_current(self):
        self.basis_current()
        if self.wire(self.request) != self.request_raw \
                or self.wire(self.admitted) != self.request_raw:
            _refuse(self.source, "source-capturable-request-changed")
        if self.capture_view is not None \
                and self.wire(self.capture_view) != self.capture_view_raw:
            _refuse(self.source, "source-capturable-predecessor-view-changed")
        if self.successor is not None \
                and self.wire(self.successor) != self.successor_raw:
            _refuse(self.source, "source-capturable-successor-changed")
        if self.pending is not None \
                and self.wire(self.pending, memo=True) != self.pending_raw:
            _refuse(self.source, "source-capturable-pending-changed")
        if self.detached_pending is not None \
                and self.wire(self.detached_pending, memo=True) != self.pending_raw:
            _refuse(self.source, "source-capturable-pending-copy-changed")
        self.basis_current()

    def observe(self, name, path, ceiling, *, required=True, archive=False):
        held = self.source.HeldFile(
            self.owner, path, ceiling, allow_absent=not required)
        self.stack.callback(held.close)
        _private(self.source, held)
        if archive and stat.S_IMODE(held.parent_generation["mode"]) != 0o700:
            _refuse(self.source, "source-capturable-archive-not-private")
        value_raw = None if held.raw is None else self.wire(
            held.value, ceiling=ceiling)
        self.files[name] = held
        self.file_values[name] = value_raw
        self.capacity()
        return held

    def capacity(self):
        # Declared retained-wire reservation, not a Python heap estimate:
        # original full request; each selected current file's raw body;
        # the exact capturable view; successor wire; prospective pending memo;
        # and the complete post-adoption request. Each representation is
        # counted once, even where its contents duplicate another document.
        retained = len(self.original_request_raw)
        for held in self.files.values():
            if held.raw is not None:
                retained += len(held.raw)
        for raw in (self.capture_view_raw, self.successor_raw,
                    self.pending_raw, self.final_request_raw):
            if raw is not None:
                retained += len(raw)
        if retained > self.capacities["MAX_STATE_JSON_BYTES"]:
            _refuse(self.source, "source-capturable-retained-wire-capacity")

    def current(self):
        self.inputs_current()
        for name, held in self.files.items():
            held.current()
            if held.raw is not None and self.wire(
                    held.value, ceiling=held.ceiling) != self.file_values[name]:
                _refuse(self.source, "source-capturable-held-value-changed")
        self.inputs_current()
        # No serialization or defensive copy follows this final descriptor
        # pass: an input-check callback must not change a previously checked
        # file and have the operation return successfully on that old check.
        for held in self.files.values():
            held.current()
        self.basis_current()

    def predecessor(self):
        import siasourceack as acknowledgment

        for name in ("MEMO_PATH", "STATUS_PATH", "GRAPH_PATH",
                     "LIVE_CANDIDATE_PATH", "LIVE_STATE_PATH"):
            self.observe(name, self.paths[name], self.capacities[
                "MAX_MEMO_BYTES" if name == "MEMO_PATH" else "MAX_STATE_JSON_BYTES"])
        self.observe("fixed", self.paths["CONTROLLER_SOURCE_BATCH_PATH"],
                     self.capacities["MAX_STATE_JSON_BYTES"], required=False)
        committed = self.admitted["committed"]
        for name, directory, pin, ceiling in (
                ("source-archive", "CONTROLLER_SOURCE_ARCHIVE_DIR",
                 committed["source_batch_sha256"], "MAX_STATE_JSON_BYTES"),
                ("effects-archive", "CONTROLLER_SOURCE_EFFECTS_ARCHIVE_DIR",
                 committed["source_effects_receipt_sha256"], "MAX_MEMO_BYTES")):
            self.observe(name, os.path.join(self.paths[directory], pin + ".json"),
                         self.capacities[ceiling], archive=True)
        if self.file_values["MEMO_PATH"] != self.memo_raw \
                or self.file_values["STATUS_PATH"] \
                   != self.wire(self.admitted["admitted_status"]) \
                or self.files["source-archive"].raw \
                   != self.wire(self.admitted["retained_batch"]):
            _refuse(self.source, "source-capturable-retained-authority")
        self.current()
        # The real capture-only reader sees the FULL caller memo and status.
        # All authority handles opened above remain live after it closes its
        # own transient contexts and throughout the subsequent storage work.
        self.capture_view = acknowledgment.read_capturable_predecessor(
            self.owner, memo=self.request["memo"],
            admitted_status=self.request["admitted_status"],
            committed=self.request["committed"],
            notification_baseline_attempt=
                self.request["notification_baseline_attempt"],
            expected_notification_baseline_attempt_sha256=
                self.request["expected_notification_baseline_attempt_sha256"])
        self.capture_view_raw = self.wire(self.capture_view)
        view = self.capture_view
        if type(view) is not dict or set(view) != {
                "schema", "status", "batch", "committed",
                "notification_baseline_attempt",
                "expected_notification_baseline_attempt_sha256", "non_claims"} \
                or view["schema"] != "sia-controller-source-capturable-predecessor-v1" \
                or view["status"] != "capturable-not-ready" \
                or self.wire(view["batch"]) != self.files["source-archive"].raw \
                or self.wire(view["committed"]) != self.wire(committed) \
                or self.wire(view["notification_baseline_attempt"]) \
                   != self.wire(self.admitted["notification_baseline_attempt"]) \
                or view["expected_notification_baseline_attempt_sha256"] \
                   != self.admitted["expected_notification_baseline_attempt_sha256"] \
                or view["non_claims"] != list(acknowledgment.CAPTURE_NON_CLAIMS):
            _refuse(self.source, "source-capturable-predecessor-view")
        self.capacity()
        self.current()

    def material(self, batch, expected_batch_sha256):
        raw, receipt = _successor_material(
            self.owner, self.source,
            retained_batch=self.admitted["retained_batch"],
            committed=self.admitted["committed"], batch=batch,
            expected_batch_sha256=expected_batch_sha256)
        if self.wire(batch.get("notification_baseline_attempt")) \
                != self.wire(self.admitted["notification_baseline_attempt"]) \
                or self.owner["hashlib"].sha256(self.wire(
                    batch["notification_baseline_attempt"])).hexdigest() \
                != self.admitted["expected_notification_baseline_attempt_sha256"]:
            _refuse(self.source, "source-capturable-successor-fence")
        self.successor, self.successor_raw = batch, raw
        fixed = self.files["fixed"]
        if fixed.raw is not None and fixed.raw != raw:
            _refuse(self.source, "source-capturable-immutable-wal-differs")
        pending = dict(self.admitted["memo"])
        pending.pop("controller_source_committed")
        pending.pop("ready")
        pending["controller_source_pending"] = receipt
        self.pending, self.pending_raw = pending, self.wire(pending, memo=True)
        encoded = self.owner["_memo_text"](pending)
        if type(encoded) is not str \
                or len(encoded.encode("utf-8")) > self.capacities["MAX_MEMO_BYTES"]:
            _refuse(self.source, "source-capturable-prospective-memo-capacity")
        final_request = dict(self.admitted, memo=pending)
        self.final_request_raw = self.wire(final_request)
        self.capacity()
        # Also reserve the selected files after WAL/memo replacement, before
        # either publication can consume storage. The old descriptor bytes
        # are still represented by the original request and pending images;
        # this remains a document budget, not a total-process-memory claim.
        future_extra = (0 if fixed.raw is not None else len(raw))
        future_extra += max(0, len(self.pending_raw)
                            - len(self.files["MEMO_PATH"].raw))
        retained = len(self.original_request_raw) + sum(
            len(held.raw) for held in self.files.values() if held.raw is not None)
        retained += sum(len(value) for value in (
            self.capture_view_raw, self.successor_raw,
            self.pending_raw, self.final_request_raw))
        if retained + future_extra > self.capacities["MAX_STATE_JSON_BYTES"]:
            _refuse(self.source, "source-capturable-publication-reservation-capacity")
        self.current()
        self.detached_pending = copy.deepcopy(pending)
        self.current()
        roots = tuple(self.paths[name] for name in ("CORPUS", "STATE", "SHARE"))
        self.staging = {}
        for name, path in (("fixed", self.paths["CONTROLLER_SOURCE_BATCH_PATH"]),
                           ("memo", self.paths["MEMO_PATH"])):
            self.staging[name] = self.source._canonical_path(
                self.owner, self.owner["siaqueue"].staging_dir_for(
                    path, authority_roots=roots))
            for leaf in (self.owner["siaqueue"].STAGING_LOCK_NAME,
                         self.owner["siaqueue"].STAGING_PAYLOAD_NAME):
                self.source._canonical_path(
                    self.owner, os.path.join(self.staging[name], leaf))
        self.current()

    def publish_wal(self):
        fixed = self.files["fixed"]
        self.current()
        result = self.owner["siaqueue"].fixed_atomic_publish(
            fixed.path, self.successor_raw, mode=0o600, exclusive=True,
            destination_dir_fd=fixed.directories.fd, nonblocking=True,
            observe_destination=True, staging_dir=self.staging["fixed"])
        self.inputs_current()
        fixed.directories.current()
        if type(result) is not dict or set(result) != {
                "status", "before", "after", "stable"} \
                or result["status"] not in {"published", "existing"} \
                or result["stable"] is not True \
                or result["after"] != self.owner["siaqueue"]._directory_identity(
                    os.fstat(fixed.directories.fd)):
            _refuse(self.source, "source-capturable-wal-publication-observation")
        if fixed.raw is not None:
            # An exact durability retry must not replace the existing WAL's
            # inode. Do not refresh away a changed original descriptor.
            fixed.current()
        else:
            refreshed = self.observe(
                "fixed", fixed.path, fixed.ceiling, required=True)
            if refreshed.parent_identity != fixed.parent_identity \
                    or refreshed.raw != self.successor_raw:
                _refuse(self.source, "source-capturable-wal-readback")
        self.current()

    def adopt(self):
        prior = self.files["MEMO_PATH"]
        self.current()
        self.owner["atomic_write"](
            prior.path, self.pending_raw.decode("utf-8"), mode=0o600,
            destination_dir_fd=prior.directories.fd)
        self.inputs_current()
        prior.directories.current()
        written = self.observe("MEMO_PATH", prior.path, prior.ceiling)
        if written.parent_identity != prior.parent_identity \
                or written.raw != self.pending_raw:
            _refuse(self.source, "source-capturable-memo-readback")
        self.current()
        # Publish the caller's mutable mirror only after the exact durable
        # pending memo and all retained authority have passed their checks.
        self.request["memo"].clear()
        self.request["memo"].update(self.detached_pending)
        self.admitted = dict(self.admitted, memo=self.detached_pending)
        self.request_raw = self.final_request_raw
        self.current()


def retain_capturable_successor(
        owner, *, memo, admitted_status, retained_batch, committed,
        batch, expected_batch_sha256, seq, notification_baseline_attempt,
        expected_notification_baseline_attempt_sha256):
    """Retain an exact fenced successor WAL, leaving the full memo unchanged.

    The explicit notification fence is acquisition history, not readiness or
    delivery. Exact retries retain the existing WAL inode and replay its
    parent-directory durability barrier. No owner scope is acquired here.
    """
    import siasourcebatch as source

    request = {
        "memo": memo, "admitted_status": admitted_status,
        "retained_batch": retained_batch, "committed": committed,
        "batch": batch, "expected_batch_sha256": expected_batch_sha256,
        "seq": seq, "notification_baseline_attempt": notification_baseline_attempt,
        "expected_notification_baseline_attempt_sha256":
            expected_notification_baseline_attempt_sha256,
    }
    with contextlib.ExitStack() as stack:
        transaction = _CapturableSuccessor(owner, source, request, stack)
        transaction.predecessor()
        transaction.material(transaction.admitted["batch"],
                             transaction.admitted["expected_batch_sha256"])
        transaction.publish_wal()
        transaction.current()
        return None


def recover_capturable_successor(
        owner, *, memo, admitted_status, retained_batch, committed, seq,
        notification_baseline_attempt,
        expected_notification_baseline_attempt_sha256):
    """Adopt exact fenced WAL bytes, or return False only for an absent WAL.

    This is a completed-predecessor-only entrypoint. A process interrupted
    after pending-memo replacement must dispatch its actual pending state;
    this function never filters that state into a completed retry. The marker
    remains byte-for-byte represented in the pending memo and successor hash.
    """
    import siasourcebatch as source

    request = {
        "memo": memo, "admitted_status": admitted_status,
        "retained_batch": retained_batch, "committed": committed, "seq": seq,
        "notification_baseline_attempt": notification_baseline_attempt,
        "expected_notification_baseline_attempt_sha256":
            expected_notification_baseline_attempt_sha256,
    }
    with contextlib.ExitStack() as stack:
        transaction = _CapturableSuccessor(owner, source, request, stack)
        transaction.predecessor()
        fixed = transaction.files["fixed"]
        if fixed.raw is None:
            transaction.current()
            return False
        successor = fixed.value
        if type(successor) is not dict \
                or type(successor.get("batch_sha256")) is not str \
                or _HEX.fullmatch(successor["batch_sha256"]) is None:
            _refuse(source, "source-capturable-wal-shape")
        transaction.material(successor, successor["batch_sha256"])
        # This exact immutable replay closes a crash after WAL publication
        # but before the parent sync, before pending memo adoption can run.
        transaction.publish_wal()
        transaction.adopt()
        return True


def _live_binding_marker(owner, source, *, memo, batch, receipt,
                         admitted_status, seq, candidate, transition):
    import sialiveloop as live

    if not owner["_nonnegative_status_integer"](seq) \
            or type(seq) is not int \
            or type(admitted_status) is not dict \
            or not owner["_nonnegative_status_integer"](
                admitted_status.get("pulse_seq")) \
            or type(admitted_status.get("pulse_seq")) is not int \
            or admitted_status["pulse_seq"] > seq \
            or not owner["_nonnegative_status_integer"](
                memo.get("pulse_seq")) \
            or type(memo["pulse_seq"]) is not int \
            or memo["pulse_seq"] != seq:
        _refuse(source, "source-live-binding-sequence")
    if type(candidate) is not dict or set(candidate) != {
            "prepare_inputs", "expected_prepare_inputs_sha256"} \
            or live._sha(candidate["prepare_inputs"]) \
            != candidate["expected_prepare_inputs_sha256"]:
        _refuse(source, "source-live-binding-prepare-pin")
    if type(transition) is not dict \
            or transition.get("state_sha256") != live._sha(
                transition.get("state")) \
            or transition.get("transition_sha256") != live._sha({
                key: value for key, value in transition.items()
                if key != "transition_sha256"}):
        _refuse(source, "source-live-binding-transition-pin")

    parent = memo.get("live_loop_committed")
    if parent is None:
        parent_generation_sha256 = parent_state_sha256 = None
    else:
        if type(parent) is not dict:
            _refuse(source, "source-live-binding-parent")
        parent_generation_sha256 = parent.get("generation_sha256")
        parent_state_sha256 = parent.get("state_sha256")
    closure = batch["event_closure"]
    closure_sha256 = None if closure is None else closure["closure_sha256"]
    fields = {
        "status": "prepared-not-published",
        "seq": seq,
        "source_pending_receipt": owner["copy"].deepcopy(receipt),
        "source_batch_sha256": receipt["batch_sha256"],
        "source_batch_wire_sha256": receipt["batch_wire_sha256"],
        "observed_at": batch["observed_at"],
        "prepare_inputs_sha256": candidate["expected_prepare_inputs_sha256"],
        "state_sha256": transition["state_sha256"],
        "transition_sha256": transition["transition_sha256"],
        "parent_generation_sha256": parent_generation_sha256,
        "parent_state_sha256": parent_state_sha256,
        "event_closure_sha256": closure_sha256,
        "admitted_status_sha256": live._sha(admitted_status),
        "non_claims": list(owner["CONTROLLER_SOURCE_LIVE_BINDING_NON_CLAIMS"]),
    }
    identity = {
        "schema": "sia-controller-source-live-publication-identity-v1",
        "binding": {key: owner["copy"].deepcopy(fields[key])
                    for key in sorted(LIVE_BINDING_IDENTITY_KEYS)},
    }
    publication_sha256 = live._sha(identity)
    marker = {
        "schema": "sia-controller-source-live-pending-v1",
        **fields,
        "publication_id": publication_sha256[:32],
        "publication_sha256": publication_sha256,
    }
    marker["marker_sha256"] = live._sha(marker)
    if set(marker) != LIVE_BINDING_KEYS:
        _refuse(source, "source-live-binding-marker-shape")
    return marker


def stage_live_binding(owner, *, memo, admitted_status, seq):
    """Retain the memo-only write-ahead identity for a source/live join."""
    import siasourcebatch as source
    import sialiveloop as live

    # Admit every caller-owned value before opening an authority descriptor.
    original_memo = _wire(owner, source, memo, memo=True)
    original_status = live._canonical(admitted_status)
    if not owner["_nonnegative_status_integer"](seq) or type(seq) is not int:
        _refuse(source, "source-live-binding-sequence")

    with _files(owner, source) as (files, observe, current, named_current):
        retained_memo = files["memo"]
        _authority(owner, source, memo, retained_memo.value)
        frozen_memo = owner["copy"].deepcopy(retained_memo.value)
        if _wire(owner, source, frozen_memo, memo=True) != original_memo \
                or not owner["_nonnegative_status_integer"](
                    frozen_memo.get("pulse_seq")) \
                or type(frozen_memo["pulse_seq"]) is not int \
                or frozen_memo["pulse_seq"] != seq \
                or "ready" in frozen_memo:
            _refuse(source, "source-live-binding-memo-state")
        try:
            existing = owner["_controller_source_live_binding_marker"](
                frozen_memo)
        except (TypeError, ValueError, KeyError, OverflowError,
                RecursionError) as exc:
            source.refuse(
                "source-live-binding-pending-invalid", phase="stage",
                upstream=exc)
        admitted = owner["_require_status_admission_unchanged"](
            admitted_status)
        if type(admitted) is not dict or not admitted:
            _refuse(source, "source-live-binding-status")
        frozen_status = owner["copy"].deepcopy(admitted)
        if live._canonical(frozen_status) != original_status:
            _refuse(source, "source-live-binding-status")

        source_view = read_pending(owner, memo=frozen_memo)
        if source_view.get("status") != "pending" \
                or type(source_view.get("batch")) is not dict \
                or type(source_view.get("receipt")) is not dict:
            _refuse(source, "source-live-binding-pending-source")
        batch = source_view["batch"]
        receipt = source_view["receipt"]
        candidate = owner["_prepare_controller_source_live_candidate"](
            memo=frozen_memo, admitted_status=frozen_status)
        transition = live.prepare_pulse(**candidate["prepare_inputs"])
        marker = _live_binding_marker(
            owner, source, memo=frozen_memo, batch=batch, receipt=receipt,
            admitted_status=frozen_status, seq=seq, candidate=candidate,
            transition=transition)

        updated = owner["copy"].deepcopy(frozen_memo)
        updated["controller_source_live_pending"] = marker
        updated.pop("ready", None)
        # Prove both serializers' whole-image ceilings before a first write.
        _wire(owner, source, marker)
        _wire(owner, source, updated, memo=True)
        updated_text = owner["_memo_text"](updated)
        updated_raw = updated_text.encode("utf-8")
        if original_memo != _wire(owner, source, memo, memo=True) \
                or original_status != live._canonical(admitted_status):
            _refuse(source, "source-live-binding-input-changed")

        if existing is not None:
            if _wire(owner, source, existing) \
                    != _wire(owner, source, marker):
                _refuse(source, "source-live-binding-pending-differs")
            current()
            owner["_require_status_admission_unchanged"](admitted_status)
            if original_memo != _wire(owner, source, memo, memo=True) \
                    or original_status != live._canonical(admitted_status):
                _refuse(source, "source-live-binding-input-changed")
            named_current()
            return None

        current()
        owner["_require_status_admission_unchanged"](admitted_status)
        if original_memo != _wire(owner, source, memo, memo=True) \
                or original_status != live._canonical(admitted_status):
            _refuse(source, "source-live-binding-input-changed")
        owner["atomic_write"](
            owner["MEMO_PATH"], updated_text, mode=0o600)
        written = observe(
            "memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
        if written.parent_identity != retained_memo.parent_identity \
                or written.raw != updated_raw:
            _refuse(source, "source-live-binding-memo-bytes-differ")
        current()
        owner["_require_status_admission_unchanged"](admitted_status)
        if original_memo != _wire(owner, source, memo, memo=True) \
                or original_status != live._canonical(admitted_status):
            _refuse(source, "source-live-binding-input-changed-after-write")
        detached = owner["copy"].deepcopy(updated)
        if _wire(owner, source, detached, memo=True) \
                != _wire(owner, source, updated, memo=True):
            _refuse(source, "source-live-binding-detachment-changed")
        named_current()
        memo.clear()
        memo.update(detached)
        named_current()
        return None


def stage_status_effects(owner, *, memo, admitted_status, batch,
                         expected_batch_sha256, source_live_pending,
                         candidate, transition, expected_transition_sha256,
                         started_at):
    """Persist the bound counter/history handoff before a closure effect."""
    import siacontrollerstatus as status_effects
    import siasourcebatch as source
    import sialiveloop as live

    originals = {
        "memo": _wire(owner, source, memo, memo=True),
        "batch": _wire(owner, source, batch),
        "admitted_status": live._canonical(admitted_status),
        "source_live_pending": live._canonical(source_live_pending),
        "candidate": live._canonical(candidate),
        "transition": live._canonical(transition),
        "expected_batch_sha256": expected_batch_sha256,
        "expected_transition_sha256": expected_transition_sha256,
        "started_at": started_at,
    }

    def inputs_current():
        try:
            changed = (
                _wire(owner, source, memo, memo=True) != originals["memo"]
                or _wire(owner, source, batch) != originals["batch"]
                or live._canonical(admitted_status)
                != originals["admitted_status"]
                or live._canonical(source_live_pending)
                != originals["source_live_pending"]
                or live._canonical(candidate) != originals["candidate"]
                or live._canonical(transition) != originals["transition"]
                or expected_batch_sha256
                != originals["expected_batch_sha256"]
                or expected_transition_sha256
                != originals["expected_transition_sha256"]
                or started_at != originals["started_at"])
        except (TypeError, ValueError, KeyError, OverflowError,
                RecursionError) as exc:
            source.refuse(
                "source-status-input-representation-changed",
                phase="stage", upstream=exc)
        if changed:
            _refuse(source, "source-status-input-changed")

    def parent_current(memo_image, status_image, binding):
        parent_sha256 = binding["parent_generation_sha256"]
        committed = memo_image.get("live_loop_committed")
        if parent_sha256 is None:
            if committed is not None:
                _refuse(source, "source-status-unbound-live-parent")
            return
        if type(committed) is not dict:
            _refuse(source, "source-status-live-parent-missing")
        try:
            view = owner["_read_committed_live_generation"](
                memo=memo_image, admitted_status=status_image)
        except (TypeError, ValueError, RuntimeError, KeyError,
                OverflowError, RecursionError) as exc:
            source.refuse(
                "source-status-live-parent-invalid", phase="stage",
                upstream=exc)
        generation = view.get("generation")
        if view.get("status") != "available" \
                or type(generation) is not dict \
                or generation.get("generation_sha256") != parent_sha256 \
                or generation.get("state_sha256") \
                != binding["parent_state_sha256"]:
            _refuse(source, "source-status-live-parent-differs")
        if frozen_batch["schema"] == "sia-controller-source-batch-v3" \
                and source.native_bytes(owner, generation) != source.native_bytes(
                    owner, frozen_batch["delivery_input"]["epoch_view"]["parent_generation"]):
            _refuse(source, "source-status-full-live-parent-differs")

    # Pure admission happens before authority descriptors or a durable write.
    status_effects.prepare(
        owner, admitted_status=admitted_status, batch=batch,
        expected_batch_sha256=expected_batch_sha256,
        source_live_pending=source_live_pending, candidate=candidate,
        transition=transition,
        expected_transition_sha256=expected_transition_sha256,
        started_at=started_at)
    inputs_current()

    with _files(owner, source) as (files, observe, current, named_current):
        retained_memo = files["memo"]
        retained_batch = files["batch"]
        _authority(owner, source, memo, retained_memo.value)
        if retained_batch.raw is None \
                or retained_batch.raw != _wire(owner, source, batch):
            _refuse(source, "source-status-retained-batch-differs")
        frozen_memo = owner["copy"].deepcopy(retained_memo.value)
        frozen_batch = owner["copy"].deepcopy(retained_batch.value)
        frozen_status = owner["_require_status_admission_unchanged"](
            admitted_status)
        try:
            binding = owner["_controller_source_live_binding_marker"](
                frozen_memo)
        except (TypeError, ValueError, KeyError, OverflowError,
                RecursionError) as exc:
            source.refuse(
                "source-status-live-binding-invalid", phase="stage",
                upstream=exc)
        if binding is None \
                or _wire(owner, source, binding) \
                != _wire(owner, source, source_live_pending):
            _refuse(source, "source-status-live-binding-differs")
        if "ready" in frozen_memo \
                or type(frozen_memo.get("pulse_seq")) is not int \
                or not owner["_nonnegative_status_integer"](
                    frozen_memo["pulse_seq"]) \
                or frozen_memo["pulse_seq"] != binding["seq"]:
            _refuse(source, "source-status-sequence-or-readiness")
        parent_current(frozen_memo, frozen_status, binding)
        prepared = status_effects.prepare(
            owner, admitted_status=frozen_status, batch=frozen_batch,
            expected_batch_sha256=expected_batch_sha256,
            source_live_pending=binding,
            candidate=owner["copy"].deepcopy(candidate),
            transition=owner["copy"].deepcopy(transition),
            expected_transition_sha256=expected_transition_sha256,
            started_at=started_at)
        handoff = {
            "v": 1, "publication_id": binding["publication_id"],
            "effects": owner["copy"].deepcopy(prepared["effects"]),
            "history": owner["copy"].deepcopy(prepared["history"][-1]),
        }
        has_existing = "pulse_status_effects_pending" in frozen_memo
        existing = frozen_memo.get("pulse_status_effects_pending")
        if has_existing:
            try:
                admitted_handoff = owner["_pending_pulse_status_effects"](
                    frozen_memo)
            except (TypeError, ValueError, RuntimeError) as exc:
                source.refuse(
                    "source-status-handoff-invalid", phase="stage",
                    upstream=exc)
            if admitted_handoff != handoff \
                    or frozen_memo.get("pulse_history") \
                    != prepared["history"]:
                _refuse(source, "source-status-handoff-differs")
        elif frozen_memo.get("pulse_history") != frozen_status["history"]:
            _refuse(source, "source-status-history-authority")

        updated = owner["copy"].deepcopy(frozen_memo)
        updated["pulse_history"] = owner["copy"].deepcopy(
            prepared["history"])
        updated["pulse_status_effects_pending"] = handoff
        _wire(owner, source, handoff)
        _wire(owner, source, updated, memo=True)
        updated_text = owner["_memo_text"](updated)
        updated_raw = updated_text.encode("utf-8")
        inputs_current()
        if has_existing:
            current()
            owner["_require_status_admission_unchanged"](admitted_status)
            inputs_current()
            parent_current(frozen_memo, frozen_status, binding)
            named_current()
            return None

        current()
        owner["_require_status_admission_unchanged"](admitted_status)
        inputs_current()
        parent_current(frozen_memo, frozen_status, binding)
        owner["atomic_write"](
            owner["MEMO_PATH"], updated_text, mode=0o600)
        written = observe(
            "memo", owner["MEMO_PATH"], owner["MAX_MEMO_BYTES"])
        if written.parent_identity != retained_memo.parent_identity \
                or written.raw != updated_raw:
            _refuse(source, "source-status-memo-bytes-differ")
        current()
        owner["_require_status_admission_unchanged"](admitted_status)
        inputs_current()
        parent_current(updated, frozen_status, binding)
        detached = owner["copy"].deepcopy(updated)
        if _wire(owner, source, detached, memo=True) \
                != _wire(owner, source, updated, memo=True):
            _refuse(source, "source-status-detachment-changed")
        named_current()
        owner["_require_status_admission_unchanged"](admitted_status)
        inputs_current()
        parent_current(updated, frozen_status, binding)
        memo.clear()
        memo.update(detached)
        named_current()
        return None
