"""Pure correspondence between controller episodes and complete native gist inputs.

This binds supplied original and current page bytes; it neither captures a
source nor holds a filesystem generation. The unchanged siagist learner owns
the engineering replay rule and its computed-unverified result. Live proposal
selection only restricts which of those existing candidates may be proposed.
"""

import copy
import hashlib
import json

import siagist as gist
import sialiveloop as live


MAX_INPUT_BYTES = live.MAX_INPUT_BYTES
MAX_OUTPUT_BYTES = live.MAX_OUTPUT_BYTES
BINDING_NON_CLAIMS = (
    "Episode bindings establish supplied-record correspondence, not collector execution, source authenticity, source freshness, or acknowledgment.",
    "Fresh-capture-only alternatives support attributed gist content but do not create controller observations, encoding events, retrieval events, or uses.",
    "Scoped live proposals do not replace or narrow the complete native capture, replay result, alternative roster, or static control.",
    "The runtime must retain or revalidate fresh source generations through eventual publication; this pure binding does not perform that transaction.",
    "A bound gist proposal is not durable consolidation, publication, delivery, biological consolidation, or a cognitive win.",
)
NON_CLAIMS = tuple(live.NON_CLAIMS) + tuple(gist.NON_CLAIMS) + BINDING_NON_CLAIMS
_RULES = {
    "observation_identity": "epoch-source-event-id-v1",
    "native_join": "exact-projected-record-and-signed-occurrence-v1",
    "page_join": "original-observation-and-current-capture-versions-v1",
    "replay": "supported-native-observation-order-once-v1",
    "support": "complete-capture-alternatives-without-synthetic-uses-v1",
    "proposals": "replay-touched-eligible-cues-only-v1",
}
# These are actual collector identities, not a spelling convention permitting
# arbitrary native chain names to impersonate a controller source.
_NATIVE_SOURCES = {
    "sense_aegis": "aegis", "sense_sekhmet": "sekhmet",
    "sense_sia": "sia", "sense_custos": "custos",
}
_DOCUMENTS = ("intake", "episode_bindings", "gist_inputs")
_REQUEST_KEYS = set(_DOCUMENTS) | {"expected_" + name + "_sha256" for name in _DOCUMENTS}
_BINDING_KEYS = {
    "schema", "epoch_id", "intake_sha256", "observed_at", "live_policy",
    "live_policy_sha256", "capture_sha256", "rules", "episodes", "non_claims",
}
_GIST_KEYS = {
    "capture", "expected_capture_sha256", "replay", "expected_replay_sha256",
    "policy", "expected_policy_sha256",
}
_EPISODE_KEYS = {"observation_id", "source_id", "event_record", "native_occurrence"}
_DIGEST_PLACEHOLDER = "0" * 64


class LiveGistRefusal(ValueError):
    """No partial correspondence or proposal roster is returned."""

    def __init__(self, reason):
        self.reason = reason
        self.non_claims = list(NON_CLAIMS)
        super().__init__("live-gist refused: " + reason)


def _fail(reason):
    raise LiveGistRefusal(reason)


def _keys(value, keys, label):
    if type(value) is not dict or set(value) != keys:
        _fail(label + "-shape")


def _raw(value, ceiling=MAX_INPUT_BYTES):
    return live._canonical(value, ceiling)


def _same(first, second):
    return _raw(first) == _raw(second)


def _source_nonclaims(request):
    captured = request["gist_inputs"]["capture"]
    return {
        "live_loop": list(live.NON_CLAIMS), "replay_gist": list(gist.NON_CLAIMS),
        "capture": captured["non_claims"], "capture_sources": captured["source_non_claims"],
        "episode_bindings": request["episode_bindings"]["non_claims"],
    }


def _gist_args(value):
    return (value["capture"], value["expected_capture_sha256"], value["replay"],
            value["expected_replay_sha256"], value["policy"], value["expected_policy_sha256"])


