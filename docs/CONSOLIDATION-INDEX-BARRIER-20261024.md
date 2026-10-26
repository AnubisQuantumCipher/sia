# Verify index coverage before source retirement

Status: TESTED repair in the legacy consolidation path; not installed or released.
Packed-index reading/writing remains unactivated. This repair does not depend on
experimental packing or grant publication authority.

## Defect and boundary

`_publish_event_index_entries` previously returned after its writes without
observing the complete written set. Its caller could then unlink original source
pages. Four retained predecessor controls injected a write that left no file,
malformed bytes, a canonical record with conflicting payload identity, or a later
write that removed an earlier index entry. Each failed because the expected
refusal was absent. These are callback fault injections using actual temporary
corpus files, not observed physical disk failures or a live-machine incident.

The writer now runs `_verify_event_index_entries` after the entire write loop and
before returning to source retirement. It checks the current count bound and
compares every canonical expected entry against the existing current-policy
reader, including that reader's epoch/source lineage checks. Missing, malformed
or differing entries refuse. The final whole-set pass matters: immediately
checking only the most recent write would miss an earlier entry removed by a
later write. Preflight conflict refusal and identical-entry replay remain.

The check uses the current owner-bound `MAX_EVENT_INDEX_RECORDS` dependency.
Its explicit unbound slot now follows the existing module pattern; normal
`bind()` supplies the active owner's value. This is not a default capacity or
new authority. Existing partial-binding limitations remain.

## Failure and recovery evidence

Candidate controls verify that refusal preserves the original source bytes and
retains the durable execution record in `executing`. The epoch may already have
been written; neither refusal nor an exception means no effect or rollback.
The missing-write control then removes the fault and resumes through the actual
retained intent: fresh execution finishes, keeps the same epoch bytes and only
then retires originals. Corrupt/conflicting bytes are not silently overwritten
as part of that retry control.

The unchanged previous 320-test roster plus four new controls passed: the final
source ran **324 tests in 42.675s**, exit zero; whole-job elapsed time was
43401837725 ns. Endpoint source inventories matched. The prior source also
passed 324 tests in 42.621s before the explicit dependency-slot declaration.
Both results and the four failing predecessor results are retained separately.

The original isolated envelope is unchanged: exclusive workload lock,
60-second job deadline, five-second termination grace, 2 GiB address-space,
512 MiB file-size, zero core, private HOME and network/PID isolation. Tests use
the existing temporary-corpus fixtures and fixture Git adapter. There is no
maximum-domain timing claim or installed workload measurement.

Strict product analysis still exits nonzero: the baseline has 530 findings,
the first implementation 531, and final source 523. The added initial finding
and seven pre-existing findings concern the undeclared owner-bound count name;
its explicit slot removes those diagnostics. No new code/message diagnostic
remains relative to the baseline. This is not a clean whole-module static gate.
The new tests and retained drivers have zero findings under the selected
167-rule profile; changed routines are within 60 physical source lines.

## Scope still open

This is sequential observation under the existing cooperative corpus lease,
not one atomic snapshot. It cannot prevent a hostile same-user writer or a
callback from changing an earlier record after its final observation. Protected
permission, immutable custody, physical durability, crash consistency and full
source-to-readiness/ACK assurance remain separate obligations. An existing
matching record does not establish which attempt wrote it.

The extra validation and I/O are deliberate. Full-domain capacity, worst-case
cost and original full-writer qualification remain open. R05's newly selected
fresh-validation policy does not relax those requirements. Full native/SPARK
admission, installed recovery, actual harness lifecycle, independent acceptance
and release/marketplace gates remain open. No universal lossless compaction or
avionics certification claim follows.

The next integration step is to carry this coverage-before-retirement boundary
through the source-bound transaction and protected pack transition, with exact
coverage, durable intent, fault recovery, correction/deletion and downgrade.
See `EVENT-INDEX-PACK-MIGRATION-GATES-20261024.md`. Exact source pins, raw results,
commands and failure classifications are in the companion evidence JSON.
