"""Bind one complete controller-source intake to committed live history.

The live loop deliberately accepts only an append-only cumulative intake.
This pure component preserves an initial descriptor-validated projection
exactly; with a committed parent it requires the supplied complete projection
to contain the parent's pages and observations as byte-exact prefixes.  It
does not guess that a truncated or empty history is an incremental delta.
The legacy entrypoint copies delivery history exactly from the committed
parent. The additive v3 entrypoint uses the complete source-bound delivery
envelope and requires the caller's independently admitted full generation.
The v4 preparation entrypoint selects the separately versioned fixed-slot
admission envelope without changing source-v3 semantics or single-artifact caps.
The checkpoint entrypoint explicitly validates compact capture/delta bindings
before extracting its cumulative intake; it does not authenticate durable roots.
None of these entrypoints acquires output receipts or executes the planned pulse.
"""

import copy

import sialiveloop as live


NON_CLAIMS = (
    "This is an append-only representation binding; it does not establish source truth, delivery, publication, acknowledgment or a cognitive win.",
    "Committed history must already be the supplied projection's exact prefix; this component does not infer a missing predecessor or manufacture a delta join.",
)

_INTAKE_KEYS = {
    "schema", "epoch_id", "started_at", "complete", "pages",
    "current_versions", "symbols", "contexts", "observations",
}
_FIXED_KEYS = {
    "schema", "epoch_id", "started_at", "complete", "symbols", "contexts",
}


class ControllerLiveInputRefusal(ValueError):
    def __init__(self, reason):
        self.reason = reason
        self.non_claims = list(NON_CLAIMS)
        super().__init__("controller live input refused: " + reason)


def _refuse(reason):
    raise ControllerLiveInputRefusal(reason)


def _canonical(value):
    try:
        return live._canonical(value)
    except (TypeError, ValueError, KeyError, OverflowError,
            RecursionError) as exc:
        raise ControllerLiveInputRefusal(
            "input-representation") from exc


def _prefix(previous, current):
    return len(current) >= len(previous) \
        and _canonical(current[:len(previous)]) == _canonical(previous)


def compose(*, frame, previous_state):
    """Return the detached complete intake or refuse a non-prefix parent."""
    original_frame = _canonical(frame)
    original_previous = _canonical(previous_state)
    if type(frame) is not dict or set(frame) != _INTAKE_KEYS:
        _refuse("frame-shape")
    if previous_state is None:
        result = copy.deepcopy(frame)
    else:
        if type(previous_state) is not dict \
                or type(previous_state.get("intake")) is not dict:
            _refuse("parent-shape")
        previous = previous_state["intake"]
        if set(previous) != _INTAKE_KEYS \
                or any(_canonical(frame[key]) != _canonical(previous[key])
                       for key in _FIXED_KEYS):
            _refuse("epoch-contract-changed")
        for name in ("pages", "current_versions", "observations"):
            if type(frame[name]) is not list or type(previous[name]) is not list:
                _refuse("history-shape")

        if not _prefix(previous["pages"], frame["pages"]) \
                or not _prefix(
                    previous["observations"], frame["observations"]):
            _refuse("history-not-cumulative")
        result = copy.deepcopy(frame)

    encoded = _canonical(result)
    detached = copy.deepcopy(result)
    if _canonical(frame) != original_frame \
            or _canonical(previous_state) != original_previous \
            or _canonical(detached) != encoded:
        _refuse("input-or-result-changed")
    return detached


def _idle_inputs(batch, basis, *, allow_v3=False, allow_checkpoint=False):
    """Share retained idle semantics without relabeling a source schema."""
    idle, gist_inputs = False, None
    if batch.get("schema") == "sia-controller-source-batch-v1":
        if "idle_input" in batch:
            _refuse("legacy-idle-input")
    elif batch.get("schema") == "sia-controller-source-batch-v2" \
            or allow_v3 and batch.get("schema") == "sia-controller-source-batch-v3" \
            or allow_checkpoint and batch.get("schema") == "sia-controller-source-checkpoint-capture-v3":
        returns = batch.get("source_returns")
        if type(returns) is not dict or type(returns.get("runs")) is not list \
                or not returns["runs"] or "idle_input" not in batch \
                or any(type(run) is not dict
                       or set(run) != {"source_id", "events"}
                       or type(run["events"]) is not list
                       for run in returns["runs"]):
            _refuse("source-idle-roster")
        idle = all(not run["events"] for run in returns["runs"])
        gist_inputs = batch["idle_input"]
        try:
            live._gist_inputs(
                gist_inputs, basis["intake"], basis["policy"], idle,
                expected_intake_sha256=basis["intake_sha256"],
                expected_policy_sha256=basis["policy_sha256"],
                observed_at=basis["observed_at"])
        except (ValueError, RuntimeError, TypeError, KeyError) as exc:
            raise ControllerLiveInputRefusal("source-idle-binding") from exc
    else:
        _refuse("source-batch-schema")
    return idle, gist_inputs


