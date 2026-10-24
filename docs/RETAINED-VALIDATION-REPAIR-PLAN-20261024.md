# Retained validation: open repair contract

Status: **FAILED regression reproduced; production repair UNPROVEN**.
This extends R05 and the existing assurance mission. It does not replace any
original acceptance requirement, deadline, fixture, proof or resource limit.
The source and raw evidence are bound in
[the gap manifest](RETAINED-VALIDATION-CACHE-GAP-20261024.json).

## Observed gap

Both `siasourcebatch.validate_batch` and
`siasourcecheckpoint.validate_capture` cache successful admission. Their keys
include the supplied pin, native image digest, state byte limit and version.
Fresh validation also depends on current source/event limits, nested policy
tables and callbacks. The same callback can change behavior through closure or
global state. Reusing its identity therefore does not establish equivalence.

The corrected comparison requires ordinary acceptance, changes one dependency,
then compares warm admission with a separately cleared cold refusal. The
corrected roster reports 14 methods with 12 stale-admission failures. Its seven
imported original capture methods and original memo test remain unchanged.
The initial empty compact decoder fixture was ineffective; its failure is
retained as a test error, separately from the corrected nonempty control.

## Selected design direction

Cache a reusable computation with closed inputs, never permission to skip
current admission. The following boundaries must be established in code before
the cache can be considered repaired:

| Boundary | Required behavior | Evidence required |
| --- | --- | --- |
| Input admission | Validate schema, canonical byte limits, pin and current policy on every call. Inputs are detached before reusable computation. | Original malformed/pin/capacity controls; mutation during admission; refusal has no reusable entry. |
| Owner-dependent operations | Execute current custom-selection, event decoding, version construction, marker and refusal validation with checked outputs. Arbitrary callback behavior cannot be certified by identity. | Callback replacement, unchanged callback with changed global/closure state, nested alias mutation, exception and malformed-output cases. |
| Pure derivation | Accept only an explicit bounded data record. No owner dictionary, callbacks, mutable module policy, filesystem, clock or ambient identity reads. | Source-level dependency review, deterministic differential tests and bounded allocation/execution evidence. |
| Reuse identity | Bind exact admitted data, complete canonical derivation context and an explicit implementation/schema revision. Digest collision resistance remains an assumption unless bytes are also compared. | Change every declared context field and implementation revision; reject unknown context fields; compare reuse against cold derivation. |
| Reuse storage | Retain existing bounded eviction, detached results and failure atomicity. Do not retain caller-owned mutable values. | Alias/output mutation, eviction, refused candidates, reentrancy and overlapping validation controls. |
| Final acceptance | Check current owner-dependent conditions and input stability before returning. A cache hit is never publication, source ancestry or acknowledgment authority. | Policy/input change during validation, ABA changes, transitive caches, existing predecessor and authority controls. |

This is a proposed implementation boundary, not a claim that existing Python
callbacks are pure. A before/after digest alone cannot detect ABA mutation or
arbitrary changes during a callback. The implementation must either remove
mutable policy from the reusable path through an owned immutable context and
controlled update protocol, or leave the affected computation uncached. Trusted
interpreter/runtime assumptions must remain explicit. Python-level freezing is
not isolation from hostile code running in that interpreter.

## Staged implementation

1. Preserve the failing regression and original performance/reuse oracle. Keep
   this branch unqualified for merge or release while the failures remain.
2. Resolve the dynamic frontiers in `siaeventintake.prepare`, `_fold_entry`,
   event-plan validation and checkpoint admission/projection. The retained AST
   inventory is a navigation aid, not a completeness certificate. Classify
   each dependency as immutable data, current admission or pure computation.
3. Extract the smallest reusable calculation from those paths, using the same
   contracts for legacy and compact captures. Keep error classifications and
   original tests. Moving a full validation under another function name merely
   to satisfy a call-count assertion is not an implementation of this design.
4. Measure the candidate under the original test envelope, then qualify the
   original workload and capacity limits. The small-fixture profile identifies
   repeated sizing and projection work; it is not evidence about maximum load.
   Admission sizing must itself avoid unchecked temporary allocations.
5. Obtain independent source/evidence review, exact-source tests and the
   existing system acceptance evidence before integration, installation or
   release. Retain every failed experiment and any justified deviation.

The private experiment removing both admission memos timed out at the original
60-second roster limit. Its partial output does not satisfy the original reuse
oracle, which it did not reach. The corrected decoder-only diagnostic pass
does not rehabilitate that whole-roster result. No cap increase, test skip or
weaker fallback is authorized by this plan.

## Power of Ten and assurance status

These are SIA adaptations, not quotations from Holzmann. P01/P02 require
explicit control flow and execution bounds through the complete dependency
path. P03 requires bounded admitted data, scratch storage and cache occupancy;
Python cannot establish fixed-allocation runtime behavior merely by counting
entries. P04/P06 require short routines and narrowly owned immutable context.
P05/P07 require non-vacuous warm/cold controls, checked callback results and
failure propagation. P08/P09 reject dynamic dependency introspection or code
object fingerprints as substitutes for a closed, reviewable interface.
P10 retains strict static checks, raw failures and exact-source CI.

No SPARK proof is claimed for these Python paths. Consequential publication
and recovery authorization still belongs to the existing Ada/SPARK authority
mission, with its own outstanding proof, binder, Linux enforcement and end-to-end
obligations. This checkpoint establishes a reproducible defect and repair
contract, not whole-system assurance, installed qualification, lossless agent
continuity, cognitive improvement or avionics certification.

## First implementation checkpoint: shared association derivation

`_derive_association` in `siaeventintake.py` now separates the data-only
first-observation calculation from callbacks and accumulator writes. Legacy
replay and checkpoint replay share its caller. The helper accepts private,
already-admitted scalar records; it is not a new arbitrary-object admission
API. Identity hashing remains conditional on a first source/event occurrence.
Repeats retain the original observation identity, version and time while
carrying current admission. Semantic conflicts return the original refusal
reason without an update. No input record is mutated.

The [extraction manifest](ASSOCIATION-DERIVATION-EXTRACTION-20261024.json)
retains original-roster and new contract evidence plus independent source
review. Two existing product static diagnostics remain. This extraction does
not close R05, establish a complete immutable validation context, or demonstrate
a speed improvement. Page admission, ordered version processing and current
owner policy still require separation. Both outer admission memos remain
unqualified, and the original reuse/performance and system gates remain open.

## Closed-reducer experiment: rejected production insertion

[The replay transition experiment](REPLAY-TRANSITION-EXPERIMENT-20261024.md)
retains a passing immutable-data reducer and two concrete integration
counterexamples. Equal-value replacement loses the first callback mapping;
rereading an unused candidate after the original comparison adds a refusal.
The private adapter is rejected. The new warm/cold projector regression remains
RED for both capture formats. The original reuse oracle is unchanged.

Before another extraction, establish meaningful reusable cost after preserving
captured reads, comparison outcomes, live aliases and refusal order. Include
snapshot, exact-key and storage costs. The small profile does not justify a
semantic-reducer cache; inclusive fold time includes current owner admission.
Repeated sizing is a separate measured frontier, including the remaining
recursive event-plan traversal. Addressing that frontier must preserve original
byte/depth/type/cycle contracts and does not close R05 by itself.
