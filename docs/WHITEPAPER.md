# SIA: An Evidence-Grounded Neurocognitive Memory for a Linux Desktop

**Khephri Labs · open source (MIT) · 2026-08-29 · v1.0**

*Measurements and deployment details herein are from the reference deployment: an Omarchy Linux 4.0 (aarch64) machine running the full optional-integration set.*

---

## Abstract

SIA ("the Omarchy Brain") is a persistent, associative, self-consolidating
memory system for an operating system. It fuses the machine's existing
evidence streams — cryptographically chained subsystem ledgers, formally
checked computation receipts, package and journal logs, agent-session
metadata — into a single knowledge graph over a git-versioned markdown
corpus, indexed by gbrain (PGLite + local embeddings). On top of storage
it implements a deterministic neurocognitive layer drawn from the memory
literature: ACT-R activation, Hebbian co-activation, spreading-activation
retrieval (HippoRAG), dopaminergic novelty gating, surprisal against
learned baselines, a Global-Workspace attention model, sleep-cycle
systems consolidation with flashbulb preservation, and outcome learning
via Brier-scored predictions. A language model — the operator's own
CLI subscription, configurable (reference deployment: GPT-5.6-Sol via
Codex) — is confined to two labeled roles, reflective synthesis and
strict evidence judging, and never writes unlabeled memory. The design's governing
principle is inherited from the host machine's evidence culture: every
answer declares what kind of answer it is, absence of recall is not
evidence of absence, and a system that fails open must say so.

## 1. Motivation

Any Linux desktop already produces evidence streams — packages, journal,
git, notifications, agent sessions — and SIA's base senses cover those on
every machine, with config-driven custom senses for the user's own
programs. The reference deployment goes further: it runs a family of
evidence-producing subsystems:
JACKAL (a deterministic mathematical kernel whose every result is
ledgered, some carrying Lean-checked certificates), SEKHMET (a
SPARK-proved self-healing fabric), Custos (a proof-carrying file
custodian), AEGIS, WORLDLINE (a branchable-reality system with a causal
event store), omarchy-guardian, plus the ordinary streams of any Linux
desktop: pacman, journald, git, desktop notifications, and — on Omarchy
Quattro — per-agent usage meters. Each stream is trustworthy alone;
none is queryable together. The operating system had evidence but no
memory: no way to ask *what happened*, *what connects*, *what is
unusual*, or *was I right*.

SIA is that memory. Its goals, in order: (1) fidelity — never
misrepresent the evidence class of what it knows; (2) association —
connect across streams the way recall connects across experiences;
(3) learning — importance, rhythm, and judgment must improve with use;
(4) locality — the memory of a machine belongs on the machine.

## 2. Architecture

```
 11+1 senses (read-only tails)                       surfaces
 ───────────────────────────────                     ────────────────
 JACKAL results + receipts   ─┐                       bar widget 󰧑 n
 SEKHMET / Custos / AEGIS     │                       cockpit (SUPER+SHIFT+B)
   attest-v1 chains           │      ┌─ mind.json     sia CLI
 WORLDLINE causal sqlite      │      │  (ACT-R, Hebb, agents via `sia context`
 pacman · journald · guardian ├──►  pulse (60 s)      ▲
 git reflogs · notifications  │      │                │ atomic JSON snapshots
 agent sessions (metadata)    │      ▼                │ status/graph/thoughts
 Quattro agents usage        ─┘   markdown corpus ────┘
                                  (git repo)   │
              deterministic thoughts ▲         ▼ sync + link extraction
              novelty · surprisal ───┘   gbrain brain (PGLite,
              workspace · integrity      local 768-d embeddings,
                                         typed knowledge graph)
 nightly 03:33 dream: consolidation → musing → take grading → gbrain cycle
```

**Single-writer discipline.** PGLite admits one process; the brainstem
daemon serializes every write. Out-of-process actors communicate through
append-only queues (recall touches, thought inbox) that the daemon
drains; queue claiming is by atomic rename so racing appends are never
lost. All cursor state becomes durable only after the corresponding
corpus writes succeed, and per-event ingestion into the cognitive layer
is gated on the same durability (bullet-level idempotence), so crash
replay can never double-count a memory.

