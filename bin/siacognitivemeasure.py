"""Freeze signed-occurrence targets and prepare unevaluated retrieval requests.

No engine, file, database, or JACKAL invocation occurs here. Callers first pin a
protocol built from independently pinned source and baseline-contract inputs.
After execution, retained baseline observations are replayed against those same
inputs. A heldout parameter freeze must already name that protocol.

Definitions are engineering adaptations of Stanford IR's relevant-set recall
and top-k ranked sets, and TREC's first-correct-response reciprocal rank:
https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-unranked-retrieval-sets-1.html
https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html
https://trec.nist.gov/presentations/TREC9/qa/tsld005.htm

Here relevance units are exact signed occurrences with frozen canonical source
chunks, not documents or semantic answers. Counts are represented-data
sufficient statistics. Fractions and means are request expressions, never
locally evaluated or given mathematical assurance by this module.
"""

import copy
import math

import siacognitivebaseline as baseline_module


MAX_ARTIFACT_BYTES = baseline_module.MAX_ARTIFACT_BYTES
NON_CLAIMS = [
    "This plan contains unevaluated JACKAL requests, not arithmetic assurance, significance, or a cognitive win.",
    "Occurrence recall and first-any-target reciprocal rank are engineering adaptations, not document relevance or semantic-answer correctness.",
    "Recency contrast support is eligibility evidence, not an answer target; repetition targets remain the complete signed occurrence roster.",
    "First-any-target reciprocal rank does not establish that all repetition targets were retrieved or answered.",
    "Target credit requires the selected canonical support chunk and exact native excerpt; alternate copies and slug matches receive no credit.",
    "Queries are generated signed-history tasks with chain/raw-subject group dependence and shared pages, not independent population samples.",
    "Per-class query means do not establish class balance, statistical power, a temporal holdout, or machine-wide cognitive mechanisms.",
    "Pinned protocol and parameter-freeze identities declare chronology; they do not independently prove when tuning or result inspection occurred.",
    "Artifact replay checks represented consistency, not current archive bytes, historical process truth, loaded code, or resident memory.",
    "Source origins and every retained raw latency value remain controlling; arithmetic cannot promote model-origin text into evidence.",
    "Unavailable classes remain unavailable and source selection exclusions are not converted into zero-valued observations.",
    "All capture, selection, baseline, model, build, and raw-adapter nonclaims remain controlling.",
]
_POLICY = {
    "schema": "sia-cognitive-retrieval-policy-v1",
    "targets": "signed-answer-occurrences-v1",
    "matching": "exact-selected-source-chunk-and-native-excerpt-v1",
    "recall": "distinct-target-union-at-k-v1",
    "reciprocal_rank": "first-any-target-row-at-k-v1",
    "aggregation": "macro-query-within-class-v1",
    "duplicates": "refuse-invalid-raw-roster-v1",
    "origins": "preserve-source-labels-no-promotion-v1",
    "missing": "zero-hit-no-denominator-shrink-v1",
    "dependence": "chain-raw-subject-groups-and-shared-pages-v1",
    "chronology": "externally-pinned-before-heldout-v1",
}
_SOURCE_KEYS = (
    "capture", "expected_capture_sha256", "selection_policy", "expected_policy_sha256",
    "selection", "expected_selection_sha256", "baseline_contract", "expected_baseline_contract_sha256",
    "metric_policy", "expected_metric_policy_sha256",
)
_SOURCE_PINS = ("capture_sha256", "policy_sha256", "selection_sha256", "pages_sha256")
_ANSWER_KINDS = {
    "recency-heavy": "latest-recorded-outcome", "repetition-heavy": "occurrence-count",
    "novelty": "first-occurrence",
}


class MeasurementRefusal(ValueError):
    """Frozen source, target, observation, or measurement policy was refused."""


def _fail(reason):
    raise MeasurementRefusal("cognitive measurement refused: " + reason)


def _keys(value, fields, label):
    if type(value) is not dict or set(value) != set(fields):
        _fail(label + " fields are invalid")


def _bounded_inputs(values):
    # Finish admission of every supplied structure before any copy or JSON
    # serialization. In particular, a late malformed metric policy must not
    # trigger eager copying/hashing of the earlier capture or baseline.
    for value in values:
        baseline_module._bounded(value, MAX_ARTIFACT_BYTES)


def _canonical(value):
    return baseline_module._canonical(value, MAX_ARTIFACT_BYTES)


def _sha(value):
    return baseline_module._sha(value)


def _same(left, right):
    return _canonical(left) == _canonical(right)


def _digest(value):
    return baseline_module._digest(value)


def _self_digest(value, field):
    return _sha(_canonical({key: item for key, item in value.items() if key != field}))


def _pin(value, expected, field=None):
    if not _digest(expected):
        _fail("external digest is missing or malformed")
    if field is not None and type(value) is not dict:
        _fail("self-bound artifact is not an object")
    actual = _self_digest(value, field) if field is not None else _sha(_canonical(value))
    if actual != expected or field is not None and value.get(field) != actual:
        _fail("external artifact digest disagrees")


def _finish(body, field):
    digest = _sha(_canonical(body))
    result = {**body, field: digest}
    _canonical(result)
    return copy.deepcopy(result)


