"""Pure activation competition with a finite, maintained software payload.

Dehaene, Kerszberg & Changeux (1998), Selective Gating, Spatio-Temporal
Dynamics and the maintained-activity Simulation Results motivate inspecting
selection, persistence and common availability:
https://pmc.ncbi.nlm.nih.gov/articles/PMC24407/

The explicit hold timer here is an engineering latch, not the paper's
recurrent neural dynamics, physiological ignition or a complete GNW model.
This module does not read resident state, use a clock, publish files, invoke
consumers, or replace siamind's existing attention-window implementation.
"""

import copy
import hashlib
import json
import math
import re

import siaactivation


MAX_SAFE_INTEGER = siaactivation.MAX_SAFE_INTEGER
MAX_CANDIDATES = siaactivation.MAX_CANDIDATES
MAX_CONSUMERS = 256
MAX_HOLD_SECONDS = 3600
_PROTOCOL_MAX_BYTES = 2097152
MAX_INPUT_BYTES = _PROTOCOL_MAX_BYTES
MAX_TOKEN_BYTES = 128
_ZERO_SHA256 = "0" * 64
_DIGEST = re.compile(r"[0-9a-f]{64}")
_SUBJECT = re.compile(r"[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*")
_CONSUMER = re.compile(r"[a-z0-9][a-z0-9._-]*")
_ORIGINS = frozenset({"evidence", "derived", "model", "legacy-unlabeled"})
_POLICY_KEYS = {
    "v", "algorithm", "time_unit", "slots", "ignition_threshold", "hold_seconds",
    "max_hold_seconds", "tie_break", "release_policy", "consumer_roster",
    "max_candidates", "max_consumers", "max_content_bytes", "max_payload_bytes",
    "max_broadcast_bytes",
}
_FRAME_KEYS = {"v", "complete", "generation_sha256", "candidates"}
_ITEM_KEYS = {"subject", "content", "origin", "source_sha256"}
_CANDIDATE_KEYS = _ITEM_KEYS | {"trace"}
_BINDING_KEYS = {"policy_sha256", "activation_policy_sha256", "consumers_sha256"}
_STATE_KEYS = {
    "v", "component", "phase", "observed_at", "frame_sha256",
    "source_generation_sha256", "parent_state_sha256", "episode",
} | _BINDING_KEYS
_PAYLOAD_KEYS = {
    "v", "component", "phase", "generation", "as_of", "ignited_at", "expires_at",
    "frame_sha256", "source_generation_sha256", "parent_state_sha256", "selected",
} | _BINDING_KEYS
NON_CLAIMS = (
    "computed-unverified labels local floating-point activation and software decisions, not JACKAL exact or formal-bounded assurance.",
    "The finite hold timer and threshold competition are engineering policies, not recurrent neuronal ignition, consciousness, or a complete global neuronal workspace model.",
    "Content, origin labels, source-generation hashes and complete histories are supplied inputs; this component does not authenticate them or equate a source hash with a content digest.",
    "An externally supplied prior-state hash binds a caller-selected state, but neither that pin nor a self-hash independently proves historical correctness or source authenticity.",
    "Every declared consumer receives an identical available payload value; no callback, delivery, consumption, acknowledgment or consumer effect is observed.",
    "Held source content and origin are preserved without promotion or rewriting; explicit release or expiry is required before a different generation may replace them.",
    "Resource admission reserves a worst-case payload for the declared slots and complete consumer roster; it refuses instead of silently truncating or narrowing the broadcast.",
    "No biological correspondence, neuroscience result, retrieval improvement, or held-out win is established; no resident controller integration is performed.",
)


class WorkspaceRefusal(ValueError):
    """A complete workspace transition could not be admitted or represented."""

    def __init__(self, reason):
        self.reason = reason
        self.non_claims = NON_CLAIMS
        super().__init__("maintained-workspace refused: " + reason)


def _refuse(reason):
    raise WorkspaceRefusal(reason)


def _keys(value, required, label):
    if type(value) is not dict or len(value) != len(required) \
            or any(type(key) is not str for key in value) or set(value) != required:
        _refuse(label + "-shape")


def _integer(value, lower, upper):
    return type(value) is int and lower <= value <= upper


def _digest(value):
    return type(value) is str and len(value) == 64 and _DIGEST.fullmatch(value) is not None


def _token(value, maximum, pattern):
    return type(value) is str and 0 < len(value) <= maximum \
        and pattern.fullmatch(value) is not None


