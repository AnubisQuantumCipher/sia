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

The [shared-rejection follow-up](CONTINUITY-UNBOUND-HELPER-EVIDENCE.json)
implements that proposal in another external candidate. Both local `Refuse`
wrappers retain their exact preconditions; their duplicated bodies call the
new `Check_Unbound_Event` helper. It requires the preceding classification
branches, the existing one-operation shape, a changed slot and a mismatched
observation. Its body retains the original observation aggregate and expected
refusal. No negative vector, fixture, assertion or call order changes.
Independent actual GPT-6.1 source review found no semantic or domain loss;
the additional premises remain caller obligations rather than assumptions.

Strict build and the original transition runtime passed. Separate focused
proofs discharged the helper package, both wrappers and both caller routines,
with fresh summaries and no non-information diagnostics in their retained raw
reports. These are separate scoped results; do not add their overlapping
counts or infer complete coverage. A fresh complete transition-unit diagnostic
still reached 120 seconds without a summary. No full-project attempt was made
on this further changed source. It remains **UNADOPTED**, with performance
improvement and complete acceptance unproved.

## Array and empty-transition proof decomposition

These external candidates preserve the earlier reference-check extraction,
capacity mutations and shared rejection helper. They add checked test lemmas;
the authority packages and original test domains are unchanged. The evidence
manifest records exact source overlays, commands, raw results, effective
settings and failed attempts. Full acceptance is evaluated separately from the
scoped results below.

| Attempt | Observed scoped result |
| --- | --- |
| Capacity assertions | Strict build/runtime and focused caller passed; the expensive obligation moved into the new validity assertion |
| Dispatch frame v1 | Strict compiler rejected missing visibility of digest equality; subsequent checks unrun |
| Dispatch frame v2 | Build/runtime, array lemma and original concrete mutation caller passed; raw attempts retain solver timeouts followed by successful fallbacks |
| Initialization lemma v1 | Strict compiler rejected a redundant body import; subsequent checks unrun |
| Initialization lemma v2 | Build/runtime, both operation helpers and the original capacity-construction caller passed; the caller's raw attempts have no solver timeout |
| Empty-transition helper | Build/runtime, helper and concrete caller passed; all three original classification checks and exact fixture construction remain |
| Targeted helper prover order | Strict build/runtime and operation-helper proof passed with CVC5 first for that package only; complete-project speed improvement is not inferred |

The dispatch lemma requires a valid operation array, an active index and an
exact single-field stage update. Its checked body preserves operation validity,
identities and canonical padding. The initialization lemma converts the
fixture's already asserted distinct first identity bytes into full identity
inequality; active validity and empty-tail premises remain concrete caller
obligations. Neither lemma grants permission or changes policy decisions.

The empty-transition helper separates exact fixture construction from three
classification implications. Its premises require valid checkpoints, joined
task/link/watermark fields and the original empty, planned and dispatched
operation shapes. The original three calls and their order remain in its body.
Independent actual GPT-6.1 source review found no lost fixtures, weakened
domains or changed oracles. That review did not independently rerun the proof.

This is an adaptation of the Power of Ten intent, not a quotation or compliance
claim. Static calls, fixed array domains, checked contracts and smaller routines
support controls 1, 2, 4, 5, 6 and 9. Original malformed-input and refusal cases
support control 7. The explicit project settings and strict compiler failures
remain visible under controls 8 and 10. No suppression, assumption annotation,
test exclusion or increased resource cap is introduced. Fixed typed arrays do
not establish total stack bounds or whole-runtime allocation compliance with
control 3; those remain separate resource obligations.

The effective GNATprove settings are retained. The existing predicate helper
and new operation helper use CVC5, Z3, then Alt-Ergo; other units retain their
original order. All-mode analysis, no-inlining, enabled tagged warnings,
warnings-as-errors, one job, the per-prover memory limit and per-check deadline
remain unchanged. The new helper order follows observed fallbacks and is not a
general claim that one prover is faster.

No scoped pass establishes complete all-unit coverage, committed-source
reproduction, authenticated evidence production, runtime restoration, installed
harness support or marketplace delivery. The original failed attempts remain
part of the evidence rather than being overwritten by later successes.

[Exact-source decomposition evidence](CONTINUITY-DECOMPOSITION-EVIDENCE.json)

The subsequent fresh full attempt passed strict compilation and all eleven
original runtime harnesses. The unchanged all-unit proof command exited 124
at its 600-second limit without a fresh summary. Complete coverage validation
was therefore UNRUN. Tool identities remained unchanged. Completed partial raw
reports contain no non-information diagnostics, but the transition test unit
was still in progress and other required units were not completed. These
observations establish neither complete proof nor an overall speed benefit.
The combined candidate remains **UNADOPTED**. Do not retry it unchanged as an
acceptance attempt or use earlier scoped reports to fill missing full coverage.

## Modular transition checks and symbolic test loops