def _contract(value, selected):
    """Admit retained policy fields, not paths or current host source bytes."""
    version = ({"sia-cognitive-baseline-contract-v1": 1,
                "sia-cognitive-baseline-contract-v2": 2}.get(value.get("schema"))
               if type(value) is dict and type(value.get("schema")) is str else None)
    input_fields = {"embedding_input_policy", "embedding_input_policy_sha256"} if version == 2 else set()
    _keys(value, {"schema", *_SOURCE_PINS, "preparer", "adapter", "embedding", "model",
                  "runtime", "code_expectations", "limit", "timeout", *input_fields}, "baseline contract")
    if version is None \
            or any(value[key] != selected[key] for key in _SOURCE_PINS):
        _fail("baseline contract source identities disagree")
    for role in ("preparer", "adapter"):
        build = value[role]
        _keys(build, {"expected", "build_receipt_sha256"}, role + " contract")
        baseline_module.runner._expectation_values(build["expected"])
        if not _digest(build["build_receipt_sha256"]):
            _fail("baseline build receipt pin is invalid")
    model = value["model"]
    _keys(model, {"model_name", "package_sha256", "manifest_sha256", "release_version",
                  "release_archive_sha256"}, "baseline model contract")
    if any(not _digest(model[key]) for key in ("package_sha256", "manifest_sha256", "release_archive_sha256")) \
            or type(model["model_name"]) is not str \
            or baseline_module.siavectormodel._MODEL.fullmatch(model["model_name"]) is None \
            or type(model["release_version"]) is not str or not model["release_version"]:
        _fail("baseline model pins are invalid")
    runtime = value["runtime"]
    if type(runtime) is not list or not runtime or len(runtime) > baseline_module.siavectormodel.MAX_ENTRIES:
        _fail("baseline shared runtime roster is invalid")
    destinations = []
    for leaf in runtime:
        _keys(leaf, {"destination", "sha256"}, "baseline runtime leaf")
        path = baseline_module._path(leaf["destination"])
        if path in destinations or not _digest(leaf["sha256"]) \
                or not (path == "/usr/bin/python3" or path.startswith("/usr/lib/")) \
                or any(part in ("site-packages", "dri", "cuda", "vulkan") for part in path.split("/")):
            _fail("baseline runtime destination or pin is invalid")
        destinations.append(path)
    if "/usr/bin/python3" not in destinations or destinations != sorted(destinations):
        _fail("baseline runtime roster is not canonical or lacks Python")
    code = value["code_expectations"]
    _keys(code, {"schema", "files"}, "baseline code inventory")
    if code["schema"] != "sia-bin-source-inventory-v1" or type(code["files"]) is not dict \
            or not code["files"] or len(code["files"]) > baseline_module.siavectormodel.MAX_ENTRIES \
            or any(not name or name.startswith(".") or "/" in name or "\\" in name
                   or not _digest(digest) for name, digest in code["files"].items()):
        _fail("baseline code inventory declaration is invalid")
    if type(value["timeout"]) not in (int, float) or not math.isfinite(value["timeout"]) \
            or not 0 < value["timeout"] <= 1800:
        _fail("baseline timeout is invalid")
    # This is only the projection consumed by the existing pure replay
    # validators. No discarded operational paths are invented to call preflight.
    kw = {"preparer": value["preparer"], "adapter": value["adapter"],
          "embedding": value["embedding"], "model_expectations": model,
          "shared_runtime": runtime, "limit": value["limit"]}
    if version == 2:
        kw.update(_raw_version=2, embedding_input_policy=value["embedding_input_policy"],
                  expected_embedding_input_policy_sha256=value["embedding_input_policy_sha256"])
        # This field is independently pinned by the complete source contract;
        # admitting a response's own policy would not establish that binding.
        baseline_module._admit_input_policy(kw)
    baseline_module.raw_admission.admit_request(baseline_module._query_request(kw, "capture", [], {}))
    if value["embedding"]["model"] != "ollama:" + model["model_name"] \
            or value["embedding"]["endpoint"] != "http://127.0.0.1:11434/v1":
        _fail("baseline embedding does not identify its private model")
    request = baseline_module.preparation_admission.admit_request(
        baseline_module._preparation_request(kw, selected))
    return kw, request


def _metric_policy(value, limit):
    _keys(value, {*_POLICY, "cutoffs"}, "retrieval policy")
    if any(type(value[key]) is not str or value[key] != expected for key, expected in _POLICY.items()):
        _fail("retrieval policy changes a frozen target or measurement rule")
    cutoffs = value["cutoffs"]
    if type(cutoffs) is not list or not cutoffs or len(cutoffs) > baseline_module.raw_admission.MAX_RESULTS \
            or any(type(k) is not int or not 0 < k <= limit for k in cutoffs) \
            or cutoffs != sorted(set(cutoffs)):
        _fail("cutoffs must be unique increasing positive integers within the observed limit")


