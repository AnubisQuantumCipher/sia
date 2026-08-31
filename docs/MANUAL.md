# SIA — The Omarchy Brain · User's Manual

*Sia: the Egyptian personification of perception, who rode the solar barque
beside Hu (utterance) and Heka (magic).*

SIA gives your machine an associative memory. Everything this computer
already records — package installs, journal errors, git commits, agent
sessions, notifications, and any log you point it at — flows into one
brain that remembers, connects, thinks, dreams, predicts, and is graded on
its predictions. You can watch it think, and you can ask it anything.

**Senses.** Base senses cover SIA's own signed lifecycle ledger, pacman, the
systemd journal, git repos under `~/Projects`, agent-session metadata,
desktop notifications, and Quattro's agent usage meters. The lifecycle sense
keeper-verifies the ledger before projecting non-`PULSE:*`, non-`DREAM:bench`
rows into `events/sia/`; those exclusions prevent ingestion/evaluation
feedback. Optional
integrations (signed evidence chains and subsystem ledgers such as
JACKAL, SEKHMET, Custos, AEGIS, WORLDLINE, omarchy-guardian) activate
automatically when their data exists. JACKAL is intentionally different from
the keeper-verified chain lanes: SIA observes its bounded convenience result
ledger and receipt filenames as unverified, `derived` recall and excludes them
from grading evidence. A retained receipt acquires no mathematical authority
inside SIA; it must be submitted to JACKAL's front-door verifier. And you can
point SIA at YOUR own
programs with custom senses in `~/.config/sia/config.json`:

```json
{ "custom_senses": [
    { "name": "myapp", "path": "~/logs/app.log", "type": "lines",
      "match": "ERROR|FATAL", "kind": "error", "tags": ["failed"] } ] }
```

`match` uses bounded literal alternatives separated by `|`, not regular
expressions. Invalid configuration is surfaced in SOURCE HEALTH and does not
advance that source cursor. A `jsonl` custom sense reads only its configured
`field`; a physical record missing that field advances only through a signed,
named refusal and never falls back to the raw object or unrelated fields.

---

## 1. Sixty-second start

| Do this | You get |
|---|---|
| Look at the top bar | 󰧑 + a number = the brain and today's event count |
| Click 󰧑 (or press **SUPER+SHIFT+B** if you opted into the binding) | the full-screen cockpit |
| `sia status` | one-screen state of the brain |
| `sia ask "what happened with wireplumber"` | semantic recall with citations |
| `sia think` | the brain's recent thoughts |
| `sia ponder` | a deep reflection over its memories by your configured judge model |

The brain's heartbeat (a "pulse") fires every 60 seconds. It dreams every
night at 03:33.

## 2. The cockpit

Summoned from the bar (or with SUPER+SHIFT+B after an install using
`SIA_INSTALL_KEYBINDING=1`); leaves with **Esc**, ✕, or
`omarchy-shell shell hide khephri.sia`.

**Header** — name, live state chip (`OK` / `THINKING` / `DEGRADED` /
`FAILED` / `STALE`), pulse number and age, clock.

**Left rail** (scrolls):
- **VITALS** — memories, links, events today, thoughts kept, mind traces
  (ACT-R–tracked memories) and Hebbian bonds.
- **PULSE ACTIVITY** — sparkline of the last ~90 heartbeats.
- **WORKSPACE — n OF 7 SLOTS** — the brain's *conscious contents*: the few
  memories that currently win the competition for attention (Global
  Workspace theory: ignition threshold, max two slots per organ,
  incumbents resist eviction). Click a slot to lock it in the graph.
- **ORGANS** — every sense, sorted by today's activity, with last-event age.
- **EVIDENCE CHAINS** — per-chain verification verdicts, SIA's own signed
  ledger head, last dream, and a **verify now** button that re-runs the
  real verifiers live.
- **BELIEFS** — open/due/graded predictions, their population-aware
  descriptive Brier record, and **SLUG DRIFT** — a nightly date-seeded
  heuristic slug-family match trend. It does not score reader answers; drift
  says to run the full signed-ledger `sia bench`.
- **INTENTS** — prospective memory: open commitments with their
  countdowns; overdue turns urgent. (Panel appears once you have one.)
- **SOURCE HEALTH** — the truth boundary: snapshot completeness, memory
  counts by kind, any sense errors or sync failures. If something failed,
  it says so here instead of quietly looking complete.

**Center — the living graph.** Time is radial: the cortex at the center,
organs on the inner ring, every memory at a radius set by its age (oldest
inner, newest at the rim) with faint day rings. Nodes glow when freshly
touched.

- **Hover** a node → its whole neighborhood lights and labels; everything
  else dims.
- **Click** a node → lock the selection (click empty space to release).
- **Inspector** (right rail) → the locked/hovered memory's title, type,
  age, in/out degree, and every connection with its type *and the text it
  was extracted from* — why the edge exists.
- **Typed edge labels** come from SIA's schema-pack domain regexes, evaluated
  deterministically on the Markdown record containing each explicit
  wikilink. Entity names are masked before matching, entity-description pages
  stay neutral, and `model` or `legacy-unlabeled` thoughts stay generic. Only
  thoughts explicitly persisted as `derived` and tagged for the
  integrity/healing/crash/refusal safety lanes may inherit a typed relation
  from their cited evidence sentence. A missing or
  invalid rule set degrades edges to
  `mentions` while SOURCE HEALTH marks the snapshot partial. This supplements,
  and does not replace, the person/company entity gazetteer that runs in a
  separate source-scoped NER pass after each sync.
  The installed rule file is
  `~/.local/share/sia/.gbrain/schema-packs/sia-pack/pack.yaml`; the installer
  ownership-marks its exact shipped content. A local modification is preserved
  and stops replacement unless you deliberately rerun with
  `SIA_REPLACE_SCHEMA_PACK=1` after reviewing the diff.
  A refused pack can still produce a diagnostic partial graph of explicit
  `mentions`, but it cannot satisfy the publication barrier. Repair or restore
  the pack and complete a pulse before memory-dependent reads become ready.
- **Graph failures stay visible.** Corpus-page read failures and other export
  gaps mark the snapshot partial in SOURCE HEALTH. If graph publication throws,
  the pulse exposes the error and signs `PULSE:ingest ... graph-fail` rather
  than reporting successful graph publication.
- **The graph window is incrementally projected.** Publication advances a
  durable no-follow corpus directory cursor, retains only the capped cockpit
  candidates, and rereads only those selected pages under their observed
  digests for edge extraction. A partial generation is never treated as an
  absence result. Supported SIA corpus mutations restart the projection before
  the page write or unlink; readiness stays closed until the replacement
  generation is fully scanned without refusal. Intentional node and unique
  display-edge cap omissions are then a complete snapshot, with separate omission
  counts and an explicit non-absence boundary; PGLite remains the full recall
  surface. Installer first-light can drain successive bounded batches, but
  refuses at its fixed convergence ceiling rather than looping indefinitely
  under corpus churn.
- **Legend chips** are filters — click `memory`, `thought`, `entity`… to
  hide that kind.
- **⟲ replay** (or the **R** key) — animate the brain growing from its
  oldest memory to now.

