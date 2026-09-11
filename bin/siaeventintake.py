"""Stateless collector-return projection with an explicit owning core.

No bound global core namespace, corpus lease, file observation, source cursor,
publication or numerical learning runs here. Supplied render plans carry their
declared source authority; absent index bytes are never reconstructed as fact.
"""

import siaeventplan as pages
import sialiveloop as live


SOURCE_NON_CLAIMS = (
    "These caller-supplied source selections and returns do not witness config.json, effective runtime configuration, installed sources, collector execution, cursor state, or acknowledgments.",
    "Completeness covers the declared collector-return roster only, not raw source records, omitted native history, or non-event controller observations.",
)
NON_CLAIMS = live.NON_CLAIMS + SOURCE_NON_CLAIMS + (
    "This pure projection binds supplied collector returns to frozen page versions; it does not publish a live generation, observe service output, settle source debt, or establish pulse/cursor/acknowledgment ordering.",
    "Event-page source hashes remain exact page-byte hashes; this projection does not synthesize a native capture, gist input, or pre-epoch use trace.",
    "Retained-epoch semantic and index provenance is inherited from the independently pinned render plan; this pure projection does not replay index bytes absent from that plan.",
)
_PROFILE = {
    "schema": "sia-controller-source-return-profile-v1",
    "scope": "source-return-frequency-not-raw-record-or-content-novelty-v1",
    "time_unit": "unix-seconds-integer", "symbol": "source-id-v1",
    "context": "controller-source-return", "source_order": "catalog-order-v1",
    "event_order": "collector-return-order-v1",
    "association_identity": "epoch-source-event-id-v1",
    "repeated_association": "retain-first-clock-version-and-metadata-v1",
    "native_timestamp": "first-normalized-event-ts-metadata-only-v1",
    "current_versions": "stable-subject-order-replace-exact-before-v1",
}
_DOCUMENTS = ("history", "source_catalog", "configuration", "profile", "live_policy")
_RETURN_KEYS = {
    "schema", "batch_id", "epoch_id", "observed_at", "complete",
    "configuration_sha256", "source_catalog_sha256", "profile_sha256",
    "live_policy_sha256", "runs", "non_claims", "returns_sha256",
}
_CATALOG_ROW = {"source_id", "collector", "organ", "custom_name"}


def _refuse(reason):
    error = ValueError("event live intake refused: " + reason)
    error.reason = reason
    error.non_claims = list(NON_CLAIMS)
    raise error


def _keys(value, expected, reason):
    if type(value) is not dict or set(value) != set(expected):
        _refuse(reason)


def _list(value, maximum, reason, *, nonempty=False):
    if type(value) is not list or len(value) > maximum or nonempty and not value:
        _refuse(reason)


def _mixed_size(owner, request, ceiling):
    """Count the whole framing; only the separately typed policy permits floats."""
    native = {key: None if key == "live_policy" else value
              for key, value in request.items()}
    count = (pages._size(native, ceiling)
             + live._size(request["live_policy"], ceiling)
             - pages._size(None, ceiling))
    if count > ceiling:
        _refuse("complete-input-capacity")
    return count


def _wire(owner, request):
    count = _mixed_size(owner, request, owner["MAX_STATE_JSON_BYTES"])
    raw = owner["json"].dumps(request, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) != count:
        _refuse("complete-input-byte-count")
    return raw


def _same(owner, left, right):
    return pages._json(owner, left) == pages._json(owner, right)


def _sha(owner, value):
    return pages._hash(owner, pages._json(owner, value))


def _source_nc(owner, value):
    if not _same(owner, value, list(SOURCE_NON_CLAIMS)):
        _refuse("source-nonclaims")


