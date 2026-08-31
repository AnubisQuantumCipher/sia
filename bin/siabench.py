"""siabench — evidence-derived, leakage-resistant SIA memory evaluation.

The full benchmark builds question/answer pairs from keeper-accepted signed
ledger rows only after the observed ledger and verifier file identity,
metadata, and digests stay unchanged across verification. Built-in Custos
retains its legacy line-hashed grammar; other built-ins and custom chains use
the attest-ledger grammar. Answer keys stay outside the indexed corpus, carry
format/row/head provenance, and are split from question-only exports.
Evaluation thresholds are selected on a deterministic calibration split and
then frozen for the held-out split. ``ABSTAIN`` is a literal scored answer,
never inferred from missing output.

The older corpus-conditioned probes remain available for the small nightly
drift tripwire; they are not described as a LongMemEval-style QA population.
"""

import argparse
import datetime
import hashlib
import heapq
import html
import json
import math
import os
import re
import stat
import statistics
import subprocess
import sys
import time
import unicodedata
import urllib.parse
from xml.sax.saxutils import escape as xml_escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import siamind, sialib, siaqueue

CORPUS = sialib.CORPUS

ABSTAIN = "ABSTAIN"
DATASET_SCHEMA = "sia-signed-ledger-qa-v2"
PRIVATE_MANIFEST_SCHEMA = "sia-signed-ledger-qa-private-manifest-v2"
# JACKAL status=exact, parsed=5+1, exact=6. Exact rational arithmetic outside
# the Lean certificate chain (NOT formal-bounded).
GENERATOR_VERSION = "6"
ANSWER_WITNESS_SCHEMA = "sia-retrieval-answer-witness-v1"
PUBLIC_MANIFEST_BASE_FIELDS = (
    "schema", "generator_version", "dataset_id", "question_count",
    "answer_key_location", "abstention_token", "calibration_policy",
    "capacity_policy", "questions", "generation_exclusions", "non_claims",
)
PUBLIC_MANIFEST_FIELDS = frozenset(PUBLIC_MANIFEST_BASE_FIELDS) | {
    "questions_sha256", "private_integrity_manifest",
}
PRIVATE_MANIFEST_FIELDS = {
    "schema", "dataset_id", "public_manifest_sha256", "answer_key_sha256",
    "mcp_evaluation_sha256", "mcp_evaluation_rows", "evaluation_manifest",
    "evaluation_manifest_sha256",
}
ATTEST_CHAIN_FORMAT = "attest-ledger-v1"
CUSTOS_CHAIN_FORMAT = "custos-ledger-v1"
CALIBRATION_DIVISOR = 4       # deterministic display/evaluation policy
MAX_PER_CATEGORY = 64         # cap runtime; hash selection avoids recency bias
TOP_K = 5
MCP_EVALUATION_LIMIT = 10
# Complete evidence is never truncated to fit these ceilings. A chain or
# artifact beyond them is an explicit BenchmarkRefusal because genesis-to-head
# linkage, latest-row questions, and negative witnesses all require the whole
# observed snapshot. The shared constants carry their JACKAL exact comments in
# sialib (NOT formal-bounded).
MAX_BENCH_FILE_BYTES = sialib.MAX_STATE_JSON_BYTES
MAX_BENCH_LEDGER_BYTES = sialib.MAX_STATE_JSON_BYTES
# JACKAL status=exact, parsed=4*1024*1024, exact=4194304. Exact rational
# arithmetic outside the Lean certificate chain (NOT formal-bounded).
MAX_BENCH_VERIFIER_BYTES = 4_194_304
MAX_BENCH_SOURCE_PAGE_BYTES = sialib.MAX_EVENT_PAGE_BYTES
MAX_BENCH_AGGREGATE_BYTES = sialib.MAX_LEDGER_PENDING_BYTES
MAX_BENCH_SOURCE_BYTES = sialib.MAX_STATE_JSON_BYTES
MAX_BENCH_ROWS = sialib.MAX_SOURCE_REPLAY_EVENTS
MAX_BENCH_SOURCE_PAGES = sialib.MAX_EVENT_LOOKUP_PAGES
MAX_BENCH_CANDIDATE_QUESTIONS = sialib.MAX_SOURCE_REPLAY_EVENTS
MAX_BENCH_NEGATIVE_PAIRS = sialib.MAX_SOURCE_REPLAY_EVENTS
LEGACY_TRIPWIRE_SCHEMA = "sia-heuristic-slug-retrieval-tripwire-v1"
LEGACY_TRIPWIRE_NON_CLAIMS = [
    "hand-authored slug-family acceptors are relevance heuristics, not answer keys",
    "a matching page slug does not establish that a reader produced a correct answer",
    "synthetic negative prompts do not prove the corpus contains no relevant evidence",
    "threshold crossings are drift signals, not scored abstention decisions",
]


class BenchmarkRefusal(RuntimeError):
    """The requested benchmark cannot make its declared evidence claim."""


def _engine(args, timeout=180):
    result = None
    for _ in range(4):
        result = sialib.gbrain(args + ["--source", "sia", "--json"],
                               timeout=timeout)
        combined = ((result.stdout if isinstance(result.stdout, str) else "")
                    + (result.stderr
                       if isinstance(result.stderr, str) else ""))
        if result.returncode == 0 or "already open" not in combined:
            break
        time.sleep(3)
    if result is None or result.returncode != 0:
        raise BenchmarkRefusal("gbrain retrieval did not complete")
    try:
        if not isinstance(result.stdout, str):
            raise ValueError("result output is not text")
        i = result.stdout.index("[")
        payload = json.loads(result.stdout[i:])
        if not isinstance(payload, list):
            raise ValueError("result is not a list")
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("result row is not an object")
            slug = item.get("slug")
            if slug is not None and not isinstance(slug, str):
                raise ValueError("result slug is not a string")
            chunk_text = item.get("chunk_text")
            if chunk_text is not None and not isinstance(chunk_text, str):
                raise ValueError("result chunk text is not a string")
            score = float(item.get("score") or 0)
            if not math.isfinite(score):
                raise ValueError("result score is not finite")
        return payload
    except (AttributeError, TypeError, UnicodeError, ValueError,
            RecursionError) as exc:
        raise BenchmarkRefusal(
            "gbrain retrieval output could not be admitted") from exc


def _dedupe(results):
    seen, out = set(), []
    for x in results:
        s = x.get("slug")
        if s and s not in seen:
            seen.add(s)
            out.append((s, float(x.get("score") or 0),
                        x.get("type", "")))
    return out


def _probe_regular_page(slug):
    """Check one fixed corpus probe without following any path component."""
    try:
        slug = sialib._canonical_corpus_slug(slug)
        info = sialib._source_path_identity(
            sialib.corpus_path(slug), os.O_RDONLY)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise BenchmarkRefusal(
            f"legacy tripwire probe could not be opened safely: {slug}") \
            from exc
    if not stat.S_ISREG(info.st_mode) \
            or info.st_size > MAX_BENCH_SOURCE_PAGE_BYTES:
        raise BenchmarkRefusal(
            f"legacy tripwire probe is not a bounded regular page: {slug}")
    return True


def _probe_organ_directory(relative):
    """Answer one existential organ probe within a fixed directory page.

    Finding a regular Markdown page is a positive observation.  Reaching the
    directory ceiling without finding one is not evidence of absence, so that
    case refuses instead of silently disabling a benchmark question.
    """
    directory = os.path.join(CORPUS, relative)
    try:
        entries, complete, _inspected, _next = \
            sialib._bounded_source_entries(directory, {})
    except FileNotFoundError:
        return False
    except (OSError, RuntimeError, ValueError) as exc:
        raise BenchmarkRefusal(
            f"legacy tripwire organ probe refused: {relative}") from exc
    for entry in entries:
        if stat.S_ISREG(entry["mode"]) and entry["name"].endswith(".md"):
            return True
    if not complete:
        raise BenchmarkRefusal(
            f"legacy tripwire organ probe exceeded its directory bound: "
            f"{relative}")
    return False


def build_questions():
    """Build the legacy hand-authored slug-family probe set.

    Corpus presence only decides whether a topical probe is eligible.  The
    accepted slug fragments are heuristic relevance labels; they are not
    answer-bearing ground truth.
    """
    def organ_has(o):
        refusals = []
        for relative in (f"events/{o}", f"epochs/{o}"):
            try:
                if _probe_organ_directory(relative):
                    return True
            except BenchmarkRefusal as exc:
                refusals.append(exc)
        if refusals:
            # A completed positive sibling is enough for this existential
            # probe. Without one, an incomplete sibling cannot be laundered
            # into a negative answer.
            raise refusals[0]
        return False
    present = []
    def add(q, accepts):
        present.append((q, accepts))
    if organ_has("sekhmet"):
        add("when did sekhmet restart wireplumber",
            ["events/sekhmet", "epochs/sekhmet"])
        add("sekhmet weekly activity summary", ["epochs/sekhmet"])
    if organ_has("jackal"):
        add("what did jackal refuse to compute",
            ["events/jackal", "refusal"])
        add("unverified JACKAL result records observed on this machine",
            ["events/jackal"])
    if organ_has("pacman"):
        add("which packages were installed or upgraded",
            ["events/pacman", "epochs/pacman", "packages/"])
    if organ_has("worldline"):
        add("what did worldline collapse", ["events/worldline", "collapse"])
    if organ_has("claude-code"):
        add("agent coding sessions on this machine",
            ["events/claude-code", "organs/claude-code"])
    if organ_has("agents"):
        add("claude token usage and rate limits", ["events/agents"])
    if organ_has("journal"):
        add("hyprland dialog coredumps", ["events/journal", "crash"])
    if organ_has("projects"):
        add("git commits to the jackal project",
            ["events/projects", "projects/jackal"])
    if _probe_regular_page("organs/custos"):
        add("what does the custos organ do", ["organs/custos",
                                             "events/custos",
                                             "epochs/custos"])
    if _probe_regular_page("sia/cortex"):
        add("what is sia the omarchy brain", ["sia/cortex"])
    add("which evidence chain failed verification", ["integrity"])
    absent = [
        "when did the nginx web server crash",
        "postgres replication lag incidents",
        "bluetooth pairing failures yesterday",
        "kernel panic in the gpu driver",
        "kubernetes cluster failover events",
        "email from the tax office about invoices",
    ]
    return present, absent


def slug_family_rank(ranked_slugs, accepts, k=5):
    for i, s in enumerate(ranked_slugs[:k]):
        if any(a in s for a in accepts):
            return i + 1
    return None


def run_quick(max_q=8, day=None):
    """Run the nightly heuristic slug-retrieval drift tripwire.

    This deterministic date-seeded sample measures only whether an accepted
    slug family appears near the top of retrieval.  It does not run a reader,
    score answers, or establish that synthetic-negative prompts are absent
    from memory.
    """
    import hashlib
    day = day or sialib.today()
    present, _ = build_questions()
    if not present:
        return None
    # date-seeded stable sample: rank questions by SHA-256(day || question)
    keyed = sorted(present, key=lambda qa: hashlib.sha256(
        (day + qa[0]).encode()).hexdigest())[:max_q]
    graph = sialib.read_json(sialib.GRAPH_PATH, None)
    mind = siamind.load_mind()
    out = {
        "schema": LEGACY_TRIPWIRE_SCHEMA,
        "kind": "heuristic-slug-retrieval-drift-tripwire",
        "date": day,
        "probe_count": len(keyed),
        "non_claims": list(LEGACY_TRIPWIRE_NON_CLAIMS),
    }
    for name in ("keyword", "blend"):
        ranks = []
        for q, accepts in keyed:
            if name == "keyword":
                res = [(s, sc) for s, sc, _ in _dedupe(_engine(["search", q]))]
            else:
                dn = _dedupe(_engine(["query", q]))
                res = siamind.ppr_rerank(
                    graph, [(s, sc) for s, sc, _ in dn],
                    mind=mind) if dn else []
            ranks.append(slug_family_rank([s for s, _ in res], accepts))
        out[f"slug_match_at_5_{name}"] = round(
            sum(1 for rank in ranks if rank) / len(keyed), 3)
        out[f"reciprocal_slug_rank_{name}"] = round(
            sum(1 / rank for rank in ranks if rank) / len(keyed), 3)
    return out


