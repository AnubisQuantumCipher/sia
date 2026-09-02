"""SIA's graph-projection, domain-edge, and export implementation.

This module deliberately does not import `sialib`.  SIA's core may be loaded
under a dynamic test alias, so importing a canonical core module here would
create a second, stale runtime state.  The owning core binds its current
namespace immediately before each public call instead.

Constants (STATUS_PATH, GRAPH_PATH, MAX_GRAPH_*, MAX_SCHEMA_PACK_*, the
domain-lane frozensets) and the GraphProjectionPending class remain owned by
sialib and arrive through bind(); tests patch them on the sialib module and
the per-call rebind keeps intra-module reads current.
"""

import threading as _threading


def _graph_projection_state_path():
    return os.path.join(
        os.path.dirname(GRAPH_PATH) or STATE, "graph-projection.json")


def _fresh_graph_projection_state():
    cutoff = iso(utcnow() - datetime.timedelta(days=14))
    return {
        "schema": GRAPH_PROJECTION_SCHEMA,
        "generation": uuid.uuid4().hex,
        "phase": "scan",
        "started_at": iso(),
        "cutoff": cutoff,
        "queue": [{"relative": "", "levels": MAX_GRAPH_TREE_LEVELS,
                   "page": {}}],
        "candidates": [],
        "pages_seen": 0,
        "eligible_seen": 0,
        "failed_ops": [],
    }


def _append_graph_failure(failures, failure):
    """Retain bounded unique refusals plus one stable overflow marker."""
    failure = str(failure)[:MAX_CONFIG_TEXT_CHARS]
    if not failure or failure in failures \
            or "graph_failure_capacity" in failures:
        return
    if len(failures) < MAX_GRAPH_SCAN_ENTRIES:
        failures.append(failure)
        return
    failures[-1] = "graph_failure_capacity"


def _record_graph_failure(state, failure):
    _append_graph_failure(state["failed_ops"], failure)