def _shape(owner, request):
    """Complete roster/shape/policy gates; no Event, copy, decoder or hash."""
    policy = request["live_policy"]
    live._policy(policy)
    _mixed_size(owner, request, min(owner["MAX_STATE_JSON_BYTES"],
                                   policy["limits"]["max_input_bytes"]))
    observed_at = request["observed_at"]
    if not live._integer(observed_at):
        _refuse("controller-clock")
    for name in _DOCUMENTS:
        pages._hex(request["expected_" + name + "_sha256"])
    configuration = request["configuration"]
    _keys(configuration, {"schema", "native_collectors", "custom_collectors", "non_claims"},
          "configuration-shape")
    if configuration["schema"] != "sia-controller-source-selection-v1":
        _refuse("configuration-schema")
    _source_nc(owner, configuration["non_claims"])
    for field in ("native_collectors", "custom_collectors"):
        _list(configuration[field], owner["MAX_SOURCE_REPLAY_EVENTS"], "selected-source-capacity")
    catalog = request["source_catalog"]
    _keys(catalog, {"schema", "configuration_sha256", "sources", "non_claims"}, "catalog-shape")
    if catalog["schema"] != "sia-controller-source-catalog-v1" \
            or catalog["configuration_sha256"] != request["expected_configuration_sha256"]:
        _refuse("catalog-configuration-binding")
    _source_nc(owner, catalog["non_claims"])
    _list(catalog["sources"], policy["encoding"]["max_symbols"], "complete-source-capacity", nonempty=True)
    source_ids = []
    for row in catalog["sources"]:
        _keys(row, _CATALOG_ROW, "catalog-source-shape")
        if any(type(row[key]) is not str or not row[key]
               for key in ("source_id", "collector", "organ")) \
                or row["custom_name"] is not None and type(row["custom_name"]) is not str:
            _refuse("catalog-source-identity")
        source_ids.append(row["source_id"])
    live.encoding._roster(source_ids, policy["encoding"]["max_symbols"], "symbols")
    profile = request["profile"]
    _keys(profile, set(_PROFILE) | {"live_policy_sha256", "non_claims"}, "profile-shape")
    if any(type(profile[key]) is not str or profile[key] != value for key, value in _PROFILE.items()) \
            or profile["live_policy_sha256"] != request["expected_live_policy_sha256"]:
        _refuse("profile-contract")
    _source_nc(owner, profile["non_claims"])
    live.encoding._roster([profile["context"]], policy["encoding"]["max_contexts"], "contexts")
    history = request["history"]
    _keys(history, {"schema", "epoch_id", "started_at", "complete", "entries", "non_claims"}, "history-shape")
    if history["schema"] != "sia-controller-event-history-v1" or history["complete"] is not True \
            or not live._token(history["epoch_id"]) or not live._integer(history["started_at"]) \
            or history["started_at"] > observed_at:
        _refuse("history-epoch-or-clock")
    _source_nc(owner, history["non_claims"])
    _list(history["entries"], owner["MAX_SOURCE_REPLAY_EVENTS"], "history-entry-capacity", nonempty=True)
    previous, batches, total_events = history["started_at"], set(), 0
    for entry in history["entries"]:
        _keys(entry, {"source_returns", "expected_source_returns_sha256", "event_batches"}, "entry-shape")
        returns = entry["source_returns"]
        _keys(returns, _RETURN_KEYS, "returns-shape")
        if returns["schema"] != "sia-controller-source-returns-v1" or returns["complete"] is not True \
                or returns["epoch_id"] != history["epoch_id"] or not live._token(returns["batch_id"]) \
                or returns["batch_id"] in batches or not live._integer(returns["observed_at"]) \
                or not previous <= returns["observed_at"] <= observed_at:
            _refuse("returns-identity-or-chronology")
        previous = returns["observed_at"]
        batches.add(returns["batch_id"])
        for name in ("configuration", "source_catalog", "profile", "live_policy"):
            if returns[name + "_sha256"] != request["expected_" + name + "_sha256"]:
                _refuse("epoch-policy-or-source-drift")
        _source_nc(owner, returns["non_claims"])
        pages._hex(entry["expected_source_returns_sha256"])
        if returns["returns_sha256"] != entry["expected_source_returns_sha256"]:
            _refuse("returns-pin")
        _list(returns["runs"], len(source_ids), "complete-collector-roster")
        if len(returns["runs"]) != len(source_ids):
            _refuse("complete-collector-roster")
        for source_id, run in zip(source_ids, returns["runs"]):
            _keys(run, {"source_id", "events"}, "collector-return-shape")
            if run["source_id"] != source_id:
                _refuse("collector-return-order")
            _list(run["events"], owner["MAX_SOURCE_REPLAY_EVENTS"], "returned-event-capacity")
            total_events += len(run["events"])
            if total_events > owner["MAX_SOURCE_REPLAY_EVENTS"]:
                _refuse("complete-returned-event-capacity")
            for record in run["events"]:
                _keys(record, {"organ", "ts", "kind", "summary", "links", "tags", "occurrence",
                               "event_id", "semantic_id"}, "returned-event-shape")
                if any(type(record[key]) is not str for key in (
                        "organ", "ts", "kind", "summary", "occurrence", "event_id", "semantic_id")):
                    _refuse("returned-event-type")
                pages._hex(record["event_id"])
                pages._hex(record["semantic_id"])
        _list(entry["event_batches"], owner["MAX_SOURCE_REPLAY_EVENTS"], "event-batch-capacity")
        for row in entry["event_batches"]:
            _keys(row, {"batch", "expected_batch_sha256"}, "event-batch-wrapper")
            batch = row["batch"]
            _keys(batch, pages.BATCH_KEYS, "event-batch-shape")
            pages._hex(row["expected_batch_sha256"])
            if batch["batch_sha256"] != row["expected_batch_sha256"]:
                _refuse("event-batch-pin")
            pages._member_structure(owner, batch["members"])
    if previous != observed_at:
        _refuse("final-controller-clock")


