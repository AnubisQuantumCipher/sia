"""Pure, caller-pinned selection of private signed-history retrieval tasks.

This module does not open a corpus, run a keeper, prepare an index, or retrieve.
Whole pages are selected before answers, and exact chain/raw-subject groups are
assigned before query caps. A complete captured signed row population supplies
targets; an independently checked retained chunk supplies retrieval support.
These engineering tasks do not establish cognitive mechanisms or improvements.
"""

import copy
import hashlib
import json
import re

import siabench
import siacognitivehistory as history
import siavectoradmit as adapter
import siavectorprepare as preparer


SCHEMA = "sia-cognitive-selection-v1"
POLICY_SCHEMA = "sia-cognitive-selection-policy-v1"
MAX_POLICY_BYTES = history.sialib.MAX_EVENT_INDEX_BYTES
MAX_SELECTION_BYTES = history.MAX_CAPTURE_BYTES
CLASSES = ("recency-heavy", "repetition-heavy", "novelty",
           "associative-multi-hop", "consolidation-gist")
UNSUPPORTED = {
    "associative-multi-hop": "no-witnessed-multi-hop-targets",
    "consolidation-gist": "no-witnessed-gist-facts",
}
NON_CLAIMS = (
    "This is a grouped query-level split, not a temporal or source-page holdout.",
    "Shared source pages and signed-chain authentication anchors can occur across splits.",
    "Class names describe engineering tasks, not demonstrated cognitive mechanisms or wins.",
    "Novelty is first occurrence of an exact action and raw subject within a complete named signed chain, not machine-wide novelty.",
    "Latest recorded outcome follows signed sequence order, not necessarily event-time chronology.",
    "Unsupported associative and gist classes are not supplied by relabeling generic ledger QA.",
    "Excluded or unavailable witnesses remain declared; retained subsets do not establish complete-history answers.",
    "Selection hashes bind represented bytes; external capture and policy authentication remain caller obligations.",
    "No retrieval scores, tuned parameters, statistical power, or cognitive improvement are established.",
)
_DIGEST = re.compile(r"[a-f0-9]{64}")


class SelectionRefusal(ValueError):
    """A capture, policy, selection, or required coverage was not admitted."""


def _fail(reason):
    raise SelectionRefusal("cognitive selection refused: " + reason)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _bounded(value, maximum):
    """Reject exotic values, cycles and excessive structure before encoding."""
    used = 0
    active = set()

    def visit(item, depth):
        nonlocal used
        used += 1
        if depth > 64 or used > maximum:
            _fail("JSON structure exceeds its ceiling")
        kind = type(item)
        if kind is str:
            if len(item) > maximum - used:
                _fail("JSON text exceeds its ceiling")
            used += len(item.encode("utf-8", errors="strict"))
        elif kind is int:
            if not -adapter.MAX_SAFE_INTEGER <= item <= adapter.MAX_SAFE_INTEGER:
                _fail("JSON integer exceeds its exact range")
        elif kind is bool or item is None:
            pass
        elif kind in (dict, list):
            if len(item) > maximum - used or id(item) in active:
                _fail("JSON container is excessive or cyclic")
            active.add(id(item))
            try:
                if kind is dict:
                    for key, child in item.items():
                        if type(key) is not str:
                            _fail("JSON object key is not text")
                        visit(key, depth + 1)
                        visit(child, depth + 1)
                else:
                    for child in item:
                        visit(child, depth + 1)
            finally:
                active.remove(id(item))
        else:
            _fail("value is not canonical bounded JSON")
        if used > maximum:
            _fail("JSON structure exceeds its ceiling")

    visit(value, 0)


def _canonical(value, maximum=MAX_SELECTION_BYTES):
    _bounded(value, maximum)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) > maximum:
        _fail("serialized JSON exceeds its ceiling")
    return raw


def _keys(value, names, label):
    if type(value) is not dict or len(value) != len(names) or set(value) != set(names):
        _fail(label + " fields are invalid")


