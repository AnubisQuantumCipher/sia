"""Bound closed multi-document calls without widening any document's ceiling.

Layouts are fixed by the calling component's versioned contract, never taken
from an evidence artifact. None marks a complete document or scalar pin;
dictionary nodes specify every permitted envelope field. Admission neither
authenticates these documents nor replaces their semantic/source replay gates.
No partial envelope, ignored field, shared-reference discount or copied result
is produced.  The separately versioned exposure codec below interns repeated
represented records; its decoder reconstructs and rechecks the complete legacy
artifact before returning it.  Existing single-artifact and v1 APIs remain
unchanged.
"""

import copy

import siacognitivebaseline as baseline


MAX_INPUT_BYTES = 67108864
MAX_DOCUMENT_BYTES = baseline.MAX_ARTIFACT_BYTES
MAX_LAYOUT_BYTES = 16384
_INTERNED_SCHEMA = "sia-cognitive-event-exposure-interned-v1"
_EXPOSURE_SCHEMA = "sia-cognitive-event-exposure-v1"
_EXPOSURE_STATUS = "computed-unverified"
_INTERNED_FIELDS = {
    "schema", "status", "source_schema", "source_sha256", "root", "tables",
    "artifact_sha256",
}
_ROOT_FIELDS = {"value", "source_record_refs", "query_refs"}
_TABLES = ("source_records", "queries", "candidates", "occurrences")
_PLAIN_ENTRY_FIELDS = {"ref", "sha256", "value"}
_QUERY_ENTRY_FIELDS = {*_PLAIN_ENTRY_FIELDS, "candidate_refs"}
_CANDIDATE_ENTRY_FIELDS = {*_PLAIN_ENTRY_FIELDS, "occurrence_refs"}
_PREFIXES = {
    "source_records": "source-record:",
    "queries": "query:",
    "candidates": "candidate:",
    "occurrences": "occurrence:",
}


class EnvelopeRefusal(ValueError):
    """The complete envelope or a constituent document exceeds its contract."""


def _fail(reason):
    raise EnvelopeRefusal("cognitive envelope refused: " + reason)


def _limits(max_input_bytes, max_document_bytes):
    for limit, ceiling in ((max_input_bytes, MAX_INPUT_BYTES),
                           (max_document_bytes, MAX_DOCUMENT_BYTES)):
        if type(limit) is not int or not 0 < limit <= ceiling:
            _fail("a declared limit is invalid or exceeds its hard ceiling")
    if max_document_bytes > max_input_bytes:
        _fail("document limit exceeds the complete envelope limit")


def _keys(value, expected, label):
    if type(value) is not dict or set(value) != set(expected):
        _fail(label + " fields are invalid")


def _sha(value, maximum):
    return baseline._sha(baseline._canonical(value, maximum))


def _body_sha(value, field, maximum):
    return _sha({key: item for key, item in value.items() if key != field}, maximum)


def _reference(table, value, maximum):
    digest = _sha(value, maximum)
    return _PREFIXES[table] + digest, digest


def _unique_refs(value, table, label):
    if type(value) is not list:
        _fail(label + " reference roster is invalid")
    prefix = _PREFIXES[table]
    seen = set()
    for reference in value:
        if type(reference) is not str or not reference.startswith(prefix) \
                or not baseline._digest(reference[len(prefix):]) or reference in seen:
            _fail(label + " reference roster is malformed, foreign, or duplicated")
        seen.add(reference)
    return value


def _exposure_source(value, maximum):
    """Admit the representation topology, not its upstream semantic claims."""
    if type(value) is not dict or value.get("schema") != _EXPOSURE_SCHEMA \
            or value.get("status") != _EXPOSURE_STATUS:
        _fail("source exposure has no supported schema or status")
    if type(value.get("event_population")) is not list \
            or type(value.get("queries")) is not list:
        _fail("source exposure has no complete record and query rosters")
    if not baseline._digest(value.get("artifact_sha256")) \
            or value["artifact_sha256"] != _body_sha(value, "artifact_sha256", maximum):
        _fail("source exposure artifact identity is invalid")
    for record in value["event_population"]:
        if type(record) is not dict:
            _fail("source exposure record is invalid")
    for query in value["queries"]:
        if type(query) is not dict or type(query.get("candidates")) is not list:
            _fail("source exposure query is invalid")
        for candidate in query["candidates"]:
            if type(candidate) is not dict or type(candidate.get("exposures")) is not list:
                _fail("source exposure candidate is invalid")
            if any(type(occurrence) is not dict for occurrence in candidate["exposures"]):
                _fail("source exposure occurrence is invalid")


