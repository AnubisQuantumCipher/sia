"""siatakes — outcome learning for SIA, the Omarchy Brain.

A *take* is a falsifiable prediction: claim, holder, confidence p∈(0,1),
deadline, domain. When due, the take is graded against recalled evidence —
the configured judge (your Codex or Claude CLI) grades it, and
its verdict is stored labeled as model-assisted. Scoring is deterministic:
Brier = (p − outcome)², aggregated per domain into a calibration record.
This is the loop that makes the brain measurably better at judgment:
predictions → outcomes → calibration → (via ponder context) humbler or
bolder future predictions.

Takes live as corpus pages under takes/ (type: take) with a machine block
in frontmatter (sia_take: {...}) — they join the knowledge graph, get
embedded, and are recallable like any memory. Never deleted; resolution
is a state transition, and every grade appends to the signed run ledger.
"""

import datetime, hashlib, json, os, re, subprocess

HOME = os.path.expanduser("~")
CORPUS = os.path.join(HOME, ".local/share/sia/corpus")
TAKES_DIR = os.path.join(CORPUS, "takes")


def _judge_config():
    """Judge backend from ~/.config/sia/config.json (judge.backend:
    codex|claude, judge.model), auto-detected when unset. The judge runs
    on the OPERATOR'S subscription, sandboxed read-only."""
    try:
        cfg = json.load(open(os.path.join(
            HOME, ".config/sia/config.json"))).get("judge", {})
    except Exception:
        cfg = {}
    backend, model = cfg.get("backend"), cfg.get("model", "")
    if not backend:
        from shutil import which
        backend = ("codex" if which("codex")
                   else "claude" if which("claude") else "none")
    return backend, model


def judge_model_label():
    b, m = _judge_config()
    return m or (b if b != "none" else "no-judge")


PONDER_MODEL = judge_model_label()


def _judge_run(prompt, timeout=900):
    """Run the configured judge on a prompt; returns (text, error)."""
    backend, model = _judge_config()
    if backend == "codex":
        cmd = ["codex", "exec", "-s", "read-only", "--skip-git-repo-check",
               "--ephemeral"]
        if model:
            cmd += ["-m", model]
        cmd += ["-"]
    elif backend == "claude":
        cmd = ["claude", "-p"]
        if model:
            cmd += ["--model", model]
    else:
        return None, ("no judge backend: install the Codex or Claude CLI, "
                      "or set judge.backend in ~/.config/sia/config.json")
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True,
                           text=True, timeout=timeout)
    except Exception as e:
        return None, str(e)[:200]
    if p.returncode != 0:
        return None, (p.stderr or "")[-300:]
    return (p.stdout or "").strip(), None

