"""Pure witnessed replay and focused, source-preserving gist candidates.

The scalar update is an engineering error-driven association rule, not the
phased network in Schapiro et al., Methods: Learning / Testing and analyses:
https://pmc.ncbi.nlm.nih.gov/articles/PMC5124075/

Replay changes accessibility of an already witnessed completion. It cannot
create an occurrence, suppress source alternatives, promote an origin, pair
an intention with an outcome, or publish/delete a corpus page.
"""

import copy
from fractions import Fraction
import hashlib
import json
import math
import re

import siacognitivehistory as history


MAX_INPUT_BYTES = history.MAX_CAPTURE_BYTES
MAX_OUTPUT_BYTES = history.MAX_CAPTURE_BYTES
MAX_OCCURRENCES = history.sialib.MAX_SOURCE_REPLAY_EVENTS
MAX_REPLAY_STEPS = 4096
MAX_CUES = 4096
MAX_COMPLETIONS = history.sialib.MAX_SOURCE_REPLAY_EVENTS
MAX_WEIGHT_UPDATES = 65536
MAX_TRACE_CELLS = 65536
MAX_TEXT_BYTES = history.sialib.MAX_EVENT_PAGE_BYTES
MAX_RATIONAL_BITS = 4096
MAX_SAFE_INTEGER = history.sialib.MAX_JSON_SAFE_INTEGER
MAX_TOKEN_BYTES = 128
# A conservative reservation for fixed field names, hashes, identifiers and
# integer formatting in each admitted metadata record. Variable source text
# and rational strings are reserved separately below, before materialization.
_METADATA_RECORD_BYTES = 4096
_HEX = re.compile(r"[0-9a-f]{64}")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*")
_MARKER = re.compile(rb"<!-- sia-event:([0-9a-f]{64}):([0-9a-f]{64}) -->$")
_ORIGINS = frozenset({"evidence", "derived", "model", "legacy-unlabeled"})
_NATIVE_CHAINS = frozenset({"aegis", "sekhmet", "sia"})
_POLICY_KEYS = {"schema", "grammar", "learning", "readout", "fidelity", "limits"}
_LEARNING_KEYS = {"algorithm", "enabled", "rate", "initial"}
_READOUT_KEYS = {"cue_roster", "threshold", "slots_per_cue", "tie_break", "static_control"}
_FIDELITY = {
    "support": "distinct-captured-occurrences-v1",
    "exceptions": "complete-same-cue-completions-v1",
    "origins": "preserve-and-attribute-no-promotion-v1",
    "unsupported": "retain-and-classify-v1",
}
_LIMITS = {
    "max_input_bytes": MAX_INPUT_BYTES, "max_output_bytes": MAX_OUTPUT_BYTES,
    "max_occurrences": MAX_OCCURRENCES, "max_replay_steps": MAX_REPLAY_STEPS,
    "max_cues": MAX_CUES, "max_completions": MAX_COMPLETIONS,
    "max_weight_updates": MAX_WEIGHT_UPDATES, "max_trace_cells": MAX_TRACE_CELLS,
    "max_text_bytes": MAX_TEXT_BYTES, "max_rational_bits": MAX_RATIONAL_BITS,
}
_EVENT_KEYS = {"chain", "seq", "entry_hash", "row", "projection", "retention"}
_PAGE_KEYS = {"slug", "text", "size", "sha256", "lineage_sha256", "type",
              "declared_origin", "origin", "role"}
_PROJECTION_KEYS = {"organ", "kind", "event_time_utc", "event_id", "semantic_id",
                    "summary", "links", "tags", "occurrence"}
