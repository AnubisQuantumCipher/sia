"""Closed dispatchers for resident controller-source transactions.

The caller supplies the resident ``sialib`` global namespace as ``owner`` and
a lazy, zero-argument ``operation`` that constructs the initial source-capture
request.  Durable source-owned prefixes are always resumed without invoking
that operation or allocating another pulse sequence.  The v1 entry remains
terminal at a completed transaction.  The additive v2 entry advances a
completed transaction only through an explicit successor epoch, capture front
door, and fixed-slot write-ahead batch.
"""

import copy
import re


_REQUEST_KEYS = frozenset({
    "epoch", "expected_epoch_sha256", "observed_at",
})
_SOURCE_PENDING_KEYS = frozenset({
    "controller_source_pending",
    "controller_source_live_pending",
    "pulse_status_effects_pending",
    "controller_source_effects_pending",
    "controller_source_effects_committed",
})
_COMMITTED_KEYS = frozenset({
    "source_batch_sha256", "live_generation_sha256",
    "source_effects_receipt_sha256",
})
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _refuse(reason):
    raise RuntimeError("controller source runner refused: " + reason)


def _history_entry(batch):
    """Return the exact history row contributed by one retained batch."""
    if type(batch) is not dict or type(batch.get("source_returns")) is not dict:
        _refuse("successor-wal-history")
    closure = batch.get("event_closure")
    if closure is None:
        batches = []
    elif type(closure) is dict and type(closure.get("batches")) is list:
        batches = closure["batches"]
    else:
        _refuse("successor-wal-history")
    try:
        return {
            "source_returns": copy.deepcopy(batch["source_returns"]),
            "expected_source_returns_sha256":
                batch["source_returns"]["returns_sha256"],
            "event_batches": [
                {
                    "batch": copy.deepcopy(member),
                    "expected_batch_sha256": member["batch_sha256"],
                }
                for member in batches
            ],
        }
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise RuntimeError(
            "controller source runner refused: successor-wal-history") \
            from exc


def validate_successor_wal(
        owner, *, retained_batch, committed, successor_batch,
        expected_batch_sha256):
    """Validate the complete predecessor/history relationship of a WAL.

    Batch validation is delegated to the source boundary first.  This
    additional check proves that the new retained batch is the one-step
    continuation of the exact compact completion authority supplied by the
    caller; it neither reads current sources nor publishes state.
    """
    if type(owner) is not dict:
        raise TypeError("owner must be a globals-style dictionary")
    import siasourcebatch as source

    if type(retained_batch) is not dict \
            or type(successor_batch) is not dict \
            or type(committed) is not dict \
            or set(committed) != _COMMITTED_KEYS \
            or any(type(value) is not str or _HEX.fullmatch(value) is None
                   for value in committed.values()) \
            or type(retained_batch.get("batch_sha256")) is not str \
            or retained_batch.get("batch_sha256") \
               != committed["source_batch_sha256"]:
        _refuse("successor-wal-commit")
    if type(expected_batch_sha256) is not str \
            or _HEX.fullmatch(expected_batch_sha256) is None \
            or successor_batch.get("batch_sha256") != expected_batch_sha256:
        _refuse("successor-wal-successor-pin")

    source.validate_batch(
        owner, retained_batch, retained_batch["batch_sha256"])
    source.validate_batch(
        owner, successor_batch, expected_batch_sha256)

    if successor_batch.get("schema") == "sia-controller-source-batch-v3":
        delivery = successor_batch["delivery_input"]
        # Pure wrapper replay establishes represented consistency only.
        # Join its declaration to the actual retained source and complete
        # completion receipt, including the consumed effects receipt pin.
        if delivery["parent_source_schema"] != retained_batch.get("schema") \
                or delivery["epoch_view"]["parent_committed"] != committed:
            _refuse("successor-wal-delivery-parent")

    prior_epoch = retained_batch.get("epoch")
    next_epoch = successor_batch.get("epoch")
    if type(prior_epoch) is not dict or type(next_epoch) is not dict:
        _refuse("successor-wal-predecessor")
    expected_predecessor = {
        "source_batch_sha256": retained_batch["batch_sha256"],
        "live_generation_sha256": committed["live_generation_sha256"],
    }
    if next_epoch.get("predecessor") != expected_predecessor \
            or next_epoch.get("epoch_id") != prior_epoch.get("epoch_id") \
            or next_epoch.get("started_at") != prior_epoch.get("started_at"):
        _refuse("successor-wal-predecessor")

    prior_history = prior_epoch.get("history")
    next_history = next_epoch.get("history")
    if type(prior_history) is not dict or type(next_history) is not dict \
            or type(prior_history.get("entries")) is not list \
            or type(next_history.get("entries")) is not list:
        _refuse("successor-wal-history")
    expected_entries = copy.deepcopy(prior_history["entries"])
    expected_entries.append(_history_entry(retained_batch))
    if next_history["entries"] != expected_entries:
        _refuse("successor-wal-history")

    # The production epoch has these immutable documents.  Minimal stopped
    # seam fixtures omit them, but a one-sided omission in any represented
    # input is always a relationship failure (batch validation catches an
    # omission in a real source batch before this comparison).
    for field in (
            "configuration", "source_catalog", "profile", "live_policy",
            "expected_configuration_sha256",
            "expected_source_catalog_sha256", "expected_profile_sha256",
            "expected_live_policy_sha256", "non_claims"):
        if (field in prior_epoch) != (field in next_epoch) \
                or field in prior_epoch \
                and prior_epoch[field] != next_epoch[field]:
            _refuse("successor-wal-history")
    return None


