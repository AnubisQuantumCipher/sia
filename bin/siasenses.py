"""SIA's bounded evidence-sensing implementation.

This module deliberately does not import `sialib`.  SIA's core may be loaded
under a dynamic test alias, so importing a canonical core module here would
create a second, stale runtime state.  The owning core binds its current
namespace immediately before each public sensing call instead.
"""

import errno as _errno
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
            r = _strict_json_loads(line)
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


def _attest_rows(path, cursors, key, *, source_fd=None):
    rows = []
    for line in tail_lines(path, cursors, key, source_fd=source_fd):
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
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() \
            or info.st_nlink != 1:
        raise RuntimeError(
            f"{label} is not an owned single-link regular file")
    return _journal_file_identity(info)


def _verified_builtin_attest_rows(chain, cursors, key):
    """Verify and tail one unchanged built-in ledger generation.

    Keep the descriptor-bound verifier and its declared authority inputs alive
    through the bounded tail. The caller's cursor commits only after every
    retained generation still matches, including keeper sidecars.
    """
    binding = _chain_cmds().get(chain)
    if binding is None:
        return []
    try:
        ledger, tool, command, inputs = _normalize_chain_binding(binding)
    except ValueError as exc:
        raise RuntimeError(
            f"{chain} ledger projection binding is invalid") from exc
    if command and command[0] == INVALID_CHAIN_SENTINEL:
        raise RuntimeError(f"{chain} ledger projection binding is invalid")
    if not os.path.lexists(ledger) and not os.path.lexists(tool):
        return []
    if not os.path.lexists(ledger) or not os.path.lexists(tool):
        raise RuntimeError(f"{chain} ledger projection keeper is incomplete")
    trial = copy.deepcopy(cursors)
    try:
        with _bound_chain_verification(
                chain, ledger, tool, command, inputs) as bound:
            bound_ledger = next(
                record for record in bound["records"]
                if record["path"] == ledger and not record["directory"])
            for record in bound["records"]:
                if record["path"] not in (ledger, tool):
                    continue
                info = os.fstat(record["fd"])
                if info.st_uid != os.geteuid() or info.st_nlink != 1:
                    raise RuntimeError(
                        f"{record['label']} is not an owned single-link "
                        "regular file")
            verified = _run_bounded_text_process(
                bound["command"], env=bound["env"], timeout=60,
                cwd=bound["cwd"],
                label=f"{chain} ledger verifier", pass_fds=bound["pass_fds"],
                output_limit=MAX_CONFIG_BYTES, isolate_process_tree=True,
                retain_output=False)
            if verified.returncode != 0:
                raise RuntimeError(f"{chain} keeper exited nonzero")
            if not all(_chain_generation_matches(record)
                       for record in bound["records"]):
                raise RuntimeError(
                    f"{chain} ledger projection changed after keeper verification")
            rows = _attest_rows(
                ledger, trial, key, source_fd=bound_ledger["fd"])
            if not all(_chain_generation_matches(record)
                       for record in bound["records"]):
                raise RuntimeError(
                    f"{chain} ledger projection changed after keeper verification")
    except Exception as exc:
        raise RuntimeError(
            f"{chain} ledger projection refused: {exc}") from exc
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
    the corpus dirty and mint another PULSE row, creating a feedback loop.
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


def _real_process_pid(process):
    pid = process.pid
    if type(pid) is not int or pid <= 1:
        raise RuntimeError("bounded subprocess lost its process identity")
    return pid


def _await_process_exit_unreaped(process, deadline, command, timeout):
    """Wait for leader exit through pidfd while preserving its PID/PGID."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(command, timeout)
    try:
        pidfd = os.pidfd_open(_real_process_pid(process), 0)
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
    pid = _real_process_pid(process)
    try:
        os.killpg(pid, signal.SIGKILL)
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
                        records.append(_strict_json_loads(line))
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
                            parsed = _strict_json_loads(raw.decode(
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


def _journalctl(args, cursor_file, *, metadata_only=False, scope="sys", journal_context=None):
    if journal_context is None:
        tmp = cursor_file + ".pulse"
        catalog_tmp = tmp + ".catalog"
        full_tmp = tmp + ".full"
    else:
        tmp, catalog_tmp, full_tmp = journal_context.begin(scope, cursor_file, metadata_only)
    temporary = (tmp, catalog_tmp, full_tmp)
    try:
        if journal_context is None:
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
        else:
            journal_context.seed(scope, catalog_tmp)
        catalog_cmd = [
            "journalctl", "-o", "json", "--output-fields=__CURSOR",
            "--no-pager", f"--cursor-file={catalog_tmp}"] + args
        try:
            catalog_rows = _journalctl_records(
                catalog_cmd, record_limit=MAX_STATE_JSON_BYTES,
                output_limit=MAX_STATE_JSON_BYTES)
        finally:
            if journal_context is not None:
                journal_context.settle(scope, catalog_tmp)
        catalog = [_journal_catalog_cursor(row) for row in catalog_rows]
        if len(catalog) != len(set(catalog)):
            raise RuntimeError("journal cursor catalog repeats an entry")

        out, refusals, processed = [], [], len(catalog)
        if not metadata_only and catalog:
            if journal_context is None:
                _journal_seed_cursor(cursor_file, full_tmp)
            else:
                journal_context.seed(scope, full_tmp)
            full_cmd = ["journalctl", "-o", "json", "--no-pager",
                        f"--cursor-file={full_tmp}"] + args
            try:
                out, refusals, processed = _journalctl_projected_records(
                    full_cmd, catalog, scope)
            finally:
                if journal_context is not None:
                    journal_context.settle(scope, full_tmp)

        # The source cursor is selected from the verified catalog prefix, not
        # from either producer-owned cursor file (which may have run ahead).
        if journal_context is not None:
            captured = journal_context.finish(scope, catalog, processed)
            return out, captured, refusals
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
        if journal_context is None:
            for target in temporary:
                _journal_unlink_tmp(target)
        else:
            journal_context.abort()
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


def sense_journal(cursors, *, journal_context=None):
    evs = []
    pending = []
    refusals = []
    try:
        for scope, extra in (("sys", []), ("user", ["--user"])):
            cfile = os.path.join(STATE, f"journal-{scope}.cursor")
            first = (not os.path.lexists(cfile) if journal_context is None
                     else journal_context.baseline(scope, cfile))
            context_args = {} if journal_context is None else {"journal_context": journal_context}
            if first:
                _records, cursor, _refused = _journalctl(
                    extra + ["-n", "1"], cfile,
                    metadata_only=True, scope=scope, **context_args)
                pending.append(cursor)
                continue
            recs, cursor, refused = _journalctl(
                extra + ["-p", "err..alert", "-n", "+300"], cfile,
                scope=scope, **context_args)
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
        if journal_context is None:
            for tmp, _real in pending:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        else:
            journal_context.abort()
        raise
    if refusals:
        queued = cursors.setdefault(SOURCE_RECORD_REFUSALS_KEY, [])
        if not isinstance(queued, list) \
                or len(queued) + len(refusals) \
                > MAX_LEDGER_PENDING_RECORDS:
            if journal_context is None:
                for tmp, _real in pending:
                    _journal_unlink_tmp(tmp)
            else:
                journal_context.abort()
            raise ValueError("source record refusal state exceeds its bound")
        queued.extend(refusals)
    if journal_context is None:
        PENDING_CURSOR_RENAMES.extend(pending)
    else:
        journal_context.current()
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
        names = []
        for entry in entries:
            name = entry["name"]
            if name.endswith(".applied"):
                continue
            if not stat.S_ISREG(entry["mode"]):
                evs.append(_source_entry_refusal_event(
                    "guardian", f"guardian {label} {name}"))
                continue
            names.append(name)
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
    special_project_entries = [
        entry for entry in entries
        if not stat.S_ISDIR(entry["mode"])
        and not stat.S_ISREG(entry["mode"])]
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
    for entry in special_project_entries:
        cycle_coverage = False
        evs.append(_source_entry_refusal_event(
            "projects", f"project repository {entry['name']}"))
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


# Only complete object names are admitted.  Git repositories use either the
# SHA-1 or SHA-256 object format; abbreviations from an untrusted reflog are
# never passed back to Git.
OBSIDIAN_HEX = frozenset("0123456789abcdef")
OBSIDIAN_OBJECT_NAME_LENGTHS = frozenset((40, 64))
OBSIDIAN_GIT_PATH = "/usr/bin/git"


def _obsidian_object_name(value):
    """True only for one complete, non-null Git object name."""
    return (isinstance(value, str)
            and len(value) in OBSIDIAN_OBJECT_NAME_LENGTHS
            and set(value) <= OBSIDIAN_HEX
            and set(value) != {"0"})


def _obsidian_commit_record(line):
    """Project one reflog row to its commit OID, or ``None`` if unrelated."""
    if "\t" not in line:
        return None
    meta, action = line.split("\t", 1)
    if not action.startswith("commit"):
        return None
    fields = meta.split(" ", 2)
    if len(fields) != 3 or not _obsidian_object_name(fields[1]):
        raise ValueError("Obsidian commit reflog row has no complete object name")
    return fields[1]


def _obsidian_git_environment():
    """Minimal environment for the fixed, non-interactive metadata read."""
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": "/nonexistent",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_PAGER": "cat",
        "PAGER": "cat",
        "LC_ALL": "C.UTF-8",
    }


def _parse_obsidian_git_metadata(output, requested):
    """Parse fixed Git output and discard every Markdown pathname.

    The returned dictionary retains only commit object name, subject, and
    aggregate add/change/delete path counts.  Any missing, duplicate, or
    malformed record refuses the whole cursor trial.
    """
    if not isinstance(output, str) or not isinstance(requested, list) \
            or not requested:
        raise ValueError("Obsidian Git metadata request is invalid")
    if not output.strip():
        raise ValueError("Obsidian Git metadata omitted a requested commit")
    # A leading NUL and two NUL field boundaries frame each commit.  Without
    # `-z`, core.quotePath C-quotes control/non-UTF-8 pathname bytes, so the
    # bounded runner can decode strict UTF-8 without retaining a pathname.
    # Commit subjects may contain every control except NUL and remain isolated
    # as their own field for the Event redaction boundary.
    fields = output.split("\x00")
    if not fields or fields.pop(0) != "" \
            or len(fields) != len(requested) * 3:
        raise ValueError("Obsidian Git metadata output is malformed")
    records = {}
    statuses = {"A", "D", "M", "T"}
    for position, expected_oid in enumerate(requested):
        oid, subject, changes = fields[position * 3:(position + 1) * 3]
        if oid != expected_oid or not _obsidian_object_name(oid) \
                or oid in records:
            raise ValueError("Obsidian Git metadata output is malformed")
        counts = {"added": 0, "changed": 0, "deleted": 0}
        for row in changes.splitlines():
            if not row:
                continue
            status_code, separator, _discarded_path = row.partition("\t")
            if not separator or status_code not in statuses \
                    or not _discarded_path:
                raise ValueError("Obsidian Git path metadata is malformed")
            if status_code == "A":
                counts["added"] += 1
            elif status_code == "D":
                counts["deleted"] += 1
            else:
                counts["changed"] += 1
        records[oid] = {"subject": subject, **counts}
    if list(records) != requested:
        raise ValueError("Obsidian Git metadata omitted a requested commit")
    return records


def _obsidian_control_file(path, payload):
    """Create one exact private file in a fresh trusted control Git dir."""
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
             | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def _obsidian_git_metadata(objects_fd, object_names):
    """Read metadata through a config-isolated view of the held object DB."""
    requested = list(dict.fromkeys(object_names))
    if not requested or len(requested) > MAX_SOURCE_TAIL_RECORDS \
            or any(not _obsidian_object_name(value) for value in requested):
        raise ValueError("Obsidian Git metadata request is invalid")
    lengths = {len(value) for value in requested}
    if len(lengths) != 1:
        raise ValueError("Obsidian Git object formats are mixed")
    object_format = "sha1" if lengths == {40} else "sha256"
    with tempfile.TemporaryDirectory(prefix="sia-obsidian-git-") as control:
        os.mkdir(os.path.join(control, "objects"), 0o700)
        os.mkdir(os.path.join(control, "refs"), 0o700)
        _obsidian_control_file(
            os.path.join(control, "HEAD"), b"ref: refs/heads/isolated\n")
        config = (
            b"[core]\n\trepositoryformatversion = 0\n\tbare = true\n"
            if object_format == "sha1" else
            b"[core]\n\trepositoryformatversion = 1\n\tbare = true\n"
            b"[extensions]\n\tobjectformat = sha256\n")
        _obsidian_control_file(os.path.join(control, "config"), config)
        command = [
            OBSIDIAN_GIT_PATH, f"--git-dir={control}",
            "--no-pager", "--no-replace-objects",
            "-c", "core.hooksPath=/dev/null",
            "-c", "core.fsmonitor=false",
            "-c", "core.attributesFile=/dev/null",
            "-c", "core.quotePath=true",
            "-c", "color.ui=false",
            "-c", "diff.external=",
            "-c", "diff.orderFile=/dev/null",
            "log", "--no-walk=unsorted", "--diff-merges=first-parent",
            "--no-ext-diff", "--no-textconv", "--no-notes",
            "--no-show-signature", "--no-renames", "--root",
            "--name-status", "--format=%x00%H%x00%s%x00",
            *[f"{value}^{{commit}}" for value in requested],
            "--", "*.md", ":(exclude).obsidian/**",
        ]
        environment = _obsidian_git_environment()
        environment["GIT_OBJECT_DIRECTORY"] = \
            f"/proc/self/fd/{objects_fd}"
        result = _run_bounded_text_process(
            command, env=environment, timeout=JOURNAL_TIMEOUT_SECONDS,
            cwd=os.sep, pass_fds=(objects_fd,), label="obsidian-git",
            output_limit=MAX_SOURCE_TAIL_BYTES)
        if result.returncode != 0 or result.stderr:
            raise RuntimeError("Obsidian Git metadata read failed")
        return _parse_obsidian_git_metadata(result.stdout, requested)


def _obsidian_git_directory_identity(path, descriptor):
    """Bind one held Git directory to its still-current no-follow path."""
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_DIRECTORY", 0))
    held = os.fstat(descriptor)
    current = _source_path_identity(path, flags)
    if not stat.S_ISDIR(held.st_mode) \
            or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino):
        raise RuntimeError("Obsidian Git directory changed while sensing")
    return (held.st_dev, held.st_ino)


def sense_obsidian(cursors):
    """Sense bounded vault Git records without opening vault note bodies.

    The reflog supplies complete commit identities only.  A fixed Git command
    resolves those identities to the actual commit subject and Markdown path
    add/change/delete counts.  Names are discarded during parsing; note
    bodies, frontmatter, wikilinks, and ``.obsidian/`` remain outside the
    source boundary.  A missing or non-directory ``.git`` is silent.
    """
    if OBSIDIAN_VAULT is None:
        return []
    vault_git = os.path.join(OBSIDIAN_VAULT, ".git")
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_DIRECTORY", 0))
    try:
        git_fd = _open_source_nofollow(vault_git, flags)
    except OSError as exc:
        if exc.errno in {errno.ENOENT, errno.ENOTDIR, errno.ELOOP}:
            return []
        raise
    objects_fd = None
    try:
        before = _obsidian_git_directory_identity(vault_git, git_fd)
        objects_path = os.path.join(vault_git, "objects")
        objects_fd = _open_source_nofollow(objects_path, flags)
        objects_before = _obsidian_git_directory_identity(
            objects_path, objects_fd)
        trial = copy.deepcopy(cursors)
        records = tail_line_records(
            os.path.join(vault_git, "logs/HEAD"), trial, "obsidian.head")
        commit_rows = []
        for generation, ordinal, line in records:
            object_name = _obsidian_commit_record(line)
            if object_name is not None:
                commit_rows.append((generation, ordinal, object_name))
        metadata = (_obsidian_git_metadata(
            objects_fd, [row[2] for row in commit_rows])
            if commit_rows else {})
        objects_after = _obsidian_git_directory_identity(
            objects_path, objects_fd)
        after = _obsidian_git_directory_identity(vault_git, git_fd)
        if before != after or objects_before != objects_after:
            raise RuntimeError("Obsidian Git directory changed while sensing")
        events = []
        for _generation, _ordinal, object_name in commit_rows:
            record = metadata[object_name]
            subject = clip(redact(record["subject"], "obsidian"), 70)
            if not subject:
                subject = "(no subject)"
            summary = (
                f"vault {object_name[:12]}: {subject} — Markdown "
                f"+{record['added']} ~{record['changed']} "
                f"-{record['deleted']}")
            events.append(Event(
                "obsidian", utcnow(), "commit", summary,
                {"organs/obsidian"},
                {"git", "commit", "markdown-metadata", "obsidian"},
                occurrence=f"obsidian:{object_name}"))
        cursors.clear()
        cursors.update(trial)
        return events
    finally:
        if objects_fd is not None:
            os.close(objects_fd)
        os.close(git_fd)


def _session_cursor_row_valid(value):
    """Accept one canonical session row, including its upgrade-only shape."""
    if not isinstance(value, dict) or set(value) not in ({
            "size", "announced", "generation"}, {
            "size", "announced", "generation", "snapshot_generation"}):
        return False
    integer_fields = {"size", "generation"}
    if "snapshot_generation" in value:
        integer_fields.add("snapshot_generation")
    return isinstance(value["announced"], bool) and all(
        not isinstance(value[field], bool)
        and isinstance(value[field], int) and value[field] >= 0
        for field in integer_fields)


def _normalized_session_cursor_row(value):
    """Migrate only byte-exact historical session row schemas."""
    if _session_cursor_row_valid(value):
        return copy.deepcopy(value)
    if isinstance(value, dict) and set(value) == {"size", "announced"} \
            and not isinstance(value["size"], bool) \
            and isinstance(value["size"], int) and value["size"] >= 0 \
            and isinstance(value["announced"], bool):
        return {**value, "generation": 0}
    if isinstance(value, dict) and set(value) == {
            "off", "n", "title", "announced", "cwd"} \
            and all(not isinstance(value[field], bool)
                    and isinstance(value[field], int) and value[field] >= 0
                    for field in ("off", "n")) \
            and isinstance(value["announced"], bool) \
            and _strict_config_string(
                value["title"], limit=MAX_CONFIG_TEXT_CHARS) \
            and _strict_config_string(
                value["cwd"], limit=MAX_CONFIG_PATH_CHARS):
        return {"size": value["off"], "announced": value["announced"],
                "generation": 0}
    return value


def sense_claude(cursors):
    """Claude sessions from filesystem metadata only; payloads are unopened."""
    evs = []
    sessions, state_truncated = _bounded_source_state(
        cursors, "claude.sessions", "claude-session",
        value_validator=_session_cursor_row_valid,
        value_normalizer=_normalized_session_cursor_row)
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
            # First observation: announce only if the file is fresh (< 1 h old).
            age = time.time() - source["mtime"]
            fresh = 0 <= age < 3600
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
            # An old session grew after its initial observation; start reporting.
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
    was a first-class session source."""
    evs = []
    sessions, state_truncated = _bounded_source_state(
        cursors, "codex.sessions", "codex-session",
        value_validator=_session_cursor_row_valid,
        value_normalizer=_normalized_session_cursor_row)
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
            age = time.time() - source["mtime"]
            fresh = 0 <= age < 3600
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


