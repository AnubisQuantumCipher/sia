"""siamind — the neurocognitive core of SIA, the Omarchy Brain.

Deterministic, named approximations and adaptations of memory mechanisms from
the cognitive-science literature.  Published equations are identified where
used; SIA-specific gates and proxy signals are described as such.  Stochastic
elements are seeded from evidence (date ‖ ledger head) so behavior is
replayable.

  ACT-R activation        Anderson; base-level B_i = ln(Σ t_k^-d), d = 0.5,
                          Petrov (2006) hybrid approximation, k = 5.
  Hebbian edge weights    co-activation counts; fan-corrected spreading.
  Personalized PageRank   HippoRAG (NeurIPS'24): damping 0.5, node
                          specificity 1/deg, dense-seeded, uncertainty
                          fallback to pure dense ranking.
  Novelty (dopamine gate) Lisman & Grace (2005) + von Restorff isolation.
  Surprise (empirical)    per (organ, time-band) cohort, the distribution
                          of observed hourly counts; a spike exceeds every
                          count the band has shown (≥30 samples), an absence
                          is a zero hour in a band that is otherwise active.
                          No Poisson, no "bits" — the estimator reports only
                          the count, the previous max, and the sample size.
  Global workspace        Baars/Dehaene: K=7 slots, ignition threshold,
                          per-organ cap (lateral inhibition), hysteresis.
  DMN musing              seeded association walk between distant
                          high-activation nodes over low-traffic paths.
  Systems consolidation   day pages → weekly epoch pages with McGaugh
                          preserve rules (arousal keeps detail verbatim).
  Stability/rehearsal     exponential retention is a retrieval-only lens;
                          the SM-2 ease/interval update follows the published
                          schedule, while quality values are deterministic SIA
                          interaction proxies rather than human recall grades.

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

ACTR_D = 0.5          # canonical ACT-R base-level decay
ACTR_K = 5            # Petrov hybrid: exact timestamps kept
PPR_DAMPING = 0.5     # HippoRAG's tuned damping factor
PPR_ITers = 30
EPISODIC_DAYS = int(os.environ.get("SIA_EPISODIC_DAYS", "14"))
WORKSPACE_K = 7
# Stability is an attention lens, never a deletion policy.  These defaults and
# the SM-2 constants below are the values frozen in SIA's research spec.
MIND_VERSION = 2
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

# McGaugh/Kensinger arousal map: consequence, not sentiment. Drives
# workspace scoring, replay priority, and verbatim preservation.
AROUSAL = {
    "integrity-failure": 1.0, "crash": 0.9, "coredump": 0.9,
    "collapse": 0.8, "failed": 0.8, "refusal": 0.7, "urgent": 0.7,
    "healing": 0.6, "guardian": 0.55,
    "upgrade": 0.4, "install": 0.4, "commit": 0.3,
}
SAFETY_TAGS = {"integrity-failure", "crash", "coredump", "collapse",
               "failed", "refusal"}   # flashbulb class in the attention lens


def _empty_mind():
    return {"v": MIND_VERSION, "nodes": {}, "edges": {}, "ewma": {},
            "seen": {}, "hourbuf": {}, "cooldown": {},
            "workspace": [], "musing_day": "", "decay": {},
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


def _bounded_float(value, label, low, high):
    return min(high, max(low, _finite_float(value, label)))


def _stability(value, label):
    number = _finite_float(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be positive")
    return min(MAX_STABILITY_DAYS, number)


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
    """Return an in-place, backward-compatible v2 state migration.

    ``now`` is injectable for replay/tests.  Unknown keys are retained so an
    older binary does not erase state belonging to a newer optional organ.
    """
    now = _finite_float(time.time() if now is None else now,
                        "migration time")
    if not isinstance(raw, dict):
        raise ValueError("mind state must be a JSON object")
    mind = raw
    defaults = _empty_mind()
    for key, value in defaults.items():
        mind.setdefault(key, value)
    if not isinstance(mind.get("nodes"), dict):
        raise ValueError("mind nodes must be an object")
    if not isinstance(mind.get("edges"), dict):
        raise ValueError("mind edges must be an object")
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
        node["rt"] = normalized_rt
        node["s"] = _stability(
            node.get("s", NODE_STABILITY_DAYS), "node stability")
        node["last_touch"] = _finite_float(
            node.get("last_touch", _last_rt(node, now)),
            "node last-touch time")
        node["arousal"] = _bounded_float(
            node.get("arousal", 0.0), "node arousal", 0.0, 1.0)
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
            review["reps"] = max(0, int(review.get("reps", 0)))
            review["interval_days"] = min(
                MAX_REVIEW_INTERVAL_DAYS,
                max(0, int(review.get("interval_days", 0))))
            review["due_at"] = _finite_float(
                review.get("due_at", now), "SM-2 due time")
            review["last_review"] = _finite_float(
                review.get("last_review", 0.0), "SM-2 last-review time")
            review["reviews"] = max(0, int(review.get("reviews", 0)))
            quality = review.get("last_quality")
            if quality is not None:
                review["last_quality"] = max(0, min(5, int(quality)))
    for key, value in list(mind["edges"].items()):
        mind["edges"][key] = _edge_record(value, now)
    mind["v"] = MIND_VERSION
    return mind


def load_mind(now=None):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) \
        | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(MIND_PATH, flags)
    except FileNotFoundError:
        return _empty_mind()
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) \
                or before.st_uid != os.geteuid() \
                or before.st_size > MAX_MIND_BYTES:
            raise ValueError("mind state is not a bounded private regular file")
        # Older SIA versions created mind.json with the caller's umask. An
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
    if observed != finished or len(raw_bytes) > MAX_MIND_BYTES \
            or not stat.S_ISREG(target.st_mode) \
            or (target.st_dev, target.st_ino) != (after.st_dev,
                                                  after.st_ino):
        raise ValueError("mind state changed while read or exceeds its bound")
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
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
    """Bound the rebuildable attention cache without deleting evidence.

    Corpus pages and signed ledgers remain authoritative. Only unpinned
    derived associations/nodes are evicted, weakest and oldest first, when
    their JSON projection would otherwise exceed the fixed state-file bound.
    """
    limit = MAX_MIND_BYTES if max_bytes is None else max_bytes
    if isinstance(limit, bool) or not isinstance(limit, int) \
            or limit <= 0 or limit > MAX_MIND_BYTES:
        raise ValueError("mind persistence limit is invalid")
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
        seen = mind.get("seen", {})
        if slug in seen:
            seen_count = len(seen)
            stamp = seen.pop(slug)
            encoded_size -= removed_entry_bytes(slug, stamp, seen_count)
        removed_slugs.add(slug)
        removed_nodes += 1
        if slug in safety_nodes:
            removed_safety_nodes += 1
        if finish_if_bounded():
            return {"edges": removed_edges, "nodes": removed_nodes,
                    "cache_entries": removed_cache_entries}
    # Shape counts, novelty cohorts, and empirical-band caches are derived
    # attention policy state, not evidence.  They must not strand a durable
    # source transaction behind operator pins.  Evict them deterministically
    # only after graph cache eviction has been exhausted.
    for field in ("seen", "kindn", "hourbuf", "hist", "cooldown", "ewma",
                  "coincide"):
        cache = mind.get(field, {})
        if not isinstance(cache, dict):
            raise ValueError(f"mind {field} cache must be an object")
        for key in sorted(list(cache)):
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
            | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(MIND_PATH, flags)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) \
                    or before.st_uid != os.geteuid() \
                    or before.st_size > MAX_MIND_BYTES:
                raise ValueError(
                    "mind state is not a bounded private regular file")
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
        if observed != finished or len(previous_bytes) > MAX_MIND_BYTES \
                or not stat.S_ISREG(target.st_mode) \
                or (target.st_dev, target.st_ino) != (after.st_dev,
                                                      after.st_ino):
            raise ValueError(
                "mind state changed while read or exceeds its bound")
        try:
            previous = previous_bytes.decode("utf-8")
            migrate_mind(json.loads(previous))
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise ValueError(
                "prior mind state is unreadable or malformed") from exc
        _atomic_state_text(MIND_PATH + ".last-good", previous)
    _atomic_state_text(MIND_PATH, encoded)


def arousal_of(tags):
    return max((AROUSAL.get(t, 0.0) for t in tags), default=0.1)


# ------------------------------------------------------------------ touches
# Every touch carries a SOURCE. Exogenous touches (an organ observed
# something; the operator asked) count at full weight. Endogenous touches
# (the system referencing its own products) are steeply discounted so the
# loop cannot promote what it already likes — importance must come from
# the world, not from self-talk.

EXO_SOURCES = {"organ", "user-ask", "user-recall", "user"}
ENDO_WEIGHT = 0.2

def _touch_w(src):
    return 1.0 if src in EXO_SOURCES else ENDO_WEIGHT


def _ensure_collections(mind):
    mind.setdefault("nodes", {})
    mind.setdefault("edges", {})


def _initial_stability(kind, arousal=0.0, novelty_score=0.0):
    base = NODE_STABILITY_DAYS if kind == "node" else EDGE_STABILITY_DAYS
    arousal = _bounded_float(arousal, "arousal gain", 0.0, 1.0)
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

    Stability reinforcement is deliberately separate from ACT-R source
    weighting: ``n`` remains echo-resistant, while every genuine retrieval or
    reference restabilizes the trace as specified.  ``reinforce=False`` is for
    state discovery/migration, not a user-visible recall.
    """
    ts = _finite_float(time.time() if ts is None else ts, "touch time")
    arousal = _bounded_float(arousal, "arousal gain", 0.0, 1.0)
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
                         * STABILITY_TOUCH_GAIN)
        n["arousal"] = max(_bounded_float(
            n.get("arousal", 0.0), "node arousal", 0.0, 1.0), arousal)
        n["novelty"] = max(_bounded_float(
            n.get("novelty", 0.0), "node novelty", 0.0, 1.0),
                           novelty_score)
        n["last_touch"] = max(_finite_float(
            n.get("last_touch", ts), "node last-touch time"), ts)
    if pin:
        _pin(n, "safety")
    n.setdefault("signals", {})[src] = max(
        _finite_float(n.get("signals", {}).get(src, 0.0),
                      "node signal time"), ts)
    n["n"] = round(_finite_float(n.get("n", 0), "node touch count") + w, 2)
    rt = [e if isinstance(e, list) else [e, 1.0] for e in n.get("rt", [])]
    n["rt"] = (rt + [[ts, w]])[-ACTR_K:]
    _ensure_review(n, ts)
    return n