_OCCURRENCE_KEYS = {"chain", "seq", "entry_hash"}
NON_CLAIMS = (
    "This scalar delta learner is an engineering abstraction, not Schapiro's phased neural network, literal CLS, sleep physiology or biological consolidation.",
    "computed-unverified describes this local software result; bounded rational representations do not grant JACKAL exact or formal-bounded assurance to the implementation.",
    "External pins bind caller-selected captured bytes; admission does not authenticate a source, rerun a keeper, or independently establish historical truth.",
    "The complete supplied capture is retained, not an export or completeness claim about the entire corpus or machine.",
    "Source origin labels remain controlling. Signed rows and repeated replay cannot promote model prose into evidence.",
    "Replay exposures affect completion accessibility, not distinct source support, confidence, or the truth of any recorded outcome.",
    "An absent learning target means not activated in that replay exposure, not logical negation or absence of a real-world event.",
    "Native intention and outcome records are separate propositions; no incident pairing, causal recovery, universal success or unrestricted semantic entailment is inferred.",
    "Every focused candidate carries its complete same-cue alternatives and qualifiers, including alternatives that were not replayed or selected.",
    "Missing or unsupported live-marker witnesses keep their source rows and make the affected cue ineligible; no lineage-only text-support claim is made.",
    "Resource admission uses conservative whole-output and arithmetic reservations and refuses rather than truncating source, alternative or replay rosters.",
    "No target answers or held-out queries enter learning or readout, and no recall improvement, latency benefit, generalization or interleaving advantage is established.",
    "The immutable result is a publication candidate only: no durable publication, corpus mutation, episode deletion, model invocation or resident integration occurs.",
)


class GistRefusal(ValueError):
    """A complete witnessed replay artifact cannot be admitted or represented."""

    def __init__(self, reason):
        self.reason = reason
        self.non_claims = NON_CLAIMS
        super().__init__("replay-gist refused: " + reason)


def _refuse(reason):
    raise GistRefusal(reason)


def _keys(value, expected, label):
    if type(value) is not dict or len(value) != len(expected) \
            or any(type(key) is not str for key in value) or set(value) != set(expected):
        _refuse(label + "-shape")


def _integer(value, lower, upper):
    return type(value) is int and lower <= value <= upper


def _digest(value):
    return type(value) is str and len(value) == 64 and _HEX.fullmatch(value) is not None


def _text_bytes(value, maximum, *, quoted=False):
    if type(value) is not str or len(value) > maximum:
        _refuse("text-byte-capacity")
    size = len('""') if quoted else 0
    for character in value:
        point = ord(character)
        if 0xD800 <= point <= 0xDFFF:
            _refuse("text-unpaired-surrogate")
        if quoted and character in '"\\\b\f\n\r\t':
            size += 2
        elif quoted and point < 0x20:
            size += 6
        elif point <= 0x7F:
            size += 1
        elif point <= 0x7FF:
            size += 2
        elif point <= 0xFFFF:
            size += 3
        else:
            size += 4
        if size > maximum:
            _refuse("text-byte-capacity")
    if size > maximum:
        _refuse("text-byte-capacity")
    return size


def _json_size(value, maximum, *, text_limit=None):
    """Count strict JSON bytes before encoding/copying, rejecting exotic values."""
    used = 0
    active = set()
    text_limit = maximum if text_limit is None else text_limit

    def visit(item, depth):
        nonlocal used
        if depth > 64:
            _refuse("input-depth-capacity")
        kind = type(item)
        if kind is str:
            _text_bytes(item, text_limit)
            used += _text_bytes(item, maximum, quoted=True)
        elif kind is int:
            if not -MAX_SAFE_INTEGER <= item <= MAX_SAFE_INTEGER:
                _refuse("integer-representation-capacity")
            used += len(str(item))
        elif kind is bool:
            used += len("true" if item else "false")
        elif item is None:
            used += len("null")
        elif kind in (dict, list):
            if id(item) in active or len(item) > maximum:
                _refuse("input-container-capacity")
            used += len("{}" if kind is dict else "[]") + max(len(item) - 1, 0)
            if kind is dict:
                used += len(item)
            if used > maximum:
                _refuse("input-byte-capacity")
            active.add(id(item))
            try:
                if kind is dict:
                    for key, child in item.items():
                        if type(key) is not str:
                            _refuse("input-key-type")
                        visit(key, depth + 1)
                        visit(child, depth + 1)
                else:
                    for child in item:
                        visit(child, depth + 1)
            finally:
                active.remove(id(item))
        else:
            _refuse("input-value-type")
        if used > maximum:
            _refuse("input-byte-capacity")

    visit(value, 0)
    return used