def _bindings(request):
    return {**{name + "_sha256": request["expected_" + name + "_sha256"] for name in _DOCUMENTS},
            "observed_at": request["observed_at"]}


def _source_nonclaims(request):
    history = request["history"]
    return {
        **{name: request[name]["non_claims"] for name in ("configuration", "source_catalog", "profile")},
        "history": history["non_claims"],
        "source_returns": [{"returns_sha256": entry["expected_source_returns_sha256"],
                            "non_claims": entry["source_returns"]["non_claims"]} for entry in history["entries"]],
        "event_batches": [{"batch_sha256": row["expected_batch_sha256"],
                           "non_claims": row["batch"]["non_claims"]}
                          for entry in history["entries"] for row in entry["event_batches"]],
        "live_loop": list(live.NON_CLAIMS),
    }


def _intake(request):
    return {"schema": "sia-live-intake-v1", "epoch_id": request["history"]["epoch_id"],
            "started_at": request["history"]["started_at"], "complete": True,
            "pages": [], "current_versions": [],
            "symbols": [row["source_id"] for row in request["source_catalog"]["sources"]],
            "contexts": [request["profile"]["context"]], "observations": []}


def _result(request, intake, associations):
    return {"schema": "sia-event-live-intake-projection-v1", "status": "prepared-not-published",
            "bindings": _bindings(request), "associations": associations, "intake": intake,
            "intake_sha256": "0" * 64, "source_non_claims": _source_nonclaims(request),
            "non_claims": list(NON_CLAIMS), "projection_sha256": "0" * 64}


