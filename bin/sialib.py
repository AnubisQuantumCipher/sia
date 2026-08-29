"""sialib — core of SIA, the Omarchy Brain.

The brainstem daemon tails every evidence stream on this box into a markdown
corpus, syncs it into SIA's own gbrain (PGLite) brain, verifies the machine's
signed evidence chains, and derives deterministic thoughts. Everything the
widget shows comes from the JSON snapshots exported here.

Honesty rules (house style):
  - Ledger rows elsewhere are recall; the attest binary is the evidence path.
  - Thoughts are deterministic and cite their sources; SIA never invents.
  - Private keys, message bodies, and clipboard contents are never read.
"""

import copy, json, os, re, sqlite3, subprocess, sys, time, hashlib, datetime, glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import siamind
import siatakes

HOME = os.path.expanduser("~")
SHARE = os.path.join(HOME, ".local/share/sia")
STATE = os.path.join(HOME, ".local/state/sia")
CORPUS = os.path.join(SHARE, "corpus")
BIN = os.path.join(SHARE, "bin")
GBRAIN = os.path.join(HOME, ".local/bin/gbrain")
ATTEST = os.path.join(HOME, ".local/bin/attest")
BUN_DIR = os.path.join(HOME, ".bun/bin")

GBRAIN_ENV = dict(os.environ,
                  GBRAIN_HOME=SHARE,
                  GBRAIN_SKIP_STARTUP_HOOKS="1",
                  PATH=BUN_DIR + ":" + os.environ.get("PATH", ""))

# ---- instance configuration (~/.config/sia/config.json) --------------
# SIA is generic: a base set of senses every Linux/Omarchy box has, plus
# OPTIONAL integrations that activate only when their data exists on this
# machine, plus user-defined custom senses. Nothing machine-specific
# lives in the code.
CONFIG_PATH = os.path.join(HOME, ".config/sia/config.json")

def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

CONFIG = load_config()

# organs every box has
BASE_ORGANS = {
    "pacman":      ("pacman",      "package manager"),
    "journal":     ("journal",     "systemd journal (errors and faults)"),
    "claude-code": ("Claude Code", "agent sessions on this box"),
    "projects":    ("Projects",    "git activity under ~/Projects"),
    "notify":      ("Notifications", "desktop notification stream"),
    "agents":      ("Agents",       "AI-agent usage meters (Omarchy Quattro)"),
}
# optional integrations: active only when their data exists on this box
OPTIONAL_ORGANS = {
    "jackal":    ("JACKAL",    "deterministic mathematical evidence kernel",
                  ".local/state/jackal"),
    "sekhmet":   ("SEKHMET",   "SPARK-proved self-healing fabric",
                  ".local/share/sekhmet"),
    "custos":    ("Custos",    "proof-carrying Downloads custodian",
                  ".local/share/custos"),
    "aegis":     ("AEGIS",     "Anubis command-authority showcase",
                  ".local/share/aegis"),
    "worldline": ("WORLDLINE", "branchable-reality system",
                  ".local/state/worldline"),
    "guardian":  ("Guardian",  "Omarchy preflight and checkpoint tool",
                  ".local/state/omarchy-guardian"),
}

def _build_organs():
    organs = dict(BASE_ORGANS)
    disabled = set(CONFIG.get("senses", {}).get("disable", []))
    for key, (name, desc, probe) in OPTIONAL_ORGANS.items():
        if key not in disabled and os.path.exists(os.path.join(HOME, probe)):
            organs[key] = (name, desc)
    for cs in CONFIG.get("custom_senses", []):
        o = re.sub(r"[^a-z0-9._-]+", "-",
                   str(cs.get("organ", cs.get("name", "custom"))).lower())
        organs.setdefault(o, (o, cs.get("description",
                                        "custom evidence stream")))
    for key in disabled:
        organs.pop(key, None)
    return organs

ORGANS = _build_organs()

# Tags that carry emotional weight for salience (mirrored into gbrain config).
HIGH_TAGS = ["integrity-failure", "refusal", "crash", "coredump", "failed",
             "formal-receipt", "collapse", "healing", "urgent"]

VERSION = "1.0.0"


# ---------------------------------------------------------------- utilities

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)

def iso(dt=None):
    return (dt or utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")

def today(dt=None):
    return (dt or utcnow()).strftime("%Y-%m-%d")

def ensure_dirs():
    for d in (SHARE, STATE, CORPUS, BIN):
        os.makedirs(d, exist_ok=True)

def atomic_write(path, data):
    tmp = path + ".new"
    with open(tmp, "w") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default

def log(msg):
    line = f"{iso()} {msg}"
    print(line, flush=True)

def sanitize_slugpart(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9._-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-.")
    return s or "unknown"

def clip(s, n=110):
    s = re.sub(r"\s+", " ", str(s)).strip()
    # keep markdown/wikilink syntax inert inside bullets
    s = s.replace("[[", "⟦").replace("]]", "⟧").replace("|", "¦").replace("\t", " ")
    s = s.replace("**", "✱✱")   # ** is the Timeline-line discriminator
    return s[: n - 1] + "…" if len(s) > n else s


# ---- ingest redaction: metadata can still carry secrets (journal lines,
# commit subjects, notification summaries). Secret-shaped spans are dropped
# AT THE SENSE BOUNDARY — before anything reaches the corpus or git — and
# every redaction is counted so SOURCE HEALTH can say "sense X omitted N
# spans" instead of storing them forever. Hex digests are NOT redacted:
# chain hashes are evidence, and they are already public in the ledgers.
REDACT_PATTERNS = [
    re.compile(r"-----BEGIN[ A-Z]*-----.*?(?:-----END[ A-Z]*-----|$)", re.S),
    re.compile(r"\beyJ[A-Za-z0-9_-]{14,}\.?[A-Za-z0-9._-]*"),      # JWT
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),                    # github
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),                         # api keys
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),                  # slack
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                            # aws
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{15,}=*", re.I),
    re.compile(r"\b(?:password|passwd|secret|api[_-]?key|token)\s*[=:]\s*\S+",
               re.I),
    re.compile(r"~?/[^\s]*\.ssh/[^\s]*"),
    re.compile(r"\b[A-Za-z0-9+/]{40,}={1,2}(?=\s|$)"),              # base64
]
REDACTIONS = {}     # organ -> spans dropped this process (pulse exports it)

def redact(text, organ="?"):
    out, n = str(text), 0
    for pat in REDACT_PATTERNS:
        out, k = pat.subn("⟦redacted⟧", out)
        n += k
    if n:
        REDACTIONS[organ] = REDACTIONS.get(organ, 0) + n
    return out


class Event:
    """One observed happening. links are corpus slugs (no .md).
    Summaries pass the redaction boundary at construction — fail closed."""
    __slots__ = ("organ", "ts", "kind", "summary", "links", "tags")

    def __init__(self, organ, ts, kind, summary, links=(), tags=()):
        self.organ = organ
        self.ts = ts                      # aware datetime UTC
        self.kind = kind
        self.summary = redact(summary, organ)
        self.links = set(links)
        self.tags = set(tags)


# ---------------------------------------------------------------- cursors

CURSORS_PATH = os.path.join(STATE, "cursors.json")

def load_cursors():
    return read_json(CURSORS_PATH, {})

def save_cursors(c):
    atomic_write(CURSORS_PATH, json.dumps(c, indent=1, sort_keys=True))


def tail_lines(path, cursors, key):
    """Line-count tail that survives the JACKAL rewrite-and-replace pattern:
    reopen by path every time; content is append-only, inode is not."""
    try:
        with open(path, errors="replace") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return []
    n = cursors.get(key, None)
    if n is None:                 # first run: establish cursor, emit nothing
        if os.environ.get("SIA_BACKFILL") == "1":
            n = 0                 # …unless backfill: replay all history once
        else:
            cursors[key] = len(lines)
            return []
    if n > len(lines):            # truncation/rotation: reset without replay
        cursors[key] = len(lines)
        return []
    cursors[key] = len(lines)
    return lines[n:]


def tail_bytes(path, cursors, key, max_read=4 * 1024 * 1024):
    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        return b""
    off = cursors.get(key, None)
    if off is None:
        if os.environ.get("SIA_BACKFILL") == "1":
            off = 0
        else:
            cursors[key] = size
            return b""
    if off > size:                # truncation: reset without replay
        cursors[key] = size
        return b""
    with open(path, "rb") as f:
        f.seek(off)
        data = f.read(max_read)
    # consume only complete lines; a torn tail waits for the next pulse
    nl = data.rfind(b"\n")
    if nl < 0:
        return b""
    data = data[:nl + 1]
    cursors[key] = off + len(data)
    return data


