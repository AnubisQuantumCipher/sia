"""Compact checkpoint epoch and delta projection for source continuation.

Construction is pure. Independent completed-source/root/seed admission must
bind the supplied predecessor and checkpoint before capture can use it. Old
source capture and publication readers intentionally do not admit this schema.
"""

import hashlib
import json
import contextlib
import os

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
CAPTURE_NON_CLAIMS = NON_CLAIMS + (
    "Capture acquires actual declared collectors under ordinary owner and descriptor checks; supplied event truth and complete raw machine history are not established.",
    "This capture omits controller delivery and idle processing and cannot be consumed as a legacy or publishable controller batch. No cursor acknowledgment, page publication, live generation or readiness is authorized.",
    "The retained root and legacy archive remain required for bootstrap ancestry. The embedded parent checkpoint is a replay result, not permission to replace source authority.",
)
CAPTURE_IDLE_NON_CLAIMS = NON_CLAIMS + (
    "Actual declared collectors and, only on empty returns, native idle history are acquired under ordinary owner and descriptor checks. These are local observations, not complete raw machine history or source truth.",
    "This capture retains episode-bound idle input but omits controller delivery processing. It is not a publishable controller transaction, source acknowledgment, gist publication, readiness or cognitive authorization.",
    "The retained root and original archive remain required for ancestry. The embedded checkpoint preserves first event records; it is not permission to replace source authority.",
)


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
    if checkpoint["schema"] not in {"sia-event-replay-checkpoint-v2", "sia-event-replay-checkpoint-v3"}:
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


def project_capture_entry(owner, *, epoch, expected_epoch_sha256, checkpoint, returns, closure, observed_at):
    entry = {"source_returns": returns, "expected_source_returns_sha256": returns["returns_sha256"],
             "event_batches": source._validate_closure(owner, closure, returns)}
    return project(owner, epoch=epoch, expected_epoch_sha256=expected_epoch_sha256, checkpoint=checkpoint,
                   entry=entry, expected_entry_sha256=hashlib.sha256(_wire(owner, entry)).hexdigest(),
                   observed_at=observed_at)


def validate_capture(owner, batch, expected_batch_sha256):
    """Pure retained-image validation; do not authenticate its root or archive."""
    raw = _wire(owner, batch)
    with_idle = type(batch) is dict and batch.get("schema") == "sia-controller-source-checkpoint-capture-v2"
    source._keys(batch, source.BATCH_KEYS | {"parent_checkpoint"} | ({"idle_input"} if with_idle else set()), "checkpoint-capture-shape")
    if batch["schema"] not in {"sia-controller-source-checkpoint-capture-v1", "sia-controller-source-checkpoint-capture-v2"} \
            or batch["status"] != "captured-not-published" \
            or batch["non_claims"] != list(CAPTURE_IDLE_NON_CLAIMS if with_idle else CAPTURE_NON_CLAIMS) \
            or type(batch["batch_id"]) is not str or source._OPERATION.fullmatch(batch["batch_id"]) is None:
        source.refuse("checkpoint-capture-contract")
    source._hex(expected_batch_sha256, "checkpoint-capture-pin")
    if batch["batch_sha256"] != expected_batch_sha256 \
            or source.native_sha(owner, {key: value for key, value in batch.items() if key != "batch_sha256"}) \
            != expected_batch_sha256:
        source.refuse("checkpoint-capture-pin")
    checkpoints.blocks._pin(_wire(owner, batch["epoch"]), batch["epoch_sha256"])
    source._keys(batch["epoch"], _KEYS, "checkpoint-epoch-shape")
    parent = checkpoints.admit(owner, checkpoint=batch["parent_checkpoint"],
                               expected_checkpoint_sha256=batch["epoch"]["checkpoint_sha256"])
    _validate(owner, batch["epoch"], parent, batch["observed_at"])
    source._validate_observation(owner, batch)
    projected = project_capture_entry(
        owner, epoch=batch["epoch"], expected_epoch_sha256=batch["epoch_sha256"], checkpoint=parent,
        returns=batch["source_returns"], closure=batch["event_closure"], observed_at=batch["observed_at"])
    if _wire(owner, projected) != _wire(owner, batch["intake_projection"]):
        source.refuse("checkpoint-capture-projection-binding")
    if with_idle:
        if parent["schema"] != "sia-event-replay-checkpoint-v3":
            source.refuse("checkpoint-idle-episode-records-required")
        if any(run["events"] for run in batch["source_returns"]["runs"]):
            if batch["idle_input"] is not None:
                source.refuse("idle-input-on-nonempty-source-batch")
        else:
            import siacontrolleridle
            siacontrolleridle.validate_checkpoint(owner, epoch=batch["epoch"], projection=projected,
                                                 observed_at=batch["observed_at"], idle_input=batch["idle_input"])
    if _wire(owner, batch) != raw:
        source.refuse("checkpoint-capture-image-changed")


def capture_root(owner, *, memo, admitted_status, directory, expected_root_sha256, observed_at):
    """Capture root-bound collector observations without delivery or idle."""
    return _capture_root(owner, memo=memo, admitted_status=admitted_status, directory=directory,
                         expected_root_sha256=expected_root_sha256, observed_at=observed_at, with_idle=False)


