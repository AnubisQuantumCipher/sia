# SIA: An Evidence-Grounded Neurocognitive Memory for a Linux Desktop

**Khephri Labs · open source (MIT) · 2026-09-01 · v1.5**

*Measurements and deployment details herein are from the reference deployment: an Omarchy Linux 4.0 (aarch64) machine running the full optional-integration set.*

---

## Abstract

SIA ("the Omarchy Brain") is a persistent, associative, self-consolidating
memory system for an operating system. It fuses the machine's existing
evidence streams — cryptographically chained subsystem ledgers, bounded
computation-record observations, package and journal logs, agent-session
metadata — into a single knowledge graph over a git-versioned markdown
corpus, indexed by gbrain (PGLite + local embeddings). On top of storage
it implements a deterministic neurocognitive layer drawn from the memory
literature: ACT-R activation, Hebbian co-activation, spreading-activation
retrieval (HippoRAG), dopaminergic novelty gating, surprisal against
learned baselines, a Global-Workspace attention model, sleep-cycle
systems consolidation with flashbulb preservation, and outcome learning
via Brier-scored predictions. Retrieval additionally uses non-destructive
stability decay, and important memories receive transaction-safe scheduled
rehearsal. An optional language model — disabled by default and available only
through an explicitly configured, tool-isolated Claude CLI model — is confined
to two labeled roles, reflective synthesis and
strict evidence judging, and never writes unlabeled memory. The design's governing
principle is inherited from the host machine's evidence culture: every
recall answer declares its origin and truth boundary, absence of recall is not
evidence of absence, and a system that fails open must say so.

## 1. Motivation

Supported Omarchy/Arch desktops produce package, journal, git, notification,
and agent-session evidence streams; SIA's built-ins observe the sources that
exist on the current deployment, while missing/disabled sources emit nothing.
Config-driven custom senses can read the operator's non-secret evidence
records. The reference deployment goes further: it runs a family of
evidence-producing subsystems:
JACKAL (a deterministic mathematical kernel whose own front door can produce
and verify multiple declared result classes and retained certificates), SEKHMET (a
SPARK-proved self-healing fabric), Custos (a proof-carrying file
custodian), AEGIS, WORLDLINE (a branchable-reality system with a causal
event store), omarchy-guardian, plus pacman, journald, git, desktop
notifications, and Omarchy Quattro agent usage meters. Each stream has its
own provenance and assurance boundary;
none is queryable together. SIA's JACKAL sense does not call that front-door
verifier: it observes the bounded convenience result ledger and receipt
filenames as `derived`, unverified recall, excludes them from grading evidence,
and suppresses categorical assurance inherited from legacy pages. Artifact
presence therefore says nothing about its mathematical verification status.
The operating system had evidence but no
memory: no way to ask *what happened*, *what connects*, *what is
unusual*, or *was I right*.

SIA is that memory. Its goals, in order: (1) fidelity — never
misrepresent the evidence class of what it knows; (2) association —
connect across streams the way recall connects across experiences;
(3) learning — importance and rhythm adapt with use, while judgment stays
measured against outcomes;
(4) locality — the memory of a machine belongs on the machine.

## 2. Architecture

```
 enabled base + optional + custom senses             surfaces
 ───────────────────────────────                     ────────────────
 JACKAL record/file observations ─┐                  bar widget 󰧑 n
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
 nightly 03:33 dream: consolidation → rehearsal → musing → grading → slug-drift tripwire → gbrain cycle
```

**Single-owner discipline.** PGLite admits one connection. Every
SIA-managed daemon, CLI, benchmark, and MCP-derived read enters through the
same advisory cross-process lease. Whole pulse/dream cycles and explicit
operator corpus mutations share a separate transaction lease, and a lifetime
brainstem lease refuses a second resident daemon. The brainstem alone
materializes agent notes. Agent notes do not share a mutable inbox: each caller
publishes one immutable mode-0600 request through a fixed owner-private staging
slot outside the spool, and the daemon removes that request only after the
labeled model-origin page is committed and the index sync succeeds. Recall
touches use a bounded atomic whole-file RMW producer and retain their
claim-by-rename consumer queue. An unterminated legacy physical record is
digest-bound as a refusal before its suffix is repaired; complete malformed
records remain claimed refusal debt.
This discipline cannot constrain an unrelated program that bypasses SIA and
opens the database directly, which is why owner errors remain visible rather
than being treated as proof of serialization. All cursor state becomes durable
only after the corresponding corpus writes succeed, and per-event ingestion
into the cognitive layer is gated on the same durability (bullet-level
idempotence), so crash replay does not double-count a memory.

**The corpus is the brain.** Every memory is a markdown page with YAML
frontmatter in a git repository; the database is a rebuildable derived index,
but rebuilding it is an installer-controlled bootstrap rather than a delete-
and-sync shortcut. A genuinely absent store is initialized off-path, source
registration and sync run under the lifecycle/PGLite/corpus leases, the result
is front-door health-probed, and only then is its generation published.
Compaction is view-level: git history retains every
original byte, and the consolidation pass refuses to unlink any file it
cannot prove committed (`git ls-files` + clean porcelain, gated behind a
successful pre-consolidation commit). Agent and operator notes are explicit,
origin-labeled prose exceptions to evidence-backed event memory; they are
recallable context, not witnesses.