**Right rail** — the inspector (above) and the **THOUGHT STREAM**, the
brain's inner monologue, newest first, urgent items in red.

**Footer** — latest-thought ticker and the key map.

## 3. The CLI

Everything lives under one command: `sia`.

### Asking and reading

```
sia status                    # one-screen state
sia ask "question"            # semantic recall: dense embeddings seeded
                              #   through the knowledge graph (spreading
                              #   activation) and re-ranked by ACT-R
                              #   activation. Recalling STRENGTHENS the
                              #   memories returned (reconsolidation).
sia recall <slug>             # read one memory page verbatim
sia think                     # recent thoughts
sia graph                     # graph snapshot statistics
sia context                   # bounded context pack for agents/sessions
```

Notes on `ask`: results show a blended score; "no matches" is not proof of
absence — the brain only finds what shares meaning with your words. If
ollama is down, search degrades to keyword-only and says so.

### Stability, pins, and rehearsal

```
sia memory                    # retention/review summary and due pages
sia memory <slug>             # inspect one page's stability and schedule
sia memory --pin <slug>       # queue a durable operator pin
sia memory --unpin <slug>     # remove only the operator pin
sia rehearse                  # list pages currently due
sia rehearse <slug>           # queue a deliberate recall signal
```

Stability is a retrieval lens, never a deletion policy. Low-retention edges
stop contributing to spreading activation, but their corpus pages and graph
evidence remain intact. Safety-class memories and operator-pinned pages are
eligible for nightly SM-2 scheduling while important. Removing the last pin
also removes a pin-only review record; a safety-class arousal signal remains
independently important. Separately, declared safety-class day pages remain
verbatim under consolidation, which therefore cannot strand their scheduled
reviews. Stability
and review intervals are finite and capped at 36500 days before persistence;
SM-2 ease is capped at 5.0. These are operational overflow bounds, not claims
about biological memory. Later intervals use the incoming ease; every response
updates ease for the next repetition, while a lapse also restarts the
repetition sequence. SIA maps observed interaction classes
to review-quality tiers; those tiers are deterministic system signals, not
measurements of human recall. A successful `sia rehearse <slug>` queues a
`user-recall` signal; when that page next becomes due, DREAM maps it to
`q=5`. A later thought/ponder/muse/grade reference maps to `q=4`, and no
qualifying post-review signal maps to `q=0`. The command does not update the
schedule immediately: the due DREAM performs re-embedding first. A failed or
missing embedding does not advance
the scheduler state, recall touch, or incident-edge reinforcement, so the page
remains due for retry until that same page is successfully re-embedded.
Legacy JACKAL pages whose formal-looking assurance has not been re-verified
through JACKAL's front door are recall-visible but deliberately excluded from
reinforcement; `sia rehearse` names that exclusion and does not claim a queued
touch.

### Deep thinking (the configured tool-free Claude CLI judge)

The judge is disabled by default. Opt in explicitly in
`~/.config/sia/config.json` with `judge.backend` set to `claude` and a
nonempty `judge.model`; missing or malformed configuration never auto-detects
a CLI.
Claude authentication/account/provider selection comes from the allowlisted
CLI environment; its normal billing and data terms apply.

```
sia ponder                    # open-ended reflection over recent memory
sia ponder "question"         # focused reflection
sia deep "question"           # same as ponder with a required question
```

Ponder writes a labeled `synthesis/…` page and drops a ✦ thought. It may
end by *proposing* predictions — proposals wait in a queue and are not
memories until you commit them with `sia take --accept <proposal-id>|all`;
the content-addressed ID prevents a concurrent queue edit from changing which
proposal you approved
(a model that mints the takes it later helps grade is too neat a loop).
Model output never masquerades as deterministic thought: every synthesis
is labeled with the model that produced it.

### Predictions and grading (outcome learning)

```
sia take "claim" --confidence 0.8 --by 2026-09-05 --domain crash-cause
sia takes                     # first bounded prediction-history page
sia takes --limit 64 --cursor CURSOR
sia grade                     # grade everything due now (configured judge)
sia grade <id>                # grade one take regardless of due date
sia calibration                         # first bounded domain page
sia calibration --cursor NEXT_CURSOR    # continue from the printed cursor
```

A take is graded strictly against recalled evidence: **TRUE**, **FALSE**,
or **UNRESOLVABLE** — the judge (configured in
`~/.config/sia/config.json`) is forbidden from guessing. A completed lookup
with no sufficient admitted evidence may yield an honest UNRESOLVABLE. A
failed or malformed retrieval is an infrastructure refusal instead: no judge
runs, no grade persists, and the take remains open and due. The deadline must
be strictly after the UTC commit date, including when an old proposal is
finally accepted. The grader sees the claim, creation time,
deadline, and admitted evidence, but not the forecast confidence; each grade
records the explicit `claude:<model-id>` judge label. Only canonical, real
`events/` and `epochs/` paths can become grading witnesses: traversal, empty
path components, symlink aliases, and the unverified JACKAL lanes are refused
before the judge runs. Its response must be exactly one `VERDICT` line and one
single-line `JUSTIFICATION`; preambles, duplicate or conflicting fields, and
trailing fields are infrastructure refusals rather than grades. Resolution
changes the take page to `origin: model` and stores the judge's explanation only as
`Model justification (inert prose): ...`; model-authored Markdown, wikilinks,
and HTML-like controls therefore cannot become active page structure. Each
Brier score is recomputed with deterministic decimal arithmetic as a separate
derived operation. The scorecard labels an
individual outcome `single-case`, keeps small series `descriptive-series`,
excludes UNRESOLVABLE and malformed resolved rows visibly, and withholds
sparse reliability bins. Its declared display gate (30 resolved takes, with
at least 5 in each outcome class) is an anti-overclaiming UI policy, **not** a
sample-size proof: passing it still describes an operator-selected,
model-graded stream and supplies no confidence interval, significance test,
or claim about truth in the world. Domain statistics come from a bounded,
cursor-paginated catalog. When another page exists, CLI and MCP output prints
an explicit omission line and the next catalog cursor rather than presenting
the current page as complete. Pass that value to
`sia calibration --cursor NEXT_CURSOR`, or as the optional `cursor` argument
of the `sia_calibration` MCP tool. The static `sia://calibration` resource
remains the first page. The nightly dream grades up to three due takes on its
own.

Corpus pages are authoritative; `~/.local/state/sia/natural-history/` is a
recoverable read model, not a second memory store. It contains digest-bound
direct rows, capped open sets, append-only catalogs, and exact Decimal
sufficient statistics. Creates, closes, and grades have durable intents before
page mutation. A grade affects calibration only after the exact signed
`GRADE:take` row is observable, the page is durable, and the idempotent
projection has settled. Pulse summaries, due selection, and intent nags
therefore have fixed work bounds even when historical catalogs are large.