# ---------------------------------------------------------------- senses

def sense_jackal(cursors):
    """The JACKAL ledger is a SLIDING WINDOW (~200 rows; older rows rotate to
    retired/), rewritten via os.replace on every append — so neither inode,
    byte offset, nor line count is a usable cursor. Cursor = last-seen ts."""
    evs = []
    path = os.path.join(HOME, ".local/state/jackal/results.jsonl")
    counts = {}
    try:
        with open(path, errors="replace") as f:
            raw = f.read().splitlines()
    except FileNotFoundError:
        raw = []
    records = []
    for line in raw:
        try:
            r = json.loads(line)
            records.append(r)
        except Exception:
            continue
    last_ts = cursors.get("jackal.ts", None)
    if last_ts is None:
        last_ts = 0.0 if os.environ.get("SIA_BACKFILL") == "1" else \
            max((r.get("ts", 0) for r in records), default=0.0)
    new = [r for r in records if r.get("ts", 0) > last_ts]
    cursors["jackal.ts"] = max((r.get("ts", 0) for r in records),
                               default=last_ts)
    cursors.pop("jackal.lines", None)
    for r in new:
        ts = datetime.datetime.fromtimestamp(r.get("ts", time.time()),
                                             datetime.timezone.utc)
        tool = r.get("tool", "?")
        status = r.get("status", "?")
        tags = {"jackal", status}
        if r.get("formal"):
            tags.add("formal-receipt")
        if status in ("refused", "refusal"):
            tags.add("refusal")
        parsed = ""
        f = r.get("fields") or {}
        if isinstance(f, dict):
            parsed = f.get("parsed") or ""
        summary = f"{tool} → {status}" + (f" ({clip(parsed, 40)})" if parsed else "")
        counts[status] = counts.get(status, 0) + 1
        evs.append(Event("jackal", ts, status, summary, {"organs/jackal"}, tags))
    # receipts: new files in the receipts dir
    rdir = os.path.join(HOME, ".local/state/jackal/receipts")
    try:
        names = sorted(x for x in os.listdir(rdir) if x.endswith(".json"))
    except FileNotFoundError:
        names = []
    seen = cursors.get("jackal.receipts")
    if seen is None:
        cursors["jackal.receipts"] = names
    else:
        for n in names:
            if n not in seen:
                evs.append(Event("jackal", utcnow(), "receipt",
                                 f"formal receipt retained {n[:12]}…",
                                 {"organs/jackal"}, {"jackal", "formal-receipt"}))
        cursors["jackal.receipts"] = names
    return evs


def _attest_rows(path, cursors, key):
    rows = []
    for line in tail_lines(path, cursors, key):
        p = line.split("\t")
        if len(p) == 9:
            rows.append(p)
    return rows


def sense_sekhmet(cursors):
    evs = []
    path = os.path.join(HOME, ".local/share/sekhmet/ledger.tsv")
    for seq, stamp, action, a1, a2, *_ in _attest_rows(path, cursors, "sekhmet.lines"):
        try:
            ts = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")\
                                  .replace(tzinfo=datetime.timezone.utc)
        except Exception:
            ts = utcnow()
        tags = {"sekhmet"}
        links = {"organs/sekhmet"}
        kind = action.split(":")[0].lower()
        if kind in ("intent", "outcome"):
            tags.add("healing")
        unit = a1 if a1 not in ("sekhmet", "-") else a2
        if unit and unit not in ("-", "ok", "degraded") and "." not in unit[:1]:
            u = sanitize_slugpart(unit.replace(".service", ""))
            if u not in ("sekhmet", "ok", "degraded", "unknown"):
                links.add(f"units/{u}")
        evs.append(Event("sekhmet", ts, kind, f"{action} {a1} {a2}".strip(),
                         links, tags))
    return evs


def sense_custos(cursors):
    evs = []
    path = os.path.join(HOME, ".local/share/custos/ledger.tsv")
    for seq, stamp, verb, src, dst, *_ in _attest_rows(path, cursors, "custos.lines"):
        try:
            ts = datetime.datetime.fromtimestamp(int(stamp), datetime.timezone.utc)
        except Exception:
            ts = utcnow()
        name = os.path.basename(src) if src not in ("-", "") else verb
        ddir = os.path.basename(os.path.dirname(dst)) if dst not in ("-", "") else ""
        evs.append(Event("custos", ts, verb,
                         f"{verb}: {clip(name, 40)}" + (f" → {ddir}/" if ddir else ""),
                         {"organs/custos"}, {"custos"}))
    return evs


def sense_aegis(cursors):
    evs = []
    path = os.path.join(HOME, ".local/share/aegis/ledger.tsv")
    for seq, stamp, action, a1, a2, *_ in _attest_rows(path, cursors, "aegis.lines"):
        try:
            ts = datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")\
                                  .replace(tzinfo=datetime.timezone.utc)
        except Exception:
            ts = utcnow()
        tags = {"aegis"}
        if a2 == "FAIL":
            tags.add("failed")
        evs.append(Event("aegis", ts, action.split(":")[0].lower(),
                         f"{action} {a1} {a2}".strip(), {"organs/aegis"}, tags))
    return evs


WL_LOUD_KINDS = {"mission", "collapse-receipt", "agent-invocation",
                 "agent-invocation-result", "result", "done", "edit"}

def sense_worldline(cursors):
    evs = []
    db = os.path.join(HOME, ".local/state/worldline/worldline.sqlite3")
    if not os.path.exists(db):
        return evs
    last = cursors.get("worldline.created_at", None)
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
        cur = con.execute(
            "SELECT kind, actor, tool, reason, path_display, created_at, world_instance "
            "FROM causal_events WHERE created_at > ? ORDER BY created_at LIMIT 2000",
            (last or "",))
        rows = cur.fetchall()
        con.close()
    except Exception as e:
        raise RuntimeError(f"worldline sqlite: {e}")
    if last is None and os.environ.get("SIA_BACKFILL") == "1":
        last = ""
    if last is None:
        # first run: set cursor to newest, emit nothing
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
            row = con.execute("SELECT MAX(created_at) FROM causal_events").fetchone()
            con.close()
            cursors["worldline.created_at"] = row[0] or ""
        except Exception:
            cursors["worldline.created_at"] = ""
        return evs
    quiet = {}
    for kind, actor, tool, reason, pathd, created, world in rows:
        cursors["worldline.created_at"] = created
        try:
            ts = datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
        except Exception:
            ts = utcnow()
        if kind in WL_LOUD_KINDS:
            tags = {"worldline"}
            if kind == "collapse-receipt":
                tags.add("collapse")
            what = tool or reason or pathd or ""
            evs.append(Event("worldline", ts, kind,
                             f"{kind} {clip(what, 60)} (world {str(world)[:8]})",
                             {"organs/worldline"}, tags))
        else:
            quiet[kind] = quiet.get(kind, 0) + 1
    if quiet:
        parts = ", ".join(f"{v}× {k}" for k, v in sorted(quiet.items()))
        evs.append(Event("worldline", utcnow(), "activity",
                         f"world activity: {parts}",
                         {"organs/worldline"}, {"worldline"}))
    return evs


PACMAN_RE = re.compile(r"^\[([^\]]+)\] \[ALPM\] (installed|upgraded|removed) ([^ ]+) (.*)$")

def sense_pacman(cursors):
    evs = []
    data = tail_bytes("/var/log/pacman.log", cursors, "pacman.off")
    if not data:
        return evs
    pkgs = {"installed": [], "upgraded": [], "removed": []}
    ts = utcnow()
    for line in data.decode(errors="replace").splitlines():
        m = PACMAN_RE.match(line)
        if not m:
            continue
        stamp, act, name = m.group(1), m.group(2), m.group(3)
        try:
            ts = datetime.datetime.fromisoformat(stamp).astimezone(datetime.timezone.utc)
        except Exception:
            pass
        pkgs[act].append(name)
    for act, names in pkgs.items():
        if not names:
            continue
        links = {"organs/pacman"}
        for n in names[:30]:
            links.add("packages/" + sanitize_slugpart(n))
        shown = ", ".join(f"[[packages/{sanitize_slugpart(n)}|{n}]]" for n in names[:8])
        extra = f" and {len(names)-8} more" if len(names) > 8 else ""
        evs.append(Event("pacman", ts, act, f"{act}: {shown}{extra}",
                         links, {"pacman", act}))
    return evs