def _rational_parameter(value):
    _keys(value, {"numerator", "denominator"}, "policy-rational")
    numerator, denominator = value["numerator"], value["denominator"]
    if not _integer(numerator, 1, MAX_SAFE_INTEGER) \
            or not _integer(denominator, 1, MAX_SAFE_INTEGER) \
            or numerator > denominator or math.gcd(numerator, denominator) != 1:
        _refuse("policy-rational-domain-or-canonicality")


def _policy(policy):
    _keys(policy, _POLICY_KEYS, "policy")
    _keys(policy["learning"], _LEARNING_KEYS, "learning-policy")
    _keys(policy["readout"], _READOUT_KEYS, "readout-policy")
    _keys(policy["fidelity"], _FIDELITY, "fidelity-policy")
    _keys(policy["limits"], _LIMITS, "limit-policy")
    required = ((policy, "schema", "sia-replay-gist-policy-v1"),
                (policy, "grammar", "native-attest-intent-outcome-v1"),
                (policy["learning"], "algorithm", "witnessed-completion-delta-v1"),
                (policy["learning"], "initial", "zero-v1"),
                (policy["readout"], "cue_roster", "complete-derived-native-cues-v1"),
                (policy["readout"], "tie_break", "first-source-occurrence-v1"),
                (policy["readout"], "static_control", "first-source-occurrence-v1"))
    for owner, key, value in required:
        if type(owner[key]) is not str or owner[key] != value:
            _refuse("policy-contract")
    for key, value in _FIDELITY.items():
        if type(policy["fidelity"][key]) is not str or policy["fidelity"][key] != value:
            _refuse("fidelity-contract")
    if type(policy["learning"]["enabled"]) is not bool:
        _refuse("learning-enabled-type")
    _rational_parameter(policy["learning"]["rate"])
    _rational_parameter(policy["readout"]["threshold"])
    for key, maximum in _LIMITS.items():
        if not _integer(policy["limits"][key], 1, maximum):
            _refuse("policy-limit-capacity")
    if not _integer(policy["readout"]["slots_per_cue"], 1, policy["limits"]["max_completions"]):
        _refuse("policy-slots-capacity")


def _occurrence_key(value):
    _keys(value, _OCCURRENCE_KEYS, "occurrence")
    if type(value["chain"]) is not str or not value["chain"] \
            or type(value["seq"]) is not str or not value["seq"] \
            or not _digest(value["entry_hash"]):
        _refuse("occurrence-identity")
    return value["chain"], value["seq"], value["entry_hash"]


def _reference(event):
    return {key: event[key] for key in ("chain", "seq", "entry_hash")}


def _native_relation(event):
    if event["chain"] not in _NATIVE_CHAINS:
        return None, "unsupported-native-chain"
    stage, separator, operation = event["row"][2].partition(":")
    if stage not in {"INTENT", "OUTCOME"} or not separator or not operation:
        return None, "unsupported-action-stage"
    return (event["chain"], operation, event["row"][3]), None