def hebb(mind, a, b, amount=1, ts=None, *, arousal=0.0,
         novelty_score=0.0, pin=False, reinforce=True):
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
                        * STABILITY_TOUCH_GAIN)
        edge["last_touch"] = max(_finite_float(
            edge.get("last_touch", ts), "edge last-touch time"), ts)
    edge["w"] = _finite_float(
        _finite_float(edge.get("w", 0.0), "edge weight")
        + _finite_float(amount, "edge reinforcement"), "edge weight")
    if pin:
        _pin(edge, "safety")
    mind["edges"][key] = edge
    return edge


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
    """Return whether an exact corpus event already changed mind state."""
    _validate_event_replay_key(day_slug, event_id)
    applied = mind.setdefault("event_applied", [])
    if not isinstance(applied, list):
        raise ValueError("mind event replay state must be a list")
    return event_id in applied


def mark_event_applied(mind, day_slug, event_id):
    """Record an exact event only after all of its mind effects succeed."""
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
    """Return whether one exact source-marker generation changed the mind."""
    _validate_event_batch_identity(batch_identity)
    applied = mind.get("event_batch_applied")
    if applied is not None:
        _validate_event_batch_identity(applied)
    return applied == batch_identity


def mark_event_batch_applied(mind, batch_identity):
    """Publish the bounded all-or-nothing cognitive replay receipt."""
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
    """Nightly edge hygiene: weights decay, dust is swept, and no node may
    keep more than degree_cap bonds (weakest pruned first) — spreading
    activation needs a sparse graph, not a hairball."""
    now = time.time() if now is None else float(now)
    edges = mind.get("edges", {})
    for k in list(edges):
        edge = _edge_record(edges[k], now)
        w = edge["w"] * decay
        if w < floor:
            if edge.get("graph_discovered"):
                # The PGLite graph says this relation still exists.  Sweep
                # only its learned associative weight; retaining the record
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
        # Pinning is metadata, not an ACT-R/reconsolidation use.
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
        | getattr(os, "O_NOFOLLOW", 0)
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
        value = json.loads(raw.decode("utf-8", errors="strict"))
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
        ensure_ascii=True)
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
        return json.loads(line)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("touch queue contains malformed JSON") from exc