# journalctl advances --cursor-file on disk at read time — before this pulse's
# pages exist. So each read runs against a TEMP copy; pulse() renames it over
# the real cursor only after the corpus write phase succeeded.
PENDING_CURSOR_RENAMES = []

def _journalctl(args, cursor_file):
    tmp = cursor_file + ".pulse"
    try:
        if os.path.exists(cursor_file):
            with open(cursor_file) as src, open(tmp, "w") as dst:
                dst.write(src.read())
        elif os.path.exists(tmp):
            os.unlink(tmp)
    except Exception:
        pass
    cmd = ["journalctl", "-o", "json", "--no-pager",
           f"--cursor-file={tmp}"] + args
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    PENDING_CURSOR_RENAMES.append((tmp, cursor_file))
    out = []
    for line in r.stdout.splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


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
    for scope, extra in (("sys", []), ("user", ["--user"])):
        cfile = os.path.join(STATE, f"journal-{scope}.cursor")
        first = not os.path.exists(cfile)
        if first:
            _journalctl(extra + ["-n", "0"], cfile)     # establish cursor
            continue
        recs = _journalctl(extra + ["-p", "err..alert", "-n", "300"], cfile)
        per_unit = {}
        for r in recs:
            try:
                unit = r.get("_SYSTEMD_UNIT") or r.get("UNIT") or \
                       r.get("SYSLOG_IDENTIFIER") or "kernel"
                msg = _journal_msg(r.get("MESSAGE", ""))
                cnt, _last = per_unit.get(unit, (0, ""))
                per_unit[unit] = (cnt + 1, msg)
            except Exception:
                continue          # one malformed record must not lose the batch
        items = sorted(per_unit.items(), key=lambda kv: -kv[1][0])[:5]
        for unit, (cnt, lastmsg) in items:
            u = sanitize_slugpart(str(unit).replace(".service", "").split("@")[0])
            tags = {"journal", "journal-error"}
            if "coredump" in str(unit) or "core dumped" in lastmsg:
                tags.add("coredump")
            evs.append(Event("journal", utcnow(), "error",
                             f"{unit}: {cnt} error(s) — {clip(lastmsg, 70)}",
                             {"organs/journal", f"units/{u}"}, tags))
    return evs


def sense_guardian(cursors):
    evs = []
    base = os.path.join(HOME, ".local/state/omarchy-guardian")
    for sub, label in (("checkpoints", "checkpoint"), ("plans", "plan"),
                       ("transactions", "transaction")):
        d = os.path.join(base, sub)
        try:
            names = sorted(os.listdir(d))
        except FileNotFoundError:
            continue
        names = [n for n in names if not n.endswith(".applied")]
        key = f"guardian.{sub}"
        seen = cursors.get(key)
        if seen is None:
            cursors[key] = names
            continue
        for n in names:
            if n not in seen:
                evs.append(Event("guardian", utcnow(), label,
                                 f"new {label}: {clip(n, 40)}",
                                 {"organs/guardian"}, {"guardian"}))
        cursors[key] = names
    return evs


def sense_git(cursors):
    evs = []
    live = {os.path.basename(os.path.dirname(g)) for g in
            glob.glob(os.path.join(HOME, "Projects/*/.git"))}
    for key in [k for k in cursors if k.startswith("git.")]:
        if key[4:] not in live:
            del cursors[key]
    for repo_git in glob.glob(os.path.join(HOME, "Projects/*/.git")):
        repo = os.path.basename(os.path.dirname(repo_git))
        head_log = os.path.join(repo_git, "logs/HEAD")
        if not os.path.exists(head_log):
            continue
        key = f"git.{repo}"
        slug = "projects/" + sanitize_slugpart(repo)
        for line in tail_lines(head_log, cursors, key):
            if "\t" not in line:
                continue
            meta, msg = line.split("\t", 1)
            if msg.startswith("commit"):
                subj = msg.split(":", 1)[1].strip() if ":" in msg else msg
                evs.append(Event("projects", utcnow(), "commit",
                                 f"[[{slug}|{repo}]]: {clip(subj, 70)}",
                                 {"organs/projects", slug}, {"git", "commit"}))
    return evs


def sense_claude(cursors):
    """Session-level only: new sessions, titles, exchange counts. Never bodies."""
    evs = []
    sessions = cursors.setdefault("claude.sessions", {})
    for f in glob.glob(os.path.join(HOME, ".claude/projects/*/*.jsonl")):
        sid = os.path.basename(f)[:-6]
        st = sessions.get(sid)
        try:
            size = os.path.getsize(f)
        except FileNotFoundError:
            continue
        if st is None:
            # first sighting: only announce if the file is fresh (< 1 h old)
            fresh = (time.time() - os.path.getmtime(f)) < 3600
            sessions[sid] = {"off": size, "n": 0, "title": "", "announced": fresh,
                             "cwd": os.path.basename(os.path.dirname(f))}
            if fresh:
                evs.append(Event("claude-code", utcnow(), "session",
                                 f"new agent session {sid[:8]}…",
                                 {"organs/claude-code"}, {"claude-code"}))
            continue
        if size <= st["off"]:
            st["off"] = min(st["off"], size)
            continue
        try:
            with open(f, "rb") as fh:
                fh.seek(st["off"])
                chunk = fh.read(6 * 1024 * 1024)
        except FileNotFoundError:
            continue              # deleted between glob and open
        st["off"] = st["off"] + len(chunk)
        n_new = 0
        for line in chunk.decode(errors="replace").splitlines():
            if '"type":"assistant"' in line or '"type": "assistant"' in line:
                n_new += 1
            if '"ai-title"' in line and not st["title"]:
                try:
                    st["title"] = clip(json.loads(line).get("aiTitle", ""), 60)
                except Exception:
                    pass
        st["n"] += n_new
        if n_new and not st.get("announced"):
            # an old session woke up after we first saw it — start reporting
            st["announced"] = True
            evs.append(Event("claude-code", utcnow(), "session",
                             f"agent session {sid[:8]}… resumed",
                             {"organs/claude-code"}, {"claude-code"}))
        if n_new and st.get("announced"):
            name = st["title"] or sid[:8] + "…"
            evs.append(Event("claude-code", utcnow(), "activity",
                             f"session “{name}”: +{n_new} replies ({st['n']} total)",
                             {"organs/claude-code"}, {"claude-code"}))
    # prune sessions whose files are gone
    seen_files = {os.path.basename(f)[:-6] for f in
                  glob.glob(os.path.join(HOME, ".claude/projects/*/*.jsonl"))}
    for sid in list(sessions):
        if sid not in seen_files:
            del sessions[sid]
    return evs


def sense_notify(cursors):
    evs = []
    d = os.path.join(HOME, ".local/state/omarchy/notifications/history")
    try:
        names = sorted(os.listdir(d))
    except FileNotFoundError:
        return evs
    last = cursors.get("notify.last")
    if last is None:
        cursors["notify.last"] = names[-1] if names else ""
        return evs
    new = [n for n in names if n > last]
    if new:
        cursors["notify.last"] = new[-1]
    per_app = {}
    for n in new[:100]:
        j = read_json(os.path.join(d, n), {})
        app = j.get("app") or "app"
        per_app.setdefault(app, []).append(clip(j.get("summary", ""), 50))
    for app, sums in per_app.items():
        tail = f": {sums[-1]}" if sums[-1] else ""
        evs.append(Event("notify", utcnow(), "notification",
                         f"{app} ×{len(sums)}{tail}",
                         {"organs/notify"}, {"notification"}))
    return evs


def sense_agents(cursors):
    """Omarchy Quattro agents-usage records: authoritative per-agent token
    spend + rate-limit pressure (~/.local/state/omarchy/agents/usage/)."""
    evs = []
    d = os.path.join(HOME, ".local/state/omarchy/agents/usage")
    state = cursors.setdefault("agents.state", {})
    try:
        names = [n for n in os.listdir(d) if n.endswith(".json")]
    except FileNotFoundError:
        return evs
    for n in sorted(names):
        j = read_json(os.path.join(d, n), {})
        aid = j.get("id") or n[:-5]
        prev = state.get(aid, {})
        def _pct(v):
            try:
                f = float(v)
            except (TypeError, ValueError):
                return 0
            # collectors store fractions of 1.0; older ones use 0-100
            return int(round(f * 100)) if 0 <= f <= 1.0 else int(round(f))
        cur = {"tokens": int(j.get("todayTotalTokens") or 0),
               "limits": {str(l.get("label", "")): _pct(l.get("percent"))
                          for l in (j.get("limits") or [])}}
        if prev:
            dtok = cur["tokens"] - prev.get("tokens", 0)
            if dtok > 500_000:
                evs.append(Event("agents", utcnow(), "usage",
                                 f"{aid}: +{dtok // 1000}k tokens today "
                                 f"({cur['tokens'] // 1000}k total)",
                                 {"organs/agents"}, {"agents"}))
            for label, pct in cur["limits"].items():
                old = prev.get("limits", {}).get(label, pct)
                if pct >= old + 10:
                    tags = {"agents"}
                    if pct >= 90:
                        tags.add("urgent")
                    evs.append(Event("agents", utcnow(), "limit",
                                     f"{aid} {clip(label, 30)} limit at "
                                     f"{pct}% (was {old}%)",
                                     {"organs/agents"}, tags))
        state[aid] = cur
    return evs