def _source(kw):
    _bounded_inputs(kw[key] for key in _SOURCE_KEYS)
    for key in ("expected_capture_sha256", "expected_policy_sha256", "expected_selection_sha256",
                "expected_baseline_contract_sha256", "expected_metric_policy_sha256"):
        if not _digest(kw[key]):
            _fail("source, contract and metric policy pins must be independently supplied")
    selected = baseline_module.selection_module.admit_selection(
        kw["selection"], capture=kw["capture"], policy=kw["selection_policy"],
        expected_capture_sha256=kw["expected_capture_sha256"], expected_policy_sha256=kw["expected_policy_sha256"])
    if selected["selection_sha256"] != kw["expected_selection_sha256"]:
        _fail("external selection pin disagrees")
    _pin(kw["baseline_contract"], kw["expected_baseline_contract_sha256"])
    replay_kw, request = _contract(kw["baseline_contract"], selected)
    _metric_policy(kw["metric_policy"], kw["baseline_contract"]["limit"])
    _pin(kw["metric_policy"], kw["expected_metric_policy_sha256"])
    return selected, replay_kw, request


def _protocol(kw, selected):
    # _source has replayed the complete policy/capture selection. New answer
    # semantics belong to that admitted version pair, not to an answer-kind
    # string that a caller could attach to an old selection and rehash.
    selector = baseline_module.selection_module
    version = (kw["selection_policy"]["schema"], selected["schema"])
    answer_kinds = dict(_ANSWER_KINDS)
    if version == (selector.EVENT_RECENCY_POLICY_SCHEMA, selector.EVENT_RECENCY_SCHEMA):
        answer_kinds["recency-heavy"] = "latest-event-time-occurrence"
    elif version != (selector.POLICY_SCHEMA, selector.SCHEMA):
        _fail("selection policy and task schema have no matching target definition")
    pages = {row["slug"]: row for row in selected["pages"]}
    chunks = {slug: tuple(baseline_module.preparation_admission._chunk_bytes(page["text"]))
              for slug, page in pages.items()}
    events = {(row["chain"], row["seq"]): row for row in kw["capture"]["events"]}
    answers = {row["id"]: row for row in selected["answer_key"]}
    queries = []
    for public in selected["queries"]:
        answer = answers[public["id"]]
        if answer["class"] not in answer_kinds or answer["answer"]["kind"] != answer_kinds[answer["class"]]:
            _fail("selected task has no frozen occurrence-target definition")
        support = {(row["chain"], row["seq"]): row for row in answer["support"]}
        sequences = answer["answer"]["sequences"]
        if not sequences or len(set(sequences)) != len(sequences) or len(support) != len(answer["support"]):
            _fail("selected occurrence or support roster is empty or duplicated")
        targets = []
        for sequence in sequences:
            key = (answer["scope"]["chain"], sequence)
            event, witness = events.get(key), support.get(key)
            if event is None or witness is None or event["entry_hash"] != witness["entry_hash"]:
                _fail("answer target is not its exact signed source occurrence")
            page = pages[witness["slug"]]
            chunk = chunks[witness["slug"]][witness["chunk_index"]]
            excerpt = witness["excerpt"].encode("utf-8")
            if not excerpt or excerpt not in chunk or _sha(chunk) != witness["chunk_sha256"]:
                _fail("target witness is not the selected exact native excerpt and chunk")
            targets.append({
                "occurrence": {"chain": key[0], "seq": sequence, "entry_hash": event["entry_hash"]},
                "witness": {"slug": witness["slug"], "origin": page["origin"],
                            "page_text_sha256": page["text_sha256"], "excerpt": witness["excerpt"],
                            "excerpt_sha256": _sha(excerpt), "chunk_index": witness["chunk_index"],
                            "chunk_sha256": witness["chunk_sha256"]},
            })
        queries.append({**public, "class": answer["class"], "group_id": answer["group_id"],
                        "action": answer["action"], "answer_kind": answer["answer"]["kind"],
                        "scope": answer["scope"], "targets": targets,
                        "eligibility_support": answer["support"]})
    return _finish({
        "schema": "sia-cognitive-retrieval-protocol-v1",
        **{key: selected[key] for key in _SOURCE_PINS},
        "baseline_contract_sha256": kw["expected_baseline_contract_sha256"],
        "metric_policy_sha256": kw["expected_metric_policy_sha256"], "metric_policy": kw["metric_policy"],
        "groups": selected["groups"], "queries": queries,
        "coverage": selected["coverage"], "exclusions": selected["exclusions"],
        "source_non_claims": {"selection": selected["non_claims"], "history": selected["source_non_claims"]},
        "non_claims": list(NON_CLAIMS),
    }, "protocol_sha256")


