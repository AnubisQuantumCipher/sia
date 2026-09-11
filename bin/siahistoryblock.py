"""Storage-free, bounded links for the forthcoming source continuation path.

Each call accepts one separately pinned native history entry and, optionally,
one separately pinned predecessor block. It emits one detached block with a
back-reference, never the transitive prefix. Every document retains the
original source-native single-document ceiling. There is no catch-and-retry
larger envelope and no filesystem, collector, clock or publication operation.

The caller must obtain entry/source authority through the real source reader
and persist/replay the chain separately. This primitive cannot replace source
validation, a durable root or a live-state continuation check.
"""

import hashlib
import json
import math
import re

import siasourcebatch as source


MAX_DOCUMENT_BYTES = 16_777_216
SCHEMA = "sia-source-history-block-v1"
NON_CLAIMS = (
    "This block binds supplied native JSON bytes and an immediate predecessor; it does not validate collector semantics, nested event proofs or source truth.",
    "A supplied source-batch digest is a reference, not proof of source capture, publication, acknowledgment or durable archive availability.",
    "A null predecessor begins this represented chain only; it does not establish machine genesis or absence of earlier history.",
    "Immediate linkage does not establish whole-chain completeness, unique ancestry, absence of earlier duplicate captures or a durable trusted root.",
    "No prefix is copied into this block; historical preservation requires retaining and verifying referenced blocks, which this storage-free operation does not do.",
    "This is not a live-state transition, cognitive authorization, held-out win or JACKAL assurance. All nested source nonclaims remain controlling.",
)
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_KEYS = frozenset({"schema", "status", "epoch_id", "observed_at",
                   "source_batch_sha256", "parent_sha256", "entry",
                   "entry_sha256", "non_claims"})
_ENTRY_KEYS = frozenset({"source_returns", "expected_source_returns_sha256",
                         "event_batches"})


class HistoryBlockRefusal(ValueError):
    def __init__(self, reason):
        self.reason = reason
        self.non_claims = list(NON_CLAIMS)
        super().__init__("source history block refused: " + reason)


def _refuse(reason):
    raise HistoryBlockRefusal(reason)


def _wire(value):
    try:
        return source.native_bytes(
            {"json": json, "math": math, "MAX_STATE_JSON_BYTES": MAX_DOCUMENT_BYTES},
            value)
    except source.SourceBatchRefusal as exc:
        raise HistoryBlockRefusal(exc.reason) from exc


def _digest(value):
    return type(value) is str and _HEX.fullmatch(value) is not None


def _pin(raw, expected):
    if not _digest(expected) or hashlib.sha256(raw).hexdigest() != expected:
        _refuse("external-pin")


def _entry(value):
    if type(value) is not dict or set(value) != _ENTRY_KEYS \
            or type(value["source_returns"]) is not dict \
            or not _digest(value["expected_source_returns_sha256"]) \
            or type(value["event_batches"]) is not list:
        _refuse("entry-shape")


def _metadata(epoch_id, observed_at, source_batch_sha256):
    if type(epoch_id) is not str or not epoch_id or len(epoch_id) > 256 \
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", epoch_id) is None:
        _refuse("epoch-id")
    if type(observed_at) is not int or not 0 <= observed_at <= source._live.MAX_SAFE_INTEGER:
        _refuse("observation-clock")
    if not _digest(source_batch_sha256):
        _refuse("source-batch-pin")


def _parent(value):
    if type(value) is not dict or set(value) != _KEYS \
            or value["schema"] != SCHEMA \
            or value["status"] != "linked-not-published" \
            or value["non_claims"] != list(NON_CLAIMS) \
            or value["parent_sha256"] is not None and not _digest(value["parent_sha256"]):
        _refuse("parent-contract")
    _metadata(value["epoch_id"], value["observed_at"], value["source_batch_sha256"])
    _entry(value["entry"])
    _pin(_wire(value["entry"]), value["entry_sha256"])