def _reserve(owner, request):
    """Reserve full variable output before decoding, copying or hashing.

    An unescaped content placeholder reserves the JSON maximum per raw byte;
    digest placeholders have the exact fixed digest width. Every association
    and every retained upstream nonclaim remains counted, without deduping it.
    """
    intake, associations, versions, observations, subjects = _intake(request), [], {}, set(), set()
    content_reserve = 0
    policy = request["live_policy"]
    for entry in request["history"]["entries"]:
        max_slug = ""
        for row in entry["event_batches"]:
            for plan in row["batch"]["members"]:
                for page in plan["pages"]:
                    slug = page["slug"]
                    if pages._text_size(slug, owner["MAX_STATE_JSON_BYTES"]) > pages._text_size(max_slug, owner["MAX_STATE_JSON_BYTES"]):
                        max_slug = slug
                    subjects.add(slug)
                    for image in (page["before"], page):
                        if image is None:
                            continue
                        if image["raw_bytes"] > policy["limits"]["max_content_bytes"]:
                            _refuse("complete-content-capacity")
                        # Before images have no supplied version digest; use
                        # their exact subject/raw digest pair as a reservation
                        # key. This also deduplicates the same target bytes.
                        key = (slug, image["raw_sha256"])
                        if key not in versions:
                            versions[key] = {"subject": slug, "content": "", "origin": "legacy-unlabeled",
                                             "source_sha256": "0" * 64, "content_sha256": "0" * 64,
                                             "version_sha256": "0" * 64}
                            content_reserve += image["raw_bytes"] * len("\\u0000")
        for run in entry["source_returns"]["runs"]:
            for position, record in enumerate(run["events"]):
                association = {"source_returns_sha256": entry["expected_source_returns_sha256"],
                               "source_id": run["source_id"], "return_index": position,
                               "event_id": record["event_id"], "semantic_id": record["semantic_id"],
                               "admission": {"event_batch_sha256": "0" * 64, "plan_sha256": "0" * 64,
                                             "slug": max_slug, "version_sha256": "0" * 64,
                                             "disposition": "retained-epoch"},
                               "observation_id": "0" * 64, "observation_version_sha256": "0" * 64,
                               "observation_timestamp": request["observed_at"], "status": "first-observation"}
                associations.append(association)
                key = (run["source_id"], record["event_id"])
                if key not in observations:
                    observations.add(key)
                    intake["observations"].append({"id": "0" * 64, "timestamp": request["observed_at"],
                                                   "version_sha256": "0" * 64, "symbol": run["source_id"],
                                                   "context": request["profile"]["context"],
                                                   "native_timestamp": record["ts"]})
    if len(versions) > policy["limits"]["max_versions"] \
            or len(observations) > policy["limits"]["max_observations"]:
        _refuse("complete-version-or-observation-capacity")
    intake["pages"] = list(versions.values())
    intake["current_versions"] = ["0" * 64 for _subject in subjects]
    limit = min(owner["MAX_STATE_JSON_BYTES"], policy["limits"]["max_output_bytes"])
    if pages._size(_result(request, intake, associations), limit) + content_reserve > limit:
        _refuse("complete-output-capacity")


def _catalog(owner, request):
    configuration, catalog = request["configuration"], request["source_catalog"]
    expected = []
    for collector in configuration["native_collectors"]:
        if type(collector) is not str or collector not in owner["_SENSE_ORGAN"]:
            _refuse("unknown-native-selection")
        expected.append({"source_id": collector, "collector": collector,
                         "organ": owner["_SENSE_ORGAN"][collector], "custom_name": None})
    for row in configuration["custom_collectors"]:
        _keys(row, {"name", "organ", "description", "path", "type", "enabled",
                    "match", "exclude", "field", "kind", "tags"}, "custom-selection-shape")
        if row["enabled"] is not True:
            _refuse("disabled-custom-selection")
        path = row["path"]
        if type(path) is not str or "\x00" in path \
                or not owner["os"].path.isabs(path) \
                or owner["os"].path.normpath(path) != path:
            _refuse("custom-selection-path")
        normalized = owner["_validated_custom_sense_entry"](row)
        if normalized is None or normalized["name"] != row["name"] \
                or normalized["organ"] != row["organ"] or normalized["path"] != path:
            _refuse("custom-selection-canonical-identity")
        expected.append({"source_id": normalized["source_id"], "collector": "sense_custom",
                         "organ": normalized["organ"], "custom_name": normalized["name"]})
    if len({row["source_id"] for row in expected}) != len(expected) \
            or not _same(owner, expected, catalog["sources"]):
        _refuse("source-catalog-selection-binding")


def _pins(owner, request):
    for name in _DOCUMENTS:
        value = request[name]
        raw = live._canonical(value) if name == "live_policy" else pages._json(owner, value)
        if pages._hash(owner, raw) != request["expected_" + name + "_sha256"]:
            _refuse("external-document-pin")
    for entry in request["history"]["entries"]:
        returns = entry["source_returns"]
        if _sha(owner, {key: value for key, value in returns.items() if key != "returns_sha256"}) \
                != entry["expected_source_returns_sha256"]:
            _refuse("source-return-body-pin")


