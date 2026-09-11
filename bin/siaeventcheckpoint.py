"""Bounded replay checkpoints bootstrapped through full source-intake replay.

The checkpoint retains exact page versions, observations and first-association
identity, but references the original history instead of embedding its plans.
Its external digest must come from independently admitted continuation
authority. A self-consistent checkpoint is not that authority.
"""

import json

import siahistoryblock as blocks
import siaeventintake as replay


NON_CLAIMS = (
    "Bootstrap runs the original whole-history projection; checkpoint admission alone checks represented consistency, not a replay of the referenced history.",
    "The raw source/event prefix is referenced, not deleted or copied here. Independent archive/root admission and retention remain required.",
    "An externally supplied checkpoint digest is a byte binding, not source truth, an active head, publication, cursor acknowledgment or a writer permit.",
    "Original version, observation and replay-entry ceilings remain; this checkpoint is not an unbounded-history or real-time-performance guarantee.",
    "No encoding, activation, delivery, consolidation, cognitive authorization, held-out win or JACKAL assurance is established by this operation.",
    "All original source and live nonclaims remain controlling.",
)
DELTA_NON_CLAIMS = (
    "This delta supplies one source-return entry and an independently expected predecessor checkpoint; it does not assert that the entry alone is a complete history.",
    "Checkpoint advancement checks the represented transition, not durable source capture, archive retention, active-head authority or publication.",
    "All original source, checkpoint and live nonclaims remain controlling.",
)
INCREMENTAL_NON_CLAIMS = NON_CLAIMS + (
    "The prefix-history pin names the bootstrap prefix; subsequent steps are bound by parent-checkpoint and delta digests, not relabeled as that original whole history.",
    "Cumulative returned-event and unique batch limits remain across steps. No prior event, page version or observation is evicted by advancement.",
)
_V2_EXTRA = {"parent_checkpoint_sha256", "last_delta_sha256", "total_returned_events"}
_DOCS = ("configuration", "source_catalog", "profile", "live_policy")
_CONTEXT_KEYS = (set(_DOCS) | {"expected_" + name + "_sha256" for name in _DOCS}
                 | {"expected_history_sha256"})
_KEYS = {"schema", "status", "context", "prefix_history_sha256", "observed_at",
         "intake", "first_associations", "seen_batch_ids", "source_non_claims", "non_claims"}


def _wire(owner, value):
    return blocks.source.native_bytes(
        owner, value, ceiling=min(owner["MAX_STATE_JSON_BYTES"], blocks.MAX_DOCUMENT_BYTES))