def acknowledge_touch_queue(claim_path, queue_path=None):
    """Durably remove a claimed batch after mind state is saved."""
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
        raw_slugs = rec.get("slugs")
        if not isinstance(raw_slugs, list) or len(raw_slugs) > 8:
            raise ValueError("touch queue slugs must be a bounded list")
        if any(not isinstance(slug, str)
               or not re.fullmatch(r"[a-z0-9][a-z0-9/._-]{0,199}", slug)
               or any(part in ("", ".", "..") for part in slug.split("/"))
               for slug in raw_slugs):
            raise ValueError("touch queue contains an invalid slug")
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

    # Validate the complete claimed batch before changing mind state. One
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
                for slug in slugs:
                    touch(target, slug, stamp, src=src)
                    changed += 1
                for left in range(len(slugs)):
                    for right in range(left + 1, len(slugs)):
                        hebb(target, slugs[left], slugs[right], ts=stamp)
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
    """Apply one already-admitted endogenous page signal."""
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
        # Thought pages use a one-second timestamp. Treat an overlapping
        # signal in that second as both the durable retry receipt and a
        # deliberate endogenous echo-rate limit. Exogenous recalls remain
        # independently counted.
        return 0
    return _apply_thought_links(mind, slugs, stamp)


# ------------------------------------------------------ stability + rehearsal

