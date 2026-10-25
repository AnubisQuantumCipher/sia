# Conditional event-pack retirement policy

This experimental, inactive SPARK package is a prerequisite for the existing
migration obligations. It does not authorize filesystem effects, authenticate
observations, implement recovery, or establish whole-system assurance. It adds
no production caller and does not change marketplace or installed behavior.

## Contract and correspondence boundary

`SIA_Pack_Retirement` classifies one represented legacy slot as refused, proposed
for unlink, recorded as retired, or originally absent. All four outcomes are
policy classifications, never capabilities or source acknowledgments.

The authenticated plan producer must bind **every** field of `Plan` to its
identity: transaction epoch and identity; corpus, organ, prefix, revision,
capture, selection and fallback manifests; old and new target identities;
permission scope; organ length; selected and fallback counts; all three ordered
rosters; original presence and generation for every represented slot. Equality
of supplied digests does not establish this binding. The policy accepts fixed
representations, including valid all-zero record identities. It does not hash,
decode, validate hexadecimal routes, or verify signatures.

The target must be the exact union of prior and represented records, including
identity, content digest and byte length, in strict identity order. Padding must
be empty. Originally absent legacy records must already be covered by the prior
pack. The selected count equals represented plus fallback counts. The producer
must additionally establish complete selection/fallback membership, disjointness,
source truth and exact prior content. These are **ASSUMED**, not proved from counts.
The inactive [manifest partition validator](EVENT-PACK-MANIFEST-PARTITION.md)
now supplies separately proved per-step correspondence and completion contracts
for supplied ordered streams. Until a protected adapter binds those streams to
the actual authenticated plan and source, this policy's producer assumptions
remain open; the validator alone does not discharge them.
A fallback-only plan with an empty target is outside this retirement slice; this
does not invalidate the transport planner's legitimate no-pack outcome.

The size function specifies every prefix by recurrence from the codec header and
per-record framing. Logical sums cover the full declared input domain before the
frame ceiling is applied. Binary digest ordering corresponds to canonical lowercase
hexadecimal wire ordering only after an adapter establishes that representation.
An organ digest plus a supplied length does not validate an organ name or route.
The existing Python codec remains a separately tested implementation.

The protected observation producer must establish these facts before supplying
witnesses to the classifier:

- Intent is durable and bound to the complete plan identity.
- Target file synchronization, parent synchronization and exact readback refer
  to the actual protected path, bytes, generation and operation. A durable
  digest label alone is insufficient.
- The selection witness covers the exact admitted selection manifest.
- Execution identity is current and trusted, not chosen by the calling model.
- Original state is a current observation of the exact slot and original
  generation under exclusive protected operation ownership.
- A retirement receipt attests **completed deletion and durable reconciliation**
  for the exact transaction, plan, scope, slot, record and original generation.
  Its custody witness alone does not establish that those effects happened.

Given these premises, present exact originals can be proposed for unlink only
without contradictory retained retirement custody. An expected-present original
that is now absent needs the matching retirement receipt. Unexplained absence,
unobserved/conflicting state, stale scope or substituted evidence is refused.
An expected-absent original covered by the prior pack is classified separately
and never proposed for unlink. These outcomes do not establish publication
readiness or durable source acknowledgment.

## Power of Ten adaptation for this slice

These are project adaptations, not quotations of Holzmann's C rules. The existing
normative paper, full mapping and exception ledger remain controlling.

| Rule | Mechanism here | Evidence and remaining boundary |
|---|---|---|
| 1 | Pure predicates, sequential classifier, no recursion or dispatch | GNAT restrictions and scoped proof; protected actuator still unqualified |
| 2 | Loops/quantifiers range over 32-byte digests or at most 64 slots | Prefix recurrence and runtime-safety obligations; no wall-clock WCET claim |
| 3 | Fixed records/arrays; no allocators or implicit heap allocation | Compiler restrictions; stack size and host process memory not proved |
| 4 | Small single-purpose predicate/test routines | Source review; declaration/contract length is not executable complexity |
| 5 | Exact recurrence, canonical order, binding and decision contracts | GNATprove plus independent negative runtime oracle; premise authentication open |
| 6 | Pure package, no I/O or capability ownership | Compiler-enforced purity; no installed integration |
| 7 | Typed bounds, explicit refused outcome, complete cases | Runtime malformed-evidence controls; wire parsing remains separate |
| 8 | No preprocessing, generated policy or conditional variants | Explicit focused source roster and strict project; original full suite retained |
| 9 | No access types or dynamic dispatch | Restrictions and direct calls; trusted producer still required |
| 10 | Warnings as errors, full scoped flow/proof checks | Retain raw outputs and failed attempts; focused proof is not full SIA proof |

Python's dynamic allocation and Linux scheduling/durability are outside these
SPARK guarantees. No claim of universal Power-of-Ten compliance, avionics
certification, cryptographic correctness or full migration safety follows.

## Reproduction and acceptance

The focused project uses the existing strict compiler/prover switches and lists
all its source files explicitly. Tests run outside SPARK and are not themselves
proved. They exercise lifecycle outcomes, all context fields, each durable
witness field, substituted records/receipts, canonical ordering, empty padding,
the complete roster/input-count domain, and the exact frame ceiling. A coherent
receipt-check deletion mutant must fail the unchanged runtime oracle.

```sh
source /home/sicarii/opt/gnat/env.sh
gprbuild -p -P spark/pack_retirement.gpr -j1
spark/pack-retirement-bin/pack_retirement_tests
gnatprove -P spark/pack_retirement.gpr -U --mode=all --assumptions \
  --no-inlining --memlimit=512 --timeout=10 -j1
```

The retained campaign runner wraps these commands in the existing exclusive
heavy-job lock, build/runtime 60-second and proof 120-second limits, five-second
termination grace, 2-GiB address-space and 512-MiB file limits, with core dumps
disabled. These are operational bounds, not a mathematical resource proof.

Required next acceptance evidence: authenticated canonical decoder and manifest
producer; protected runtime enforcement; exact modeled-to-actual crash/refinement
coverage; complete original runtime/proof workload; current-policy validation and
useful expensive reuse; installed lifecycle and off-host recovery; independent
review and controlled publication. The finite migration model's assumptions and
all original acceptance gates remain open where previously open. This focused
project does not replace or reduce their workloads.

## Retained focused result (October 24, 2026)

Candidate c9 passed strict build, all 188 runtime controls and the complete focused
GNATprove run: 89 checks discharged (42 flow, 47 prover), zero justified or
unproved checks. The report covers all 16 package entities and all 7 entities of
its `SIA_Policy` dependency; the two test units explicitly remain outside SPARK.
The receipt-removal mutant built successfully and failed the unchanged test on
`unexplained absence`. The original codec independently confirmed the header,
maximum-organ and exact-frame boundary fixtures. Earlier build/proof failures
remain in the evidence archive. This is conditional source-level proof plus
runtime testing, not qualification of the protected or installed system.