Historical take and intent listings are cursor-paginated. Existing pages are
admitted by a resumable, generation-bound baseline in bounded pulse-sized
pages; directory mutation restarts the cursor conservatively and journaled
mutations override older baseline observations. Recurring authority passes
then mark every live direct row and sweep the paginated catalog. Missing,
replaced, or repaired identities transition through a durable projection WAL;
tombstones subtract their exact prior open/calibration contribution, while a
changed resolved take is scored only when the signed ledger contains its new
exact page bytes. Readiness and calibration remain closed while either scan or
sweep is incomplete, unstable, or awaiting replay. Unsigned resolved legacy
pages are counted as invalid resolved observations and excluded from Brier and
accuracy denominators. Once both authorities are ready, the next pass durably
enters a shared fresh incomplete `audit` cycle before reading a direct row.
Each participant pins its own catalog limit and directory checkpoint; bounded
slices advance across live rows and tombstones while readiness remains closed.
The faster participant waits ready for the slower one instead of independently
rotating into another audit. Global ready returns only when both generations
reach their pins and each catalog has not
grown, no transaction is pending, and the checkpoint is unchanged. Directory
entry churn is therefore an immediate reconciliation signal. A same-inode
edit made after the final observation remains an explicit nonclaim until a
later pinned audit reaches it; SIA does not claim instantaneous coherence
against another process running as the same user.

**Evidence-derived proposals.** When a self-healing integration reports
a successful heal, the brain *proposes* a hold-take on its own: "this
heal will hold — no repeat within 7 days," with a confidence computed
arithmetically from that action's own history in the corpus (fraction
of past heals that held; prior 0.70 under thin history). No model is
involved, and nothing is committed until you run `sia take --accept` —
this is how the calibration population grows without loosening the
propose-don't-mint rule.

### Signed-ledger memory benchmark

```
sia bench                              # held-out retrieval + abstention run
sia bench run --chain sia --chain custos
sia bench generate --out /tmp/sia-qa  # question file + private answer key
sia bench generate --chain sia --out /tmp/sia-qa
sia bench score --dataset /tmp/sia-qa --answers predictions.jsonl
sia bench legacy                       # older hand-authored corpus probes
```

`--chain` is repeatable on `run` and `generate`; omitting it selects every
available configured chain and preserves any rejection as a named diagnostic.
The default run writes its Markdown report to
`~/.local/share/sia/research/ledger-bench-YYYY-MM-DD.md` after printing it.

The generator opens ledger and verifier files without following symlinks,
requires their observed bytes, inode, size, modification metadata, and digest
to match before and after each chain's registered verifier runs, and refuses
unknown or rejected chains. These observations do not exclude a same-user
in-place ABA completed between checks, and the verifier digest does not bind
every library, interpreter, kernel, or hardware dependency it loads. Every
custom chain must set `verifier` to a real file that is either the exact first
`verify` argv element (a directly executed verifier) or the immediate script
operand of SIA's current Python interpreter. Explicit shell-wrapper and
alternate-interpreter forms, interpreter flags before the script, duplicate
verifier placements, and unrelated later placements are refused. The exact
absolute `ledger` path must also appear as an argv element; entries that leave
either binding implicit, collide with another name, or are malformed appear as
explicit integrity/benchmark refusals rather than silently shrinking the
verified scope. Set `enabled: false` to exclude a deliberate example entry. It
parses the reserved built-in `custos` chain as Custos v1 (canonical Unix stamps
and SHA-256 of each complete signed TSV line); every other built-in or custom
chain remains strict attest-ledger v1. The selected `chain_format`, native
head, whole-ledger digest, verifier identity, source pages, and native entry
hashes remain in owner-private provenance. The generator creates
information-extraction, temporal,
multi-event aggregation, knowledge-update, and hard-negative abstention questions from
the accepted rows. A deterministic stratified calibration split selects each
retriever's abstention threshold; that threshold is frozen before the held-out
split is scored. If both calibration classes are not present, retrieval results
are withheld rather than scored using an invented policy. `ABSTAIN` is a literal
answer: omitting an answer does not earn abstention credit.

Exports contain `questions.jsonl` without answers, source slugs, or observed
timestamps; a mode-0600
`answer-key.jsonl` with row/head provenance and normalized source-excerpt
witnesses, and a mode-0600
`mcp-evaluation.xml` containing a deterministic held-out subset in the MCP
evaluation-guide format. The public manifest is an explicit allow-list: it
contains no chain/file provenance, source path, witness path, or source digest
that could disclose a dated temporal answer. Before publication, question text
is compared with private dates and slugs after compatibility-Unicode and
repeated URL/HTML decoding, so a common reversible spelling cannot bypass the
same boundary. That consumer-canonical spelling also governs conflicting-prompt
checks and public IDs. Control, bidi-format, surrogate, and
unassigned/noncharacter text is rejected from public question fields without
rewriting the exact signed ledger provenance. Answer-independent IDs reveal no
private-file digest; a mode-0600 `private-manifest.json` binds the public
manifest, answer key, evaluation XML, and the complete private evaluation
manifest needed to revalidate exact source-page and event-index bindings. SIA
refuses to export the private files beneath its indexed corpus. The default
run measures retrieval of answer-bearing evidence plus a thresholded
non-abstention proxy. A present row earns evidence credit only when a returned
chunk from the bound source page contains the exact private excerpt witness;
matching the page slug or title alone is wrong evidence. Multi-event counts
require every contributing event excerpt in the scored retrieval window. This
does not label the proxy as a reader answer.
Use `score` for judge-free normalized scoring of reader output in JSONL form:
`{"id": "…", "answer": "…"}`. A verifier refusal or a sparse local
population is reported as such, without falling back to unsigned rows; unknown,
rejected, or empty generation exits nonzero.

Benchmark capacity is also fail-closed. Ledger and verifier snapshots,
source-page count and aggregate bytes, parsed rows, candidate questions,
negative-witness cross-products, generated artifacts, and submitted answer
files each have explicit implementation ceilings. Crossing one refuses the
run; SIA never truncates a signed chain or source-page witness to manufacture a
score, because latest-row and abstention claims require a complete observed
snapshot.

On a fresh installation, the installer signs two facts it has just
established—`INSTALL:runtime ... prepared` and `INSTALL:index sia registered`.
The verified SIA-lifecycle sense projects them into `events/sia/`, so the
standalone corpus receives truthful, answer-bearing rows from which the
generator can form a held-out bundle. `PULSE:*`, `DREAM:bench`, and terminal
`SOURCE:refuse` rows are deliberately not projected, so ingestion, evaluation,
and capacity handling cannot recursively train on or replace their own result.

### Intents (prospective memory)

```
sia intend "rotate the ledger keys" --by 2026-10-01
sia intend --list             # open intents with countdowns
sia intend --history          # first bounded all-intent history page
sia intend --history --cursor CURSOR
sia intend --done <id> [note] # close one, on your word only
```

The one thing a pure historian lacks: remembering **to do**, not just
what happened. An intent is a corpus page like any memory; the brain
surfaces it as a thought when the deadline is within 48 hours and nags
once a day when overdue (urgent, red). It never closes an intent
itself — that is a due-date lane, not a mechanism.

### Integrity

```
sia verify                    # re-verify every signed chain with its own
                              #   keeper's verifier, live
sia ledger                    # SIA's own signed run ledger: head + verify
```

### Maintenance (daemon must be stopped first)

```
systemctl --user stop sia-brainstem
sia pulse                     # run one heartbeat by hand
sia dream                     # run the nightly cycle now (consolidation,
                              #   rehearsal, musing, grading, slug-drift probe,
                              #   gbrain dream)
systemctl --user start sia-brainstem
```

