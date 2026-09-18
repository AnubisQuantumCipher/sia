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


def _wrapper(owner, *, epoch, projection, observed_at, captured):
    """Build the only episode/replay wrapper authorized by retained inputs."""
    import siasourcebatch as source
    source._json_size(owner, {
        "epoch": epoch, "projection": projection, "capture": captured,
    }, owner["MAX_STATE_JSON_BYTES"], ascii_only=True)
    names = _names(epoch)
    if not names:
        _refuse("idle-native-source-roster-empty")
    if [row["chain"] for row in captured["chains"]] != sorted(names):
        _refuse("idle-native-source-roster-binding")
    episodes = _episode_records(epoch, projection)
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


def _without_native(owner, *, epoch, projection, observed_at):
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
        "episodes": _episode_records(epoch, projection),
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
    request = {"epoch": epoch, "projection": projection,
               "observed_at": observed_at}
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
            observed_at=observed_at, captured=captured)
    else:
        result = _without_native(
            owner, epoch=epoch, projection=projection, observed_at=observed_at)
    raw = live._canonical(result, owner["MAX_STATE_JSON_BYTES"])
    detached = copy.deepcopy(result)
    if source.native_bytes(owner, request) != original \
            or live._canonical(result, owner["MAX_STATE_JSON_BYTES"]) != raw \
            or live._canonical(detached, owner["MAX_STATE_JSON_BYTES"]) != raw:
        _refuse("idle-capture-input-or-result-changed")
    return detached


def validate(owner, *, epoch, projection, observed_at, idle_input):
    """Reconstruct from pinned capture bytes, with no source acquisition."""
    import siasourcebatch as source
    source._json_size(owner, {
        "epoch": epoch, "projection": projection,
        "observed_at": observed_at, "idle_input": idle_input,
    }, owner["MAX_STATE_JSON_BYTES"], ascii_only=True)
    original = live._canonical(idle_input, owner["MAX_STATE_JSON_BYTES"])
    if _names(epoch):
        if type(idle_input) is not dict or set(idle_input) != IDLE_INPUT_KEYS \
                or type(idle_input["gist_inputs"]) is not dict \
                or "capture" not in idle_input["gist_inputs"]:
            _refuse("idle-input-shape")
        expected = _wrapper(
            owner, epoch=epoch, projection=projection, observed_at=observed_at,
            captured=idle_input["gist_inputs"]["capture"])
    else:
        expected = _without_native(
            owner, epoch=epoch, projection=projection, observed_at=observed_at)
    if live._canonical(expected, owner["MAX_STATE_JSON_BYTES"]) != original \
            or live._canonical(idle_input, owner["MAX_STATE_JSON_BYTES"]) != original:
        _refuse("idle-input-binding")
