"""Inert fixed-slot source batch retention, owned by the active core.

The pending slot is immutable except for an exact byte retry. It is not a
live generation, source acknowledgment or history archive. No current
configuration, source collector, page renderer or live producer runs here.
"""

import contextlib
import stat


RECEIPT_KEYS = frozenset({
    "schema", "epoch_id", "batch_id", "epoch_sha256", "batch_sha256",
    "batch_wire_sha256", "batch_bytes", "parent_batch_sha256",
})


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