def _source_state(memo):
    """Classify only the durable source prefixes this runner can resume."""
    if type(memo) is not dict:
        _refuse("memo is not an object")

    completed = "controller_source_committed" in memo
    source_pending = "controller_source_pending" in memo
    live_pending = "controller_source_live_pending" in memo
    handoff_pending = "pulse_status_effects_pending" in memo
    effects_pending = "controller_source_effects_pending" in memo
    effects_committed = "controller_source_effects_committed" in memo

    if completed:
        if any(key in memo for key in _SOURCE_PENDING_KEYS):
            _refuse("completed state retains pending authority")
        return "completed"

    if effects_pending and effects_committed:
        _refuse("effects state is ambiguous")
    if not source_pending:
        if live_pending or handoff_pending \
                or effects_pending or effects_committed:
            _refuse("downstream state lacks source authority")
        return "absent"
    if effects_pending or effects_committed:
        if not live_pending or not handoff_pending:
            _refuse("effects state lacks its durable prefix")
        return "effects-pending" if effects_pending else "effects-committed"
    if handoff_pending:
        if not live_pending:
            _refuse("status handoff lacks live binding")
        return "handoff"
    if live_pending:
        return "binding"
    return "batch"


def _sequence(owner, memo, *, reservable=False):
    seq = memo.get("pulse_seq", 0)
    ceiling = owner["MAX_JSON_SAFE_INTEGER"]
    if type(seq) is not int or seq < 0 or seq > ceiling:
        _refuse("pulse sequence is invalid")
    if reservable and seq >= ceiling:
        _refuse("pulse sequence is exhausted")
    return seq


def _admit_status(owner, memo):
    return owner["_require_status_sequence_not_ahead"](
        _sequence(owner, memo))


def _initial_request(owner, memo, operation):
    """Reserve once, then lazily capture and retain the initial batch."""
    current = _sequence(owner, memo, reservable=True)
    admitted_status = owner["_require_status_sequence_not_ahead"](current)
    seq = current + 1
    memo["pulse_seq"] = seq
    owner["_write_memo"](memo)

    request = operation()
    if type(request) is not dict or set(request) != _REQUEST_KEYS:
        _refuse("initial capture request fields differ")
    batch = owner["_capture_controller_source_batch"](
        memo=memo, epoch=request["epoch"],
        expected_epoch_sha256=request["expected_epoch_sha256"],
        observed_at=request["observed_at"])
    if type(batch) is not dict \
            or type(batch.get("batch_sha256")) is not str:
        _refuse("captured batch is invalid")
    owner["_stage_controller_source_batch"](
        memo=memo, batch=batch,
        expected_batch_sha256=batch["batch_sha256"])
    if _source_state(memo) != "batch":
        _refuse("batch stage did not publish its durable prefix")
    return admitted_status, seq