def _validate(owner, value):
    incremental = type(value) is dict and value.get("schema") == "sia-event-replay-checkpoint-v2"
    replay._keys(value, _KEYS | _V2_EXTRA if incremental else _KEYS, "checkpoint-shape")
    if value["schema"] not in {"sia-event-replay-checkpoint-v1", "sia-event-replay-checkpoint-v2"} \
            or value["status"] != "prepared-not-authorized" \
            or value["non_claims"] != list(INCREMENTAL_NON_CLAIMS if incremental else NON_CLAIMS):
        blocks._refuse("checkpoint-contract")
    context = value["context"]
    replay._keys(context, _CONTEXT_KEYS, "checkpoint-context-shape")
    if context["expected_history_sha256"] != value["prefix_history_sha256"]:
        blocks._refuse("checkpoint-prefix-binding")
    request = {**context, "observed_at": value["observed_at"]}
    replay._context_shape(owner, request)
    replay._catalog(owner, request)
    for name in _DOCS:
        raw = (replay.live._canonical(context[name]) if name == "live_policy"
               else replay.pages._json(owner, context[name]))
        if replay.pages._hash(owner, raw) != context["expected_" + name + "_sha256"]:
            blocks._refuse("checkpoint-context-pin")
    intake, policy = value["intake"], context["live_policy"]
    replay.live._inputs(
        intake, {"schema": "sia-live-deliveries-v1", "epoch_id": intake["epoch_id"],
                 "complete": True, "records": []}, policy, value["observed_at"])
    if intake["symbols"] != [row["source_id"] for row in context["source_catalog"]["sources"]] \
            or intake["contexts"] != [context["profile"]["context"]]:
        blocks._refuse("checkpoint-intake-context")
    observed = {row["id"]: row for row in intake["observations"]}
    index = value["first_associations"]
    if type(index) is not list or len(index) != len(observed):
        blocks._refuse("checkpoint-first-roster")
    keys, identifiers = set(), []
    for row in index:
        replay._keys(row, {"source_id", "event_id", "semantic_id", "observation_id"},
                     "checkpoint-first-shape")
        if row["source_id"] not in intake["symbols"] \
                or not blocks._digest(row["event_id"]) or not blocks._digest(row["semantic_id"]):
            blocks._refuse("checkpoint-first-identity")
        key = (row["source_id"], row["event_id"])
        identifier = replay._sha(owner, {
            "schema": "sia-controller-event-association-v1", "epoch_id": intake["epoch_id"],
            "source_id": key[0], "event_id": key[1]})
        if key in keys or identifier != row["observation_id"] or identifier not in observed \
                or observed[identifier]["symbol"] != row["source_id"]:
            blocks._refuse("checkpoint-first-binding")
        keys.add(key)
        identifiers.append(identifier)
    if identifiers != [row["id"] for row in intake["observations"]]:
        blocks._refuse("checkpoint-first-order")
    if incremental:
        parent, delta = value["parent_checkpoint_sha256"], value["last_delta_sha256"]
        if (parent is None) != (delta is None) \
                or parent is not None and (not blocks._digest(parent) or not blocks._digest(delta)):
            blocks._refuse("checkpoint-step-pins")
        total = value["total_returned_events"]
        if type(total) is not int or not len(index) <= total <= owner["MAX_SOURCE_REPLAY_EVENTS"]:
            blocks._refuse("checkpoint-total-event-capacity")
    batches = value["seen_batch_ids"]
    if type(batches) is not list or not batches \
            or len(batches) > owner["MAX_SOURCE_REPLAY_EVENTS"] \
            or any(not replay.live._token(item) for item in batches) \
            or len(set(batches)) != len(batches):
        blocks._refuse("checkpoint-batch-roster")
    claims = value["source_non_claims"]
    replay._keys(claims, {"configuration", "source_catalog", "profile", "history",
                         "source_returns", "event_batches", "live_loop"}, "checkpoint-source-nonclaims")
    for name in ("configuration", "source_catalog", "profile"):
        if claims[name] != context[name]["non_claims"]:
            blocks._refuse("checkpoint-source-nonclaims")
    if claims["history"] != list(replay.SOURCE_NON_CLAIMS) \
            or claims["live_loop"] != list(replay.live.NON_CLAIMS) \
            or type(claims["source_returns"]) is not list \
            or len(claims["source_returns"]) != len(batches) \
            or type(claims["event_batches"]) is not list:
        blocks._refuse("checkpoint-source-nonclaims")
    for field, key, expected in (
            ("source_returns", "returns_sha256", list(replay.SOURCE_NON_CLAIMS)),
            ("event_batches", "batch_sha256", list(replay.pages.BATCH_NON_CLAIMS))):
        for row in claims[field]:
            replay._keys(row, {key, "non_claims"}, "checkpoint-source-nonclaims")
            if not blocks._digest(row[key]) or row["non_claims"] != expected:
                blocks._refuse("checkpoint-source-nonclaims")


def admit(owner, *, checkpoint, expected_checkpoint_sha256):
    """Validate/detach a pinned checkpoint; do not authenticate its ancestry."""
    raw = _wire(owner, checkpoint)
    blocks._pin(raw, expected_checkpoint_sha256)
    _validate(owner, checkpoint)
    detached = json.loads(raw)
    if _wire(owner, detached) != raw or _wire(owner, checkpoint) != raw:
        blocks._refuse("checkpoint-input-changed")
    return detached


