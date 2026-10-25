"""Unactivated source-bound pack planning; no writes or effect authority.

The caller owns the existing live capture and corpus lease. A result covers the
declared selection and preserves the prior pack; it is not a corpus inventory,
durable intent, source-authenticity proof or permission to retire legacy files.
"""

import os

import siaeventpack as codec
import siaeventpackplan as planner
import siaeventpackreader as reader
import siaeventplan as capture_module
import siaeventpackproposal as proposal


POLICIES = ("MAX_EVENT_INDEX_RECORDS", "MAX_EVENT_INDEX_BYTES", "MAX_STATE_JSON_BYTES",
            "MAX_EPOCH_SOURCE_RECORDS", "MAX_EPOCH_EVENT_IDS",
            "MAX_EPOCH_SOURCE_MANIFEST_BYTES", "MAX_EPOCH_PAGE_BYTES", "MAX_EVENT_PAGE_BYTES")


def _policies(owner):
    values = tuple(owner[name] for name in POLICIES)
    if any(type(value) is not int or value <= 0 for value in values):
        raise ValueError("event pack capture policy is invalid")
    planner._limits(values[:3])
    return values


def _current(owner, capture, policy):
    if _policies(owner) != policy:
        raise ValueError("event pack capture policy changed")
    if owner["_CORPUS_OWNER_DEPTH"].get() <= 0:
        raise ValueError("event pack capture requires the corpus lease")
    if type(capture) is not capture_module._Capture or capture.owner is not owner \
            or capture.root != os.path.abspath(owner["CORPUS"]) \
            or capture.budget.limit != policy[2] or capture.root_fd is None:
        raise ValueError("event pack capture owner mismatch")
    capture.budget.check()


def _selection(owner, organ, prefix, identifiers, policy):
    codec.header_size(organ, prefix)
    if type(identifiers) is not tuple or len(identifiers) > policy[0]:
        raise ValueError("event pack capture selection capacity")
    previous = ""
    for identifier in identifiers:
        if type(identifier) is not str or len(identifier) != 64 \
                or identifier <= previous or identifier[:3] != prefix:
            raise ValueError("event pack capture selection identity")
        owner["_event_index_relative"](organ, identifier)
        previous = identifier


def _legacy(owner, organ, identifier, capture, policy):
    path = capture.path(owner["_event_index_relative"](organ, identifier))
    raw = reader._optional(capture, path, policy[1])
    if raw is not None:
        owner["_validate_event_index_raw"](
            raw, organ, identifier, dependency_capture=capture)
    return raw


def _prior(owner, organ, prefix, capture, policy):
    path = capture.path("/".join(("event-packs", organ, prefix[:2], prefix + ".siaep")))
    raw = reader._optional(capture, path, codec.MAX_BYTES)
    rows = reader._packed_entries(owner, capture, raw, organ, prefix)
    # Even unselected prior entries must agree with an existing legacy copy.
    for identifier, (_entry, packed) in rows.items():
        legacy = _legacy(owner, organ, identifier, capture, policy)
        if legacy is not None and legacy != packed:
            raise ValueError("event index representations conflict")
    return raw, rows


def _records(owner, organ, identifiers, capture, policy, prior):
    records = []
    for identifier in identifiers:
        raw = _legacy(owner, organ, identifier, capture, policy)
        packed = prior.get(identifier)
        if packed is not None:
            if raw is not None and raw != packed[1]:
                raise ValueError("event index representations conflict")
            raw = packed[1]
        if raw is None:
            raise ValueError("event pack capture selected record missing")
        records.append((identifier.encode("ascii"), raw))
    return tuple(records)


def prepare_captured(owner, *, organ, prefix, identifiers, capture):
    """Return the planner's exact partition under one retained source capture.

    Each organ/prefix may be attempted once in this capture. Its reservation
    remains after failure; callers must not reset the whole-operation budget.
    Capture ownership stays with the caller on success and failure. Validate
    again at any later use: this observation is neither atomic nor perpetual.
    """
    policy = _policies(owner)
    _current(owner, capture, policy)
    _selection(owner, organ, prefix, identifiers, policy)
    key = ("event-pack-plan", organ, prefix)
    if key in capture.budget.items:
        raise ValueError("event pack prefix already attempted in capture")
    # Logical result/envelope reservation. CPython allocator overhead is unproved.
    capture.budget.reserve(key, 4096 + codec.MAX_BYTES + 2048 * len(identifiers))
    prior_raw, prior = _prior(owner, organ, prefix, capture, policy)
    records = _records(owner, organ, identifiers, capture, policy, prior)
    _current(owner, capture, policy)
    result = planner.plan(organ, prefix, records, prior_raw, limits=policy[:3])
    _current(owner, capture, policy)
    capture.current()
    _current(owner, capture, policy)
    return result


def _proposal_dependencies(owner, capture, policy, key):
    # Reserve the logical detached-view envelope before constructing it.
    # Existing path strings, generations and directory entries remain borrowed.
    capture.budget.reserve((key, "dependency-view"),
                           4096 + 1024 * (len(capture.files) + len(capture.directories)))
    dependencies = {"schema": "sia-pack-capture-v1", "policies": list(policy),
                    "policy_names": list(POLICIES), "sources": capture.dependencies()}
    size = capture_module._size(dependencies, policy[2])
    capture.budget.reserve((key, "dependencies"), 4096 + 2 * size)
    return capture_module._json(owner, dependencies)


