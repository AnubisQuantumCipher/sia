"""Private captured history for later memory experiments, not an experiment.

Construction consumes the signed benchmark's already-admitted in-memory
snapshots and resolver cache. No corpus or resident-index path is opened.
Admission checks the captured representation and its internal byte bindings;
it does not rerun keepers or authenticate an externally supplied capture.
"""

import base64
import binascii
import copy
import datetime
import hashlib
import json
import re

import sialib
import siamind


SCHEMA = "sia-cognitive-history-capture-v1"
MAX_CAPTURE_BYTES = sialib.MAX_STATE_JSON_BYTES
NON_CLAIMS = (
    "This is the verified-ledger projection cache, not an export of the entire corpus.",
    "Inspected-only pages are retained bytes, not admitted answer witnesses.",
    "Not-projected means excluded or unavailable in this generator, not an absent event.",
    "Lineage-only retention does not establish that answer text remains in a page.",
    "Page origins remain controlling even when a signed event has a matching excerpt.",
    "Capture hashes bind represented bytes; admission does not rerun keepers or authenticate an external capture.",
    "No query classes, tuned parameters, or cognitive wins are established.",
)
_BODY_KEYS = {
    "schema", "dataset_id", "generator", "scope", "capacity_policy", "chains",
    "events", "pages", "witness_files", "diagnostics", "witness_coverage",
    "question_coverage", "generation_exclusions", "source_non_claims", "non_claims",
}
_RETENTION_KEYS = {
    "status", "witness_kind", "source_slug", "index_file", "retrieval_excerpt",
    "projected_event_retained", "value_answer_retained",
}
_CHAIN_KEYS = {
    "chain", "chain_format", "ledger_sha256", "head", "row_count", "verifier",
    "verifier_sha256", "launch_contract_sha256", "inputs", "ledger_final_lf",
}


class HistoryRefusal(ValueError):
    """The requested private history representation was not admitted."""


def _fail(reason):
    raise HistoryRefusal("cognitive history refused: " + reason)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _keys(value, keys, label):
    if type(value) is not dict or len(value) != len(keys) or set(value) != keys:
        _fail(label + " fields are invalid")


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _bounded_json(value):
    """Bound structure and text before serialization or a detached copy."""
    used = 0
    active = set()

    def visit(item, depth):
        nonlocal used
        used += 1
        if depth > 64 or used > MAX_CAPTURE_BYTES:
            _fail("capture structure exceeds its ceiling")
        kind = type(item)
        if kind is str:
            if len(item) > MAX_CAPTURE_BYTES - used:
                _fail("capture text exceeds its ceiling")
            used += len(item.encode("utf-8", errors="strict"))
        elif kind is int:
            if not -sialib.MAX_JSON_SAFE_INTEGER <= item <= sialib.MAX_JSON_SAFE_INTEGER:
                _fail("capture integer exceeds its exact JSON range")
        elif item is None or kind is bool:
            pass
        elif kind in (dict, list):
            if len(item) > MAX_CAPTURE_BYTES - used or id(item) in active:
                _fail("capture container is excessive or cyclic")
            active.add(id(item))
            try:
                if kind is dict:
                    for key, child in item.items():
                        if type(key) is not str:
                            _fail("capture object key is not text")
                        visit(key, depth + 1)
                        visit(child, depth + 1)
                else:
                    for child in item:
                        visit(child, depth + 1)
            finally:
                active.remove(id(item))
        else:
            _fail("capture contains a noncanonical JSON value")
        if used > MAX_CAPTURE_BYTES:
            _fail("capture structure exceeds its ceiling")

    visit(value, 0)


def _canonical(value):
    _bounded_json(value)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) > MAX_CAPTURE_BYTES:
        _fail("serialized capture exceeds its byte ceiling")
    return raw


def _relative(value):
    return type(value) is str and bool(value) and not value.startswith("/") \
        and "\x00" not in value and "\\" not in value \
        and all(part not in ("", ".", "..") for part in value.split("/"))


