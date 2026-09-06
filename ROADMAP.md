# ROADMAP — from shipped laboratory to measured system

*Written 2026-09-02, immediately after v1.5.1. This document applies the project's own
hypothesis-lane freeze rule (Whitepaper §11) to the project itself: nothing in the
retrieval-and-rehearsal evaluation lane is promoted — and no new capability is added —
except on a measured showing. The next phase of SIA is not more machinery. It is evidence
about the machinery that exists.*

## Current mission amendment — construction behind an honesty gate (2026-09-06)

The operator's Build the Mind directives supersede this roadmap's capability freeze for
the in-scope source/live and cognitive construction work. They do not relax the hard
limits, the marketplace `main` freeze, release integrity, sequential test discipline, or
the rule that a claim must be proved rather than inferred from an implementation name.

The durable controller-source components now implement the local transaction from an
immutable retained batch through sealed page effects, a descriptor-bound clean Git
generation, receipt-bound gbrain sync/projection, graph/status/live publication, and
finally source acknowledgment. The cumulative `sia-runtime-v8` roster adds
`siasourceack.py`, `siasourceeffects.py`, `siasourceengine.py`, and `siasourcegit.py`.
Readiness remains closed until archival, refusal settlement, journal cursors, the main
cursor, and the final memo receipt have settled in that order. This is component and
recovery-boundary progress; it is not a claim that a resident pulse used the complete
path. That claim requires a front-door run with retained witnesses.

The cognitive acceptance rule is now controlling: define each named mechanism by a
falsifiable behavior from the cited literature, implement an inspectable input/output
contract, and evaluate it on held-out real machine history captured through SIA's front
door against an explicit dense-retrieval baseline. Report recall@k, nDCG or MRR, latency,
and the applicable memory-fidelity measures, with derived arithmetic routed through
JACKAL and its status class carried verbatim. A mechanism keeps a neurocognitive name only
after a held-out win; otherwise it is fixed or renamed and every product surface loses the
unsupported claim. This roadmap records no per-mechanism win yet.

## Historical project snapshot (measured 2026-09-02)

**Proven and usable today — capture and recall.** Origin-labeled capture across nine source
adapters, the git-versioned corpus (1,604 pages), local recall, the Ed25519 signed ledger
(seq 4,600+, chains passing), the cockpit, the MCP surface, and — as of v1.5.1 — a nightly
SM-2 rehearsal that actually grades: the first two real cycles recorded
`reviewed=5 embedded=5 failed=0` and
`reviewed=2 embedded=2 failed=0` in the signed ledger, after a lifetime of silent
`reviewed=0`. The SIA↔gbrain seam that shipped both real defects is now pinned by
`tests/test_gbrain_contract.py` against the real binary, locally and in CI.

**Unproven, honestly labeled — the retrieval and rehearsal policies.** The whitepaper
states it plainly: the associative tie-breaker matched the unmodified hybrid query on the historical
probe set and did not beat it, and this release contains no controlled evidence that
rehearsal improves answer quality.

**The instruments, read today:**

| Instrument | Baseline (2026-09-02) | What it needs |
|---|---|---|
| Calibration record | **0 resolved grades** (1 legacy row excluded as invalid; 3 open takes, 2 past due ungraded; monitoring-eligibility needs 30 resolved, ≥5 per class) | committed takes + a grading decision (§P1.2) |
| Nightly drift tripwire | 8 rows; latest: blend reciprocal-slug-rank **0.562** vs keyword **0.844** — the blend is *underperforming* on the current 8-probe set | investigation (§P1.1) — this is the whitepaper's own "operator-visible warning that must be investigated" |
| Rehearsal efficacy | no data existed before 2026-09-02 03:05Z (the grader never worked); repetition histories begin accumulating now | weeks of cycles + the efficacy report (§P1.3) |
| `sia bench` | runnable; scored QA over the signed ledger | periodic runs on a fixed cadence (§P1.4) |
| Module size | `bin/sialib.py` = 516,796 bytes of the 524,288 marketplace cap (98.6%) | the extraction series (§P2) |