def _digest(value):
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _policy(value):
    _keys(value, {"schema", "seed", "split", "pages", "queries", "protocol",
                  "required_classes"}, "policy")
    if value["schema"] != POLICY_SCHEMA or not preparer._text(value["seed"], 1024):
        _fail("policy schema or seed is invalid")
    split = value["split"]
    _keys(split, {"kind", "group_key", "calibration_modulus", "calibration_residue"}, "split")
    if split["kind"] != "grouped-query-v1" or split["group_key"] != "chain-raw-subject-v1" \
            or not _integer(split["calibration_modulus"], 2, adapter.MAX_QUERIES) \
            or not _integer(split["calibration_residue"], 0, split["calibration_modulus"] - 1):
        _fail("grouped split policy is invalid")
    pages = value["pages"]
    _keys(pages, {"order", "title", "max_pages", "max_page_bytes",
                  "max_total_page_bytes", "max_chunks"}, "page policy")
    if pages["order"] != "seeded-slug-sha256-v1" or pages["title"] != "slug-v1":
        _fail("page ordering or title policy is invalid")
    for field, hard in (("max_pages", preparer.MAX_PAGES),
                        ("max_page_bytes", preparer.MAX_PAGE_BYTES),
                        ("max_total_page_bytes", preparer.MAX_TOTAL_PAGE_BYTES),
                        ("max_chunks", preparer.MAX_CHUNKS)):
        if not _integer(pages[field], 1, hard):
            _fail("page policy ceiling is invalid: " + field)
    queries = value["queries"]
    _keys(queries, {"templates", "max_groups_per_class", "max_queries"}, "query policy")
    if queries["templates"] != "signed-history-tasks-v1" \
            or any(not _integer(queries[key], 1, adapter.MAX_QUERIES)
                   for key in ("max_groups_per_class", "max_queries")):
        _fail("query policy is invalid")
    protocol = value["protocol"]
    _keys(protocol, {"chunking", "max_chunk_bytes", "page_pooling", "max_query_bytes"}, "protocol")
    if protocol["chunking"] != preparer.POLICY["chunking"] \
            or not _integer(protocol["max_chunk_bytes"], preparer.MAX_CHUNK_BYTES, preparer.MAX_CHUNK_BYTES) \
            or protocol["page_pooling"] != "single-chunk-per-slug" \
            or not _integer(protocol["max_query_bytes"], adapter.MAX_QUERY_BYTES, adapter.MAX_QUERY_BYTES):
        _fail("selection protocol disagrees with the frozen preparer or adapter")
    required = value["required_classes"]
    if type(required) is not list or len(required) > len(CLASSES) \
            or any(type(item) is not str or item not in CLASSES for item in required) \
            or len(set(required)) != len(required):
        _fail("required class roster is invalid")


def _inputs(capture, expected_capture_sha256, policy, expected_policy_sha256):
    _bounded(policy, MAX_POLICY_BYTES)
    _bounded(capture, history.MAX_CAPTURE_BYTES)
    if not _digest(expected_capture_sha256) or not _digest(expected_policy_sha256):
        _fail("external capture and policy pins are required")
    _policy(policy)
    if _sha(_canonical(policy, MAX_POLICY_BYTES)) != expected_policy_sha256:
        _fail("external policy pin mismatch")
    if type(capture) is not dict or capture.get("capture_sha256") != expected_capture_sha256:
        _fail("external capture pin mismatch")
    # This performs native-row, complete-population, page and witness checks.
    # It does not reopen any source or invoke a verifier.
    admitted = history.admit_capture(capture)
    return admitted, copy.deepcopy(policy)


def _identity(domain, *parts):
    return _sha(_canonical([domain, *parts]))


def _exclude(exclusions, *, kind, identifier, reason, klass=None, group=None):
    exclusions.append({"kind": kind, "id": identifier, "class": klass,
                       "group_id": group, "reason": reason})


def _preparer_envelope_bytes():
    """Reserve the maximum scalar envelope, without inventing a model binding.

    These placeholders are only JSON-size accounting. Published model/endpoint
    input ceilings are ASCII, and the actual caller must still admit its full
    embedding request. No placeholder is exported or used for model execution.
    """
    return len(_canonical({
        "v": 1, "operation": "prepare_index", "source": "sia",
        "dataset_sha256": "0" * 64, "pages_sha256": "0" * 64,
        "embedding": {"model": "x" * 256, "dimensions": 16000,
                      "endpoint": "x" * 256},
        "output": {"parent_fd": 1048576}, "pages": [],
    }))