**The corpus is the brain.** Every memory is a markdown page with YAML
frontmatter in a git repository; the database is a disposable index
rebuilt by one sync. Compaction is view-level: git history retains every
original byte, and the consolidation pass refuses to unlink any file it
cannot prove committed (`git ls-files` + clean porcelain, gated behind a
successful pre-consolidation commit).

**Truth-boundary contract.** Graph snapshots carry their own completeness
declaration — failed reads, truncation, aged-out counts, per-kind totals
— and the cockpit renders it as SOURCE HEALTH. A snapshot that fails
open visually announces its incompleteness (a lesson taken directly from
the Hermes Star Map review and the Microsoft Recall postmortem).

## 3. Evidence model

Four subsystem chains (Custos, SEKHMET, AEGIS, and SIA's own run ledger)
use the attest-ledger v1 format: 9-column TSV rows, length-prefixed
SHA-256 entry hashing, Ed25519 signatures, anti-rollback head pins. SIA
re-verifies each chain with *its own keeper's verifier* (Custos
additionally via the SPARK-proved `attest` binary) on a rolling cadence;
verification-state *transitions* — including pass→absent — become
thoughts, and failures are urgent. SIA's ledger records its own acts
(boot, pulse ingests, dreams, grades) under the same scheme, so the
memory system is auditable by the standards it audits others against.

Ledger rows and corpus pages are recall; the verifiers are the evidence
path. The distinction is preserved end-to-end: even exact mathematics in
memory remains labeled by the class its source declared.

## 4. The neurocognitive core

All mechanisms are deterministic; the single stochastic element (musing)
is seeded from `SHA-256(date ‖ ledger head)` and therefore replayable.

**4.1 Activation (ACT-R).** Each memory carries a touch history; its
base-level activation is `B_i = ln(Σ_k t_k^{-d})` with the canonical
`d = 0.5`, computed by the Petrov (2006) constant-space hybrid (five
exact recent timestamps plus a closed-form tail). Every touch carries a
source: world-originated touches (an organ observed something; the
operator asked) count at full weight, while the system's references to
its own products count at one-fifth — importance must come from the
world, not from self-talk. With power-law forgetting, importance is
learned from use without becoming an echo chamber.

**4.2 Hebbian bonding.** Edges strengthen only on typed co-occurrence
within a single event (an event and its own extracted entities) and on
co-recall in a query — never on mere clock adjacency across a pulse.
Nightly hygiene decays weights, sweeps dust, and caps node degree at 32
(weakest bonds pruned first): spreading activation needs a sparse graph,
not a hairball. Recall reshaping structure is reconsolidation
(Nader et al. 2000), implemented as touch-on-retrieval plus co-recall
bonding.

**4.3 Retrieval.** `sia ask` ranks by dense similarity (nomic-embed-text,
768-d, local) with two *gentle multiplicative tie-breakers*: graph
spreading (Personalized PageRank seeded by the dense hits, damping 0.5,
1/deg specificity, dangling mass returned to seeds) and activation, plus
origin weighting that demotes model prose below evidence. This shape is
benchmarked, not asserted: an earlier additive blend that could reorder
dense results LOST recall (hit@5 0.77 vs 0.92) and was replaced; on the
current 13-question ground-truth set the tie-breaker blend matches dense
(hit@5 0.92) and does not yet beat it — the graph earns rank influence
only when an eval table says so (see §9). Score-threshold abstention was
also measured and found unidentifiable on this stack (present/absent
score distributions overlap); abstention therefore lives in the judge
and the answer's truth-boundary footer, not in a cutoff.

**4.4 Novelty (encoding gate).** Following Lisman & Grace (2005), novelty
raises encoding strength: first-ever entities (+0.40), 30-day returns
(+0.20, measured against a last-seen timestamp refreshed on *every*
sighting), new (organ, event-type) shapes (+0.20), and a von Restorff
isolation bonus (+0.15) for events unlike ≥90 % of their pulse batch.
Scores ≥0.6 emit explainable novelty thoughts naming the firing terms.

