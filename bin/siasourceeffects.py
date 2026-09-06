"""Crash-recoverable effects publication for one retained source pulse.

The fixed source slot, source/live binding, and status-effects handoff are
already durable when this component starts.  This module publishes their
closed page plan, admits structured corpus/index witnesses, freezes the new
graph-bound status in a memo WAL, publishes the matching live generation, and
then replaces the WAL with one self-hashed receipt.  It never acknowledges or
archives the source.
"""

import copy
import json
import os
import re
import stat


NON_CLAIMS = (
    "The effects receipt binds one retained source/live transition, staged status-effects handoff, local artifact bytes, structured corpus generation and source-scoped index witnesses; it does not authenticate source truth, complete machine history or a hostile same-user environment.",
    "Matching logical page witnesses and a zero-unembedded count do not prove embedding-vector values, ranking behavior, retrieval quality or a held-out cognitive-mechanism win.",
    "Publication does not acknowledge source cursors, settle source refusals, archive the retained batch, prove output delivery or establish readiness.",
    "The receipt is local transaction evidence, not JACKAL assurance or biological cognition.",
)

CORPUS_KEYS = frozenset({
    "schema", "object_format", "git_executable_sha256",
    "before_commit_oid", "corpus_commit_oid", "corpus_tree_oid", "clean",
    "generation_sha256",
})
SYNC_KEYS = frozenset({
    "schema", "source_id", "engine_version", "gbrain_commit",
    "gbrain_bun_lock_sha256", "gbrain_pin_sha256",
    "gbrain_pin_receipt_sha256", "gbrain_release_receipt_sha256",
    "gbrain_executable_sha256", "version_raw_sha256",
    "sync_raw_sha256", "sync_stderr_sha256", "sync_result_sha256",
    "sync_status", "sync_requested_commit", "links_raw_sha256",
    "links_stderr_sha256", "links_result_sha256",
    "links_stale_remaining", "mentions_raw_sha256",
    "mentions_stderr_sha256", "mentions_result_sha256",
    "status_raw_sha256", "status_stderr_sha256", "status_result_sha256",
    "status_last_commit", "local_path", "index_manifest_sha256",
    "chunks_unembedded", "embedding_column", "unacknowledged_failures",
    "projection_request_sha256", "projection_raw_sha256",
    "projection_stderr_sha256", "projection_result_sha256",
    "projection_target_count", "projection_retrieval_bookkeeping_updated",
    "projection_operation_writes_performed", "generation_sha256",
})
TARGET_KEYS = frozenset({
    "slug", "source_sha256", "version_sha256", "page_state",
    "parse_error_codes", "expected_projection_sha256",
    "current_projection_sha256", "current_content_hash",
    "current_content_hash_match", "projection_match",
})
GRAPH_KEYS = frozenset({
    "publication_id", "raw_bytes", "raw_sha256", "nodes", "edges",
    "pages", "complete", "generation_sha256",
})
STATUS_KEYS = frozenset({
    "publication_id", "ts", "raw_bytes", "raw_sha256",
    "semantic_sha256", "generation_sha256",
})
LIVE_KEYS = frozenset({
    "publication_id", "candidate_sha256", "generation_sha256",
    "status_sha256", "candidate_raw_sha256", "generation_raw_sha256",
})
PENDING_KEYS = frozenset({
    "schema", "source_batch_sha256", "source_batch_wire_sha256",
    "source_live_publication_sha256", "event_closure_sha256",
    "closure_result_sha256", "status_effects_sha256", "target_manifest",
    "target_manifest_sha256", "corpus_generation", "sync_generation",
    "graph_generation", "status_generation", "status",
    "prepare_inputs_sha256", "state_sha256", "transition_sha256",
    "non_claims", "pending_sha256",
})
RECEIPT_KEYS = frozenset({
    "schema", "status", "source_batch_sha256",
    "source_batch_wire_sha256", "source_live_publication_sha256",
    "event_closure_sha256", "closure_result_sha256",
    "status_effects_sha256", "target_manifest",
    "target_manifest_sha256", "corpus_generation", "sync_generation",
    "graph_generation", "status_generation", "live_generation",
    "prepare_inputs_sha256", "state_sha256", "transition_sha256",
    "non_claims", "receipt_sha256",
})
_HEX = re.compile(r"[0-9a-f]{64}")
_OID = {"sha1": re.compile(r"[0-9a-f]{40}"),
        "sha256": re.compile(r"[0-9a-f]{64}")}


def _refuse(source, reason, *, upstream=None):
    source.refuse(reason, phase="effects", upstream=upstream)


def _same(live, first, second):
    return live._canonical(first) == live._canonical(second)


def _sha(live, value):
    return live._sha(value)


def _hex(source, value, reason="source-effects-digest"):
    if type(value) is not str or _HEX.fullmatch(value) is None:
        _refuse(source, reason)


def _nonnegative(owner, value):
    return type(value) is int and owner["_nonnegative_status_integer"](value)


def _self_hash(source, live, value, field, keys, reason):
    if type(value) is not dict or set(value) != keys:
        _refuse(source, reason + "-shape")
    _hex(source, value.get(field), reason + "-digest")
    body = {key: item for key, item in value.items() if key != field}
    if value[field] != _sha(live, body):
        _refuse(source, reason + "-identity")


def _plan_publication_result(plan):
    return {
        "schema": "sia-event-page-render-publication-v1",
        "status": "page-bytes-published",
        "plan_sha256": plan["plan_sha256"],
        "day_slugs": plan["day_slugs"],
        "appended_event_ids": plan["appended_event_ids"],
        "admissions": plan["admissions"],
        "page_versions": [
            {key: page[key]
             for key in ("slug", "raw_sha256", "version_sha256")}
            for page in plan["pages"]
        ],
        "non_claims": plan["non_claims"],
    }