def _reserve_output(request, events, groups, reserved):
    """Bound all repeated output occurrences before any learner or pin work.

    Canonical gist JSON contains no literal control characters: representing
    it as an outer JSON string costs at most twice its existing byte bound.
    A further whole-artifact bound covers the unchanged occurrence projection.
    Variable binding strings, both page witnesses and source nonclaims are
    counted explicitly, rather than hidden in fixed per-record metadata.
    """
    bindings = request["episode_bindings"]
    base = {
        "schema": "sia-live-replay-gist-binding-v1", "status": "bound-not-published",
        "availability": "no-eligible-native-episodes",
        "bindings": _bindings(request),
        **{name: request[name] for name in _DOCUMENTS},
        "gist": {"artifact_json": "", "artifact_sha256": _DIGEST_PLACEHOLDER},
        "episode_dispositions": [], "support_roster": [], "proposal_decisions": [],
        "proposed_candidate_ids": [], "source_non_claims": _source_nonclaims(request),
        "non_claims": list(NON_CLAIMS), "binding_sha256": _DIGEST_PLACEHOLDER,
    }
    ceiling = min(MAX_OUTPUT_BYTES, bindings["live_policy"]["limits"]["max_output_bytes"])
    amount = live._size(base, ceiling) + 3 * reserved
    matches = {}
    for row in bindings["episodes"]:
        reference = row["native_occurrence"]
        key = None if reference is None else gist._occurrence_key(reference)
        event = events.get(key)
        if key is not None:
            matches.setdefault(key, []).append(row["observation_id"])
        witness = None
        if event is not None:
            retention = event["retention"]
            witness = {
                "occurrence": reference, "page_slug": retention["source_slug"],
                "page_sha256": _DIGEST_PLACEHOLDER,
                "event_id": _DIGEST_PLACEHOLDER, "semantic_id": _DIGEST_PLACEHOLDER,
                "excerpt": retention["retrieval_excerpt"], "excerpt_sha256": _DIGEST_PLACEHOLDER,
                "start_byte": live.MAX_SAFE_INTEGER, "end_byte": live.MAX_SAFE_INTEGER,
            }
        disposition = {
            "observation_id": row["observation_id"], "source_id": row["source_id"],
            "native_occurrence": reference, "disposition": "unsupported-controller-source",
            "reason": "unsupported-controller-source",
            "observation_version_sha256": _DIGEST_PLACEHOLDER,
            "current_version_sha256": _DIGEST_PLACEHOLDER,
            "original_witness": witness, "current_witness": witness,
            "replay_step_id": row["observation_id"], "cue_id": _DIGEST_PLACEHOLDER,
            "cue_eligible": False,
        }
        amount += live._size(disposition, ceiling) + 1
    for event in events.values():
        amount += live._size({"binding_scope": "controller-observed-native",
                              "observation_ids": matches.get(gist._occurrence_key(gist._reference(event)), []),
                              "capture_sha256": _DIGEST_PLACEHOLDER}, ceiling) + 1
    # Candidate/cue identifiers and closed decision reasons have fixed widths.
    # Reuse the learner's existing metadata reservation, with no new limit.
    amount += sum(len(group) for group in groups.values()) * gist._METADATA_RECORD_BYTES
    if amount > ceiling:
        _fail("complete-output-reservation-capacity")
    return ceiling, amount