## 4. Reading the thought stream

| Glyph | Kind | Meaning |
|---|---|---|
| ⛓ | integrity | a signed chain's verification state changed |
| ✚ | healing | a self-healing integration acted (optional) |
| ∅ | refusal | a subsystem refused rather than guess (optional) |
| ≻ | collapse | a WORLDLINE reality collapsed (optional) |
| ✖ | crash | a coredump was observed (urgent, red) |
| σ | anomaly | statistical cohort anomaly (real baseline only) |
| ◉ | attention | the most salient memory shifted |
| ✧ | novelty | something genuinely new appeared (first sighting, 30-day return, or isolation within a batch of at least five) |
| Δ | surprise | after the sample floor, a count of at least five above the prior band maximum; includes **absence** for paced organs and uses a six-hour per-band cooldown |
| ∞ | association | the nightly musing found distant memories connected by a bounded low-traffic path |
| ☾ | dream | the consolidation cycle's report |
| ✦ | ponder | a judge-model synthesis landed |
| ⊢ | take | a prediction was registered, proposed, or came due |
| ⚖ | grade | a prediction was judged |
| ◎ | calibration | the running scorecard was restated |
| ⋈ | coincidence | two organs went out-of-band in the same window (a stated observation, never a cause) |
| ➤ | intent | a prospective-memory commitment is due soon or overdue |
| ≟ | bench | the nightly heuristic slug-drift tripwire reported its proxy metrics |
| ✉ | note | an agent or the operator left a labeled note for future sessions |

The former `∎ formal` presentation is retired. Historical JACKAL pages that
asserted categorical receipt assurance are suppressed at recall; current
JACKAL result rows and receipt filenames are unverified observations, not
proof-bearing thought kinds.

New persisted memories use exactly `evidence`, `derived`, or `model` as their
origin. Outside the narrow signed legacy-take migration described below,
missing, invalid, or ambiguous legacy metadata is displayed as
`legacy-unlabeled`; it is never evidence and is conservatively weighted like
`model`. Deterministic generator thoughts cite their evidence. ✦ ponder, ⚖
judge-grade, and ✉ agent/operator-note thoughts are `model`. Brier
recomputation and signed-transition handling are deterministic operations, but
they do not promote the judge's verdict to `derived` or `evidence`.

### Corpus publication and read readiness

SIA treats a corpus page, its git commit, the PGLite index, and the exported
graph as one generation. Every shipped SIA corpus writer — `pulse`, `dream`,
`take`, `intent`, `grade`, and `ponder` — holds the corpus transaction lease
and persists `sync_needed` publication debt before its first page create,
rewrite, or unlink. The shared low-level page barrier covers pulse/dream
helpers; take, intent, grade, and migration transitions also pass an explicit
write-ahead callback. Agent-note queueing is not a corpus write; its later page
materialization runs inside `pulse` under this barrier.

The marker clears only after a successful git commit or clean verification,
PGLite sync, and graph export. Direct `take`, `intent`, and `ponder` commands
can leave publication debt for the next pulse, which makes new pages durable
without exposing them through an older index. The daemon and manual pulse both
reserve the pulse sequence under the same lease as the heartbeat, preserving
any concurrent debt bit and preventing sequence reuse. DREAM publishes between
memory-backed phases: after consolidation before later retrieval, before and
after grade work, before the benchmark, and before the gbrain dream cycle.

Readiness refuses while the marker is set, while a
`~/.local/state/sia/grade-transactions/` journal awaits recovery, or while the
legacy-take migration is pending or cannot be safely scanned. A gated CLI
request retains the corpus lease from readiness through rendering the returned
result, so its output belongs to the same corpus generation. MCP memory tools
and resources shell out to that CLI and inherit the boundary.

Readiness also reports bounded graph-projection and consolidation-scan debt.
`sia status` remains the diagnostic surface while that debt is active; memory
reads and publication stay fail-closed until the corresponding durable
generation has converged. A DREAM that completes only one directory slice may
leave its named consolidation transaction pending; each later pulse recovers
one crash-resumable bounded unit under that same DREAM ledger identity. The
marker clears only after scan cursors, candidate days, exact claims, admitted
source removals, and the resulting conservative rescan all converge.

The live readiness reason names the retained recovery lane. Preserve the
named state; deleting a marker or journal does not turn an incomplete
publication into a valid one.

| Readiness reason family | Retained authority | Recovery action |
|---|---|---|
| Corpus publication pending, graph projection debt, or no successful publication receipt | `memo.json`, corpus git state, PGLite, graph cursor | Run or wait for one successful `sia pulse`; repair the named git/index/graph refusal first if it repeats. |
| Pulse, DREAM, consolidation, source-replay, or thought recovery pending | `memo.json`, consolidation/source/thought cursors and claims | Keep the marker and run a pulse; SIA resumes the exact bounded transaction. |
| Evidence cursor replay guard or DREAM mind transition pending | `mind.json` plus the bound event/DREAM transition | Keep mind state intact and run a pulse so the recorded transition can settle idempotently. |
| Take/intent projection, signed grade, or legacy provenance migration pending | `natural-history/`, `grade-transactions/`, or `take-migrations/` | Preserve the journal and authoritative page; run a pulse, or rerun first-light installation for a migration refusal after repairing the named provenance issue. |
| Readiness check refused or malformed state | The exact file named by `sia status` | Restore or repair that owner file from known-good state; do not bypass the refusal or delete signing/publication history. |

## 5. How it learns (the short version)

- **The graph wires itself** — wikilinks in event/epoch evidence may become
  typed edges; only explicitly `derived` safety thoughts may do the same.
  `model` and `legacy-unlabeled` thoughts remain generic `mentions`.
- **Bonds strengthen with use** — co-occurring and co-*recalled* memories
  gain Hebbian weight; every question you ask reshapes the brain.
- **Importance is learned from use** — ACT-R activation (recency +
  frequency, power-law decay) decides what surfaces and what sinks.
- **Stability fades without erasing** — an exponential retention lens
  demotes stale nodes and associations only in retrieval. Important or pinned
  pages are re-embedded on a deterministic SM-2 schedule; interaction-derived
  quality tiers are adapters, not evidence about human memory.
- **Rhythms are learned** — per-organ hourly baselines make surprise
  measurable against each band's own history (count vs previous max vs
  sample size), including the silence of a paced source; when two organs
  exceed their bands in the same window, the coincidence itself becomes
  a thought stating both counts — an observation, never a cause.
- **Sleep turns episodes into knowledge** — day memories older than 14
  days consolidate into weekly epochs; declared safety-class days stay
  verbatim; originals always remain in git. Discovery is a durable bounded
  scan. Before mutation, consolidation persists the exact source paths and
  byte digests for each admitted day; crash replay accepts a missing shard only
  when the epoch already contains that exact lineage. A partial scan never
  licenses deletion. The eligibility cutoff remains pinned while that bounded
  generation has a cursor, pending day, or claim; a later UTC cutoff starts a
  new generation only after the prior one converges.
