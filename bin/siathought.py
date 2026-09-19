"""Durable generated-entry and epoch pages, recovery, and legacy replay for SIA.

``thought``, ``mind``, and ``DREAM`` are persisted/API compatibility names for
generated records, retrieval-policy state, and scheduled maintenance. They do
not assert cognition or biological processes.

This is the third bounded child of ``sialib`` and it follows the same
bind/invoke façade as ``siasenses`` and ``siagraph``: it imports no SIA
module, so one runtime state survives the dynamic aliases the test suite
loads sialib under, and explicit test patches of these helpers are mirrored
back into intra-module calls.  See ``docs/ARCHITECTURE.md``.

Epoch materialization owns its completeness manifests, bounded consolidation
claims and recovery markers here. Event-day admission and occurrence indexes
remain core services; the same binding supplies their helpers, constants and
exception classes without introducing a second runtime state.

The façade also carries this lane's context managers safely across the child
boundary.  ``invoke()`` returns a bound proxy for the explicitly named
context exports; that proxy rebinds the owning ``sialib`` globals under the
shared lock for both ``__enter__`` and ``__exit__`` without holding the lock
across caller code.  The legacy directory reader similarly reuses the core's
single generic ``_SOURCE_LIBC`` handle through ``bind()``. No generated-entry-only
ABI state remains in the core.
"""

import contextlib as _contextlib
import threading as _threading

def _canonical_thought_page_record(thought):
    """Project a compatibility-named generated entry into its page record."""
    if not isinstance(thought, dict):
        raise ValueError("thought record must be an object")
    timestamp = _canonical_utc_timestamp(thought.get("ts"))
    kind = thought.get("kind")
    text = thought.get("text")
    origin = _canonical_thought_origin(thought.get("origin", "derived"))
    links_in = thought.get("links") or ["sia/cortex"]
    if not isinstance(kind, str) or sanitize_slugpart(kind) != kind:
        raise ValueError("thought kind is not canonical")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("thought text must be a non-empty string")
    if not isinstance(links_in, (list, tuple, set)):
        raise ValueError("thought links must be a sequence")
    links_in = sorted({_canonical_corpus_slug(link) for link in links_in})
    text = inert_summary(text)
    queue_id = thought.get("queue_id")
    if queue_id is not None and not re.fullmatch(r"[0-9a-f]{32}", queue_id):
        raise ValueError("invalid thought queue identity")
    record = {"ts": timestamp, "kind": kind, "text": text,
              "links": links_in, "urgent": bool(thought.get("urgent")),
              "origin": origin}
    if queue_id:
        record["queue_id"] = queue_id
    if "slug" in thought:
        slug = _canonical_corpus_slug(thought["slug"])
        if re.fullmatch(r"thoughts/[a-z0-9_][a-z0-9._-]*", slug) is None:
            raise ValueError("thought page must be a flat thoughts entry")
        if queue_id and slug != _queued_thought_slug(queue_id):
            raise ValueError("queued thought page has a noncanonical identity")
        record["slug"] = slug
    return record


def _thought_page_parts(record):
    tags = ["thought", record["kind"]] \
        + (["urgent"] if record["urgent"] else [])
    links_in = record["links"] or ["sia/cortex"]
    links = " ".join(f"[[{link}]]" for link in links_in)
    fm = ["type: thought", fm_title(clip(record["text"], 70)),
          f"tags: [{', '.join(tags)}]", f"date: {record['ts'][:10]}",
          f"origin: {record['origin']}",
          "sia_thought: " + json.dumps(
              record, sort_keys=True, ensure_ascii=False)]
    if record.get("queue_id"):
        fm.append(f"queue_id: {record['queue_id']}")
    body = (f"# thought · {record['kind']}\n\n{record['text']}\n\n"
            f"{links}\n")
    return fm, body


def _queued_thought_slug(queue_id):
    """Name queue-owned generated entries solely from durable identity."""
    if not isinstance(queue_id, str) \
            or re.fullmatch(r"[0-9a-f]{32}", queue_id) is None:
        raise ValueError("invalid thought queue identity")
    return f"thoughts/queue-{queue_id}"


def _thought_queue_binding(record):
    """Fields whose exact equality is promised by one queue identity.

    ``ts`` is deliberately excluded: it records the first successful
    materialization, while a retry can occur later.  The durable page supplies
    that original timestamp after every bounded projection has aged out.
    """
    return {key: record[key] for key in
            ("kind", "text", "links", "urgent", "origin", "queue_id")}


