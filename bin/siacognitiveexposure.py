"""Pure, target-blind retained-event-exposure overlays on admitted raw rows.

Event timestamps here are a source-bound engineering proxy, not actual memory
encoding or retrieval-use times. The existing activation component supplies
only computed-unverified local scores. This module neither evaluates metrics
nor chooses a parameter, measures a new duration, opens evidence, or runs an
engine. Raw adapter observations are retained verbatim; overlays are bijective
row-reference permutations and never masquerade as new raw engine output.
"""

import calendar
import copy
import datetime
import json
import math
import re

import siaactivation as activation
import siacognitivemeasure as measurement


MAX_INPUT_BYTES = measurement.MAX_ARTIFACT_BYTES
MAX_OUTPUT_BYTES = measurement.MAX_ARTIFACT_BYTES
MAX_TRACE_BYTES = activation.MAX_INPUT_BYTES
MAX_QUERIES = measurement.baseline_module.raw_admission.MAX_QUERIES
MAX_GRID_POLICIES = MAX_QUERIES
MAX_SOURCE_EVENTS = measurement.baseline_module.sialib.MAX_SOURCE_REPLAY_EVENTS
MAX_QUERY_BYTES = measurement.baseline_module.raw_admission.MAX_QUERY_BYTES
ARMS = ("raw-original", "cue-only", "cue-event-exposure")
NON_CLAIMS = [
    "computed-unverified is local software computation, not a JACKAL assurance class or a cognitive win.",
    "Signed event times are retained-event-exposure proxies, not measured SIA encoding, presentation, retrieval-attempt, or successful-use times.",
    "The event-exposure arm does not establish an ACT-R implementation, a human-memory mechanism, or a retrieval-probability model.",
    "Only complete retained native occurrences witnessed in each exact returned chunk contribute; inspected pages are not the entire corpus or machine history.",
    "The cue-only ablation controls exact public metadata matching; this roster does not separately identify decay and frequency effects.",
    "Ranking sees public query cues and source-derived candidate exposures, never private answer keys, task classes, target sequences, or eligibility support.",
    "All arms are permutations of the same raw candidates; raw adapter order, score bytes, canonical-row receipts, source origins, and latency observations remain unchanged.",
    "Unavailable exposures preserve raw-order ties; resource overflow refuses the complete roster rather than clipping history or dropping queries.",
    "Observation time and the complete ordered activation grid are externally declared; this component neither chooses an optimum nor evaluates the calibration objective.",
    "Heldout parameter pins declare calibration-only selection chronology but do not independently prove when tuning or result inspection occurred.",
    "No rerank duration was measured, and retained raw latencies do not establish CPU, model, machine, or cognitive comparisons.",
    "No retrieval metrics, significance, statistical power, independent sampling, or public win are established; an independently frozen ordered-measurement adapter is still required.",
    "All retained capture, selection, measurement, baseline, raw-adapter, model, build, and activation nonclaims remain controlling.",
]
_POLICY = {
    "schema": "sia-cognitive-event-exposure-policy-v1",
    "exposures": "retained-native-excerpt-in-returned-chunk-v1",
    "cue_parser": "signed-history-exact-clause-v1",
    "timestamp_source": "signed-event-time-utc-v1",
    "ordering": "cue-presence-activation-raw-rank-v1",
    "unavailable": "preserve-raw-order-v1",
    "overflow": "refuse-complete-run-v1",
}
_RESOURCE_LIMITS = {
    "max_queries": MAX_QUERIES, "max_source_events": MAX_SOURCE_EVENTS,
    "max_grid_policies": MAX_GRID_POLICIES, "max_input_bytes": MAX_INPUT_BYTES,
    "max_trace_bytes": MAX_TRACE_BYTES, "max_output_bytes": MAX_OUTPUT_BYTES,
}
_REPLAY_KEYS = {
    *measurement._SOURCE_KEYS, "protocol", "expected_protocol_sha256", "baseline", "expected_baseline_sha256",
    "expected_parameter_freeze_sha256",
}
_CHAIN = re.compile(r"[a-z][a-z0-9_-]*")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_UNIX = re.compile(r"0|[1-9][0-9]*")
_RETENTION = {"not-projected", "no-admitted-witness", "retained", "lineage-only"}
# These are the exact existing public template envelopes. Quoted values are
# decoded independently; syntax appearing *inside* those values is just data.
_TEMPLATES = (
    ("What was the latest recorded outcome value for ",
     "? Use signed sequence order, not event-time chronology."),
    ("How many occurrences are recorded for ", "?"),
    ("At what recorded timestamp was the first occurrence of ",
     "? Use signed sequence order; the scope is this chain, not the entire machine."),
    ("At what native timestamp did the unique latest event-time occurrence of ",
     " occur? Use native event-time chronology, not signed sequence order; the scope is this chain, not the entire machine."),
)