_NOTIFY_LEGACY_CURSOR_KEYS = frozenset({
    "notify.last", "notify.pending", "notify.pending_complete",
    "notify.paginated", "notify.baselining", "notify.seen",
    "notify.cycle_max",
})
_NOTIFY_SCAN_MODES = frozenset({"baseline", "replay", "empty-replay"})
_NOTIFY_SCAN_SCHEMA = "sia-notification-directory-scan-v3"
_NOTIFY_SCAN_LEGACY_SCHEMAS = frozenset({
    "sia-notification-directory-scan-v1",
    "sia-notification-directory-scan-v2",
})
_NOTIFY_BASELINE_SCHEMA = "sia-notification-baseline-v1"
_NOTIFY_OPAQUE_CAUSES = frozenset({
    "baseline-unstable", "legacy-ambiguous", "v2-migration"})
# Arithmetic evidence: status=exact, parsed=256*8, exact=2048; parsed=256*2,
# exact=512. Exact rational arithmetic outside the Lean certificate chain;
# NOT formal-bounded.
_NOTIFY_FILTER_BYTES = 256
_NOTIFY_FILTER_BITS = 2048
_NOTIFY_FILTER_HEX_CHARS = 512


def _notify_generation(value):
    """Return one canonical completed notification-directory generation."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("notification directory generation is invalid")
    generation = _source_tree_directory_generation(value)
    if value != generation:
        raise ValueError("notification directory generation is invalid")
    return generation


def _notify_scan_candidate(value):
    """Validate one bounded notification generation candidate."""
    if value is None:
        return {
            "schema": _NOTIFY_SCAN_SCHEMA, "generation": None,
            "sources": [], "truncated": False,
            "baseline_bits": "0" * _NOTIFY_FILTER_HEX_CHARS,
        }
    if not isinstance(value, dict) \
            or set(value) != {
                "schema", "generation", "sources", "truncated",
                "baseline_bits"} \
            or value.get("schema") != _NOTIFY_SCAN_SCHEMA \
            or not isinstance(value.get("sources"), list) \
            or not isinstance(value.get("truncated"), bool) \
            or not isinstance(value.get("baseline_bits"), str) \
            or len(value["baseline_bits"]) != _NOTIFY_FILTER_HEX_CHARS \
            or re.fullmatch(r"[0-9a-f]+", value["baseline_bits"]) is None \
            or len(value["sources"]) > MAX_LEDGER_PENDING_RECORDS \
            or any(not _agent_source_capture_valid(source, suffix=None)
                   for source in value["sources"]) \
            or len({source["name"] for source in value["sources"]}) \
            != len(value["sources"]) \
            or value["sources"] != sorted(
                value["sources"], key=_notification_source_order,
                reverse=True) \
            or (value["truncated"]
                and len(value["sources"]) != MAX_LEDGER_PENDING_RECORDS):
        raise ValueError("notification directory scan cursor is invalid")
    generation = _notify_generation(value.get("generation"))
    if generation is None or value["generation"] != generation:
        raise ValueError("notification directory scan cursor is invalid")
    return value


def _notification_name_valid(value):
    """Whether a cursor value can be one exact filesystem component."""
    if not isinstance(value, str):
        return False
    try:
        raw = os.fsencode(value)
    except UnicodeError:
        return False
    return bool(raw) and raw not in {b".", b".."} \
        and b"/" not in raw and b"\0" not in raw \
        and len(raw) <= MAX_CORPUS_COMPONENT_BYTES


def _notify_baseline(value):
    """Return one immutable exact/filter baseline or opaque boundary."""
    if value is None:
        return None
    if not isinstance(value, dict) \
            or value.get("schema") != _NOTIFY_BASELINE_SCHEMA:
        raise ValueError("notification baseline cursor is invalid")
    if value.get("kind") == "exact":
        if set(value) != {"schema", "kind", "names"} \
                or not isinstance(value.get("names"), list) \
                or len(value["names"]) > MAX_LEDGER_PENDING_RECORDS \
                or any(not _notification_name_valid(name)
                       for name in value["names"]) \
                or len(set(value["names"])) != len(value["names"]) \
                or value["names"] != sorted(
                    value["names"], key=os.fsencode):
            raise ValueError("notification baseline cursor is invalid")
        return {"schema": _NOTIFY_BASELINE_SCHEMA, "kind": "exact",
                "names": list(value["names"])}
    if value.get("kind") == "filter":
        if set(value) != {"schema", "kind", "bits"} \
                or not isinstance(value.get("bits"), str) \
                or len(value["bits"]) != _NOTIFY_FILTER_HEX_CHARS \
                or re.fullmatch(r"[0-9a-f]+", value["bits"]) is None \
                or value["bits"] == "0" * _NOTIFY_FILTER_HEX_CHARS:
            raise ValueError("notification baseline cursor is invalid")
        return dict(value)
    if value.get("kind") == "opaque":
        if set(value) != {"schema", "kind", "cause"} \
                or value.get("cause") not in _NOTIFY_OPAQUE_CAUSES:
            raise ValueError("notification baseline cursor is invalid")
        return dict(value)
    raise ValueError("notification baseline cursor is invalid")


def _notify_opaque_baseline(cause):
    if cause not in _NOTIFY_OPAQUE_CAUSES:
        raise ValueError("notification baseline cause is invalid")
    return {"schema": _NOTIFY_BASELINE_SCHEMA,
            "kind": "opaque", "cause": cause}


def _notify_filter_add(bits, name):
    """Add a raw leaf name to the fixed one-sided membership filter."""
    digest = hashlib.sha256(
        (_NOTIFY_BASELINE_SCHEMA + "\0").encode("ascii")
        + os.fsencode(name)).digest()
    bit = int.from_bytes(digest, "big") % _NOTIFY_FILTER_BITS
    byte_index, bit_index = divmod(bit, 8)
    updated = bytearray.fromhex(bits)
    updated[byte_index] |= 1 << bit_index
    return updated.hex()


def _notify_filter_contains(bits, name):
    """Return false only when the immutable filter proves non-membership."""
    digest = hashlib.sha256(
        (_NOTIFY_BASELINE_SCHEMA + "\0").encode("ascii")
        + os.fsencode(name)).digest()
    bit = int.from_bytes(digest, "big") % _NOTIFY_FILTER_BITS
    byte_index, bit_index = divmod(bit, 8)
    return bool(bytes.fromhex(bits)[byte_index] & (1 << bit_index))


def _notify_baseline_from_scan(scan):
    """Bind a clean first generation with one-sided overflow membership."""
    if scan["truncated"]:
        return {
            "schema": _NOTIFY_BASELINE_SCHEMA,
            "kind": "filter",
            "bits": scan["baseline_bits"],
        }
    return {
        "schema": _NOTIFY_BASELINE_SCHEMA,
        "kind": "exact",
        "names": sorted(
            (source["name"] for source in scan["sources"]),
            key=os.fsencode),
    }


def _notify_baseline_refusal_event(baseline):
    return _source_entry_refusal_event(
        "notify", f"notification baseline {baseline['cause']}")


def _legacy_notify_cursor_valid(cursors):
    """Validate the bounded legacy fields before replacing their authority."""
    for key in ("notify.last", "notify.cycle_max"):
        if key in cursors and cursors[key] != "" \
                and not _notification_name_valid(cursors[key]):
            return False
    for key in ("notify.pending", "notify.seen"):
        if key not in cursors:
            continue
        names = cursors[key]
        if not isinstance(names, list) \
                or len(names) > MAX_SOURCE_SCAN_ENTRIES \
                or any(not _notification_name_valid(name)
                       for name in names) \
                or len(set(names)) != len(names):
            return False
    for key in ("notify.pending_complete", "notify.paginated",
                "notify.baselining"):
        if key in cursors and not isinstance(cursors[key], bool):
            return False
    return True


def _notify_scan_page_authority(cursors):
    """Validate a paired in-progress directory page and scan candidate."""
    page_present = "source.notify.page" in cursors
    scan_present = "notify.scan" in cursors
    if page_present != scan_present:
        raise ValueError("notification replay cursor authority is ambiguous")
    if not page_present:
        return False
    try:
        scan = _notify_scan_candidate(cursors["notify.scan"])
        page = _validated_source_page_state(cursors["source.notify.page"])
        page_generation = _source_tree_directory_generation(page)
    except (AttributeError, TypeError, ValueError):
        raise ValueError(
            "notification replay cursor authority is ambiguous") from None
    if page.get("cookie", 0) <= 0 \
            or scan["generation"] != page_generation:
        raise ValueError("notification replay cursor authority is ambiguous")
    return True


def _notify_replay_authority(cursors, *, allow_opaque=False):
    """Name the persisted authority that can justify notification replay.

    A source replay marker predates cursor publication.  Only an immutable
    membership baseline from the current runtime, or the unique legacy state
    proving an empty prior directory, can distinguish a newly observed name
    from a pre-upgrade baseline row.
    """
    if not isinstance(allow_opaque, bool) or not isinstance(cursors, dict):
        raise ValueError("notification replay cursor image is invalid")
    legacy_keys = {
        key for key in _NOTIFY_LEGACY_CURSOR_KEYS if key in cursors}
    current_keys = {
        "notify.baseline", "notify.generation", "notify.scan_mode",
        "notify.scan_tainted", "notify.scan", "source.notify.page",
    }
    if legacy_keys:
        if legacy_keys == {"notify.last"} \
                and cursors["notify.last"] == "" \
                and not current_keys.intersection(cursors):
            return "legacy-empty"
        raise ValueError("notification replay cursor authority is ambiguous")
    try:
        baseline = _notify_baseline(cursors.get("notify.baseline"))
        generation = _notify_generation(cursors.get("notify.generation"))
    except ValueError:
        raise ValueError(
            "notification replay cursor authority is ambiguous") from None
    mode_present = "notify.scan_mode" in cursors
    mode = cursors.get("notify.scan_mode")
    taint_present = "notify.scan_tainted" in cursors
    tainted = cursors.get("notify.scan_tainted", False)
    if mode_present and mode not in _NOTIFY_SCAN_MODES \
            or not isinstance(tainted, bool) \
            or tainted and mode is None:
        raise ValueError("notification replay cursor authority is ambiguous")
    page_present = _notify_scan_page_authority(cursors)
    if mode is None and (taint_present or page_present):
        raise ValueError("notification replay cursor authority is ambiguous")
    if baseline is not None and baseline["kind"] in {"exact", "filter"} \
            and generation is not None:
        if mode not in {None, "replay"} \
                or not allow_opaque and mode is not None:
            raise ValueError(
                "notification replay cursor authority is ambiguous")
        return "baseline"
    if baseline is not None and baseline["kind"] == "exact" \
            and not baseline["names"] and generation is None \
            and "notify.generation" not in cursors \
            and cursors.get("notify.scan_mode") == "empty-replay":
        tainted = cursors.get("notify.scan_tainted", False)
        if not isinstance(tainted, bool):
            raise ValueError(
                "notification replay cursor authority is ambiguous")
        return "legacy-empty-continuation"
    if allow_opaque and baseline is not None \
            and baseline["kind"] == "opaque":
        if mode not in {None, "replay"} \
                or generation is None and mode != "replay":
            raise ValueError(
                "notification replay cursor authority is ambiguous")
        return "opaque-diagnostic"
    if allow_opaque and baseline is None and generation is None \
            and mode == "baseline" and page_present:
        return "baseline-continuation"
    raise ValueError("notification replay cursor authority is ambiguous")


def _notify_cursor_checkpoint_safe(cursors):
    """Whether a durable cursor makes an interrupted baseline unambiguous."""
    try:
        _notify_replay_authority(cursors, allow_opaque=True)
        return True
    except (TypeError, ValueError):
        return False


def _notify_recover_interrupted_baseline(cursors):
    """Turn a pre-cursor crash at first baseline into permanent opacity."""
    if not isinstance(cursors, dict):
        raise ValueError("notification baseline recovery cursor is invalid")
    recovered = copy.deepcopy(cursors)
    if _notify_cursor_checkpoint_safe(recovered):
        return recovered
    notification_keys = set(_NOTIFY_LEGACY_CURSOR_KEYS) | {
        "notify.baseline", "notify.generation", "notify.scan_mode",
        "notify.scan_tainted", "notify.scan", "source.notify.page",
    }
    if notification_keys.intersection(recovered):
        raise ValueError("notification baseline recovery cursor is ambiguous")
    recovered["notify.baseline"] = _notify_opaque_baseline(
        "baseline-unstable")
    recovered["notify.scan_mode"] = "replay"
    return recovered


def _notification_source_order(source):
    """Newest stable notification captures win a bounded generation."""
    return (
        source["mtime_ns"], source["ctime_ns"],
        os.fsencode(source["name"]))


def sense_notify(cursors, *, before_initial_baseline=None):
    """Rescan a changed notification-directory generation from its root.

    A completed generation is a cheap unchanged-directory gate.  A changed
    directory is paged from the beginning, and a between-page mutation makes
    the generic directory cursor restart that scan.  A complete first
    generation binds an immutable exact name baseline, or a fixed one-sided
    membership filter when the source window overflows.  Replays emit only
    names proved outside it and keep source-stable occurrence identities for
    durable admission.  Legacy, membership-free, or unstable first scans
    stay explicitly opaque instead of guessing.
    """
    if before_initial_baseline is not None \
            and not callable(before_initial_baseline):
        raise TypeError("notification baseline callback is not callable")
    evs = []
    d = os.path.join(HOME, ".local/state/omarchy/notifications/history")
    page_key = "source.notify.page"
    mode_key = "notify.scan_mode"
    generation_key = "notify.generation"
    taint_key = "notify.scan_tainted"
    scan_key = "notify.scan"
    baseline_key = "notify.baseline"
    baseline_refusal_emitted = False

    if generation_key in cursors and cursors[generation_key] is None:
        raise ValueError("notification directory generation is invalid")
    if baseline_key in cursors and cursors[baseline_key] is None:
        raise ValueError("notification baseline cursor is invalid")

    legacy = any(key in cursors for key in _NOTIFY_LEGACY_CURSOR_KEYS)
    completed_generation = _notify_generation(cursors.get(generation_key))
    baseline = _notify_baseline(cursors.get(baseline_key))
    mode = cursors.get(mode_key)
    if mode is not None and mode not in _NOTIFY_SCAN_MODES:
        raise ValueError("notification directory scan mode is invalid")
    scan_tainted = cursors.get(taint_key, False)
    if not isinstance(scan_tainted, bool) \
            or (scan_tainted and mode is None):
        raise ValueError("notification directory scan taint is invalid")

    if legacy:
        if baseline is not None or not _legacy_notify_cursor_valid(cursors):
            raise ValueError("notification legacy cursor is invalid")
        legacy_keys = {
            key for key in _NOTIFY_LEGACY_CURSOR_KEYS if key in cursors}
        empty_high_water = legacy_keys == {"notify.last"} \
            and cursors["notify.last"] == ""
        # The producer's lone empty high-water value proves that its prior
        # generation had no names.  Every other lexical cursor can confuse an
        # old baseline name with a later lower-sorting name and stays opaque.
        baseline = ({"schema": _NOTIFY_BASELINE_SCHEMA,
                     "kind": "exact", "names": []}
                    if empty_high_water else
                    _notify_opaque_baseline("legacy-ambiguous"))
        cursors[baseline_key] = baseline
        for key in _NOTIFY_LEGACY_CURSOR_KEYS:
            cursors.pop(key, None)
        cursors.pop(page_key, None)
        cursors.pop(scan_key, None)
        cursors.pop(taint_key, None)
        mode = "empty-replay" if empty_high_water else "replay"
        scan_tainted = False
    elif baseline is None and completed_generation is not None:
        # v2 recorded only a directory generation.  Even an unchanged rescan
        # cannot recover baseline names that were subsequently deleted, so
        # this uncertainty must remain opaque across future reappearance.
        baseline = _notify_opaque_baseline("v2-migration")
        cursors[baseline_key] = baseline
        if page_key in cursors or mode is not None:
            cursors.pop(page_key, None)
            cursors.pop(scan_key, None)
            cursors.pop(taint_key, None)
            mode = "replay"
            scan_tainted = False
    elif baseline is None and completed_generation is None \
            and mode == "replay":
        # An interrupted legacy migration may already have removed its old
        # fields.  The replay marker proves uncertainty, not membership.
        baseline = _notify_opaque_baseline("legacy-ambiguous")
        cursors[baseline_key] = baseline
        cursors.pop(page_key, None)
        cursors.pop(scan_key, None)
        cursors.pop(taint_key, None)
        scan_tainted = False

    if mode == "baseline" and (
            baseline is not None or completed_generation is not None):
        raise ValueError("notification baseline cursor is incomplete")
    if baseline is not None and baseline["kind"] in {"exact", "filter"} \
            and completed_generation is None and not (
                mode == "empty-replay"
                and baseline["kind"] == "exact"
                and not baseline["names"]):
        raise ValueError("notification baseline cursor is incomplete")
    if baseline is not None and baseline["kind"] == "opaque" \
            and completed_generation is None and mode != "replay":
        raise ValueError("notification baseline cursor is incomplete")
    if mode == "empty-replay" and (
            completed_generation is not None
            or baseline is None or baseline["kind"] != "exact"
            or baseline["names"]):
        raise ValueError("notification baseline cursor is incomplete")

    page_present = page_key in cursors
    raw_scan = cursors.get(scan_key)
    old_scan = isinstance(raw_scan, dict) \
        and raw_scan.get("schema") in _NOTIFY_SCAN_LEGACY_SCHEMAS

    def make_initial_scan_opaque():
        """Absorb uncertainty from an interrupted/unstable first scan."""
        nonlocal baseline, mode, scan_tainted, baseline_refusal_emitted
        baseline = _notify_opaque_baseline("baseline-unstable")
        cursors[baseline_key] = baseline
        cursors.pop(page_key, None)
        cursors.pop(scan_key, None)
        cursors.pop(taint_key, None)
        mode = "replay"
        cursors[mode_key] = mode
        scan_tainted = False
        if not baseline_refusal_emitted:
            evs.append(_notify_baseline_refusal_event(baseline))
            baseline_refusal_emitted = True

    if mode == "baseline" and (
            not page_present or scan_tainted
            or raw_scan is None or old_scan):
        # A discarded prefix could contain a preexisting name that later
        # reappears.  No compact rescan can recover that membership fact.
        make_initial_scan_opaque()
        page_present = False
        raw_scan = None
    if not page_present:
        cursors.pop(scan_key, None)
    if page_present and mode is None:
        raise ValueError("notification directory scan state is incomplete")

    if not page_present:
        # A candidate without its directory cookie cannot establish which
        # portion of a generation it represents and is never an authority.
        # A prior refused pass deliberately left its mode and taint marker at
        # EOF.  This call is a fresh root-to-EOF attempt over the same
        # generation, so only refusals observed again may taint it.
        scan_tainted = False
        initial_observation = (
            mode is None and baseline is None
            and completed_generation is None)
        initial_fence_set = False
        if initial_observation and before_initial_baseline is not None:
            # Absence is itself an exact empty membership observation. Fence
            # it before even the path stat so a crash cannot later reinterpret
            # the first appearing name as an old baseline member.
            before_initial_baseline()
            initial_fence_set = True
        try:
            current_generation = _source_tree_path_generation(d)
        except FileNotFoundError:
            if initial_observation:
                baseline = {
                    "schema": _NOTIFY_BASELINE_SCHEMA,
                    "kind": "exact", "names": [],
                }
                cursors[baseline_key] = baseline
                mode = "empty-replay"
                cursors[mode_key] = mode
                cursors.pop(taint_key, None)
            elif mode is not None:
                cursors[mode_key] = mode
            if baseline is not None and baseline["kind"] == "opaque":
                evs.append(_notify_baseline_refusal_event(baseline))
            return evs
        if mode is None:
            if completed_generation == current_generation:
                if baseline is not None and baseline["kind"] == "opaque":
                    evs.append(_notify_baseline_refusal_event(baseline))
                return evs
            mode = ("baseline" if completed_generation is None
                    else "replay")
        if mode == "baseline" and before_initial_baseline is not None \
                and not initial_fence_set:
            before_initial_baseline()
        page_before = None
        scan = _notify_scan_candidate(None)
    else:
        page_before = cursors[page_key]
        if raw_scan is None or old_scan:
            # Migrate an old page-only cursor by replaying its generation
            # from the root; its already-returned prefix is not candidate
            # state that can justify publication after this upgrade.
            page_before = None
            scan_tainted = False
            scan = _notify_scan_candidate(None)
        else:
            scan = _notify_scan_candidate(raw_scan)
            page_generation = _source_tree_directory_generation(page_before)
            if page_before.get("cookie", 0) <= 0 \
                    or scan["generation"] != page_generation:
                raise ValueError(
                    "notification directory scan cursor is invalid")

    cursors[mode_key] = mode
    try:
        entries, complete, _inspected, next_page = \
            _bounded_source_entries(d, page_before)
    except FileNotFoundError:
        if mode == "baseline":
            make_initial_scan_opaque()
        else:
            # Preserve the scan mode but discard a cookie into a vanished
            # generation.  Reappearance begins at the directory root.
            cursors.pop(page_key, None)
            cursors.pop(scan_key, None)
        return evs
    except RuntimeError:
        if mode != "baseline":
            raise
        # The generic scanner detected a within-page generation change.
        # The lost prefix makes an exact/filter first baseline impossible.
        make_initial_scan_opaque()
        return evs
    cursors[page_key] = next_page
    generation = _source_tree_directory_generation(next_page)
    if next_page.get("reset"):
        scan_tainted = False
        scan = _notify_scan_candidate(None)
        if mode == "baseline":
            # The page belongs to the restarted generation, but a name from
            # the discarded first-generation prefix may later reappear.
            baseline = _notify_opaque_baseline("baseline-unstable")
            cursors[baseline_key] = baseline
            mode = "replay"
            cursors[mode_key] = mode
            if not baseline_refusal_emitted:
                evs.append(_notify_baseline_refusal_event(baseline))
                baseline_refusal_emitted = True
    scan["generation"] = generation

    def read_notification(source):
        name = source["name"]
        try:
            record = _read_bounded_source_json(
                os.path.join(d, name), f"notification record {name}")
            if not _agent_source_capture_matches(
                    d, source, suffix=None):
                raise RuntimeError("notification source changed")
            app_value = record["app"] if "app" in record else "app"
            summary_value = record["summary"] \
                if "summary" in record else ""
            if not _strict_config_string(
                    app_value, limit=MAX_SOURCE_NAME_CHARS) \
                    or not _strict_config_string(
                        summary_value, limit=MAX_CONFIG_TEXT_CHARS):
                raise ValueError("notification text is invalid")
            app = app_value or "app"
            summary = clip(summary_value, 80)
        except Exception:
            evs.append(_source_entry_refusal_event(
                "notify", f"notification record {name}"))
            return None
        return app, summary

    for entry in entries:
        if not stat.S_ISREG(entry["mode"]):
            scan_tainted = True
            evs.append(_source_entry_refusal_event(
                "notify", f"notification record {entry['name']}"))
            continue
        source = _agent_source_capture(entry)
        if read_notification(source) is None:
            scan_tainted = True
            continue
        if any(prior["name"] == source["name"]
               for prior in scan["sources"]):
            scan_tainted = True
            evs.append(_source_entry_refusal_event(
                "notify", f"duplicate notification record "
                f"{source['name']}"))
            continue
        if mode == "baseline":
            scan["baseline_bits"] = _notify_filter_add(
                scan["baseline_bits"], source["name"])
        scan["sources"].append(source)
        scan["sources"].sort(
            key=_notification_source_order, reverse=True)
        if len(scan["sources"]) > MAX_LEDGER_PENDING_RECORDS:
            del scan["sources"][MAX_LEDGER_PENDING_RECORDS:]
            scan["truncated"] = True
    cursors[taint_key] = scan_tainted
    if not complete:
        cursors[scan_key] = scan
        return evs

    cursors.pop(page_key, None)
    cursors.pop(scan_key, None)
    admitted = []
    if not scan_tainted:
        for source in scan["sources"]:
            record = read_notification(source)
            if record is None:
                scan_tainted = True
                continue
            admitted.append((source["name"], *record))
    if scan_tainted:
        if mode == "baseline":
            # Refusal during a first scan means unseen/deleted names cannot
            # be reconstructed later.  Make that uncertainty permanent, but
            # retain replay debt: repairing a file in place need not change
            # the parent directory generation.
            make_initial_scan_opaque()
            return evs
        # Keep the mode and the last completed generation. Repairing a file
        # in place need not mutate the parent directory, so the next call
        # must rescan even if its generation gate is unchanged. No candidate
        # notification becomes public from this refused generation.
        cursors[mode_key] = mode
        cursors[taint_key] = True
        return evs
    if scan["truncated"]:
        evs.append(Event(
            "notify", utcnow(), "source-truncated",
            "notification history exceeded its bounded source state; "
            "only the newest stable records were admitted",
            {"organs/notify"}, {"source-truncated", "refusal"},
            occurrence="source-truncated:notify:notification-history"))
    if mode == "baseline":
        baseline = _notify_baseline_from_scan(scan)
        cursors[baseline_key] = baseline
    if baseline is None:
        raise ValueError("notification baseline cursor is incomplete")
    if mode in {"replay", "empty-replay"} \
            and baseline["kind"] in {"exact", "filter"}:
        baseline_names = (set(baseline["names"])
                          if baseline["kind"] == "exact" else None)
        for name, app, summary in admitted:
            if baseline_names is not None and name in baseline_names:
                continue
            if baseline["kind"] == "filter" and _notify_filter_contains(
                    baseline["bits"], name):
                continue
            token = _source_entity_token(name, "notification")
            evs.append(Event(
                "notify", utcnow(), "notification",
                f"{app}" + (f": {summary}" if summary else ""),
                {"organs/notify"}, {"notification"},
                occurrence=f"notification:{token}"))
    elif baseline["kind"] == "opaque" and not baseline_refusal_emitted:
        evs.append(_notify_baseline_refusal_event(baseline))
    cursors[generation_key] = generation
    cursors.pop(mode_key, None)
    cursors.pop(taint_key, None)
    return evs


_AGENT_SCAN_SCHEMA = "sia-agent-catalog-scan-v1"
_AGENT_SOURCE_FIELDS = (
    "device", "inode", "mode", "size", "mtime_ns", "ctime_ns")
_AGENT_SOURCE_STAT_FIELDS = (
    "st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")


def _agent_source_capture(entry):
    return {
        "name": entry["name"],
        **{field: entry[field] for field in _AGENT_SOURCE_FIELDS},
    }


def _agent_source_capture_valid(value, *, suffix=".json"):
    if not isinstance(value, dict) \
            or set(value) != {"name", *_AGENT_SOURCE_FIELDS} \
            or not isinstance(value.get("name"), str):
        return False
    try:
        name_bytes = os.fsencode(value["name"])
    except UnicodeError:
        return False
    return bool(name_bytes) and name_bytes not in {b".", b".."} \
        and b"/" not in name_bytes and b"\0" not in name_bytes \
        and len(name_bytes) <= MAX_CORPUS_COMPONENT_BYTES \
        and (suffix is None or value["name"].endswith(suffix)) \
        and all(not isinstance(value[field], bool)
                and isinstance(value[field], int) and value[field] >= 0
                for field in _AGENT_SOURCE_FIELDS) \
        and stat.S_ISREG(value["mode"])


def _agent_source_capture_matches(directory, capture, *, suffix=".json"):
    """Revalidate one prior-page usage record without following links."""
    if not _agent_source_capture_valid(capture, suffix=suffix):
        return False
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    path = os.path.join(directory, capture["name"])
    descriptor = _open_source_nofollow(path, flags)
    try:
        before = os.fstat(descriptor)
        after = os.fstat(descriptor)
        current = _source_path_identity(path, flags)
    finally:
        os.close(descriptor)
    expected = tuple(capture[field] for field in _AGENT_SOURCE_FIELDS)
    observed = tuple(getattr(before, field)
                     for field in _AGENT_SOURCE_STAT_FIELDS)
    finished = tuple(getattr(after, field)
                     for field in _AGENT_SOURCE_STAT_FIELDS)
    current_identity = tuple(getattr(current, field)
                             for field in _AGENT_SOURCE_STAT_FIELDS)
    return expected == observed == finished == current_identity


def _agent_usage_row_valid(value):
    """Validate one authoritative per-agent usage row exactly."""
    if not isinstance(value, dict) \
            or set(value) != {"tokens", "limits", "generation"} \
            or isinstance(value["tokens"], bool) \
            or not isinstance(value["tokens"], int) \
            or value["tokens"] < 0 \
            or not isinstance(value["limits"], dict) \
            or len(value["limits"]) > MAX_CONFIG_TAGS \
            or isinstance(value["generation"], bool) \
            or not isinstance(value["generation"], int) \
            or value["generation"] < 0:
        return False
    return all(
        _source_entity_token_is_canonical(label_id, "agent-limit")
        and not isinstance(percent, bool)
        and isinstance(percent, int)
        and 0 <= percent <= 100
        for label_id, percent in value["limits"].items())


def _normalized_agent_usage_row(value):
    """Migrate only the exact pre-generation agent row schema."""
    if _agent_usage_row_valid(value):
        return copy.deepcopy(value)
    if not isinstance(value, dict) \
            or set(value) != {"tokens", "limits"} \
            or isinstance(value["tokens"], bool) \
            or not isinstance(value["tokens"], int) \
            or value["tokens"] < 0 \
            or not isinstance(value["limits"], dict) \
            or len(value["limits"]) > MAX_CONFIG_TAGS:
        return value
    limits = {}
    for raw_label, percent in value["limits"].items():
        if not _strict_config_string(
                raw_label, nonempty=True, limit=MAX_CONFIG_TEXT_CHARS) \
                or isinstance(percent, bool) \
                or not isinstance(percent, int) \
                or not 0 <= percent <= 100:
            return value
        label_id = _source_entity_token(raw_label, "agent-limit")
        if label_id in limits:
            return value
        limits[label_id] = percent
    return {
        "tokens": value["tokens"], "limits": limits, "generation": 0}


def _normalized_legacy_agent_key(source_key, value, tagged):
    """Classify a persisted agent key using its producer's row schema."""
    legacy = isinstance(value, dict) \
        and set(value) == {"tokens", "limits"}
    modern = _agent_usage_row_valid(value)
    if legacy:
        if not tagged:
            return _source_entity_token(source_key, "agent"), 0
        if not isinstance(source_key, str):
            raise ValueError("legacy agent identity is invalid")
        broad = re.fullmatch(
            r"[a-z0-9_][a-z0-9._-]*", source_key) is not None \
            and len(source_key) <= MAX_SOURCE_NAME_CHARS \
            and len(source_key.encode("utf-8")) <= MAX_CORPUS_LEAF_BYTES
        if not broad:
            raise ValueError("legacy agent identity is invalid")
        if not _source_entity_token_is_canonical(source_key, "agent"):
            return _source_entity_token(source_key, "agent"), 0
        if _source_entity_token(source_key, "agent") != source_key:
            raise ValueError("legacy agent identity is ambiguous")
        return source_key, 0
    if not modern \
            or not _source_entity_token_is_canonical(source_key, "agent"):
        raise ValueError("agent usage identity is invalid")
    return source_key, 1