def _pending_batch(owner, memo):
    view = owner["_read_pending_controller_source_batch"](memo=memo)
    if type(view) is not dict or view.get("status") != "pending" \
            or type(view.get("batch")) is not dict:
        _refuse("pending batch is unavailable")
    batch = view["batch"]
    if type(batch.get("batch_sha256")) is not str:
        _refuse("pending batch digest is invalid")
    return batch


def _stage_handoff(owner, memo, admitted_status):
    """Replay the pure bound input and retain the status-effects handoff."""
    import sialiveloop

    batch = _pending_batch(owner, memo)
    binding = owner["_controller_source_live_binding_marker"](memo)
    if type(binding) is not dict:
        _refuse("live binding is unavailable")
    candidate = owner["_prepare_controller_source_live_candidate"](
        memo=memo, admitted_status=admitted_status)
    if type(candidate) is not dict \
            or set(candidate) != {
                "prepare_inputs", "expected_prepare_inputs_sha256"}:
        _refuse("live candidate is invalid")
    transition = sialiveloop.prepare_pulse(**candidate["prepare_inputs"])
    if type(transition) is not dict \
            or type(transition.get("transition_sha256")) is not str:
        _refuse("live transition is invalid")
    owner["_stage_controller_source_status_effects"](
        memo=memo, admitted_status=admitted_status, batch=batch,
        expected_batch_sha256=batch["batch_sha256"],
        source_live_pending=binding, candidate=candidate,
        transition=transition,
        expected_transition_sha256=transition["transition_sha256"],
        started_at=owner["iso"]())
    if _source_state(memo) != "handoff":
        _refuse("status handoff did not publish its durable prefix")


def run(owner, *, operation):
    """Run or recover the terminal initial controller-source transaction."""
    if type(owner) is not dict:
        raise TypeError("owner must be a globals-style dictionary")
    if not callable(operation):
        raise TypeError("operation must be callable")

    memo = owner["load_memo"]()
    owner["_require_status_memo_fields"](memo)
    state = _source_state(memo)

    if state == "completed":
        admitted_status = _admit_status(owner, memo)
        owner["_acknowledge_controller_source_batch"](
            memo=memo, admitted_status=admitted_status)
        fresh_status = _admit_status(owner, memo)
        return owner["copy"].deepcopy(fresh_status)

    if state == "absent":
        if owner["_controller_source_present"](memo):
            recovered = owner["_recover_orphan_controller_source_batch"](
                memo=memo)
            if recovered is not True or _source_state(memo) != "batch":
                _refuse("orphan batch recovery did not establish authority")
            state = "batch"
            seq = _sequence(owner, memo)
            admitted_status = owner[
                "_require_status_sequence_not_ahead"](seq)
        else:
            admitted_status, seq = _initial_request(
                owner, memo, operation)
            state = "batch"
    else:
        seq = _sequence(owner, memo)
        admitted_status = owner["_require_status_sequence_not_ahead"](seq)

    if state == "batch":
        owner["_stage_controller_source_live_binding"](
            memo=memo, admitted_status=admitted_status, seq=seq)
        if _source_state(memo) != "binding":
            _refuse("live binding did not publish its durable prefix")
        state = "binding"

    if state == "binding":
        _stage_handoff(owner, memo, admitted_status)
        state = "handoff"

    if state in ("handoff", "effects-pending"):
        owner["_publish_controller_source_effects"](
            memo=memo, admitted_status=admitted_status)
        if _source_state(memo) != "effects-committed":
            _refuse("source effects did not publish their durable receipt")
        fresh_status = _admit_status(owner, memo)
    elif state == "effects-committed":
        # This admission occurred after the durable effects prefix and is the
        # status authority the ACK seam revalidates.
        fresh_status = admitted_status
    else:
        _refuse("unhandled source state")

    owner["_acknowledge_controller_source_batch"](
        memo=memo, admitted_status=fresh_status)
    if _source_state(memo) != "completed":
        _refuse("acknowledgment did not publish terminal authority")
    return owner["copy"].deepcopy(fresh_status)