def bootstrap(owner, *, request, expected_request_sha256):
    """Produce a checkpoint only after the original complete replay passes."""
    raw = _wire(owner, request)
    blocks._pin(raw, expected_request_sha256)
    projected = replay.prepare(owner, **request)
    first = []
    for row in projected["associations"]:
        if row["status"] == "first-observation":
            first.append({key: row[key] for key in
                          ("source_id", "event_id", "semantic_id", "observation_id")})
    checkpoint = {
        "schema": "sia-event-replay-checkpoint-v1", "status": "prepared-not-authorized",
        "context": {key: request[key] for key in _CONTEXT_KEYS},
        "prefix_history_sha256": request["expected_history_sha256"],
        "observed_at": request["observed_at"], "intake": projected["intake"],
        "first_associations": first,
        "seen_batch_ids": [entry["source_returns"]["batch_id"] for entry in request["history"]["entries"]],
        "source_non_claims": projected["source_non_claims"], "non_claims": list(NON_CLAIMS),
    }
    checkpoint_raw = _wire(owner, checkpoint)
    _validate(owner, checkpoint)
    detached = json.loads(checkpoint_raw)
    if _wire(owner, checkpoint) != checkpoint_raw or _wire(owner, detached) != checkpoint_raw \
            or _wire(owner, request) != raw:
        blocks._refuse("checkpoint-bootstrap-changed")
    return detached


def bootstrap_incremental(owner, *, request, expected_request_sha256):
    """Bootstrap v2 cumulative accounting from the actual complete history.

    No v1 checkpoint is silently upgraded: it lacks the duplicate-inclusive
    event count, which cannot be inferred from unique observations.
    """
    raw = _wire(owner, request)
    result = bootstrap(owner, request=request, expected_request_sha256=expected_request_sha256)
    result.update(
        schema="sia-event-replay-checkpoint-v2", non_claims=list(INCREMENTAL_NON_CLAIMS),
        parent_checkpoint_sha256=None, last_delta_sha256=None,
        total_returned_events=sum(len(run["events"])
                                  for entry in request["history"]["entries"]
                                  for run in entry["source_returns"]["runs"]))
    result_raw = _wire(owner, result)
    _validate(owner, result)
    detached = json.loads(result_raw)
    if _wire(owner, request) != raw or _wire(owner, result) != result_raw \
            or _wire(owner, detached) != result_raw:
        blocks._refuse("checkpoint-bootstrap-changed")
    return detached