def _agent_scan_candidate(value):
    """Validate one bounded, generation-scoped agent scan candidate."""
    if value is None:
        return {
            "schema": _AGENT_SCAN_SCHEMA, "generation": None,
            "tainted": False, "rows": {}, "sources": {}, "displays": {},
            "partial_limits": [], "conflicted_ids": []}
    if not isinstance(value, dict) \
            or set(value) != {
                "schema", "generation", "tainted", "rows", "sources",
                "displays", "partial_limits", "conflicted_ids"} \
            or value.get("schema") != _AGENT_SCAN_SCHEMA \
            or not isinstance(value.get("tainted"), bool) \
            or not isinstance(value.get("rows"), dict) \
            or not isinstance(value.get("sources"), dict) \
            or set(value["sources"]) != set(value["rows"]) \
            or not isinstance(value.get("displays"), dict) \
            or set(value["displays"]) != set(value["rows"]) \
            or any(not _agent_source_capture_valid(source)
                   for source in value["sources"].values()) \
            or len({source["name"]
                    for source in value["sources"].values()}) \
            != len(value["sources"]) \
            or not isinstance(value.get("partial_limits"), list) \
            or not isinstance(value.get("conflicted_ids"), list) \
            or len(value["rows"]) > MAX_SOURCE_SCAN_ENTRIES \
            or len(value["partial_limits"]) > MAX_SOURCE_SCAN_ENTRIES \
            or len(value["conflicted_ids"]) > MAX_SOURCE_SCAN_ENTRIES \
            or len(value["rows"]) + len(value["conflicted_ids"]) \
            > MAX_SOURCE_SCAN_ENTRIES \
            or any(not isinstance(aid, str)
                   for aid in value["partial_limits"]
                   + value["conflicted_ids"]) \
            or len(set(value["partial_limits"])) \
            != len(value["partial_limits"]) \
            or len(set(value["conflicted_ids"])) \
            != len(value["conflicted_ids"]) \
            or any(aid not in value["rows"]
                   for aid in value["partial_limits"]) \
            or any(not isinstance(aid, str)
                   or re.fullmatch(r"[a-z0-9_][a-z0-9._-]*", aid) is None
                   or aid in value["rows"]
                   for aid in value["conflicted_ids"]):
        raise ValueError("agent usage scan cursor is invalid")
    generation = value.get("generation")
    if generation is not None:
        generation = _source_tree_directory_generation(generation)
        if value["generation"] != generation:
            raise ValueError("agent usage scan cursor is invalid")
    for aid, row in value["rows"].items():
        source = value["sources"].get(aid)
        display = value["displays"].get(aid)
        if not isinstance(aid, str) \
                or re.fullmatch(r"[a-z0-9_][a-z0-9._-]*", aid) is None \
                or len(aid) > MAX_SOURCE_NAME_CHARS \
                or len(aid.encode("utf-8")) > MAX_CORPUS_LEAF_BYTES \
                or not _agent_usage_row_valid(row) \
                or not _agent_source_capture_valid(source) \
                or not isinstance(display, dict) \
                or set(display) != {"agent", "limits"} \
                or not isinstance(display["agent"], str) \
                or len(display["agent"]) > 40 \
                or not isinstance(display["limits"], dict) \
                or set(display["limits"]) != set(row["limits"]) \
                or any(not isinstance(label, str) or len(label) > 30
                       for label in display["limits"].values()):
            raise ValueError("agent usage scan cursor is invalid")
    return value