def _canonical_graph_projection_state(value):
    if not isinstance(value, dict) \
            or value.get("schema") != GRAPH_PROJECTION_SCHEMA \
            or value.get("phase") not in {"scan", "ready"} \
            or not isinstance(value.get("generation"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", value["generation"]) is None \
            or not isinstance(value.get("started_at"), str) \
            or not isinstance(value.get("cutoff"), str) \
            or not isinstance(value.get("queue"), list) \
            or len(value["queue"]) > MAX_GRAPH_DIRECTORY_QUEUE \
            or not isinstance(value.get("candidates"), list) \
            or len(value["candidates"]) > MAX_GRAPH_NODES \
            or isinstance(value.get("pages_seen"), bool) \
            or not isinstance(value.get("pages_seen"), int) \
            or value["pages_seen"] < 0 \
            or isinstance(value.get("eligible_seen"), bool) \
            or not isinstance(value.get("eligible_seen"), int) \
            or value["eligible_seen"] < 0 \
            or not isinstance(value.get("failed_ops"), list) \
            or len(value["failed_ops"]) > MAX_GRAPH_SCAN_ENTRIES:
        raise RuntimeError("graph projection state is invalid")
    try:
        _canonical_utc_timestamp(value["started_at"])
        _canonical_utc_timestamp(value["cutoff"])
    except ValueError as exc:
        raise RuntimeError("graph projection state is invalid") from exc
    queue = []
    for frame in value["queue"]:
        if not isinstance(frame, dict) or set(frame) != {
                "relative", "levels", "page"}:
            raise RuntimeError("graph projection cursor is invalid")
        relative = frame["relative"]
        parts = relative.split("/") if isinstance(relative, str) \
            and relative else []
        if not isinstance(relative, str) or os.path.isabs(relative) \
                or any(part in {"", ".", ".."} for part in parts) \
                or (os.altsep and os.altsep in relative) \
                or isinstance(frame["levels"], bool) \
                or not isinstance(frame["levels"], int) \
                or frame["levels"] < 0 \
                or frame["levels"] > MAX_GRAPH_TREE_LEVELS:
            raise RuntimeError("graph projection cursor is invalid")
        queue.append({"relative": relative, "levels": frame["levels"],
                      "page": _validated_source_page_state(frame["page"])})
    candidates = []
    seen = set()
    for record in value["candidates"]:
        required = {"slug", "type", "title", "updated_at", "origin",
                    "sha256"}
        if not isinstance(record, dict) or set(record) != required \
                or not isinstance(record.get("slug"), str) \
                or not isinstance(record.get("type"), str) \
                or not isinstance(record.get("title"), str) \
                or not isinstance(record.get("updated_at"), str) \
                or not isinstance(record.get("origin"), str) \
                or not isinstance(record.get("sha256"), str) \
                or len(record["type"]) > MAX_SOURCE_NAME_CHARS \
                or re.fullmatch(
                    r"[a-z0-9][a-z0-9._-]*", record["type"]) is None \
                or len(record["title"]) > MAX_SOURCE_NAME_CHARS \
                or record["origin"] not in (
                    THOUGHT_ORIGINS | {"legacy-unlabeled"}) \
                or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None \
                or record["slug"] in seen:
            raise RuntimeError("graph projection candidate is invalid")
        try:
            _canonical_corpus_slug(record["slug"])
            _canonical_utc_timestamp(record["updated_at"])
        except ValueError as exc:
            raise RuntimeError("graph projection candidate is invalid") \
                from exc
        seen.add(record["slug"])
        candidates.append(dict(record))
    failed_ops = []
    for failure in value["failed_ops"]:
        if not isinstance(failure, str) or not failure \
                or len(failure) > MAX_CONFIG_TEXT_CHARS:
            raise RuntimeError("graph projection failure is invalid")
        if failure not in failed_ops:
            failed_ops.append(failure)
    if value["phase"] == "ready" and queue:
        raise RuntimeError("completed graph projection retains a cursor")
    return dict(value, queue=queue, candidates=candidates,
                failed_ops=failed_ops)


def _load_graph_projection_state():
    path = _graph_projection_state_path()
    try:
        value = read_state_json(path, {}, "graph projection")
    except RuntimeError:
        raise
    if not value:
        return _fresh_graph_projection_state()
    state = _canonical_graph_projection_state(value)
    failures = [failure for failure in state["failed_ops"]
                if failure != LEGACY_GRAPH_README_FAILURE]
    if failures != state["failed_ops"]:
        # Older first-light scans recorded the installer-owned root README as
        # refusal debt. It was never a page candidate, so removing only this
        # byte-exact obsolete diagnostic preserves the completed generation.
        state = _save_graph_projection_state(
            dict(state, failed_ops=failures))
    return state


def _save_graph_projection_state(value):
    value = _canonical_graph_projection_state(value)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_STATE_JSON_BYTES:
        raise RuntimeError("graph projection state exceeds its byte bound")
    ensure_durable_directory(os.path.dirname(
        _graph_projection_state_path()))
    atomic_write(_graph_projection_state_path(), encoded)
    return value


def _mark_graph_projection_dirty():
    """Durably restart the conservative corpus baseline before mutation."""
    _save_graph_projection_state(_fresh_graph_projection_state())


def _read_graph_corpus_page(slug):
    """Read and parse one bounded corpus page with a full no-follow walk."""
    slug = _canonical_corpus_slug(slug)
    path = corpus_path(slug)
    fd = _open_source_nofollow(path, os.O_RDONLY)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_size > MAX_EVENT_PAGE_BYTES:
            raise RuntimeError(
                f"graph source is not a bounded regular page: {slug}")
        raw = stream.read(MAX_EVENT_PAGE_BYTES + 1)
        after = os.fstat(stream.fileno())
        try:
            target = _source_path_identity(path, os.O_RDONLY)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"graph source changed while reading: {slug}") from exc
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_EVENT_PAGE_BYTES \
            or (target.st_dev, target.st_ino) != (after.st_dev,
                                                  after.st_ino):
        raise RuntimeError(f"graph source changed while reading: {slug}")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise RuntimeError(f"graph source is not valid UTF-8: {slug}") \
            from exc
    match = FM_RE.match(text)
    frontmatter = match.group(1) if match else ""
    body = text[match.end():] if match else text

    type_values = re.findall(r"^type:\s*(.*?)\s*$", frontmatter, re.M)
    if not type_values:
        page_type = "note"
    elif len(type_values) != 1:
        raise RuntimeError(f"graph source type is ambiguous: {slug}")
    else:
        try:
            page_type = _yaml_scalar(type_values[0])
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"graph source type is invalid: {slug}") \
                from exc
    if len(page_type) > MAX_SOURCE_NAME_CHARS or re.fullmatch(
            r"[a-z0-9][a-z0-9._-]*", page_type) is None:
        raise RuntimeError(f"graph source type is invalid: {slug}")
    title_values = re.findall(r"^title:\s*(.*?)\s*$", frontmatter, re.M)
    title = slug
    if len(title_values) == 1:
        try:
            title = _yaml_scalar(title_values[0])
        except (ValueError, json.JSONDecodeError):
            title = slug
    title = clip(title, MAX_SOURCE_NAME_CHARS)
    origin_values = re.findall(r"^origin:\s*(.*?)\s*$", frontmatter, re.M)
    if len(origin_values) > 1:
        raise RuntimeError(f"graph source origin is ambiguous: {slug}")
    declared_origin = ""
    if origin_values:
        try:
            declared_origin = _yaml_scalar(origin_values[0])
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"graph source origin is invalid: {slug}") \
                from exc
        if declared_origin not in THOUGHT_ORIGINS:
            raise RuntimeError(f"graph source origin is invalid: {slug}")
    updated_at = datetime.datetime.fromtimestamp(
        before.st_mtime, tz=datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
    return {
        "slug": slug,
        "type": page_type,
        "title": title,
        "updated_at": updated_at,
        "origin": siamind.origin_class(
            slug, page_type, declared_origin or None),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }, frontmatter, body


def _admit_graph_candidate(state, record):
    slug = record["slug"]
    if not (record["type"] == "organ" or slug == "sia/cortex"
            or record["updated_at"] >= state["cutoff"]):
        return
    if any(candidate["slug"] == slug for candidate in state["candidates"]):
        raise RuntimeError("graph scan repeated a page in one generation")
    state["eligible_seen"] += 1
    state["candidates"].append(record)
    state["candidates"].sort(
        key=lambda candidate: (
            candidate["type"] == "organ"
            or candidate["slug"] == "sia/cortex",
            candidate["updated_at"], candidate["slug"]),
        reverse=True)
    del state["candidates"][MAX_GRAPH_NODES:]


def _advance_graph_projection(state, limit):
    """Inspect one bounded recursive corpus page and persist its cursor."""
    state = _canonical_graph_projection_state(state)
    if state["phase"] == "ready":
        return state
    queue = collections.deque(state["queue"])
    remaining = limit
    while queue and remaining:
        frame = queue.popleft()
        directory = os.path.join(CORPUS, frame["relative"])
        try:
            entries, complete, inspected, next_page = \
                _bounded_source_entries(
                    directory, frame["page"], remaining,
                    cleanup_legacy_atomic=True)
        except FileNotFoundError:
            failure = ("corpus_root_missing" if not frame["relative"]
                       else "graph_directory_missing:" + frame["relative"])
            _record_graph_failure(state, failure)
            continue
        if next_page.get("reset"):
            # No candidate gathered before a directory-generation change may
            # prove that a page is absent. Restart the complete baseline.
            restarted = _fresh_graph_projection_state()
            _save_graph_projection_state(restarted)
            return restarted
        remaining -= inspected
        if not complete:
            frame["page"] = next_page
            queue.appendleft(frame)
        for entry in entries:
            relative = os.path.join(frame["relative"], entry["name"])
            if stat.S_ISDIR(entry["mode"]):
                if not frame["relative"] and (
                        entry["name"].startswith(".")
                        or entry["name"] == "event-index"):
                    continue
                if frame["levels"] <= 0:
                    failure = "graph_depth_refused:" + relative
                    _record_graph_failure(state, failure)
                    continue
                if len(queue) >= MAX_GRAPH_DIRECTORY_QUEUE:
                    failure = "graph_directory_queue_capacity:" + relative
                    _record_graph_failure(state, failure)
                    continue
                queue.append({"relative": relative,
                              "levels": frame["levels"] - 1,
                              "page": {}})
                continue
            if not entry["name"].endswith(".md"):
                continue
            if not frame["relative"] and entry["name"] == "README.md":
                # The installer-created corpus genesis document describes the
                # repository; it is not a typed memory page and deliberately
                # has no frontmatter or canonical lowercase page slug.
                continue
            if not stat.S_ISREG(entry["mode"]):
                failure = "graph_nonregular_page:" + relative
                _record_graph_failure(state, failure)
                continue
            slug = relative[:-3].replace(os.sep, "/")
            try:
                record, _frontmatter, _body = _read_graph_corpus_page(slug)
            except Exception as exc:
                failure = "graph_page_refused:" + slug + ":" \
                    + str(exc)[:160]
                _record_graph_failure(state, failure)
                continue
            state["pages_seen"] += 1
            _admit_graph_candidate(state, record)
    state["queue"] = list(queue)
    if not queue:
        state["phase"] = "ready"
    return _save_graph_projection_state(state)


def _graph_projection_pages(batch_size=500):
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) \
            or batch_size <= 0 or batch_size > MAX_GRAPH_SCAN_ENTRIES:
        raise ValueError("graph scan batch bound is invalid")
    state = _advance_graph_projection(
        _load_graph_projection_state(), batch_size)
    complete = state["phase"] == "ready" and not state["failed_ops"]
    failure = None
    if state["phase"] != "ready":
        failure = "graph_projection_pending"
    elif state["failed_ops"]:
        failure = state["failed_ops"][0]
    return [dict(record) for record in state["candidates"]], complete, failure


