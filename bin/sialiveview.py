"""Read-only inspection of an acknowledged controller-source live generation.

The resident lease belongs to the running controller.  This reader holds only
the corpus transaction owner and reuses the completed-source reader, retained
effects receipt and committed-live reader.  Compatibility status and legacy
policy state cannot supply missing source authority.

The separate view leaves existing status schemas unchanged.  Values are
retained observations: no score, metric, count or clock is recomputed here.
Corpus bodies and broadcast payloads are excluded from the display envelope.
"""

import contextlib
import copy
import hashlib
import json
import os
import re

import sialiveloop as live
import siasourceack as acknowledgment
import siasourcebatch as source
import siasourceeffects as effects


# An independently declared display envelope within the existing single
# state-artifact ceiling. Exceeding it refuses the whole view, without a tail.
MAX_VIEW_BYTES = 16_777_216
CACHE_BASENAME = "live-view.json"
NON_CLAIMS = (
    "This view reports retained computed-unverified component observations from one acknowledged local source transaction; it is not JACKAL assurance, biological cognition, cognitive authorization or a held-out retrieval win.",
    "The as_of value is the retained controller observation clock, not a fresh measurement of the machine or proof that the displayed workspace is still active now.",
    "Selection-time activation and admission explain a held workspace separately from the current pulse's activation; inspection does not select, broadcast, execute or acknowledge a consumer.",
    "Gist proposals and retained page-publication receipts remain distinct; a receipt establishes only its declared local publication boundary, not successful later recall or biological consolidation.",
    "The published source, effects, live and status joins were revalidated under the corpus owner; represented identities do not establish source truth, complete machine history or protection against hostile same-user mutation.",
    "A cached view is the last acknowledged complete generation, not an observation of an in-progress pulse; cache readers do not acquire the resident writer lease.",
    "The display omits corpus bodies and broadcast payload text. All source, component, publication, origin and delivery nonclaims remain controlling.",
)
_REASON = re.compile(r"[a-z][a-z0-9-]*\Z")
_OWNER_CALLS = (
    "corpus_owner", "load_memo", "read_state_json",
    "_recoverable_status_integrity", "_load_live_publication",
    "_read_committed_live_generation",
)
_PROPOSAL_FIELDS = (
    "subject", "origin", "source_sha256", "content_sha256", "version_sha256",
)
_VIEW_FIELDS = {
    "schema", "status", "origin", "as_of", "publication", "workspace",
    "encoding", "admission", "activation", "coretrieval", "idle",
    "non_claims", "upstream_non_claims", "view_sha256",
}
_PUBLICATION_FIELDS = {
    "publication_id", "pulse_seq", "status_timestamp", "epoch_id",
    "state_sha256", "transition_sha256", "generation_sha256",
    "source_batch_sha256", "source_effects_receipt_sha256", "policy_sha256",
}
_WORKSPACE_FIELDS = {
    "component", "status", "observed_at", "transition", "release_reason",
    "slots", "candidates", "payload_sha256", "phase", "capacity",
    "ignition_threshold", "ignited_at", "expires_at", "selected_sources",
    "selection", "broadcast_identities",
}
_IDLE_FIELDS = {
    "requested", "availability", "binding_status", "binding_sha256",
    "gist_artifact_sha256", "proposed_pages", "gist_publication_status",
    "gist_publication",
}
_FORBIDDEN_CACHE_FIELDS = {
    "content", "chunk_text", "payload_json", "artifact_json",
    "raw_utf8_base64", "output_utf8_base64",
}


class LiveViewRefusal(ValueError):
    """No partial view or compatibility replacement is returned."""

    def __init__(self, reason, *, upstream=None):
        self.status = "refused"
        self.reason = (reason if type(reason) is str and _REASON.fullmatch(reason)
                       else "closed-refusal")
        self.non_claims = list(NON_CLAIMS)
        upstream_reason = getattr(upstream, "reason", None)
        self.upstream_reason = (
            upstream_reason if type(upstream_reason) is str
            and _REASON.fullmatch(upstream_reason) else None)
        self.upstream_non_claims = copy.deepcopy(
            getattr(upstream, "non_claims", ()))
        super().__init__("live view refused: " + self.reason)


def _refuse(reason, *, upstream=None):
    raise LiveViewRefusal(reason, upstream=upstream)


def _owner(owner):
    if type(owner) is not dict \
            or any(not callable(owner.get(name)) for name in _OWNER_CALLS) \
            or type(owner.get("STATUS_PATH")) is not str \
            or any(type(owner.get(name)) is not int or owner[name] <= 0
                   for name in ("MAX_MEMO_BYTES", "MAX_STATE_JSON_BYTES")):
        _refuse("owner-contract")


