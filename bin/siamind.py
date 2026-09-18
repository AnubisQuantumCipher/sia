"""siamind — deterministic retrieval-policy state for SIA.

This module implements replayable software operations over local memory:
usage-score calculation, co-return edge reinforcement, retrieval-seeded
Personalized PageRank, novelty and intake-surprise scoring, a bounded
attention window, a seeded distant-node walk, weekly epoch compaction, and
retrieval-only stability plus SM-2 scheduling. These names describe observable
program behavior; they do not establish biological or human mental processes.

The ``ACTR_*``, ``hebb*``, ``WORKSPACE_K``, ``arousal``, ``mind``, and
``workspace`` spellings are compatibility contracts retained for callers and
persisted state. They are not evidence that the similarly named scientific
theories or biological quantities are implemented or measured.

State lives in ~/.local/state/sia/mind.json, owned exclusively by the
brainstem daemon. Other processes (sia ask/recall and the memory CLI)
communicate through a bounded, lock-serialized touch queue; the daemon drains
it each pulse.
"""

import copy, contextlib, fcntl, hashlib, json, math, os, random, re, stat, sys, time, uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import siaqueue

STATE = os.path.expanduser("~/.local/state/sia")
CORPUS = os.path.expanduser("~/.local/share/sia/corpus")
MIND_PATH = os.path.join(STATE, "mind.json")
TOUCH_QUEUE = os.path.join(STATE, "touch-queue.jsonl")
RECOVERY_UNPIN_QUEUE = os.path.join(STATE, "recovery-unpin-queue.jsonl")
TOUCH_QUEUE_REFUSAL_SCHEMA = "sia-touch-queue-tail-refusal-v1"
TOUCH_QUEUE_REFUSAL_NAME = ".touch-queue-tail-refusal.json"
# The runtime has exactly the ordinary-reinforcement and recovery-unpin lanes.
MAX_TOUCH_QUEUE_REFUSAL_SOURCES = 2
MAX_TOUCH_QUEUE_BYTES = 16_777_216
MAX_TOUCH_QUEUE_RECORDS = 65_536
MAX_MIND_BYTES = 16_777_216
MAX_FAMILIARITY_SLUG_CHARS = 2000
MAX_FAMILIARITY_COMPONENT_BYTES = 255
MAX_FAMILIARITY_LEAF_BYTES = 252
MAX_FAMILIARITY_TOKEN_CHARS = 200

# Compatibility names retained for callers; these values configure the local
# usage-score and graph-propagation policies, not scientific model claims.
ACTR_D = 0.5          # usage-score decay exponent
ACTR_K = 5            # retained exact recent-use entries
PPR_DAMPING = 0.5     # graph-propagation damping factor
PPR_ITers = 30
PPR_TIEBREAK_GAIN = 0.15
ACTIVATION_TIEBREAK_GAIN = 0.08
EPISODIC_DAYS = int(os.environ.get("SIA_EPISODIC_DAYS", "14"))
WORKSPACE_K = 7       # compatibility name for the attention-window limit
# Stability is a retrieval lens, never a deletion policy. These defaults and
# the SM-2 constants below are the values frozen in SIA's research spec.
MIND_VERSION = 5
SURPRISE_BASIS = "sia-admitted-intake-v1"
SECONDS_PER_DAY = 86400.0
NODE_STABILITY_DAYS = 30.0
EDGE_STABILITY_DAYS = 7.0
STABILITY_TOUCH_GAIN = 1.6
AROUSAL_STABILITY_GAIN = 1.5
NOVELTY_STABILITY_GAIN = 1.0
RETENTION_DEMOTE = 0.05
SM2_EF_INITIAL = 2.5
SM2_EF_FLOOR = 1.3
SM2_FIRST_INTERVAL = 1
SM2_SECOND_INTERVAL = 6
SM2_IMPORTANCE_AROUSAL = 0.7
# Operational bounds prevent repeated reinforcement or malformed persisted
MAX_STABILITY_DAYS = 36500.0
MAX_REVIEW_INTERVAL_DAYS = 36500
MAX_SM2_EF = 5.0
# (surprise uses an empirical count distribution per band — see
# surprisal_update; there is deliberately no Poisson rate or bit threshold)

# ``arousal`` is the persisted compatibility key for a deterministic
# safety-priority map. It drives window scoring, replay order, and verbatim
# preservation; it is not a biological measurement.
AROUSAL = {
    "integrity-failure": 1.0, "crash": 0.9, "coredump": 0.9,
    "collapse": 0.8, "failed": 0.8, "refusal": 0.7, "urgent": 0.7,
    "healing": 0.6, "guardian": 0.55,
    "upgrade": 0.4, "install": 0.4, "commit": 0.3,
}
SAFETY_TAGS = {"integrity-failure", "crash", "coredump", "collapse",
               "failed", "refusal"}   # always preserve verbatim in compaction

_strict_json_loads = siaqueue.strict_json_loads


def _empty_mind():
    return {"v": MIND_VERSION, "nodes": {}, "edges": {}, "ewma": {},
            "seen": {}, "familiarity_complete": True,
            "familiarity_bootstrap_pending": False,
            "hourbuf": {}, "cooldown": {},
            "surprise_basis": SURPRISE_BASIS,
            "workspace": [], "musing_day": "", "decay": {},
            "rehearsal_cursor": 0,
            "coreturn_applied": {},
            "event_applied": [], "event_batch_applied": None,
            "event_transition_pending": None}


def _finite_float(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label} must be finite") from None
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _canonical_familiarity_token(value, label):
    if not isinstance(value, str) \
            or len(value) > MAX_FAMILIARITY_TOKEN_CHARS \
            or re.fullmatch(r"[a-z0-9_][a-z0-9._-]*", value) is None:
        raise ValueError(f"{label} is not a canonical familiarity token")
    return value


def _canonical_familiarity_entity(value, label="familiarity entity"):
    if not isinstance(value, str) or not value \
            or len(value) > MAX_FAMILIARITY_SLUG_CHARS:
        raise ValueError(f"{label} must be a bounded canonical corpus slug")
    parts = value.split("/")
    if any(re.fullmatch(r"[a-z0-9_][a-z0-9._-]*", part) is None
           for part in parts) \
            or any(len(part.encode("utf-8"))
                   > MAX_FAMILIARITY_COMPONENT_BYTES
                   for part in parts[:-1]) \
            or len(parts[-1].encode("utf-8")) \
            > MAX_FAMILIARITY_LEAF_BYTES:
        raise ValueError(f"{label} is not a canonical corpus slug")
    return value


def _canonical_familiarity_key(value):
    if isinstance(value, str) and value.startswith("pair:"):
        parts = value.split(":")
        if len(parts) != 3:
            raise ValueError("mind familiarity pair identity is invalid")
        _canonical_familiarity_token(
            parts[1], "mind familiarity pair organ")
        _canonical_familiarity_token(
            parts[2], "mind familiarity pair kind")
        return value
    return _canonical_familiarity_entity(value, "mind familiarity key")


def _normalized_familiarity_map(value):
    if not isinstance(value, dict):
        raise ValueError("mind familiarity map must be an object")
    normalized = {}
    for label, stamp in value.items():
        _canonical_familiarity_key(label)
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
            raise ValueError("mind familiarity time must be a JSON number")
        normalized[label] = _finite_float(stamp, "mind familiarity time")
    return normalized


def _bounded_float(value, label, low, high):
    return min(high, max(low, _finite_float(value, label)))