**4.5 Surprise.** Desktop evidence is bursty, so no Poisson model and no
"bits" are claimed. Each (organ, weekday/weekend × 6-hour band) cohort
keeps the empirical distribution of observed hourly counts (120-sample
ring). A spike is a count above everything the band has produced in ≥30
observed hours; an absence fires only for paced bands — active in ≥90 %
of their observed hours — when an hour closes at zero. Silent hours are
closed retroactively, so silence remains an observable and bursts join
the band and stop being surprising. The thought reports exactly what was
measured: the count, the band's previous maximum, and the sample size.

**4.6 Attention (Global Workspace).** Seven slots; candidates are
memories touched in 24 h scored by activation plus arousal; ignition
threshold, lateral inhibition (two slots per bucket), and incumbent
hysteresis yield stable, diverse conscious contents. The workspace is
broadcast: it appears in the cockpit, biases retrieval seeds, and
anchors context packs.

**4.7 Consolidation (sleep).** Nightly, day-memories older than 14 days
compact into weekly epoch pages — merged with any existing epoch, never
overwritten — preserving summed counts, dated exemplars, and the link
structure (gist), per complementary-learning-systems theory. The
McGaugh/Kensinger arousal rule ("flashbulb"): days tagged with
safety-class arousal (crash, coredump, integrity failure, refusal,
collapse, failure) are never compacted.

**4.8 Mind-wandering (DMN).** Once nightly, a seeded walk selects two
high-activation memories from different regions with no direct edge and
searches (≤4 hops) for a connecting path, preferring obscure routes.
The result is an *association* thought — explicitly a hypothesis, never
a causal claim.

## 5. Outcome learning

A **take** is a falsifiable prediction — claim, holder, confidence
p ∈ (0,1), deadline, domain — stored as a corpus page (part of the
graph, embedded, recallable). Takes originate from the user, from
ponder syntheses (the model proposes at most two per reflection in a
strict grammar), or from future deterministic rules. When due, a take
is judged against deterministically gathered evidence (semantic recall,
entity-matched organ records, and thoughts since creation) by the
configured judge under a strict rubric:
TRUE / FALSE / UNRESOLVABLE, citations required, guessing forbidden — a
failed evidence lookup yields UNRESOLVABLE by construction. Scoring is
arithmetic: Brier `(p − o)²`, aggregated per domain into a calibration
record (mean Brier, directional accuracy) surfaced in the CLI, the
cockpit, and — closing the loop — in ponder's own context, so future
confidence is informed by measured past performance. The nightly dream
grades up to three due takes; every grade is a signed ledger row.

## 6. Model policy

The cognitive core is deterministic. Exactly one chat model exists in
the system — **the operator-configured judge**, their own Codex or
Claude CLI subscription (reference deployment: GPT-5.6-Sol at maximum
reasoning), invoked in a read-only, ephemeral sandbox — and it holds
exactly two offices: *reflective synthesis* (ponder/deep) and
*evidence judge* (take grading). Its output is stored under labeled
types (`synthesis`, grade sections) naming the model, and never
inherits deterministic authority. Offline chat models are excluded by default (the only local model is
the embedding encoder), keeping quality of judgment tied to the
operator's chosen frontier model rather than whatever fits in RAM.

## 7. Privacy design

The formative negative example is Microsoft Recall: content capture
creates an attack surface no downstream cryptography repairs, and
post-capture secret filters leak. SIA therefore ingests **records, not
content**: subsystem ledgers, receipts, logs, reflogs, notification
summaries, and session *metadata* (titles, counts, timestamps — never
message bodies), and by policy never reads private keys, clipboards, or
password stores. Everything remains on the machine; embeddings are
computed locally; the update phone-home in the indexing engine is
disabled. Deletion is never silent: consolidation is git-recoverable and
ledgered.

## 8. Implementation