New persisted origin metadata has three canonical classes: `evidence`,
`derived`, and `model`. Outside the bounded compatibility lanes below,
missing, invalid, duplicated, or otherwise ambiguous legacy metadata crosses
an explicit `legacy-unlabeled` read boundary: it is
never promoted to evidence and receives the same conservative retrieval weight
as `model`. Judge grades, ponder syntheses, take-proposal notifications, and
agent/operator notes are model output and persist as `model`; deterministic
Brier recomputation and signed
transition handling are separate derived operations, not a relabeling of the
verdict.

There are two bounded compatibility exceptions to the legacy-unlabeled rule.
During the v1.3 first-light pulse, a current-schema pre-origin open take is
migrated to `origin: derived`, while a resolved one is migrated to
`origin: model` and its historical judge explanation is rendered as inert
prose. Pages outside the current schema are admitted only when every byte-level
shape check matches the v1.2 producer; those pages are compatibility-normalized
and retain source-field digests plus corpus git history. A malformed legacy
graded page refuses the cutover rather than receiving a guessed origin.

The second exception exists before corpus publication. A legacy shared thought
inbox can contain producer rows with neither queue identity nor queued time.
After one bounded, no-follow, stable-file read, SIA derives each identity from
the captured bytes, file modification time, and row position and derives the
queued timestamp from that same file time. Renaming the inode into the draining
claim therefore preserves the result across retry. Fully modern and
metadata-free legacy rows may coexist and are handled row by row. When origin
is absent, known `note`, `ponder`, and `grade` prose plus `take` proposal
notifications map to `model`, while other admitted historical kinds retain the
old deterministic `derived` default; that compatibility default never maps to
`evidence`. An explicitly
present canonical origin is validated and preserved. Partial queue metadata,
unknown fields, or malformed modern identity on any row refuses the batch.

This is a publication protocol, not an in-place relabel. An owner-private
journal under `~/.local/state/sia/take-migrations/` binds source and target
digests. The ledger accepts the exact target under `MIGRATE:take-origin` with
kind `model-inert-v1` or `legacy-v1-normalize` before `sync_needed` is made
durable and the page is atomically replaced. Pulse then commits the corpus,
syncs PGLite, exports the graph, and clears the marker last. Crash recovery
recognizes the exact signed target instead of appending a duplicate transition.
Memory-dependent CLI and MCP reads refuse throughout the cutover.

The migration is one specialization of a generalized publication invariant.
Every shipped SIA corpus writer — `pulse`, `dream`, `take`, `intent`, `grade`,
and `ponder` — runs under the corpus transaction lease and durably establishes
`sync_needed` publication debt before a page is created, rewritten, or
unlinked. The low-level page writer and consolidation cleanup invoke a scoped
write-ahead barrier, while take/intent/grade transitions invoke an explicit
callback. The marker clears only after git accepts or verifies the corpus,
PGLite sync succeeds, and graph export succeeds; any failure preserves debt.

The pulse sequence reservation and its heartbeat share that lease, preventing
a whole-memo reservation from overwriting publication state. DREAM inserts
settlement barriers between memory-backed phases and around each grade, so a
later phase never queries pre-mutation PGLite or graph state. Readiness also
refuses any pending journal in
`~/.local/state/sia/grade-transactions/`. Each gated CLI request holds the
corpus lease from the readiness predicate through its returned result, and an
MCP memory request inherits that subprocess boundary. The predicate and answer
therefore observe the same corpus generation.

The predicate is also exposed directly as `sia ready`: under the corpus-owner
lease it emits a stable ready/not-ready line and maps that result to process
success/failure. Installer first light runs one fatal `SIA_BACKFILL=1` pulse,
which advances the take and intent authorities together through scan/sweep and
their paired audit until neither is pending (or a finite generation ceiling
refuses), then calls the newly published readiness gate before any later
integration or activation. A successful pulse exit is therefore necessary but
not sufficient for installation success.

**Truth-boundary contract.** Graph snapshots carry their own completeness
declaration — failed reads, display omission counts, aged-out counts, per-kind totals
— and the cockpit renders it as SOURCE HEALTH. A snapshot that fails
open visually announces its incompleteness (a lesson taken directly from
the Hermes Star Map review and the Microsoft Recall postmortem). Corpus read or
edge-export gaps therefore produce a partial snapshot. If graph publication
itself throws, the pulse keeps the error visible and signs its ingest result as
`graph-fail` rather than claiming graph success.
The exporter does not enumerate the resident corpus into memory. It advances
an owner-private, generation-bound directory cursor, retains only the bounded
cockpit candidate window, and then opens only those selected pages no-follow
under their observed digests for edge extraction. Supported corpus writers
restart the projection durably before mutation. The corpus-root `README.md` is
bootstrap/repository metadata rather than a canonical page; the scanner skips
that exact root name. Upgrade recovery removes only the byte-exact obsolete
README failure emitted by the former projector, leaving all candidates and
unrelated failures intact. A publication retains the corpus lease while it
drains successive individually bounded cursor pages; a finite aggregate
generation ceiling converts churn or excessive size into retained debt. Thus
an active corpus larger than one page cannot alternate indefinitely between a
partial recovery pass and the next publication's conservative restart. An incomplete cursor,
capacity refusal, changed generation, or selected-page mismatch is therefore
debt, never an absence claim; publication and readiness remain closed.
Once that authoritative scan is complete, deterministic node and unique display-edge
display-cap omissions are nonfatal: the snapshot is complete-with-omissions,
reports both counts, and explicitly says that omissions imply no absence. Full
recall remains in the corpus-backed PGLite index. First-light may drain
successive bounded batches only up to its fixed convergence ceiling.
For take pages, SIA's own graph exporter independently ignores everything after
the canonical grade heading. That defense prevents a legacy judge explanation
from minting SIA graph edges even before migration, but gbrain still indexes the
raw corpus and its backlinks; inert migration plus the PGLite readiness gate is
therefore required to reconcile every retrieval surface.