class ExposureRefusal(ValueError):
    """A complete pinned exposure observation could not be admitted."""


def _fail(reason):
    error = ExposureRefusal("cognitive event exposure refused: " + reason)
    error.non_claims = list(NON_CLAIMS)
    raise error


def _keys(value, fields, label):
    if type(value) is not dict or len(value) != len(fields) \
            or any(type(key) is not str for key in value) or set(value) != set(fields):
        _fail(label + " fields are invalid")


def _integer(value, ceiling, *, positive=False):
    return type(value) is int and (0 < value if positive else 0 <= value) and value <= ceiling


def _json_size(value, ceiling):
    """Count canonical UTF-8 JSON without copying or serializing containers.

    Initial untrusted inputs receive the existing complete structural/type/
    cycle check first. This second pass accounts for every duplicate envelope
    occurrence, JSON escape and delimiter; shared references receive no byte
    discount. Small generated projections use the same finite byte accounting.
    """
    size = 0

    def add(amount):
        nonlocal size
        size += amount
        if size > ceiling:
            _fail("canonical JSON exceeds its complete declared byte capacity")

    def visit(item):
        kind = type(item)
        if kind is str:
            add(len('""'))
            for char in item:
                if char in ('"', "\\", "\b", "\f", "\n", "\r", "\t"):
                    add(len("\\n"))
                elif ord(char) < ord(" "):
                    add(len("\\u0000"))
                else:
                    add(len(char.encode("utf-8", "strict")))
        elif kind is bool:
            add(len("true" if item else "false"))
        elif item is None:
            add(len("null"))
        elif kind is int:
            if not -activation.MAX_SAFE_INTEGER <= item <= activation.MAX_SAFE_INTEGER:
                _fail("JSON integer exceeds its exact representation range")
            add(len(str(item)))
        elif kind is float:
            if not math.isfinite(item):
                _fail("JSON number is not finite")
            add(len(repr(item)))
        elif kind is list:
            add(len("[]"))
            for index, child in enumerate(item):
                if index:
                    add(len(","))
                visit(child)
        elif kind is dict:
            add(len("{}"))
            for index, (key, child) in enumerate(item.items()):
                if type(key) is not str:
                    _fail("JSON key is not text")
                if index:
                    add(len(","))
                visit(key)
                add(len(":"))
                visit(child)
        else:
            _fail("unsupported JSON value")

    visit(value)
    return size