def _archive(value):
    _keys(value, {"path", "sha256", "manifest", "manifest_sha256"}, "retained archive")
    if value["path"] != "index.tar" or not _digest(value["sha256"]) or not _digest(value["manifest_sha256"]):
        _fail("retained archive identity is invalid")
    manifest = value["manifest"]
    if type(manifest) is not list or not manifest or len(manifest) > baseline_module.MAX_MEMBERS:
        _fail("retained archive manifest is empty or excessive")
    seen, total, has_file = {}, 0, False
    for row in manifest:
        if type(row) is not dict or row.get("type") not in ("file", "directory"):
            _fail("retained archive manifest contains an unsupported member")
        kind = row["type"]
        _keys(row, {"path", "type", "bytes", "sha256"} if kind == "file" else {"path", "type"}, "archive member")
        path = row["path"]
        if type(path) is not str or not path or path.startswith("/") or "\x00" in path \
                or len(path.encode("utf-8")) > baseline_module.sialib.MAX_CONFIG_BYTES \
                or any(part in ("", ".", "..") for part in path.split("/")) or path in seen:
            _fail("retained archive member path is unsafe or duplicated")
        parts = path.split("/")
        for end in range(1, len(parts)):
            if seen.get("/".join(parts[:end])) != "directory":
                _fail("retained archive member lacks its preceding ordinary parent")
        seen[path] = kind
        if kind == "file":
            if type(row["bytes"]) is not int or not 0 <= row["bytes"] <= baseline_module.MAX_ARCHIVE_BYTES \
                    or not _digest(row["sha256"]):
                _fail("retained archive file byte identity is invalid")
            total += row["bytes"]
            has_file = True
            if total > baseline_module.MAX_ARCHIVE_BYTES:
                _fail("retained archive exceeds its aggregate file-byte ceiling")
    if not has_file or value["manifest_sha256"] != _sha(_canonical(manifest)):
        _fail("retained archive manifest digest or file population disagrees")


def _freeze(value, protocol, expected):
    freeze, supplied = value["parameter_freeze"], value["parameter_freeze_sha256"]
    if value["split"] == "calibration":
        if freeze is not None or supplied is not None or expected is not None:
            _fail("calibration measurement does not consume a heldout freeze")
        return
    _keys(freeze, {"schema", "capture_sha256", "policy_sha256", "selection_sha256",
                   "baseline_contract_sha256", "calibration_run_sha256", "tuning_split",
                   "parameters", "parameters_sha256", "non_claims", "freeze_sha256"}, "parameter freeze")
    _pin(freeze, expected, "freeze_sha256")
    if supplied != expected or freeze["schema"] != "sia-cognitive-parameter-freeze-v1" \
            or freeze["tuning_split"] != "calibration" or type(freeze["parameters"]) is not dict \
            or not _digest(freeze["calibration_run_sha256"]) \
            or freeze["baseline_contract_sha256"] != protocol["baseline_contract_sha256"] \
            or any(freeze[key] != protocol[key] for key in ("capture_sha256", "policy_sha256", "selection_sha256")) \
            or not _same(freeze["non_claims"], baseline_module.FREEZE_NON_CLAIMS) \
            or freeze["parameters_sha256"] != _sha(_canonical(freeze["parameters"])) \
            or freeze["parameters"].get("measurement_protocol_sha256") != protocol["protocol_sha256"]:
        _fail("heldout parameter freeze does not bind this frozen retrieval protocol")


def _baseline(kw, selected, protocol, replay_kw, request):
    value = kw["baseline"]
    input_fields = baseline_module._input_policy_fields(replay_kw)
    _keys(value, {"schema", "status", "lane", "split", *_SOURCE_PINS, "query_roster_sha256",
                  "baseline_contract_sha256", "parameter_freeze_sha256", "parameter_freeze", "contract",
                  "queries", "pages", "answer_key", "preparation", "observation", "retrieval_rows", "archive",
                  "source_non_claims", "non_claims", "artifact_sha256", *input_fields}, "baseline artifact")
    _pin(value, kw["expected_baseline_sha256"], "artifact_sha256")
    if value["schema"] != "sia-cognitive-baseline-v" + str(baseline_module._raw_version(replay_kw)) \
            or value["status"] != "observed" \
            or value["lane"] != "raw_vector" or type(value["split"]) is not str \
            or value["split"] not in ("calibration", "heldout") \
            or any(value[key] != protocol[key] for key in _SOURCE_PINS) \
            or value["baseline_contract_sha256"] != kw["expected_baseline_contract_sha256"] \
            or not _same(value["contract"], kw["baseline_contract"]) \
            or not _same(value["non_claims"], baseline_module._baseline_nonclaims(replay_kw)) \
            or any(not _same(value[key], expected) for key, expected in input_fields.items()):
        _fail("baseline schema, source, contract or nonclaims disagree")
    queries = [{"id": row["id"], "text": row["text"]}
               for row in selected["queries"] if row["split"] == value["split"]]
    ids = {row["id"] for row in queries}
    if not queries or not _same(value["queries"], queries) \
            or value["query_roster_sha256"] != _sha(_canonical(queries)) \
            or not _same(value["pages"], selected["pages"]) \
            or not _same(value["answer_key"], [row for row in selected["answer_key"] if row["id"] in ids]) \
            or not _same(value["source_non_claims"], {
                "selection": selected["non_claims"], "history": selected["source_non_claims"]}):
        _fail("baseline query, answer, page or source-boundary roster differs from replayed selection")
    _freeze(value, protocol, kw["expected_parameter_freeze_sha256"])
    _archive(value["archive"])
    # Preserve actual rebound wire SHA versus logical null-descriptor SHA roles,
    # full owned model generations and opaque stdout digests. These existing
    # validators are pure; no archive/model/source path is reopened here.
    preparation = baseline_module._preparation(value["preparation"], request, replay_kw)
    _observation, labels = baseline_module._observation(
        value["observation"], value["archive"], preparation, queries, selected, replay_kw)
    if not _same(labels, value["retrieval_rows"]):
        _fail("baseline source labels differ from exact raw chunk joins")
    return value