def run_legacy():
    present, absent = build_questions()
    graph = sialib.read_json(sialib.GRAPH_PATH, None)
    mind = siamind.load_mind()
    systems = ["keyword", "dense", "blend"]
    per = {s: {"ranks": [], "negative_top": [], "negative_crossings": 0,
               "conditioned_top": []} for s in systems}

    for q, accepts in present:
        kw = _dedupe(_engine(["search", q]))
        dn = _dedupe(_engine(["query", q]))
        bl = siamind.ppr_rerank(graph, [(s, sc) for s, sc, _ in dn],
                                mind=mind) if dn else []
        for name, res in (("keyword", [(s, sc) for s, sc, _ in kw]),
                          ("dense", [(s, sc) for s, sc, _ in dn]),
                          ("blend", bl)):
            slugs = [s for s, _ in res]
            per[name]["ranks"].append(slug_family_rank(slugs, accepts))
            if res:
                per[name]["conditioned_top"].append(res[0][1])

    # Heuristic drift threshold: compare corpus-conditioned and synthetic-
    # negative top-score distributions.  This is not an abstention policy.
    tau = {name: None for name in systems}

    for q in absent:
        kw = _dedupe(_engine(["search", q]))
        dn = _dedupe(_engine(["query", q]))
        bl = siamind.ppr_rerank(graph, [(s, sc) for s, sc, _ in dn],
                                mind=mind) if dn else []
        for name, res in (("keyword", [(s, sc) for s, sc, _ in kw]),
                          ("dense", [(s, sc) for s, sc, _ in dn]),
                          ("blend", bl)):
            per[name]["negative_top"].append(res[0][1] if res else 0.0)

    # threshold from MEASURED separability of the two score distributions
    sep = {}
    for name in systems:
        pres = sorted(per[name]["conditioned_top"])
        absv = per[name]["negative_top"]
        p10 = pres[max(0, int(0.1 * len(pres)))] if pres else 0.0
        amax = max(absv) if absv else 0.0
        tau[name] = (p10 + amax) / 2 if amax < p10 else p10
        per[name]["negative_crossings"] = sum(
            1 for t in absv if t >= tau[name])
        per[name]["conditioned_below_threshold"] = sum(
            1 for t in pres if t < tau[name])
        sep[name] = (f"conditioned p10={p10:.2f} med="
                     f"{statistics.median(pres):.2f} · synthetic-negative max="
                     f"{amax:.2f} med={statistics.median(absv):.2f} · "
                     + ("separable" if amax < p10 else "OVERLAP — "
                        "threshold drift discriminator not separable"))

    n, na = len(present), len(absent)
    lines = [f"# SIA legacy slug-retrieval drift tripwire · {sialib.today()}",
             "",
             f"{n} hand-authored corpus-conditioned probes use accepted "
             f"slug-family fragments as heuristic relevance labels; {na} "
             f"synthetic-negative prompts probe score overlap. Neither set "
             f"is answer-bearing ground truth. The heuristic threshold per "
             f"system is the midpoint of conditioned-p10 and "
             f"synthetic-negative-max when the distributions separate.",
             "",
             "| system | slug match@1 | slug match@5 | reciprocal slug rank "
             "| synthetic-negative threshold crossings "
             "| conditioned probes below threshold | heuristic τ |",
             "|---|---|---|---|---|---|---|"]
    for name in systems:
        ranks = per[name]["ranks"]
        match1 = sum(1 for rank in ranks if rank == 1) / n
        match5 = sum(1 for rank in ranks if rank) / n
        reciprocal = sum(1 / rank for rank in ranks if rank) / n
        lines.append(
                     f"| {name} | {match1:.2f} | {match5:.2f} "
                     f"| {reciprocal:.2f} "
                     f"| {per[name]['negative_crossings']}/{na} "
                     f"| {per[name]['conditioned_below_threshold']}/{n} "
                     f"| {tau[name]:.2f} |")
    lines += [""] + [f"- {name}: {sep[name]}" for name in systems]
    lines += ["",
              "No accepted slug-family match in the top retrieval window:"]
    for name in systems:
        misses = [present[i][0] for i, r in enumerate(per[name]["ranks"])
                  if not r]
        lines.append(f"- {name}: " + ("; ".join(misses) if misses
                                      else "none"))
    lines += ["", "Boundaries:"]
    lines += [f"- {item}" for item in LEGACY_TRIPWIRE_NON_CLAIMS]
    report = "\n".join(lines)
    out = os.path.expanduser(
        f"~/.local/share/sia/research/bench-{sialib.today()}.md")
    with open(out, "w") as f:
        f.write(report + "\n")
    print(report)
    print(f"\nsaved → {out}")
    return report


# ================================================================= ledger QA

def _u64be(value):
    return int(value).to_bytes(8, "big")


def _atext(value):
    raw = value.encode("utf-8")
    return _u64be(len(raw)) + raw


def _entry_hash(row):
    """attest-entry-v1 hash for a strict nine-column row."""
    seq, stamp, action, arg1, arg2, content_hash, size, prev, _sig = row
    payload = bytearray(b"attest-entry-v1")
    payload += _u64be(seq)
    payload += _atext(stamp)
    payload += _atext(action)
    payload += _atext(arg1)
    payload += _atext(arg2)
    payload += bytes.fromhex(content_hash)
    payload += _u64be(size)
    payload += bytes.fromhex(prev)
    return hashlib.sha256(bytes(payload)).hexdigest()


def _strict_attest_rows(text_data):
    """Parse the complete attest-ledger v1 row/chain grammar."""
    # The keeper's signed wire format has exactly one record separator:
    # literal LF.  ``str.splitlines`` would reinterpret signed U+0085,
    # U+2028, and U+2029 field bytes as phantom record boundaries.
    if not text_data or not text_data.endswith("\n"):
        raise ValueError("empty ledger or non-canonical torn row")
    lines = text_data[:-1].split("\n")
    if any(not line for line in lines):
        raise ValueError("empty ledger or non-canonical blank line")
    rows = [line.split("\t") for line in lines]
    expected_seq = 0
    expected_prev = hashlib.sha256(b"attest-genesis-v1").hexdigest()
    for row in rows:
        if len(row) != 9:
            raise ValueError("non-nine-column ledger row")
        seq, stamp, action, _arg1, _arg2, content_hash, size, prev, sig = row
        if seq != str(expected_seq):
            raise ValueError("non-canonical or discontinuous sequence")
        if _date_from_stamp(stamp) is None:
            raise ValueError("invalid UTC timestamp")
        if not action:
            raise ValueError("empty action")
        if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
            raise ValueError("invalid content hash")
        if not re.fullmatch(r"(?:0|[1-9][0-9]*)", size):
            raise ValueError("invalid canonical size")
        if not re.fullmatch(r"[0-9a-f]{64}", prev) \
                or prev != expected_prev:
            raise ValueError("invalid or discontinuous predecessor")
        if not re.fullmatch(r"[0-9a-f]{128}", sig):
            raise ValueError("invalid signature spelling")
        expected_prev = _entry_hash(row)
        expected_seq += 1
    return rows, expected_prev