def _store_agent_state(cursors, rows):
    """Replace the authoritative bounded agent state without aliasing it."""
    if not isinstance(rows, dict) \
            or len(rows) > MAX_SOURCE_SCAN_ENTRIES:
        raise ValueError("agent usage state exceeds its bound")
    cursors["agents.state"] = [
        "sia-source-entity-state-v1", copy.deepcopy(rows)]


def _agent_transition_events(aid, display, prior, current):
    """Render transitions only after one candidate survives to EOF."""
    if not prior:
        return []
    transition_id = hashlib.sha256(json.dumps(
        {"prior": prior, "current": current},
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    agent_label = display["agent"]
    events = []
    dtok = current["tokens"] - prior.get("tokens", 0)
    if dtok > 500_000:
        events.append(Event(
            "agents", utcnow(), "usage",
            f"{agent_label}: +{dtok // 1000}k tokens today "
            f"({current['tokens'] // 1000}k total)",
            {"organs/agents"}, {"agents"},
            occurrence=f"agents:{aid}:usage:{transition_id}"))
    prior_limits = prior.get("limits", {})
    if not isinstance(prior_limits, dict):
        raise ValueError("agent usage cursor is invalid")
    for label_id, pct in current["limits"].items():
        old = prior_limits.get(label_id, pct)
        if pct < old + 10:
            continue
        tags = {"agents"}
        if pct >= 90:
            tags.add("urgent")
        label = display["limits"][label_id]
        events.append(Event(
            "agents", utcnow(), "limit",
            f"{agent_label} {label} limit at {pct}% (was {old}%)",
            {"organs/agents"}, tags,
            occurrence=(f"agents:{aid}:limit:{label_id}:"
                        f"{transition_id}")))
    return events


def sense_agents(cursors):
    """Omarchy Quattro agents-usage records.

    Directory pages accumulate in a generation-bound candidate.  The prior
    authoritative catalog therefore remains intact until EOF; only a clean
    generation can replace it and prove that an agent vanished.  A refused
    generation still advances and merges every admitted observation, but it
    cannot prune an unseen authoritative row.
    """
    evs = []
    d = os.path.join(HOME, ".local/state/omarchy/agents/usage")
    state, state_truncated = _bounded_source_state(
        cursors, "agents.state", "agent",
        value_validator=_agent_usage_row_valid,
        value_normalizer=_normalized_agent_usage_row,
        legacy_key_normalizer=_normalized_legacy_agent_key)
    if state_truncated:
        evs.append(_source_truncation_event("agents", "agent usage cursor"))
    page_key = "source.agents.page"
    scan_key = "agents.scan"
    page_before = cursors.get(page_key)
    raw_scan = cursors.get(scan_key)
    if page_before is None:
        # A candidate without its directory cookie cannot establish which
        # portion of the generation it represents.  Start from the root.
        scan = _agent_scan_candidate(None)
    elif raw_scan is None:
        # Migrate the old page-only cursor conservatively: replay its
        # generation rather than treating a page-mutated authority as a
        # candidate or inferring absence from its suffix.
        page_before = None
        scan = _agent_scan_candidate(None)
    else:
        scan = _agent_scan_candidate(raw_scan)
        page_generation = _source_tree_directory_generation(page_before)
        if page_before.get("cookie", 0) <= 0 \
                or scan["generation"] != page_generation:
            raise ValueError("agent usage scan cursor is invalid")
    try:
        entries, complete, _inspected, next_page = _bounded_source_entries(
            d, page_before, MAX_CONFIG_TAGS)
    except FileNotFoundError:
        cursors.pop(page_key, None)
        cursors.pop(scan_key, None)
        return evs
    generation = _source_tree_directory_generation(next_page)
    if next_page.get("reset") or scan["generation"] not in (None, generation):
        # The returned page starts at the new generation's root.  Nothing
        # accumulated under the old cookie may leak into this candidate.
        scan = _agent_scan_candidate(None)
    scan["generation"] = generation
    candidate = scan["rows"]

    for entry in entries:
        n = entry["name"]
        if not n.endswith(".json"):
            continue
        if not stat.S_ISREG(entry["mode"]):
            scan["tainted"] = True
            evs.append(_source_entry_refusal_event(
                "agents", f"agent usage record {n}"))
            continue
        try:
            j = _read_bounded_source_json(
                os.path.join(d, n), f"agent usage record {n}")
        except Exception:
            scan["tainted"] = True
            evs.append(_source_entry_refusal_event(
                "agents", f"agent usage record {n}"))
            continue
        source_capture = _agent_source_capture(entry)
        try:
            source_stable = _agent_source_capture_matches(d, source_capture)
        except (OSError, RuntimeError, ValueError):
            source_stable = False
        if not source_stable:
            scan["tainted"] = True
            evs.append(_source_entry_refusal_event(
                "agents", f"agent usage record {n}"))
            continue
        try:
            aid_raw = j["id"] if "id" in j else n[:-5]
            if not _strict_config_string(
                    aid_raw, nonempty=True, limit=MAX_SOURCE_NAME_CHARS):
                raise ValueError("agent identity is invalid")
            raw_tokens = j["todayTotalTokens"] \
                if "todayTotalTokens" in j else 0
            if isinstance(raw_tokens, bool) \
                    or not isinstance(raw_tokens, int) \
                    or raw_tokens < 0:
                raise ValueError("agent token count is invalid")
            source_limits = j["limits"] if "limits" in j else []
            if not isinstance(source_limits, list):
                raise ValueError("agent limits are invalid")
            tokens = raw_tokens
        except (TypeError, UnicodeError, ValueError):
            scan["tainted"] = True
            evs.append(_source_entry_refusal_event(
                "agents", f"agent usage record {n}"))
            continue
        aid = _source_entity_token(aid_raw, "agent")
        if aid in scan["conflicted_ids"]:
            scan["tainted"] = True
            evs.append(_source_entry_refusal_event(
                "agents", f"duplicate agent usage identity {aid_raw} "
                f"in {n}"))
            continue
        prior_source = scan["sources"].get(aid)
        if prior_source is not None and prior_source["name"] != n:
            scan["tainted"] = True
            candidate.pop(aid, None)
            scan["sources"].pop(aid, None)
            scan["displays"].pop(aid, None)
            scan["partial_limits"] = [
                value for value in scan["partial_limits"] if value != aid]
            scan["conflicted_ids"].append(aid)
            evs.append(_source_entry_refusal_event(
                "agents", f"duplicate agent usage identity {aid_raw} "
                f"in {prior_source['name']} and {n}"))
            continue
        prior = candidate.get(aid, state.get(aid, {}))
        if not isinstance(prior, dict):
            raise ValueError("agent usage cursor is invalid")
        if aid not in candidate and aid not in scan["conflicted_ids"] \
                and (len(candidate) + len(scan["conflicted_ids"])) \
                >= MAX_SOURCE_SCAN_ENTRIES:
            scan["tainted"] = True
            evs.append(_source_entry_refusal_event(
                "agents", f"agent usage identity {aid_raw}"))
            continue

        def _pct(v):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return None
            try:
                f = float(v)
                if not math.isfinite(f):
                    return None
                # collectors store fractions of 1.0; older ones use 0-100
                percent = int(round(f * 100)) if 0 <= f <= 1.0 \
                    else int(round(f))
                return percent if 0 <= percent <= 100 else None
            except (OverflowError, TypeError, ValueError):
                return None

        limits = {}
        limits_truncated = len(source_limits) > MAX_CONFIG_TAGS
        limits_invalid = False
        for source_limit in source_limits[:MAX_CONFIG_TAGS]:
            if not isinstance(source_limit, dict):
                limits_invalid = True
                break
            label = source_limit.get("label")
            if not _strict_config_string(
                    label, nonempty=True, limit=MAX_SOURCE_NAME_CHARS):
                limits_invalid = True
                break
            label_id = _source_entity_token(label, "agent-limit")
            percent = _pct(source_limit.get("percent"))
            if percent is None or label_id in limits:
                limits_invalid = True
                break
            limits[label_id] = {"label": label, "percent": percent}
        if limits_invalid:
            scan["tainted"] = True
            evs.append(_source_entry_refusal_event(
                "agents", f"agent limit record {aid_raw}"))
            continue
        limits_partial = limits_truncated
        if limits_truncated:
            scan["tainted"] = True
            evs.append(_source_truncation_event(
                "agents", f"agent limit record {aid_raw}"))
        cur = {"tokens": tokens,
               "limits": {label_id: value["percent"]
                          for label_id, value in limits.items()}}
        transition_generation = prior.get("generation", 0)
        if isinstance(transition_generation, bool) \
                or not isinstance(transition_generation, int) \
                or transition_generation < 0:
            raise ValueError("agent usage generation is invalid")
        if prior and cur["tokens"] < prior.get("tokens", 0):
            transition_generation += 1
        cur["generation"] = transition_generation
        candidate[aid] = cur
        scan["sources"][aid] = source_capture
        scan["displays"][aid] = {
            "agent": clip(aid_raw, 40),
            "limits": {label_id: clip(value["label"], 30)
                       for label_id, value in limits.items()},
        }
        if limits_partial and aid not in scan["partial_limits"]:
            scan["partial_limits"].append(aid)

    if not complete:
        cursors[page_key] = next_page
        cursors[scan_key] = scan
        return evs

    for aid, source_capture in list(scan["sources"].items()):
        try:
            source_stable = _agent_source_capture_matches(d, source_capture)
        except (OSError, RuntimeError, ValueError):
            source_stable = False
        if source_stable:
            continue
        scan["tainted"] = True
        candidate.pop(aid, None)
        scan["sources"].pop(aid, None)
        scan["displays"].pop(aid, None)
        scan["partial_limits"] = [
            value for value in scan["partial_limits"] if value != aid]
        evs.append(_source_entry_refusal_event(
            "agents", f"agent usage record {source_capture['name']}"))

    for aid, row in candidate.items():
        prior = state.get(aid, {})
        if not isinstance(prior, dict):
            raise ValueError("agent usage cursor is invalid")
        evs.extend(_agent_transition_events(
            aid, scan["displays"][aid], prior, row))

    if scan["tainted"]:
        merged = copy.deepcopy(state)
        for aid, row in candidate.items():
            if aid in merged or len(merged) < MAX_SOURCE_SCAN_ENTRIES:
                admitted = copy.deepcopy(row)
                if aid in scan["partial_limits"]:
                    prior_row = merged.get(aid, {})
                    prior_limits = prior_row.get("limits", {}) \
                        if isinstance(prior_row, dict) else {}
                    if not isinstance(prior_limits, dict):
                        raise ValueError("agent usage cursor is invalid")
                    observed_limits = admitted["limits"]
                    admitted["limits"] = copy.deepcopy(prior_limits)
                    admitted["limits"].update(observed_limits)
                merged[aid] = admitted
            else:
                evs.append(_source_entry_refusal_event(
                    "agents", f"agent usage identity {aid}"))
        _store_agent_state(cursors, merged)
    else:
        _store_agent_state(cursors, candidate)
    cursors.pop(page_key, None)
    cursors.pop(scan_key, None)
    return evs


def _configured_skill_roots():
    return _configured_skill_root_paths()




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


_SKILL_MANIFEST_ABSENCE_ERRNOS = frozenset({
    _errno.ENOENT, _errno.ENOTDIR, _errno.ELOOP})


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
        try:
            skill_fd = os.open(name, directory_flags, dir_fd=root_fd)
        except OSError as exc:
            if exc.errno in _SKILL_MANIFEST_ABSENCE_ERRNOS:
                raise FileNotFoundError(
                    _errno.ENOENT, "skill directory is absent") from exc
            raise RuntimeError("skill directory could not be inspected") \
                from exc
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
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0), dir_fd=skill_fd)
        except OSError as exc:
            try:
                stable_absence = containers_stable()
            except OSError:
                stable_absence = False
            if not stable_absence:
                raise RuntimeError(
                    "skill manifest path changed while inspected") from exc
            if exc.errno in _SKILL_MANIFEST_ABSENCE_ERRNOS:
                raise FileNotFoundError(
                    _errno.ENOENT, "skill manifest is absent") from exc
            raise RuntimeError(
                "skill manifest could not be inspected") from exc
        before = os.fstat(manifest_fd)
        if not stat.S_ISREG(before.st_mode):
            raise FileNotFoundError(
                _errno.ENOENT, "skill manifest is not a regular file")
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
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0), dir_fd=skill_fd)
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


