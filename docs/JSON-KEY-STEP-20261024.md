# Dictionary sizing without cached admission

Status: **selected traversal TESTED; R05 FAILED; complete system INCOMPLETE**.
The source baseline is the commit recorded by the retained runtime receipts.
One production module changes: `siasourcebatch.py`. No outer admission cache,
original test, workload oracle, deadline, resource ceiling or release gate changes.

## Ownership and order

The JSON walker previously returned a dictionary key from its ancestry frame,
then returned the pending value on another traversal turn. The frame now sizes
the key and returns its captured value in one turn. This removes the frame's
pending/child fields and the extra dispatch for each key; it adds no cache or
width-sized queue.

The iterator entry captures the value before key-sizing callbacks. The walker
still accounts for the comma, refuses a nontext key, applies the key-depth
bound, invokes current string sizing, accounts for the colon, and only then
processes the captured child at its original depth. The child remains a live
alias: replacing a mapping entry during its key callback does not replace the
captured child, while mutation of that child's contents remains observable.

Native dictionary-iterator failures, capacity refusals and scalar callback order
remain. Input introspection through Python frames, arbitrary interpreter
modification and exact allocation-failure equivalence are outside this evidence.
The existing byte/depth/cycle guards remain; this is not a whole-runtime bound
or fixed-allocation proof.

## Qualification

The final repository-portable roster passed **72 tests in 22.608 seconds**,
exit 0, with unchanged source endpoint maps. It includes original sizing,
Unicode/budget, memo, compact capture, checkpoint/delta and episode controls.
The new differential controls compare result, refusal reason and callback/budget
trace against the complete preceding source frozen in
`tests/fixtures/json-size-key-step-baseline.py`. Its string-sizing dependencies
remain the unchanged current modules; this is not an independent implementation.

Four deliberate negative variants were detected, with no harness errors or skips:

| Unsafe change | Recorded failures |
| --- | ---: |
| Omit key-depth check | 2 |
| Move depth refusal before nontext-key refusal | 1 |
| Omit colon accounting | 35 |
| Reread the mapping value after the key callback | 2 |

The initial private-loader roster passed 72 tests, but its hard-coded temporary
reference path was unsuitable for publication. That evidence is retained
separately. The loader was made repository-relative and the complete affected
roster and negative variants were rerun. No historical output was rewritten.
Production/test/runner sources passed the selected 167-rule static policy and
syntax compilation. Actual GPT-6.1 source/raw review found no remaining blocker
within this scope; it was not independent execution.

## Compact workload evidence

The new diagnostic starts with the unchanged private collectors producing 1046
events. Existing `bootstrap_episodes` performs full replay and v3 validation.
Existing `prepare_epoch` and `project_capture_entry` then construct a synthetic
empty next-entry compact-v1 image. Both source and candidate runs complete full
fresh `_validate_capture_image`, preserve input/corpus/cursor checks and leave
the compact memo empty.

The complete setup, bootstrap and measurement remain inside the original
60-second deadline, five-second termination grace, 2 GiB address-space and
512 MiB file ceilings, workload lock and private sandbox. No cap was raised.

| Observation | Preceding source | Candidate |
| --- | ---: | ---: |
| Compact image bytes | 3189942 | 3189942 |
| Parent episode records | 1046 | 1046 |
| Current entry events | 0 | 0 |
| Profiled fresh validation nanoseconds | 9094410539 | 6780676706 |
| `_json_size` calls | 214 | 214 |
| Frame `take` calls | 2293983 | 1367258 |

These are separate synthetic images with different identities and profiled
timings, not a controlled speed benchmark. Cumulative profile times overlap.
The profile identifies repeated sizing cost and supports this structural change;
it does not prove general speed, maximum-load behavior or WCET.

The supplied zero predecessor/root pins are fixture data, not witnessed authority.
An empty delta measures repeated predecessor/context work, not large new-entry
decoding. Compact-v1 does not cover idle/delivery branches. This is not the missing
historical 12.7 MB capture, a resident-front-door acceptance run, or recovery proof.

## Evidence and remaining work

The reproducible bundles retain exact source, commands, endpoint maps, raw
outputs, review and complete synthetic inputs:

- [A: preceding compact workload](JSON-KEY-STEP-20261024-A.json).
- [B: source, differential tests and negative controls](JSON-KEY-STEP-20261024-B.json).
- [C: candidate compact workload](JSON-KEY-STEP-20261024-C.json).

Each bundle keeps the existing member and byte limits. The complete bootstrap
checkpoint is reproduced from the compact image and checked against its saved
bytes; large images are split and bound by whole-file hashes. Endpoint hashes
are not loaded-code custody. Reproduction/packaging is not product acceptance.

The immutable-byte frontiers in checkpoint admission and projection still do
not authorize skipping current context, decoder or policy checks. This change
improves the structure of fresh validation; it establishes no useful expensive
derivation cache and does not exercise the conditional reuse-oracle decision.
R05 remains FAILED. Original full-workload, continuity, SPARK, protected-runtime,
installed-path and marketplace acceptance requirements remain binding.
