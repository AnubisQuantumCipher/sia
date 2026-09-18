"""Pure idle disposition when the selected roster has no native gist source.

Every controller episode remains represented. Absence of a supported source
in this roster grants no assertion about machine history and manufactures no
capture, replay exposure, gist candidate, or support witness.
"""

import copy

import sialivegist as native
import sialiveloop as live


WRAPPER_KEYS = frozenset({
    "idle_without_native", "expected_idle_without_native_sha256",
})
DOCUMENT_KEYS = frozenset({
    "schema", "availability", "epoch_id", "intake_sha256", "observed_at",
    "live_policy_sha256", "source_ids", "episodes", "non_claims",
})
RECEIPT_KEYS = frozenset({
    "schema", "status", "availability", "idle_without_native",
    "idle_without_native_sha256", "gist", "non_claims", "binding_sha256",
})
NON_CLAIMS = (
    "No selected controller source has a supported native gist binding; this does not establish that the machine has no native history.",
    "Controller episodes and their origins remain unchanged; no native occurrence, capture, replay exposure, gist candidate or consolidation is manufactured.",
    "An idle disposition is a local selection result, not source truth, publication, delivery, biological sleep or a cognitive win.",
)


class LiveIdleRefusal(ValueError):
    def __init__(self, reason):
        self.reason = reason
        self.non_claims = list(NON_CLAIMS)
        super().__init__("live idle disposition refused: " + reason)


def _refuse(reason):
    raise LiveIdleRefusal(reason)


def _keys(value, fields, reason):
    if type(value) is not dict or set(value) != fields:
        _refuse(reason)


def _body(value):
    return {
        "schema": "sia-live-idle-without-native-binding-v1",
        "status": "bound-no-gist",
        "availability": "no-selected-supported-native-source",
        "idle_without_native": value["idle_without_native"],
        "idle_without_native_sha256": value[
            "expected_idle_without_native_sha256"],
        "gist": None,
        "non_claims": list(NON_CLAIMS),
    }


def _prepare(request):
    live._size(request, live.MAX_INPUT_BYTES)
    policy, value = request["policy"], request["idle_input"]
    live._policy(policy)
    live._size(request, policy["limits"]["max_input_bytes"])
    if policy["schema"] != "sia-live-loop-policy-v2":
        _refuse("bound-live-policy-required")
    _keys(value, WRAPPER_KEYS, "no-native-wrapper-shape")
    document = value["idle_without_native"]
    _keys(document, DOCUMENT_KEYS, "no-native-document-shape")
    if document["schema"] != "sia-live-idle-without-native-v1" \
            or document["availability"] != "no-selected-supported-native-source" \
            or document["non_claims"] != list(NON_CLAIMS):
        _refuse("no-native-document-contract")
    intake = request["intake"]
    observed_at = request["observed_at"]
    if not live._integer(observed_at) \
            or type(document["observed_at"]) is not int \
            or document["observed_at"] != observed_at \
            or document["epoch_id"] != intake["epoch_id"] \
            or document["intake_sha256"] != request["expected_intake_sha256"] \
            or document["live_policy_sha256"] != request["expected_policy_sha256"]:
        _refuse("no-native-outer-pulse-binding")
    live._pages(intake, observed_at, policy)
    if document["source_ids"] != intake["symbols"] \
            or any(source in native._NATIVE_SOURCES
                   for source in document["source_ids"]):
        _refuse("no-native-source-roster")
    episodes = document["episodes"]
    if type(episodes) is not list \
            or len(episodes) != len(intake["observations"]):
        _refuse("no-native-complete-episode-roster")
    for episode, observation in zip(episodes, intake["observations"], strict=True):
        _keys(episode, native._EPISODE_KEYS, "no-native-episode-shape")
        if episode["native_occurrence"] is not None \
                or episode["source_id"] != observation["symbol"] \
                or episode["observation_id"] != observation["id"] \
                or observation["context"] != "controller-source-return":
            _refuse("no-native-episode-binding")
        record = episode["event_record"]
        core = native.gist.history.sialib
        event = core._event_from_replay_record(record)
        if core._event_replay_record(event) != record \
                or record["ts"] != observation["native_timestamp"] \
                or live._sha({
                    "schema": "sia-controller-event-association-v1",
                    "epoch_id": document["epoch_id"],
                    "source_id": episode["source_id"],
                    "event_id": record["event_id"],
                }) != episode["observation_id"]:
            _refuse("no-native-exact-event-binding")
    for field in ("intake", "policy"):
        live._pin(request[field], request["expected_" + field + "_sha256"])
    live._pin(document, value["expected_idle_without_native_sha256"])
    ceiling = policy["limits"]["max_output_bytes"]
    reserved = live._size({**_body(value), "binding_sha256": "0" * 64}, ceiling)
    return live._canonical(request), reserved


def reservation(*, intake, expected_intake_sha256, policy,
                expected_policy_sha256, observed_at, idle_input):
    """Validate supplied idle documents and reserve the complete receipt."""
    try:
        _original, reserved = _prepare(locals().copy())
        return reserved
    except LiveIdleRefusal:
        raise
    except (ValueError, RuntimeError, TypeError, KeyError, RecursionError) as exc:
        raise LiveIdleRefusal("no-native-input-contract") from exc


def bind(*, intake, expected_intake_sha256, policy,
         expected_policy_sha256, observed_at, idle_input):
    """Return an immutable no-gist receipt; no acquisition or learning runs."""
    try:
        request = locals().copy()
        original, _reserved = _prepare(request)
        detached = copy.deepcopy(request)
        if live._canonical(request) != original \
                or live._canonical(detached) != original:
            _refuse("no-native-input-copy-changed")
        _prepare(detached)
        body = _body(detached["idle_input"])
        result = {**body, "binding_sha256": live._sha(body)}
        raw = live._canonical(result, policy["limits"]["max_output_bytes"])
        final = copy.deepcopy(result)
        if live._canonical(result) != raw or live._canonical(final) != raw \
                or live._canonical(request) != original \
                or live._canonical(detached) != original:
            _refuse("no-native-input-or-result-changed")
        return final
    except LiveIdleRefusal:
        raise
    except (ValueError, RuntimeError, TypeError, KeyError, RecursionError) as exc:
        raise LiveIdleRefusal("no-native-input-contract") from exc


def validate_receipt(*, intake, expected_intake_sha256, policy,
                     expected_policy_sha256, observed_at, receipt):
    """Reconstruct the complete receipt solely from retained supplied data."""
    live._size(locals().copy(), live.MAX_INPUT_BYTES)
    _keys(receipt, RECEIPT_KEYS, "no-native-receipt-shape")
    expected = bind(
        intake=intake, expected_intake_sha256=expected_intake_sha256,
        policy=policy, expected_policy_sha256=expected_policy_sha256,
        observed_at=observed_at,
        idle_input={
            "idle_without_native": receipt["idle_without_native"],
            "expected_idle_without_native_sha256": receipt[
                "idle_without_native_sha256"],
        })
    if live._canonical(receipt) != live._canonical(expected):
        _refuse("no-native-receipt-binding")