def _graph_projection_debt():
    state = _load_graph_projection_state()
    if state["phase"] != "ready":
        return "bounded graph projection scan is pending"
    if state["failed_ops"]:
        return "graph projection has explicit refusal debt"
    return ""


# gbrain's NER gazetteer deliberately covers its built-in entity types.  SIA
# also has machine-domain entity types (organ/unit/package/project/skill), and
# those are usually referenced explicitly with wikilinks.  The cockpit graph
# is derived from those corpus links rather than from gbrain traversal, so it
# needs to apply the active SIA pack's declared inference regexes itself.


def _yaml_scalar(value):
    """Decode the small YAML scalar subset used by SIA's pack manifest."""
    value = value.strip()
    if value.startswith('"'):
        try:
            decoded = json.loads(value)
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise ValueError("quoted scalar is malformed") from exc
    elif value.startswith("'"):
        if not value.endswith("'"):
            raise ValueError("unterminated quoted schema-pack scalar")
        decoded = value[1:-1].replace("''", "'")
    else:
        decoded = value.split(" #", 1)[0].strip()
    if not isinstance(decoded, str) or not decoded:
        raise ValueError("empty schema-pack scalar")
    return decoded


def _sia_schema_pack_path(pack_path=None):
    if pack_path:
        return pack_path
    candidates = [
        os.environ.get("SIA_SCHEMA_PACK", ""),
        os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "schema-pack", "pack.yaml")),
        os.path.join(SHARE, ".gbrain/schema-packs/sia-pack/pack.yaml"),
    ]
    for path in candidates:
        # Select without following the final component. The authoritative
        # opener below decides whether the candidate is an admissible file;
        # a present but unsafe override must refuse instead of falling through.
        if path and os.path.lexists(path):
            return path
    raise FileNotFoundError("SIA schema pack not found")