## 3. Evidence model

SEKHMET, AEGIS, and SIA's own run ledger use attest-ledger v1: 9-column
TSV rows, length-prefixed SHA-256 entry hashing, Ed25519 signatures, and local
head pins that detect ordinary truncation and partial rollback. Custos retains
its earlier valid 9-column Custos v1 grammar: canonical Unix timestamps,
Ed25519 over `custos-v1\t` plus the first eight tab-separated fields, a genesis
predecessor of `SHA-256("custos-genesis-v1")`, and each later predecessor and
head equal to SHA-256 of the complete previous signed TSV line without its
newline. A same-user attacker who coordinates rollback of both ledger and pin
is outside that tripwire's claim. SIA re-verifies each chain with *its own
keeper's verifier* (Custos via the SPARK-proved `attest` binary) on a rolling
cadence;
verification-state *transitions* — including pass→absent — become
thoughts, and failures are urgent. SIA's ledger records its own acts
(boot, pulse ingests, dreams, grades) under attest-ledger v1, so the
memory system is auditable by the standards it audits others against.
After keeper verification, a base lifecycle sense projects signed rows other
than `PULSE:*` and `DREAM:bench` into retrievable `events/sia/` pages. The
exclusions prevent an ingest/evaluation feedback loop; the signed ledger
remains ground truth and the pages are its local recall projection.

Ledger rows and corpus pages are recall; the verifiers are the evidence
path. The distinction is preserved end-to-end: even exact mathematics in
memory remains labeled by the class its source declared.

## 4. The neurocognitive core

Given the recorded state and captured operation timestamps, all mechanisms are
deterministic. The single stochastic element (musing) binds activation to the
dream transaction timestamp and seeds its shuffle from
`SHA-256(date ‖ ledger head)`, making the selection replayable.

**4.1 Activation (ACT-R).** Each memory carries a touch history; its
base-level activation is `B_i = ln(Σ_k w_k·t_k^{-d})` with the canonical
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
origin weighting that demotes model prose below evidence and treats
`legacy-unlabeled` with the same conservative weight as `model`. This shape is
instrumented, not asserted: on the historical 13-probe heuristic slug set, an
earlier additive blend scored slug match@5 0.77 versus 0.92 and was replaced;
the tie-breaker blend matched dense at slug match@5 0.92 and did not beat it. Those probes
are a retrieval-drift tripwire, not answer ground truth. The shipped runtime
does not automatically gate PPR on that nightly tripwire: graph influence is
the tested release-selected policy, while a later tripwire regression is an
operator-visible warning that must be investigated before a future policy is
accepted (see §9). Score-threshold abstention was
also measured and found unidentifiable on this stack (present/absent
score distributions overlap); abstention therefore lives in the judge
and the answer's truth-boundary footer, not in a cutoff.

**4.4 Novelty (encoding gate).** Following Lisman & Grace (2005), novelty
raises encoding strength: first-ever entities (+0.40), 30-day returns
(+0.20, measured against a last-seen timestamp refreshed on *every*
sighting), new (organ, event-type) shapes (+0.20), and a von Restorff
isolation bonus (+0.15) for events unlike ≥90 % of a pulse batch containing
at least five events.
Scores ≥0.6 emit explainable novelty thoughts naming the firing terms.

**4.5 Surprise.** Desktop evidence is bursty, so no Poisson model and no
"bits" are claimed. Each (organ, weekday/weekend × 6-hour band) cohort
keeps the empirical distribution of observed hourly counts (120-sample
ring). After ≥30 observed hours, a spike requires both a new band maximum and
at least five events; an absence fires only for paced bands — active in ≥90 %
of their observed hours — when an hour closes at zero. Either alert starts a
six-hour per-band cooldown. Silent hours are
closed retroactively, so silence remains an observable and bursts join
the band and stop being surprising. The thought reports exactly what was
measured: the count, the band's previous maximum, and the sample size.

**4.6 Attention (Global Workspace).** Seven slots; candidates are
memories touched in 24 h scored by activation plus arousal; ignition
threshold, lateral inhibition (two slots per bucket), and incumbent
hysteresis yield stable, diverse conscious contents. The workspace appears in
the cockpit and anchors `sia context` packs; `sia ask` ranking remains seeded
by its dense retrieval hits.