def _canonical(value, ceiling):
    _json_size(value, ceiling)
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _policy(kw):
    # Admit ALL complete input structures before any copy, JSON serialization,
    # hash, or numerical work, including late malformed grid/replay fields.
    measurement.baseline_module._bounded(kw, MAX_INPUT_BYTES)
    policy = kw["rerank_policy"]
    _keys(policy, {*_POLICY, "observed_at", "ablation_roster", "activation_grid",
                   "activation_grid_sha256", "calibration_objective", "resources"}, "rerank policy")
    if any(type(policy[key]) is not str or policy[key] != expected for key, expected in _POLICY.items()):
        _fail("rerank policy changes the frozen exposure or ordering contract")
    resources = policy["resources"]
    _keys(resources, _RESOURCE_LIMITS, "resource policy")
    for key, ceiling in _RESOURCE_LIMITS.items():
        if not _integer(resources[key], ceiling, positive=True):
            _fail("resource policy is outside its strict hard ceiling: " + key)
    _json_size(kw, resources["max_input_bytes"])
    if not _integer(policy["observed_at"], activation.MAX_SAFE_INTEGER):
        _fail("observation time must be an explicit unsigned integer Unix time")
    if type(policy["ablation_roster"]) is not list or policy["ablation_roster"] != list(ARMS):
        _fail("the complete ordered ablation roster is required")
    grid = policy["activation_grid"]
    if type(grid) is not list or not 0 < len(grid) <= resources["max_grid_policies"]:
        _fail("complete activation grid exceeds its capacity or is absent")
    # Finish bounded admission for *every* grid member before hashing any.
    for member in grid:
        _keys(member, {"policy", "policy_sha256"}, "activation grid member")
        activation._policy(member["policy"])
        if not measurement._digest(member["policy_sha256"]):
            _fail("activation grid member hash is invalid")
    activation._policy(kw["activation_policy"])
    objective = policy["calibration_objective"]
    _keys(objective, {"metric_protocol_sha256", "class", "metric", "cutoff", "tie_break"}, "calibration objective")
    if not measurement._digest(objective["metric_protocol_sha256"]) \
            or type(objective["class"]) is not str or objective["class"] not in measurement._ANSWER_KINDS \
            or type(objective["metric"]) is not str or objective["metric"] not in {"recall_at_k", "mrr_at_k"} \
            or not _integer(objective["cutoff"], measurement.baseline_module.raw_admission.MAX_RESULTS, positive=True) \
            or objective["tie_break"] != "activation-grid-order-v1":
        _fail("calibration objective is not a declared supported retrieval request")
    _keys(kw["replay_inputs"], _REPLAY_KEYS, "complete measurement replay")
    replay = kw["replay_inputs"]
    if objective["metric_protocol_sha256"] != replay["expected_protocol_sha256"] \
            or objective["cutoff"] not in replay["metric_policy"]["cutoffs"]:
        _fail("calibration objective does not name the independently frozen retrieval protocol and cutoff")
    seen = set()
    for member in grid:
        measurement._pin(member["policy"], member["policy_sha256"])
        if member["policy_sha256"] in seen:
            _fail("activation grid repeats a policy")
        seen.add(member["policy_sha256"])
    measurement._pin(grid, policy["activation_grid_sha256"])
    measurement._pin(policy, kw["expected_rerank_policy_sha256"])
    measurement._pin(kw["activation_policy"], kw["expected_activation_policy_sha256"])
    if not any(member["policy_sha256"] == kw["expected_activation_policy_sha256"]
               and measurement._same(member["policy"], kw["activation_policy"]) for member in grid):
        _fail("selected activation policy is not an exact member of the complete frozen grid")
    return policy


def parse_public_cue(text):
    """Decode one whole canonical public template; quoted syntax is data."""
    try:
        if type(text) is not str or not 0 < len(text) <= MAX_QUERY_BYTES \
                or len(text.encode("utf-8", "strict")) > MAX_QUERY_BYTES:
            _fail("public query text exceeds its strict shape or byte capacity")
        envelopes = [(prefix, suffix) for prefix, suffix in _TEMPLATES
                     if text.startswith(prefix) and text.endswith(suffix)]
        if len(envelopes) != 1:
            _fail("public query is not exactly one complete supported canonical template")
        prefix, suffix = envelopes[0]
        clause = text[len(prefix):len(text) - len(suffix)]
        marker = "exact action "
        if not clause.startswith(marker):
            _fail("public query has no exact canonical action clause")
        decoder = json.JSONDecoder()
        action, end = decoder.raw_decode(clause, len(marker))
        marker = " and raw subject "
        if not clause.startswith(marker, end):
            _fail("public query has no exact canonical raw-subject clause")
        subject, end = decoder.raw_decode(clause, end + len(marker))
        marker, ending = " in the complete signed ", " chain"
        if not clause.startswith(marker, end) or not clause.endswith(ending):
            _fail("public query has no exact complete signed-chain clause")
        chain = clause[end + len(marker):len(clause) - len(ending)]
        if type(action) is not str or not action or type(subject) is not str or not subject \
                or _CHAIN.fullmatch(chain) is None:
            _fail("public cue has a non-text or invalid native identity")
        expected = ("exact action " + json.dumps(action, ensure_ascii=False) + " and raw subject "
                    + json.dumps(subject, ensure_ascii=False) + " in the complete signed " + chain + " chain")
        if clause != expected:
            _fail("public cue uses a noncanonical encoding, extra clause, or trailing text")
        return {"chain": chain, "action": action, "raw_subject": subject}
    except ExposureRefusal:
        raise
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError) as exc:
        _fail("public cue could not be admitted: " + str(exc))