def _closure_publication_result(closure):
    batches = []
    for batch in closure["batches"]:
        batches.append({
            "schema": "sia-event-page-render-batch-publication-v1",
            "status": "page-bytes-published",
            "batch_sha256": batch["batch_sha256"],
            "members": [
                _plan_publication_result(plan)
                for plan in batch["members"]
            ],
            "non_claims": batch["non_claims"],
        })
    return {
        "schema": "sia-event-page-closure-publication-v1",
        "status": "page-bytes-published",
        "closure_sha256": closure["closure_sha256"],
        "batches": batches,
        "non_claims": closure["non_claims"],
    }


def _closure_result_identity(source, live, closure, observed):
    if closure is None:
        if observed is not None:
            _refuse(source, "source-effects-null-closure-result")
        return
    try:
        expected = _sha(live, _closure_publication_result(closure))
    except (TypeError, ValueError, KeyError, OverflowError,
            RecursionError) as exc:
        _refuse(source, "source-effects-closure-result", upstream=exc)
    if observed != expected:
        _refuse(source, "source-effects-closure-result")


def _status_effects_identity(owner, source, live, status, binding,
                             observed):
    try:
        history = status["history"]
        handoff = {
            "v": 1,
            "publication_id": binding["publication_id"],
            "effects": {
                "day": status["day"],
                "events_pulse": status["events_pulse"],
                "organs": copy.deepcopy(status["organs"]),
            },
            "history": copy.deepcopy(history[-1]),
        }
        admitted = owner["_pending_pulse_status_effects"]({
            "pulse_status_effects_pending": handoff,
            "pulse_history": copy.deepcopy(history),
        })
    except (TypeError, ValueError, RuntimeError, KeyError, IndexError,
            OverflowError, RecursionError) as exc:
        _refuse(source, "source-effects-status-handoff", upstream=exc)
    if admitted != handoff or observed != _sha(live, handoff):
        _refuse(source, "source-effects-status-handoff")


def _graph_shape(owner, source, live, value, reason):
    _self_hash(source, live, value, "generation_sha256", GRAPH_KEYS, reason)
    if type(value["publication_id"]) is not str \
            or re.fullmatch(r"[0-9a-f]{32}", value["publication_id"]) is None \
            or not _nonnegative(owner, value["raw_bytes"]) \
            or value["raw_bytes"] == 0 \
            or value["raw_bytes"] > owner["MAX_STATE_JSON_BYTES"] \
            or not all(_nonnegative(owner, value[key])
                       for key in ("nodes", "edges", "pages")) \
            or value["complete"] is not True:
        _refuse(source, reason + "-fields")
    _hex(source, value["raw_sha256"], reason + "-wire")


def _status_shape(owner, source, live, value, reason):
    _self_hash(source, live, value, "generation_sha256", STATUS_KEYS, reason)
    if type(value["publication_id"]) is not str \
            or re.fullmatch(r"[0-9a-f]{32}", value["publication_id"]) is None \
            or type(value["ts"]) is not str or not value["ts"] \
            or len(value["ts"]) > owner["MAX_CONFIG_TEXT_CHARS"] \
            or not _nonnegative(owner, value["raw_bytes"]) \
            or value["raw_bytes"] == 0 \
            or value["raw_bytes"] > owner["MAX_STATE_JSON_BYTES"]:
        _refuse(source, reason + "-fields")
    _hex(source, value["raw_sha256"], reason + "-wire")
    _hex(source, value["semantic_sha256"], reason + "-semantic")


def _corpus_generation(owner, source, live, value):
    _self_hash(source, live, value, "generation_sha256", CORPUS_KEYS,
               "source-effects-corpus-generation")
    if value["schema"] != "sia-controller-source-corpus-generation-v1" \
            or value["object_format"] not in _OID \
            or value["clean"] is not True:
        _refuse(source, "source-effects-corpus-generation-fields")
    pattern = _OID[value["object_format"]]
    _hex(source, value["git_executable_sha256"],
         "source-effects-git-executable-digest")
    for key in ("before_commit_oid", "corpus_commit_oid", "corpus_tree_oid"):
        if type(value[key]) is not str or pattern.fullmatch(value[key]) is None:
            _refuse(source, "source-effects-corpus-object-id")
    return copy.deepcopy(value)


def _target_versions(owner, source, closure):
    if closure is None:
        return []
    rows = {}
    try:
        for batch in closure["batches"]:
            for plan in batch["members"]:
                for page in plan["pages"]:
                    row = {key: page[key] for key in (
                        "slug", "raw_sha256", "version_sha256")}
                    row = {
                        "slug": row["slug"],
                        "source_sha256": row["raw_sha256"],
                        "version_sha256": row["version_sha256"],
                    }
                    if owner["_canonical_corpus_slug"](row["slug"]) \
                            != row["slug"]:
                        _refuse(source, "source-effects-target-slug")
                    _hex(source, row["source_sha256"])
                    _hex(source, row["version_sha256"])
                    prior = rows.setdefault(row["slug"], row)
                    if prior != row:
                        _refuse(source, "source-effects-target-version-conflict")
    except (TypeError, ValueError, KeyError, OverflowError,
            RecursionError) as exc:
        _refuse(source, "source-effects-target-roster", upstream=exc)
    return [rows[slug] for slug in sorted(rows)]