def _source_shape(capture, policy):
    """Reuse capture schemas; provisionally inventory without trusting hashes."""
    _keys(capture, history._BODY_KEYS | {"capture_sha256"}, "capture")
    limits = policy["limits"]
    if type(capture["events"]) is not list or not 0 < len(capture["events"]) <= limits["max_occurrences"] \
            or type(capture["pages"]) is not list or len(capture["pages"]) > limits["max_occurrences"] \
            or type(capture["chains"]) is not list or not capture["chains"]:
        _refuse("source-roster-capacity")
    pages = {}
    for page in capture["pages"]:
        _keys(page, _PAGE_KEYS, "page")
        if type(page["slug"]) is not str or page["slug"] in pages \
                or type(page["text"]) is not str or not _digest(page["sha256"]) \
                or type(page["origin"]) is not str or page["origin"] not in _ORIGINS:
            _refuse("source-page-shape")
        pages[page["slug"]] = page
    chain_order = []
    for chain in capture["chains"]:
        _keys(chain, history._CHAIN_KEYS, "chain")
        if type(chain["chain"]) is not str or chain["chain"] in chain_order:
            _refuse("source-chain-roster")
        chain_order.append(chain["chain"])
    events, sequence_keys, groups = {}, set(), {}
    ordered = {name: [] for name in chain_order}
    for event in capture["events"]:
        _keys(event, _EVENT_KEYS, "event")
        key = _occurrence_key(_reference(event))
        if key in events or key[:2] in sequence_keys or event["chain"] not in ordered \
                or type(event["row"]) is not list or len(event["row"]) != 9 \
                or any(type(item) is not str for item in event["row"]) \
                or event["seq"] != event["row"][0]:
            _refuse("source-occurrence-roster")
        _keys(event["retention"], history._RETENTION_KEYS, "retention")
        if event["projection"] is not None:
            _keys(event["projection"], _PROJECTION_KEYS, "projection")
        retention = event["retention"]
        if type(retention["status"]) is not str \
                or retention["source_slug"] is not None and type(retention["source_slug"]) is not str \
                or retention["retrieval_excerpt"] is not None and type(retention["retrieval_excerpt"]) is not str:
            _refuse("source-retention-shape")
        events[key] = event
        sequence_keys.add(key[:2])
        ordered[event["chain"]].append(event)
    # Native canonical admission below enforces sequence order within each
    # chain. Chain roster order, rather than a target or replay order, governs
    # the deterministic first-source control.
    for name in chain_order:
        for event in ordered[name]:
            cue, _reason = _native_relation(event)
            if cue is None:
                continue
            page = pages.get(event["retention"]["source_slug"])
            origin = None if page is None else page["origin"]
            completion = (event["row"][2].partition(":")[0], event["row"][4], origin)
            group = groups.setdefault(cue, {})
            group.setdefault(completion, []).append(event)
    if len(groups) > limits["max_cues"] \
            or sum(len(group) for group in groups.values()) > limits["max_completions"]:
        _refuse("cue-or-completion-capacity")
    return events, pages, groups


def _replay_shape(replay, events, policy):
    _keys(replay, {"schema", "steps"}, "replay")
    if type(replay["schema"]) is not str or replay["schema"] != "sia-gist-replay-v1" \
            or type(replay["steps"]) is not list \
            or len(replay["steps"]) > policy["limits"]["max_replay_steps"]:
        _refuse("replay-contract-or-capacity")
    seen, exposures = set(), {}
    for step in replay["steps"]:
        _keys(step, {"id", "occurrence"}, "replay-step")
        identifier = step["id"]
        if type(identifier) is not str or not 0 < len(identifier) <= MAX_TOKEN_BYTES \
                or _TOKEN.fullmatch(identifier) is None or identifier in seen:
            _refuse("replay-step-identity")
        seen.add(identifier)
        key = _occurrence_key(step["occurrence"])
        if key not in events:
            _refuse("replay-occurrence-not-in-complete-store")
        cue, reason = _native_relation(events[key])
        if reason is not None:
            _refuse("replay-unsupported-occurrence")
        exposures[cue] = exposures.get(cue, 0) + 1
    return exposures


