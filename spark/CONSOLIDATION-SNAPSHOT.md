# Immutable consolidation discovery candidate

Status: experimental reader only. The resident scanner is unchanged and the
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
- A tree ID is not a durable retention pin. Production must bind a retained
  commit/reference to the named transaction and protect it from collection
  until the complete transaction and recovery obligations permit retirement.
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