**4.7 Consolidation (sleep).** Nightly, day-memories older than 14 days
compact into weekly epoch pages — merged with any existing epoch, never
overwritten — preserving summed counts, dated exemplars, and the link
structure (gist), per complementary-learning-systems theory. The
McGaugh/Kensinger arousal rule ("flashbulb"): days tagged with
declared safety-class arousal (crash, coredump, integrity failure, refusal,
collapse, failure) remain verbatim. Compacted originals remain in git.
Discovery is a crash-resumable bounded directory generation, not a whole-tree
glob. Before any epoch write or unlink, SIA durably claims the admitted day's
complete bounded shard set and exact byte digests. Replay permits a missing
claimed shard only when the epoch already carries that exact source lineage;
new or changed shards refuse. A partial scan never proves deletion, and scan
or claim debt remains visible to readiness. The eligibility cutoff is an
immutable property of the incomplete generation: UTC-day rollover cannot
restart its prefix, and newly eligible days enter only after the prior cursor
and claims have converged.

**4.8 Mind-wandering (DMN).** Once nightly, a seeded walk selects two
high-activation memories from different regions with no direct edge and
searches (≤4 hops) for a connecting path. Candidate routes are ordered by
their summed learned edge traffic, then length and slug order, making the
low-traffic preference deterministic across processes.
The result is an *association* thought — explicitly a hypothesis, never
a causal claim.

**4.9 Stability and rehearsal.** Each tracked node and learned edge carries
a stability horizon `S`; its retrieval lens is `R = exp(−Δt/S)`. Touches,
arousal, and novelty can lengthen that horizon. Pins hold `R = 1`, and an
edge below the declared retention threshold stops contributing to graph
spreading. Stability is capped at 36500 days; SM-2 intervals use the same cap,
and ease is capped at 5.0. Those are operational overflow bounds, not memory
science claims. None of these transitions deletes or rewrites corpus evidence.

Operator-pinned or high-arousal pages—including pages raised by safety-class
and urgent signals—receive an SM-2 review record. The nightly scheduler uses
SIA interaction signals as explicit quality adapters:
a post-review user ask/rehearsal signal maps to `q=5`, a
thought/ponder/muse/grade reference maps to `q=4`, and no qualifying signal
maps to `q=0`. These are SIA interaction classes, not human-memory
measurements. It
then applies the published ease/interval recurrence and re-embeds
the page: later intervals use the incoming E-Factor, the response updates ease
for the next repetition, and a quality below three restarts the repetition
sequence after that ease update. The scheduler state, recall touch, and incident-edge reinforcement
commit only after that same page is successfully re-embedded; a missing page
or failed engine call remains due. Removing the last pin removes a pin-only
review record; a qualifying high-arousal signal remains independently eligible.
These quality tiers are system-event proxies, not observed human recall
scores, and the mechanism makes no claim that it improves human memory or
semantic answer quality.

Any currently pinned page and every safety-tagged day remain verbatim during
systems consolidation. Removing a pin also removes its pin-only review record,
so the scheduler does not retain a due record for a day page that may later be
consolidated.

## 5. Outcome learning

A **take** is a falsifiable prediction — claim, holder, confidence
p ∈ (0,1), deadline, domain — stored as a corpus page (part of the
graph, embedded, recallable). Takes originate from the user, from
ponder syntheses (the model proposes at most two per reflection in a
strict grammar), or from deterministic evidence templates: a successful
fabric heal auto-proposes "this heal will hold — no repeat within 7
days," with confidence `clamp(held/judged, 0.55, 0.95)` computed from
that action's own corpus history (prior 0.70 when fewer than three full
windows exist). The history source is the sekhmet day pages, so its
horizon is the episodic window plus verbatim (flashbulb) days — under
that horizon the prior dominates by construction, which is the honest
behavior for a young evidence base. Every origin lands in the same proposal queue; nothing
becomes a take until a human runs `sia take --accept`. When due, a take
is judged against deterministically gathered evidence (semantic recall and
entity-matched event/epoch organ records; model notes, syntheses, takes,
intents, entity descriptions, and thoughts are excluded) by the
configured judge under a strict rubric:
TRUE / FALSE / UNRESOLVABLE, citations required, guessing forbidden. A
completed lookup with insufficient admitted evidence can yield UNRESOLVABLE;
a failed or malformed retrieval refuses before the judge, persists no grade,
and leaves the take open. A deadline must be
strictly after its UTC commit date, and the judge prompt is blinded to the
forecast confidence so it cannot anchor on the predicted probability. Scoring is
arithmetic: Brier `(p − o)²`, recomputed from each stored decimal confidence
and binary outcome rather than trusting the cached score. The per-domain and
overall calibration record carries its population boundary: single cases and
small series are named as such; UNRESOLVABLE and internally inconsistent rows
are counted but excluded; reliability bins are withheld below their declared
display floor. The record marks monitoring eligibility only at 30 resolved
grades with at least 5 in each outcome class. Case/aggregate metrics remain
visible below that gate with sparse/single-case labels. Those constants are
anti-overclaiming machine-readable display-policy gates, not a power
calculation: even after the gate, the stream remains an
operator-selected, model-assisted descriptive population with no confidence
interval, significance claim, or warrant about world truth. The record is
surfaced in the CLI, the cockpit, and — closing the loop — in ponder's own
context. The nightly dream grades up to three due takes; every grade uses a
durable transaction journal and an exact content-bound signed ledger row.
The published take becomes `origin: model`, and the model explanation is stored
as `Model justification (inert prose): ...`; deterministic Brier computation
and signed transition handling remain separate derived operations. The
signature authenticates the authorized target and publication order. It does
not prove the verdict or the historical judge prose true.