def prepare(*, epoch_id, entry, expected_entry_sha256, source_batch_sha256,
            observed_at, parent, expected_parent_sha256):
    """Return one inert link; pin arguments come from the caller's authority.

    Hashes use source-native ASCII canonical JSON, including the entry pin.
    Nested component hashes retain their own meanings and are not redefined.
    Null parent and null parent pin are required together. Equal observation
    clocks are allowed; clock rollback and immediate capture reuse refuse.
    """
    # Bound both supplied documents before hashing or detaching either.
    entry_raw = _wire(entry)
    parent_raw = _wire(parent)
    _metadata(epoch_id, observed_at, source_batch_sha256)
    _entry(entry)
    _pin(entry_raw, expected_entry_sha256)
    if parent is None:
        if expected_parent_sha256 is not None:
            _refuse("absent-parent-pin")
    else:
        _pin(parent_raw, expected_parent_sha256)
        _parent(parent)
        if parent["epoch_id"] != epoch_id:
            _refuse("epoch-discontinuity")
        if parent["observed_at"] > observed_at:
            _refuse("clock-rollback")
        if parent["source_batch_sha256"] == source_batch_sha256:
            _refuse("immediate-capture-reuse")
    result = {
        "schema": SCHEMA, "status": "linked-not-published",
        "epoch_id": epoch_id, "observed_at": observed_at,
        "source_batch_sha256": source_batch_sha256,
        "parent_sha256": expected_parent_sha256,
        "entry": entry, "entry_sha256": expected_entry_sha256,
        "non_claims": list(NON_CLAIMS),
    }
    result_raw = _wire(result)
    detached = json.loads(result_raw)
    if _wire(detached) != result_raw or _wire(result) != result_raw \
            or _wire(entry) != entry_raw or _wire(parent) != parent_raw:
        _refuse("input-or-output-changed")
    return detached


def prepare_captured(owner, *, batch, expected_batch_sha256,
                     parent, expected_parent_sha256):
    """Extract one entry through the existing complete source validator.

    A root may anchor a retained legacy capture with its own prefix. That
    prefix remains in the referenced source archive, not in this new block.
    Archive retention and committed authority must be established separately.
    An immediate parent must match the source epoch's explicit predecessor.
    """
    return _prepare_captured(owner, batch=batch, expected_batch_sha256=expected_batch_sha256,
                             parent=parent, expected_parent_sha256=expected_parent_sha256)


def prepare_checkpoint_capture(owner, *, batch, expected_batch_sha256,
                               parent, expected_parent_sha256):
    """Extract a fully validated compact capture with a mandatory predecessor.

    This preserves the current raw return/closure entry for durable chain
    retention. It does not retain the capture archive, admit its root, publish
    a live generation or advance source authority. The parent is an explicit
    represented premise, not an inferred or newly fabricated genesis.
    """
    return _prepare_captured(owner, batch=batch, expected_batch_sha256=expected_batch_sha256,
                             parent=parent, expected_parent_sha256=expected_parent_sha256, checkpoint=True)


def _prepare_captured(owner, *, batch, expected_batch_sha256,
                      parent, expected_parent_sha256, checkpoint=False):
    batch_raw = _wire(batch)
    parent_raw = _wire(parent)
    if checkpoint:
        import siasourcecheckpoint
        if parent is None or type(batch) is not dict \
                or batch.get("schema") != "sia-controller-source-checkpoint-capture-v3":
            _refuse("checkpoint-capture-and-parent-required")
        siasourcecheckpoint.validate_capture(owner, batch, expected_batch_sha256)
    else:
        source.validate_batch(owner, batch, expected_batch_sha256)
    if parent is not None:
        _pin(parent_raw, expected_parent_sha256)
        _parent(parent)
        predecessor = batch["epoch"]["predecessor"]
        if type(predecessor) is not dict \
                or predecessor.get("source_batch_sha256") != parent["source_batch_sha256"]:
            _refuse("source-predecessor-binding")
    entry = {
        "source_returns": batch["source_returns"],
        "expected_source_returns_sha256": batch["source_returns"]["returns_sha256"],
        "event_batches": [
            {"batch": member, "expected_batch_sha256": member["batch_sha256"]}
            for member in ([] if batch["event_closure"] is None
                           else batch["event_closure"]["batches"])],
    }
    result = prepare(
        epoch_id=batch["epoch"]["epoch_id"], entry=entry,
        expected_entry_sha256=hashlib.sha256(_wire(entry)).hexdigest(),
        source_batch_sha256=expected_batch_sha256, observed_at=batch["observed_at"],
        parent=parent, expected_parent_sha256=expected_parent_sha256)
    if _wire(batch) != batch_raw or _wire(parent) != parent_raw:
        _refuse("capture-input-changed")
    return result