def retention(record, now=None):
    """Ebbinghaus/MemoryBank lens ``R = exp(-elapsed_days / S)``.

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

    Discovery is not a touch: it neither raises ACT-R counts nor reinforces
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
            # A learned co-recall edge may predate the graph snapshot that
            # proves the same relation exists in the corpus.  Promote the
            # existing record in place without refreshing its stability.
            edge = _edge_record(mind["edges"][key], now)
            edge["graph_discovered"] = True
            mind["edges"][key] = edge
    return mind


def decay_sweep(mind, now=None):
    """Refresh active/demoted counts; demotion only affects graph spreading."""
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
    old_reps = max(0, int(review.get("reps", 0)))
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
            prior = max(SM2_SECOND_INTERVAL,
                        int(review.get("interval_days", SM2_SECOND_INTERVAL)))
            interval = min(MAX_REVIEW_INTERVAL_DAYS,
                           int(math.ceil(prior * old_ef)))
    review.update({"ef": ef, "reps": reps, "interval_days": interval,
                   "due_at": now + interval * SECONDS_PER_DAY,
                   "last_review": now, "last_quality": q,
                   "reviews": int(review.get("reviews", 0)) + 1})
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
    """Project status from an already-normalized mind without mutating it."""
    now = time.time() if now is None else float(now)
    if not isinstance(mind, dict) \
            or not isinstance(mind.get("nodes"), dict) \
            or not isinstance(mind.get("edges"), dict):
        raise ValueError("mind summary requires normalized node and edge maps")
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


# ------------------------------------------------------------------ ACT-R

def actr_base(node, now=None):
    """B_i = ln(Σ w_k · t_k^-d) — Petrov hybrid (exact recent timestamps
    plus a closed-form tail), with per-touch source weights so endogenous
    self-reference cannot masquerade as importance."""
    now = time.time() if now is None else float(now)
    rt = [e if isinstance(e, list) else [e, 1.0] for e in node.get("rt", [])]
    n = node.get("n", 0)
    t0 = node.get("t0", now)
    if not rt or n <= 0:
        return -10.0
    s = 0.0
    for t, w in rt:
        dt = max(60.0, now - t)
        s += w * dt ** (-ACTR_D)
    extra = n - sum(w for _, w in rt)
    if extra > 0:
        t_n = max(3600.0, now - t0)          # oldest use ≈ creation
        t_k = max(60.0, now - rt[0][0])
        if t_n > t_k:
            s += extra * (t_n ** (1 - ACTR_D) - t_k ** (1 - ACTR_D)) \
                 / ((1 - ACTR_D) * (t_n - t_k))
    return math.log(s) if s > 0 else -10.0


def activations(mind, slugs, now=None):
    now = time.time() if now is None else float(now)
    return {s: actr_base(mind["nodes"].get(s, {}), now) for s in slugs}


# ------------------------------------------------------------------ novelty

def novelty(mind, organ, kind, entities, batch_kinds, ts=None):
    """Lisman-Grace dopamine gate: novelty at ingest, additive terms,
    explainable. Returns (score, reasons)."""
    ts = ts or time.time()
    score, reasons = 0.0, []
    seen = mind["seen"]
    for e in entities:
        last = seen.get(e)
        if last is None:
            score += 0.40
            reasons.append(f"first sighting of {e}")
        elif ts - last > 30 * 86400:
            score += 0.20
            reasons.append(f"{e} returns after 30d+ away")
        seen[e] = ts       # ALWAYS refresh: the test must measure absence
    pair = f"pair:{organ}:{kind}"
    if pair not in seen:
        score += 0.20
        reasons.append(f"new event shape {organ}/{kind}")
        seen[pair] = ts
    # von Restorff isolation: distinct within its local surround
    if batch_kinds:
        same = sum(1 for k in batch_kinds if k == kind)
        if len(batch_kinds) >= 5 and same / len(batch_kinds) <= 0.1:
            score += 0.15
            reasons.append("isolated among unlike events")
    return min(1.0, score), reasons


# ---------------------------------------------------------------- surprise
# Honest estimator: desktop evidence is bursty, so no Poisson, no "bits".
# Each (organ, band) cohort keeps the EMPIRICAL distribution of observed
# hourly counts (ring of 120 samples). A spike is a count that exceeds
# everything the band has ever produced (n ≥ 30 observed hours); an
# absence fires only for PACED organs — bands active in ≥90 % of their
# observed hours. Bursts join the band and stop being surprising. The
# claim never exceeds what was measured.

MIN_BAND_SAMPLES = 30

def _band(ts):
    lt = time.gmtime(ts)
    kind = "we" if lt.tm_wday >= 5 else "wd"
    return f"{kind}:{lt.tm_hour // 6}"       # four 6h blocks × wd/we


def surprisal_update(mind, organ_counts, ts=None):
    """Close out hour buckets against empirical per-band count history.
    Iterates the UNION of buffered and active organs, closing every
    intervening silent hour with x=0, so absence is observable and the
    band keeps learning through silence."""
    ts = ts or time.time()
    hour = int(ts // 3600)
    buf = mind.setdefault("hourbuf", {})
    hist = mind.setdefault("hist", {})
    findings = []
    for organ in sorted(set(buf) | set(organ_counts)):
        cnt = organ_counts.get(organ, 0)
        b = buf.setdefault(organ, {"hour": hour, "count": 0})
        if b["hour"] == hour:
            b["count"] += cnt
            continue
        start = max(b["hour"], hour - 168)    # cap backfill at one week
        for h in range(start, hour):
            x = b["count"] if h == b["hour"] else 0
            key = f"{organ}|{_band(h * 3600)}"
            samples = hist.get(key, [])
            n = len(samples)
            if n >= MIN_BAND_SAMPLES:
                cd_key = f"s:{key}"
                cooled = ts - mind["cooldown"].get(cd_key, 0) > 6 * 3600
                hi = max(samples)
                active_frac = sum(1 for v in samples if v > 0) / n
                if x > hi and x >= 5 and cooled:
                    mind["cooldown"][cd_key] = ts
                    findings.append((organ, "spike",
                        f"{organ} produced {x} events in an hour — above "
                        f"everything this band has shown in {n} observed "
                        f"hours (previous max {hi})"))
                if x == 0 and active_frac >= 0.9 and cooled:
                    mind["cooldown"][cd_key] = ts
                    findings.append((organ, "absence",
                        f"{organ} went silent for an hour in a band that "
                        f"was active in {round(active_frac * 100)}% of "
                        f"{n} observed hours — expected activity is "
                        f"missing"))
            hist[key] = (samples + [x])[-120:]
        buf[organ] = {"hour": hour, "count": cnt}
    return findings


# --------------------------------------------------------------- workspace

def _ws_bucket(slug):
    """Lateral-inhibition bucket: events/<o> and organs/<o> share the organ
    bucket; every other collection (thoughts, units, packages, synthesis…)
    is one bucket, so near-duplicate echoes can't flood the workspace."""
    if slug.startswith("events/"):
        parts = slug.split("/")
        return parts[1] if len(parts) > 1 else slug
    if slug.startswith("organs/"):
        return slug.split("/")[-1]
    return slug.split("/")[0]