- **Judgment is graded** — predictions meet outcomes; Brier calibration
  accumulates; ponder sees its own track record. Successful heals
  auto-*propose* hold-takes (deterministic confidence from their own
  history) so the calibration population grows — you still commit
  every one by hand.
- **Retrieval drift is instrumented nightly** — the dream runs a small
  date-seeded heuristic slug-family probe and plots its trend in the cockpit.
  It is a regression tripwire, not an answer-quality score. Oversized or
  malformed pre-bounded display history is read from a stable no-follow tail,
  compacted to recent complete rows, and exposed as legacy truncation; because
  this file is derived display state, it cannot strand the authoritative DREAM
  receipt or readiness.

## 6. Where everything lives

| Thing | Path |
|---|---|
| The memory itself (markdown, git) | `~/.local/share/sia/corpus/` |
| The brain index (gbrain/PGLite) | `~/.local/share/sia/.gbrain/` |
| Installed typed-relation schema pack | `~/.local/share/sia/.gbrain/schema-packs/sia-pack/pack.yaml` |
| Daemon + engine code | `~/.local/share/sia/bin/` |
| Private Bun + compiled gbrain | `~/.local/share/sia/toolchain/` |
| Signed run ledger | `~/.local/share/sia/ledger.tsv` |
| Ledger signing/public keys + pinned head | `~/.local/share/sia/key.hex`, `pub.hex`, `head.pin` |
| Research reports | `~/.local/share/sia/research/` |
| Pending signed grade transactions | `~/.local/state/sia/grade-transactions/` |
| Pending signed take migrations | `~/.local/state/sia/take-migrations/` |
| Publication/readiness marker | `~/.local/state/sia/memo.json` (`sync_needed`) |
| Authoritative mind/rehearsal state, queues, and live snapshots | `~/.local/state/sia/` |
| Non-authoritative fixed publication slots | `~/.local/state/.sia.sia-stage/`, `~/.local/share/.sia.sia-stage/` |
| Plugin (bar + cockpit) | `~/.config/omarchy/plugins/khephri.sia/` |
| Services | `sia-brainstem.service`, `ollama.service` (user) |
| CLI | `~/.local/bin/sia` |

**The corpus is the evidence source of truth.** The PGLite database is a
rebuildable index over it, but `mind.json`, review schedules, queues, pending
transactions, the signed ledger/key/head, and config are not derivable from
that index. Back up all of `~/.local/share/sia`, `~/.local/state/sia`, and
`~/.config/sia`; `.gbrain` may be omitted only if you accept an index rebuild.
Do not move, open, or rebuild `.gbrain` directly. The installer creates an
initially absent database through a durable `managed-install/gbrain-bootstrap`
intent and resumes only the exact partial state attributable to that intent.
It initializes off-path, validates through gbrain's supported health probe,
and publishes the validated tree by generation compare-and-swap through
`prepared`, `initializing`, `publishing`, `probing`, and `published` phases.
The probe is authorized before it may mutate the staged store, and the full
post-probe generation is bound before the intent retires. A valid preexisting database
is front-door health-checked and used in place. An unattributed partial
bootstrap workspace or unhealthy existing database is preserved and refused;
it is never moved, deleted, or claimed automatically. A safe destructive rebuild
would have to hold SIA's lifecycle, PGLite-owner, and corpus-transaction leases
through archive, initialization, source registration, sync, and validation.
This release deliberately provides no shortcut around that boundary. For
disaster recovery, preserve the suspect tree and either restore a known-good
database or restore the retained corpus/state/config into a clean installation
where the database is genuinely absent.

## 7. Agents everywhere

Every agent harness on this machine can use the brain:

| Harness | Lane |
|---|---|
| Claude Code | MCP server `sia` (user scope) + the `sia` skill |
| Codex CLI | `[mcp_servers.sia]` in config.toml |
| Grok | `grok mcp add sia` |
| OMP (oh-my-pi) | the `sia` skill via ~/.claude/skills |
| anything MCP-capable | `python3 ~/.local/share/sia/bin/sia-mcp` (stdio) |

`install.sh` never performs a name-only MCP add or remove because the supported
harness CLIs do not expose a compare-and-add/delete operation. For each present
harness it inspects the exact client-specific registration shape. An absent
registration produces the exact manual add command; an unrelated registration
is preserved; an indeterminate inspection refuses. Exact unmarked
registrations and modified registrations that still reference SIA remain
user-owned and unchanged, with a durable non-ownership guard preserving their
CLI/runtime dependency. A prior ownership marker is recovered only when the
current registration verifies exactly; invalid or unresolved historical
markers fail closed rather than being reclassified after display-format drift.
Uninstall likewise preserves the registration and prints the exact manual
removal command when appropriate. Rerun the installer after adding SIA
manually, or create the documented external-consumer guard, before depending
on the runtime being retained through uninstall. The shared OMP/Claude skill is
installed only when the path is new or
its ownership marker and content hash show an unmodified SIA-managed file. An
unmarked or locally modified skill is preserved; use the printed source path,
or explicitly consent with `SIA_REPLACE_AGENT_SKILL=1` (which retains a
backup). An arbitrary MCP-capable client is not auto-registered; configure the
stdio command from the last row manually, then create a keep-runtime file under
`~/.local/state/sia/mcp-consumer-guards/`. Any entry there conservatively
preserves the CLI/runtime during uninstall; retire it only after its external
consumer is gone. If SIA was installed standalone, read `docs/MANUAL.md` from
the checkout used for installation; if that checkout is unavailable, use
`sia --help` and the MCP tool/resource descriptions rather than assuming the
Omarchy plugin path exists.

Copyable user-scope registration commands for the supported clients are:

```bash
claude mcp add --scope user sia -- python3 ~/.local/share/sia/bin/sia-mcp
codex mcp add sia -- python3 ~/.local/share/sia/bin/sia-mcp
grok mcp add --scope user sia -- python3 ~/.local/share/sia/bin/sia-mcp
```

Run only the command for the client you intend to configure, then rerun
`./install.sh` so SIA can inspect it and create the appropriate durable
non-ownership guard. For a generic client, create an explicit guard before
depending on SIA's runtime surviving uninstall:

```bash
install -d -m 0700 ~/.local/state/sia/mcp-consumer-guards
install -m 0600 /dev/null \
  ~/.local/state/sia/mcp-consumer-guards/my-resident-agent
```

Remove that guard only after the external consumer is retired.

When Omarchy is installed, plugin enablement is a required installation step.
The installer requests a shell plugin rescan and requires the exact
`khephri.sia` catalog ID before enablement; a discovery or enablement error
remains visible and stops the installer. Its generic catalog reader accepts
extra object fields but requires valid top-level-list JSON and an object with
that exact ID; rescan failure, malformed output, or a missing ID is a refusal,
not a directory-name guess. Without Omarchy, only the cockpit is skipped; the
CLI and MCP surface remain available.

The optional binding edit is staged beside `bindings.lua` and renamed into
place only as a complete file. In a live session, reload/config validation
failure restores the original. If either managed marker is missing, repeated,
or reversed, install and removal preserve the entire file and report the
malformed block rather than deleting an open-ended range.