def _cache_path(owner):
    state = owner.get("STATE") if type(owner) is dict else None
    if type(state) is not str or not os.path.isabs(state) \
            or os.path.normpath(state) != state or state == os.path.sep \
            or "\x00" in state:
        _refuse("cache-owner-contract")
    return os.path.join(state, CACHE_BASENAME)


def _contains_forbidden_cache_field(value):
    if type(value) is dict:
        if _FORBIDDEN_CACHE_FIELDS.intersection(value):
            return True
        return any(_contains_forbidden_cache_field(item)
                   for item in value.values())
    if type(value) is list:
        return any(_contains_forbidden_cache_field(item) for item in value)
    return False


def _validate_cached_view(owner, value):
    if type(value) is not dict or set(value) != _VIEW_FIELDS \
            or value.get("schema") != "sia-controller-live-view-v1" \
            or value.get("status") != "available" \
            or value.get("origin") != "derived" \
            or type(value.get("as_of")) is not int \
            or value.get("non_claims") != list(NON_CLAIMS) \
            or type(value.get("upstream_non_claims")) is not dict \
            or _contains_forbidden_cache_field(value):
        _refuse("cached-view-contract")
    publication = value.get("publication")
    workspace = value.get("workspace")
    idle = value.get("idle")
    if type(publication) is not dict or set(publication) != _PUBLICATION_FIELDS \
            or type(workspace) is not dict or set(workspace) != _WORKSPACE_FIELDS \
            or type(idle) is not dict or set(idle) != _IDLE_FIELDS \
            or any(type(value.get(field)) is not dict for field in (
                "encoding", "activation", "coretrieval")) \
            or type(value.get("admission")) is not list \
            or type(workspace.get("slots")) is not list \
            or type(workspace.get("selected_sources")) is not list \
            or type(workspace.get("broadcast_identities")) is not dict \
            or type(idle.get("proposed_pages")) is not list:
        _refuse("cached-view-contract")
    if any(not live._digest(publication.get(field)) for field in (
            "state_sha256", "transition_sha256", "generation_sha256",
            "source_batch_sha256", "source_effects_receipt_sha256",
            "policy_sha256")) \
            or type(publication.get("pulse_seq")) is not int \
            or publication["pulse_seq"] < 0 \
            or any(type(publication.get(field)) is not str
                   or not publication[field] for field in (
                       "publication_id", "status_timestamp", "epoch_id")):
        _refuse("cached-view-identity")
    expected = hashlib.sha256(_raw(
        owner, {key: item for key, item in value.items()
                if key != "view_sha256"}, display=True)).hexdigest()
    if not live._digest(value.get("view_sha256")) \
            or value["view_sha256"] != expected:
        _refuse("cached-view-digest")
    _raw(owner, value, display=True)
    return value


def read_cached_view(owner):
    """Read the last source-authorized complete view without the writer lease."""
    try:
        _owner(owner)
        value = owner["read_state_json"](
            _cache_path(owner), None, "retained live view", expected_type=dict)
        if value is None:
            _refuse("live-view-cache-unavailable")
        original = _raw(owner, value, display=True)
        detached = copy.deepcopy(_validate_cached_view(owner, value))
        if _raw(owner, detached, display=True) != original:
            _refuse("cached-view-detachment-changed")
        return detached
    except LiveViewRefusal:
        raise
    except (OSError, RuntimeError, TypeError, ValueError, KeyError,
            AttributeError, OverflowError, RecursionError) as exc:
        _refuse("cached-view-refusal", upstream=exc)


def publish_cache(owner):
    """Publish one fully rejoined view for nonblocking resident inspection."""
    try:
        _owner(owner)
        if not callable(owner.get("atomic_write")):
            _refuse("cache-owner-contract")
        value = read_view(owner)
        raw = _raw(owner, _validate_cached_view(owner, value), display=True)
        owner["atomic_write"](
            _cache_path(owner), raw.decode("utf-8") + "\n", mode=0o600)
        retained = read_cached_view(owner)
        if _raw(owner, retained, display=True) != raw:
            _refuse("cached-view-publication-changed")
        return retained
    except LiveViewRefusal:
        raise
    except (OSError, RuntimeError, TypeError, ValueError, KeyError,
            AttributeError, OverflowError, RecursionError) as exc:
        _refuse("cached-view-publication-refusal", upstream=exc)


def _raw(owner, value, *, display=False):
    limit = owner["MAX_STATE_JSON_BYTES"]
    if display:
        if type(MAX_VIEW_BYTES) is not int or MAX_VIEW_BYTES <= 0:
            _refuse("display-envelope-contract")
        limit = min(limit, MAX_VIEW_BYTES)
    return source.native_bytes(owner, value, ceiling=limit)


def _status(owner):
    status = owner["read_state_json"](
        owner["STATUS_PATH"], None, "resident status", expected_type=dict)
    if owner["_recoverable_status_integrity"](status) is None:
        _refuse("status-unavailable")
    return status