def _reservations(capture, replay, policy, input_size, events, pages, groups, exposures):
    limits = policy["limits"]
    completions = sum(len(group) for group in groups.values())
    updates = sum(len(groups[cue]) * count for cue, count in exposures.items())
    cells = 2 * completions + 2 * updates
    if updates > limits["max_weight_updates"] or cells > limits["max_trace_cells"]:
        _refuse("replay-work-or-trace-capacity")
    rate = policy["learning"]["rate"]
    threshold = policy["readout"]["threshold"]
    parameter_bits = max(rate["denominator"].bit_length(), threshold["denominator"].bit_length())
    largest_exposure = max(exposures.values(), default=0)
    # Starting from zero with a rational rate, unreduced denominators can be
    # bounded by repeated products of its denominator. Reserve extra product
    # and addition space for intermediate operations and readout comparison.
    rational_bits = 2 * (largest_exposure + 1) * parameter_bits + 4
    if rational_bits > limits["max_rational_bits"]:
        _refuse("rational-bit-capacity")
    records = len(events) + len(groups) + completions + len(replay["steps"]) + updates + cells
    reserved = input_size + (records + 1) * _METADATA_RECORD_BYTES + cells * (2 * rational_bits)
    # Retained unsupported chains can have variable-size labels. Reserve each
    # actual occurrence reference, rather than counting its text as fixed
    # metadata; supported occurrences can also carry a witness reference.
    for event in events.values():
        reference_size = _json_size(_reference(event), MAX_INPUT_BYTES)
        reserved += reference_size
        if _native_relation(event)[0] is not None:
            reserved += reference_size
    for step in replay["steps"]:
        reserved += _json_size(step["occurrence"], MAX_INPUT_BYTES)
    # Every focused candidate embeds the SAME full alternative bundle twice:
    # once as its immutable JSON witness and once inside its meaning text.
    # Reserve worst-case JSON re-escaping without creating either string.
    for cue, group in groups.items():
        source_text = _json_size(list(cue), MAX_INPUT_BYTES)
        bundle_size = _METADATA_RECORD_BYTES + source_text
        for completion, occurrences in group.items():
            bundle_size += _METADATA_RECORD_BYTES + _json_size(list(completion), MAX_INPUT_BYTES)
            for event in occurrences:
                retention = event["retention"]
                excerpt = retention["retrieval_excerpt"]
                page = pages.get(retention["source_slug"])
                witness_text = {"excerpt": excerpt, "page_slug": None if page is None else page["slug"]}
                size = _json_size(witness_text, MAX_INPUT_BYTES)
                reference_size = _json_size(_reference(event), MAX_INPUT_BYTES)
                # The alternative occurrence roster and its witness each
                # retain the complete reference before outer JSON escaping.
                bundle_size += _METADATA_RECORD_BYTES + size + 2 * reference_size
                reserved += size
        for completion in group:
            focus_text = source_text + _json_size(list(completion), MAX_INPUT_BYTES)
            reserved += 4 * bundle_size + 4 * focus_text + _METADATA_RECORD_BYTES
        if reserved > limits["max_output_bytes"]:
            _refuse("output-byte-capacity")
    if reserved > limits["max_output_bytes"]:
        _refuse("output-byte-capacity")
    return reserved


def _preflight_with_reservation(capture, expected_capture, replay, expected_replay, policy, expected_policy):
    _policy(policy)
    if any(not _digest(value) for value in (expected_capture, expected_replay, expected_policy)):
        _refuse("external-pins-required")
    bundle = {"capture": capture, "expected_capture_sha256": expected_capture,
              "replay": replay, "expected_replay_sha256": expected_replay,
              "policy": policy, "expected_policy_sha256": expected_policy}
    input_size = _json_size(bundle, policy["limits"]["max_input_bytes"],
                            text_limit=policy["limits"]["max_text_bytes"])
    events, pages, groups = _source_shape(capture, policy)
    exposures = _replay_shape(replay, events, policy)
    reserved = _reservations(capture, replay, policy, input_size, events, pages, groups, exposures)
    return events, pages, groups, reserved