def intern_exposure(*, exposure, max_input_bytes, max_document_bytes):
    """Return a detached, content-addressed representation of exposure v1.

    This changes storage shape only.  It neither replays the source artifact
    nor promotes its ``computed-unverified`` status.
    """
    try:
        _limits(max_input_bytes, max_document_bytes)
        # Bound and serialize the complete source before hashing or copying it.
        baseline._bounded(exposure, max_document_bytes)
        source_raw = baseline._canonical(exposure, max_document_bytes)
        _exposure_source(exposure, max_document_bytes)

        tables = {name: [] for name in _TABLES}
        seen = {name: {} for name in _TABLES}

        def add(table, original, entry):
            reference = entry["ref"]
            raw = baseline._canonical(original, max_document_bytes)
            previous = seen[table].get(reference)
            if previous is not None:
                if previous != raw:
                    _fail("content-addressed exposure record collides")
                return reference
            seen[table][reference] = raw
            tables[table].append(entry)
            return reference

        source_refs = []
        for record in exposure["event_population"]:
            reference, digest = _reference("source_records", record, max_document_bytes)
            source_refs.append(add(
                "source_records", record,
                {"ref": reference, "sha256": digest, "value": copy.deepcopy(record)}))
        _unique_refs(source_refs, "source_records", "source record")

        query_refs = []
        for query in exposure["queries"]:
            candidate_refs = []
            for candidate in query["candidates"]:
                occurrence_refs = []
                for occurrence in candidate["exposures"]:
                    reference, digest = _reference(
                        "occurrences", occurrence, max_document_bytes)
                    occurrence_refs.append(add(
                        "occurrences", occurrence,
                        {"ref": reference, "sha256": digest,
                         "value": copy.deepcopy(occurrence)}))
                _unique_refs(occurrence_refs, "occurrences", "candidate occurrence")
                reference, digest = _reference(
                    "candidates", candidate, max_document_bytes)
                value = {key: copy.deepcopy(item) for key, item in candidate.items()
                         if key != "exposures"}
                candidate_refs.append(add(
                    "candidates", candidate,
                    {"ref": reference, "sha256": digest, "value": value,
                     "occurrence_refs": occurrence_refs}))
            _unique_refs(candidate_refs, "candidates", "query candidate")
            reference, digest = _reference("queries", query, max_document_bytes)
            value = {key: copy.deepcopy(item) for key, item in query.items()
                     if key != "candidates"}
            query_refs.append(add(
                "queries", query,
                {"ref": reference, "sha256": digest, "value": value,
                 "candidate_refs": candidate_refs}))
        _unique_refs(query_refs, "queries", "root query")

        root_value = {key: copy.deepcopy(item) for key, item in exposure.items()
                      if key not in ("event_population", "queries")}
        body = {
            "schema": _INTERNED_SCHEMA,
            "status": exposure["status"],
            "source_schema": exposure["schema"],
            "source_sha256": baseline._sha(source_raw),
            "root": {
                "value": root_value,
                "source_record_refs": source_refs,
                "query_refs": query_refs,
            },
            "tables": tables,
        }
        result = {**body, "artifact_sha256": _sha(body, max_document_bytes)}
        # The compact representation is itself one complete document.  A
        # useful interning result that does not fit the old ceiling refuses.
        baseline._canonical(result, max_document_bytes)
        return result
    except EnvelopeRefusal:
        raise
    except (baseline.BaselineRefusal, ValueError, TypeError, KeyError,
            OverflowError, RecursionError) as exc:
        raise EnvelopeRefusal(
            "cognitive envelope could not intern exposure: " + str(exc)) from exc