def _preflight_with_reservation(request):
    # This first walk includes every repeated full document and variable NC;
    # no hash, copy, Event construction or component validation precedes it.
    live._size(request, MAX_INPUT_BYTES)
    _keys(request, _REQUEST_KEYS, "request")
    for name in _DOCUMENTS:
        if not live._digest(request["expected_" + name + "_sha256"]):
            _fail("external-document-pin-required")
    bindings, value = request["episode_bindings"], request["gist_inputs"]
    _keys(bindings, _BINDING_KEYS, "episode-bindings")
    _keys(value, _GIST_KEYS, "gist-inputs")
    if bindings["schema"] != "sia-live-episode-bindings-v1" \
            or not live._token(bindings["epoch_id"]) \
            or not live._integer(bindings["observed_at"]) \
            or any(not live._digest(bindings[key]) for key in
                   ("intake_sha256", "live_policy_sha256", "capture_sha256")) \
            or bindings["rules"] != _RULES \
            or bindings["non_claims"] != list(BINDING_NON_CLAIMS):
        _fail("episode-binding-contract")
    policy = bindings["live_policy"]
    live._policy(policy)
    if policy["schema"] != "sia-live-loop-policy-v2":
        _fail("bound-live-policy-required")
    live._size(request, policy["limits"]["max_input_bytes"])
    if type(bindings["episodes"]) is not list \
            or len(bindings["episodes"]) > policy["limits"]["max_observations"]:
        _fail("episode-roster-capacity")
    for row in bindings["episodes"]:
        _keys(row, _EPISODE_KEYS, "episode")
        if not live._digest(row["observation_id"]) or not live._token(row["source_id"]):
            _fail("episode-identity")
        if row["native_occurrence"] is not None:
            gist._occurrence_key(row["native_occurrence"])
    events, pages, groups, reserved = gist._preflight_with_reservation(*_gist_args(value))
    ceiling, amount = _reserve_output(request, events, groups, reserved)
    return events, pages, ceiling, amount


def _preflight(request):
    events, pages, ceiling, _amount = _preflight_with_reservation(request)
    return events, pages, ceiling


def _bindings(request):
    value, bindings = request["gist_inputs"], request["episode_bindings"]
    return {
        "intake_sha256": request["expected_intake_sha256"],
        "episode_bindings_sha256": request["expected_episode_bindings_sha256"],
        "gist_inputs_sha256": request["expected_gist_inputs_sha256"],
        "capture_sha256": value["expected_capture_sha256"],
        "replay_sha256": value["expected_replay_sha256"],
        "gist_policy_sha256": value["expected_policy_sha256"],
        "live_policy_sha256": bindings["live_policy_sha256"],
        "observed_at": bindings["observed_at"], "epoch_id": bindings["epoch_id"],
    }


def _current(request, original):
    live._size(request, MAX_INPUT_BYTES)
    if _raw(request, MAX_INPUT_BYTES) != original:
        _fail("input-changed-during-binding")


def _page_bytes(page):
    if hashlib.sha256(page["content"].encode("utf-8")).hexdigest() != page["source_sha256"] \
            or gist.history._origin(page["subject"], page["content"])["origin"] != page["origin"]:
        _fail("page-byte-origin-binding")


