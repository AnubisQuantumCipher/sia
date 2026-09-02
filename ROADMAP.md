# ROADMAP — from shipped laboratory to measured system

*Written 2026-09-02, immediately after v1.5.1. This document applies the project's own
hypothesis-lane freeze rule (Whitepaper §11) to the project itself: nothing in the cognitive
lane is promoted — and no new capability is added — except on a measured showing. The next
phase of SIA is not more machinery. It is evidence about the machinery that exists.*

## Where the project actually stands (measured 2026-09-02)

**Proven and usable today — the historian.** Origin-labeled capture across nine organs, the
git-versioned corpus (1,604 pages), local recall, the Ed25519 signed ledger (seq 4,600+,
chains passing), the cockpit, the MCP surface, and — as of v1.5.1 — a nightly SM-2 rehearsal
that actually grades: the first two real cycles recorded `reviewed=5 embedded=5 failed=0` and
`reviewed=2 embedded=2 failed=0` in the signed ledger, after a lifetime of silent
`reviewed=0`. The SIA↔gbrain seam that shipped both real defects is now pinned by
`tests/test_gbrain_contract.py` against the real binary, locally and in CI.

**Unproven, honestly labeled — the mind.** The whitepaper states it plainly: the associative
tie-breaker matched dense retrieval on the historical probe set and did not beat it, and this
release contains no controlled evidence that rehearsal improves answer quality.

**The instruments, read today:**

| Instrument | Baseline (2026-09-02) | What it needs |
|---|---|---|
| Calibration record | **0 resolved grades** (1 legacy row excluded as invalid; 3 open takes, 2 past due ungraded; monitoring-eligibility needs 30 resolved, ≥5 per class) | committed takes + a grading decision (§P1.2) |
| Nightly drift tripwire | 8 rows; latest: blend reciprocal-slug-rank **0.562** vs keyword **0.844** — the blend is *underperforming* on the current 8-probe set | investigation (§P1.1) — this is the whitepaper's own "operator-visible warning that must be investigated" |
| Rehearsal efficacy | no data existed before 2026-09-02 03:05Z (the grader never worked); repetition histories begin accumulating now | weeks of cycles + the efficacy report (§P1.3) |
| `sia bench` | runnable; scored QA over the signed ledger | periodic runs on a fixed cadence (§P1.4) |
| Module size | `bin/sialib.py` = 516,796 bytes of the 524,288 marketplace cap (98.6%) | the extraction series (§P2) |

---

## Phase 0 — The Freeze (now → 2026-09-30)

**Frozen:** new organs, new cognitive mechanisms, new subsystems, cockpit features, chain
anchoring into sibling projects, gbrain pin bumps (except a security fix upstream), new
documentation *surface* (docs may get shorter or truer, not longer).

**Allowed:** defect fixes with tests; marketplace-verification support for the already-bound
commit; the §P1 instruments (they measure, they do not add capability); the §P2 extractions
(they remove mass, not add it); claim corrections anywhere a document overstates the code.

**Why:** sixteen releases in five days built more surface than any reader can hold, and the
one part of the system that needed attention — the seam with gbrain — got it only after two
shipped defects. The bottleneck is no longer code. Every gate below is measurable, so the
freeze ends on evidence, not on mood.

**Standing gates (enforced, not aspirational):**
- The full test suite (848+) and the real-gbrain contract lane green on every commit; a
  contract-lane skip in CI is a failure.
