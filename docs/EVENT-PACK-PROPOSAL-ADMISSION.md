# Conditional event-pack proposal admission

Experimental and inactive. `SIA_Pack_Proposal` composes the existing retirement
plan and ordered manifest partition contracts. It grants no permission and has
no filesystem effects. No installed or marketplace path calls this package.

## Gap and contract

The partition package sees represented records and the selection/fallback
streams, but has no prior or complete target roster. It can therefore accept a
structurally valid partition whose fallback identity is already in the plan's
target. The new wrapper fixes that composition gap: every fallback identity must
be absent from the entire target, including prior records. Content differences
do not excuse identity overlap.

`Start` freezes a valid typed plan and requires both manifest counts to equal
that plan's selected/fallback counts. `Take` preserves the existing complete
identity/content/length correspondence and rejects target overlap. Failed steps
preserve the entire accepted stream prefix; rejection remains sticky until an
explicit new `Start`. Only a successful `Finish`, after both complete streams
and every represented slot with no trailing bytes, returns the conditional
admitted plan. Failed completion clears its returned plan. The `Proposal`
accessor and intermediate accepted steps are observations, not admission or
permission.

The existing partition `Take` contract is strengthened to state that a successful
result is `Represented_Record` exactly when the old-state classification says
so. Its implementation and admitted domain are unchanged. This missing bridge
was exposed by an unresolved wrapper postcondition; it is now an explicit
obligation of the callee rather than an inference from its implementation.

Safe non-greedy partitions remain admitted. Exact coverage, complete-record
correspondence, target union, target/fallback disjointness and existing limits
are safety requirements here; greedy packing optimality is not. The actual
producer's selection policy remains separately accountable.

## Evidence boundary

The v2 c3 complete focused proof passed under the original 120-second limit:
476 checks discharged, with zero justified or unproved checks. The raw/report
auditor confirms all declared production entities and the explicitly excluded
test units. Original proposal, retirement, wire and manifest suites pass.
Independent GPT-6.1 clean-source reproduction passed the strict build, all four
runtime suites and complete proof under the same limits. This establishes only
the declared focused component, not system or release acceptance.

The package has fixed private state, direct calls, checked counts and lengths,
no heap allocation, no I/O and no mutable global state. This does not prove
whole-process stack, worst-case execution time, Python allocation or Linux
scheduling bounds. The original Power-of-Ten assessment and full completion
contract remain controlling.

Five entity-scoped `Hide_Info` annotations prevent expansion of the existing
retirement validity expression in selected wrapper proof contexts. This is
intentional modular abstraction, not a new truth assumption or an excluded
body. Every predicate call and pre/postcondition remains; the original validity
definition must still be discharged in the full focused source scope. See the
AdaCore [context-management documentation](https://docs.adacore.com/spark2014-docs/html/ug/en/appendix/additional_annotate_pragmas.html#pruning-the-proof-context-on-a-case-by-case-basis).

Two further caller-scoped annotations hide only `Record_Start` expansion in
`Roster_Decoded` and `Roster_Value`. The same deterministic function is used in
both quantified validation and decoding; these contexts need its congruence and
return subtype. Its original definition remains fully analyzed. Generated
obligations exposed redundant affine expansion at this boundary. This candidate
passed complete proof; prior candidates remain failed. This is not a worst-case
proof-performance guarantee.

Total Boolean checks use strict conjunction where every operand is defined;
leading guards remain wherever decoding requires a precondition. The five fixed
high bytes in `Small_Valid` are explicit equalities rather than a nested
quantifier. No byte, range, record or correspondence check is removed.

The actual wire decoder is exercised before this gate in runtime traces. This
is not a mathematical proof of a full trace history, canonical re-encoding,
hash authentication, source completeness or byte custody. Adapters must bind
actual framing, lengths, EOF, manifest hashes, plan identity, task/repository/
revision, current policy, resource reservations and permission scope. Protected
publication, retention and recovery effects remain separate obligations.

## Failures retained

C1 failed strict compilation on visibility of private-state equality. C2 repaired
that visibility and passed runtime checks. C3 added a non-greedy positive case,
a counterexample contrasting partition-only and composed admission, and trailing
stream rejection. C3 and C4 full proofs timed out under the original limit; C4
only reordered pure conjuncts and narrowed the target helper's parameter. C5
added modular context annotations; its full proof timed out and retained an
unresolved represented-position postcondition. C6 strengthens the missing
partition discriminator contract. C7 and C8 simplify only total or explicitly guarded conjunctions; both full
proofs also time out. Every earlier source and result remains retained; later evidence cannot relabel those failures.

The v2 c1 candidate simplified total Boolean expressions; its full proof timed
out. C2 expanded the fixed high-byte predicate; its full proof also timed out.
C3 added only the two caller-scoped offset abstractions and completed the full
proof. No per-prover or campaign time, memory, scope or warning cap changed.
A timed-out prover attempt followed by another prover's successful result is a
discharged goal; it is not an unresolved proof obligation. The earlier incomplete
campaigns nevertheless remain failures.

The coherent fault candidate changes both fallback-exclusion predicate and
postcondition to inspect only represented records. The unchanged independent
test rejects the prior-target identity; merely making code and specification
agree does not pass this oracle. A second fault removes one high-byte check; the unchanged exact-roundtrip oracle
rejects the lost information. These finite controls do not establish exhaustive
semantic coverage.

## Remaining acceptance

Full native-boundary qualification, R05 useful expensive reuse AND fresh current
policy validation, protected capture/publication, real harness continuity,
held-out retrieval, off-host recovery, installed qualification and release/
marketplace readback remain open. This component cannot establish universal
compaction continuity, whole-system formal verification or certification.

## Reproduction

The evidence JSON binds the exact 26-file roster, command lines, toolchain,
full report, raw unit scope and two evidence archives. `prior-failures` preserves
the preceding unsuccessful campaign; `qualified-c3` contains this campaign and
the independent clean-source run. Archive hashes establish package integrity,
not semantic correctness or release authority.

For a fresh Linux reproduction using the recorded GNAT toolchain, create an
empty output directory, copy the archive's `run.py` there and reconstruct
`stage-c3/` from its final source roster. Run `python3 run.py c3 PHASE` sequentially
for `build`, `runtime`, `retirement`, `wire`, `manifest`, and `proof`. Inspect every
child `.result.json`: the orchestration driver's exit alone does not establish
success. Require zero child exits, identical before/after source hashes, the
complete original unit/declaration scope, and no unproved/justified checks or
excluded production analysis. Do not use `prepare`, which refers to the original
checkout. Preserve existing phase files; the runner refuses to overwrite them.

The retained root auditor references the pinned predecessor checkout and is a
focused report checker, not a general Ada parser. The independent auditor avoids
that imported-checker dependency. Both retain compiler/toolchain and ordinary
modular-proof assumptions. Tests remain outside SPARK; no whole-process resource
bound follows from the fixed-size critical state.