def _member(owner, plan, images):
    """Validate supplied exact Events and represented target semantics, not I/O."""
    records, prepared = {}, {}
    for record in plan["input_records"]:
        event = owner["_event_from_replay_record"](record)
        if event.organ != plan["organ"] or record["ts"][:10] != plan["date"] \
                or not _same(owner, owner["_event_replay_record"](event), record):
            _refuse("plan-record-binding")
        line, payload, _base = owner["_event_line"](event, record["event_id"], record["semantic_id"])
        value = (record["semantic_id"], payload)
        prior = records.get(record["event_id"])
        if prior is not None and prior != value:
            _refuse("plan-occurrence-conflict")
        records[record["event_id"]] = value
        prepared.setdefault(record["event_id"], line)
    if [row["event_id"] for row in plan["admissions"]] != list(records):
        _refuse("complete-plan-admissions")
    targets, before_lines, epochs = {}, {}, {}
    page_by_slug = {page["slug"]: page for page in plan["pages"]}
    day_parts = {}
    for page in plan["pages"]:
        slug = page["slug"]
        image = images[slug + ".md"]
        if slug.startswith("events/"):
            organ, date, part = owner["_event_source_parts"](slug + ".md")
            state = owner["_event_page_state"](
                organ, date, part, dependency_capture=pages._TargetView(owner, slug, image["raw"]))
            targets[slug] = state["bullets"]
            before_lines[slug] = [] if image["before"] is None else pages._entries(owner, image["before"])
            if date == plan["date"]:
                day_parts[part] = slug
        else:
            epochs[slug] = owner["_read_epoch_state"](
                slug, dependency_capture=pages._TargetView(owner, slug, image["raw"]))
    files = {row["relative"]: row["before"] for row in plan["read_dependencies"]["files"]}
    additions, appended = {}, []
    for admission in plan["admissions"]:
        event_id, slug = admission["event_id"], admission["slug"]
        if slug not in page_by_slug or admission["semantic_id"] != records[event_id][0] \
                or admission["version_sha256"] != page_by_slug[slug]["version_sha256"]:
            _refuse("admission-version-or-semantic-binding")
        disposition = admission["disposition"]
        if disposition == "retained-epoch":
            if slug not in epochs or page_by_slug[slug]["write"]:
                _refuse("retained-epoch-target")
            epoch = epochs[slug]
            if epoch["event_ids_declared"] and event_id not in epoch["event_ids"]:
                _refuse("epoch-occurrence-roster")
            relative = owner["_event_index_relative"](plan["organ"], event_id)
            if relative not in files or files[relative] is None:
                _refuse("missing-pinned-epoch-index-dependency")
            continue
        if slug not in targets:
            _refuse("event-admission-target")
        matches = [owner["EVENT_MARKER_RE"].fullmatch(line) for line in targets[slug]]
        matches = [match for match in matches if match is not None and match.group("id") == event_id]
        if len(matches) != 1 or (matches[0].group("semantic"), matches[0].group("payload")) != records[event_id]:
            _refuse("exact-event-marker-binding")
        if disposition == "appended":
            if not page_by_slug[slug]["write"] or prepared[event_id] not in targets[slug]:
                _refuse("appended-event-image")
            additions.setdefault(slug, []).append(prepared[event_id])
            appended.append(event_id)
        elif disposition == "retained-day":
            if matches[0].group(0) not in before_lines[slug]:
                _refuse("retained-event-before-image")
        else:
            _refuse("admission-disposition")
    if plan["appended_event_ids"] != appended:
        _refuse("complete-appended-roster")
    for page in plan["pages"]:
        if page["write"] and (not additions.get(page["slug"]) or targets[page["slug"]]
                              != before_lines[page["slug"]] + additions[page["slug"]]):
            _refuse("exact-event-entry-preservation")
    parts = sorted(day_parts)
    if any(part != position for position, part in enumerate(parts, start=1)):
        _refuse("day-page-contiguity")
    expected_days = [day_parts[part] for part in parts] or [owner["_event_shard_slug"](plan["organ"], plan["date"], 1)]
    if plan["day_slugs"] != expected_days \
            or set(page_by_slug) != set(day_parts.values()) | {row["slug"] for row in plan["admissions"]}:
        _refuse("complete-target-page-roster")