def _proposal_reservation(count):
    # At most four full manifests cover retained selection plus transient
    # reference records, joined records and fallback output. Eight frames cover
    # fixed rosters, frame concatenation/hash slices and generation digests;
    # generation JSON is separately limited to a 4096-byte scratch value.
    # Container allocator overhead is not proved by this logical accounting.
    manifest_bytes = len(proposal.MANIFEST_TAG) + 8 + 72 * count
    return 4 * manifest_bytes + 8 * proposal.FRAME_BYTES + 4096


def _original_generations(owner, organ, records, capture):
    result = []
    for identifier, raw in records:
        relative = owner["_event_index_relative"](organ, identifier.decode("ascii"))
        if relative not in capture.files:
            raise ValueError("pack proposal original was not captured")
        item = capture.files[relative]
        if item is None:
            result.append((False, proposal.ZERO))
            continue
        if item["raw"] != raw:
            raise ValueError("pack proposal original bytes changed")
        capture_module._generation_shape(item["generation"], capture_module.F_KEYS)
        capture_module._size(item["generation"], 4096)
        encoded = capture_module._json(owner, item["generation"])
        result.append((True, proposal.digest(b"LEGACY-GENERATION", encoded)))
    return tuple(result)


def _proposal_parts(owner, organ, prefix, identifiers, capture, result):
    packed, represented, fallback = result
    if packed is None:
        raise ValueError("pack retirement proposal has no target")
    selected = tuple(sorted(represented + fallback))
    if tuple(key.decode("ascii") for key, _raw in selected) != identifiers:
        raise ValueError("pack proposal selection correspondence")
    target = codec.decode(packed, organ, prefix)
    relative = "/".join(("event-packs", organ, prefix[:2], prefix + ".siaep"))
    if relative not in capture.files:
        raise ValueError("pack proposal prior was not captured")
    previous = capture.files[relative]
    prior_raw = None if previous is None else previous["raw"]
    if previous is not None and type(prior_raw) is not bytes:
        raise ValueError("pack proposal prior bytes unavailable")
    prior = () if prior_raw is None else codec.decode(prior_raw, organ, prefix)
    _proposal_correspondence(owner, organ, selected, prior, target, represented, fallback, capture)
    rosters = tuple(proposal.references(organ, prefix, rows)
                    for rows in (prior, target, represented))
    selected_bytes = proposal.manifest(proposal.references(organ, prefix, selected))
    fallback_bytes = proposal.manifest(proposal.references(organ, prefix, fallback))
    originals = _original_generations(owner, organ, represented, capture)
    old_target = proposal.digest(b"TARGET", b"\0" if prior_raw is None else b"\1" + prior_raw)
    new_target = proposal.digest(b"TARGET", b"\1" + packed)
    return rosters, selected_bytes, fallback_bytes, originals, old_target, new_target


def _proposal_correspondence(owner, organ, selected, prior, target, represented, fallback, capture):
    old = dict(prior)
    expected = dict(prior)
    for identifier, raw in selected:
        relative = owner["_event_index_relative"](organ, identifier.decode("ascii"))
        if relative not in capture.files:
            raise ValueError("pack proposal selection was not captured")
        item = capture.files[relative]
        original = old.get(identifier) if item is None else item["raw"]
        if original is None or original != raw:
            raise ValueError("pack proposal selection bytes mismatch")
    for identifier, raw in represented:
        if identifier in expected and expected[identifier] != raw:
            raise ValueError("pack proposal represented conflict")
        expected[identifier] = raw
    if tuple(sorted(expected.items())) != target:
        raise ValueError("pack proposal target coverage mismatch")
    for identifier, raw in fallback:
        relative = owner["_event_index_relative"](organ, identifier.decode("ascii"))
        if identifier in expected or capture.files[relative] is None \
                or capture.files[relative]["raw"] != raw:
            raise ValueError("pack proposal fallback mismatch")


def prepare_proposal(owner, *, organ, prefix, identifiers, capture, operation):
    """Return (frame, selection, fallback, dependencies, transport_result).

    Operation is an untrusted (epoch, transaction, revision, permission) reference.
    This byte-bound observation grants no authentication or effect authority.
    Caller retains the live capture and must revalidate at any later use.
    """
    proposal.request(operation)
    policy = _policies(owner)
    _current(owner, capture, policy)
    _selection(owner, organ, prefix, identifiers, policy)
    key = ("event-pack-proposal", organ, prefix)
    if key in capture.budget.items:
        raise ValueError("pack proposal already attempted in capture")
    capture.budget.reserve(key, _proposal_reservation(len(identifiers)))
    result = prepare_captured(owner, organ=organ, prefix=prefix,
                              identifiers=identifiers, capture=capture)
    _current(owner, capture, policy)
    parts = _proposal_parts(owner, organ, prefix, identifiers, capture, result)
    rosters, selected, fallback, originals, old_target, new_target = parts
    dependencies = _proposal_dependencies(owner, capture, policy, key)
    capture_module._size(capture.root_identity, 4096)
    corpus = capture_module._json(owner, capture.root_identity)
    scope = (proposal.digest(b"CORPUS", corpus), proposal.digest(b"CAPTURE", dependencies),
             proposal.digest(b"SELECTION", selected), proposal.digest(b"FALLBACK", fallback),
             old_target, new_target)
    frame = proposal.encode(organ, prefix, operation, scope, *rosters,
                            len(identifiers), len(result[2]), originals)
    _current(owner, capture, policy)
    capture.current()
    _current(owner, capture, policy)
    return frame, selected, fallback, dependencies, result
