"""Compact checkpoint epoch and delta projection for source continuation.

Construction is pure. Independent completed-source/root/seed admission must
bind the supplied predecessor and checkpoint before capture can use it. Old
source capture and publication readers intentionally do not admit this schema.
"""

import hashlib
import json

import siaeventcheckpoint as checkpoints
import siasourcebatch as source


NON_CLAIMS = source.NON_CLAIMS + (
    "This epoch references an incremental checkpoint, not an embedded complete raw history. Original archives and the independently admitted root remain required.",
    "Supplied predecessor/root/checkpoint pins bind represented values only; this pure constructor does not read or authenticate acknowledged source authority, retain a seed or activate continuation.",
    "Projection preserves the represented checkpoint and current entry semantics, not actual collector execution, delivery, idle input, cursor acknowledgment or a live publication.",
)
_DOC_KEYS = set(checkpoints._CONTEXT_KEYS) - {"expected_history_sha256"}
_KEYS = _DOC_KEYS | {"schema", "epoch_id", "started_at", "observed_at", "predecessor",
                     "root_sha256", "checkpoint_sha256", "non_claims"}
_COMMIT_KEYS = {"source_batch_sha256", "live_generation_sha256", "source_effects_receipt_sha256"}


def _wire(owner, value):
    return checkpoints._wire(owner, value)


def _validate(owner, epoch, checkpoint, observed_at):
    source._keys(epoch, _KEYS, "checkpoint-epoch-shape")
    if epoch["schema"] != "sia-controller-source-checkpoint-epoch-v1" \
            or epoch["non_claims"] != list(NON_CLAIMS):
        source.refuse("checkpoint-epoch-contract")
    if type(observed_at) is not int or epoch["observed_at"] != observed_at \
            or type(epoch["observed_at"]) is not int \
            or observed_at < checkpoint["observed_at"] \
            or epoch["epoch_id"] != checkpoint["intake"]["epoch_id"] \
            or type(epoch["started_at"]) is not int \
            or epoch["started_at"] != checkpoint["intake"]["started_at"]:
        source.refuse("checkpoint-epoch-identity-or-clock")
    source._hex(epoch["root_sha256"], "checkpoint-root-pin")
    source._keys(epoch["predecessor"], _COMMIT_KEYS, "checkpoint-predecessor-shape")
    for value in epoch["predecessor"].values():
        source._hex(value, "checkpoint-predecessor-pin")
    checkpoints.blocks._pin(_wire(owner, checkpoint), epoch["checkpoint_sha256"])
    if checkpoint["schema"] != "sia-event-replay-checkpoint-v2":
        source.refuse("checkpoint-incremental-accounting-required")
    source._validate_epoch_context(owner, epoch)
    for name in _DOC_KEYS:
        if _wire(owner, epoch[name]) != _wire(owner, checkpoint["context"][name]):
            source.refuse("checkpoint-epoch-context-drift")


def prepare_epoch(owner, *, checkpoint, expected_checkpoint_sha256, committed, root_sha256, observed_at):
    """Build a compact reference epoch without claiming source authority."""
    checkpoint_raw, committed_raw = _wire(owner, checkpoint), _wire(owner, committed)
    admitted = checkpoints.admit(owner, checkpoint=checkpoint,
                                 expected_checkpoint_sha256=expected_checkpoint_sha256)
    epoch = {"schema": "sia-controller-source-checkpoint-epoch-v1",
             "epoch_id": admitted["intake"]["epoch_id"], "started_at": admitted["intake"]["started_at"],
             "observed_at": observed_at, "checkpoint_sha256": expected_checkpoint_sha256,
             "root_sha256": root_sha256, "predecessor": json.loads(committed_raw),
             **{name: admitted["context"][name] for name in _DOC_KEYS}, "non_claims": list(NON_CLAIMS)}
    _validate(owner, epoch, admitted, observed_at)
    raw = _wire(owner, epoch)
    detached = json.loads(raw)
    if _wire(owner, checkpoint) != checkpoint_raw or _wire(owner, admitted) != checkpoint_raw \
            or _wire(owner, committed) != committed_raw or _wire(owner, epoch) != raw \
            or _wire(owner, detached) != raw:
        source.refuse("checkpoint-epoch-input-or-output-changed")
    return detached


def project(owner, *, epoch, expected_epoch_sha256, checkpoint, entry, expected_entry_sha256, observed_at):
    """Project one entry under the exact compact epoch; acquire no sources.

    Each supplied document has its original ceiling. No compound input is
    serialized, and the returned delta projection has its own original cap.
    """
    epoch_raw, checkpoint_raw, entry_raw = (_wire(owner, value) for value in (epoch, checkpoint, entry))
    checkpoints.blocks._pin(epoch_raw, expected_epoch_sha256)
    checkpoints.blocks._pin(entry_raw, expected_entry_sha256)
    selected = json.loads(epoch_raw)
    source._keys(selected, _KEYS, "checkpoint-epoch-shape")
    admitted = checkpoints.admit(owner, checkpoint=checkpoint,
                                 expected_checkpoint_sha256=selected["checkpoint_sha256"])
    _validate(owner, selected, admitted, observed_at)
    delta = {"schema": "sia-event-replay-delta-v1", "parent_checkpoint_sha256": selected["checkpoint_sha256"],
             "entry": json.loads(entry_raw), "observed_at": observed_at,
             "non_claims": list(checkpoints.DELTA_NON_CLAIMS)}
    delta_raw = _wire(owner, delta)
    result = checkpoints.project_delta(
        owner, checkpoint=admitted, expected_checkpoint_sha256=selected["checkpoint_sha256"],
        delta=delta, expected_delta_sha256=hashlib.sha256(delta_raw).hexdigest())
    result_raw = _wire(owner, result)
    detached = json.loads(result_raw)
    if _wire(owner, epoch) != epoch_raw or _wire(owner, selected) != epoch_raw \
            or _wire(owner, checkpoint) != checkpoint_raw or _wire(owner, admitted) != checkpoint_raw \
            or _wire(owner, entry) != entry_raw or _wire(owner, delta) != delta_raw \
            or _wire(owner, result) != result_raw or _wire(owner, detached) != result_raw:
        source.refuse("checkpoint-source-projection-changed")
    return detached