def _completed_view(owner, memo, admitted_status):
    view = owner["_read_committed_controller_source_batch"](
        memo=memo, admitted_status=admitted_status)
    if type(view) is not dict or set(view) != {
            "status", "batch", "committed"} \
            or view.get("status") != "available" \
            or type(view.get("batch")) is not dict \
            or type(view.get("committed")) is not dict:
        _refuse("completed source authority is unavailable")
    if view["committed"] != memo.get("controller_source_committed"):
        _refuse("completed source authority differs from memo")
    return view


def run_v2(owner, *, operation, clock):
    """Run/recover one transaction, rolling a completed epoch forward.

    A fixed successor batch is the only rollover WAL.  Until it is durable,
    the predecessor completion and readiness marker remain authoritative.  A
    retry that finds that WAL validates and adopts it without invoking the
    clock, epoch builder, collectors, capture, or allocation again.
    """
    if type(owner) is not dict:
        raise TypeError("owner must be a globals-style dictionary")
    if not callable(operation) or not callable(clock):
        raise TypeError("operation and clock must be callable")

    memo = owner["load_memo"]()
    owner["_require_status_memo_fields"](memo)
    state = _source_state(memo)
    if state != "completed":
        return run(owner, operation=operation)

    seq = _sequence(owner, memo)
    admitted_status = owner["_require_status_sequence_not_ahead"](seq)
    # Keep the v1 completed admission as a distinct, tested boundary.  Its
    # completed reader is successor-aware only insofar as it may ignore the
    # different fixed-slot digest while revalidating the predecessor archive.
    owner["_acknowledge_controller_source_batch"](
        memo=memo, admitted_status=admitted_status)
    view = _completed_view(owner, memo, admitted_status)
    retained_batch = view["batch"]
    committed = view["committed"]

    recovered = owner[
        "_recover_orphan_controller_source_successor_batch"](
            memo=memo, retained_batch=retained_batch,
            committed=committed, seq=seq)
    if recovered is True:
        if _source_state(memo) != "batch":
            _refuse("successor orphan adoption did not establish authority")
        return run(owner, operation=operation)
    if recovered is not False:
        _refuse("successor orphan probe returned an invalid result")

    seq = _sequence(owner, memo, reservable=True) + 1
    memo["pulse_seq"] = seq
    owner["_write_memo"](memo)

    observed_at = clock()
    import siacontrollerepoch
    request = siacontrollerepoch.build_successor(
        owner, retained_batch=retained_batch, committed=committed,
        observed_at=observed_at)
    if type(request) is not dict or set(request) != _REQUEST_KEYS:
        _refuse("successor capture request fields differ")
    batch = owner["_capture_controller_source_successor_batch"](
        memo=memo, retained_batch=retained_batch, committed=committed,
        epoch=request["epoch"],
        expected_epoch_sha256=request["expected_epoch_sha256"],
        observed_at=request["observed_at"])
    if type(batch) is not dict \
            or type(batch.get("batch_sha256")) is not str:
        _refuse("captured successor batch is invalid")
    validate_successor_wal(
        owner, retained_batch=retained_batch, committed=committed,
        successor_batch=batch,
        expected_batch_sha256=batch["batch_sha256"])
    owner["_retain_controller_source_successor_batch"](
        memo=memo, retained_batch=retained_batch, committed=committed,
        batch=batch, expected_batch_sha256=batch["batch_sha256"], seq=seq)
    owner["_controller_source_rollover_boundary"](
        "successor-batch-durable")

    recovered = owner[
        "_recover_orphan_controller_source_successor_batch"](
            memo=memo, retained_batch=retained_batch,
            committed=committed, seq=seq)
    if recovered is not True or _source_state(memo) != "batch":
        _refuse("successor batch adoption did not establish authority")
    return run(owner, operation=operation)