def _pages(capture, policy, exclusions):
    limits = policy["pages"]
    ordered = sorted(capture["pages"], key=lambda page: (
        _identity("sia-cognitive-page-order-v1", policy["seed"], page["slug"]), page["slug"]))
    selected, chunks = [], {}
    byte_count = chunk_count = 0
    request_bytes = _preparer_envelope_bytes()
    for page in ordered:
        slug, text = page["slug"], page["text"]
        reason = None
        if not preparer._text(slug, 1024) or preparer._SLUG.fullmatch(slug) is None \
                or slug.startswith(preparer._EXCLUDES) \
                or not preparer._text(page["type"], 128) \
                or preparer._TYPE.fullmatch(page["type"]) is None \
                or not preparer._text(text, history.sialib.MAX_EVENT_PAGE_BYTES):
            reason = "page-preparer-contract"
        elif page["size"] > limits["max_page_bytes"]:
            reason = "page-byte-budget"
        elif len(selected) >= limits["max_pages"]:
            reason = "page-count-budget"
        elif byte_count + page["size"] > limits["max_total_page_bytes"]:
            reason = "page-aggregate-byte-budget"
        if reason is None:
            page_chunks = tuple(preparer._chunk_bytes(text))
            if chunk_count + len(page_chunks) > limits["max_chunks"]:
                reason = "page-chunk-budget"
        if reason is None:
            prepared_page = {"slug": slug, "title": slug, "type": page["type"],
                             "origin": page["origin"], "text": text,
                             "text_sha256": page["sha256"]}
            additional = len(_canonical(prepared_page)) + (len(b",") if selected else 0)
            if request_bytes + additional > preparer.MAX_REQUEST_BYTES:
                reason = "page-request-byte-budget"
        if reason is not None:
            _exclude(exclusions, kind="page", identifier=slug, reason=reason)
            continue
        selected.append(prepared_page)
        chunks[slug] = page_chunks
        byte_count += page["size"]
        chunk_count += len(page_chunks)
        request_bytes += additional
    if not selected:
        _fail("no whole page fits the frozen preparer policy")
    return selected, chunks


def _groups(capture, policy):
    populations = {}
    for event in capture["events"]:
        action, subject = event["row"][2:4]
        if action.startswith("GENESIS:") or action == "genesis":
            continue
        key = (event["chain"], subject)
        populations.setdefault(key, {}).setdefault(action, []).append(event)
    groups = []
    split = policy["split"]
    for chain, subject in sorted(populations):
        identifier = _identity("sia-cognitive-group-v1", chain, subject)
        residue = int(_identity("sia-cognitive-split-v1", policy["seed"], identifier), 16) \
            % split["calibration_modulus"]
        groups.append({"id": identifier, "chain": chain, "subject": subject,
                       "split": "calibration" if residue == split["calibration_residue"] else "heldout"})
        for events in populations[(chain, subject)].values():
            events.sort(key=lambda event: int(event["seq"]))
    return sorted(groups, key=lambda row: row["id"]), populations


def _support(events, chunks, *, value_required=False):
    result, per_page = [], {}
    for event in events:
        retention = event["retention"]
        if retention["status"] != "retained" or not retention["projected_event_retained"] \
                or value_required and not retention["value_answer_retained"]:
            return None, "required-witness-unavailable"
        slug, excerpt = retention["source_slug"], retention["retrieval_excerpt"]
        if slug not in chunks:
            return None, "required-page-not-selected"
        encoded = excerpt.encode("utf-8")
        options = {index for index, chunk in enumerate(chunks[slug]) if encoded in chunk}
        if not options:
            return None, "required-excerpt-crosses-chunk"
        if slug in per_page:
            per_page[slug] &= options
            if not per_page[slug]:
                return None, "page-pooling-witness-conflict"
        else:
            per_page[slug] = options
        if len(per_page) > adapter.MAX_RESULTS:
            return None, "required-pages-exceed-adapter-results"
        result.append({"chain": event["chain"], "seq": event["seq"],
                       "entry_hash": event["entry_hash"], "slug": slug, "excerpt": excerpt})
    # Multiple identical occurrences of an excerpt are not ambiguity: choose the
    # earliest chunk that simultaneously covers every required excerpt per page.
    for item in result:
        index = min(per_page[item["slug"]])
        item.update({"chunk_index": index, "chunk_sha256": _sha(chunks[item["slug"]][index])})
    return result, None


