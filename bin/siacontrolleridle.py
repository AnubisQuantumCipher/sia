"""Capture and bind native replay inputs for one empty source successor.

Acquisition goes through the native-history front door while the source
controller owns its corpus lease. The returned wrapper retains the complete
capture, every original controller episode, and the fixed replay policy.
Validation consumes those retained bytes only; it never rereads a source or
turns a custom collector into a supported native ledger.
"""

import copy

import siagist as gist
import sialivegist as binding
import sialiveloop as live


IDLE_INPUT_KEYS = frozenset({
    "episode_bindings", "expected_episode_bindings_sha256",
    "gist_inputs", "expected_gist_inputs_sha256",
})


class ControllerIdleRefusal(ValueError):
    def __init__(self, reason):
        self.reason = reason
        self.non_claims = list(binding.NON_CLAIMS)
        super().__init__("controller idle input refused: " + reason)


def _refuse(reason):
    raise ControllerIdleRefusal(reason)


def _policy():
    """Checked-in engineering selection; no query or answer enters it."""
    return {
        "schema": "sia-replay-gist-policy-v1",
        "grammar": "native-attest-intent-outcome-v1",
        "learning": {
            "algorithm": "witnessed-completion-delta-v1", "enabled": True,
            "rate": {"numerator": 1, "denominator": 2},
            "initial": "zero-v1",
        },
        "readout": {
            "cue_roster": "complete-derived-native-cues-v1",
            "threshold": {"numerator": 1, "denominator": 2},
            "slots_per_cue": 1, "tie_break": "first-source-occurrence-v1",
            "static_control": "first-source-occurrence-v1",
        },
        "fidelity": dict(gist._FIDELITY),
        "limits": dict(gist._LIMITS),
    }


def _names(epoch):
    return [binding._NATIVE_SOURCES[name]
            for name in epoch["configuration"]["native_collectors"]
            if name in binding._NATIVE_SOURCES]


def _episode_records(epoch, projection):
    """Keep each association's first complete normalized Event record."""
    records = {}
    for entry in epoch["history"]["entries"]:
        for run in entry["source_returns"]["runs"]:
            for record in run["events"]:
                identity = live._sha({
                    "schema": "sia-controller-event-association-v1",
                    "epoch_id": epoch["epoch_id"],
                    "source_id": run["source_id"],
                    "event_id": record["event_id"],
                })
                records.setdefault(identity, (run["source_id"], record))
    result = []
    for observation in projection["intake"]["observations"]:
        matched = records.get(observation["id"])
        if matched is None or matched[0] != observation["symbol"]:
            _refuse("idle-observation-record-binding")
        result.append({
            "observation_id": observation["id"],
            "source_id": matched[0],
            "event_record": matched[1],
            "native_occurrence": None,
        })
    if len(result) != len(records):
        _refuse("idle-complete-observation-roster")
    return result


def _native_records(owner, captured):
    indexed = {}
    for event in captured["events"]:
        if event["projection"] is None:
            continue
        projected = owner["signed_ledger_event_projection"](
            event["chain"], event["row"])
        if projected is None:
            _refuse("idle-native-projection-binding")
        record = owner["_event_replay_record"](projected)
        key = (event["chain"], live._canonical(record))
        if key in indexed:
            _refuse("idle-ambiguous-native-record")
        indexed[key] = event
    return indexed


def _wrapper(owner, *, epoch, projection, observed_at, captured, episode_records=None):
    """Build the only episode/replay wrapper authorized by retained inputs."""
    import siasourcebatch as source
    source._json_size(owner, {
        "epoch": epoch, "projection": projection, "capture": captured,
        **({"episode_records": episode_records} if episode_records is not None else {}),
    }, owner["MAX_STATE_JSON_BYTES"], ascii_only=True)
    names = _names(epoch)
    if not names:
        _refuse("idle-native-source-roster-empty")
    if [row["chain"] for row in captured["chains"]] != sorted(names):
        _refuse("idle-native-source-roster-binding")
    episodes = (_episode_records(epoch, projection) if episode_records is None else copy.deepcopy(episode_records))
    natives = _native_records(owner, captured)
    steps = []
    for episode in episodes:
        chain = binding._NATIVE_SOURCES.get(episode["source_id"])
        if chain is None:
            continue
        event = natives.get((
            chain, live._canonical(episode["event_record"])))
        if event is None:
            _refuse("idle-required-native-occurrence-missing")
        episode["native_occurrence"] = gist._reference(event)
        _cue, reason = gist._native_relation(event)
        if reason is None:
            steps.append({
                "id": episode["observation_id"],
                "occurrence": episode["native_occurrence"],
            })
    replay = {"schema": "sia-gist-replay-v1", "steps": steps}
    policy = _policy()
    gist_inputs = {
        "capture": captured,
        "expected_capture_sha256": captured["capture_sha256"],
        "replay": replay, "expected_replay_sha256": live._sha(replay),
        "policy": policy, "expected_policy_sha256": live._sha(policy),
    }
    episodes_document = {
        "schema": "sia-live-episode-bindings-v1",
        "epoch_id": epoch["epoch_id"],
        "intake_sha256": projection["intake_sha256"],
        "observed_at": observed_at,
        "live_policy": epoch["live_policy"],
        "live_policy_sha256": epoch["expected_live_policy_sha256"],
        "capture_sha256": captured["capture_sha256"],
        "rules": dict(binding._RULES),
        "episodes": episodes,
        "non_claims": list(binding.BINDING_NON_CLAIMS),
    }
    result = {
        "episode_bindings": episodes_document,
        "expected_episode_bindings_sha256": live._sha(episodes_document),
        "gist_inputs": gist_inputs,
        "expected_gist_inputs_sha256": live._sha(gist_inputs),
    }
    live._size(result, owner["MAX_STATE_JSON_BYTES"])
    live._gist_inputs(
        result, projection["intake"], epoch["live_policy"], True,
        expected_intake_sha256=projection["intake_sha256"],
        expected_policy_sha256=epoch["expected_live_policy_sha256"],
        observed_at=observed_at)
    return result


