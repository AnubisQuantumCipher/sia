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
