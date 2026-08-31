"""SIA's bounded evidence-sensing implementation.

This module deliberately does not import `sialib`.  SIA's core may be loaded
under a dynamic test alias, so importing a canonical core module here would
create a second, stale runtime state.  The owning core binds its current
namespace immediately before each public sensing call instead.
"""

import threading as _threading

def sense_jackal(cursors):
    """The JACKAL ledger is a SLIDING WINDOW (~200 rows; older rows rotate to
    retired/), rewritten via os.replace on every append — so neither inode,
    byte offset, line count, nor timestamp is a total cursor.  Retain the
    exact identities in the current bounded window instead."""
    evs = []
    path = os.path.join(HOME, ".local/state/jackal/results.jsonl")
    raw, truncated = _stable_bounded_source_tail(path)
    lines = _decode_lf_records(raw, "JACKAL retained window")
    if len(lines) > MAX_SOURCE_TAIL_RECORDS:
        lines = lines[-MAX_SOURCE_TAIL_RECORDS:]
        truncated = True
    records = []
    for line in lines:
        try:
            r = json.loads(line)
            if not isinstance(r, dict):
                continue
            source_ts = r.get("ts", 0)
            if isinstance(source_ts, bool) \
                    or not isinstance(source_ts, (int, float)):
                continue
            source_ts = float(source_ts)
            if not math.isfinite(source_ts):
                continue
            observed_at = datetime.datetime.fromtimestamp(
                source_ts, datetime.timezone.utc)
            record_id = hashlib.sha256(json.dumps(
                r, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
            records.append((r, source_ts, observed_at, record_id))
        except (OverflowError, OSError, TypeError, UnicodeError, ValueError,
                RecursionError):
            continue
    current_ids = [record_id for _r, _ts, _at, record_id in records]
    window = cursors.get("jackal.window")
    if window is None:
        # A legacy timestamp cannot distinguish a same/lower-timestamp row
        # introduced by a later rewrite. Replay the retained bounded window;
        # stable occurrence identities make already-published rows idempotent.
        previous_ids = set() if "jackal.ts" in cursors \
            or os.environ.get("SIA_BACKFILL") == "1" else set(current_ids)
    else:
        if not isinstance(window, dict) \
                or window.get("schema") != "sia-jackal-window-v1" \
                or not isinstance(window.get("receipt"), str) \
                or re.fullmatch(r"[0-9a-f]{64}", window["receipt"]) is None \
                or not isinstance(window.get("truncated"), bool) \
                or not isinstance(window.get("seen"), list) \
                or len(window["seen"]) > MAX_SOURCE_TAIL_RECORDS \
                or any(not isinstance(value, str)
                       or re.fullmatch(r"[0-9a-f]{64}", value) is None
                       for value in window["seen"]):
            raise ValueError("JACKAL window cursor is invalid")
        prior_receipt_payload = json.dumps({
            "rows": window["seen"], "truncated": window["truncated"],
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if window["receipt"] != hashlib.sha256(
                prior_receipt_payload).hexdigest():
            raise ValueError("JACKAL window cursor receipt is invalid")
        previous_ids = set(window["seen"])
    emitted_ids = set()
    new = []
    for row in records:
        record_id = row[3]
        if record_id not in previous_ids and record_id not in emitted_ids:
            new.append(row)
            emitted_ids.add(record_id)
    receipt_payload = json.dumps({
        "rows": current_ids, "truncated": bool(truncated),
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    cursors["jackal.window"] = {
        "schema": "sia-jackal-window-v1",
        "receipt": hashlib.sha256(receipt_payload).hexdigest(),
        "truncated": bool(truncated),
        "seen": current_ids,
    }
    cursors.pop("jackal.ts", None)
    cursors.pop("jackal.lines", None)
    if truncated:
        evs.append(_source_truncation_event("jackal", "JACKAL result ledger"))
    for r, _source_ts, observed_at, record_id in new:
        tool = str(r.get("tool", "?"))
        status_raw = str(r.get("status", "?"))
        status = _source_entity_token(status_raw, "jackal-status")
        # results.jsonl is a convenience ledger written by the integration,
        # not a verified artifact. Even a row that claims ``formal`` is only
        # an unverified observation until a retained artifact has gone back
        # through JACKAL's front-door verifier.
        tags = {"jackal", "unverified-observation", status}
        if status_raw in ("refused", "refusal"):
            tags.add("refusal")
        parsed = ""
        f = r.get("fields") or {}
        if isinstance(f, dict):
            parsed = f.get("parsed") or ""
        summary = f"{tool} → {status_raw}" \
            + (f" ({clip(parsed, 40)})" if parsed else "")
        occurrence = "jackal:" + record_id
        evs.append(Event("jackal", observed_at, status, summary,
                         {"organs/jackal"}, tags, occurrence=occurrence))
    # receipts: new files in the receipts dir
    rdir = os.path.join(HOME, ".local/state/jackal/receipts")
    page_key = "jackal.receipts.page"
    page_before = cursors.get(page_key)
    began_at_start = page_before is None or (
        isinstance(page_before, dict) and page_before.get("cookie", 0) == 0)
    try:
        entries, complete, _inspected, next_page = _bounded_source_entries(
            rdir, page_before)
    except FileNotFoundError:
        cursors.pop(page_key, None)
        entries, complete, next_page = [], True, {}
    cursors[page_key] = next_page
    names = [entry["name"] for entry in entries
             if stat.S_ISREG(entry["mode"])
             and entry["name"].endswith(".json")]
    seen = _bounded_seen_names(cursors.get("jackal.receipts"))
    if seen is None:
        seen = []
        cursors["jackal.receipts.baselining"] = True
    baselining = bool(cursors.get("jackal.receipts.baselining", False))
    seen_set = set(seen)
    for name in names:
        if name in seen_set:
            continue
        if len(seen) >= MAX_SOURCE_SCAN_ENTRIES:
            evs.append(_source_entry_refusal_event(
                "jackal", f"JACKAL receipt {name}"))
            continue
        if not baselining:
            token = _source_entity_token(name, "jackal-receipt")
            evs.append(Event("jackal", utcnow(), "receipt-observed",
                             f"unverified receipt file observed "
                             f"{clip(name, 12)}…",
                             {"organs/jackal"},
                             {"jackal", "unverified-observation"},
                             occurrence=f"jackal-receipt:{token}"))
        seen.append(name)
        seen_set.add(name)
    cursors["jackal.receipts"] = (
        sorted(names) if complete and began_at_start else sorted(seen))
    if complete and baselining:
        cursors["jackal.receipts.baselining"] = False
    return evs


def _attest_rows(path, cursors, key):
    rows = []
    for line in tail_lines(path, cursors, key):
        p = line.split("\t")
        if len(p) == 9:
            rows.append(p)
    return rows


def _attest_generation(path, label):
    """Return a no-follow identity for one regular keeper authority file."""
    descriptor = _open_source_nofollow(path, os.O_RDONLY)
    try:
        info = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
        raise RuntimeError(f"{label} is not an owned regular file")
    return _journal_file_identity(info)


def _verified_builtin_attest_rows(chain, cursors, key):
    """Verify and tail one unchanged built-in ledger generation.

    The caller's cursor is isolated until the same ledger and verifier file
    identities are observed before verification and after the bounded tail.
    Thus no row appended/replaced after keeper success can become evidence in
    this transaction.
    """
    binding = _chain_cmds().get(chain)
    if binding is None:
        return []
    ledger, tool, command = binding
    if command and command[0] == INVALID_CHAIN_SENTINEL:
        raise RuntimeError(f"{chain} ledger projection binding is invalid")
    if not os.path.lexists(ledger) and not os.path.lexists(tool):
        return []
    if not os.path.lexists(ledger) or not os.path.lexists(tool):
        raise RuntimeError(f"{chain} ledger projection keeper is incomplete")
    trial = copy.deepcopy(cursors)
    ledger_before = _attest_generation(ledger, f"{chain} ledger")
    tool_before = _attest_generation(tool, f"{chain} verifier")
    try:
        verified = _run_bounded_text_process(
            command, env=None, timeout=60, cwd=None,
            label=f"{chain} ledger verifier")
    except Exception as exc:
        raise RuntimeError(
            f"{chain} ledger projection keeper did not run") from exc
    if verified.returncode != 0:
        detail = (verified.stderr or verified.stdout
                  or "keeper refused")[-160:]
        raise RuntimeError(
            f"{chain} ledger projection refused: {detail}")
    rows = _attest_rows(ledger, trial, key)
    ledger_after = _attest_generation(ledger, f"{chain} ledger")
    tool_after = _attest_generation(tool, f"{chain} verifier")
    if ledger_before != ledger_after or tool_before != tool_after:
        raise RuntimeError(
            f"{chain} ledger projection changed after keeper verification")
    cursors.clear()
    cursors.update(trial)
    return rows


def signed_ledger_event_projection(chain, row):
    """Return the exact corpus Event semantics for one supported signed row.

    This pure seam is shared by live sensing and the benchmark. Unknown custom
    chains deliberately have no guessed projection: their verifier authenticates
    rows, but does not define how those rows become SIA event bullets.
    """
    if not isinstance(chain, str) or not isinstance(row, (list, tuple)) \
            or len(row) != 9 or any(not isinstance(field, str) for field in row):
        raise ValueError("signed ledger projection row is invalid")
    seq, stamp, action, arg1, arg2, _digest, _size, _prev, _sig = row
    if chain == "custos":
        try:
            timestamp = datetime.datetime.fromtimestamp(
                int(stamp), datetime.timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise ValueError(
                "Custos row has no canonical projection timestamp") from exc
        name = os.path.basename(arg1) if arg1 not in ("-", "") else action
        destination = (os.path.basename(os.path.dirname(arg2))
                       if arg2 not in ("-", "") else "")
        return Event(
            "custos", timestamp, action,
            f"{action}: {clip(name, 40)}"
            + (f" → {destination}/" if destination else ""),
            {"organs/custos"}, {"custos"},
            occurrence=f"custos-ledger:{seq}")
    try:
        timestamp = datetime.datetime.strptime(
            stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=datetime.timezone.utc)
    except ValueError as exc:
        raise ValueError(
            "attest row has no canonical projection timestamp") from exc
    if chain == "sia":
        if action.startswith(("GENESIS:", "PULSE:")) \
                or action in {"DREAM:bench", "SOURCE:refuse"}:
            return None
        return Event(
            "sia", timestamp, action.split(":", 1)[0].lower(),
            f"signed sequence {seq}: {action} {arg1} {arg2}".strip(),
            {"organs/sia"}, {"sia", "signed-ledger"},
            occurrence=f"sia-ledger:{seq}")
    if chain == "sekhmet":
        tags = {"sekhmet"}
        links = {"organs/sekhmet"}
        kind = action.split(":", 1)[0].lower()
        if kind in ("intent", "outcome"):
            tags.add("healing")
        unit = arg1 if arg1 not in ("sekhmet", "-") else arg2
        if unit and unit not in ("-", "ok", "degraded") \
                and "." not in unit[:1]:
            raw_unit = unit.replace(".service", "")
            token = _source_entity_token(raw_unit, "unit")
            if raw_unit not in ("sekhmet", "ok", "degraded", "unknown"):
                links.add(f"units/{token}")
        return Event(
            "sekhmet", timestamp, kind,
            f"{action} {arg1} {arg2}".strip(), links, tags,
            occurrence=f"sekhmet-ledger:{seq}")
    if chain == "aegis":
        tags = {"aegis"}
        if arg2 == "FAIL":
            tags.add("failed")
        return Event(
            "aegis", timestamp, action.split(":", 1)[0].lower(),
            f"{action} {arg1} {arg2}".strip(), {"organs/aegis"}, tags,
            occurrence=f"aegis-ledger:{seq}")
    raise ValueError(
        f"signed chain {chain!r} has no defined corpus projection")


def sense_sia(cursors):
    """Project verified SIA lifecycle rows into answer-bearing memory pages.

    PULSE rows are deliberately excluded: projecting one would itself make
    the corpus dirty and mint another PULSE row, creating an endogenous loop.
    Benchmark-result rows are excluded for the analogous evaluation-feedback
    reason. Source refusal rows are also terminal evidence, not fresh source
    material: projecting one and refusing that projection could otherwise
    mint a replacement refusal forever. The signed ledger remains the ground
    truth; this is only its local retrievable projection.
    """
    events = []
    for row in _verified_builtin_attest_rows(
            "sia", cursors, "sia.lines"):
        try:
            event = signed_ledger_event_projection("sia", row)
        except ValueError as exc:
            raise RuntimeError(
                "verified SIA ledger exposed a non-canonical row") from exc
        if event is not None:
            events.append(event)
    return events


def sense_sekhmet(cursors):
    evs = []
    for row in _verified_builtin_attest_rows(
            "sekhmet", cursors, "sekhmet.lines"):
        evs.append(signed_ledger_event_projection("sekhmet", row))
    return evs


def sense_custos(cursors):
    evs = []
    for row in _verified_builtin_attest_rows(
            "custos", cursors, "custos.lines"):
        evs.append(signed_ledger_event_projection("custos", row))
    return evs


def sense_aegis(cursors):
    evs = []
    for row in _verified_builtin_attest_rows(
            "aegis", cursors, "aegis.lines"):
        evs.append(signed_ledger_event_projection("aegis", row))
    return evs


def _worldline_select_list(specs):
    return ", ".join(
        f"typeof({name}), length(CAST({name} AS BLOB)), "
        f"substr(CAST({name} AS BLOB), 1, ?)"
        for name, _cap, _nullable in specs)


def _worldline_observation(row, specs):
    """Decode one SQL-guarded row without admitting a whole hostile field."""
    if not isinstance(row, (list, tuple)) or len(row) != len(specs) * 3:
        raise RuntimeError("worldline bounded query returned a bad row shape")
    observed = {}
    selected_bytes = 0
    for index, (name, cap, nullable) in enumerate(specs):
        sql_type, byte_length, prefix = row[index * 3:index * 3 + 3]
        if not isinstance(sql_type, str):
            raise RuntimeError("worldline bounded query returned a bad type")
        if sql_type == "null":
            if byte_length is not None or prefix is not None:
                raise RuntimeError(
                    "worldline bounded query returned inconsistent NULL")
            raw = b""
            length = 0
        else:
            if byte_length == 0 and prefix is None:
                # SQLite represents substr(X'') as NULL even though the
                # source value is a non-NULL, zero-byte TEXT/BLOB.
                prefix = b""
            if isinstance(byte_length, bool) \
                    or not isinstance(byte_length, int) \
                    or byte_length < 0 \
                    or not isinstance(prefix, bytes) \
                    or len(prefix) > cap + 1 \
                    or (byte_length <= cap and len(prefix) != byte_length) \
                    or (byte_length > cap and len(prefix) != cap + 1):
                raise RuntimeError(
                    "worldline bounded query returned inconsistent bytes")
            raw = prefix
            length = byte_length
        selected_bytes += len(raw)
        observed[name] = {
            "type": sql_type, "bytes": length, "prefix": raw,
            "cap": cap, "nullable": nullable,
        }
    return observed, selected_bytes


def _worldline_decode_text(observed, name):
    item = observed[name]
    if item["type"] == "null":
        if item["nullable"]:
            return "", None
        return None, f"worldline-{name}-type-invalid"
    if item["type"] != "text":
        return None, f"worldline-{name}-type-invalid"
    if item["bytes"] > item["cap"]:
        return None, f"worldline-{name}-capacity"
    try:
        value = item["prefix"].decode("utf-8", errors="strict")
    except UnicodeError:
        return None, f"worldline-{name}-utf8-invalid"
    if "\x00" in value or any(
            unicodedata.category(char) in {"Cc", "Cf"} for char in value):
        return None, f"worldline-{name}-control-invalid"
    return value, None


def _worldline_ordering_identity(observed):
    event_id, event_error = _worldline_decode_text(observed, "event_id")
    created, created_error = _worldline_decode_text(observed, "created_at")
    if event_error is not None or not event_id \
            or WORLDLINE_VISIBLE_ID_RE.fullmatch(event_id) is None:
        raise ValueError("worldline cursor event id is invalid")
    if created_error is not None:
        raise ValueError("worldline cursor timestamp is invalid")
    return event_id, created, _worldline_time(created)


def _worldline_observation_digest(observed):
    metadata = [{
        "name": name,
        "type": observed[name]["type"],
        "bytes": observed[name]["bytes"],
        "prefix_sha256": hashlib.sha256(
            observed[name]["prefix"]).hexdigest(),
    } for name, _cap, _nullable in WORLDLINE_FIELD_SPECS]
    return hashlib.sha256(json.dumps(
        metadata, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()


def _worldline_refusal_record(event_id, created, reason, observed):
    entry_id = hashlib.sha256(
        (created + "\0" + event_id).encode("utf-8")).hexdigest()
    return {
        "schema": "sia-source-entry-refusal-v1",
        "source": "sense_worldline",
        "reason": reason,
        "entry_sha256": entry_id,
        "observation_sha256": _worldline_observation_digest(observed),
        "created_at": created,
    }


def _queue_source_entry_refusal(cursors, record):
    rows = cursors.setdefault(SOURCE_ENTRY_REFUSALS_KEY, [])
    if not isinstance(rows, list) or len(rows) >= MAX_WORLDLINE_REFUSALS:
        raise ValueError("source entry refusal state exceeds its bound")
    rows.append(record)


def _worldline_refusal_event(timestamp, record):
    return Event(
        "worldline", timestamp, "source-entry-refused",
        f"WORLDLINE row refused: {record['reason']}",
        {"organs/worldline"}, {"source-entry-refused", "refusal"},
        occurrence=(f"worldline-refusal:{record['entry_sha256']}:"
                    f"{record['observation_sha256']}"))


def _worldline_time(value):
    """Validate WORLDLINE's UTC ordering key and return its datetime."""
    if not isinstance(value, str) \
            or len(value.encode("utf-8")) > MAX_SOURCE_NAME_CHARS \
            or WORLDLINE_TIME_RE.fullmatch(value) is None:
        raise ValueError("worldline cursor timestamp is invalid")
    try:
        parsed = datetime.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("worldline cursor timestamp is invalid") from exc
    if parsed.utcoffset() != datetime.timedelta(0):
        raise ValueError("worldline cursor timestamp is not UTC")
    return parsed


def _worldline_cursor(cursors):
    """Read the composite cursor, accepting the old timestamp-only state.

    A missing event id is the legacy representation.  Its empty event-id
    lower bound deliberately replays the tied timestamp once, favoring
    recovery of its possibly unobserved tail over irreversible omission.
    """
    has_time = WORLDLINE_CURSOR_TIME in cursors
    has_event = WORLDLINE_CURSOR_EVENT in cursors
    if not has_time:
        if has_event:
            raise ValueError("worldline cursor event id has no timestamp")
        return None
    created = cursors[WORLDLINE_CURSOR_TIME]
    if not isinstance(created, str):
        raise ValueError("worldline cursor timestamp is invalid")
    if created:
        _worldline_time(created)
    event_id = cursors.get(WORLDLINE_CURSOR_EVENT, "")
    if not isinstance(event_id, str) \
            or len(event_id.encode("utf-8")) > MAX_SOURCE_NAME_CHARS \
            or (event_id
                and WORLDLINE_VISIBLE_ID_RE.fullmatch(event_id) is None):
        raise ValueError("worldline cursor event id is invalid")
    if not created and event_id:
        raise ValueError("worldline cursor event id has no timestamp")
    return created, event_id


def _set_worldline_cursor(cursors, created, event_id):
    if created:
        _worldline_time(created)
    if not isinstance(event_id, str) \
            or len(event_id.encode("utf-8")) > MAX_SOURCE_NAME_CHARS \
            or (event_id
                and WORLDLINE_VISIBLE_ID_RE.fullmatch(event_id) is None):
        raise ValueError("worldline event id is invalid")
    cursors[WORLDLINE_CURSOR_TIME] = created
    cursors[WORLDLINE_CURSOR_EVENT] = event_id


def sense_worldline(cursors):
    evs = []
    db = os.path.join(HOME, ".local/state/worldline/worldline.sqlite3")
    if not os.path.exists(db):
        return evs
    last = _worldline_cursor(cursors)
    backfill = os.environ.get("SIA_BACKFILL") == "1"
    if last is None and not backfill:
        try:
            with contextlib.closing(sqlite3.connect(
                    f"file:{db}?mode=ro", uri=True, timeout=2.0)) as con:
                row = con.execute(
                    f"SELECT {_worldline_select_list(WORLDLINE_ORDER_SPECS)} "
                    "FROM causal_events ORDER BY created_at DESC, "
                    "event_id DESC LIMIT 1",
                    tuple(cap + 1 for _name, cap, _nullable
                          in WORLDLINE_ORDER_SPECS)).fetchone()
        except Exception as e:
            raise RuntimeError(f"worldline sqlite: {e}") from e
        if row is None:
            _set_worldline_cursor(cursors, "", "")
        else:
            observed, _selected = _worldline_observation(
                row, WORLDLINE_ORDER_SPECS)
            event_id, created, _timestamp = \
                _worldline_ordering_identity(observed)
            _set_worldline_cursor(cursors, created, event_id)
        return evs
    if last is None:
        last = ("", "")
    last_created, last_event = last
    prior_refusals = cursors.get(SOURCE_ENTRY_REFUSALS_KEY, [])
    if not isinstance(prior_refusals, list) \
            or len(prior_refusals) > MAX_WORLDLINE_REFUSALS:
        raise ValueError("source entry refusal state exceeds its bound")
    staged_refusals = []
    try:
        with contextlib.closing(sqlite3.connect(
                f"file:{db}?mode=ro", uri=True, timeout=2.0)) as con:
            query = con.execute(
                f"SELECT {_worldline_select_list(WORLDLINE_FIELD_SPECS)} "
                "FROM causal_events "
                "WHERE created_at > ? OR "
                "(created_at = ? AND event_id > ?) "
                "ORDER BY created_at, event_id LIMIT ?",
                (*tuple(cap + 1 for _name, cap, _nullable
                        in WORLDLINE_FIELD_SPECS),
                 last_created, last_created, last_event,
                 MAX_WORLDLINE_ROWS))
            next_created, next_event = last_created, last_event
            selected_total = 0
            while True:
                row = query.fetchone()
                if row is None:
                    break
                observed, selected_bytes = _worldline_observation(
                    row, WORLDLINE_FIELD_SPECS)
                if selected_total + selected_bytes \
                        > MAX_WORLDLINE_PAGE_BYTES:
                    break
                event_id, created, timestamp = \
                    _worldline_ordering_identity(observed)
                if (created, event_id) <= (next_created, next_event):
                    raise ValueError(
                        "worldline cursor ordering identity is invalid")

                decoded = {}
                refusal_reason = None
                for name, _cap, _nullable in WORLDLINE_FIELD_SPECS:
                    if name in {"event_id", "created_at"}:
                        continue
                    value, error = _worldline_decode_text(observed, name)
                    decoded[name] = value
                    if refusal_reason is None and error is not None:
                        refusal_reason = error
                kind = decoded["kind"]
                world = decoded["world_instance"]
                if refusal_reason is None \
                        and (not kind or sanitize_slugpart(kind) != kind):
                    refusal_reason = "worldline-kind-identity-invalid"
                if refusal_reason is None \
                        and (not world or
                             WORLDLINE_VISIBLE_ID_RE.fullmatch(world) is None):
                    refusal_reason = "worldline-world-identity-invalid"

                if refusal_reason is not None:
                    if len(prior_refusals) + len(staged_refusals) \
                            >= MAX_WORLDLINE_REFUSALS:
                        break
                    refusal = _worldline_refusal_record(
                        event_id, created, refusal_reason, observed)
                    staged_refusals.append(refusal)
                    evs.append(_worldline_refusal_event(timestamp, refusal))
                elif kind in WL_LOUD_KINDS:
                    tags = {"worldline"}
                    if kind == "collapse-receipt":
                        tags.add("collapse")
                    what = (decoded["tool"] or decoded["reason"]
                            or decoded["path_display"] or "")
                    evs.append(Event(
                        "worldline", timestamp, kind,
                        f"{kind} {clip(what, 60)} (world {world[:8]})",
                        {"organs/worldline"}, tags,
                        occurrence=f"worldline:{event_id}"))
                else:
                    evs.append(Event(
                        "worldline", timestamp, "activity",
                        f"world activity: {kind}",
                        {"organs/worldline"}, {"worldline"},
                        occurrence=f"worldline:{event_id}"))
                selected_total += selected_bytes
                next_created, next_event = created, event_id
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise RuntimeError(f"worldline sqlite: {e}") from e
    # The pulse commits this pair atomically only after its corpus writes.
    # Updating after the full page also makes a direct failed call retry-safe.
    for refusal in staged_refusals:
        _queue_source_entry_refusal(cursors, refusal)
    _set_worldline_cursor(cursors, next_created, next_event)
    return evs


def sense_pacman(cursors):
    evs = []
    records = tail_line_records(
        "/var/log/pacman.log", cursors, "pacman.off")
    for _generation, _ordinal, line in records:
        m = PACMAN_RE.match(line)
        if not m:
            continue
        stamp, act, name = m.group(1), m.group(2), m.group(3)
        try:
            ts = datetime.datetime.fromisoformat(stamp).astimezone(datetime.timezone.utc)
        except Exception:
            ts = utcnow()
        package_slug = "packages/" + _source_entity_token(name, "package")
        occurrence = "pacman:" + hashlib.sha256(
            line.encode("utf-8")).hexdigest()
        evs.append(Event(
            "pacman", ts, act, f"{act}: {name}",
            {"organs/pacman", package_slug}, {"pacman", act},
            occurrence=occurrence))
    return evs


def _journal_unlink_tmp(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _journal_file_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _journal_create_tmp(tmp, raw):
    descriptor = os.open(
        tmp,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        remaining = memoryview(raw)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("short journal cursor write")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _journal_seed_cursor(cursor_file, tmp):
    """Copy an existing cursor without links, unbounded reads, or races."""
    try:
        source_fd = _open_source_nofollow(cursor_file, os.O_RDONLY)
    except FileNotFoundError:
        # journalctl documents that an empty cursor file falls back to the
        # other selection options. Seed it ourselves because a successful
        # empty query has no last row and therefore may create no file.
        _journal_create_tmp(tmp, b"")
        try:
            _source_path_identity(cursor_file, os.O_RDONLY)
        except FileNotFoundError:
            return
        raise RuntimeError("journal cursor appeared while baselining")
    try:
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_size > MAX_JOURNAL_CURSOR_BYTES:
            raise RuntimeError(
                "journal cursor is not a bounded owned regular file")
        raw = bytearray()
        while len(raw) <= MAX_JOURNAL_CURSOR_BYTES:
            request = min(MAX_JOURNAL_READ_BYTES,
                          MAX_JOURNAL_CURSOR_BYTES + 1 - len(raw))
            block = os.read(source_fd, request)
            if not block:
                break
            raw.extend(block)
        after = os.fstat(source_fd)
    finally:
        os.close(source_fd)
    try:
        target = _source_path_identity(cursor_file, os.O_RDONLY)
    except FileNotFoundError as exc:
        raise RuntimeError("journal cursor changed while copied") from exc
    if len(raw) > MAX_JOURNAL_CURSOR_BYTES \
            or _journal_file_identity(before) != _journal_file_identity(after) \
            or _journal_file_identity(before) != _journal_file_identity(target):
        raise RuntimeError("journal cursor changed while copied or exceeds its bound")
    _journal_create_tmp(tmp, raw)
    try:
        target = _source_path_identity(cursor_file, os.O_RDONLY)
    except FileNotFoundError as exc:
        raise RuntimeError("journal cursor changed while copied") from exc
    if _journal_file_identity(before) != _journal_file_identity(target):
        raise RuntimeError("journal cursor changed while copied")


def _await_process_exit_unreaped(process, deadline, command, timeout):
    """Wait for leader exit through pidfd while preserving its PID/PGID."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(command, timeout)
    try:
        pidfd = os.pidfd_open(process.pid, 0)
    except (AttributeError, OSError) as exc:
        raise RuntimeError(
            "bounded subprocess cannot establish a stable process identity") \
            from exc
    watcher = selectors.DefaultSelector()
    try:
        watcher.register(pidfd, selectors.EVENT_READ)
        if not watcher.select(remaining):
            raise subprocess.TimeoutExpired(command, timeout)
    finally:
        watcher.close()
        os.close(pidfd)


def _signal_and_reap_process_group(process, timeout):
    """Signal a still-identity-bound process group, then reap its leader."""
    if process is None:
        return None
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            process.kill()
        except OSError:
            pass
    try:
        returncode = process.wait(timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        returncode = None
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
    return returncode


def _journal_abort_process(process):
    """Stop a producer group without letting pipe backpressure hang it."""
    return _signal_and_reap_process_group(
        process, JOURNAL_TIMEOUT_SECONDS)


def _journalctl_records(cmd, *, record_limit=None, output_limit=None):
    """Stream complete JSONL records under byte, row, and time ceilings."""
    record_limit = (MAX_JOURNAL_RECORD_BYTES if record_limit is None
                    else record_limit)
    output_limit = (MAX_JOURNAL_OUTPUT_BYTES if output_limit is None
                    else output_limit)
    if any(isinstance(value, bool) or not isinstance(value, int)
           or value <= 0 or value > MAX_STATE_JSON_BYTES
           for value in (record_limit, output_limit)):
        raise ValueError("journalctl record limits are invalid")
    process = None
    selector = selectors.DefaultSelector()
    try:
        process = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=False, close_fds=True,
            start_new_session=True)
        if process.stdout is None or process.stderr is None:
            raise RuntimeError("journalctl did not provide bounded pipes")
        for stream, label in ((process.stdout, "stdout"),
                              (process.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)
        deadline = time.monotonic() + JOURNAL_TIMEOUT_SECONDS
        records = []
        record = bytearray()
        stderr = bytearray()
        stderr_truncated = False
        output_bytes = 0
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("journalctl timed out; cursor retained")
            ready = selector.select(remaining)
            if not ready:
                continue
            for key, _events in ready:
                stream = key.fileobj
                try:
                    block = os.read(stream.fileno(), MAX_JOURNAL_READ_BYTES)
                except BlockingIOError:
                    continue
                if not block:
                    selector.unregister(stream)
                    stream.close()
                    continue
                if key.data == "stderr":
                    available = MAX_JOURNAL_STDERR_BYTES - len(stderr)
                    if available > 0:
                        stderr.extend(block[:available])
                    if len(block) > available:
                        stderr_truncated = True
                    continue
                output_bytes += len(block)
                if output_bytes > output_limit:
                    raise RuntimeError(
                        "journalctl output exceeds aggregate byte bound; "
                        "cursor retained")
                record.extend(block)
                while True:
                    newline = record.find(b"\n")
                    if newline < 0:
                        if len(record) > record_limit:
                            raise RuntimeError(
                                "journalctl record exceeds byte bound; "
                                "cursor retained")
                        break
                    if newline > record_limit:
                        raise RuntimeError(
                            "journalctl record exceeds byte bound; "
                            "cursor retained")
                    line = bytes(record[:newline])
                    del record[:newline + 1]
                    if not line.strip():
                        continue
                    if len(records) >= MAX_JOURNAL_RECORDS:
                        raise RuntimeError(
                            "journalctl output exceeds record bound; "
                            "cursor retained")
                    try:
                        records.append(json.loads(line))
                    except (UnicodeError, ValueError, RecursionError) as exc:
                        raise RuntimeError(
                            "journalctl returned malformed JSON; "
                            "cursor retained") from exc
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("journalctl timed out; cursor retained")
        try:
            _await_process_exit_unreaped(
                process, deadline, cmd, JOURNAL_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("journalctl timed out; cursor retained") from exc
        returncode = _journal_abort_process(process)
        process = None
        if returncode is None:
            raise RuntimeError("journalctl timed out; cursor retained")
        if returncode != 0:
            try:
                detail = stderr.decode("utf-8", errors="strict")[-240:] \
                    or "journalctl failed"
            except UnicodeError:
                detail = "journalctl stderr is not valid UTF-8"
            if stderr_truncated:
                detail = "[stderr truncated] " + detail
            raise RuntimeError(
                f"journalctl refused cursor advance: {detail}")
        if record:
            raise RuntimeError(
                "journalctl returned unterminated JSON; cursor retained")
        return records
    finally:
        selector.close()
        # Cleanup is unconditional: the direct parent may have exited after a
        # descendant inherited or deliberately closed both output pipes.
        _journal_abort_process(process)


def _journal_catalog_cursor(record):
    if not isinstance(record, dict):
        raise RuntimeError("journal cursor catalog row is not an object")
    cursor = record.get("__CURSOR")
    if not isinstance(cursor, str) or not cursor \
            or len(cursor.encode("utf-8")) > MAX_JOURNAL_CURSOR_BYTES \
            or re.fullmatch(r"[\x21-\x7e]+", cursor) is None:
        raise RuntimeError("journal cursor catalog row is invalid")
    return cursor


def _journal_refusal(scope, cursor, ordinal, observed_bytes,
                     record_sha256, reason, complete):
    row = {
        "schema": "sia-journal-record-refusal-v1",
        "key": "journal." + scope, "scope": scope, "cursor": cursor,
        "cursor_sha256": hashlib.sha256(cursor.encode("utf-8")).hexdigest(),
        "ordinal": ordinal, "observed_bytes": observed_bytes,
        "record_sha256": record_sha256, "reason": reason,
        "complete": complete,
    }
    probe = {SOURCE_RECORD_REFUSALS_KEY: [row]}
    if _take_source_record_refusals(probe) != [row]:
        raise RuntimeError("journal refusal could not be validated")
    return row


def _journal_require_exact_cursor(cursor, scope):
    """Rebind a poison row to its source cursor after journal churn.

    A prior catalog only establishes order at catalog time.  If the journal is
    vacuumed before the full pass, an over-bound row cannot expose its own
    cursor for the usual equality check.  Re-query that exact catalog cursor
    and require journalctl to return it before signing a refusal.
    """
    cmd = [
        "journalctl", "-o", "json", "--output-fields=__CURSOR",
        "--no-pager", f"--cursor={cursor}", "-n", "1",
    ]
    if scope == "user":
        cmd.append("--user")
    rows = _journalctl_records(
        cmd,
        # Independent from the full MESSAGE row cap: tests and operators may
        # tighten that cap below the small JSON wrapper around a valid cursor.
        record_limit=MAX_SOURCE_TAIL_BYTES,
        output_limit=MAX_STATE_JSON_BYTES)
    if len(rows) != 1 or _journal_catalog_cursor(rows[0]) != cursor:
        raise RuntimeError(
            "journal poison cursor changed after cursor catalog")


def _journalctl_projected_records(cmd, catalog, scope):
    """Bind bounded full JSON rows to a prior ordered cursor catalog."""
    if scope not in {"sys", "user"} \
            or not isinstance(catalog, list) \
            or len(catalog) > MAX_JOURNAL_RECORDS:
        raise ValueError("journal projected record request is invalid")
    process = None
    selector = selectors.DefaultSelector()
    group_reaped = False
    try:
        process = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=False, close_fds=True,
            start_new_session=True)
        if process.stdout is None or process.stderr is None:
            raise RuntimeError("journalctl did not provide bounded pipes")
        for stream, label in ((process.stdout, "stdout"),
                              (process.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)
        deadline = time.monotonic() + JOURNAL_TIMEOUT_SECONDS
        records = []
        refusals = []
        stderr = bytearray()
        current = bytearray()
        current_hash = hashlib.sha256()
        current_bytes = 0
        admitted_bytes = 0
        ordinal = 0
        stopped = False
        while selector.get_map() and not stopped:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("journalctl timed out; cursor retained")
            ready = selector.select(remaining)
            if not ready:
                continue
            for key, _events in ready:
                stream = key.fileobj
                try:
                    block = os.read(stream.fileno(), MAX_JOURNAL_READ_BYTES)
                except BlockingIOError:
                    continue
                if not block:
                    selector.unregister(stream)
                    stream.close()
                    continue
                if key.data == "stderr":
                    available = MAX_JOURNAL_STDERR_BYTES - len(stderr)
                    if available > 0:
                        stderr.extend(block[:available])
                    continue
                for value in block:
                    if ordinal >= len(catalog):
                        raise RuntimeError(
                            "journal snapshot changed after cursor catalog")
                    byte = bytes((value,))
                    current_hash.update(byte)
                    current_bytes += 1
                    if len(current) <= MAX_JOURNAL_RECORD_BYTES:
                        current.extend(byte)
                    if admitted_bytes + current_bytes \
                            > MAX_JOURNAL_OUTPUT_BYTES:
                        if admitted_bytes:
                            stopped = True
                            break
                        _journal_require_exact_cursor(
                            catalog[ordinal], scope)
                        refusals.append(_journal_refusal(
                            scope, catalog[ordinal], ordinal, current_bytes,
                            current_hash.hexdigest(),
                            "journal-record-over-aggregate", False))
                        ordinal += 1
                        stopped = True
                        break
                    if value != 0x0A:
                        continue
                    cursor = catalog[ordinal]
                    digest = current_hash.hexdigest()
                    row_bytes = current_bytes
                    raw = bytes(current[:-1])
                    reason = None
                    parsed = None
                    if row_bytes > MAX_JOURNAL_RECORD_BYTES:
                        reason = "journal-record-over-bound"
                    else:
                        try:
                            parsed = json.loads(raw.decode(
                                "utf-8", errors="strict"))
                        except (UnicodeError, ValueError, RecursionError):
                            reason = "journal-record-malformed"
                        if reason is None and not isinstance(parsed, dict):
                            reason = "journal-record-non-object"
                        if reason is None \
                                and parsed.get("__CURSOR") != cursor:
                            raise RuntimeError(
                                "journal snapshot changed after cursor catalog")
                    if reason is not None:
                        _journal_require_exact_cursor(cursor, scope)
                        refusals.append(_journal_refusal(
                            scope, cursor, ordinal, row_bytes, digest,
                            reason, True))
                        ordinal += 1
                        stopped = True
                        break
                    records.append(parsed)
                    admitted_bytes += row_bytes
                    ordinal += 1
                    current.clear()
                    current_hash = hashlib.sha256()
                    current_bytes = 0
                if stopped:
                    break
        if stopped:
            returncode = _journal_abort_process(process)
            process = None
            group_reaped = True
            if returncode is None:
                raise RuntimeError("journalctl timed out; cursor retained")
        else:
            _await_process_exit_unreaped(
                process, deadline, cmd, JOURNAL_TIMEOUT_SECONDS)
            returncode = _journal_abort_process(process)
            process = None
            group_reaped = True
            if returncode is None:
                raise RuntimeError("journalctl timed out; cursor retained")
            if returncode != 0:
                try:
                    detail = stderr.decode(
                        "utf-8", errors="strict")[-240:] \
                        or "journalctl failed"
                except UnicodeError:
                    detail = "journalctl stderr is not valid UTF-8"
                raise RuntimeError(
                    f"journalctl refused cursor advance: {detail}")
            if current_bytes:
                raise RuntimeError(
                    "journalctl returned unterminated JSON; cursor retained")
            if ordinal != len(catalog):
                raise RuntimeError(
                    "journal snapshot changed after cursor catalog")
        return records, refusals, ordinal
    finally:
        selector.close()
        if process is not None and not group_reaped:
            _journal_abort_process(process)


def _journalctl(args, cursor_file, *, metadata_only=False, scope="sys"):
    tmp = cursor_file + ".pulse"
    catalog_tmp = tmp + ".catalog"
    full_tmp = tmp + ".full"
    temporary = (tmp, catalog_tmp, full_tmp)
    try:
        for target in temporary:
            try:
                tmp_info = os.lstat(target)
            except FileNotFoundError:
                continue
            if not (stat.S_ISREG(tmp_info.st_mode)
                    or stat.S_ISLNK(tmp_info.st_mode)):
                raise RuntimeError("journal temporary cursor is not a file")
            os.unlink(target)
        _journal_seed_cursor(cursor_file, catalog_tmp)
        catalog_cmd = [
            "journalctl", "-o", "json", "--output-fields=__CURSOR",
            "--no-pager", f"--cursor-file={catalog_tmp}"] + args
        catalog_rows = _journalctl_records(
            catalog_cmd, record_limit=MAX_JOURNAL_CURSOR_BYTES,
            output_limit=MAX_STATE_JSON_BYTES)
        catalog = [_journal_catalog_cursor(row) for row in catalog_rows]
        if len(catalog) != len(set(catalog)):
            raise RuntimeError("journal cursor catalog repeats an entry")

        out, refusals, processed = [], [], len(catalog)
        if not metadata_only and catalog:
            _journal_seed_cursor(cursor_file, full_tmp)
            full_cmd = ["journalctl", "-o", "json", "--no-pager",
                        f"--cursor-file={full_tmp}"] + args
            out, refusals, processed = _journalctl_projected_records(
                full_cmd, catalog, scope)

        # The source cursor is selected from the verified catalog prefix, not
        # from either producer-owned cursor file (which may have run ahead).
        _journal_seed_cursor(cursor_file, tmp)
        if processed:
            _journal_unlink_tmp(tmp)
            _journal_create_tmp(tmp, catalog[processed - 1].encode("utf-8"))
        descriptor = _open_source_nofollow(tmp, os.O_RDONLY)
        try:
            info = os.fstat(descriptor)
            target = _source_path_identity(tmp, os.O_RDONLY)
            if not stat.S_ISREG(info.st_mode) \
                    or info.st_uid != os.geteuid() \
                    or info.st_size > MAX_JOURNAL_CURSOR_BYTES \
                    or _journal_file_identity(info) \
                    != _journal_file_identity(target):
                raise RuntimeError(
                    "journalctl produced an unsafe cursor file")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("journalctl produced an unsafe cursor file")
    except Exception:
        for target in temporary:
            _journal_unlink_tmp(target)
        raise
    _journal_unlink_tmp(catalog_tmp)
    _journal_unlink_tmp(full_tmp)
    return out, (tmp, cursor_file), refusals


def _journal_msg(msg):
    """journalctl -o json MESSAGE can be a string, an array of ints (non-UTF8),
    or an array of strings/arrays (multiple MESSAGE= fields)."""
    try:
        if isinstance(msg, str):
            return msg
        if isinstance(msg, list):
            if msg and all(isinstance(x, int) for x in msg):
                return bytes(msg).decode(errors="replace")
            return " | ".join(_journal_msg(m) for m in msg)
    except Exception:
        pass
    return str(msg)


def sense_journal(cursors):
    evs = []
    pending = []
    refusals = []
    try:
        for scope, extra in (("sys", []), ("user", ["--user"])):
            cfile = os.path.join(STATE, f"journal-{scope}.cursor")
            first = not os.path.lexists(cfile)
            if first:
                _records, cursor, _refused = _journalctl(
                    extra + ["-n", "1"], cfile,
                    metadata_only=True, scope=scope)
                pending.append(cursor)
                continue
            recs, cursor, refused = _journalctl(
                extra + ["-p", "err..alert", "-n", "+300"], cfile,
                scope=scope)
            pending.append(cursor)
            refusals.extend(refused)
            for record in recs:
                if not isinstance(record, dict):
                    raise RuntimeError(
                        "journalctl JSON record is not an object")
                unit = record.get("_SYSTEMD_UNIT") or record.get("UNIT") \
                    or record.get("SYSLOG_IDENTIFIER") or "kernel"
                msg = _journal_msg(record.get("MESSAGE", ""))
                raw_unit = str(unit).replace(
                    ".service", "").split("@")[0]
                u = _source_entity_token(raw_unit, "unit")
                tags = {"journal", "journal-error"}
                if "coredump" in str(unit) or "core dumped" in msg:
                    tags.add("coredump")
                source_cursor = record.get("__CURSOR")
                if not isinstance(source_cursor, str) or not source_cursor:
                    source_cursor = hashlib.sha256(json.dumps(
                        record, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False, default=str).encode(
                            "utf-8")).hexdigest()
                evs.append(Event(
                    "journal", utcnow(), "error",
                    f"{unit}: {clip(msg, 100)}",
                    {"organs/journal", f"units/{u}"}, tags,
                    occurrence=f"journal:{scope}:{source_cursor}"))
    except Exception:
        for tmp, _real in pending:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise
    if refusals:
        queued = cursors.setdefault(SOURCE_RECORD_REFUSALS_KEY, [])
        if not isinstance(queued, list) \
                or len(queued) + len(refusals) \
                > MAX_LEDGER_PENDING_RECORDS:
            for tmp, _real in pending:
                _journal_unlink_tmp(tmp)
            raise ValueError("source record refusal state exceeds its bound")
        queued.extend(refusals)
    PENDING_CURSOR_RENAMES.extend(pending)
    return evs


def sense_guardian(cursors):
    evs = []
    base = os.path.join(HOME, ".local/state/omarchy-guardian")
    for sub, label in (("checkpoints", "checkpoint"), ("plans", "plan"),
                       ("transactions", "transaction")):
        d = os.path.join(base, sub)
        key = f"guardian.{sub}"
        page_key = f"{key}.page"
        page_before = cursors.get(page_key)
        began_at_start = page_before is None or (
            isinstance(page_before, dict)
            and page_before.get("cookie", 0) == 0)
        try:
            entries, complete, _inspected, next_page = \
                _bounded_source_entries(d, page_before)
        except FileNotFoundError:
            cursors.pop(page_key, None)
            continue
        cursors[page_key] = next_page
        names = [entry["name"] for entry in entries
                 if not entry["name"].endswith(".applied")]
        seen = _bounded_seen_names(cursors.get(key))
        if seen is None:
            seen = []
            cursors[f"{key}.baselining"] = True
        baselining = bool(cursors.get(f"{key}.baselining", False))
        seen_set = set(seen)
        for name in names:
            if name in seen_set:
                continue
            if len(seen) >= MAX_SOURCE_SCAN_ENTRIES:
                evs.append(_source_entry_refusal_event(
                    "guardian", f"guardian {label} {name}"))
                continue
            if not baselining:
                token = _source_entity_token(name, f"guardian-{sub}")
                evs.append(Event("guardian", utcnow(), label,
                                 f"new {label}: {clip(name, 40)}",
                                 {"organs/guardian"}, {"guardian"},
                                 occurrence=(f"guardian:{sub}:"
                                             f"{token}")))
            seen.append(name)
            seen_set.add(name)
        cursors[key] = (sorted(names) if complete and began_at_start
                        else sorted(seen))
        if complete and baselining:
            cursors[f"{key}.baselining"] = False
    return evs


def sense_git(cursors):
    evs = []
    projects = os.path.join(HOME, "Projects")
    page_key = "source.git.projects.page"
    page_before = cursors.get(page_key)
    began_at_start = page_before is None or (
        isinstance(page_before, dict) and page_before.get("cookie", 0) == 0)
    try:
        entries, complete, _inspected, next_page = _bounded_source_entries(
            projects, page_before, MAX_CONFIG_TAGS)
    except FileNotFoundError:
        cursors.pop(page_key, None)
        return evs
    cursors[page_key] = next_page
    directory_reset = bool(next_page.get("reset", False))
    repos = [entry for entry in entries if stat.S_ISDIR(entry["mode"])]
    cycle_value = cursors.get("source.git.cycle")
    if began_at_start or directory_reset:
        cycle_live = []
        # A changed directory generation invalidates the preceding cookie
        # cycle.  Complete this restarted scan for visibility, but only the
        # next unchanged root-to-EOF cycle may prove deletion.
        cycle_coverage = not directory_reset
    else:
        if not isinstance(cycle_value, dict) \
                or not isinstance(cycle_value.get("coverage"), bool):
            cycle_live = []
            cycle_coverage = False
        else:
            cycle_live = _bounded_seen_names(cycle_value.get("live")) or []
            cycle_coverage = cycle_value["coverage"]
    cycle_live_set = set(cycle_live)
    admitted = _bounded_seen_names(cursors.get("source.git.repositories"))
    if admitted is None:
        admitted = []
    admitted_set = set(admitted)
    metadata_suffixes = (
        ".cursor_v", ".generation", ".offset", ".device", ".inode",
        ".head_bytes", ".head_sha256", ".prefix_sha256",
        ".overbound_skip")
    for entry in repos:
        repo = entry["name"]
        repo_id = _source_entity_token(repo, "project")
        repo_git = os.path.join(projects, repo, ".git")
        try:
            if not _nofollow_source_directory(repo_git):
                continue
        except Exception:
            cycle_coverage = False
            evs.append(_source_entry_refusal_event(
                "projects", f"project repository {repo}"))
            continue
        if repo_id not in cycle_live_set:
            if len(cycle_live) >= MAX_SOURCE_SCAN_ENTRIES:
                cycle_coverage = False
                evs.append(_source_entry_refusal_event(
                    "projects", f"project repository {repo}"))
                continue
            cycle_live.append(repo_id)
            cycle_live_set.add(repo_id)
        if repo_id not in admitted_set:
            if len(admitted) >= MAX_SOURCE_SCAN_ENTRIES:
                evs.append(_source_entry_refusal_event(
                    "projects", f"project repository {repo}"))
                continue
            admitted.append(repo_id)
            admitted_set.add(repo_id)
        head_log = os.path.join(repo_git, "logs/HEAD")
        key = f"git.{repo_id}"
        slug = "projects/" + repo_id
        try:
            records = tail_line_records(head_log, cursors, key)
        except Exception:
            evs.append(_source_entry_refusal_event(
                "projects", f"project history {repo}"))
            continue
        for generation, ordinal, line in records:
            if "\t" not in line:
                continue
            meta, msg = line.split("\t", 1)
            if msg.startswith("commit"):
                subj = msg.split(":", 1)[1].strip() if ":" in msg else msg
                evs.append(Event("projects", utcnow(), "commit",
                                 f"[[{slug}|{repo}]]: {clip(subj, 70)}",
                                 {"organs/projects", slug}, {"git", "commit"},
                                 occurrence=(f"git:{repo_id}:{generation}:"
                                             f"{ordinal}")))
    if complete and cycle_coverage:
        admitted = [repo_id for repo_id in admitted
                    if repo_id in cycle_live_set]
        for key in [k for k in cursors
                    if k.startswith("git.")
                    and not k.endswith(metadata_suffixes)]:
            if key[4:] not in cycle_live_set:
                del cursors[key]
                cursors.pop(f"{key}.generation", None)
        for key in [k for k in cursors
                    if k.startswith("git.") and k.endswith(
                        metadata_suffixes)]:
            suffix = next(value for value in metadata_suffixes
                          if key.endswith(value))
            base_key = key[:-len(suffix)]
            if base_key not in cursors:
                del cursors[key]
    if complete:
        cursors.pop("source.git.cycle", None)
    else:
        cursors["source.git.cycle"] = {
            "live": sorted(cycle_live), "coverage": cycle_coverage}
    cursors["source.git.repositories"] = sorted(admitted)
    return evs


def sense_claude(cursors):
    """Claude sessions from filesystem metadata only; payloads are unopened."""
    evs = []
    sessions, state_truncated = _bounded_source_state(
        cursors, "claude.sessions", "claude-session")
    if state_truncated:
        evs.append(_source_truncation_event(
            "claude-code", "Claude session cursor"))
    files, complete_snapshot, refused, snapshot_generation = \
        _bounded_source_tree_files(
        os.path.join(HOME, ".claude/projects"), cursors,
        "source.claude.tree", 1, ".jsonl")
    for relative in refused:
        evs.append(_source_entry_refusal_event(
            "claude-code", f"Claude session path {relative}"))
    for source in files:
        f = source["path"]
        sid_raw = os.path.basename(f)[:-6]
        sid = _source_entity_token(sid_raw, "claude-session")
        st = sessions.get(sid)
        size = source["size"]
        if st is None and len(sessions) >= MAX_SOURCE_SCAN_ENTRIES:
            evs.append(_source_entry_refusal_event(
                "claude-code", f"Claude session {sid_raw}"))
            continue
        if st is None:
            # first sighting: only announce if the file is fresh (< 1 h old)
            fresh = (time.time() - source["mtime"]) < 3600
            sessions[sid] = {"size": size, "announced": fresh,
                             "generation": 0,
                             "snapshot_generation": snapshot_generation}
            if fresh:
                evs.append(Event("claude-code", utcnow(), "session",
                                 f"new agent session {clip(sid_raw, 8)}…",
                                 {"organs/claude-code"}, {"claude-code"},
                                 occurrence=f"claude:{sid}:0:new:{size}"))
            continue
        previous_size = st.get("size", st.get("off", size))
        generation = st.get("generation", 0)
        if isinstance(generation, bool) or not isinstance(generation, int) \
                or generation < 0:
            raise ValueError("Claude session generation is invalid")
        if size <= previous_size:
            if size < previous_size:
                generation += 1
            was_announced = bool(st.get("announced", False))
            st.clear()
            st.update({"size": size,
                       "announced": was_announced,
                       "generation": generation,
                       "snapshot_generation": snapshot_generation})
            continue
        was_announced = bool(st.get("announced"))
        st.clear()
        st.update({"size": size, "announced": True,
                   "generation": generation,
                   "snapshot_generation": snapshot_generation})
        if not was_announced:
            # an old session woke up after we first saw it — start reporting
            evs.append(Event("claude-code", utcnow(), "session",
                             f"agent session {clip(sid_raw, 8)}… resumed",
                             {"organs/claude-code"}, {"claude-code"},
                             occurrence=(f"claude:{sid}:{generation}:"
                                         f"resume:{size}")))
        else:
            evs.append(Event("claude-code", utcnow(), "activity",
                             f"agent session {clip(sid_raw, 8)}… active",
                             {"organs/claude-code"}, {"claude-code"},
                             occurrence=(f"claude:{sid}:{generation}:"
                                         f"activity:{size}")))
    # Only a complete unchanged and refusal-free root-to-EOF generation
    # proves absence. Earlier pages mark their rows with this same durable
    # generation, so a bounded multi-pulse snapshot can prune exactly once.
    if complete_snapshot:
        for sid in list(sessions):
            if sessions[sid].get("snapshot_generation") \
                    != snapshot_generation:
                del sessions[sid]
    return evs


def sense_codex(cursors):
    """Codex CLI sessions — metadata only (existence, growth), never
    payload bodies. Dated tree: ~/.codex/sessions/YYYY/MM/DD/*.jsonl.
    Closes the coverage gap where MCP advertised Codex but only Claude
    was a first-class session organ."""
    evs = []
    sessions, state_truncated = _bounded_source_state(
        cursors, "codex.sessions", "codex-session")
    if state_truncated:
        evs.append(_source_truncation_event("codex", "Codex session cursor"))
    files, complete_snapshot, refused, snapshot_generation = \
        _bounded_source_tree_files(
        os.path.join(HOME, ".codex/sessions"), cursors,
        "source.codex.tree", 3, ".jsonl")
    for relative in refused:
        evs.append(_source_entry_refusal_event(
            "codex", f"Codex session path {relative}"))
    for source in files:
        f = source["path"]
        sid_raw = os.path.basename(f).replace("rollout-", "")[:-6]
        sid = _source_entity_token(sid_raw, "codex-session")
        size = source["size"]
        st = sessions.get(sid)
        if st is None and len(sessions) >= MAX_SOURCE_SCAN_ENTRIES:
            evs.append(_source_entry_refusal_event(
                "codex", f"Codex session {sid_raw}"))
            continue
        if st is None:
            fresh = (time.time() - source["mtime"]) < 3600
            sessions[sid] = {"size": size, "announced": fresh,
                             "generation": 0,
                             "snapshot_generation": snapshot_generation}
            if fresh:
                evs.append(Event("codex", utcnow(), "session",
                                 f"new Codex session {clip(sid_raw, 8)}…",
                                 {"organs/codex"}, {"codex"},
                                 occurrence=f"codex:{sid}:0:new:{size}"))
            continue
        generation = st.get("generation", 0)
        if isinstance(generation, bool) or not isinstance(generation, int) \
                or generation < 0:
            raise ValueError("Codex session generation is invalid")
        if size < st["size"]:
            st["size"] = size
            st["generation"] = generation + 1
            st["snapshot_generation"] = snapshot_generation
            continue
        if size > st["size"] and st.get("announced"):
            evs.append(Event("codex", utcnow(), "activity",
                             f"Codex session {clip(sid_raw, 8)}… active",
                             {"organs/codex"}, {"codex"},
                             occurrence=(f"codex:{sid}:{generation}:"
                                         f"activity:{size}")))
        elif size > st["size"] and not st.get("announced"):
            st["announced"] = True
            evs.append(Event("codex", utcnow(), "session",
                             f"Codex session {clip(sid_raw, 8)}… resumed",
                             {"organs/codex"}, {"codex"},
                             occurrence=(f"codex:{sid}:{generation}:"
                                         f"resume:{size}")))
        st["size"] = size
        st["generation"] = generation
        st["snapshot_generation"] = snapshot_generation
    if complete_snapshot:
        for sid in list(sessions):
            if sessions[sid].get("snapshot_generation") \
                    != snapshot_generation:
                del sessions[sid]
    return evs


def sense_notify(cursors):
    evs = []
    d = os.path.join(HOME, ".local/state/omarchy/notifications/history")
    pending = _bounded_seen_names(cursors.get("notify.pending"))
    if pending:
        names = pending
        complete = bool(cursors.get("notify.pending_complete", False))
        paginated = True
    else:
        cursors.pop("notify.pending", None)
        cursors.pop("notify.pending_complete", None)
        page_key = "source.notify.page"
        page_before = cursors.get(page_key)
        began_at_start = page_before is None or (
            isinstance(page_before, dict)
            and page_before.get("cookie", 0) == 0)
        try:
            entries, complete, _inspected, next_page = \
                _bounded_source_entries(d, page_before)
        except FileNotFoundError:
            cursors.pop(page_key, None)
            return evs
        cursors[page_key] = next_page
        names = [entry["name"] for entry in entries
                 if stat.S_ISREG(entry["mode"])]
        paginated = bool(cursors.get("notify.paginated", False)) \
            or not (complete and began_at_start)

    def append_notification(name):
        try:
            record = _read_bounded_source_json(
                os.path.join(d, name), f"notification record {name}")
            app = record.get("app") or "app"
            summary = clip(record.get("summary", ""), 80)
        except Exception:
            evs.append(_source_entry_refusal_event(
                "notify", f"notification record {name}"))
            return
        token = _source_entity_token(name, "notification")
        evs.append(Event(
            "notify", utcnow(), "notification",
            f"{app}" + (f": {summary}" if summary else ""),
            {"organs/notify"}, {"notification"},
            occurrence=f"notification:{token}"))

    last = cursors.get("notify.last")
    if last is not None and not isinstance(last, str):
        raise ValueError("notification cursor is invalid")
    if not paginated:
        if last is None:
            cursors["notify.last"] = names[-1] if names else ""
            return evs
        new = [name for name in names if name > last]
        batch = new[:100]
        for name in batch:
            append_notification(name)
        if batch:
            cursors["notify.last"] = batch[-1]
        return evs

    cursors["notify.paginated"] = True
    if last is None:
        last = ""
        cursors["notify.last"] = last
        cursors["notify.baselining"] = True
    baselining = bool(cursors.get("notify.baselining", False))
    seen = _bounded_seen_names(cursors.get("notify.seen")) or []
    seen_set = set(seen)
    cycle_max = cursors.get("notify.cycle_max", "")
    if not isinstance(cycle_max, str):
        raise ValueError("notification page cursor is invalid")
    candidates = [name for name in names if name > last]
    batch = candidates[:100]
    remainder = candidates[100:]
    for name in batch:
        cycle_max = max(cycle_max, name)
        if name in seen_set:
            continue
        if len(seen) >= MAX_SOURCE_SCAN_ENTRIES:
            evs.append(_source_entry_refusal_event(
                "notify", f"notification record {name}"))
            continue
        if not baselining:
            append_notification(name)
        seen.append(name)
        seen_set.add(name)
    cursors["notify.seen"] = sorted(seen)
    cursors["notify.cycle_max"] = cycle_max
    if remainder:
        cursors["notify.pending"] = remainder
        cursors["notify.pending_complete"] = complete
    else:
        cursors.pop("notify.pending", None)
        cursors.pop("notify.pending_complete", None)
        if complete:
            cursors["notify.last"] = max(last, cycle_max)
            cursors["notify.cycle_max"] = ""
            if baselining:
                cursors["notify.baselining"] = False
    return evs


def sense_agents(cursors):
    """Omarchy Quattro agents-usage records: authoritative per-agent token
    spend + rate-limit pressure (~/.local/state/omarchy/agents/usage/)."""
    evs = []
    d = os.path.join(HOME, ".local/state/omarchy/agents/usage")
    state, state_truncated = _bounded_source_state(
        cursors, "agents.state", "agent")
    if state_truncated:
        evs.append(_source_truncation_event("agents", "agent usage cursor"))
    page_key = "source.agents.page"
    try:
        entries, _complete, _inspected, next_page = _bounded_source_entries(
            d, cursors.get(page_key), MAX_CONFIG_TAGS)
    except FileNotFoundError:
        cursors.pop(page_key, None)
        return evs
    cursors[page_key] = next_page
    names = [entry["name"] for entry in entries
             if stat.S_ISREG(entry["mode"])
             and entry["name"].endswith(".json")]
    for n in names:
        try:
            j = _read_bounded_source_json(
                os.path.join(d, n), f"agent usage record {n}")
        except Exception:
            evs.append(_source_entry_refusal_event(
                "agents", f"agent usage record {n}"))
            continue
        aid_raw = str(j.get("id") or n[:-5])
        aid = _source_entity_token(aid_raw, "agent")
        prev = state.get(aid, {})
        if not isinstance(prev, dict):
            raise ValueError("agent usage cursor is invalid")
        if not prev and aid not in state \
                and len(state) >= MAX_SOURCE_SCAN_ENTRIES:
            evs.append(_source_entry_refusal_event(
                "agents", f"agent usage identity {aid_raw}"))
            continue

        def _pct(v):
            try:
                f = float(v)
                if not math.isfinite(f):
                    return 0
                # collectors store fractions of 1.0; older ones use 0-100
                return int(round(f * 100)) if 0 <= f <= 1.0 \
                    else int(round(f))
            except (OverflowError, TypeError, ValueError):
                return 0

        try:
            tokens = int(j.get("todayTotalTokens") or 0)
        except (OverflowError, TypeError, ValueError):
            evs.append(_source_entry_refusal_event(
                "agents", f"agent usage record {n}"))
            continue
        source_limits = j.get("limits") or []
        if not isinstance(source_limits, list):
            source_limits = []
        limits = {}
        limits_truncated = len(source_limits) > MAX_CONFIG_TAGS
        for source_limit in source_limits[:MAX_CONFIG_TAGS]:
            if not isinstance(source_limit, dict):
                continue
            label = str(source_limit.get("label", ""))
            label_id = _source_entity_token(label, "agent-limit")
            limits[label_id] = {"label": label,
                                "percent": _pct(source_limit.get("percent"))}
        if limits_truncated:
            evs.append(_source_truncation_event(
                "agents", f"agent limit record {aid_raw}"))
        cur = {"tokens": tokens,
               "limits": {label_id: value["percent"]
                          for label_id, value in limits.items()}}
        generation = prev.get("generation", 0) if isinstance(prev, dict) else 0
        if isinstance(generation, bool) or not isinstance(generation, int) \
                or generation < 0:
            raise ValueError("agent usage generation is invalid")
        if prev and cur["tokens"] < prev.get("tokens", 0):
            generation += 1
        cur["generation"] = generation
        transition_id = hashlib.sha256(json.dumps(
            {"prior": prev, "current": cur},
            sort_keys=True, separators=(",", ":")).encode(
                "utf-8")).hexdigest()
        if prev:
            dtok = cur["tokens"] - prev.get("tokens", 0)
            if dtok > 500_000:
                evs.append(Event("agents", utcnow(), "usage",
                                 f"{clip(aid_raw, 40)}: +{dtok // 1000}k tokens today "
                                 f"({cur['tokens'] // 1000}k total)",
                                 {"organs/agents"}, {"agents"},
                                 occurrence=(f"agents:{aid}:usage:"
                                             f"{transition_id}")))
            for label_id, pct in cur["limits"].items():
                old = prev.get("limits", {}).get(label_id, pct)
                if pct >= old + 10:
                    tags = {"agents"}
                    if pct >= 90:
                        tags.add("urgent")
                    label = limits[label_id]["label"]
                    evs.append(Event("agents", utcnow(), "limit",
                                     f"{clip(aid_raw, 40)} "
                                     f"{clip(label, 30)} limit at "
                                     f"{pct}% (was {old}%)",
                                     {"organs/agents"}, tags,
                                     occurrence=(f"agents:{aid}:limit:"
                                                 f"{label_id}:"
                                                 f"{transition_id}")))
        state[aid] = cur
    return evs


def _configured_skill_roots():
    skills = CONFIG.get("skills", {})
    roots = skills.get("roots", DEFAULT_SKILL_ROOTS) \
        if isinstance(skills, dict) else DEFAULT_SKILL_ROOTS
    if not isinstance(roots, list) or len(roots) > MAX_CONFIG_TAGS \
            or any(not isinstance(root, str) or not root.strip()
                   or len(root) > MAX_CONFIG_PATH_CHARS for root in roots):
        roots = DEFAULT_SKILL_ROOTS
    return [os.path.join(HOME, root) for root in roots]




def _skill_manifest_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _skill_description_from_head(head):
    """Extract one bounded inert description from an admitted manifest head."""
    match = re.search(r"^description:\s*(.*)$", head, re.M)
    if not match:
        return ""
    value = match.group(1).strip().strip('"')
    if value in (">", ">-", "|", "|-", ""):
        lines = []
        for line in head[match.end():].splitlines()[1:]:
            if line[:1] in (" ", "\t"):
                lines.append(line.strip())
            elif line.strip():
                break
        value = " ".join(lines)
    return redact(clip(value, 220), "skills") if value else ""


def _read_skill_manifest(root, name):
    """Capture one stable directly-contained SKILL.md without symlinks."""
    if not isinstance(name, str) or not name or name in {".", ".."} \
            or os.sep in name or (os.altsep and os.altsep in name):
        raise OSError("skill name is not a direct child")
    directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                       | getattr(os, "O_NOFOLLOW", 0)
                       | getattr(os, "O_DIRECTORY", 0))
    root_fd = _open_source_nofollow(root, directory_flags)
    skill_fd = -1
    manifest_fd = -1
    try:
        root_before = os.fstat(root_fd)
        skill_fd = os.open(name, directory_flags, dir_fd=root_fd)
        skill_before = os.fstat(skill_fd)

        def containers_stable():
            skill_after = os.fstat(skill_fd)
            current_skill_fd = os.open(
                name, directory_flags, dir_fd=root_fd)
            try:
                current_skill = os.fstat(current_skill_fd)
            finally:
                os.close(current_skill_fd)
            root_after = os.fstat(root_fd)
            current_root = _source_path_identity(root, directory_flags)
            return _skill_manifest_identity(skill_before) == \
                _skill_manifest_identity(skill_after) == \
                _skill_manifest_identity(current_skill) \
                and _skill_manifest_identity(root_before) == \
                _skill_manifest_identity(root_after) == \
                _skill_manifest_identity(current_root)

        try:
            manifest_fd = os.open(
                "SKILL.md", os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0), dir_fd=skill_fd)
        except OSError as exc:
            try:
                stable_absence = containers_stable()
            except OSError:
                stable_absence = False
            if not stable_absence:
                raise RuntimeError(
                    "skill manifest path changed while inspected") from exc
            raise
        before = os.fstat(manifest_fd)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("skill manifest is not a regular file")
        captured = bytearray()
        while len(captured) <= MAX_SKILL_MANIFEST_HEAD_BYTES:
            request = MAX_SKILL_MANIFEST_HEAD_BYTES + 1 - len(captured)
            block = os.read(manifest_fd, request)
            if not block:
                break
            captured.extend(block)
        after = os.fstat(manifest_fd)

        try:
            current_manifest_fd = os.open(
                "SKILL.md", os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0), dir_fd=skill_fd)
        except OSError as exc:
            raise RuntimeError(
                "skill manifest path changed while captured") from exc
        try:
            current_manifest = os.fstat(current_manifest_fd)
        finally:
            os.close(current_manifest_fd)
        try:
            stable_containers = containers_stable()
        except OSError:
            stable_containers = False
        manifest_identity = _skill_manifest_identity(before)
        if manifest_identity != _skill_manifest_identity(after) \
                or manifest_identity \
                != _skill_manifest_identity(current_manifest) \
                or not stable_containers:
            raise RuntimeError("skill manifest changed while captured")
        head_raw = bytes(captured[:MAX_SKILL_MANIFEST_HEAD_BYTES])
        head = head_raw.decode("utf-8", errors="replace")
        return {
            "head": head,
            "description": _skill_description_from_head(head),
            "manifest": {
                "device": before.st_dev, "inode": before.st_ino,
                "mode": before.st_mode, "uid": before.st_uid,
                "size": before.st_size, "mtime_ns": before.st_mtime_ns,
                "ctime_ns": before.st_ctime_ns,
                "head_bytes": len(head_raw),
                "head_truncated": before.st_size > len(head_raw),
                "head_sha256": hashlib.sha256(head_raw).hexdigest(),
            },
        }
    finally:
        if manifest_fd >= 0:
            os.close(manifest_fd)
        if skill_fd >= 0:
            os.close(skill_fd)
        os.close(root_fd)


def _list_skill_entries(root):
    entries, complete, _inspected, page = _bounded_source_entries(
        root, limit=MAX_SKILL_SNAPSHOT_ENTRIES)
    return [entry["name"] for entry in entries], not complete, page


def _skill_name_bytes(name):
    """Canonical bytes for a live fs name or a legacy cursor label."""
    try:
        return os.fsencode(str(name))
    except UnicodeEncodeError:
        # A hand-edited/legacy JSON cursor can contain a non-surrogateescape
        # lone surrogate.  It is not a filesystem name, but still needs a
        # deterministic safe identity so recovery can replace it.
        return str(name).encode("utf-8", errors="backslashreplace")


def _skill_display_name(name):
    """Render arbitrary filesystem bytes as valid Unicode agent prose."""
    return _skill_name_bytes(name).decode("utf-8", errors="backslashreplace")


def _skill_root_generation_matches(root, generation):
    """Revalidate the exact root generation after reading its manifests."""
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_DIRECTORY", 0))
    descriptor = _open_source_nofollow(root, flags)
    try:
        before = os.fstat(descriptor)
        after = os.fstat(descriptor)
        current = _source_path_identity(root, flags)
    finally:
        os.close(descriptor)
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    expected = tuple(generation.get(field) for field in (
        "device", "inode", "size", "mtime_ns", "ctime_ns"))
    current_generation = (
        current.st_dev, current.st_ino, current.st_size,
        current.st_mtime_ns, current.st_ctime_ns)
    return observed == finished == expected == current_generation


def _skill_manifest_capture_matches(root, name, capture):
    """Revalidate one captured manifest path without reading it again."""
    if not isinstance(capture, dict) \
            or not isinstance(capture.get("manifest"), dict):
        return False
    manifest = capture["manifest"]
    expected = tuple(manifest.get(field) for field in (
        "device", "inode", "mode", "uid", "size", "mtime_ns",
        "ctime_ns"))
    directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                       | getattr(os, "O_NOFOLLOW", 0)
                       | getattr(os, "O_DIRECTORY", 0))
    root_fd = _open_source_nofollow(root, directory_flags)
    skill_fd = -1
    manifest_fd = -1
    current_skill_fd = -1
    current_manifest_fd = -1
    try:
        root_before = os.fstat(root_fd)
        skill_fd = os.open(name, directory_flags, dir_fd=root_fd)
        skill_before = os.fstat(skill_fd)
        manifest_fd = os.open(
            "SKILL.md", os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0), dir_fd=skill_fd)
        manifest_before = os.fstat(manifest_fd)
        current_root = _source_path_identity(root, directory_flags)
        current_skill_fd = os.open(name, directory_flags, dir_fd=root_fd)
        current_skill = os.fstat(current_skill_fd)
        current_manifest_fd = os.open(
            "SKILL.md", os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0), dir_fd=skill_fd)
        current_manifest = os.fstat(current_manifest_fd)
        manifest_after = os.fstat(manifest_fd)
        skill_after = os.fstat(skill_fd)
        root_after = os.fstat(root_fd)
    finally:
        for descriptor in (current_manifest_fd, current_skill_fd,
                           manifest_fd, skill_fd, root_fd):
            if descriptor >= 0:
                os.close(descriptor)
    return (
        expected == _skill_manifest_identity(manifest_before)
        == _skill_manifest_identity(current_manifest)
        == _skill_manifest_identity(manifest_after)
        and _skill_manifest_identity(skill_before)
        == _skill_manifest_identity(current_skill)
        == _skill_manifest_identity(skill_after)
        and _skill_manifest_identity(root_before)
        == _skill_manifest_identity(current_root)
        == _skill_manifest_identity(root_after)
    )


def _skill_entity_token(name):
    # Reversible byte escaping prevents lossy slugs from aliasing across
    # different scans, when the colliding names are never present together.
    return _source_entity_token(name, "skill")

def _skill_description(name):
    """description: line of the skill's SKILL.md frontmatter, first root
    that has it. clip() neutralizes wikilink/markdown syntax, so a hostile
    description cannot inject links or structure into the corpus."""
    for root in SKILL_ROOTS:
        try:
            capture = _read_skill_manifest(root, name)
        except OSError:
            continue
        if capture["description"]:
            return capture["description"]
    return ""


def sense_skills(cursors):
    """Agent skills installed in the personal skill roots. Scans for
    <root>/<name>/SKILL.md, diffs against the last snapshot, and emits
    cataloged/installed/updated/removed events linking [[skills/<name>]]
    entities. Snapshot rides in cursors, so it commits only after the
    corpus write — a failed pulse re-diffs and the day-page idempotence
    gate absorbs the replay."""
    previous = cursors.get("skills.snapshot")
    prev = previous if isinstance(previous, dict) else None
    snap = {}
    truncated = False
    incomplete_roots = []
    for root in SKILL_ROOTS:
        root_id = hashlib.sha256(_skill_name_bytes(root)).hexdigest()
        try:
            entries, root_truncated, generation = _list_skill_entries(root)
        except (OSError, RuntimeError, ValueError):
            incomplete_roots.append(root)
            continue
        truncated |= root_truncated
        root_rows = []
        manifest_unstable = False
        for name in entries:
            try:
                capture = _read_skill_manifest(root, name)
            except RuntimeError:
                manifest_unstable = True
                break
            except OSError:
                continue
            root_rows.append((name, capture))
        try:
            root_stable = _skill_root_generation_matches(root, generation)
        except (OSError, RuntimeError, ValueError):
            root_stable = False
        if root_stable and not manifest_unstable:
            for name, capture in root_rows:
                try:
                    current = _skill_manifest_capture_matches(
                        root, name, capture)
                except (OSError, RuntimeError, ValueError):
                    current = False
                if not current:
                    manifest_unstable = True
                    break
        if manifest_unstable or not root_stable:
            incomplete_roots.append(root)
            continue
        for name, capture in root_rows:
            raw_id = hashlib.sha256(_skill_name_bytes(name)).hexdigest()
            skill = _skill_entity_token(name)
            if skill in snap and snap[skill].get("name_id") != raw_id:
                skill = "skill-" + raw_id
            if skill not in snap and len(snap) >= MAX_SKILL_SNAPSHOT_ENTRIES:
                truncated = True
                continue
            cur = snap.setdefault(
                skill, {"name": _skill_display_name(name),
                        "name_id": raw_id, "description": "",
                        "roots": []})
            root_row = {
                "root_id": root_id,
                "description": capture["description"],
                "manifest": capture["manifest"],
            }
            if not any(row.get("root_id") == root_id
                       for row in cur["roots"] if isinstance(row, dict)):
                cur["roots"].append(root_row)
            if not cur["description"] and capture["description"]:
                cur["description"] = capture["description"]
    partial = bool(truncated or incomplete_roots)
    prior_partial = bool(cursors.get(
        "skills.partial", cursors.get("skills.truncated", False)))
    # A partial aggregate cannot prove absence.  Retain the last effective
    # rows during the partial pass and for its first complete successor; the
    # following complete unchanged pass can then prove a removal.
    if prev and (partial or prior_partial):
        observed_snap = snap
        snap = {}
        for skill, prior in prev.items():
            if not isinstance(skill, str) or not isinstance(prior, dict):
                continue
            if len(snap) >= MAX_SKILL_SNAPSHOT_ENTRIES:
                truncated = True
                partial = True
                break
            preserved = dict(prior)
            preserved["name"] = _skill_display_name(
                preserved.get("name", skill))
            snap[skill] = preserved
        for skill, observed in observed_snap.items():
            if skill in snap:
                snap[skill] = observed
            elif len(snap) < MAX_SKILL_SNAPSHOT_ENTRIES:
                snap[skill] = observed
            else:
                truncated = True
                partial = True
    cursors["skills.snapshot"] = snap
    prior_truncated = bool(cursors.get("skills.truncated", False))
    cursors["skills.truncated"] = truncated
    cursors["skills.partial"] = partial
    ts = utcnow()
    refusal_events = [Event(
        "skills", ts, "source-refused",
        f"skill root could not be read as one stable snapshot: "
        f"{clip(_skill_display_name(root), 220)}",
        {"organs/skills"}, {"skills", "refusal"},
        occurrence=("skills:source-refused:" +
                    _source_entity_token(root, "skill-root")))
        for root in incomplete_roots]
    if prev is None:
        if not snap:
            return refusal_events
        evs = []
        for skill in sorted(snap):
            label = snap[skill].get("name", skill)
            desc = snap[skill].get("description", "")
            evs.append(Event(
                "skills", ts, "cataloged",
                f"cataloged installed skill: {clip(label, 220)}"
                + (f" — {desc}" if desc else ""),
                {"organs/skills", f"skills/{skill}"},
                {"skills", "cataloged"},
                occurrence=("skills:cataloged:" + skill + ":" +
                            hashlib.sha256(json.dumps(
                                snap[skill], sort_keys=True,
                                separators=(",", ":"),
                                ensure_ascii=True).encode(
                                    "utf-8")).hexdigest())))
        if truncated:
            evs.append(Event(
                "skills", ts, "catalog-truncated",
                "skill catalog exceeded its bounded snapshot; later entries "
                "were not indexed", {"organs/skills"},
                {"skills", "refusal"},
                occurrence="skills:catalog-truncated"))
        return evs + refusal_events
    evs = []
    # A partial directory page cannot prove absence.  Require two complete
    # consecutive snapshots before emitting a removal after any truncation.
    removed = (set() if partial or prior_partial
               else set(prev) - set(snap))
    for kind, names in (("installed", sorted(set(snap) - set(prev))),
                        ("removed", sorted(removed)),
                        ("updated", sorted(s for s in set(snap) & set(prev)
                                           if snap[s] != prev[s]))):
        for s in names:
            source_state = snap.get(s, prev.get(s))
            label = _skill_display_name(source_state.get("name", s))
            desc = source_state.get("description", "") \
                if isinstance(source_state, dict) else ""
            source_id = hashlib.sha256(json.dumps(
                source_state, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True).encode("utf-8")).hexdigest()
            evs.append(Event("skills", ts, kind,
                             f"skill {kind}: {clip(label, 220)}"
                             + (f" — {desc}" if desc else ""),
                             {"organs/skills", f"skills/{s}"},
                             {"skills", kind},
                             occurrence=f"skills:{kind}:{s}:{source_id}"))
    if truncated and not prior_truncated:
        evs.append(Event(
            "skills", ts, "catalog-truncated",
            "skill catalog exceeded its bounded snapshot; later entries "
            "were not indexed", {"organs/skills"},
            {"skills", "refusal"},
            occurrence="skills:catalog-truncated"))
    return evs + refusal_events


def _parse_custom_json_record(line):
    """Parse/classify one decoded JSONL row at its physical boundary."""
    try:
        value = json.loads(line)
    except (UnicodeError, ValueError, RecursionError):
        return None, "malformed-json-record"
    if not isinstance(value, dict):
        return None, "non-object-json-record"
    return value, None


def _custom_json_record_refusal(line):
    return _parse_custom_json_record(line)[1]


def _custom_match_literals(value, *, field="match"):
    """Validate one finite custom inclusion/exclusion grammar.

    Compatibility intentionally covers the shipped ``ERROR|FATAL`` shape.
    Regex operators are refused instead of being silently reinterpreted or
    evaluated with attacker-controlled backtracking cost.
    """
    if field not in {"match", "exclude"}:
        raise ValueError("custom literal field is invalid")
    if value is None or value == "":
        return ()
    if not _strict_config_string(value, limit=MAX_CONFIG_TEXT_CHARS):
        raise ValueError(f"{field} must be a bounded string")
    alternatives = value.split("|")
    if len(alternatives) > MAX_CONFIG_TAGS \
            or any(not literal for literal in alternatives):
        raise ValueError(
            f"{field} must contain bounded non-empty literal alternatives")
    regex_operators = set(r"\.^$*+?{}[]()")
    if any(regex_operators.intersection(literal)
           for literal in alternatives):
        raise ValueError(
            f"{field} supports literal alternatives only, not regex syntax")
    return tuple(alternatives)


def sense_custom(cursors, include_sources=False, *, entry_index=None,
                 seen_names=None):
    """User-defined evidence streams from config custom_senses: tail a
    log (lines or jsonl), match a pattern, emit events into the user's
    own organ. This is how anyone points SIA at THEIR programs."""
    evs, successful = [], []
    config_errors = (copy.deepcopy(CONFIG_ERRORS)
                     if entry_index in (None, 0) else [])
    configured = CONFIG.get("custom_senses", [])
    if not isinstance(configured, list):
        config_errors.append({"config": "custom_senses",
                              "error": "configuration must be a list"})
        result = ([], config_errors)
        return (*result, successful) if include_sources else result
    if len(configured) > MAX_LEDGER_PENDING_RECORDS:
        config_errors.append({
            "config": "custom_senses",
            "error": "configuration exceeds the bounded entry limit"})
        result = ([], config_errors)
        return (*result, successful) if include_sources else result
    seen_names = set() if seen_names is None else seen_names
    if not isinstance(seen_names, set):
        raise TypeError("custom sense name registry must be a set")
    if entry_index is None:
        selected = enumerate(configured)
    elif isinstance(entry_index, int) and not isinstance(entry_index, bool) \
            and 0 <= entry_index < len(configured):
        selected = ((entry_index, configured[entry_index]),)
    else:
        raise ValueError("custom sense entry index is invalid")
    for index, cs in selected:
        trial = copy.deepcopy(cursors)
        config_events = []
        label = f"entry-{index}"
        try:
            if not isinstance(cs, dict):
                raise ValueError("configuration entry must be an object")
            if cs.get("enabled") is False:
                continue
            if "enabled" in cs and not isinstance(cs.get("enabled"), bool):
                raise ValueError("enabled must be boolean")
            description = cs.get("description", "custom evidence stream")
            if not _strict_config_string(
                    description, limit=MAX_CONFIG_TEXT_CHARS):
                raise ValueError("description must be a bounded string")
            if not _strict_config_string(
                    cs.get("name"), nonempty=True,
                    limit=MAX_CONFIG_TEXT_CHARS):
                raise ValueError("name must be a non-empty string")
            name = sanitize_slugpart(cs["name"])
            label = name
            source_id = f"sense_custom:{name}"
            if len(name) > MAX_SOURCE_NAME_CHARS \
                    or len(source_id) > MAX_SOURCE_NAME_CHARS:
                raise ValueError("name exceeds its canonical source bound")
            if name in seen_names:
                raise ValueError("custom sense names must be unique")
            seen_names.add(name)
            organ_value = cs.get("organ", name)
            if not _strict_config_string(
                    organ_value, nonempty=True,
                    limit=MAX_CONFIG_TEXT_CHARS):
                raise ValueError("organ must be a non-empty string")
            organ = sanitize_slugpart(organ_value)
            if len(organ) > MAX_SOURCE_NAME_CHARS:
                raise ValueError("organ exceeds its canonical bound")
            path_value = cs.get("path")
            if not _strict_config_string(
                    path_value, nonempty=True,
                    limit=MAX_CONFIG_PATH_CHARS):
                raise ValueError("path must be a non-empty string")
            path = os.path.expanduser(path_value)
            stream_type = cs.get("type", "lines")
            if stream_type not in {"lines", "jsonl"}:
                raise ValueError("type must be lines or jsonl")
            match_literals = _custom_match_literals(cs.get("match"))
            exclude_literals = _custom_match_literals(
                cs.get("exclude"), field="exclude")
            field = cs.get("field", "message")
            if not _strict_config_string(
                    field, nonempty=True, limit=MAX_SOURCE_NAME_CHARS):
                raise ValueError("field must be a non-empty string")
            kind = cs.get("kind", "event")
            if not _strict_config_string(
                    kind, nonempty=True, limit=MAX_CONFIG_TEXT_CHARS):
                raise ValueError("kind must be a non-empty string")
            kind = sanitize_slugpart(kind)
            if len(kind) > MAX_SOURCE_NAME_CHARS:
                raise ValueError("kind exceeds its canonical bound")
            tags_value = cs.get("tags", [])
            if not isinstance(tags_value, list) \
                    or len(tags_value) > MAX_CONFIG_TAGS \
                    or any(not _strict_config_string(
                               tag, nonempty=True,
                               limit=MAX_CONFIG_TEXT_CHARS)
                           for tag in tags_value):
                raise ValueError("tags must be a list of non-empty strings")
            tags = {sanitize_slugpart(tag) for tag in tags_value} | {organ}
            if any(len(tag) > MAX_SOURCE_NAME_CHARS for tag in tags):
                raise ValueError("tag exceeds its canonical bound")
            selected_json_texts = []

            def validate_json_record(line):
                value, reason = _parse_custom_json_record(line)
                if reason is None:
                    # A configured JSONL field is a privacy boundary. Format
                    # drift must never turn an absent field into authority to
                    # ingest the entire object (and its unrelated fields).
                    if field not in value:
                        return "missing-json-field"
                    selected = value[field]
                    if not isinstance(selected, str):
                        return "non-text-json-field"
                    try:
                        encoded_selected = selected.encode(
                            "utf-8", errors="strict")
                    except UnicodeError:
                        return "invalid-utf8-json-field"
                    if len(encoded_selected) > MAX_THOUGHT_INBOX_TEXT:
                        return "over-bound-json-field"
                    # Retain only the configured string beyond the physical
                    # validation boundary.  The parsed object and every
                    # unrelated field lose their last reference here; the
                    # event loop cannot accidentally widen its authority.
                    # A positional cache preserves duplicate physical lines
                    # without retaining the raw line as a dictionary key.
                    selected_json_texts.append(selected)
                return reason

            records = tail_line_records(
                path, trial, f"custom.{name}",
                refusal_validator=(
                    validate_json_record
                    if stream_type == "jsonl" else None))
            if stream_type == "jsonl" \
                    and len(selected_json_texts) != len(records):
                raise RuntimeError(
                    "custom JSON validation/render cache mismatch")
            if stream_type == "jsonl":
                # Drop every raw JSON line before matching/rendering.  The
                # positional projection retains occurrence identity and
                # duplicate rows while carrying only the admitted field.
                records = [
                    (generation, ordinal, selected_json_texts[index])
                    for index, (generation, ordinal, _raw_line)
                    in enumerate(records)
                ]
                selected_json_texts.clear()
            count = 0
            overflow_ordinals = []
            for generation, ordinal, text in records:
                if match_literals \
                        and not any(literal in text
                                    for literal in match_literals):
                    continue
                if exclude_literals \
                        and any(literal in text
                                for literal in exclude_literals):
                    continue
                count += 1
                if count <= 10:
                    config_events.append(Event(
                        organ, utcnow(), kind, clip(text, 100),
                        {f"organs/{organ}"}, tags,
                        occurrence=(f"custom:{name}:{generation}:"
                                    f"{ordinal}")))
                else:
                    overflow_ordinals.append([generation, ordinal])
            if count > 10:
                overflow_id = hashlib.sha256(json.dumps(
                    overflow_ordinals, separators=(",", ":")).encode(
                        "utf-8")).hexdigest()
                config_events.append(Event(
                    organ, utcnow(), "activity",
                    f"+{count - 10} more matching lines",
                    {f"organs/{organ}"}, {organ},
                    occurrence=f"custom:{name}:overflow:{overflow_id}"))
        except Exception as exc:
            config_errors.append({"config": label,
                                  "error": str(exc)[:120]})
            continue
        cursors.clear()
        cursors.update(trial)
        evs.extend(config_events)
        successful.append(source_id)
    result = (evs, config_errors)
    return (*result, successful) if include_sources else result


# Exports are captured before bind() exists, so the owner can wrap every
# sensing/helper function while leaving intra-module calls direct and stable.
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
        raise TypeError("sialib sense context must be a globals dictionary")
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
        raise AttributeError(f"unknown SIA sensing export: {name}")
    with _BIND_LOCK:
        bind(parent_globals)
        return target(*args, **kwargs)