def _origin(slug, text):
    """Apply the existing origin grammar to captured bytes, never a reread."""
    ptype = declared = None
    valid = False
    try:
        # Match corpus_origin's bounded frontmatter view, including its
        # conservative treatment of a UTF-8 character cut by that view.
        prefix = text.encode("utf-8")[:sialib.MAX_THOUGHT_INBOX_BYTES].decode("utf-8")
        match = sialib.FM_RE.match(prefix)
        if match is not None:
            frontmatter = match.group(1)
            types = re.findall(r"^type:\s*(.*?)\s*$", frontmatter, re.M)
            origins = re.findall(r"^origin:\s*(.*?)\s*$", frontmatter, re.M)
            if len(types) == 1:
                ptype = sialib._yaml_scalar(types[0])
                declared = (None if not origins else sialib._yaml_scalar(origins[0])
                            if len(origins) == 1 else "invalid-duplicate-origin")
                valid = True
    except (UnicodeError, ValueError, TypeError):
        pass
    if slug.startswith(("events/jackal/", "epochs/jackal/")):
        origin = "derived"
    else:
        origin = siamind.origin_class(slug, ptype, declared) if valid else "legacy-unlabeled"
    return {"type": ptype, "declared_origin": declared, "origin": origin}


def _projection(event):
    return {
        "organ": event.organ, "kind": event.kind,
        "event_time_utc": event.ts.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event_id": sialib.event_memory_identity(event),
        "semantic_id": sialib.event_semantic_identity(event),
        "summary": event.summary, "links": sorted(event.links), "tags": sorted(event.tags),
        "occurrence": event.occurrence,
    }


def _limit(policy, key, hard):
    value = policy.get(key)
    if type(value) is not int or not 0 < value <= hard:
        _fail("capacity policy is invalid: " + key)
    return value