def _target_manifest(owner, source, live, value, target_versions):
    if type(value) is not list or len(value) != len(target_versions):
        _refuse(source, "source-effects-target-manifest-shape")
    expected = {row["slug"]: row for row in target_versions}
    prior = None
    detached = []
    for row in value:
        if type(row) is not dict or set(row) != TARGET_KEYS:
            _refuse(source, "source-effects-target-witness-shape")
        slug = row.get("slug")
        if type(slug) is not str \
                or owner["_canonical_corpus_slug"](slug) != slug \
                or prior is not None and slug <= prior:
            _refuse(source, "source-effects-target-witness-order")
        prior = slug
        wanted = expected.get(slug)
        if wanted is None \
                or row.get("source_sha256") != wanted["source_sha256"] \
                or row.get("version_sha256") != wanted["version_sha256"]:
            _refuse(source, "source-effects-target-witness-version")
        for key in (
                "source_sha256", "version_sha256",
                "expected_projection_sha256", "current_projection_sha256",
                "current_content_hash"):
            _hex(source, row.get(key),
                 "source-effects-target-witness-digest")
        if row["page_state"] != "live" \
                or row["parse_error_codes"] != [] \
                or row["expected_projection_sha256"] \
                != row["current_projection_sha256"] \
                or row["expected_projection_sha256"] \
                != row["current_content_hash"] \
                or row["current_content_hash_match"] is not True \
                or row["projection_match"] is not True:
            _refuse(source, "source-effects-target-content-differs")
        detached.append(copy.deepcopy(row))
    if set(expected) != {row["slug"] for row in detached}:
        _refuse(source, "source-effects-target-witness-roster")
    _sha(live, detached)
    return detached


def _sync_generation(owner, source, live, value, corpus, manifest_sha256,
                     manifest_count):
    _self_hash(source, live, value, "generation_sha256", SYNC_KEYS,
               "source-effects-sync-generation")
    if value["schema"] != "sia-controller-source-sync-generation-v2" \
            or value["source_id"] != owner["GBRAIN_SOURCE"] \
            or type(value["engine_version"]) is not str \
            or not value["engine_version"] \
            or len(value["engine_version"]) > owner["MAX_CONFIG_TEXT_CHARS"] \
            or value["sync_status"] not in {
                "synced", "first_sync", "up_to_date"} \
            or value["sync_requested_commit"] \
            != corpus["corpus_commit_oid"] \
            or value["status_last_commit"] \
            != corpus["corpus_commit_oid"] \
            or value["index_manifest_sha256"] != manifest_sha256 \
            or value["chunks_unembedded"] != 0 \
            or value["links_stale_remaining"] != 0 \
            or value["unacknowledged_failures"] != 0 \
            or value["projection_target_count"] != manifest_count \
            or value["projection_retrieval_bookkeeping_updated"] is not False \
            or value["projection_operation_writes_performed"] is not False \
            or type(value["embedding_column"]) is not str \
            or not value["embedding_column"]:
        _refuse(source, "source-effects-sync-generation-fields")
    for key in SYNC_KEYS - {
            "schema", "source_id", "engine_version", "gbrain_commit",
            "sync_status", "sync_requested_commit", "status_last_commit",
            "local_path", "chunks_unembedded", "embedding_column",
            "links_stale_remaining", "unacknowledged_failures",
            "projection_target_count",
            "projection_retrieval_bookkeeping_updated",
            "projection_operation_writes_performed", "generation_sha256"}:
        _hex(source, value[key], "source-effects-sync-generation-digest")
    if type(value["gbrain_commit"]) is not str \
            or re.fullmatch(r"[0-9a-f]{40}", value["gbrain_commit"]) is None \
            or not all(_nonnegative(owner, value[key]) for key in (
                "chunks_unembedded", "links_stale_remaining",
                "unacknowledged_failures", "projection_target_count")):
        _refuse(source, "source-effects-sync-generation-fields")
    local_path = value["local_path"]
    if type(local_path) is not str or "\x00" in local_path \
            or not os.path.isabs(local_path) \
            or os.path.realpath(local_path) != os.path.realpath(owner["CORPUS"]):
        _refuse(source, "source-effects-sync-source-path")
    return copy.deepcopy(value)


def _held_json(owner, source, path, ceiling):
    held = source.HeldFile(owner, path, ceiling, allow_absent=False)
    try:
        if held.generation is None \
                or stat.S_IMODE(held.generation["mode"]) != 0o600:
            _refuse(source, "source-effects-artifact-not-private")
        raw = bytes(held.raw)
        value = copy.deepcopy(held.value)
        held.current()
        held.named_current()
        return raw, value
    finally:
        held.close()


def _graph_generation(owner, source, live):
    raw, graph = _held_json(
        owner, source, owner["GRAPH_PATH"], owner["MAX_STATE_JSON_BYTES"])
    snapshot = owner["_recoverable_graph_snapshot"](
        graph, observed_by=graph.get("ts"))
    if snapshot is None or graph.get("snapshot", {}).get("complete") is not True:
        _refuse(source, "source-effects-graph-generation")
    body = {
        "publication_id": snapshot["publication_id"],
        "raw_bytes": len(raw),
        "raw_sha256": owner["hashlib"].sha256(raw).hexdigest(),
        "nodes": snapshot["nodes"], "edges": snapshot["edges"],
        "pages": snapshot["pages"], "complete": True,
    }
    return {**body, "generation_sha256": _sha(live, body)}, graph