def _strict_custos_rows(text_data):
    """Parse Custos' legacy signed-line hash-chain grammar.

    Custos signs nine tab-separated fields with a canonical Unix stamp. Its
    predecessor and public head are SHA-256 over the complete preceding signed
    line bytes, excluding the newline; they are not attest-entry-v1 hashes.
    """
    if "\r" in text_data:
        raise ValueError("non-canonical Custos line ending")
    lines = text_data.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or any(not line for line in lines):
        raise ValueError("empty ledger or non-canonical blank line")

    rows, entry_hashes = [], []
    expected_seq = 0
    expected_prev = hashlib.sha256(b"custos-genesis-v1").hexdigest()
    for line in lines:
        row = line.split("\t")
        if len(row) != 9:
            raise ValueError("non-nine-column Custos ledger row")
        seq, stamp, action, _src, _dst, content_hash, size, prev, sig = row
        if seq != str(expected_seq):
            raise ValueError("non-canonical or discontinuous Custos sequence")
        if not re.fullmatch(r"(?:0|[1-9][0-9]*)", stamp) \
                or _date_from_stamp(stamp) is None:
            raise ValueError("invalid canonical Custos Unix timestamp")
        if not action:
            raise ValueError("empty Custos action")
        if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
            raise ValueError("invalid Custos content hash")
        if not re.fullmatch(r"(?:0|[1-9][0-9]*)", size):
            raise ValueError("invalid canonical Custos size")
        if not re.fullmatch(r"[0-9a-f]{64}", prev) \
                or prev != expected_prev:
            raise ValueError("invalid or discontinuous Custos predecessor")
        if not re.fullmatch(r"[0-9a-f]{128}", sig):
            raise ValueError("invalid Custos signature spelling")
        entry_hash = hashlib.sha256(line.encode("utf-8")).hexdigest()
        rows.append(row)
        entry_hashes.append(entry_hash)
        expected_prev = entry_hash
        expected_seq += 1
    return rows, expected_prev, entry_hashes


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def _sha_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_token(info):
    """Observed identity and mutation-sensitive metadata for one open file."""
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _read_nofollow_regular(
        path, max_bytes=MAX_BENCH_FILE_BYTES, *, private=False):
    """Read one regular file without following any path-component symlink.

    The descriptor is checked before and after the read so an in-place change
    observed during the read is refused. The returned token is compared with a
    separately opened post-verification observation by ``_snapshot_chains``.
    """
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) \
            or max_bytes <= 0 or max_bytes > MAX_BENCH_AGGREGATE_BYTES:
        raise ValueError("benchmark file byte ceiling is invalid")
    absolute = os.path.abspath(path)
    parts = [part for part in absolute.split(os.sep) if part]
    if not parts:
        raise OSError("file path has no regular-file component")
    directory_flags = (os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
                       | os.O_DIRECTORY)
    directory_fd = os.open(os.sep, directory_flags)
    fd = None
    stream = None
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        fd = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                     dir_fd=directory_fd)
        stream = os.fdopen(fd, "rb")
        fd = None
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise OSError("not a regular file")
        if before.st_size > max_bytes:
            raise OSError("file exceeds its complete-snapshot byte ceiling")
        if private and (before.st_uid != os.geteuid()
                        or stat.S_IMODE(before.st_mode) & 0o077):
            raise OSError("private benchmark artifact is not owner-private")
        data = stream.read(max_bytes + 1)
        after = os.fstat(stream.fileno())
        if len(data) > max_bytes:
            raise OSError("file exceeds its complete-snapshot byte ceiling")
        if _file_token(before) != _file_token(after):
            raise OSError("file changed while it was read")
        rebound = os.stat(
            parts[-1], dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(rebound.st_mode) \
                or _file_token(rebound) != _file_token(after):
            raise OSError("file path changed while it was read")
        return data, _file_token(after), hashlib.sha256(data).hexdigest()
    finally:
        if stream is not None:
            stream.close()
        elif fd is not None:
            os.close(fd)
        os.close(directory_fd)


def _snapshot_chains(chain_registry=None, names=None, timeout=60):
    """Verify and observe stable signed-ledger snapshots.

    Each chain is checked with its registered keeper. Ledger and verifier
    files are opened without following symlinks, then their bytes, inode, and
    mutation-sensitive metadata are compared across verification. This closes
    ordinary replacement races; the manifest retains the precise same-user
    in-place ABA non-claim. A refusal/failure is never parsed as weaker input.
    """
    registry = chain_registry if chain_registry is not None \
        else sialib._chain_cmds()
    wanted = set(registry) if names is None else set(names)
    snapshots, diagnostics = [], []
    aggregate_bytes = 0
    aggregate_rows = 0
    for name in sorted(wanted - set(registry)):
        diagnostics.append({"chain": name, "status": "refused",
                            "reason": "unknown-requested-chain"})
    for name in sorted(registry):
        if name not in wanted:
            continue
        diag = {"chain": name, "status": "refused"}
        binding = registry[name]
        if not isinstance(binding, (list, tuple)) or len(binding) != 3:
            diag["reason"] = "invalid-chain-binding"
            diagnostics.append(diag)
            continue
        ledger, tool, command = binding
        if isinstance(command, (list, tuple)) and command \
                and command[0] == sialib.INVALID_CHAIN_SENTINEL:
            diag["reason"] = "invalid-chain-config"
            diag["detail"] = command[1] if len(command) > 1 \
                else "configured chain is invalid"
            diagnostics.append(diag)
            continue
        binding_error = sialib._chain_verifier_binding_error(tool, command)
        if binding_error:
            diag["reason"] = "invalid-verifier-binding"
            diag["detail"] = binding_error
            diagnostics.append(diag)
            continue
        try:
            before, before_token, before_digest = \
                _read_nofollow_regular(
                    ledger, max_bytes=MAX_BENCH_LEDGER_BYTES)
        except Exception as exc:
            diag["reason"] = "ledger-open-refused"
            diag["detail"] = str(exc)[:160]
            diagnostics.append(diag)
            continue
        try:
            _verifier_before, verifier_before_token, verifier_before_digest = \
                _read_nofollow_regular(
                    tool, max_bytes=MAX_BENCH_VERIFIER_BYTES)
        except Exception as exc:
            diag["reason"] = "keeper-verifier-open-refused"
            diag["detail"] = str(exc)[:160]
            diagnostics.append(diag)
            continue
        try:
            # Keeper output is not part of the verification product.  A
            # configured verifier may legitimately be verbose, so never let
            # its stdout or stderr accumulate in parent-owned pipes.
            proc = sialib._run_bounded_text_process(
                command, env=None, timeout=timeout, cwd=None,
                label="benchmark chain verifier",
                output_limit=sialib.MAX_CONFIG_BYTES)
        except Exception as exc:
            diag["reason"] = "verification-error"
            diag["detail"] = str(exc)[:160]
            diagnostics.append(diag)
            continue
        try:
            after, after_token, after_digest = \
                _read_nofollow_regular(
                    ledger, max_bytes=MAX_BENCH_LEDGER_BYTES)
        except Exception as exc:
            diag["reason"] = "ledger-post-verification-open-refused"
            diag["detail"] = str(exc)[:160]
            diagnostics.append(diag)
            continue
        try:
            _verifier_after, verifier_after_token, verifier_after_digest = \
                _read_nofollow_regular(
                    tool, max_bytes=MAX_BENCH_VERIFIER_BYTES)
        except Exception as exc:
            diag["reason"] = "keeper-verifier-post-check-refused"
            diag["detail"] = str(exc)[:160]
            diagnostics.append(diag)
            continue
        if before_digest != after_digest or before_token != after_token:
            diag["reason"] = "ledger-changed-during-verification"
            diagnostics.append(diag)
            continue
        if verifier_before_digest != verifier_after_digest \
                or verifier_before_token != verifier_after_token:
            diag["reason"] = "keeper-verifier-changed-during-verification"
            diagnostics.append(diag)
            continue
        if proc.returncode != 0:
            diag["reason"] = "keeper-rejected"
            diag["detail"] = (
                f"keeper verifier exited with status {proc.returncode}")
            diagnostics.append(diag)
            continue
        del before, _verifier_before
        candidate_bytes = len(after) + len(_verifier_after)
        if aggregate_bytes + candidate_bytes > MAX_BENCH_AGGREGATE_BYTES:
            diag["reason"] = "aggregate-snapshot-capacity"
            diagnostics.append(diag)
            continue
        chain_format = CUSTOS_CHAIN_FORMAT if name == "custos" \
            else ATTEST_CHAIN_FORMAT
        diag["chain_format"] = chain_format
        try:
            text_data = after.decode("utf-8")
            # ``_chain_cmds`` reserves the built-in Custos name, so it is the
            # closed format discriminator. Every custom chain remains on the
            # strict attest path even when its verifier is permissive.
            if name == "custos":
                raw_rows, head, entry_hashes = \
                    _strict_custos_rows(text_data)
            else:
                raw_rows, head = _strict_attest_rows(text_data)
                entry_hashes = [_entry_hash(row) for row in raw_rows]
        except Exception as exc:
            diag["reason"] = "strict-row-parse-refused"
            diag["detail"] = str(exc)[:160]
            diagnostics.append(diag)
            continue
        if len(raw_rows) > MAX_BENCH_ROWS \
                or aggregate_rows + len(raw_rows) > MAX_BENCH_ROWS:
            diag["reason"] = "ledger-row-capacity"
            diagnostics.append(diag)
            continue
        aggregate_bytes += candidate_bytes
        aggregate_rows += len(raw_rows)
        snap = {
            "chain": name,
            "chain_format": chain_format,
            "rows": raw_rows,
            "entry_hashes": entry_hashes,
            "ledger_sha256": after_digest,
            "head": head,
            "row_count": len(raw_rows),
            "verifier": os.path.basename(tool),
            "verifier_sha256": verifier_after_digest,
        }
        snapshots.append(snap)
        diagnostics.append({"chain": name, "status": "verified",
                            "chain_format": chain_format,
                            "rows": len(raw_rows), "head": head,
                            "ledger_sha256": after_digest,
                            "verifier_sha256": verifier_after_digest})
    return snapshots, diagnostics


def _date_from_stamp(stamp):
    try:
        return datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ") \
            .date().isoformat()
    except ValueError:
        try:
            return datetime.datetime.fromtimestamp(
                int(stamp), datetime.timezone.utc).date().isoformat()
        except (ValueError, OverflowError):
            return None


def _safe_field(value):
    value = str(value)
    # Signed text remains exact in its ledger/hash provenance, but controls,
    # bidi format characters, surrogates, and unassigned/noncharacters are not
    # safe public-question or XML text. Do not reinterpret them into a benign
    # display spelling at this boundary.
    if any(unicodedata.category(char) in {"Cc", "Cf", "Cs", "Cn"}
           for char in value):
        return None
    value = " ".join(value.split())
    if not value or value == "-" or len(value) > 120:
        return None
    if any(p.search(value) for p in getattr(sialib, "REDACT_PATTERNS", ())):
        return None
    return value


def _label_for(row):
    for value in (row[3], row[4]):
        value = _safe_field(value)
        if value:
            base = os.path.basename(value.rstrip("/"))
            return base or value
    return None


def _public_leak_view(value):
    """Canonicalize common reversible encodings before leak comparison."""
    current = unicodedata.normalize("NFKC", str(value)).casefold()
    seen = set()
    while current not in seen:
        seen.add(current)
        decoded = html.unescape(urllib.parse.unquote(current))
        decoded = "".join(
            char for char in decoded
            if unicodedata.category(char) not in {"Cc", "Cf", "Cs"})
        decoded = unicodedata.normalize("NFKC", decoded).casefold()
        if decoded == current:
            break
        current = decoded
    return current


def _public_question_key(value):
    """Consumer-equivalent public wording used for conflicts and IDs."""
    return " ".join(_public_leak_view(value).split())


def _question_id(payload):
    identity = dict(payload)
    if isinstance(identity.get("question"), str):
        identity["question"] = _public_question_key(identity["question"])
    return hashlib.sha256(_canonical(identity).encode("utf-8")).hexdigest()[:20]


def _normalize_witness_excerpt(value):
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _make_question(category, question, answer, sources, provenance,
                   answer_witness=None):
    # Public IDs bind only the consumer-canonical public wording. Category,
    # sources, provenance, and answers are private answer-key fields; none may
    # become a side channel in an ostensibly answer-independent identifier.
    public_identity = {"question": question}
    row = {"id": _question_id(public_identity), "category": category,
           **public_identity,
           "sources": sorted(sources), "provenance": provenance,
           "answer": answer}
    if answer_witness is not None:
        row["answer_witness"] = answer_witness
    return row


def _signed_result_question(chain, action, label):
    """One public template shared by witnessed and absent subject pairs."""
    return (f"What result did signed {chain} record for `{action}` "
            f"concerning `{label}`?")


def _answer_visible(question, answer):
    """Whether canonical answer tokens appear contiguously in public text."""
    if answer == ABSTAIN:
        return False
    question = _public_leak_view(question)
    answer = _public_leak_view(answer)
    answer_tokens = re.findall(r"[a-z0-9]+", str(answer).casefold())
    question_tokens = re.findall(r"[a-z0-9]+", str(question).casefold())
    if not answer_tokens:
        return bool(str(answer).strip()) and \
            str(answer).casefold() in str(question).casefold()
    width = len(answer_tokens)
    return any(question_tokens[index:index + width] == answer_tokens
               for index in range(len(question_tokens) - width + 1))


def _audit_questions(questions, private_source_slugs=()):
    """Drop public-answer leakage, conflicting wording, and duplicate IDs."""
    grouped = {}
    for question in questions:
        key = _public_question_key(question["question"])
        grouped.setdefault(key, []).append(question)
    conflicting = {
        key for key, rows in grouped.items()
        if len({str(row["answer"]) for row in rows}) > 1
    }
    temporal_answers = {
        str(row["answer"])
        for row in questions
        if row.get("category") == "temporal-reasoning"
        and row.get("answer") != ABSTAIN
    }
    source_slugs = {
        slug for slug in private_source_slugs
        if isinstance(slug, str) and slug
    }
    kept, seen_ids = [], set()
    exclusions = {"answer_visible": 0, "conflicting_wording": 0,
                  "duplicate_public_id": 0,
                  "temporal_answer_visible": 0,
                  "source_slug_visible": 0}
    for question in questions:
        key = _public_question_key(question["question"])
        if key in conflicting:
            exclusions["conflicting_wording"] += 1
            continue
        if _answer_visible(question["question"], question["answer"]):
            exclusions["answer_visible"] += 1
            continue
        # A date withheld from one temporal question must not reappear in a
        # different public question (for example, the old per-sequence prompt
        # exposed the signed timestamp). Audit across the whole generated
        # population, not only against each row's own answer.
        if any(_answer_visible(question["question"], answer)
               for answer in temporal_answers):
            exclusions["temporal_answer_visible"] += 1
            continue
        if any(_answer_visible(question["question"], slug)
               for slug in source_slugs):
            exclusions["source_slug_visible"] += 1
            continue
        if question["id"] in seen_ids:
            exclusions["duplicate_public_id"] += 1
            continue
        seen_ids.add(question["id"])
        kept.append(question)
    return kept, exclusions


def _cap_questions(questions):
    grouped = {}
    for q in questions:
        grouped.setdefault(q["category"], []).append(q)
    out = []
    for category in sorted(grouped):
        out.extend(sorted(grouped[category],
                          key=lambda q: hashlib.sha256(
                              (category + q["id"]).encode()).hexdigest())
                   [:MAX_PER_CATEGORY])
    return out


def _append_bounded_question(questions, question):
    if len(questions) >= MAX_BENCH_CANDIDATE_QUESTIONS:
        raise BenchmarkRefusal(
            "benchmark candidate-question population exceeds its ceiling")
    questions.append(question)


class _WitnessOpenRefusal(RuntimeError):
    """An authoritative corpus path could not be opened safely."""

    def __init__(self, reason, relative, detail):
        super().__init__(detail)
        self.reason = reason
        self.relative = relative
        self.detail = detail


class _CorpusWitnessResolver:
    """Resolve signed rows to exact bounded event or epoch witnesses."""

    def __init__(self, corpus, wanted_by_day):
        self.corpus = os.path.abspath(corpus)
        self.wanted_by_day = wanted_by_day
        self.page_cache = {}
        self.directory_cache = {}
        self.day_cache = {}
        self.epoch_cache = {}
        self.witness_files = {}
        self.aggregate_bytes = 0

    @staticmethod
    def _relative(relative):
        if not isinstance(relative, str) or os.path.isabs(relative) \
                or any(part in ("", ".", "..")
                       for part in relative.split("/")):
            raise ValueError("benchmark witness path is invalid")
        return relative

    def _consume(self, size):
        self.aggregate_bytes += size
        if self.aggregate_bytes > MAX_BENCH_SOURCE_BYTES:
            raise BenchmarkRefusal(
                "benchmark source-page bytes exceed their aggregate ceiling")

    def _read_page(self, relative):
        relative = self._relative(relative)
        if not relative.endswith(".md"):
            raise ValueError("benchmark source page path is invalid")
        cached = self.page_cache.get(relative)
        if cached is not None:
            return cached
        if len(self.page_cache) >= MAX_BENCH_SOURCE_PAGES:
            raise BenchmarkRefusal(
                "benchmark source-page population exceeds its ceiling")
        try:
            raw, _token, digest = _read_nofollow_regular(
                os.path.join(self.corpus, *relative.split("/")),
                max_bytes=MAX_BENCH_SOURCE_PAGE_BYTES)
            text = raw.decode("utf-8", errors="strict")
        except Exception as exc:
            if isinstance(exc, BenchmarkRefusal):
                raise
            raise _WitnessOpenRefusal(
                "corpus-page-open-refused", relative,
                str(exc)[:160]) from exc
        self._consume(len(raw))
        page = {"slug": relative[:-3], "sha256": digest,
                "lineage_sha256": hashlib.sha256(
                    relative.encode("utf-8") + b"\0" + raw).hexdigest(),
                "size": len(raw), "text": text}
        self.page_cache[relative] = page
        return page

    def _read_index(self, relative):
        relative = self._relative(relative)
        cached = self.witness_files.get(relative)
        if cached is not None:
            return cached
        if len(self.witness_files) >= MAX_BENCH_ROWS:
            raise BenchmarkRefusal(
                "benchmark witness-file population exceeds its ceiling")
        try:
            raw, _token, digest = _read_nofollow_regular(
                os.path.join(self.corpus, *relative.split("/")),
                max_bytes=sialib.MAX_EVENT_INDEX_BYTES)
        except FileNotFoundError:
            return None
        except Exception as exc:
            raise _WitnessOpenRefusal(
                "event-index-open-refused", relative,
                str(exc)[:160]) from exc
        self._consume(len(raw))
        artifact = {"path": relative, "sha256": digest,
                    "size": len(raw), "kind": "event-index", "raw": raw}
        return artifact

    @staticmethod
    def _event_page_lines(page, organ, date, part):
        match = sialib.FM_RE.match(page["text"])
        if match is None:
            return None, "event-page-frontmatter-missing"
        frontmatter = match.group(1)
        if re.findall(r"^type:\s*(.*?)\s*$", frontmatter, re.M) \
                != ["event-day"] \
                or re.findall(r"^date:\s*(.*?)\s*$", frontmatter, re.M) \
                != [date]:
            return None, "event-page-identity-invalid"
        shards = re.findall(r"^sia_shard:\s*(.*?)\s*$", frontmatter, re.M)
        if shards and shards != [str(part)]:
            return None, "event-page-shard-invalid"
        log_part = page["text"][match.end():].split("## Timeline", 1)[0]
        if "## Log" in log_part:
            log_part = log_part.split("## Log", 1)[1]
        bullets = [line for line in log_part.splitlines()
                   if line.startswith("- ")]
        if len(bullets) > sialib.MAX_EVENT_BULLETS:
            return None, "event-page-bullet-capacity"
        return bullets, None

    def _load_day(self, organ, date):
        key = (organ, date)
        cached = self.day_cache.get(key)
        if cached is not None:
            return cached
        wanted = self.wanted_by_day.get(key, set())
        result = {"matches": {}, "pages": {}, "error": None}
        directory = os.path.join(self.corpus, "events", organ)
        entries = self.directory_cache.get(organ)
        if entries is None:
            try:
                entries = sialib._bounded_event_directory_snapshot(directory)
            except FileNotFoundError:
                entries = []
            except Exception as exc:
                raise _WitnessOpenRefusal(
                    "event-directory-open-refused", f"events/{organ}",
                    str(exc)[:160]) from exc
            self.directory_cache[organ] = entries
        base_name = date + ".md"
        part_re = re.compile(
            rf"^{re.escape(date)}-part-([2-9][0-9]*)\.md$")
        parts = {}
        for entry in entries:
            name = entry["name"]
            part = 1 if name == base_name else None
            match = part_re.fullmatch(name)
            if match is not None:
                part = int(match.group(1))
            if part is None:
                continue
            if not stat.S_ISREG(entry["mode"]):
                raise _WitnessOpenRefusal(
                    "corpus-page-open-refused",
                    f"events/{organ}/{name}",
                    "event shard is not a regular file")
            if part in parts:
                result["error"] = "event-shard-set-ambiguous"
                self.day_cache[key] = result
                return result
            parts[part] = name
        ordered = sorted(parts)
        if ordered and (len(ordered) > sialib.MAX_EVENT_SHARDS
                        or ordered[-1] > sialib.MAX_EVENT_SHARDS
                        or ordered[0] != 1
                        or any(part != position for position, part in
                               enumerate(ordered, start=1))):
            result["error"] = "event-shard-set-invalid"
            self.day_cache[key] = result
            return result
        for part in ordered:
            relative = f"events/{organ}/{parts[part]}"
            page = self._read_page(relative)
            result["pages"][relative] = page
            bullets, error = self._event_page_lines(
                page, organ, date, part)
            if error is not None:
                result["error"] = error
                self.day_cache[key] = result
                return result
            for line in bullets:
                marker = sialib.EVENT_MARKER_RE.fullmatch(line)
                if marker is None:
                    if "sia-event:" in line:
                        result["error"] = "event-marker-malformed"
                        self.day_cache[key] = result
                        return result
                    continue
                event_id = marker.group("id")
                if event_id not in wanted:
                    continue
                result["matches"].setdefault(event_id, []).append({
                    "line": line, "semantic_id": marker.group("semantic"),
                    "payload": marker.group("payload"), "page": page,
                    "relative": relative,
                })
        self.day_cache[key] = result
        return result

    def _load_epoch(self, slug):
        cached = self.epoch_cache.get(slug)
        if cached is not None:
            return cached
        page = self._read_page(slug + ".md")
        match = sialib.FM_RE.match(page["text"])
        if match is None:
            result = (None, "epoch-frontmatter-missing")
            self.epoch_cache[slug] = result
            return result
        frontmatter = match.group(1)
        if re.findall(r"^type:\s*(.*?)\s*$", frontmatter, re.M) != ["epoch"]:
            result = (None, "epoch-identity-invalid")
            self.epoch_cache[slug] = result
            return result

        def field(name):
            values = re.findall(
                rf"^{re.escape(name)}: (.*)$", frontmatter, re.M)
            if len(values) != 1:
                raise ValueError("epoch lineage field is missing or duplicated")
            try:
                return json.loads(values[0])
            except (UnicodeError, ValueError, RecursionError) as exc:
                raise ValueError("epoch lineage field is malformed") from exc

        try:
            sources = field("sia_sources")
            dates = field("sia_dates")
            manifest = field("sia_source_manifest")
            if not isinstance(sources, list) \
                    or len(sources) != len(set(sources)) \
                    or any(not isinstance(value, str)
                           or re.fullmatch(r"[0-9a-f]{64}", value) is None
                           for value in sources) \
                    or not isinstance(dates, list) \
                    or dates != sorted(set(dates)) \
                    or any(not isinstance(value, str)
                           or re.fullmatch(
                               r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
                           is None for value in dates):
                raise ValueError("epoch lineage fields are invalid")
            for value in dates:
                if datetime.date.fromisoformat(value).isoformat() != value:
                    raise ValueError("epoch date lineage is invalid")
            canonical = sialib._canonical_epoch_source_manifest(
                manifest, slug, set(sources))
            if canonical != manifest:
                raise ValueError("epoch source manifest is not canonical")
            day_counts = re.findall(
                r"Consolidated from ([0-9]+) day-memories", page["text"])
            if day_counts != [str(len(dates))]:
                raise ValueError("epoch day count conflicts with lineage")
        except Exception:
            result = (None, "epoch-lineage-invalid")
            self.epoch_cache[slug] = result
            return result
        result = ({"page": page, "sources": sources, "dates": dates,
                   "manifest": manifest}, None)
        self.epoch_cache[slug] = result
        return result

    def _index_witness(self, event, event_id, semantic_id, payload,
                       exact_line, day, live_pages):
        relative = sialib._event_index_relative(
            event.organ, event_id).replace(os.sep, "/")
        artifact = self._read_index(relative)
        if artifact is None:
            return None, "event-witness-missing"
        try:
            try:
                entry = json.loads(
                    artifact["raw"].decode("utf-8", errors="strict"))
            except (UnicodeError, ValueError, RecursionError) as exc:
                raise ValueError("event index JSON is malformed") from exc
            entry = sialib._canonical_event_index_entry(entry)
            if artifact["raw"] != sialib._event_index_encoded(entry) \
                    or entry["organ"] != event.organ \
                    or entry["event_id"] != event_id \
                    or entry["semantic_id"] != semantic_id \
                    or entry["payload_sha256"] != \
                       sialib._event_payload_digest(payload):
                raise ValueError("event index does not bind projected event")
            source_organ, source_date, _part = sialib._event_source_parts(
                entry["source_rel"])
            if source_organ != event.organ or source_date != day:
                raise ValueError("event index source identity conflicts")
            live_source = live_pages.get(entry["source_rel"])
            if live_source is not None \
                    and live_source["lineage_sha256"] \
                    != entry["source_sha256"]:
                raise ValueError("live source conflicts with event index")
        except Exception:
            return None, "event-index-binding-invalid"
        epoch, error = self._load_epoch(entry["epoch_slug"])
        if error is not None:
            return None, error
        _source_organ, source_date, _source_part = \
            sialib._event_source_parts(entry["source_rel"])
        if source_date not in epoch["dates"] \
                or entry["source_sha256"] not in epoch["sources"] \
                or {"rel": entry["source_rel"],
                    "sha256": entry["source_sha256"]} \
                   not in epoch["manifest"]:
            return None, "epoch-lineage-invalid"
        self.witness_files[relative] = artifact
        descriptor = {key: artifact[key]
                      for key in ("path", "sha256", "size", "kind")}
        epoch_lines = set(epoch["page"]["text"].splitlines())
        exact_exemplar = f"- {day} ·{exact_line[1:]}"
        retained_excerpt = (exact_line if exact_line in epoch_lines else
                            exact_exemplar if exact_exemplar in epoch_lines
                            else None)
        return {"page": epoch["page"], "kind": "epoch-lineage",
                "index_file": descriptor,
                "projected_event_retained": retained_excerpt is not None,
                "retrieval_excerpt": retained_excerpt}, None

    def resolve(self, event):
        event_id = sialib.event_memory_identity(event)
        semantic_id = sialib.event_semantic_identity(event)
        day = event.ts.astimezone(datetime.timezone.utc).date().isoformat()
        exact_line, payload, _base_line = sialib._event_line(
            event, event_id, semantic_id)
        day_state = self._load_day(event.organ, day)
        if day_state["error"] is not None:
            return None, day_state["error"]
        matches = day_state["matches"].get(event_id, [])
        if len(matches) > 1:
            return None, "event-marker-ambiguous"
        if matches:
            match = matches[0]
            if match["semantic_id"] != semantic_id \
                    or match["line"] != exact_line:
                return None, "event-marker-binding-invalid"
            return {"page": match["page"], "kind": "live-event-marker",
                    "index_file": None,
                    "projected_event_retained": True,
                    "retrieval_excerpt": match["line"]}, None
        return self._index_witness(
            event, event_id, semantic_id, payload, exact_line, day,
            day_state["pages"])


def _assign_splits(questions, seed):
    """Stratify present/absent; fit policy only on calibration rows."""
    classes = {
        "present": [q for q in questions if q["answer"] != ABSTAIN],
        "absent": [q for q in questions if q["answer"] == ABSTAIN],
    }
    out = []
    for label, rows in classes.items():
        ordered = sorted(rows, key=lambda q: hashlib.sha256(
            (seed + "|" + label + "|" + q["id"]).encode()).hexdigest())
        if len(ordered) < 2:
            calibration_n = len(ordered)
        else:
            calibration_n = max(1, len(ordered) // CALIBRATION_DIVISOR)
            calibration_n = min(calibration_n, len(ordered) - 1)
        for index, q in enumerate(ordered):
            out.append({**q, "split": "calibration"
                        if index < calibration_n else "evaluation"})
    return sorted(out, key=lambda q: q["id"])


def build_ledger_dataset(corpus=None, chain_registry=None, chain_names=None):
    """Generate deterministic QA + private answer keys from signed rows.

    CLI callers hold ``sialib.corpus_owner`` while this snapshot is built.
    Every admitted source page is also opened no-follow and digest-bound so
    the returned bundle remains self-describing after the lease is released.
    """
    corpus = corpus or CORPUS
    snapshots, diagnostics = _snapshot_chains(
        chain_registry=chain_registry, names=chain_names)
    records, raw_pairs, raw_subjects, verified_latest_seq = [], {}, {}, {}
    projected = []
    coverage_counts = {}
    question_coverage_counts = {}

    def exclude(chain, reason):
        key = (chain, reason)
        coverage_counts[key] = coverage_counts.get(key, 0) + 1

    def exclude_question(chain, reason):
        key = (chain, reason)
        question_coverage_counts[key] = \
            question_coverage_counts.get(key, 0) + 1

    for snap in snapshots:
        chain = snap["chain"]
        raw_pairs[chain] = set()
        for row_index, row in enumerate(snap["rows"]):
            action = _safe_field(row[2])
            label = _label_for(row)
            if action and label:
                raw_pairs[chain].add((action, label))
            if not action or action.startswith("GENESIS:") or not label:
                continue
            subject = (chain, action, label)
            raw_subjects.setdefault(subject, []).append(row)
            sequence = int(row[0])
            verified_latest_seq[subject] = max(
                sequence, verified_latest_seq.get(subject, -1))
            day = _date_from_stamp(row[1])
            if not day:
                exclude(chain, "row-projection-date-invalid")
                continue
            if chain not in {"sia", "sekhmet", "custos", "aegis"}:
                exclude(chain, "undefined-corpus-projection")
                continue
            try:
                event = sialib.signed_ledger_event_projection(chain, row)
            except (TypeError, ValueError):
                exclude(chain, "row-projection-invalid")
                continue
            if event is None:
                exclude(chain, "row-not-projected-by-source-policy")
                continue
            event_day = event.ts.astimezone(
                datetime.timezone.utc).date().isoformat()
            if event_day != day:
                exclude(chain, "row-projection-date-conflict")
                continue
            projected.append({
                "chain": chain, "row": row, "action": action,
                "label": label, "value": _safe_field(row[4]),
                "day": day, "event": event,
                "entry_hash": snap["entry_hashes"][row_index],
                "snapshot": snap,
            })

    wanted_by_day = {}
    for candidate in projected:
        event = candidate["event"]
        key = (event.organ, candidate["day"])
        wanted_by_day.setdefault(key, set()).add(
            sialib.event_memory_identity(event))
    resolver = _CorpusWitnessResolver(corpus, wanted_by_day)
    unsafe_seen = set()
    for candidate in projected:
        chain = candidate["chain"]
        try:
            witness, reason = resolver.resolve(candidate["event"])
        except _WitnessOpenRefusal as exc:
            key = (chain, exc.reason, exc.relative)
            if key not in unsafe_seen:
                unsafe_seen.add(key)
                diagnostics.append({
                    "chain": chain, "status": "refused",
                    "reason": exc.reason, "detail": exc.detail,
                    "path": exc.relative,
                })
            exclude(chain, exc.reason)
            continue
        if reason is not None:
            exclude(chain, reason)
            continue
        event = candidate["event"]
        page = witness["page"]
        value = candidate["value"]
        projected_event_retained = witness["projected_event_retained"]
        # The supported attest projectors render arg2 as the terminal result
        # field in Event.summary. Requiring that exact terminal association
        # prevents a coincidental token elsewhere in the bound event from
        # becoming an answer witness. Custos intentionally projects custody
        # paths into a different summary grammar, so its raw arg2 is withheld.
        value_answer_retained = bool(
            value and candidate["chain"] != "custos"
            and projected_event_retained
            and event.summary.casefold().endswith(
                (" " + value).casefold()))
        records.append({
            **candidate,
            "slug": page["slug"],
            "source_page": {key: page[key]
                            for key in ("slug", "sha256", "size")},
            "event_id": sialib.event_memory_identity(event),
            "semantic_id": sialib.event_semantic_identity(event),
            "witness_kind": witness["kind"],
            "index_file": witness["index_file"],
            "projected_event_retained": projected_event_retained,
            "value_answer_retained": value_answer_retained,
            "retrieval_excerpt": witness["retrieval_excerpt"],
        })
        if value and not projected_event_retained:
            exclude_question(chain, "projected-event-answer-not-retained")
        elif value and not value_answer_retained:
            exclude_question(chain, "projected-value-answer-not-retained")

    witness_coverage = [
        {"chain": chain, "reason": reason, "excluded_rows": count}
        for (chain, reason), count in sorted(coverage_counts.items())]
    diagnostics.extend({"chain": item["chain"],
                        "status": "coverage-excluded",
                        "reason": item["reason"],
                        "rows": item["excluded_rows"]}
                       for item in witness_coverage)
    question_coverage = [
        {"chain": chain, "reason": reason, "affected_rows": count}
        for (chain, reason), count in sorted(
            question_coverage_counts.items())]
    diagnostics.extend({"chain": item["chain"],
                        "status": "coverage-excluded",
                        "scope": "answer-bearing-question",
                        "reason": item["reason"],
                        "rows": item["affected_rows"]}
                       for item in question_coverage)

    def witness_provenance(record):
        value = {"event_id": record["event_id"],
                 "semantic_id": record["semantic_id"],
                 "witness_kind": record["witness_kind"]}
        if record["index_file"] is not None:
            value["event_index"] = record["index_file"]
        return value

    def answer_witness(rows, match):
        excerpts = []
        for row in rows:
            excerpt = _normalize_witness_excerpt(row["retrieval_excerpt"])
            if excerpt is None:
                raise BenchmarkRefusal(
                    "answer-bearing question lacks a retrievable source excerpt")
            excerpts.append({
                "slug": row["slug"],
                "excerpt": excerpt,
                "sha256": _sha_text(excerpt),
            })
        excerpts = sorted(
            {(_canonical(item), item["sha256"]): item
             for item in excerpts}.values(),
            key=lambda item: (item["slug"], item["sha256"]))
        if not excerpts:
            raise BenchmarkRefusal(
                "answer-bearing question has no source excerpt witness")
        return {"schema": ANSWER_WITNESS_SCHEMA, "match": match,
                "excerpts": excerpts}

    questions = []
    for rec in records:
        value = rec["value"]
        if value and rec["value_answer_retained"] \
                and value.casefold() not in rec["label"].casefold():
            prov = {"chain": rec["chain"],
                    "chain_format": rec["snapshot"]["chain_format"],
                    "seq": rec["row"][0],
                    "entry_hash": rec["entry_hash"],
                    "ledger_head": rec["snapshot"]["head"],
                    "source_page": rec["source_page"],
                    **witness_provenance(rec)}
            _append_bounded_question(questions, _make_question(
                "information-extraction",
                f"At signed {rec['chain']} sequence {rec['row'][0]}, "
                f"what result did `{rec['action']}` "
                f"record for `{rec['label']}`?",
                value, [rec["slug"]], prov,
                answer_witness([rec], "any-excerpt")))

    by_subject = {}
    for rec in records:
        by_subject.setdefault((rec["chain"], rec["action"], rec["label"]), []) \
            .append(rec)
    for (chain, action, label), rows in sorted(by_subject.items()):
        # Pair this witnessed answer with the exact public wording used by
        # hard negatives. Admit it only when every occurrence survived the
        # source-page boundary and all occurrences establish one answer.
        raw_rows = raw_subjects[(chain, action, label)]
        values = {r["value"] for r in rows if r["value"]}
        source_slugs = sorted({r["slug"] for r in rows})
        if len(rows) == len(raw_rows) and len(values) == 1 \
                and len(source_slugs) <= TOP_K:
            value = next(iter(values))
            if all(r["value"] == value
                   and r["value_answer_retained"] for r in rows):
                _append_bounded_question(questions, _make_question(
                    "information-extraction",
                    _signed_result_question(chain, action, label),
                    value, source_slugs,
                    {"chain": chain,
                     "chain_format": rows[0]["snapshot"]["chain_format"],
                     "ledger_head": rows[0]["snapshot"]["head"],
                     "entry_hashes": [r["entry_hash"] for r in rows],
                     "selection": "exhaustive-single-value-subject",
                     "event_witnesses": [witness_provenance(r)
                                         for r in rows],
                     "source_pages": sorted(
                         {page["slug"]: page for page in
                          (r["source_page"] for r in rows)}.values(),
                         key=lambda page: page["slug"])},
                    answer_witness(rows, "any-excerpt")))

        latest = max(rows, key=lambda r: int(r["row"][0]))
        # “Most recent signed record” is a claim about the complete verified
        # snapshot, not merely its corpus-retained subset.  If the actual latest
        # row has no admitted digest-bound source page, withhold both temporal
        # and update questions instead of laundering an older row into latest.
        if int(latest["row"][0]) != verified_latest_seq[
                (chain, action, label)]:
            continue
        # A row retained only in an external event-index/ledger lineage has no
        # answer-bearing text in gbrain's source-page chunk surface. Do not let
        # its page slug stand in for the missing temporal/update evidence.
        if not latest["projected_event_retained"]:
            continue
        prov = {"chain": chain,
                "chain_format": latest["snapshot"]["chain_format"],
                "seq": latest["row"][0],
                "entry_hash": latest["entry_hash"],
                "ledger_head": latest["snapshot"]["head"],
                "selection": "largest-verified-sequence",
                "source_page": latest["source_page"],
                **witness_provenance(latest)}
        _append_bounded_question(questions, _make_question(
            "temporal-reasoning",
            f"On what UTC date did signed {chain} most recently record "
            f"`{action}` for `{label}`?",
            latest["day"], [latest["slug"]], prov,
            answer_witness([latest], "any-excerpt")))
        if len(rows) > 1 and len(values) > 1 and latest["value"] \
                and latest["value_answer_retained"]:
            _append_bounded_question(questions, _make_question(
                "knowledge-update",
                f"What is the most recent signed {chain} result for "
                f"`{action}` concerning `{label}`?",
                latest["value"], [latest["slug"]], prov,
                answer_witness([latest], "any-excerpt")))

    by_action = {}
    for rec in records:
        by_action.setdefault((rec["chain"], rec["action"]), []).append(rec)
    for (chain, action), rows in sorted(by_action.items()):
        # Only generate a count if every signed occurrence survived the
        # corpus-retention boundary.  Otherwise the question would silently
        # mix ledger truth with a partial retrievable history.
        snap = rows[0]["snapshot"]
        all_n = sum(1 for row in snap["rows"] if row[2] == action)
        if len(rows) <= 1 or len(rows) != all_n \
                or not all(row["projected_event_retained"] for row in rows):
            continue
        source_slugs = sorted({r["slug"] for r in rows})
        if len(source_slugs) > TOP_K:
            # A question whose complete witness set cannot fit in the scored
            # retrieval window is structurally unanswerable by that scorer.
            continue
        prov = {"chain": chain,
                "chain_format": snap["chain_format"],
                "ledger_head": snap["head"],
                "entry_hashes": [r["entry_hash"] for r in rows],
                "aggregation": "exhaustive-equal-action-row-count",
                "event_witnesses": [witness_provenance(r) for r in rows],
                "source_pages": sorted(
                    {page["slug"]: page for page in
                     (r["source_page"] for r in rows)}.values(),
                    key=lambda page: page["slug"])}
        _append_bounded_question(questions, _make_question(
            "multi-event-aggregation",
            f"Across the verified signed {chain} snapshot, how many "
            f"`{action}` records are there?",
            str(len(rows)), source_slugs, prov,
            answer_witness(rows, "all-excerpts")))

    # Hard negatives recombine two observed fields but only when an exhaustive
    # scan of the verified snapshot proves that pair never occurred.
    by_chain = {}
    for rec in records:
        by_chain.setdefault(rec["chain"], []).append(rec)
    for chain, rows in sorted(by_chain.items()):
        actions = sorted({r["action"] for r in rows})
        labels = sorted({r["label"] for r in rows})
        snap = rows[0]["snapshot"]
        if len(actions) * len(labels) > MAX_BENCH_NEGATIVE_PAIRS:
            raise BenchmarkRefusal(
                "benchmark negative-witness cross-product exceeds its "
                "ceiling")

        def negative_candidates():
            for action in actions:
                for label in labels:
                    if (action, label) in raw_pairs[chain]:
                        continue
                    payload = f"{snap['head']}|{action}|{label}"
                    yield (hashlib.sha256(payload.encode()).hexdigest(),
                           action, label)

        for _digest, action, label in heapq.nsmallest(
                MAX_PER_CATEGORY, negative_candidates()):
            prov = {"chain": chain,
                    "chain_format": snap["chain_format"],
                    "ledger_head": snap["head"],
                    "ledger_sha256": snap["ledger_sha256"],
                    "negative_witness": "pair-absent-from-all-verified-rows"}
            _append_bounded_question(questions, _make_question(
                "abstention",
                _signed_result_question(chain, action, label),
                ABSTAIN, [], prov))

    questions, generation_exclusions = _audit_questions(
        questions, {record["slug"] for record in records})
    questions = _cap_questions(questions)
    chain_provenance = [{k: snap[k] for k in
                         ("chain", "chain_format", "ledger_sha256", "head",
                          "row_count",
                          "verifier", "verifier_sha256")}
                        for snap in snapshots]
    source_pages = sorted(
        {page["slug"]: page for page in
         (record["source_page"] for record in records)}.values(),
        key=lambda page: page["slug"])
    witness_files = sorted(
        ({key: artifact[key] for key in
          ("path", "sha256", "size", "kind")}
         for artifact in resolver.witness_files.values()),
        key=lambda artifact: artifact["path"])
    seed = _sha_text(_canonical(chain_provenance))
    questions = _assign_splits(questions, seed)
    capacity_policy = {
        "kind": "complete-snapshot-refusal-v1",
        "ledger_bytes_per_chain": MAX_BENCH_LEDGER_BYTES,
        "verifier_bytes_per_chain": MAX_BENCH_VERIFIER_BYTES,
        "snapshot_aggregate_bytes": MAX_BENCH_AGGREGATE_BYTES,
        "ledger_rows_aggregate": MAX_BENCH_ROWS,
        "source_page_bytes": MAX_BENCH_SOURCE_PAGE_BYTES,
        "source_pages": MAX_BENCH_SOURCE_PAGES,
        "witness_files": MAX_BENCH_ROWS,
        "source_page_aggregate_bytes": MAX_BENCH_SOURCE_BYTES,
        "candidate_questions": MAX_BENCH_CANDIDATE_QUESTIONS,
        "negative_pair_cross_product": MAX_BENCH_NEGATIVE_PAIRS,
        "artifact_bytes_each": MAX_BENCH_FILE_BYTES,
        "artifact_aggregate_bytes": MAX_BENCH_AGGREGATE_BYTES,
    }
    identity = {
        "schema": DATASET_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "capacity_policy": capacity_policy,
        "chains": chain_provenance,
        "source_pages": source_pages,
        "witness_files": witness_files,
        "witness_coverage": witness_coverage,
        "question_coverage": question_coverage,
        "questions": [{"id": q["id"], "split": q["split"]}
                      for q in questions],
    }
    dataset_id = _sha_text(_canonical(identity))
    manifest = {
        **identity,
        "dataset_id": dataset_id,
        "question_count": len(questions),
        "answer_key_location": "separate-file-outside-indexed-corpus",
        "abstention_token": ABSTAIN,
        "calibration_policy": {
            "kind": "deterministic-stratified-hash-split",
            "divisor": CALIBRATION_DIVISOR,
            "threshold_source": "calibration-only",
        },
        "generation_exclusions": generation_exclusions,
        "non_claims": [
            "keeper verification authenticates rows, not memory-system correctness",
            "generated questions are a local regression population, not LongMemEval",
            "retrieval evidence recall requires exact digest-bound source-page "
            "excerpts; it is not reader answer correctness",
            "absence is scoped to the keeper-accepted observed ledger snapshot",
            "before/after byte, inode, metadata, and verifier-digest checks "
            "do not exclude a same-user in-place ABA completed between observations",
            "the verifier digest binds the registered executable or script, "
            "not every library, interpreter, kernel, or hardware dependency it loads",
            "strict format parsing checks row spelling and linkage after keeper "
            "success; it does not independently re-run signature verification",
            "Custos ledger intake does not re-open or re-hash files named by "
            "its signed custody rows",
            "only chains with a shared deterministic row-to-event projector "
            "can produce present questions; custom verifier success alone "
            "does not define corpus projection semantics",
            "consolidation-index lineage proves retention of an exact event "
            "occurrence, not that every answer token remains verbatim in the "
            "epoch summary",
            "every present question requires an exact projected event excerpt "
            "in the bound page; value and update questions also require its "
            "terminal result field, and omissions are reported as coverage",
            "thresholded retrieval non-abstention is a proxy, not a reader answer",
            "inputs beyond the manifest capacity policy refuse; no signed "
            "snapshot or witness is truncated",
        ],
    }
    return {"manifest": manifest, "questions": questions,
            "diagnostics": diagnostics}


def _inside(path, root):
    try:
        return os.path.commonpath((os.path.realpath(path),
                                   os.path.realpath(root))) == os.path.realpath(root)
    except ValueError:
        return False


def _require_usable_bundle(bundle):
    diagnostics = bundle.get("diagnostics", [])
    refused = [item for item in diagnostics
               if item.get("status") == "refused"]
    if refused:
        detail = ", ".join(
            f"{item.get('chain', '?')}:{item.get('reason', 'refused')}"
            for item in refused)
        raise BenchmarkRefusal(f"chain intake refused ({detail})")
    if not any(item.get("status") == "verified" for item in diagnostics):
        raise BenchmarkRefusal("no requested chain produced a verified snapshot")
    questions = bundle.get("questions", [])
    if not questions:
        raise BenchmarkRefusal("verified snapshots produced no benchmark questions")
    if not any(q.get("split") == "evaluation" for q in questions):
        raise BenchmarkRefusal("benchmark population has no held-out evaluation rows")


def _atomic_text(path, content, mode=0o644):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    if not isinstance(content, str):
        raise TypeError("benchmark publication payload must be text")
    siaqueue.fixed_atomic_publish(
        path, content.encode("utf-8", errors="strict"), mode=mode,
        staging_dir=siaqueue.staging_dir_for(path))


def write_dataset(bundle, out_dir, corpus=None):
    _require_usable_bundle(bundle)
    corpus = corpus or CORPUS
    out_dir = os.path.realpath(os.path.expanduser(out_dir))
    if _inside(out_dir, corpus):
        raise ValueError("refusing answer-key output inside indexed corpus")
    os.makedirs(out_dir, exist_ok=True)
    questions = "".join(_canonical({
        "schema": DATASET_SCHEMA,
        "dataset_id": bundle["manifest"]["dataset_id"],
        "id": q["id"], "split": q["split"], "question": q["question"],
    }) + "\n" for q in bundle["questions"])
    key = "".join(_canonical({
        "schema": DATASET_SCHEMA,
        "dataset_id": bundle["manifest"]["dataset_id"],
        "id": q["id"], "split": q["split"],
        "category": q["category"], "answer": q["answer"],
        "sources": q["sources"], "provenance": q["provenance"],
        **({"answer_witness": q["answer_witness"]}
           if "answer_witness" in q else {}),
    }) + "\n" for q in bundle["questions"])
    eval_rows = sorted((q for q in bundle["questions"]
                        if q["split"] == "evaluation"),
                       key=lambda q: q["id"])[:MCP_EVALUATION_LIMIT]
    mcp_evaluation = "<evaluation>\n" + "".join(
        "  <qa_pair>\n"
        "    <question>Using only SIA's read-only search and memory "
        f"resources, {xml_escape(q['question'])}</question>\n"
        f"    <answer>{xml_escape(str(q['answer']))}</answer>\n"
        "  </qa_pair>\n" for q in eval_rows) + "</evaluation>\n"
    # The in-memory evaluation manifest carries exact source-page and witness
    # bindings. They are private answer-key material: a dated source slug can
    # itself answer a temporal question. Export only an explicit public
    # allow-list and retain the complete manifest under mode 0600 below.
    full_manifest = dict(bundle["manifest"])
    manifest = {key: full_manifest[key]
                for key in PUBLIC_MANIFEST_BASE_FIELDS}
    manifest["questions_sha256"] = _sha_text(questions)
    manifest["private_integrity_manifest"] = "private-manifest.json (mode 0600)"
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    private_manifest = {
        "schema": PRIVATE_MANIFEST_SCHEMA,
        "dataset_id": manifest["dataset_id"],
        "public_manifest_sha256": _sha_text(manifest_text),
        "answer_key_sha256": _sha_text(key),
        "mcp_evaluation_sha256": _sha_text(mcp_evaluation),
        "mcp_evaluation_rows": len(eval_rows),
        "evaluation_manifest": full_manifest,
        "evaluation_manifest_sha256": _sha_text(_canonical(full_manifest)),
    }
    private_manifest_text = json.dumps(
        private_manifest, indent=2, sort_keys=True) + "\n"
    artifacts = {
        "questions.jsonl": questions,
        "answer-key.jsonl": key,
        "mcp-evaluation.xml": mcp_evaluation,
        "private-manifest.json": private_manifest_text,
        "manifest.json": manifest_text,
    }
    encoded_sizes = [len(value.encode("utf-8"))
                     for value in artifacts.values()]
    if any(size > MAX_BENCH_FILE_BYTES for size in encoded_sizes) \
            or sum(encoded_sizes) > MAX_BENCH_AGGREGATE_BYTES:
        raise BenchmarkRefusal(
            "serialized benchmark dataset exceeds its byte ceiling")
    _atomic_text(os.path.join(out_dir, "questions.jsonl"), questions)
    _atomic_text(os.path.join(out_dir, "answer-key.jsonl"), key, 0o600)
    _atomic_text(os.path.join(out_dir, "mcp-evaluation.xml"),
                 mcp_evaluation, 0o600)
    _atomic_text(os.path.join(out_dir, "private-manifest.json"),
                 private_manifest_text, 0o600)
    _atomic_text(os.path.join(out_dir, "manifest.json"), manifest_text)
    return manifest


def _parse_jsonl(content, source, *, require_trailing_lf=False):
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise BenchmarkRefusal(
                "benchmark JSONL is not valid UTF-8") from exc
    if not isinstance(content, str):
        raise ValueError(f"JSONL input is not text in {source}")
    if require_trailing_lf and content and not content.endswith("\n"):
        raise ValueError(f"generated JSONL lacks trailing LF in {source}")
    rows = []
    # JSONL is framed by the literal byte LF. Unicode NEL/line/paragraph
    # separators are valid characters inside JSON strings and must not split
    # a physical record.
    for line_no, line in enumerate(content.split("\n"), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise BenchmarkRefusal(
                f"benchmark JSONL row is malformed at line {line_no}") \
                from exc
        if not isinstance(row, dict):
            raise ValueError(f"non-object JSONL in {source} at line {line_no}")
        if len(rows) >= MAX_BENCH_ROWS:
            raise ValueError(f"JSONL row ceiling exceeded in {source}")
        rows.append(row)
    return rows


def _read_jsonl(path):
    raw, _token, _digest = _read_nofollow_regular(
        path, max_bytes=MAX_BENCH_FILE_BYTES)
    # Submitted predictions may omit the final LF; generated/private dataset
    # artifacts have a stricter policy in ``load_dataset`` below.
    return _parse_jsonl(raw, path, require_trailing_lf=False)


def load_dataset(dataset_dir):
    dataset_dir = os.path.realpath(os.path.expanduser(dataset_dir))
    artifacts = {}
    for name, private in (
            ("manifest.json", False), ("private-manifest.json", True),
            ("questions.jsonl", False), ("answer-key.jsonl", True),
            ("mcp-evaluation.xml", True)):
        raw, _token, _digest = _read_nofollow_regular(
            os.path.join(dataset_dir, name),
            max_bytes=MAX_BENCH_FILE_BYTES, private=private)
        artifacts[name] = raw
    if sum(len(value) for value in artifacts.values()) \
            > MAX_BENCH_AGGREGATE_BYTES:
        raise ValueError("benchmark dataset exceeds its aggregate byte ceiling")
    try:
        manifest_bytes = artifacts["manifest.json"].decode("utf-8")
        private_manifest_bytes = artifacts["private-manifest.json"].decode(
            "utf-8")
        qbytes = artifacts["questions.jsonl"].decode("utf-8")
        kbytes = artifacts["answer-key.jsonl"].decode("utf-8")
        mcp_bytes = artifacts["mcp-evaluation.xml"].decode("utf-8")
    except UnicodeError as exc:
        raise BenchmarkRefusal(
            "benchmark dataset contains non-UTF-8 text") from exc
    try:
        manifest = json.loads(manifest_bytes)
        private_manifest = json.loads(private_manifest_bytes)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise BenchmarkRefusal(
            "benchmark dataset manifests are malformed") from exc
    if not isinstance(manifest, dict) \
            or not isinstance(private_manifest, dict):
        raise BenchmarkRefusal(
            "benchmark dataset manifests must be objects")
    if set(manifest) != PUBLIC_MANIFEST_FIELDS:
        raise ValueError("public benchmark manifest fields are invalid")
    if set(private_manifest) != PRIVATE_MANIFEST_FIELDS:
        raise ValueError("private benchmark manifest fields are invalid")
    if _sha_text(manifest_bytes) != \
            private_manifest.get("public_manifest_sha256") \
            or _sha_text(qbytes) != manifest.get("questions_sha256") \
            or _sha_text(kbytes) != private_manifest.get("answer_key_sha256") \
            or _sha_text(mcp_bytes) != \
            private_manifest.get("mcp_evaluation_sha256"):
        raise ValueError("dataset digest mismatch")
    expected_id = manifest.get("dataset_id")
    if private_manifest.get("schema") != PRIVATE_MANIFEST_SCHEMA \
            or private_manifest.get("dataset_id") != expected_id:
        raise ValueError("private manifest identity mismatch")
    evaluation_manifest = private_manifest.get("evaluation_manifest")
    if not isinstance(evaluation_manifest, dict) \
            or evaluation_manifest.get("schema") != DATASET_SCHEMA \
            or evaluation_manifest.get("dataset_id") != expected_id \
            or _sha_text(_canonical(evaluation_manifest)) != \
               private_manifest.get("evaluation_manifest_sha256"):
        raise ValueError("private evaluation manifest mismatch")
    if manifest.get("schema") != DATASET_SCHEMA \
            or manifest.get("generator_version") != GENERATOR_VERSION:
        raise ValueError("public benchmark manifest version mismatch")
    questions = _parse_jsonl(
        qbytes, "questions.jsonl", require_trailing_lf=True)
    keys = _parse_jsonl(
        kbytes, "answer-key.jsonl", require_trailing_lf=True)
    question_ids = [q.get("id") for q in questions]
    key_ids = [k.get("id") for k in keys]
    if any(not isinstance(value, str) or not value
           for value in question_ids + key_ids):
        raise ValueError("question and answer-key IDs must be non-empty strings")
    qids, kids = set(question_ids), set(key_ids)
    if any(not isinstance(qid, str) or not qid for qid in question_ids):
        raise ValueError("question IDs must be non-empty strings")
    if any(not isinstance(qid, str) or not qid for qid in key_ids):
        raise ValueError("answer-key IDs must be non-empty strings")
    if len(qids) != len(question_ids):
        raise ValueError("question IDs must be unique")
    if len(kids) != len(key_ids):
        raise ValueError("answer-key IDs must be unique")
    if qids != kids:
        raise ValueError("question/key ID closure mismatch")
    if any(row.get("schema") != DATASET_SCHEMA for row in questions + keys):
        raise ValueError("dataset row schema mismatch")
    if any(row.get("dataset_id") != expected_id for row in questions + keys):
        raise ValueError("dataset ID mismatch")
    if any(not isinstance(row.get("answer"), str) for row in keys):
        raise ValueError("answer-key answers must be strings")
    return manifest, questions, keys


def _norm_answer(value):
    return " ".join(str(value).split()).casefold()


def score_answer_file(dataset_dir, answers_path):
    """Deterministic normalized scoring. Missing output is not abstention."""
    manifest, _questions, keys = load_dataset(dataset_dir)
    submitted = _read_jsonl(os.path.expanduser(answers_path))
    predictions = {}
    for row in submitted:
        qid = row.get("id")
        if not isinstance(qid, str) or not qid or qid in predictions:
            raise ValueError("prediction IDs must be present and unique")
        if "answer" not in row or not isinstance(row["answer"], str):
            raise ValueError("each prediction requires an explicit string answer")
        predictions[qid] = row["answer"]
    evaluation = [row for row in keys if row.get("split") == "evaluation"]
    known = {row["id"] for row in keys}
    unknown = sorted(set(predictions) - known)
    if unknown:
        raise ValueError("predictions contain unknown question IDs")
    rows = []
    for key in evaluation:
        present = key["id"] in predictions
        predicted = predictions.get(key["id"])
        correct = present and _norm_answer(predicted) == _norm_answer(key["answer"])
        rows.append({"id": key["id"], "predicted": predicted,
                     "submitted": present,
                     "correct": correct})
    by_category = {}
    for key, row in zip(evaluation, rows):
        d = by_category.setdefault(key["category"],
                                   {"correct": 0, "total": 0})
        d["total"] += 1
        d["correct"] += int(row["correct"])
    return {
        "schema": "sia-ledger-qa-score-v1",
        "dataset_id": manifest["dataset_id"],
        "evaluation_total": len(rows),
        "submitted": sum(1 for r in rows if r["submitted"]),
        "correct": sum(1 for r in rows if r["correct"]),
        "abstention_correct": sum(
            1 for key, row in zip(evaluation, rows)
            if row["correct"] and key["answer"] == ABSTAIN),
        "abstention_total": sum(
            1 for key in evaluation if key["answer"] == ABSTAIN),
        "by_category": by_category,
        "rows": rows,
        "non_claims": manifest.get("non_claims", []),
    }


def _full_results(results):
    seen, out = set(), []
    for item in results:
        slug = item.get("slug")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        chunk_text = item.get("chunk_text", "")
        if not isinstance(chunk_text, str):
            chunk_text = ""
        out.append({"slug": slug, "score": float(item.get("score") or 0),
                    "chunk_text": chunk_text})
    return out


def _query_systems(question, graph, mind):
    keyword = _full_results(_engine(["search", question]))
    dense = _full_results(_engine(["query", question]))
    meta = {row["slug"]: row for row in dense}
    blend_ranked = siamind.ppr_rerank(
        graph, [(row["slug"], row["score"]) for row in dense], mind=mind) \
        if dense else []
    blend = [{"slug": slug, "score": score,
              "chunk_text": meta.get(slug, {}).get("chunk_text", "")}
             for slug, score in blend_ranked]
    return {"keyword": keyword, "dense": dense, "blend": blend}


def choose_abstention_threshold(samples):
    """Select on calibration rows only; ties prefer more abstention."""
    present_n = sum(1 for _score, present in samples if present)
    absent_n = sum(1 for _score, present in samples if not present)
    if not present_n or not absent_n:
        return None, "insufficient-calibration-classes"
    finite = sorted({score for score, _present in samples
                     if math.isfinite(score)})
    candidates = finite + [math.inf]
    best = None
    for threshold in candidates:
        present_correct = sum(1 for score, label in samples
                              if label and score >= threshold)
        absent_correct = sum(1 for score, label in samples
                             if not label and score < threshold)
        # Cross-multiplied balanced accuracy; no float comparison needed.
        balanced_numerator = (present_correct * absent_n
                              + absent_correct * present_n)
        key = (balanced_numerator, absent_correct, threshold)
        if best is None or key > best[0]:
            best = (key, threshold)
    return best[1], "calibrated-descriptive"


def _evidence_rank(question, results, k=TOP_K):
    if question["answer"] == ABSTAIN:
        return None
    witness = question.get("answer_witness")
    if not isinstance(witness, dict) \
            or witness.get("schema") != ANSWER_WITNESS_SCHEMA \
            or witness.get("match") not in {"any-excerpt", "all-excerpts"}:
        return None
    excerpts = witness.get("excerpts")
    if not isinstance(excerpts, list) or not excerpts \
            or len(excerpts) > MAX_BENCH_ROWS:
        return None
    wanted = set(question.get("sources", []))
    admitted = []
    aggregate_bytes = 0
    for item in excerpts:
        if not isinstance(item, dict) or set(item) != {
                "slug", "excerpt", "sha256"}:
            return None
        slug = item.get("slug")
        excerpt = _normalize_witness_excerpt(item.get("excerpt"))
        digest = item.get("sha256")
        if not isinstance(slug, str) or slug not in wanted \
                or excerpt is None \
                or not isinstance(digest, str) \
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None \
                or _sha_text(excerpt) != digest:
            return None
        aggregate_bytes += len(excerpt.encode("utf-8"))
        if aggregate_bytes > MAX_BENCH_SOURCE_BYTES:
            return None
        admitted.append((slug, excerpt))

    matched = set()
    last_rank = None
    for rank, row in enumerate(results[:k], 1):
        if not isinstance(row, dict):
            continue
        slug = row.get("slug")
        chunk_text = _normalize_witness_excerpt(row.get("chunk_text"))
        if not isinstance(slug, str) or chunk_text is None:
            continue
        for index, (wanted_slug, excerpt) in enumerate(admitted):
            if slug == wanted_slug and excerpt in chunk_text:
                if witness["match"] == "any-excerpt":
                    return rank
                matched.add(index)
                last_rank = rank
        if len(matched) == len(admitted):
            return last_rank
    return None


def _verify_source_pages(bundle, corpus=None):
    """Re-open every digest-bound source page/witness or refuse stale data.

    Generation binds the bytes; this check makes live evaluation consume that
    same snapshot instead of trusting only a slug after the corpus lease has
    moved on. It runs on both sides of querying to detect in-run mutation.
    """
    # Preserve the caller's path components so the opener can reject a corpus
    # root or parent replaced by a symlink after generation. Resolving it here
    # would silently turn that authority change into a different trusted root.
    corpus = os.path.abspath(os.path.expanduser(corpus or CORPUS))
    manifest = bundle.get("manifest", {}) if isinstance(bundle, dict) else {}
    pages = manifest.get("source_pages")
    if pages is None:
        # Compatibility for unit-sized synthetic bundles that do not claim to
        # be generated signed-ledger datasets.
        return
    if not isinstance(pages, list):
        raise BenchmarkRefusal("source-page manifest is malformed")
    if len(pages) > MAX_BENCH_SOURCE_PAGES:
        raise BenchmarkRefusal(
            "source-page manifest exceeds its page-count ceiling")
    aggregate_bytes = 0
    seen_slugs = set()
    for page in pages:
        if not isinstance(page, dict):
            raise BenchmarkRefusal("source-page manifest is malformed")
        slug = page.get("slug")
        digest = page.get("sha256")
        size = page.get("size")
        if not isinstance(slug, str) \
                or not re.fullmatch(r"[a-z0-9][a-z0-9/._-]{0,199}", slug) \
                or any(part in ("", ".", "..") for part in slug.split("/")) \
                or not isinstance(digest, str) \
                or not re.fullmatch(r"[0-9a-f]{64}", digest) \
                or not isinstance(size, int) or isinstance(size, bool) \
                or size < 0 or slug in seen_slugs:
            raise BenchmarkRefusal("source-page manifest is malformed")
        seen_slugs.add(slug)
        if size > MAX_BENCH_SOURCE_PAGE_BYTES:
            raise BenchmarkRefusal(
                "source-page manifest exceeds its per-page byte ceiling")
        aggregate_bytes += size
        if aggregate_bytes > MAX_BENCH_SOURCE_BYTES:
            raise BenchmarkRefusal(
                "source-page manifest exceeds its aggregate-byte ceiling")
        path = os.path.join(corpus, slug + ".md")
        try:
            if os.path.commonpath((corpus, os.path.abspath(path))) != corpus:
                raise OSError("source page escapes corpus")
            data, _token, observed_digest = _read_nofollow_regular(
                path, max_bytes=MAX_BENCH_SOURCE_PAGE_BYTES)
        except Exception as exc:
            raise BenchmarkRefusal(
                f"source page {slug} cannot be re-opened: {exc}") from exc
        if len(data) != size or observed_digest != digest:
            raise BenchmarkRefusal(
                f"source page {slug} changed after dataset generation")
    witnesses = manifest.get("witness_files", [])
    if not isinstance(witnesses, list):
        raise BenchmarkRefusal("witness-file manifest is malformed")
    if len(witnesses) > MAX_BENCH_ROWS:
        raise BenchmarkRefusal(
            "witness-file manifest exceeds its file-count ceiling")
    seen_paths = set()
    for witness in witnesses:
        if not isinstance(witness, dict) or set(witness) != {
                "path", "sha256", "size", "kind"}:
            raise BenchmarkRefusal("witness-file manifest is malformed")
        relative = witness.get("path")
        digest = witness.get("sha256")
        size = witness.get("size")
        if witness.get("kind") != "event-index" \
                or not isinstance(relative, str) \
                or re.fullmatch(
                    r"event-index/[a-z0-9][a-z0-9._-]{0,199}/"
                    r"[0-9a-f]{2}/[0-9a-f]{64}\.json", relative) is None \
                or any(part in ("", ".", "..")
                       for part in relative.split("/")) \
                or not isinstance(digest, str) \
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None \
                or not isinstance(size, int) or isinstance(size, bool) \
                or size < 0 or size > sialib.MAX_EVENT_INDEX_BYTES \
                or relative in seen_paths:
            raise BenchmarkRefusal("witness-file manifest is malformed")
        seen_paths.add(relative)
        aggregate_bytes += size
        if aggregate_bytes > MAX_BENCH_SOURCE_BYTES:
            raise BenchmarkRefusal(
                "source witness manifest exceeds its aggregate-byte ceiling")
        try:
            data, _token, observed_digest = _read_nofollow_regular(
                os.path.join(corpus, *relative.split("/")),
                max_bytes=sialib.MAX_EVENT_INDEX_BYTES)
            entry = json.loads(data.decode("utf-8", errors="strict"))
            entry = sialib._canonical_event_index_entry(entry)
            expected_relative = sialib._event_index_relative(
                entry["organ"], entry["event_id"]).replace(os.sep, "/")
            if data != sialib._event_index_encoded(entry) \
                    or expected_relative != relative:
                raise ValueError("event-index path binding is invalid")
        except (UnicodeError, ValueError, RecursionError) as exc:
            raise BenchmarkRefusal(
                f"witness file {relative} is malformed") from exc
        except Exception as exc:
            raise BenchmarkRefusal(
                f"witness file {relative} cannot be re-opened: {exc}") \
                from exc
        if len(data) != size or observed_digest != digest:
            raise BenchmarkRefusal(
                f"witness file {relative} changed after dataset generation")


def evaluate_retrieval(bundle, query_fn=None, corpus=None):
    """Score evidence retrieval + a thresholded non-abstention proxy.

    This deliberately does not copy the private answer key into a synthetic
    reader response.  Present-question success means answer-bearing evidence
    was retrieved: the result must name the bound source page and its returned
    chunk must contain the question's exact private excerpt witness. Normalized
    reader answers are scored separately with ``score``.
    """
    _verify_source_pages(bundle, corpus=corpus)
    if query_fn is None:
        graph = sialib.read_json(sialib.GRAPH_PATH, None)
        mind = siamind.load_mind()
        query_fn = lambda q: _query_systems(q, graph, mind)
    observed = {}
    for q in bundle["questions"]:
        observed[q["id"]] = query_fn(q["question"])
    _verify_source_pages(bundle, corpus=corpus)
    systems = sorted({name for result in observed.values() for name in result})
    reports = {}
    for system in systems:
        calibration = []
        for q in bundle["questions"]:
            if q["split"] != "calibration":
                continue
            results = observed[q["id"]].get(system, [])
            score = results[0]["score"] if results else -math.inf
            calibration.append((score, q["answer"] != ABSTAIN))
        threshold, threshold_status = choose_abstention_threshold(calibration)
        evaluation = [q for q in bundle["questions"]
                      if q["split"] == "evaluation"]
        if threshold is None:
            reports[system] = {
                "scored": False,
                "threshold": None,
                "threshold_status": threshold_status,
                "calibration_n": len(calibration),
                "evaluation_n": len(evaluation),
                "correct": None,
                "present_evidence_correct": None,
                "present_total": None,
                "abstention_correct": None,
                "abstention_total": None,
                "false_nonabstentions": None,
                "false_abstains": None,
                "wrong_evidence": None,
                "rows": [],
            }
            continue
        rows = []
        for q in evaluation:
            results = observed[q["id"]].get(system, [])
            top = results[0]["score"] if results else -math.inf
            abstained = top < threshold
            rank = _evidence_rank(q, results)
            if q["answer"] == ABSTAIN:
                correct = abstained
                error = None if correct else "false-nonabstention"
            else:
                correct = (not abstained) and rank is not None
                error = None if correct else ("false-abstain" if abstained
                                               else "wrong-evidence")
            rows.append({"id": q["id"], "category": q["category"],
                         "expected_abstain": q["answer"] == ABSTAIN,
                         "abstained": abstained, "evidence_rank": rank,
                         "correct": correct, "error": error})
        present = [r for r in rows if not r["expected_abstain"]]
        absent = [r for r in rows if r["expected_abstain"]]
        reports[system] = {
            "scored": True,
            "threshold": threshold,
            "threshold_status": threshold_status,
            "calibration_n": len(calibration),
            "evaluation_n": len(rows),
            "correct": sum(1 for r in rows if r["correct"]),
            "present_evidence_correct": sum(1 for r in present if r["correct"]),
            "present_total": len(present),
            "abstention_correct": sum(1 for r in absent if r["correct"]),
            "abstention_total": len(absent),
            "false_nonabstentions": sum(
                1 for r in rows if r["error"] == "false-nonabstention"),
            "false_abstains": sum(1 for r in rows if r["error"] == "false-abstain"),
            "wrong_evidence": sum(1 for r in rows if r["error"] == "wrong-evidence"),
            "rows": rows,
        }
    return reports


def _fraction(numerator, denominator):
    return f"{numerator}/{denominator}" if denominator else "n/a"


def render_retrieval_report(bundle, reports):
    manifest = bundle["manifest"]
    cal_n = sum(1 for q in bundle["questions"] if q["split"] == "calibration")
    eval_n = sum(1 for q in bundle["questions"] if q["split"] == "evaluation")
    lines = [f"# SIA signed-ledger memory benchmark · {manifest['dataset_id'][:12]}",
             "",
             f"Dataset: {len(bundle['questions'])} auto-generated QA rows; "
             f"{cal_n} calibration, {eval_n} held-out evaluation. "
             "The literal expected answer for negative rows is `ABSTAIN`.",
             "",
             "Every source ledger was accepted by its registered keeper and "
             "matched the observed pre/post byte, inode, metadata, and "
             "verifier-digest checks. Thresholds use only the calibration "
             "split; answer keys are never indexed.",
             "",
             "The threshold decision is a retrieval non-abstention proxy, not "
             "a reader answer.",
             "",
             "| system | retrieval proxy correct | witnessed present evidence | "
             "abstention | false non-abstentions | false abstains | "
             "wrong evidence | τ |",
             "|---|---|---|---|---|---|---|---|"]
    for name, result in sorted(reports.items()):
        if not result["scored"]:
            lines.append(
                f"| {name} | withheld | withheld | withheld | withheld | "
                f"withheld | withheld | withheld "
                f"({result['threshold_status']}) |")
            continue
        threshold = result["threshold"]
        tau = ("withheld" if threshold is None else
               "+inf" if math.isinf(threshold) else f"{threshold:.6g}")
        lines.append(
            f"| {name} | {_fraction(result['correct'], result['evaluation_n'])} "
            f"| {_fraction(result['present_evidence_correct'], result['present_total'])} "
            f"| {_fraction(result['abstention_correct'], result['abstention_total'])} "
            f"| {result['false_nonabstentions']} | {result['false_abstains']} "
            f"| {result['wrong_evidence']} | {tau} ({result['threshold_status']}) |")
    if not reports or not any(result["scored"] for result in reports.values()):
        lines += ["", "No held-out result was scored: the verified local "
                  "population is too sparse, threshold calibration was "
                  "withheld, or no query system was available."]
    lines += ["", "Boundaries:"]
    lines += [f"- {item}" for item in manifest["non_claims"]]
    if bundle.get("diagnostics"):
        lines += ["", "Chain intake:"]
        for diag in bundle["diagnostics"]:
            detail = f" — {diag.get('reason')}" if diag.get("reason") else ""
            lines.append(f"- {diag['chain']}: {diag['status']}{detail}")
    return "\n".join(lines)


def run(chain_names=None):
    with sialib.corpus_owner():
        bundle = build_ledger_dataset(chain_names=chain_names)
        _require_usable_bundle(bundle)
        reports = evaluate_retrieval(bundle, corpus=CORPUS)
        report = render_retrieval_report(bundle, reports)
    out_dir = os.path.expanduser("~/.local/share/sia/research")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"ledger-bench-{sialib.today()}.md")
    _atomic_text(out, report + "\n")
    print(report)
    print(f"\nsaved → {out}")
    return report


def _print_score(score):
    print(json.dumps(score, indent=2, sort_keys=True))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="sia bench",
        description="signed-ledger QA generation, retrieval evaluation, and deterministic scoring")
    sub = parser.add_subparsers(dest="command")
    run_p = sub.add_parser("run", help="run held-out retrieval/abstention evaluation")
    run_p.add_argument("--chain", action="append", dest="chains")
    gen_p = sub.add_parser("generate", help="export question-only and private key files")
    gen_p.add_argument("--out", required=True)
    gen_p.add_argument("--chain", action="append", dest="chains")
    score_p = sub.add_parser("score", help="normalized-score JSONL {id, answer} predictions")
    score_p.add_argument("--dataset", required=True)
    score_p.add_argument("--answers", required=True)
    sub.add_parser(
        "legacy", help="run the heuristic slug-retrieval drift tripwire")
    args = parser.parse_args(argv)
    try:
        if args.command in (None, "run"):
            run(getattr(args, "chains", None))
            return 0
        if args.command == "generate":
            with sialib.corpus_owner():
                bundle = build_ledger_dataset(chain_names=args.chains)
                manifest = write_dataset(bundle, args.out)
            print(json.dumps({"dataset_id": manifest["dataset_id"],
                              "questions": manifest["question_count"],
                              "output": os.path.realpath(
                                  os.path.expanduser(args.out)),
                              "answer_key": "answer-key.jsonl (mode 0600)",
                              "private_manifest":
                                  "private-manifest.json (mode 0600)",
                              "mcp_evaluation":
                                  "mcp-evaluation.xml (mode 0600)"}, indent=2))
            return 0
        if args.command == "score":
            _print_score(score_answer_file(args.dataset, args.answers))
            return 0
        if args.command == "legacy":
            run_legacy()
            return 0
    except BenchmarkRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