def _text_length(value, maximum, *, json_string=False):
    """Count UTF-8 or canonical JSON-string bytes without an encoded copy."""
    if type(value) is not str or len(value) > maximum:
        _refuse("text-byte-capacity")
    consumed = len('""') if json_string else 0
    for char in value:
        point = ord(char)
        if 0xD800 <= point <= 0xDFFF:
            _refuse("text-unpaired-surrogate")
        if json_string and char in '"\\\b\f\n\r\t':
            consumed += 2
        elif json_string and point < 0x20:
            consumed += 6
        elif point <= 0x7F:
            consumed += 1
        elif point <= 0x7FF:
            consumed += 2
        elif point <= 0xFFFF:
            consumed += 3
        else:
            consumed += 4
        if consumed > maximum:
            _refuse("text-byte-capacity")
    if consumed > maximum:
        _refuse("text-byte-capacity")
    return consumed


def _json_length(value, maximum, label):
    """Bound admitted data before JSON allocation; no user-defined codecs."""
    consumed = 0

    def count(item, depth):
        nonlocal consumed
        if depth > 16:
            _refuse(label + "-depth")
        kind = type(item)
        if kind is str:
            consumed += _text_length(item, maximum, json_string=True)
        elif item is None:
            consumed += len("null")
        elif kind is bool:
            consumed += len("true" if item else "false")
        elif kind in (int, float):
            if not math.isfinite(item):
                _refuse(label + "-numeric-domain")
            consumed += len(str(item))
        elif kind is list:
            consumed += len("[]") + max(len(item) - 1, 0)
            for child in item:
                count(child, depth + 1)
        elif kind is dict:
            consumed += len("{}") + max(len(item) - 1, 0) + len(item)
            for key, child in item.items():
                count(key, depth + 1)
                count(child, depth + 1)
        else:
            _refuse(label + "-value")
        if consumed > maximum:
            _refuse(label + "-byte-capacity")

    count(value, 0)
    return consumed


def _policy(value):
    _keys(value, _POLICY_KEYS, "policy")
    if not _integer(value["v"], 1, 1):
        _refuse("policy-version")
    for key, required in (
            ("algorithm", "activation-competition-held-payload-v1"),
            ("time_unit", "unix-seconds-integer"),
            ("tie_break", "stable-input-order"), ("release_policy", "expire-or-explicit")):
        if type(value[key]) is not str or value[key] != required:
            _refuse("policy-contract")
    threshold = value["ignition_threshold"]
    if type(threshold) not in (int, float) \
            or not -MAX_SAFE_INTEGER <= threshold <= MAX_SAFE_INTEGER \
            or not math.isfinite(threshold):
        _refuse("policy-threshold")
    for key, ceiling in (("max_candidates", MAX_CANDIDATES), ("max_consumers", MAX_CONSUMERS),
                         ("max_content_bytes", _PROTOCOL_MAX_BYTES),
                         ("max_payload_bytes", _PROTOCOL_MAX_BYTES),
                         ("max_broadcast_bytes", _PROTOCOL_MAX_BYTES),
                         ("max_hold_seconds", MAX_HOLD_SECONDS)):
        if not _integer(value[key], 1, ceiling):
            _refuse("policy-capacity")
    if not _integer(value["slots"], 1, value["max_candidates"]) \
            or not _integer(value["hold_seconds"], 1, value["max_hold_seconds"]):
        _refuse("policy-slot-or-hold-capacity")
    _consumers(value["consumer_roster"], value["max_consumers"])


def _consumers(value, maximum):
    if type(value) is not list or not 0 < len(value) <= maximum:
        _refuse("consumer-roster-capacity")
    seen = set()
    for name in value:
        if not _token(name, MAX_TOKEN_BYTES, _CONSUMER) or name in seen:
            _refuse("consumer-roster-identity")
        seen.add(name)


def _item(value, policy, *, candidate=False):
    _keys(value, _CANDIDATE_KEYS if candidate else _ITEM_KEYS, "candidate" if candidate else "payload-item")
    if not _token(value["subject"], siaactivation.MAX_SUBJECT_BYTES, _SUBJECT):
        _refuse("candidate-subject")
    _text_length(value["content"], policy["max_content_bytes"])
    if type(value["origin"]) is not str or value["origin"] not in _ORIGINS \
            or not _digest(value["source_sha256"]):
        _refuse("candidate-provenance")