def build_capture(*, manifest, snapshots, projected, records, resolver, diagnostics):
    """Detach one capture from the benchmark's already-read generation."""
    try:
        candidates = {(item["chain"], item["row"][0]): item for item in projected}
        retained = {(item["chain"], item["row"][0]): item for item in records}
        chains, events = [], []
        answer_pages = {item["slug"] for item in records if item["projected_event_retained"]}
        for snapshot in snapshots:
            chain = {key: snapshot[key] for key in _CHAIN_KEYS - {"ledger_final_lf"}}
            text = "\n".join("\t".join(row) for row in snapshot["rows"])
            if _sha((text + "\n").encode("utf-8")) == snapshot["ledger_sha256"]:
                chain["ledger_final_lf"] = True
            elif _sha(text.encode("utf-8")) == snapshot["ledger_sha256"]:
                chain["ledger_final_lf"] = False
            else:
                _fail("accepted row bytes disagree with their ledger digest")
            chains.append(chain)
            for row, entry_hash in zip(snapshot["rows"], snapshot["entry_hashes"]):
                key = (snapshot["chain"], row[0])
                candidate, record = candidates.get(key), retained.get(key)
                retention = {
                    "status": "not-projected" if candidate is None else "no-admitted-witness",
                    "witness_kind": None, "source_slug": None, "index_file": None,
                    "retrieval_excerpt": None, "projected_event_retained": False,
                    "value_answer_retained": False,
                }
                if record is not None:
                    retention.update({
                        "status": "retained" if record["projected_event_retained"] else "lineage-only",
                        "witness_kind": record["witness_kind"], "source_slug": record["slug"],
                        "index_file": record["index_file"],
                        "retrieval_excerpt": record["retrieval_excerpt"],
                        "projected_event_retained": record["projected_event_retained"],
                        "value_answer_retained": record["value_answer_retained"],
                    })
                events.append({"chain": snapshot["chain"], "seq": row[0],
                               "entry_hash": entry_hash, "row": row,
                               "projection": None if candidate is None else _projection(candidate["event"]),
                               "retention": retention})
        pages = [{
            **{key: page[key] for key in ("slug", "text", "size", "sha256", "lineage_sha256")},
            **_origin(page["slug"], page["text"]),
            "role": "answer-witness" if page["slug"] in answer_pages else "inspected-only",
        } for _relative_path, page in sorted(resolver.page_cache.items())]
        witnesses = [{
            **{key: item[key] for key in ("path", "kind", "size", "sha256")},
            "content_base64": base64.b64encode(item["raw"]).decode("ascii"),
        } for _path, item in sorted(resolver.witness_files.items())]
        body = {
            "schema": SCHEMA, "dataset_id": manifest["dataset_id"],
            "generator": {"schema": manifest["schema"], "version": manifest["generator_version"]},
            "scope": {"kind": "verified-ledger-projection-cache", "entire_corpus": False},
            "capacity_policy": manifest["capacity_policy"], "chains": chains, "events": events,
            "pages": pages, "witness_files": witnesses, "diagnostics": diagnostics,
            "witness_coverage": manifest["witness_coverage"],
            "question_coverage": manifest["question_coverage"],
            "generation_exclusions": manifest["generation_exclusions"],
            "source_non_claims": manifest["non_claims"], "non_claims": list(NON_CLAIMS),
        }
        return admit_capture({**body, "capture_sha256": _sha(_canonical(body))})
    except HistoryRefusal:
        raise
    except (KeyError, AttributeError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise HistoryRefusal("cognitive history capture could not be constructed") from exc


def _admit(value):
    _keys(value, _BODY_KEYS | {"capture_sha256"}, "capture")
    _bounded_json(value)
    if value["schema"] != SCHEMA or not _digest(value["dataset_id"]):
        _fail("capture identity is invalid")
    if value["non_claims"] != list(NON_CLAIMS):
        _fail("capture non-claims changed")
    _keys(value["scope"], {"kind", "entire_corpus"}, "scope")
    if value["scope"]["kind"] != "verified-ledger-projection-cache" \
            or value["scope"]["entire_corpus"] is not False:
        _fail("capture scope is invalid")
    _keys(value["generator"], {"schema", "version"}, "generator")
    if any(type(item) is not str or not item for item in value["generator"].values()):
        _fail("generator identity is invalid")
    policy = value["capacity_policy"]
    if type(policy) is not dict:
        _fail("capacity policy is invalid")
    row_limit = _limit(policy, "ledger_rows_aggregate", sialib.MAX_SOURCE_REPLAY_EVENTS)
    page_limit = _limit(policy, "source_pages", sialib.MAX_EVENT_LOOKUP_PAGES)
    page_bytes = _limit(policy, "source_page_bytes", sialib.MAX_EVENT_PAGE_BYTES)
    source_bytes = _limit(policy, "source_page_aggregate_bytes", sialib.MAX_STATE_JSON_BYTES)
    ledger_bytes = _limit(policy, "ledger_bytes_per_chain", sialib.MAX_STATE_JSON_BYTES)
    for name, maximum in (("chains", row_limit), ("events", row_limit),
                          ("pages", page_limit), ("witness_files", row_limit),
                          ("diagnostics", row_limit), ("witness_coverage", row_limit),
                          ("question_coverage", row_limit), ("source_non_claims", row_limit)):
        if type(value[name]) is not list or len(value[name]) > maximum:
            _fail(name + " population is invalid")
    if not value["chains"] or not value["events"] or not value["pages"] \
            or not value["source_non_claims"] \
            or any(type(item) is not str or not item for item in value["source_non_claims"]):
        _fail("capture has incomplete provenance")
    if any(type(item) is not dict or item.get("status") == "refused" for item in value["diagnostics"]):
        _fail("capture contains refused intake")
    pages, total = {}, 0
    for page in value["pages"]:
        _keys(page, {"slug", "text", "size", "sha256", "lineage_sha256", "type",
                     "declared_origin", "origin", "role"}, "page")
        slug = page["slug"]
        if not _relative(slug) or slug in pages or type(page["text"]) is not str:
            _fail("page identity is invalid")
        raw = page["text"].encode("utf-8")
        if len(raw) > page_bytes or type(page["size"]) is not int or page["size"] != len(raw) \
                or page["sha256"] != _sha(raw) \
                or page["lineage_sha256"] != _sha((slug + ".md").encode() + b"\0" + raw):
            _fail("page byte identity is invalid")
        if any(page[key] != item for key, item in _origin(slug, page["text"]).items()):
            _fail("page origin disagrees with captured bytes")
        if page["role"] not in ("answer-witness", "inspected-only"):
            _fail("page role is invalid")
        total += len(raw)
        pages[slug] = page
    witnesses = {}
    for item in value["witness_files"]:
        _keys(item, {"path", "kind", "size", "sha256", "content_base64"}, "witness")
        if not _relative(item["path"]) or item["path"] in witnesses \
                or item["kind"] != "event-index" or type(item["content_base64"]) is not str:
            _fail("witness identity is invalid")
        raw = base64.b64decode(item["content_base64"], validate=True)
        if len(raw) > sialib.MAX_EVENT_INDEX_BYTES \
                or base64.b64encode(raw).decode("ascii") != item["content_base64"] \
                or type(item["size"]) is not int or item["size"] != len(raw) \
                or item["sha256"] != _sha(raw):
            _fail("witness byte identity is invalid")
        total += len(raw)
        witnesses[item["path"]] = item
    if total > source_bytes:
        _fail("captured sources exceed their aggregate ceiling")
    chains = {}
    for chain in value["chains"]:
        _keys(chain, _CHAIN_KEYS, "chain")
        name = chain["chain"]
        if type(name) is not str or not name or name in chains \
                or type(chain["row_count"]) is not int or not 0 < chain["row_count"] <= row_limit \
                or type(chain["ledger_final_lf"]) is not bool \
                or any(not _digest(chain[key]) for key in (
                    "ledger_sha256", "head", "verifier_sha256", "launch_contract_sha256")):
            _fail("chain provenance is invalid")
        chains[name] = chain
    grouped = {name: [] for name in chains}
    answered = set()
    for event in value["events"]:
        _keys(event, {"chain", "seq", "entry_hash", "row", "projection", "retention"}, "event")
        if type(event["chain"]) is not str or event["chain"] not in chains \
                or type(event["row"]) is not list or len(event["row"]) != 9 \
                or any(type(field) is not str for field in event["row"]) \
                or event["seq"] != event["row"][0] or not _digest(event["entry_hash"]):
            _fail("event row identity is invalid")
        grouped[event["chain"]].append(event)
        projection, retention = event["projection"], event["retention"]
        _keys(retention, _RETENTION_KEYS, "retention")
        if any(type(retention[key]) is not bool for key in (
                "projected_event_retained", "value_answer_retained")):
            _fail("retention flags are invalid")
        if projection is not None:
            expected = sialib.signed_ledger_event_projection(event["chain"], event["row"])
            if expected is None or projection != _projection(expected):
                _fail("projected event disagrees with signed row")
        if retention["status"] in ("not-projected", "no-admitted-witness"):
            if (projection is None) != (retention["status"] == "not-projected") \
                    or any(retention[key] is not None for key in (
                        "witness_kind", "source_slug", "index_file", "retrieval_excerpt")) \
                    or retention["projected_event_retained"] or retention["value_answer_retained"]:
                _fail("unwitnessed event claims retention")
            continue
        if projection is None or retention["status"] not in ("retained", "lineage-only") \
                or type(retention["source_slug"]) is not str or retention["source_slug"] not in pages \
                or retention["witness_kind"] not in ("live-event-marker", "epoch-lineage"):
            _fail("retention witness is invalid")
        if retention["witness_kind"] == "epoch-lineage":
            index = retention["index_file"]
            _keys(index, {"path", "kind", "size", "sha256"}, "event index")
            witness = witnesses.get(index["path"])
            if witness is None or index != {key: witness[key] for key in index}:
                _fail("retention index is not captured")
        elif retention["index_file"] is not None:
            _fail("live marker has an unexpected index witness")
        if retention["status"] == "retained":
            excerpt = retention["retrieval_excerpt"]
            if retention["projected_event_retained"] is not True \
                    or type(excerpt) is not str or not excerpt \
                    or excerpt not in pages[retention["source_slug"]]["text"].split("\n"):
                _fail("retained excerpt is not in the captured page")
            answered.add(retention["source_slug"])
        elif retention["projected_event_retained"] or retention["value_answer_retained"] \
                or retention["retrieval_excerpt"] is not None \
                or retention["witness_kind"] != "epoch-lineage":
            _fail("lineage-only retention overclaims text")
    # Reuse the native ledger grammar; this is internal consistency checking,
    # not a second keeper invocation or an authenticity claim.
    import siabench
    for name, chain in chains.items():
        events = grouped[name]
        text = "\n".join("\t".join(event["row"]) for event in events)
        if chain["ledger_final_lf"]:
            text += "\n"
        raw = text.encode("utf-8")
        if len(events) != chain["row_count"] or len(raw) > ledger_bytes \
                or _sha(raw) != chain["ledger_sha256"]:
            _fail("complete signed row population disagrees with its ledger")
        if chain["chain_format"] == siabench.CUSTOS_CHAIN_FORMAT and name == "custos":
            rows, head, hashes = siabench._strict_custos_rows(text)
        elif chain["chain_format"] == siabench.ATTEST_CHAIN_FORMAT and name != "custos":
            rows, head = siabench._strict_attest_rows(text)
            hashes = [siabench._entry_hash(row) for row in rows]
        else:
            _fail("chain format disagrees with native registry identity")
        if head != chain["head"] or hashes != [event["entry_hash"] for event in events]:
            _fail("native row hashes disagree with their chain head")
    if any(page["role"] != ("answer-witness" if slug in answered else "inspected-only")
           for slug, page in pages.items()):
        _fail("page witness role disagrees with retained events")
    body = {key: value[key] for key in _BODY_KEYS}
    if not _digest(value["capture_sha256"]) or value["capture_sha256"] != _sha(_canonical(body)):
        _fail("capture digest mismatch")
    _canonical(value)


def admit_capture(value):
    """Validate internal capture bindings and return a detached JSON value."""
    try:
        _admit(value)
        return copy.deepcopy(value)
    except HistoryRefusal:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError,
            AttributeError, binascii.Error) as exc:
        raise HistoryRefusal("cognitive history capture is malformed") from exc