def _list_skill_entries(root, page_state=None):
    entries, complete, _inspected, page = _bounded_source_entries(
        root, page_state,
        limit=MAX_SKILL_SNAPSHOT_ENTRIES)
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
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0), dir_fd=skill_fd)
        manifest_before = os.fstat(manifest_fd)
        current_root = _source_path_identity(root, directory_flags)
        current_skill_fd = os.open(name, directory_flags, dir_fd=root_fd)
        current_skill = os.fstat(current_skill_fd)
        current_manifest_fd = os.open(
            "SKILL.md", os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0), dir_fd=skill_fd)
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


_SKILL_SCAN_SCHEMA_V1 = "sia-skill-catalog-scan-v1"
_SKILL_SCAN_SCHEMA = "sia-skill-catalog-scan-v2"
_SKILL_ROOT_HISTORY_SCHEMA = "sia-skill-root-history-v1"


def _skill_root_id(root):
    return hashlib.sha256(_skill_name_bytes(root)).hexdigest()


def _validated_skill_root_history(value, root_ids, snapshot, *, present=True):
    """Load exact root-presence history and seed upgrades from provenance."""
    if not present:
        stored = []
    elif isinstance(value, list) and len(value) == 2 \
            and value[0] == _SKILL_ROOT_HISTORY_SCHEMA \
            and isinstance(value[1], list) \
            and len(value[1]) <= MAX_CONFIG_TAGS \
            and all(isinstance(root_id, str)
                    and re.fullmatch(r"[0-9a-f]{64}", root_id) is not None
                    for root_id in value[1]) \
            and len(value[1]) == len(set(value[1])):
        stored = value[1]
    else:
        raise ValueError("skill catalog state is invalid")
    known = set(stored)
    for state in snapshot.values():
        for row in state["roots"]:
            known.add(row["root_id"])
    return [root_id for root_id in root_ids if root_id in known]


