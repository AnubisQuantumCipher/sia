# Conservative continuity reference policy

Status: experimental pure policy; incremental reported checks discharged,
fresh committed-source reproduction still open. No runtime adapter,
capture, source authentication, durable checkpoint, approval or action execution
is implemented by this package. It is a dependency of the agent continuity
mission in `docs/AGENT-CONTINUITY.md`, not an installed continuity guarantee.

## Inputs, decision and safety intent

`SIA_Continuity` compares a bounded proposed checkpoint with independently
supplied current evidence descriptors. It returns a classification only. Its
most permissive result, `References_Proposed`, never grants an action, declares
an operation complete, validates a human approval, or permits a retry.

The decision order is deliberate:

| Result | Condition |
| --- | --- |
| `Invalid_Checkpoint` | The checkpoint violates structural validity, ordering, supersession, origin, coverage or operation shape |
| `Identity_Mismatch` | Task, session or repository identity differs |
| `Stale_Checkpoint` | Checkpoint identity/generation, capture head, observed-through sequence or retention generation differs |
| `Need_Evidence` | Required durable witnesses or exact source descriptors are absent/mismatched/retracted, or coverage is incomplete |
| `Reconcile_Repository` | Source revision or uncommitted-state descriptor differs |
| `Reconcile_Operations` | A dispatched or uncertain operation remains |
| `References_Proposed` | None of the preceding conditions holds |

A refusal can mask later problems; resolving the first one requires a fresh
comparison, not an inference that every other condition passed. There is no
state mutation, read/write permission or retry instruction in the result type.

## Closed bounds and invariants

The representation has 64 claim slots and 16 operation slots, fixed digest
arrays, bounded generation types, closed enumerations and canonical empty
padding. Quantifiers range only over these declared finite types. The existing
project restrictions exclude allocation, recursion, indirect subprogram
access and dispatch. Proof of language-level termination and absence of
run-time errors does not establish wall-clock deadlines or physical stack/RAM
capacity; target resource measurements remain required.

Active claims have unique nonzero identities and slots identify the scope of
supersession. Source sequence is strictly increasing and cannot exceed the
checkpoint's observed-through sequence. A replacement must name the latest
earlier claim in the same slot with the same kind, role and origin. No branching,
forward/self replacement or implicit override is admitted. This initial schema
does not support several claims from a single sequence, cross-kind supersession
or a handoff between different session identities. These cases require an
explicit later contract.

Task, session, repository, checkpoint, claim, slot and operation/action
identities reserve zero as invalid. Capture, revision, dirty-state and original
content descriptors use the whole digest domain; zero bytes are a content
value and never mean "missing". Repository-less tasks are not represented by
this version. Retention generation zero is an initial generation, not absence
of a retention policy; producer qualification must establish its current value.
Missing evidence is carried by explicit availability/witness state.

Assistant-origin claims must remain model records. A permission reference must
refer to a user source record; even this classification authenticates neither
the source nor its meaning. A model-origin pending-approval reference may be
retained because it does not assert that approval was granted.

Coverage preserves not-observed, unavailable, observed-empty, partial and
complete states. Partial/complete categories must have at least one row.
Only observed-empty/complete coverage can reach the proposal result, and goal,
acceptance, source and next-action categories must be complete. These are
supplied coverage assertions, not semantic proof that no fact was missed.

Operations retain stable identities, action references and source/result
references. Planned operations cannot have a result; observed-complete and
acknowledged operations require a result reference. Presence is represented
separately so the entire content-digest domain, including all-zero bytes,
remains usable. Identity slots reserve zero, but content digests do not.
Duplicate operation identities or nonempty unused slots refuse.
Every dispatched or uncertain operation requires reconciliation regardless of
whether a provisional result reference exists.

## Assumption and integration ledger

Any proof of the pure policy covers only a decision about its supplied typed
inputs. The following premises remain external and must be enforced before
runtime reliance:

1. Task/session/repository descriptors come from a trusted enrollment context,
   and current heads cannot be rolled back or forged by a model or peer process.
2. The checkpoint identity binds its complete canonical representation, including
   coverage and predecessor; its previous-generation chain is authenticated.
   Checking that a noninitial checkpoint has a previous identity does not verify
   the predecessor bytes or the historical transition.
3. Current claim/operation descriptors are resolved from the exact retained
   original records. Source role, origin, sequence, action scope, retention and
   deletion state are checked by the producer, not asserted by the proposer.
4. Manifest/original durable witnesses reflect actual protected publication and
   storage outcomes, bound to this checkpoint generation and identity. Supplying
   matching Boolean flags cannot establish durability or authentication.
5. Operation transitions are reconciled across checkpoints. An uncertain
   operation cannot be reset to planned or omitted by publishing a new proposal.
   This package compares one checkpoint; it does not implement that journal.
6. Source/dirty descriptors bind native Git identities without padding or
   relabeling them as SHA-256. Coverage and claim meanings require separate
   semantic retrieval/continuation evaluation.
7. Deletion and revocation update the protected current retention generation and
   dependent observations, and remain effective across backups and summaries.
8. Consumers treat all restored content as untrusted source material. Current
   action authorization is checked separately through the actual authority path.

The Python proposal codec is not yet wired to this policy. In particular its
version-one operation schema has no acknowledged state or retention generation.
The adapter must add an explicit versioned transport with byte bounds, validate
decoding, and differential-test the representation before runtime acceptance.
No Python success value is a substitute for a SPARK decision.

## Required verification

Strict build, all prior harnesses plus `continuity_tests`, complete GNATprove
coverage with no unresolved/justified obligations, exact source/toolchain
receipts and independent review are required for this increment. Positive
controls include full claim/operation capacity, empty optional categories,
maximum generation values and zero-valued content digests. Negative controls
include each identity byte, stale heads, missing/retracted observations, false
durability, origin escalation, incomplete coverage, supersession forks, invalid
padding and operation uncertainty.

These checks do not establish a durable capture ACK, correct semantic retrieval,
hostile same-user isolation, harness execution or correct continuation after
compaction. Those remain acceptance gates of the surrounding mission.

## Current scoped evidence

The development-v9 snapshot passed the strict build and all eight runtime
harnesses. Its fresh all-unit proof exceeded the unchanged 600-second command
limit and exited 124. The exact copied source/session then completed in
`continuity-policy-incremental-v1`, using the same full proof command and
resource limits. GNATprove reports 782 discharged checks across sixteen units,
with zero justified/unproved checks; the strict coverage validator exited zero.
Source, parent-session and before/after tool identities are retained.

This is an incremental proof result, not a passing fresh reproduction.
Independent GPT-6.1 review found no source or evidence-binding blocker within
that scope. See [the evidence manifest](../docs/CONTINUITY-POLICY-EVIDENCE.json)
and [the continuity mission](../docs/AGENT-CONTINUITY.md) for retained failures
and open gates. Runtime authority and end-to-end compaction remain unimplemented.

The later fresh committed reproduction at `2794db2` again passed build and all
eight harnesses but timed out at the unchanged 600-second proof limit.
Inspection of raw output also exposed disabled miscellaneous warnings outside
the old flow-summary gate. The [warning-gate repair](../docs/PROOF-WARNING-GATE.md)
must qualify before any all-channel zero-warning acceptance.

The strengthened development-v11 campaign then passed strict build, all eight
runtime harnesses, full proof and raw/summary validation. It reported 788
discharged checks across the complete 16-unit scope, using all tagged warnings
and the same prover set reordered to Z3/CVC5/Alt-Ergo under unchanged caps.
The linked warning-gate evidence binds that fresh development snapshot.
Committed-source reproduction subsequently passed at `1f71a97`, with all 788
reported checks and the complete raw/summary gate accepted. Independent
evidence review found no blocker within that scope. Runtime restoration and
the external premises above remain unqualified.