def _occurrence(event):
    return {key: event[key] for key in ("chain", "seq", "entry_hash")}


def _event_timestamp(event):
    """Convert admitted canonical native time to integer seconds, not a clock.

    UTC calendar conversion uses the standard library's integer timegm path,
    never a floating Unix timestamp or a max-event-derived observation time.
    Full signed-row/projection replay remains mandatory after this preflight.
    """
    native, projected = event["row"][1], event["projection"]["event_time_utc"]
    if type(projected) is not str or _UTC.fullmatch(projected) is None:
        _fail("retained event has no canonical whole-second UTC projection")
    parsed = datetime.datetime.fromisoformat(projected.replace("Z", "+00:00"))
    seconds = calendar.timegm(parsed.utctimetuple())
    if event["chain"] == "custos":
        if type(native) is not str or _UNIX.fullmatch(native) is None or int(native) != seconds:
            _fail("native unsigned Unix event time disagrees with its captured projection")
    elif type(native) is not str or _UTC.fullmatch(native) is None or native != projected:
        _fail("native canonical UTC event time disagrees with its captured projection")
    return seconds


def _sources(kw, policy):
    capture = kw["replay_inputs"]["capture"]
    events = capture["events"]
    if type(events) is not list or len(events) > policy["resources"]["max_source_events"]:
        _fail("complete source event population exceeds its declared ceiling")
    pages = kw["replay_inputs"]["selection"]["pages"]
    if type(pages) is not list or len(pages) > measurement.baseline_module.preparation_admission.MAX_PAGES:
        _fail("selected page roster exceeds the existing preparer capacity")
    pages_by_slug = {}
    for page in pages:
        if type(page) is not dict or type(page.get("slug")) is not str or page["slug"] in pages_by_slug:
            _fail("selected page roster has malformed or repeated identities")
        pages_by_slug[page["slug"]] = page
    by_slug, population, seen = {}, [], set()
    for event in events:
        identity = _occurrence(event)
        key = tuple(identity.values())
        if any(type(value) is not str for value in key) or key in seen:
            _fail("complete source population repeats or malforms an occurrence identity")
        seen.add(key)
        status = event["retention"]["status"]
        if type(status) is not str or status not in _RETENTION:
            _fail("source occurrence has an undeclared retention state")
        population.append({"occurrence": identity, "retention_status": status})
        if status != "retained":
            continue
        retention = event["retention"]
        if retention["projected_event_retained"] is not True \
                or type(retention["retrieval_excerpt"]) is not str or not retention["retrieval_excerpt"] \
                or type(retention["source_slug"]) is not str:
            _fail("retained occurrence has no exact native excerpt witness")
        # Keep references to the complete admitted population, not answer-key
        # support or a max_uses-sized prefix. Excluded pages are never invented
        # as candidates; selected source-page feasibility is a separate layer.
        by_slug.setdefault(retention["source_slug"], []).append(event)
    return pages_by_slug, by_slug, population


def _exposure(event, page, raw, chunk_sha256):
    excerpt = event["retention"]["retrieval_excerpt"]
    return {
        "occurrence": _occurrence(event), "action": event["row"][2], "raw_subject": event["row"][3],
        "native_timestamp": event["row"][1], "event_time_utc": event["projection"]["event_time_utc"],
        "timestamp": _event_timestamp(event), "excerpt": excerpt,
        "excerpt_sha256": measurement._sha(excerpt.encode("utf-8")),
        "source_slug": raw["slug"], "origin": page["origin"], "page_text_sha256": page["text_sha256"],
        "chunk_index": raw["chunk_index"], "chunk_text_sha256": chunk_sha256,
    }


