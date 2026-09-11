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
_DOCS = ("configuration", "source_catalog", "profile", "live_policy")
_CONTEXT_KEYS = (set(_DOCS) | {"expected_" + name + "_sha256" for name in _DOCS}
                 | {"expected_history_sha256"})
_KEYS = {"schema", "status", "context", "prefix_history_sha256", "observed_at",
         "intake", "first_associations", "seen_batch_ids", "source_non_claims", "non_claims"}


def _wire(owner, value):
    return blocks.source.native_bytes(
        owner, value, ceiling=min(owner["MAX_STATE_JSON_BYTES"], blocks.MAX_DOCUMENT_BYTES))


def _validate(owner, value):
    replay._keys(value, _KEYS, "checkpoint-shape")
    if value["schema"] != "sia-event-replay-checkpoint-v1" \
            or value["status"] != "prepared-not-authorized" \
            or value["non_claims"] != list(NON_CLAIMS):
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
