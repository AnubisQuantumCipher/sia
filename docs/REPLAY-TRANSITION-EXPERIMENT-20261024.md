# Replay transition experiment and retained admission failures

Status: **R05 FAILED; experimental adapter REJECTED**. This checkpoint adds
regression controls and retained evidence. It changes no production runtime,
cache policy, original assertion, resource ceiling or acceptance gate.
Product source is `ea23fbe9db362bcd361f7aacd98d461ca6cb95ac`; the added test
bytes and all executed source maps are in the companion JSON. The private
reducer and adapter are evidence members, not installed or imported code.

## Current cache counterexample

The same projector callback and owner first accept the real fixture. Its closure
then changes the output and recomputes internally consistent hashes. Warm
validation accepts without invoking the projector again; separately cleared
validation refuses. This occurs for both legacy and compact retained captures.

`tests/test_retained_projector_context.py` preserves this failing comparison.
It is intentionally RED until the actual runtime is repaired, with no skip or
expected-failure annotation. Existing policy/decoder/cache and derivation-reuse
controls remain unchanged. Source binding inside the projector does not protect
a path that bypasses that projector.

## Closed calculation and integration limits

The private reducer accepts immutable tuple/scalar data, explicit predecessor
state and prototype counters. It computes page/current-version and
first-observation/association state without owner callbacks, hashing, clock or
filesystem access. Its final 12 differential/negative tests pass in 1.075s,
including a real compact predecessor/delta and exact first-association state.
This is tested value-level behavior under producer premises: tuple layouts,
seed uniqueness, joins and candidate correctness are not an arbitrary-input
validation contract. Python allocation, integer magnitude, complete producer
storage and the production byte envelope remain unqualified.

Production retains the first callback-owned version mapping when equal versions
repeat. Replacing it hides a later mutation of that first mapping. The new
`test_replay_transition_order.py` checks this plus early before-image and
collision refusal ordering. Current source passes 3 tests in 0.299s; a controlled
replace-first variant fails the alias test. The reducer was corrected to retain
the first tuple, but immutable tuple equality alone cannot establish live alias
semantics.

A private adapter then inserted one pure version step after existing comparison,
while retaining original mapping aliases and callback placement. Its focused
original-and-ordering roster passes 84 tests in 9.989s. Review identified an
uncovered read frontier: it rereads the candidate after the owner-dependent
comparison and repeats collision checking. Production uses the captured pin and
comparison result, and discards an equal incoming candidate.

`test_replay_interleaved_frontier.py` supplies the exact counterexample. A wrapper
runs the original comparison and then changes only the unused equal candidate.
Current source returns the unchanged expected projection (1 test, 0.107s).
The adapter instead refuses (1 error, 0.102s). This is a compatibility failure,
not stronger assurance. **The adapter is rejected and has not been adopted.**
Its additional snapshot/allocation work and prototype limits are also not
qualified for the production domain.

## Retained results and qualification

| Scope | Result |
| --- | --- |
| Original 126-method scoped roster plus the new controls | **FAILED**, 131 methods in 31.426s, two stale-cache subtest failures; all earlier scoped methods pass |
| Three added test files, original 167-rule static profile and syntax | **TESTED**, exit 0, no diagnostics |
| Private adapter static profile | **NONPASS**, the same two B905 findings as original intake source; no waiver |
| Private final reducer | **TESTED** for the declared fixture domain; no SPARK proof |
| Actual GPT-6.1 review | Source/raw review only; no independent execution |
| Useful cache, original reuse/performance oracle, maximum workload | **UNPROVEN** |

The original 60-second deadline with five-second termination grace, resource
limits, isolated test home/network and source observations were retained.
Initial imported-test duplication, B023 diagnostics, the compact digest fixture
error, an initially wrong refusal expectation, rejected variants and a test
receipt-writing failure are retained. The receipt-writing failure occurred
after raw test output; its before/after maps were not retained, so that run is
not accepted as an exact-source receipt. A corrected source-pinned run supplies
the 131-method result above. No failed result is converted into a pass.

## Measurement and next decision

The nonempty fixture profile is an observation, not maximum-load or WCET
qualification. It covers a 75209-byte legacy image and 82613-byte compact image.
The recorded `_fold_entry` own times are 0.000088626s and 0.000039835s;
`_derive_association` cumulative times are 0.000004791s and 0.000001291s.
The much larger inclusive fold time includes owner-dependent admission.
These measurements do **not** establish a useful semantic-reducer cache.
Snapshot creation, exact-key comparison and retained storage would add costs.

Do not continue tiny extractions merely to create a cache. First identify
substantial closed work after preserving captured reads, callback outcomes,
alias checks and refusal order, and measure its complete reuse cost. The profile
also identifies repeated sizing work; the event-plan `_size` traversal remains
recursive and requires an explicit Power-of-Ten control-flow/resource assessment.
Any successor must preserve exact sizing, original depth/byte limits, type and
cycle refusals, all original fixtures and the unchanged reuse oracle. Optimizing
admission cost does not itself repair cached admission.

All A01–A24, G1–G6, C01–C14, P01–P10 and R01–R46 obligations remain. This
checkpoint is not publication authority, installed qualification, lossless
compaction, cognitive improvement, whole-system assurance or certification.
No main merge, install, tag, release or marketplace update is authorized by these
results alone. Their evidence cannot replace the original complete gates.
