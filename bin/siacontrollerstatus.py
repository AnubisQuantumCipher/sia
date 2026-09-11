"""Pure status-effects projection for one bound controller-source pulse.

This component converts already validated source returns and their immutable
page-admission closure into the legacy-compatible pulse counters, one retained
history row, and the live transition's shallow workspace slots.  It has no
clock, path, source, graph, publication, cursor, model, or legacy-mind effects.

Unique event occurrence IDs count once.  Only newly appended admissions may
advance same-day organ counters; retained events remain visible as observed
events without being counted as newly stored.  The source/live marker and all
full hashes remain caller premises validated here, not cognitive proof.
"""

import copy


NON_CLAIMS = (
    "Status effects are a deterministic projection of an admitted source batch and page-admission plan; they do not establish source truth, publication, acknowledgment or delivery.",
    "Unique event counts and append-only organ counters are compatibility telemetry, not a biological measure or a held-out cognitive win.",
    "Workspace output is the exact shallow slot projection of the supplied computed-unverified live transition; this component does not select, broadcast or execute it.",
    "The supplied start time names the write-ahead history row; source observation and later status-publication clocks remain distinct.",
)


class ControllerStatusRefusal(ValueError):
    def __init__(self, reason, *, upstream=None):
        self.reason = reason
        self.non_claims = list(NON_CLAIMS)
        self.upstream_reason = getattr(upstream, "reason", None)
        self.upstream_non_claims = list(
            getattr(upstream, "non_claims", ()))[:64]
        super().__init__("controller source status refused: " + reason)


def _refuse(reason, *, upstream=None):
    raise ControllerStatusRefusal(reason, upstream=upstream)


def _unchanged(source, live, originals, values):
    if source.native_bytes(values["owner"], values["batch"]) \
            != originals["batch"]:
        _refuse("batch-changed")
    for name in ("admitted_status", "source_live_pending",
                 "candidate", "transition"):
        if live._canonical(values[name]) != originals[name]:
            _refuse(name.replace("_", "-") + "-changed")


def _receipt(owner, source, batch, raw):
    predecessor = batch["epoch"]["predecessor"]
    return {
        "schema": "sia-controller-source-pending-v1",
        "epoch_id": batch["epoch"]["epoch_id"],
        "batch_id": batch["batch_id"],
        "epoch_sha256": batch["epoch_sha256"],
        "batch_sha256": batch["batch_sha256"],
        "batch_wire_sha256": owner["hashlib"].sha256(raw).hexdigest(),
        "batch_bytes": len(raw),
        "parent_batch_sha256": (
            None if predecessor is None
            else predecessor["source_batch_sha256"]),
    }


def _marker(owner, source, live, batch, raw, admitted_status,
            source_live_pending, candidate, transition,
            expected_transition_sha256):
    import siacontrollerliveinput

    validation_memo = {
        "controller_source_pending":
            copy.deepcopy(source_live_pending.get(
                "source_pending_receipt"))
            if type(source_live_pending) is dict else None,
        "controller_source_live_pending": source_live_pending,
    }
    try:
        marker = owner["_controller_source_live_binding_marker"](
            validation_memo)
    except (TypeError, ValueError, KeyError, OverflowError,
            RecursionError) as exc:
        _refuse("live-binding-invalid", upstream=exc)
    receipt = _receipt(owner, source, batch, raw)
    if marker is None or marker["source_pending_receipt"] != receipt \
            or marker["source_batch_sha256"] != batch["batch_sha256"] \
            or marker["source_batch_wire_sha256"] \
            != receipt["batch_wire_sha256"] \
            or marker["observed_at"] != batch["observed_at"] \
            or marker["admitted_status_sha256"] \
            != live._sha(admitted_status) \
            or marker["seq"] < admitted_status["pulse_seq"]:
        _refuse("live-binding-external-pins")

    if type(candidate) is not dict or set(candidate) != {
            "prepare_inputs", "expected_prepare_inputs_sha256"}:
        _refuse("candidate-shape")
    inputs = candidate["prepare_inputs"]
    if candidate["expected_prepare_inputs_sha256"] != live._sha(inputs) \
            or marker["prepare_inputs_sha256"] \
            != candidate["expected_prepare_inputs_sha256"]:
        _refuse("candidate-pin")
    try:
        replayed = live.prepare_pulse(**inputs)
    except (TypeError, ValueError, KeyError, OverflowError,
            RecursionError) as exc:
        _refuse("candidate-replay", upstream=exc)
    if live._canonical(replayed) != live._canonical(transition) \
            or type(expected_transition_sha256) is not str \
            or transition.get("transition_sha256") \
            != expected_transition_sha256 \
            or expected_transition_sha256 != live._sha({
                key: value for key, value in transition.items()
                if key != "transition_sha256"}) \
            or transition.get("state_sha256") \
            != live._sha(transition.get("state")) \
            or marker["transition_sha256"] != expected_transition_sha256 \
            or marker["state_sha256"] != transition["state_sha256"]:
        _refuse("transition-pin")

    closure = batch["event_closure"]
    closure_sha256 = (
        None if closure is None else closure["closure_sha256"])
    if marker["event_closure_sha256"] != closure_sha256:
        _refuse("event-closure-pin")
    previous = inputs.get("previous_state")
    previous_sha256 = inputs.get("expected_previous_state_sha256")
    if previous_sha256 != marker["parent_state_sha256"] \
            or (previous is None) != (previous_sha256 is None) \
            or previous is not None and live._sha(previous) \
            != previous_sha256:
        _refuse("parent-state-pin")
    if (marker["parent_generation_sha256"] is None) \
            != (previous_sha256 is None):
        _refuse("parent-generation-pin")
    if batch["schema"] == "sia-controller-source-batch-v3":
        # This pure replay treats the separately supplied marker as a
        # premise. Current storage authority belongs to the durable handoff
        # caller, which independently reads and joins the full generation.
        expected_inputs = siacontrollerliveinput.prepare_inputs_v4(
            owner, batch=batch,
            previous_generation=batch["delivery_input"]["epoch_view"]["parent_generation"],
            expected_previous_generation_sha256=marker["parent_generation_sha256"])
    else:
        expected_inputs = siacontrollerliveinput.prepare_inputs(
            batch=batch, previous_state=previous,
            expected_previous_state_sha256=previous_sha256)
    if live._canonical(inputs) != live._canonical(expected_inputs):
        _refuse("retained-producer-pin")
    return marker


