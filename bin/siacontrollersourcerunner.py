"""Closed dispatcher for the initial resident controller-source transaction.

The caller supplies the resident ``sialib`` global namespace as ``owner`` and
a lazy, zero-argument ``operation`` that constructs the initial source-capture
request.  Durable source-owned prefixes are always resumed without invoking
that operation or allocating another pulse sequence.  A completed v1 source
transaction is terminal: this module revalidates it, but does not invent a
successor epoch or history contract.
"""


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


def _refuse(reason):
    raise RuntimeError("controller source runner refused: " + reason)


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
