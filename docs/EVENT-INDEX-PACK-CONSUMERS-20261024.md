# Consolidation consumers and publication conflict repair

Status: TESTED legacy publication repair and experimental consumer fixtures.
Normal runtime remains legacy-only. No pack activation, migration, legacy
retirement, installed change, source acknowledgment or release follows.

## Reproduced publication gap

`_publish_event_index_entries` preflights the complete requested batch and then
reads each entry again before writing. Previously, that second read skipped any
existing entry, including one that no longer matched the request. A retained
negative control replaces the temporary legacy leaf with a different canonical
payload digest on the second read. The original reader returns that new entry;
the old publisher silently returns instead of refusing. The test fails with
`ValueError not raised` on the exact retained original source.

The publisher now compares the fresh entry to the requested entry before
skipping it. Conflicts raise the existing explicit error. Preflight, the second
read, existing write ordering, limits and identical-entry replay remain intact.
The negative fixture itself performs the replacement; the repaired operation
refuses before `_before_corpus_mutation`. This is not a claim that the entire
fixture had no effect or that the check prevents every subsequent filesystem
race. The cooperative lease and existing filesystem assumptions remain.

## Consumer fixture evidence

The new fixture substitutes the experimental captured reader into the real
consumer calls under one corpus lease and one aggregate capture per operation.
It does not change the installed or normal runtime dispatch.

- Packed duplicates survive preflight, publication and repeated publication
  without rewriting the pack or recreating the retired fixture legacy leaf.
- Conflicting packed payloads refuse both preflight and publication before a
  product write. A malformed pack cannot silently fall back to a valid leaf.
- Actual retained-intent consolidation runs first through the legacy path.
  Exact temporary legacy bytes are then packed, and actual `inspect_outcomes`
  returns the same selected-claim result twice. Pending journal and memo bytes
  remain unchanged; no acknowledgment or readiness is inferred.
- A transport-valid pack with a changed payload digest still fails the existing
  comparison against the pinned original source. Missing packed coverage also
  refuses. A checksum alone is not source truth or publication authority.

These are controlled fixtures, not a qualified migration or evidence that every
consumer, workload and installed client supports packed storage.

## An explicit mutation limitation

The read-only substitution cannot serve as a publication mutation protocol.
When an unrepresented entry is legitimately written to a new legacy fallback,
the capture's previously observed absence becomes stale. The test verifies that
the new leaf contains the exact requested bytes, the existing pack is unchanged,
and the final capture check refuses `source-absence-changed`.

That is a known write followed by refusal. It is not rollback, no-effect failure,
successful acknowledgment or a qualified retry. A future adapter must bind and
validate intended after-write state while continuing to reject unrelated changes;
it must reconcile uncertain outcomes and preserve original source-retirement
gates. Suppressing the capture check, clearing observations or accepting all
changed paths would weaken the contract. This checkpoint does none of those.

## Validation and Power of Ten adaptations

The complete selected roster retained the original pack, captured-reader,
grouping, page-plan, owner-binding and epoch tests, and added the new consumer
tests plus the original consolidation-outcome, delivery-execution and executor
suites: **176 tests passed in 32.127s**. The whole job recorded 32895949661 ns,
exit zero and equal before/after source inventories. The original isolated
60-second, 2 GiB address-space, 512 MiB file-size and zero-core envelope remains.

The selected 167-rule static profile reports zero findings for the new fixture
and named execution drivers. `siathought.py` retains 530 findings both before
and after; the code/message multiset has no added or removed diagnostics. This
is not a zero-warning claim for that module or SIA. New fixture routines and the
changed publication routine are within 60 physical source lines.

The repair applies the safety intent of simple control flow, short routines,
checked fresh results and explicit error propagation. Python allocation,
dynamic dispatch, assertions and external calls are not a SPARK proof, bounded
allocator or complete worst-case execution argument. Those Power of Ten
deviations and the original strict-analysis obligations remain visible.

Exact source hashes, raw test output, command envelope and retained negative
evidence are in `EVENT-INDEX-PACK-CONSUMERS-EVIDENCE-20261024.json` and the local
sealed evidence bundle. Independent review is source/raw-evidence review only;
it does not stand in for independent execution.

## Next acceptance boundary

Before activation, qualify the intended mutation view and complete consumer
integration, then a bounded deterministic exact-coverage plan and protected
SPARK authorization for the durable transition. Retain fault tests at each
write, durability and retirement boundary. Original capacity equivalence,
correction/deletion, downgrade, capsule/off-path recovery, installed-client,
whole-job admission, proof and release gates remain open. R05 has not changed.
No whole-system assurance or avionics certification is established.