def _admit(request, events, pages):
    intake, bindings, value = (request[name] for name in _DOCUMENTS)
    for name in _DOCUMENTS:
        if hashlib.sha256(_raw(request[name])).hexdigest() != request["expected_" + name + "_sha256"]:
            _fail("external-document-pin-mismatch")
    if bindings["intake_sha256"] != request["expected_intake_sha256"] \
            or bindings["epoch_id"] != intake["epoch_id"] \
            or bindings["capture_sha256"] != value["expected_capture_sha256"] \
            or hashlib.sha256(_raw(bindings["live_policy"])).hexdigest() != bindings["live_policy_sha256"]:
        _fail("episode-document-binding")
    gist._admit_pins(*_gist_args(value))
    versions = live._pages(intake, bindings["observed_at"], bindings["live_policy"])
    current = {versions[key]["subject"]: versions[key] for key in intake["current_versions"]}
    if len(bindings["episodes"]) != len(intake["observations"]):
        _fail("complete-observation-binding-roster")
    dispositions, steps, inventories = [], [], {}
    for row, observation in zip(bindings["episodes"], intake["observations"], strict=True):
        if row["observation_id"] != observation["id"] \
                or row["source_id"] != observation["symbol"] \
                or observation["context"] != "controller-source-return":
            _fail("ordered-observation-source-binding")
        record = row["event_record"]
        event_object = gist.history.sialib._event_from_replay_record(record)
        if not _same(gist.history.sialib._event_replay_record(event_object), record) \
                or observation["native_timestamp"] != record["ts"]:
            _fail("exact-native-event-metadata")
        identity = {"schema": "sia-controller-event-association-v1", "epoch_id": bindings["epoch_id"],
                    "source_id": row["source_id"], "event_id": record["event_id"]}
        if hashlib.sha256(_raw(identity)).hexdigest() != row["observation_id"]:
            _fail("observation-association-identity")
        original = versions[observation["version_sha256"]]
        present = current.get(original["subject"])
        if present is None:
            _fail("missing-current-observation-subject")
        _page_bytes(original)
        _page_bytes(present)
        disposition = {
            "observation_id": row["observation_id"], "source_id": row["source_id"],
            "native_occurrence": row["native_occurrence"],
            "disposition": "unsupported-controller-source", "reason": "unsupported-controller-source",
            "observation_version_sha256": original["version_sha256"],
            "current_version_sha256": present["version_sha256"],
            "original_witness": None, "current_witness": None,
            "replay_step_id": None, "cue_id": None, "cue_eligible": False,
        }
        chain = _NATIVE_SOURCES.get(row["source_id"])
        if chain is None:
            if row["native_occurrence"] is not None:
                _fail("unsupported-source-native-relabel")
            dispositions.append(disposition)
            continue
        if row["native_occurrence"] is None:
            _fail("required-native-occurrence-missing")
        native = events.get(gist._occurrence_key(row["native_occurrence"]))
        if native is None or native["chain"] != chain or native["projection"] is None:
            _fail("required-native-occurrence-or-projection")
        projected = gist.history.sialib.signed_ledger_event_projection(chain, native["row"])
        if projected is None or not _same(gist.history.sialib._event_replay_record(projected), record):
            _fail("exact-native-projection-record-binding")
        cue, reason = gist._native_relation(native)
        if reason is None and (native["retention"]["status"] != "retained"
                               or native["retention"]["witness_kind"] != "live-event-marker"
                               or native["retention"]["projected_event_retained"] is not True
                               or native["retention"]["value_answer_retained"] is not True):
            _fail("required-native-observation-witness")
        source = pages.get(native["retention"]["source_slug"])
        if source is None or source["slug"] != original["subject"] \
                or source["text"] != present["content"] or source["sha256"] != present["source_sha256"] \
                or source["origin"] != present["origin"]:
            _fail("current-capture-page-version-binding")
        if reason is not None:
            disposition.update(disposition="unsupported-native-grammar", reason=reason)
            dispositions.append(disposition)
            continue
        # A separate immutable page view preserves the original observation;
        # the complete capture/native row and its current retention stay intact.
        before_view = {original["subject"]: {
            "slug": original["subject"], "text": original["content"],
            "sha256": original["source_sha256"], "origin": original["origin"],
        }}
        old_witness = gist._witness(native, before_view, {}, value["policy"])
        new_witness = gist._witness(native, pages, inventories, value["policy"])
        if old_witness is None or new_witness is None:
            _fail("required-native-observation-witness")
        step = {"id": observation["id"], "occurrence": row["native_occurrence"]}
        steps.append(step)
        disposition.update(disposition="replay-bound", reason=None,
                           original_witness=old_witness, current_witness=new_witness,
                           replay_step_id=step["id"], cue_id=gist._identity("sia-gist-cue-v1", *cue))
        dispositions.append(disposition)
    if not _same(value["replay"]["steps"], steps):
        _fail("complete-observed-replay-schedule")
    return dispositions


def _prepare_request_with_reservation(request):
    """Admission and output reservation only; no replay or numeric learning."""
    events, pages, ceiling, amount = _preflight_with_reservation(request)
    original = _raw(request, MAX_INPUT_BYTES)
    dispositions = _admit(request, events, pages)
    _current(request, original)
    return original, dispositions, ceiling, amount


