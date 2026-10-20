# Immutable consolidation discovery candidate

Status: experimental admitted snapshot discovery. The resident scanner is unchanged and the
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

Exact-source reproduction for the process-death checkpoint:

- Commit: `6fbe1fa8f5a7cec74adf3e254f1fd58e99e9eb04`.
- Git archive SHA-256: `ddcf1b49f032677e37834af114b4cf885b7e573ab8f51a5d3ffd4ab4a808df82`.
- Runtime: Python 3.14.7; git version 2.55.0.
- Command: `python3 -B -m unittest tests.test_consolidation_admission_exec tests.test_consolidation_admission tests.test_consolidation_snapshot tests.test_consolidation_exec_recovery -v`.
- Exit: 0; the retained raw log reports 20 tests passed.
- External evidence directory: `consolidation-admission-exec-reproduction-v1`
  under the mission evidence root; it retains archive, extracted source, raw log
  and receipt. Independent GPT-6.1 read-only review is retained as
  `consolidation-admission-exec-review-v1.txt`; it found no blocker for this
  limited component scope and does not supply certification independence.

## Admitted immutable traversal

`siaconsolidationdiscovery.discover` composes the retained admission journal,
read-only pin verification and exact commit-tree resolution under the corpus
lease. It traverses the corpus root, `events` and one organ level with a stack
bounded to three frames. Each resumed frame must match its parent entry and
the root must match the admitted commit. The returned cursor includes the exact
admission record. Moving HEAD and replacement objects are not traversal inputs.

Each call accepts a bounded work budget. A visited entry or exhausted frame
consumes a unit; empty trees cannot create an uncharged loop. Ancestors are
visited one entry at a time so the active child remains anchored to the last
parent entry. Leaf entries are read in bounded batches. Candidate output is
limited by the same budget and includes path, blob identity, organ, date and
shard number. Existing event-path parsing and the pinned cutoff decide which
paths are candidates; blob identity is not live-source validation.

The copied input cursor is never advanced in place. If a later descendant read
fails after private progress, no result is returned and the caller can replay
the original cursor. This is not durable exactly-once delivery: the production
consumer must atomically retain the next cursor together with its pending
candidate batch before acknowledging or consuming that batch.

Tests cover continuing atomic replacements and commits between single-unit
steps, deterministic replay, immutable candidate blob identities and a late old
day remaining intact outside the admitted snapshot. Additional controls cover
multiple organs, shards, the exclusive cutoff boundary, invalid calendar dates,
empty corpus/events trees, batching equivalence, changed bindings, missing pins
and a descendant-read failure after private advancement. The combined discovery,
admission, snapshot and prior recovery suites pass 32 tests.

One passing test deliberately records an **UNPROVEN boundary**: a forged
completed cursor can return no candidates despite eligible sources existing.
Structural validation cannot authenticate traversal history. This API is only
an internal candidate pending a durable owner and, for a hostile same-user threat
model, a protected authority boundary. It must not be exposed as a caller-owned
completion certificate or used to clear recovery debt. The production legacy
churn characterization remains unchanged and still records the known defect.

Remaining integration work:

- Persist pending candidates and cursor as one recoverable state, bind their
  consumption to the named maintenance transaction, and forbid skipping a batch.
- Preserve legacy claims and debt through explicit migration.
- Durably schedule post-snapshot arrivals without including them in this
  snapshot's completion claim or repeatedly restarting this snapshot.
- Preserve all live complete-shard, source identity, protection, open-take,
  epoch/index lineage and unlink revalidation gates.
- Qualify pin lifecycle/resource budgets, filename compatibility, failures within
  durable operations, selected resident restart and actual recall.

The default budget and finite per-command timeout do not establish a wall-clock
deadline: lease waiting, Git/CPython allocation and full bounded tree-listing
materialization remain in the runtime assumptions. No Power of Ten compliance,
whole-system liveness, formal proof or release qualification is claimed here.

Exact-source traversal reproduction:

- Commit: `218c18acd8367974fa0fb2e0ecfead10dedb6843`.
- Git archive SHA-256: `214f4344ab36bb9e623d483bc462dc127d74d39750ce2304c5c66b4105d5338c`.
- Runtime: Python 3.14.7; git version 2.55.0.
- Exit: 0; raw log reports 32 tests passed, including the explicitly
  negative forged-cursor and legacy-churn characterizations.
- External evidence: `consolidation-discovery-reproduction-v1` retains the
  exact archive, extracted source, command, raw log and receipt.
- Independent GPT-6.1 review: `consolidation-discovery-review-v2.txt`,
  read-only inspection with no blocker in the stated component scope.

Command:

```sh
python3 -B -m unittest tests.test_consolidation_discovery tests.test_consolidation_admission_exec tests.test_consolidation_admission tests.test_consolidation_snapshot tests.test_consolidation_exec_recovery tests.test_consolidation_backlog_recovery -v
```

