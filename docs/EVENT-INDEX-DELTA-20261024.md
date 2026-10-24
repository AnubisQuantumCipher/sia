# Captured index writes and capture ownership repair

Status: TESTED experimental legacy-fallback adapter and shared capture cleanup
repair. Normal index lookup remains legacy-only; no runtime imports the new
adapter. No pack publication, migration, source retirement, installation or
release is qualified by this checkpoint.

## Intended writes remain part of the checked dependency set

The prior read-only packed-reader substitution correctly refused after creating
a new legacy fallback because its captured absence had changed. The new
`siaeventindexdelta.publish_legacy_fallbacks` experiment instead declares exact
intended target bytes before writing. It requires the existing corpus lease,
native immutable sorted input records, current record/count/byte policies and
the original canonical/epoch validator. All requested entries are preflighted
before the first write; packed or legacy conflicts refuse.

It reuses the existing complete dependency observer and one aggregate budget
through every capture refresh. Before and after a selected write, it checks
current policy, the exact expected record, both storage representations and
the captured dependencies. Duplicate entries do not create a redundant legacy
leaf. New entries remain exact legacy fallbacks, including when a pack is full.
The adapter returns only its selected write paths, never readiness or an ACK.

This interface is not an authorization boundary. Canonical bytes and epoch
membership do not establish original payload truth. The original caller must
bind the expected records to authentic retained source evidence and obtain
protected authority. Neither a successful return nor an existing matching file
proves which attempt created it. No durable operation journal is introduced.

## Complete directory transitions

The initial combined run failed three valid publication/retry controls: full
ancestor scans observed changed child-directory metadata after the intended
file write. Those raw failures and exact source are retained.

The shared observer now has an explicit directory-entry transition mode,
disabled by default. It permits metadata changes only on declared target
ancestors whose identity and complete child roster are independently checked.
The parent entry must match the child's captured generation. Missing child
closure, unscanned children, replaced identities, unrelated members and
unexpected entries in newly created ancestor chains refuse. File generations
still join the complete scan. The original page observer's default policy
continues to reject these directory-entry changes.

Each original directory roster is captured once during index preflight. Every
subsequent write-phase observation still checks the complete retained closure;
there is no budget reset or cross-operation validation cache. This has real
costs, and maximum-domain performance and previously accepted-workload
compatibility remain unresolved acceptance obligations.

## Capture ownership must survive close errors

Independent source review found that the initial adapter closed the old capture
before registering its replacement. A close error could leave the new capture
unowned while cleanup retried the old descriptors. The retained negative test
demonstrates live descriptors after that failure and then cleans them up as
fixture teardown; it does not leave a deliberate leak on the user's machine.

The same handoff pattern existed in the shared page writer. A corrected
predecessor-source overlay test reproduces its leaked replacement capture.
The first page fault observer patched a different loaded module instance, so it
did not inject the fault; that failed observer is retained separately and is
not evidence of the product defect.

The repair gives each new capture an explicit cleanup owner before closing the
old one. The shared page, batch and cross-organ publication paths and the
experimental index adapter use the same handoff and cleanup helpers. Old and
new owners remain reachable through a failed transfer; normal cleanup handles
both without double-closing an alias.

`_Capture.close` consumes each descriptor slot before calling `os.close`,
attempts the remaining owned descriptors after an `OSError`, and reports the
first close error with the total error count. Repeating cleanup does not retry
consumed descriptor numbers. This is Linux-specific: retrying `close` after an
error can close an unrelated descriptor that reused the number. Successful
close is not a durability guarantee. See the normative operating-system
behavior in the [Linux close(2) manual](https://man7.org/linux/man-pages/man2/close.2.html).

When an operation and cleanup both fail, the affected constructor/observer and
publication cleanup paths retain both errors in an exception group. This is an
explicit simultaneous-failure error contract, not a success or suppression of
the original refusal. Normal isolated close errors still propagate. Arbitrary
asynchronous interruption, allocator failure and the entire Python runtime are
not proved safe by these tests; those remain unresolved assurance obligations.

## Tests, negative results and limits

The final expanded roster includes the original pack/planner/epoch and
consolidation suites, plus original page-batch, complete-closure, checkpoint,
checkpoint-delta and live-intake suites. It passed **320 tests in 40.929s**;
whole-job elapsed time was 41672025962 ns, exit zero, and source inventories
matched before and after. The original isolated 60-second, 2 GiB address-space,
512 MiB file-size and zero-core limits remain unchanged.

Controls cover full-pack fallback, duplicate retry, later conflicts before
any write, malformed inputs, late policy changes, pack corruption, foreign
directory members, newly created ancestors, incorrect writes, known effects
followed by injected failure, fresh retry, budget exhaustion after a write,
descriptor closure, multiple close errors, deterministic descriptor-number
reuse and primary-plus-cleanup failures. Exception injection is not a power-loss
or full resident-process crash campaign.

Retained observer failures include a wrong positional budget argument, an
incorrect assumption that `open` would reuse the desired descriptor number,
and the wrong module instance for a fault patch. The corrected reuse test uses
`dup2` to force the exact condition. Product behavior was not weakened to satisfy
these observers. Earlier passing subsets are not substituted for the expanded
final roster.

The selected 167-rule static profile reports zero findings in the changed
modules, new tests and named final drivers. New and changed routines are within
60 physical source lines; inherited large routines and repository findings are
not silently waived. This is a scoped test/static result, not SPARK proof,
maximum resource qualification, whole-system assurance or avionics certification.

## Next acceptance work

Before activation, integrate the adapter with the real source-bound consolidation
transaction and durable operation intent; independently establish original
payload evidence, protected permission, complete coverage and failure recovery.
Then implement and prove the actual pack transition, including correction,
deletion, retention and downgrade. Qualify full-domain capacity and cost,
installed capsule/off-path restore, actual harness lifecycle and loaded clients.

Original A/G/C/P/R gates, strict native/SPARK admission, the failed full writer,
R05 implementation qualification and full release/marketplace acceptance remain
open. After the user explicitly delegated the pending decision in the owner
session, the selected R05 policy is fresh current-policy validation on every call,
retiring only mandatory expensive reuse and its call-count assertion. The written
proposal and historical failures remain retained. The fresh-validation experiment is already retained on this branch; this
decision does not retroactively correct the earlier authorization misbinding or
qualify that experiment for installation. Original deadlines, capacities,
full-workload checks, proof, installed-runtime and release gates remain binding. No claim of universal lossless compaction or complete capture follows.
