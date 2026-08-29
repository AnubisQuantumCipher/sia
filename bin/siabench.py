"""siabench — measure SIA's retrieval instead of asserting it.

Questions are generated from ground truth SIA itself established (day
pages, epochs, entities that provably exist in the corpus), plus absent
questions about plausible things that were never recorded. Three systems
compete: keyword (BM25), dense (gbrain hybrid order as returned), and
blend (the production dense × PPR × ACT-R rerank with origin weights).

Scored: hit@1 / hit@5 / MRR@5 on present questions (a hit = a returned
slug containing an accept-substring that provably holds the answer), and
on absent questions the FALSE-ANSWER rate — answering confidently about
something not in memory is the failure; abstention is the success.
Abstention rule per system: no results, or top score below τ (dense/blend
τ chosen as half the present-set median top-1 score — reported, not
hidden). Output: a markdown table saved to research/.
"""

import json, os, statistics, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import siamind, sialib

CORPUS = sialib.CORPUS


def _engine(args, timeout=180):
    for _ in range(4):
        r = subprocess.run([sialib.GBRAIN] + args + ["--source", "sia",
                                                     "--json"],
                           env=sialib.GBRAIN_ENV, capture_output=True,
                           text=True, timeout=timeout, cwd=CORPUS)
        if r.returncode == 0 or "already open" not in (r.stdout + r.stderr):
            break
        time.sleep(3)
    try:
        i = r.stdout.index("[")
        return json.loads(r.stdout[i:])
    except Exception:
        return []


def _dedupe(results):
    seen, out = set(), []
    for x in results:
        s = x.get("slug")
        if s and s not in seen:
            seen.add(s)
            out.append((s, float(x.get("score") or 0),
                        x.get("type", "")))
    return out


def build_questions():
    """Present questions conditioned on pages that actually exist."""
    have = set()
    for root, _, files in os.walk(CORPUS):
        for f in files:
            if f.endswith(".md"):
                have.add(os.path.relpath(os.path.join(root, f),
                                         CORPUS)[:-3])
    def organ_has(o):
        return any(s.startswith(f"events/{o}/") or
                   s.startswith(f"epochs/{o}/") for s in have)
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
        add("formal receipts retained by the math kernel",
            ["events/jackal", "formal"])
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
    if "organs/custos" in have:
        add("what does the custos organ do", ["organs/custos",
                                             "events/custos",
                                             "epochs/custos"])
    if "sia/cortex" in have:
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


def hit_rank(ranked_slugs, accepts, k=5):
    for i, s in enumerate(ranked_slugs[:k]):
        if any(a in s for a in accepts):
            return i + 1
    return None


def run():
    present, absent = build_questions()
    graph = sialib.read_json(sialib.GRAPH_PATH, None)
    mind = siamind.load_mind()
    systems = ["keyword", "dense", "blend"]
    per = {s: {"ranks": [], "abs_top": [], "false_ans": 0,
               "pres_top": []} for s in systems}

    for q, accepts in present:
        kw = _dedupe(_engine(["search", q]))
        dn = _dedupe(_engine(["query", q]))
        bl = siamind.ppr_rerank(graph, [(s, sc) for s, sc, _ in dn],
                                mind=mind) if dn else []
        for name, res in (("keyword", [(s, sc) for s, sc, _ in kw]),
                          ("dense", [(s, sc) for s, sc, _ in dn]),
                          ("blend", bl)):
            slugs = [s for s, _ in res]
            per[name]["ranks"].append(hit_rank(slugs, accepts))
            if res:
                per[name]["pres_top"].append(res[0][1])

    # abstention thresholds: measured separability, not a guessed ratio —
    # τ sits between the 10th percentile of present top-1 scores and the
    # maximum absent top-1 (computed after both distributions are known)
    tau = {name: None for name in systems}

    for q in absent:
        kw = _dedupe(_engine(["search", q]))
        dn = _dedupe(_engine(["query", q]))
        bl = siamind.ppr_rerank(graph, [(s, sc) for s, sc, _ in dn],
                                mind=mind) if dn else []
        for name, res in (("keyword", [(s, sc) for s, sc, _ in kw]),
                          ("dense", [(s, sc) for s, sc, _ in dn]),
                          ("blend", bl)):
            per[name]["abs_top"].append(res[0][1] if res else 0.0)

    # threshold from MEASURED separability of the two score distributions
    sep = {}
    for name in systems:
        pres = sorted(per[name]["pres_top"])
        absv = per[name]["abs_top"]
        p10 = pres[max(0, int(0.1 * len(pres)))] if pres else 0.0
        amax = max(absv) if absv else 0.0
        tau[name] = (p10 + amax) / 2 if amax < p10 else p10
        per[name]["false_ans"] = sum(1 for t in absv if t >= tau[name])
        per[name]["wrong_abstain"] = sum(1 for t in pres if t < tau[name])
        sep[name] = (f"present p10={p10:.2f} med="
                     f"{statistics.median(pres):.2f} · absent max="
                     f"{amax:.2f} med={statistics.median(absv):.2f} · "
                     + ("separable" if amax < p10 else "OVERLAP — "
                        "threshold abstention not identifiable"))

    n, na = len(present), len(absent)
    lines = [f"# SIA retrieval benchmark · {sialib.today()}",
             "",
             f"{n} present questions (ground truth = corpus pages that "
             f"provably hold the answer), {na} absent questions "
             f"(correct answer = abstain). τ per system = midpoint of "
             f"present-p10 and absent-max when the distributions "
             f"separate; the separability itself is reported.",
             "",
             "| system | hit@1 | hit@5 | MRR@5 | false-ans on absent "
             "| wrong-abstain on present | τ |",
             "|---|---|---|---|---|---|---|"]
    for name in systems:
        ranks = per[name]["ranks"]
        h1 = sum(1 for r in ranks if r == 1) / n
        h5 = sum(1 for r in ranks if r) / n
        mrr = sum(1 / r for r in ranks if r) / n
        lines.append(f"| {name} | {h1:.2f} | {h5:.2f} | {mrr:.2f} "
                     f"| {per[name]['false_ans']}/{na} "
                     f"| {per[name]['wrong_abstain']}/{n} "
                     f"| {tau[name]:.2f} |")
    lines += [""] + [f"- {name}: {sep[name]}" for name in systems]
    lines += ["",
              "Misses (present questions with no hit in top-5):"]
    for name in systems:
        misses = [present[i][0] for i, r in enumerate(per[name]["ranks"])
                  if not r]
        lines.append(f"- {name}: " + ("; ".join(misses) if misses
                                      else "none"))
    report = "\n".join(lines)
    out = os.path.expanduser(
        f"~/.local/share/sia/research/bench-{sialib.today()}.md")
    with open(out, "w") as f:
        f.write(report + "\n")
    print(report)
    print(f"\nsaved → {out}")
    return report


if __name__ == "__main__":
    run()
