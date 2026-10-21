# Continuity proof experiments, 2026-10-21 UTC

Status: **UNADOPTED**. Complete qualification still fails the existing time
limit. These experiments do not modify the branch's authority or test sources.
They are retained to prevent a later session from repeating failed work or
treating focused passes as complete acceptance.

The [derived evidence manifest](CONTINUITY-PROOF-SEARCH-EVIDENCE.json) binds
each source base, archive, overlay, command, tool identity, log and result.
The two candidate patches are reproducible against their respective archived
base commits. They are evidence artifacts, not active project source.

The patches are now stored as lossless `.patch.gz` archives; the original patch
bytes and original manifest remain bound to commit
`e1e339f08d1287815172f22e868cc200756cc5b5`. The
[archive manifest](CONTINUITY-PROOF-ARCHIVE-EVIDENCE.json) records both compressed
and original hashes. Decompress before applying to the recorded base. This
avoids treating unified-diff context markers as source whitespace violations;
it changes no patch content and adds no exception to the repository check.

| Experiment | Observed result | Interpretation |
| --- | --- | --- |
| Original continuity unit, CVC5-first diagnostic | Exit 124 at the 120-second diagnostic limit; no fresh summary | Changing prover order alone did not establish a complete unit result |
| Extract frozen equivalence and partition checks into a pure test package | Strict build and continuity runtime passed; focused package discharged 50 checks | Scoped result; six independent reference expressions and original assertions preserved |
| Full predicate-extraction campaign | Build and all eleven runtimes passed; full proof exit 124 at 600 seconds; no fresh summary | Full coverage validation UNRUN; extraction unadopted |
| Extract capacity mutations through an in-out helper | Strict build rejected an overwritten-value warning | Failed attempt retained; warning policy preserved |
| Keep those mutations in an input-only helper's local copy | Build and original continuity runtime passed; helper discharged 7 checks and caller discharged 16 checks in separate focused runs | Both scoped summaries retain their modular dependencies; not a combined project result |
| Full local-copy campaign | Build and all eleven runtimes passed; full proof exit 124 at 600 seconds; no fresh summary | Full coverage validation UNRUN; candidate unadopted |

The predicate extraction preserves the six frozen `Original_*` functions,
three checking procedures, their contracts and their runtime call order.
Its package alone uses CVC5, Z3, then Alt-Ergo. Retained generated translator
settings confirmed that the warnings, all-mode analysis, no-inlining and
resource settings were inherited. The active project configuration is unchanged.

The local-copy helper preserves the original seven mutation/check statements.
Its precondition requires the already established valid, coverage-ready,
full-capacity checkpoint and exact constructed operation array. The concrete
caller proves these conditions. The helper's local state is discarded after
the checks; the original caller immediately reset the same state before its
remaining malformed-operation controls. Those controls remain intact.

Independent actual GPT-6.1 source reviews found no lost fixtures, assertions,
domains or observable results. Those model-generated reviews are separate from
compiler/prover evidence and did not establish complete-project acceptance.
The review texts remain in the pinned local evidence directory.

This applies the Power of Ten intent of small routines, meaningful checked
contracts, narrow scope and strict diagnostics. No `pragma Assume` annotations,
proof exclusions, warning suppressions or narrower original test domains were
introduced. Ordinary modular dependency assumptions remain explicit.
All attempts retain one proof job, 512 MB per prover and a 10-second per-check
limit. Full campaigns retain 600 seconds; diagnostics retain 120 seconds.
The proposed 900-second full-campaign limit remains unapproved and unused.

The complete failed runs retained partial raw reports without non-information
diagnostics in their completed units. This does not establish the uncompleted
units or the whole project's coverage. Both stopped while the transition-test
unit was in progress. Solver-attempt timings are not whole-command wall times.
The local-copy experiment did not establish an overall performance improvement.

Next acceptance requires a fresh strict build, every original runtime harness,
complete `-U` proof, raw/summary coverage checks, committed-source reproduction
and independent evidence review. Do not repeat an unchanged failed campaign or
adopt these candidates from their focused results. Runtime integration,
installed harness continuity and marketplace publication remain separate gates.

## Transition helper follow-up

The [transition experiment manifest](CONTINUITY-TRANSITION-PROOF-SEARCH-EVIDENCE.json)
retains the next attempts, including the failed extraction and compiler result.
Its compressed patch contains the complete unadopted overlay against its exact
base, including the earlier predicate and local-copy changes. Decompression
preserves the original patch bytes; it is not active project source.

| Attempt | Retained outcome |
| --- | --- |
| Original transition unit, CVC5-first | Diagnostic exit 124 at 120 seconds; no fresh summary |
| Helper extraction v1 | Extractor failed before build/proof because it assumed a declaration line break |
| Helper extraction v2 | Strict compilation refused a non-static composite constant in a pure package |
| Helper extraction v3 | Strict build and original transition runtime passed; extracted helper package discharged 13 checks; complete caller diagnostic timed out at 120 seconds |
| Helper extraction v4 | Restored the synthetic-observation boundary comment; Alt-Ergo-first caller diagnostic timed out at 120 seconds; no new build/runtime claim |
| Complete extraction v5 | Fresh strict build and all eleven original runtimes passed; full `-U` proof exited 124 at 600 seconds without a fresh summary; coverage validation UNRUN |

The extraction preserves `Event`, `Expected`, `Check` and `Check_Unchanged`,
their conditions/contracts and executable statements. The empty-observation
constant becomes a zero-argument pure expression function with the same exact
aggregate. Remaining fixtures, assertions and calls retain their order.
Independent actual GPT-6.1 source review found no semantic loss; its requested
comment was restored before the full attempt. The helper's focused proof does
not establish its callers or complete project coverage.

All these candidates remain **UNADOPTED**. No authority source, original test
domain, warning setting or resource limit was weakened. The full attempt's
proof-tool hashes matched before and after execution. Partial raw reports are
retained even though no complete summary was produced.

A subsequent read-only review proposed sharing the two parameterized rejection
checks behind an explicitly checked helper. That proposal still needs body and
caller proof, all original runtime controls, and complete all-unit acceptance.
No performance benefit has been established, and another unchanged full run is
not justified by these results.