def rebuild_workspace(mind, organ_arousal, now=None):
    """Global Workspace: K slots, ignition threshold, per-bucket cap 2
    (lateral inhibition), hysteresis for incumbents."""
    now = now or time.time()
    cands = {}
    for slug, node in mind["nodes"].items():
        rt = node.get("rt", [])
        if not rt:
            continue
        last = rt[-1][0] if isinstance(rt[-1], list) else rt[-1]
        if now - last > 24 * 3600:
            continue
        score = actr_base(node, now) \
            + 2.0 * organ_arousal.get(_ws_bucket(slug), 0.0)
        cands[slug] = score
    incumbents = set(mind.get("workspace", []))
    def key(item):
        return item[1] + (0.2 if item[0] in incumbents else 0.0)
    ranked = sorted(cands.items(), key=key, reverse=True)
    ws, per_bucket = [], {}
    for item in ranked:
        if key(item) < -2.5:                  # ignition (on the sort key —
            break                             # monotone, so break is safe)
        b = _ws_bucket(item[0])
        if per_bucket.get(b, 0) >= 2:         # lateral inhibition
            continue
        per_bucket[b] = per_bucket.get(b, 0) + 1
        ws.append(item[0])
        if len(ws) >= WORKSPACE_K:
            break
    mind["workspace"] = ws
    return ws