## Durable candidate and live-claim staging

`siaconsolidationdelivery` now owns an experimental on-disk handoff record.
Its public operations accept the expected admission and a bounded work budget;
they do not accept a caller cursor or acknowledgment. The existing strict
state-file reader, corpus lease and atomic writer are used.

| Phase | Retained work | Permitted progress in this checkpoint |
|---|---|---|
| `scan` | Last cursor from an empty candidate page | Read and atomically retain the next page |
| `pending` | Before-cursor, exact next cursor and candidate batch | Replay that batch or derive live claims |
| `claimed` | Same batch plus bounded selected live claims and remaining days | Revalidate and replay; no execution or retirement |
| `complete` | Exhausted discovery with no outstanding candidate batch | Revalidate admission/pin and replay the observation |

The next cursor of a nonempty page is retained inside its pending batch; it
does not replace the before-cursor. Loading pending work recomputes its exact
page against the pinned snapshot and rejects omitted candidates or a cursor
jump. A different later requested budget cannot replace that outstanding batch.
Missing delivery state restarts from the snapshot root; this can replay work
and is not rollback detection. Protected state ownership and authenticated
traversal history remain unimplemented. `complete` is not publication or
consolidation settlement authority, and a caller must not use it to clear debt.

The new `_observe_consolidation_claims` helper is extracted from the original
claim-preparation path. Legacy preparation still performs its original state
update and uses the same source-directory and content checks. The delivery
path uses this helper to derive claims from the retained batch, then atomically
stores them together. It requires every selected day and every selected
candidate path to appear in the live claims. Missing observations refuse
without discarding the pending batch.

Staging additionally requires every claimed source to remain live and match the
existing source validator. This is deliberately distinct from legacy execution
recovery: the legacy validator can accept a missing source with exact retained
epoch lineage, while this staging phase has executed no consolidation. The
initial independent review found that using the legacy validator alone violated
the staging contract. A regression using actual legacy consolidation and real
epoch lineage failed before the fix (`ValueError not raised`). The staging-only
presence check repairs that defect without changing legacy recovery semantics.
The failing source, log and receipt remain in
`consolidation-delivery-missing-source-negative-v1` externally.

Another retained negative control showed that ordinary Python dictionary
equality accepted Boolean/integer substitutions in a persisted batch. Exact
replay now compares canonical JSON encodings, preserving those type distinctions.
The pre-repair test failed for both substitutions; its source and raw evidence
remain in `consolidation-delivery-typed-replay-negative-v1`.

The staging tests retain exceptions before and after batch/claim persistence,
mutated-return and malformed-state controls, missing and changed sources, and
exact source digest checks. Additional workers perform actual SIGKILL after
batch persistence and after claim persistence; fresh interpreters must replay
the exact records with unchanged original source and maintenance-marker bytes.
These are returned-operation cuts, not failures inside a filesystem write,
storage power loss or a resident-service campaign.

The expanded check also exposed stale release export expectations for
`_canonical_consolidation_queue` and `_canonical_consolidation_claims`. An AST
comparison found both omissions in the pre-change base as well as the working
tree. Both names are now explicitly pinned; exact export equality remains
required. The original failed run is retained in
`consolidation-delivery-development-v2`, with the source-list diagnosis in
`consolidation-delivery-export-pin-diagnosis-v1.json`.

The delivery serialization ceiling is currently 1,048,576 bytes; its reader
inherits the larger existing state-reader ceiling. These are prototype resource
limits, not an approved reduction of supported corpus/claim capacity. CPython
allocation, authenticated producer/currentness, full capacity compatibility,
execution/retirement, late-arrival handoff and legacy migration remain open.
There is no transition out of a nonempty claimed batch until the real consumer
protocol is implemented and qualified; there is no acknowledgment shortcut.

Exact-source staging reproduction:

- Commit: `cfd7727b404264b5b6de5a7e63a85de440e06653`.
- Git archive SHA-256: `a875e237ab893131f7188e4a225dfe419a08fce72fe4607e6988d901d0b015c4`.
- Runtime: Python 3.14.7; git version 2.55.0.
- Exit: 0; the retained raw log reports 86 tests passed.
- External evidence: `consolidation-delivery-reproduction-v1` retains the
  archive, extracted source, exact command, raw output and receipt. It covers
  delivery/discovery/admission, fresh-process cuts, original EpochMerge and
  exemplar cases, module ownership and explicit facade export contracts.
- Independent GPT-6.1 review: `consolidation-delivery-review-v3.txt`;
  the earlier blocker and both pre-repair failing regressions remain retained.

The source-bound result qualifies only the staged component and the named
regressions. The installed runtime, execution/retirement protocol and full
assurance/release gates remain incomplete.