def _read_thought_page_text(slug):
    """Read one stable, bounded, no-follow generated-entry page."""
    path = corpus_path(_canonical_corpus_slug(slug))
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with siaqueue.regular_file_stream(
            fd, label="thought page", error_type=RuntimeError) as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_nlink != 1 \
                or before.st_size > MAX_THOUGHT_INBOX_BYTES:
            raise RuntimeError(
                "thought page is not a bounded owned single-link regular file")
        raw = stream.read(MAX_THOUGHT_INBOX_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_THOUGHT_INBOX_BYTES:
        raise RuntimeError("thought page changed while read")
    try:
        decoded = raw.decode("utf-8")
    except UnicodeError as exc:
        raise RuntimeError("thought page is not UTF-8") from exc
    try:
        current = os.lstat(path)
    except OSError as exc:
        raise RuntimeError("thought page changed while read") from exc
    current_identity = (
        current.st_dev, current.st_ino, current.st_size,
        current.st_mtime_ns, current.st_ctime_ns)
    if current_identity != finished or not stat.S_ISREG(current.st_mode) \
            or current.st_uid != os.geteuid() or current.st_nlink != 1:
        raise RuntimeError("thought page changed while read")
    return decoded


def _decode_exact_thought_page(slug, text_value):
    """Recover and byte-verify one self-described generated-entry page."""
    metadata = re.findall(r"^sia_thought: (.*)$", text_value, re.M)
    if not metadata:
        raise RuntimeError("thought page has no recovery metadata")
    if len(metadata) != 1:
        raise RuntimeError("thought page has duplicate recovery metadata")
    try:
        encoded_record = json.loads(metadata[0])
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise RuntimeError("thought recovery metadata is malformed") from exc
    allowed = {"ts", "kind", "text", "links", "urgent", "origin",
               "queue_id", "slug"}
    if not isinstance(encoded_record, dict) \
            or set(encoded_record) - allowed:
        raise RuntimeError("thought recovery metadata is invalid")
    if encoded_record.get("slug") != slug:
        raise RuntimeError("thought recovery metadata binds another page")
    record = _canonical_thought_page_record(encoded_record)
    if record != encoded_record:
        raise RuntimeError("thought recovery metadata is noncanonical")
    if record.get("queue_id") \
            and slug != _queued_thought_slug(record["queue_id"]):
        raise RuntimeError("queued thought page has a noncanonical identity")
    fm, body = _thought_page_parts(record)
    expected = "---\n" + "\n".join(fm) + "\n---\n" + body
    if text_value != expected:
        raise RuntimeError("thought page differs from its recovery record")
    return record


def _thought_recovery_dir():
    return os.path.join(STATE, THOUGHT_RECOVERY_DIRNAME)


def _thought_legacy_index_dir():
    return os.path.join(STATE, THOUGHT_LEGACY_INDEX_DIRNAME)


def _thought_legacy_catalog_path():
    return os.path.join(STATE, THOUGHT_LEGACY_CATALOG_NAME)


def _thought_mind_replay_path():
    return os.path.join(STATE, THOUGHT_MIND_REPLAY_NAME)


def _thought_recovery_claim_path():
    return os.path.join(STATE, THOUGHT_RECOVERY_CLAIM_NAME)


def _thought_legacy_scan_path():
    return os.path.join(STATE, THOUGHT_LEGACY_SCAN_NAME)


def _thought_recovery_lock_path():
    return os.path.join(STATE, THOUGHT_RECOVERY_LOCK_NAME)


@_contextlib.contextmanager
def _thought_legacy_catalog():
    """Open the bounded-query catalog for canonical JSON index records."""
    ensure_durable_directory(STATE, mode=0o700)
    path = _thought_legacy_catalog_path()
    existed = os.path.lexists(path)
    if existed:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
                or info.st_nlink != 1:
            raise ValueError(
                "legacy thought catalog is not an owned single-link file")
    connection = sqlite3.connect(path, timeout=2.0)
    try:
        if hasattr(connection, "setlimit"):
            connection.setlimit(
                sqlite3.SQLITE_LIMIT_LENGTH,
                MAX_THOUGHT_RECOVERY_RECORD_BYTES)
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS legacy_thought_index ("
            "index_name TEXT PRIMARY KEY NOT NULL, "
            "entry_json TEXT NOT NULL) WITHOUT ROWID")
        objects = connection.execute(
            "SELECT type, name FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()
        if objects != [("table", "legacy_thought_index")]:
            raise ValueError("legacy thought catalog schema is invalid")
        columns = connection.execute(
            "PRAGMA table_info(legacy_thought_index)").fetchall()
        column_shape = [(row[1], row[2], row[3], row[5])
                        for row in columns]
        if column_shape != [
                ("index_name", "TEXT", 1, 1),
                ("entry_json", "TEXT", 1, 0)]:
            raise ValueError("legacy thought catalog columns are invalid")
        connection.commit()
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
                or info.st_nlink != 1:
            raise ValueError(
                "legacy thought catalog is not an owned single-link file")
        os.chmod(path, 0o600)
        if not existed:
            _sync_directory(STATE)
        yield connection
    finally:
        connection.close()


@_contextlib.contextmanager
def _thought_mind_replay_catalog():
    """Open bounded-query replay journals for every generated-entry source."""
    ensure_durable_directory(STATE, mode=0o700)
    path = _thought_mind_replay_path()
    existed = os.path.lexists(path)
    if existed:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
                or info.st_nlink != 1:
            raise ValueError(
                "thought mind replay journal is not an owned single-link file")
    connection = sqlite3.connect(path, timeout=2.0)
    try:
        if hasattr(connection, "setlimit"):
            connection.setlimit(
                sqlite3.SQLITE_LIMIT_LENGTH,
                MAX_THOUGHT_RECOVERY_RECORD_BYTES)
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS thought_mind_replay ("
            "record_id TEXT PRIMARY KEY NOT NULL, "
            "claim_id TEXT NOT NULL, claim_sha256 TEXT NOT NULL, "
            "state TEXT NOT NULL) WITHOUT ROWID")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS native_thought_mind_replay ("
            "record_id TEXT PRIMARY KEY NOT NULL, "
            "claim_id TEXT NOT NULL, claim_sha256 TEXT NOT NULL, "
            "state TEXT NOT NULL, queue_id TEXT NOT NULL) WITHOUT ROWID")
        objects = connection.execute(
            "SELECT type, name FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name").fetchall()
        if objects != [
                ("table", "native_thought_mind_replay"),
                ("table", "thought_mind_replay")]:
            raise ValueError("thought mind replay journal schema is invalid")
        expected_legacy_columns = [
            ("record_id", "TEXT", 1, 1),
            ("claim_id", "TEXT", 1, 0),
            ("claim_sha256", "TEXT", 1, 0),
            ("state", "TEXT", 1, 0)]
        legacy_columns = connection.execute(
            "PRAGMA table_info(thought_mind_replay)").fetchall()
        legacy_shape = [(row[1], row[2], row[3], row[5])
                        for row in legacy_columns]
        native_columns = connection.execute(
            "PRAGMA table_info(native_thought_mind_replay)").fetchall()
        native_shape = [(row[1], row[2], row[3], row[5])
                        for row in native_columns]
        if legacy_shape != expected_legacy_columns \
                or native_shape != expected_legacy_columns + [
                    ("queue_id", "TEXT", 1, 0)]:
            raise ValueError(
                "thought mind replay journal columns are invalid")
        connection.commit()
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
                or info.st_nlink != 1:
            raise ValueError(
                "thought mind replay journal is not an owned single-link file")
        os.chmod(path, 0o600)
        if not existed:
            _sync_directory(STATE)
        yield connection
    finally:
        connection.close()


def _ensure_private_recovery_directory(path):
    ensure_durable_directory(path, mode=0o700)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError("thought recovery store is not an owned directory")
        os.fchmod(descriptor, 0o700)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def _thought_recovery_record(page_record):
    page = _canonical_thought_page_record(page_record)
    if "slug" not in page:
        raise ValueError("thought recovery record requires a page slug")
    payload = json.dumps(
        page, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf-8")
    record_id = hashlib.sha256(payload).hexdigest()
    return {"schema": THOUGHT_RECOVERY_SCHEMA,
            "record_id": record_id, "page": page}


def _thought_recovery_record_bytes(record):
    if not isinstance(record, dict) or set(record) != {
            "schema", "record_id", "page"} \
            or record.get("schema") != THOUGHT_RECOVERY_SCHEMA:
        raise ValueError("thought recovery record schema is invalid")
    expected = _thought_recovery_record(record.get("page"))
    if record != expected:
        raise ValueError("thought recovery record identity is invalid")
    encoded = (json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
        raise ValueError("thought recovery record exceeds its byte bound")
    return encoded


def _read_thought_recovery_record(path):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with siaqueue.regular_file_stream(
            descriptor, label="thought recovery record") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_nlink != 1 \
                or before.st_mode & 0o077 \
                or before.st_size > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
            raise ValueError(
                "thought recovery record is not a bounded private "
                "single-link file")
        raw = stream.read(MAX_THOUGHT_RECOVERY_RECORD_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
        raise ValueError("thought recovery record changed while read")
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("thought recovery record is malformed") from exc
    if raw != _thought_recovery_record_bytes(record) \
            or os.path.basename(path) != record["record_id"] + ".json":
        raise ValueError("thought recovery record path binding is invalid")
    try:
        current = os.lstat(path)
    except OSError as exc:
        raise ValueError("thought recovery record changed while read") from exc
    current_identity = (
        current.st_dev, current.st_ino, current.st_size,
        current.st_mtime_ns, current.st_ctime_ns)
    if current_identity != finished or not stat.S_ISREG(current.st_mode) \
            or current.st_uid != os.geteuid() or current.st_nlink != 1:
        raise ValueError("thought recovery record changed while read")
    return record, observed


def _list_thought_recovery_records_locked():
    directory = _thought_recovery_dir()
    try:
        info = os.lstat(directory)
    except FileNotFoundError:
        return []
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("thought recovery store is not a real directory")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    names = []
    total = 0
    inspected = 0
    cleaned = False
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode) \
                or opened.st_uid != os.geteuid():
            raise ValueError(
                "thought recovery store is not an owned directory")
        with os.scandir(descriptor) as entries:
            for entry in entries:
                inspected += 1
                if inspected >= MAX_THOUGHT_RECOVERY_SCAN_ENTRIES:
                    raise ValueError(
                        "thought recovery store exceeds its scan bound")
                name = entry.name
                if _legacy_atomic_temp_name(name):
                    _remove_legacy_atomic_temp(
                        descriptor, entry, "thought recovery store")
                    cleaned = True
                    continue
                if name.startswith("."):
                    continue
                if re.fullmatch(r"[0-9a-f]{64}\.json", name) is None:
                    raise ValueError(
                        "thought recovery store has an unexpected entry")
                if len(names) >= MAX_THOUGHT_RECOVERY_RECORDS:
                    raise ValueError(
                        "thought recovery queue exceeds its record bound")
                entry_info = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(entry_info.st_mode) \
                        or entry_info.st_size \
                        > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
                    raise ValueError(
                        "thought recovery queue has an invalid record")
                if entry_info.st_size > MAX_THOUGHT_RECOVERY_BYTES - total:
                    raise ValueError(
                        "thought recovery queue exceeds its byte bound")
                total += entry_info.st_size
                names.append(name)
    finally:
        if cleaned:
            os.fsync(descriptor)
        os.close(descriptor)
    records = []
    for name in sorted(names):
        record, _identity = _read_thought_recovery_record(
            os.path.join(directory, name))
        records.append(record)
    return records


def _thought_recovery_claim_basis(records, active_ids, legacy):
    canonical = [_thought_recovery_record(record["page"])
                 for record in records]
    canonical.sort(key=lambda record: (
        record["page"]["ts"], record["page"]["slug"],
        record["record_id"]))
    if not isinstance(active_ids, list) \
            or any(not isinstance(value, str)
                   or re.fullmatch(r"[0-9a-f]{64}", value) is None
                   for value in active_ids) \
            or sorted(set(active_ids)) != active_ids:
        raise ValueError("thought recovery claim active IDs are invalid")
    canonical_ids = {record["record_id"] for record in canonical}
    if any(value not in canonical_ids for value in active_ids):
        raise ValueError("thought recovery claim active ID is unbound")
    if legacy is not None:
        required = {"before", "after", "complete", "entries", "unindexed",
                    "directory", "discarded", "indexed_before",
                    "indexed_after"}
        if not isinstance(legacy, dict) or set(legacy) != required \
                or not isinstance(legacy.get("before"), str) \
                or not isinstance(legacy.get("after"), str) \
                or legacy["after"] <= legacy["before"] \
                or legacy["before"] and re.fullmatch(
                    r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{64}\.json",
                    legacy["before"]) is None \
                or not isinstance(legacy.get("complete"), bool) \
                or not isinstance(legacy.get("entries"), list) \
                or isinstance(legacy.get("unindexed"), bool) \
                or not isinstance(legacy.get("unindexed"), int) \
                or legacy["unindexed"] < 0 \
                or isinstance(legacy.get("indexed_before"), bool) \
                or not isinstance(legacy.get("indexed_before"), int) \
                or legacy["indexed_before"] <= 0 \
                or isinstance(legacy.get("indexed_after"), bool) \
                or not isinstance(legacy.get("indexed_after"), int) \
                or legacy["indexed_after"] < 0:
            raise ValueError("thought recovery legacy claim is invalid")
        directory = _validated_thought_directory_generation(
            legacy.get("directory"))
        if directory is None:
            raise ValueError("thought recovery legacy directory is invalid")
        discarded = legacy.get("discarded")
        if not isinstance(discarded, list) \
                or len(discarded) > MAX_THOUGHT_RECOVERY_RECORDS \
                or any(not isinstance(item, str)
                       or re.fullmatch(r"[0-9a-f]{32}", item) is None
                       for item in discarded) \
                or len(set(discarded)) != len(discarded):
            raise ValueError(
                "thought recovery legacy discarded generations are invalid")
        entries = []
        for entry in legacy["entries"]:
            _thought_legacy_index_bytes(entry)
            entries.append(dict(entry))
        names = [entry["index_name"] for entry in entries]
        if len(entries) != len(canonical) or names != sorted(set(names)) \
                or not names or names[0] <= legacy["before"] \
                or names[-1] != legacy["after"] \
                or legacy["indexed_before"] - len(entries) \
                != legacy["indexed_after"] \
                or legacy["complete"] \
                != (legacy["indexed_after"] == 0):
            raise ValueError("thought recovery legacy range is invalid")
        pages = {record["page"]["slug"]: record["page"]
                 for record in canonical}
        if len(pages) != len(canonical):
            raise ValueError("thought recovery legacy pages are duplicated")
        for entry in entries:
            page = pages.get(entry["slug"])
            if page is None or page["ts"] != entry["ts"]:
                raise ValueError("thought recovery legacy page is unbound")
            frontmatter, body = _thought_page_parts(page)
            rendered = "---\n" + "\n".join(frontmatter) + "\n---\n" + body
            if hashlib.sha256(rendered.encode("utf-8")).hexdigest() \
                    != entry["page_sha256"]:
                raise ValueError("thought recovery legacy digest is unbound")
        legacy = {**legacy, "entries": entries, "directory": directory,
                  "discarded": list(discarded)}
    return {"records": canonical, "active_ids": active_ids,
            "legacy": legacy}


def _thought_recovery_claim_document(
        records, active_ids, legacy, claim_id=None):
    basis = _thought_recovery_claim_basis(records, active_ids, legacy)
    payload = json.dumps(
        basis, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf-8")
    claim_id = uuid.uuid4().hex if claim_id is None else claim_id
    if not isinstance(claim_id, str) \
            or re.fullmatch(r"[0-9a-f]{32}", claim_id) is None:
        raise ValueError("thought recovery claim identity is invalid")
    return {"schema": THOUGHT_RECOVERY_CLAIM_SCHEMA,
            "claim_id": claim_id,
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            **basis}


def _thought_recovery_claim_bytes(claim):
    if not isinstance(claim, dict) or set(claim) != {
            "schema", "claim_id", "payload_sha256", "records",
            "active_ids", "legacy"} \
            or claim.get("schema") != THOUGHT_RECOVERY_CLAIM_SCHEMA:
        raise ValueError("thought recovery claim schema is invalid")
    expected = _thought_recovery_claim_document(
        claim.get("records"), claim.get("active_ids"), claim.get("legacy"),
        claim_id=claim.get("claim_id"))
    if claim != expected:
        raise ValueError("thought recovery claim binding is invalid")
    encoded = (json.dumps(
        claim, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_THOUGHT_RECOVERY_BYTES:
        raise ValueError("thought recovery claim exceeds its byte bound")
    return encoded


def _read_thought_recovery_claim():
    path = _thought_recovery_claim_path()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    with siaqueue.regular_file_stream(
            descriptor, label="thought recovery claim") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_nlink != 1 \
                or before.st_mode & 0o077 \
                or before.st_size > MAX_THOUGHT_RECOVERY_BYTES:
            raise ValueError(
                "thought recovery claim is not a bounded private "
                "single-link file")
        raw = stream.read(MAX_THOUGHT_RECOVERY_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_THOUGHT_RECOVERY_BYTES:
        raise ValueError("thought recovery claim changed while read")
    try:
        claim = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("thought recovery claim is malformed") from exc
    if raw != _thought_recovery_claim_bytes(claim):
        raise ValueError("thought recovery claim is noncanonical")
    try:
        current = os.lstat(path)
    except OSError as exc:
        raise ValueError("thought recovery claim changed while read") from exc
    current_identity = (
        current.st_dev, current.st_ino, current.st_size,
        current.st_mtime_ns, current.st_ctime_ns)
    if current_identity != finished or not stat.S_ISREG(current.st_mode) \
            or current.st_uid != os.geteuid() or current.st_nlink != 1:
        raise ValueError("thought recovery claim changed while read")
    return claim


def _queue_thought_recovery(page_record):
    """Durably bind a page intent before any corresponding corpus write."""
    record = _thought_recovery_record(page_record)
    encoded = _thought_recovery_record_bytes(record)
    ensure_durable_directory(STATE, mode=0o700)
    with _owner_lease(_thought_recovery_lock_path(), "thought recovery"):
        directory = _ensure_private_recovery_directory(
            _thought_recovery_dir())
        path = os.path.join(directory, record["record_id"] + ".json")
        if os.path.lexists(path):
            existing, _identity = _read_thought_recovery_record(path)
            if existing != record:
                raise ValueError("thought recovery identity collision")
            return record["record_id"]
        records = _list_thought_recovery_records_locked()
        if len(records) >= MAX_THOUGHT_RECOVERY_RECORDS:
            raise ValueError("thought recovery queue reached its record bound")
        candidate = records + [record]
        _thought_recovery_claim_bytes(_thought_recovery_claim_document(
            candidate,
            sorted(item["record_id"] for item in candidate), None,
            claim_id="0" * 32))
        atomic_write(path, encoded.decode("utf-8"))
        os.chmod(path, 0o600)
    return record["record_id"]
def _thought_directory_generation(info):
    return {"device": info.st_dev, "inode": info.st_ino,
            "size": info.st_size, "mtime_ns": info.st_mtime_ns,
            "ctime_ns": info.st_ctime_ns}


def _validated_thought_directory_generation(value):
    if value is None:
        return None
    required = {"device", "inode", "size", "mtime_ns", "ctime_ns"}
    if not isinstance(value, dict) or set(value) != required \
            or any(isinstance(value[name], bool)
                   or not isinstance(value[name], int)
                   or value[name] < 0 for name in required):
        raise ValueError("legacy thought directory generation is invalid")
    return dict(value)


def _read_legacy_thought_directory_page(
        directory, generation, cookie, limit):
    """Inspect at most ``limit`` raw entries and return a durable next cookie.

    The baseline runs while the corpus owner is held.  Its first page pins the
    directory generation; a replacement, addition, removal, or rename between
    pages refuses instead of allowing a new entry behind the opaque Linux
    cookie to escape.  Every native SIA write is separately journaled before
    touching the directory.
    """
    generation = _validated_thought_directory_generation(generation)
    if isinstance(cookie, bool) or not isinstance(cookie, int) or cookie < 0 \
            or isinstance(limit, bool) or not isinstance(limit, int) \
            or limit <= 0:
        raise ValueError("legacy thought directory cursor is invalid")
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_DIRECTORY", 0))
    try:
        descriptor = os.open(directory, flags)
    except FileNotFoundError:
        if generation is not None or cookie:
            raise ThoughtDirectoryGenerationChanged(
                "legacy thought directory disappeared during baseline")
        return [], True, 0, None, 0
    except OSError as exc:
        if generation is not None or cookie:
            raise ThoughtDirectoryGenerationChanged(
                "legacy thought directory changed between bounded pages") \
                from exc
        raise
    directory_pointer = None
    try:
        before = os.fstat(descriptor)
        observed_generation = _thought_directory_generation(before)
        if not stat.S_ISDIR(before.st_mode) \
                or before.st_uid != os.geteuid():
            raise ValueError(
                "legacy thought source is not an owned directory")
        if generation is not None and generation != observed_generation:
            raise ThoughtDirectoryGenerationChanged(
                "legacy thought directory changed between bounded pages")
        scan_descriptor = os.dup(descriptor)
        directory_pointer = _SOURCE_LIBC.fdopendir(scan_descriptor)
        if not directory_pointer:
            saved_errno = ctypes.get_errno()
            os.close(scan_descriptor)
            raise OSError(saved_errno, os.strerror(saved_errno), directory)
        if cookie:
            _SOURCE_LIBC.seekdir(directory_pointer, cookie)
        selected = []
        inspected = 0
        complete = False
        while inspected < limit:
            ctypes.set_errno(0)
            record = _SOURCE_LIBC.readdir(directory_pointer)
            if not record:
                saved_errno = ctypes.get_errno()
                if saved_errno:
                    raise OSError(
                        saved_errno, os.strerror(saved_errno), directory)
                complete = True
                break
            inspected += 1
            raw_name = bytes(record.contents.d_name).split(b"\0", 1)[0]
            name = os.fsdecode(raw_name)
            if name in {".", ".."}:
                continue
            try:
                info = os.stat(
                    name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError as exc:
                raise ThoughtDirectoryGenerationChanged(
                    "legacy thought directory changed while scanned") from exc
            selected.append({"name": name, "mode": info.st_mode,
                             "device": info.st_dev, "inode": info.st_ino,
                             "size": info.st_size,
                             "mtime_ns": info.st_mtime_ns,
                             "ctime_ns": info.st_ctime_ns})
        next_cookie = (0 if complete else int(
            _SOURCE_LIBC.telldir(directory_pointer)))
        if next_cookie < 0:
            raise ValueError("legacy thought directory cookie is invalid")
        after = os.fstat(descriptor)
        try:
            target = os.stat(directory, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise ThoughtDirectoryGenerationChanged(
                "legacy thought directory changed while scanned") from exc
    finally:
        if directory_pointer:
            _SOURCE_LIBC.closedir(directory_pointer)
        os.close(descriptor)
    finished_generation = _thought_directory_generation(after)
    target_generation = _thought_directory_generation(target)
    if observed_generation != finished_generation \
            or observed_generation != target_generation \
            or not stat.S_ISDIR(target.st_mode):
        raise ThoughtDirectoryGenerationChanged(
            "legacy thought directory changed while scanned")
    selected.sort(key=lambda item: item["name"])
    return (selected, complete, next_cookie,
            observed_generation, inspected)


def _assert_legacy_thought_directory_generation(generation):
    """Refuse between-page corpus mutations before applying the baseline."""
    generation = _validated_thought_directory_generation(generation)
    directory = os.path.join(CORPUS, "thoughts")
    if generation is None:
        if os.path.lexists(directory):
            raise ThoughtDirectoryGenerationChanged(
                "legacy thought directory appeared after baseline scan")
        return
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_DIRECTORY", 0))
    try:
        descriptor = os.open(directory, flags)
    except OSError as exc:
        raise ThoughtDirectoryGenerationChanged(
            "legacy thought directory changed after baseline scan") from exc
    try:
        info = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if not stat.S_ISDIR(info.st_mode) \
            or info.st_uid != os.geteuid() \
            or _thought_directory_generation(info) != generation:
        raise ThoughtDirectoryGenerationChanged(
            "legacy thought directory changed after baseline scan")


def _current_legacy_thought_directory_generation():
    """Return one owned no-follow directory generation, or absent."""
    directory = os.path.join(CORPUS, "thoughts")
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_DIRECTORY", 0))
    try:
        descriptor = os.open(directory, flags)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        raise ValueError("legacy thought source is not an owned directory")
    return _thought_directory_generation(info)


def _thought_legacy_index_entry(page_name, record, page_text):
    if not isinstance(page_name, str) \
            or re.fullmatch(r"[a-z0-9_.-]+\.md", page_name) is None:
        raise ValueError("legacy thought page name is invalid")
    page = _canonical_thought_page_record(record)
    if page.get("slug") != "thoughts/" + page_name[:-3]:
        raise ValueError("legacy thought page identity is invalid")
    if not isinstance(page_text, str):
        raise ValueError("legacy thought page text is invalid")
    stamp = page["ts"].replace("-", "").replace(":", "")
    index_name = (stamp + "-"
                  + hashlib.sha256(page["slug"].encode("utf-8")).hexdigest()
                  + ".json")
    return {"schema": THOUGHT_LEGACY_INDEX_SCHEMA,
            "index_name": index_name, "page_name": page_name,
            "slug": page["slug"], "ts": page["ts"],
            "page_sha256": hashlib.sha256(
                page_text.encode("utf-8")).hexdigest()}


def _thought_legacy_index_bytes(entry):
    required = {"schema", "index_name", "page_name", "slug", "ts",
                "page_sha256"}
    if not isinstance(entry, dict) or set(entry) != required \
            or entry.get("schema") != THOUGHT_LEGACY_INDEX_SCHEMA \
            or not isinstance(entry.get("index_name"), str) \
            or re.fullmatch(
                r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{64}\.json",
                entry["index_name"]) is None \
            or not isinstance(entry.get("page_name"), str) \
            or re.fullmatch(
                r"[a-z0-9_.-]+\.md", entry["page_name"]) is None \
            or not isinstance(entry.get("slug"), str) \
            or entry["slug"] != "thoughts/" + entry["page_name"][:-3] \
            or _canonical_corpus_slug(entry["slug"]) != entry["slug"] \
            or _canonical_utc_timestamp(entry.get("ts")) != entry["ts"] \
            or not isinstance(entry.get("page_sha256"), str) \
            or re.fullmatch(
                r"[0-9a-f]{64}", entry["page_sha256"]) is None:
        raise ValueError("legacy thought index entry is invalid")
    expected_name = (entry["ts"].replace("-", "").replace(":", "") + "-"
                     + hashlib.sha256(
                         entry["slug"].encode("utf-8")).hexdigest()
                     + ".json")
    if entry["index_name"] != expected_name:
        raise ValueError("legacy thought index identity is invalid")
    encoded = (json.dumps(
        entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
        raise ValueError("legacy thought index entry exceeds its byte bound")
    return encoded


def _read_thought_legacy_index_entry(path):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with siaqueue.regular_file_stream(
            descriptor, label="legacy thought index") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_nlink != 1 \
                or before.st_mode & 0o077 \
                or before.st_size > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
            raise ValueError(
                "legacy thought index is not a bounded private "
                "single-link file")
        raw = stream.read(MAX_THOUGHT_RECOVERY_RECORD_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
        raise ValueError("legacy thought index changed while read")
    try:
        entry = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("legacy thought index is malformed") from exc
    if raw != _thought_legacy_index_bytes(entry) \
            or os.path.basename(path) != entry["index_name"]:
        raise ValueError("legacy thought index path binding is invalid")
    try:
        current = os.lstat(path)
    except OSError as exc:
        raise ValueError("legacy thought index changed while read") from exc
    current_identity = (
        current.st_dev, current.st_ino, current.st_size,
        current.st_mtime_ns, current.st_ctime_ns)
    if current_identity != finished or not stat.S_ISREG(current.st_mode) \
            or current.st_uid != os.geteuid() or current.st_nlink != 1:
        raise ValueError("legacy thought index changed while read")
    return entry


def _write_thought_legacy_index(entry):
    encoded = _thought_legacy_index_bytes(entry)
    directory = _ensure_private_recovery_directory(
        _thought_legacy_index_dir())
    path = os.path.join(directory, entry["index_name"])
    if os.path.lexists(path):
        if _read_thought_legacy_index_entry(path) != entry:
            raise ValueError("legacy thought index identity collision")
        return path
    atomic_write(path, encoded.decode("utf-8"))
    os.chmod(path, 0o600)
    return path




def _thought_mind_replay_records(claim):
    """Return one validated claim's exact replay identities and scope."""
    _thought_recovery_claim_bytes(claim)
    table = ("thought_mind_replay" if claim.get("legacy") is not None
             else "native_thought_mind_replay")
    return [(table, record["record_id"], claim["claim_id"],
             claim["payload_sha256"],
             record["page"].get("queue_id", ""))
            for record in claim["records"]]


def _thought_mind_replay_intent(claim):
    """Durably stage exact page IDs before changing their policy projection."""
    records = _thought_mind_replay_records(claim)
    if not records:
        return set()
    if claim.get("legacy") is None:
        # A prior transaction may have crashed after producer acknowledgment
        # but before end-of-pulse receipt retirement. Retire those now, before
        # enforcing capacity, while preserving every exact record in this
        # already-durable active claim.
        _finalize_native_thought_mind_replay(
            protected_record_ids={record["record_id"]
                                  for record in claim["records"]})
    applied = set()
    with _thought_mind_replay_catalog() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            native_rows = connection.execute(
                "SELECT COUNT(*) FROM native_thought_mind_replay"
                ).fetchone()[0]
            for table, record_id, claim_id, claim_sha256, queue_id in records:
                row = connection.execute(
                    "SELECT claim_id, claim_sha256, state"
                    + (", queue_id" if table ==
                       "native_thought_mind_replay" else "") + " "
                    f"FROM {table} "
                    "WHERE record_id = ?", (record_id,)).fetchone()
                if row is None:
                    if table == "native_thought_mind_replay" \
                            and native_rows >= MAX_THOUGHT_RECOVERY_RECORDS:
                        raise ValueError(
                            "thought mind replay journal reached its bound")
                    if table == "native_thought_mind_replay":
                        connection.execute(
                            "INSERT INTO native_thought_mind_replay "
                            "(record_id, claim_id, claim_sha256, state, "
                            "queue_id) VALUES (?, ?, ?, ?, ?)",
                            (record_id, claim_id, claim_sha256, "pending",
                             queue_id))
                    else:
                        connection.execute(
                            "INSERT INTO thought_mind_replay "
                            "(record_id, claim_id, claim_sha256, state) "
                            "VALUES (?, ?, ?, ?)",
                            (record_id, claim_id, claim_sha256, "pending"))
                    if table == "native_thought_mind_replay":
                        native_rows += 1
                    continue
                prior_claim, prior_sha256, state = row[:3]
                if not isinstance(prior_claim, str) \
                        or re.fullmatch(r"[0-9a-f]{32}", prior_claim) is None \
                        or not isinstance(prior_sha256, str) \
                        or re.fullmatch(
                            r"[0-9a-f]{64}", prior_sha256) is None \
                        or state not in {"pending", "applied"}:
                    raise ValueError(
                        "thought mind replay journal row is invalid")
                if table == "native_thought_mind_replay" \
                        and (row[3] != queue_id
                             or not isinstance(row[3], str)
                             or (row[3] and re.fullmatch(
                                 r"[0-9a-f]{32}", row[3]) is None)):
                    raise ValueError(
                        "thought mind replay queue binding is invalid")
                if state == "pending" and (
                        prior_claim != claim_id
                        or prior_sha256 != claim_sha256):
                    raise ValueError(
                        "another thought mind replay claim is pending")
                if state == "applied":
                    applied.add(record_id)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return applied


def _mark_thought_mind_replay_applied_locked(claim):
    """Commit staged page IDs only after policy state and store are durable."""
    records = _thought_mind_replay_records(claim)
    if not records:
        return
    with _thought_mind_replay_catalog() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for table, record_id, claim_id, claim_sha256, queue_id in records:
                row = connection.execute(
                    "SELECT claim_id, claim_sha256, state"
                    + (", queue_id" if table ==
                       "native_thought_mind_replay" else "") + " "
                    f"FROM {table} "
                    "WHERE record_id = ?", (record_id,)).fetchone()
                if row is None:
                    raise ValueError("thought mind replay intent is missing")
                prior_claim, prior_sha256, state = row[:3]
                if not isinstance(prior_claim, str) \
                        or re.fullmatch(r"[0-9a-f]{32}", prior_claim) is None \
                        or not isinstance(prior_sha256, str) \
                        or re.fullmatch(
                            r"[0-9a-f]{64}", prior_sha256) is None \
                        or state not in {"pending", "applied"}:
                    raise ValueError(
                        "thought mind replay journal row is invalid")
                if table == "native_thought_mind_replay" \
                        and row[3] != queue_id:
                    raise ValueError(
                        "thought mind replay queue binding is invalid")
                if state == "applied":
                    continue
                if state != "pending" or prior_claim != claim_id \
                        or prior_sha256 != claim_sha256:
                    raise ValueError("thought mind replay intent is misbound")
                connection.execute(
                    f"UPDATE {table} SET state = ? "
                    "WHERE record_id = ?", ("applied", record_id))
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _clear_thought_mind_replay_scope_locked(table):
    """Clear one finalized scope; unlink the journal only when wholly empty."""
    if table not in {"thought_mind_replay",
                     "native_thought_mind_replay"}:
        raise ValueError("thought mind replay scope is invalid")
    path = _thought_mind_replay_path()
    if not os.path.lexists(path):
        return
    with _thought_mind_replay_catalog() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(f"DELETE FROM {table}")
            remaining = sum(connection.execute(
                f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in ("thought_mind_replay",
                             "native_thought_mind_replay"))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    if remaining:
        return
    _remove_empty_thought_mind_replay_artifacts_locked()


def _remove_empty_thought_mind_replay_artifacts_locked():
    """Unlink an already-empty replay database and its private sidecars."""
    path = _thought_mind_replay_path()
    changed = False
    for suffix in ("", "-journal", "-wal", "-shm"):
        target = path + suffix
        if not os.path.lexists(target):
            continue
        info = os.lstat(target)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise ValueError("thought mind replay artifact is invalid")
        os.unlink(target)
        changed = True
    if changed:
        _sync_directory(STATE)


def _clear_legacy_thought_mind_replay_locked():
    _clear_thought_mind_replay_scope_locked("thought_mind_replay")


def _clear_native_thought_mind_replay_locked():
    _clear_thought_mind_replay_scope_locked(
        "native_thought_mind_replay")


def _pending_external_thought_queue_ids():
    """Return a bounded stable view of producers still able to requeue."""
    queue_dir = siaqueue._queue_dir(STATE)
    try:
        queue_info = os.lstat(queue_dir)
    except FileNotFoundError:
        agent_requests, agent_errors = [], []
    else:
        if not stat.S_ISDIR(queue_info.st_mode):
            raise ValueError("agent thought producer is not a directory")
        # ``pending`` owns the queue lease for its bounded snapshot.  Taking
        # the same flock here as well would open a second file description in
        # this process and block forever on our own exclusive lock.
        agent_requests, agent_errors = siaqueue.pending(STATE)
    serious_agent_errors = [
        row for row in agent_errors
        if row.get("error") != "agent queue reached its bounded capacity"]
    if serious_agent_errors:
        raise RuntimeError(
            "agent thought producer snapshot is incomplete")
    pending = {
        record["request_id"] for _path, record, _identity in agent_requests}
    if any(re.fullmatch(r"[0-9a-f]{32}", value) is None
           for value in pending):
        raise ValueError("agent thought producer identity is invalid")

    with _owner_lease(THOUGHT_INBOX_LOCK, "thought inbox"):
        for path in (THOUGHT_INBOX_PATH, _thought_inbox_claim_path()):
            if not os.path.lexists(path):
                continue
            for row in _read_thought_inbox(path):
                pending.add(row["_queue_id"])
    if len(pending) > (siaqueue.MAX_PENDING_REQUESTS
                       + MAX_THOUGHT_INBOX_ITEMS):
        raise ValueError("thought producer identity snapshot exceeds its bound")
    return pending


def _finalize_native_thought_mind_replay(protected_record_ids=()):
    """Retire only applied receipts whose exact producer is durably gone."""
    if not isinstance(protected_record_ids, (set, frozenset, list, tuple)):
        raise ValueError("native thought replay protection is invalid")
    protected = set(protected_record_ids)
    if len(protected) > MAX_THOUGHT_RECOVERY_RECORDS \
            or any(not isinstance(record_id, str)
                   or re.fullmatch(r"[0-9a-f]{64}", record_id) is None
                   for record_id in protected):
        raise ValueError("native thought replay protection is invalid")
    if not os.path.lexists(_thought_mind_replay_path()):
        return
    pending = _pending_external_thought_queue_ids()
    with _owner_lease(_thought_recovery_lock_path(), "thought recovery"):
        path = _thought_mind_replay_path()
        if not os.path.lexists(path):
            return
        with _thought_mind_replay_catalog() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                rows = connection.execute(
                    "SELECT record_id, queue_id, state "
                    "FROM native_thought_mind_replay "
                    "ORDER BY record_id LIMIT ?",
                    (MAX_THOUGHT_RECOVERY_RECORDS + 1,)).fetchall()
                if len(rows) > MAX_THOUGHT_RECOVERY_RECORDS:
                    raise ValueError(
                        "native thought replay journal exceeds its bound")
                for record_id, queue_id, state in rows:
                    if not isinstance(record_id, str) \
                            or re.fullmatch(
                                r"[0-9a-f]{64}", record_id) is None \
                            or not isinstance(queue_id, str) \
                            or (queue_id and re.fullmatch(
                                r"[0-9a-f]{32}", queue_id) is None) \
                            or state not in {"pending", "applied"}:
                        raise ValueError(
                            "native thought replay row is invalid")
                    if state != "applied" and record_id in protected:
                        continue
                    if state != "applied":
                        raise RuntimeError(
                            "native thought replay intent remains pending")
                    if record_id not in protected \
                            and (not queue_id or queue_id not in pending):
                        connection.execute(
                            "DELETE FROM native_thought_mind_replay "
                            "WHERE record_id = ?", (record_id,))
                remaining = sum(connection.execute(
                    f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                    for name in ("thought_mind_replay",
                                 "native_thought_mind_replay"))
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        if not remaining:
            _remove_empty_thought_mind_replay_artifacts_locked()


def _upsert_thought_legacy_catalog(entries):
    canonical = []
    for entry in entries:
        encoded = _thought_legacy_index_bytes(entry).decode("utf-8")
        canonical.append((entry["index_name"], encoded))
    if not canonical:
        return
    with _thought_legacy_catalog() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for name, encoded in canonical:
                row = connection.execute(
                    "SELECT entry_json FROM legacy_thought_index "
                    "WHERE index_name = ?", (name,)).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO legacy_thought_index "
                        "(index_name, entry_json) VALUES (?, ?)",
                        (name, encoded))
                elif row != (encoded,):
                    raise ValueError(
                        "legacy thought catalog identity collision")
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _thought_legacy_catalog_batch(after, limit):
    if not isinstance(after, str) or isinstance(limit, bool) \
            or not isinstance(limit, int) or limit <= 0:
        raise ValueError("legacy thought catalog cursor is invalid")
    with _thought_legacy_catalog() as connection:
        rows = connection.execute(
            "SELECT index_name, entry_json FROM legacy_thought_index "
            "WHERE index_name > ? ORDER BY index_name LIMIT ?",
            (after, limit)).fetchall()
        entries = []
        for name, encoded in rows:
            if not isinstance(name, str) or not isinstance(encoded, str) \
                    or len(encoded.encode("utf-8")) \
                    > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
                raise ValueError("legacy thought catalog row is invalid")
            try:
                entry = json.loads(encoded)
            except (UnicodeError, ValueError, RecursionError) as exc:
                raise ValueError("legacy thought catalog row is malformed") \
                    from exc
            if encoded.encode("utf-8") != _thought_legacy_index_bytes(entry) \
                    or entry["index_name"] != name:
                raise ValueError("legacy thought catalog row is misbound")
            entries.append(entry)
        more = False
        if entries:
            more = connection.execute(
                "SELECT 1 FROM legacy_thought_index "
                "WHERE index_name > ? LIMIT 1",
                (entries[-1]["index_name"],)).fetchone() is not None
    return entries, more


def _load_thought_legacy_scan():
    state = read_state_json(
        _thought_legacy_scan_path(),
        {"schema": THOUGHT_LEGACY_SCAN_SCHEMA,
         "phase": "index", "after": "", "unindexed": 0,
         "indexed": 0, "cookie": 0, "directory": None,
         "discarded": [], "reset_id": None},
        "legacy thought recovery scan")
    return _validated_thought_legacy_scan(state)


def _validated_thought_legacy_scan(state):
    if not isinstance(state, dict) or set(state) != {
            "schema", "phase", "after", "unindexed", "indexed",
            "cookie", "directory", "discarded", "reset_id"} \
            or state.get("schema") != THOUGHT_LEGACY_SCAN_SCHEMA \
            or state.get("phase") \
            not in {"index", "apply", "complete", "reset", "blocked"} \
            or not isinstance(state.get("after"), str) \
            or len(state["after"].encode("utf-8")) \
            > MAX_CORPUS_COMPONENT_BYTES \
            or isinstance(state.get("unindexed"), bool) \
            or not isinstance(state.get("unindexed"), int) \
            or state["unindexed"] < 0 \
            or isinstance(state.get("indexed"), bool) \
            or not isinstance(state.get("indexed"), int) \
            or state["indexed"] < 0 \
            or isinstance(state.get("cookie"), bool) \
            or not isinstance(state.get("cookie"), int) \
            or state["cookie"] < 0:
        raise ValueError("legacy thought recovery scan state is invalid")
    discarded = state.get("discarded")
    if not isinstance(discarded, list) \
            or len(discarded) > MAX_THOUGHT_RECOVERY_RECORDS \
            or any(not isinstance(item, str)
                   or re.fullmatch(r"[0-9a-f]{32}", item) is None
                   for item in discarded) \
            or len(set(discarded)) != len(discarded):
        raise ValueError("legacy thought discarded generations are invalid")
    reset_id = state.get("reset_id")
    if reset_id is not None and (not isinstance(reset_id, str)
                                 or re.fullmatch(
                                     r"[0-9a-f]{32}", reset_id) is None):
        raise ValueError("legacy thought reset identity is invalid")
    directory = _validated_thought_directory_generation(
        state.get("directory"))
    invalid_cursor = (
        (state["phase"] == "index" and bool(state["after"]))
        or (state["phase"] != "index" and bool(state["cookie"]))
        or (state["phase"] in {"apply", "reset"}
            and bool(state["after"])
            and re.fullmatch(
                r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{64}\.json",
                state["after"]) is None)
        or (state["phase"] == "complete"
            and bool(state["after"] or state["indexed"]))
        or (state["phase"] == "reset"
            and bool(state["indexed"] or state["cookie"]
                     or state["unindexed"]))
        or (state["phase"] == "blocked"
            and bool(state["after"] or state["indexed"]
                     or state["cookie"] or state["unindexed"]
                     or directory is not None))
        or (directory is None
            and bool(state["cookie"] or state["indexed"]))
        or (state["phase"] == "reset") != (reset_id is not None)
        or (reset_id is not None
            and (not discarded or discarded[-1] != reset_id)))
    if invalid_cursor:
        raise ValueError("legacy thought recovery scan cursor is invalid")
    return {**state, "directory": directory,
            "discarded": list(discarded), "reset_id": reset_id}


def _save_thought_legacy_scan(state):
    probe = _validated_thought_legacy_scan(dict(state))
    atomic_write(_thought_legacy_scan_path(), json.dumps(
        probe, sort_keys=True, separators=(",", ":"), allow_nan=False))
    os.chmod(_thought_legacy_scan_path(), 0o600)


def _schedule_legacy_thought_reset_locked(state):
    """Persist a new rebuild generation before reporting stale-cookie debt."""
    state = _validated_thought_legacy_scan(state)
    if state["phase"] == "reset":
        return state
    if len(state["discarded"]) >= MAX_THOUGHT_RECOVERY_RECORDS:
        _save_thought_legacy_scan({
            "schema": THOUGHT_LEGACY_SCAN_SCHEMA,
            "phase": "blocked", "after": "", "unindexed": 0,
            "indexed": 0, "cookie": 0, "directory": None,
            "discarded": state["discarded"], "reset_id": None})
        raise ValueError(
            "legacy thought recovery exhausted its reset generation bound")
    reset_id = uuid.uuid4().hex
    reset = {"schema": THOUGHT_LEGACY_SCAN_SCHEMA,
             "phase": "reset", "after": "", "unindexed": 0,
             "indexed": 0, "cookie": 0, "directory": None,
             "discarded": state["discarded"] + [reset_id],
             "reset_id": reset_id}
    _save_thought_legacy_scan(reset)
    return reset


def _archive_legacy_reset_path(source, destination, *, directory):
    """Idempotently rename one stale derived artifact for diagnostics."""
    source_exists = os.path.lexists(source)
    destination_exists = os.path.lexists(destination)
    if source_exists and destination_exists:
        raise ValueError("legacy thought reset artifacts are ambiguous")
    path = source if source_exists else destination
    if not os.path.lexists(path):
        return False
    info = os.lstat(path)
    expected = stat.S_ISDIR(info.st_mode) if directory \
        else stat.S_ISREG(info.st_mode)
    if not expected or info.st_uid != os.geteuid():
        raise ValueError("legacy thought reset artifact is invalid")
    if source_exists:
        os.rename(source, destination)
        return True
    return False


def _execute_legacy_thought_reset_locked(state):
    """Archive one stale derived baseline, then restart at cookie zero.

    The catalog and JSON index are rebuildable derivatives, not authority.
    Re-reading their old page paths would permanently wedge a legitimate
    quiescent delete, rename, or replacement. Immutable active claims are
    handled before reset scheduling, and acknowledged claims already reside in
    both authoritative projections. Preserve those projections, archive the
    stale derivatives for diagnosis, and bind a fresh scan to the directory's
    current generation. Fresh pages still pass the ordinary bounded no-follow,
    exact-metadata, and digest checks before they can produce another claim.
    """
    state = _validated_thought_legacy_scan(state)
    if state["phase"] != "reset":
        return state
    reset_id = state["reset_id"]
    catalog = _thought_legacy_catalog_path()
    catalog_archive = catalog + ".discarded-" + reset_id
    if os.path.lexists(catalog) and os.path.lexists(catalog_archive):
        raise ValueError("legacy thought reset catalogs are ambiguous")
    generation = _current_legacy_thought_directory_generation()
    changed = _archive_legacy_reset_path(
        _thought_legacy_index_dir(),
        _thought_legacy_index_dir() + ".discarded-" + reset_id,
        directory=True)
    changed = _archive_legacy_reset_path(
        catalog, catalog_archive, directory=False) or changed
    for suffix in ("-journal", "-wal", "-shm"):
        changed = _archive_legacy_reset_path(
            catalog + suffix, catalog_archive + suffix,
            directory=False) or changed
    if changed:
        _sync_directory(STATE)
    restarted = {"schema": THOUGHT_LEGACY_SCAN_SCHEMA,
                 "phase": "index", "after": "", "unindexed": 0,
                 "indexed": 0, "cookie": 0, "directory": generation,
                 "discarded": state["discarded"], "reset_id": None}
    _save_thought_legacy_scan(restarted)
    return restarted


def _index_legacy_thought_batch_locked(state):
    directory = os.path.join(CORPUS, "thoughts")
    entries, complete, next_cookie, generation, _inspected = \
        _read_legacy_thought_directory_page(
            directory, state["directory"], state["cookie"],
            MAX_THOUGHT_RECOVERY_RECORDS)
    indexed_entries = []
    unindexed = state["unindexed"]
    for observed in entries:
        name = observed["name"]
        if re.fullmatch(r"[a-z0-9_.-]+\.md", name) is None:
            continue
        if not stat.S_ISREG(observed["mode"]):
            raise ValueError("legacy thought page is not a regular file")
        slug = _canonical_corpus_slug("thoughts/" + name[:-3])
        page_text = _read_thought_page_text(slug)
        metadata = re.findall(r"^sia_thought: (.*)$", page_text, re.M)
        if not metadata:
            # Pre-self-describing pages have no exact record to replay. They
            # are not evidence of a missing signal, so preserve their origin
            # boundary, record the migration diagnostic, and advance only
            # after this page's bounded stable read has completed.
            unindexed += 1
            log(f"legacy thought page lacks recovery metadata: {slug}")
            continue
        record = _decode_exact_thought_page(slug, page_text)
        index_entry = _thought_legacy_index_entry(name, record, page_text)
        _write_thought_legacy_index(index_entry)
        indexed_entries.append(index_entry)
    _upsert_thought_legacy_catalog(indexed_entries)
    _assert_legacy_thought_directory_generation(generation)
    updated = {"schema": THOUGHT_LEGACY_SCAN_SCHEMA,
               "phase": "apply" if complete else "index",
               "after": "", "unindexed": unindexed,
               "indexed": state["indexed"] + len(indexed_entries),
               "cookie": 0 if complete else next_cookie,
               "directory": generation,
               "discarded": state["discarded"], "reset_id": None}
    # The opaque cookie follows every durable JSON index entry and its ordered
    # catalog row. A crash before this write merely revalidates the same
    # content-bound page of entries on retry.
    _save_thought_legacy_scan(updated)
    return updated


def _legacy_thought_claim_locked(state):
    _assert_legacy_thought_directory_generation(state["directory"])
    directory = _thought_legacy_index_dir()
    catalog_entries, more_entries = _thought_legacy_catalog_batch(
        state["after"], MAX_THOUGHT_RECOVERY_RECORDS)
    if not catalog_entries:
        if state["indexed"]:
            raise ValueError("legacy thought catalog lost indexed pages")
        _save_thought_legacy_scan({
            "schema": THOUGHT_LEGACY_SCAN_SCHEMA,
            "phase": "complete", "after": "",
            "unindexed": state["unindexed"], "indexed": 0,
            "cookie": 0, "directory": state["directory"],
            "discarded": state["discarded"], "reset_id": None})
        return None
    if len(catalog_entries) > state["indexed"] \
            or not more_entries \
            and len(catalog_entries) != state["indexed"] \
            or more_entries and len(catalog_entries) >= state["indexed"]:
        raise ValueError("legacy thought catalog count is inconsistent")
    entries = []
    records = []
    total = 0
    admitted_names = []
    for catalog_entry in catalog_entries:
        entry = _read_thought_legacy_index_entry(os.path.join(
            directory, catalog_entry["index_name"]))
        if entry != catalog_entry:
            raise ValueError("legacy thought catalog differs from its index")
        page_text = _read_thought_page_text(entry["slug"])
        page_bytes = len(page_text.encode("utf-8"))
        if page_bytes > MAX_THOUGHT_RECOVERY_BYTES - total:
            more_entries = True
            break
        if hashlib.sha256(page_text.encode("utf-8")).hexdigest() \
                != entry["page_sha256"]:
            raise ValueError("legacy thought page changed after indexing")
        page = _decode_exact_thought_page(entry["slug"], page_text)
        if page["ts"] != entry["ts"]:
            raise ValueError("legacy thought index timestamp is misbound")
        records.append(_thought_recovery_record(page))
        entries.append(entry)
        admitted_names.append(entry["index_name"])
        total += page_bytes
    if not records:
        raise ValueError("legacy thought apply batch cannot make progress")
    _assert_legacy_thought_directory_generation(state["directory"])
    indexed_after = state["indexed"] - len(entries)
    complete = not more_entries and indexed_after == 0
    if not complete and indexed_after <= 0:
        raise ValueError("legacy thought catalog cursor cannot make progress")
    legacy = {"before": state["after"], "after": admitted_names[-1],
              "complete": complete, "entries": entries,
              "unindexed": state["unindexed"],
              "directory": state["directory"],
              "discarded": state["discarded"],
              "indexed_before": state["indexed"],
              "indexed_after": indexed_after}
    return _thought_recovery_claim_document(records, [], legacy)


def _write_thought_recovery_claim_locked(claim):
    encoded = _thought_recovery_claim_bytes(claim)
    path = _thought_recovery_claim_path()
    if os.path.lexists(path):
        existing = _read_thought_recovery_claim()
        if existing != claim:
            raise ValueError("another thought recovery claim is active")
        return existing
    atomic_write(path, encoded.decode("utf-8"))
    os.chmod(path, 0o600)
    return claim


def _prepare_thought_recovery_claim():
    """Create at most one bounded immutable replay generation."""
    if _CORPUS_OWNER_DEPTH.get() <= 0:
        raise RuntimeError("thought recovery requires the corpus owner")
    ensure_durable_directory(STATE, mode=0o700)
    with _owner_lease(_thought_recovery_lock_path(), "thought recovery"):
        existing = _read_thought_recovery_claim()
        if existing is not None:
            return existing
        state = _load_thought_legacy_scan()
        if state["phase"] == "blocked":
            raise RuntimeError(
                "legacy thought recovery is blocked by reset capacity")
        if state["phase"] == "complete":
            # Once this cursor is durable, later native writes are protected by
            # their own pre-page intents and no legacy rescan can reopen a page.
            # The potentially corpus-sized exact replay journal is transient.
            _clear_legacy_thought_mind_replay_locked()
        try:
            if state["phase"] == "reset":
                state = _execute_legacy_thought_reset_locked(state)
                if state["phase"] == "reset":
                    return None
            if state["phase"] == "index":
                state = _index_legacy_thought_batch_locked(state)
                if state["phase"] == "index":
                    return None
            if state["phase"] == "apply":
                claim = _legacy_thought_claim_locked(state)
                if claim is not None:
                    return _write_thought_recovery_claim_locked(claim)
                state = _load_thought_legacy_scan()
        except ThoughtDirectoryGenerationChanged as exc:
            if state["phase"] == "reset":
                _save_thought_legacy_scan({
                    **state, "after": "", "directory": None})
            else:
                _schedule_legacy_thought_reset_locked(state)
            raise RuntimeError(
                "legacy thought directory changed; durable reset scheduled; "
                "retry after corpus writers are quiescent") from exc
        if state["phase"] != "complete":
            raise ValueError("legacy thought recovery did not reach a phase")
        records = _list_thought_recovery_records_locked()
        if not records:
            return None
        claim = _thought_recovery_claim_document(
            records, sorted(record["record_id"] for record in records), None)
        return _write_thought_recovery_claim_locked(claim)


def _thought_recovery_receipt(claim):
    return {"claim_id": claim["claim_id"],
            "payload_sha256": claim["payload_sha256"]}


def _validated_thought_recovery_receipt(target):
    receipt = target.get("thought_recovery")
    if receipt is None:
        return None
    if not isinstance(receipt, dict) or set(receipt) != {
            "claim_id", "payload_sha256"} \
            or not isinstance(receipt.get("claim_id"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", receipt["claim_id"]) is None \
            or not isinstance(receipt.get("payload_sha256"), str) \
            or re.fullmatch(
                r"[0-9a-f]{64}", receipt["payload_sha256"]) is None:
        raise ValueError("thought recovery receipt is invalid")
    return dict(receipt)


def _materialize_thought_recovery_page(record):
    page = record["page"]
    slug = page["slug"]
    try:
        existing = _read_thought_page_text(slug)
    except FileNotFoundError:
        frontmatter, body = _thought_page_parts(page)
        write_page(slug, frontmatter, body)
        existing = _read_thought_page_text(slug)
    durable = _decode_exact_thought_page(slug, existing)
    if durable != page:
        raise ValueError("thought recovery page conflicts with its intent")
    return durable


def _apply_thought_recovery_claim(store, mind, claim):
    """Apply one immutable claim independently to both projections."""
    _thought_recovery_claim_bytes(claim)
    if not isinstance(store, dict) or not isinstance(store.get("thoughts"), list):
        raise ValueError("thought recovery requires a thought store")
    if mind is not None and not isinstance(mind, dict):
        raise ValueError("thought recovery mind must be an object")
    mind_applied = _thought_mind_replay_intent(claim)
    pages = [_materialize_thought_recovery_page(record)
             for record in claim["records"]]
    receipt = _thought_recovery_receipt(claim)
    recovered = reinforced = 0

    if _validated_thought_recovery_receipt(store) != receipt:
        by_slug = {row.get("slug"): row for row in store["thoughts"]
                   if isinstance(row, dict)
                   and isinstance(row.get("slug"), str)}
        by_queue = {row.get("queue_id"): row for row in store["thoughts"]
                    if isinstance(row, dict)
                    and isinstance(row.get("queue_id"), str)}
        for page in pages:
            slug = page["slug"]
            existing = by_slug.get(slug)
            if existing is None and page.get("queue_id"):
                existing = by_queue.get(page["queue_id"])
            if existing is not None:
                comparable = {key: existing.get(key) for key in page
                              if key != "slug"}
                expected = {key: value for key, value in page.items()
                            if key != "slug"}
                if comparable != expected \
                        or existing.get("slug") not in (None, slug):
                    raise RuntimeError(
                        "thought state differs from its recovery page")
                if existing.get("slug") is None:
                    existing["slug"] = slug
                    recovered += 1
                continue
            row = dict(page)
            store["thoughts"].append(row)
            by_slug[slug] = row
            if page.get("queue_id"):
                by_queue[page["queue_id"]] = row
            recovered += 1
        store["thoughts"].sort(
            key=lambda row: (str(row.get("ts", "")),
                             str(row.get("slug", ""))))
        store["thoughts"] = store["thoughts"][
            -MAX_THOUGHT_INBOX_ITEMS:]
        store["thought_recovery"] = receipt

    if mind is not None \
            and _validated_thought_recovery_receipt(mind) != receipt:
        for record, page in zip(claim["records"], pages):
            if record["record_id"] in mind_applied:
                continue
            reinforced += siamind.apply_exact_thought_reinforcement(
                mind, page["links"], _thought_reinforcement_ts(page),
                record["record_id"])
        mind["thought_recovery"] = receipt
    return recovered, reinforced


def _commit_thought_legacy_claim(claim):
    legacy = claim.get("legacy")
    if legacy is None:
        return
    state = _load_thought_legacy_scan()
    expected = {"schema": THOUGHT_LEGACY_SCAN_SCHEMA,
                "phase": "apply", "after": legacy["before"],
                "unindexed": legacy["unindexed"],
                "indexed": legacy["indexed_before"], "cookie": 0,
                "directory": legacy["directory"],
                "discarded": legacy["discarded"], "reset_id": None}
    target = ({"schema": THOUGHT_LEGACY_SCAN_SCHEMA,
               "phase": "complete", "after": "",
               "unindexed": legacy["unindexed"], "indexed": 0,
               "cookie": 0, "directory": legacy["directory"],
               "discarded": legacy["discarded"], "reset_id": None}
              if legacy["complete"] else
              {"schema": THOUGHT_LEGACY_SCAN_SCHEMA,
               "phase": "apply", "after": legacy["after"],
               "unindexed": legacy["unindexed"],
               "indexed": legacy["indexed_after"], "cookie": 0,
               "directory": legacy["directory"],
               "discarded": legacy["discarded"], "reset_id": None})
    if state == target:
        return
    if state != expected:
        raise ValueError("legacy thought scan cursor conflicts with its claim")
    _save_thought_legacy_scan(target)


def _sync_directory(path):
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _acknowledge_thought_recovery_claim(claim):
    """Remove claimed inputs, then the self-contained claim, crash-safely."""
    with _owner_lease(_thought_recovery_lock_path(), "thought recovery"):
        durable = _read_thought_recovery_claim()
        if durable != claim:
            raise ValueError("thought recovery claim changed before acknowledgment")
        active_by_id = {record["record_id"]: record
                        for record in claim["records"]}
        active_directory = _thought_recovery_dir()
        active_changed = False
        for record_id in claim["active_ids"]:
            path = os.path.join(active_directory, record_id + ".json")
            try:
                observed, _identity = _read_thought_recovery_record(path)
            except FileNotFoundError:
                continue
            if observed != active_by_id[record_id]:
                raise ValueError(
                    "thought recovery record changed before acknowledgment")
            os.unlink(path)
            active_changed = True
        if active_changed:
            _sync_directory(active_directory)

        legacy = claim.get("legacy")
        if legacy is not None:
            index_directory = _thought_legacy_index_dir()
            for expected in legacy["entries"]:
                path = os.path.join(index_directory, expected["index_name"])
                try:
                    observed = _read_thought_legacy_index_entry(path)
                except FileNotFoundError:
                    continue
                if observed != expected:
                    raise ValueError(
                        "legacy thought index changed before acknowledgment")
            # Retain canonical JSON/catalog diagnostics through completion.
            # A reset archives these rebuildable derivatives; the exact policy
            # replay journal below, rather than a timestamp maximum or stale
            # page path, decides which earlier records already had effects.
        # Both native and baseline pages require an exact per-record receipt.
        # For native records this deliberately outlives the claim: an inbox
        # or agent request can be retried after this claim is acknowledged but
        # before its producer file is durably removed.
        _mark_thought_mind_replay_applied_locked(claim)

        # The claim contains every replay byte, so partial input deletion is
        # harmless: it remains the authoritative redo record until this last
        # unlink and state-directory fsync both succeed.
        os.unlink(_thought_recovery_claim_path())
        _sync_directory(STATE)


def _thought_recovery_debt():
    """Return a bounded readiness reason under the recovery generation lock."""
    ensure_durable_directory(STATE, mode=0o700)
    with _owner_lease(_thought_recovery_lock_path(), "thought recovery"):
        claim = _read_thought_recovery_claim()
        if claim is not None:
            return "a thought recovery claim is pending"
        records = _list_thought_recovery_records_locked()
        if records:
            return "thought page recovery intents are pending"
        scan = _load_thought_legacy_scan()
        if scan["phase"] != "complete":
            return "legacy thought recovery baseline is pending"
        if os.path.lexists(_thought_mind_replay_path()):
            return "thought mind replay finalization is pending"
    return ""


def _persist_thought(thought):
    """Persist a generated entry and return its exact canonical record."""
    record = _canonical_thought_page_record(thought)
    timestamp = record["ts"]
    kind = record["kind"]
    text = record["text"]
    queue_id = record.get("queue_id")
    dt = timestamp.replace(":", "").replace("-", "")[:13]
    base_slug = (f"thoughts/{timestamp[:10]}-{dt[9:13]}-"
                 f"{kind}")
    slug = base_slug
    if queue_id:
        slug = _queued_thought_slug(queue_id)
        if record.get("slug") not in (None, slug):
            raise ValueError("queued thought state binds a different corpus page")
    elif record.get("slug") is not None:
        slug = record["slug"]
        digest_slug = (base_slug + "-"
                       + hashlib.sha256(text.encode()).hexdigest()[:6])
        if slug != base_slug and re.fullmatch(
                re.escape(digest_slug)
                + r"(?:-(?:[2-9]|[1-9][0-9]+))?", slug) is None:
            raise ValueError("thought state binds a noncanonical corpus page")
    elif page_exists(slug):
        slug += "-" + hashlib.sha256(text.encode()).hexdigest()[:6]
        base, n = slug, 2
        collision_checks = 0
        while page_exists(slug):
            if collision_checks >= MAX_THOUGHT_RECOVERY_RECORDS:
                raise ValueError(
                    "thought page collision search reached its bound")
            collision_checks += 1
            slug = f"{base}-{n}"
            n += 1
    slug = _canonical_corpus_slug(slug)
    page_record = dict(record, slug=slug)
    fm, body = _thought_page_parts(page_record)
    if queue_id:
        try:
            existing = _read_thought_page_text(slug)
        except FileNotFoundError:
            # The content-bound intent is the redo log for both the corpus
            # page and its projections. Capacity refusal precedes page bytes.
            _queue_thought_recovery(page_record)
            write_page(slug, fm, body)
            return page_record
        expected = "---\n" + "\n".join(fm) + "\n---\n" + body
        pre_metadata_fm = [line for line in fm
                           if not line.startswith("sia_thought: ")]
        legacy_fm = [line for line in pre_metadata_fm
                     if not line.startswith("origin: ")]
        pre_metadata_expected = ("---\n" + "\n".join(pre_metadata_fm)
                                 + "\n---\n" + body)
        legacy_expected = ("---\n" + "\n".join(legacy_fm)
                           + "\n---\n" + body)
        if existing in (pre_metadata_expected, legacy_expected):
            # Exact pre-origin page from a crash between page creation and
            # inbox acknowledgement: upgrade only that known byte shape.
            _queue_thought_recovery(page_record)
            write_page(slug, fm, body)
            return page_record
        if existing == expected:
            _queue_thought_recovery(page_record)
            return page_record
        try:
            durable_record = _decode_exact_thought_page(slug, existing)
        except RuntimeError as exc:
            raise ValueError(
                "queued thought path differs from exact request") from exc
        if _thought_queue_binding(durable_record) \
                != _thought_queue_binding(page_record):
            raise ValueError("queued thought identity conflicts with its page")
        _queue_thought_recovery(durable_record)
        return durable_record
    else:
        try:
            existing = _read_thought_page_text(slug)
        except FileNotFoundError:
            _queue_thought_recovery(page_record)
            write_page(slug, fm, body)
            return page_record
        durable_record = _decode_exact_thought_page(slug, existing)
        if durable_record != page_record:
            raise ValueError("thought path differs from its exact record")
        _queue_thought_recovery(durable_record)
    return page_record


def write_thought(thought):
    """Persist one validated, origin-labeled generated-entry page."""
    return _persist_thought(thought)["slug"]


def reconcile_thought_pages(store, mind=None):
    """Prepare and apply one bounded, receipt-guarded recovery generation.

    This compatibility entry point deliberately does not acknowledge the
    immutable claim: only ``_settle_thought_page_signals`` may do that after
    both authoritative state files have reached durable storage.
    """
    def reconcile_owned():
        claim = _prepare_thought_recovery_claim()
        if claim is None:
            return (0, 0)
        return _apply_thought_recovery_claim(store, mind, claim)

    if _CORPUS_OWNER_DEPTH.get() > 0:
        recovered, reinforced = reconcile_owned()
    else:
        with corpus_owner():
            recovered, reinforced = reconcile_owned()
    return (recovered, reinforced) if mind is not None else recovered


# Epoch pages and their durable consolidation lifecycle share this memory
# materialization owner. Generic corpus publication remains in the core.
def _epoch_exemplars(bullets, *, limit=None):
    """Pick action-prefix coverage before spending an epoch summary's spare positions.

    Positional sampling — the first two and the last — was the original rule,
    and it silently dropped whole classes of event.  Measured: on 2026-08-24
    SEKHMET's four ``OUTCOME:restart_wireplumber  ok`` rows all sat in the
    middle of a nineteen-line log, so the epoch recorded that a heal had been
    *intended* and never that it *succeeded*.  The aggregate counts still said
    ``outcome: 4`` while no exemplar showed one, which is the worst shape a
    summary can take: it asserts that something happened and keeps no instance of
    it, so a rigorous reader must abstain on a fact the machine really did
    observe.

    Every explicit action class gets a position before duplicate anchors.
    The same rule applies to the merged weekly summary, including retained older
    exemplars. If the bound cannot cover the classes, retain the source pages
    rather than publish a partial summary. Unstructured prose has no recoverable
    action class here; anchors do not make semantic coverage claims for it.
    Order stays chronological and compacted originals remain in git.
    """
    if limit is None:
        limit = MAX_EPOCH_EXEMPLARS
    if type(limit) is not int or limit <= 0:
        raise ValueError("epoch exemplar bound is invalid")
    if not bullets:
        return []
    representatives = {}
    for index, bullet in enumerate(bullets):
        match = _EPOCH_EXEMPLAR_KIND_RE.match(bullet)
        if match:
            representatives.setdefault(match.group(1), index)
            if len(representatives) > limit:
                raise ConsolidationCapacityError(
                    "epoch action coverage exceeds its exemplar bound")
    keep = set(representatives.values())
    for index in list(range(min(2, len(bullets)))) + [len(bullets) - 1]:
        if len(keep) < limit:
            keep.add(index)
    return [bullets[index] for index in sorted(keep)]


def _pending_consolidation_marker(memo):
    marker = memo.get("consolidation_pending", False)
    if marker is False or marker is None:
        return None
    if marker is True:  # pre-structured crash marker; upgraded on recovery
        return True
    if not isinstance(marker, dict) or set(marker) not in ({
            "v", "id", "started_at"}, {
            "v", "id", "started_at", "ledger"}, {
            "v", "id", "started_at", "ledger", "applied_at"}) \
            or not _exact_int(marker.get("v"), 1) \
            or not isinstance(marker.get("id"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", marker["id"]) is None \
            or not isinstance(marker.get("started_at"), str):
        raise RuntimeError("consolidation recovery marker is invalid")
    try:
        if _canonical_utc_timestamp(marker["started_at"]) \
                != marker["started_at"]:
            raise ValueError
    except ValueError:
        raise RuntimeError("consolidation recovery marker is invalid") \
            from None
    if "ledger" in marker:
        ledger = marker["ledger"]
        if not isinstance(ledger, dict) or set(ledger) != {
                "order", "action", "arg1", "arg2", "content",
                "record_id"}:
            raise RuntimeError("consolidation ledger binding is invalid")
        try:
            basis = _pending_basis(
                ledger["order"], ledger["action"], ledger["arg1"],
                ledger["arg2"], ledger["content"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError("consolidation ledger binding is invalid") \
                from exc
        expected = {**basis, "record_id": _pending_identity(basis)}
        if ledger != expected or basis["action"] not in {
                "DREAM:consolidate", "RECOVER:consolidate"}:
            raise RuntimeError("consolidation ledger binding is invalid")
    if "applied_at" in marker:
        if "ledger" not in marker \
                or not isinstance(marker["applied_at"], str):
            raise RuntimeError("consolidation applied marker is invalid")
        try:
            if _canonical_utc_timestamp(marker["applied_at"]) \
                    != marker["applied_at"]:
                raise ValueError
        except ValueError:
            raise RuntimeError(
                "consolidation applied marker is invalid") from None
    return marker


def _mark_consolidation_pending(memo):
    marker = _pending_consolidation_marker(memo)
    if marker is not None:
        return marker
    marker = {"v": 1, "id": uuid.uuid4().hex, "started_at": iso()}
    updated = dict(memo, consolidation_pending=marker)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return marker


def _ensure_structured_consolidation_marker(memo):
    marker = _pending_consolidation_marker(memo)
    if marker is not True:
        return marker
    marker = {"v": 1, "id": uuid.uuid4().hex, "started_at": iso()}
    updated = dict(memo, consolidation_pending=marker)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return marker


def _bind_consolidation_ledger(memo, action, arg1, arg2, content=""):
    marker = _ensure_structured_consolidation_marker(memo)
    if not isinstance(marker, dict):
        raise RuntimeError("consolidation has no recovery identity")
    if "ledger" in marker:
        return marker["ledger"]
    basis = _pending_basis(time.time_ns(), action, arg1, arg2, content)
    ledger = {**basis, "record_id": _pending_identity(basis)}
    probe = {"schema": LEDGER_PENDING_SCHEMA,
             "record_id": ledger["record_id"], "queued_at": iso(), **basis}
    if len((json.dumps(
            probe, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False) + "\n").encode("utf-8")) \
            > MAX_LEDGER_PENDING_RECORD_BYTES:
        raise ValueError("consolidation ledger binding exceeds record bound")
    rebound = dict(marker, ledger=ledger)
    updated = dict(memo, consolidation_pending=rebound)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return ledger


def _settle_consolidation_ledger(memo):
    marker = _pending_consolidation_marker(memo)
    if not isinstance(marker, dict) or "ledger" not in marker:
        raise RuntimeError("consolidation ledger binding is absent")
    ledger = marker["ledger"]
    path = queue_ledger_transition(
        ledger["order"], ledger["action"], ledger["arg1"],
        ledger["arg2"], ledger["content"])
    _settle_ledger_transition(path)
    return ledger


def _mark_consolidation_applied(memo):
    marker = _pending_consolidation_marker(memo)
    if not isinstance(marker, dict) or "ledger" not in marker:
        raise RuntimeError("consolidation ledger must bind before apply")
    if "applied_at" in marker:
        return marker
    rebound = dict(marker, applied_at=iso())
    updated = dict(memo, consolidation_pending=rebound)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)
    return rebound


def _clear_consolidation_marker(memo):
    updated = dict(memo)
    updated.pop("consolidation_pending", None)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)


def _recover_pending_consolidation(memo):
    """Replay an interrupted lineage-bound consolidation before reads."""
    marker = _ensure_structured_consolidation_marker(memo)
    if marker is None:
        return None
    if "ledger" not in marker:
        _bind_consolidation_ledger(
            memo, "RECOVER:consolidate", f"id={marker['id']}",
            "completed")
        marker = _pending_consolidation_marker(memo)
    result = None
    if "applied_at" not in marker:
        result = consolidate_corpus()
        # The named scheduled-maintenance transaction owns the cutoff-pinned generation,
        # not merely one directory page or claim batch.  Keep its exact ledger
        # binding pending while later pulses resume bounded consolidation
        # units, including the conservative scan after admitted source unlink.
        if _consolidation_scan_debt():
            return result
        _mark_consolidation_applied(memo)
    _settle_consolidation_ledger(memo)
    _clear_consolidation_marker(memo)
    return result


def _epoch_slug_for_day(organ, date):
    year, week, _weekday = datetime.date.fromisoformat(date).isocalendar()
    return f"epochs/{organ}/{year}-w{week:02d}"


def _epoch_json_field(frontmatter, key, label, default):
    values = re.findall(rf"^{re.escape(key)}: (.*)$", frontmatter, re.M)
    if not values:
        return copy.deepcopy(default)
    if len(values) != 1:
        raise RuntimeError(f"{label} has duplicate {key}")
    try:
        return _strict_json_loads(values[0])
    except (TypeError, UnicodeError, ValueError, RecursionError) as exc:
        raise RuntimeError(f"{label} {key} is malformed") from exc


def _canonical_epoch_source_manifest(records, epoch_slug, prior_sources):
    if not isinstance(records, list):
        raise RuntimeError(f"epoch source manifest is invalid: {epoch_slug}")
    if len(records) > MAX_EPOCH_SOURCE_RECORDS:
        raise ConsolidationCapacityError(
            f"epoch source manifest is at capacity: {epoch_slug}")
    canonical = []
    day_parts = collections.defaultdict(list)
    seen_rel, seen_sha = set(), set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"rel", "sha256"} \
                or not isinstance(record.get("rel"), str) \
                or not isinstance(record.get("sha256"), str) \
                or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None:
            raise RuntimeError(
                f"epoch source manifest is invalid: {epoch_slug}")
        organ, date, part = _event_source_parts(record["rel"])
        if _epoch_slug_for_day(organ, date) != epoch_slug \
                or record["rel"] in seen_rel \
                or record["sha256"] in seen_sha \
                or record["sha256"] not in prior_sources:
            raise RuntimeError(
                f"epoch source manifest is invalid: {epoch_slug}")
        seen_rel.add(record["rel"])
        seen_sha.add(record["sha256"])
        day_parts[(organ, date)].append(part)
        canonical.append({"rel": record["rel"],
                          "sha256": record["sha256"]})
    for parts in day_parts.values():
        parts.sort()
        if parts != list(range(1, parts[-1] + 1)):
            raise RuntimeError(
                f"epoch source manifest has incomplete day lineage: "
                f"{epoch_slug}")
    canonical.sort(key=lambda record: record["rel"])
    if records != canonical:
        raise RuntimeError(f"epoch source manifest is invalid: {epoch_slug}")
    encoded = json.dumps(canonical, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) \
            > MAX_EPOCH_SOURCE_MANIFEST_BYTES:
        raise ConsolidationCapacityError(
            f"epoch source manifest exceeds its bound: {epoch_slug}")
    return canonical


def _canonical_epoch_event_ids(event_ids, epoch_slug):
    if not isinstance(event_ids, list):
        raise RuntimeError(
            f"epoch event-index completeness is invalid: {epoch_slug}")
    if len(event_ids) > MAX_EPOCH_EVENT_IDS:
        raise ConsolidationCapacityError(
            f"epoch event-index completeness is at capacity: {epoch_slug}")
    canonical = sorted(set(event_ids))
    if event_ids != canonical \
            or any(not isinstance(event_id, str)
                   or re.fullmatch(r"[0-9a-f]{64}", event_id) is None
                   for event_id in event_ids):
        raise RuntimeError(
            f"epoch event-index completeness is invalid: {epoch_slug}")
    return list(event_ids)


def _read_epoch_state(slug, *, expected_generation=None, dependency_capture=None):
    """Read and validate one bounded epoch plus optional exact shard lineage."""
    try:
        text = _read_event_page(
            slug, expected_generation=expected_generation,
            **({"dependency_capture": dependency_capture}
               if dependency_capture is not None else {}))
    except FileNotFoundError:
        return {"slug": slug, "text": "", "sources": [], "dates": [],
                "ndays": 0, "source_manifest": [], "event_ids": [],
                "source_manifest_declared": False,
                "event_ids_declared": False}
    match = FM_RE.match(text)
    if match is None:
        raise RuntimeError(f"existing epoch lacks frontmatter: {slug}")
    frontmatter = match.group(1)
    types = re.findall(r"^type:\s*(.*?)\s*$", frontmatter, re.M)
    if types != ["epoch"]:
        raise RuntimeError(f"existing epoch identity is invalid: {slug}")
    prior_sources = _epoch_json_field(
        frontmatter, "sia_sources", f"epoch lineage {slug}", [])
    if not isinstance(prior_sources, list) \
            or len(prior_sources) != len(set(prior_sources)) \
            or any(not isinstance(value, str)
                   or re.fullmatch(r"[0-9a-f]{64}", value) is None
                   for value in prior_sources):
        raise RuntimeError(f"epoch lineage is invalid: {slug}")
    prior_dates = _epoch_json_field(
        frontmatter, "sia_dates", f"epoch date lineage {slug}", [])
    if not isinstance(prior_dates, list) \
            or prior_dates != sorted(set(prior_dates)) \
            or any(not isinstance(value, str)
                   or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None
                   for value in prior_dates):
        raise RuntimeError(f"epoch date lineage is invalid: {slug}")
    source_manifest_declared = bool(re.findall(
        r"^sia_source_manifest: ", frontmatter, re.M))
    manifest = _epoch_json_field(
        frontmatter, "sia_source_manifest",
        f"epoch source manifest {slug}", [])
    manifest = _canonical_epoch_source_manifest(
        manifest, slug, set(prior_sources))
    if any(_event_source_parts(record["rel"])[1] not in prior_dates
           for record in manifest):
        raise RuntimeError(f"epoch source manifest lacks date lineage: {slug}")
    event_ids_declared = bool(re.findall(
        r"^sia_event_ids: ", frontmatter, re.M))
    event_ids = _epoch_json_field(
        frontmatter, "sia_event_ids",
        f"epoch event-index completeness {slug}", [])
    event_ids = _canonical_epoch_event_ids(event_ids, slug)
    if event_ids_declared and (
            not source_manifest_declared
            or {record["sha256"] for record in manifest} != set(prior_sources)):
        raise RuntimeError(
            f"epoch event-index completeness lacks source lineage: {slug}")
    day_matches = re.findall(r"Consolidated from (\d+) day-memories", text)
    if len(day_matches) != 1:
        raise RuntimeError(f"existing epoch lacks exact day count: {slug}")
    ndays = int(day_matches[0])
    manifest_dates = {_event_source_parts(record["rel"])[1]
                      for record in manifest}
    if event_ids_declared and (
            ndays != len(prior_dates) or manifest_dates != set(prior_dates)):
        raise RuntimeError(
            f"epoch event-index completeness lacks source lineage: {slug}")
    return {"slug": slug, "text": text, "sources": prior_sources,
            "dates": prior_dates, "ndays": ndays,
            "source_manifest": manifest, "event_ids": event_ids,
            "source_manifest_declared": source_manifest_declared,
            "event_ids_declared": event_ids_declared}


def _merge_epoch_source_manifest(existing, items, epoch_slug, source_ids):
    by_rel = {record["rel"]: record for record in existing}
    by_sha = {record["sha256"]: record for record in existing}
    for _date, _path, _text, _tags, source_id, relative, _part in items:
        record = {"rel": relative, "sha256": source_id}
        prior_rel = by_rel.get(relative)
        prior_sha = by_sha.get(source_id)
        if (prior_rel is not None and prior_rel != record) \
                or (prior_sha is not None and prior_sha != record):
            raise RuntimeError(
                f"epoch source manifest conflicts with live shard: {relative}")
        if prior_rel is None and len(by_rel) >= MAX_EPOCH_SOURCE_RECORDS:
            raise ConsolidationCapacityError(
                f"epoch source manifest is at capacity: {epoch_slug}")
        by_rel[relative] = record
        by_sha[source_id] = record
    merged = sorted(by_rel.values(), key=lambda record: record["rel"])
    return _canonical_epoch_source_manifest(
        merged, epoch_slug, set(source_ids))


def _merge_epoch_event_ids(state, items, entries):
    live_records = {
        (relative, source_id)
        for _date, _path, _text, _tags, source_id, relative, _part
        in items
    }
    live_source_ids = {source_id for _relative, source_id in live_records}
    if state["text"] and not state["event_ids_declared"]:
        retained_prior_dates = {
            _event_source_parts(relative)[1]
            for relative, source_id in live_records
            if source_id in state["sources"]}
        if state["ndays"] != len(retained_prior_dates) \
                or (state["dates"]
                    and retained_prior_dates != set(state["dates"])) \
                or any(source_id not in live_source_ids
                       for source_id in state["sources"]):
            raise ConsolidationCompletenessError(
                "pre-index epoch event completeness cannot be "
                f"reconstructed: {state['slug']}")
    if state["source_manifest_declared"] \
            and not state["event_ids_declared"]:
        missing_sources = [
            record for record in state["source_manifest"]
            if (record["rel"], record["sha256"]) not in live_records
        ]
        if missing_sources:
            raise ConsolidationCompletenessError(
                "epoch event-index completeness cannot be reconstructed: "
                f"{state['slug']}")
    event_ids = sorted(
        set(state["event_ids"])
        | {entry["event_id"] for entry in entries})
    return _canonical_epoch_event_ids(event_ids, state["slug"])


def _event_index_entries_for_sources(items, epoch_slug):
    entries = {}
    for _date, _path, text, _tags, source_id, relative, _part in items:
        source_organ, _source_date, _source_part = _event_source_parts(relative)
        match = FM_RE.match(text)
        if match is None:
            raise RuntimeError(
                f"consolidation source lacks frontmatter: {relative}")
        log_part = text[match.end():].split("## Timeline", 1)[0]
        if "## Log" in log_part:
            log_part = log_part.split("## Log", 1)[1]
        for line in (value for value in log_part.splitlines()
                     if value.startswith("- ")):
            marker = EVENT_MARKER_RE.fullmatch(line)
            if marker is None:
                if "sia-event:" in line:
                    raise RuntimeError(
                        f"consolidation source has malformed event identity: "
                        f"{relative}")
                continue
            event_id = marker.group("id")
            if event_id in entries:
                raise RuntimeError(
                    "event identity is duplicated across consolidation sources")
            if len(entries) >= MAX_EVENT_INDEX_RECORDS:
                raise ConsolidationCapacityError(
                    "consolidated event index batch is at capacity")
            entries[event_id] = {
                "schema": EVENT_INDEX_SCHEMA,
                "organ": source_organ,
                "event_id": event_id,
                "semantic_id": marker.group("semantic"),
                "payload_sha256": _event_payload_digest(
                    marker.group("payload")),
                "source_rel": relative,
                "source_sha256": source_id,
                "epoch_slug": epoch_slug,
            }
    result = [entries[event_id] for event_id in sorted(entries)]
    if len(result) > MAX_EVENT_INDEX_RECORDS:
        raise RuntimeError("consolidated event index batch exceeds its bound")
    for entry in result:
        _event_index_encoded(entry)
    return result


def _render_epoch_source_manifest(state, records, dates, event_ids):
    """Prepare a legacy/recovery epoch update without mutating the corpus."""
    if not isinstance(dates, list) or dates != sorted(set(dates)) \
            or any(not isinstance(value, str)
                   or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None
                   for value in dates):
        raise RuntimeError(
            f"epoch date lineage is invalid: {state['slug']}")
    if records == state["source_manifest"] \
            and dates == state["dates"] \
            and event_ids == state["event_ids"] \
            and state["source_manifest_declared"] \
            and state["event_ids_declared"]:
        return None
    text = state["text"]
    match = FM_RE.match(text)
    if match is None:
        raise RuntimeError(
            f"existing epoch lacks frontmatter: {state['slug']}")
    lines = match.group(1).splitlines()
    fields = {
        "sia_source_manifest": json.dumps(
            records, separators=(",", ":"), ensure_ascii=False),
        "sia_event_ids": json.dumps(
            event_ids, separators=(",", ":"), ensure_ascii=False),
        "sia_dates": json.dumps(
            dates, separators=(",", ":"), ensure_ascii=False),
    }
    for key, value in fields.items():
        field = f"{key}: {value}"
        positions = [index for index, line in enumerate(lines)
                     if line.startswith(f"{key}: ")]
        if len(positions) > 1:
            raise RuntimeError(
                f"epoch recovery metadata is invalid: {state['slug']}")
        if positions:
            lines[positions[0]] = field
            continue
        source_positions = [index for index, line in enumerate(lines)
                            if line.startswith("sia_sources: ")]
        position = source_positions[0] + 1 if len(source_positions) == 1 \
            else len(lines)
        lines.insert(position, field)
    body = text[match.end():]
    encoded = ("---\n" + "\n".join(lines) + "\n---\n" + body).encode(
        "utf-8")
    if len(encoded) > MAX_EPOCH_PAGE_BYTES:
        raise ConsolidationCapacityError(
            f"epoch page exceeds its lineage bound: {state['slug']}")
    return lines, body


def _write_epoch_source_manifest(state, rendered):
    if rendered is not None:
        frontmatter, body = rendered
        write_page(state["slug"], frontmatter, body)


def _render_bounded_epoch(slug, frontmatter, body):
    """Prepare a complete epoch page and classify capacity before publish."""
    encoded = ("---\n" + "\n".join(frontmatter) + "\n---\n" + body).encode(
        "utf-8")
    if len(encoded) > MAX_EPOCH_PAGE_BYTES:
        raise ConsolidationCapacityError(
            f"epoch page exceeds its lineage bound: {slug}")
    return frontmatter, body


def _write_bounded_epoch(slug, rendered):
    frontmatter, body = rendered
    write_page(slug, frontmatter, body)


def _consolidation_scan_path():
    """Return production state, or a corpus-scoped sibling for test roots."""
    production_corpus = os.path.abspath(os.path.join(SHARE, "corpus"))
    if os.path.abspath(CORPUS) == production_corpus:
        return os.path.join(STATE, "consolidation-scan.json")
    token = hashlib.sha256(os.path.abspath(CORPUS).encode("utf-8")).hexdigest()
    return os.path.join(
        os.path.dirname(os.path.abspath(CORPUS)),
        ".sia-consolidation-" + token,
        "scan.json")


def _fresh_consolidation_scan(cutoff):
    if not isinstance(cutoff, str) \
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", cutoff) is None:
        raise ValueError("consolidation cutoff is invalid")
    return {
        "schema": CONSOLIDATION_SCAN_SCHEMA,
        "generation": uuid.uuid4().hex,
        "phase": "scan",
        "cutoff": cutoff,
        "queue": [{"relative": "", "levels":
                   MAX_CONSOLIDATION_TREE_LEVELS, "page": {}}],
        "pending_days": [],
        "claims": [],
    }


def _canonical_consolidation_day(value):
    if not isinstance(value, dict) or set(value) != {"organ", "date"} \
            or not isinstance(value.get("organ"), str) \
            or re.fullmatch(
                r"[a-z0-9][a-z0-9._-]{0,199}", value["organ"]) is None \
            or not isinstance(value.get("date"), str):
        raise RuntimeError("consolidation candidate day is invalid")
    try:
        if datetime.date.fromisoformat(value["date"]).isoformat() \
                != value["date"]:
            raise ValueError
    except ValueError:
        raise RuntimeError("consolidation candidate day is invalid") \
            from None
    return dict(value)


def _canonical_consolidation_scan(value):
    if not isinstance(value, dict) \
            or set(value) != {
                "schema", "generation", "phase", "cutoff", "queue",
                "pending_days", "claims"} \
            or value.get("schema") != CONSOLIDATION_SCAN_SCHEMA \
            or value.get("phase") not in {"scan", "complete"} \
            or not isinstance(value.get("generation"), str) \
            or re.fullmatch(r"[0-9a-f]{32}", value["generation"]) is None \
            or not isinstance(value.get("cutoff"), str) \
            or re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value["cutoff"]) is None \
            or not isinstance(value.get("queue"), list) \
            or len(value["queue"]) > MAX_CONSOLIDATION_DIRECTORY_QUEUE \
            or not isinstance(value.get("pending_days"), list) \
            or len(value["pending_days"]) > MAX_SOURCE_SCAN_ENTRIES \
            or not isinstance(value.get("claims"), list) \
            or len(value["claims"]) > MAX_CONSOLIDATION_DAYS_PER_RUN:
        raise RuntimeError("consolidation scan state is invalid")
    queue = []
    queued_relatives = set()
    page_fields = {
        "device", "inode", "cookie", "size", "mtime_ns", "ctime_ns",
        "reset"}
    for frame in value["queue"]:
        if not isinstance(frame, dict) or set(frame) != {
                "relative", "levels", "page"}:
            raise RuntimeError("consolidation scan cursor is invalid")
        relative = frame["relative"]
        parts = relative.split("/") if isinstance(relative, str) \
            and relative else []
        if not isinstance(relative, str) or os.path.isabs(relative) \
                or relative in {".", ".."} \
                or any(part in {"", ".", ".."} for part in parts) \
                or (os.altsep and os.altsep in relative) \
                or relative in queued_relatives \
                or isinstance(frame["levels"], bool) \
                or not isinstance(frame["levels"], int) \
                or frame["levels"] \
                    != MAX_CONSOLIDATION_TREE_LEVELS - len(parts):
            raise RuntimeError("consolidation scan cursor is invalid")
        raw_page = frame["page"]
        if not isinstance(raw_page, dict) \
                or raw_page and (
                    set(raw_page) != page_fields
                    or raw_page["reset"] is not False
                    or any(isinstance(raw_page[name], bool)
                           or not isinstance(raw_page[name], int)
                           or raw_page[name] < 0
                           for name in page_fields - {"reset"})):
            raise RuntimeError("consolidation scan cursor is invalid")
        queued_relatives.add(relative)
        queue.append({"relative": relative, "levels": frame["levels"],
                      "page": _validated_source_page_state(raw_page)})
    pending = [_canonical_consolidation_day(day)
               for day in value["pending_days"]]
    if len({(day["organ"], day["date"]) for day in pending}) != len(pending):
        raise RuntimeError("consolidation candidate day is duplicated")
    claims = []
    for claim in value["claims"]:
        if not isinstance(claim, dict) or set(claim) != {
                "organ", "date", "cutoff", "directory", "sources"}:
            raise RuntimeError("consolidation day claim is invalid")
        day = _canonical_consolidation_day(
            {"organ": claim.get("organ"), "date": claim.get("date")})
        raw_directory = claim.get("directory")
        if not isinstance(raw_directory, dict) \
                or set(raw_directory) != page_fields:
            raise RuntimeError("consolidation day claim is invalid")
        directory = _validated_source_page_state(raw_directory)
        sources = claim.get("sources")
        if not isinstance(sources, list) \
                or len(sources) > MAX_EVENT_SHARDS or not sources:
            raise RuntimeError("consolidation day claim is invalid")
        canonical_sources = []
        for record in sources:
            if not isinstance(record, dict) or set(record) != {
                    "rel", "sha256"} \
                    or not isinstance(record.get("rel"), str) \
                    or not isinstance(record.get("sha256"), str) \
                    or re.fullmatch(
                        r"[0-9a-f]{64}", record["sha256"]) is None:
                raise RuntimeError("consolidation day claim is invalid")
            organ, date, _part = _event_source_parts(record["rel"])
            if organ != day["organ"] or date != day["date"]:
                raise RuntimeError("consolidation day claim is invalid")
            canonical_sources.append(dict(record))
        canonical_sources.sort(key=lambda record: record["rel"])
        if sources != canonical_sources \
                or len({record["rel"] for record in sources}) != len(sources):
            raise RuntimeError("consolidation day claim is invalid")
        if claim["cutoff"] != value["cutoff"]:
            raise RuntimeError("consolidation claim cutoff conflicts")
        claims.append({**day, "cutoff": claim["cutoff"],
                       "directory": directory,
                       "sources": canonical_sources})
    if (value["phase"] == "complete") != (not queue):
        raise RuntimeError("consolidation scan phase/cursor is invalid")
    return dict(value, queue=queue, pending_days=pending, claims=claims)


def _load_consolidation_scan(cutoff):
    """Load one cutoff-pinned generation, rolling only after convergence."""
    path = _consolidation_scan_path()
    value = read_state_json(path, {}, "consolidation scan")
    if not value:
        return _fresh_consolidation_scan(cutoff)
    value = _canonical_consolidation_scan(value)
    if value["cutoff"] != cutoff \
            and value["phase"] == "complete" \
            and not value["queue"] \
            and not value["pending_days"] \
            and not value["claims"]:
        # A later UTC day widens eligibility only after the prior generation
        # has no cursor or admitted work left. Restarting an incomplete scan
        # here would repeatedly discard its suffix on a large corpus.
        return _fresh_consolidation_scan(cutoff)
    return value


def _save_consolidation_scan(value):
    value = _canonical_consolidation_scan(value)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_STATE_JSON_BYTES:
        raise RuntimeError("consolidation scan state exceeds its byte bound")
    path = _consolidation_scan_path()
    ensure_durable_directory(os.path.dirname(path))
    atomic_write(path, encoded)
    return value


def _advance_consolidation_scan(value):
    """Inspect one global directory-page budget without deletion inference."""
    value = _canonical_consolidation_scan(value)
    if value["claims"] or value["pending_days"]:
        return value
    if value["phase"] == "complete":
        return value
    root = os.path.join(CORPUS, "events")
    queue = collections.deque(value["queue"])
    remaining = MAX_SOURCE_SCAN_ENTRIES
    discovered = []
    while queue and remaining:
        frame = queue.popleft()
        directory = os.path.join(root, frame["relative"])
        try:
            entries, complete, inspected, next_page = \
                _bounded_source_entries(
                    directory, frame["page"], remaining,
                    cleanup_legacy_atomic=True)
        except FileNotFoundError:
            if not frame["relative"]:
                queue.clear()
                break
            continue
        if next_page.get("reset"):
            return _save_consolidation_scan(
                _fresh_consolidation_scan(value["cutoff"]))
        remaining -= inspected
        if not complete:
            frame["page"] = next_page
            queue.appendleft(frame)
        for entry in entries:
            relative = os.path.join(frame["relative"], entry["name"])
            if frame["levels"] \
                    and not stat.S_ISDIR(entry["mode"]) \
                    and not stat.S_ISREG(entry["mode"]):
                raise RuntimeError(
                    "consolidation organ path is not a regular file or "
                    "directory")
            if frame["levels"] and stat.S_ISDIR(entry["mode"]):
                if len(queue) >= MAX_CONSOLIDATION_DIRECTORY_QUEUE:
                    raise RuntimeError(
                        "consolidation directory queue exceeds its bound")
                queue.append({"relative": relative,
                              "levels": frame["levels"] - 1,
                              "page": {}})
                continue
            if frame["levels"] or not entry["name"].endswith(".md"):
                continue
            rel = os.path.join("events", relative).replace(os.sep, "/")
            try:
                organ, date, _part = _event_source_parts(rel)
            except ValueError:
                continue
            if date < value["cutoff"]:
                discovered.append({"organ": organ, "date": date})
    deduped = {(day["organ"], day["date"]): day for day in discovered}
    value["pending_days"] = [deduped[key] for key in sorted(deduped)]
    value["queue"] = list(queue)
    if not queue:
        value["phase"] = "complete"
    return _save_consolidation_scan(value)


def _bounded_event_directory_entries(organ):
    """Read one complete source directory only within the existing page cap."""
    root = os.path.join(CORPUS, "events", organ)
    page = {}
    remaining = MAX_EVENT_LOOKUP_PAGES
    gathered = []
    while remaining:
        limit = min(remaining, MAX_SOURCE_SCAN_ENTRIES)
        try:
            entries, complete, inspected, next_page = \
                _bounded_source_entries(
                    root, page, limit, cleanup_legacy_atomic=True)
        except FileNotFoundError:
            return [], {}
        if next_page.get("reset"):
            raise RuntimeError(
                "event directory changed during bounded consolidation scan")
        gathered.extend(entries)
        remaining -= inspected
        if complete:
            return gathered, next_page
        if inspected <= 0:
            raise RuntimeError("event directory scan made no progress")
        page = next_page
    raise RuntimeError("event directory exceeds its consolidation page bound")


def _prepare_consolidation_claims(value):
    if value["claims"]:
        return value
    selected = value["pending_days"][:MAX_CONSOLIDATION_DAYS_PER_RUN]
    if not selected:
        return value
    by_organ = collections.defaultdict(list)
    for day in selected:
        by_organ[day["organ"]].append(day["date"])
    claims = []
    for organ in sorted(by_organ):
        entries, directory = _bounded_event_directory_entries(organ)
        wanted = set(by_organ[organ])
        sources = collections.defaultdict(list)
        for entry in entries:
            if not entry["name"].endswith(".md"):
                continue
            if not stat.S_ISREG(entry["mode"]):
                raise RuntimeError(
                    "consolidation event source is not a regular file")
            rel = f"events/{organ}/{entry['name']}"
            try:
                source_organ, date, _part = _event_source_parts(rel)
            except ValueError:
                continue
            if source_organ != organ or date not in wanted:
                continue
            slug = rel[:-3]
            text = _read_event_page(slug)
            raw = text.encode("utf-8")
            sources[date].append({
                "rel": rel,
                "sha256": hashlib.sha256(
                    rel.encode("utf-8") + b"\0" + raw).hexdigest(),
            })
        for date in sorted(wanted):
            records = sorted(sources.get(date, []),
                             key=lambda record: record["rel"])
            if not records:
                # A candidate may have disappeared before its immutable claim.
                # It makes no absence claim and will be reconsidered later.
                continue
            claims.append({"organ": organ, "date": date,
                           "cutoff": value["cutoff"],
                           "directory": directory,
                           "sources": records})
    claimed_keys = {(claim["organ"], claim["date"]) for claim in claims}
    selected_keys = {(day["organ"], day["date"]) for day in selected}
    value["pending_days"] = [
        day for day in value["pending_days"]
        if (day["organ"], day["date"]) not in selected_keys
        or (day["organ"], day["date"]) in claimed_keys]
    value["claims"] = claims
    return _save_consolidation_scan(value)


def _claimed_consolidation_paths(value):
    """Revalidate exact claim bytes; missing sources require epoch lineage."""
    if not value["claims"]:
        return []
    by_organ = collections.defaultdict(list)
    for claim in value["claims"]:
        by_organ[claim["organ"]].append(claim)
    paths = []
    for organ, claims in by_organ.items():
        entries, _generation = _bounded_event_directory_entries(organ)
        live = {}
        selected_dates = {claim["date"] for claim in claims}
        for entry in entries:
            if not entry["name"].endswith(".md"):
                continue
            rel = f"events/{organ}/{entry['name']}"
            try:
                _source_organ, date, _part = _event_source_parts(rel)
            except ValueError:
                continue
            if date in selected_dates:
                live[rel] = os.path.join(CORPUS, rel)
        for claim in claims:
            records = {record["rel"]: record for record in claim["sources"]}
            extra = {rel for rel in live
                     if _event_source_parts(rel)[1] == claim["date"]} \
                - set(records)
            if extra:
                raise RuntimeError(
                    "live event shards conflict with consolidation claim")
            epoch = None
            for rel, record in records.items():
                path = live.get(rel)
                if path is not None:
                    text = _read_event_page(rel[:-3])
                    digest = hashlib.sha256(
                        rel.encode("utf-8") + b"\0"
                        + text.encode("utf-8")).hexdigest()
                    if digest != record["sha256"]:
                        raise RuntimeError(
                            "live event shard conflicts with epoch source "
                            "lineage and consolidation "
                            f"claim: {rel}")
                    paths.append(path)
                    continue
                if epoch is None:
                    epoch = _read_epoch_state(
                        _epoch_slug_for_day(organ, claim["date"]))
                if record not in epoch["source_manifest"]:
                    raise RuntimeError(
                        "missing event shard lacks exact epoch source lineage")
    return sorted(paths)


def _acknowledge_consolidation_claims(value):
    claimed_days = {(claim["organ"], claim["date"])
                    for claim in value["claims"]}
    mutated = False
    for claim in value["claims"]:
        for record in claim["sources"]:
            if not page_exists(record["rel"][:-3]):
                mutated = True
                break
    value["pending_days"] = [
        day for day in value["pending_days"]
        if (day["organ"], day["date"]) not in claimed_days]
    value["claims"] = []
    if mutated:
        replacement = _fresh_consolidation_scan(value["cutoff"])
        return _save_consolidation_scan(replacement)
    return _save_consolidation_scan(value)


def _consolidation_scan_debt():
    path = _consolidation_scan_path()
    try:
        value = read_state_json(path, {}, "consolidation scan")
    except RuntimeError as exc:
        return f"consolidation scan refused: {exc}"
    if not value:
        return ""
    value = _canonical_consolidation_scan(value)
    if value["claims"]:
        return "a bounded consolidation day claim is pending"
    if value["pending_days"] or value["phase"] != "complete":
        return "bounded corpus consolidation scan is pending"
    return ""


def consolidate_corpus():
    """Compact old day pages into weekly epoch pages.

    Day pages older than the configured event-day window are summarized;
    declared safety-class days stay verbatim. Originals remain in corpus git
    history.
    """
    # never consolidate over an unhealthy repo: the unlink below is only
    # honest if the verbatim file is provably in git history first
    if corpus_commit("pre-consolidation") == "error":
        raise RuntimeError("pre-consolidation corpus git commit failed")
    mind_state = siamind.load_mind()
    # A completed `sia memory --pin` is protection immediately, even though
    # the single-writer brainstem materializes it on the next pulse.  The
    # producer and scheduled maintenance share the corpus lease; the queue snapshot itself is
    # additionally bounded and flocked inside siamind.
    scheduled_pages = siamind.pending_user_pin_slugs() | {
        slug for slug, record in mind_state.get("nodes", {}).items()
        if isinstance(record, dict)
        and siamind.is_important(record)
    }
    cutoff = (utcnow() - datetime.timedelta(
        days=siamind.EPISODIC_DAYS)).strftime("%Y-%m-%d")
    scan_state = _load_consolidation_scan(cutoff)
    scan_state = _advance_consolidation_scan(scan_state)
    scan_state = _prepare_consolidation_claims(scan_state)
    if not scan_state["claims"]:
        return 0, 0, 0
    claimed_paths = _claimed_consolidation_paths(scan_state)
    claimed_source_ids = {
        record["rel"]: record["sha256"]
        for claim in scan_state["claims"] for record in claim["sources"]
    }
    groups, kept_days = {}, set()
    epoch_states = {}

    def epoch_state_for_day(organ, date):
        slug = _epoch_slug_for_day(organ, date)
        if slug not in epoch_states:
            epoch_states[slug] = _read_epoch_state(slug)
        return epoch_states[slug]

    day_paths = collections.defaultdict(list)
    for path in claimed_paths:
        rel = os.path.relpath(path, CORPUS)
        try:
            organ, date, part = _event_source_parts(rel)
        except ValueError:
            continue
        if date >= cutoff:
            continue
        page_slug = rel[:-3]
        day_paths[(organ, date)].append((path, rel, page_slug, part))

    for (organ, date), paths in day_paths.items():
        paths.sort(key=lambda item: item[3])
        observed_parts = [item[3] for item in paths]
        observed_parts.sort()
        if len(observed_parts) != len(set(observed_parts)):
            raise RuntimeError("event day shard identity is duplicated")

        try:
            epoch_state = epoch_state_for_day(organ, date)
        except ConsolidationCapacityError:
            kept_days.add((organ, date))
            continue
        day_manifest = []
        for record in epoch_state["source_manifest"]:
            source_organ, source_date, _source_part = _event_source_parts(
                record["rel"])
            if source_organ == organ and source_date == date:
                day_manifest.append(record)
        recovery_lineage = bool(day_manifest)
        manifest_by_rel = {record["rel"]: record
                           for record in day_manifest}
        if recovery_lineage:
            if date not in epoch_state["dates"] \
                    or any(rel not in manifest_by_rel
                           for _path, rel, _page_slug, _part in paths):
                raise RuntimeError(
                    "live event shards conflict with epoch source lineage")
        elif observed_parts != list(range(1, observed_parts[-1] + 1)):
            raise RuntimeError("event day shards are not contiguous")

        durable = True
        for _path, rel, _page_slug, _part in paths:
            try:
                tracked = _run_bounded_text_process(
                    ["git", "ls-files", "--error-unmatch", "--", rel],
                    env=None, timeout=30, cwd=CORPUS,
                    label="git tracked-source check").returncode == 0
                clean_status = _run_bounded_text_process(
                    ["git", "status", "--porcelain", "--", rel],
                    env=None, timeout=30, cwd=CORPUS,
                    label="git source status")
                clean = clean_status.returncode == 0 \
                    and clean_status.stdout.strip() == ""
            except Exception:
                tracked = clean = False
            durable = durable and tracked and clean
        if not durable:
            continue               # retain the entire day; try next dream

        day_items = []
        protected = any(page_slug in scheduled_pages
                        for _path, _rel, page_slug, _part in paths)
        for path, rel, _page_slug, part in paths:
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
                | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            try:
                fd = os.open(path, flags)
            except OSError as exc:
                raise RuntimeError(
                    f"consolidation source cannot be opened safely: {rel}") \
                    from exc
            with siaqueue.regular_file_stream(
                    fd, label="consolidation source", error_type=RuntimeError) as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) \
                        or before.st_size > MAX_EVENT_PAGE_BYTES:
                    raise RuntimeError(
                        f"consolidation source is not a bounded regular file: "
                        f"{rel}")
                raw = stream.read(MAX_EVENT_PAGE_BYTES + 1)
                after = os.fstat(stream.fileno())
            before_token = (before.st_dev, before.st_ino, before.st_size,
                            before.st_mtime_ns, before.st_ctime_ns)
            after_token = (after.st_dev, after.st_ino, after.st_size,
                           after.st_mtime_ns, after.st_ctime_ns)
            if before_token != after_token \
                    or len(raw) > MAX_EVENT_PAGE_BYTES:
                raise RuntimeError(
                    f"consolidation source changed while read: {rel}")
            try:
                text = raw.decode("utf-8", errors="strict")
            except UnicodeError as exc:
                raise RuntimeError(
                    f"consolidation source is not valid UTF-8: {rel}") \
                    from exc
            source_id = hashlib.sha256(
                rel.encode("utf-8") + b"\0" + raw).hexdigest()
            if claimed_source_ids.get(rel) != source_id:
                raise RuntimeError(
                    f"consolidation source changed after its claim: {rel}")
            lineage_record = manifest_by_rel.get(rel)
            if recovery_lineage and (lineage_record is None
                                     or lineage_record["sha256"]
                                     != source_id):
                raise RuntimeError(
                    f"live event shard conflicts with epoch source lineage: "
                    f"{rel}")
            tm = re.search(r"^tags: \[(.*)\]$", text, re.M)
            tags = {tag.strip()
                    for tag in (tm.group(1).split(",") if tm else [])}
            protected = protected or bool(tags & siamind.SAFETY_TAGS)
            day_items.append(
                (date, path, text, tags, source_id, rel, part))
        if protected and not recovery_lineage:
            # Safety-detail preservation is a day-level invariant. Keeping only a
            # protected shard would orphan its siblings' numbering.
            kept_days.add((organ, date))
            continue
        y, w, _ = datetime.date.fromisoformat(date).isocalendar()
        groups.setdefault((organ, y, w), []).extend(day_items)
    consolidated_days = set()
    written_epochs = 0
    for (organ, y, w), items in groups.items():
        items.sort(key=lambda item: (item[0], item[6], item[5]))
        slug = f"epochs/{organ}/{y}-w{w:02d}"
        state = epoch_states.get(slug)
        if state is None:
            state = _read_epoch_state(slug)
            epoch_states[slug] = state
        et = state["text"]
        prior_sources = state["sources"]
        prior_dates = state["dates"]
        prior_ndays = state["ndays"]
        prior_source_set = set(prior_sources)
        pending_items = [item for item in items
                         if item[4] not in prior_source_set]
        source_ids = prior_sources + [item[4] for item in pending_items]
        try:
            merged_manifest = _merge_epoch_source_manifest(
                state["source_manifest"], items, slug, source_ids)
            event_entries = _event_index_entries_for_sources(items, slug)
            event_ids = _merge_epoch_event_ids(
                state, items, event_entries)
            _preflight_event_index_entries(event_entries)
        except (ConsolidationCapacityError,
                ConsolidationCompletenessError):
            # Unrepresentable capacity or unavailable completeness retains
            # the verbatim sources. Nothing in this weekly group has been
            # mutated yet, so scheduled maintenance can reconsider it later.
            kept_days |= {(organ, item[0]) for item in items}
            continue

        for item in pending_items:
            if item[0] in prior_dates \
                    and not any(record["rel"] == item[5]
                                for record in state["source_manifest"]):
                raise RuntimeError(
                    "event source conflicts with legacy epoch date lineage")

        def unlink_admitted(item):
            """Delete only the exact source bytes admitted to this epoch."""
            _date, path, _text, _tags, expected_id, rel, _part = item
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
                | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            fd = os.open(path, flags)
            with siaqueue.regular_file_stream(
                    fd, label="consolidation source", error_type=RuntimeError) as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) \
                        or before.st_size > MAX_EVENT_PAGE_BYTES:
                    raise RuntimeError(
                        f"consolidation cleanup target is not bounded: {rel}")
                current = stream.read(MAX_EVENT_PAGE_BYTES + 1)
                after = os.fstat(stream.fileno())
            observed = (before.st_dev, before.st_ino, before.st_size,
                        before.st_mtime_ns, before.st_ctime_ns)
            finished = (after.st_dev, after.st_ino, after.st_size,
                        after.st_mtime_ns, after.st_ctime_ns)
            target = os.lstat(path)
            if observed != finished or len(current) > MAX_EVENT_PAGE_BYTES \
                    or (target.st_dev, target.st_ino) != (after.st_dev,
                                                          after.st_ino):
                raise RuntimeError(
                    f"consolidation source changed before cleanup: {rel}")
            current_id = hashlib.sha256(
                rel.encode("utf-8") + b"\0" + current).hexdigest()
            if current_id != expected_id:
                raise RuntimeError(
                    f"consolidation source changed before cleanup: {rel}")
            _before_corpus_mutation()
            os.unlink(path)
            dfd = os.open(os.path.dirname(path),
                          os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)

        # A crash can leave sources whose lineage is already in the durable
        # epoch page. Cleanup is replayable and must not merge their counts a
        # second time.
        if not pending_items:
            recovery_dates = sorted(
                set(prior_dates) | {item[0] for item in items})
            try:
                recovery_epoch = _render_epoch_source_manifest(
                    state, merged_manifest, recovery_dates, event_ids)
            except ConsolidationCapacityError:
                kept_days |= {(organ, item[0]) for item in items}
                continue
            _write_epoch_source_manifest(state, recovery_epoch)
            _publish_event_index_entries(event_entries)
            for item in items:
                unlink_admitted(item)
            continue

        name = ORGANS.get(organ, (organ, ""))[0]
        pending_exemplars = {}
        try:
            for item in pending_items:
                log_part = item[2].split("## Timeline")[0].split("## Log")[-1]
                pending_exemplars[item[5]] = _epoch_exemplars([
                    line for line in log_part.splitlines()
                    if line.startswith("- ")])
        except ConsolidationCapacityError:
            kept_days |= {(organ, item[0]) for item in items}
            continue
        counts, all_tags, bullets, links = {}, {organ}, [], set()
        for date, path, text, tags, _source_id, _rel, _part in pending_items:
            cm = re.search(r"^sia_counts: (.*)$", text, re.M)
            if not cm:
                raise RuntimeError(
                    f"consolidation source lacks sia_counts: "
                    f"{os.path.relpath(path, CORPUS)}")
            source_counts = _parse_sia_counts(
                cm.group(1), os.path.relpath(path, CORPUS))
            for k, v in source_counts.items():
                counts[k] = counts.get(k, 0) + v
            all_tags |= tags
            for b in pending_exemplars[_rel]:
                bullets.append(f"- {date} ·" + b[1:])
            for wl in re.findall(r"\[\[([a-z0-9/._-]+)", text):
                links.add(wl)
        # merge with an existing epoch page — a later consolidation run for
        # the same week must extend it, never atomically erase it
        from_date = pending_items[0][0]
        to_date = pending_items[-1][0]
        pending_dates = {item[0] for item in pending_items}
        all_dates = sorted(set(prior_dates) | pending_dates)
        ndays = prior_ndays + len(pending_dates - set(prior_dates))
        if et:
            pm = re.search(r"^sia_counts: (.*)$", et, re.M)
            if not pm:
                raise RuntimeError(f"existing epoch lacks sia_counts: {slug}")
            epoch_counts = _parse_sia_counts(pm.group(1), slug)
            for k, v in epoch_counts.items():
                counts[k] = counts.get(k, 0) + v
            ptm = re.search(r"^tags: \[(.*)\]$", et, re.M)
            if ptm:
                all_tags |= {t.strip() for t in ptm.group(1).split(",")
                             if t.strip()}
            pdm = re.search(r"^date: (.*)$", et, re.M)
            if pdm and pdm.group(1).strip() < from_date:
                from_date = pdm.group(1).strip()
            etm = re.search(
                r"Consolidated from \d+ day-memories "
                r"\(\d{4}-\d{2}-\d{2} … (\d{4}-\d{2}-\d{2})\)", et)
            if etm and etm.group(1) > to_date:
                to_date = etm.group(1)
            if "## Exemplars" in et:
                ex = et.split("## Exemplars", 1)[1].split("\n## ")[0]
                prev_b = [l for l in ex.splitlines() if l.startswith("- ")]
                bullets = prev_b + bullets
            for wl in re.findall(r"\[\[([a-z0-9/._-]+)", et):
                links.add(wl)
        try:
            bullets = _epoch_exemplars(
                bullets, limit=MAX_WEEKLY_EPOCH_EXEMPLARS)
        except ConsolidationCapacityError:
            kept_days |= {(organ, item[0]) for item in items}
            continue
        total = sum(counts.values())
        agg = ", ".join(f"{v}× {k}" for k, v in
                        sorted(counts.items(), key=lambda kv: -kv[1])[:8])
        linkline = " ".join(f"[[{l}]]" for l in sorted(links)
                            if not l.startswith("events/"))[:800]
        epoch_frontmatter = [
            "type: epoch", fm_title(f"{name} — {y} week {w}"),
            f"tags: [{', '.join(sorted(all_tags))}]",
            f"date: {from_date}",
            f"sia_sources: {json.dumps(source_ids, separators=(',', ':'))}",
            "sia_source_manifest: " + json.dumps(
                merged_manifest, separators=(",", ":"),
                ensure_ascii=False),
            "sia_event_ids: " + json.dumps(
                event_ids, separators=(",", ":"), ensure_ascii=False),
            f"sia_dates: {json.dumps(all_dates, separators=(',', ':'))}",
            f"sia_counts: {json.dumps(counts, sort_keys=True)}",
        ]
        if organ == "jackal":
            epoch_frontmatter.insert(1, "origin: derived")
        epoch_body = (
            f"# {name} — {y} week {w}\n\n"
            f"Consolidated from {ndays} day-memories "
            f"({from_date} … {to_date}); originals verbatim in "
            f"corpus git history. Source: [[organs/{organ}]] for "
            f"[[sia/cortex]].\n\n"
            f"## Exemplars\n" + "\n".join(bullets) + "\n\n"
            f"{linkline}\n\n"
            f"## Timeline\n- **{to_date}** — {total} events that "
            f"week: {agg}\n")
        try:
            rendered_epoch = _render_bounded_epoch(
                slug, epoch_frontmatter, epoch_body)
        except ConsolidationCapacityError:
            kept_days |= {(organ, item[0]) for item in items}
            continue
        _write_bounded_epoch(slug, rendered_epoch)
        _publish_event_index_entries(event_entries)
        consolidated_days |= {(organ, item[0]) for item in pending_items}
        written_epochs += 1
        for item in items:
            unlink_admitted(item)
    result = (len(consolidated_days), written_epochs, len(kept_days))
    _acknowledge_consolidation_claims(scan_state)
    return result


def _parse_sia_counts(raw, label):
    try:
        counts = _strict_json_loads(raw)
    except (TypeError, UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError(f"{label} sia_counts is malformed") from exc
    if not isinstance(counts, dict) or any(
            not isinstance(key, str) or not key
            or sanitize_slugpart(key) != key
            or isinstance(value, bool) or not isinstance(value, int)
            or value < 0
            for key, value in counts.items()):
        raise ValueError(f"{label} sia_counts is invalid")
    return counts


def _event_shard_slug(organ, date, part):
    if isinstance(part, bool) or not isinstance(part, int) or part < 1:
        raise ValueError("event shard number is invalid")
    base = day_slug(organ, date)
    return base if part == 1 else f"{base}-part-{part}"


def _read_event_page(slug, *, expected_generation=None, dependency_capture=None):
    """Read one bounded regular event page without following its leaf."""
    path = corpus_path(slug)
    if dependency_capture is not None:
        return dependency_capture.read_file(
            path, MAX_EVENT_PAGE_BYTES,
            expected_generation=expected_generation).decode("utf-8", errors="strict")
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        fd = (_open_source_nofollow(path, flags)
              if expected_generation is not None else os.open(path, flags))
    except OSError as exc:
        if expected_generation is not None:
            raise ValueError(f"event page changed before read: {slug}") from exc
        raise
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_size > MAX_EVENT_PAGE_BYTES:
            raise ValueError(f"event page is not a bounded regular file: {slug}")
        if expected_generation is not None \
                and _file_generation(before) != expected_generation:
            raise ValueError(f"event page changed before read: {slug}")
    except Exception:
        os.close(fd)
        raise
    with os.fdopen(fd, "rb") as stream:
        raw = stream.read(MAX_EVENT_PAGE_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_EVENT_PAGE_BYTES:
        raise ValueError(f"event page changed while read: {slug}")
    if expected_generation is not None:
        try:
            target = _source_path_identity(path, flags)
        except OSError as exc:
            raise ValueError(f"event page changed after read: {slug}") from exc
        if _file_generation(target) != expected_generation:
            raise ValueError(f"event page changed after read: {slug}")
    return raw.decode("utf-8", errors="strict")


def _bounded_event_directory_snapshot(
        directory, *, cleanup_legacy_atomic=False, dependency_capture=None):
    """Return one complete event-directory snapshot or refuse its ceiling.

    Each raw directory page is independently bounded and generation-bound.
    The aggregate never crosses the event occurrence lookup ceiling; a
    mutation between pages refuses instead of turning a partial cycle into an
    absence or deletion claim.
    """
    if dependency_capture is not None:
        if cleanup_legacy_atomic:
            raise ValueError("captured event scans cannot clean source entries")
        return dependency_capture.directory_snapshot(directory)
    entries = []
    page_state = None
    inspected_total = 0
    try:
        while True:
            remaining = MAX_EVENT_DIRECTORY_INSPECTIONS - inspected_total
            if remaining <= 0:
                raise ValueError(
                    "event occurrence lookup exceeds its page bound")
            page, complete, inspected, next_state = _bounded_source_entries(
                directory, page_state,
                min(remaining, MAX_SOURCE_SCAN_ENTRIES),
                cleanup_legacy_atomic=cleanup_legacy_atomic)
            if page_state is not None and next_state.get("reset", False):
                raise RuntimeError(
                    "event directory changed during its bounded snapshot")
            inspected_total += inspected
            entries.extend(page)
            if inspected_total > MAX_EVENT_LOOKUP_PAGES:
                raise ValueError(
                    "event occurrence lookup exceeds its page bound")
            if complete:
                break
            page_state = next_state
    except FileNotFoundError as exc:
        if page_state is None and not entries:
            return []
        raise RuntimeError(
            "event directory disappeared during its bounded snapshot") \
            from exc
    names = [entry["name"] for entry in entries]
    if len(names) != len(set(names)):
        raise RuntimeError("event directory snapshot repeated an entry")
    return sorted(entries, key=lambda entry: entry["name"])


def _event_page_state(organ, date, part, *, expected_generation=None,
                      dependency_capture=None):
    slug = _event_shard_slug(organ, date, part)
    text = _read_event_page(
        slug, expected_generation=expected_generation,
        **({"dependency_capture": dependency_capture}
           if dependency_capture is not None else {}))
    match = FM_RE.match(text)
    if match is None:
        raise ValueError(f"existing event page lacks frontmatter: {slug}")
    fmtext = match.group(1)
    types = re.findall(r"^type:\s*(.*?)\s*$", fmtext, re.M)
    dates = re.findall(r"^date:\s*(.*?)\s*$", fmtext, re.M)
    if types != ["event-day"] or dates != [date]:
        raise ValueError(f"existing event page identity is invalid: {slug}")
    shard_values = re.findall(r"^sia_shard:\s*(.*?)\s*$", fmtext, re.M)
    if shard_values and shard_values != [str(part)]:
        raise ValueError(f"existing event page shard is invalid: {slug}")
    cm = re.search(r"^sia_counts: (.*)$", fmtext, re.M)
    if cm is None:
        raise ValueError(f"existing event page lacks sia_counts: {slug}")
    counts = _parse_sia_counts(cm.group(1), slug)
    tags = {organ}
    tm = re.search(r"^tags: \[(.*)\]$", fmtext, re.M)
    if tm:
        tags |= {tag.strip() for tag in tm.group(1).split(",")
                 if tag.strip()}
    body = text[match.end():]
    log_part = body.split("## Timeline", 1)[0]
    if "## Log" in log_part:
        log_part = log_part.split("## Log", 1)[1]
    bullets = [line for line in log_part.splitlines()
               if line.startswith("- ")]
    if len(bullets) > MAX_EVENT_BULLETS:
        raise ValueError(f"existing event shard exceeds its bound: {slug}")
    return {"slug": slug, "part": part, "counts": counts, "tags": tags,
            "bullets": bullets, "dirty": False}


def _event_day_shards(organ, date, *, dependency_capture=None):
    base = day_slug(organ, date)
    base_path = corpus_path(base)
    root = os.path.dirname(base_path)
    capture_kw = ({"dependency_capture": dependency_capture}
                  if dependency_capture is not None else {})
    entries = _bounded_event_directory_snapshot(
        root, cleanup_legacy_atomic=dependency_capture is None, **capture_kw)
    part_re = re.compile(
        rf"^{re.escape(os.path.basename(base_path[:-3]))}"
        r"-part-((?:[2-9]|[1-9][0-9]+))\.md$")
    parts, generations = [], {}
    base_present = False
    for entry in entries:
        is_base = entry["name"] == os.path.basename(base_path)
        match = part_re.fullmatch(entry["name"])
        if not is_base and match is None:
            continue
        if not stat.S_ISREG(entry["mode"]):
            raise ValueError("event day page is not a regular file")
        part = 1 if is_base else int(match.group(1))
        generations[part] = tuple(entry[key] for key in (
            "device", "inode", "size", "mtime_ns", "ctime_ns"))
        if is_base:
            base_present = True
        else:
            parts.append(part)
    if len(parts) != len(set(parts)) or len(parts) >= MAX_EVENT_SHARDS \
            or any(part > MAX_EVENT_SHARDS for part in parts):
        raise ValueError(
            "event day shard set is invalid or exceeds its bound "
            f"({len(parts)} shards, bound {MAX_EVENT_SHARDS}, "
            f"highest {max(parts) if parts else 0})")
    parts.sort()
    if base_present:
        if any(part != position for position, part in
               enumerate(parts, start=2)):
            raise ValueError(
                "event day shards are not contiguous "
                f"(observed parts {parts[:24]})")
        return [_event_page_state(
            organ, date, part, expected_generation=generations[part], **capture_kw)
            for part in [1] + parts]
    if parts:
        raise ValueError("event day has shards without its base page")
    return []


def _event_line(ev, event_id, semantic_id):
    stamp = ev.ts.strftime("%H:%M:%SZ")
    links = " ".join(
        f"[[{link}]]" for link in sorted(ev.links)
        if not link.startswith("organs/")
        and f"[[{link}" not in ev.summary)
    payload = ev.summary + (f" {links}" if links else "")
    base_line = f"- {stamp} {payload}"
    return (base_line
            + f" <!-- sia-event:{event_id}:{semantic_id} -->", payload,
            base_line)


def _render_event_shard(organ, date, shard, *, dependency_capture=None):
    name = ORGANS.get(organ, (organ, ""))[0]
    part = shard["part"]
    title = f"{name} — {date}" + (f" — part {part}" if part > 1 else "")
    total = sum(shard["counts"].values())
    aggregate = ", ".join(
        f"{value}× {kind}" for kind, value in sorted(
            shard["counts"].items(), key=lambda item: -item[1])[:6])
    fm = ["type: event-day", fm_title(title),
          f"tags: [{', '.join(sorted(shard['tags']))}]", f"date: {date}",
          f"sia_shard: {part}",
          f"sia_counts: {json.dumps(shard['counts'], sort_keys=True)}"]
    if organ == "jackal":
        fm.insert(1, "origin: derived")
    body = (f"# {title}\n\n"
            f"What [[organs/{organ}]] reported to [[sia/cortex]] on {date}.\n\n"
            f"## Log\n" + "\n".join(shard["bullets"]) + "\n\n"
            f"## Timeline\n- **{date}** — {total} events in this shard: "
            f"{aggregate}\n")
    if dependency_capture is not None:
        dependency_capture.reserve_render(shard["slug"], fm, body)
    encoded = ("---\n" + "\n".join(fm) + "\n---\n" + body).encode(
        "utf-8")
    if len(encoded) > MAX_EVENT_PAGE_BYTES:
        raise ValueError("rendered event shard exceeds its byte bound")
    if dependency_capture is not None:
        dependency_capture.rendered(shard["slug"], encoded)
    return fm, body


def _event_shard_trial(organ, date, shard, ev, line, *, dependency_capture=None):
    trial = {"slug": shard["slug"], "part": shard["part"],
             "counts": dict(shard["counts"]), "tags": set(shard["tags"]),
             "bullets": list(shard["bullets"]), "dirty": True}
    trial["bullets"].append(line)
    trial["counts"][ev.kind] = trial["counts"].get(ev.kind, 0) + 1
    trial["tags"] |= ev.tags
    try:
        _render_event_shard(
            organ, date, trial,
            **({"dependency_capture": dependency_capture}
               if dependency_capture is not None else {}))
    except ValueError as exc:
        if str(exc) == "rendered event shard exceeds its byte bound":
            return None
        raise
    return trial


def _event_source_parts(relative):
    """Return the canonical source/day/shard identity of an event source."""
    if not isinstance(relative, str):
        raise ValueError("event source path is invalid")
    match = EVENT_SOURCE_RE.fullmatch(relative)
    if match is None:
        raise ValueError("event source path is invalid")
    try:
        parsed = datetime.date.fromisoformat(match.group("date"))
    except ValueError as exc:
        raise ValueError("event source date is invalid") from exc
    if parsed.isoformat() != match.group("date"):
        raise ValueError("event source date is invalid")
    part = int(match.group("part") or "1")
    if part > MAX_EVENT_SHARDS:
        raise ValueError("event source shard exceeds its bound")
    return match.group("organ"), match.group("date"), part


def _event_payload_digest(payload):
    if not isinstance(payload, str):
        raise ValueError("event payload is invalid")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _event_index_relative(organ, event_id):
    if not isinstance(organ, str) \
            or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,199}", organ) is None \
            or not isinstance(event_id, str) \
            or re.fullmatch(r"[0-9a-f]{64}", event_id) is None:
        raise ValueError("consolidated event lookup identity is invalid")
    return os.path.join(
        "event-index", organ, event_id[:2], event_id + ".json")


def _canonical_event_index_entry(entry):
    required = {"schema", "organ", "event_id", "semantic_id",
                "payload_sha256", "source_rel", "source_sha256",
                "epoch_slug"}
    if not isinstance(entry, dict) or set(entry) != required \
            or entry.get("schema") != EVENT_INDEX_SCHEMA \
            or any(not isinstance(entry.get(key), str) for key in (
                "organ", "event_id", "payload_sha256", "source_rel",
                "source_sha256", "epoch_slug")) \
            or re.fullmatch(r"[0-9a-f]{64}", entry["event_id"]) is None \
            or re.fullmatch(
                r"[0-9a-f]{64}", entry["payload_sha256"]) is None \
            or re.fullmatch(
                r"[0-9a-f]{64}", entry["source_sha256"]) is None \
            or (entry["semantic_id"] is not None
                and (not isinstance(entry["semantic_id"], str)
                     or re.fullmatch(
                         r"[0-9a-f]{64}", entry["semantic_id"]) is None)):
        raise ValueError("consolidated event index entry is invalid")
    source_organ, source_date, _part = _event_source_parts(
        entry["source_rel"])
    year, week, _weekday = datetime.date.fromisoformat(
        source_date).isocalendar()
    expected_epoch = f"epochs/{source_organ}/{year}-w{week:02d}"
    if entry["organ"] != source_organ \
            or entry["epoch_slug"] != expected_epoch:
        raise ValueError("consolidated event index binding is invalid")
    return dict(entry)


def _event_index_encoded(entry):
    entry = _canonical_event_index_entry(entry)
    encoded = (json.dumps(
        entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n").encode("utf-8")
    if len(encoded) > MAX_EVENT_INDEX_BYTES:
        raise ValueError("consolidated event index entry exceeds its bound")
    return encoded


def _read_event_index_entry(organ, event_id, *, dependency_capture=None):
    relative = _event_index_relative(organ, event_id)
    path = os.path.join(CORPUS, relative)
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    if dependency_capture is not None:
        try:
            raw = dependency_capture.read_file(path, MAX_EVENT_INDEX_BYTES)
        except FileNotFoundError:
            return None
    else:
        try:
            fd = os.open(path, flags)
        except FileNotFoundError:
            return None
        with siaqueue.regular_file_stream(
                fd, label="consolidated event index entry") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) \
                    or before.st_size > MAX_EVENT_INDEX_BYTES:
                raise ValueError(
                    "consolidated event index entry is not a bounded regular file")
            raw = stream.read(MAX_EVENT_INDEX_BYTES + 1)
            after = os.fstat(stream.fileno())
        observed = (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns)
        finished = (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns)
        if observed != finished or len(raw) > MAX_EVENT_INDEX_BYTES:
            raise ValueError("consolidated event index entry changed while read")
    try:
        entry = _strict_json_loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("consolidated event index entry is malformed") from exc
    entry = _canonical_event_index_entry(entry)
    if entry["organ"] != organ or entry["event_id"] != event_id \
            or raw != _event_index_encoded(entry):
        raise ValueError("consolidated event index path binding is invalid")
    epoch = _read_epoch_state(
        entry["epoch_slug"],
        **({"dependency_capture": dependency_capture}
           if dependency_capture is not None else {}))
    source_record = {"rel": entry["source_rel"],
                     "sha256": entry["source_sha256"]}
    if entry["source_sha256"] not in epoch["sources"] \
            or source_record not in epoch["source_manifest"]:
        raise ValueError(
            "consolidated event index lacks exact epoch lineage")
    if epoch["event_ids_declared"] \
            and entry["event_id"] not in epoch["event_ids"]:
        raise ValueError(
            "consolidated event index lacks epoch completeness lineage")
    if dependency_capture is not None:
        dependency_capture.check_file(path)
    else:
        try:
            target = _source_path_identity(path, flags)
        except OSError as exc:
            raise ValueError("consolidated event index changed while validating") from exc
        if _file_generation(target) != finished:
            raise ValueError("consolidated event index changed while validating")
    return entry


def _preflight_event_index_entries(entries):
    if not isinstance(entries, list) \
            or len(entries) > MAX_EVENT_INDEX_RECORDS:
        raise ValueError("consolidated event index batch exceeds its bound")
    for entry in entries:
        entry = _canonical_event_index_entry(entry)
        existing = _read_event_index_entry(
            entry["organ"], entry["event_id"])
        if existing is not None and existing != entry:
            raise ValueError(
                "event identity conflicts with durable consolidation index")


def _publish_event_index_entries(entries):
    """Write every exact index entry before its source page may be unlinked."""
    _preflight_event_index_entries(entries)
    for entry in entries:
        existing = _read_event_index_entry(
            entry["organ"], entry["event_id"])
        if existing is not None:
            continue
        encoded = _event_index_encoded(entry)
        relative = _event_index_relative(entry["organ"], entry["event_id"])
        path = os.path.join(CORPUS, relative)
        _before_corpus_mutation()
        ensure_durable_directory(os.path.dirname(path))
        atomic_write(path, encoded.decode("utf-8"))


# Event-id rosters reconstructed from retained sources for epochs that
# declared source lineage but not yet `sia_event_ids` (every 1.7.x epoch has
# exactly this shape). Keyed by epoch slug and its observed file generation.
_RECONSTRUCTED_EPOCH_EVENT_IDS = {}
MAX_RETAINED_SOURCE_HISTORY = 64


def _retained_source_text(rel, expected_sha256, slug):
    """Exact text of a consolidated source page named by an epoch manifest.

    The live page is used when its lineage digest (sha256 of ``rel``, NUL,
    bytes) still matches; otherwise the corpus git history is searched, newest
    first and bounded, for the retained original with that digest. Nothing
    is guessed: an unretained source refuses by name.
    """
    _event_source_parts(rel)
    if not isinstance(expected_sha256, str) \
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise ValueError(
            f"event-index completeness is unavailable: {slug} "
            f"(manifest digest for {rel} is malformed)")

    def matches(raw):
        return hashlib.sha256(
            rel.encode("utf-8") + b"\0" + raw).hexdigest() == expected_sha256

    path = os.path.join(CORPUS, rel)
    try:
        with open(path, "rb") as stream:
            raw = stream.read(MAX_EVENT_PAGE_BYTES + 1)
    except (FileNotFoundError, NotADirectoryError):
        raw = None
    if raw is not None and len(raw) <= MAX_EVENT_PAGE_BYTES and matches(raw):
        return raw.decode("utf-8", errors="strict")
    history = _run_bounded_text_process(
        ["git", "log", "--format=%H", f"-n{MAX_RETAINED_SOURCE_HISTORY}",
         "--", rel], env=None, timeout=60, cwd=CORPUS,
        label="git retained-source history")
    if history.returncode == 0:
        for commit in history.stdout.split():
            if re.fullmatch(r"[0-9a-f]{40,64}", commit) is None:
                continue
            shown = _run_bounded_text_process(
                ["git", "show", f"{commit}:{rel}"], env=None, timeout=60,
                cwd=CORPUS, label="git retained-source read",
                output_limit=MAX_EVENT_PAGE_BYTES + 1)
            if shown.returncode != 0:
                continue
            raw = shown.stdout.encode("utf-8")
            if len(raw) <= MAX_EVENT_PAGE_BYTES and matches(raw):
                return shown.stdout
    raise ValueError(
        f"event-index completeness is unavailable: {slug} (retained source "
        f"{rel} with lineage digest {expected_sha256[:12]} is in neither the "
        "corpus tree nor its git history)")


def _event_ids_in_source_text(text, rel):
    match = FM_RE.match(text)
    if match is None:
        raise ValueError(
            f"retained consolidation source lacks frontmatter: {rel}")
    log_part = text[match.end():].split("## Timeline", 1)[0]
    if "## Log" in log_part:
        log_part = log_part.split("## Log", 1)[1]
    found = set()
    for line in (value for value in log_part.splitlines()
                 if value.startswith("- ")):
        marker = EVENT_MARKER_RE.fullmatch(line)
        if marker is None:
            if "sia-event:" in line:
                raise ValueError(
                    f"retained consolidation source has malformed event "
                    f"identity: {rel}")
            continue
        found.add(marker.group("id"))
        if len(found) > MAX_EVENT_INDEX_RECORDS:
            raise ValueError(
                f"retained consolidation source exceeds the event index "
                f"bound: {rel}")
    return found


def _reconstructed_epoch_event_ids(epoch, expected_generation):
    """The event-id roster of a manifest-only epoch, from its exact sources."""
    key = (epoch["slug"], tuple(expected_generation))
    cached = _RECONSTRUCTED_EPOCH_EVENT_IDS.get(key)
    if cached is not None:
        return cached
    if len(epoch["source_manifest"]) > MAX_EVENT_INDEX_RECORDS:
        raise ValueError(
            f"event-index completeness is unavailable: {epoch['slug']} "
            "(source manifest exceeds its bound)")
    roster = set()
    for record in epoch["source_manifest"]:
        text = _retained_source_text(
            record["rel"], record["sha256"], epoch["slug"])
        roster |= _event_ids_in_source_text(text, record["rel"])
    if len(_RECONSTRUCTED_EPOCH_EVENT_IDS) >= 4096:
        _RECONSTRUCTED_EPOCH_EVENT_IDS.clear()
    _RECONSTRUCTED_EPOCH_EVENT_IDS[key] = frozenset(roster)
    return _RECONSTRUCTED_EPOCH_EVENT_IDS[key]


def _missing_event_index_expectations(organ, wanted, *, dependency_capture=None):
    """Resolve missing leaves only from complete, bounded epoch manifests."""
    if not wanted:
        return {}
    if not isinstance(wanted, set) \
            or len(wanted) > MAX_EVENT_INDEX_RECORDS \
            or any(not isinstance(event_id, str)
                   or re.fullmatch(r"[0-9a-f]{64}", event_id) is None
                   for event_id in wanted):
        raise ValueError("event completeness lookup identity is invalid")
    root = os.path.join(CORPUS, "epochs", organ)
    capture_kw = ({"dependency_capture": dependency_capture}
                  if dependency_capture is not None else {})
    entries = _bounded_event_directory_snapshot(root, **capture_kw)
    found = {}
    for directory_entry in entries:
        name = directory_entry["name"]
        if EPOCH_PAGE_NAME_RE.fullmatch(name) is None:
            continue
        if not stat.S_ISREG(directory_entry["mode"]):
            raise ValueError(
                "epoch completeness source is not a regular file")
        slug = f"epochs/{organ}/{name[:-3]}"
        expected_generation = tuple(directory_entry[key] for key in (
            "device", "inode", "size", "mtime_ns", "ctime_ns"))
        epoch = _read_epoch_state(
            slug, expected_generation=expected_generation, **capture_kw)
        if not epoch["source_manifest_declared"]:
            # Epochs predating exact source/index lineage cannot make a
            # completeness claim. They remain readable legacy summaries.
            continue
        if not epoch["event_ids_declared"]:
            # Source lineage declared, event roster not yet: the shape every
            # 1.7.x epoch has. Its completeness claim is reconstructed from
            # the exact retained sources the manifest names (live page or
            # corpus git history by lineage digest); an unretained source
            # refuses by name instead of blocking every later pulse.
            epoch_ids = _reconstructed_epoch_event_ids(
                epoch, expected_generation)
        else:
            epoch_ids = epoch["event_ids"]
        for event_id in wanted.intersection(epoch_ids):
            prior = found.get(event_id)
            if prior is not None and prior != slug:
                raise ValueError(
                    "consolidated event identity occurs in multiple epochs")
            found[event_id] = slug
    return found


def _other_event_occurrences(organ, wanted, excluded, *, dependency_capture=None):
    """Find source-native IDs already admitted on another recent day."""
    if not wanted:
        return {}
    if len(wanted) > MAX_EVENT_INDEX_RECORDS:
        raise ValueError("event occurrence lookup exceeds its identity bound")
    root = os.path.join(CORPUS, "events", organ)
    capture_kw = ({"dependency_capture": dependency_capture}
                  if dependency_capture is not None else {})
    entries = _bounded_event_directory_snapshot(
        root, cleanup_legacy_atomic=dependency_capture is None, **capture_kw)
    found = {}
    page_re = re.compile(
        rf"^events/{re.escape(organ)}/[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}"
        r"(?:-part-(?:[2-9]|[1-9][0-9]+))?$")
    for entry in entries:
        if not entry["name"].endswith(".md"):
            continue
        slug = f"events/{organ}/{entry['name'][:-3]}"
        if page_re.fullmatch(slug) is None:
            continue
        if not stat.S_ISREG(entry["mode"]):
            raise ValueError("event occurrence source is not a regular file")
        if slug in excluded:
            continue
        generation = tuple(entry[key] for key in (
            "device", "inode", "size", "mtime_ns", "ctime_ns"))
        text = _read_event_page(
            slug, expected_generation=generation, **capture_kw)
        for line in text.splitlines():
            marker = EVENT_MARKER_RE.fullmatch(line)
            if marker is None:
                if "sia-event:" in line:
                    raise ValueError("event page contains a malformed identity")
                continue
            if marker.group("id") not in wanted:
                continue
            event_id = marker.group("id")
            prior = found.get(event_id)
            value = (slug, _event_payload_digest(marker.group("payload")),
                     marker.group("semantic"))
            if prior is not None and prior != value:
                raise ValueError("event identity occurs with conflicting bytes")
            found[event_id] = value
    missing = set()
    for event_id in sorted(wanted):
        entry = _read_event_index_entry(organ, event_id, **capture_kw)
        if entry is None:
            missing.add(event_id)
            continue
        if event_id in found:
            raise ValueError(
                "event identity occurs in live and consolidated evidence")
        found[event_id] = (
            entry["epoch_slug"], entry["payload_sha256"],
            entry["semantic_id"])
    expected = _missing_event_index_expectations(organ, missing, **capture_kw)
    if expected:
        event_id = sorted(expected)[0]
        raise ValueError(
            f"consolidated event index leaf is missing: {event_id}")
    return found


def _preflight_event_lookup(events):
    organs = {event.organ for event in events if event.occurrence}
    for organ in organs:
        root = os.path.join(CORPUS, "events", organ)
        _bounded_event_directory_snapshot(root, cleanup_legacy_atomic=True)


def _preflight_event_path_plan(planned_paths_by_organ):
    """Bound the union of every day planned for each source in this pulse."""
    for organ, planned_paths in planned_paths_by_organ.items():
        root = os.path.join(CORPUS, "events", organ)
        live_paths = {
            os.path.abspath(os.path.join(root, entry["name"]))
            for entry in _bounded_event_directory_snapshot(
                root, cleanup_legacy_atomic=True)
            if stat.S_ISREG(entry["mode"])
            and entry["name"].endswith(".md")}
        if len(live_paths | set(planned_paths)) > MAX_EVENT_LOOKUP_PAGES:
            raise ValueError(
                "event batch would exceed its bounded occurrence index")


def _plan_event_day_update(organ, date, new_events, *, dependency_capture=None):
    """Shared first assignment/render pass; this function never writes pages."""
    capture_kw = ({"dependency_capture": dependency_capture}
                  if dependency_capture is not None else {})
    shards = _event_day_shards(organ, date, **capture_kw)
    if not shards:
        shards = [{"slug": _event_shard_slug(organ, date, 1), "part": 1,
                   "counts": {}, "tags": {organ}, "bullets": [],
                   "dirty": False}]
    known_ids, legacy = {}, collections.defaultdict(list)
    for shard in shards:
        for index, line in enumerate(shard["bullets"]):
            marker = EVENT_MARKER_RE.fullmatch(line)
            if marker is None:
                if "sia-event:" in line:
                    raise ValueError("event page contains a malformed identity")
                legacy[line].append((shard, index))
                continue
            event_id = marker.group("id")
            if event_id in known_ids:
                raise ValueError("event identity is duplicated in day shards")
            known_ids[event_id] = (
                shard, marker.group("payload"), marker.group("semantic"))

    prepared = []
    stable_wanted = set()
    for ev in new_events:
        if not isinstance(ev, Event) or ev.organ != organ:
            raise ValueError("event does not belong to its day page")
        event_id = event_memory_identity(ev)
        semantic_id = event_semantic_identity(ev)
        line, payload, base_line = _event_line(ev, event_id, semantic_id)
        prepared.append((ev, event_id, semantic_id, line, payload, base_line))
        if ev.occurrence and event_id not in known_ids:
            stable_wanted.add(event_id)
    other_ids = _other_event_occurrences(
        organ, stable_wanted, {shard["slug"] for shard in shards}, **capture_kw)

    appended, admitted_pages, admitted_ids = [], [], set()
    batch_payloads = {}
    for ev, event_id, semantic_id, line, payload, base_line in prepared:
        prior_payload = batch_payloads.get(event_id)
        if prior_payload is not None \
                and prior_payload != (payload, semantic_id):
            raise ValueError("event identity conflicts within the input batch")
        batch_payloads[event_id] = (payload, semantic_id)
        existing = known_ids.get(event_id)
        if existing is not None:
            shard, stored_payload, stored_semantic = existing
            if stored_payload != payload or stored_semantic != semantic_id:
                raise ValueError("event identity conflicts with its day page")
            admitted_slug = shard["slug"]
        elif event_id in other_ids:
            admitted_slug, stored_payload_digest, stored_semantic = \
                other_ids[event_id]
            if stored_payload_digest != _event_payload_digest(payload) \
                    or stored_semantic != semantic_id:
                raise ValueError("event identity conflicts with another day page")
        elif legacy.get(base_line):
            raise ValueError(
                "legacy event cannot be identity-upgraded automatically")
        else:
            shard = shards[-1]
            if len(shard["bullets"]) >= MAX_EVENT_BULLETS:
                part = shard["part"] + 1
                if part > MAX_EVENT_SHARDS:
                    raise ValueError("event day exceeds its shard bound")
                shard = {"slug": _event_shard_slug(organ, date, part),
                         "part": part, "counts": {}, "tags": {organ},
                         "bullets": [], "dirty": False}
                shards.append(shard)
            trial = _event_shard_trial(organ, date, shard, ev, line, **capture_kw)
            if trial is None and shard["bullets"]:
                part = shard["part"] + 1
                if part > MAX_EVENT_SHARDS:
                    raise ValueError("event day exceeds its shard bound")
                shard = {"slug": _event_shard_slug(organ, date, part),
                         "part": part, "counts": {}, "tags": {organ},
                         "bullets": [], "dirty": False}
                shards.append(shard)
                trial = _event_shard_trial(organ, date, shard, ev, line, **capture_kw)
            if trial is None:
                raise ValueError("one event exceeds the event shard byte bound")
            shard.update(trial)
            known_ids[event_id] = (shard, payload, semantic_id)
            appended.append(ev)
            admitted_slug = shard["slug"]
        if event_id not in admitted_ids:
            admitted_ids.add(event_id)
            admitted_pages.append((ev, admitted_slug))

    # Render every target before the first mutation. Sequential atomic writes
    # are then replayable: an interrupted prefix already contains exact IDs.
    organ_root = os.path.join(CORPUS, "events", organ)
    live_paths = {
        os.path.abspath(os.path.join(organ_root, entry["name"]))
        for entry in _bounded_event_directory_snapshot(
            organ_root, cleanup_legacy_atomic=dependency_capture is None,
            **capture_kw)
        if stat.S_ISREG(entry["mode"])
        and entry["name"].endswith(".md")}
    planned_paths = {
        os.path.abspath(corpus_path(shard["slug"])) for shard in shards}
    if len(live_paths | planned_paths) > MAX_EVENT_LOOKUP_PAGES:
        raise ValueError(
            "event organ would exceed its bounded occurrence index")
    rendered = ([] if dependency_capture is not None else [
        (shard, _render_event_shard(organ, date, shard))
        for shard in shards if shard["dirty"]])
    return {"shards": shards, "appended": appended,
            "admitted_pages": admitted_pages, "rendered": rendered}


def update_day_page(organ, date, new_events, *, dry_run=False):
    """Plan or append observations to immutable bounded day shards."""
    planned = _plan_event_day_update(organ, date, new_events)
    if not dry_run:
        for shard, (frontmatter, body) in planned["rendered"]:
            write_page(shard["slug"], frontmatter, body)
    return ([shard["slug"] for shard in planned["shards"]],
            planned["appended"], planned["admitted_pages"])



# Exports are captured before bind() exists, so the owner can wrap every
# generated-entry/epoch-page, recovery, and legacy-replay function while
# leaving intra-module calls direct and stable.
_EXPORTED_FUNCTIONS = tuple(
    name for name, value in globals().items()
    if getattr(value, "__module__", None) == __name__)
_CHILD_FUNCTIONS = frozenset(_EXPORTED_FUNCTIONS)
_ORIGINAL_CHILD_FUNCTIONS = {
    name: globals()[name] for name in _EXPORTED_FUNCTIONS}
_CONTEXT_EXPORTS = frozenset({
    "_thought_legacy_catalog", "_thought_mind_replay_catalog",
})
_MISSING = object()
_BIND_LOCK = _threading.RLock()
_BIND_CONTROL_NAMES = frozenset({
    "_EXPORTED_FUNCTIONS", "_CHILD_FUNCTIONS", "_ORIGINAL_CHILD_FUNCTIONS",
    "_CONTEXT_EXPORTS", "_MISSING", "_BIND_LOCK", "_BIND_CONTROL_NAMES",
    "_BoundInvocationContext", "bind", "invoke",
})


def bind(parent_globals):
    """Bind the active sialib namespace without importing a second core."""
    if not isinstance(parent_globals, dict):
        raise TypeError("sialib thought context must be a globals dictionary")
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


class _BoundInvocationContext:
    """Rebind one owner at each context-protocol boundary."""

    def __init__(self, parent_globals, target, args, kwargs):
        self._parent_globals = parent_globals
        self._target = target
        self._args = args
        self._kwargs = kwargs
        self._manager = None
        self._state = "new"

    def __enter__(self):
        if self._state != "new":
            raise RuntimeError("SIA thought context manager is single-use")
        self._state = "opening"
        with _BIND_LOCK:
            bind(self._parent_globals)
            try:
                manager = self._target(*self._args, **self._kwargs)
                self._manager = manager
                value = manager.__enter__()
            except BaseException:
                self._manager = None
                self._state = "closed"
                raise
        self._state = "entered"
        return value

    def __exit__(self, exc_type, exc_value, traceback):
        if self._state != "entered":
            raise RuntimeError("SIA thought context manager is not entered")
        manager = self._manager
        self._manager = None
        self._state = "closed"
        with _BIND_LOCK:
            bind(self._parent_globals)
            return manager.__exit__(exc_type, exc_value, traceback)


def invoke(parent_globals, name, *args, **kwargs):
    """Bind and call one exported child function as one re-entrant action."""
    target = _ORIGINAL_CHILD_FUNCTIONS.get(name)
    if target is None:
        raise AttributeError(f"unknown SIA thought export: {name}")
    if name in _CONTEXT_EXPORTS:
        return _BoundInvocationContext(parent_globals, target, args, kwargs)
    with _BIND_LOCK:
        bind(parent_globals)
        return target(*args, **kwargs)
