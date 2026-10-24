# Source roster pairing: scoped refusal repair

Status: **TESTED scoped repair; whole-system assurance remains incomplete**.

Source capture checks a snapshot of event records before pairing the live event
list with those records. A callback can change the live list during the snapshot
check. The prior ordinary `zip` could then silently omit unmatched entries.
The synthetic regression demonstrates both an append reaching the forbidden
planner boundary and a clear returning without the required refusal.

The new private `_paired_rows` helper checks initial cardinality and limits
traversal to that initial length. It converts premature exhaustion, unequal
exhaustion and additional pairs into the caller's existing `SourceBatchRefusal`
reason. Only iterator advancement is inside the conversion handler. A callback
or loop-body error retains its original identity and meaning.

The helper is used for catalog rows, events/records, cursor steps and refusal
intents. Their existing input/type/capacity checks remain. Fixed generation and
immutable identity tuples use explicit strict pairing; identity comparisons keep
length checks, including an explicit exported-identity length check. That added
check is defensive, not a separately demonstrated reachable defect.

This helper does not undo partial private work, detect same-length replacement
or ABA changes, authenticate callbacks, or establish concurrent-process isolation.
If a caller stops iterating early, it has not established complete roster equality.
The four current callers either exhaust the helper or propagate failure; their
surrounding content, identity and final consistency checks remain necessary.

## Evidence

The [source-bound evidence manifest](SOURCE-PAIRED-ROSTERS-20261024.json) retains
commands, hashes, raw terminal output, failure classifications and review scope.
Original capture, epoch, JSON sizing and iterative sizing fixtures are unchanged.
The existing 44-test composition and six new methods pass in the same original
resource envelope. New controls cover both initial mismatch directions, mutation
during traversal, body-error identity, ordering/empty input, the actual event
planning boundary, and the explicit same-length mutation limitation.

The corrected baseline control fails its two intended assertions. The earlier
baseline's missing runtime stub was a harness error and is retained separately.
Also retained: the initial candidate's generic-ValueError review finding, test
closure-binding static findings, and a read-only overlay mount failure before
Python started. These attempts are not counted as successful validation.

Original strict 167-rule static analysis and compile-only syntax checks report no
diagnostics for the final changed product and new test. The historical recursive
fixture remains unchanged, including its old diagnostics. This is not a clean
whole-repository static-analysis claim. Actual GPT-6.1 reviewed source and raw
evidence; it did not independently execute the tests.

## Power of Ten adaptation and limits

These are SIA adaptations, not quotations from Holzmann. Explicit control flow,
an initial-length traversal bound, a short private helper, checked iterator
results, narrowly scoped exception conversion and strict static checks support
P01/P02/P04/P06/P07/P10. Existing data admission and surrounding consistency checks
are not replaced. The generator adds bounded control state relative to admitted
input, but Python still allocates dynamically; fixed-memory P03 compliance and
native worst-case timing are not proved. Dynamic callbacks remain outside a
proved P09 boundary. The tests are evidence of selected behavior, not formal proof.

R05 retained-admission caching, SDK qualification, full strict C analysis, complete
SPARK proofs, protected Linux enforcement, continuity lifecycle demonstrations,
installed upgrade/recovery and marketplace publication remain open. No source
receipt here grants publication authority or establishes a release guarantee.