def advance(owner, *, checkpoint, expected_checkpoint_sha256, delta, expected_delta_sha256):
    """Advance one pinned v2 checkpoint without decoding its raw prefix.

    Fixed input slots and output each keep their original document cap.
    Output reservation conservatively counts the prior checkpoint plus the
    entire new projection skeleton and worst-case escaped page contents.
    A reservation refusal has no fallback. No live computation or I/O runs.
    """
    original = _wire(owner, checkpoint)
    delta_raw = _wire(owner, delta)
    blocks._pin(delta_raw, expected_delta_sha256)
    current = admit(owner, checkpoint=checkpoint, expected_checkpoint_sha256=expected_checkpoint_sha256)
    if current["schema"] != "sia-event-replay-checkpoint-v2":
        blocks._refuse("incremental-accounting-required")
    replay._keys(delta, {"schema", "parent_checkpoint_sha256", "entry", "observed_at", "non_claims"},
                 "checkpoint-delta-shape")
    if delta["schema"] != "sia-event-replay-delta-v1" \
            or delta["parent_checkpoint_sha256"] != expected_checkpoint_sha256 \
            or delta["non_claims"] != list(DELTA_NON_CLAIMS):
        blocks._refuse("checkpoint-delta-binding")
    selected = json.loads(delta_raw)
    entry = selected["entry"]
    # A private entry-validation/reservation view, not a fabricated complete
    # history document: no schema or completeness assertion is attached.
    history = {"epoch_id": current["intake"]["epoch_id"],
               "started_at": current["intake"]["started_at"],
               "entries": [entry], "non_claims": list(replay.SOURCE_NON_CLAIMS)}
    request = {**current["context"], "history": history, "observed_at": selected["observed_at"]}
    source_ids, policy = replay._context_shape(owner, request)
    batch_ids, event_count = replay._entries_shape(
        owner, request, history, source_ids, previous=current["observed_at"])
    if batch_ids.intersection(current["seen_batch_ids"]):
        blocks._refuse("checkpoint-duplicate-batch")
    total = current["total_returned_events"] + event_count
    if total > owner["MAX_SOURCE_REPLAY_EVENTS"]:
        blocks._refuse("checkpoint-total-event-capacity")
    if len(current["seen_batch_ids"]) >= owner["MAX_SOURCE_REPLAY_EVENTS"]:
        blocks._refuse("checkpoint-batch-capacity")
    returns = entry["source_returns"]
    if replay._sha(owner, {key: value for key, value in returns.items() if key != "returns_sha256"}) \
            != entry["expected_source_returns_sha256"]:
        blocks._refuse("checkpoint-delta-return-pin")
    claims = current["source_non_claims"]
    additions = replay._source_nonclaims(request)
    new_claims = {**claims, **{name: claims[name] + additions[name]
                             for name in ("source_returns", "event_batches")}}
    updates = {"observed_at": selected["observed_at"], "total_returned_events": total,
               "seen_batch_ids": current["seen_batch_ids"] + [returns["batch_id"]],
               "source_non_claims": new_claims, "parent_checkpoint_sha256": expected_checkpoint_sha256,
               "last_delta_sha256": expected_delta_sha256}
    reserve_first = current["first_associations"] + [
        {"source_id": run["source_id"], "event_id": record["event_id"],
         "semantic_id": record["semantic_id"], "observation_id": "0" * 64}
        for run in returns["runs"] for record in run["events"]]
    skeleton, content_reserve = replay._reservation(owner, request)
    limit = min(owner["MAX_STATE_JSON_BYTES"], blocks.MAX_DOCUMENT_BYTES,
                policy["limits"]["max_output_bytes"])
    reserved = (blocks.source._json_size(owner, {**current, **updates, "first_associations": reserve_first},
                                        limit, ascii_only=True)
                + blocks.source._json_size(owner, skeleton, limit, ascii_only=True) + content_reserve)
    if reserved > limit:
        blocks._refuse("checkpoint-output-reservation")
    if _wire(owner, checkpoint) != original or _wire(owner, delta) != delta_raw \
            or _wire(owner, selected) != delta_raw:
        blocks._refuse("checkpoint-delta-input-changed")
    intake = current["intake"]
    versions = {page["version_sha256"]: page for page in intake["pages"]}
    active = {versions[pin]["subject"]: pin for pin in intake["current_versions"]}
    observations = {row["id"]: row for row in intake["observations"]}
    first = {(row["source_id"], row["event_id"]):
             (row["semantic_id"], observations[row["observation_id"]])
             for row in current["first_associations"]}
    associations = []
    replay._fold_entry(owner, request, entry, intake, associations, versions, active, first)
    intake["pages"], intake["current_versions"] = list(versions.values()), list(active.values())
    current.update(updates)
    current["first_associations"] = [
        {"source_id": key[0], "event_id": key[1], "semantic_id": semantic,
         "observation_id": observation["id"]}
        for key, (semantic, observation) in first.items()]
    result_raw = _wire(owner, current)
    if len(result_raw) > reserved:
        blocks._refuse("checkpoint-reservation-mismatch")
    _validate(owner, current)
    detached = json.loads(result_raw)
    if _wire(owner, current) != result_raw or _wire(owner, detached) != result_raw \
            or _wire(owner, checkpoint) != original or _wire(owner, delta) != delta_raw \
            or _wire(owner, selected) != delta_raw:
        blocks._refuse("checkpoint-delta-input-or-output-changed")
    return detached