def _use(exposure):
    identity = exposure["occurrence"]
    identifier = measurement._sha(measurement._canonical([
        "sia-cognitive-event-exposure-use-v1", identity["chain"], identity["seq"], identity["entry_hash"]]))
    return {"id": identifier, "timestamp": exposure["timestamp"]}


def _cue_match(exposure, cue):
    return exposure["occurrence"]["chain"] == cue["chain"] \
        and exposure["action"] == cue["action"] and exposure["raw_subject"] == cue["raw_subject"]


def _prepare_queries(kw, policy, *, parsed_queries=None):
    """Preflight the ENTIRE roster before any rank worker or output copy.

    This also runs provisionally before detaching the bounded input snapshot.
    No provenance is admitted by that provisional pass. The detached source
    packet is subsequently replayed independently, and its projections are
    rebuilt before scoring without parsing the same public query twice.
    """
    pages, events_by_slug, population = _sources(kw, policy)
    baseline = kw["measurement_plan"]["baseline"]
    queries = baseline["queries"]
    raw_results = baseline["observation"]["query"]["payload"]["results"]
    if type(queries) is not list or len(queries) > policy["resources"]["max_queries"] \
            or type(raw_results) is not list or len(raw_results) != len(queries):
        _fail("complete query or raw-result roster exceeds its declared capacity")
    if parsed_queries is not None and len(parsed_queries) != len(queries):
        _fail("public query roster changed while detaching inputs")
    prepared, trace_bytes, ids = [], 0, set()
    for index, (query, raw_result) in enumerate(zip(queries, raw_results)):
        _keys(query, {"id", "text"}, "public query")
        if type(query["id"]) is not str or query["id"] in ids or query["id"] != raw_result["id"]:
            _fail("public/raw query identities are missing, duplicated, or reordered")
        ids.add(query["id"])
        if parsed_queries is None:
            cue = parse_public_cue(query["text"])
        else:
            previous = parsed_queries[index]["query"]
            if query["id"] != previous["id"] or query["text"] != previous["text"]:
                _fail("public query changed while detaching inputs")
            cue = dict(previous["cue"])
        raw_rows = raw_result["rows"]
        selected_policy = kw["activation_policy"]
        if type(raw_rows) is not list or len(raw_rows) > selected_policy["max_candidates"]:
            _fail("complete raw candidate roster exceeds activation capacity")
        candidates, full_traces, total_uses = [], [], 0
        for rank, raw in enumerate(raw_rows, 1):
            chunk_ceiling = measurement.baseline_module.preparation_admission.MAX_CHUNK_BYTES
            if type(raw) is not dict or type(raw.get("slug")) is not str \
                    or type(raw.get("chunk_text")) is not str or len(raw["chunk_text"]) > chunk_ceiling \
                    or not _integer(raw.get("chunk_index"), activation.MAX_SAFE_INTEGER):
                _fail("raw candidate has no bounded exact source chunk identity")
            page = pages[raw["slug"]]
            chunk = raw["chunk_text"].encode("utf-8", "strict")
            if len(chunk) > chunk_ceiling:
                _fail("raw candidate exceeds the existing prepared chunk byte capacity")
            chunk_sha = measurement._sha(chunk)
            exposures = []
            for event in events_by_slug.get(raw["slug"], ()):
                if event["retention"]["retrieval_excerpt"].encode("utf-8") not in chunk:
                    continue
                if len(exposures) >= selected_policy["max_uses"] or total_uses >= selected_policy["max_total_uses"]:
                    _fail("complete per-query exposure population exceeds activation use capacity")
                exposed = _exposure(event, page, raw, chunk_sha)
                # The complete unfiltered exposure count/bytes are controlling
                # even when its cue differs. Filtering is not a capacity escape.
                trace_bytes += _json_size(exposed, policy["resources"]["max_trace_bytes"])
                if trace_bytes > policy["resources"]["max_trace_bytes"]:
                    _fail("complete aggregate exposure records exceed trace byte capacity")
                exposures.append(exposed)
                total_uses += 1
            exposures.sort(key=lambda item: (item["timestamp"], item["occurrence"]["chain"],
                                             item["occurrence"]["seq"], item["occurrence"]["entry_hash"]))
            row_ref = "row-" + str(rank)
            complete = {"v": 1, "subject": row_ref, "complete": True, "uses": [_use(row) for row in exposures]}
            full_traces.append(complete)
            trace = {**complete, "uses": [_use(row) for row in exposures if _cue_match(row, cue)]}
            candidates.append({
                "row_ref": row_ref, "raw_rank": rank, "raw_row": raw, "origin": page["origin"],
                "page_text_sha256": page["text_sha256"], "chunk_text_sha256": chunk_sha,
                "exposures": exposures, "trace": trace,
            })
        # Complete traces and all timestamps admit before cue-only subsets.
        # Both passes are validation only; neither computes an activation.
        activation._validate_set(full_traces, policy["observed_at"], selected_policy)
        activation._validate_set([row["trace"] for row in candidates], policy["observed_at"], selected_policy)
        prepared.append({"query": {"id": query["id"], "text": query["text"], "cue": cue}, "candidates": candidates})
    trace_view = [{"id": item["query"]["id"], "candidates": [
        {"row_ref": row["row_ref"], "exposures": row["exposures"], "trace": row["trace"]}
        for row in item["candidates"]]} for item in prepared]
    _json_size(trace_view, policy["resources"]["max_trace_bytes"])
    return prepared, population


