# Bound selected intake traversal and terminal pair checks

Status: selected traversal repair TESTED. R05 remains FAILED; whole-system
assurance, release and installed qualification remain INCOMPLETE.
Base source: `25438fa466760d0a9a8a4e2d7f4796e5d75a67df`.

## Counterexamples and repair

Ordinary list iteration in replay could continue processing records appended by
a decoder, association function, page-state provider or marker matcher. Shrink
could produce a partial result or reach an unrelated later refusal. The new
direct fold/member/project controls retain these outcomes on the original
source: eleven methods, seventeen failing controls. Growth sentinels stop the
tests deterministically after the initial count is exceeded; no timeout is used
as evidence that a particular loop is bounded.

Intake now uses a small iterator at the selected replay boundaries. It captures
the initial cardinality, performs at most that many yields, keeps live element
reads and aliases, and checks both exhaustion and final length. Shape and byte
admission remain the caller's responsibility. No replacement input snapshot,
owner callback result, publication decision or successful admission is cached.

Covered traversal includes member input records, target pages, admissions and
marker lines; fold events, event batches, members, admissions and source runs;
and whole-history entry replay. Each guard reports a typed local refusal.
Caller-body exceptions remain outside iterator error translation.

A second counterexample corrects a limitation in the preceding pairing
repairs. If a callback deletes an already-yielded final row, iterator exhaustion
alone does not distinguish successful completion from truncation. Original
intake, page and source pair helpers produce eighteen unexpected StopIteration
errors in the new terminal-deletion controls, instead of the required typed
refusal. All three helpers now compare final lengths with the initial count.
Prior tests established other shrink/growth cases, not this terminal case.
Their original failures, passes and source remain retained.

## Exact-source verification

- The composed candidate passes 210 tests in 18.634 seconds. This includes the
  new adversarial controls and existing source/page pairing, event-plan/batch/
  closure, replay, association, refusal-order, alias and checkpoint/delta tests.
- All three changed modules, both new tests and their runners pass the pinned
  167-rule static profile and syntax checks. The workload runner and evidence
  builder also pass that profile. This is scoped analysis, not repository-wide
  Power-of-Ten compliance.
- Tests retain the original 60-second deadline, five-second kill grace, 2-GiB
  address-space and 512-MiB file limits, exclusive heavy-job lock, private home,
  network/PID namespaces and read-only source. Before/after source maps match.
- Actual GPT-6.1 source/raw review found no concrete blocker to this repair.
  That review did not independently execute the tests.

The unchanged larger synthetic workload also runs with all three overlays.
Ordinary capture and cold/warm validation complete. The process exits 1 with
`FAILED_STALE_ADMISSION`: changed-current-capacity warm acceptance still differs
from cold `source-catalog-capacity` refusal. Its full process observation is
15,732,447,036 ns; cold public validation is 2,513,711,782 ns. These are single
observations within the original envelope, not speed improvements, WCET or
latency guarantees. The workload remains synthetic and does not replace the
outstanding historical compact-workload qualification.

[The evidence bundle](INTAKE-BOUNDED-TRAVERSAL-20261024.json) retains exact
original/candidate files, tests, runners, input maps, raw failures and passes,
static results, review, synthetic source records and the complete retained
image. Its embedded builder reproduces the bundle and reconstructs the split
image byte for byte within the existing member and aggregate limits. Package
integrity does not authorize acceptance or release.

## Limits and remaining acceptance

An initial-count bound is not a proof that callbacks or individual interpreter
operations terminate. Same-length replacement, ABA mutations, changes before a
particular traversal starts, incomplete generator consumption, other unmodified
paths and allocations outside the iterator remain outside this repair. Private
accumulators can be partial on refusal and must not be published. The iterator
has no authority to publish them. Python is not claimed to provide fixed memory
or complete Power-of-Ten compliance.

The original outer admission caches and reuse oracle are unchanged. The prior
string cache remains NOT ADOPTED. R05 still requires useful closed derivation
reuse, fresh current admission, qualified retention/deletion and original
whole-workload/rejection/resource evidence before the conditional test
instrumentation decision can be exercised. All original SPARK, supervision,
harness lifecycle, recovery, installed-runtime and marketplace gates remain.