def _frame(value, observed_at, policy, activation_policy):
    _keys(value, _FRAME_KEYS, "frame")
    if not _integer(value["v"], 1, 1) or value["complete"] is not True \
            or not _digest(value["generation_sha256"]):
        _refuse("frame-generation-or-completeness")
    candidates = value["candidates"]
    if type(candidates) is not list or len(candidates) > policy["max_candidates"]:
        _refuse("candidate-capacity")
    subjects = set()
    traces = []
    for value in candidates:
        _item(value, policy, candidate=True)
        if value["subject"] in subjects:
            _refuse("duplicate-candidate")
        trace = value["trace"]
        if type(trace) is not dict or type(trace.get("subject")) is not str \
                or trace["subject"] != value["subject"]:
            _refuse("candidate-trace-subject")
        subjects.add(value["subject"])
        traces.append(trace)
    # Reuse the existing pure complete-history validators. No rank, score,
    # hash, deep copy or aggregate-tail reconstruction occurs in this call.
    siaactivation._validate_set(traces, observed_at, activation_policy)


def _episode(value, state, policy):
    _keys(value, _PAYLOAD_KEYS, "episode")
    if not _integer(value["v"], 1, 1) or type(value["component"]) is not str \
            or value["component"] != "maintained-workspace-payload" \
            or type(value["phase"]) is not str or value["phase"] != "holding":
        _refuse("episode-contract")
    for key in _BINDING_KEYS | {"generation", "frame_sha256", "source_generation_sha256"}:
        if not _digest(value[key]):
            _refuse("episode-generation")
    if value["parent_state_sha256"] is not None and not _digest(value["parent_state_sha256"]):
        _refuse("episode-parent-generation")
    start, expiry = value["ignited_at"], value["expires_at"]
    if not _integer(start, 0, MAX_SAFE_INTEGER) \
            or not _integer(expiry, 0, MAX_SAFE_INTEGER) \
            or not _integer(value["as_of"], 0, MAX_SAFE_INTEGER) \
            or value["as_of"] != start \
            or expiry != start + policy["hold_seconds"] \
            or not start <= state["observed_at"] < expiry:
        _refuse("episode-hold-or-chronology")
    if any(value[key] != state[key] for key in _BINDING_KEYS):
        _refuse("episode-protocol-binding")
    selected = value["selected"]
    if type(selected) is not list or not 0 < len(selected) <= policy["slots"]:
        _refuse("episode-selected-capacity")
    subjects = set()
    for item in selected:
        _item(item, policy)
        if item["subject"] in subjects:
            _refuse("episode-duplicate-subject")
        subjects.add(item["subject"])


def _prior(state, expected, observed_at, policy):
    if state is None:
        if expected is not None:
            _refuse("initial-state-pin")
        return
    if not _digest(expected):
        _refuse("prior-state-external-pin-required")
    _keys(state, _STATE_KEYS, "prior-state")
    if not _integer(state["v"], 1, 1) or type(state["component"]) is not str \
            or state["component"] != "maintained-workspace" \
            or type(state["phase"]) is not str or state["phase"] not in {"idle", "holding"} \
            or not _integer(state["observed_at"], 0, MAX_SAFE_INTEGER) \
            or state["observed_at"] > observed_at:
        _refuse("prior-state-contract-or-chronology")
    for key in _BINDING_KEYS | {"frame_sha256", "source_generation_sha256"}:
        if not _digest(state[key]):
            _refuse("prior-state-generation")
    if state["parent_state_sha256"] is not None and not _digest(state["parent_state_sha256"]):
        _refuse("prior-state-parent-generation")
    if state["phase"] == "idle":
        if state["episode"] is not None:
            _refuse("idle-state-has-episode")
    else:
        _episode(state["episode"], state, policy)


def _payload_body(frame_sha256, source_generation, parent, observed_at, bindings, selected, *, holding, policy):
    return {"v": 1, "component": "maintained-workspace-payload",
            "phase": "holding" if holding else "idle", "as_of": observed_at,
            "ignited_at": observed_at if holding else None,
            "expires_at": observed_at + policy["hold_seconds"] if holding else None,
            "frame_sha256": frame_sha256, "source_generation_sha256": source_generation,
            "parent_state_sha256": parent, **bindings, "selected": selected}