def _generation(owner, memo, status, completed):
    view = owner["_read_committed_live_generation"](
        memo=memo, admitted_status=status)
    generation = view.get("generation") if type(view) is dict else None
    if type(view) is not dict or view.get("status") != "available" \
            or type(generation) is not dict \
            or generation.get("generation_sha256") \
            != completed["committed"]["live_generation_sha256"]:
        _refuse("committed-live-generation-unavailable")
    return generation


def _project(*, completed, status, generation, receipt):
    """Project admitted observations without bodies or fresh calculations."""
    state = generation["transition"]["state"]
    maintained = state["workspace"]
    episode = maintained["state"]["episode"]
    held = state["held_selection_receipt"]
    selection = None if held is None else {
        field: held[field] for field in (
            "observed_at", "payload_sha256", "frame_sha256",
            "admission", "activation")}
    workspace = {
        field: maintained[field] for field in (
            "component", "status", "observed_at", "transition",
            "release_reason", "slots", "candidates", "payload_sha256")}
    workspace.update({
        "phase": maintained["state"]["phase"],
        "capacity": state["policy"]["workspace"]["slots"],
        "ignition_threshold": state["policy"]["workspace"]["ignition_threshold"],
        "ignited_at": None if episode is None else episode["ignited_at"],
        "expires_at": None if episode is None else episode["expires_at"],
        "selected_sources": [] if episode is None else [
            {field: item[field] for field in ("subject", "origin", "source_sha256")}
            for item in episode["selected"]],
        "selection": selection,
        "broadcast_identities": {
            consumer: {field: value[field] for field in (
                "generation", "payload_sha256")}
            for consumer, value in maintained["broadcast"].items()},
    })

    proposals = generation["transition"]["gist_pages"]
    publication = receipt.get("gist_publication")
    if publication is not None:
        if type(publication) is not dict \
                or publication.get("schema") != "sia-controller-source-gist-publication-v1" \
                or publication.get("status") != "gist-pages-published" \
                or publication.get("gist_pages_sha256") != live._sha(proposals):
            _refuse("gist-publication-proposal-binding")
        publication_status = publication["status"]
    elif state["idle"]["requested"]:
        publication_status = "proposals-only"
    else:
        publication_status = "not-requested"
    binding = state["idle"].get("binding")
    binding_sources = {}
    if binding is not None:
        if type(binding) is not dict:
            _refuse("idle-binding-shape")
        if binding.get("schema") == "sia-live-idle-without-native-binding-v1":
            import sialiveidle
            try:
                sialiveidle.validate_receipt(
                    intake=state["intake"],
                    expected_intake_sha256=live._sha(state["intake"]),
                    policy=state["policy"], expected_policy_sha256=state["policy_sha256"],
                    observed_at=state["observed_at"], receipt=binding)
            except (ValueError, RuntimeError, TypeError, KeyError,
                    OverflowError, RecursionError) as exc:
                _refuse("no-native-idle-binding", upstream=exc)
            if proposals:
                _refuse("no-native-idle-has-proposals")
        elif binding.get("schema") == "sia-live-replay-gist-binding-v1":
            binding_sources = binding["source_non_claims"]
        else:
            _refuse("idle-binding-schema")
    gist = (binding.get("gist") if type(binding) is dict
            else state["idle"].get("gist"))
    gist_body = None if gist is None else json.loads(gist["artifact_json"])
    idle = {
        "requested": state["idle"]["requested"],
        "availability": None if binding is None else binding["availability"],
        "binding_status": None if binding is None else binding["status"],
        "binding_sha256": None if binding is None else binding["binding_sha256"],
        "gist_artifact_sha256": None if gist is None else gist["artifact_sha256"],
        "proposed_pages": [
            {field: proposal[field] for field in _PROPOSAL_FIELDS}
            for proposal in proposals],
        "gist_publication_status": publication_status,
        "gist_publication": publication,
    }
    return {
        "schema": "sia-controller-live-view-v1", "status": "available",
        "origin": "derived", "as_of": state["observed_at"],
        "publication": {
            **{field: generation[field] for field in (
                "publication_id", "pulse_seq", "epoch_id", "state_sha256",
                "transition_sha256", "generation_sha256")},
            "status_timestamp": status["ts"],
            "source_batch_sha256": completed["committed"]["source_batch_sha256"],
            "source_effects_receipt_sha256": receipt["receipt_sha256"],
            "policy_sha256": state["policy_sha256"],
        },
        "workspace": workspace,
        **{field: state[field] for field in (
            "encoding", "admission", "activation", "coretrieval")},
        "idle": idle,
        "non_claims": list(NON_CLAIMS),
        "upstream_non_claims": {
            "source_ack": list(acknowledgment.NON_CLAIMS),
            "source_batch": completed["batch"]["non_claims"],
            "source_effects": receipt["non_claims"],
            "live_publication": generation["non_claims"],
            "live_loop": state["non_claims"],
            "workspace": maintained["non_claims"],
            "gist_binding": [] if binding is None else binding["non_claims"],
            "gist_binding_sources": binding_sources,
            "gist": [] if gist_body is None else gist_body["non_claims"],
        },
    }