def _fold_entry(owner, request, entry, intake, associations, versions, current, first):
    """Apply one already-admitted entry to private replay accumulators.

    This is a shared semantic kernel, not an admission or checkpoint API.
    The caller must validate shapes/pins, reserve output capacity and own a
    detached accumulator. Failure may leave that private accumulator partial;
    it must never be published. No earlier entry is decoded by this kernel.
    """
    catalog = request["source_catalog"]["sources"]
    returns, grouped, admissions = entry["source_returns"], {}, {}
    for source, run in zip(catalog, returns["runs"]):
        for record in run["events"]:
            event = owner["_event_from_replay_record"](record)
            if event.organ != source["organ"] \
                    or not _same(owner, owner["_event_replay_record"](event), record):
                _refuse("collector-event-binding")
            grouped.setdefault((event.organ, record["ts"][:10]), []).append(record)
    actual_groups, organs = set(), []
    for row in entry["event_batches"]:
        batch = row["batch"]
        members = pages._member_structure(owner, batch["members"])
        body = pages._batch_body(owner, members)
        if not _same(owner, body, {key: value for key, value in batch.items() if key != "batch_sha256"}) \
                or _sha(owner, body) != row["expected_batch_sha256"]:
            _refuse("batch-original-body-or-pin")
        pages._member_pins(owner, batch["members"], [plan["plan_sha256"] for plan in batch["members"]])
        images = pages._union_images(owner, members)
        organs.append(batch["organ"])
        for plan in members:
            key = (plan["organ"], plan["date"])
            if key in actual_groups or key not in grouped or not _same(owner, grouped[key], plan["input_records"]):
                _refuse("complete-duplicate-return-plan-join")
            actual_groups.add(key)
            _member(owner, plan, images)
            for admitted in plan["admissions"]:
                admissions[(plan["organ"], plan["date"], admitted["event_id"])] = {
                    "event_batch_sha256": row["expected_batch_sha256"], "plan_sha256": plan["plan_sha256"],
                    **{key: admitted[key] for key in ("slug", "version_sha256", "disposition")}}
        for image in images.values():
            slug = image["page"]["slug"]
            if slug in current and (image["before"] is None
                                    or versions[current[slug]]["content"].encode("utf-8") != image["before"]):
                _refuse("unexplained-page-version-change")
            for raw in (image["before"], image["raw"]):
                if raw is None:
                    continue
                version = owner["_corpus_page_version_from_bytes"](slug=slug, raw=raw)
                pin = version["version_sha256"]
                if pin in versions and not _same(owner, version, versions[pin]):
                    _refuse("page-version-collision")
                if pin not in versions:
                    versions[pin] = version
                current[slug] = pin
    if actual_groups != set(grouped) or organs != sorted(set(organs)):
        _refuse("complete-event-batch-roster")
    for run in returns["runs"]:
        for position, record in enumerate(run["events"]):
            key = (run["source_id"], record["event_id"])
            admitted = admissions[(record["organ"], record["ts"][:10], record["event_id"])]
            if key not in first:
                identifier = _sha(owner, {"schema": "sia-controller-event-association-v1",
                                          "epoch_id": intake["epoch_id"], "source_id": key[0], "event_id": key[1]})
                observation = {"id": identifier, "timestamp": returns["observed_at"],
                               "version_sha256": admitted["version_sha256"], "symbol": key[0],
                               "context": request["profile"]["context"], "native_timestamp": record["ts"]}
                first[key] = (record["semantic_id"], observation)
                intake["observations"].append(observation)
                status = "first-observation"
            else:
                semantic, observation = first[key]
                if semantic != record["semantic_id"]:
                    _refuse("repeated-source-association-conflict")
                status = "already-observed"
            associations.append({"source_returns_sha256": entry["expected_source_returns_sha256"],
                                 "source_id": key[0], "return_index": position, "event_id": key[1],
                                 "semantic_id": record["semantic_id"], "admission": admitted,
                                 "observation_id": observation["id"],
                                 "observation_version_sha256": observation["version_sha256"],
                                 "observation_timestamp": observation["timestamp"], "status": status})