def _occurrence_key(value):
    return value["chain"], value["seq"], value["entry_hash"]


def _request(scope, identifier, metric, k, query_ids, expression):
    # The caller executes and retains JACKAL responses separately. This object
    # carries neither a fabricated result/status nor local fraction evaluation.
    return {"tool": "jackal_exact", "arguments": {"expression": expression},
            "scope": {"kind": scope, "id": identifier}, "metric": metric, "k": k,
            "query_ids": list(query_ids)}


def _measure_queries(protocol, baseline):
    raw = {row["id"]: row for row in baseline["observation"]["query"]["payload"]["results"]}
    labels = {row["id"]: row["rows"] for row in baseline["retrieval_rows"]}
    protocol_queries = {row["id"]: row for row in protocol["queries"]}
    coverage_by_id = {}
    for public in baseline["queries"]:
        identifier = public["id"]
        query = protocol_queries[identifier]
        targets = query["targets"]
        if not targets:
            _fail("a measured query has no frozen occurrence denominator")
        row_coverage = []
        for rank, (row, label) in enumerate(zip(raw[identifier]["rows"], labels[identifier], strict=True), 1):
            hits = []
            chunk = row["chunk_text"].encode("utf-8")
            for target in targets:
                witness = target["witness"]
                if witness["slug"] == label["slug"] and witness["chunk_index"] == label["chunk_index"] \
                        and witness["chunk_sha256"] == label["chunk_text_sha256"] \
                        and witness["page_text_sha256"] == label["page_text_sha256"] \
                        and witness["origin"] == label["origin"] and witness["excerpt"].encode("utf-8") in chunk:
                    hits.append(target["occurrence"])
            row_coverage.append({"rank": rank, "slug": label["slug"], "chunk_index": label["chunk_index"],
                                 "origin": label["origin"], "target_occurrences": hits})
        coverage_by_id[identifier] = row_coverage
    return _summarize_coverage(protocol, baseline["queries"], coverage_by_id)


def _summarize_coverage(protocol, query_roster, coverage_by_id):
    """Summarize already admitted native-target hits in an explicit row order.

    This internal seam neither admits observations nor defines relevance.
    The raw caller above still reconstructs every hit using the exact native
    witness matcher; ordered callers must independently replay that complete
    raw measurement and admit a bijection before permuting its hit records.
    """
    protocol_queries = {row["id"]: row for row in protocol["queries"]}
    queries, requests, expressions = [], [], {}
    for public in query_roster:
        identifier = public["id"]
        query = protocol_queries[identifier]
        targets = query["targets"]
        if not targets:
            _fail("a measured query has no frozen occurrence denominator")
        row_coverage = coverage_by_id[identifier]
        cutoffs = []
        for k in protocol["metric_policy"]["cutoffs"]:
            covered, first_rank = set(), None
            for row in row_coverage[:k]:
                if row["target_occurrences"] and first_rank is None:
                    first_rank = row["rank"]
                covered.update(_occurrence_key(item) for item in row["target_occurrences"])
            occurrences = [target["occurrence"] for target in targets
                           if _occurrence_key(target["occurrence"]) in covered]
            cutoffs.append({"k": k, "target_count": len(targets), "retrieved_target_count": len(occurrences),
                            "covered_occurrences": occurrences, "first_target_rank": first_rank})
            recall = str(len(occurrences)) + "/" + str(len(targets))
            reciprocal = "0" if first_rank is None else "1/" + str(first_rank)
            expressions[(identifier, "recall_at_k", k)] = recall
            expressions[(identifier, "reciprocal_rank_at_k", k)] = reciprocal
            requests.append(_request("query", identifier, "recall_at_k", k, [identifier], recall))
            requests.append(_request("query", identifier, "reciprocal_rank_at_k", k, [identifier], reciprocal))
        queries.append({"id": identifier, "class": query["class"], "group_id": query["group_id"],
                        "targets": targets, "row_coverage": row_coverage, "cutoffs": cutoffs})
    classes = []
    for coverage in protocol["coverage"]:
        klass = coverage["class"]
        members = [row for row in queries if row["class"] == klass]
        ids = [row["id"] for row in members]
        classes.append({"class": klass, "query_ids": ids, "group_ids": sorted({row["group_id"] for row in members}),
                        "status": "prepared-for-jackal" if members else "unavailable",
                        "reason": None if members else coverage["reason"] or "no-queries-in-requested-split"})
        if not members:
            continue
        for k in protocol["metric_policy"]["cutoffs"]:
            for metric, constituent in (("recall_at_k", "recall_at_k"), ("mrr_at_k", "reciprocal_rank_at_k")):
                expression = "(" + "+".join("(" + expressions[(identifier, constituent, k)] + ")"
                                             for identifier in ids) + ")/" + str(len(ids))
                requests.append(_request("class", klass, metric, k, ids, expression))
    return queries, classes, requests