def _question(klass, chain, action, subject):
    action = json.dumps(action, ensure_ascii=False)
    subject = json.dumps(subject, ensure_ascii=False)
    clause = f"exact action {action} and raw subject {subject} in the complete signed {chain} chain"
    if klass == "recency-heavy":
        return (f"What was the latest recorded outcome value for {clause}? "
                "Use signed sequence order, not event-time chronology.")
    if klass == "repetition-heavy":
        return f"How many occurrences are recorded for {clause}?"
    return (f"At what recorded timestamp was the first occurrence of {clause}? "
            "Use signed sequence order; the scope is this chain, not the entire machine.")


def _candidates(capture, policy, groups, populations, chunks, exclusions):
    chains = {row["chain"]: row for row in capture["chains"]}
    candidates = []
    for group in groups:
        chain, subject = group["chain"], group["subject"]
        anchor = chains[chain]
        scope = {"kind": "complete-signed-chain", "chain": chain,
                 "head": anchor["head"], "ledger_sha256": anchor["ledger_sha256"]}
        for action, events in sorted(populations[(chain, subject)].items()):
            # All accepted occurrences are present here, including unprojected
            # and unretained rows. Neither targets nor counts use a retained subset.
            for klass in CLASSES:
                if klass in UNSUPPORTED:
                    continue
                if klass == "recency-heavy" and not action.startswith("OUTCOME:"):
                    continue
                question = _question(klass, chain, action, subject)
                identifier = siabench._question_id({"question": question})
                reason = None
                if not adapter._text(question, adapter.MAX_QUERY_BYTES):
                    reason = "query-text-contract"
                elif klass == "recency-heavy":
                    if len(events) < 2 or events[-1]["row"][4] == events[-2]["row"][4]:
                        reason = "no-competing-recorded-outcome"
                    else:
                        required = events[-2:]
                        answer = {"kind": "latest-recorded-outcome", "value": events[-1]["row"][4],
                                  "sequences": [events[-1]["seq"]]}
                elif klass == "repetition-heavy":
                    if len(events) < 2:
                        reason = "no-repeated-occurrence"
                    else:
                        required = events
                        answer = {"kind": "occurrence-count", "value": len(events),
                                  "sequences": [event["seq"] for event in events]}
                else:
                    required = events[:1]
                    answer = {"kind": "first-occurrence", "value": events[0]["row"][1],
                              "sequences": [events[0]["seq"]]}
                if reason is None:
                    support, reason = _support(required, chunks, value_required=klass == "recency-heavy")
                if reason is not None:
                    _exclude(exclusions, kind="query", identifier=identifier,
                             klass=klass, group=group["id"], reason=reason)
                    continue
                candidates.append({
                    "public": {"id": identifier, "text": question, "split": group["split"]},
                    "private": {"id": identifier, "class": klass, "group_id": group["id"],
                                "action": action, "answer": answer, "support": support, "scope": scope},
                })
    # Canonical-public-wording collisions never merge raw subject identities or
    # acquire an answer through dictionary overwrite. Exclude the entire collision.
    counts = {}
    for item in candidates:
        identifier = item["public"]["id"]
        counts[identifier] = counts.get(identifier, 0) + 1
    unique = []
    for item in candidates:
        row = item["private"]
        if counts[row["id"]] != 1:
            _exclude(exclusions, kind="query", identifier=row["id"], klass=row["class"],
                     group=row["group_id"], reason="public-wording-collision")
        else:
            unique.append(item)
    return unique


