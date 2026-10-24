# Captured source join for event-pack planning

Status: **TESTED, UNACTIVATED, NOT SYSTEM ACCEPTANCE**. This connects the
[transport planner](EVENT-PACK-COVERAGE-PLAN-20261024.md) to the existing retained
file capture and epoch validator. It does not change an installed path or grant
publication, source-retirement, readiness or acknowledgment authority.

## Contract and scope

`siaeventpackcapture.prepare_captured` receives a strictly ordered immutable
selection of native event identifiers for one organ/prefix. The caller retains
the existing `_Capture`, its shared budget and corpus lease. The adapter reads
the prior pack and selected legacy files through that capture, validates their
canonical bytes and current epoch/source-manifest correspondence, and calls the
unchanged planner with those observed bytes. A selected record missing from both
representations refuses the complete plan.

Every prior-pack record is validated, including records outside the selection.
Any existing legacy counterpart must have identical bytes. Conflicting copies,
malformed packs or invalid lineage cannot be hidden by fallback or an empty
selection. Prior records survive, and each selected input is represented or
retained as legacy fallback according to the existing transport contract.

The result is the planner's immutable `(pack bytes or None, represented inputs,
fallback inputs)` tuple. No file is written, removed or acknowledged. The result
is a finite observation; the caller must retain and revalidate the capture at
later use. It is not a durable operation record, protected permit or proof of
original payload authenticity. Epoch-manifest correspondence does not establish
that a human or source actually produced the claimed payload.

This covers the **declared selection and all prior-pack records**, not every
legacy record in that prefix or the entire corpus. No directory enumeration or
global completeness claim is made. Unselected legacy-only records remain outside
the selection. The complete migration/capsule inventory remains a separate gate.

## Resource and policy boundary

Native count, order, route and type checks precede source reads. Existing planner
ceilings remain unchanged. The adapter checks the current index/count/state
limits and epoch lineage limits before and after planning and after the final
capture check. The actual epoch read path uses `MAX_EVENT_PAGE_BYTES`; this limit
is included alongside `MAX_EPOCH_PAGE_BYTES`. Planner limits retain their original
explicit first-three-field mapping.

One shared capture budget covers the existing file/dependency reservations plus
a logical plan/envelope reservation. Each organ/prefix may be attempted only once
in that capture, including after failure, so a retry cannot silently reset its
reservation. Other prefix attempts still consume the same budget. The caller
owns cleanup on both success and failure. Existing capacity refusals propagate.

The reservation is logical accounting, not a proof of CPython allocator usage or
maximum-domain capacity compatibility. Large selections can refuse before reads;
no existing cap is raised. Capture and owner implementations, callbacks, lease
authenticity and Python runtime behavior remain trusted integration premises.
Endpoint checks cannot detect every transient policy change or protect against
hostile code with the same process authority. No such isolation is claimed.

## Evidence and retained failures

Final source passed **355 tests in 36.790s**, exit zero; whole-job elapsed was
37669420712 ns and before/after inventories matched. The original 338-test roster
ran unchanged with 17 new temporary-corpus controls under the original isolated
60-second deadline, five-second termination grace, 2 GiB address-space,
512 MiB file-size, zero-core and exclusive workload lock. No live corpus was used.

Controls include independent wire comparison, legacy/pack-only/duplicate joins,
empty selection, full-pack fallback, selected absence, unselected prior conflict
and lineage, malformed packs, owner/lease/type rejection, shared-budget refusal,
retained failed-attempt reservations, source replacement, absence changes and
post-check policy mutation. A returned capture can still detect a later change.

The first full run failed: its fixture constructed a separately reloaded capture
class, triggering the production exact-type rejection before intended checks.
The fixture now uses the adapter's actual capture implementation; the production
type gate was not weakened. Exact first-run source and output remain retained.

Owner inspection and independent review also found an actual omission of
`MAX_EVENT_PAGE_BYTES` from the policy snapshot. A pre-fix isolated counterexample
changed that limit after the final capture check and failed because the expected
refusal was absent. The final full run includes that control and passes. The
counterexample, failed run and all corresponding source hashes are preserved.

The existing selected 167-rule static profile reports zero findings for the new
adapter, tests and retained drivers; their routines are at most 29 physical lines.
This is not repository-wide warning freedom or SPARK proof. Actual GPT-6.1
review inspected source, raw output and receipts; no independent reviewer
execution is claimed. The companion evidence JSON binds exact bytes and commands.
Raw evidence remains in the owner's retained directory, not a complete portable
offline acceptance bundle.

## Remaining acceptance work

Follow the unchanged [migration gates](EVENT-INDEX-PACK-MIGRATION-GATES-20261024.md):
complete captured inventory and source authentication; a source-bound protected
SPARK transition; durable intent and filesystem publication/reconciliation;
crash/fault tests before retirement; correction/deletion/retention/downgrade;
actual capsule/off-host restore and installed-client qualification. This module
has no production importer and does not activate dual-format storage.

Power of Ten adaptations here are bounded nonrecursive traversal, short routines,
native-type admission, narrow read-only effects, explicit checked refusals and
strict scoped analysis. Dynamic allocation, callback semantics and whole-system
resource bounds remain unproved. These are adaptations, not Holzmann quotations,
whole-system assurance or avionics certification. All original assurance,
continuity, native, writer, recovery and marketplace gates remain binding. R05
remains UNVERIFIED/PENDING; both useful expensive reuse and fresh current-policy
validation remain required.