# ------------------------------------------------------------------ musing

def muse(mind, graph, day, ledger_head, now=None):
    """DMN association walk, once per day: find two high-activation nodes
    with no direct edge, in different regions, joined only by a low-traffic
    path. The captured timestamp plus seeded shuffle make the result replayable.
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
    now = time.time() if now is None else float(now)
    acts = activations(mind, nodes, now=now)
    top = sorted(nodes, key=lambda s: (-acts.get(s, -10), s))[:24]
    rng = random.Random(hashlib.sha256(
        (day + "|" + ledger_head).encode()).hexdigest())
    rng.shuffle(top)
    # the cortex hub touches everything — a path through it is trivially
    # valid and never interesting; musing must find LATERAL bridges
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
                return (f"Musing: {a} and {b} share no direct link, yet "
                        f"they connect through {chain}. An association, "
                        f"not a causal claim.", [a, b])
    mind["musing_day"] = day
    return None


def _low_traffic_path(adj, traffic, a, b, max_hops, min_nodes=4):
    """Choose a replayable bounded route, preferring low learned traffic.

    One best path per endpoint is retained at each hop, which bounds the
    search by graph size and ``max_hops``.  Route order is total and stable:
    learned Hebbian edge-weight sum, then hop count, then the slug tuple.
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