def expand_interned_exposure(*, interned, max_input_bytes, max_document_bytes):
    """Validate a closed interned topology and reconstruct exposure v1."""
    try:
        _limits(max_input_bytes, max_document_bytes)
        # Admission and the outer identity precede every detached copy.
        baseline._bounded(interned, max_document_bytes)
        baseline._canonical(interned, max_document_bytes)
        _keys(interned, _INTERNED_FIELDS, "interned exposure")
        if interned["schema"] != _INTERNED_SCHEMA \
                or interned["status"] != _EXPOSURE_STATUS \
                or interned["source_schema"] != _EXPOSURE_SCHEMA \
                or not baseline._digest(interned["source_sha256"]) \
                or not baseline._digest(interned["artifact_sha256"]):
            _fail("interned exposure has no supported schema, status, or identity")
        if interned["artifact_sha256"] != _body_sha(
                interned, "artifact_sha256", max_document_bytes):
            _fail("interned exposure artifact identity is invalid")

        root, tables = interned["root"], interned["tables"]
        _keys(root, _ROOT_FIELDS, "interned exposure root")
        _keys(tables, set(_TABLES), "interned exposure tables")
        if type(root["value"]) is not dict \
                or "event_population" in root["value"] or "queries" in root["value"]:
            _fail("interned exposure root value is invalid")

        maps = {}
        for table in _TABLES:
            rows = tables[table]
            if type(rows) is not list:
                _fail("interned exposure table is invalid")
            expected = _PLAIN_ENTRY_FIELDS
            if table == "queries":
                expected = _QUERY_ENTRY_FIELDS
            elif table == "candidates":
                expected = _CANDIDATE_ENTRY_FIELDS
            mapped = {}
            for row in rows:
                _keys(row, expected, table + " entry")
                reference, digest, value = row["ref"], row["sha256"], row["value"]
                if type(reference) is not str or not baseline._digest(digest) \
                        or reference != _PREFIXES[table] + digest \
                        or reference in mapped or type(value) is not dict:
                    _fail(table + " entry is malformed, foreign, or duplicated")
                if table in ("source_records", "occurrences") \
                        and digest != _sha(value, max_document_bytes):
                    _fail(table + " entry hash does not bind its represented value")
                if table == "queries":
                    if "candidates" in value:
                        _fail("query entry embeds candidates outside its reference roster")
                    _unique_refs(row["candidate_refs"], "candidates", "query candidate")
                elif table == "candidates":
                    if "exposures" in value:
                        _fail("candidate entry embeds occurrences outside its reference roster")
                    _unique_refs(row["occurrence_refs"], "occurrences", "candidate occurrence")
                mapped[reference] = row
            maps[table] = mapped

        used = {name: set() for name in _TABLES}

        def resolve(reference, table, label):
            if type(reference) is not str or not reference.startswith(_PREFIXES[table]):
                _fail(label + " reference is foreign")
            row = maps[table].get(reference)
            if row is None:
                _fail(label + " reference is missing")
            used[table].add(reference)
            return row

        source_refs = _unique_refs(
            root["source_record_refs"], "source_records", "root source record")
        event_population = [copy.deepcopy(
            resolve(reference, "source_records", "source record")["value"])
            for reference in source_refs]

        query_refs = _unique_refs(root["query_refs"], "queries", "root query")
        queries = []
        for query_ref in query_refs:
            query_row = resolve(query_ref, "queries", "query")
            candidate_refs = _unique_refs(
                query_row["candidate_refs"], "candidates", "query candidate")
            candidates = []
            for candidate_ref in candidate_refs:
                candidate_row = resolve(candidate_ref, "candidates", "candidate")
                occurrence_refs = _unique_refs(
                    candidate_row["occurrence_refs"], "occurrences",
                    "candidate occurrence")
                occurrences = [copy.deepcopy(
                    resolve(reference, "occurrences", "occurrence")["value"])
                    for reference in occurrence_refs]
                candidate = {**copy.deepcopy(candidate_row["value"]),
                             "exposures": occurrences}
                if candidate_row["sha256"] != _sha(candidate, max_document_bytes):
                    _fail("candidate entry hash does not bind its complete value")
                candidates.append(candidate)
            query = {**copy.deepcopy(query_row["value"]), "candidates": candidates}
            if query_row["sha256"] != _sha(query, max_document_bytes):
                _fail("query entry hash does not bind its complete value")
            queries.append(query)

        for table in _TABLES:
            if used[table] != set(maps[table]):
                _fail(table + " table contains an unreferenced or foreign record")

        source = {**copy.deepcopy(root["value"]),
                  "event_population": event_population, "queries": queries}
        if source.get("schema") != interned["source_schema"] \
                or source.get("status") != interned["status"] \
                or interned["source_sha256"] != _sha(source, max_document_bytes):
            _fail("reconstructed exposure order or source identity changed")
        _exposure_source(source, max_document_bytes)
        baseline._canonical(source, max_document_bytes)
        return source
    except EnvelopeRefusal:
        raise
    except (baseline.BaselineRefusal, ValueError, TypeError, KeyError,
            OverflowError, RecursionError) as exc:
        raise EnvelopeRefusal(
            "cognitive envelope could not expand exposure: " + str(exc)) from exc


def admit_compound(*, envelope, layout, max_input_bytes, max_document_bytes):
    """Admit a caller-declared closed topology; return no data or assurance."""
    try:
        for limit, ceiling in ((max_input_bytes, MAX_INPUT_BYTES),
                               (max_document_bytes, MAX_DOCUMENT_BYTES)):
            if type(limit) is not int or not 0 < limit <= ceiling:
                _fail("a declared limit is invalid or exceeds its hard ceiling")
        if max_document_bytes > max_input_bytes:
            _fail("document limit exceeds the complete envelope limit")
        if type(layout) is not dict:
            _fail("layout root must be a closed dictionary")
        baseline._bounded(layout, MAX_LAYOUT_BYTES)
        # Complete shape/domain admission precedes all serialization, including
        # earlier documents when a later branch is cyclic or nonfinite.
        baseline._bounded(envelope, max_input_bytes)
        documents = []

        def visit(value, node):
            if node is None:
                baseline._bounded(value, max_document_bytes)
                documents.append(value)
                return
            if type(node) is not dict or type(value) is not dict or set(value) != set(node):
                _fail("envelope differs from its complete closed document layout")
            for key, child in node.items():
                visit(value[key], child)

        visit(envelope, layout)
        # Structural work bounds are not exact JSON byte counts. Enforce both
        # original document wire limits and the declared aggregate wire limit.
        # Shared document references are counted each time they occur on wire.
        for document in documents:
            baseline._canonical(document, max_document_bytes)
        baseline._canonical(envelope, max_input_bytes)
    except EnvelopeRefusal:
        raise
    except (baseline.BaselineRefusal, ValueError, TypeError, KeyError,
            OverflowError, RecursionError) as exc:
        raise EnvelopeRefusal("cognitive envelope could not be admitted: " + str(exc)) from exc