def _read_owned_stable_lines(path, *, max_bytes, max_lines,
                             max_line_bytes, label):
    """Read one owned regular text file without following or streaming it."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_mode & 0o022 \
                or before.st_size > max_bytes:
            raise ValueError(
                f"{label} is not an owned bounded regular file")
        raw = stream.read(max_bytes + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    try:
        rebound = os.lstat(path)
        if not stat.S_ISREG(rebound.st_mode) \
                or rebound.st_uid != os.geteuid() \
                or rebound.st_mode & 0o022:
            raise ValueError(f"{label} changed while read")
        current = (rebound.st_dev, rebound.st_ino, rebound.st_size,
                   rebound.st_mtime_ns, rebound.st_ctime_ns)
    except OSError as exc:
        raise ValueError(f"{label} changed while read") from exc
    if observed != finished or current != observed or len(raw) > max_bytes:
        raise ValueError(f"{label} changed or exceeded its byte limit")
    # maxsplit bounds the temporary object count even for an all-newline file.
    raw_lines = raw.split(b"\n", max_lines)
    if raw_lines and raw_lines[-1] == b"":
        raw_lines.pop()
    if len(raw_lines) > max_lines:
        raise ValueError(f"{label} exceeds its line limit")
    lines = []
    for raw_line in raw_lines:
        if len(raw_line) > max_line_bytes:
            raise ValueError(f"{label} exceeds its line-width limit")
        try:
            lines.append(raw_line.decode("utf-8", errors="strict"))
        except UnicodeError as exc:
            raise ValueError(f"{label} contains invalid UTF-8") from exc
    return tuple(lines)


def _validate_domain_regex(pattern, rule_name):
    """Admit a deliberately finite regex subset with no unbounded repeat.

    The active SIA pack needs literals, alternation, one-level groups,
    optionals, and a small bounded ``.{m,n}`` window.  Rejecting every other
    Python-regex construct keeps matching linear in the bounded context and
    avoids treating a heuristic catastrophic-backtracking detector as a
    proof of safety.
    """
    if len(pattern) > _DOMAIN_REGEX_MAX_CHARS:
        raise ValueError(f"unsafe domain regex for {rule_name}: too long")
    if "(?" in pattern or any(char in pattern for char in "*+[]^$\\"):
        raise ValueError(
            f"unsafe domain regex for {rule_name}: unsupported or unbounded construct")
    if pattern.count("?") > _DOMAIN_REGEX_MAX_OPTIONALS or "??" in pattern:
        raise ValueError(
            f"unsafe domain regex for {rule_name}: excessive optionals")
    depth = 0
    for char in pattern:
        if char == "(":
            depth += 1
            if depth > 1:
                raise ValueError(
                    f"unsafe domain regex for {rule_name}: nested groups")
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError(
                    f"unsafe domain regex for {rule_name}: unbalanced group")
    if depth:
        raise ValueError(
            f"unsafe domain regex for {rule_name}: unbalanced group")

    def check_bound(match):
        lower, upper = int(match.group(1)), int(match.group(2))
        if lower > upper or upper > _DOMAIN_REGEX_MAX_BOUND:
            raise ValueError(
                f"unsafe domain regex for {rule_name}: invalid bound")
        return "."

    without_bounds = _DOMAIN_BOUNDED_DOT_RE.sub(check_bound, pattern)
    if "{" in without_bounds or "}" in without_bounds:
        raise ValueError(
            f"unsafe domain regex for {rule_name}: unsupported bound")


def load_domain_edge_spec(pack_path=None):
    """Load SIA entity types and every declared link inference regex.

    This is intentionally a narrow manifest reader, not a second YAML
    implementation: it accepts the validated pack's sequence-of-maps shape
    and decodes only `name`, `primitive`, and `inference.regex`.  Patterns are
    restricted to SIA's finite, no-unbounded-repeat subset; rejected or
    malformed rules fail the typed layer closed. export_graph then retains the
    underlying `mentions` edges and marks the snapshot partial.
    """
    path = _sia_schema_pack_path(pack_path)
    section = current_name = None
    entity_types = set(_GAZETTEER_ENTITY_TYPES)
    rules, seen_rules = [], set()
    lines = _read_owned_stable_lines(
        path, max_bytes=MAX_SCHEMA_PACK_BYTES,
        max_lines=MAX_SCHEMA_PACK_LINES,
        max_line_bytes=MAX_SCHEMA_PACK_LINE_BYTES,
        label="SIA schema pack")
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            section = stripped[:-1] if stripped.endswith(":") else None
            current_name = None
            continue
        if section not in ("page_types", "link_types"):
            continue
        if indent == 2 and stripped.startswith("- name:"):
            current_name = _yaml_scalar(stripped.split(":", 1)[1])
            continue
        if not current_name:
            continue
        if section == "page_types" and indent == 4 and \
                stripped.startswith("primitive:"):
            primitive = _yaml_scalar(stripped.split(":", 1)[1])
            if primitive == "entity":
                if current_name not in entity_types \
                        and len(entity_types) >= MAX_DOMAIN_ENTITY_TYPES:
                    raise ValueError(
                        "SIA schema pack exceeds its entity-type limit")
                entity_types.add(current_name)
            continue
        if section == "link_types" and indent == 6 and \
                stripped.startswith("regex:"):
            if current_name in seen_rules:
                raise ValueError(
                    f"duplicate inference regex for {current_name}")
            if len(rules) >= MAX_DOMAIN_EDGE_RULES:
                raise ValueError(
                    "SIA schema pack exceeds its inference-rule limit")
            pattern = _yaml_scalar(stripped.split(":", 1)[1])
            _validate_domain_regex(pattern, current_name)
            try:
                compiled = re.compile(pattern)
            except re.error as e:
                raise ValueError(
                    f"invalid inference regex for {current_name}: {e}") from e
            seen_rules.add(current_name)
            rules.append((current_name, compiled))
    if not rules:
        raise ValueError("SIA schema pack declares no inference regexes")
    return tuple(rules), frozenset(entity_types)


def _relation_context(body, link_match, inherit_link_only=False):
    """Return the Markdown record governing one explicit wikilink.

    Generated event records are one line, so a leading verb still governs the
    last member of a long package list.  Thought pages put their evidence links
    on a link-only line; for those, inherit the nearest preceding prose line.
    Headings never supply a relation.
    """
    line_start = body.rfind("\n", 0, link_match.start()) + 1
    line_end = body.find("\n", link_match.end())
    if line_end < 0:
        line_end = len(body)
    line = body[line_start:line_end]
    if line.lstrip().startswith("#"):
        return ""
    masked = _WIKILINK_RE.sub(" ", line)
    if any(ch.isalnum() for ch in masked):
        return line
    if not inherit_link_only:
        return line

    cursor = line_start
    while cursor > 0:
        previous_end = cursor - 1
        previous_start = body.rfind("\n", 0, previous_end) + 1
        previous = body[previous_start:previous_end]
        cursor = previous_start
        if not previous.strip():
            continue
        if previous.lstrip().startswith("#"):
            return line
        return previous + "\n" + line
    return line


def _infer_domain_link_type(context, rules):
    # Link targets and display aliases are entity identity, not evidence of a
    # relation.  Masking them prevents names such as `diagnose-crash` from
    # manufacturing a `crashed` edge to every neighbor in the same record.
    scan = _WIKILINK_RE.sub(" ", context)
    if len(scan) > _DOMAIN_CONTEXT_MAX_CHARS:
        return "mentions"
    for name, pattern in rules:
        if pattern.search(scan):
            return name
    return "mentions"


def _suppress_shadowed_mentions(edges):
    """Drop generic edges when the same directed pair has typed evidence."""
    typed_pairs = {
        (edge.get("from_slug"), edge.get("to_slug"))
        for edge in edges
        if edge.get("link_type", "mentions") != "mentions"
    }
    return [
        edge for edge in edges
        if edge.get("link_type", "mentions") != "mentions"
        or (edge.get("from_slug"), edge.get("to_slug")) not in typed_pairs
    ]


def _iter_corpus_link_edges(canonical_slugs, rules, source_digests,
                            target_slugs=None):
    """Yield stable link occurrences from a fixed selected-page generation."""
    for slug in canonical_slugs:
        record, fmtext, body = _read_graph_corpus_page(slug)
        expected_digest = source_digests.get(slug)
        if expected_digest is None:
            source_digests[slug] = record["sha256"]
        elif not isinstance(expected_digest, str) \
                or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None \
                or record["sha256"] != expected_digest:
            raise RuntimeError(
                f"graph source changed after selection: {slug}")
        page_type = record["type"]
        if page_type == "take":
            # The prediction and its operator-approved structural links
            # precede the canonical grade heading. Everything after it may
            # include legacy model prose and never participates in the graph.
            body = body.split("\n## Grade · ", 1)[0]
        tagm = re.search(r"^tags:\s*\[(.*)\]\s*$", fmtext, re.M)
        tags = ({t.strip() for t in tagm.group(1).split(",")}
                if tagm else set())
        origin_values = re.findall(r"^origin:\s*(.*?)\s*$", fmtext, re.M)
        try:
            page_origin = (_yaml_scalar(origin_values[0])
                           if len(origin_values) == 1 else "")
        except (ValueError, json.JSONDecodeError):
            page_origin = ""
        trusted_thought = (page_type == "thought"
                           and page_origin == "derived"
                           and bool(tags & _DOMAIN_THOUGHT_KINDS))
        inherit_link_only = trusted_thought
        page_rules = (rules if page_type in _DOMAIN_EVIDENCE_PAGE_TYPES
                      or trusted_thought else ())
        for lm in _WIKILINK_RE.finditer(body):
            target = lm.group(1)
            if target_slugs is not None and target not in target_slugs:
                continue
            lo = max(0, lm.start() - 45)
            why = re.sub(r"\s+", " ",
                         body[lo:lm.end() + 45]).strip()[:90]
            link_type = _infer_domain_link_type(
                _relation_context(body, lm, inherit_link_only), page_rules)
            yield {"from_slug": slug, "to_slug": target,
                   "link_type": link_type, "context": why}


def corpus_edges(rules=None, entity_types=None, slugs=None,
                 source_digests=None, include_omissions=False,
                 target_slugs=None):
    """Extract bounded edges from the already-selected cockpit window.

    With no explicit ``slugs`` this advances the durable graph baseline once
    and proceeds only if that bounded generation is complete.  It never walks
    or materializes the whole corpus merely to discard most pages afterward.
    Each selected page is opened no-follow, byte-bounded, and optionally bound
    to the digest observed by the selection pass.  Edge retention is a
    deterministic cockpit display window.  With an explicit ``target_slugs``
    window, duplicates, out-of-window targets, and generic mentions shadowed by
    typed relations are resolved before the cap; ``include_omissions`` then
    returns ``(edges, omitted_count)`` for exact unique display edges.
    """
    if rules is None or entity_types is None:
        rules, entity_types = load_domain_edge_spec()
    if slugs is None:
        pages, complete, failure = _graph_projection_pages(
            MAX_GRAPH_SCAN_ENTRIES)
        if not complete:
            raise GraphProjectionPending(
                failure or "graph projection baseline is incomplete")
        slugs = [page["slug"] for page in pages]
        source_digests = {page["slug"]: page["sha256"] for page in pages}
    if not isinstance(slugs, (list, tuple, set)) \
            or len(slugs) > MAX_GRAPH_NODES:
        raise ValueError("graph edge source window exceeds its bound")
    if not isinstance(include_omissions, bool):
        raise ValueError("graph edge omission mode is invalid")
    try:
        rules = tuple(rules)
    except TypeError as exc:
        raise ValueError("graph edge rules are invalid") from exc
    if len(rules) > MAX_DOMAIN_EDGE_RULES:
        raise ValueError("graph edge rules exceed their bound")
    canonical_slugs = []
    for slug in slugs:
        slug = _canonical_corpus_slug(slug)
        if slug in canonical_slugs:
            continue
        canonical_slugs.append(slug)
    canonical_slugs.sort()
    source_digests = source_digests or {}
    if not isinstance(source_digests, dict):
        raise ValueError("graph source digest map is invalid")
    observed_digests = dict(source_digests)
    if target_slugs is None:
        typed_edges, mention_edges = [], []
        omitted_edges = 0
        for edge in _iter_corpus_link_edges(
                canonical_slugs, rules, observed_digests):
            if len(typed_edges) + len(mention_edges) >= MAX_GRAPH_EDGES:
                omitted_edges += 1
                continue
            (typed_edges if edge["link_type"] != "mentions"
             else mention_edges).append(edge)
        retained = _suppress_shadowed_mentions(typed_edges + mention_edges)
        if include_omissions:
            return retained, omitted_edges
        return retained

    if not isinstance(target_slugs, (list, tuple, set)) \
            or len(target_slugs) > MAX_GRAPH_NODES:
        raise ValueError("graph edge target window exceeds its bound")
    allowed_targets = {_canonical_corpus_slug(slug) for slug in target_slugs}
    if len(allowed_targets) != len(target_slugs) \
            or not set(canonical_slugs) <= allowed_targets:
        raise ValueError("graph edge target window is invalid")
    relation_names = ["mentions"]
    for name, _pattern in rules:
        if not isinstance(name, str) or name in relation_names:
            raise ValueError("graph edge relation identities are invalid")
        relation_names.append(name)

    # First establish typed pairs. The set has at most one entry per directed
    # pair in the already capped node window.
    typed_pairs = set()
    for edge in _iter_corpus_link_edges(
            canonical_slugs, rules, observed_digests, allowed_targets):
        if edge["link_type"] != "mentions":
            typed_pairs.add((edge["from_slug"], edge["to_slug"]))

    node_names = sorted(allowed_targets)
    node_index = {slug: index for index, slug in enumerate(node_names)}
    relation_index = {
        relation: index for index, relation in enumerate(relation_names)}
    slots = len(node_names) * len(node_names) * len(relation_names)
    seen = bytearray((slots + 7) // 8)
    retained, omitted_edges = [], 0
    for edge in _iter_corpus_link_edges(
            canonical_slugs, rules, observed_digests, allowed_targets):
        source, target = edge["from_slug"], edge["to_slug"]
        relation = edge["link_type"]
        if relation == "mentions" and (source, target) in typed_pairs:
            continue
        slot = ((node_index[source] * len(node_names) + node_index[target])
                * len(relation_names) + relation_index[relation])
        byte_index, bit_index = divmod(slot, 8)
        mask = 1 << bit_index
        if seen[byte_index] & mask:
            continue
        seen[byte_index] |= mask
        if len(retained) < MAX_GRAPH_EDGES:
            retained.append(edge)
        else:
            omitted_edges += 1
    if include_omissions:
        return retained, omitted_edges
    return retained


def _graph_display_nodes(pages):
    """Select the deterministic capped cockpit node window."""
    cutoff = iso(utcnow() - datetime.timedelta(days=14))
    keep = {}
    for page in pages:
        slug = page.get("slug", "")
        page_type = page.get("type", "note")
        recent = (page.get("updated_at") or "") >= cutoff
        if page_type in ("organ",) or slug == "sia/cortex" or recent:
            keep[slug] = {
                "id": slug, "t": page_type,
                "title": page.get("title", slug),
                "ts": page.get("updated_at", ""),
                "origin": (page["origin"]
                           if isinstance(page.get("origin"), str)
                           else corpus_origin(slug, page_type)),
                "deg": 0, "din": 0, "dout": 0,
            }
    aged_out = len(pages) - len(keep)
    truncated = 0
    if len(keep) > MAX_GRAPH_NODES:
        organs = {slug: node for slug, node in keep.items()
                  if node["t"] == "organ"}
        rest = sorted(
            (node for node in keep.values() if node["t"] != "organ"),
            key=lambda node: (node["ts"], node["id"]), reverse=True)[
                :max(0, MAX_GRAPH_NODES - len(organs))]
        truncated = len(keep) - len(organs) - len(rest)
        keep = {**organs, **{node["id"]: node for node in rest}}
    return keep, aged_out, truncated


def export_graph(require_complete=True):
    """Graph snapshot v2 — carries its own truth boundary (the snapshot
    block says what is complete, what was truncated, and which reads
    failed), per-node in/out degrees, and per-edge type + extraction
    context so the panel can answer 'why does this connection exist'.
    Edges come from the corpus itself (see corpus_edges)."""
    failed_ops = []
    pages, pages_complete, page_failure = gbrain_all_pages()
    if not pages_complete:
        _append_graph_failure(failed_ops, page_failure or "list_pages")
    keep, aged_out, truncated = _graph_display_nodes(pages)
    try:
        rules, entity_types = load_domain_edge_spec()
    except Exception:
        _append_graph_failure(failed_ops, "domain_link_rules")
        rules, entity_types = (), _GAZETTEER_ENTITY_TYPES
    try:
        # Defend the exported invariant even when another edge provider is
        # substituted for corpus_edges.
        selected_slugs = sorted(keep)
        source_digests = {
            page["slug"]: page["sha256"] for page in pages
            if isinstance(page, dict)
            and isinstance(page.get("slug"), str)
            and isinstance(page.get("sha256"), str)}
        edge_projection = corpus_edges(
            rules, entity_types, selected_slugs, source_digests, True,
            selected_slugs)
        # Preserve the substitution seam used by embedders that supplied a
        # pre-cap edge provider before omission accounting was added.
        if isinstance(edge_projection, tuple):
            if len(edge_projection) != 2:
                raise ValueError("graph edge projection result is invalid")
            paths, omitted_edges = edge_projection
        else:
            paths, omitted_edges = edge_projection, 0
        if isinstance(omitted_edges, bool) \
                or not isinstance(omitted_edges, int) \
                or omitted_edges < 0:
            raise ValueError("graph edge omission count is invalid")
        paths = _suppress_shadowed_mentions(paths)
    except Exception:
        _append_graph_failure(failed_ops, "corpus_edges")
        paths = []
        omitted_edges = 0
    edges, eseen = [], set()
    for e in paths:
        s, d = e.get("from_slug"), e.get("to_slug")
        relation = e.get("link_type", "mentions")
        if s in keep and d in keep and (s, d, relation) not in eseen:
            eseen.add((s, d, relation))
            why = re.sub(r"\s+", " ", str(e.get("context") or "")).strip()[:90]
            edges.append({"s": s, "d": d,
                          "t": relation, "why": why})
            keep[s]["deg"] += 1; keep[s]["dout"] += 1
            keep[d]["deg"] += 1; keep[d]["din"] += 1
    counts = {}
    for v in keep.values():
        counts[v["t"]] = counts.get(v["t"], 0) + 1
    pages_total = len(pages)
    try:
        projection = _load_graph_projection_state()
        projected_slugs = {record["slug"]
                           for record in projection["candidates"]}
        if projected_slugs == set(keep) or projected_slugs == {
                page.get("slug") for page in pages
                if isinstance(page, dict)}:
            pages_total = projection["pages_seen"]
            aged_out = max(
                aged_out,
                projection["pages_seen"] - projection["eligible_seen"])
            truncated = max(
                truncated,
                projection["eligible_seen"]
                - len(projection["candidates"]))
            for failure in projection["failed_ops"]:
                _append_graph_failure(failed_ops, failure)
    except Exception as exc:
        _append_graph_failure(
            failed_ops, "graph_projection_state:" + str(exc)[:120])
    graph = {"v": 2, "ts": iso(),
             "nodes": sorted(keep.values(), key=lambda n: n["id"]),
             "edges": edges,
             "pages_total": pages_total,
             "pages_total_complete": pages_complete,
             "snapshot": {"complete": not failed_ops,
                          "truncated": truncated,
                          "omitted_nodes": truncated,
                          "omitted_edges": omitted_edges,
                          "omissions_imply_absence": False,
                          "aged_out": aged_out,
                          "counts_by_kind": counts,
                          "failed_ops": failed_ops,
                          "window_days": 14}}
    atomic_write(GRAPH_PATH, json.dumps(graph))
    if require_complete and not graph["snapshot"]["complete"]:
        reason = ", ".join(graph["snapshot"]["failed_ops"][:3]) \
            or "graph snapshot is partial"
        raise GraphProjectionPending(reason)
    return len(keep), len(edges), pages_total


def _export_graph_publication():
    """Require a complete graph and drain its bounded durable cursor.

    Corpus mutation conservatively restarts the projection. Returning after
    only one directory page would make an active corpus larger than that page
    alternate forever between recovery and new publication debt. Keep the
    corpus lease, advance independently bounded pages, and retain a finite
    aggregate ceiling for churn or an unexpectedly large tree.
    """
    attempts = 0
    while True:
        try:
            return export_graph()
        except GraphProjectionPending:
            state = _load_graph_projection_state()
            if state["phase"] == "ready":
                raise
            attempts += 1
            if attempts >= MAX_EVENT_LOOKUP_PAGES:
                raise GraphProjectionPending(
                    "graph publication exceeded its generation "
                    "ceiling") from None


# Exports are captured before bind() exists, so the owner can wrap every
# graph/domain/export function while leaving intra-module calls direct and
# stable.
_EXPORTED_FUNCTIONS = tuple(
    name for name, value in globals().items()
    if getattr(value, "__module__", None) == __name__)
_CHILD_FUNCTIONS = frozenset(_EXPORTED_FUNCTIONS)
_ORIGINAL_CHILD_FUNCTIONS = {
    name: globals()[name] for name in _EXPORTED_FUNCTIONS}
_MISSING = object()
_BIND_LOCK = _threading.RLock()
_BIND_CONTROL_NAMES = frozenset({
    "_EXPORTED_FUNCTIONS", "_CHILD_FUNCTIONS", "_ORIGINAL_CHILD_FUNCTIONS",
    "_MISSING", "_BIND_LOCK", "_BIND_CONTROL_NAMES", "bind", "invoke",
})


def bind(parent_globals):
    """Bind the active sialib namespace without importing a second core."""
    if not isinstance(parent_globals, dict):
        raise TypeError("sialib graph context must be a globals dictionary")
    for name, value in parent_globals.items():
        if (name.startswith("__") or name in _CHILD_FUNCTIONS
                or name in _BIND_CONTROL_NAMES):
            continue
        globals()[name] = value
    # Preserve sialib's historical test/runtime seam: an explicit parent
    # replacement of a helper is mirrored into intra-module calls, while an
    # ordinary parent façade restores the raw child implementation.  This
    # avoids delegate recursion and prevents a prior dynamically loaded
    # sialib alias from leaking a mocked helper into the next one.
    for name, original in _ORIGINAL_CHILD_FUNCTIONS.items():
        value = parent_globals.get(name, _MISSING)
        if value is _MISSING or getattr(value, "__dict__", {}).get(
                "_sia_senses_delegate") is True:
            globals()[name] = original
        else:
            globals()[name] = value


def invoke(parent_globals, name, *args, **kwargs):
    """Bind and call one exported child function as one re-entrant action."""
    target = _ORIGINAL_CHILD_FUNCTIONS.get(name)
    if target is None:
        raise AttributeError(f"unknown SIA graph export: {name}")
    with _BIND_LOCK:
        bind(parent_globals)
        return target(*args, **kwargs)