---

## Historical Phase 0 — The Freeze (originally 2026-09-02 → 2026-09-30)

The capability-freeze portion below is superseded only for the current operator-directed
construction described above. Its `main`/marketplace rule and quality gates remain hard
constraints.

**Frozen:** new source adapters, new retrieval or rehearsal policies, new subsystems,
cockpit features, chain anchoring into sibling projects, gbrain pin bumps (except a
security fix upstream), new documentation *surface* (docs may get shorter or truer, not
longer).

**Allowed:** defect fixes with tests; marketplace-verification support for the already-bound
commit; the §P1 instruments (they measure, they do not add capability); the §P2 extractions
(they remove mass, not add it); claim corrections anywhere a document overstates the code.

**Why:** sixteen releases in five days built more surface than any reader can hold, and the
one part of the system that needed attention — the seam with gbrain — got it only after two
shipped defects. The bottleneck is no longer code. Every gate below is measurable, so the
freeze ends on evidence, not on mood.

**Standing gates (enforced, not aspirational):**
- The full test suite (900+) and the real-gbrain contract lane green on every commit; a
  contract-lane skip in CI is a failure. The shell-lint lane counts: shellcheck reported
  one finding on `install.sh` between v1.7.2 and v1.7.5, and a red lane is a red gate.
- `README.md` stays ≤ 500 lines (a shape test enforces this — a size ceiling like the
  marketplace's 512 KB cap, not a vocabulary assertion).
- Any new gbrain invocation shape lands with a probe in `tests/test_gbrain_contract.py`
  in the same commit. `GbrainArgvGate` in that file enforces it: it reads every argv
  the runtime hands gbrain out of `bin/`'s own AST and fails on any subcommand path
  this lane does not probe. It was written after the v1.7.5 audit found this gate
  held by discipline alone — and it immediately caught two shapes that had already
  slipped through, `query` and `schema validate`.
- **`main` is frozen while marketplace verification is pending.** The verify flow binds
  one exact SHA and the automation refuses when that SHA is no longer default-branch
  HEAD, so any push to `main` invalidates the evidence chain it is waiting on. Landing
  work during a pending verification is not a tradeoff against velocity; it is the
  reason the last three verification attempts produced no publishable chain. Queue on a
  branch, and push only after the listing flips or the maintainer closes the cycle.
  - The one exception, and it is deliberately not a loophole: **a reviewer block on the
    bound commit itself.** A block ends that attempt, so there is no longer a validation
    in flight for a push to invalidate; and the fix has to be at HEAD, because HEAD is
    the only thing the next attempt can bind. A blocking finding may therefore move
    `main` — once, carrying the fix for that finding and nothing else that was waiting.
    Everything else keeps waiting on its branch. If a push to `main` cannot be traced to
    a block on the commit currently bound, the freeze applies and the answer is no.
    Because automation cannot observe the reviewer's decision, record the ended attempt
    first with a declaration-only `state=none` commit. That administrative closure is not
    the fix: the following push is the one permitted fix-only movement of `main`, and a
    later validation attempt must bind its resulting exact SHA separately.
  - The rule is mechanically checked by the `marketplace-freeze` job in
    `.github/workflows/ci.yml`, which reads the declaration below and turns a push
    to the frozen branch that is not the bound commit red. It cannot protect the
    branch — that is a GitHub setting — but the rule is no longer invisible, and a
    declaration it cannot read is a failure rather than a silent pass.

---

## Phase 1 — Behavior evaluation (runs through the freeze and beyond)

The project's thesis is that a memory system should keep honest books. Phase 1 makes SIA
keep honest books **about its own retrieval and rehearsal claims**, using its own
instruments. The original subsections measure existing machinery; the controlling P1.0
gate also permits only the construction needed by the current operator directive.

### P1.0 — Current held-out dense-baseline gate

This gate controls the cognitive names; the older tripwire and rehearsal studies below
remain useful diagnostics but cannot substitute for it. Build a train/tune/held-out split
from real retained machine history through the public SIA capture boundary, freeze the
held-out answers before tuning, and run the same questions and candidate corpus through
the dense baseline and each single-mechanism intervention. Publish per-query outputs and
aggregate recall@k, nDCG or MRR, latency, and memory-fidelity measures. Route the metric
arithmetic through JACKAL and preserve the returned status and non-claims. A tie, loss,
missing witness, contaminated split, or refused arithmetic is not a win.

No older keyword tripwire, historical associative parity result, component unit test, or
successful runtime publication earns a neurocognitive label. The fail-closed claim gate
must consume the held-out artifact and either admit the measured claim or require the
name/surface copy to be stripped.

### P1.1 — Investigate the live tripwire warning (first, it is already flashing)

The 2026-09-02 tripwire row shows the blend at 0.562 vs keyword at 0.844. Per the
whitepaper's own policy this is a warning that must be investigated before any future
retrieval policy is accepted. Bounded investigation, in order:
1. Read the per-probe rows: is the deficit concentrated in a probe family (e.g. the new
   pages from this week's heavy sessions) or uniform?
2. Check whether the 8-probe set still reflects the corpus (it predates the last ~400
   pages); if stale, extend the probe set *as data, not code* — hand-authored acceptors,
   reviewed by the operator, committed to the corpus.
3. Only if the deficit is real and uniform: consider demoting the blend behind a
   default-off config flag. That change is *permitted during the freeze* because it removes
   an unproven influence; the whitepaper §4.3 policy text would be updated in the same
   commit. The verdict must come from the extended probe set, not the 8-row baseline.
   Non-claims stay attached: slug proximity is a drift heuristic, not answer correctness.

### P1.2 — Grow the calibration population from zero (operator decisions required)

The record cannot call itself monitoring-eligible before **30 resolved grades with ≥5 in
each outcome class**. It has zero. Two decisions belong to the operator alone:

1. **The judge.** Takes cannot resolve to TRUE/FALSE without a grading path, and the judge
   is off by default because enabling it sends recalled context to a configured Claude
   model. The deliberate choice: enable it (`judge.backend: "claude"` + explicit
   `judge.model` in `~/.config/sia/config.json`), accept its disclosed boundary, and let
   the nightly scheduled run grade up to three due takes; or leave it off and accept that
   the calibration lane stays empty. Recommendation: enable it for the evaluation window — grading
   sends only recalled evidence for takes the operator chose to commit, and the abstention
   audit keeps refusals honest. Revisit after the study.
2. **The takes.** Agents propose; only the operator commits — a model that mints the takes
   it later helps grade is too neat a loop, so these are written here as *ready-to-run
   commands*, not run by the agent that drafted them:

```bash
# The retrieval-and-rehearsal lane's own claims, made falsifiable. Adjust confidences to
# taste — they are yours, not the drafter's. Spread deadlines so grading work arrives
# steadily.
sia take "The extended (>=20-probe) tripwire set will show the associative blend within 0.05 of keyword reciprocal-slug-rank" --confidence 0.5 --by 2026-09-21 --domain self-measurement
sia take "By the deadline, at least 10 SM-2 rehearsal cycles will have completed with failed=0 in the signed ledger" --confidence 0.8 --by 2026-09-21 --domain self-measurement
sia take "Rehearsed pages will show a higher bench retrieval hit-rate than matched unrehearsed pages in the first efficacy report" --confidence 0.45 --by 2026-10-07 --domain self-measurement
sia take "The calibration record will reach 30 resolved grades" --confidence 0.4 --by 2026-10-15 --domain self-measurement
sia take "sialib.py will be under 400 KB with the full suite green" --confidence 0.7 --by 2026-10-07 --domain self-measurement
sia take "The marketplace listing will show a verified v1.5.1 snapshot" --confidence 0.6 --by 2026-09-16 --domain custody
```

   Beyond the evaluation, commit ordinary machine-life takes weekly (crashes, upgrades,
   healings — the domains that already exist). Thirty grades is roughly six weeks of five
   takes a week; the population grows by use, not by time.

### P1.3 — The rehearsal-efficacy report (the one number that settles the headline claim)

Rehearsal histories exist only since 2026-09-02. Once ≥10 cycles have run, add a small
derived report (scheduled-run time, deterministic, no model):

- **Partition** bench/tripwire probe targets into rehearsed (≥1 successful SM-2 review)
  vs never-rehearsed pages, matched on age band and source adapter.
- **Report** retrieval hit-rate for each partition, with population sizes, in the
  scheduled-run receipt and `sia memory` output. Label it descriptive; no significance claim.
- **Interpretation rule, fixed in advance:** if after 4 weeks the rehearsed partition shows
  no advantage, the honest conclusion is that rehearsal is (so far) retention hygiene, not
  retrieval improvement — and the README's retrieval section says so. If it shows an
  advantage, the whitepaper §11 sentence about "no controlled evidence" gets replaced by
  the measured sentence. Either way the docs move toward the data.

### P1.4 — Fixed measurement cadence

- `sia bench generate` weekly (same day, same corpus-relative scope), trend recorded.
- `sia calibration` reviewed weekly; unresolvable/invalid exclusions investigated, not
  ignored (the current 1 invalid legacy row: root-cause once, during P1.2 setup).
- The tripwire runs nightly on its own; its trend is reviewed with the bench run.

---

## Phase 2 — The split (one extraction per release)

Per `docs/ARCHITECTURE.md` (the measured lane map and the three verified constraints):
extraction is a *designed* change — introducing a runtime member requires a
new rung in the runtime ladder and its installer/test contracts. Expanding an
existing child's coherent ownership preserves that member set while extending
its exact export contract. The monkeypatched-globals hazard is documented in
the repo itself, and `bin/siarelease.py:RUNTIME_LADDER` is the current
member-set authority.

| Release | Extraction | Lines (approx.) | Status |
|---|---|---|---|
| **v1.6.0** | **exports lane → `bin/siagraph.py`** | ~1,000 | **DONE** — 857-test suite + façade smoke green; sialib 517 KB → 477 KB |
| **v1.7.5** | **outside audit of that extraction, closed** | — | **DONE** — @m10ust: no HIGH/MEDIUM; the three conventions it named are now tests (façade export pin, four-site rung ladder, `bind()` seam) |
| Unreleased | generated-entry/epoch pages, weekly compaction + recovery/legacy replay | See current source | **IMPLEMENTED**; compatibility-named thought-recovery, epoch-completeness and module-ownership tests are the gates |
| Unreleased | durable controller-source effects and acknowledgment (`siasourceeffects`, `siasourcegit`, `siasourceengine`, `siasourceack`) | See current source | **COMPONENT CONTRACTS IMPLEMENTED**; v8 packages the closure, readiness refuses pending ACK, and resident front-door invocation remains a separate proof obligation |
| Unscheduled | cursors lane | ~1,100 | last (senses-substrate; most entangled) |

Order revised from the original guess after four parallel extraction maps:
exports scored decisively cleanest and led. See `docs/ARCHITECTURE.md`.

The longer-term sizing target remains `sialib.py` < 400 KB, but no release is assigned to
it. Each extraction stays small enough for a human to read the diff end to end, which is
the entire point. The pulse lane (4,373 lines) is deliberately **not** scheduled: it is the
transaction core, and any future split requires its own performance and upgrade/rollback
plan on a real machine.

**Review invitations (with, not after, v1.6.0):** SENT 2026-09-02 —
[m10ust](https://github.com/AnubisQuantumCipher/sia/issues/2#issuecomment-5507962051)
(installer/member-set lane) and
[webdevtodayjason](https://github.com/AnubisQuantumCipher/sia/issues/1#issuecomment-5507962249)
(Obsidian source-adapter contract across the series), each with an explicit standing-reviewer
offer. Original intent: ask
[@m10ust](https://github.com/m10ust) to review the installer/member-set changes (they
audited exactly that lane in issue #2 and called its hygiene the best they had seen), and
[@webdevtodayjason](https://github.com/webdevtodayjason) to sanity-check the Obsidian source adapter
against the extractions. Credited reviewers who already found real defects are
co-maintainers in waiting; the ask makes it explicit.

---

## Phase 3 — The verdict (v2.0 decision point, ~2026-10-15)

With ≥6 weeks of instrument data, the retrieval-and-rehearsal evaluation lane gets one
of three honest outcomes, decided by the numbers on the table above — not by affection
for the policies:

1. **Promote.** The efficacy report shows rehearsed pages retrieving better AND the
   extended tripwire shows the blend at parity or better: the whitepaper's "no controlled
   evidence" sentence is replaced with the measurement, and the freeze lifts for the next
   deliberate capability.
2. **Hold.** Mixed or insufficient data: the freeze extends, the evaluation continues, and
   the README keeps saying "research program" — which costs nothing, because capture and
   recall are the product.
3. **Demote.** The blend keeps losing to keyword and rehearsal shows no retrieval effect:
   the blend goes behind a default-off flag, rehearsal is redescribed as retention hygiene,
   and the retrieval and rehearsal claims shrink to what was measured. The system's own
   thesis — the class of a fact matters more than the fluency of the answer — applies to
   its own marketing first.

Also at the decision point, *only if* outcome 1 or a stable 2: revisit the deferred items
below in priority order.

## Explicit non-goals during this roadmap

Deferred with reasons, not forgotten:
- **Chain anchoring into ATTEST/SEKHMET** — real value, but it is exactly the
  cross-project dependency growth that overexpanded the system once already. After the split.
- **New source adapters / senses** — each is surface area; the existing nine are not yet fully
  studied by their own instruments.
- **Cockpit features** — the cockpit's job during the study is to display the instruments
  it already has, honestly.
- **gbrain pin bump** — the pin is verified and the contract lane now guards the seam;
  bump deliberately (`sia bench` + `sia judge-audit` before and after, per `GBRAIN_PIN`),
  not opportunistically, and only through a dedicated compatibility change.
- **A second marketplace submission** — SIA is already listed; updates flow through the
  existing verify path only.

This historical deferral list does not defer the operator-directed Build the Mind work in
the current amendment. It still forbids unrelated scope growth and cannot be used to
launder an unmeasured mechanism into the product.

## Marketplace track (external, in parallel)

Verify issue #4078 has been retargeted three times, and every retarget had a defensible
local reason: a grading defect that should not have become the verified snapshot
(`ac3483fd` → `3cb08d8`), then two shipped releases (`3cb08d8` → `817717d`), then four
defect-fix releases on 2026-09-03 that closed a real memory-loss bug (`817717d` →
`2307182`, v1.7.8). Each reason was good and the pattern was still churn, because the
maintainer's constraint is not "bind a good commit" but "bind the commit that is
currently HEAD" — and this repository kept moving HEAD.

The correction is upstream of the verify form: **do not push to `main` while a
verification is pending.** The current review binds `8a624ef…` with the form intact.
Until the listing flips or the maintainer closes the cycle, releases queue on branches.
After it flips, normal cadence resumes — one re-bind per release, after tagging, and
never while validation is in flight.

The binding is declared here, in one machine-readable line, because a rule only a
reader can see is the rule that was already broken three times. CI reads this exact
line (`.github/workflows/ci.yml`, job `marketplace-freeze`): while the state is
`pending`, a push to the named branch that is not the named commit fails the build.
Closing the cycle means editing the line to `state=none`; re-binding means editing
`sha=` and nothing else in the same commit, because no commit can name its own SHA.

    sia-freeze: state=pending branch=main sha=8a624efc911457ae393a72758ade8729de5ba45d

---

*The short version: the source/live transaction is now an inspectable, fail-closed set of
components, but resident invocation and cognitive efficacy are separate claims that still
need front-door evidence. Build the named mechanisms, measure each against dense retrieval
on held-out real history, and keep only the names the numbers earn.*