def _without_native(owner, *, epoch, projection, observed_at, episode_records=None):
    import sialiveidle
    if _names(epoch):
        _refuse("idle-supported-native-source-selected")
    document = {
        "schema": "sia-live-idle-without-native-v1",
        "availability": "no-selected-supported-native-source",
        "epoch_id": epoch["epoch_id"],
        "intake_sha256": projection["intake_sha256"],
        "observed_at": observed_at,
        "live_policy_sha256": epoch["expected_live_policy_sha256"],
        "source_ids": projection["intake"]["symbols"],
        "episodes": (_episode_records(epoch, projection) if episode_records is None else copy.deepcopy(episode_records)),
        "non_claims": list(sialiveidle.NON_CLAIMS),
    }
    result = {
        "idle_without_native": document,
        "expected_idle_without_native_sha256": live._sha(document),
    }
    live._size(result, owner["MAX_STATE_JSON_BYTES"])
    sialiveidle.reservation(
        intake=projection["intake"],
        expected_intake_sha256=projection["intake_sha256"],
        policy=epoch["live_policy"],
        expected_policy_sha256=epoch["expected_live_policy_sha256"],
        observed_at=observed_at, idle_input=result)
    return result


def capture(owner, *, epoch, projection, observed_at):
    """Acquire native history once and return detached pinned idle inputs."""
    return _capture(owner, epoch=epoch, projection=projection, observed_at=observed_at)


def _capture(owner, *, epoch, projection, observed_at, episode_records=None):
    request = {"epoch": epoch, "projection": projection,
               "observed_at": observed_at,
               **({"episode_records": episode_records} if episode_records is not None else {})}
    import siasourcebatch as source
    original = source.native_bytes(owner, request)
    names = _names(epoch)
    if names:
        registry = owner["_chain_cmds"]()
        if type(registry) is not dict or any(name not in registry for name in names):
            _refuse("idle-required-native-source-unregistered")
        import siabench
        captured = siabench.capture_native_history_v2(
            corpus=owner["CORPUS"], chain_registry=registry, chain_names=names)
        result = _wrapper(
            owner, epoch=epoch, projection=projection,
            observed_at=observed_at, captured=captured, episode_records=episode_records)
    else:
        result = _without_native(
            owner, epoch=epoch, projection=projection, observed_at=observed_at, episode_records=episode_records)
    raw = live._canonical(result, owner["MAX_STATE_JSON_BYTES"])
    detached = copy.deepcopy(result)
    if source.native_bytes(owner, request) != original \
            or live._canonical(result, owner["MAX_STATE_JSON_BYTES"]) != raw \
            or live._canonical(detached, owner["MAX_STATE_JSON_BYTES"]) != raw:
        _refuse("idle-capture-input-or-result-changed")
    return detached


def validate(owner, *, epoch, projection, observed_at, idle_input):
    """Reconstruct from pinned capture bytes, with no source acquisition."""
    return _validate(owner, epoch=epoch, projection=projection, observed_at=observed_at, idle_input=idle_input)