def capture_root_idle(owner, *, memo, admitted_status, directory, expected_root_sha256, observed_at):
    """Capture root-bound sources and empty-pulse idle input, never delivery."""
    return _capture_root(owner, memo=memo, admitted_status=admitted_status, directory=directory,
                         expected_root_sha256=expected_root_sha256, observed_at=observed_at, with_idle=True)


def _capture_root(owner, *, memo, admitted_status, directory, expected_root_sha256, observed_at, with_idle):
    """Capture actual collectors after read-only acknowledged-root bootstrap.

    The existing root and final-entry block must already be retained. This
    entry point writes neither seed nor active head. It is not yet a resident
    controller transaction: delivery processing and publication remain
    required integration work. The explicit idle variant adds episode-bound
    idle input, not durable consolidation.
    """
    import siahistoryroot as roots
    import siasourceack as ack

    source._hex(expected_root_sha256, "checkpoint-root-pin")
    memo_raw, status_raw = _wire(owner, memo), _wire(owner, admitted_status)
    limit = min(owner["MAX_STATE_JSON_BYTES"], checkpoints.blocks.MAX_DOCUMENT_BYTES)
    with owner["brainstem_owner"](), owner["corpus_owner"](), contextlib.ExitStack() as stack:
        directory_hold = source._DirectoryChain(owner, directory, private_terminal=True)
        stack.callback(directory_hold.close)

        def hold(name, pin):
            held = ack._HeldRaw(owner, source, os.path.join(directory, name), limit, allow_absent=False)
            stack.callback(held.close)
            checkpoints.blocks._pin(held.raw, pin)
            return held

        root_file = hold("root-" + expected_root_sha256 + ".json", expected_root_sha256)
        view = ack.read_completed(owner, memo=memo, admitted_status=admitted_status)
        if view.get("status") != "available" or view.get("committed") != memo.get("controller_source_committed"):
            source.refuse("checkpoint-source-authority")
        prior, committed = view["batch"], view["committed"]
        prior_raw, committed_raw = _wire(owner, prior), _wire(owner, committed)
        block = checkpoints.blocks.prepare_captured(
            owner, batch=prior, expected_batch_sha256=committed["source_batch_sha256"],
            parent=None, expected_parent_sha256=None)
        block_raw = _wire(owner, block)
        block_pin = hashlib.sha256(block_raw).hexdigest()
        expected_root = {"schema": "sia-source-history-root-v1", "status": "root-retained-not-activated",
                         "epoch_id": prior["epoch"]["epoch_id"], "committed": committed,
                         "legacy_epoch_sha256": prior["epoch_sha256"],
                         "legacy_history_sha256": prior["epoch"]["expected_history_sha256"],
                         "final_entry_block_sha256": block_pin, "non_claims": list(roots.NON_CLAIMS)}
        if _wire(owner, expected_root) != root_file.raw:
            source.refuse("checkpoint-root-source-binding")
        block_file = hold(block_pin + ".json", block_pin)
        if block_file.raw != block_raw:
            source.refuse("checkpoint-root-entry-binding")
        history = json.loads(_wire(owner, prior["epoch"]["history"]))
        history["entries"].append(json.loads(_wire(owner, block["entry"])))
        request = {"history": history, "expected_history_sha256": source._component_sha(owner, history),
                   "observed_at": prior["observed_at"], **{key: prior["epoch"][key] for key in _DOC_KEYS}}
        request_raw = _wire(owner, request)
        checkpoint = checkpoints.bootstrap_incremental(
            owner, request=request, expected_request_sha256=hashlib.sha256(request_raw).hexdigest())
        if _wire(owner, checkpoint["intake"]) != _wire(owner, prior["intake_projection"]["intake"]) \
                or _wire(owner, checkpoint["source_non_claims"]) != _wire(owner, prior["intake_projection"]["source_non_claims"]):
            source.refuse("checkpoint-source-intake-fidelity")
        if with_idle:
            checkpoint = checkpoints._with_episodes(owner, checkpoint, request, hashlib.sha256(request_raw).hexdigest())
        epoch = prepare_epoch(owner, checkpoint=checkpoint,
                              expected_checkpoint_sha256=hashlib.sha256(_wire(owner, checkpoint)).hexdigest(),
                              committed=committed, root_sha256=expected_root_sha256, observed_at=observed_at)

        def current(files):
            if _wire(owner, memo) != memo_raw or _wire(owner, admitted_status) != status_raw:
                source.refuse("checkpoint-capture-authority-changed")
            source._durable_successor_authority(owner, files, memo, committed)
            present = ack.read_completed(owner, memo=memo, admitted_status=admitted_status)
            if present.get("status") != "available" or _wire(owner, present.get("batch")) != prior_raw \
                    or _wire(owner, present.get("committed")) != committed_raw:
                source.refuse("checkpoint-capture-source-changed")
            root_file.current()
            block_file.current()
            directory_hold.current()

        return source._capture_locked(
            owner, memo=memo, epoch=epoch, expected_epoch_sha256=hashlib.sha256(_wire(owner, epoch)).hexdigest(),
            observed_at=observed_at, authority=current, checkpoint=checkpoint, checkpoint_idle=with_idle)