def _new_skill_scan(root_ids, prior_truncated=False, prior_guard=False,
                    known_roots=()):
    return {
        "schema": _SKILL_SCAN_SCHEMA, "roots": list(root_ids),
        "root_index": 0, "page": None, "entries": [], "rows": [],
        "tainted_roots": [], "truncated_roots": [],
        "known_roots": list(known_roots), "absent_roots": [],
        "completed_roots": [],
        "prior_truncated": bool(prior_truncated),
        "prior_removal_guard": bool(prior_guard),
    }


def _skill_manifest_state_valid(value):
    if not isinstance(value, dict) \
            or set(value) != {
                "device", "inode", "mode", "uid", "size", "mtime_ns",
                "ctime_ns", "head_bytes", "head_truncated", "head_sha256",
            } \
            or any(isinstance(value[field], bool)
                   or not isinstance(value[field], int)
                   or value[field] < 0
                   for field in (
                       "device", "inode", "mode", "uid", "size",
                       "mtime_ns", "ctime_ns", "head_bytes")) \
            or not stat.S_ISREG(value["mode"]) \
            or value["head_bytes"] \
            != min(value["size"], MAX_SKILL_MANIFEST_HEAD_BYTES) \
            or not isinstance(value["head_truncated"], bool) \
            or value["head_truncated"] \
            != (value["size"] > value["head_bytes"]) \
            or not isinstance(value["head_sha256"], str) \
            or re.fullmatch(
                r"[0-9a-f]{64}", value["head_sha256"]) is None:
        return False
    return True


def _migrated_legacy_skill_state(skill, value):
    """Recognize the old positive-only row without inheriting its roots."""
    if not isinstance(value, dict) \
            or set(value) != {"mtime", "name", "roots"}:
        return None
    name = value.get("name")
    roots = value.get("roots")
    mtime = value.get("mtime")
    name_bytes = _skill_name_bytes(name) if isinstance(name, str) else b""
    if isinstance(mtime, bool) or not isinstance(mtime, int) or mtime < 0 \
            or not _strict_config_string(
                name, nonempty=True, limit=MAX_CONFIG_TEXT_CHARS) \
            or not name_bytes or name_bytes in {b".", b".."} \
            or b"/" in name_bytes or b"\0" in name_bytes \
            or len(name_bytes) > MAX_CORPUS_COMPONENT_BYTES \
            or sanitize_slugpart(name) != skill \
            or not isinstance(roots, list) \
            or len(roots) > MAX_CONFIG_TAGS \
            or any(not _strict_config_string(
                root, nonempty=True, limit=MAX_CONFIG_PATH_CHARS)
                   for root in roots) \
            or len(roots) != len(set(roots)):
        raise ValueError("skill catalog state is invalid")
    return {
        "name": _skill_display_name(name),
        "name_id": hashlib.sha256(name_bytes).hexdigest(),
        "description": "",
        # Legacy root strings were followed-path labels, not descriptor-bound
        # provenance. A current scan must earn every replacement root row.
        "roots": [],
    }


def _validated_skill_snapshot(value):
    """Validate the exact authoritative catalog before any scan mutates it."""
    if not isinstance(value, dict) \
            or len(value) > MAX_SKILL_SNAPSHOT_ENTRIES:
        raise ValueError("skill catalog state is invalid")
    validated = {}
    for skill, state in value.items():
        if not isinstance(skill, str) \
                or re.fullmatch(
                    r"[a-z0-9_][a-z0-9._-]*", skill) is None \
                or len(skill) > MAX_SOURCE_NAME_CHARS \
                or len(skill.encode("utf-8")) > MAX_CORPUS_LEAF_BYTES:
            raise ValueError("skill catalog state is invalid")
        legacy = _migrated_legacy_skill_state(skill, state)
        if legacy is not None:
            validated[skill] = legacy
            continue
        if not isinstance(state, dict) \
                or set(state) != {
                    "name", "name_id", "description", "roots"} \
                or not _strict_config_string(
                    state["name"], nonempty=True,
                    limit=MAX_CONFIG_TEXT_CHARS) \
                or not isinstance(state["name_id"], str) \
                or re.fullmatch(r"[0-9a-f]{64}", state["name_id"]) is None \
                or not _strict_config_string(
                    state["description"], limit=220) \
                or not isinstance(state["roots"], list) \
                or len(state["roots"]) > MAX_CONFIG_TAGS:
            raise ValueError("skill catalog state is invalid")
        seen_roots = set()
        for row in state["roots"]:
            if not isinstance(row, dict) \
                    or set(row) != {
                        "root_id", "description", "manifest"} \
                    or not isinstance(row["root_id"], str) \
                    or re.fullmatch(
                        r"[0-9a-f]{64}", row["root_id"]) is None \
                    or row["root_id"] in seen_roots \
                    or not _strict_config_string(
                        row["description"], limit=220) \
                    or not _skill_manifest_state_valid(row["manifest"]):
                raise ValueError("skill catalog state is invalid")
            seen_roots.add(row["root_id"])
        validated[skill] = state
    return validated