def _output_reservation(frame, state, policy, observed_at, consumers):
    """Reserve worst-case slots and escaped consumer copies before scoring."""
    bindings = {key: _ZERO_SHA256 for key in _BINDING_KEYS}
    template = _payload_body(_ZERO_SHA256, _ZERO_SHA256, _ZERO_SHA256,
                             observed_at, bindings, [], holding=True, policy=policy)
    template["generation"] = _ZERO_SHA256
    payload_size = _json_length(template, _PROTOCOL_MAX_BYTES, "payload-reservation")
    sizes = []
    for candidate in frame["candidates"]:
        item = {key: candidate[key] for key in _ITEM_KEYS}
        sizes.append(_json_length(item, _PROTOCOL_MAX_BYTES, "payload-item"))
    # This list contains only admitted bounded candidates' integer sizes.
    sizes.sort(reverse=True)
    selected_sizes = sizes[:policy["slots"]]
    payload_size += sum(selected_sizes) + max(len(selected_sizes) - 1, 0)
    idle_template = _payload_body(_ZERO_SHA256, _ZERO_SHA256, _ZERO_SHA256,
                                  observed_at, bindings, [], holding=False, policy=policy)
    idle_template["generation"] = _ZERO_SHA256
    payload_size = max(payload_size, _json_length(
        idle_template, _PROTOCOL_MAX_BYTES, "idle-payload-reservation"))
    if state is not None and state["episode"] is not None:
        payload_size = max(payload_size, _json_length(
            state["episode"], _PROTOCOL_MAX_BYTES, "held-payload"))
    if payload_size > policy["max_payload_bytes"]:
        _refuse("payload-byte-capacity")
    envelope = {"generation": _ZERO_SHA256, "payload_sha256": _ZERO_SHA256, "payload_json": ""}
    envelope_size = _json_length(envelope, _PROTOCOL_MAX_BYTES, "broadcast-envelope")
    # JSON embedding can escape every payload byte; reserve that worst case
    # without first constructing or duplicating consumer payload strings.
    broadcast_size = len("{}") + max(len(consumers) - 1, 0)
    for consumer in consumers:
        broadcast_size += _text_length(consumer, _PROTOCOL_MAX_BYTES, json_string=True) \
            + len(":") + envelope_size + 2 * payload_size
    if broadcast_size > policy["max_broadcast_bytes"]:
        _refuse("broadcast-byte-capacity")


def _validate_inputs(frame, observed_at, state, expected, policy, activation_policy, consumers, release):
    _policy(policy)
    if not _integer(observed_at, 0, MAX_SAFE_INTEGER):
        _refuse("observation-time")
    if observed_at + policy["hold_seconds"] > MAX_SAFE_INTEGER:
        _refuse("hold-time-range")
    if type(release) is not bool:
        _refuse("release-contract")
    _consumers(consumers, policy["max_consumers"])
    if consumers != policy["consumer_roster"]:
        _refuse("consumer-roster-incomplete-or-reordered")
    _frame(frame, observed_at, policy, activation_policy)
    _prior(state, expected, observed_at, policy)
    _json_length({"frame": frame, "observed_at": observed_at, "previous_state": state,
                  "expected_previous_state_sha256": expected, "policy": policy,
                  "activation_policy": activation_policy, "consumers": consumers,
                  "release": release}, MAX_INPUT_BYTES, "input")
    _output_reservation(frame, state, policy, observed_at, consumers)


def _encode(value, maximum, label):
    size = _json_length(value, maximum, label)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) != size or len(raw) > maximum:
        _refuse(label + "-byte-count-mismatch")
    return raw


def _sha(value):
    return hashlib.sha256(_encode(value, MAX_INPUT_BYTES, "identity")).hexdigest()


def _bindings(policy, activation_policy, consumers):
    return {"policy_sha256": _sha(policy), "activation_policy_sha256": _sha(activation_policy),
            "consumers_sha256": _sha(consumers)}


def _verify_prior(frame, state, expected, bindings, observed_at, release):
    if state is None:
        return
    if _sha(state) != expected:
        _refuse("prior-state-external-pin-mismatch")
    if any(state[key] != value for key, value in bindings.items()):
        _refuse("prior-state-protocol-generation-mismatch")
    episode = state["episode"]
    if episode is None:
        return
    if _sha({key: value for key, value in episode.items() if key != "generation"}) != episode["generation"]:
        _refuse("episode-payload-generation-mismatch")
    if release or observed_at >= episode["expires_at"]:
        return
    candidates = {item["subject"]: item for item in frame["candidates"]}
    for item in episode["selected"]:
        current = candidates.get(item["subject"])
        if current is None or any(current[key] != item[key] for key in _ITEM_KEYS):
            _refuse("held-source-missing-or-generation-changed")


