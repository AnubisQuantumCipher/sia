# Immutable consolidation discovery candidate

Status: experimental reader and retention-pin primitives. The resident scanner is unchanged and the
cursor-churn defect remains OPEN. This is not a new accepted retention policy.

## Implemented primitive

`bin/siaconsolidationsnapshot.py` reads a page from one full Git tree object ID.
The tree is type-checked before enumeration. A cursor is an entry offset in that
immutable tree, never an offset in the changing worktree or a moving branch.
Each call uses the existing bounded subprocess runner, restricts child output,
and rejects malformed records, unsupported entry kinds, unsafe names, truncated
output, excess records and invalid page bounds.

The primitive uses Git's documented
[`ls-tree --full-tree -z`](https://git-scm.com/docs/git-ls-tree.html)
format, without recursive enumeration. Replacement objects are disabled and
lazy fetch/protocol use are disabled for these commands. These process settings
are not OS-enforced network isolation or protection from hostile same-user code.

Tests use real Git objects and the real bounded runner. They show that one tree's
pages remain unchanged after file replacement, new arrivals, a newer commit and
a Git replacement mapping. The newer tree separately exposes the new arrival.
Blob identities, missing objects and cursors beyond the tree refuse. Malformed
record/name/type and byte/entry/page bounds also have negative tests.

The reader materializes one bounded tree listing on each page call. Its byte
ceiling is 16,777,216; its tree-entry ceiling is 4096 and its page ceiling is
1024. These are prototype limits, not an approved change to accepted corpus
capacity. CPython and Git still allocate dynamically. Reading a bounded tree
does not prove bounded total recovery or worst-case execution time.

## Trust and compatibility obligations

- A full object name pins a Git namespace under the assumption that the local
  Git implementation and object store preserve object integrity. The helper
  does not independently recompute the raw tree-object hash.
- A tree ID alone is not a retention pin. The prototype now supports a
  generation-bound commit reference, but production must durably bind it to
  the named transaction before admitting the scan and qualify its retirement.
- The prototype rejects control-character names, unsupported entry types and
  non-UTF-8 output. The legacy walker can ignore some non-candidate names.
  Compatibility and refusal behavior must be explicitly reconciled before
  integration; tests of the new reader cannot silently authorize regressions.
- The helper's subprocess callback is trusted. No caller-supplied Boolean or
  tree listing may become protected source authenticity or deletion authority.

## Integration gate

1. Specify a versioned persisted discovery schema with exact retained commit,
   tree IDs, offsets, cutoff, generation and transaction identity. Reject missing
   or mismatched bindings. Define crash ordering for reference and state writes.
2. Preserve all pending legacy claims and their source/ledger bindings.
   Migration may not clear debt or reinterpret incomplete v1 state as complete.
3. Define which arrivals belong to the admitted snapshot and how later eligible
   arrivals are durably scheduled. Continue capture without losing events or
   manufacturing coverage. This boundary has not yet been accepted.
4. Revalidate complete live day shards, content identities, Git retention,
   protection/open-take windows, epoch/index lineage and unlink conditions.
   Immutable discovery alone is never authority to delete a changed source.
5. Account for absent or corrupt objects, ref loss, directory/entry ceilings,
   UTF-8/path compatibility, replay, cutoff rollover and storage exhaustion.
6. Prove the regression completes while current-day writes continue; retain
   late-arrival, source-conflict and restart negative controls. Then qualify
   the selected resident path and installed recall before release.

The existing characterization remains unchanged until the integrated behavior
is deliberately repaired and its new acceptance evidence is reviewed.

## Retention-pin primitive

`pin_commit` admits only a full available commit identity and a canonical
generation. Its reference is `refs/sia/consolidation/<generation>`. Creation
uses Git's [expected-old-value update](https://git-scm.com/docs/git-update-ref.html)
with an absent-reference precondition and no symbolic dereference. Identical
replay is accepted; a conflicting or symbolic reference refuses. Readback must
match. Git fsync hardening is requested explicitly. This is not evidence of
power-loss durability of all preexisting objects, packed references or storage.

`check_pin` is a separate read-only operation for already admitted state.
It refuses a missing or different reference and an unavailable commit; it never
recreates the missing reference. Integration must preserve that distinction:
creation retries before admission are not authority to repair missing pins after
admission. Both operations require the caller's exclusive corpus lease; they
do not exclude hostile same-user Git writers.

The tests replace HEAD with an independent root, expire fixture reflogs, pack
references and run real garbage collection. The pin retains the original commit
and tree; exact replay still works with packed refs. After exact fixture-only
pin removal, the negative control confirms the original commit is collected.
Another test rejects a symbolic pin without changing its target. These commands
operate only on disposable test repositories, never on the installed corpus.

Four snapshot tests pass. No production reference is created by this checkpoint.
Admission journaling, fresh-process/power-loss cuts, aggregate reference budgets,
retirement, orphan-pin recovery and persisted schema integration remain OPEN.