The natural-history implementation keeps the corpus as the sole semantic
authority while removing whole-corpus work from the resident loop. Each
supported take or intent create/mutation first has a durable intent; after the
page transition, an idempotent event updates a digest-bound direct record, a
capped open-set projection, and an append-only cursor-paginated catalog.
Overall calibration is an exact Decimal sufficient-statistic projection;
domain statistics are sharded and their domain catalog is paginated. Every
page repeats the complete overall population totals and exclusions; only the
domain rows are cursor-paginated. Only a settled grade whose exact signed
`GRADE:take` target is observable contributes to scored totals. UNRESOLVABLE,
malformed, inconsistent, and unsigned legacy resolutions remain explicitly
counted outside the score denominator.

Legacy pages are admitted through a fixed resumable baseline. Its Linux
directory cookie is bound to device, inode, size, modification time, and change
time; a changed generation restarts conservatively rather than seeking into a
possibly reordered directory. Supported mutation journals and exact event
identities override or deduplicate observations made by the baseline. A
second no-addition pass closes the debt. Readiness consults bounded transaction
and baseline metadata, while direct/list reads revalidate selected page
digests. A recurring authority generation subsequently performs a bounded
source scan followed by a bounded catalog sweep. Live direct rows are marked
with that generation; unseen or replaced identities are retired by a durable
event that tombstones the catalog target and subtracts its exact overall,
domain, and open-set contribution. Replay guards on event sequence and domain
sequence make a crash before or after subtraction idempotent. Page edits are
reprojected from corpus bytes, and a resolved contribution is rebuilt only
when the exact edited target is present in the signed grade ledger. Only a
stable completed scan/sweep publishes a directory checkpoint; readiness and
calibration refuse incomplete, changed, or errored checkpoints. Thus long
historical corpora affect the number of bounded reconciliation pages or
history pages an operator may traverse, not the work of one pulse step. A
bounded incomplete consolidation generation retains its originating DREAM
transaction marker and ledger binding. Each later pulse recovers one bounded
unit of that same transaction, including exact claim application when reached;
the marker is applied, signed, and cleared only after source removals and the
post-removal scan converge, so readiness cannot expose a partial generation.
A ready state does not repeatedly launch that full generation. Instead, once
both take and intent authorities are ready, the paired scheduler's leader
persists a shared incomplete `audit` cycle, pinning each catalog limit and
directory checkpoint before it validates any direct row. The follower may join
or finish that active cycle but cannot immediately open another after
completion. Bounded calls advance only within each half-open pinned range; a
participant that finishes first remains ready until its sibling completes;
tombstones consume audit positions and readiness/calibration remain closed for
the whole phase. Global ready is republished only after separate reloads
observe both generations at their limits, unchanged catalog heads and
directory checkpoints, and no pending transaction. A mismatch or checkpoint change
starts fresh scan/sweep reconciliation. Directory additions, removals,
renames, and atomic replacements therefore invalidate the checkpoint
immediately. A same-inode in-place edit made after the final observation is an
explicit nonclaim until a later pinned audit reaches it; the design does not
claim instantaneous coherence against a hostile same-user writer.

**Prospective memory.** Intents are dated commitments stored as corpus
pages: the brain surfaces each one as its deadline approaches (a thought
inside 48 h, an urgent daily nag when overdue) and closes it only on the
operator's word. This is deliberately a due-date lane, not a cognitive
mechanism — no scores, no model, no auto-close — because the faculty a
historian lacks is remembering *to do*, and that faculty needs a diary,
not a dopamine analogue.

**Cross-organ coincidence.** When two or more organs exceed their own
empirical bands (spikes) in the same detection window, the coincidence
itself is recorded as a thought stating both counts and the pair's
sighting ordinal — never a cause. Simultaneous *absences* are
deliberately not paired: a suspend would pair every organ at once. Pair history accumulates deterministically;
a future hypothesis lane would build on it only behind a measured gate,
per the hypothesis-lane freeze rule stated in §11.

## 6. Model policy

The cognitive core is deterministic. No judge is selected by default. When the
operator explicitly opts in, exactly one chat model exists in the system —
**the operator-configured judge**, reached through the operator's configured
Claude CLI authentication/account/provider (whose normal billing/data terms
apply) with built-in tools, MCP, customizations, session
persistence, and project discovery disabled from an empty directory — and it holds
exactly two offices: *reflective synthesis* (ponder/deep) and
*evidence judge* (take grading). Its output is stored under labeled
types (`synthesis`, grade sections) naming the backend and explicit model
identifier, and never
inherits deterministic authority. Offline chat models are excluded by default (the only local model is
the embedding encoder), keeping quality of judgment tied to the
operator's chosen frontier model rather than whatever fits in RAM.
Codex CLI is refused as a judge because its documented read-only sandbox still
permits local reads and the installed CLI exposes no documented inference-only
switch. This is a confidentiality boundary, not a model-quality preference.

**What the judge is not.** A frontier model behind a VERDICT regex is
not a verifier. It keeps score on *what the judge said about what recall
returned* — never on reality. That is precisely why agents propose and
only a human commits, why judge-grade and ponder thoughts are origin-class
`model`, and why
abstention correctness is a first-class audited metric. No surface may
imply the machine is keeping honest score on the world; it keeps
auditable score on its own evidence, and says which. The transition journal and
Brier recomputation are deterministic, but neither turns the model verdict into
derived evidence.