def _rank_query(*, query, candidates, observed_at, activation_policy):
    """The target-blind numerical boundary: no capture, classes, or keys enter."""
    traces = [row["trace"] for row in candidates]
    receipt = activation.rank_traces(traces, observed_at=observed_at, policy=activation_policy)
    original = [row["row_ref"] for row in candidates]
    cue_only = [row["row_ref"] for row in candidates if row["trace"]["uses"]] \
        + [row["row_ref"] for row in candidates if not row["trace"]["uses"]]
    order = receipt["order"]
    if len(order) != len(original) or set(order) != set(original) or len(set(order)) != len(order):
        _fail("activation receipt is not a complete candidate permutation")
    return {**query, "candidates": candidates, "activation": receipt,
            "arms": [{"name": "raw-original", "order": original},
                     {"name": "cue-only", "order": cue_only},
                     {"name": "cue-event-exposure", "order": order}]}


def _result_body(kw, queries, population):
    plan, policy = kw["measurement_plan"], kw["rerank_policy"]
    return {
        "schema": "sia-cognitive-event-exposure-v1", "status": "computed-unverified",
        **{key: plan[key] for key in (
            "capture_sha256", "policy_sha256", "selection_sha256", "pages_sha256", "metric_policy_sha256",
            "baseline_contract_sha256", "protocol_sha256", "baseline_sha256", "query_roster_sha256",
            "split", "parameter_freeze_sha256")},
        "measurement_plan_sha256": kw["expected_measurement_plan_sha256"], "measurement_plan": plan,
        "rerank_policy": policy, "rerank_policy_sha256": kw["expected_rerank_policy_sha256"],
        "activation_policy": kw["activation_policy"], "activation_policy_sha256": kw["expected_activation_policy_sha256"],
        "activation_grid_sha256": policy["activation_grid_sha256"], "observed_at": policy["observed_at"],
        "event_population": population, "queries": queries,
        "source_non_claims": {"measurement": plan["non_claims"], "history": plan["source_non_claims"],
                              "activation": list(activation.NON_CLAIMS)},
        "non_claims": list(NON_CLAIMS),
    }