def _build(kw):
    selected, _replay_kw, _request_value = _source(kw)
    return _protocol(kw, selected)


def _prepare(kw):
    _bounded_inputs(kw.values())
    selected, replay_kw, request = _source(kw)
    expected_protocol = _protocol(kw, selected)
    _pin(kw["protocol"], kw["expected_protocol_sha256"], "protocol_sha256")
    if not _same(kw["protocol"], expected_protocol):
        _fail("rehashed protocol differs from replayed source targets and frozen policy")
    baseline = _baseline(kw, selected, expected_protocol, replay_kw, request)
    queries, classes, requests = _measure_queries(expected_protocol, baseline)
    return _finish({
        "schema": "sia-cognitive-measurement-plan-v1", "status": "prepared-for-jackal",
        "arithmetic_status": "not-evaluated", **{key: expected_protocol[key] for key in _SOURCE_PINS},
        "metric_policy_sha256": kw["expected_metric_policy_sha256"],
        "baseline_contract_sha256": kw["expected_baseline_contract_sha256"],
        "protocol_sha256": kw["expected_protocol_sha256"], "baseline_sha256": kw["expected_baseline_sha256"],
        "query_roster_sha256": baseline["query_roster_sha256"], "split": baseline["split"],
        "parameter_freeze_sha256": kw["expected_parameter_freeze_sha256"],
        "protocol": expected_protocol, "baseline": baseline,
        "queries": queries, "classes": classes, "jackal_requests": requests,
        "source_non_claims": {"protocol": expected_protocol["non_claims"], "baseline": baseline["non_claims"],
                              "history": baseline["source_non_claims"]},
        "non_claims": list(NON_CLAIMS),
    }, "plan_sha256")


def _guard(function, kw):
    try:
        return function(kw)
    except MeasurementRefusal:
        raise
    except (baseline_module.BaselineRefusal, baseline_module.siavector.VectorRefusal,
            baseline_module.siavectormodel.ModelRefusal, ValueError, TypeError,
            KeyError, IndexError, OverflowError, RecursionError) as exc:
        error = MeasurementRefusal("cognitive measurement could not be admitted: " + str(exc))
        error.non_claims = list(NON_CLAIMS)
        raise error from exc


def build_protocol(*, capture, expected_capture_sha256, selection_policy, expected_policy_sha256,
                   selection, expected_selection_sha256, baseline_contract, expected_baseline_contract_sha256,
                   metric_policy, expected_metric_policy_sha256):
    """Return a detached protocol before engine results exist; authenticate pins externally."""
    return _guard(_build, locals())


def prepare_measurement(*, capture, expected_capture_sha256, selection_policy, expected_policy_sha256,
                        selection, expected_selection_sha256, baseline_contract, expected_baseline_contract_sha256,
                        metric_policy, expected_metric_policy_sha256, protocol, expected_protocol_sha256,
                        baseline, expected_baseline_sha256, expected_parameter_freeze_sha256=None):
    """Replay pinned observations and return exact-expression requests without executing them."""
    return _guard(_prepare, locals())


def _live_input_envelope(kw, *, comparison, compound):
    import sialiveloop as live
    if not compound:
        live._size(kw, live.MAX_INPUT_BYTES)
        _bounded_inputs(kw.values())
        return
    import siacognitiveenvelope as envelope
    replay = {key: None for key in (*_SOURCE_KEYS, "protocol", "expected_protocol_sha256",
                                    "baseline", "expected_baseline_sha256", "expected_parameter_freeze_sha256")}
    layout = {"replay_inputs": replay, "live_capture": None, "expected_live_capture_sha256": None}
    if comparison:
        layout.update(ranking_policy=None, expected_ranking_policy_sha256=None)
    envelope.admit_compound(envelope=kw, layout=layout,
        max_input_bytes=envelope.MAX_INPUT_BYTES, max_document_bytes=MAX_ARTIFACT_BYTES)