def _validated_skill_scan(value, root_ids, prior_truncated=False,
                          prior_guard=False, known_root_ids=None, *,
                          present=True):
    """Validate the bounded continuation for one configured root roster."""
    if not present:
        return _new_skill_scan(
            root_ids, prior_truncated, prior_guard,
            known_root_ids or ())
    if not isinstance(value, dict):
        raise ValueError("skill catalog scan cursor is invalid")
    if value.get("roots") != list(root_ids):
        return _new_skill_scan(
            root_ids, prior_truncated, prior_guard,
            known_root_ids or ())
    schema = value.get("schema")
    if schema not in {_SKILL_SCAN_SCHEMA_V1, _SKILL_SCAN_SCHEMA}:
        return _new_skill_scan(
            root_ids, prior_truncated, prior_guard,
            known_root_ids or ())
    legacy = schema == _SKILL_SCAN_SCHEMA_V1
    expected_fields = {
            "schema", "roots", "root_index", "page", "rows",
            "tainted_roots", "truncated_roots", "prior_truncated",
            "prior_removal_guard"}
    if not legacy:
        expected_fields.update({
            "entries", "known_roots", "absent_roots", "completed_roots"})
    if set(value) != expected_fields:
        raise ValueError("skill catalog scan cursor is invalid")
    index = value.get("root_index")
    rows = value.get("rows")
    tainted = value.get("tainted_roots")
    truncated = value.get("truncated_roots")
    if isinstance(index, bool) or not isinstance(index, int) \
            or index < 0 or index >= len(root_ids) \
            or not isinstance(rows, list) \
            or len(rows) > MAX_SKILL_SNAPSHOT_ENTRIES \
            or not isinstance(tainted, list) \
            or not isinstance(truncated, list) \
            or not isinstance(value.get("prior_truncated"), bool) \
            or not isinstance(value.get("prior_removal_guard"), bool) \
            or len(tainted) > len(root_ids) \
            or len(truncated) > len(root_ids) \
            or any(not isinstance(root_id, str)
                   for root_id in tainted + truncated) \
            or len(set(tainted)) != len(tainted) \
            or len(set(truncated)) != len(truncated) \
            or any(root_id not in root_ids
                   for root_id in tainted + truncated):
        raise ValueError("skill catalog scan cursor is invalid")
    page = value.get("page")
    if page is not None:
        _validated_source_page_state(page)
        _source_tree_directory_generation(page)
        if page.get("cookie", 0) <= 0:
            raise ValueError("skill catalog scan cursor is invalid")
    else:
        # Persisted candidates are written only at a partial directory page;
        # a missing cookie cannot justify retaining their prefix.
        raise ValueError("skill catalog scan cursor is invalid")
    prior_roots = set(root_ids[:index])
    reached_roots = set(root_ids[:index + 1])
    if any(root_id not in prior_roots for root_id in tainted) \
            or any(root_id not in reached_roots for root_id in truncated):
        raise ValueError("skill catalog scan cursor is invalid")
    row_keys = set()
    for row in rows:
        name_bytes = _skill_name_bytes(row.get("name", "")) \
            if isinstance(row, dict) else b""
        manifest = row.get("manifest") if isinstance(row, dict) else None
        if not isinstance(row, dict) \
                or set(row) != {
                    "root_id", "name", "name_id", "description",
                    "manifest"} \
                or row["root_id"] not in reached_roots \
                or row["root_id"] in tainted \
                or not isinstance(row["name"], str) \
                or not name_bytes or name_bytes in {b".", b".."} \
                or b"/" in name_bytes or b"\0" in name_bytes \
                or len(name_bytes) > MAX_CORPUS_COMPONENT_BYTES \
                or not isinstance(row["name_id"], str) \
                or re.fullmatch(r"[0-9a-f]{64}", row["name_id"]) is None \
                or row["name_id"] != hashlib.sha256(name_bytes).hexdigest() \
                or not isinstance(row["description"], str) \
                or len(row["description"]) > 220 \
                or not _skill_manifest_state_valid(manifest):
            raise ValueError("skill catalog scan cursor is invalid")
        row_key = (row["root_id"], row["name_id"])
        if row_key in row_keys:
            raise ValueError("skill catalog scan cursor is invalid")
        row_keys.add(row_key)
    if legacy:
        known = set(known_root_ids or ())
        known.update(row["root_id"] for row in rows)
        known.add(root_ids[index])
        known.update(root_id for root_id in root_ids[:index]
                     if root_id not in tainted)
        # V1 retained neither negative child coverage nor completed-root
        # generations. Its private candidate cannot be upgraded into exact
        # removal authority, so restart it while preserving observed roots
        # and the pre-scan guard state.
        return _new_skill_scan(
            root_ids, value["prior_truncated"],
            value["prior_removal_guard"],
            [root_id for root_id in root_ids if root_id in known])
    known = value.get("known_roots")
    absent = value.get("absent_roots")
    if not isinstance(known, list) \
            or len(known) > MAX_CONFIG_TAGS \
            or any(root_id not in root_ids for root_id in known) \
            or len(known) != len(set(known)) \
            or known != [root_id for root_id in root_ids
                          if root_id in set(known)] \
            or root_ids[index] not in known \
            or any(row["root_id"] not in known for row in rows) \
            or known_root_ids is not None \
            and known != list(known_root_ids):
        raise ValueError("skill catalog scan cursor is invalid")
    entries = value.get("entries")
    entry_names = {}
    if not isinstance(entries, list) \
            or len(entries) > MAX_SKILL_SNAPSHOT_ENTRIES:
        raise ValueError("skill catalog scan cursor is invalid")
    for entry in entries:
        name_bytes = _skill_name_bytes(entry.get("name", "")) \
            if isinstance(entry, dict) else b""
        if not isinstance(entry, dict) \
                or set(entry) != {"root_id", "name", "name_id"} \
                or entry["root_id"] not in reached_roots \
                or entry["root_id"] in tainted \
                or not isinstance(entry["name"], str) \
                or not name_bytes or name_bytes in {b".", b".."} \
                or b"/" in name_bytes or b"\0" in name_bytes \
                or len(name_bytes) > MAX_CORPUS_COMPONENT_BYTES \
                or not isinstance(entry["name_id"], str) \
                or re.fullmatch(
                    r"[0-9a-f]{64}", entry["name_id"]) is None \
                or entry["name_id"] \
                != hashlib.sha256(name_bytes).hexdigest():
            raise ValueError("skill catalog scan cursor is invalid")
        entry_key = (entry["root_id"], entry["name_id"])
        if entry_key in entry_names:
            raise ValueError("skill catalog scan cursor is invalid")
        entry_names[entry_key] = entry["name"]
    if any(row_key not in entry_names for row_key in row_keys) \
            or any(entry_names[(row["root_id"], row["name_id"])]
                   != row["name"] for row in rows):
        raise ValueError("skill catalog scan cursor is invalid")
    completed = value.get("completed_roots")
    if not isinstance(completed, list) \
            or len(completed) > MAX_CONFIG_TAGS:
        raise ValueError("skill catalog scan cursor is invalid")
    completed_ids = []
    generation_fields = set(SOURCE_TREE_GENERATION_FIELDS)
    for completion in completed:
        if not isinstance(completion, dict) \
                or set(completion) != {"root_id", "generation"} \
                or completion["root_id"] not in prior_roots \
                or completion["root_id"] in completed_ids \
                or not isinstance(completion["generation"], dict) \
                or set(completion["generation"]) != generation_fields:
            raise ValueError("skill catalog scan cursor is invalid")
        try:
            _source_tree_directory_generation(completion["generation"])
        except ValueError as exc:
            raise ValueError(
                "skill catalog scan cursor is invalid") from exc
        completed_ids.append(completion["root_id"])
    if completed_ids != [root_id for root_id in root_ids
                          if root_id in set(completed_ids)]:
        raise ValueError("skill catalog scan cursor is invalid")
    if not isinstance(absent, list) \
            or len(absent) > MAX_CONFIG_TAGS \
            or any(root_id not in root_ids for root_id in absent) \
            or len(absent) != len(set(absent)) \
            or absent != [root_id for root_id in root_ids
                           if root_id in set(absent)] \
            or any(root_id not in prior_roots for root_id in absent) \
            or set(absent) & (set(known) | set(tainted)
                              | set(truncated)) \
            or set(completed_ids) & (set(absent) | set(tainted)) \
            or any(root_id not in set(absent) | set(tainted)
                   | set(completed_ids) for root_id in prior_roots) \
            or any(root_id not in known for root_id in completed_ids) \
            or any(entry["root_id"] != root_ids[index]
                   and entry["root_id"] not in completed_ids
                   for entry in entries):
        raise ValueError("skill catalog scan cursor is invalid")
    return value


def _discard_skill_root_candidate(scan, root_id):
    scan["rows"] = [
        row for row in scan["rows"] if row["root_id"] != root_id]
    scan["entries"] = [
        row for row in scan["entries"] if row["root_id"] != root_id]
    scan["tainted_roots"] = [
        value for value in scan["tainted_roots"] if value != root_id]
    scan["truncated_roots"] = [
        value for value in scan["truncated_roots"] if value != root_id]
    scan["absent_roots"] = [
        value for value in scan["absent_roots"] if value != root_id]
    scan["completed_roots"] = [
        value for value in scan["completed_roots"]
        if value["root_id"] != root_id]


def _skill_root_refusal(root, timestamp=None):
    timestamp = utcnow() if timestamp is None else timestamp
    return Event(
        "skills", timestamp, "source-refused",
        f"skill root could not be read as one stable snapshot: "
        f"{clip(_skill_display_name(root), 220)}",
        {"organs/skills"}, {"skills", "refusal"},
        occurrence=("skills:source-refused:" +
                    _source_entity_token(root, "skill-root")))


def _skill_snapshot_from_rows(rows):
    """Project captured root/name rows into the bounded public snapshot."""
    snap = {}
    for row in rows:
        name = row["name"]
        raw_id = row["name_id"]
        skill = _skill_entity_token(name)
        if skill in snap and snap[skill].get("name_id") != raw_id:
            skill = "skill-" + raw_id
        if skill not in snap and len(snap) >= MAX_SKILL_SNAPSHOT_ENTRIES:
            raise ValueError("skill catalog projection exceeds its bound")
        cur = snap.setdefault(
            skill, {"name": _skill_display_name(name),
                    "name_id": raw_id, "description": "", "roots": []})
        root_row = {
            "root_id": row["root_id"],
            "description": row["description"],
            "manifest": row["manifest"],
        }
        if not any(existing.get("root_id") == row["root_id"]
                   for existing in cur["roots"]
                   if isinstance(existing, dict)):
            cur["roots"].append(root_row)
        if not cur["description"] and row["description"]:
            cur["description"] = row["description"]
    return snap


def _skill_positive_merge(previous, observed, unresolved_root_ids, root_ids):
    """Overlay positives while retaining unresolved root provenance.

    A partial aggregate can prove the state of each successfully completed
    root, but it cannot replace provenance previously captured from a root
    that was refused or exceeded the aggregate bound.  Preserve those root
    rows, overlay every observed row for the same root, then rebuild root and
    description order from the configured root roster.
    """
    unresolved = set(unresolved_root_ids)
    merged = {}
    overflow = []

    def project(skill, prior, current):
        prior_roots = prior.get("roots", [])
        current_roots = current.get("roots", []) \
            if isinstance(current, dict) else []
        by_root = {}
        if isinstance(prior_roots, list):
            for row in prior_roots:
                prior_root_id = row.get("root_id") \
                    if isinstance(row, dict) else None
                if isinstance(prior_root_id, str) \
                        and prior_root_id in unresolved:
                    by_root.setdefault(
                        prior_root_id, copy.deepcopy(row))
        if isinstance(current_roots, list):
            for row in current_roots:
                current_root_id = row.get("root_id") \
                    if isinstance(row, dict) else None
                if isinstance(current_root_id, str) \
                        and current_root_id in root_ids:
                    by_root[current_root_id] = copy.deepcopy(row)
        combined = copy.deepcopy(
            current if isinstance(current, dict) else prior)
        combined["name"] = _skill_display_name(
            combined.get("name", skill))
        combined["roots"] = [by_root[root_id] for root_id in root_ids
                             if root_id in by_root]
        combined["description"] = next((
            row.get("description", "") for row in combined["roots"]
            if isinstance(row.get("description", ""), str)
            and row.get("description", "")), "")
        return combined

    for skill, prior in previous.items():
        if not isinstance(skill, str) or not isinstance(prior, dict):
            continue
        if len(merged) >= MAX_SKILL_SNAPSHOT_ENTRIES:
            overflow.append(skill)
            continue
        merged[skill] = project(skill, prior, observed.get(skill))
    for skill, current in observed.items():
        if skill in merged:
            continue
        if len(merged) >= MAX_SKILL_SNAPSHOT_ENTRIES:
            overflow.append(skill)
            continue
        merged[skill] = project(skill, {}, current)
    return merged, overflow