def _validate(owner, *, epoch, projection, observed_at, idle_input, episode_records=None):
    import siasourcebatch as source
    source._json_size(owner, {
        "epoch": epoch, "projection": projection,
        "observed_at": observed_at, "idle_input": idle_input,
        **({"episode_records": episode_records} if episode_records is not None else {}),
    }, owner["MAX_STATE_JSON_BYTES"], ascii_only=True)
    original = live._canonical(idle_input, owner["MAX_STATE_JSON_BYTES"])
    if _names(epoch):
        if type(idle_input) is not dict or set(idle_input) != IDLE_INPUT_KEYS \
                or type(idle_input["gist_inputs"]) is not dict \
                or "capture" not in idle_input["gist_inputs"]:
            _refuse("idle-input-shape")
        expected = _wrapper(
            owner, epoch=epoch, projection=projection, observed_at=observed_at,
            captured=idle_input["gist_inputs"]["capture"], episode_records=episode_records)
    else:
        expected = _without_native(
            owner, epoch=epoch, projection=projection, observed_at=observed_at, episode_records=episode_records)
    if live._canonical(expected, owner["MAX_STATE_JSON_BYTES"]) != original \
            or live._canonical(idle_input, owner["MAX_STATE_JSON_BYTES"]) != original:
        _refuse("idle-input-binding")


def _checkpoint_basis(owner, epoch, projection, observed_at):
    """Admit represented v3 records, not root ancestry or source authority."""
    import siaeventcheckpoint as checkpoints
    import siasourcecheckpoint as source_checkpoint
    source = source_checkpoint.source
    source._keys(epoch, source_checkpoint._KEYS, "checkpoint-epoch-shape")
    source._keys(projection, {"schema", "status", "checkpoint", "checkpoint_sha256",
                             "parent_checkpoint_sha256", "delta_sha256", "associations", "non_claims"},
                 "checkpoint-idle-projection-shape")
    checkpoint = checkpoints.admit(owner, checkpoint=projection["checkpoint"],
                                    expected_checkpoint_sha256=projection["checkpoint_sha256"])
    if checkpoint["schema"] != "sia-event-replay-checkpoint-v3" \
            or epoch["schema"] != "sia-controller-source-checkpoint-epoch-v1" \
            or epoch["non_claims"] != list(source_checkpoint.NON_CLAIMS) \
            or projection["schema"] != "sia-event-delta-projection-v1" \
            or projection["status"] != "prepared-not-authorized" \
            or projection["non_claims"] != list(checkpoints.PROJECTION_NON_CLAIMS) \
            or type(observed_at) is not int or type(epoch["observed_at"]) is not int \
            or epoch["observed_at"] != observed_at or checkpoint["observed_at"] != observed_at \
            or epoch["epoch_id"] != checkpoint["intake"]["epoch_id"] \
            or type(epoch["started_at"]) is not int or epoch["started_at"] != checkpoint["intake"]["started_at"] \
            or epoch["checkpoint_sha256"] != checkpoint["parent_checkpoint_sha256"] \
            or projection["parent_checkpoint_sha256"] != checkpoint["parent_checkpoint_sha256"] \
            or projection["delta_sha256"] != checkpoint["last_delta_sha256"]:
        _refuse("checkpoint-idle-basis-binding")
    source._hex(epoch["root_sha256"], "checkpoint-root-pin")
    source._keys(epoch["predecessor"], source_checkpoint._COMMIT_KEYS, "checkpoint-predecessor-shape")
    for value in epoch["predecessor"].values():
        source._hex(value, "checkpoint-predecessor-pin")
    source._validate_epoch_context(owner, epoch)
    for name in source_checkpoint._DOC_KEYS:
        if source.native_bytes(owner, epoch[name]) != source.native_bytes(owner, checkpoint["context"][name]):
            _refuse("checkpoint-idle-context-binding")
    # A private intake view, not a fabricated legacy history/projection.
    view = {"intake": checkpoint["intake"], "intake_sha256": live._sha(checkpoint["intake"])}
    return view, checkpoint["episode_records"]


def capture_checkpoint(owner, *, epoch, projection, observed_at):
    import siasourcebatch as source
    request = {"epoch": epoch, "projection": projection, "observed_at": observed_at}
    raw = source.native_bytes(owner, request)
    view, episodes = _checkpoint_basis(owner, epoch, projection, observed_at)
    result = _capture(owner, epoch=epoch, projection=view, observed_at=observed_at, episode_records=episodes)
    if source.native_bytes(owner, request) != raw:
        _refuse("checkpoint-idle-capture-input-changed")
    return result


def validate_checkpoint(owner, *, epoch, projection, observed_at, idle_input):
    import siasourcebatch as source
    request = {"epoch": epoch, "projection": projection, "observed_at": observed_at, "idle_input": idle_input}
    raw = source.native_bytes(owner, request)
    view, episodes = _checkpoint_basis(owner, epoch, projection, observed_at)
    _validate(owner, epoch=epoch, projection=view, observed_at=observed_at,
              idle_input=idle_input, episode_records=episodes)
    if source.native_bytes(owner, request) != raw:
        _refuse("checkpoint-idle-validation-input-changed")