def _prepare_live_history(kw, *, compound=False):
    import sialiveloop as live
    _live_input_envelope(kw, comparison=False, compound=compound)
    detached = copy.deepcopy(kw)
    plan = prepare_measurement(**detached["replay_inputs"])
    capture = live.admit_history_capture(detached["live_capture"],
        expected_capture_sha256=detached["expected_live_capture_sha256"])
    baseline = plan["baseline"]
    if plan["split"] == "heldout" and baseline["parameter_freeze"]["parameters"].get(
            "live_history_capture_sha256") != capture["capture_sha256"]:
        _fail("heldout freeze does not bind the live history capture")
    versions = {}
    for page in capture["intake"]["pages"]:
        key = (page["subject"], page["content_sha256"], page["origin"])
        if key in versions:
            _fail("live history has ambiguous source versions for the same full page")
        versions[key] = page
    pages = {page["slug"]: page for page in baseline["pages"]}
    queries = []
    for query, result in zip(baseline["queries"], baseline["observation"]["query"]["payload"]["results"], strict=True):
        candidates, rows = [], []
        for index, raw in enumerate(result["rows"]):
            # prepare_measurement replay already checked the complete chunk
            # roster, raw model/index/config bindings and full-page identity.
            page = pages[raw["slug"]]
            version = versions.get((page["slug"], page["text_sha256"], page["origin"]))
            ref = "row-" + str(index)
            rows.append({"row_ref": ref, "raw_row": raw, "origin": page["origin"],
                         "page_text_sha256": page["text_sha256"],
                         "availability": "exact-version-not-captured", "history": None})
            if version is not None:
                candidates.append({"row_ref": ref, **{key: version[key] for key in
                    ("subject", "content_sha256", "source_sha256", "origin")}})
        projection = live.project_history_traces(capture=capture,
            expected_capture_sha256=capture["capture_sha256"], candidates=candidates,
            expected_candidates_sha256=live._sha(candidates))
        histories = {row["candidate"]["row_ref"]: row for row in projection["rows"]}
        for row in rows:
            history = histories.get(row["row_ref"])
            if history is not None:
                row.update(availability=history["availability"], history=history)
        queries.append({"id": query["id"], "text": query["text"], "rows": rows,
                        "projection_sha256": projection["projection_sha256"],
                        "projection_non_claims": projection["non_claims"]})
    return _finish({
        "schema": "sia-cognitive-live-history-plan-v2" if compound else "sia-cognitive-live-history-plan-v1",
        "status": "computed-unverified",
        "baseline_sha256": plan["baseline_sha256"], "measurement_plan_sha256": plan["plan_sha256"],
        "live_capture_sha256": capture["capture_sha256"], "split": plan["split"],
        "epoch_id": capture["epoch_id"], "scope": capture["scope"],
        "started_at": capture["intake"]["started_at"], "observed_at": capture["observed_at"],
        "queries": queries,
        "source_non_claims": {"measurement": plan["non_claims"],
                              "sources": plan["source_non_claims"], "live": capture["non_claims"]},
        "non_claims": [
            "Raw chunks, page bytes and origins are replay-bound; source-version provenance comes from the independently pinned controller capture.",
            "Unmatched candidates remain in raw order with unavailable history; no answer keys, classes or target sequences enter the projected query packet.",
            "Controller-epoch completeness is not complete machine history, human use, or historical source authentication.",
            "This is a data binding, not a reranking, executed JACKAL metric, held-out independence proof, latency comparison or cognitive win.",
        ],
    }, "plan_sha256")


def prepare_live_history(*, replay_inputs, live_capture, expected_live_capture_sha256):
    """Replay raw-vector source bindings before attaching exact-version uses."""
    return _guard(_prepare_live_history, locals())


def prepare_live_history_v2(*, replay_inputs, live_capture, expected_live_capture_sha256):
    """Explicit closed compound inputs; original single-document limits remain."""
    return _guard(lambda kw: _prepare_live_history(kw, compound=True), locals())


def _live_rank_traces(rows, observed_at, activation_policy):
    import sialiveloop as live

    live._size(rows, live.activation.MAX_INPUT_BYTES)
    if type(rows) is not list or len(rows) > activation_policy["max_candidates"]:
        _fail("complete live candidate roster exceeds activation capacity")
    refs, traces = set(), {}
    for row in rows:
        _keys(row, {"row_ref", "origin", "trace"}, "live rank input")
        if not live._token(row["row_ref"], live.activation.MAX_SUBJECT_BYTES) \
                or row["row_ref"] in refs or type(row["origin"]) is not str or row["origin"] not in live._ORIGINS:
            _fail("live rank reference or origin is invalid")
        refs.add(row["row_ref"])
        trace = row["trace"]
        if trace is None:
            continue
        live.activation._trace(trace, observed_at, activation_policy)
        subject = trace["subject"]
        if subject in traces and not _same(trace, traces[subject]):
            _fail("duplicate version has conflicting live traces")
        traces[subject] = trace
    values = list(traces.values())
    live.activation._validate_set(values, observed_at, activation_policy)
    return values


def _rank_live_query(*, rows, observed_at, activation_policy):
    """Rank-only worker: no query, answers, classes, target coverage or metrics."""
    import sialiveloop as live

    traces = _live_rank_traces(rows, observed_at, activation_policy)
    ranked = live.activation.rank_traces(traces, observed_at=observed_at, policy=activation_policy)
    scores = {item["subject"]: item["score"] for item in ranked["activations"]}

    def key(row):
        score = None if row["trace"] is None else scores[row["trace"]["subject"]]
        return score is None, -score if score is not None else 0

    slots = {origin: iter(sorted((row for row in rows if row["origin"] == origin), key=key))
             for origin in live._ORIGINS}
    return {"order": [next(slots[row["origin"]])["row_ref"] for row in rows], "activation": ranked}