## 7. Privacy design

The formative negative example is Microsoft Recall: content capture
creates an attack surface no downstream cryptography repairs, and
post-capture secret filters leak. SIA therefore ingests **records, not
content**: subsystem ledgers, receipts, logs, reflogs, notification
summaries, and session-file *metadata* (existence, size changes, freshness,
and an identifier — never message bodies). Built-in senses do not open private
keys, clipboards, or password stores. Operator-configured custom senses read
the exact file/field named in config and must not target secret/content stores.
Their optional inclusion and exclusion filters are finite literal alternatives,
not a general regular-expression evaluator; malformed filters refuse without
advancing that source cursor.
The distinct signed-ledger keeper reads
SIA's signing key only to authorize ledger transitions. The memory-content
runtime — ingestion, indexing, retrieval, and embedding — remains on the
machine; embeddings are computed locally and
the update phone-home in the indexing engine is disabled. The optional judge
is a separate operator-configured CLI path that may send explicitly recalled
context for synthesis or grading. MCP consumers are another
operator-configured trust boundary: they receive requested memory over stdio
and may forward it to their own model/provider, whose data terms apply.
Deletion is never silent: consolidation is
git-recoverable, and its enclosing dream transition is ledgered.

## 8. Implementation

Host: Omarchy Linux 4.0 "Quattro" (aarch64). The daemon
(`sia-brainstem`, Python stdlib) pulses at 60 s; per-op PGLite cost
≈0.6 s on this hardware; a full initial embedding of a 150-page corpus
took ~6 minutes on CPU. The UI is a Quickshell plugin (`khephri.sia`):
a bar widget and a full-screen layer-shell cockpit (Canvas force layout
with radial-time constraint; ~260-node display cap with non-absence omission
counts declared). Indexing is gbrain 0.47.6.0 with a custom schema pack (organ /
event-day / epoch / thought / synthesis / take / intent / note / unit /
package / project / skill types, typed link verbs), graph-aware retrieval mode, and
Ollama `nomic-embed-text` embeddings served at 127.0.0.1:11434.

Installation is a journaled publication protocol rather than an in-place copy.
Before the first dependency mutation, a launch-fence record binds the old CLI,
brainstem, and MCP launcher inodes, modes, and digests; those exact files are
then mode `000`. On retry, the lifecycle tombstone and strict, duplicate-free
journal authorize metadata-only inspection of those otherwise unreadable
generations. Single-file CAS recovery precedes CLI ownership preflight, and
runtime/CLI preflight is repeated after the fence so its changed mode/change
time cannot leave a stale publication token. Post-rename recovery accepts only
the journal-bound old/new digest and the rename-induced metadata transition;
independent replacements remain preserved refusals.

Tree CAS is descriptor-rooted and generation-bound. Parent, root, directories,
and regular files must be current-user-owned and non-group/world-writable;
regular files must have one link. Each symlink inode must itself be stable,
current-user-owned, and single-link. Tree CAS admits only relative symlinks
whose lexical target stays inside the tree and whose complete in-tree chain
resolves to such a safe regular file, binding link text and metadata into the
tree digest. A post-walk pass reopens every captured directory from the root
descriptor and rereads each link generation and target before and after
referent acceptance, so nested replacement refuses. This admits the official
Ollama archive's relative soname links while refusing absolute, escaping,
dangling, group/world-writable, hard-linked-file, and special entries. After
configuring gbrain, installation accepts only the
pinned CLI's exact combined `off` plus file/env-plane provenance output (or its
one exact DB-plane-shadowed form), so stderr drift is not hidden by a correct stdout
value.

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
checks are live-fire: a real JACKAL call traced from MCP through the
convenience ledger, pulse, corpus, graph, and widget within one heartbeat.
That trace tested pipeline wiring, not the call's mathematical assurance;
SIA deliberately labels the resulting memory unverified. The first take
graded TRUE at Brier 0.01 while its sibling returned an honest
UNRESOLVABLE after completed recall admitted no sufficient evidence.

One verification lesson postdates that record and belongs beside it.
Issue #3 (fixed in v1.5.1) showed that the nightly SM-2 rehearsal had
never graded a page in the project's life: its per-page embed omitted
``--source``, the real gbrain binary answered "Page not found" every
night, and the signed ledger recorded ``reviewed=0`` with nobody
reading it. Issue #2 had the same shape at the same boundary — the
installer's transactional protocol was right about every internal
invariant and wrong about gbrain writing an absolute ``database_path``.
Both defects were invisible to the adversarial panels above because
panels — like the unit suite — read code and stubs; a missing flag
against an external binary is not findable by reading. "Re-verified"
in this section therefore means verified against SIA's own invariants,
not against the live gbrain contract. That gap now has its own
instrument: ``tests/test_gbrain_contract.py`` runs every gbrain argv
shape SIA ships against the real pinned binary, locally and in CI,
so the next contract drift fails in the pipeline instead of in the
ledger.

