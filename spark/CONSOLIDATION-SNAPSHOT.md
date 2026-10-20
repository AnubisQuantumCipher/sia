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
Admission journaling and fresh-process cuts now have the limited evidence below.
Power-loss behavior, aggregate reference budgets, retirement, orphan-pin recovery
and persisted scanner schema integration remain OPEN.

## Experimental admission journal

`siaconsolidationadmission.admit` now serializes one exact request under the
existing corpus lease. It persists `planned` before creating the reference,
then persists `admitted` only after exact pin readback. Recovery of `planned`
may finish creating that same pin. Recovery of `admitted` uses `check_pin` and
cannot recreate a missing pin. The journal binds schema, generation,
transaction digest, cutoff, commit and phase. Conflicting fields refuse before
changing the retained request. Malformed state is not silently normalized.

The transaction digest is currently caller-supplied; it is not an authenticated
producer or a proved binding to the installed named maintenance transaction.
The fixed journal path permits one outstanding request. There is deliberately
no implicit replacement, cleanup or retirement policy. Integrating repeated
generations requires those transitions and their evidence, not deletion of a
blocking journal.

Exception-injection tests interrupt after plan persistence, after pin creation
and after admission persistence, then reload and resume the exact request.
Other tests remove an admitted pin, conflict the request, or corrupt retained
fields and require refusal without journal repair. These tests use real
bounded Git commands, the corpus lease and atomic journal writes in isolated
storage. They do not establish actual process-death, torn-write or power-loss
behavior of this new journal.

The first development run failed because the composed fixture's lock path
still referenced its separate isolated HOME while its STATE was relocated.
The fixture now binds the corpus lock to its own STATE directory. This did not
require bypassing or mocking the lease.

## Fresh-process admission cuts

`tests.test_consolidation_admission_exec` uses distinct interpreter executions
and actual SIGKILL after each of these returned operations:

- Persist the planned journal, before creating the reference.
- Create and read back the pin, before persisting admitted state.
- Persist admitted state, before returning success.

The parent checks the exact journal fields and whether the reference is present
at each cut. Fresh recovery and a second fresh replay must return the same
admitted record and leave the journal bytes unchanged on replay. The real corpus
lease, Git operations and atomic writer execute in an explicitly marked disposable
HOME. Original source bytes and the unrelated named maintenance marker must stay
unchanged; no epoch is created by admission.

Negative controls remove an admitted pin, introduce a conflicting pin after the
planned cut, and explicitly truncate a planned journal. Recovery must refuse
without replacing the retained journal or reference. The truncated-file control
is deliberate corruption, not an observed storage tear. A separate worker guard
requires explicit disposable-HOME opt-in before importing the runtime.

The combined admission exec, admission exception, snapshot and existing
consolidation exec suites pass 20 tests. SIGKILL at returned operation boundaries
establishes only these process-death cases. It does not establish failures inside
Git or the atomic writer, storage power-loss durability, authenticated transaction
production, the complete resident path, or a bound on recovery time. The new
tests do not enable the experimental journal in production.
