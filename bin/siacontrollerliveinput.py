"""Bind one complete controller-source intake to committed live history.

The live loop deliberately accepts only an append-only cumulative intake.
This pure component preserves an initial descriptor-validated projection
exactly; with a committed parent it requires the supplied complete projection
to contain the parent's pages and observations as byte-exact prefixes.  It
does not guess that a truncated or empty history is an incremental delta.
Delivery history is likewise copied exactly from the committed parent because
this source-only seam has no authority to add, remove or rewrite deliveries.
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


def prepare_inputs(*, batch, previous_state,
                   expected_previous_state_sha256):
    """Return the sole live-loop request authorized by a source frame."""
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
    idle, gist_inputs = False, None
    if batch.get("schema") == "sia-controller-source-batch-v1":
        if "idle_input" in batch:
            _refuse("legacy-idle-input")
    elif batch.get("schema") == "sia-controller-source-batch-v2":
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