def _stability(value, label):
    number = _finite_float(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be positive")
    return min(MAX_STABILITY_DAYS, number)


def _sm2_review_integer(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("SM-2 review integer is invalid")
    return value


def _last_rt(node, fallback):
    stamps = []
    for entry in node.get("rt", []):
        try:
            stamp = float(entry[0] if isinstance(entry, list) else entry)
            if math.isfinite(stamp):
                stamps.append(stamp)
        except (TypeError, ValueError, IndexError):
            pass
    return max(stamps, default=_finite_float(
        node.get("t0", fallback), "node creation time"))


def _edge_record(value, now):
    """Migrate the v1 ``edge -> weight`` form without discarding weight.

    Old edges had no timestamp.  Giving them the migration timestamp grants one
    full stability window instead of silently demoting the installed graph on
    upgrade.  The daemon persists this exactly once on its next save.
    """
    if isinstance(value, dict):
        rec = value
        try:
            rec["w"] = float(rec.get("w", 0.0))
        except (TypeError, ValueError):
            rec["w"] = 0.0
        if not math.isfinite(rec["w"]):
            raise ValueError("edge weight must be finite")
        rec["s"] = _stability(
            rec.get("s", EDGE_STABILITY_DAYS), "edge stability")
        rec["last_touch"] = _finite_float(
            rec.get("last_touch", now), "edge last-touch time")
        if "pins" not in rec:
            rec["pins"] = []
        elif not isinstance(rec["pins"], list) \
                or any(not isinstance(pin, str) or not pin
                       for pin in rec["pins"]):
            raise ValueError("edge pins must be a list of non-empty strings")
        return rec
    try:
        weight = float(value)
    except (TypeError, ValueError):
        weight = 0.0
    if not math.isfinite(weight):
        raise ValueError("edge weight must be finite")
    return {"w": weight, "s": EDGE_STABILITY_DAYS,
            "last_touch": now, "pins": [], "migrated_v1": True}


def migrate_mind(raw, now=None):
    """Return an in-place, backward-compatible v5 state migration.

    ``now`` is injectable for replay/tests.  Unknown keys are retained so an
    older binary does not erase state belonging to a newer optional organ.
    """
    now = _finite_float(time.time() if now is None else now,
                        "migration time")
    if not isinstance(raw, dict):
        raise ValueError("mind state must be a JSON object")
    raw_version = raw.get("v")
    if "v" in raw and (
            isinstance(raw_version, bool) or not isinstance(raw_version, int)
            or raw_version not in {1, 2, 3, 4, MIND_VERSION}):
        raise ValueError("mind state version is unsupported")
    # Build on a detached JSON-shaped copy and publish back only after every
    # field has passed. Callers never observe a half-migrated rejected state.
    mind = copy.deepcopy(raw)
    familiarity_is_authoritative = raw_version in {4, MIND_VERSION}
    legacy_usage_order = raw_version != MIND_VERSION
    if familiarity_is_authoritative:
        if "familiarity_complete" not in mind \
                or type(mind["familiarity_complete"]) is not bool:
            raise ValueError("mind familiarity completeness must be boolean")
        if "familiarity_bootstrap_pending" not in mind \
                or type(mind["familiarity_bootstrap_pending"]) is not bool:
            raise ValueError(
                "mind familiarity bootstrap marker must be boolean")
        if mind["familiarity_complete"] \
                and mind["familiarity_bootstrap_pending"]:
            raise ValueError(
                "mind familiarity bootstrap cannot already be complete")
    normalized_seen = _normalized_familiarity_map(mind.get("seen", {}))
    if familiarity_is_authoritative \
            and mind["familiarity_bootstrap_pending"] and normalized_seen:
        raise ValueError(
            "mind familiarity bootstrap requires an empty familiarity map")
    mind["seen"] = normalized_seen
    if "coreturn_applied" in mind:
        _coreturn_receipts(mind)
    hourbuf, hist, cooldown = _surprise_cache_candidate(mind)
    mind.update(hourbuf=hourbuf, hist=hist, cooldown=cooldown,
                surprise_basis=SURPRISE_BASIS)
    defaults = _empty_mind()
    for key, value in defaults.items():
        mind.setdefault(key, value)
    if not familiarity_is_authoritative:
        # Older generations did not record whether capacity compaction had
        # removed familiarity. Absence cannot be promoted to completeness.
        mind["familiarity_complete"] = False
        mind["familiarity_bootstrap_pending"] = False
    if not isinstance(mind.get("nodes"), dict):
        raise ValueError("mind nodes must be an object")
    if not isinstance(mind.get("edges"), dict):
        raise ValueError("mind edges must be an object")
    _coreturn_receipts(mind)
    raw_events = mind.get("event_applied")
    if isinstance(raw_events, dict):
        # Brief pre-release builds grouped IDs by page. Flatten that exact
        # state into the compact generation-wide replay guard.
        identities = [identity for values in raw_events.values()
                      if isinstance(values, list) for identity in values]
        if any(not isinstance(values, list)
               for values in raw_events.values()):
            raise ValueError("mind event replay state is invalid")
    elif isinstance(raw_events, list):
        identities = raw_events
    else:
        raise ValueError("mind event replay state must be a list")
    if any(not isinstance(identity, str)
           or re.fullmatch(r"[0-9a-f]{64}", identity) is None
           for identity in identities):
        raise ValueError("mind event replay state is invalid")
    mind["event_applied"] = list(dict.fromkeys(identities))
    batch_identity = mind.get("event_batch_applied")
    if batch_identity is not None \
            and (not isinstance(batch_identity, str)
                 or re.fullmatch(r"[0-9a-f]{32}", batch_identity) is None):
        raise ValueError("mind event batch replay state is invalid")
    rehearsal_cursor = mind.get("rehearsal_cursor")
    if isinstance(rehearsal_cursor, bool) \
            or not isinstance(rehearsal_cursor, int) \
            or rehearsal_cursor < 0:
        raise ValueError("mind rehearsal cursor must be a non-negative integer")
    for slug, node in list(mind["nodes"].items()):
        if not isinstance(node, dict):
            raise ValueError(f"mind node {slug!r} must be an object")
        node["n"] = max(0.0, _finite_float(node.get("n", 0),
                                           "node touch count"))
        node["t0"] = _finite_float(node.get("t0", now),
                                    "node creation time")
        node.setdefault("rt", [])
        if not isinstance(node["rt"], list):
            raise ValueError("node retrieval times must be a list")
        normalized_rt = []
        for entry in node["rt"]:
            if isinstance(entry, list):
                if len(entry) != 2:
                    raise ValueError("node retrieval entry must have two fields")
                stamp = _finite_float(entry[0], "node retrieval time")
                weight = _finite_float(entry[1], "node retrieval weight")
            else:
                stamp = _finite_float(entry, "node retrieval time")
                weight = 1.0
            if weight < 0:
                raise ValueError("node retrieval weight must be non-negative")
            normalized_rt.append([stamp, weight])
        if legacy_usage_order:
            # Older backfills appended native event times after later uses.
            # Weighted uses are compatibility policy, not evidence: preserve
            # every retained use and restore the ordering current touch()
            # already enforces. Creation time must cover the repaired trace.
            normalized_rt.sort(key=lambda entry: entry[0])
            if normalized_rt:
                node["t0"] = min(node["t0"], normalized_rt[0][0])
        previous = node["t0"]
        for stamp, _weight in normalized_rt:
            if stamp < previous or stamp > now:
                raise ValueError(
                    "node retrieval history is not chronological")
            previous = stamp
        node["rt"] = normalized_rt
        node["s"] = _stability(
            node.get("s", NODE_STABILITY_DAYS), "node stability")
        node["last_touch"] = _finite_float(
            node.get("last_touch", _last_rt(node, now)),
            "node last-touch time")
        node["arousal"] = _bounded_float(
            node.get("arousal", 0.0), "node safety-priority field", 0.0, 1.0)
        node["novelty"] = _bounded_float(
            node.get("novelty", 0.0), "node novelty", 0.0, 1.0)
        if "pins" not in node:
            node["pins"] = []
        elif not isinstance(node["pins"], list) \
                or any(not isinstance(pin, str) or not pin
                       for pin in node["pins"]):
            raise ValueError("node pins must be a list of non-empty strings")
        if "signals" not in node:
            node["signals"] = {}
        elif not isinstance(node["signals"], dict):
            raise ValueError("node signals must be an object")
        else:
            if any(not isinstance(source, str) or not source
                   for source in node["signals"]):
                raise ValueError(
                    "node signal names must be non-empty strings")
            node["signals"] = {
                source: _finite_float(stamp, "node signal time")
                for source, stamp in node["signals"].items()
            }
        if "review" in node and not isinstance(node["review"], dict):
            raise ValueError("node review must be an object")
        elif isinstance(node.get("review"), dict):
            review = node["review"]
            review["ef"] = _bounded_float(
                review.get("ef", SM2_EF_INITIAL), "SM-2 ease",
                SM2_EF_FLOOR, MAX_SM2_EF)
            review["reps"] = max(
                0, _sm2_review_integer(review.get("reps", 0)))
            review["interval_days"] = min(
                MAX_REVIEW_INTERVAL_DAYS,
                max(0, _sm2_review_integer(
                    review.get("interval_days", 0))))
            review["due_at"] = _finite_float(
                review.get("due_at", now), "SM-2 due time")
            review["last_review"] = _finite_float(
                review.get("last_review", 0.0), "SM-2 last-review time")
            review["reviews"] = max(
                0, _sm2_review_integer(review.get("reviews", 0)))
            quality = review.get("last_quality")
            if quality is not None:
                review["last_quality"] = max(
                    0, min(5, _sm2_review_integer(quality)))
    for key, value in list(mind["edges"].items()):
        mind["edges"][key] = _edge_record(value, now)
    mind["v"] = MIND_VERSION
    raw.clear()
    raw.update(mind)
    return raw


def load_mind(now=None):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(MIND_PATH, flags)
    except FileNotFoundError:
        mind = _empty_mind()
        # A missing compatibility cache is not itself evidence that no prior
        # event or entity existed. The first admitted graph inventory may
        # distinguish an actually history-free install from lost history.
        mind["familiarity_complete"] = False
        mind["familiarity_bootstrap_pending"] = True
        return mind
    with siaqueue.regular_file_stream(fd, label="mind state") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_nlink != 1 \
                or before.st_size > MAX_MIND_BYTES:
            raise ValueError(
                "mind state is not a bounded private single-link regular file")
        # Older SIA versions created the compatibility file mind.json with the caller's umask. An
        # owned no-follow descriptor can be safely normalized during upgrade.
        if before.st_mode & 0o077:
            os.fchmod(stream.fileno(), 0o600)
            before = os.fstat(stream.fileno())
        raw_bytes = stream.read(MAX_MIND_BYTES + 1)
        after = os.fstat(stream.fileno())
        try:
            target = os.lstat(MIND_PATH)
        except FileNotFoundError as exc:
            raise ValueError("mind state changed while read") from exc
    observed = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns)
    finished = (after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, after.st_ctime_ns)
    current = (target.st_dev, target.st_ino, target.st_size,
               target.st_mtime_ns, target.st_ctime_ns)
    if observed != finished or len(raw_bytes) > MAX_MIND_BYTES \
            or after.st_uid != os.geteuid() or after.st_nlink != 1 \
            or not stat.S_ISREG(target.st_mode) \
            or target.st_uid != os.geteuid() or target.st_nlink != 1 \
            or current != finished:
        raise ValueError("mind state changed while read or exceeds its bound")
    try:
        raw = _strict_json_loads(raw_bytes.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("mind state is unreadable or malformed") from exc
    return migrate_mind(raw, now=now)


def _atomic_state_text(path, text):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    if not isinstance(text, str):
        raise TypeError("atomic state payload must be text")
    siaqueue.fixed_atomic_publish(
        path, text.encode("utf-8", errors="strict"), mode=0o600,
        staging_dir=siaqueue.staging_dir_for(
            path, authority_roots=(STATE,)))


def _mind_text(mind):
    return json.dumps(mind, allow_nan=False)


def compact_mind_for_persistence(mind, max_bytes=None):
    """Bound the rebuildable retrieval-policy cache without deleting evidence.

    Corpus pages and signed ledgers remain authoritative. Only unpinned
    derived associations/nodes are evicted, weakest and oldest first, when
    their JSON projection would otherwise exceed the fixed state-file bound.
    """
    limit = MAX_MIND_BYTES if max_bytes is None else max_bytes
    if isinstance(limit, bool) or not isinstance(limit, int) \
            or limit <= 0 or limit > MAX_MIND_BYTES:
        raise ValueError("mind persistence limit is invalid")
    if "familiarity_complete" not in mind:
        mind["familiarity_complete"] = False
    elif type(mind["familiarity_complete"]) is not bool:
        raise ValueError("mind familiarity completeness must be boolean")
    if "familiarity_bootstrap_pending" not in mind:
        mind["familiarity_bootstrap_pending"] = False
    elif type(mind["familiarity_bootstrap_pending"]) is not bool:
        raise ValueError("mind familiarity bootstrap marker must be boolean")
    if mind["familiarity_complete"] \
            and mind["familiarity_bootstrap_pending"]:
        raise ValueError(
            "mind familiarity bootstrap cannot already be complete")
    encoded_size = len(_mind_text(mind).encode("utf-8"))
    if encoded_size <= limit:
        return {"edges": 0, "nodes": 0, "cache_entries": 0}
    removed_edges = removed_nodes = 0
    removed_cache_entries = 0
    removed_safety_edges = removed_safety_nodes = 0
    removed_slugs = set()
    compact_now = time.time()

    def removed_entry_bytes(key, value, count_before):
        # json.dumps(dict) is the exact representation embedded in the full
        # state. Remove its braces and, when siblings remain, one separator.
        entry = len(json.dumps(
            {key: value}, allow_nan=False).encode("utf-8")) - 2
        return entry + (2 if count_before > 1 else 0)

    def mark_familiarity_incomplete():
        nonlocal encoded_size
        if mind["familiarity_complete"] \
                or mind["familiarity_bootstrap_pending"]:
            mind["familiarity_complete"] = False
            mind["familiarity_bootstrap_pending"] = False
            encoded_size = len(_mind_text(mind).encode("utf-8"))

    def finish_if_bounded():
        nonlocal encoded_size
        if encoded_size > limit:
            return False
        if removed_slugs:
            mind["workspace"] = [
                value for value in mind.get("workspace", [])
                if value not in removed_slugs]
        if removed_edges:
            # The persisted decay report is a derived snapshot of the edge
            # collection.  Once compaction changes that collection, retain no
            # stale counts; callers project a fresh, read-only report from the
            # exact compacted generation.
            mind["decay"] = {}
        mind["capacity"] = {
            "evicted_edges": removed_edges,
            "evicted_nodes": removed_nodes,
            "evicted_safety_edges": removed_safety_edges,
            "evicted_safety_nodes": removed_safety_nodes,
            "evicted_cache_entries": removed_cache_entries,
        }
        encoded_size = len(_mind_text(mind).encode("utf-8"))
        if encoded_size <= limit:
            return True
        mind.pop("capacity", None)
        encoded_size = len(_mind_text(mind).encode("utf-8"))
        return False

    edges = mind.setdefault("edges", {})
    ordinary_edge_order = sorted(
        (key for key, value in edges.items()
         if not _edge_record(value, compact_now).get("pins")),
        key=lambda key: (
            _finite_float(_edge_record(edges[key], compact_now).get(
                "w", 0.0), "edge weight"),
            _finite_float(_edge_record(edges[key], compact_now).get(
                "last_touch", 0.0), "edge last-touch time"), key))
    safety_edge_order = sorted(
        (key for key, value in edges.items()
         if set(_edge_record(value, compact_now).get("pins", []))
         == {"safety"}),
        key=lambda key: (
            _finite_float(_edge_record(edges[key], compact_now).get(
                "w", 0.0), "edge weight"),
            _finite_float(_edge_record(edges[key], compact_now).get(
                "last_touch", 0.0), "edge last-touch time"), key))
    safety_edges = set(safety_edge_order)
    for key in ordinary_edge_order + safety_edge_order:
        count_before = len(edges)
        value = edges.pop(key)
        encoded_size -= removed_entry_bytes(key, value, count_before)
        removed_edges += 1
        if key in safety_edges:
            removed_safety_edges += 1
        if finish_if_bounded():
            return {"edges": removed_edges, "nodes": removed_nodes,
                    "cache_entries": removed_cache_entries}
    pinned_endpoints = set()
    for key, value in edges.items():
        if _edge_record(value, compact_now).get("pins"):
            pinned_endpoints.update(key.split("|", 1))
    nodes = mind.setdefault("nodes", {})
    ordinary_node_order = sorted(
        (slug for slug, node in nodes.items()
         if not node.get("pins") and slug not in pinned_endpoints),
        key=lambda slug: (
            bool(_important(nodes[slug])),
            _finite_float(nodes[slug].get("last_touch", 0.0),
                          "node last-touch time"), slug))
    safety_node_order = sorted(
        (slug for slug, node in nodes.items()
         if set(node.get("pins", [])) == {"safety"}
         and slug not in pinned_endpoints),
        key=lambda slug: (
            _finite_float(nodes[slug].get("last_touch", 0.0),
                          "node last-touch time"), slug))
    safety_nodes = set(safety_node_order)
    for slug in ordinary_node_order + safety_node_order:
        count_before = len(nodes)
        node = nodes.pop(slug)
        encoded_size -= removed_entry_bytes(slug, node, count_before)
        removed_slugs.add(slug)
        removed_nodes += 1
        if slug in safety_nodes:
            removed_safety_nodes += 1
        if finish_if_bounded():
            return {"edges": removed_edges, "nodes": removed_nodes,
                    "cache_entries": removed_cache_entries}
    # Shape counts, novelty cohorts, and empirical-band caches are derived
    # retrieval-policy state, not evidence. They must not strand a durable
    # source transaction behind operator pins.  Evict them deterministically
    # only after graph cache eviction has been exhausted.
    for field in ("seen", "kindn", "hourbuf", "hist", "cooldown", "ewma",
                  "coincide"):
        cache = mind.get(field, {})
        if not isinstance(cache, dict):
            raise ValueError(f"mind {field} cache must be an object")
        for key in sorted(list(cache)):
            if field == "seen":
                mark_familiarity_incomplete()
            count_before = len(cache)
            value = cache.pop(key)
            encoded_size -= removed_entry_bytes(key, value, count_before)
            removed_cache_entries += 1
            if finish_if_bounded():
                return {"edges": removed_edges, "nodes": removed_nodes,
                        "cache_entries": removed_cache_entries}
    raise ValueError(
        "mind state exceeds its persistence bound after derived-cache compaction")


def save_mind(mind):
    if not isinstance(mind, dict):
        raise ValueError("mind state must be a JSON object")
    migrate_mind(mind)
    compact_mind_for_persistence(mind)
    encoded = _mind_text(mind)
    if len(encoded.encode("utf-8")) > MAX_MIND_BYTES:
        raise ValueError("mind state exceeds its persistence bound")
    os.makedirs(os.path.dirname(MIND_PATH), exist_ok=True)
    if os.path.lexists(MIND_PATH):
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
            | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(MIND_PATH, flags)
        with siaqueue.regular_file_stream(fd, label="mind state") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) \
                    or before.st_uid != os.geteuid() \
                    or before.st_nlink != 1 \
                    or before.st_size > MAX_MIND_BYTES:
                raise ValueError(
                    "mind state is not a bounded private single-link "
                    "regular file")
            previous_bytes = stream.read(MAX_MIND_BYTES + 1)
            after = os.fstat(stream.fileno())
            try:
                target = os.lstat(MIND_PATH)
            except FileNotFoundError as exc:
                raise ValueError("mind state changed while read") from exc
        observed = (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns)
        finished = (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns)
        current = (target.st_dev, target.st_ino, target.st_size,
                   target.st_mtime_ns, target.st_ctime_ns)
        if observed != finished or len(previous_bytes) > MAX_MIND_BYTES \
                or after.st_uid != os.geteuid() or after.st_nlink != 1 \
                or not stat.S_ISREG(target.st_mode) \
                or target.st_uid != os.geteuid() or target.st_nlink != 1 \
                or current != finished:
            raise ValueError(
                "mind state changed while read or exceeds its bound")
        try:
            previous = previous_bytes.decode("utf-8")
            migrate_mind(_strict_json_loads(previous))
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise ValueError(
                "prior mind state is unreadable or malformed") from exc
        _atomic_state_text(MIND_PATH + ".last-good", previous)
    _atomic_state_text(MIND_PATH, encoded)


def arousal_of(tags):
    return max((AROUSAL.get(t, 0.0) for t in tags), default=0.1)


# ------------------------------------------------------------------ touches
# Every touch carries a source. Source-adapter and operator-request touches
# count at full weight. System-generated references receive a smaller fixed
# weight so repeated internal output cannot increase its own rank unchecked.

EXO_SOURCES = {"organ", "user-ask", "user-recall", "user"}
ENDO_WEIGHT = 0.2

def _touch_w(src):
    return 1.0 if src in EXO_SOURCES else ENDO_WEIGHT


def _canonical_delivered_slugs(raw_slugs):
    """Validate one bounded result delivery and return a stable ordering."""
    if not isinstance(raw_slugs, list) or len(raw_slugs) > 8:
        raise ValueError("touch queue slugs must be a bounded list")
    if any(not isinstance(slug, str)
           or not re.fullmatch(r"[a-z0-9][a-z0-9/._-]{0,199}", slug)
           or any(part in ("", ".", "..") for part in slug.split("/"))
           for slug in raw_slugs):
        raise ValueError("touch queue contains an invalid slug")
    if len(raw_slugs) != len(set(raw_slugs)):
        raise ValueError("touch queue contains duplicate delivered slugs")
    return sorted(raw_slugs)


def _ensure_collections(mind):
    mind.setdefault("nodes", {})
    mind.setdefault("edges", {})


def _initial_stability(kind, arousal=0.0, novelty_score=0.0):
    base = NODE_STABILITY_DAYS if kind == "node" else EDGE_STABILITY_DAYS
    arousal = _bounded_float(arousal, "safety-priority gain", 0.0, 1.0)
    novelty_score = _bounded_float(
        novelty_score, "novelty gain", 0.0, 1.0)
    return min(MAX_STABILITY_DAYS,
               base * (1 + AROUSAL_STABILITY_GAIN * arousal)
               * (1 + NOVELTY_STABILITY_GAIN * novelty_score))


def _pin(rec, reason):
    pins = set(rec.get("pins", []))
    pins.add(reason)
    rec["pins"] = sorted(pins)


def _unpin(rec, reason):
    rec["pins"] = sorted(set(rec.get("pins", [])) - {reason})


def _important(node):
    if node.get("pins"):
        return True
    try:
        arousal = float(node.get("arousal", 0.0))
        return math.isfinite(arousal) and arousal >= SM2_IMPORTANCE_AROUSAL
    except (TypeError, ValueError):
        return False


def is_important(node):
    """Public predicate shared by the CLI and the rehearsal scheduler."""
    return _important(node)


def _ensure_review(node, ts):
    if not _important(node):
        return None
    return node.setdefault("review", {
        "ef": SM2_EF_INITIAL, "reps": 0, "interval_days": 0,
        "due_at": float(ts), "last_review": 0.0,
        "last_quality": None, "reviews": 0,
    })


def touch(mind, slug, ts=None, src="organ", *, arousal=0.0,
          novelty_score=0.0, pin=False, reinforce=True):
    """Record a node touch and its provenance.

    Stability reinforcement is deliberately separate from usage source
    weighting: ``n`` remains echo-resistant, while every genuine retrieval or
    reference restabilizes the trace as specified.  ``reinforce=False`` is for
    state discovery/migration, not a user-visible recall.
    """
    ts = _finite_float(time.time() if ts is None else ts, "touch time")
    arousal = _bounded_float(arousal, "safety-priority gain", 0.0, 1.0)
    novelty_score = _bounded_float(
        novelty_score, "novelty gain", 0.0, 1.0)
    _ensure_collections(mind)
    w = _touch_w(src)
    fresh = slug not in mind["nodes"]
    n = mind["nodes"].setdefault(slug, {"n": 0, "t0": ts, "rt": []})
    if fresh:
        n["s"] = _initial_stability("node", arousal, novelty_score)
        n["last_touch"] = ts
        n["arousal"] = max(0.0, float(arousal))
        n["novelty"] = max(0.0, float(novelty_score))
        n["pins"] = []
        n["signals"] = {}
    else:
        if reinforce:
            n["s"] = min(MAX_STABILITY_DAYS,
                         _stability(n.get("s", NODE_STABILITY_DAYS),
                                    "node stability")
                         * STABILITY_TOUCH_GAIN
                         * (1 + NOVELTY_STABILITY_GAIN * novelty_score))
        n["arousal"] = max(_bounded_float(
            n.get("arousal", 0.0), "node safety-priority field", 0.0, 1.0), arousal)
        n["novelty"] = max(_bounded_float(
            n.get("novelty", 0.0), "node novelty", 0.0, 1.0),
                           novelty_score)
        n["last_touch"] = max(_finite_float(
            n.get("last_touch", ts), "node last-touch time"), ts)
    n["t0"] = min(
        _finite_float(n.get("t0", ts), "node creation time"), ts)
    if pin:
        _pin(n, "safety")
    n.setdefault("signals", {})[src] = max(
        _finite_float(n.get("signals", {}).get(src, 0.0),
                      "node signal time"), ts)
    n["n"] = round(_finite_float(n.get("n", 0), "node touch count") + w, 2)
    rt = [e if isinstance(e, list) else [e, 1.0] for e in n.get("rt", [])]
    rt.append([ts, w])
    rt.sort(key=lambda entry: _finite_float(
        entry[0], "node retrieval time"))
    n["rt"] = rt[-ACTR_K:]
    _ensure_review(n, ts)
    return n


def hebb(mind, a, b, amount=1, ts=None, *, arousal=0.0,
         novelty_score=0.0, pin=False, reinforce=True):
    """Reinforce one co-return edge; the function name is compatibility only."""
    if a == b:
        return
    ts = _finite_float(time.time() if ts is None else ts, "edge touch time")
    _ensure_collections(mind)
    key = "|".join(sorted((a, b)))
    fresh = key not in mind["edges"]
    edge = _edge_record(mind["edges"].get(key, 0.0), ts)
    if fresh:
        edge["s"] = _initial_stability("edge", arousal, novelty_score)
        edge["last_touch"] = ts
        edge.pop("migrated_v1", None)
    elif reinforce:
        edge["s"] = min(MAX_STABILITY_DAYS,
                        _stability(edge.get("s", EDGE_STABILITY_DAYS),
                                   "edge stability")
                        * STABILITY_TOUCH_GAIN
                        * (1 + NOVELTY_STABILITY_GAIN * novelty_score))
        edge["last_touch"] = max(_finite_float(
            edge.get("last_touch", ts), "edge last-touch time"), ts)
    edge["w"] = _finite_float(
        _finite_float(edge.get("w", 0.0), "edge weight")
        + _finite_float(amount, "edge reinforcement"), "edge weight")
    if pin:
        _pin(edge, "safety")
    mind["edges"][key] = edge
    return edge


def _apply_coreturn_effects(mind, slugs, stamp, src):
    """Apply one prevalidated result delivery to candidate policy state."""
    node_delta = _touch_w(src)
    node_deltas = {}
    pair_deltas = {}
    for slug in slugs:
        touch(mind, slug, stamp, src=src)
        node_deltas[slug] = node_delta
    for left in range(len(slugs)):
        for right in range(left + 1, len(slugs)):
            key = "|".join((slugs[left], slugs[right]))
            hebb(mind, slugs[left], slugs[right], ts=stamp)
            pair_deltas[key] = 1.0
    return node_deltas, pair_deltas


def _coreturn_receipts(mind):
    receipts = mind.get("coreturn_applied", {})
    if not isinstance(receipts, dict) \
            or len(receipts) > MAX_TOUCH_QUEUE_RECORDS:
        raise ValueError("co-return replay state is invalid")
    for identity, digest in receipts.items():
        if not isinstance(identity, str) or not identity \
                or len(identity) > 200 \
                or not isinstance(digest, str) \
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("co-return replay state is invalid")
    return receipts


def apply_coreturn_record(mind, record):
    """Atomically apply one exact delivered result set.

    The record uses the resident touch-queue product shape. Slugs must be
    unique and canonical before either node usage or unordered pair state can
    change. A receipt binds the caller's identity to the normalized payload,
    making an exact retry a no-op and a reused identity a refusal.
    """
    if not isinstance(record, dict) \
            or set(record) - {"id", "ts", "src", "slugs"}:
        raise ValueError("co-return record is invalid")
    identity = record.get("id")
    if not isinstance(identity, str) or not identity \
            or len(identity) > 200:
        raise ValueError("co-return record identity is invalid")
    stamp = _finite_float(record.get("ts"), "co-return record time")
    src = record.get("src", "user-ask")
    if not isinstance(src, str) \
            or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,199}", src):
        raise ValueError("co-return record source is invalid")
    slugs = _canonical_delivered_slugs(record.get("slugs"))
    if not isinstance(mind, dict) \
            or not isinstance(mind.get("nodes", {}), dict) \
            or not isinstance(mind.get("edges", {}), dict):
        raise ValueError("co-return mind state is invalid")
    receipts = _coreturn_receipts(mind)
    normalized = json.dumps(
        {"id": identity, "ts": stamp, "src": src, "slugs": slugs},
        sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    prior = receipts.get(identity)
    if prior is not None:
        if prior != digest:
            raise ValueError("co-return record identity was reused")
        return {
            "status": "already-applied",
            "record_id": identity,
            "node_deltas": {},
            "unordered_pair_deltas": {},
        }
    if len(receipts) >= MAX_TOUCH_QUEUE_RECORDS:
        raise ValueError("co-return replay state reached its bound")

    candidate = copy.deepcopy(mind)
    candidate.setdefault("nodes", {})
    candidate.setdefault("edges", {})
    candidate_receipts = candidate.setdefault("coreturn_applied", {})
    node_deltas, pair_deltas = _apply_coreturn_effects(
        candidate, slugs, stamp, src)
    candidate_receipts[identity] = digest
    mind.clear()
    mind.update(candidate)
    return {
        "status": "applied",
        "record_id": identity,
        "node_deltas": node_deltas,
        "unordered_pair_deltas": pair_deltas,
    }


def bump_kind(mind, organ, kind, tags=()):
    """Track how often each event shape and each safety tag has EVER been
    seen for deterministic history-dependent policies and diagnostics."""
    kn = mind.setdefault("kindn", {})
    kn[f"{organ}:{kind}"] = kn.get(f"{organ}:{kind}", 0) + 1
    tn = mind.setdefault("tagn", {})
    for t in tags:
        if t in SAFETY_TAGS:
            tn[t] = tn.get(t, 0) + 1


def event_was_applied(mind, day_slug, event_id):
    """Return whether an exact corpus event already changed policy state."""
    _validate_event_replay_key(day_slug, event_id)
    applied = mind.setdefault("event_applied", [])
    if not isinstance(applied, list):
        raise ValueError("mind event replay state must be a list")
    return event_id in applied


def mark_event_applied(mind, day_slug, event_id):
    """Record an exact event only after all of its policy updates succeed."""
    _validate_event_replay_key(day_slug, event_id)
    applied = mind.setdefault("event_applied", [])
    if not isinstance(applied, list):
        raise ValueError("mind event replay state must be a list")
    if event_id not in applied:
        applied.append(event_id)


def clear_event_applied(mind):
    """Forget replay guards after the matching evidence cursors commit."""
    applied = mind.get("event_applied", [])
    if not isinstance(applied, list):
        raise ValueError("mind event replay state must be a list")
    removed = len(applied)
    mind["event_applied"] = []
    return removed


def event_batch_was_applied(mind, batch_identity):
    """Return whether one exact source-marker generation changed policy state."""
    _validate_event_batch_identity(batch_identity)
    applied = mind.get("event_batch_applied")
    if applied is not None:
        _validate_event_batch_identity(applied)
    return applied == batch_identity


def mark_event_batch_applied(mind, batch_identity):
    """Publish the bounded all-or-nothing event-policy replay receipt."""
    _validate_event_batch_identity(batch_identity)
    prior = mind.get("event_batch_applied")
    if prior not in (None, batch_identity):
        raise ValueError("a different mind event batch is pending")
    mind["event_batch_applied"] = batch_identity


def clear_event_replay(mind):
    """Clear legacy and batch guards after their evidence cursors commit."""
    removed = clear_event_applied(mind)
    if mind.get("event_batch_applied") is not None:
        _validate_event_batch_identity(mind["event_batch_applied"])
        mind["event_batch_applied"] = None
        removed += 1
    mind["event_transition_pending"] = None
    return removed


def _validate_event_batch_identity(value):
    if not isinstance(value, str) \
            or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise ValueError("event batch replay identity is invalid")


def _validate_event_replay_key(day_slug, event_id):
    if not isinstance(day_slug, str) \
            or re.fullmatch(
                r"events/[a-z0-9][a-z0-9._-]{0,199}/"
                r"\d{4}-\d{2}-\d{2}"
                r"(?:-part-[2-9][0-9]*)?", day_slug) is None \
            or not isinstance(event_id, str) \
            or re.fullmatch(r"[0-9a-f]{64}", event_id) is None:
        raise ValueError("event replay identity is invalid")


def hebb_hygiene(mind, decay=0.95, floor=0.4, degree_cap=32, now=None):
    """Nightly edge hygiene under the retained compatibility API name.

    Weights decay, dust is swept, and no node may keep more than degree_cap
    edges (weakest pruned first), keeping graph propagation bounded.
    """
    now = time.time() if now is None else float(now)
    edges = mind.get("edges", {})
    for k in list(edges):
        edge = _edge_record(edges[k], now)
        w = edge["w"] * decay
        if w < floor:
            if edge.get("graph_discovered"):
                # The PGLite graph says this relation still exists.  Sweep
                # only its accumulated co-return weight; retaining the record
                # lets stability continue aging across graph synchronizations.
                edge["w"] = 0.0
                edges[k] = edge
            else:
                del edges[k]
        else:
            edge["w"] = round(w, 3)
            edges[k] = edge
    per = {}
    for k, edge in edges.items():
        if edge["w"] <= 0:
            continue
        a, b = k.split("|", 1)
        w = edge["w"]
        per.setdefault(a, []).append((w, k))
        per.setdefault(b, []).append((w, k))
    doomed = set()
    for node, lst in per.items():
        if len(lst) > degree_cap:
            lst.sort(reverse=True)
            for _, k in lst[degree_cap:]:
                doomed.add(k)
    for k in doomed:
        edge = edges.get(k)
        if edge and edge.get("graph_discovered"):
            edge["w"] = 0.0
        else:
            edges.pop(k, None)
    return len(doomed)


def _corpus_page_exists(slug):
    if not isinstance(slug, str) \
            or not re.fullmatch(r"[a-z0-9][a-z0-9/._-]{0,199}", slug) \
            or any(part in ("", ".", "..") for part in slug.split("/")):
        return False
    try:
        return stat.S_ISREG(os.lstat(os.path.join(
            CORPUS, slug + ".md")).st_mode)
    except OSError:
        return False


def set_user_pin(mind, slug, pinned=True, ts=None, page_exists=None):
    """Apply a queued operator pin without pretending it was a recall."""
    ts = time.time() if ts is None else float(ts)
    _ensure_collections(mind)
    page_exists = page_exists or _corpus_page_exists
    node = mind["nodes"].get(slug)
    if pinned and not page_exists(slug):
        # Validation at the producer can race consolidation or a stale/manual
        # queue record. The consumer must refuse an absent corpus page too.
        return None
    if node is None and not pinned:
        # An unpin is a removal request, never a discovery signal.  Old or
        # hand-written queue records therefore cannot mint ghost memories.
        return None
    if node is None:
        node = touch(mind, slug, ts, src="pin", reinforce=False)
        # Pinning is metadata, not a usage or reinforcement event.
        node["n"] = 0
        node["rt"] = []
        node["signals"].pop("pin", None)
    if pinned:
        _pin(node, "user")
        _ensure_review(node, ts)
    else:
        _unpin(node, "user")
        if not _important(node):
            node.pop("review", None)
    return node


def _fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextlib.contextmanager
def _touch_queue_lock(queue_path):
    directory = os.path.dirname(queue_path) or "."
    os.makedirs(directory, exist_ok=True)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) \
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(directory, directory_flags)
    directory_info = os.fstat(directory_fd)
    if not stat.S_ISDIR(directory_info.st_mode) \
            or directory_info.st_uid != os.geteuid() \
            or stat.S_IMODE(directory_info.st_mode) & 0o022:
        os.close(directory_fd)
        raise ValueError(
            "touch queue directory is not an owner-private real directory")
    lock_name = os.path.basename(queue_path) + ".lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(lock_name, flags, 0o600, dir_fd=directory_fd)
    except Exception:
        os.close(directory_fd)
        raise
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) \
                or info.st_uid != os.geteuid() or info.st_nlink != 1:
            raise ValueError("touch queue lock is not an owned regular file")
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            held = os.fstat(fd)
            current = os.stat(
                lock_name, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISREG(current.st_mode) \
                    or current.st_uid != os.geteuid() \
                    or current.st_nlink != 1 \
                    or (held.st_dev, held.st_ino) != (
                        current.st_dev, current.st_ino):
                raise ValueError(
                    "touch queue lock changed while acquiring its lease")
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
        os.close(directory_fd)


def _touch_refusal_path(queue_path):
    return os.path.join(
        os.path.dirname(queue_path) or ".", TOUCH_QUEUE_REFUSAL_NAME)


def _queue_file_identity(info, raw):
    return {
        "dev": info.st_dev,
        "ino": info.st_ino,
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _read_touch_queue_bytes_locked(path, limit=None):
    """Read one queue generation through a stable, bounded no-follow fd."""
    limit = MAX_TOUCH_QUEUE_BYTES if limit is None else limit
    try:
        linked = os.lstat(path)
    except FileNotFoundError:
        return None, None
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_nlink != 1 \
                or before.st_size > limit \
                or (linked.st_dev, linked.st_ino) != (
                    before.st_dev, before.st_ino):
            raise ValueError("touch queue is not a bounded owned regular file")
        if before.st_mode & 0o077:
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
            before = os.fstat(descriptor)
        raw = bytearray()
        while len(raw) <= limit:
            chunk = os.read(
                descriptor, limit + 1 - len(raw))
            if not chunk:
                break
            raw.extend(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        current = os.lstat(path)
    except FileNotFoundError as exc:
        raise ValueError("touch queue changed while read") from exc
    identity = lambda value: (
        value.st_dev, value.st_ino, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns)
    if len(raw) > limit \
            or identity(before) != identity(after) \
            or identity(after) != identity(current):
        raise ValueError("touch queue changed while read or exceeded its bound")
    result = bytes(raw)
    return result, _queue_file_identity(after, result)


def _literal_lf_touch_lines(raw):
    """Decode complete physical records; Unicode line separators are data."""
    if not raw:
        return []
    if not raw.endswith(b"\n"):
        raise ValueError("touch queue has an unterminated physical record")
    if raw.count(b"\n") > MAX_TOUCH_QUEUE_RECORDS:
        raise ValueError("touch queue exceeds aggregate record limit")
    rows = raw[:-1].split(b"\n")
    try:
        return [row.decode("utf-8", errors="strict") for row in rows]
    except UnicodeError as exc:
        raise ValueError("touch queue is not valid UTF-8") from exc


def _valid_touch_refusal_last(value):
    if value is None:
        return True
    if not isinstance(value, dict) or set(value) != {
            "reason", "queue_sha256", "generation", "complete_offset",
            "suffix_sha256"} \
            or value.get("reason") != "unterminated-suffix" \
            or re.fullmatch(r"[0-9a-f]{64}",
                            value.get("queue_sha256", "")) is None \
            or re.fullmatch(r"[0-9a-f]{64}",
                            value.get("suffix_sha256", "")) is None:
        return False
    generation = value.get("generation")
    if not isinstance(generation, dict) or set(generation) != {
            "dev", "ino", "size", "mtime_ns", "ctime_ns", "sha256"} \
            or re.fullmatch(r"[0-9a-f]{64}",
                            generation.get("sha256", "")) is None:
        return False
    numeric = [generation.get(key) for key in (
        "dev", "ino", "size", "mtime_ns", "ctime_ns")]
    offset = value.get("complete_offset")
    return all(isinstance(item, int) and not isinstance(item, bool)
               and item >= 0 for item in numeric) \
        and isinstance(offset, int) and not isinstance(offset, bool) \
        and 0 <= offset <= generation["size"]


def _load_touch_refusal_locked(queue_path):
    path = _touch_refusal_path(queue_path)
    raw, _identity = _read_touch_queue_bytes_locked(
        path, limit=MAX_MIND_BYTES)
    if raw is None:
        return {"schema": TOUCH_QUEUE_REFUSAL_SCHEMA, "count": 0,
                "last": None, "receipts": {}}
    try:
        value = _strict_json_loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("touch queue refusal state is malformed") from exc
    if not isinstance(value, dict) or set(value) != {
            "schema", "count", "last", "receipts"} \
            or value.get("schema") != TOUCH_QUEUE_REFUSAL_SCHEMA \
            or not isinstance(value.get("count"), int) \
            or isinstance(value.get("count"), bool) \
            or not 0 <= value["count"] <= MAX_TOUCH_QUEUE_BYTES \
            or not _valid_touch_refusal_last(value.get("last")) \
            or not isinstance(value.get("receipts"), dict) \
            or len(value["receipts"]) > MAX_TOUCH_QUEUE_REFUSAL_SOURCES \
            or any(re.fullmatch(r"[0-9a-f]{64}", key) is None
                   or not _valid_touch_refusal_last(receipt)
                   or receipt is None
                   for key, receipt in value["receipts"].items()):
        raise ValueError("touch queue refusal state is malformed")
    return value


def _record_touch_tail_refusal_locked(
        queue_path, identity, complete_offset, suffix):
    state = _load_touch_refusal_locked(queue_path)
    queue_digest = hashlib.sha256(
        os.path.abspath(queue_path).encode(
            "utf-8", errors="surrogateescape")).hexdigest()
    last = {
        "reason": "unterminated-suffix",
        "queue_sha256": queue_digest,
        "generation": identity,
        "complete_offset": complete_offset,
        "suffix_sha256": hashlib.sha256(suffix).hexdigest(),
    }
    receipts = state["receipts"]
    if queue_digest not in receipts \
            and len(receipts) >= MAX_TOUCH_QUEUE_REFUSAL_SOURCES:
        raise ValueError("touch queue refusal source bound is exhausted")
    if receipts.get(queue_digest) != last:
        state["count"] = min(
            MAX_TOUCH_QUEUE_BYTES, state.get("count", 0) + 1)
    receipts[queue_digest] = last
    state["last"] = last
    encoded = json.dumps(
        state, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False)
    _atomic_state_text(_touch_refusal_path(queue_path), encoded)
    return state


def _repair_touch_tail_locked(path):
    """Record, revalidate, then remove only one unterminated suffix."""
    raw, identity = _read_touch_queue_bytes_locked(path)
    if raw is None or not raw or raw.endswith(b"\n"):
        return raw
    complete_offset = raw.rfind(b"\n") + 1
    suffix = raw[complete_offset:]
    _record_touch_tail_refusal_locked(
        path, identity, complete_offset, suffix)
    current, current_identity = _read_touch_queue_bytes_locked(path)
    if current_identity != identity or current != raw:
        raise ValueError("touch queue changed before torn-tail repair")
    siaqueue.fixed_atomic_publish(
        path, raw[:complete_offset], mode=0o600,
        staging_dir=siaqueue.staging_dir_for(
            path, authority_roots=(STATE,)))
    return raw[:complete_offset]


def _parse_touch_json_line(line):
    try:
        return _strict_json_loads(line)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("touch queue contains malformed JSON") from exc


def acknowledge_touch_queue(claim_path, queue_path=None):
    """Durably remove a claimed batch after policy state is saved."""
    if not claim_path:
        return
    queue_path = queue_path or TOUCH_QUEUE
    expected = queue_path + ".draining"
    if os.path.abspath(claim_path) != os.path.abspath(expected):
        raise ValueError("unexpected touch queue claim path")
    with _touch_queue_lock(queue_path):
        info = os.lstat(claim_path)
        if not stat.S_ISREG(info.st_mode) \
                or info.st_uid != os.geteuid() or info.st_nlink != 1 \
                or info.st_mode & 0o077:
            raise ValueError(
                "touch queue claim is not an owned private regular file")
        os.unlink(claim_path)
        _fsync_directory(os.path.dirname(queue_path) or ".")


def clear_touch_queue_claim(
        mind, claim_field="touch_queue_claim_sha256"):
    """Forget one batch receipt after its claimed file is acknowledged."""
    if claim_field not in {
            "touch_queue_claim_sha256", "recovery_unpin_claim_sha256"}:
        raise ValueError("touch queue claim field is invalid")
    mind.pop(claim_field, None)
    if claim_field == "touch_queue_claim_sha256":
        # Remove the larger pre-release per-record replay representation.
        mind.pop("touch_queue_applied", None)


def _validate_touch_queue_snapshot(lines, now):
    """Parse a bounded queue snapshot without applying its operations."""
    if len(lines) > MAX_TOUCH_QUEUE_RECORDS:
        raise ValueError("touch queue exceeds aggregate record limit")
    validated = []
    for line in lines:
        rec = _parse_touch_json_line(line)
        if not isinstance(rec, dict):
            raise ValueError("touch queue record is not an object")
        record_id = rec.get("id")
        if record_id is None:
            record_id = hashlib.sha256(line.encode()).hexdigest()
        elif not isinstance(record_id, str) or not record_id \
                or len(record_id) > 200:
            raise ValueError("touch queue record identity is invalid")
        ts = _finite_float(rec.get("ts", now), "touch queue timestamp")
        if "op" in rec:
            if rec.get("op") not in ("pin", "unpin"):
                raise ValueError("touch queue operation is invalid")
            if set(rec) - {"id", "ts", "op", "slug"}:
                raise ValueError("pin queue record has unknown fields")
            slug = rec.get("slug")
            if not isinstance(slug, str) \
                    or not re.fullmatch(r"[a-z0-9][a-z0-9/._-]{0,199}", slug) \
                    or any(part in ("", ".", "..")
                           for part in slug.split("/")):
                raise ValueError("pin queue slug is invalid")
            validated.append(("pin", record_id, ts, rec["op"], slug))
            continue
        if set(rec) - {"id", "ts", "src", "slugs"}:
            raise ValueError("touch queue record has unknown fields")
        raw_slugs = _canonical_delivered_slugs(rec.get("slugs"))
        src = rec.get("src", "user-ask")
        if not isinstance(src, str) \
                or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,199}", src):
            raise ValueError("touch queue source is invalid")
        validated.append(("touch", record_id, ts, src, list(raw_slugs)))
    return validated


def pending_user_pin_slugs(queue_path=None, now=None):
    """Return queued operator pins that consolidation must protect."""
    now = _finite_float(time.time() if now is None else now,
                        "pin snapshot time")
    queue_path = queue_path or TOUCH_QUEUE
    lines = []
    total = 0
    records = 0
    with _touch_queue_lock(queue_path):
        for candidate in (queue_path, queue_path + ".draining"):
            raw = _repair_touch_tail_locked(candidate)
            if raw is None:
                continue
            total += len(raw)
            if total > MAX_TOUCH_QUEUE_BYTES:
                raise ValueError("touch queue exceeds aggregate byte limit")
            records += raw.count(b"\n")
            if records > MAX_TOUCH_QUEUE_RECORDS:
                raise ValueError("touch queue exceeds aggregate record limit")
            lines.extend(_literal_lf_touch_lines(raw))
    return {
        value for operation, _record_id, _stamp, argument, value in
        _validate_touch_queue_snapshot(lines, now)
        if operation == "pin" and argument == "pin"
    }


def drain_touch_queue(mind, now=None, queue_path=None, defer_ack=False,
                      page_exists=None,
                      claim_field="touch_queue_claim_sha256",
                      report_capacity=False):
    """Apply one crash-recoverable batch of recall/pin signals.

    Writers and the rename share one flock, so an already-open append cannot
    follow a renamed inode. With ``defer_ack``, the batch stays claimed until
    the caller durably saves mind state. One digest receipts the complete
    atomic batch, so adversarial record IDs cannot consume the mind bound.
    """
    try:
        now = _finite_float(time.time() if now is None else now,
                            "retention time")
    except ValueError:
        return 0.0
    queue_path = queue_path or TOUCH_QUEUE
    draining = queue_path + ".draining"
    directory = os.path.dirname(queue_path) or "."
    with _touch_queue_lock(queue_path):
        draining_raw = _repair_touch_tail_locked(draining) or b""
        queued_raw = _repair_touch_tail_locked(queue_path) or b""
        if len(draining_raw) + len(queued_raw) > MAX_TOUCH_QUEUE_BYTES:
            raise ValueError("touch queue exceeds aggregate byte limit")
        if draining_raw.count(b"\n") + queued_raw.count(b"\n") \
                > MAX_TOUCH_QUEUE_RECORDS:
            raise ValueError("touch queue exceeds aggregate record limit")
        if not os.path.lexists(draining) and os.path.lexists(queue_path):
            os.replace(queue_path, draining)
            _fsync_directory(directory)
    lines, claim_digest = [], None
    if os.path.lexists(draining):
        claim_bytes, _claim_identity = _read_touch_queue_bytes_locked(draining)
        claim_digest = hashlib.sha256(claim_bytes).hexdigest()
        lines = _literal_lf_touch_lines(claim_bytes)

    # Validate the complete claimed batch before changing policy state. One
    # malformed record retains the whole claim; no valid sibling is partially
    # applied and then accidentally acknowledged with it.
    validated = _validate_touch_queue_snapshot(lines, now)

    if claim_field not in {
            "touch_queue_claim_sha256", "recovery_unpin_claim_sha256"}:
        raise ValueError("touch queue claim field is invalid")
    refused = 0
    drained = 0
    if claim_digest is None:
        clear_touch_queue_claim(mind, claim_field)
    elif mind.get(claim_field) != claim_digest:
        original = copy.deepcopy(mind)
        candidate = copy.deepcopy(mind)
        clear_touch_queue_claim(candidate, claim_field)
        candidate[claim_field] = claim_digest

        def apply_records(target, *, unpins_only=False):
            changed = 0
            accepted = 0
            for operation, _record_id, stamp, argument, value in validated:
                if operation == "pin":
                    is_unpin = argument == "unpin"
                    if unpins_only and not is_unpin:
                        continue
                    accepted += 1
                    if set_user_pin(
                            target, value, not is_unpin, stamp,
                            page_exists=page_exists) is not None:
                        changed += 1
                    continue
                if unpins_only:
                    continue
                accepted += 1
                src, slugs = argument, value
                if src == "thought":
                    changed += apply_thought_reinforcement(
                        target, slugs, stamp)
                    continue
                node_deltas, _pair_deltas = _apply_coreturn_effects(
                    target, slugs, stamp, src)
                changed += len(node_deltas)
            return changed, accepted

        drained, _accepted = apply_records(candidate)
        try:
            compact_mind_for_persistence(candidate)
        except ValueError as exc:
            if "persistence bound" not in str(exc):
                raise
            # Capacity is an admission refusal, not a permanent head-of-line
            # block. Roll back the generation, retain only idempotent unpins,
            # and let the caller surface how many records were refused.
            candidate = copy.deepcopy(original)
            clear_touch_queue_claim(candidate, claim_field)
            drained, accepted = apply_records(candidate, unpins_only=True)
            refused = len(validated) - accepted
            compact_mind_for_persistence(candidate)
        mind.clear()
        mind.update(candidate)
    claim = draining if os.path.lexists(draining) else None
    if claim and not defer_ack:
        acknowledge_touch_queue(claim, queue_path=queue_path)
        clear_touch_queue_claim(mind, claim_field)
    if report_capacity:
        return (drained, claim, refused) if defer_ack else (drained, refused)
    return (drained, claim) if defer_ack else drained


def _apply_thought_links(mind, slugs, stamp):
    """Apply one already-admitted system-generated page signal."""
    for slug in slugs:
        touch(mind, slug, stamp, src="thought")
    for left in range(len(slugs)):
        for right in range(left + 1, len(slugs)):
            hebb(mind, slugs[left], slugs[right], ts=stamp)
    return len(slugs)


def apply_exact_thought_reinforcement(mind, slugs, stamp, record_id):
    """Apply one exact page ID admitted by SIA's durable replay journal.

    Timestamp maxima are salience metadata, not occurrence identities: an older
    page can introduce a previously unseen node or edge through a shared newer
    node. The caller owns exact-record idempotence with its immutable claim and
    applied-page journal, while this function validates that identity before
    applying every link in the admitted record.
    """
    if not isinstance(record_id, str) \
            or re.fullmatch(r"[0-9a-f]{64}", record_id) is None:
        raise ValueError("thought replay record identity is invalid")
    stamp = _finite_float(stamp, "thought signal time")
    slugs = list(slugs)
    return _apply_thought_links(mind, slugs, stamp)


def apply_thought_reinforcement(mind, slugs, stamp):
    """Coalesce non-journaled touch-queue echoes within one page second."""
    stamp = _finite_float(stamp, "thought signal time")
    slugs = list(slugs)
    if any(_finite_float(
            mind.get("nodes", {}).get(slug, {}).get(
                "signals", {}).get("thought", 0.0),
            "thought signal time") >= stamp for slug in slugs):
        # Generated-entry pages use a one-second timestamp. Treat an overlapping
        # signal in that second as both the durable retry receipt and a
        # deliberate system-entry echo-rate limit. External recalls remain
        # independently counted.
        return 0
    return _apply_thought_links(mind, slugs, stamp)


# -------------------------------------------- retrieval stability + scheduling

def retention(record, now=None):
    """Retrieval-only stability lens ``R = exp(-elapsed_days / S)``.

    Pins make R=1 but never alter or delete corpus evidence.  A malformed or
    non-positive stability fails closed to zero salience.
    """
    now = time.time() if now is None else float(now)
    if record.get("pins"):
        return 1.0
    try:
        stability = float(record.get("s", 0.0))
        last_touch = float(record.get("last_touch", now))
        if not math.isfinite(stability) or not math.isfinite(last_touch) \
                or stability <= 0:
            return 0.0
        stability = min(stability, MAX_STABILITY_DAYS)
        elapsed = max(0.0, now - last_touch) \
            / SECONDS_PER_DAY
        return math.exp(-elapsed / stability)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def sync_graph_state(mind, graph, now=None):
    """Ensure every exported graph node/edge has v2 stability metadata.

    Discovery is not a touch: it neither raises usage counts nor reinforces
    stability.  This closes the migration gap for pages never seen by the
    current daemon process.
    """
    now = _finite_float(time.time() if now is None else now,
                        "graph synchronization time")
    _ensure_collections(mind)
    for item in (graph or {}).get("nodes", []):
        slug = item.get("id")
        if not slug or slug in mind["nodes"]:
            continue
        mind["nodes"][slug] = {
            "n": 0, "t0": now, "rt": [], "s": NODE_STABILITY_DAYS,
            "last_touch": now, "arousal": 0.0, "novelty": 0.0,
            "pins": [], "signals": {},
        }
    for item in (graph or {}).get("edges", []):
        a, b = item.get("s"), item.get("d")
        if not a or not b or a == b:
            continue
        key = "|".join(sorted((a, b)))
        if key not in mind["edges"]:
            mind["edges"][key] = {
                "w": 0.0, "s": EDGE_STABILITY_DAYS,
                "last_touch": now, "pins": [], "graph_discovered": True,
            }
        else:
            # An accumulated co-return edge may predate the graph snapshot that
            # proves the same relation exists in the corpus.  Promote the
            # existing record in place without refreshing its stability.
            edge = _edge_record(mind["edges"][key], now)
            edge["graph_discovered"] = True
            mind["edges"][key] = edge
    return mind


def baseline_graph_familiarity(mind, graph, observed_at):
    """Settle a new-install familiarity bootstrap from one admitted graph.

    Positive page identities may be seeded from any complete projection. Only
    an exhaustive zero-omission inventory with no event-day or epoch history
    proves that the pending installation has no unrepresented event-shape
    observations. The timestamp is the inventory observation, never a
    reconstructed page occurrence. Lost or legacy history has no pending
    authority and cannot regain completeness through this projection.
    """
    if not isinstance(mind, dict) or not isinstance(mind.get("seen"), dict):
        raise ValueError("graph familiarity state must be an object")
    complete = mind.get("familiarity_complete", False)
    if type(complete) is not bool:
        raise ValueError("graph familiarity completeness must be boolean")
    pending = mind.get("familiarity_bootstrap_pending", False)
    if type(pending) is not bool:
        raise ValueError("graph familiarity bootstrap marker must be boolean")
    if complete and pending:
        raise ValueError("graph familiarity bootstrap cannot already be complete")
    if not pending:
        return 0
    if mind["seen"]:
        raise ValueError("graph familiarity bootstrap requires an empty map")
    stamp = _finite_float(observed_at, "graph familiarity observation time")
    if not isinstance(graph, dict):
        raise ValueError("graph familiarity snapshot must be an object")
    nodes = graph.get("nodes")
    pages_total = graph.get("pages_total")
    pages_total_complete = graph.get("pages_total_complete")
    snapshot = graph.get("snapshot")
    if not isinstance(nodes, list):
        raise ValueError("graph familiarity nodes must be a list")
    if isinstance(pages_total, bool) or not isinstance(pages_total, int) \
            or pages_total < 0:
        raise ValueError("graph familiarity page total is invalid")
    if type(pages_total_complete) is not bool:
        raise ValueError("graph familiarity page-total marker is invalid")
    if not isinstance(snapshot, dict):
        raise ValueError("graph familiarity envelope must be an object")

    def nonnegative_integer(field):
        value = snapshot.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"graph familiarity {field.replace('_', '-')} is invalid")
        return value

    snapshot_complete = snapshot.get("complete")
    if type(snapshot_complete) is not bool:
        raise ValueError("graph familiarity completeness marker is invalid")
    if snapshot.get("omissions_imply_absence") is not False:
        raise ValueError("graph familiarity omission contract is invalid")
    truncated = nonnegative_integer("truncated")
    omitted_nodes = nonnegative_integer("omitted_nodes")
    omitted_edges = nonnegative_integer("omitted_edges")
    aged_out = nonnegative_integer("aged_out")
    failed_ops = snapshot.get("failed_ops")
    if not isinstance(failed_ops, list) or any(
            not isinstance(value, str) or not value for value in failed_ops):
        raise ValueError("graph familiarity failure roster is invalid")
    counts = snapshot.get("counts_by_kind")
    if not isinstance(counts, dict):
        raise ValueError("graph familiarity kind counts must be an object")

    slugs, node_kinds, kinds = [], [], {}
    for item in nodes:
        slug = item.get("id") if isinstance(item, dict) else None
        kind = item.get("t") if isinstance(item, dict) else None
        _canonical_familiarity_entity(
            slug, "graph familiarity node identity")
        _canonical_familiarity_token(
            kind, "graph familiarity node kind")
        slugs.append(slug)
        node_kinds.append(kind)
        kinds[kind] = kinds.get(kind, 0) + 1
    if len(set(slugs)) != len(slugs):
        raise ValueError("graph familiarity node identities must be unique")
    for kind, count in counts.items():
        _canonical_familiarity_token(
            kind, "graph familiarity count kind")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("graph familiarity kind count is invalid")
    if counts != kinds:
        raise ValueError("graph familiarity kind counts do not match nodes")

    if snapshot_complete != (not failed_ops):
        raise ValueError("graph familiarity completeness is inconsistent")
    if not snapshot_complete or not pages_total_complete:
        raise ValueError("graph familiarity snapshot is not admitted")
    if omitted_nodes != truncated:
        raise ValueError("graph familiarity node omission is inconsistent")
    if aged_out > pages_total \
            or truncated > pages_total - aged_out \
            or len(nodes) != pages_total - aged_out - truncated:
        raise ValueError("graph familiarity page inventory is inconsistent")

    # A complete but bounded inventory supplies positive identities yet can
    # never supply absence authority for anything outside its projection.
    inventory_complete = (
        truncated == 0 and omitted_nodes == 0 and omitted_edges == 0
        and aged_out == 0 and pages_total == len(nodes)
    )
    history_bearing = any(
        kind in {"event-day", "epoch"}
        or slug.startswith(("events/", "epochs/"))
        for slug, kind in zip(slugs, node_kinds)
    )
    mind["seen"].update({slug: stamp for slug in slugs})
    mind["familiarity_complete"] = (
        inventory_complete and not history_bearing)
    mind["familiarity_bootstrap_pending"] = False
    return len(slugs)


def decay_sweep(mind, now=None):
    """Refresh active/demoted counts; demotion only affects graph propagation."""
    now = time.time() if now is None else float(now)
    active = demoted = pinned = 0
    for key, value in list(mind.get("edges", {}).items()):
        edge = _edge_record(value, now)
        mind["edges"][key] = edge
        r = retention(edge, now)
        edge["demoted"] = r < RETENTION_DEMOTE
        if edge.get("pins"):
            pinned += 1
        if edge["demoted"]:
            demoted += 1
        else:
            active += 1
    report = {"at": now, "active_edges": active,
              "demoted_edges": demoted, "pinned_edges": pinned,
              "threshold": RETENTION_DEMOTE}
    mind["decay"] = report
    return report


def sm2_quality(node, since=None):
    """Highest deterministic rehearsal signal since the prior review."""
    since = float(node.get("review", {}).get("last_review", 0.0) \
                  if since is None else since)
    signals = node.get("signals", {})
    for sources, quality in (
            (("user-ask", "user-recall", "user"), 5),
            (("thought", "ponder", "muse", "grade"), 4)):
        for src in sources:
            try:
                if float(signals.get(src, 0.0)) > since:
                    return quality
            except (TypeError, ValueError):
                continue
    return 0


def sm2_update(review, quality, now=None):
    """Apply the original SM-2 ease/interval update to one review record."""
    now = _finite_float(time.time() if now is None else now,
                        "SM-2 update time")
    q = max(0, min(5, int(quality)))
    old_ef = _bounded_float(review.get("ef", SM2_EF_INITIAL), "SM-2 ease",
                            SM2_EF_FLOOR, MAX_SM2_EF)
    old_reps = max(
        0, _sm2_review_integer(review.get("reps", 0)))
    # The response updates E-Factor after the interval decision for every
    # quality, including a lapse. The updated factor is carried into the next
    # repetition; low quality also restarts the repetition sequence.
    ef = old_ef + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)
    ef = min(MAX_SM2_EF, max(SM2_EF_FLOOR, ef))
    if q < 3:
        # The failed review is not repetition one; the next success still
        # uses I(1), now with the response-adjusted E-Factor carried forward.
        reps = 0
        interval = SM2_FIRST_INTERVAL
    else:
        reps = old_reps + 1
        if reps == 1:
            interval = SM2_FIRST_INTERVAL
        elif reps == 2:
            interval = SM2_SECOND_INTERVAL
        else:
            prior = max(
                SM2_SECOND_INTERVAL,
                _sm2_review_integer(
                    review.get("interval_days", SM2_SECOND_INTERVAL)))
            interval = min(MAX_REVIEW_INTERVAL_DAYS,
                           int(math.ceil(prior * old_ef)))
    review.update({"ef": ef, "reps": reps, "interval_days": interval,
                   "due_at": now + interval * SECONDS_PER_DAY,
                   "last_review": now, "last_quality": q,
                   "reviews": _sm2_review_integer(
                       review.get("reviews", 0)) + 1})
    return review


