"""The multi-writer agent-note lane: materialize, account, acknowledge.

Extracted from the resident library without behavioural change. The
marketplace per-file scan guard refuses a library above its headroom and
says extraction is the repair, not a raised threshold, so this lane moved out
whole rather than being trimmed.

Agent notes enter as immutable per-request files. `materialize_agent_notes`
writes their corpus pages and moves any queue-bound redaction counts into the
cumulative memo exactly once; `acknowledge_agent_notes` retires the requests
only after the corpus commit and gbrain sync succeed, and
`_forget_agent_note_redaction_receipt` drops the exactly-once receipt with them.

The lane uses the same bind/invoke facade as `siasenses` and `siagraph`: the
child never imports sialib, because tests load sialib under dynamic aliases
and must not create a second copy of its state. sialib binds its namespace
here and keeps every original name as a delegate, so each caller, and each
test that patches one of these names, still binds the call.
"""

import threading as _threading


def _read_existing_agent_note(slug):
    """Read one deterministic note page through a bounded stable handle."""
    slug = _canonical_corpus_slug(slug)
    path = corpus_path(slug)
    fd = _open_source_nofollow(path, os.O_RDONLY)
    with siaqueue.regular_file_stream(fd, label="agent note") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_size > MAX_THOUGHT_INBOX_BYTES:
            raise ValueError(
                "deterministic note page is not a bounded owner file")
        raw = stream.read(MAX_THOUGHT_INBOX_BYTES + 1)
        after = os.fstat(stream.fileno())
        try:
            target = _source_path_identity(path, os.O_RDONLY)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "deterministic note page changed while reading") from exc
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    current = (target.st_dev, target.st_ino, target.st_size,
               target.st_mtime_ns, target.st_ctime_ns)
    if observed != finished or finished != current \
            or len(raw) > MAX_THOUGHT_INBOX_BYTES:
        raise RuntimeError("deterministic note page changed while reading")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError("deterministic note page is not valid UTF-8") \
            from exc


def _account_agent_note_redactions(memo, requests, queue_errors):
    """Move queue-bound secret omissions into cumulative memo state once."""
    if memo is None:
        if any(request.get("redactions") for _path, request, _identity
               in requests):
            raise RuntimeError(
                "agent-note redaction accounting needs the durable memo")
        return
    receipts = _agent_note_redaction_receipts(
        memo.get("agent_note_redaction_receipts"))
    active = {request["request_id"] for _path, request, _identity in requests}
    changed = False
    if not queue_errors:
        retained = {request_id: count for request_id, count in receipts.items()
                    if request_id in active}
        if retained != receipts:
            receipts = retained
            changed = True
    totals = _canonical_pulse_redactions(memo.get("redactions", {}))
    for _path, request, _identity in requests:
        bound = request.get("redactions")
        count = bound.get("agent-note") if isinstance(bound, dict) else None
        request_id = request["request_id"]
        payload = request.get("payload", {})
        if count is not None and any(
                _redaction_projection(payload.get(field, ""))[1]
                for field in ("author", "text")):
            raise RuntimeError(
                "counted agent-note request still contains secret material")
        if count is None:
            if request_id in receipts:
                raise RuntimeError(
                    "agent-note redaction receipt conflicts with its request")
            continue
        if request_id in receipts:
            if receipts[request_id] != count:
                raise RuntimeError(
                    "agent-note redaction receipt conflicts with its request")
            continue
        current = totals.get("agent-note", 0)
        if current > MAX_JSON_SAFE_INTEGER - count:
            raise RuntimeError("pulse publication redactions are invalid")
        totals["agent-note"] = current + count
        receipts[request_id] = count
        changed = True
    if not changed:
        return
    updated = dict(memo, redactions=totals)
    if receipts:
        updated["agent_note_redaction_receipts"] = receipts
    else:
        updated.pop("agent_note_redaction_receipts", None)
    # A pulse or dream publication already in flight carries a redaction
    # TARGET, and crash recovery refuses any marker whose target is below the
    # durable totals.  This function raises those totals mid-pulse (agent notes
    # are materialized after the pulse marker is written), so it must advance
    # every pending target in the SAME memo write.  Before this, the first
    # counted agent-note redaction left the pulse marker at its old target while
    # the durable total moved past it, and every later start refused the marker:
    # the resident daemon could never start again.
    _rebind_pending_redaction_targets(updated)
    _write_memo(updated)
    memo.clear()
    memo.update(updated)


def _rebind_pending_redaction_targets(memo):
    """Advance pending publication redaction targets to cover durable totals.

    The target a pending marker binds is the cumulative total it will publish:
    the durable totals plus this process's not-yet-folded increments -- exactly
    `_projected_pulse_redactions`.  A target only ever moves forward; if the
    projection would retract any organ's target the state is inconsistent and
    this refuses rather than silently lowering what a publication promised.
    """
    target = _projected_pulse_redactions(memo)
    for key in ("pulse_publication", "dream_publication"):
        marker = memo.get(key)
        if not isinstance(marker, dict) or "redactions" not in marker:
            continue
        bound = _canonical_pulse_redactions(marker["redactions"])
        if any(target.get(organ, 0) < count for organ, count in bound.items()):
            raise RuntimeError(
                f"{key.split('_')[0]} publication redactions would retract: "
                f"bound {bound} exceeds projected {target}")
        if bound != target:
            memo[key] = dict(marker, redactions=copy.deepcopy(target))