def advance_workspace(frame, *, observed_at, previous_state, expected_previous_state_sha256,
                      policy, activation_policy, consumers, release):
    """Return one complete transition and shared available payload, or refuse.

    Callers retain state_sha256 independently for the next transition. That
    external expectation is required even when the state self-hash is valid.
    Holding freezes the entire selected episode; expiry followed by new
    selection is explicitly a replacement, not an unreported release.
    """
    try:
        _validate_inputs(frame, observed_at, previous_state, expected_previous_state_sha256,
                         policy, activation_policy, consumers, release)
        bindings = _bindings(policy, activation_policy, consumers)
        _verify_prior(frame, previous_state, expected_previous_state_sha256,
                      bindings, observed_at, release)
        admitted = copy.deepcopy({"frame": frame, "state": previous_state, "policy": policy,
                                  "activation_policy": activation_policy, "consumers": consumers})
        frame, previous_state, policy = admitted["frame"], admitted["state"], admitted["policy"]
        activation_policy, consumers = admitted["activation_policy"], admitted["consumers"]
        _validate_inputs(frame, observed_at, previous_state, expected_previous_state_sha256,
                         policy, activation_policy, consumers, release)
        bindings = _bindings(policy, activation_policy, consumers)
        _verify_prior(frame, previous_state, expected_previous_state_sha256,
                      bindings, observed_at, release)
        frame_sha256 = _sha(frame)
        activation = siaactivation.rank_traces(
            [item["trace"] for item in frame["candidates"]],
            observed_at=observed_at, policy=activation_policy)
        scores = {item["subject"]: item for item in activation["activations"]}
        eligible = {subject for subject, item in scores.items()
                    if item["status"] == "computed-unverified"
                    and item["score"] >= policy["ignition_threshold"]}
        episode = None if previous_state is None else previous_state["episode"]
        release_reason = None
        if release:
            episode = None
            transition, release_reason = "released", "explicit-release"
        elif episode is not None and observed_at < episode["expires_at"]:
            transition = "sustained"
        else:
            if episode is not None:
                release_reason = "hold-expired"
            episode = None
            subjects = [subject for subject in activation["order"] if subject in eligible][:policy["slots"]]
            if subjects:
                candidates = {item["subject"]: item for item in frame["candidates"]}
                selected = [{key: candidates[subject][key] for key in _ITEM_KEYS} for subject in subjects]
                body = _payload_body(frame_sha256, frame["generation_sha256"],
                                     expected_previous_state_sha256, observed_at, bindings,
                                     selected, holding=True, policy=policy)
                episode = {**body, "generation": _sha(body)}
                transition = "replaced" if release_reason is not None else "ignited"
            else:
                transition = "released" if release_reason is not None else "idle"
        if episode is None:
            body = _payload_body(frame_sha256, frame["generation_sha256"],
                                 expected_previous_state_sha256, observed_at, bindings,
                                 [], holding=False, policy=policy)
            payload = {**body, "generation": _sha(body)}
        else:
            payload = episode
        raw_payload = _encode(payload, policy["max_payload_bytes"], "payload")
        payload_json = raw_payload.decode("utf-8")
        payload_sha256 = hashlib.sha256(raw_payload).hexdigest()
        slots = [item["subject"] for item in payload["selected"]]
        selected_subjects = set(slots)
        state = {"v": 1, "component": "maintained-workspace",
                 "phase": "holding" if episode is not None else "idle", "observed_at": observed_at,
                 "frame_sha256": frame_sha256, "source_generation_sha256": frame["generation_sha256"],
                 "parent_state_sha256": expected_previous_state_sha256, **bindings, "episode": episode}
        _prior(state, _sha(state), observed_at, policy)
        broadcast = {consumer: {"generation": payload["generation"],
                                "payload_sha256": payload_sha256, "payload_json": payload_json}
                     for consumer in consumers}
        _json_length(broadcast, policy["max_broadcast_bytes"], "broadcast")
        return {"v": 1, "component": "maintained-workspace", "status": "computed-unverified",
                "observed_at": observed_at, "transition": transition, "release_reason": release_reason,
                "activation": activation, "slots": slots,
                "candidates": [{"subject": item["subject"], "eligible": item["subject"] in eligible,
                                "selected": item["subject"] in selected_subjects}
                               for item in frame["candidates"]],
                "state": state, "state_sha256": _sha(state), "payload_json": payload_json,
                "payload_sha256": payload_sha256, "broadcast": broadcast,
                "non_claims": list(NON_CLAIMS)}
    except WorkspaceRefusal:
        raise
    except siaactivation.ActivationRefusal as exc:
        raise WorkspaceRefusal("activation-input-or-numeric-refusal") from exc
    except (TypeError, ValueError, OverflowError, KeyError, RecursionError, UnicodeError) as exc:
        raise WorkspaceRefusal("input-admission-or-representation") from exc