def _cap_queries(candidates, policy, exclusions):
    allowed = {}
    for klass in CLASSES:
        identifiers = {item["private"]["group_id"] for item in candidates
                       if item["private"]["class"] == klass}
        ordered = sorted(identifiers, key=lambda identifier: (
            _identity("sia-cognitive-class-group-order-v1", policy["seed"], klass, identifier), identifier))
        allowed[klass] = set(ordered[:policy["queries"]["max_groups_per_class"]])
    ordered = sorted(candidates, key=lambda item: (
        _identity("sia-cognitive-query-order-v1", policy["seed"], item["public"]["id"]),
        item["public"]["id"]))
    selected = []
    for item in ordered:
        row = item["private"]
        reason = None
        if row["group_id"] not in allowed[row["class"]]:
            reason = "class-group-budget"
        elif len(selected) >= policy["queries"]["max_queries"]:
            reason = "query-count-budget"
        if reason is not None:
            _exclude(exclusions, kind="query", identifier=row["id"], klass=row["class"],
                     group=row["group_id"], reason=reason)
        else:
            selected.append(item)
    return selected


def _select(capture, expected_capture_sha256, policy, expected_policy_sha256):
    capture, policy = _inputs(capture, expected_capture_sha256, policy, expected_policy_sha256)
    exclusions = []
    pages, chunks = _pages(capture, policy, exclusions)
    groups, populations = _groups(capture, policy)
    candidates = _candidates(capture, policy, groups, populations, chunks, exclusions)
    selected = _cap_queries(candidates, policy, exclusions)
    coverage = []
    for klass in CLASSES:
        rows = [item["private"] for item in selected if item["private"]["class"] == klass]
        reason = UNSUPPORTED.get(klass, None if rows else "no-feasible-selected-queries")
        coverage.append({"class": klass, "status": "unsupported" if klass in UNSUPPORTED
                         else "available" if rows else "empty", "reason": reason,
                         "selected_queries": len(rows),
                         "selected_groups": len({row["group_id"] for row in rows})})
        if klass in policy["required_classes"] and not rows:
            _fail("required class is unavailable: " + klass + " (" + reason + ")")
    body = {
        "schema": SCHEMA, "capture_sha256": expected_capture_sha256,
        "policy_sha256": expected_policy_sha256, "pages": pages,
        "pages_sha256": _sha(_canonical(pages)), "groups": groups,
        "queries": [item["public"] for item in selected],
        "answer_key": [item["private"] for item in selected],
        "coverage": coverage, "exclusions": sorted(exclusions, key=_canonical),
        "source_non_claims": {"capture": capture["non_claims"],
                              "generator": capture["source_non_claims"]},
        "non_claims": list(NON_CLAIMS),
    }
    result = {**body, "selection_sha256": _sha(_canonical(body))}
    _canonical(result)
    return result


def select_history(capture, *, expected_capture_sha256, policy, expected_policy_sha256):
    """Construct one bounded, detached selection from externally pinned inputs."""
    try:
        return _select(capture, expected_capture_sha256, policy, expected_policy_sha256)
    except SelectionRefusal:
        raise
    except (TypeError, ValueError, KeyError, AttributeError, RecursionError, UnicodeError, OverflowError) as exc:
        raise SelectionRefusal("cognitive selection input could not be admitted") from exc


def admit_selection(selection, *, capture, policy, expected_capture_sha256, expected_policy_sha256):
    """Replay source/policy selection; a self-consistent altered digest is insufficient."""
    try:
        _bounded(selection, MAX_SELECTION_BYTES)
        expected = _select(capture, expected_capture_sha256, policy, expected_policy_sha256)
        if _canonical(selection) != _canonical(expected):
            _fail("selection disagrees with deterministic source and policy replay")
        # Return the freshly reconstructed object, not any caller-owned container.
        return expected
    except SelectionRefusal:
        raise
    except (TypeError, ValueError, KeyError, AttributeError, RecursionError, UnicodeError, OverflowError) as exc:
        raise SelectionRefusal("cognitive selection could not be admitted") from exc