Host: Omarchy Linux 4.0 "Quattro" (aarch64). The daemon
(`sia-brainstem`, Python stdlib) pulses at 60 s; per-op PGLite cost
≈0.6 s on this hardware; a full initial embedding of a 150-page corpus
took ~6 minutes on CPU. The UI is a Quickshell plugin (`khephri.sia`):
a bar widget and a full-screen layer-shell cockpit (Canvas force layout
with radial-time constraint; ~260-node display cap with truncation
declared). Indexing is gbrain 0.47.6 with a custom schema pack (organ /
event-day / epoch / thought / synthesis / take / unit / package /
project types, typed link verbs), graph-aware retrieval mode, and
Ollama `nomic-embed-text` embeddings served at 127.0.0.1:11434.

## 9. Verification

The build was adversarially reviewed twice by independent agent panels
(find → verify-with-reproduction): 17 confirmed defects in the base
system (notably: a sliding-window ledger defeating positional cursors;
cursor persistence preceding durable writes; YAML-breaking titles) and
12 in the cognitive core (notably: an unreachable absence-surprise
branch; a novelty test measuring first-sighting age rather than
absence; epoch pages overwritten rather than merged; unlink without
committed-ness proof; PPR dangling-mass leakage) — all fixed and
re-verified, several by sandboxed reproduction (two-run epoch-merge
idempotence; simulated silent-organ absence detection). End-to-end
checks are live-fire: a real JACKAL call traced from MCP through ledger,
pulse, corpus, graph, and widget within one heartbeat; first take
graded TRUE at Brier 0.01 while its sibling returned an honest
UNRESOLVABLE when evidence recall failed.

## 10. Nomenclature

The cognitive-science names in §4 are ancestry, not warrants. Every
mechanism must survive a rename test — describable purely by behavior:
importance decays with time and grows with world-originated use; the
system's references to its own products count one-fifth; memories that
occur together or are recalled together become easier to reach from one
another; silence of a paced organ is an event; high-severity days are
not summarized away while they are rare; the model may summarize and
grade, never mint facts. If a mechanism cannot be defended in that
vocabulary, it is not ready, whatever the citation says.

## 11. Limitations and future work

Typed-NER edge inference is currently limited by the indexing engine's
entity gazetteer (person/company types); SIA's domain regexes are
declared but under-utilized. Stability decay and SM-2 rehearsal are
specified but not yet wired. The calibration loop has one graded take —
statistical claims about judgment await a population. A LongMemEval-
style self-benchmark (auto-generated QA from the signed ledgers, with
abstention as a scored answer) is designed but unbuilt. An MCP memory
surface for resident agents awaits a multi-writer story compatible with
PGLite's single-owner constraint. Publication to the community plugin
directory (omarchyplugins.com) requires only a public repository; the
manifest, docs, and graceful-degradation states already conform.

## References

Anderson & Schooler (1991); Petrov (2006), *Computationally efficient
approximation of the base-level learning equation in ACT-R*; Collins &
Loftus (1975), *A spreading-activation theory of semantic processing*;
Nader, Schafe & LeDoux (2000), *Nature* 406; Lee, Nader & Schiller
(2017), *TiCS* 21; Lisman & Grace (2005), *Neuron* 46; McGaugh (2004),
*Annu. Rev. Neurosci.* 27; Kensinger (2004; 2009); McClelland,
McNaughton & O'Reilly (1995), *Psych. Rev.* 102; Buzsáki (2015),
*Hippocampus* 25; Yassa & Stark (2011), *TiNS* 34; Davis & Zhong
(2017), *Neuron* 95; Friston (2010), *Nat. Rev. Neurosci.* 11; Dehaene
et al., Global Neuronal Workspace; Gutiérrez et al. (2024), *HippoRAG*,
NeurIPS; Park et al. (2023), *Generative Agents*; Zep/Graphiti (2025),
arXiv:2501.13956; Letta sleep-time compute, arXiv:2504.13171; MemoryBank
(AAAI'24); Woźniak, SM-2; gbrain (garrytan/gbrain) and gbrain-evals;
Omarchy 4.0 "Quattro" release notes; Microsoft Recall security
postmortems (2024–2026). Full annotated research reports accompany the reference
deployment's research archive.

---

*This document describes the system as deployed and verified on
2026-08-29. The user's guide is `MANUAL.md` alongside this file.*