The review-established invariants now ship as an executable suite
(`tests/`, run in CI on every push): cursor/replay semantics,
epoch-merge idempotence, ledger tamper-rejection, PPR mass
conservation, novelty-as-absence, empirical surprise including absence,
redaction fail-closure, exogenous/endogenous touch weighting, heal
hold-rate arithmetic, proposal deduplication, intent lifecycle, and
coincidence pair-counting. The dream additionally runs a nightly
retrieval-drift tripwire (a date-seeded sample of heuristic
corpus-conditioned slug probes) whose blend slug-match@5 trend the cockpit
plots. It can detect rank drift; it does not establish that a page contains a
correct answer. Its pre-bounded JSONL history is an explicitly derived display
surface: upgrade reads only a stable owned no-follow tail, discards incomplete
or malformed legacy rows, retains the declared recent complete window, and
publishes a legacy-truncation boundary. Such compaction cannot block settlement
of the separately durable DREAM receipt.

Runtime-loading tests install a process-wide temporary home-expansion fixture
before importing SIA. A structural regression check recognizes currently
enumerated syntactic runtime-loading patterns and checks the currently
enumerated runtime modules' import-time mutable paths beneath that fixture.
Those module and path enumerations must be extended when the code adds another
runtime module or import-time path constant. This contains covered test-state
side effects away from the resident brain; it does not prove that arbitrary
test code cannot explicitly name another path. The recovery suite also exercises
mode-`000` CAS interruption before and after rename, strict launch-fence
schema/path validation, safe and escaping/dangling tree symlinks, stable legacy
inbox identity across a claim rename, partial-metadata refusal, and the root
README graph migration.

The full memory instrument is a signed-ledger QA benchmark patterned after
LongMemEval's separation of extraction, temporal reasoning, knowledge updates,
and abstention. Signed ledger rows do not independently bind a session
identity, so SIA labels their cross-row count ability as multi-event
aggregation rather than multi-session reasoning. It is not LongMemEval and
makes no cross-system comparability claim. Each registered keeper first accepts its
own ledger. The generator observes ledger and verifier bytes through no-follow
descriptors and requires inode, size, modification metadata, and digests to
match across verification. This does not exclude a same-user in-place ABA
completed between observations. Questions carry byte-selected row, entry-hash,
ledger-head, chain-format, normalized source-excerpt answer witnesses, and
negative-witness provenance in a private key file. Custos
entry hashes and heads retain its signed-line SHA-256 semantics rather than
being reinterpreted as attest-entry hashes. Public questions omit answers,
categories, sources, observed timestamps, and provenance; their IDs are
answer-independent. The allow-listed public manifest also omits source slugs
and chain/file witness material, preventing a dated source path from answering
a temporal prompt. Public-question leakage checks canonicalize compatibility
Unicode and repeatedly decode common URL/HTML representations before comparing
private dates and slugs; conflict grouping and IDs use the same consumer view.
Controls, bidi-format characters, surrogates, and noncharacters cannot enter
public question fields, while private digest provenance continues to bind the
unaltered ledger. The public questions are bound by that manifest, while the
private key, complete evaluation manifest, and read-only MCP evaluation XML are
digest-bound by a mode-0600 private manifest outside the indexed corpus. A
deterministic stratified calibration
split fixes the answer/abstain threshold before held-out scoring. Missing
reader output is wrong, not an implicit abstention; only the literal
`ABSTAIN` answer earns abstention credit. An unidentified threshold is withheld,
not scored as universal abstention. For a present question, the returned chunk
must come from the bound page and contain its exact private excerpt witness;
page slug or title alone cannot score. Aggregate questions require every
contributing event excerpt. The built-in run reports evidence retrieval and
non-abstention proxies separately from normalized reader-answer scoring.
Every complete ledger/verifier snapshot, source-page set, parsed population,
candidate cross-product, serialized dataset, and answer input is subject to an
explicit implementation ceiling. Crossing a ceiling refuses the benchmark;
no signed chain or witness is truncated into a weaker claim.
Live evaluation re-opens every digest-bound source page before and after its
queries while holding SIA's corpus-owner lease; a changed or symlinked page
refuses the run rather than being scored against a newer slug target. The lease
coordinates SIA's own writers and is not a hostile same-user sandbox.
A fresh installer adds two keeper-signed facts only after establishing them:
`INSTALL:runtime ... prepared` and `INSTALL:index sia registered`. Their
verified `events/sia/` projections provide a standalone corpus with truthful
answer-bearing observations for a held-out bundle; they are not synthetic
benchmark labels. Pulse rows, benchmark-result rows, and terminal
`SOURCE:refuse` rows are excluded from projection so their own ingestion,
evaluation, or capacity handling cannot recursively mint replacements.

## 10. Nomenclature

The cognitive-science names in §4 are ancestry, not warrants. Every
mechanism must survive a rename test — describable purely by behavior:
importance decays with time and grows with world-originated use; the
system's references to its own products count one-fifth; memories that
occur together or are recalled together become easier to reach from one
another; stale associations lose retrieval influence without losing their
records; important pages rehearse only after a successful re-embedding;
silence of a paced organ is an event; declared safety-class days are
not summarized away; the model may summarize and
grade, never mint facts. If a mechanism cannot be defended in that
vocabulary, it is not ready, whatever the citation says.

## 11. Limitations and operational boundaries

**The hypothesis-lane freeze rule.** A mechanism in the cognitive lane
ships as deterministic policy with an instrument attached, and it is
promoted — or a new hypothesis lane is opened — only when its instrument
shows it beating the plain alternative, never on citation or plausibility.
The shipped example is §4.3's associative tie-breaker: graph influence is
the tested release-selected policy because it matched dense retrieval on
the historical probe set, and a tripwire regression is an operator-visible
warning that must be investigated before any future policy is accepted.
Anything without that measured showing stays behind its gate.