@contextlib.contextmanager
def _source_authority(owner):
    """Hold and rejoin the complete acknowledged source generation."""
    _owner(owner)
    with owner["corpus_owner"]():
        memo = owner["load_memo"]()
        marker = memo.get("controller_source_committed") \
            if type(memo) is dict else None
        if marker is None:
            _refuse("source-completion-unavailable")
        if type(marker) is not dict \
                or set(marker) != acknowledgment._COMMITTED_KEYS \
                or any(not live._digest(value) for value in marker.values()):
            _refuse("source-completion-invalid")
        if acknowledgment._PENDING_ONLY.intersection(memo):
            _refuse("source-completion-pending")
        owner["_load_live_publication"]()
        status = _status(owner)
        # On the compact lane (a retained chain pointer, exactly the
        # selection siacheckpointdispatch.select_chain makes) the completed
        # source is a checkpoint capture: read and rejoin it through the
        # checkpoint-aware readers, as the checkpoint transaction does.
        compact = type(memo.get("controller_checkpoint_chain")) is dict
        completed = (acknowledgment.read_checkpoint_completed if compact
                     else acknowledgment.read_completed)(
            owner, memo=memo, admitted_status=status)
        generation = _generation(owner, memo, status, completed)
        receipt_sha256 = \
            completed["committed"]["source_effects_receipt_sha256"]
        with contextlib.closing(acknowledgment._EffectsArchiveSlot(
                owner, source, receipt_sha256, required=True)) as archive:
            receipt = (effects.validate_checkpoint_archived_receipt if compact
                       else effects.validate_archived_receipt)(
                owner, raw=archive.raw, retained_batch=completed["batch"],
                memo=memo, admitted_status=status,
                expected_receipt_sha256=receipt_sha256)
            values = {
                "memo": memo, "status": status, "completed": completed,
                "generation": generation, "receipt": receipt,
            }
            originals = {
                key: _raw(owner, value) for key, value in values.items()}
            yield values
            for key, value in values.items():
                if _raw(owner, value) != originals[key]:
                    _refuse("projection-input-changed")

            # Rejoin the named retained artifacts after projection. A stale
            # copied generation or archive cannot inherit the first read's
            # authority even though the corpus owner remained held.
            if _raw(owner, owner["load_memo"]()) != originals["memo"] \
                    or _raw(owner, _status(owner)) != originals["status"]:
                _refuse("view-authority-changed")
            current = acknowledgment.read_completed(
                owner, memo=memo, admitted_status=status)
            if _raw(owner, current) != originals["completed"] \
                    or _raw(owner, _generation(
                        owner, memo, status, current)) \
                    != originals["generation"]:
                _refuse("view-generation-changed")
            archive.current()


def read_view(owner):
    """Return one bounded detached source-authorized view or refuse wholly."""
    try:
        with _source_authority(owner) as values:
            completed = values["completed"]
            status = values["status"]
            generation = values["generation"]
            receipt = values["receipt"]
            result = _project(
                completed=completed, status=status,
                generation=generation, receipt=receipt)
            result["view_sha256"] = hashlib.sha256(
                _raw(owner, result, display=True)).hexdigest()
            raw_result = _raw(owner, result, display=True)
            detached = copy.deepcopy(result)
            if _raw(owner, detached, display=True) != raw_result:
                _refuse("view-detachment-changed")
            return detached
    except LiveViewRefusal:
        raise
    except (OSError, RuntimeError, TypeError, ValueError, KeyError,
            AttributeError, OverflowError, RecursionError) as exc:
        _refuse("source-or-representation-refusal", upstream=exc)


def read_history_capture(owner):
    """Return the exact admitted private history from one authorized generation."""
    try:
        with _source_authority(owner) as values:
            transition = values["generation"]["transition"]
            capture = transition["history_capture"]
            expected = transition["history_capture_sha256"]
            admitted = live.admit_history_capture(
                capture, expected_capture_sha256=expected)
            original = _raw(owner, capture)
            if _raw(owner, admitted) != original:
                _refuse("history-capture-admission-changed")
            detached = copy.deepcopy(admitted)
            if _raw(owner, detached) != original:
                _refuse("history-capture-detachment-changed")
            return detached
    except LiveViewRefusal:
        raise
    except (OSError, RuntimeError, TypeError, ValueError, KeyError,
            AttributeError, OverflowError, RecursionError) as exc:
        _refuse("source-or-representation-refusal", upstream=exc)