MCP tools: `sia_ask`, `sia_search`, `sia_recall`, `sia_status`, `sia_think`,
`sia_note`, `sia_propose_take`, `sia_calibration`. The server never
opens the database. SIA-managed reads share the same cross-process owner
lease as the daemon; note writes create immutable per-request files instead
of touching either the corpus or PGLite. The brainstem acknowledges a note
only after its labeled page is committed and indexed. Agents propose takes;
only you commit them (`sia take --accept`). Agent notes are model-origin,
labeled, and weighted below evidence. Agent and operator notes are deliberate
prose exceptions to evidence-backed event memory, never witnesses. They persist
and can be returned to configured consumers: never store credentials, secrets,
or private content in them. Pattern-based redaction is defense in depth, not a
secrecy guarantee.

The stdio MCP process itself makes no cloud or external network calls;
configured retrieval can use the loopback Ollama service. Its consumer remains
a separate trust boundary because it receives every requested result and may
forward that content to its own model/provider.

Memory-dependent CLI commands perform the readiness check while already
holding the corpus owner lease and retain that lease through the returned
result. The check requires a Boolean `sync_needed` marker that is not set, no
pending `grade-transactions` journal, and no pending or discoverable
legacy-take migration, natural-history transaction, or unfinished bounded
take/intent baseline. The MCP ask/search/recall/thought/calibration tools and
non-status memory resources shell out to those commands and inherit their
refusal as a tool error or resource-unavailable response, with result bytes
drawn from the same corpus generation. `sia status`, `sia_status`, and
`sia://status` remain callable for diagnosis: the readiness line is live, while
the pulse, source-health, and graph fields are the last-published snapshot.
`sia_note` and `sia_propose_take` may still enqueue writes; neither exposes
indexed memory.

The skills sense likewise admits only a real skill directory directly beneath
a configured root containing a real, directly contained regular `SKILL.md`.
Configure precedence-ordered roots in `~/.config/sia/config.json`; relative
entries are interpreted beneath your home directory:

```json
{ "skills": { "roots": [
    ".claude/skills", ".agents/skills", ".omp/skills",
    ".copilot/skills", ".config/agents/skills"
] } }
```

The CLI reloads configuration on its next invocation. The brainstem is a
resident process and keeps its import-time configuration, so after changing
custom senses, skill roots, or judge settings run:

```bash
systemctl --user restart sia-brainstem.service
sia status
```

It opens the root, child directory, and manifest with no-follow semantics.
A symlinked or unopenable root makes that root incomplete and the aggregate
source partial; symlinked child directories or manifests are skipped rather
than cataloged. Each manifest's bounded frontmatter head is captured once, with
before/after/current-path identity checks both at capture and after root
validation. The sanitized description, head digest, and file metadata are kept
together in the cursor snapshot, so event rendering never reopens the file and
change detection is not based on modification time alone. A replacement or
in-place change observed across those checks makes the whole root partial and
retains its prior effective rows; no removal is inferred from that pass.

The same read surface is mountable as MCP resources:

| URI | Content |
|---|---|
| `sia://status` | current pulse and source-health boundary |
| `sia://thoughts` | recent thoughts with their origin labels |
| `sia://calibration` | population-aware descriptive scorecard |
| `sia://cortex` | root cortex page |
| `sia://memory/{slug}` | one canonical corpus slug returned by recall |

The memory template rejects traversal, uppercase/non-canonical slugs, and
arbitrary schemes. Resource reads and `sia_search` use the CLI's no-touch
lane and are idempotent; `sia_ask` is intentionally not marked read-only
because successful recall queues reinforcement touches.

The stdio server is dual-era MCP. It negotiates the legacy `2024-11-05`,
`2025-03-26`, `2025-06-18`, and `2025-11-25` handshake revisions and also
implements the stateless `2026-07-28` `server/discover` flow with required
per-request metadata, modern-only version advertisement, `resultType`, server
identity, and cache hints. Legacy versions remain on the separate `initialize`
fallback path. JSON-RPC
batches are accepted only by the `2025-03-26` revision that introduced them;
the earlier revision and the newer legacy/modern revisions receive a protocol
error rather than silently using incompatible batch semantics.
Each newline-delimited request and captured CLI result is capped at 262144
bytes, batches at eight items, and a serialized response at 1048576 bytes;
oversize input/output refuses instead of being parsed or returned partially.

## 8. Troubleshooting

Graceful degradation remains explicit; each fallback preserves the origin and
absence boundary instead of silently claiming equivalent retrieval.

| Failure | Observable behavior | What remains trustworthy |
|---|---|---|
| Ollama/embedding search unavailable | `sia ask` reports keyword-only retrieval | Returned chunks and origin labels; ranking is no longer semantic. |
| Graph or mind snapshot cannot support associative reranking | Recall reports `associative rerank unavailable; origin-safe fallback` | Dense ordering with conservative origin weighting; no PPR/activation claim. |
| Schema pack is missing, invalid, or changes during export | Affected relations fall back to `mentions`; SOURCE HEALTH marks the graph partial and publication debt keeps memory reads closed | The diagnostic partial graph, explicit links, and retained PGLite memory—not the missing typed inference; repair the pack and complete a pulse. |
| Publication or recovery debt exists | Memory-dependent CLI/MCP reads refuse; live status and queued note/proposal writes remain available | The refusal reason and retained journals; last-published cockpit fields are diagnostic snapshots. |
| Touch queue has a torn or malformed record | The suffix is digest-bound before repair, or a complete malformed record remains visible claim debt | The complete durable prefix; no silent cursor advance or invented touch. |

- **Bar icon dim / "brainstem not reporting"** —
  `systemctl --user status sia-brainstem`, then `journalctl --user -u
  sia-brainstem -n 30`.
- **`sia ask` says keyword-only** — ollama is down:
  `systemctl --user restart ollama`.
- **"already open through gbrain serve"** — an unrelated program bypassed
  SIA's owner lease and opened the single-connection brain. Stop that process;
  the daemon, CLI, benchmark, and MCP paths serialize their own access.
- **Widget vanished after an Omarchy update** — quattro upgrades can
  rewrite `shell.json`; run `omarchy plugin enable khephri.sia`.
- **Edited plugin QML but nothing changed** — the hot-reloader can serve
  stale code; `omarchy-restart-shell`. (Each shell restart may coredump a
  `hyprland-dialog` helper — an Omarchy quirk SIA will dutifully report
  as a crash thought.)
- **SOURCE HEALTH shows a sense error** — that sense failed this pulse;
  its events are safe (cursors only advance after durable writes) and it
  retries next pulse.
- **SOURCE HEALTH reports a touch-queue physical-record refusal** — a killed
  legacy writer left an unterminated suffix. SIA durably recorded the exact
  queue generation, complete-prefix offset, and byte digests before repairing
  only that suffix. The retained count is diagnostic history; a complete
  malformed LF-terminated row is not repaired and remains visible debt.
- **`SIA memory read refused`** — publication debt, a pending signed grade
  transaction, or a legacy-take migration is still owed. Run or wait for a
  successful `sia pulse`; the command refuses until recovery and corpus git
  commit, PGLite sync, and graph publication all succeed. `sia status` reports
  the live readiness reason, but its pulse/source/graph values and the cockpit
  may still be last-published snapshots. If the reason names grade recovery,
  preserve `~/.local/state/sia/grade-transactions/`; the pulse must reconcile
  the exact journal, signed row, and page rather than discard the transaction.
