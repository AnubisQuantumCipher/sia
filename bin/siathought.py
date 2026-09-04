"""Thought pages, thought recovery, and legacy replay for SIA.

This is the third bounded child of ``sialib`` and it follows the same
bind/invoke façade as ``siasenses`` and ``siagraph``: it imports no SIA
module, so one runtime state survives the dynamic aliases the test suite
loads sialib under, and explicit test patches of these helpers are mirrored
back into intra-module calls.  See ``docs/ARCHITECTURE.md``.

Two things this lane owns did **not** come with it, and both refusals are
load-bearing.

``_THOUGHT_RECOVERY_LIBC`` and ``_ThoughtRecoveryDirent`` stay in the core.
They execute ``ctypes.CDLL`` at module-body time, and a child that did that
would build a second libc handle for every alias the suite loads — the exact
duplicate state the façade exists to prevent.  The one function that reads
that handle, ``_read_legacy_thought_directory_page``, moved here and reaches
it through ``bind()`` instead.

The two ``@contextlib.contextmanager`` helpers stay in the core as well, and
the reason is a limit of the façade rather than of the code.  ``invoke()``
binds this module's globals, calls the target, and releases the lock when the
call returns — but calling a context manager only *constructs* it.  Its body
runs later, at ``__enter__``, outside that bind and outside that lock, so a
different sialib alias may have re-bound this module in between.  A context
manager therefore cannot be a delegate, and rather than export one with a
caveat it stays where its globals are stable.  Both are read from here through
``bind()``; nothing outside this lane calls them.
"""

import threading as _threading

def _canonical_thought_page_record(thought):
    """Project a thought into the exact self-describing page record."""
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
        record["slug"] = _canonical_corpus_slug(thought["slug"])
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
    """Name queue-owned thoughts solely from their durable identity."""
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
    """Read one stable, bounded, no-follow thought page."""
    path = corpus_path(_canonical_corpus_slug(slug))
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_size > MAX_THOUGHT_INBOX_BYTES:
            raise RuntimeError("thought page is not a bounded regular file")
        raw = stream.read(MAX_THOUGHT_INBOX_BYTES + 1)
        after = os.fstat(stream.fileno())
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    if observed != finished or len(raw) > MAX_THOUGHT_INBOX_BYTES:
        raise RuntimeError("thought page changed while read")
    try:
        return raw.decode("utf-8")
    except UnicodeError as exc:
        raise RuntimeError("thought page is not UTF-8") from exc


def _decode_exact_thought_page(slug, text_value):
    """Recover and byte-verify one self-described thought page."""
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
    record = _canonical_thought_page_record(encoded_record)
    if record != encoded_record:
        raise RuntimeError("thought recovery metadata is noncanonical")
    if record.get("slug") != slug:
        raise RuntimeError("thought recovery metadata binds another page")
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
        | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_mode & 0o077 \
                or before.st_size > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
            raise ValueError(
                "thought recovery record is not a bounded private file")
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
        | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_mode & 0o077 \
                or before.st_size > MAX_THOUGHT_RECOVERY_BYTES:
            raise ValueError(
                "thought recovery claim is not a bounded private file")
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
        directory_pointer = _THOUGHT_RECOVERY_LIBC.fdopendir(scan_descriptor)
        if not directory_pointer:
            saved_errno = ctypes.get_errno()
            os.close(scan_descriptor)
            raise OSError(saved_errno, os.strerror(saved_errno), directory)
        if cookie:
            _THOUGHT_RECOVERY_LIBC.seekdir(directory_pointer, cookie)
        selected = []
        inspected = 0
        complete = False
        while inspected < limit:
            ctypes.set_errno(0)
            record = _THOUGHT_RECOVERY_LIBC.readdir(directory_pointer)
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
            _THOUGHT_RECOVERY_LIBC.telldir(directory_pointer)))
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
            _THOUGHT_RECOVERY_LIBC.closedir(directory_pointer)
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
        | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_mode & 0o077 \
                or before.st_size > MAX_THOUGHT_RECOVERY_RECORD_BYTES:
            raise ValueError(
                "legacy thought index is not a bounded private file")
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
    """Durably stage exact page IDs before changing their mind projection."""
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
    """Commit staged page IDs only after mind and store are both durable."""
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
            # A reset archives these rebuildable derivatives; the exact mind
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
    """Persist a thought and return the page's exact canonical record."""
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
    """Persist one validated, origin-labeled thought corpus page."""
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


# Exports are captured before bind() exists, so the owner can wrap every
# thought-page, recovery and legacy-replay function while leaving intra-module
# calls direct and stable.
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


def invoke(parent_globals, name, *args, **kwargs):
    """Bind and call one exported child function as one re-entrant action."""
    target = _ORIGINAL_CHILD_FUNCTIONS.get(name)
    if target is None:
        raise AttributeError(f"unknown SIA thought export: {name}")
    with _BIND_LOCK:
        bind(parent_globals)
        return target(*args, **kwargs)