def plan_rehearsal(mind, now=None):
    """Return due important pages without changing rehearsal state.

    Planning must remain side-effect free because page embedding is the commit
    gate.  A missing review record is treated as due in the returned plan but
    is not materialized until the corresponding embed succeeds.
    """
    now = time.time() if now is None else float(now)
    planned = []
    for slug in sorted(mind.get("nodes", {})):
        node = mind["nodes"][slug]
        if not isinstance(node, dict) or not _important(node):
            continue
        review = node.get("review")
        if isinstance(review, dict):
            try:
                due_at = float(review.get("due_at", now))
            except (TypeError, ValueError):
                due_at = now
            try:
                since = float(review.get("last_review", 0.0))
            except (TypeError, ValueError):
                since = 0.0
        else:
            due_at = now
            since = 0.0
        if due_at <= now:
            planned.append({"slug": slug,
                            "quality": sm2_quality(node, since=since),
                            "due_at": due_at})
    return planned


def select_rehearsal_window(planned, cursor, limit=WORKSPACE_K):
    """Choose one bounded rotating window without changing the plan.

    The persisted cursor moves by attempts, not successes. A missing page or
    failed embed therefore cannot hold every lexically later due page behind
    it forever. ``WORKSPACE_K`` is the compatibility name for the existing
    measured window bound; the nightly worker does not invent another size.
    """
    if not isinstance(planned, list):
        raise ValueError("rehearsal plan must be a list")
    if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
        raise ValueError("rehearsal cursor must be a non-negative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) \
            or limit <= 0 or limit > WORKSPACE_K:
        raise ValueError("rehearsal window exceeds the attention bound")
    if not planned:
        return [], 0, 0
    start = cursor % len(planned)
    attempted = min(limit, len(planned))
    selected = [planned[(start + offset) % len(planned)]
                for offset in range(attempted)]
    return selected, (start + attempted) % len(planned), \
        len(planned) - attempted


def apply_rehearsal(mind, planned, now=None):
    """Commit one planned rehearsal after its page embed has succeeded."""
    now = time.time() if now is None else float(now)
    slug = planned.get("slug") if isinstance(planned, dict) else None
    node = mind.get("nodes", {}).get(slug)
    if not isinstance(node, dict) or not _important(node):
        return None
    review = _ensure_review(node, now)
    try:
        if float(review.get("due_at", now)) > now:
            return None
    except (TypeError, ValueError):
        review["due_at"] = now
    quality = planned.get("quality", 0)
    sm2_update(review, quality, now)
    touch(mind, slug, now, src="review")
    for key in list(mind.get("edges", {})):
        try:
            a, b = key.split("|", 1)
        except (AttributeError, ValueError):
            continue
        if slug == a or slug == b:
            hebb(mind, a, b, amount=1, ts=now)
    return {"slug": slug, "quality": review["last_quality"],
            "interval_days": review["interval_days"],
            "ef": review["ef"], "due_at": review["due_at"]}


def run_rehearsal(mind, now=None):
    """Compatibility name for the now read-only rehearsal planner."""
    return plan_rehearsal(mind, now=now)


def memory_summary_view(mind, now=None):
    """Project status from normalized policy state without mutating it."""
    now = time.time() if now is None else float(now)
    if not isinstance(mind, dict) \
            or not isinstance(mind.get("nodes"), dict) \
            or not isinstance(mind.get("edges"), dict):
        raise ValueError("mind summary requires normalized node and edge maps")
    complete = mind.get("familiarity_complete", False)
    pending = mind.get("familiarity_bootstrap_pending", False)
    if type(complete) is not bool or type(pending) is not bool \
            or complete and pending:
        raise ValueError("mind summary familiarity state is invalid")
    familiarity_status = ("bootstrap-pending" if pending else
                          "complete" if complete else "incomplete")
    eligible = due = pinned = 0
    for node in mind["nodes"].values():
        if not isinstance(node, dict):
            raise ValueError("mind summary node must be an object")
        if node.get("pins"):
            pinned += 1
        if _important(node):
            eligible += 1
            review = node.get("review")
            if not isinstance(review, dict) \
                    or float(review.get("due_at", now)) <= now:
                due += 1
    active = demoted = pinned_edges = 0
    for edge in mind["edges"].values():
        if not isinstance(edge, dict):
            raise ValueError("mind summary edge must be an object")
        if edge.get("pins"):
            pinned_edges += 1
        if retention(edge, now) < RETENTION_DEMOTE:
            demoted += 1
        else:
            active += 1
    decay = {"at": now, "active_edges": active,
             "demoted_edges": demoted, "pinned_edges": pinned_edges,
             "threshold": RETENTION_DEMOTE}
    return {"v": mind.get("v"), "nodes": len(mind["nodes"]),
            "familiarity_status": familiarity_status,
            "edges": len(mind["edges"]), "eligible": eligible,
            "due": due, "pinned": pinned, **decay}


def memory_summary(mind, now=None):
    """Materialize rehearsal/decay state, then return its status projection."""
    now = time.time() if now is None else float(now)
    migrate_mind(mind, now=now)
    for node in mind["nodes"].values():
        if _important(node):
            _ensure_review(node, now)
    decay_sweep(mind, now)
    return memory_summary_view(mind, now)


# ------------------------------------------------------------ usage salience

def usage_activation_snapshot(node, as_of):
    """Return a bounded usage-score observation without a numeric sentinel.

    The calculation exposes availability, the captured clock, and the
    exact/tail split explicitly.
    Persisted recent uses must be chronological, fall between creation and the
    captured clock, fit the fixed recent window, and not outweigh the recorded
    total. The input mapping is never normalized in place.
    """
    def usage_number(value, label):
        if isinstance(value, bool):
            raise ValueError(f"{label} must be finite")
        return _finite_float(value, label)

    now = usage_number(as_of, "usage activation observation time")
    if not isinstance(node, dict):
        raise ValueError("usage activation node must be an object")
    n = usage_number(
        node.get("n", 0.0), "usage activation total weight")
    if n < 0:
        raise ValueError("usage activation total weight must be non-negative")
    t0 = usage_number(
        node.get("t0", now), "usage activation creation time")
    if t0 > now:
        raise ValueError("usage activation creation time is in the future")
    raw_rt = node.get("rt", [])
    if not isinstance(raw_rt, list) or len(raw_rt) > ACTR_K:
        raise ValueError("usage activation recent history exceeds its bound")

    recent = []
    previous = t0
    for entry in raw_rt:
        if isinstance(entry, (list, tuple)):
            if len(entry) != 2:
                raise ValueError(
                    "usage activation recent entry must have two fields")
            stamp, weight = entry
        else:
            stamp, weight = entry, 1.0
        stamp = usage_number(stamp, "usage activation use time")
        weight = usage_number(weight, "usage activation use weight")
        if stamp < previous or stamp > now:
            raise ValueError(
                "usage activation recent history is not chronological")
        if weight < 0:
            raise ValueError(
                "usage activation use weight must be non-negative")
        recent.append((stamp, weight))
        previous = stamp

    try:
        recent_weight = math.fsum(weight for _stamp, weight in recent)
    except OverflowError as exc:
        raise ValueError("usage activation recent weight must be finite") \
            from exc
    if recent_weight > n and not math.isclose(
            recent_weight, n, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError(
            "usage activation recent weight exceeds recorded total")
    tail_weight = max(0.0, n - recent_weight)
    if not recent or n <= 0:
        return {
            "status": "unavailable",
            "score": None,
            "as_of": now,
            "exact_recent_weight": recent_weight,
            "tail_weight": tail_weight,
            "reason": "no-usage-history",
        }

    terms = []
    for stamp, weight in recent:
        age = max(60.0, now - stamp)
        terms.append(weight * age ** (-ACTR_D))
    try:
        mass = math.fsum(terms)
    except OverflowError as exc:
        raise ValueError("usage activation mass must be finite") from exc
    if tail_weight > 0:
        oldest_age = max(3600.0, now - t0)
        recent_boundary_age = max(60.0, now - recent[0][0])
        if oldest_age > recent_boundary_age:
            mass += tail_weight * (
                oldest_age ** (1 - ACTR_D)
                - recent_boundary_age ** (1 - ACTR_D)) \
                / ((1 - ACTR_D)
                   * (oldest_age - recent_boundary_age))
        else:
            mass += tail_weight * oldest_age ** (-ACTR_D)
    mass = _finite_float(mass, "usage activation mass")
    if mass <= 0:
        return {
            "status": "unavailable",
            "score": None,
            "as_of": now,
            "exact_recent_weight": recent_weight,
            "tail_weight": tail_weight,
            "reason": "zero-weight-usage-history",
        }
    score = _finite_float(math.log(mass), "usage activation score")
    return {
        "status": "available",
        "score": score,
        "as_of": now,
        "exact_recent_weight": recent_weight,
        "tail_weight": tail_weight,
        "reason": None,
    }


def actr_base(node, now=None):
    """Compatibility-named usage scalar for callers not yet on the envelope."""
    now = time.time() if now is None else now
    snapshot = usage_activation_snapshot(node, now)
    return snapshot["score"] \
        if snapshot["status"] == "available" else -10.0


def activations(mind, slugs, now=None):
    now = time.time() if now is None else float(now)
    return {s: actr_base(mind["nodes"].get(s, {}), now) for s in slugs}


# ------------------------------------------------ novelty scoring and intake

def novelty_encoding_gate(
        mind, organ, kind, entities, batch_kinds, observed_at=None):
    """Compare an admitted observation with stored familiarity.

    Input is one organ/kind observation, its linked entities, its local event
    surround, and one captured time. Output separates mismatch, the bounded
    novelty-score gain, and its reasons. All input is admitted before the
    copied familiarity map replaces state, so refusal is atomic.  This is a
    deterministic software policy; it measures stored familiarity only.
    """
    if not isinstance(mind, dict) or not isinstance(mind.get("seen"), dict):
        raise ValueError("novelty familiarity state must be an object")
    familiarity_complete = mind.get("familiarity_complete", False)
    if type(familiarity_complete) is not bool:
        raise ValueError("novelty familiarity completeness must be boolean")
    pending = mind.get("familiarity_bootstrap_pending", False)
    if type(pending) is not bool:
        raise ValueError("novelty familiarity bootstrap marker must be boolean")
    if pending:
        raise ValueError("novelty familiarity bootstrap is pending")
    _canonical_familiarity_token(organ, "novelty familiarity organ")
    _canonical_familiarity_token(kind, "novelty familiarity kind")
    if not isinstance(entities, (list, tuple)):
        raise ValueError("novelty familiarity entities must be a sequence")
    for value in entities:
        _canonical_familiarity_entity(
            value, "novelty familiarity entity")
    if not isinstance(batch_kinds, (list, tuple)):
        raise ValueError("novelty familiarity surround must be a sequence")
    for value in batch_kinds:
        _canonical_familiarity_token(
            value, "novelty familiarity surround kind")
    ts = _finite_float(
        time.time() if observed_at is None else observed_at,
        "novelty observation time")
    seen = _normalized_familiarity_map(mind["seen"])
    score, reasons = 0.0, []
    for e in dict.fromkeys(entities):
        last = seen.get(e)
        if last is None:
            if familiarity_complete:
                score += 0.40
                reasons.append(f"first recorded occurrence of {e}")
        elif ts - last > 30 * 86400:
            score += 0.20
            reasons.append(f"{e} recurs after a 30d+ observation gap")
        # Historical/backfill sources may arrive after a newer observation.
        # Familiarity is a latest-observation watermark, never arrival order.
        seen[e] = ts if last is None else max(last, ts)
    pair = f"pair:{organ}:{kind}"
    if pair not in seen and familiarity_complete:
        score += 0.20
        reasons.append(f"new event shape {organ}/{kind}")
    pair_last = seen.get(pair)
    seen[pair] = ts if pair_last is None else max(pair_last, ts)
    # Isolation bonus: distinct within its local admitted surround.
    if batch_kinds:
        same = sum(1 for k in batch_kinds if k == kind)
        if len(batch_kinds) >= 5 and same / len(batch_kinds) <= 0.1:
            score += 0.15
            reasons.append("isolated among unlike events")
    score = min(1.0, score)
    mind["seen"] = seen
    return {
        "status": "observed",
        "mismatch": bool(reasons),
        "score": score,
        "encoding_gain": score,
        "reasons": reasons,
        "observed_at": ts,
        "familiarity_status": (
            "complete" if familiarity_complete else "incomplete"),
    }


def novelty(mind, organ, kind, entities, batch_kinds, ts=None):
    """Compatibility tuple for callers migrating to ``novelty_encoding_gate``."""
    result = novelty_encoding_gate(
        mind, organ, kind, entities, batch_kinds, observed_at=ts)
    return result["score"], result["reasons"]


# ---------------------------------------------------------------- surprise
# Honest estimator: desktop evidence is bursty, so no Poisson, no "bits".
# Each (source, band) cohort keeps sampled ADMISSION counts, not source
# production rates. Unknown organs/hours never become synthetic zeros.
# An explicitly sampled zero can be unusual among active intake buckets,
# but neither a partial bucket nor its absence proves source inactivity.

MIN_BAND_SAMPLES = 30

def _band(ts):
    lt = time.gmtime(ts)
    kind = "we" if lt.tm_wday >= 5 else "wd"
    return f"{kind}:{lt.tm_hour // 6}"       # four 6h blocks × wd/we


def _surprise_cache_candidate(mind):
    """Copy current intake caches, or retire unversioned derived samples.

    Old histories contain synthetic zeros with no coverage record. They
    cannot become observed samples by changing a label. Corpus records and
    unrelated policy state is untouched by this cache migration.
    """
    cooldown = mind.get("cooldown", {})
    if not isinstance(cooldown, dict) \
            or any(not isinstance(key, str) for key in cooldown):
        raise ValueError("surprise cooldown cache is invalid")
    if "surprise_basis" not in mind:
        return {}, {}, {key: value for key, value in cooldown.items()
                        if not key.startswith("s:")}
    if mind["surprise_basis"] != SURPRISE_BASIS:
        raise ValueError("surprise observation basis is unsupported")
    buf = mind.get("hourbuf", {})
    hist = mind.get("hist", {})
    if not isinstance(buf, dict) or not isinstance(hist, dict):
        raise ValueError("surprise intake cache is invalid")
    for organ, record in buf.items():
        if not isinstance(organ, str) or not organ \
                or not isinstance(record, dict) \
                or set(record) != {"hour", "count"} \
                or type(record["hour"]) is not int \
                or type(record["count"]) is not int \
                or record["count"] < 0:
            raise ValueError("surprise intake bucket is invalid")
    for key, samples in hist.items():
        if not isinstance(key, str) or not key \
                or not isinstance(samples, list) or len(samples) > 120 \
                or any(type(value) is not int or value < 0
                       for value in samples):
            raise ValueError("surprise intake history is invalid")
    for key, stamp in cooldown.items():
        if key.startswith("s:"):
            _finite_float(stamp, "surprise cooldown time")
    return ({organ: dict(record) for organ, record in buf.items()},
            {key: list(samples) for key, samples in hist.items()},
            dict(cooldown))


def surprisal_update(mind, organ_counts, ts=None):
    """Compare explicit admission samples in their intake-hour buckets.

    Missing keys and missing hours are unknown, not zero. An explicit zero
    describes only the caller's sample, never complete source coverage.
    Current pulse callers provide newly admitted positive counts or no
    samples; they cannot certify an inactive source. Admit the whole update
    before replacing caches so invalid input cannot partly advance them.
    """
    ts = _finite_float(time.time() if ts is None else ts,
                       "surprise observation time")
    if not isinstance(organ_counts, dict) or any(
            not isinstance(organ, str) or not organ
            or type(count) is not int or count < 0
            for organ, count in organ_counts.items()):
        raise ValueError("surprise intake count must be a non-negative integer")
    hour = int(ts // 3600)
    buf, hist, cooldown = _surprise_cache_candidate(mind)
    if any(organ in buf and buf[organ]["hour"] > hour
           for organ in organ_counts):
        raise ValueError("surprise observation hour moved backward")
    findings = []
    for organ in sorted(organ_counts):
        cnt = organ_counts[organ]
        b = buf.setdefault(organ, {"hour": hour, "count": 0})
        if b["hour"] == hour:
            b["count"] += cnt
            continue
        x = b["count"]
        key = f"{organ}|{_band(b['hour'] * 3600)}"
        samples = hist.get(key, [])
        n = len(samples)
        if n >= MIN_BAND_SAMPLES:
            cd_key = f"s:{key}"
            cooled = ts - cooldown.get(cd_key, 0) > 6 * 3600
            hi = max(samples)
            active_frac = sum(1 for v in samples if v > 0) / n
            if x > hi and x >= 5 and cooled:
                cooldown[cd_key] = ts
                findings.append((organ, "spike",
                    f"SIA admitted {x} events from {organ} into an hourly "
                    f"intake bucket — above {n} prior sampled buckets "
                    f"in this band (previous max {hi}). "
                    f"Sampling may be incomplete."))
            if x == 0 and active_frac >= 0.9 and cooled:
                cooldown[cd_key] = ts
                findings.append((organ, "absence",
                    f"SIA recorded zero {organ} events in an explicitly "
                    f"sampled hourly intake bucket; "
                    f"{round(active_frac * 100)}% of {n} prior sampled "
                    f"buckets in this band had admitted events. "
                    f"Sampling may be incomplete; this does not establish "
                    f"source inactivity."))
        hist[key] = (samples + [x])[-120:]
        buf[organ] = {"hour": hour, "count": cnt}
    mind.update(hourbuf=buf, hist=hist, cooldown=cooldown,
                surprise_basis=SURPRISE_BASIS)
    return findings


# -------------------------------------------------------- bounded attention

def _ws_bucket(slug):
    """Per-source cap bucket: events/<o> and organs/<o> share the source
    bucket; every other collection (thoughts, units, packages, synthesis…)
    is one bucket, so near-duplicate echoes can't flood the workspace."""
    if slug.startswith("events/"):
        parts = slug.split("/")
        return parts[1] if len(parts) > 1 else slug
    if slug.startswith("organs/"):
        return slug.split("/")[-1]
    return slug.split("/")[0]


def attention_window_broadcast(
        mind, organ_arousal, *, consumers, as_of=None):
    """Select one bounded attention window and copy it to named consumers.

    This pure component returns every candidate contribution, the selected
    slots, and identical per-consumer broadcasts. It makes no claim beyond
    that selection and does not mutate the supplied state snapshot.
    """
    if not isinstance(mind, dict) or not isinstance(mind.get("nodes"), dict) \
            or not isinstance(mind.get("workspace", []), list):
        raise ValueError("attention input state is invalid")
    if not isinstance(organ_arousal, dict) or any(
            not isinstance(key, str) or not key
            for key in organ_arousal):
        raise ValueError("attention safety-priority map is invalid")
    if not isinstance(consumers, (list, tuple)) or not consumers \
            or any(not isinstance(value, str) or not value
                   for value in consumers) \
            or len(consumers) != len(set(consumers)):
        raise ValueError("attention broadcast consumers are invalid")
    now = _finite_float(
        time.time() if as_of is None else as_of, "attention observation time")
    cands = {}
    for slug, node in mind["nodes"].items():
        if not isinstance(slug, str) or not slug \
                or not isinstance(node, dict):
            raise ValueError("attention candidate is invalid")
        rt = node.get("rt", [])
        if not rt:
            continue
        last = rt[-1][0] if isinstance(rt[-1], list) else rt[-1]
        last = _finite_float(last, "attention candidate time")
        if now - last > 24 * 3600:
            continue
        arousal = _bounded_float(
            organ_arousal.get(_ws_bucket(slug), 0.0),
            "attention safety-priority value", 0.0, 1.0)
        score = actr_base(node, now) + 2.0 * arousal
        cands[slug] = score
    incumbents = set(mind.get("workspace", []))

    def adjusted_score(item):
        return item[1] + (0.2 if item[0] in incumbents else 0.0)
    ranked = sorted(
        cands.items(), key=lambda item: (-adjusted_score(item), item[0]))
    ws, per_bucket = [], {}
    for item in ranked:
        if adjusted_score(item) < -2.5:       # score threshold (the sort key is
            break                             # monotone, so break is safe)
        b = _ws_bucket(item[0])
        if per_bucket.get(b, 0) >= 2:         # per-bucket cap
            continue
        per_bucket[b] = per_bucket.get(b, 0) + 1
        ws.append(item[0])
        if len(ws) >= WORKSPACE_K:
            break
    selected = set(ws)
    rows = []
    for slug, score in sorted(cands.items()):
        gain = 0.2 if slug in incumbents else 0.0
        rows.append({
            "slug": slug,
            "bucket": _ws_bucket(slug),
            "score": score,
            "incumbent_gain": gain,
            "adjusted_score": score + gain,
            "ignited": score + gain >= -2.5,
            "selected": slug in selected,
        })
    return {
        "status": "available",
        "as_of": now,
        "slots": list(ws),
        "broadcast": {consumer: list(ws) for consumer in consumers},
        "candidates": rows,
    }


def rebuild_workspace(mind, organ_arousal, now=None):
    """Persist the selected bounded attention window for resident consumers."""
    result = attention_window_broadcast(
        mind, organ_arousal,
        consumers=("resident-status", "context-selection"), as_of=now)
    mind["workspace"] = result["slots"]
    return result["slots"]


# ------------------------------------------------ seeded distant-node walk

def muse(mind, graph, day, ledger_head, now=None):
    """Once daily, find two high-usage-score nodes.

    The function name is a compatibility API for this seeded graph walk. It
    finds nodes with no direct edge, in different regions, joined only by a
    low-traffic path. The captured timestamp plus seeded shuffle make the result replayable.
    Returns (text, links) or None."""
    if mind.get("musing_day") == day or not graph:
        return None
    nodes = sorted({n["id"] for n in graph.get("nodes", [])})
    if len(nodes) < 10:
        return None
    adj = {}
    for e in graph.get("edges", []):
        adj.setdefault(e["s"], set()).add(e["d"])
        adj.setdefault(e["d"], set()).add(e["s"])
    now = _finite_float(
        time.time() if now is None else now, "musing observation time")
    snapshots = {
        slug: usage_activation_snapshot(
            mind.get("nodes", {}).get(slug, {}), now)
        for slug in nodes
    }
    available = {
        slug: snapshot["score"]
        for slug, snapshot in snapshots.items()
        if snapshot["status"] == "available"
    }
    if len(available) < 2:
        mind["musing_day"] = day
        return None
    top = sorted(available, key=lambda slug: (-available[slug], slug))[:24]
    rng = random.Random(hashlib.sha256(
        (day + "|" + ledger_head).encode()).hexdigest())
    rng.shuffle(top)
    # The root hub links broadly, so a path through it is trivial; this walk
    # searches only non-root routes.
    adj = {k: {m for m in v if m != "sia/cortex"}
           for k, v in adj.items() if k != "sia/cortex"}
    traffic = {}
    for source, neighbors in adj.items():
        for target in neighbors:
            key = "|".join(sorted((source, target)))
            record = mind.get("edges", {}).get(key)
            value = record.get("w", 0.0) if isinstance(record, dict) \
                else (record if record is not None else 0.0)
            try:
                value = float(value)
                if not math.isfinite(value) or value < 0:
                    raise ValueError
            except (TypeError, ValueError, OverflowError):
                value = math.inf
            traffic[key] = value
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            a, b = top[i], top[j]
            if a == "sia/cortex" or b == "sia/cortex":
                continue
            if b in adj.get(a, ()) or a.split("/")[0] == b.split("/")[0]:
                continue
            path = _low_traffic_path(adj, traffic, a, b, 4)
            if path and len(path) >= 4:
                mind["musing_day"] = day
                chain = " → ".join(path)
                return (f"Graph-link proposal: {a} and {b} share no direct link, yet "
                        f"they connect through {chain}. An association, "
                        f"not a causal claim.", [a, b])
    mind["musing_day"] = day
    return None


def _low_traffic_path(adj, traffic, a, b, max_hops, min_nodes=4):
    """Choose a replayable bounded route, preferring low accumulated traffic.

    One best path per endpoint is retained at each hop, which bounds the
    search by graph size and ``max_hops``.  Route order is total and stable:
    accumulated co-return edge-weight sum, then hop count, then the slug tuple.
    """
    frontier = [(0.0, (a,))]
    found = []
    for _ in range(max_hops):
        next_by_endpoint = {}
        for total, path in frontier:
            node = path[-1]
            for neighbor in sorted(adj.get(node, ())):
                if neighbor in path:
                    continue
                edge = "|".join(sorted((node, neighbor)))
                candidate = (total + traffic.get(edge, 0.0),
                             path + (neighbor,))
                if neighbor == b:
                    if len(candidate[1]) >= min_nodes:
                        found.append(candidate)
                    continue
                current = next_by_endpoint.get(neighbor)
                if current is None or candidate < current:
                    next_by_endpoint[neighbor] = candidate
        frontier = sorted(next_by_endpoint.values())
    if not found:
        return None
    _total, path = min(found, key=lambda item: (
        item[0], len(item[1]), item[1]))
    return list(path)


# ---------------------------------------------------------- PPR retrieval
# Used out-of-process by `sia ask` against the exported graph snapshot.


class AssociativeRerankUnavailable(RuntimeError):
    """The configured graph lane could not influence this result set."""


def _ppr_power_iteration(pers, adj):
    """Run the PPR power iteration and return the UN-normalised rank vector.

    Split out of ``ppr_rerank`` so the mass invariant can actually be tested.
    The caller divides by ``max(rank)``, and that normalisation is why a pure
    leak — dropping the dangling teleport entirely — is invisible from the
    outside: both updates have the form ``c*pers + (1-damping)*A*rank`` and
    differ only in ``c``, so their fixed points lie on the same ray and the
    normalised output is identical. Mass conservation is a property of this
    vector, not of the ranking, so it has to be asserted here or not at all.
    """
    rank = pers[:]
    for _ in range(PPR_ITers):
        nxt = [PPR_DAMPING * p for p in pers]
        dangling = 0.0
        for i, r in enumerate(rank):
            if r == 0:
                continue
            if not adj[i]:
                dangling += (1 - PPR_DAMPING) * r
                continue
            total_w = sum(w for _, w in adj[i]) or 1.0
            share = (1 - PPR_DAMPING) * r / total_w
            for j, weight in adj[i]:
                nxt[j] += share * weight
        if dangling:
            # dangling mass teleports back to the personalization vector, so
            # rank that reaches a sink returns to the seeds instead of
            # evaporating. Without this the total shrinks every iteration.
            for k, pk in enumerate(pers):
                if pk:
                    nxt[k] += dangling * pk
        rank = nxt
    return rank


def _associative_unavailable(reason, as_of, candidate_scope,
                             retrieval_adjacency=()):
    return {
        "status": "unavailable",
        "reason": reason,
        "as_of": as_of,
        "candidate_scope": candidate_scope,
        "rows": [],
        "retrieval_adjacency": list(retrieval_adjacency),
    }


def associative_components(
        graph, retrieval_hits, mind=None, as_of=None, include_learned=False,
        expand_candidates=False):
    """Expose every factor in SIA's optional associative retrieval lane.

    The default is a compatibility analysis over the supplied retrieval window.
    ``expand_candidates=True`` additionally returns graph nodes reachable from
    a positive retrieval seed; an expanded row has ``retrieval_score=None``
    rather than pretending that an unscored candidate received a zero input.
    Accumulated co-return pairs can be admitted only as explicitly labelled
    retrieval-only adjacency and never modify or mint a factual graph edge.
    """
    now = _finite_float(
        time.time() if as_of is None else as_of,
        "associative retrieval observation time")
    if type(include_learned) is not bool \
            or type(expand_candidates) is not bool:
        raise ValueError("associative retrieval options must be boolean")
    candidate_scope = "retrieval-plus-reachable-graph" \
        if expand_candidates else "retrieval-window"
    if not isinstance(graph, dict) \
            or not isinstance(graph.get("nodes"), list) \
            or not isinstance(graph.get("edges"), list):
        raise ValueError("associative retrieval graph is invalid")
    if not isinstance(retrieval_hits, (list, tuple)):
        raise ValueError("associative retrieval input hits are invalid")
    if mind is not None and (
            not isinstance(mind, dict)
            or not isinstance(mind.get("nodes", {}), dict)
            or not isinstance(mind.get("edges", {}), dict)):
        raise ValueError("associative retrieval mind state is invalid")

    types = {}
    declared_origins = {}
    for item in graph["nodes"]:
        if not isinstance(item, dict):
            raise ValueError("associative retrieval graph node is invalid")
        slug = item.get("id")
        if not isinstance(slug, str) \
                or not re.fullmatch(r"[a-z0-9][a-z0-9/._-]{0,199}", slug) \
                or any(part in ("", ".", "..") for part in slug.split("/")) \
                or slug in types:
            raise ValueError("associative retrieval graph node is invalid")
        ptype = item.get("t", "")
        if not isinstance(ptype, str):
            raise ValueError("associative retrieval graph node type is invalid")
        types[slug] = ptype
        if "origin" in item:
            declared_origins[slug] = item["origin"]
    nodes = sorted(types)
    idx = {slug: index for index, slug in enumerate(nodes)}

    hits = []
    retrieval_scores = {}
    for item in retrieval_hits:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("associative retrieval input hit is invalid")
        slug, raw_score = item
        if not isinstance(slug, str) \
                or not re.fullmatch(r"[a-z0-9][a-z0-9/._-]{0,199}", slug) \
                or any(part in ("", ".", "..") for part in slug.split("/")) \
                or slug in retrieval_scores:
            raise ValueError("associative retrieval input hit is invalid")
        score = _finite_float(
            raw_score, "associative retrieval input score")
        if score < 0:
            raise ValueError(
                "associative retrieval input score must be non-negative")
        hits.append((slug, score))
        retrieval_scores[slug] = score
    if not hits:
        return _associative_unavailable(
            "no-retrieval-candidates", now, candidate_scope)

    adj = [[] for _slug in nodes]
    degree = [0 for _slug in nodes]
    factual_pairs = set()
    retrieval_adjacency = []

    def admit_edge(source, target, weight, *, provenance, scope,
                   relation=None):
        source_index = idx[source]
        target_index = idx[target]
        adj[source_index].append((target_index, weight))
        adj[target_index].append((source_index, weight))
        degree[source_index] += 1
        degree[target_index] += 1
        exposed = {
            "s": source,
            "d": target,
            "weight": weight,
            "provenance": provenance,
            "scope": scope,
        }
        if relation is not None:
            exposed["relation"] = relation
        retrieval_adjacency.append(exposed)

    for edge in graph["edges"]:
        if not isinstance(edge, dict):
            raise ValueError("associative retrieval graph edge is invalid")
        source, target = edge.get("s"), edge.get("d")
        relation = edge.get("t", "mentions")
        if not isinstance(source, str) or not isinstance(target, str) \
                or source not in idx or target not in idx or source == target \
                or not isinstance(relation, str) or not relation:
            raise ValueError("associative retrieval graph edge is invalid")
        key = "|".join(sorted((source, target)))
        factual_pairs.add(key)
        weight = 1.0
        if mind is not None:
            stored = mind.get("edges", {}).get(key)
            if stored is not None:
                record = _edge_record(copy.deepcopy(stored), now)
                edge_retention = retention(record, now)
                if edge_retention < RETENTION_DEMOTE:
                    continue
                weight = edge_retention * max(1.0, record["w"])
        admit_edge(
            source, target, weight, provenance="factual-graph",
            scope="corpus-graph", relation=relation)

    if include_learned and mind is not None:
        for key, stored in sorted(mind.get("edges", {}).items()):
            if not isinstance(key, str) or key.count("|") != 1:
                raise ValueError(
                    "associative retrieval co-return edge is invalid")
            source, target = key.split("|", 1)
            if key != "|".join(sorted((source, target))):
                raise ValueError(
                    "associative retrieval co-return edge is invalid")
            if key in factual_pairs or source not in idx or target not in idx:
                continue
            if source == target:
                raise ValueError(
                    "associative retrieval co-return edge is invalid")
            record = _edge_record(copy.deepcopy(stored), now)
            if record.get("graph_discovered") or record["w"] <= 0:
                continue
            edge_retention = retention(record, now)
            if edge_retention < RETENTION_DEMOTE:
                continue
            admit_edge(
                source, target,
                edge_retention * max(1.0, record["w"]),
                provenance="learned-coreturn", scope="retrieval-only")

    retrieval_adjacency.sort(key=lambda edge: (
        edge["s"], edge["d"], edge["provenance"],
        edge.get("relation", "")))
    if not any(adj):
        return _associative_unavailable(
            "graph-has-no-usable-edges", now, candidate_scope,
            retrieval_adjacency)

    maximum_retrieval = max(score for _slug, score in hits)
    if maximum_retrieval <= 0:
        return _associative_unavailable(
            "zero-connected-seed-mass", now, candidate_scope,
            retrieval_adjacency)
    personalization = [0.0 for _slug in nodes]
    positive_seed_indices = []
    for slug, score in hits:
        index = idx.get(slug)
        if index is None or score <= 0:
            continue
        personalization[index] = (score / maximum_retrieval) \
            / max(1, degree[index])
        positive_seed_indices.append(index)
    connected_seed_mass = math.fsum(
        personalization[index] for index in positive_seed_indices
        if adj[index])
    if connected_seed_mass <= 0:
        return _associative_unavailable(
            "zero-connected-seed-mass", now, candidate_scope,
            retrieval_adjacency)
    total_seed_mass = math.fsum(personalization)
    if not math.isfinite(total_seed_mass) or total_seed_mass <= 0:
        raise ValueError("associative retrieval seed mass is invalid")
    personalization = [value / total_seed_mass
                       for value in personalization]
    rank = _ppr_power_iteration(personalization, adj)
    if len(rank) != len(nodes) or any(
            not math.isfinite(value) or value < 0 for value in rank):
        raise ValueError("associative retrieval propagation is invalid")
    maximum_rank = max(rank) if rank else 0.0

    candidate_slugs = [slug for slug, _score in hits]
    if expand_candidates:
        reachable = set(positive_seed_indices)
        frontier = list(positive_seed_indices)
        while frontier:
            current = frontier.pop()
            for neighbor, _weight in adj[current]:
                if neighbor not in reachable:
                    reachable.add(neighbor)
                    frontier.append(neighbor)
        candidate_slugs.extend(
            slug for slug in nodes
            if idx[slug] in reachable and slug not in retrieval_scores)

    usage = {}
    for slug in candidate_slugs:
        node = mind.get("nodes", {}).get(slug, {}) \
            if mind is not None else {}
        usage[slug] = usage_activation_snapshot(node, now)
    available_scores = [
        snapshot["score"] for snapshot in usage.values()
        if snapshot["status"] == "available"
    ]
    if available_scores:
        lowest_usage = min(available_scores)
        highest_usage = max(available_scores)
    else:
        lowest_usage, highest_usage = 0.0, 0.0

    rows = []
    for slug in candidate_slugs:
        retrieval_score = retrieval_scores.get(slug)
        retrieval_normalized = retrieval_score / maximum_retrieval \
            if retrieval_score is not None else 0.0
        index = idx.get(slug)
        propagated = rank[index] if index is not None else None
        propagation_normalized = (
            propagated / maximum_rank
            if propagated is not None and maximum_rank > 0 else 0.0)
        origin = origin_class(
            slug, types.get(slug, ""), declared_origins.get(slug))
        origin_weight = ORIGIN_WEIGHT.get(
            origin, ORIGIN_WEIGHT["legacy-unlabeled"])
        node = mind.get("nodes", {}).get(slug) \
            if mind is not None else None
        retained = retention(node, now) if node is not None else 1.0
        usage_snapshot = dict(usage[slug])
        usage_normalized = 0.0
        if usage_snapshot["status"] == "available" \
                and highest_usage > lowest_usage:
            usage_normalized = (
                usage_snapshot["score"] - lowest_usage) \
                / (highest_usage - lowest_usage)
        usage_snapshot["normalized"] = usage_normalized
        if expand_candidates:
            associative_base = retrieval_normalized \
                + PPR_TIEBREAK_GAIN * propagation_normalized
            final = associative_base * origin_weight * retained \
                * (1 + ACTIVATION_TIEBREAK_GAIN * usage_normalized)
        else:
            final = retrieval_normalized * origin_weight * retained \
                * (1 + PPR_TIEBREAK_GAIN * propagation_normalized
                   + ACTIVATION_TIEBREAK_GAIN * usage_normalized)
        rows.append({
            "slug": slug,
            "retrieval_score": retrieval_score,
            "origin": {"class": origin, "weight": origin_weight},
            "retention": retained,
            "propagation": propagated,
            "usage": usage_snapshot,
            "final": final,
        })
    return {
        "status": "applied",
        "reason": None,
        "as_of": now,
        "candidate_scope": candidate_scope,
        "rows": rows,
        "retrieval_adjacency": retrieval_adjacency,
    }


def ppr_rerank(graph, retrieval_hits, *, mind=None, now=None, origins=None,
               require_associative=False):
    """Retrieval hits seed Personalized PageRank over the typed graph.

    Input score remains primary; named, benchmark-frozen gains apply graph
    propagation and usage salience as multiplicative
    tie-breakers rather than advertising ineffective tuning parameters.
    retrieval_hits: [(slug, score)] best-first. Returns [(slug, blended)]."""
    if not retrieval_hits:
        return retrieval_hits
    now = time.time() if now is None else float(now)
    graph_nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    types = {node["id"]: node.get("t", "") for node in graph_nodes
             if isinstance(node, dict) and isinstance(node.get("id"), str)}
    declared_origins = {
        node["id"]: node.get("origin") for node in graph_nodes
        if isinstance(node, dict) and isinstance(node.get("id"), str)
        and "origin" in node
    }
    if isinstance(origins, dict):
        declared_origins.update(origins)

    def fallback(reason):
        if require_associative:
            raise AssociativeRerankUnavailable(reason)
        out = []
        for slug, score in retrieval_hits:
            weighted = score * ORIGIN_WEIGHT.get(origin_class(
                slug, types.get(slug, ""), declared_origins.get(slug)),
                ORIGIN_WEIGHT["legacy-unlabeled"])
            if mind:
                node = mind.get("nodes", {}).get(slug)
                if node is not None:
                    weighted *= retention(node, now)
            out.append((slug, weighted))
        out.sort(key=lambda item: item[1], reverse=True)
        return out

    if not graph or not graph.get("edges"):
        return fallback("graph has no usable edges")
    nodes = [n["id"] for n in graph["nodes"]]
    idx = {s: i for i, s in enumerate(nodes)}
    adj = [[] for _ in nodes]
    deg = [0] * len(nodes)
    for e in graph["edges"]:
        si, di = idx.get(e["s"]), idx.get(e["d"])
        if si is None or di is None:
            continue
        weight = 1.0
        if mind:
            edge = mind.get("edges", {}).get(
                "|".join(sorted((e["s"], e["d"]))))
            if edge is not None:
                edge = _edge_record(edge, now)
                er = retention(edge, now)
                if er < RETENTION_DEMOTE:
                    continue
                weight = er * max(1.0, float(edge.get("w", 0.0)))
        adj[si].append((di, weight)); adj[di].append((si, weight))
        deg[si] += 1; deg[di] += 1
    # personalization: retrieval score × node specificity (1/deg)
    input_max = max(score for _, score in retrieval_hits) or 1.0
    pers = [0.0] * len(nodes)
    seeded = False
    seeded_indices = []
    for slug, score in retrieval_hits:
        i = idx.get(slug)
        if i is not None:
            pers[i] = (score / input_max) / max(1, deg[i])
            seeded = True
            seeded_indices.append(i)
    if not seeded or not any(adj[i] for i in seeded_indices):
        return fallback(
            "graph has no connected retrieval seed")
    tot = sum(pers) or 1.0
    pers = [p / tot for p in pers]
    rank = _ppr_power_iteration(pers, adj)
    rmax = max(rank) or 1.0
    acts = {}
    if mind:
        acts = activations(mind, [s for s, _ in retrieval_hits], now=now)
        avals = [v for v in acts.values() if v > -10]
        alo, ahi = (min(avals), max(avals)) if avals else (0, 1)
    # Benchmarked 2026-08-29 (research/bench-*.md): an additive blend that
    # can reorder hybrid-query results LOST slug-family proximity
    # (slug match@5 0.77 vs unmodified hybrid query 0.92).
    # So: input ordering is primary; PPR and activation act as gentle
    # multiplicative tie-breakers that can only promote within near-ties,
    # and origin weighting demotes model prose without touching evidence.
    out = []
    for slug, score in retrieval_hits:
        i = idx.get(slug)
        p = rank[i] / rmax if i is not None else 0.0
        a = 0.0
        if mind and acts.get(slug, -10) > -10 and ahi > alo:
            a = (acts[slug] - alo) / (ahi - alo)
        blended = (score / input_max) \
            * ORIGIN_WEIGHT.get(origin_class(
                slug, types.get(slug, ""), declared_origins.get(slug)),
                ORIGIN_WEIGHT["legacy-unlabeled"]) \
            * (1 + PPR_TIEBREAK_GAIN * p + ACTIVATION_TIEBREAK_GAIN * a)
        if mind and slug in mind.get("nodes", {}):
            blended *= retention(mind["nodes"][slug], now)
        out.append((slug, blended))
    out.sort(key=lambda kv: kv[1], reverse=True)
    return out


# Origin classes describe record provenance. Epochs are deterministic
# aggregations of evidence; generated entries (the ``thought`` compatibility
# kind) are derived, while syntheses are model prose.
ORIGIN_WEIGHT = {"evidence": 1.0, "derived": 0.85, "model": 0.55,
                 "legacy-unlabeled": 0.55}

# Missing origin metadata is classified only when both the canonical corpus
# namespace and its shipped page type agree.  This is provenance policy, not
# merely schema recognition: an unknown or misplaced unlabeled page must never
# inherit evidence status from the catch-all behavior used by older releases.
_UNLABELED_NAMESPACE_TYPE_ORIGIN = {
    "organs": ("organ", "evidence"),
    "events": ("event-day", "evidence"),
    "epochs": ("epoch", "evidence"),
    "units": ("unit", "evidence"),
    "packages": ("package", "evidence"),
    "projects": ("project", "evidence"),
    "skills": ("skill", "evidence"),
    "intents": ("intent", "evidence"),
    "synthesis": ("synthesis", "model"),
    "notes": ("note", "model"),
    "thoughts": ("thought", "legacy-unlabeled"),
    "takes": ("take", "legacy-unlabeled"),
}

def origin_class(slug, ptype="", declared_origin=None):
    # The JACKAL integration's ledger and receipt-file observations are
    # recall, not proof. Namespace precedence keeps legacy pages without an
    # origin label (and even stale categorical labels) out of evidence lanes.
    if slug.startswith(("events/jackal/", "epochs/jackal/")):
        return "derived"
    if declared_origin in {"evidence", "derived", "model"}:
        return declared_origin
    if declared_origin is not None:
        return "legacy-unlabeled"
    if slug == "sia/cortex" and ptype == "organ":
        return "evidence"
    namespace = slug.split("/", 1)[0]
    policy = _UNLABELED_NAMESPACE_TYPE_ORIGIN.get(namespace)
    if policy is not None and ptype == policy[0]:
        return policy[1]
    return "legacy-unlabeled"


def _append_queue(record, queue_path=None):
    queue_path = queue_path or TOUCH_QUEUE
    try:
        record = dict(record)
        deduplicate = "id" in record
        record.setdefault("id", uuid.uuid4().hex)
        encoded = (json.dumps(
            record, separators=(",", ":"), allow_nan=False) + "\n") \
            .encode("utf-8")
        with _touch_queue_lock(queue_path):
            total = 0
            records = 0
            active = b""
            for candidate in (queue_path, queue_path + ".draining"):
                raw = _repair_touch_tail_locked(candidate)
                if raw is None:
                    continue
                total += len(raw)
                if total > MAX_TOUCH_QUEUE_BYTES:
                    raise ValueError("touch queue exceeds aggregate byte limit")
                records += raw.count(b"\n")
                if records > MAX_TOUCH_QUEUE_RECORDS:
                    raise ValueError(
                        "touch queue exceeds aggregate record limit")
                if candidate == queue_path:
                    active = raw
                rows = _literal_lf_touch_lines(raw)
                # Complete malformed middle records remain authoritative
                # refusal debt; only a physically torn final suffix is
                # repairable.
                _validate_touch_queue_snapshot(rows, time.time())
                if deduplicate:
                    for line in rows:
                        existing = _parse_touch_json_line(line)
                        if isinstance(existing, dict) \
                                and existing.get("id") == record["id"]:
                            if existing == record:
                                # A previous publish can become visible before
                                # its destination/staging directory fsyncs. An
                                # exact producer retry must drive the fixed
                                # publisher again, not return merely because
                                # the bytes are currently reachable.
                                if candidate == queue_path:
                                    siaqueue.fixed_atomic_publish(
                                        queue_path, active, mode=0o600,
                                        staging_dir=siaqueue.staging_dir_for(
                                            queue_path,
                                            authority_roots=(STATE,)))
                                else:
                                    _fsync_directory(
                                        os.path.dirname(queue_path) or ".")
                                return True
                            raise ValueError(
                                "touch queue identity conflicts with its record")
            if total + len(encoded) > MAX_TOUCH_QUEUE_BYTES:
                raise ValueError("touch queue is at capacity")
            if records >= MAX_TOUCH_QUEUE_RECORDS:
                raise ValueError("touch queue is at record capacity")
            siaqueue.fixed_atomic_publish(
                queue_path, active + encoded, mode=0o600,
                staging_dir=siaqueue.staging_dir_for(
                    queue_path, authority_roots=(STATE,)))
        return True
    except (OSError, ValueError):
        return False


def touch_queue_usage(queue_path=None):
    """Return a no-follow aggregate for SOURCE HEALTH reporting."""
    queue_path = queue_path or TOUCH_QUEUE
    total = 0
    records = 0
    with _touch_queue_lock(queue_path):
        for candidate in (queue_path, queue_path + ".draining"):
            raw = _repair_touch_tail_locked(candidate)
            if raw is not None:
                total += len(raw)
                records += raw.count(b"\n")
                if total > MAX_TOUCH_QUEUE_BYTES:
                    raise ValueError(
                        "touch queue exceeds aggregate byte limit")
                if records > MAX_TOUCH_QUEUE_RECORDS:
                    raise ValueError(
                        "touch queue exceeds aggregate record limit")
        refusal = _load_touch_refusal_locked(queue_path)
    last = refusal.get("last")
    return {"bytes": total, "capacity": MAX_TOUCH_QUEUE_BYTES,
            "records": records,
            "record_capacity": MAX_TOUCH_QUEUE_RECORDS,
            "at_capacity": (total >= MAX_TOUCH_QUEUE_BYTES
                            or records >= MAX_TOUCH_QUEUE_RECORDS),
            "refusal_count": refusal.get("count", 0),
            "last_refusal": (last or {}).get("reason", "")}


def queue_touches(slugs, src="user-ask", ts=None, queue_path=None,
                  record_id=None):
    """Queue recall touches without writing compatibility policy state directly."""
    ts = time.time() if ts is None else float(ts)
    record = {"ts": ts, "src": src, "slugs": list(slugs)[:8]}
    if record_id:
        record["id"] = str(record_id)
    return _append_queue(record, queue_path)


def recovery_unpin_queue_path():
    """Keep the reducing lane beside an overridden/test touch queue."""
    return os.path.join(
        os.path.dirname(TOUCH_QUEUE), os.path.basename(RECOVERY_UNPIN_QUEUE))


def queue_pin(slug, pinned=True, ts=None, queue_path=None):
    """Queue a user pin/unpin for the daemon's single-writer pulse."""
    ts = time.time() if ts is None else float(ts)
    if queue_path is None:
        queue_path = TOUCH_QUEUE if pinned else recovery_unpin_queue_path()
    return _append_queue({"ts": ts, "op": "pin" if pinned else "unpin",
                          "slug": str(slug)}, queue_path)