def _prepare_request(request):
    original, dispositions, ceiling, _amount = _prepare_request_with_reservation(request)
    return original, dispositions, ceiling


def _result(request, artifact, dispositions):
    body = json.loads(artifact["artifact_json"])
    cues = {row["id"]: row for row in body["cues"]}
    touched = set()
    for row in dispositions:
        if row["disposition"] == "replay-bound":
            row["cue_eligible"] = cues[row["cue_id"]]["eligible"]
            if row["cue_eligible"]:
                touched.add(row["cue_id"])
    matched = {}
    for row in request["episode_bindings"]["episodes"]:
        if row["native_occurrence"] is not None:
            matched.setdefault(gist._occurrence_key(row["native_occurrence"]), []).append(row["observation_id"])
    support = []
    for row in body["occurrences"]:
        observations = matched.get(gist._occurrence_key(row["occurrence"]), [])
        support.append({**row, "binding_scope": "controller-observed-native" if observations else "fresh-capture-only",
                        "observation_ids": observations,
                        "capture_sha256": request["gist_inputs"]["expected_capture_sha256"]})
    selected = {identity for row in body["readout"] for identity in row["selected"]}
    decisions, proposed = [], []
    for row in body["candidates"]:
        chosen = row["id"] in selected
        eligible = cues[row["cue_id"]]["eligible"]
        allowed = chosen and eligible and row["cue_id"] in touched
        reason = (None if allowed else "ineligible-cue" if not eligible else
                  "cue-not-live-replay-touched" if row["cue_id"] not in touched else "not-selected-by-gist")
        decisions.append({"candidate_id": row["id"], "cue_id": row["cue_id"], "selected_by_gist": chosen,
                          "disposition": "proposed-live" if allowed else "not-proposed-live", "reason": reason})
        if allowed:
            proposed.append(row["id"])
    return {
        "schema": "sia-live-replay-gist-binding-v1", "status": "bound-not-published",
        "availability": ("proposals-prepared" if proposed else
                         "no-eligible-native-episodes" if not touched else "no-accessible-completion"),
        "bindings": _bindings(request), **{name: request[name] for name in _DOCUMENTS},
        "gist": artifact, "episode_dispositions": dispositions, "support_roster": support,
        "proposal_decisions": decisions, "proposed_candidate_ids": proposed,
        "source_non_claims": _source_nonclaims(request), "non_claims": list(NON_CLAIMS),
    }


def bind_replay_gist(*, intake, expected_intake_sha256, episode_bindings,
                     expected_episode_bindings_sha256, gist_inputs, expected_gist_inputs_sha256):
    """Return the complete unchanged replay plus scoped, inert live proposals."""
    try:
        request = locals().copy()
        original, _dispositions, ceiling = _prepare_request(request)
        detached = copy.deepcopy(request)
        _current(request, original)
        _current(detached, original)
        _again, dispositions, _ceiling = _prepare_request(detached)
        _current(request, original)
        _current(detached, original)
        artifact = gist.replay_gist(**detached["gist_inputs"])
        _current(request, original)
        _current(detached, original)
        result = _result(detached, artifact, dispositions)
        # Reserve the final digest field before hashing the exact body.
        live._size({**result, "binding_sha256": _DIGEST_PLACEHOLDER}, ceiling)
        result_bytes = _raw(result, ceiling)
        identity = hashlib.sha256(result_bytes).hexdigest()
        if _raw(result, ceiling) != result_bytes:
            _fail("result-changed-during-digest")
        result["binding_sha256"] = identity
        original_result = _raw(result, ceiling)
        final = copy.deepcopy(result)
        if _raw(result, ceiling) != original_result or _raw(final, ceiling) != original_result:
            _fail("result-changed-during-detachment")
        _current(request, original)
        _current(detached, original)
        return final
    except LiveGistRefusal:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, RuntimeError) as exc:
        # Never echo keeper/path/arbitrary exception text across the pure API.
        raise LiveGistRefusal("upstream-input-or-representation-refusal") from exc
