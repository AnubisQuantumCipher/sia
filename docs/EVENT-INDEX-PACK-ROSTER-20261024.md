# Complete occurrence roster integration experiment

Status: TESTED prerequisite in temporary fixtures. Normal runtime lookup remains
legacy-only. This does not activate packing, migrate source records, retire legacy
files, repair the installed backup, or grant publication/readiness authority.

The exact legacy per-identity loop is extracted into the ordinary eager
`_join_event_index_occurrences` helper. Its sorted lookup order, fresh per-record
validation, early live/consolidated conflict refusal and missing-record result are
preserved. The enclosing occurrence caller still runs the original missing-lineage
gate. The existing owner facade binds this helper before execution; no suspended
generator is introduced into that dynamically bound module.

The separate experimental reader adds a complete-request iterator and eager join.
The iterator checks an exact sorted unique tuple against the original owner's
identity limit before I/O, partitions the entire tuple by three-hex prefix and
groups of at most 64, and carries one capture across every group. It does not
reset budgets or discard observations. A full pack does not hide an additional
legacy entry. The iterator must be exhausted or refused; a yielded prefix is not
a complete result or authorization. A changed identity policy is checked before
each yield and after the final yield.

The eager join admits only native sets/frozensets of native strings, snapshots the
existing result, rejects results outside the request, and accumulates additions
privately. It updates the caller's result only after the complete request succeeds
and request/result snapshots still match. It does not undo mutations performed by
an untrusted callback. Callback authenticity, transient mutations restored before
checks, hostile same-process code and Python allocation remain outside this
experimental guarantee. The caller must hold the corpus lease and complete its
existing capture validation before acting. The final `found.update` is not proved
atomic under allocation failure; successful late-validation controls do not prove
that stronger property.

## Retained evidence

The final isolated roster passed 136 tests in 10.782s; whole-job elapsed time is
recorded separately in the evidence JSON. All original selected rosters remain:
codec, reader, grouped lookup, page replay, complete event-page-plan suite, module
ownership, epoch admission integrity and EpochMerge. The original 60-second job,
2 GiB address-space, 512 MiB file, zero core limits, heavy-job lock, read-only
source and private fixture filesystem/network/PID environment were unchanged.
Inventoried source bytes matched before and after.

New controls exercise:

- All 65 identities in a saturated-prefix fixture, split into groups of 64 and 1,
  including the exact legacy overflow entry, through one capture.
- Actual mixed-prefix event consolidation, prepare, publication and retry under
  the real fixture lease with both `_Capture` and `_BeforeView`, complete request
  coverage, retained pack dependencies and exactly one new page event.
- Missing durable lineage and replaced later-pack refusal before publication.
- Failure in a later group without partial additions to the caller's result;
  changed request/result inputs; changed policy after the final yielded entry.
- Empty, malformed, over-limit, non-native and out-of-scope requests before I/O.
- Original legacy early conflict ordering and per-owner/parent patch binding.

The initial 135-test run also passed, but selected static analysis found three
B023 test-loop capture diagnostics. Those are retained, with hash-verified source
reconstruction; explicit closure bindings corrected them. The final selected
167-rule static profile has zero diagnostics in the changed reader, new tests and
named final drivers. `siathought.py` retains 530 findings, with no added or removed
code/message findings against the exact baseline. Independent source/raw review
then found an equality-based container type gate. A retained negative run reproduced
both deceptive and raising metaclass failures. Identity checks now reject these
containers before their equality, length or iteration hooks and before capture I/O.
The initial metaclass fixture also triggered PLW1641; an explicit refusing hash
hook corrected that diagnostic without suppressing the check. The final complete
roster includes the corrected adversarial fixture. This is not a zero-warning
claim for that module or the system.

## Engineering scope and remaining acceptance

These are project adaptations of the Power of Ten safety intent, not quotations
from Holzmann or formal compliance: simple finite partitioning, original logical
identity and group limits, short routines, checked native shapes, explicit refusal,
limited result mutation and retained static findings. The Python sorting, sets,
dicts, callback dispatch, complete capture storage and interpreter allocation are
not proved fixed-memory or worst-case-time bounded. Group callback order is the
new operation contract from the predecessor checkpoint, not trace equivalence to
repeated legacy lookups. Normal runtime keeps its original operation.

Next acceptance work must qualify whole-request costs and input ownership, then
define exact-coverage durable pack publication and crash-reconciled migration
before any installed activation or legacy retirement. The current controlled
65-record roster is not evidence of captured historical truth or a maximum-domain
resource proof. The mixed-prefix fixture uses real temporary event records but
does not qualify the installed corpus or resident harness.

Protected SPARK authority, native admission, full writer qualification, actual
capsule/off-path restore and replay, continuity lifecycle, all original assurance
gates, and release/marketplace verification remain open. The specific R05 question
remains pending; neither these tests nor publication of this checkpoint waives
useful expensive reuse or fresh policy validation. No certification is claimed.