The [next diagnostic manifest](CONTINUITY-MODULAR-SEARCH-EVIDENCE.json)
retains two additional checked helpers and their exact-source overlay against
`9c831d23af5b86815933789230d8249e2da2aea6`. It is **UNADOPTED**.
No authority implementation, original fixture, runtime iteration, expected
result or test domain was removed. Independent actual GPT-6.1 source reviews
found no concrete preservation or soundness defect; they did not replay proof.

The single-transition helper preserves the five original positive chain checks.
Its concrete callers establish valid joined checkpoints, one changed operation
and the required event kind. The two-event helper retains both the duplicate-ID
refusal and the corrected-ID positive case. Two malformed-observation controls
use the existing rejection helper with their original mutations. Every added
precondition remains an obligation for the original concrete caller.

| Diagnostic | Retained outcome |
| --- | --- |
| Single-transition helper and chain caller | Strict build/runtime and both focused proofs passed |
| Complete transition unit after that extraction | Exit 124 at 120 seconds; no fresh summary |
| Symbolic loops for three continuity test units | Build and selected runtimes passed; first complete-unit diagnostic reached 120 seconds; later diagnostics UNRUN in that attempt |
| Two-event-identity helper and caller | Strict build/runtime and both focused proofs passed |
| Independent whole-unit follow-up | Fresh strict build and all eleven runtime harnesses passed; transition and general continuity units reached 120 seconds; complete observation-wire unit passed |

The symbolic-loop option disables automatic finite-loop expansion for those
three test units. It retains the runtime loops and requires symbolic proof of
their bodies and applicable invariants, termination and caller obligations.
Captured translator settings retain all-mode analysis, no-inlining, enabled
warnings, proof warnings, warnings-as-errors, one job, 512 MB and 10 seconds
per check. This is a proof-strategy adaptation, not a Power of Ten compliance
claim or permission to omit an iteration. Complete project benefit remains
unproved.

Completed scoped raw reports have no non-information diagnostics, assumptions
annotations or proof/flow exclusions. Their overlapping dependency scopes must
not be added together. The two whole-unit timeouts remain failed attempts to
establish those units. The later complete attempt is recorded below; the
existing 600-second gate remains unchanged. A proposed increase requires a
separate operator decision and is not implied by these artifacts.

The retained profiling correction also remains visible: the first parser
defaulted absent XML timing fields to zero; its successor marks those times
UNAVAILABLE. Neither value is used as a measured wall time or acceptance claim.
Exact source reconstruction, full proof/coverage, committed-source reproduction,
independent evidence review and the installed continuity gates remain distinct.

The next [identity-fixture diagnostic](CONTINUITY-IDENTITY-PARAMETER-DIAGNOSTIC.json)
passed the same initial fixture through a parameter constrained to equal that
fixture. Actual GPT-6.1 source review found every original mutation and expected
result preserved, including the epoch-zero negative against the valid baseline's
observations. Strict build and the continuity runtime passed. The focused proof
still exited 124 at 120 seconds without a fresh summary. This attempt remains
**FAILED** as proof establishment and **UNADOPTED**; no speed benefit, caller
proof, complete-unit coverage or all-project acceptance follows. The original
negative result and source delta are retained. The current proof cap is unchanged.

## Complete modular-candidate follow-up

The [terminal full-campaign evidence](CONTINUITY-MODULAR-FULL-EVIDENCE.json)
binds the reviewed modular overlay to the clean `b34b9a7` source archive.
The failed identity-parameter experiment above is excluded. Strict compilation
and all eleven original runtime harnesses passed. Full `-U` analysis exited
124 at the unchanged 600-second limit without a fresh summary, so the complete
coverage gate was **UNRUN**. Tool hashes match before and after the campaign.
The candidate remains **UNADOPTED** and full proof remains **UNPROVEN**.

Completed raw reports include the general continuity and transition harnesses;
their retained diagnostics are informational and their assumption/exclusion
arrays are empty. The last translator invocation was for the continuity
transition authority unit. These partial products do not establish missing
units, complete coverage, a complete-project speed improvement or acceptance.
Do not fill their gaps using earlier focused reports or rerun this candidate
unchanged as another acceptance attempt.

Independent review of the initial evidence retainer found checks missing for
tool-roster equality, extra source inputs, raw warning/exclusion findings and
bound complete-summary/coverage products. The replacement verifies these
conditions and limits directory/archive enumeration while collecting it.
Its first inventory check refused because the archive also contains a separate
transport project; the correction matches this project's declared `src` and
`tests` scope exactly, without changing proof scope. Both review findings and
that refusal are preserved. [Ten focused controls passed](CONTINUITY-FULL-RETAINER-CONTROLS.json), including an actual
extra Ada source file, forged success flags, warnings, exclusions and a missing
bound summary. Follow-up review also found an unbounded decompression call;
the final retainer caps decompressed bytes and retains positive and overflow
controls. These are evidence-tool tests, not additional SPARK proofs. The
successful qualification branch still awaits a completed real campaign.

The proposed larger full-campaign budget remains pending and unused. Exact
committed-source reproduction, independent acceptance, authenticated producers,
actual harness restoration and installed/release verification remain required.