def materialize_agent_notes(store, memo=None):
    """Materialize valid agent-note requests without acknowledging them.

    The caller acknowledges returned paths only after corpus commit and gbrain
    sync succeed. Existing deterministic pages make retry idempotent if a
    daemon dies after writing but before acknowledgment.
    """
    requests, queue_errors = siaqueue.pending(STATE)
    _account_agent_note_redactions(memo, requests, queue_errors)
    processed, pages, thoughts, errors = [], [], [], list(queue_errors)
    for path, request, identity in requests:
        try:
            payload = request["payload"]
            author = clip(redact(payload["author"], "agent-note"), 40)
            body = redact(payload["text"], "agent-note").strip()[:2000]
            if not body:
                raise ValueError("note is empty after redaction")
            # Notes are intentionally model-origin prose. Keep their body
            # visually readable while making Markdown/wiki-link syntax inert,
            # so a resident agent cannot mint graph edges or page structure.
            inert_body = html.escape(body, quote=False) \
                .replace("[", "&#91;").replace("]", "&#93;")
            queued = datetime.datetime.strptime(
                request["queued_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=datetime.timezone.utc)
            slug = (f"notes/{queued.strftime('%Y-%m-%d-%H%M%S')}-"
                    f"{sanitize_slugpart(author)}-{request['request_id']}")
            request_digest = identity.get("sha256", "")
            if not re.fullmatch(r"[0-9a-f]{64}", request_digest):
                raise ValueError("agent request has no observed content digest")
            frontmatter_lines = [
                "type: note", fm_title(clip(body, 70)),
                f"tags: [note, agent, {sanitize_slugpart(author)}]",
                f"date: {queued.strftime('%Y-%m-%d')}",
                "origin: model",
                f"request_id: {request['request_id']}",
                f"request_sha256: {request_digest}",
            ]
            page_body = (
                f"# note · from {author} · "
                f"{queued.strftime('%Y-%m-%d %H:%MZ')}\n\n"
                f"**Agent-authored memory — model-origin, not evidence. "
                f"A message from one session to the next.**\n\n"
                f"<pre class=\"sia-agent-note\">{inert_body}</pre>\n\n"
                f"[[organs/agents]] [[sia/cortex]]\n")
            expected_page = ("---\n" + "\n".join(frontmatter_lines)
                             + "\n---\n" + page_body)
            if page_exists(slug):
                existing = _read_existing_agent_note(slug)
                legacy_lines = [line for line in frontmatter_lines
                                if line != "origin: model"]
                legacy_page = ("---\n" + "\n".join(legacy_lines)
                               + "\n---\n" + page_body)
                if existing == legacy_page:
                    _before_corpus_mutation()
                    atomic_write(corpus_path(slug), expected_page)
                elif existing != expected_page:
                    raise ValueError(
                        "deterministic note page differs from exact request")
            else:
                ensure_durable_directory(
                    os.path.dirname(corpus_path(slug)))
                _before_corpus_mutation()
                atomic_write(corpus_path(slug), expected_page)
            already_materialized = any(
                item.get("queue_id") == request["request_id"]
                for item in store.get("thoughts", []))
            thought = add_thought(
                store, "note",
                f"{author} left a note for future sessions: "
                f"{clip(body, 100)} (⟦{slug}⟧)",
                [slug, "organs/agents"], queue_id=request["request_id"],
                thought_ts=request["queued_at"], origin="model")
            if not already_materialized:
                thoughts.append(thought)
            processed.append((path, identity))
            pages.append(slug)
        except Exception as exc:
            errors.append({"file": os.path.basename(path),
                           "error": str(exc)})
    return processed, pages, thoughts, errors


def acknowledge_agent_notes(paths, commit_status, synced, after_ack=None):
    """Acknowledge only requests whose corpus transaction reached gbrain.

    Return the successful count and per-request errors so a partial unlink
    failure remains visible and retryable rather than being reported as an
    all-or-nothing result.
    """
    if commit_status == "error" or not synced:
        return 0, []
    acknowledged, errors = 0, []
    for path, identity in paths:
        try:
            siaqueue.acknowledge(path, identity)
            if after_ack is not None:
                after_ack(identity)
            acknowledged += 1
        except Exception as exc:
            errors.append({"file": os.path.basename(path),
                           "error": str(exc)})
    return acknowledged, errors


def _forget_agent_note_redaction_receipt(memo, identity):
    """Retire an accounted request only after its durable queue unlink."""
    request_id = identity.get("request_id") \
        if isinstance(identity, dict) else None
    receipts = memo.get("agent_note_redaction_receipts") \
        if isinstance(memo, dict) else None
    if not isinstance(receipts, dict) or request_id not in receipts:
        return
    receipts.pop(request_id)
    if not receipts:
        memo.pop("agent_note_redaction_receipts", None)


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
        raise TypeError("sialib agent-note context must be a globals dictionary")
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
        raise AttributeError(f"unknown SIA agent-note export: {name}")
    with _BIND_LOCK:
        bind(parent_globals)
        return target(*args, **kwargs)
