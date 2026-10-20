# Conservative checkpoint transitions

Status: implementation under verification; no acceptance or runtime claim.
The current fresh proof receipt for `1f71a97` predates this package and must
not be used as evidence for it.
The [incomplete development manifest](../docs/CONTINUITY-TRANSITION-STATUS.json)
binds the current proof-source bytes and retained command outcomes. Full proof
reached its 600-second deadline; full raw coverage and committed reproduction
remain unrun.

`SIA_Continuity_Transitions` implements the bounded C13 comparison described in
the [continuity mission](../docs/AGENT-CONTINUITY.md). It returns a typed refusal
or `Transition_Proposed`. That result grants no publication, execution, retry,
acknowledgment, retirement or permission. `SIA_Continuity` retains its public
policy signatures and intended acceptance conditions. Its predicate extraction
and independent equivalence bridge are described below. Original test helpers
and fixtures are retained, with an additional claim-preservation invariant in
the operation-capacity loop. Every mutation, reset, original invariant and exact
expected result remains.

## Conserved state

Both checkpoints must satisfy existing structural validity. Task, session and
repository must match; the successor names the exact predecessor identity and
next epoch without overflow. Capture-through and retention generations cannot
decrease. Revision and dirty-state changes still require the existing restore
policy's reconciliation. These comparisons do not validate a capture hash chain.

Operations use the existing fixed capacity and canonical append order. Count
cannot decrease, and every old slot preserves operation, action and original
source identity. New slots must be planned with no result. Missing, reordered,
reset or implicitly retried operations refuse. There is no retirement protocol,
even for acknowledged operations. Capacity exhaustion cannot evict anything.

| Before | After | Required evidence |
| --- | --- | --- |
| identical | identical | canonical empty observation |
| newly appended | planned, no result | canonical empty observation; original still resolved separately |
| planned | dispatched, no result | dispatch-attempt event |
| dispatched | uncertain | interruption event; preserve result presence and reference |
| dispatched | observed complete | observed-outcome event and independent final result |
| uncertain | observed complete | reconciled-outcome event and independent final result |
| observed complete | acknowledged | acknowledgment event; preserve final result |
| any other change | any | refusal |

Provisional results already allowed by the single-checkpoint contract remain
valid. Unchanged copies and result-preserving uncertainty are supported.
Acquiring/substituting a provisional result without completion is unsupported.
Completion may replace a provisional result only through an event binding the
complete before/after values and the independent final result.
Direct planned-to-uncertain/complete changes, multiple phase transitions between
checkpoints and recovery of missing intermediate checkpoints are unsupported.

## Acyclic artifact identities

Three distinct layers prevent a checkpoint and its result from hashing each
other:

1. Independent result artifact **R** contains observed output/reconciliation
   data. It cannot depend on the same completion event E, the successor
   checkpoint containing R's identity, or its own digest.
2. Retained event **E** describes the complete before/after operation, closed
   event kind and, for completion, R's identity. Its own identity is distinct
   in meaning from the operation's result reference. E contains neither
   checkpoint identity.
3. Detached observation **D** joins the two checkpoint identities/epochs to E's
   identity and exact resolved event fields. D is constructed after both
   checkpoint identities exist; its digest is embedded in neither checkpoint,
   R nor E.

The SPARK core compares D's supplied fields. Qualified producers must establish
the canonical schemas, acyclic dependencies, retained bytes and authenticated
custody of R, E and both checkpoints. The core cannot infer these facts from
equal digests. It cannot establish the truth of external outcomes.

One observation slot corresponds to each operation slot. Changed slots require
retained state and exact identities, epochs, before/after values and event kind.
Completion additionally requires explicit result presence and a matching
result reference; other events require canonical absent outcome fields.
Unused, new and unchanged slots require canonical empty observations. Two
changed slots cannot reuse an event identity in this one-event-per-operation
schema. All-zero content digests remain supported; absence is explicit.

## Power of Ten and acceptance boundary

The pure package uses fixed arrays and digests, closed types, finite
quantifiers, small expression functions, explicit error results and a complete
classification postcondition. Existing strict compiler/prover flags and
restrictions remain. No allocation, recursion, dynamic dispatch, raw pointers,
imports or suppressions are introduced. Language-level resource bounds do not
establish physical RAM/stack capacity, wall-clock timing or WCET.