def prepare_inputs(*, batch, previous_state,
                   expected_previous_state_sha256):
    """Return the sole live-loop request authorized by a legacy source frame."""
    if type(batch) is not dict \
            or type(batch.get("intake_projection")) is not dict \
            or type(batch.get("epoch")) is not dict:
        _refuse("batch-shape")
    if "delivery_input" in batch:
        _refuse("legacy-delivery-input")
    basis = {
        "schema": batch.get("schema"),
        "intake": batch["intake_projection"].get("intake"),
        "intake_sha256": batch["intake_projection"].get("intake_sha256"),
        "policy": batch["epoch"].get("live_policy"),
        "policy_sha256": batch["epoch"].get(
            "expected_live_policy_sha256"),
        "observed_at": batch.get("observed_at"),
        "source_returns": batch.get("source_returns"),
        "idle_input": batch.get("idle_input"),
    }
    original_basis = _canonical(basis)
    original_previous = _canonical(previous_state)
    idle, gist_inputs = _idle_inputs(batch, basis)
    if previous_state is None:
        if expected_previous_state_sha256 is not None:
            _refuse("initial-parent-pin")
        deliveries = {
            "schema": "sia-live-deliveries-v1",
            "epoch_id": batch["intake_projection"]["intake"]["epoch_id"],
            "complete": True,
            "records": [],
        }
    else:
        if type(expected_previous_state_sha256) is not str \
                or live._sha(previous_state) \
                != expected_previous_state_sha256 \
                or type(previous_state.get("deliveries")) is not dict:
            _refuse("parent-pin")
        deliveries = copy.deepcopy(previous_state["deliveries"])
    intake = compose(
        frame=batch["intake_projection"]["intake"],
        previous_state=previous_state)
    result = {
        "intake": intake,
        "expected_intake_sha256": live._sha(intake),
        "deliveries": deliveries,
        "expected_deliveries_sha256": live._sha(deliveries),
        "previous_state": copy.deepcopy(previous_state),
        "expected_previous_state_sha256": expected_previous_state_sha256,
        "policy": copy.deepcopy(batch["epoch"]["live_policy"]),
        "expected_policy_sha256":
            batch["epoch"]["expected_live_policy_sha256"],
        "observed_at": batch["observed_at"],
        "idle": idle,
        "gist_inputs": copy.deepcopy(gist_inputs),
    }
    encoded = _canonical(result)
    detached = copy.deepcopy(result)
    current_basis = {
        "schema": batch.get("schema"),
        "intake": batch["intake_projection"].get("intake"),
        "intake_sha256": batch["intake_projection"].get("intake_sha256"),
        "policy": batch["epoch"].get("live_policy"),
        "policy_sha256": batch["epoch"].get(
            "expected_live_policy_sha256"),
        "observed_at": batch.get("observed_at"),
        "source_returns": batch.get("source_returns"),
        "idle_input": batch.get("idle_input"),
    }
    if _canonical(current_basis) != original_basis \
            or _canonical(previous_state) != original_previous \
            or _canonical(detached) != encoded:
        _refuse("prepare-input-or-result-changed")
    if "delivery_input" in batch:
        _refuse("legacy-delivery-input")
    return detached


def prepare_inputs_v3(owner, *, batch, previous_generation,
                      expected_previous_generation_sha256):
    """Bind retained v3 input to the caller's complete admitted generation.

    The generation and independent pin are caller premises. Resident
    preparation must obtain the generation through its actual authority
    reader. Pure retained status replay instead uses the separately supplied
    live marker's pin; its durable caller must independently join current
    storage before effects. This component compares the full represented
    generation to the wrapper's parent; a matching state is insufficient.
    It does not acquire storage, execute a pulse, consume a journal or observe
    output, and represented replay never establishes current authority.
    """
    import siacontrollerdeliverywrapper as wrapper
    return _prepare_inputs_v3(
        owner, batch=batch, previous_generation=previous_generation,
        expected_previous_generation_sha256=expected_previous_generation_sha256,
        admission_type=wrapper._Admission)