def _prepare_live_comparison(kw, *, compound=False):
    import sialiveloop as live

    _live_input_envelope(kw, comparison=True, compound=compound)
    policy = kw["ranking_policy"]
    _keys(policy, {"schema", "observed_at", "activation_policy", "activation_policy_sha256",
                   "ordering", "unavailable"}, "live ranking policy")
    _pin(policy, kw["expected_ranking_policy_sha256"])
    if policy["schema"] != "sia-cognitive-live-ranking-policy-v1" \
            or policy["ordering"] != "origin-slot-preserving-activation-v1" \
            or policy["unavailable"] != "last-within-origin-stable-v1" \
            or not live._integer(policy["observed_at"]):
        _fail("live ranking policy is unsupported")
    live.activation._policy(policy["activation_policy"])
    _pin(policy["activation_policy"], policy["activation_policy_sha256"])
    detached = copy.deepcopy(kw)
    policy = detached["ranking_policy"]
    raw = prepare_measurement(**detached["replay_inputs"])
    history = prepare_live_history_v2 if compound else prepare_live_history
    source = history(**{key: detached[key] for key in
        ("replay_inputs", "live_capture", "expected_live_capture_sha256")})
    if policy["observed_at"] < source["observed_at"]:
        _fail("ranking clock precedes complete captured history")
    if raw["split"] == "heldout" and raw["baseline"]["parameter_freeze"]["parameters"].get(
            "live_ranking_policy_sha256") != detached["expected_ranking_policy_sha256"]:
        _fail("heldout freeze does not bind the live ranking policy")
    live._size({"measurement_plan": raw, "live_history": source}, live.MAX_OUTPUT_BYTES)
    prepared = []
    for query, measured in zip(source["queries"], raw["queries"], strict=True):
        if query["id"] != measured["id"] or len(query["rows"]) != len(measured["row_coverage"]):
            _fail("live query and raw coverage rosters differ")
        rows = [{"row_ref": row["row_ref"], "origin": row["origin"],
                 "trace": None if row["history"] is None else row["history"]["trace"]}
                for row in query["rows"]]
        # Every query's complete trace population admits before the first
        # worker computes a score. Duplicate chunks never duplicate uses.
        _live_rank_traces(rows, policy["observed_at"], policy["activation_policy"])
        prepared.append((query["id"], rows, measured["row_coverage"]))
    orders, coverage, activation = {"raw-original": [], "live-use": []}, {"raw-original": {}, "live-use": {}}, []
    for identifier, rows, hits in prepared:
        input_sha256 = _sha(_canonical(rows))
        ranked = _rank_live_query(rows=rows, observed_at=policy["observed_at"],
                                  activation_policy=policy["activation_policy"])
        _pin(rows, input_sha256)
        refs = [row["row_ref"] for row in rows]
        order = ranked["order"]
        if type(order) is not list or any(type(ref) is not str for ref in order) \
                or len(order) != len(refs) or set(order) != set(refs):
            _fail("live order is not a complete raw-reference bijection")
        origins = {row["row_ref"]: row["origin"] for row in rows}
        if [origins[ref] for ref in order] != [row["origin"] for row in rows]:
            _fail("live order changed an origin slot")
        by_ref = dict(zip(refs, hits, strict=True))
        for name, sequence in (("raw-original", refs), ("live-use", order)):
            orders[name].append({"id": identifier, "order": sequence})
            coverage[name][identifier] = [{**by_ref[ref], "rank": rank}
                for rank, ref in enumerate(sequence, 1)]
        activation.append({"id": identifier, "receipt": ranked["activation"]})
    arms = []
    for name in ("raw-original", "live-use"):
        queries, classes, requests = _summarize_coverage(raw["protocol"], raw["baseline"]["queries"], coverage[name])
        if not _same(classes, raw["classes"]):
            _fail("live comparison changed measured class membership")
        if name == "raw-original" and any(not _same(value, raw[field]) for field, value in
                (("queries", queries), ("classes", classes), ("jackal_requests", requests))):
            _fail("live comparison changed original raw measurement")
        arms.append({"name": name, "query_orders": orders[name], "queries": queries,
                     "classes": classes, "jackal_requests": requests})
    return _finish({"schema": "sia-cognitive-live-comparison-v2" if compound else "sia-cognitive-live-comparison-v1",
        "status": "prepared-for-jackal",
        "arithmetic_status": "not-evaluated", "measurement_plan": raw, "live_history": source,
        "ranking_policy": policy, "ranking_policy_sha256": detached["expected_ranking_policy_sha256"],
        "activation": activation, "arms": arms, "non_claims": [
            "Activation is computed-unverified software output; metric expressions require JACKAL execution and do not establish a win.",
            "Origin-slot preservation and unavailable-last ordering are engineering policies, not a biological law.",
            "Ranking sees only version-use traces and row origins; the separately replayed target grader preserves every query and denominator.",
            "Raw rows, scores, latency observations and origins remain unchanged; no rerank latency was measured or inferred.",
            "Externally pinned held-out policies do not independently prove tuning chronology, independent samples or statistical power.",
            "All retained measurement, source, live-history and activation nonclaims remain controlling.",
        ]}, "comparison_sha256")


def prepare_live_comparison(*, replay_inputs, live_capture, expected_live_capture_sha256,
                            ranking_policy, expected_ranking_policy_sha256):
    """Prepare raw/live-use metric requests without rewriting the observation."""
    return _guard(_prepare_live_comparison, locals())


def prepare_live_comparison_v2(*, replay_inputs, live_capture, expected_live_capture_sha256,
                               ranking_policy, expected_ranking_policy_sha256):
    """Explicit compound input envelope; no automatic retry or output-cap change."""
    return _guard(lambda kw: _prepare_live_comparison(kw, compound=True), locals())