def sense_custom(cursors):
    """User-defined evidence streams from config custom_senses: tail a
    log (lines or jsonl), match a pattern, emit events into the user's
    own organ. This is how anyone points SIA at THEIR programs."""
    evs = []
    for cs in CONFIG.get("custom_senses", []):
        try:
            name = sanitize_slugpart(str(cs.get("name", "custom")))
            organ = sanitize_slugpart(str(cs.get("organ", name)))
            path = os.path.expanduser(str(cs.get("path", "")))
            pat = re.compile(cs["match"]) if cs.get("match") else None
            lines = tail_lines(path, cursors, f"custom.{name}")
            count = 0
            for line in lines:
                if cs.get("type") == "jsonl":
                    try:
                        j = json.loads(line)
                        text = str(j.get(cs.get("field", "message"), line))
                    except Exception:
                        continue
                else:
                    text = line
                if pat and not pat.search(text):
                    continue
                count += 1
                if count <= 10:
                    evs.append(Event(organ, utcnow(),
                                     str(cs.get("kind", "event"))[:24],
                                     clip(text, 100), {f"organs/{organ}"},
                                     set(cs.get("tags", [])) | {organ}))
            if count > 10:
                evs.append(Event(organ, utcnow(), "activity",
                                 f"+{count - 10} more matching lines",
                                 {f"organs/{organ}"}, {organ}))
        except Exception:
            continue
    return evs


_SENSE_ORGAN = {
    "sense_jackal": "jackal", "sense_sekhmet": "sekhmet",
    "sense_custos": "custos", "sense_aegis": "aegis",
    "sense_worldline": "worldline", "sense_guardian": "guardian",
    "sense_pacman": "pacman", "sense_journal": "journal",
    "sense_git": "projects", "sense_claude": "claude-code",
    "sense_notify": "notify", "sense_agents": "agents",
}

_ALL_SENSES = [sense_jackal, sense_sekhmet, sense_custos, sense_aegis,
               sense_worldline, sense_pacman, sense_journal,
               sense_guardian, sense_git, sense_claude, sense_notify,
               sense_agents]

# only senses whose organ is active on THIS machine run
SENSES = [s for s in _ALL_SENSES
          if _SENSE_ORGAN.get(s.__name__, "") in ORGANS] + [sense_custom]


# ---------------------------------------------------------------- corpus

FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)

def corpus_path(slug):
    return os.path.join(CORPUS, slug + ".md")

def page_exists(slug):
    return os.path.exists(corpus_path(slug))

def write_page(slug, fm, body):
    path = corpus_path(slug)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fml = "---\n" + "\n".join(fm) + "\n---\n"
    atomic_write(path, fml + body)

def fm_title(title):
    # JSON string escaping is valid YAML double-quote style — colons etc. safe
    return "title: " + json.dumps(title, ensure_ascii=False)

def ensure_entity(slug, ptype, title, body_lines):
    if page_exists(slug):
        return False
    write_page(slug,
               [f"type: {ptype}", fm_title(title)],
               f"# {title}\n\n" + "\n".join(body_lines) + "\n")
    return True

def ensure_organs():
    made = ensure_entity("sia/cortex", "organ", "SIA cortex", [
        "I am SIA, the Omarchy Brain — the associative memory of this machine.",
        "Every organ below reports what it observes; the signed chains are",
        "re-verified with the SPARK-proved `attest` binary, and my thoughts",
        "are deterministic functions of the evidence.", ""])
    for key, (name, desc) in ORGANS.items():
        made |= ensure_entity(f"organs/{key}", "organ", name, [
            f"{desc}. Organ of [[sia/cortex]].", ""])
    return made


def day_slug(organ, date):
    return f"events/{organ}/{date}"


def update_day_page(organ, date, new_events):
    """Append bullets to the day page's Log and refresh Timeline + tags."""
    slug = day_slug(organ, date)
    path = corpus_path(slug)
    name = ORGANS.get(organ, (organ, ""))[0]
    counts, tags = {}, {organ}
    bullets = []
    if os.path.exists(path):
        text = open(path).read()
        m = FM_RE.match(text)
        if m:
            fmtext = m.group(1)
            cm = re.search(r"^sia_counts: (.*)$", fmtext, re.M)
            if cm:
                try:
                    counts = json.loads(cm.group(1))
                except Exception:
                    counts = {}
            tm = re.search(r"^tags: \[(.*)\]$", fmtext, re.M)
            if tm:
                tags |= {t.strip() for t in tm.group(1).split(",") if t.strip()}
            body = text[m.end():]
        else:
            body = text
        # bullets live only in the ## Log section; never parse past Timeline
        log_part = body.split("## Timeline")[0]
        if "## Log" in log_part:
            log_part = log_part.split("## Log", 1)[1]
        for line in log_part.splitlines():
            if line.startswith("- "):
                bullets.append(line)
    known = set(bullets)
    appended = []
    for ev in new_events:
        stamp = ev.ts.strftime("%H:%M:%SZ")
        links = " ".join(f"[[{l}]]" for l in sorted(ev.links)
                         if not l.startswith("organs/") and f"[[{l}" not in ev.summary)
        line = f"- {stamp} {ev.summary}" + (f" {links}" if links else "")
        if line not in known:      # single idempotence gate under replay:
            known.add(line)        # counts/tags move only with new bullets
            bullets.append(line)
            appended.append(ev)
            counts[ev.kind] = counts.get(ev.kind, 0) + 1
            tags |= ev.tags
    bullets = bullets[-400:]
    total = sum(counts.values())
    agg = ", ".join(f"{v}× {k}" for k, v in
                    sorted(counts.items(), key=lambda kv: -kv[1])[:6])
    fm = [f"type: event-day",
          fm_title(f"{name} — {date}"),
          f"tags: [{', '.join(sorted(tags))}]",
          f"date: {date}",
          f"sia_counts: {json.dumps(counts, sort_keys=True)}"]
    body = (f"# {name} — {date}\n\n"
            f"What [[organs/{organ}]] reported to [[sia/cortex]] on {date}.\n\n"
            f"## Log\n" + "\n".join(bullets) + "\n\n"
            f"## Timeline\n- **{date}** — {total} events: {agg}\n")
    write_page(slug, fm, body)
    return slug, appended


def ensure_event_entities(events):
    """Create referenced entity pages (units/packages/projects) lazily."""
    made = False
    for ev in events:
        for l in ev.links:
            if l.startswith("units/"):
                made |= ensure_entity(l, "unit", l.split("/", 1)[1],
                                      [f"systemd unit observed by [[organs/{ev.organ}]].", ""])
            elif l.startswith("packages/"):
                made |= ensure_entity(l, "package", l.split("/", 1)[1],
                                      ["Arch package seen in [[organs/pacman]] events.", ""])
            elif l.startswith("projects/"):
                made |= ensure_entity(l, "project", l.split("/", 1)[1],
                                      ["Repository under ~/Projects. Watched by [[organs/projects]].", ""])
    return made


def write_thought(thought):
    """thought: dict(ts, kind, text, links, urgent)."""
    dt = thought["ts"].replace(":", "").replace("-", "")[:13]
    slug = f"thoughts/{thought['ts'][:10]}-{dt[9:13]}-{sanitize_slugpart(thought['kind'])}"
    if page_exists(slug):
        slug += "-" + hashlib.sha256(thought["text"].encode()).hexdigest()[:6]
        base, n = slug, 2
        while page_exists(slug):
            slug = f"{base}-{n}"
            n += 1
    tags = ["thought", thought["kind"]] + (["urgent"] if thought.get("urgent") else [])
    links = " ".join(f"[[{l}]]"
                     for l in (thought.get("links") or ["sia/cortex"]))
    write_page(slug,
               ["type: thought",
                fm_title(clip(thought["text"], 70)),
                f"tags: [{', '.join(tags)}]",
                f"date: {thought['ts'][:10]}"],
               f"# thought · {thought['kind']}\n\n{thought['text']}\n\n{links}\n")
    return slug