def _skill_catalog_event(kind, skill, source_state, timestamp):
    label = _skill_display_name(source_state.get("name", skill))
    desc = source_state.get("description", "") \
        if isinstance(source_state, dict) else ""
    source_id = hashlib.sha256(json.dumps(
        source_state, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("utf-8")).hexdigest()
    if kind == "cataloged":
        summary = f"cataloged installed skill: {clip(label, 220)}" \
            + (f" — {desc}" if desc else "")
        tags = {"skills", "cataloged"}
    else:
        summary = f"skill {kind}: {clip(label, 220)}" \
            + (f" — {desc}" if desc else "")
        tags = {"skills", kind}
    return Event(
        "skills", timestamp, kind, summary,
        {"organs/skills", f"skills/{skill}"}, tags,
        occurrence=f"skills:{kind}:{skill}:{source_id}")


def sense_skills(cursors):
    """Scan skill roots through a resumable, generation-stable aggregate.

    Each pulse reads at most one bounded page from the current root. Positive
    captures and negative child-name coverage stay private in a cursor
    candidate until every configured root reaches a stable EOF. A
    root-generation reset drops that root's earlier captures. Completed roots
    are revalidated across the aggregate boundary. Refused or over-cap
    aggregates may add/update observations, but never use missing rows as
    evidence of removal.
    """
    if "skills.snapshot" in cursors:
        prev = _validated_skill_snapshot(cursors["skills.snapshot"])
    else:
        prev = None
    for flag in (
            "skills.truncated", "skills.partial", "skills.removal_guard"):
        if flag in cursors and not isinstance(cursors[flag], bool):
            raise ValueError("skill catalog state is invalid")
    skill_roots = []
    root_ids = []
    for root in SKILL_ROOTS:
        root_id = _skill_root_id(root)
        if root_id in root_ids:
            continue
        skill_roots.append(root)
        root_ids.append(root_id)
    root_history_key = "skills.root_history"
    known_root_ids = _validated_skill_root_history(
        cursors.get(root_history_key), root_ids, prev or {},
        present=root_history_key in cursors)
    scan_key = "skills.scan"
    prior_truncated = cursors.get("skills.truncated", False)
    prior_guard = cursors.get(
        "skills.removal_guard",
        cursors.get("skills.partial", prior_truncated))
    scan = _validated_skill_scan(
        cursors.get(scan_key), root_ids, prior_truncated, prior_guard,
        known_root_ids, present=scan_key in cursors)
    known_roots = set(scan["known_roots"])
    evs = []

    while scan["root_index"] < len(skill_roots):
        root_index = scan["root_index"]
        root = skill_roots[root_index]
        root_id = root_ids[root_index]
        page_before = scan["page"]
        try:
            entries, root_truncated, next_page = _list_skill_entries(
                root, page_before)
        except FileNotFoundError:
            _discard_skill_root_candidate(scan, root_id)
            if root_id in known_roots:
                if root_id not in scan["tainted_roots"]:
                    scan["tainted_roots"].append(root_id)
                evs.append(_skill_root_refusal(root))
            elif root_id not in scan["absent_roots"]:
                scan["absent_roots"].append(root_id)
            scan["root_index"] += 1
            scan["page"] = None
            continue
        except (OSError, RuntimeError, ValueError):
            _discard_skill_root_candidate(scan, root_id)
            if root_id not in scan["tainted_roots"]:
                scan["tainted_roots"].append(root_id)
            evs.append(_skill_root_refusal(root))
            scan["root_index"] += 1
            scan["page"] = None
            continue
        known_roots.add(root_id)
        scan["known_roots"] = [
            value for value in root_ids if value in known_roots]

        if next_page.get("reset"):
            # `_bounded_source_entries` already returned a page from the new
            # root generation. Discard every capture tied to the old cookie
            # before considering that returned page.
            _discard_skill_root_candidate(scan, root_id)

        page_rows = []
        manifest_unstable = False
        for name in entries:
            try:
                capture = _read_skill_manifest(root, name)
            except FileNotFoundError:
                continue
            except RuntimeError:
                manifest_unstable = True
                break
            except OSError:
                manifest_unstable = True
                break
            page_rows.append((name, capture))
        try:
            root_stable = _skill_root_generation_matches(root, next_page)
        except (OSError, RuntimeError, ValueError):
            root_stable = False
        if root_stable and not manifest_unstable:
            for name, capture in page_rows:
                try:
                    current = _skill_manifest_capture_matches(
                        root, name, capture)
                except (OSError, RuntimeError, ValueError):
                    current = False
                if not current:
                    manifest_unstable = True
                    break
        if manifest_unstable or not root_stable:
            _discard_skill_root_candidate(scan, root_id)
            if root_id not in scan["tainted_roots"]:
                scan["tainted_roots"].append(root_id)
            evs.append(_skill_root_refusal(root))
            scan["root_index"] += 1
            scan["page"] = None
            continue

        page_captures = {name: capture for name, capture in page_rows}
        for name in entries:
            raw_id = hashlib.sha256(_skill_name_bytes(name)).hexdigest()
            covered = next((
                entry for entry in scan["entries"]
                if entry["root_id"] == root_id
                and entry["name_id"] == raw_id), None)
            if covered is None:
                if len(scan["entries"]) >= MAX_SKILL_SNAPSHOT_ENTRIES:
                    if root_id not in scan["truncated_roots"]:
                        scan["truncated_roots"].append(root_id)
                        evs.append(_source_entry_refusal_event(
                            "skills", "skill root entry coverage for "
                            f"{_skill_display_name(root)}"))
                    continue
                scan["entries"].append({
                    "root_id": root_id, "name": name, "name_id": raw_id})
            capture = page_captures.get(name)
            if capture is None:
                continue
            duplicate = next((
                row for row in scan["rows"]
                if row["root_id"] == root_id and row["name_id"] == raw_id),
                None)
            row = {
                "root_id": root_id, "name": name, "name_id": raw_id,
                "description": capture["description"],
                "manifest": capture["manifest"],
            }
            if duplicate is not None:
                scan["rows"][scan["rows"].index(duplicate)] = row
            elif len(scan["rows"]) < MAX_SKILL_SNAPSHOT_ENTRIES:
                scan["rows"].append(row)
            else:
                if root_id not in scan["truncated_roots"]:
                    scan["truncated_roots"].append(root_id)
                evs.append(_source_entry_refusal_event(
                    "skills", "skill manifest "
                    f"{_skill_display_name(name)} in "
                    f"{_skill_display_name(root)}"))

        if root_truncated:
            scan["page"] = next_page
            cursors[scan_key] = scan
            cursors[root_history_key] = [
                _SKILL_ROOT_HISTORY_SCHEMA,
                [value for value in root_ids if value in known_roots],
            ]
            cursors["skills.partial"] = True
            cursors["skills.truncated"] = bool(
                scan["truncated_roots"]
                or len(scan["entries"]) >= MAX_SKILL_SNAPSHOT_ENTRIES)
            return evs

        # EOF validates every manifest captured from earlier pages too; a
        # child-file rewrite does not necessarily change the root directory's
        # own generation and therefore cannot be detected by its cookie alone.
        root_rows = [row for row in scan["rows"]
                     if row["root_id"] == root_id]
        for row in root_rows:
            capture = {"description": row["description"],
                       "manifest": row["manifest"]}
            try:
                current = _skill_manifest_capture_matches(
                    root, row["name"], capture)
            except (OSError, RuntimeError, ValueError):
                current = False
            if not current:
                manifest_unstable = True
                break
        if manifest_unstable:
            _discard_skill_root_candidate(scan, root_id)
            if root_id not in scan["tainted_roots"]:
                scan["tainted_roots"].append(root_id)
            evs.append(_skill_root_refusal(root))
        else:
            scan["completed_roots"].append({
                "root_id": root_id,
                "generation": _source_tree_directory_generation(next_page),
            })
        scan["root_index"] += 1
        scan["page"] = None

    # A clean optional-root absence has no filesystem generation to retain.
    # Recheck every such absence after the last root reaches EOF; if a root
    # appeared (or can no longer be classified as absent), this aggregate is
    # incomplete and therefore cannot authorize a removal.
    directory_flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                       | getattr(os, "O_NOFOLLOW", 0)
                       | getattr(os, "O_DIRECTORY", 0))
    roots_by_id = dict(zip(root_ids, skill_roots))
    for root_id in list(scan["absent_roots"]):
        root = roots_by_id[root_id]
        try:
            descriptor = _open_source_nofollow(root, directory_flags)
        except FileNotFoundError:
            continue
        except (OSError, RuntimeError, ValueError):
            pass
        else:
            os.close(descriptor)
            known_roots.add(root_id)
        scan["absent_roots"] = [
            value for value in scan["absent_roots"] if value != root_id]
        if root_id not in scan["tainted_roots"]:
            scan["tainted_roots"].append(root_id)
        evs.append(_skill_root_refusal(root))

    # Completed roots also need a final aggregate-bound check. Directory
    # generation proves that the enumerated child-name set did not change;
    # replaying every bounded child covers both captured manifests and stable
    # negative observations where SKILL.md was absent or inadmissible.
    for completion in list(scan["completed_roots"]):
        root_id = completion["root_id"]
        root = roots_by_id[root_id]
        generation = completion["generation"]
        try:
            root_current = _skill_root_generation_matches(root, generation)
        except (OSError, RuntimeError, ValueError):
            root_current = False
        expected_rows = {
            (row["root_id"], row["name_id"]): row
            for row in scan["rows"] if row["root_id"] == root_id}
        if root_current:
            for entry in scan["entries"]:
                if entry["root_id"] != root_id:
                    continue
                expected = expected_rows.get((root_id, entry["name_id"]))
                try:
                    capture = _read_skill_manifest(root, entry["name"])
                except FileNotFoundError:
                    if expected is not None:
                        root_current = False
                        break
                    continue
                except RuntimeError:
                    root_current = False
                    break
                except OSError:
                    root_current = False
                    break
                current = {
                    "description": capture["description"],
                    "manifest": capture["manifest"],
                }
                if expected is None or current != {
                        "description": expected["description"],
                        "manifest": expected["manifest"]}:
                    root_current = False
                    break
        if root_current:
            try:
                root_current = _skill_root_generation_matches(
                    root, generation)
            except (OSError, RuntimeError, ValueError):
                root_current = False
        if not root_current:
            _discard_skill_root_candidate(scan, root_id)
            if root_id not in scan["tainted_roots"]:
                scan["tainted_roots"].append(root_id)
            evs.append(_skill_root_refusal(root))

    observed = _skill_snapshot_from_rows(scan["rows"])
    partial = bool(scan["tainted_roots"] or scan["truncated_roots"])
    prior_partial = scan["prior_removal_guard"]
    prior_truncated = scan["prior_truncated"]
    overflow = []
    if prev is not None and (partial or prior_partial):
        unresolved_roots = set(scan["tainted_roots"]) \
            | set(scan["truncated_roots"])
        snap, overflow = _skill_positive_merge(
            prev, observed, unresolved_roots, root_ids)
        if overflow:
            partial = True
    else:
        snap = observed
    cursors["skills.snapshot"] = snap
    cursors["skills.truncated"] = bool(
        scan["truncated_roots"] or overflow)
    cursors["skills.partial"] = partial
    cursors["skills.removal_guard"] = partial
    cursors[root_history_key] = [
        _SKILL_ROOT_HISTORY_SCHEMA,
        [value for value in root_ids if value in known_roots],
    ]
    cursors.pop(scan_key, None)

    for skill in overflow:
        source = observed.get(skill, prev.get(skill) if prev else {})
        label = source.get("name", skill) if isinstance(source, dict) else skill
        evs.append(_source_entry_refusal_event(
            "skills", f"skill snapshot identity {label}"))

    ts = utcnow()
    if prev is None:
        for skill in sorted(snap):
            evs.append(_skill_catalog_event(
                "cataloged", skill, snap[skill], ts))
    else:
        removed = (set() if partial or prior_partial
                   else set(prev) - set(snap))
        for kind, names in (
                ("installed", sorted(set(snap) - set(prev))),
                ("removed", sorted(removed)),
                ("updated", sorted(
                    skill for skill in set(snap) & set(prev)
                    if skill in observed
                    and snap[skill] != prev[skill]))):
            for skill in names:
                source_state = snap.get(skill, prev.get(skill))
                evs.append(_skill_catalog_event(
                    kind, skill, source_state, ts))
    if cursors["skills.truncated"] and not prior_truncated:
        evs.append(Event(
            "skills", ts, "catalog-truncated",
            "skill catalog exceeded its bounded snapshot; later entries "
            "were observed but could not be retained", {"organs/skills"},
            {"skills", "refusal"},
            occurrence="skills:catalog-truncated"))
    return evs


def _parse_custom_json_record(line):
    """Parse/classify one decoded JSONL row at its physical boundary."""
    try:
        value = _strict_json_loads(line)
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
    return _validated_custom_match_literals(value, field=field)


def sense_custom(cursors, include_sources=False, *, entry_index=None,
                 seen_names=None):
    """User-defined evidence streams from config custom_senses: tail a
    log (lines or jsonl), match a pattern, and emit events through the user's
    own source adapter. This is how anyone points SIA at their programs."""
    evs, successful = [], []
    disable_policy = _configured_disabled_sense_policy()
    config_errors = (copy.deepcopy(CONFIG_ERRORS)
                     if entry_index in (None, 0) else [])
    if not isinstance(CONFIG, dict):
        result = ([], config_errors)
        return (*result, successful) if include_sources else result
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
            normalized = _validated_custom_sense_entry(cs)
            if normalized is None:
                continue
            if _custom_sense_disabled(normalized, disable_policy):
                continue
            description = normalized["description"]
            name = normalized["name"]
            label = name
            source_id = normalized["source_id"]
            if name in seen_names:
                raise ValueError("custom sense names must be unique")
            seen_names.add(name)
            organ = normalized["organ"]
            path = normalized["path"]
            stream_type = normalized["stream_type"]
            match_literals = normalized["match_literals"]
            exclude_literals = normalized["exclude_literals"]
            field = normalized["field"]
            kind = normalized["kind"]
            tags = normalized["tags"]
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