def _events(batch):
    records = {}
    for run in batch["source_returns"]["runs"]:
        for record in run["events"]:
            prior = records.get(record["event_id"])
            if prior is None:
                records[record["event_id"]] = record
            elif prior["semantic_id"] != record["semantic_id"]:
                _refuse("repeated-event-semantics")

    admissions = {}
    closure = batch["event_closure"]
    if closure is not None:
        for grouped in closure["batches"]:
            for member in grouped["members"]:
                for admission in member["admissions"]:
                    prior = admissions.get(admission["event_id"])
                    if prior is not None and prior != admission:
                        _refuse("repeated-event-admission")
                    admissions[admission["event_id"]] = admission
    if set(records) != set(admissions):
        _refuse("event-admission-set")
    return records, admissions


def prepare(owner, *, admitted_status, batch, expected_batch_sha256,
            source_live_pending, candidate, transition,
            expected_transition_sha256, started_at):
    """Return detached pulse effects/history/workspace or refuse wholly."""
    import siasourcebatch as source
    import sialiveloop as live

    values = {
        "owner": owner, "admitted_status": admitted_status, "batch": batch,
        "source_live_pending": source_live_pending, "candidate": candidate,
        "transition": transition,
    }
    originals = {
        "batch": source.native_bytes(owner, batch),
        "admitted_status": live._canonical(admitted_status),
        "source_live_pending": live._canonical(source_live_pending),
        "candidate": live._canonical(candidate),
        "transition": live._canonical(transition),
    }
    if type(expected_batch_sha256) is not str \
            or type(expected_transition_sha256) is not str \
            or type(started_at) is not str:
        _refuse("input-shape")
    try:
        admitted_values = {
            "admitted_status": copy.deepcopy(admitted_status),
            "batch": copy.deepcopy(batch),
            "source_live_pending": copy.deepcopy(source_live_pending),
            "candidate": copy.deepcopy(candidate),
            "transition": copy.deepcopy(transition),
        }
        if source.native_bytes(owner, admitted_values["batch"]) \
                != originals["batch"] \
                or any(live._canonical(admitted_values[name]) \
                       != originals[name] for name in (
                           "admitted_status", "source_live_pending",
                           "candidate", "transition")):
            _refuse("input-copy-changed")
        admitted_status = admitted_values["admitted_status"]
        batch = admitted_values["batch"]
        source_live_pending = admitted_values["source_live_pending"]
        candidate = admitted_values["candidate"]
        transition = admitted_values["transition"]
        source.validate_batch(owner, batch, expected_batch_sha256)
        if owner["_recoverable_status_integrity"](admitted_status) is None \
                or admitted_status.get("version") != owner["VERSION"]:
            _refuse("admitted-status")
        if owner["_canonical_utc_timestamp"](started_at) != started_at \
                or admitted_status["ts"] > started_at:
            _refuse("started-at")
        raw = source.native_bytes(owner, batch)
        _marker(
            owner, source, live, batch, raw, admitted_status,
            source_live_pending, candidate, transition,
            expected_transition_sha256)
        records, admissions = _events(batch)

        day = started_at[:10]
        organs = copy.deepcopy(admitted_status["organs"])
        if admitted_status["day"] != day:
            for state in organs.values():
                state["today"] = 0
        for event_id, admission in admissions.items():
            if admission["disposition"] != "appended":
                continue
            record = records[event_id]
            state = organs.setdefault(
                record["organ"], {"today": 0, "last_ts": ""})
            if record["ts"][:10] == day:
                state["today"] += 1
            state["last_ts"] = max(state["last_ts"], record["ts"])
        effects = owner["_canonical_pulse_effects"](
            day, len(records), organs)
        history = copy.deepcopy(admitted_status["history"])
        history.append([started_at, len(records)])
        history = history[-owner["MAX_PULSE_HISTORY_ROWS"]:]
        if not owner["_status_history_shape"](history):
            _refuse("history-projection")
        workspace = copy.deepcopy(
            transition["state"]["workspace"]["slots"])
        if not owner["_status_workspace_shape"](workspace):
            _refuse("workspace-projection")
        result = {
            "effects": effects, "history": history,
            "workspace": workspace,
        }
        live._canonical(result)
        _unchanged(source, live, originals, values)
        detached = copy.deepcopy(result)
        if live._canonical(detached) != live._canonical(result):
            _refuse("result-detachment")
        _unchanged(source, live, originals, values)
        return detached
    except ControllerStatusRefusal:
        raise
    except (TypeError, ValueError, KeyError, OverflowError,
            RecursionError) as exc:
        _refuse("input-or-component-refusal", upstream=exc)