def prepare_inputs_v4(owner, *, batch, previous_generation,
                      expected_previous_generation_sha256):
    """Explicit compound admission with unchanged v3 source/parent semantics.

    This entrypoint never retries a refused v3 preparation. The fixed-slot
    contract preserves each artifact ceiling; all source, full-parent, idle,
    intake and prepared-output validation below remains shared with v3.
    No represented result establishes current publication authority.
    """
    import siacontrollerdeliverywrapper as wrapper
    return _prepare_inputs_v3(
        owner, batch=batch, previous_generation=previous_generation,
        expected_previous_generation_sha256=expected_previous_generation_sha256,
        admission_type=wrapper.PreparationAdmissionV1)


def prepare_inputs_checkpoint(owner, *, batch, previous_generation,
                              expected_previous_generation_sha256):
    """Prepare the real pulse request from a validated compact capture.

    The full parent generation and its independent pin remain caller premises.
    This pure operation replays source/delta/delivery bindings, not durable
    root authority, and neither publishes nor acknowledges the capture.
    Each original artifact retains the explicit fixed-slot admission ceiling.
    """
    import siacontrollerdeliverywrapper as wrapper
    return _prepare_inputs_v3(
        owner, batch=batch, previous_generation=previous_generation,
        expected_previous_generation_sha256=expected_previous_generation_sha256,
        admission_type=wrapper.CheckpointPreparationAdmissionV1, checkpoint=True)


def _prepare_inputs_v3(owner, *, batch, previous_generation,
                       expected_previous_generation_sha256, admission_type, checkpoint=False):
    import siasourcebatch as source

    try:
        request = {
            "batch": batch, "previous_generation": previous_generation,
            "expected_previous_generation_sha256": expected_previous_generation_sha256,
        }
        # The explicitly selected native contract bounds all original inputs
        # and pins the owner basis before copying: aggregate in v3, closed
        # per-artifact slots in v4. Native filesystem identities never enter
        # the live serializer.
        admission = admission_type(owner, request)
        retained = admission.admitted["batch"]
        generation = admission.admitted["previous_generation"]
        pin = admission.admitted["expected_previous_generation_sha256"]
        schema = "sia-controller-source-checkpoint-capture-v3" if checkpoint else "sia-controller-source-batch-v3"
        if type(retained) is not dict \
                or retained.get("schema") != schema \
                or type(generation) is not dict or not live._digest(pin):
            _refuse("v3-source-and-full-parent-required")
        if checkpoint:
            import siasourcecheckpoint
            siasourcecheckpoint.validate_capture(owner, retained, retained.get("batch_sha256"))
        else:
            source.validate_batch(owner, retained, retained.get("batch_sha256"))
        admission.current()
        view = retained["delivery_input"]["epoch_view"]
        if generation.get("generation_sha256") != pin \
                or live._own(generation, "generation_sha256") != pin \
                or view["expected_parent_generation_sha256"] != pin \
                or source.native_bytes(owner, generation) \
                   != source.native_bytes(owner, view["parent_generation"]):
            _refuse("v3-full-parent-generation-differs")
        previous_state = generation["transition"]["state"]
        binding = retained["delivery_input"]["binding"]
        projection, epoch = retained["intake_projection"], retained["epoch"]
        frame = projection["checkpoint"]["intake"] if checkpoint else projection["intake"]
        frame_pin = live._sha(frame) if checkpoint else projection["intake_sha256"]
        basis = {
            "intake": frame,
            "intake_sha256": frame_pin,
            "policy": epoch["live_policy"],
            "policy_sha256": epoch["expected_live_policy_sha256"],
            "observed_at": retained["observed_at"],
        }
        idle, gist_inputs = _idle_inputs(retained, basis, allow_v3=not checkpoint, allow_checkpoint=checkpoint)
        intake = compose(frame=frame, previous_state=previous_state)
        result = {
            "intake": intake, "expected_intake_sha256": live._sha(intake),
            "deliveries": copy.deepcopy(binding["deliveries"]),
            "expected_deliveries_sha256": binding["deliveries_sha256"],
            "previous_state": copy.deepcopy(previous_state),
            "expected_previous_state_sha256": generation["state_sha256"],
            "policy": copy.deepcopy(epoch["live_policy"]),
            "expected_policy_sha256": epoch["expected_live_policy_sha256"],
            "observed_at": retained["observed_at"], "idle": idle,
            "gist_inputs": copy.deepcopy(gist_inputs),
        }
        live._budget(result["policy"], result)
        encoded = _canonical(result)
        admission.current()
        detached = copy.deepcopy(result)
        if _canonical(result) != encoded or _canonical(detached) != encoded:
            _refuse("v3-prepared-result-changed")
        admission.current()
        return detached
    except ControllerLiveInputRefusal:
        raise
    except (ValueError, RuntimeError, TypeError, KeyError, IndexError,
            AttributeError, OverflowError, RecursionError, OSError) as exc:
        raise ControllerLiveInputRefusal("v3-live-input-refused") from exc