Required evidence is strict build, every original runtime harness plus the
transition harness, complete all-unit proof and raw diagnostics under the
existing resource caps, exact-source/tool receipts, and independent review.
Controls include every admitted edge and refused phase pair, provisional and
zero-result records, omission/reset/reordering, event-binding corruption,
duplicate/unused events, full capacity, maximum generations and repeated
uncertainty before evidenced completion.

This increment does not conserve claim history across checkpoints, authenticate
the current head, publish data, enforce retention deletion, qualify a harness,
or demonstrate correct model continuation. Those are separate mission gates.
Capacity retirement, durable intermediate publication and crash recovery also
remain open before sustained operation can be claimed.

## Predicate dependencies and equivalence

The original checkpoint validity predicates accepted an entire checkpoint even
when they read only its claims, operations or coverage. The extracted predicates
accept exactly those fields, with the same bounded types and no additional
preconditions. The original public signatures remain wrappers. This makes
unchanged-field dependencies explicit during proof; it does not change intended
policy or establish a proof-time improvement.

`continuity_tests.adb` retains independent copies of the six original predicate
expressions from `0f21fa357b128dcdc06cc9108059408219b4bf46`, renamed only.
`Check_Predicate_Equivalence` has no precondition and compares current predicates
with those frozen expressions for an arbitrary typed checkpoint. The original
index guards, empty padding, whole-domain uniqueness, ordering, watermark,
coverage and result rules remain part of this bridge. Its concrete runtime call
is one test; only discharged universal proof obligations establish equivalence
over the typed domain. Full-scope proof, original fixtures and all caller
obligations remain required.

## Retained development failures

`continuity-transition-development-v1` failed strict compilation because a pure
unit's constant aggregate used imported composite constants. The repaired
aggregate spells out the same empty values; no proof ran in that attempt.
Development-v2, development-v3 and development-v4 passed the strict build and all nine
runtime harnesses, then reached the unchanged 600-second full-proof limit
(exit 124). Their partial raw reports establish neither complete proof nor
coverage acceptance. Receipts, logs and source overlays remain in the pinned
evidence directory.

Experiments with modular test-helper contracts retained every original case.
Independent source review found no lost control or weakened exact-result
oracle. That review is not a substitute for the complete proof, raw-diagnostic
gate or committed reproduction. Generalizing `Check_Gaps` increased proof
search, so that helper and its main call were restored to the committed version.
Development-v5 also reached the command deadline and retained a medium
diagnostic: `Valid_Claims (Item)` was not established after the original
capacity harness's operation-array loop. The next source explicitly carries
`Valid_Claims (Item)` as a loop invariant. The loop changes no claim, count or
through-sequence field. Initialization and preservation are additional proof
obligations; the old operation-array invariant and every control remain.
Development-v6 discharged the previously reported assertion in its raw unit
report, but still reached the full-command deadline. All original helper
parameterization was then restored to the committed form, keeping only the
additional claim-preservation invariant. Focused diagnostics may guide repairs;
they cannot substitute for the required fresh full-scope reproduction.
Development-v7 added the predicate extraction and independent equivalence
bridge. Strict build and every runtime harness passed; both continuity raw
reports contained no unresolved diagnostics. The full command again exited
124 at the unchanged deadline before complete project coverage. The focused
equivalence/capacity diagnostic passed separately. Neither observation is fresh
full-project acceptance. Its exact source and failure receipt remain retained.

A later diagnostic experiment split the bridge into pointwise lemmas and added
an operation-array lemma. Its first strict build refused unchanged-input
postcondition warnings; classifying the new capacity lemma as Ghost resolved
that compiler issue with checked bodies and the existing assertion policy.
The subsequent build and all runtime harnesses passed, but the focused bridge
proof reached its 120-second diagnostic deadline. That decomposition was
reverted to the exact development-v7 harness. Both failed diagnostic snapshots
and independent reviews remain retained. No warning switch or proof obligation
was suppressed, and the full-project deadline remains unchanged unless the
operator explicitly approves the separately proposed resource change.

The restored source's focused transition-package diagnostic subsequently
completed with all 32 reported checks discharged and no unresolved raw
diagnostics. Its modular assumptions include the existing checkpoint-validity
dependency. This one-unit result is retained as
`continuity-transition-core-probe-v1`; it is not full-project acceptance.
