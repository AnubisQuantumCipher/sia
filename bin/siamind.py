"""siamind — the neurocognitive core of SIA, the Omarchy Brain.

Deterministic implementations of memory mechanisms from the cognitive-science
literature. Every formula is used as published; every stochastic element is
seeded from evidence (date ‖ ledger head) so behavior is replayable.

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

State lives in ~/.local/state/sia/mind.json, owned exclusively by the
brainstem daemon. Other processes (sia ask) communicate through the
append-only touch queue; the daemon drains it each pulse.
"""

import hashlib, json, math, os, random, time

STATE = os.path.expanduser("~/.local/state/sia")
MIND_PATH = os.path.join(STATE, "mind.json")
TOUCH_QUEUE = os.path.join(STATE, "touch-queue.jsonl")

ACTR_D = 0.5          # canonical ACT-R base-level decay
ACTR_K = 5            # Petrov hybrid: exact timestamps kept
PPR_DAMPING = 0.5     # HippoRAG's tuned damping factor
PPR_ITers = 30
EPISODIC_DAYS = int(os.environ.get("SIA_EPISODIC_DAYS", "14"))
WORKSPACE_K = 7
# (surprise uses an empirical count distribution per band — see
# surprisal_update; there is deliberately no Poisson rate or bit threshold)

# McGaugh/Kensinger arousal map: consequence, not sentiment. Drives
# workspace scoring, replay priority, and verbatim preservation.
AROUSAL = {
    "integrity-failure": 1.0, "crash": 0.9, "coredump": 0.9,
    "collapse": 0.8, "failed": 0.8, "refusal": 0.7, "urgent": 0.7,
    "healing": 0.6, "guardian": 0.55, "formal-receipt": 0.5,
    "upgrade": 0.4, "install": 0.4, "commit": 0.3,
}
SAFETY_TAGS = {"integrity-failure", "crash", "coredump", "collapse",
               "failed", "refusal"}   # flashbulb class: never compacted


def load_mind():
    try:
        with open(MIND_PATH) as f:
            return json.load(f)
    except Exception:
        return {"v": 1, "nodes": {}, "edges": {}, "ewma": {},
                "seen": {}, "hourbuf": {}, "cooldown": {},
                "workspace": [], "musing_day": ""}


def save_mind(mind):
    tmp = MIND_PATH + ".new"
    with open(tmp, "w") as f:
        json.dump(mind, f)
    os.replace(tmp, MIND_PATH)


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


def touch(mind, slug, ts=None, src="organ"):
    ts = ts or time.time()
    w = _touch_w(src)
    n = mind["nodes"].setdefault(slug, {"n": 0, "t0": ts, "rt": []})
    n["n"] = round(n.get("n", 0) + w, 2)
    rt = [e if isinstance(e, list) else [e, 1.0] for e in n.get("rt", [])]
    n["rt"] = (rt + [[ts, w]])[-ACTR_K:]


def hebb(mind, a, b, amount=1):
    if a == b:
        return
    key = "|".join(sorted((a, b)))
    mind["edges"][key] = mind["edges"].get(key, 0) + amount


def bump_kind(mind, organ, kind, tags=()):
    """Track how often each event shape and each safety tag has EVER been
    seen — rarity is what earns verbatim preservation, not a keyword."""
    kn = mind.setdefault("kindn", {})
    kn[f"{organ}:{kind}"] = kn.get(f"{organ}:{kind}", 0) + 1
    tn = mind.setdefault("tagn", {})
    for t in tags:
        if t in SAFETY_TAGS:
            tn[t] = tn.get(t, 0) + 1