def _preflight(capture, expected_capture, replay, expected_replay, policy, expected_policy):
    events, pages, groups, _reserved = _preflight_with_reservation(
        capture, expected_capture, replay, expected_replay, policy, expected_policy)
    return events, pages, groups


def _encode(value, maximum=MAX_OUTPUT_BYTES):
    size = _json_size(value, maximum)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) != size or len(raw) > maximum:
        _refuse("canonical-representation-capacity")
    return raw


def _sha(value):
    return hashlib.sha256(_encode(value)).hexdigest()


def _admit_pins(capture, expected_capture, replay, expected_replay, policy, expected_policy):
    if capture["capture_sha256"] != expected_capture or _sha(replay) != expected_replay \
            or _sha(policy) != expected_policy:
        _refuse("external-pin-mismatch")
    # Existing pure canonical validators check complete native rows, ledger
    # population/head, projection, page origins and captured source hashes.
    # No keeper, file, clock or resident state is consulted here.
    history._admit(capture)


def _identity(domain, *parts):
    return _sha([domain, *parts])


def _marker_inventory(page, policy):
    raw = page["text"].encode("utf-8")
    markers, start, count = {}, 0, 0
    while start < len(raw):
        ending = raw.find(b"\n", start)
        end = len(raw) if ending < 0 else ending
        line = raw[start:end]
        match = _MARKER.search(line)
        if match is not None:
            count += 1
            if count > policy["limits"]["max_occurrences"]:
                _refuse("source-marker-capacity")
            identifier = match.group(1).decode("ascii")
            record = (start, end, line, match.group(2).decode("ascii"))
            # Duplicate markers remain ambiguous, not an arbitrary first hit.
            markers[identifier] = None if identifier in markers else record
        start = len(raw) if ending < 0 else ending + 1
    return markers


def _witness(event, pages, inventories, policy):
    retention, projection = event["retention"], event["projection"]
    if retention["status"] != "retained" or retention["witness_kind"] != "live-event-marker" \
            or retention["projected_event_retained"] is not True \
            or retention["value_answer_retained"] is not True or projection is None:
        return None
    page = pages.get(retention["source_slug"])
    if page is None:
        return None
    if page["slug"] not in inventories:
        inventories[page["slug"]] = _marker_inventory(page, policy)
    marker = inventories[page["slug"]].get(projection["event_id"])
    if marker is None:
        return None
    source_event = history.sialib.signed_ledger_event_projection(event["chain"], event["row"])
    if source_event is None:
        return None
    expected_line, _payload, _base = history.sialib._event_line(
        source_event, projection["event_id"], projection["semantic_id"])
    start, end, line, semantic_id = marker
    if line != expected_line.encode("utf-8") or expected_line != retention["retrieval_excerpt"] \
            or semantic_id != projection["semantic_id"]:
        return None
    return {"occurrence": _reference(event), "page_slug": page["slug"],
            "page_sha256": page["sha256"], "event_id": projection["event_id"],
            "semantic_id": semantic_id, "excerpt": expected_line,
            "excerpt_sha256": hashlib.sha256(line).hexdigest(), "start_byte": start, "end_byte": end}


def _completion_value(completion):
    stage, value, origin = completion
    return {"stage": stage, "value": value, "origin": origin}