- `README.md` stays ≤ 500 lines (a shape test enforces this — a size ceiling like the
  marketplace's 512 KB cap, not a vocabulary assertion).
- Any new gbrain invocation shape lands with a probe in `tests/test_gbrain_contract.py`
  in the same commit.
- No retarget of marketplace issue #4078; `3cb08d8…` is final, as promised there.

---

## Phase 1 — The self-study (runs through the freeze and beyond)

The project's thesis is that a memory system should keep honest books. Phase 1 makes SIA
keep honest books **about its own cognition claims**, using its own instruments. Nothing
here is new machinery; it is the existing machinery pointed at the mirror.

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
   the nightly dream grade up to three due takes; or leave it off and accept that the
   calibration lane stays empty. Recommendation: enable it for the study window — grading
   sends only recalled evidence for takes the operator chose to commit, and the abstention
   audit keeps refusals honest. Revisit after the study.
2. **The takes.** Agents propose; only the operator commits — a model that mints the takes
   it later helps grade is too neat a loop, so these are written here as *ready-to-run
   commands*, not run by the agent that drafted them:

```bash
# The cognitive lane's own claims, made falsifiable. Adjust confidences to taste — they
# are yours, not the drafter's. Spread deadlines so grading work arrives steadily.
sia take "The extended (>=20-probe) tripwire set will show the associative blend within 0.05 of keyword reciprocal-slug-rank" --confidence 0.5 --by 2026-09-21 --domain self-measurement
sia take "By the deadline, at least 10 SM-2 rehearsal cycles will have completed with failed=0 in the signed ledger" --confidence 0.8 --by 2026-09-21 --domain self-measurement
sia take "Rehearsed pages will show a higher bench retrieval hit-rate than matched unrehearsed pages in the first efficacy report" --confidence 0.45 --by 2026-10-07 --domain self-measurement
sia take "The calibration record will reach 30 resolved grades" --confidence 0.4 --by 2026-10-15 --domain self-measurement
sia take "sialib.py will be under 400 KB with the full suite green" --confidence 0.7 --by 2026-10-07 --domain self-measurement
sia take "The marketplace listing will show a verified v1.5.1 snapshot" --confidence 0.6 --by 2026-09-16 --domain custody
```

   Beyond the self-study, commit ordinary machine-life takes weekly (crashes, upgrades,
   healings — the domains that already exist). Thirty grades is roughly six weeks of five
   takes a week; the population grows by use, not by time.

### P1.3 — The rehearsal-efficacy report (the one number that settles the headline claim)

Rehearsal histories exist only since 2026-09-02. Once ≥10 cycles have run, add a small
derived report (dream-time, deterministic, no model):

- **Partition** bench/tripwire probe targets into rehearsed (≥1 successful SM-2 review)
  vs never-rehearsed pages, matched on age band and organ.
- **Report** retrieval hit-rate for each partition, with population sizes, in the dream
  receipt and `sia memory` output. Label it descriptive; no significance claim.
- **Interpretation rule, fixed in advance:** if after 4 weeks the rehearsed partition shows
  no advantage, the honest conclusion is that rehearsal is (so far) retention hygiene, not
  retrieval improvement — and the README's "mind" section says so. If it shows an
  advantage, the whitepaper §11 sentence about "no controlled evidence" gets replaced by
  the measured sentence. Either way the docs move toward the data.

### P1.4 — Fixed measurement cadence

- `sia bench generate` weekly (same day, same corpus-relative scope), trend recorded.
- `sia calibration` reviewed weekly; unresolvable/invalid exclusions investigated, not
  ignored (the current 1 invalid legacy row: root-cause once, during P1.2 setup).
- The tripwire runs nightly on its own; its trend is reviewed with the bench run.

---

## Phase 2 — The split (v1.6.x, one extraction per release)

Per `docs/ARCHITECTURE.md` (the measured lane map and the three verified constraints):
extraction is a *designed* change — the `siasenses.py` bind/invoke façade plus a
`sia-runtime-v5` member-set revision in the three digest sites and the installer/test
lists. Never a mechanical move; the monkeypatched-globals hazard is documented in the
repo itself.

| Release | Extraction | Lines (approx.) | Status |
|---|---|---|---|
| **v1.6.0** | **exports lane → `bin/siagraph.py`** | ~1,000 | **DONE** — 857-test suite + façade smoke green; sialib 517 KB → 477 KB |
| v1.6.1 | thought-pages + recovery/legacy replay | ~1,870 | next; `test_thought_recovery.py` is the gate |
| v1.6.2 | cursors lane | ~1,100 | last (senses-substrate; most entangled) |

Order revised from the original guess after four parallel extraction maps:
exports scored decisively cleanest and led. See `docs/ARCHITECTURE.md`.

Target: `sialib.py` < 400 KB by v1.6.2 — roughly 23% below the marketplace cap instead of
1.4%. Each release is small enough for a human to read the diff end to end, which is the
entire point. The pulse lane (4,373 lines) is deliberately **not** scheduled: it is the
transaction core, and it gets split only after three successful façade extractions have
proven the pattern under upgrade/rollback on a real machine.

**Review invitations (with, not after, v1.6.0):** SENT 2026-09-02 —
[m10ust](https://github.com/AnubisQuantumCipher/sia/issues/2#issuecomment-5507962051)
(installer/member-set lane) and
[webdevtodayjason](https://github.com/AnubisQuantumCipher/sia/issues/1#issuecomment-5507962249)
(Obsidian-organ contract across the series), each with an explicit standing-reviewer
offer. Original intent: ask
[@m10ust](https://github.com/m10ust) to review the installer/member-set changes (they
audited exactly that lane in issue #2 and called its hygiene the best they had seen), and
[@webdevtodayjason](https://github.com/webdevtodayjason) to sanity-check the Obsidian organ
against the extractions. Credited reviewers who already found real defects are
co-maintainers in waiting; the ask makes it explicit.

---

## Phase 3 — The verdict (v2.0 decision point, ~2026-10-15)

With ≥6 weeks of instrument data, the cognitive lane gets one of three honest outcomes,
decided by the numbers on the table above — not by affection for the mechanisms:

1. **Promote.** The efficacy report shows rehearsed pages retrieving better AND the
   extended tripwire shows the blend at parity or better: the whitepaper's "no controlled
   evidence" sentence is replaced with the measurement, and the freeze lifts for the next
   deliberate capability.
2. **Hold.** Mixed or insufficient data: the freeze extends, the study continues, and the
   README keeps saying "research program" — which costs nothing, because the historian is
   the product.
3. **Demote.** The blend keeps losing to keyword and rehearsal shows no retrieval effect:
   the blend goes behind a default-off flag, rehearsal is redescribed as retention hygiene,
   and the cognitive claims shrink to what was measured. The system's own thesis — the
   class of a fact matters more than the fluency of the answer — applies to its own
   marketing first.

Also at the decision point, *only if* outcome 1 or a stable 2: revisit the deferred items
below in priority order.

## Explicit non-goals during this roadmap

Deferred with reasons, not forgotten:
- **Chain anchoring into ATTEST/SEKHMET** — real value, but it is exactly the
  cross-project immune-system growth that overgrew the body once already. After the split.
- **New organs / senses** — each is surface area; the existing nine are not yet fully
  studied by their own instruments.
- **Cockpit features** — the cockpit's job during the study is to display the instruments
  it already has, honestly.
- **gbrain pin bump** — the pin is verified and the contract lane now guards the seam;
  bump deliberately (`sia bench` + `sia judge-audit` before and after, per `GBRAIN_PIN`),
  not opportunistically, and only after v1.6.0 proves the façade pattern.
- **A second marketplace submission** — SIA is already listed; updates flow through the
  existing verify path only.

## Marketplace track (external, in parallel)

v1.5.1 (`3cb08d8…`) is bound in verify issue #4078 with the form intact and a stated
promise of no further retargets. When the maintainer publishes: confirm the listing flips,
then normal cadence — each future release re-binds through the same verify flow, once,
after tagging. Nothing else; the churn is over.

---

*The short version: the historian is finished enough to trust. The mind became a testable
experiment at 03:05 this morning, when its apparatus worked for the first time. This
roadmap spends the next six weeks running that experiment instead of building a bigger
laboratory — and commits, in advance and in writing, to believing the result.*