- **`legacy take migration refused` during install, pulse, or dream** — the
  reported page, store, or owner-private journal did not pass fail-closed
  validation. Common causes include a graded page that is neither a current
  canonical take nor an exact v1.2 producer page, an ambiguous origin, or an
  invalid journal. Keep `~/.local/state/sia/take-migrations/` and the
  `sync_needed` marker intact. Compare the page with corpus git history,
  restore the exact producer page or deliberately repair it to the current
  schema after reviewing provenance, then rerun `install.sh` or run a
  successful `sia pulse` with the brainstem stopped. An invalid v1.2 open
  deadline is not guessed: its normalized record remains explicitly blocked
  from automatic grading.

## 9. Privacy and refusal boundaries

- Built-in senses do not open Claude/Codex **message bodies**, clipboards,
  password stores, or private keys. They ingest metadata and evidence records;
  agent-session sensing observes file existence, size changes, and freshness,
  not JSONL payloads. That metadata walk is a bounded paginated generation:
  every traversed directory retains a generation token and must revalidate
  through a durable bounded cursor before absence can prune a session. Nested
  disappearance, replacement, page reset, or capacity refusal preserves the
  prior session baseline. Journal JSON uses a bounded cursor-catalog pass and
  a separately bounded full-row pass. A valid prefix can settle; a malformed
  or over-bound row advances only after its exact cursor is re-queried and its
  named refusal is durable. Churn that defeats that identity check, a partial
  row, timeout, or failed producer retains the prior journal cursor. A custom
  sense reads the exact file/field configured by
  the operator, so never point one at a secret or content store. The separate
  SIA ledger keeper necessarily reads SIA's own
  signing key when signing an authorized transition —
  and secret-shaped spans (key blocks, tokens, JWTs, `.ssh` paths,
  password fields) are **redacted at the sense boundary**, before
  anything reaches the corpus or git; every omission is counted in
  SOURCE HEALTH and the `sia ask` boundary footer.
- The ingestion, indexing, retrieval, and embedding runtime does not send
  memory content to the cloud. Embeddings are local (Ollama). The separate optional
  judge path consists of the calls **you** trigger (`ponder`, `deep`, `grade`)
  or enable through capped nightly grading; those calls may send recalled
  context through your explicitly configured, tool-free Claude CLI model and
  are always labeled. Codex grading is refused at this confidentiality boundary.
  MCP clients are a separate operator-configured trust boundary: they receive
  requested memory over stdio and may forward it to their own model/provider,
  whose data terms apply. Scripts, pipes, and agents that capture local `sia`
  CLI output cross the same boundary.
- **SIA does not silently delete.** Consolidation compacts only what git
  provably holds;
  declared safety-class days stay verbatim, and every compacted original
  remains recoverable in git. The signed ledger records
  named lifecycle transitions (boot, pulse ingests, dreams, and grades).
- **SIA does not guess.** Refusals, UNRESOLVABLE grades, and "snapshot
  partial" are first-class answers.

## 10. Uninstall

```
./uninstall.sh           # removes code/UI; keeps corpus, ledger, keys, queues, config
./uninstall.sh --purge   # attempts to erase retained data and config too
```

Default removal preserves the corpus, ledger and signing identity/head,
queues and state snapshots, research, private toolchain, and operator config;
the enclosing share/state/config trees are not byte-for-byte intact. It
unregisters only MCP entries the installer ownership-marked
and that still match the exact client-specific shape, removes only an unmodified
ownership-marked SIA skill, reloads systemd after
removing the brainstem unit, and validates Hyprland when it removes the
consented keybinding in an active session. The installed plugin tree is moved
to a printed hidden sibling backup rather than recursively deleted. Ollama
and its service/model remain because other local tools may share them. SIA's
private Bun/gbrain toolchain remains under the retained share root during
normal removal and is erased only with a successful `--purge`. Any failed
operation is listed and makes the uninstaller exit nonzero.
Purge also validates and removes the two fixed publication slots at
`~/.local/state/.sia.sia-stage` and `~/.local/share/.sia.sia-stage`. It removes
only SIA's exact owner-private lock/payload shape; unsafe, malformed, busy, or
unexpected contents are preserved and make purge incomplete. A crash-left
`payload` is non-authoritative staging data—never treat it as a corpus/state
record or publish it manually.
If systemd cannot stop the brainstem, its unit/runtime are preserved and a
requested purge is blocked so a possibly live process never loses its memory
underfoot. Any surviving or indeterminate service, plugin, or recovery CLI
retains both CLI and runtime and blocks purge rather than knowingly leaving a
broken command. For MCP, only a registration that references the installed
SIA path, an indeterminate inspection, or an explicit consumer guard retains
them; an unrelated mismatched registration is preserved without doing so. An
unowned or locally modified runtime tree also blocks purge until it is
inspected/removed manually or restored to a valid SIA ownership receipt.
Durable external-consumer guards live under
`~/.local/state/sia/mcp-consumer-guards/` and are never removed automatically.
`--purge` performs blocker checks but is not transactional: state, share, and
config removals are attempted independently, and a later failure does not roll
back an earlier removal. Back up all retained categories before using it.

### Brainstem service lifecycle barrier

A locally installed user unit under `~/.config/systemd/user` outranks a runtime
systemd mask, so `install.sh` and `uninstall.sh` do not use a runtime mask as
their quiescence primitive. Once preflight proves an existing unit and receipt
are SIA-owned, or proves the managed unit path is safely absent, they create
exactly
`$XDG_RUNTIME_DIR/systemd/user/sia-brainstem.service.d/sia-lifecycle-barrier.conf`.
The helper opens the canonical mode-0700 runtime root and every descendant by
descriptor without following links. It requires current-user-owned,
non-group/world-writable directories and an exact mode-0644, single-link,
stable-generation regular barrier file. Its content is:

```ini
[Unit]
RefuseManualStart=yes
ConditionPathExists=
ConditionPathExists=!/
```

The empty assignment clears prior path conditions; the negated root condition
is structurally false on a running host, blocking indirect activation before
`ExecStart` or its hooks. `RefuseManualStart=yes` independently rejects an
explicit start. After a manager reload, SIA accepts the barrier only when one
bounded `systemctl show` reports the exact managed fragment, that sole drop-in,
an inactive service with no main PID, no pending job, and the effective
manual-start refusal. Foreign runtime fragments, extra operator drop-ins,
links, modes, owners, content, or changing generations are never normalized or
deleted to make the check pass.

A fresh install first publishes the drop-in as an orphan while the main unit is
absent. It then publishes the owned main unit, reloads the user manager, stops
and resets any failed state, and attests the complete barrier before first
light. An upgrade arms and attests the same barrier before replacing runtime or
integration artifacts. At final activation, the installer uses
`renameat2(RENAME_NOREPLACE)` to retire only its exact `.conf` file to the
non-drop-in `sia-lifecycle-barrier.retired` sibling. It reloads and verifies the
unit is unbarriered, enables and starts it, verifies the live Python executable
and exact brainstem argument, and only then discards the retired copy. An exit
or activation failure restores that copy atomically to the active `.conf`
name, reloads systemd, and leaves the daemon stopped behind the barrier.