def ppr_rerank(graph, dense_hits, alpha=0.6, beta=0.25, gamma=0.15,
               mind=None, now=None, origins=None):
    """HippoRAG-style: dense hits seed Personalized PageRank over the typed
    graph (damping 0.5, specificity 1/deg); blend dense + PPR + ACT-R.
    dense_hits: [(slug, score)] best-first. Returns [(slug, blended)]."""
    if not dense_hits:
        return dense_hits
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

    def fallback():
        out = []
        for slug, score in dense_hits:
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
        return fallback()
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
    # personalization: dense score × node specificity (1/deg)
    dmax = max(s for _, s in dense_hits) or 1.0
    pers = [0.0] * len(nodes)
    seeded = False
    for slug, score in dense_hits:
        i = idx.get(slug)
        if i is not None:
            pers[i] = (score / dmax) / max(1, deg[i])
            seeded = True
    if not seeded:
        return fallback()        # uncertainty fallback retains origin policy
    tot = sum(pers) or 1.0
    pers = [p / tot for p in pers]
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
            # dangling mass teleports back to the personalization vector
            for k, pk in enumerate(pers):
                if pk:
                    nxt[k] += dangling * pk
        rank = nxt
    rmax = max(rank) or 1.0
    acts = {}
    if mind:
        acts = activations(mind, [s for s, _ in dense_hits], now=now)
        avals = [v for v in acts.values() if v > -10]
        alo, ahi = (min(avals), max(avals)) if avals else (0, 1)
    # Benchmarked 2026-08-29 (research/bench-*.md): an additive blend that
    # can reorder dense results LOST slug-family proximity
    # (slug match@5 0.77 vs dense 0.92).
    # So: dense ordering is primary; PPR and activation act as gentle
    # multiplicative tie-breakers that can only promote within near-ties,
    # and origin weighting demotes model prose without touching evidence.
    out = []
    for slug, score in dense_hits:
        i = idx.get(slug)
        p = rank[i] / rmax if i is not None else 0.0
        a = 0.0
        if mind and acts.get(slug, -10) > -10 and ahi > alo:
            a = (acts[slug] - alo) / (ahi - alo)
        blended = (score / dmax) \
            * ORIGIN_WEIGHT.get(origin_class(
                slug, types.get(slug, ""), declared_origins.get(slug)),
                ORIGIN_WEIGHT["legacy-unlabeled"]) \
            * (1 + 0.15 * p + 0.08 * a)
        if mind and slug in mind.get("nodes", {}):
            blended *= retention(mind["nodes"][slug], now)
        out.append((slug, blended))
    out.sort(key=lambda kv: kv[1], reverse=True)
    return out


# origin classes: what a memory IS, epistemically. Epochs are DETERMINISTIC
# aggregation of evidence (compressed gist, still evidence); thoughts are
# derived-deterministic; syntheses are model prose.
ORIGIN_WEIGHT = {"evidence": 1.0, "derived": 0.85, "model": 0.55,
                 "legacy-unlabeled": 0.55}

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
    if slug.startswith(("synthesis/", "notes/")) \
            or ptype in ("synthesis", "note"):
        return "model"       # agent/model prose — never competes as evidence
    if slug.startswith("thoughts/") or ptype == "thought":
        return "legacy-unlabeled"
    if slug.startswith("takes/") or ptype == "take":
        # New open takes declare derived and graded takes declare model.
        # An unlabelled legacy take may already contain model-written grade
        # prose, so absence must not promote the mixed page to derived.
        return "legacy-unlabeled"
    return "evidence"


def _append_queue(record, queue_path=None):
    queue_path = queue_path or TOUCH_QUEUE
    try:
        record = dict(record)
        deduplicate = "id" in record
        record.setdefault("id", uuid.uuid4().hex)
        encoded = (json.dumps(record, separators=(",", ":")) + "\n") \
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
    """Queue recall touches for the daemon without writing mind directly."""
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
