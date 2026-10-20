# Pure consolidation observation planner

`SIA_Consolidation` proposes recording a complete supplied batch observation.
It does not authorize cursor advancement, source deletion, durable ACK,
original-reference retirement or publication. The caller must authenticate
observations and enforce the existing protected-service gates before any
consequential runtime integration.

The exact transaction, batch, before/after cursors, day/source/original-reference
roster and padding must match. A pending batch accepts only complete per-day
`Retained_Intact` or `Compacted_Exact` observations. An identical recorded replay
preserves the state; changed replay, missing/partial/unavailable observations
and mismatches refuse without changing any state. Retention is not compaction
success and never licenses deleting original data.

The fixed prototype capacity is 1024 distinct day identities, matching the
discovery page-entry ceiling. This is not a production memory/stack/WCET budget
or a claim that a page contains a complete day. Batch/day/original-reference
identities reserve all-zero as absent. Transaction and source content digests
retain all byte values, including zero; nonzero epoch identifies transaction
presence. The adapter must preserve this distinction.

Development snapshots v1/v2 retained strict-build failures (preelaboration
initialization and an unused import). They were repaired without suppressions.
Snapshot v3 passed strict build, runtime controls and all-unit proof. Independent
GPT-6.1 review required positive one-day/full-capacity controls and explicit
zero-transaction-digest semantics; v4 adds those cases and passes build, runtime
and the complete proof-summary gate. These are development observations; exact
committed-source reproduction and evidence review remain separate acceptance.

All prior policy/transaction/wire/admission/lifetime/retraction tests remain
required. The new harness checks proposal/replay, all dispositions, identity
mutations, invalid padding, duplicate days, zero reserved identities, bounded
counts, full-capacity retention and final-slot partial refusal. Proof includes
helper caller preconditions and the capacity-construction loop invariants.

Full consumer progression remains OPEN: split days across immutable pages,
more than one execution-sized claim set per batch, durable complete-outcome
recording, current protection decisions, late arrivals and bounded original-pin
retirement must be resolved before replacing the installed consolidation path.

## Committed-source reproduction

Source `1e3e6de7281142ac08005274ffa452dcbad341b7` passed `spark/verify-policy.sh` in a fresh
archived tree. The retained summary reports 482 discharged checks (156 flow,
326 prover), fourteen fully analyzed units, no justified or unproved checks,
and all seven runtime harnesses passing. Strict build, proof and coverage
commands exited zero. Spark-subtree archive SHA-256:
`451afedea2d6478558f8d9223098c3fc43e6fba3a66f8004bdd753ac201313cb`.

Evidence: `consolidation-policy-reproduction-v1` and independent GPT-6.1
`consolidation-policy-review-v3.txt` in the external assurance evidence directory.
The reviewer compared archive/source and recorded tool hashes and inspected
the completed reports; it did not rerun the proof. This qualifies the pure
contracts and harnesses only. All runtime/enforcement/resource non-claims above
remain controlling.