def _status_generation_value(owner, source, live, status):
    try:
        # The live publisher reopens its canonical sorted-key candidate and
        # export_status preserves that order in the retained spaced JSON.
        raw = json.dumps(
            status, sort_keys=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        _refuse(source, "source-effects-status-wire", upstream=exc)
    if len(raw) > owner["MAX_STATE_JSON_BYTES"]:
        _refuse(source, "source-effects-status-capacity")
    body = {
        "publication_id": status["publication_id"], "ts": status["ts"],
        "raw_bytes": len(raw),
        "raw_sha256": owner["hashlib"].sha256(raw).hexdigest(),
        "semantic_sha256": _sha(live, status),
    }
    return {**body, "generation_sha256": _sha(live, body)}


def _status_generation_file(owner, source, live):
    raw, status = _held_json(
        owner, source, owner["STATUS_PATH"], owner["MAX_STATE_JSON_BYTES"])
    expected = _status_generation_value(owner, source, live, status)
    if expected["raw_bytes"] != len(raw) \
            or expected["raw_sha256"] \
            != owner["hashlib"].sha256(raw).hexdigest():
        _refuse(source, "source-effects-status-wire-differs")
    return expected, status


def _live_generation(owner, source, live, memo, admitted_status):
    try:
        view = owner["_read_committed_live_generation"](
            memo=memo, admitted_status=admitted_status)
    except (TypeError, ValueError, RuntimeError, KeyError,
            OverflowError, RecursionError) as exc:
        _refuse(source, "source-effects-live-generation", upstream=exc)
    generation = view.get("generation")
    if view.get("status") != "available" or type(generation) is not dict:
        _refuse(source, "source-effects-live-generation")
    candidate_raw, candidate = _held_json(
        owner, source, owner["LIVE_CANDIDATE_PATH"],
        owner["MAX_STATE_JSON_BYTES"])
    generation_raw, retained = _held_json(
        owner, source, owner["LIVE_STATE_PATH"],
        owner["MAX_STATE_JSON_BYTES"])
    if not _same(live, generation, retained) \
            or candidate.get("candidate_sha256") \
            != generation.get("candidate_sha256"):
        _refuse(source, "source-effects-live-artifact-differs")
    return {
        "publication_id": generation["publication_id"],
        "candidate_sha256": generation["candidate_sha256"],
        "generation_sha256": generation["generation_sha256"],
        "status_sha256": generation["status_sha256"],
        "candidate_raw_sha256":
            owner["hashlib"].sha256(candidate_raw).hexdigest(),
        "generation_raw_sha256":
            owner["hashlib"].sha256(generation_raw).hexdigest(),
    }


def _binding_context(owner, source, live, memo, admitted_status,
                     *, require_handoff):
    view = owner["_read_pending_controller_source_batch"](memo=memo)
    batch = view.get("batch")
    if view.get("status") != "pending" or type(batch) is not dict:
        _refuse(source, "source-effects-source-batch")
    try:
        binding = owner["_controller_source_live_binding_marker"](memo)
    except (TypeError, ValueError, KeyError, OverflowError,
            RecursionError) as exc:
        _refuse(source, "source-effects-live-binding", upstream=exc)
    if binding is None or binding["source_batch_sha256"] \
            != batch["batch_sha256"]:
        _refuse(source, "source-effects-live-binding")
    handoff = None
    if require_handoff:
        try:
            handoff = owner["_pending_pulse_status_effects"](memo)
        except (TypeError, ValueError, RuntimeError, KeyError,
                OverflowError, RecursionError) as exc:
            _refuse(source, "source-effects-status-handoff", upstream=exc)
        if handoff is None or handoff["publication_id"] \
                != binding["publication_id"]:
            _refuse(source, "source-effects-status-handoff")
    candidate = owner["_prepare_controller_source_live_candidate"](
        memo=memo, admitted_status=admitted_status)
    try:
        transition = live.prepare_pulse(**candidate["prepare_inputs"])
    except (TypeError, ValueError, KeyError, OverflowError,
            RecursionError) as exc:
        _refuse(source, "source-effects-transition-replay", upstream=exc)
    if candidate.get("expected_prepare_inputs_sha256") \
            != binding["prepare_inputs_sha256"] \
            or transition.get("state_sha256") != binding["state_sha256"] \
            or transition.get("transition_sha256") \
            != binding["transition_sha256"]:
        _refuse(source, "source-effects-transition-binding")
    return batch, binding, handoff, candidate, transition


def _initial_context(owner, source, live, memo, admitted_status):
    status = owner["_require_status_admission_unchanged"](admitted_status)
    _raw, graph = _held_json(
        owner, source, owner["GRAPH_PATH"], owner["MAX_STATE_JSON_BYTES"])
    try:
        owner["_live_graph_status"](status, graph)
    except (TypeError, ValueError, RuntimeError, KeyError,
            OverflowError, RecursionError) as exc:
        _refuse(source, "source-effects-admitted-graph", upstream=exc)
    batch, binding, handoff, candidate, transition = _binding_context(
        owner, source, live, memo, status, require_handoff=True)
    started_at = handoff["history"][0]
    prepared = owner["_prepare_controller_source_status_effects"](
        admitted_status=status, batch=batch,
        expected_batch_sha256=batch["batch_sha256"],
        source_live_pending=binding, candidate=candidate,
        transition=transition,
        expected_transition_sha256=transition["transition_sha256"],
        started_at=started_at)
    if prepared.get("effects") != handoff["effects"] \
            or prepared.get("history") != memo.get("pulse_history") \
            or prepared.get("history", [None])[-1] != handoff["history"]:
        _refuse(source, "source-effects-status-handoff-differs")
    return status, batch, binding, handoff, candidate, transition, prepared


def _project_status(owner, source, live, admitted, binding, handoff,
                    transition, graph, history, observed_at):
    snapshot = owner["_recoverable_graph_snapshot"](
        graph, observed_by=observed_at)
    if snapshot is None or graph.get("snapshot", {}).get("complete") is not True:
        _refuse(source, "source-effects-projected-graph")
    effects = handoff["effects"]
    status = copy.deepcopy(admitted)
    status.update({
        "version": owner["VERSION"], "ts": observed_at,
        "pulse_seq": binding["seq"],
        "state": "thinking" if effects["events_pulse"] else "ok",
        "publication_id": binding["publication_id"],
        "graph_publication_id": snapshot["publication_id"],
        "day": effects["day"],
        "events_pulse": effects["events_pulse"],
        "events_today": sum(
            row["today"] for row in effects["organs"].values()),
        "organs": copy.deepcopy(effects["organs"]),
        "pages": snapshot["pages"], "graph_nodes": snapshot["nodes"],
        "graph_edges": snapshot["edges"],
        "history": copy.deepcopy(history),
        "workspace": copy.deepcopy(
            transition["state"]["workspace"]["slots"]),
        "sync_note": "",
    })
    return status


def _pending_value(owner, source, live, *, batch, binding, handoff,
                   candidate, transition, closure_result, target_manifest,
                   corpus_generation, sync_generation, graph_generation,
                   status_generation, status):
    closure = batch["event_closure"]
    body = {
        "schema": "sia-controller-source-effects-pending-v1",
        "source_batch_sha256": batch["batch_sha256"],
        "source_batch_wire_sha256": binding["source_batch_wire_sha256"],
        "source_live_publication_sha256": binding["publication_sha256"],
        "event_closure_sha256": (
            None if closure is None else closure["closure_sha256"]),
        "closure_result_sha256": (
            None if closure_result is None else _sha(live, closure_result)),
        "status_effects_sha256": _sha(live, handoff),
        "target_manifest": copy.deepcopy(target_manifest),
        "target_manifest_sha256": _sha(live, target_manifest),
        "corpus_generation": copy.deepcopy(corpus_generation),
        "sync_generation": copy.deepcopy(sync_generation),
        "graph_generation": copy.deepcopy(graph_generation),
        "status_generation": copy.deepcopy(status_generation),
        "status": copy.deepcopy(status),
        "prepare_inputs_sha256": binding["prepare_inputs_sha256"],
        "state_sha256": binding["state_sha256"],
        "transition_sha256": binding["transition_sha256"],
        "non_claims": list(NON_CLAIMS),
    }
    value = {**body, "pending_sha256": _sha(live, body)}
    _pending_shape(owner, source, live, value, batch, binding)
    return value


def _pending_shape(owner, source, live, value, batch, binding):
    _self_hash(source, live, value, "pending_sha256", PENDING_KEYS,
               "source-effects-pending")
    if value["schema"] != "sia-controller-source-effects-pending-v1" \
            or value["non_claims"] != list(NON_CLAIMS) \
            or value["source_batch_sha256"] != batch["batch_sha256"] \
            or value["source_batch_wire_sha256"] \
            != binding["source_batch_wire_sha256"] \
            or value["source_live_publication_sha256"] \
            != binding["publication_sha256"] \
            or value["prepare_inputs_sha256"] \
            != binding["prepare_inputs_sha256"] \
            or value["state_sha256"] != binding["state_sha256"] \
            or value["transition_sha256"] != binding["transition_sha256"]:
        _refuse(source, "source-effects-pending-binding")
    closure = batch["event_closure"]
    closure_sha256 = None if closure is None else closure["closure_sha256"]
    if value["event_closure_sha256"] != closure_sha256 \
            or (closure is None) != (value["closure_result_sha256"] is None) \
            or (closure is None) != (value["corpus_generation"] is None) \
            or (closure is None) != (value["sync_generation"] is None):
        _refuse(source, "source-effects-pending-closure")
    _closure_result_identity(
        source, live, closure, value["closure_result_sha256"])
    for key in ("source_batch_sha256", "source_batch_wire_sha256",
                "source_live_publication_sha256", "status_effects_sha256",
                "target_manifest_sha256", "prepare_inputs_sha256",
                "state_sha256", "transition_sha256"):
        _hex(source, value[key])
    if value["closure_result_sha256"] is not None:
        _hex(source, value["closure_result_sha256"])
    target_versions = _target_versions(owner, source, closure)
    manifest = _target_manifest(
        owner, source, live, value["target_manifest"], target_versions)
    if value["target_manifest_sha256"] != _sha(live, manifest):
        _refuse(source, "source-effects-pending-target-identity")
    if closure is not None:
        corpus = _corpus_generation(
            owner, source, live, value["corpus_generation"])
        _sync_generation(
            owner, source, live, value["sync_generation"], corpus,
            value["target_manifest_sha256"], len(manifest))
    _graph_shape(owner, source, live, value["graph_generation"],
                 "source-effects-pending-graph")
    _status_shape(owner, source, live, value["status_generation"],
                  "source-effects-pending-status")
    if type(value["status"]) is not dict \
            or owner["_recoverable_status_integrity"](value["status"]) is None \
            or value["status_generation"] \
            != _status_generation_value(owner, source, live, value["status"]):
        _refuse(source, "source-effects-pending-status")
    status = value["status"]
    graph = value["graph_generation"]
    status_generation = value["status_generation"]
    if status.get("publication_id") != binding["publication_id"] \
            or status_generation["publication_id"] \
            != binding["publication_id"] \
            or status_generation["ts"] != status.get("ts") \
            or status_generation["semantic_sha256"] != _sha(live, status) \
            or graph["publication_id"] \
            != status.get("graph_publication_id") \
            or graph["nodes"] != status.get("graph_nodes") \
            or graph["edges"] != status.get("graph_edges") \
            or graph["pages"] != status.get("pages"):
        _refuse(source, "source-effects-pending-status-graph-join")
    _status_effects_identity(
        owner, source, live, status, binding,
        value["status_effects_sha256"])
    return copy.deepcopy(value)


def _receipt_from_pending(owner, source, live, pending, live_generation):
    body = {
        "schema": "sia-controller-source-effects-committed-v1",
        "status": ("status-live-committed-no-closure"
                   if pending["event_closure_sha256"] is None
                   else "closure-index-status-live-committed"),
        **{key: copy.deepcopy(pending[key]) for key in (
            "source_batch_sha256", "source_batch_wire_sha256",
            "source_live_publication_sha256", "event_closure_sha256",
            "closure_result_sha256", "status_effects_sha256",
            "target_manifest", "target_manifest_sha256",
            "corpus_generation", "sync_generation", "graph_generation",
            "status_generation", "prepare_inputs_sha256", "state_sha256",
            "transition_sha256", "non_claims")},
        "live_generation": copy.deepcopy(live_generation),
    }
    return {**body, "receipt_sha256": _sha(live, body)}


def _receipt_shape(owner, source, live, value, batch, binding,
                   *, retained_status=None):
    _self_hash(source, live, value, "receipt_sha256", RECEIPT_KEYS,
               "source-effects-receipt")
    closure = batch["event_closure"]
    expected_status = ("status-live-committed-no-closure"
                       if closure is None
                       else "closure-index-status-live-committed")
    if value["schema"] != "sia-controller-source-effects-committed-v1" \
            or value["status"] != expected_status \
            or value["non_claims"] != list(NON_CLAIMS):
        _refuse(source, "source-effects-receipt-fields")
    if value["source_batch_sha256"] != batch["batch_sha256"] \
            or value["source_batch_wire_sha256"] \
            != binding["source_batch_wire_sha256"] \
            or value["source_live_publication_sha256"] \
            != binding["publication_sha256"] \
            or value["prepare_inputs_sha256"] \
            != binding["prepare_inputs_sha256"] \
            or value["state_sha256"] != binding["state_sha256"] \
            or value["transition_sha256"] != binding["transition_sha256"]:
        _refuse(source, "source-effects-receipt-binding")
    closure_sha256 = None if closure is None else closure["closure_sha256"]
    if value["event_closure_sha256"] != closure_sha256 \
            or (closure is None) != (value["corpus_generation"] is None) \
            or (closure is None) != (value["sync_generation"] is None):
        _refuse(source, "source-effects-receipt-closure")
    _closure_result_identity(
        source, live, closure, value["closure_result_sha256"])
    for key in (
            "source_batch_sha256", "source_batch_wire_sha256",
            "source_live_publication_sha256", "status_effects_sha256",
            "target_manifest_sha256", "prepare_inputs_sha256",
            "state_sha256", "transition_sha256"):
        _hex(source, value[key], "source-effects-receipt-digest")
    if value["closure_result_sha256"] is not None:
        _hex(source, value["closure_result_sha256"],
             "source-effects-receipt-digest")
    target_versions = _target_versions(owner, source, closure)
    manifest = _target_manifest(
        owner, source, live, value["target_manifest"], target_versions)
    if value["target_manifest_sha256"] != _sha(live, manifest):
        _refuse(source, "source-effects-receipt-target-identity")
    if closure is not None:
        corpus = _corpus_generation(
            owner, source, live, value["corpus_generation"])
        _sync_generation(
            owner, source, live, value["sync_generation"], corpus,
            value["target_manifest_sha256"], len(manifest))
    _graph_shape(owner, source, live, value["graph_generation"],
                 "source-effects-receipt-graph")
    _status_shape(owner, source, live, value["status_generation"],
                  "source-effects-receipt-status")
    live_generation = value["live_generation"]
    if type(live_generation) is not dict \
            or set(live_generation) != LIVE_KEYS:
        _refuse(source, "source-effects-receipt-live-shape")
    for key in LIVE_KEYS - {"publication_id"}:
        _hex(source, live_generation.get(key),
             "source-effects-receipt-live-digest")
    if type(live_generation.get("publication_id")) is not str \
            or re.fullmatch(r"[0-9a-f]{32}",
                            live_generation["publication_id"]) is None:
        _refuse(source, "source-effects-receipt-live-publication")
    if value["status_generation"]["publication_id"] \
            != binding["publication_id"] \
            or live_generation["publication_id"] \
            != binding["publication_id"] \
            or live_generation["status_sha256"] \
            != value["status_generation"]["semantic_sha256"]:
        _refuse(source, "source-effects-receipt-status-live-join")
    if retained_status is not None:
        if _sha(live, retained_status) \
                != value["status_generation"]["semantic_sha256"]:
            _refuse(source, "source-effects-receipt-retained-status")
        _status_effects_identity(
            owner, source, live, retained_status, binding,
            value["status_effects_sha256"])
    return copy.deepcopy(value)


def _write_memo(owner, source, live, memo, value):
    owner["_memo_text"](value)
    owner["_write_memo"](value)
    durable = owner["load_memo"]()
    if not _same(live, durable, value):
        _refuse(source, "source-effects-memo-publication")
    memo.clear()
    memo.update(copy.deepcopy(value))


def _finalize(owner, source, live, memo, pending):
    status_generation, status = _status_generation_file(
        owner, source, live)
    if status_generation != pending["status_generation"] \
            or not _same(live, status, pending["status"]):
        _refuse(source, "source-effects-published-status-differs")
    graph_generation, graph = _graph_generation(owner, source, live)
    if graph_generation != pending["graph_generation"]:
        _refuse(source, "source-effects-published-graph-differs")
    try:
        owner["_live_graph_status"](status, graph)
    except (TypeError, ValueError, RuntimeError, KeyError,
            OverflowError, RecursionError) as exc:
        _refuse(source, "source-effects-published-status-graph", upstream=exc)
    live_generation = _live_generation(owner, source, live, memo, status)
    if live_generation["status_sha256"] \
            != status_generation["semantic_sha256"]:
        _refuse(source, "source-effects-live-status-join")
    receipt = _receipt_from_pending(
        owner, source, live, pending, live_generation)
    _receipt_shape(owner, source, live, receipt,
                   owner["_read_pending_controller_source_batch"](
                       memo=memo)["batch"],
                   owner["_controller_source_live_binding_marker"](memo),
                   retained_status=status)
    updated = copy.deepcopy(memo)
    updated.pop("controller_source_effects_pending", None)
    updated["controller_source_effects_committed"] = receipt
    updated.pop("ready", None)
    _write_memo(owner, source, live, memo, updated)
    return None


def _recover_pending(owner, source, live, memo, admitted_status, pending):
    current_status = owner["_require_status_admission_unchanged"](
        admitted_status)
    if "live_loop_committed" in memo:
        if not _same(live, current_status, pending["status"]):
            _refuse(source, "source-effects-recovery-status")
        return _finalize(owner, source, live, memo, pending)
    candidate = None
    if not _same(live, current_status, pending["status"]):
        batch, binding, handoff, candidate, transition = _binding_context(
            owner, source, live, memo, current_status,
            require_handoff=True)
        if candidate["expected_prepare_inputs_sha256"] \
                != pending["prepare_inputs_sha256"]:
            _refuse(source, "source-effects-recovery-candidate")
    elif "live_loop_pending" not in memo:
        _refuse(source, "source-effects-recovery-status-premature")
    graph_generation, graph = _graph_generation(owner, source, live)
    if graph_generation != pending["graph_generation"]:
        _refuse(source, "source-effects-recovery-graph")
    try:
        owner["_live_graph_status"](pending["status"], graph)
    except (TypeError, ValueError, RuntimeError, KeyError,
            OverflowError, RecursionError) as exc:
        _refuse(source, "source-effects-recovery-status-graph", upstream=exc)
    if "live_loop_pending" not in memo:
        if candidate is None:
            _refuse(source, "source-effects-recovery-candidate")
        owner["_stage_live_generation"](
            memo=memo, status=pending["status"],
            prepare_inputs=candidate["prepare_inputs"],
            expected_prepare_inputs_sha256=
                candidate["expected_prepare_inputs_sha256"])
    owner["_publish_staged_live_generation"](memo=memo)
    owner["_controller_source_effects_boundary"]("live-published")
    return _finalize(owner, source, live, memo, pending)


def _completed(owner, source, live, memo, admitted_status, receipt,
               retained_batch=None):
    status = owner["_require_status_admission_unchanged"](admitted_status)
    if retained_batch is None:
        view = owner["_read_pending_controller_source_batch"](memo=memo)
        batch = view.get("batch")
    else:
        batch = copy.deepcopy(retained_batch)
    binding = owner["_controller_source_live_binding_marker"](memo)
    if type(batch) is not dict or binding is None:
        _refuse(source, "source-effects-completed-authority")
    status_generation, retained_status = _status_generation_file(
        owner, source, live)
    _receipt_shape(
        owner, source, live, receipt, batch, binding,
        retained_status=retained_status)
    graph_generation, graph = _graph_generation(owner, source, live)
    if not _same(live, status, retained_status) \
            or receipt["status_generation"] != status_generation \
            or receipt["graph_generation"] != graph_generation:
        _refuse(source, "source-effects-completed-artifacts")
    try:
        owner["_live_graph_status"](status, graph)
    except (TypeError, ValueError, RuntimeError, KeyError,
            OverflowError, RecursionError) as exc:
        _refuse(source, "source-effects-completed-status-graph", upstream=exc)
    if receipt["live_generation"] \
            != _live_generation(owner, source, live, memo, status):
        _refuse(source, "source-effects-completed-live")
    return None


def committed_receipt(owner, *, memo, admitted_status, retained_batch=None):
    """Validate and return the exact completed effects receipt without writes."""
    import siasourcebatch as source
    import siasourcepublication as publication
    import sialiveloop as live

    if type(memo) is not dict:
        _refuse(source, "source-effects-memo-shape")
    durable = owner["load_memo"]()
    if not _same(live, durable, memo):
        _refuse(source, "source-effects-memo-authority")
    receipt = memo.get("controller_source_effects_committed")
    if receipt is None or "controller_source_effects_pending" in memo:
        _refuse(source, "source-effects-completed-authority")
    if retained_batch is not None:
        pending = memo.get("controller_source_pending")
        if type(pending) is not dict:
            _refuse(source, "source-effects-completed-authority")
        source.validate_batch(
            owner, retained_batch, pending.get("batch_sha256"))
        raw = source.native_bytes(owner, retained_batch)
        expected = publication._receipt(
            owner, source, retained_batch, raw)
        if not _same(live, expected, pending):
            _refuse(source, "source-effects-completed-authority")
    _completed(
        owner, source, live, memo, admitted_status, receipt,
        retained_batch=retained_batch)
    return copy.deepcopy(receipt)


def validate_archived_receipt(
        owner, *, raw, retained_batch, memo, admitted_status,
        expected_receipt_sha256):
    """Re-admit one canonical retained receipt after its memo compaction.

    The original live-binding marker is deliberately retired by ACK.  The
    immutable receipt retains every binding field used by ``_receipt_shape``;
    this reader reconstructs only that validation view, then rejoins it to the
    retained batch and the currently admitted graph, status and live files.
    """
    import siasourcebatch as source
    import sialiveloop as live

    if not isinstance(raw, bytes) or not raw \
            or len(raw) > owner["MAX_MEMO_BYTES"]:
        _refuse(source, "source-effects-archive-bytes")
    if type(expected_receipt_sha256) is not str \
            or _HEX.fullmatch(expected_receipt_sha256) is None:
        _refuse(source, "source-effects-archive-digest")
    if type(memo) is not dict or type(retained_batch) is not dict:
        _refuse(source, "source-effects-archive-authority")
    try:
        receipt = owner["_strict_json_loads"](
            raw.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        _refuse(source, "source-effects-archive-json", upstream=exc)
    _self_hash(
        source, live, receipt, "receipt_sha256", RECEIPT_KEYS,
        "source-effects-archive-receipt")
    if receipt["receipt_sha256"] != expected_receipt_sha256:
        _refuse(source, "source-effects-archive-identity")
    canonical = source.native_bytes(
        owner, receipt, ceiling=owner["MAX_MEMO_BYTES"])
    if canonical != raw:
        _refuse(source, "source-effects-archive-not-canonical")
    source.validate_batch(
        owner, retained_batch, receipt["source_batch_sha256"])
    batch_raw = source.native_bytes(owner, retained_batch)
    if receipt["source_batch_wire_sha256"] \
            != owner["hashlib"].sha256(batch_raw).hexdigest():
        _refuse(source, "source-effects-archive-batch-wire")

    publication_id = receipt["live_generation"].get("publication_id") \
        if type(receipt["live_generation"]) is dict else None
    binding = {
        "publication_id": publication_id,
        "publication_sha256": receipt["source_live_publication_sha256"],
        "source_batch_wire_sha256": receipt["source_batch_wire_sha256"],
        "prepare_inputs_sha256": receipt["prepare_inputs_sha256"],
        "state_sha256": receipt["state_sha256"],
        "transition_sha256": receipt["transition_sha256"],
    }
    status = owner["_require_status_admission_unchanged"](
        admitted_status)
    status_generation, retained_status = _status_generation_file(
        owner, source, live)
    _receipt_shape(
        owner, source, live, receipt, retained_batch, binding,
        retained_status=retained_status)
    graph_generation, graph = _graph_generation(owner, source, live)
    if not _same(live, status, retained_status) \
            or receipt["status_generation"] != status_generation \
            or receipt["graph_generation"] != graph_generation:
        _refuse(source, "source-effects-archive-artifacts")
    try:
        owner["_live_graph_status"](status, graph)
    except (TypeError, ValueError, RuntimeError, KeyError,
            OverflowError, RecursionError) as exc:
        _refuse(source, "source-effects-archive-status-graph", upstream=exc)
    if receipt["live_generation"] \
            != _live_generation(owner, source, live, memo, status):
        _refuse(source, "source-effects-archive-live")
    return copy.deepcopy(receipt)


def publish(owner, *, memo, admitted_status):
    """Publish or recover exactly one bound source-effects generation."""
    import siasourcebatch as source
    import sialiveloop as live

    try:
        if type(memo) is not dict:
            _refuse(source, "source-effects-memo-shape")
        original = copy.deepcopy(memo)
        durable = owner["load_memo"]()
        if not _same(live, original, memo) \
                or not _same(live, durable, memo):
            _refuse(source, "source-effects-memo-authority")
        committed = memo.get("controller_source_effects_committed")
        pending = memo.get("controller_source_effects_pending")
        if committed is not None:
            if pending is not None:
                _refuse(source, "source-effects-double-state")
            return _completed(
                owner, source, live, memo, admitted_status, committed)
        if pending is not None:
            view = owner["_read_pending_controller_source_batch"](memo=memo)
            batch = view.get("batch")
            binding = owner["_controller_source_live_binding_marker"](memo)
            if type(batch) is not dict or binding is None:
                _refuse(source, "source-effects-pending-authority")
            pending = _pending_shape(
                owner, source, live, pending, batch, binding)
            return _recover_pending(
                owner, source, live, memo, admitted_status, pending)

        admitted, batch, binding, handoff, candidate, transition, prepared = \
            _initial_context(owner, source, live, memo, admitted_status)
        closure = batch["event_closure"]
        closure_result = corpus_generation = sync_generation = None
        target_manifest = []
        target_versions = _target_versions(owner, source, closure)
        if closure is not None:
            closure_result = owner["_publish_event_page_batch_closure"](
                closure=closure,
                expected_closure_sha256=closure["closure_sha256"])
            corpus_generation = _corpus_generation(
                owner, source, live,
                owner["_controller_source_corpus_commit_generation"](
                    source_batch_sha256=batch["batch_sha256"],
                    event_closure_sha256=closure["closure_sha256"]))
            observed = owner["_controller_source_sync_generation"](
                corpus_generation=corpus_generation,
                target_versions=target_versions)
            if type(observed) is not dict or set(observed) != {
                    "sync_generation", "target_manifest",
                    "target_manifest_sha256"}:
                _refuse(source, "source-effects-sync-result-shape")
            target_manifest = _target_manifest(
                owner, source, live, observed["target_manifest"],
                target_versions)
            target_manifest_sha256 = _sha(live, target_manifest)
            if observed["target_manifest_sha256"] \
                    != target_manifest_sha256:
                _refuse(source, "source-effects-sync-target-identity")
            sync_generation = _sync_generation(
                owner, source, live, observed["sync_generation"],
                corpus_generation, target_manifest_sha256,
                len(target_manifest))
        owner["export_graph"]()
        graph_generation, graph = _graph_generation(owner, source, live)
        status = _project_status(
            owner, source, live, admitted, binding, handoff, transition,
            graph, memo["pulse_history"],
            owner["_controller_source_effects_observed_at"]())
        if owner["_recoverable_status_integrity"](status) is None:
            _refuse(source, "source-effects-projected-status")
        status_generation = _status_generation_value(
            owner, source, live, status)
        pending = _pending_value(
            owner, source, live, batch=batch, binding=binding,
            handoff=handoff, candidate=candidate, transition=transition,
            closure_result=closure_result,
            target_manifest=target_manifest,
            corpus_generation=corpus_generation,
            sync_generation=sync_generation,
            graph_generation=graph_generation,
            status_generation=status_generation, status=status)
        updated = copy.deepcopy(memo)
        updated["controller_source_effects_pending"] = pending
        updated.pop("ready", None)
        _write_memo(owner, source, live, memo, updated)
        owner["_controller_source_effects_boundary"]("effects-pending")
        owner["_stage_live_generation"](
            memo=memo, status=status,
            prepare_inputs=candidate["prepare_inputs"],
            expected_prepare_inputs_sha256=
                candidate["expected_prepare_inputs_sha256"])
        owner["_publish_staged_live_generation"](memo=memo)
        owner["_controller_source_effects_boundary"]("live-published")
        return _finalize(owner, source, live, memo, pending)
    except source.SourceBatchRefusal:
        raise
    except (TypeError, ValueError, KeyError, OSError,
            OverflowError, RecursionError) as exc:
        _refuse(source, "source-effects-publication", upstream=exc)