def hebb_hygiene(mind, decay=0.95, floor=0.4, degree_cap=32):
    """Nightly edge hygiene: weights decay, dust is swept, and no node may
    keep more than degree_cap bonds (weakest pruned first) — spreading
    activation needs a sparse graph, not a hairball."""
    edges = mind.get("edges", {})
    for k in list(edges):
        w = edges[k] * decay
        if w < floor:
            del edges[k]
        else:
            edges[k] = round(w, 3)
    per = {}
    for k, w in edges.items():
        a, b = k.split("|", 1)
        per.setdefault(a, []).append((w, k))
        per.setdefault(b, []).append((w, k))
    doomed = set()
    for node, lst in per.items():
        if len(lst) > degree_cap:
            lst.sort(reverse=True)
            for _, k in lst[degree_cap:]:
                doomed.add(k)
    for k in doomed:
        edges.pop(k, None)
    return len(doomed)


def drain_touch_queue(mind):
    """Recall touches queued by out-of-process readers (reconsolidation:
    retrieval makes memories labile → recency boost + Hebbian binding).
    Claim-by-rename: appends racing the drain land in a fresh queue file
    instead of being deleted unread."""
    draining = TOUCH_QUEUE + ".draining"
    lines = []
    try:
        if os.path.exists(draining):          # leftover from a crashed drain
            with open(draining) as f:
                lines += f.read().splitlines()
            os.unlink(draining)
    except OSError:
        pass
    try:
        if os.path.exists(TOUCH_QUEUE):
            os.replace(TOUCH_QUEUE, draining)
            with open(draining) as f:
                lines += f.read().splitlines()
            os.unlink(draining)
    except OSError:
        pass
    drained = 0
    for line in lines:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        slugs = rec.get("slugs", [])[:8]
        ts = float(rec.get("ts", time.time()))
        src = rec.get("src", "user-ask")
        for s in slugs:
            touch(mind, s, ts, src=src)
            drained += 1
        for i in range(len(slugs)):          # co-recall binds (Hebb)
            for j in range(i + 1, len(slugs)):
                hebb(mind, slugs[i], slugs[j])
    return drained


# ------------------------------------------------------------------ ACT-R

def actr_base(node, now=None):
    """B_i = ln(Σ w_k · t_k^-d) — Petrov hybrid (exact recent timestamps
    plus a closed-form tail), with per-touch source weights so endogenous
    self-reference cannot masquerade as importance."""
    now = now or time.time()
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
    now = now or time.time()
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

def muse(mind, graph, day, ledger_head):
    """DMN association walk, once per day: find two high-activation nodes
    with no direct edge, in different regions, joined only by a low-traffic
    path. Seeded → replayable. Returns (text, links) or None."""
    if mind.get("musing_day") == day or not graph:
        return None
    nodes = [n["id"] for n in graph.get("nodes", [])]
    if len(nodes) < 10:
        return None
    adj = {}
    for e in graph.get("edges", []):
        adj.setdefault(e["s"], set()).add(e["d"])
        adj.setdefault(e["d"], set()).add(e["s"])
    acts = activations(mind, nodes)
    top = sorted(nodes, key=lambda s: acts.get(s, -10), reverse=True)[:24]
    rng = random.Random(hashlib.sha256(
        (day + "|" + ledger_head).encode()).hexdigest())
    rng.shuffle(top)
    # the cortex hub touches everything — a path through it is trivially
    # valid and never interesting; musing must find LATERAL bridges
    adj = {k: {m for m in v if m != "sia/cortex"}
           for k, v in adj.items() if k != "sia/cortex"}
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            a, b = top[i], top[j]
            if a == "sia/cortex" or b == "sia/cortex":
                continue
            if b in adj.get(a, ()) or a.split("/")[0] == b.split("/")[0]:
                continue
            path = _bfs(adj, a, b, 4)
            if path and len(path) >= 4:
                mind["musing_day"] = day
                chain = " → ".join(path)
                return (f"Musing: {a} and {b} share no direct link, yet "
                        f"they connect through {chain}. An association, "
                        f"not a causal claim.", [a, b])
    mind["musing_day"] = day
    return None