Typed edge inference now has two deliberately separate deterministic lanes:
gbrain runs its person/company entity gazetteer after each sync, while SIA
applies every declared domain regex to explicit corpus wikilinks at
Markdown-record scope.
The latter masks entity names before matching, leaves entity-description pages
and all `model` or `legacy-unlabeled` thoughts neutral, and permits typed
thought edges only when a safety-lane integrity/healing/crash/refusal thought
is explicitly persisted as `derived`. It prefers evidence-bearing typed
occurrences over generic duplicates, and degrades to `mentions` with a partial snapshot when the pack
cannot be safely loaded. That fallback is exclusive to the schema-regex lane;
a failure in gbrain's separate gazetteer/NER extraction fails brain sync and
retains publication debt instead of crossing lanes. These relations are lexical
inferences over explicit links, not proofs of the underlying relationship.
Calibration data remain operator-selected and
model-assisted; population growth improves descriptive monitoring but cannot
turn it into a representative sample. The signed-ledger benchmark is a local
regression population whose coverage depends on retained corpus pages; it is
not a substitute for the curated LongMemEval benchmark or a claim of reader
correctness. Its keeper verification authenticates the selected rows, not the
memory system's answers.

Stability and SM-2 are deterministic retrieval policies. Their quality tiers
encode SIA interaction classes, not human-recall observations, and this
release contains no controlled evidence that rehearsal improves answer
quality. Decay changes salience only; evidence retention continues to be
governed by the git corpus and its explicit consolidation rules.

The resident-agent MCP surface provides bounded tools and read resources
without giving clients a database handle. Its filesystem spool and advisory
owner lease coordinate SIA's own processes; they are not a hostile same-user
sandbox and cannot prevent third-party code from bypassing the project. The
corpus remains the source of truth and PGLite remains rebuildable. The
installer inspects named harness integrations but deliberately performs no
name-only add or remove: missing registrations receive an exact manual command,
while existing external registrations are preserved and guarded. Generic MCP
clients must likewise be explicitly configured with SIA's stdio server command.
The readiness gate likewise covers only SIA's memory-dependent CLI commands
and the MCP tools/resources that invoke them. Status remains available: its
readiness verdict is live, while its pulse/graph fields and the cockpit are
diagnostic last-published snapshots. Note/proposal writes may still queue, and
same-user code can read corpus files directly. Neither the gate nor a
`MIGRATE:take-origin` signature is an access-control boundary or evidence that
a model judgment is correct.
The server is dual-era: handshake-based revisions through `2025-11-25` and
the stateless `2026-07-28` discovery/per-request-metadata revision share the
same bounded dispatch, with batch framing enabled only for revisions that
define it.

The skills sense is intentionally shallower than a recursive skill search: it
admits only real skill directories directly contained by configured roots and
a real directly contained regular `SKILL.md`. Root, child, and manifest opens
use no-follow semantics, so symlinked entries are not cataloged. A bounded
manifest head is captured once and bound to before/after/current-path identity,
head digest, metadata, and its sanitized description. The exact capture drives
both the cursor diff and event text; no later rendering pass rereads the
manifest. The manifest identities are revalidated after the root generation,
and observed churn makes the root partial while retaining prior rows. This is
an ingestion boundary, not a validation of the skill's instructions or a
hostile same-user filesystem snapshot after the final observation.

The v1.5 plugin separates discoverability from lifecycle authority. Omarchy's
standard add-and-enable command clones, validates, and loads the QML, but its
plugin manager supplies no install, update, or remove hook for SIA's resident
runtime. When that runtime is absent or older than the plugin, the cockpit
renders a setup/update gate instead of ordinary controls. The gate discloses
the substantial local work; only an explicit operator action launches the
existing fail-closed installer in a visible terminal. QML load alone never
installs software. The gate clears only after the runtime version matches the
plugin and the installer atomically publishes its owner-private completion
record after a live `sia ready` check succeeds. That coordination record is
not signed evidence and does not replace a later live-readiness query.

SIA is listed in the Omarchy Plugin Marketplace, although its public catalog
entry may continue to say **Manual setup** until a maintainer removes the
existing registry override. Release preparation still requires a local
`omarchy plugin validate .` run against the exact public commit and the
approval-gated update workflow in the
[official publishing guide](https://plugins.omarchy.org/publish.html). A
directory listing provides discovery and manifest compatibility, not a
security review. Likewise, Omarchy's ordinary plugin removal deletes the QML
checkout but does not uninstall SIA's resident runtime or user service; the
SIA uninstaller remains the resident-runtime removal boundary, with its
separate purge mode governing attempted erasure of retained brain data.

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
(AAAI'24); Wu et al. (ICLR 2025), *LongMemEval: Benchmarking Chat
Assistants on Long-Term Interactive Memory*, arXiv:2410.10813; Woźniak,
[SM-2](https://super-memory.org/archive/english/ol/sm2.htm); gbrain
(garrytan/gbrain) and gbrain-evals;
Omarchy 4.0 "Quattro" release notes; Microsoft Recall security
postmortems (2024–2026). Full annotated research reports accompany the reference
deployment's research archive.

---

*This document describes the v1.5 system. The user's guide is `MANUAL.md`
alongside this file.*