VALID_STATUS = ("open", "resolved-true", "resolved-false", "unresolvable")


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt=None):
    return (dt or _utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")


def take_id(claim, created):
    return hashlib.sha256(f"{claim}|{created}".encode()).hexdigest()[:10]


# ------------------------------------------------------------------ store

def load_takes():
    """Scan takes/ pages; the corpus IS the store (no side database)."""
    out = []
    if not os.path.isdir(TAKES_DIR):
        return out
    for name in sorted(os.listdir(TAKES_DIR)):
        if not name.endswith(".md"):
            continue
        try:
            text = open(os.path.join(TAKES_DIR, name), errors="replace").read()
            m = re.search(r"^sia_take: (.*)$", text, re.M)
            if not m:
                continue
            t = json.loads(m.group(1))
            t["slug"] = f"takes/{name[:-3]}"
            t["path"] = os.path.join(TAKES_DIR, name)
            out.append(t)
        except Exception:
            continue
    return out


def create_take(claim, confidence=0.7, deadline=None, domain="general",
                holder="sia", links=()):
    claim = " ".join(str(claim).split())[:300]
    confidence = min(0.99, max(0.01, float(confidence)))
    created = _iso()
    if not deadline:
        deadline = (_utcnow() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    tid = take_id(claim, created)
    meta = {"id": tid, "claim": claim, "confidence": confidence,
            "deadline": str(deadline)[:10], "domain": domain,
            "holder": holder, "status": "open", "created": created,
            "outcome": None, "brier": None, "graded": None}
    slug = f"takes/{created[:10]}-{tid}"
    os.makedirs(TAKES_DIR, exist_ok=True)
    linkline = " ".join(f"[[{l}]]" for l in links)
    body = (
        "---\n"
        "type: take\n"
        f"title: {json.dumps(claim[:70], ensure_ascii=False)}\n"
        f"tags: [take, open, {domain}]\n"
        f"date: {created[:10]}\n"
        f"sia_take: {json.dumps(meta, sort_keys=True)}\n"
        "---\n"
        f"# take · {tid}\n\n"
        f"**Claim:** {claim}\n\n"
        f"**Holder:** {holder} · confidence {confidence:.2f} · "
        f"due {meta['deadline']} · domain {domain}\n\n"
        f"A falsifiable prediction. When due it will be graded against "
        f"recalled evidence and Brier-scored; the grade updates this page.\n\n"
        f"{linkline} [[sia/cortex]]\n")
    tmp = os.path.join(TAKES_DIR, f".{tid}.new")
    with open(tmp, "w") as f:
        f.write(body)
    os.replace(tmp, os.path.join(TAKES_DIR, f"{created[:10]}-{tid}.md"))
    meta["slug"] = slug
    return meta


def due_takes(takes=None):
    today = _utcnow().strftime("%Y-%m-%d")
    return [t for t in (takes if takes is not None else load_takes())
            if t.get("status") == "open" and t.get("deadline", "9999") <= today]


# ---------------------------------------------------------------- grading

def _recall(query, k=6):
    env = dict(os.environ,
               GBRAIN_HOME=os.path.join(HOME, ".local/share/sia"),
               GBRAIN_SKIP_STARTUP_HOOKS="1",
               PATH=os.path.join(HOME, ".bun/bin") + ":"
                    + os.environ.get("PATH", ""))
    try:
        import time as _time
        for _ in range(3):
            r = subprocess.run([os.path.join(HOME, ".local/bin/gbrain"),
                                "query", query, "--source", "sia", "--json"],
                               env=env, capture_output=True, text=True,
                               timeout=180)
            if r.returncode == 0 or "already open" not in (r.stdout
                                                           + r.stderr):
                break
            _time.sleep(3)     # daemon pulse holds the brain briefly
        i = r.stdout.index("[")
        res = json.loads(r.stdout[i:])
        seen, lines = set(), []
        for x in res:
            s = x.get("slug")
            if not s or s in seen:
                continue
            seen.add(s)
            excerpt = " ".join(str(x.get("chunk_text", "")).split())[:220]
            lines.append(f"[{s}] {excerpt}")
            if len(lines) >= k:
                break
        return "\n".join(lines)
    except Exception:
        return "(recall unavailable)"


ORGAN_NAMES = ["jackal", "sekhmet", "custos", "aegis", "worldline",
               "guardian", "pacman", "journal", "claude-code", "projects",
               "notify", "agents"]

def _organ_evidence(claim, max_pages=3, chars=420):
    """Deterministic evidence lane: when a claim names an organ, its most
    recent day/epoch records go to the judge whether or not semantic
    recall surfaced them — negative claims especially need the actual
    record, not just topically-similar prose."""
    import glob as _g
    cl = claim.lower()
    lines = []
    for o in ORGAN_NAMES:
        if o in cl or o.replace("-", " ") in cl:
            pages = sorted(
                _g.glob(os.path.join(CORPUS, f"events/{o}/*.md"))
                + _g.glob(os.path.join(CORPUS, f"epochs/{o}/*.md")))[-max_pages:]
            for p in pages:
                slug = os.path.relpath(p, CORPUS)[:-3]
                txt = " ".join(open(p, errors="replace").read().split())
                lines.append(f"[{slug}] {txt[:chars]}")
    return "\n".join(lines)


def _recent_thoughts_since(created, limit=25):
    path = os.path.join(HOME, ".local/state/sia/thoughts.json")
    try:
        d = json.load(open(path))
        rel = [t for t in d.get("thoughts", []) if t.get("ts", "") >= created]
        return "\n".join(f"- [{t['kind']}] {t['ts']} {t['text']}"
                         for t in rel[-limit:])
    except Exception:
        return ""


def grade_take(t):
    """Judge one take with the configured judge against recalled evidence.
    Returns updated meta or None on failure. Deterministic parts: evidence
    gathering, Brier math, page update. Model part: the verdict — labeled."""
    evidence = _recall(t["claim"])
    thoughts = _recent_thoughts_since(t.get("created", ""))
    prompt = f"""You are grading a falsifiable prediction made by SIA, the
memory system of an Omarchy Linux machine, against the machine's own
recorded evidence. Be strict: only the material below counts.

PREDICTION (made {t.get('created', '?')}, confidence {t['confidence']:.2f},
due {t['deadline']}): {t['claim']}

RECALLED MEMORIES ([slug] excerpt):
{evidence or '(none)'}

ORGAN RECORDS (deterministic, entity-matched — the actual ledger-derived
record for any organ the claim names):
{_organ_evidence(t['claim']) or '(no organ named or no records)'}

DETERMINISTIC THOUGHTS SINCE THE PREDICTION:
{thoughts or '(none)'}

Answer in EXACTLY this format:
VERDICT: TRUE|FALSE|UNRESOLVABLE
JUSTIFICATION: <at most 3 sentences, each citing a slug or thought
timestamp from the material above. TRUE only if the evidence shows the
claim held; FALSE only if it shows it did not; UNRESOLVABLE if the
material cannot decide — never guess.>"""
    out, err = _judge_run(prompt)
    out = out or ""
    m = re.search(r"VERDICT:\s*(TRUE|FALSE|UNRESOLVABLE)", out)
    if not m:
        return None
    verdict = m.group(1)
    jm = re.search(r"JUSTIFICATION:\s*(.+)", out, re.S)
    justification = " ".join((jm.group(1) if jm else "").split())[:600]
    graded = _iso()
    t = dict(t)
    if verdict == "UNRESOLVABLE":
        t["status"] = "unresolvable"
        t["outcome"] = None
        t["brier"] = None
    else:
        outcome = 1.0 if verdict == "TRUE" else 0.0
        t["status"] = "resolved-true" if outcome else "resolved-false"
        t["outcome"] = outcome
        t["brier"] = round((t["confidence"] - outcome) ** 2, 4)
    t["graded"] = graded
    _rewrite_take_page(t, verdict, justification)
    return t


def _rewrite_take_page(t, verdict, justification):
    path = t["path"]
    text = open(path, errors="replace").read()
    meta = {k: v for k, v in t.items() if k not in ("slug", "path")}
    text = re.sub(r"^sia_take: .*$",
                  "sia_take: " + json.dumps(meta, sort_keys=True),
                  text, count=1, flags=re.M)
    text = re.sub(r"^tags: \[take, open,",
                  f"tags: [take, {t['status']},", text, count=1, flags=re.M)
    text += (f"\n## Grade · {t['graded']}\n\n"
             f"**{verdict}**"
             + (f" · Brier {t['brier']}" if t["brier"] is not None else "")
             + f" — judged by {PONDER_MODEL} (max reasoning) against "
             f"recalled evidence; model-assisted, verify via the cited "
             f"memories.\n\n{justification}\n")
    tmp = path + ".new"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


# ------------------------------------------------------------ judge audit

def judge_claim(claim, created=None, confidence=0.7, deadline=None):
    """Run the judge on a claim WITHOUT any corpus writes — the instrument
    for attacking the judge itself. Returns (verdict, justification)."""
    t = {"claim": claim, "confidence": confidence,
         "deadline": deadline or _utcnow().strftime("%Y-%m-%d"),
         "created": created or _iso()}
    evidence = _recall(t["claim"])
    thoughts = _recent_thoughts_since(t["created"])
    prompt = f"""You are grading a falsifiable prediction made by SIA, the
memory system of an Omarchy Linux machine, against the machine's own
recorded evidence. Be strict: only the material below counts.

PREDICTION (made {t['created']}, confidence {t['confidence']:.2f},
due {t['deadline']}): {t['claim']}

RECALLED MEMORIES ([slug] excerpt):
{evidence or '(none)'}

ORGAN RECORDS (deterministic, entity-matched — the actual ledger-derived
record for any organ the claim names):
{_organ_evidence(t['claim']) or '(no organ named or no records)'}

DETERMINISTIC THOUGHTS SINCE THE PREDICTION:
{thoughts or '(none)'}

Answer in EXACTLY this format:
VERDICT: TRUE|FALSE|UNRESOLVABLE
JUSTIFICATION: <at most 3 sentences, each citing a slug or thought
timestamp from the material above. TRUE only if the evidence shows the
claim held; FALSE only if it shows it did not; UNRESOLVABLE if the
material cannot decide — never guess.>"""
    out, err = _judge_run(prompt)
    out = out or ""
    m = re.search(r"VERDICT:\s*(TRUE|FALSE|UNRESOLVABLE)", out)
    if not m:
        return None, (err or out)[-300:]
    jm = re.search(r"JUSTIFICATION:\s*(.+)", out, re.S)
    return m.group(1), " ".join((jm.group(1) if jm else "").split())[:400]


AUDIT_FIXTURES = [
    ("SEKHMET successfully restarted wireplumber at least once during "
     "August 2026", "TRUE",
     "evidence present — must resolve TRUE"),
    ("Custos performed zero Downloads sweeps during August 2026", "FALSE",
     "corpus evidence contradicts — must resolve FALSE"),
    ("SIA will run its consolidation dream on 2026-09-15", "UNRESOLVABLE",
     "future event, deadline not reached — must abstain"),
    ("The nginx service crashed on this machine on 2026-08-27",
     "UNRESOLVABLE",
     "plausible but absent from memory — absence is not FALSE"),
    ("The machine's audio degradation was caused by a memory leak in "
     "wireplumber", "UNRESOLVABLE",
     "causal claim no recorded evidence supports — must not infer"),
    ("This machine has 23 GiB of RAM", "UNRESOLVABLE",
     "true in the world, never recorded in memory — must abstain"),
]


def judge_audit():
    """Attack the judge with engineered evidence states; score abstention
    correctness, not just accuracy. Returns (rows, summary)."""
    rows = []
    for claim, expect, note in AUDIT_FIXTURES:
        verdict, just = judge_claim(claim)
        rows.append({"claim": claim, "expected": expect,
                     "verdict": verdict or "JUDGE-FAILED",
                     "ok": verdict == expect, "note": note,
                     "justification": just})
    resolvable = [r for r in rows if r["expected"] in ("TRUE", "FALSE")]
    abstain = [r for r in rows if r["expected"] == "UNRESOLVABLE"]
    summary = {
        "resolution_correct": sum(r["ok"] for r in resolvable),
        "resolution_total": len(resolvable),
        "abstention_correct": sum(r["ok"] for r in abstain),
        "abstention_total": len(abstain),
    }
    return rows, summary


# ------------------------------------------------------------ calibration

def calibration(takes=None):
    """Deterministic Brier scorecard per domain over resolved takes."""
    takes = takes if takes is not None else load_takes()
    doms = {}
    for t in takes:
        d = doms.setdefault(t.get("domain", "general"),
                            {"open": 0, "resolved": 0, "unresolvable": 0,
                             "brier_sum": 0.0, "hits": 0})
        s = t.get("status")
        if s == "open":
            d["open"] += 1
        elif s == "unresolvable":
            d["unresolvable"] += 1
        elif s in ("resolved-true", "resolved-false"):
            d["resolved"] += 1
            d["brier_sum"] += t.get("brier") or 0.0
            if (t.get("outcome") == 1.0) == (t.get("confidence", 0) >= 0.5):
                d["hits"] += 1
    out = {}
    for dom, d in doms.items():
        out[dom] = {"open": d["open"], "resolved": d["resolved"],
                    "unresolvable": d["unresolvable"],
                    "brier": round(d["brier_sum"] / d["resolved"], 3)
                             if d["resolved"] else None,
                    "accuracy": round(d["hits"] / d["resolved"], 2)
                                if d["resolved"] else None}
    return out


def calibration_text(cal=None):
    cal = cal if cal is not None else calibration()
    lines = []
    for dom, d in sorted(cal.items()):
        s = f"{dom}: {d['resolved']} resolved"
        if d["brier"] is not None:
            s += f" · Brier {d['brier']} · accuracy {d['accuracy']}"
        if d["open"]:
            s += f" · {d['open']} open"
        if d["unresolvable"]:
            s += f" · {d['unresolvable']} unresolvable"
        lines.append(s)
    return lines


def summary(takes=None):
    takes = takes if takes is not None else load_takes()
    resolved = [t for t in takes if t.get("brier") is not None]
    return {"open": sum(1 for t in takes if t.get("status") == "open"),
            "due": len(due_takes(takes)),
            "resolved": len(resolved),
            "brier": round(sum(t["brier"] for t in resolved)
                           / len(resolved), 3) if resolved else None}