def _project(owner, request):
    intake, associations, versions, current, first = _intake(request), [], {}, {}, {}
    for entry in request["history"]["entries"]:
        _fold_entry(owner, request, entry, intake, associations, versions, current, first)
    intake["pages"], intake["current_versions"] = list(versions.values()), list(current.values())
    return _result(request, intake, associations)


def prepare(owner, **request):
    """Admit one complete supplied history and return only a detached projection."""
    try:
        expected_keys = set(_DOCUMENTS) | {"expected_" + name + "_sha256" for name in _DOCUMENTS} | {"observed_at"}
        _keys(request, expected_keys, "request-shape")
        _mixed_size(owner, request, min(owner["MAX_STATE_JSON_BYTES"], live.MAX_INPUT_BYTES))
        original = _wire(owner, request)
        _shape(owner, request)
        _reserve(owner, request)
        if _wire(owner, request) != original:
            _refuse("input-changed-during-admission")
        admitted = owner["copy"].deepcopy(request)
        if _wire(owner, admitted) != original or _wire(owner, request) != original:
            _refuse("input-copy-change")
        _pins(owner, admitted)
        _catalog(owner, admitted)
        result = _project(owner, admitted)
        intake = result["intake"]
        # This is policy/trace validation only; it does not run encoding,
        # activation, workspace, co-retrieval or any gist computation.
        live._inputs(intake, {"schema": "sia-live-deliveries-v1", "epoch_id": intake["epoch_id"],
                              "complete": True, "records": []}, admitted["live_policy"], admitted["observed_at"])
        intake_bytes = pages._json(owner, intake)
        before_digest = pages._json(owner, result)
        intake_sha256 = pages._hash(owner, intake_bytes)
        if pages._json(owner, intake) != intake_bytes \
                or pages._json(owner, result) != before_digest:
            _refuse("result-changed-during-intake-digest")
        result["intake_sha256"] = intake_sha256
        before_digest = pages._json(owner, result)
        projection_bytes = pages._json(owner, {
            key: value for key, value in result.items() if key != "projection_sha256"})
        projection_sha256 = pages._hash(owner, projection_bytes)
        if pages._json(owner, intake) != intake_bytes \
                or pages._json(owner, result) != before_digest:
            _refuse("result-changed-during-projection-digest")
        result["projection_sha256"] = projection_sha256
        limit = min(owner["MAX_STATE_JSON_BYTES"], admitted["live_policy"]["limits"]["max_output_bytes"])
        pages._size(result, limit)
        original_result = pages._json(owner, result)
        detached = owner["copy"].deepcopy(result)
        if pages._json(owner, result) != original_result \
                or pages._json(owner, detached) != original_result \
                or _wire(owner, admitted) != original or _wire(owner, request) != original:
            _refuse("result-or-input-changed")
        return detached
    except (ValueError, RuntimeError) as exc:
        if getattr(exc, "non_claims", None) == list(NON_CLAIMS):
            raise
        error = ValueError("event live intake refused: upstream-admission")
        error.reason = "upstream-admission"
        error.non_claims = list(NON_CLAIMS)
        error.upstream_reason = getattr(exc, "reason", None)
        error.upstream_non_claims = list(getattr(exc, "non_claims", ()))
        raise error from exc
    except (KeyError, TypeError, AttributeError, RecursionError) as exc:
        error = ValueError("event live intake refused: malformed-input")
        error.reason = "malformed-input"
        error.non_claims = list(NON_CLAIMS)
        raise error from exc