def _literal(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _construct(capture, pages, groups, policy):
    cues, candidates, occurrences = [], [], []
    cue_index, occurrence_index, completion_index, inventories = {}, {}, {}, {}
    for cue_key, group in groups.items():
        chain, operation, subject = cue_key
        cue_id = _identity("sia-gist-cue-v1", chain, operation, subject)
        cue = {"id": cue_id, "chain": chain, "operation": operation, "subject": subject,
               "eligible": True, "reason": None, "completion_ids": []}
        alternatives = []
        for completion, source_events in group.items():
            focus = _completion_value(completion)
            completion_id = _identity("sia-gist-completion-v1", cue_id, focus)
            cue["completion_ids"].append(completion_id)
            completion_index[(cue_key, completion)] = completion_id
            witnesses, references = [], []
            for event in source_events:
                witness = _witness(event, pages, inventories, policy)
                if witness is None:
                    cue["eligible"], cue["reason"] = False, "incomplete-required-witness"
                else:
                    witnesses.append(witness)
                reference = _reference(event)
                references.append(reference)
                occurrence_index[_occurrence_key(reference)] = {
                    "occurrence": reference, "cue_id": cue_id, "completion_id": completion_id,
                    "origin": completion[2], "status": "supported" if witness is not None else "unavailable",
                    "reason": None if witness is not None else "incomplete-required-witness", "witness": witness}
            alternatives.append({"completion_id": completion_id, "completion": focus,
                                 "occurrences": references, "witnesses": witnesses})
        bundle = {"cue": {"chain": chain, "operation": operation, "subject": subject},
                  "alternatives": alternatives}
        raw_bundle = _encode(bundle, policy["limits"]["max_output_bytes"])
        bundle_json = raw_bundle.decode("utf-8")
        bundle_sha256 = hashlib.sha256(raw_bundle).hexdigest()
        for alternative in alternatives:
            focus = alternative["completion"]
            text = (
                f"Recorded focus: {focus['stage']} for operation {_literal(operation)} "
                f"on raw subject {_literal(subject)} in chain {_literal(chain)}; "
                f"exact value {_literal(focus['value'])}; source origin {_literal(focus['origin'])}.\n\n"
                "All recorded alternatives (not causal pairings; no universal-success claim):\n"
                + bundle_json + "\n")
            identifier = _identity("sia-gist-candidate-v1", capture["capture_sha256"],
                                   cue_id, alternative["completion_id"], bundle_sha256)
            candidates.append({"id": identifier, "cue_id": cue_id,
                               "completion_id": alternative["completion_id"], "focus": focus,
                               "text": text, "alternative_bundle_json": bundle_json,
                               "alternative_bundle_sha256": bundle_sha256})
        cues.append(cue)
        cue_index[cue_key] = cue
    for event in capture["events"]:
        key = _occurrence_key(_reference(event))
        row = occurrence_index.get(key)
        if row is None:
            _cue, reason = _native_relation(event)
            row = {"occurrence": _reference(event), "cue_id": None, "completion_id": None,
                   "origin": None, "status": "unsupported", "reason": reason, "witness": None}
        occurrences.append(row)
    return cues, candidates, occurrences, occurrence_index


def _fraction_value(value, bit_limit):
    if value < 0 or value > 1 or value.numerator.bit_length() > bit_limit \
            or value.denominator.bit_length() > bit_limit:
        _refuse("rational-state-domain-or-capacity")
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def _state(cues, weights, bit_limit):
    return [{"cue_id": cue["id"], "completion_id": completion_id,
             "weight": _fraction_value(weights[completion_id], bit_limit)}
            for cue in cues for completion_id in cue["completion_ids"]]


def _learn(cues, occurrence_index, replay, policy):
    bit_limit = policy["limits"]["max_rational_bits"]
    rate = Fraction(policy["learning"]["rate"]["numerator"], policy["learning"]["rate"]["denominator"])
    weights = {completion_id: Fraction(0) for cue in cues for completion_id in cue["completion_ids"]}
    initial = _state(cues, weights, bit_limit)
    cue_index = {cue["id"]: cue for cue in cues}
    trace = []
    for step in replay["steps"]:
        occurrence = occurrence_index[_occurrence_key(step["occurrence"])]
        cue = cue_index[occurrence["cue_id"]]
        target_id = occurrence["completion_id"]
        updates = []
        if cue["eligible"]:
            for completion_id in cue["completion_ids"]:
                before = weights[completion_id]
                target = 1 if completion_id == target_id else 0
                after = before + rate * (target - before) if policy["learning"]["enabled"] else before
                update = {"completion_id": completion_id, "target": target,
                          "before": _fraction_value(before, bit_limit),
                          "after": _fraction_value(after, bit_limit)}
                weights[completion_id] = after
                updates.append(update)
        trace.append({"step_id": step["id"], "occurrence": step["occurrence"], "cue_id": cue["id"],
                      "target_completion_id": target_id, "updates": updates,
                      "status": "replayed" if cue["eligible"] else "ineligible-cue",
                      "reason": None if cue["eligible"] else cue["reason"]})
    return initial, _state(cues, weights, bit_limit), trace, weights


def _readout(cues, candidates, weights, policy):
    threshold = Fraction(policy["readout"]["threshold"]["numerator"],
                         policy["readout"]["threshold"]["denominator"])
    slots = policy["readout"]["slots_per_cue"]
    by_completion = {candidate["completion_id"]: candidate for candidate in candidates}
    learned, static = [], []
    for cue in cues:
        roster = cue["completion_ids"]
        eligible = [identifier for identifier in roster if weights[identifier] >= threshold] if cue["eligible"] else []
        # Python's stable sort preserves the complete first-source order for
        # equal weights. There is no desired-completion or query input.
        ordered = sorted(eligible, key=lambda identifier: -weights[identifier])
        selected = [by_completion[identifier]["id"] for identifier in ordered[:slots]]
        static_selected = [by_completion[identifier]["id"] for identifier in roster[:slots]] if cue["eligible"] else []
        learned.append({"cue_id": cue["id"], "eligible": cue["eligible"], "selected": selected,
                        "reason": cue["reason"] if not cue["eligible"] else None if selected else "no-accessible-completion"})
        static.append({"cue_id": cue["id"], "eligible": cue["eligible"], "selected": static_selected,
                       "reason": cue["reason"]})
    return learned, static


def replay_gist(capture, *, expected_capture_sha256, replay, expected_replay_sha256,
                policy, expected_policy_sha256):
    """Return a complete immutable focused-gist artifact, or refuse atomically."""
    try:
        _preflight(capture, expected_capture_sha256, replay, expected_replay_sha256,
                   policy, expected_policy_sha256)
        _admit_pins(capture, expected_capture_sha256, replay, expected_replay_sha256,
                    policy, expected_policy_sha256)
        detached = copy.deepcopy({"capture": capture, "replay": replay, "policy": policy})
        capture, replay, policy = detached["capture"], detached["replay"], detached["policy"]
        _events, pages, groups = _preflight(
            capture, expected_capture_sha256, replay, expected_replay_sha256,
            policy, expected_policy_sha256)
        _admit_pins(capture, expected_capture_sha256, replay, expected_replay_sha256,
                    policy, expected_policy_sha256)
        cues, candidates, occurrences, occurrence_index = _construct(capture, pages, groups, policy)
        initial, final, trace, weights = _learn(cues, occurrence_index, replay, policy)
        readout, static = _readout(cues, candidates, weights, policy)
        body = {"schema": "sia-replay-gist-v1", "component": "replay-gist", "status": "computed-unverified",
                "capture": capture, "capture_sha256": expected_capture_sha256,
                "replay": replay, "replay_sha256": expected_replay_sha256,
                "policy": policy, "policy_sha256": expected_policy_sha256,
                "cues": cues, "candidates": candidates, "occurrences": occurrences,
                "initial_state": initial, "final_state": final, "replay_trace": trace,
                "readout": readout, "static_readout": static, "non_claims": list(NON_CLAIMS)}
        raw = _encode(body, policy["limits"]["max_output_bytes"])
        return {"artifact_json": raw.decode("utf-8"), "artifact_sha256": hashlib.sha256(raw).hexdigest()}
    except GistRefusal:
        raise
    except history.HistoryRefusal as exc:
        raise GistRefusal("captured-source-admission") from exc
    except (TypeError, ValueError, KeyError, OverflowError, RecursionError, UnicodeError, AttributeError) as exc:
        raise GistRefusal("input-admission-or-representation") from exc