def _bfs(adj, a, b, max_hops):
    frontier = [(a, [a])]
    seen = {a}
    for _ in range(max_hops):
        nxt = []
        for node, path in frontier:
            for m in adj.get(node, ()):
                if m == b:
                    return path + [b]
                if m not in seen:
                    seen.add(m)
                    nxt.append((m, path + [m]))
        frontier = nxt
    return None


# ---------------------------------------------------------- PPR retrieval
# Used out-of-process by `sia ask` against the exported graph snapshot.

def ppr_rerank(graph, dense_hits, alpha=0.6, beta=0.25, gamma=0.15,
               mind=None):
    """HippoRAG-style: dense hits seed Personalized PageRank over the typed
    graph (damping 0.5, specificity 1/deg); blend dense + PPR + ACT-R.
    dense_hits: [(slug, score)] best-first. Returns [(slug, blended)]."""
    if not graph or not graph.get("edges") or not dense_hits:
        return dense_hits
    nodes = [n["id"] for n in graph["nodes"]]
    idx = {s: i for i, s in enumerate(nodes)}
    adj = [[] for _ in nodes]
    deg = [0] * len(nodes)
    for e in graph["edges"]:
        si, di = idx.get(e["s"]), idx.get(e["d"])
        if si is None or di is None:
            continue
        adj[si].append(di); adj[di].append(si)
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
        return dense_hits                     # uncertainty fallback: dense
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
            share = (1 - PPR_DAMPING) * r / len(adj[i])
            for j in adj[i]:
                nxt[j] += share
        if dangling:
            # dangling mass teleports back to the personalization vector
            for k, pk in enumerate(pers):
                if pk:
                    nxt[k] += dangling * pk
        rank = nxt
    rmax = max(rank) or 1.0
    acts = {}
    if mind:
        acts = activations(mind, [s for s, _ in dense_hits])
        avals = [v for v in acts.values() if v > -10]
        alo, ahi = (min(avals), max(avals)) if avals else (0, 1)
    # Benchmarked 2026-08-29 (research/bench-*.md): an additive blend that
    # can reorder dense results LOST recall (hit@5 0.77 vs dense 0.92).
    # So: dense ordering is primary; PPR and activation act as gentle
    # multiplicative tie-breakers that can only promote within near-ties,
    # and origin weighting demotes model prose without touching evidence.
    types = {n["id"]: n.get("t", "") for n in graph["nodes"]}
    out = []
    for slug, score in dense_hits:
        i = idx.get(slug)
        p = rank[i] / rmax if i is not None else 0.0
        a = 0.0
        if mind and acts.get(slug, -10) > -10 and ahi > alo:
            a = (acts[slug] - alo) / (ahi - alo)
        blended = (score / dmax) \
            * ORIGIN_WEIGHT.get(origin_class(slug, types.get(slug, "")), 1.0) \
            * (1 + 0.15 * p + 0.08 * a)
        out.append((slug, blended))
    out.sort(key=lambda kv: kv[1], reverse=True)
    return out


# origin classes: what a memory IS, epistemically. Epochs are DETERMINISTIC
# aggregation of evidence (compressed gist, still evidence); thoughts are
# derived-deterministic; syntheses are model prose.
ORIGIN_WEIGHT = {"evidence": 1.0, "derived": 0.85, "model": 0.55}

def origin_class(slug, ptype=""):
    if slug.startswith(("synthesis/", "notes/")) \
            or ptype in ("synthesis", "note"):
        return "model"       # agent/model prose — never competes as evidence
    if slug.startswith(("thoughts/", "takes/")) \
            or ptype in ("thought", "take"):
        return "derived"
    return "evidence"


def queue_touches(slugs, src="user-ask"):
    """Called by sia ask (out of process): append recall touches for the
    daemon to drain — never writes mind.json directly."""
    try:
        with open(TOUCH_QUEUE, "a") as f:
            f.write(json.dumps({"ts": time.time(), "src": src,
                                "slugs": list(slugs)[:8]}) + "\n")
    except OSError:
        pass