# ---------------------------------------------------------------- gbrain

class _FailedRun:
    returncode = -1
    stdout = ""
    stderr = "subprocess failed/timed out"

def gbrain(args, timeout=120, json_out=False):
    try:
        r = subprocess.run([GBRAIN] + args, env=GBRAIN_ENV, capture_output=True,
                           text=True, timeout=timeout, cwd=CORPUS)
    except Exception:
        r = _FailedRun()
    if json_out:
        try:
            return json.loads(r.stdout[r.stdout.index("["):] if "[" in r.stdout
                              else r.stdout)
        except Exception:
            try:
                return json.loads(r.stdout[r.stdout.index("{"):])
            except Exception:
                return None
    return r


def gbrain_call(op, params, timeout=120):
    try:
        r = subprocess.run([GBRAIN, "call", "--source", "sia", op,
                            json.dumps(params)],
                           env=GBRAIN_ENV, capture_output=True, text=True,
                           timeout=timeout, cwd=CORPUS)
    except Exception:
        return None
    out = r.stdout
    for opener in ("[", "{"):
        i = out.find(opener)
        if i >= 0:
            try:
                return json.loads(out[i:])
            except Exception:
                continue
    return None


def corpus_commit(msg):
    """Tri-state: 'committed' | 'clean' (nothing to commit) | 'error'."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=CORPUS, capture_output=True,
                       timeout=60)
        s = subprocess.run(["git", "status", "--porcelain"], cwd=CORPUS,
                           capture_output=True, text=True, timeout=60)
        if s.returncode != 0:
            return "error"
        if not s.stdout.strip():
            return "clean"
        r = subprocess.run(["git", "-c", "user.email=sia@omarchy.local",
                            "-c", "user.name=SIA", "commit", "-q", "-m", msg],
                           cwd=CORPUS, capture_output=True, text=True,
                           timeout=60)
        return "committed" if r.returncode == 0 else "error"
    except Exception:
        return "error"


def brain_sync():
    r = gbrain(["sync", "--source", "sia"], timeout=300)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout)[-400:]
    # sync does not run link extraction — materialize typed edges now
    x = gbrain(["extract", "links", "--source", "db", "--stale", "--json"],
               timeout=300)
    if x.returncode != 0:
        return False, "extract: " + (x.stderr or x.stdout)[-300:]
    return True, ""


# ---------------------------------------------------------------- integrity

AEGIS_LEDGER_TOOL = os.path.join(
    HOME, ".config/omarchy/plugins/khephri.aegis/bin/aegis-ledger")

def _chain_cmds():
    """Chain registry: SIA's own signed ledger always; known keeper chains
    auto-detected when present on this machine (each verified by ITS OWN
    verifier); user-defined chains from config `chains` entries of the
    form {name, ledger, verify: [argv...]}."""
    chains = {
        "sia": (os.path.join(SHARE, "ledger.tsv"),
                os.path.join(BIN, "sia-ledger"),
                [sys.executable, os.path.join(BIN, "sia-ledger"), "verify",
                 SHARE, "--quiet"]),
    }
    custos_dir = os.path.join(HOME, ".local/share/custos")
    sekhmet_bin = os.path.join(HOME, ".local/bin/sekhmet")
    known = {
        "custos": (os.path.join(custos_dir, "ledger.tsv"), ATTEST,
                   [ATTEST, "verify-custos",
                    os.path.join(custos_dir, "ledger.tsv"),
                    os.path.join(custos_dir, "pub.hex")]),
        "sekhmet": (os.path.join(HOME, ".local/share/sekhmet/ledger.tsv"),
                    sekhmet_bin,
                    [sekhmet_bin, "ledger", "verify", "--quiet"]),
        "aegis": (os.path.join(HOME, ".local/share/aegis/ledger.tsv"),
                  AEGIS_LEDGER_TOOL,
                  [sys.executable, AEGIS_LEDGER_TOOL, "verify",
                   os.path.join(HOME, ".local/share/aegis"), "--quiet"]),
    }
    for name, (ledger, tool, cmd) in known.items():
        if os.path.exists(ledger) and os.path.exists(tool):
            chains[name] = (ledger, tool, cmd)
    for c in CONFIG.get("chains", []):
        try:
            ledger = os.path.expanduser(str(c["ledger"]))
            cmd = [os.path.expanduser(str(a)) for a in c["verify"]]
            chains[sanitize_slugpart(str(c["name"]))] = (ledger, cmd[0], cmd)
        except Exception:
            continue
    return chains

def verify_chains():
    """Returns {name: 'pass'|'fail'|'absent'}."""
    out = {}
    for name, (ledger, tool, cmd) in _chain_cmds().items():
        if not os.path.exists(ledger) or not os.path.exists(tool):
            out[name] = "absent"
            continue
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            out[name] = "pass" if r.returncode == 0 else "fail"
        except Exception:
            out[name] = "fail"
    return out


def ledger_append(action, arg1, arg2, content=""):
    try:
        sha = hashlib.sha256(content.encode()).hexdigest()
        subprocess.run([sys.executable, os.path.join(BIN, "sia-ledger"),
                        "append", SHARE, action, str(arg1)[:120],
                        str(arg2)[:120], sha, str(len(content.encode()))],
                       capture_output=True, timeout=30)
    except Exception:
        log(f"ledger append failed for {action}")


def ledger_head():
    try:
        r = subprocess.run([sys.executable, os.path.join(BIN, "sia-ledger"),
                            "head", SHARE], capture_output=True, text=True, timeout=30)
        n, h = r.stdout.split()
        return int(n), h
    except Exception:
        return 0, ""


# ---------------------------------------------------------------- thoughts

THOUGHTS_PATH = os.path.join(STATE, "thoughts.json")

def load_thoughts():
    return read_json(THOUGHTS_PATH, {"v": 1, "thoughts": []})

def add_thought(store, kind, text, links=(), urgent=False):
    t = {"ts": iso(), "kind": kind, "text": text,
         "links": sorted(links), "urgent": bool(urgent)}
    store["thoughts"].append(t)
    store["thoughts"] = store["thoughts"][-200:]
    slug = write_thought(t)
    t["slug"] = slug
    log(f"thought[{kind}] {text}")
    return t


def think(store, memo, events, chains, salience, anomalies):
    """Deterministic thought generators. memo persists across pulses."""
    new = []
    day = today()

    # 1. chain integrity transitions (pass→absent is a regression too)
    prev = memo.get("chains", {})
    failing = sorted(k for k, v in chains.items() if v == "fail")
    gone = sorted(k for k, v in chains.items()
                  if v != "pass" and prev.get(k) == "pass" and v != "fail")
    if chains != prev:
        if failing:
            new.append(add_thought(store, "integrity",
                f"Evidence chain FAILED verification: {', '.join(failing)}. "
                f"The keeper's own verifier rejected the chain.",
                [f"organs/{f}" for f in failing if f in ORGANS], urgent=True))
        elif gone:
            new.append(add_thought(store, "integrity",
                f"Evidence chain no longer verifiable: {', '.join(gone)} "
                f"(ledger or verifier missing).", ["sia/cortex"], urgent=True))
        elif prev:
            passing = sorted(k for k, v in chains.items() if v == "pass")
            new.append(add_thought(store, "integrity",
                f"All evidence chains verify again: {', '.join(passing)}.",
                ["sia/cortex"]))
        memo["chains"] = chains
    if not prev and not failing and chains:
        passing = sorted(k for k, v in chains.items() if v == "pass")
        new.append(add_thought(store, "integrity",
            f"First integrity sweep: {len(passing)} signed chains verified "
            f"with attest ({', '.join(passing)}).", ["sia/cortex"]))
        memo["chains"] = chains

    # 2. per-organ rules (dedup identical thoughts within a pulse)
    pulse_seen = set()
    def once(kind, text):
        if (kind, text) in pulse_seen:
            return False
        pulse_seen.add((kind, text))
        return True
    for ev in events:
        if "refusal" in ev.tags and memo.get("last_refusal_day") != day:
            memo["last_refusal_day"] = day
            new.append(add_thought(store, "refusal",
                f"JACKAL refused to answer rather than guess ({ev.summary}). "
                f"A refusal is an answer.", ["organs/jackal"]))
        if ev.organ == "sekhmet" and ev.kind == "outcome":
            t = f"I watched SEKHMET heal the fabric: {ev.summary}."
            if once("healing", t):
                new.append(add_thought(store, "healing", t, sorted(ev.links)))
        if "collapse" in ev.tags:
            t = f"WORLDLINE collapsed a reality: {ev.summary}."
            if once("collapse", t):
                new.append(add_thought(store, "collapse", t,
                                       ["organs/worldline"]))
        if "coredump" in ev.tags:
            t = f"Something crashed: {ev.summary}."
            if once("crash", t):
                new.append(add_thought(store, "crash", t, sorted(ev.links),
                                       urgent=True))
        if "formal-receipt" in ev.tags and ev.kind == "receipt" \
                and memo.get("last_receipt_day") != day:
            memo["last_receipt_day"] = day
            new.append(add_thought(store, "formal",
                "JACKAL retained a formal receipt today — Lean-checked "
                "mathematics entered my memory.", ["organs/jackal"]))

    # 3. anomaly cohorts (statistical, from gbrain) — a zero baseline means
    # "no history yet", not "anomaly"; require a real baseline and cap per pulse
    seen = set(memo.get("anomaly_keys", []))
    emitted = 0
    for a in (anomalies or []):
        if float(a.get("baseline_mean") or 0) <= 0 or \
           float(a.get("baseline_stddev") or 0) <= 0 or emitted >= 3:
            continue
        key = f"{a.get('cohort_kind')}:{a.get('cohort_value')}:{day}"
        if key in seen:
            continue
        seen.add(key)
        emitted += 1
        new.append(add_thought(store, "anomaly",
            f"Unusual activity in {a.get('cohort_kind')} "
            f"“{a.get('cohort_value')}”: {a.get('count')} pages touched vs "
            f"baseline μ={round(a.get('baseline_mean', 0), 1)} "
            f"σ={round(a.get('baseline_stddev', 0), 1)}.", ["sia/cortex"]))
    memo["anomaly_keys"] = sorted(seen)[-100:]

    # 4. salience shift
    if salience:
        top = salience[0].get("slug", "")
        if top and top != memo.get("salience_top") and not top.startswith("thoughts/"):
            memo["salience_top"] = top
            new.append(add_thought(store, "attention",
                f"My attention has shifted: the most salient memory is now "
                f"“{salience[0].get('title', top)}”.", [top]))

    return new


# ---------------------------------------------------------------- exports

STATUS_PATH = os.path.join(STATE, "status.json")
GRAPH_PATH = os.path.join(STATE, "graph.json")

def corpus_edges():
    """Derive the edge set directly from the corpus's own wikilinks —
    the daemon wrote every [[link]], so it need not ask the engine what
    they are. Deterministic, O(files), immune to traversal blowup (the
    engine's path-enumerating traverse_graph times out once a hub page
    links a hundred entities — discovered 2026-08-29 when a package
    burst created exactly that)."""
    edges = []
    for root, _, files in os.walk(CORPUS):
        if ".git" in root:
            continue
        for fname in files:
            if not fname.endswith(".md"):
                continue
            path = os.path.join(root, fname)
            slug = os.path.relpath(path, CORPUS)[:-3]
            try:
                text = open(path, errors="replace").read()
            except OSError:
                continue
            m = FM_RE.match(text)
            body = text[m.end():] if m else text
            for lm in re.finditer(r"\[\[([a-z0-9/._-]+)(?:\|[^\]]*)?\]\]",
                                  body):
                target = lm.group(1)
                lo = max(0, lm.start() - 45)
                why = re.sub(r"\s+", " ",
                             body[lo:lm.end() + 45]).strip()[:90]
                edges.append({"from_slug": slug, "to_slug": target,
                              "link_type": "mentions", "context": why})
    return edges


def export_graph():
    """Graph snapshot v2 — carries its own truth boundary (the snapshot
    block says what is complete, what was truncated, and which reads
    failed), per-node in/out degrees, and per-edge type + extraction
    context so the panel can answer 'why does this connection exist'.
    Edges come from the corpus itself (see corpus_edges)."""
    failed_ops = []
    pages = gbrain_call("list_pages", {"limit": 1000})
    if not isinstance(pages, list):
        failed_ops.append("list_pages")
        pages = []
    try:
        paths = corpus_edges()
    except Exception:
        failed_ops.append("corpus_edges")
        paths = []
    cutoff = (utcnow() - datetime.timedelta(days=14)).isoformat()
    keep = {}
    for p in pages:
        slug = p.get("slug", "")
        t = p.get("type", "note")
        recent = (p.get("updated_at") or "") >= cutoff
        if t in ("organ",) or slug == "sia/cortex" or recent:
            keep[slug] = {"id": slug, "t": t, "title": p.get("title", slug),
                          "ts": p.get("updated_at", ""),
                          "deg": 0, "din": 0, "dout": 0}
    aged_out = len(pages) - len(keep)
    truncated = 0
    if len(keep) > 260:
        organs = {k: v for k, v in keep.items() if v["t"] == "organ"}
        rest = sorted((v for v in keep.values() if v["t"] != "organ"),
                      key=lambda v: v["ts"], reverse=True)[:260 - len(organs)]
        truncated = len(keep) - len(organs) - len(rest)
        keep = {**organs, **{v["id"]: v for v in rest}}
    edges, eseen = [], set()
    for e in paths:
        s, d = e.get("from_slug"), e.get("to_slug")
        if s in keep and d in keep and (s, d) not in eseen:
            eseen.add((s, d))
            why = re.sub(r"\s+", " ", str(e.get("context") or "")).strip()[:90]
            edges.append({"s": s, "d": d,
                          "t": e.get("link_type", "mentions"), "why": why})
            keep[s]["deg"] += 1; keep[s]["dout"] += 1
            keep[d]["deg"] += 1; keep[d]["din"] += 1
    counts = {}
    for v in keep.values():
        counts[v["t"]] = counts.get(v["t"], 0) + 1
    graph = {"v": 2, "ts": iso(),
             "nodes": sorted(keep.values(), key=lambda n: n["id"]),
             "edges": edges,
             "pages_total": len(pages),
             "snapshot": {"complete": not failed_ops and not truncated,
                          "truncated": truncated,
                          "aged_out": aged_out,
                          "counts_by_kind": counts,
                          "failed_ops": failed_ops,
                          "window_days": 14}}
    atomic_write(GRAPH_PATH, json.dumps(graph))
    return len(keep), len(edges), len(pages)


def export_status(st):
    atomic_write(STATUS_PATH, json.dumps(st))


def export_thoughts(store):
    atomic_write(THOUGHTS_PATH, json.dumps(store))


# ---------------------------------------------------------------- pulse

MEMO_PATH = os.path.join(STATE, "memo.json")

def pulse(seq, opts=None):
    """One heartbeat. Returns the status dict it exported."""
    opts = opts or {}
    ensure_dirs()
    cursors = load_cursors()
    store = load_thoughts()
    memo = read_json(MEMO_PATH, {})
    stnow = read_json(STATUS_PATH, {})
    organs_st = stnow.get("organs", {})
    day = today()
    if stnow.get("day") != day:
        # keep the organ roster stable across midnight; zero the counters
        organs_st = {k: {**v, "today": 0} for k, v in organs_st.items()}

    # Each sense runs on an isolated cursor copy, merged back only on
    # success — a raising sense never persists cursor advances for events
    # it dropped. Cursors are made durable only AFTER the corpus writes.
    PENDING_CURSOR_RENAMES.clear()
    events, errors = [], {}
    for sense in SENSES:
        trial = copy.deepcopy(cursors)
        try:
            evs = sense(trial)
        except Exception as e:
            errors[sense.__name__] = str(e)[:160]
            continue
        events.extend(evs)
        cursors.clear()
        cursors.update(trial)

    synced, sync_note = True, ""
    made_pages = []
    committed_events = []          # events whose bullets are durably new
    write_ok = True
    try:
        if events:
            ensure_organs()
            ensure_event_entities(events)
            by_day = {}
            for ev in events:
                by_day.setdefault((ev.organ, ev.ts.strftime("%Y-%m-%d")),
                                  []).append(ev)
            for (organ, d), evs in by_day.items():
                dslug, appended = update_day_page(organ, d, evs)
                made_pages.append(dslug)
                committed_events.extend(appended)
                o = organs_st.setdefault(organ, {"today": 0, "last_ts": ""})
                if d == day:
                    o["today"] += len(appended)
                if appended:
                    o["last_ts"] = iso(max(e.ts for e in appended))
    except Exception as e:
        write_ok = False
        errors["corpus_write"] = str(e)[:160]
    if write_ok:
        # events are on disk (or there were none) — commit the cursors
        for tmp, real in PENDING_CURSOR_RENAMES:
            try:
                if os.path.exists(tmp):
                    os.replace(tmp, real)
            except Exception:
                pass
        PENDING_CURSOR_RENAMES.clear()
        save_cursors(cursors)

    # thoughts may add corpus pages too — generate BEFORE commit+sync
    every = int(opts.get("integrity_every", 10))
    chains = memo.get("chains", {})
    salience = anomalies = None
    if events or seq % every == 0 or not chains:
        chains = verify_chains()
        if seq % every == 0 or events:
            salience = gbrain_call("get_recent_salience", {"days": 7, "limit": 5})
            anomalies = gbrain_call("find_anomalies", {"sigma": 3.0})
            if isinstance(anomalies, dict):
                anomalies = anomalies.get("anomalies", anomalies.get("results", []))
    new_thoughts = think(store, memo, events, chains,
                         salience if isinstance(salience, list) else [],
                         anomalies if isinstance(anomalies, list) else [])

    # thoughts queued by out-of-band tools (e.g. `sia ponder` → GPT-5.6-Sol);
    # the inbox keeps thoughts.json single-writer (this daemon)
    inbox_path = os.path.join(STATE, "thought-inbox.json")
    inbox = read_json(inbox_path, [])
    if inbox:
        for t in inbox:
            try:
                new_thoughts.append(add_thought(
                    store, t.get("kind", "note"), t.get("text", ""),
                    t.get("links", []), t.get("urgent", False)))
            except Exception:
                pass
        try:
            os.unlink(inbox_path)
        except OSError:
            pass

    # ---- neurocognitive core (siamind): recall touches, Hebbian binding,
    # novelty gate, surprisal baselines, global workspace. Deterministic;
    # mind.json is owned by this daemon alone.
    mind = siamind.load_mind()
    ws = mind.get("workspace", [])
    try:
        if not mind["seen"]:
            # first run: everything already in the graph counts as seen —
            # novelty is for what arrives from now on
            g0 = read_json(GRAPH_PATH, {})
            for n0 in g0.get("nodes", []):
                mind["seen"][n0["id"]] = time.time()
        siamind.drain_touch_queue(mind)
        # ingest ONLY durably-appended events (idempotent under replay:
        # a re-sensed event whose bullet already exists never re-counts)
        ingest = committed_events if write_ok else []
        batch_kinds = [ev.kind for ev in ingest]
        organ_counts, organ_arousal = {}, {}
        nov_emitted = 0
        for ev in ingest:
            organ_counts[ev.organ] = organ_counts.get(ev.organ, 0) + 1
            ar = siamind.arousal_of(ev.tags)
            organ_arousal[ev.organ] = max(organ_arousal.get(ev.organ, 0.0), ar)
            siamind.bump_kind(mind, ev.organ, ev.kind, ev.tags)
            dslug = day_slug(ev.organ, ev.ts.strftime("%Y-%m-%d"))
            siamind.touch(mind, dslug, ev.ts.timestamp(), src="organ")
            for l in ev.links:
                siamind.touch(mind, l, ev.ts.timestamp(), src="organ")
                siamind.hebb(mind, dslug, l)
            score, reasons = siamind.novelty(
                mind, ev.organ, ev.kind, sorted(ev.links), batch_kinds,
                ev.ts.timestamp())
            if score >= 0.6 and nov_emitted < 2:
                nov_emitted += 1
                ev.tags.add("novelty")
                new_thoughts.append(add_thought(store, "novelty",
                    f"Novel: {ev.summary} — {'; '.join(reasons[:2])} "
                    f"(novelty {score:.2f}).", sorted(ev.links)))
        for s_organ, s_kind, s_text in siamind.surprisal_update(
                mind, organ_counts):
            new_thoughts.append(add_thought(store, "surprise", s_text,
                                            [f"organs/{s_organ}"]))
        ws = siamind.rebuild_workspace(mind, organ_arousal)
        siamind.save_mind(mind)
    except Exception as e:
        errors["siamind"] = str(e)[:160]

    # outcome learning: remind (once a day) when predictions come due
    takes_sum = {}
    try:
        takes_sum = siatakes.summary()
        if takes_sum.get("due") and memo.get("takes_reminder_day") != day:
            memo["takes_reminder_day"] = day
            new_thoughts.append(add_thought(store, "take",
                f"{takes_sum['due']} of my predictions are due for "
                f"grading — tonight's dream judges up to 3, or run "
                f"`sia grade` now.", ["sia/cortex"]))
    except Exception as e:
        errors["siatakes"] = str(e)[:160]

    nodes = edges = pages_total = None
    if events or new_thoughts or ensure_organs():
        commit = corpus_commit(f"pulse {seq}: {len(events)} events, "
                               f"{len(new_thoughts)} thoughts")
        if commit == "error":
            synced, sync_note = False, "corpus git commit failed"
        elif commit == "committed":
            synced, sync_note = brain_sync()
        nodes, edges, pages_total = export_graph()
        ledger_append("PULSE:ingest", f"{len(events)}ev/{len(new_thoughts)}th",
                      "ok" if synced else "sync-fail",
                      json.dumps([p for p in made_pages]))

    hist = memo.get("pulse_history", [])
    hist.append([iso(), len(events)])
    memo["pulse_history"] = hist[-120:]
    if REDACTIONS:
        red = memo.setdefault("redactions", {})
        for organ, n in REDACTIONS.items():
            red[organ] = red.get(organ, 0) + n
        REDACTIONS.clear()
    atomic_write(MEMO_PATH, json.dumps(memo))
    export_thoughts(store)

    lseq, lhead = ledger_head()
    failing = [k for k, v in chains.items() if v == "fail"]
    state = ("failed" if failing else
             "degraded" if (errors or not synced) else
             "thinking" if (events or new_thoughts) else "ok")
    last_thought = (store["thoughts"] or [{}])[-1]
    prev_graph = read_json(GRAPH_PATH, {})
    st = {"v": 1, "ts": iso(), "state": state, "pulse_seq": seq, "day": day,
          "events_pulse": len(events),
          "events_today": sum(o.get("today", 0) for o in organs_st.values()),
          "organs": organs_st, "errors": errors,
          "pages": pages_total if pages_total is not None
                   else prev_graph.get("pages_total", 0),
          "graph_nodes": nodes if nodes is not None
                         else len(prev_graph.get("nodes", [])),
          "graph_edges": edges if edges is not None
                         else len(prev_graph.get("edges", [])),
          "integrity": {"chains": chains,
                        "verdict": "fail" if failing else
                                   ("pass" if chains else "unknown"),
                        "checked_at": iso()},
          "ledger": {"seq": lseq, "head": lhead[:12]},
          "thought": {"ts": last_thought.get("ts", ""),
                      "kind": last_thought.get("kind", ""),
                      "text": last_thought.get("text", "")},
          "dream": memo.get("dream", {}),
          "history": memo.get("pulse_history", []),
          "workspace": ws,
          "mind": {"nodes": len(mind.get("nodes", {})),
                   "edges": len(mind.get("edges", {}))},
          "takes": takes_sum,
          "redactions": memo.get("redactions", {}),
          "sync_note": sync_note}
    export_status(st)
    return st


def consolidate_corpus():
    """Systems consolidation (hippocampus→neocortex): day pages older than
    the episodic window compact into weekly epoch pages. McGaugh preserve
    rule: days tagged with safety-class arousal stay verbatim forever
    (flashbulb memories). Originals always remain in corpus git history."""
    # never consolidate over an unhealthy repo: the unlink below is only
    # honest if the verbatim file is provably in git history first
    if corpus_commit("pre-consolidation") == "error":
        log("consolidation skipped: corpus git commit failing")
        return 0, 0, 0
    cutoff = (utcnow() - datetime.timedelta(
        days=siamind.EPISODIC_DAYS)).strftime("%Y-%m-%d")
    groups, kept = {}, 0
    for path in glob.glob(os.path.join(CORPUS, "events/*/*.md")):
        m = re.match(r".*events/([^/]+)/(\d{4}-\d{2}-\d{2})\.md$", path)
        if not m:
            continue
        organ, date = m.group(1), m.group(2)
        if date >= cutoff:
            continue
        rel = os.path.relpath(path, CORPUS)
        try:
            tracked = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", rel],
                cwd=CORPUS, capture_output=True, timeout=30).returncode == 0
            clean = subprocess.run(
                ["git", "status", "--porcelain", "--", rel],
                cwd=CORPUS, capture_output=True, text=True,
                timeout=30).stdout.strip() == ""
        except Exception:
            tracked = clean = False
        if not (tracked and clean):
            continue               # not durably committed — try next dream
        text = open(path, errors="replace").read()
        tm = re.search(r"^tags: \[(.*)\]$", text, re.M)
        tags = {t.strip() for t in (tm.group(1).split(",") if tm else [])}
        if tags & siamind.SAFETY_TAGS:
            # flashbulb is a POLICY, not a keyword: integrity transitions
            # always stay verbatim; other safety classes stay only while
            # they are rare (≤12 lifetime events of that class). Routine
            # breakage — the 40th hyprland-dialog coredump — compacts to
            # gist like everything else; git keeps the bytes either way.
            tagn = siamind.load_mind().get("tagn", {})
            rare = ("integrity-failure" in tags) or any(
                t in siamind.SAFETY_TAGS and tagn.get(t, 0) <= 12
                for t in tags)
            if rare:
                kept += 1
                continue
        y, w, _ = datetime.date.fromisoformat(date).isocalendar()
        groups.setdefault((organ, y, w), []).append((date, path, text, tags))
    nfiles = 0
    for (organ, y, w), items in groups.items():
        items.sort()
        name = ORGANS.get(organ, (organ, ""))[0]
        counts, all_tags, bullets, links = {}, {organ}, [], set()
        for date, path, text, tags in items:
            cm = re.search(r"^sia_counts: (.*)$", text, re.M)
            if cm:
                try:
                    for k, v in json.loads(cm.group(1)).items():
                        counts[k] = counts.get(k, 0) + v
                except Exception:
                    pass
            all_tags |= tags
            log_part = text.split("## Timeline")[0].split("## Log")[-1]
            blts = [l for l in log_part.splitlines() if l.startswith("- ")]
            for b in blts[:2] + blts[-1:]:
                bullets.append(f"- {date} ·" + b[1:])
            for wl in re.findall(r"\[\[([a-z0-9/._-]+)", text):
                links.add(wl)
        slug = f"epochs/{organ}/{y}-w{w:02d}"
        # merge with an existing epoch page — a later consolidation run for
        # the same week must extend it, never atomically erase it
        epath = corpus_path(slug)
        from_date, ndays = items[0][0], len(items)
        if os.path.exists(epath):
            et = open(epath, errors="replace").read()
            pm = re.search(r"^sia_counts: (.*)$", et, re.M)
            if pm:
                try:
                    for k, v in json.loads(pm.group(1)).items():
                        counts[k] = counts.get(k, 0) + v
                except Exception:
                    pass
            ptm = re.search(r"^tags: \[(.*)\]$", et, re.M)
            if ptm:
                all_tags |= {t.strip() for t in ptm.group(1).split(",")
                             if t.strip()}
            pdm = re.search(r"^date: (.*)$", et, re.M)
            if pdm and pdm.group(1).strip() < from_date:
                from_date = pdm.group(1).strip()
            ddm = re.search(r"Consolidated from (\d+) day-memories", et)
            if ddm:
                ndays += int(ddm.group(1))
            if "## Exemplars" in et:
                ex = et.split("## Exemplars", 1)[1].split("\n## ")[0]
                prev_b = [l for l in ex.splitlines() if l.startswith("- ")]
                bullets = prev_b + bullets
            for wl in re.findall(r"\[\[([a-z0-9/._-]+)", et):
                links.add(wl)
        bullets = bullets[:24]
        total = sum(counts.values())
        agg = ", ".join(f"{v}× {k}" for k, v in
                        sorted(counts.items(), key=lambda kv: -kv[1])[:8])
        linkline = " ".join(f"[[{l}]]" for l in sorted(links)
                            if not l.startswith("events/"))[:800]
        write_page(slug,
            ["type: epoch", fm_title(f"{name} — {y} week {w}"),
             f"tags: [{', '.join(sorted(all_tags))}]",
             f"date: {from_date}",
             f"sia_counts: {json.dumps(counts, sort_keys=True)}"],
            f"# {name} — {y} week {w}\n\n"
            f"Consolidated from {ndays} day-memories "
            f"({from_date} … {items[-1][0]}); originals verbatim in "
            f"corpus git history. Organ: [[organs/{organ}]] of "
            f"[[sia/cortex]].\n\n"
            f"## Exemplars\n" + "\n".join(bullets) + "\n\n"
            f"{linkline}\n\n"
            f"## Timeline\n- **{items[-1][0]}** — {total} events that "
            f"week: {agg}\n")
        for date, path, text, tags in items:
            try:
                os.unlink(path)
                nfiles += 1
            except OSError:
                pass
    return nfiles, len(groups), kept


def dream(memo_update=True):
    """Nightly consolidation: run gbrain's deterministic dream cycle."""
    store0 = load_thoughts()
    # the nightly job is FOUR units with separate ledgers and separate
    # failure — a bad grade must never block an epoch merge
    try:
        ncomp, nepoch, nkept = consolidate_corpus()
        ledger_append("DREAM:consolidate", f"{ncomp}d>{nepoch}e",
                      f"verbatim={nkept}")
        if ncomp:
            add_thought(store0, "dream",
                f"I consolidated {ncomp} day-memories into {nepoch} epoch "
                f"memories; {nkept} rare/high-arousal days stay verbatim. "
                f"The originals live on in my git history.", ["sia/cortex"])
    except Exception as e:
        ledger_append("DREAM:consolidate", "error", str(e)[:80])
        log(f"consolidation failed: {e!r}")
    try:
        mind = siamind.load_mind()
        pruned = siamind.hebb_hygiene(mind)
        g = read_json(GRAPH_PATH, None)
        _, lhead = ledger_head()
        m = siamind.muse(mind, g, today(), lhead)
        siamind.save_mind(mind)
        ledger_append("DREAM:muse", "1" if m else "0",
                      f"edges-pruned={pruned}")
        if m:
            add_thought(store0, "association", m[0], m[1])
    except Exception as e:
        ledger_append("DREAM:muse", "error", str(e)[:80])
        log(f"musing failed: {e!r}")
    # outcome learning: grade due predictions (≤3/night; GPT-5.6-Sol judge,
    # deterministic Brier), then restate calibration
    try:
        graded_any = False
        for t in siatakes.due_takes()[:3]:
            gt = siatakes.grade_take(t)
            if not gt:
                continue
            graded_any = True
            ledger_append("GRADE:take", gt["id"], gt["status"], gt["claim"])
            mark = {"resolved-true": "TRUE",
                    "resolved-false": "FALSE"}.get(gt["status"],
                                                   "UNRESOLVABLE")
            brier = (f" · Brier {gt['brier']}"
                     if gt["brier"] is not None else "")
            add_thought(store0, "grade",
                f"Graded my prediction “{clip(gt['claim'], 80)}”: "
                f"{mark}{brier}.", [gt["slug"]])
        if graded_any:
            cal = siatakes.summary()
            if cal.get("resolved"):
                add_thought(store0, "calibration",
                    f"My calibration: {cal['resolved']} predictions "
                    f"resolved, mean Brier {cal['brier']} "
                    f"(0.0 = prophet, 0.25 = coin-flip).", ["sia/cortex"])
        ledger_append("DREAM:grade", "done" if graded_any else "none-due", "")
    except Exception as e:
        ledger_append("DREAM:grade", "error", str(e)[:80])
        log(f"take grading failed: {e!r}")
    export_thoughts(store0)
    r = gbrain(["dream", "--json"], timeout=900)
    rep = None
    for opener in ("{",):
        i = r.stdout.find(opener)
        if i >= 0:
            try:
                rep = json.loads(r.stdout[i:])
            except Exception:
                pass
    store = load_thoughts()
    memo = read_json(MEMO_PATH, {})
    if rep:
        tot = rep.get("totals", {})
        bits = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in tot.items()
                         if isinstance(v, (int, float)) and v)
        text = (f"I dreamed: consolidation cycle finished with status "
                f"“{rep.get('status')}” in "
                f"{round(rep.get('duration_ms', 0) / 1000)}s"
                + (f" — {bits}." if bits else "."))
        memo["dream"] = {"last": iso(), "status": rep.get("status"),
                         "summary": bits}
        add_thought(store, "dream", text, ["sia/cortex"])
        ledger_append("DREAM:cycle", rep.get("status", "?"), bits[:100],
                      json.dumps(tot))
    else:
        memo["dream"] = {"last": iso(), "status": "failed",
                         "summary": (r.stderr or "")[-160:]}
        add_thought(store, "dream", "My dream cycle failed to run.",
                    ["sia/cortex"], urgent=True)
    atomic_write(MEMO_PATH, json.dumps(memo))
    export_thoughts(store)
    corpus_commit("dream")
    brain_sync()
    export_graph()
    return rep