def _reserve_output(kw, prepared, population):
    """Reserve a conservative whole result before executing a rank worker.

    Score and variant placeholders deliberately exceed finite binary64 JSON
    spelling and either fixed variant label. They are capacity reservations,
    never fabricated observed activations. No placeholder is returned.
    """
    policy, queries = kw["rerank_policy"], []
    digest_placeholder = "0" * len(kw["expected_activation_policy_sha256"])
    numeric_placeholder = "x" * activation.MAX_USE_ID_BYTES
    for item in prepared:
        references = [row["row_ref"] for row in item["candidates"]]
        receipts = [{
            "v": 1, "component": "usage-salience", "status": "computed-unverified",
            "subject": row["row_ref"], "observed_at": policy["observed_at"], "score": numeric_placeholder,
            "reason": "no-use-history", "uses_count": len(row["trace"]["uses"]),
            "trace_sha256": digest_placeholder, "policy_sha256": digest_placeholder,
            "variant": numeric_placeholder, "non_claims": list(activation.NON_CLAIMS),
        } for row in item["candidates"]]
        receipt = {
            "v": 1, "component": "usage-salience", "status": "computed-unverified",
            "observed_at": policy["observed_at"], "policy_sha256": digest_placeholder,
            "trace_set_sha256": digest_placeholder, "order": references,
            "activations": receipts, "non_claims": list(activation.NON_CLAIMS),
        }
        queries.append({**item["query"], "candidates": item["candidates"], "activation": receipt,
                        "arms": [{"name": name, "order": references} for name in ARMS]})
    body = _result_body(kw, queries, population)
    body["artifact_sha256"] = digest_placeholder
    _json_size(body, policy["resources"]["max_output_bytes"])


def _replay(kw):
    measurement._pin(kw["measurement_plan"], kw["expected_measurement_plan_sha256"], "plan_sha256")
    replayed = measurement.prepare_measurement(**kw["replay_inputs"])
    if not measurement._same(replayed, kw["measurement_plan"]):
        _fail("retained measurement plan differs from complete independently pinned source replay")
    if replayed["split"] == "heldout":
        parameters = replayed["baseline"]["parameter_freeze"]["parameters"]
        required = {
            "measurement_protocol_sha256": replayed["protocol_sha256"],
            "event_exposure_policy_sha256": kw["expected_rerank_policy_sha256"],
            "activation_grid_sha256": kw["rerank_policy"]["activation_grid_sha256"],
            "selected_activation_policy_sha256": kw["expected_activation_policy_sha256"],
        }
        if any(type(parameters.get(key)) is not str or parameters[key] != value for key, value in required.items()):
            _fail("heldout parameter freeze omits or changes a required protocol, rerank, grid, or selected policy pin")


def _rerank(kw):
    policy = _policy(kw)
    prepared, population = _prepare_queries(kw, policy)
    _reserve_output(kw, prepared, population)
    # Only after complete provisional trace/output resource admission do we
    # detach the supplied packet. Pins and provenance are checked again on this
    # private snapshot before any numerical work. The public cue is parsed just
    # once; identity/text must be unchanged when its projection is reused.
    detached = copy.deepcopy(kw)
    detached_policy = _policy(detached)
    detached_prepared, detached_population = _prepare_queries(detached, detached_policy, parsed_queries=prepared)
    _reserve_output(detached, detached_prepared, detached_population)
    _replay(detached)
    del prepared, population
    queries = [_rank_query(query=item["query"], candidates=item["candidates"],
                           observed_at=detached_policy["observed_at"], activation_policy=detached["activation_policy"])
               for item in detached_prepared]
    body = _result_body(detached, queries, detached_population)
    ceiling = detached_policy["resources"]["max_output_bytes"]
    body["artifact_sha256"] = measurement._sha(_canonical(body, ceiling))
    _json_size(body, ceiling)
    # All fields already belong to the private validated snapshot or newly
    # constructed projections/receipts. No caller-owned mutable object remains.
    return body


def rerank_event_exposure(*, measurement_plan, expected_measurement_plan_sha256, replay_inputs,
                          rerank_policy, expected_rerank_policy_sha256, activation_policy,
                          expected_activation_policy_sha256):
    """Return a detached computed-unverified overlay on fully replayed raw evidence."""
    try:
        return _rerank(locals())
    except ExposureRefusal:
        raise
    except (measurement.baseline_module.BaselineRefusal, ValueError, TypeError, KeyError,
            IndexError, OverflowError, RecursionError, UnicodeError) as exc:
        _fail("complete input could not be admitted: " + str(exc))