Uninstall uses the same exact barrier before disabling and stopping the unit.
Successful cleanup retires only the SIA-owned `.conf`, reloads and attests the
unbarriered/absent unit, then discards the retired copy. It does not recursively
remove the `.service.d` directory or clean up an operator's drop-ins. If any
uninstall step fails, it retains either the active barrier or, once the main
unit is already absent, the exact retired recovery copy. A retry verifies the
absent/reloaded state before discarding that retired copy.

The barrier coordinates SIA and systemd within one user lifecycle; it is not a
hostile same-UID sandbox. Another process running as the account can modify
user-owned runtime files or bypass SIA entirely. The no-follow and generation
checks turn interference observed at their boundaries into a refusal, but do
not establish privilege separation from that process.

Installer reproducibility is fail-closed: Bun is installed in SIA's private
toolchain, and gbrain is compiled from the full pinned commit using its
SHA-256-bound upstream lock with a frozen production install. Receipts bind
the resulting executables. Before replacing or activating managed payloads,
the installer exercises the runtime's actual pidfd, Ed25519,
`renameat2(RENAME_NOREPLACE)`, and share-
filesystem `O_TMPFILE`/`linkat(AT_EMPTY_PATH)` capabilities; an import-only or
kernel-version guess is not accepted. The local Ollama archive and runtime version are
pinned, the user unit must have no drop-ins, its listener must be owned and
loopback-only, and the effective model directory is read from the running user
service. An unreceipted nonempty corpus is automatically recognized as legacy
SIA only when `.git/` is a real directory, `README.md` is a regular non-symlink
containing the exact `# SIA corpus — this machine's memory` marker line, and
the release checkout's `bin/sia-ledger verify` accepts the share tree. Other
nonempty corpora require
explicit `SIA_ADOPT_EXISTING_CORPUS=1` consent and must already be real git
working trees. Fresh creation is attributed by a durable
`managed-install/corpus-bootstrap` record that binds an absent corpus or its
exact owned-empty generation and resumes only producer-exact partial work. An
absent corpus is constructed in a fixed off-path tree under that intent and
advances through `prepared`, `publishing`, and `published`; only its bound tree
generation may claim the canonical path with `renameat2(RENAME_NOREPLACE)`.
Legacy or explicitly consented adoption is bound by
`managed-install/corpus-adoption` to its mode, stable tree generation, and Git
`HEAD`. A v2 root-identity receipt is made durable before either intent is
retired. It binds the canonical corpus directory's device, inode, full mode,
and owner while excluding timestamps, contents, and Git `HEAD`; ordinary
in-place memory changes therefore remain valid. The root must be a real,
current-user-owned directory with no group/world write bits. A replacement,
ownership/mode change, or restored directory invalidates the receipt and is
never auto-rebound: inspect the state, deliberately rotate the receipt, and
explicitly re-adopt it. An exact path-only receipt from an older release is
migrated once, only while both the installer lifecycle and corpus-owner leases
are held. The generation-CAS migration captures the root identity on both sides
of publication, verifies the v2 result, and retires the returned legacy receipt.
It binds the root present during migration and does not prove historical root
continuity before that observation.
Preserve an interrupted intent and rerun `install.sh`; deleting the record does
not authorize creation or adoption. Exact-content regular unmarked managed
files—including the brainstem and Ollama units and the CLI—are adopted by
writing a content receipt; modified unmarked files and unowned runtime trees
require the printed
`SIA_REPLACE_*` consent. The runtime receipt covers only the allowlisted
shipped member names and their content and requires those members to be
regular files; it does not attest to extra entries. Runtime replacement or
removal archives the entire prior tree, extras included. SIA-marker-owned
Bun/gbrain trees may be upgraded or repaired automatically, with the old tree
retained at a printed sibling path. Ollama's pinned release does not support a
digest-qualified pull, so the installer pulls the semantic
`nomic-embed-text:v1.5` tag and verifies the resulting manifest and every
referenced blob. A verified local
`latest` alias keeps older untagged gbrain configurations working; a different
existing alias requires explicit `SIA_REPLACE_NOMIC_LATEST=1` consent before
replacement. Custom/unowned Ollama units or runtimes are not adopted.
Replacing them with SIA's managed artifacts requires the separately printed
`SIA_REPLACE_OLLAMA_UNIT=1` and/or `SIA_REPLACE_OLLAMA_RUNTIME=1` consent.
`SIA_ALLOW_UNPINNED_OLLAMA=1` weakens only post-start executable
identity/version checks and does not retain a custom unit/runtime; model,
listener, and ownership verification still run.

On an empty share, `sia-ledger init` publishes only this exact durable prefix:
`key.hex`, its matching `pub.hex`, one canonical signed `GENESIS:init` row in
`ledger.tsv`, then the matching `head.pin`. Startup resumes only such a prefix.
A non-prefix component combination or a pending transition journal alongside
an incomplete prefix refuses closed. Preserve the entire share and rerun the
installer; never delete, copy, or regenerate individual key, ledger, pin, or
journal files to force initialization forward.

After host dependency, architecture, Python-cryptography, corpus, and
brainstem-unit ownership preflights pass, the installer stops an active
owned/adoptable SIA brainstem before private toolchain and Ollama validation
or mutation. Runtime modules are assembled as a complete sibling tree and
published through a durable generation-bound no-clobber journal. Only the
exact observed prior tree may be archived, and the staged tree may claim only
an absent canonical name; a concurrent replacement is preserved and refuses
the install. The previous tree remains at the printed backup path. Before any
desktop mutation, MCP inspection, or service enablement,
the installer temporarily releases its brainstem/PGLite/corpus locks, runs a
fatal first-light pulse, and reacquires those locks immediately afterward.
That pulse uses the same generalized publication barrier: it recovers any
pending `grade-transactions` journal, then scans current-schema pre-origin
takes and exact v1.2 producer takes. Open pages publish as `origin: derived`;
resolved pages publish as
`origin: model`, with historical judge prose made inert. Each target is
journaled under `~/.local/state/sia/take-migrations/`, signed as
`MIGRATE:take-origin` with kind `model-inert-v1` or `legacy-v1-normalize`, then
published only after `sync_needed` is durable. Corpus commit, PGLite sync, and
graph publication follow, and the marker clears last. A malformed candidate
therefore stops first light rather than allowing later integration steps to
expose inconsistent memory.

A failure before the first successful installer mutation restores prior
enablement/activity; a later pin, model, configuration, desktop, or harness
failure leaves the brainstem disabled/stopped rather than restarting mixed
dependencies. Correct the reported failure and rerun `install.sh`. Additive Ollama blobs may remain in Ollama's
shared store. A failed or rejected pull/copy preserves the shared post-command
manifest because attribution is unavailable, while retaining the exact
pre-operation snapshot at a printed private path for manual recovery; the
rejected generation is never accepted by SIA's verification gate. gbrain's canonical file-plane self-upgrade mode is
set to `off` and read back through the pinned CLI before the daemon is enabled.

---

*Companion document: `WHITEPAPER.md` — the architecture, the science, and
the verification record.*
