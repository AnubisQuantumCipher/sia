# Runtime architecture and the module map

This file exists because an outside review made a correct observation: the
core module is too large to review, and the project's own ethic — carve a
system into pieces a reader can hold — argues for splitting it. It records
what already lives in sibling modules, what constrains an extraction, and the
sanctioned order for doing it. Volatile measurements belong to the current
source and release checks rather than a second hand-maintained map here.

## What is already split

The runtime is not one file. These lanes were extracted in earlier releases
or are implemented in the current tree, and are the pattern to follow:

| Module | Lane |
|---|---|
| `bin/siasenses.py` | sensing subsystem (extracted in v1.3.7) |
| `bin/siagraph.py` | graph/domain projection (extracted in v1.6.0) |
| `bin/siathought.py` | event-day admission/indexing, durable generated-entry/epoch pages, weekly compaction and recovery/legacy replay (implemented, unreleased; filename is compatibility) |
| `bin/siaeventplan.py` | bounded frozen-page planning and retryable publication with an explicit core owner (implemented, unreleased) |
| `bin/siaeventintake.py` | pure collector-return/page-version projection for the live loop (implemented, unreleased) |
| `bin/sialivegist.py` | pure native-episode/replay-gist binding for idle live proposals (implemented, unreleased) |
| `bin/siacontrolleridle.py` | capture and immutable binding of idle successor inputs (implemented, unreleased) |
| `bin/sialiveidle.py` | explicit idle disposition when no selected source supports native gist binding (implemented, unreleased) |
| `bin/siasourcegist.py` | deterministic derived gist page plans and exclusive, retryable publication (implemented, unreleased) |
| `bin/sialiveview.py` | read-only view of an acknowledged source transaction and its retained workspace (implemented, unreleased) |
| `bin/siasourcebatch.py` | bounded collector capture and closed source-batch construction (implemented, unreleased) |
| `bin/siasourcepublication.py` | immutable retained-batch slot plus source/live/status write-ahead bindings (implemented, unreleased) |
| `bin/siasourceeffects.py` | crash-recoverable corpus/index/graph/status/live effects publication and committed receipt (implemented, unreleased) |
| `bin/siasourcegit.py` | descriptor-bound clean corpus Git generation (implemented, unreleased) |
| `bin/siasourceengine.py` | receipt-bound pinned-engine sync and source-page projection readback (implemented, unreleased) |
| `bin/siasourceack.py` | immutable batch archival, refusal settlement, cursor publication, and final readiness acknowledgment (implemented, unreleased) |
| `bin/siatakes.py` | predictions, judge, grading, calibration |
| `bin/siacapsule.py` | continuity capsules, freeze/thaw, restore |
| `bin/siabackup.py` | repository adapters and scheduled verification |
| `bin/siabench.py` | signed-ledger QA benchmark and source-only native capture (capture entrypoint implemented, unreleased) |
| `bin/siamind.py` | usage salience, co-return reinforcement, PPR rerank, stability |
| `bin/siaqueue.py` | agent note queue |
| `bin/siarestoreadmit.py` | restore admission |
| `bin/siarelease.py` | release checks and runtime-receipt authority |

`siabench.capture_native_history` holds the real corpus owner while using
the benchmark's shared verified-source, projection and witness-cache path.
It requires the configured corpus's canonical absolute path and an explicit,
bounded, distinct requested chain roster; it does not inherit the legacy
dataset entrypoint's ambient defaults. Its `sia-native-source-capture-v1`
generator identity binds every cached page, including inspected-only pages.
Complete native rows remain in the existing scoped capture schema even
when the projection or answer-field checks exclude them. The shared prefix
performs no QA generation, retrieval scoring or artifact publication.
The old default and opt-in dataset outputs remain separate compatibility
contracts. This capture alone does not establish complete machine history,
idle-gist admission, live-loop publication or a cognitive win.

## The durable controller-source transaction

The implemented, unreleased controller-source boundary turns one retained
collector cut into an ordered, recoverable local transaction. Capture and
`siasourcepublication` first preserve the canonical batch and bind its exact
live transition and projected status effects in `memo.json`. Those markers are
write-ahead recovery authority; they are not acknowledgment or readiness.

An empty successor uses `sia-controller-source-batch-v2` to retain its idle
input in the fixed source slot before adoption. `siacontrolleridle` acquires
selected native history through `siabench.capture_native_history_v2`, binds
the complete controller episode roster and fixes the replay inputs. Recovery
uses those retained inputs without recapture. When no selected source has a
supported native binding, `sialiveidle` records that scoped disposition and
preserves the episodes without inventing native occurrences or gist pages.
The original v1 batch contract remains non-idle.

`siasourceeffects` then consumes only that retained authority. For a non-empty
event closure it publishes the already-sealed page plans, asks
`siasourcegit` for a descriptor-bound clean commit/tree generation, and asks
`siasourceengine` for a receipt-bound pinned-engine generation. The engine
phase admits closed JSON for sync, stale-link extraction, mention extraction,
sync status, and a no-migrate projection of every changed source page. It
requires the requested commit to be the indexed commit, no unembedded chunks
or unacknowledged failures, no remaining stale links, and exact logical page
projection matches. It explicitly records that the projection operation did
not update retrieval bookkeeping or perform operation writes. That is an
operation-level contract, not a byte-for-byte claim about PGLite storage;
opening the engine may maintain its own lock or WAL files. Matching these
witnesses does not establish vector values, retrieval quality, or a cognitive
benchmark win.

For v2, `siasourcegist` reconstructs the exact idle proposal roster and renders
derived pages under `gists/live/`. Publication holds the corpus owner and
destination directory descriptors, checks the complete target roster before
effects, and accepts only absent targets or exact existing bytes. It adds
gist pages without deleting or replacing episodes. The effects transaction
binds event and gist publication together and commits/synchronizes gist
targets even when the event closure is empty. Its pending and committed v2
receipts retain the gist plan, proposal and publication identities; recovery
revalidates them against the captured idle replay. Archived receipt admission
also joins input, state and transition pins to the retained live artifacts.

After graph export, the effects component binds the graph, projected status,
and live candidate in one self-hashed pending record, publishes the live
generation, reopens all retained artifacts, and replaces the pending record
with a committed effects receipt. A batch with neither an event closure nor
gist targets still receives a graph/status/live receipt without inventing a
corpus or engine generation.
At this point the source remains deliberately unacknowledged and readiness is
still closed.

Only `siasourceack` may retire the source. It revalidates the batch, effects
receipt, live generation, admitted status, notification fence, and every
cursor before moving the batch to its immutable digest-named archive. It then
settles recorded refusals, publishes journal cursors in their declared order,
publishes the main cursor, and finally replaces all pending authorities with a
compact committed marker plus the ready receipt. Each durable prefix accepts
only the exact before or target generation on replay; a third state, changed
artifact, partial join, or unsafe pathname refuses instead of rebasing.

These are concrete component contracts and recovery gates. Their availability
alone does not prove that a particular resident controller invocation used the
whole sequence; that requires an end-to-end front-door run and retained
receipts. The transaction is cooperative same-user coordination, not a
hostile same-user sandbox, source-truth attestation, delivery proof, or
biological-cognition claim.

The implemented, unreleased `sialiveview.read_view` front door holds the corpus
owner and revalidates completed-source authority, its archived effects receipt
and the committed live generation. It returns a separate bounded display
envelope, leaving compatibility status schemas unchanged. The view carries
retained workspace selection reasons, activation, encoding, co-retrieval and
idle/gist dispositions, while omitting corpus bodies and broadcast text.
`sia live [--json]`, `sia status` and `sia think` consume this view. Inspection
does not collect, publish, recompute activation or advance workspace expiry;
its `as_of` clock belongs to the acknowledged pulse. Missing or pending source
completion refuses the view. These interfaces do not establish deployment,
biological cognition or a benchmark win. Controller activation remains an
explicit `mind.controller_source` selection.

## What remains in `bin/sialib.py`

Exact line ranges and file-size headroom are intentionally not duplicated
here because every extraction changes them. Inspect the current file with
`wc -lc bin/sialib.py`; its marketplace size boundary and advance-warning
policy are executable in `tests/test_release.py` as
`test_marketplace_scanned_source_files_fit_the_static_limit` and
`test_marketplace_scanned_sources_keep_headroom_under_the_limit`.

## Release process ownership

`bin/sialifetime.py` is a self-contained release-source helper, not an
installed runtime member or a new runtime rung. Direct install/uninstall
and first-light setup enter the same owner. It snapshots the admitted
helper and Bash script into sealed descriptors. It also admits one source-root
directory descriptor, opens the helper and entry descriptor-relative to that
root, and passes the root directory descriptor to the worker. Release-tree
reads therefore remain on the admitted inode even if the checkout pathname is
rebound; retiring or replacing the source directory cannot replace code or
later snapshot inputs during cleanup. An inherited private,
credential-checked control channel admits the worker; environment flags alone
do not establish ownership.

Before mutation, the worker transfers actual lease descriptors to the
owner. The shared bounded-command runner drains detached descendants
before returning a result. The outer owner separately drains before Bash
cleanup or a deliberate lease handoff. Linux subreaper adoption, stopped
worker observation and pinned process identities let it follow descendants
that leave the original process group without treating one live process
tree snapshot as complete. Repeated cancellation follows the same drainage
path. If termination or observation cannot complete, ownership remains
held instead of reporting successful cleanup.

This is cooperative same-user release coordination, not a hostile-worker
sandbox. The guarantee requires the owner to remain alive: killing that
owner with SIGKILL or OOM is outside the boundary. A malformed control
protocol drains descendants but can bypass Bash rollback; retained stages
and recovery debt must not be described as successful rollback. Missing
required kernel features refuse before launching the mutation worker.

## Why an extraction is a designed change, not a mechanical move

Three verified constraints make a naive "move the code and re-import" wrong:

1. **Tests monkeypatch module globals.** Suites load `sialib` under dynamic
   aliases and patch `STATE`, `CORPUS`, bounds, and path constants on the
   loaded module. Code moved into a child module would read its own globals,
   not the patched ones. The repo documents this hazard at the senses façade
   and in `siasenses.py` itself: *the child never imports sialib, because
   tests intentionally load sialib under dynamic aliases and must not create
   a second copy of that state.*
2. **The sanctioned pattern is the bind/invoke façade.** `siasenses.py` is
   the template: the child receives sialib's namespace through an explicit
   `bind(globals())` and per-call `invoke`, so patched globals keep working
   and there is exactly one copy of mutable state.
3. **The runtime member set has one production authority.**
   `bin/siarelease.py:RUNTIME_LADDER` owns every shipped salt, marker, and
   cumulative member set. `install.sh` and `uninstall.sh` delegate normal
   digesting to that helper, and fenced uninstall authorization delegates its
   mode-zero digest path there too. The authority pins the owned runtime root,
   opens every member relative to that descriptor, enforces the per-member
   byte bound, and revalidates every held member plus the root's named
   generation before returning a digest. A new module still requires a
   deliberate `sia-runtime-vN` rung, `SIA_RELEASE_FILES`, the staging copy
   loop, and test fixtures, but it never requires another executable ladder
   copy. Marker presence selects the newest applicable rung even for a partial
   tree, so a missing required member refuses instead of validating as an
   older runtime.
   The authority is release-source code, not a member of the runtime it
   authenticates; the uninstaller holds its owner-controlled source descriptor
   across plugin archival so the final runtime check neither becomes circular
   nor loses its helper midway through removal.

## Extraction progress

**v1.6.0 — DONE: the exports lane → `bin/siagraph.py`.** Four extraction maps
were run in parallel before cutting anything; the exports lane scored
decisively cleanest (one contiguous ~1,000-line block, 26 functions reachable
from four entry points, only 8 names referenced from 14 parent functions, no
import-time execution beyond constants, one exception class that stays
parent-owned), so it led rather than the originally guessed generated-entry recovery
cluster. The move used the exact `siasenses` bind/invoke façade, added a
`sia-runtime-v5` member set to the then-four digest routines (now consolidated
in `siarelease.py`) and the installer/test file lists, and required no change
to the graph/domain test suites — the façade keeps every `sialib.<name>`
working and mirrors test monkeypatches. `sialib.py`
dropped from 517 KB to 477 KB; the 857-test suite and a façade-identity smoke
(delegates resolve, `GraphProjectionPending` is one shared class across the
boundary, `except sialib.X` catches a `siagraph` raise) are green.

**v1.7.5 — the façade contract stopped being a convention.** An outside
review of the v1.5.2…v1.6.0 diff found no HIGH and no MEDIUM, and named three
properties the extraction relied on that nothing enforced. Each now has a
test: the exact export set and count of every façade child (so a future
extraction that drops a name fails on a readable number rather than silently
un-publishing a sialib delegate); the then-four rung ladders pinned as one text
plus behavioural proof that a partial v5 tree still classifies as v5 at every
site; and the three branches of `bind()`, including the delegate-marked
branch that keeps a child's intra-module calls on its own raw implementations
rather than on the parent façade. Which modules are façade children is now
discovered rather than hand-listed, so the next extraction is pinned the
moment it captures its own exports, and adding one dict entry to
`FACADE_CHILD_EXPORTS` inherits every guard above.

**Current — the runtime ladder is an API, not synchronized prose.** Release
tests now pin each historical rung with an independent member fixture and
golden digest, reject ladder declarations in either shell script, exercise the
normal and fenced consumers through the helper CLI, and cover the current v10
uninstall fence member by member. A separate descriptor-lifetime regression
archives the helper's containing plugin directory before the final digest and
proves the held authority remains usable and is then closed.

The cumulative `sia-runtime-v10` member set adds the claim registry, idle
input/disposition, live view and gist publication modules to v9. Its exact
members and selectors are declared in `bin/siarelease.py:RUNTIME_LADDER`.
The receipt reader continues to recognize complete historical v1–v9 trees.
Presence of any v10 selector chooses v10 even for an incomplete tree; a
missing peer refuses instead of validating the tree under an older salt.

**Implemented (unreleased) — generated-entry/epoch materialization and recovery are
child-owned.**
The initial extraction left its context managers and a duplicate directory
ABI in `sialib`; the completed boundary removes both exceptions. `siathought`
declares its context exports explicitly, and `invoke()` returns a one-shot
proxy that binds the owning `sialib` namespace under the shared lock while
constructing/entering the real manager and binds it again while exiting. The
lock is deliberately released across caller code, so another dynamically
loaded `sialib` alias can run without deadlock while each suspended generator
still resumes against its own `STATE`, patches, and helper identities. The
proxy returns the wrapped `__exit__` result unchanged, preserving exception
suppression.

The legacy directory reader now consumes the existing generic `_SOURCE_LIBC`
ABI through `bind()`; no generated-entry-specific ctypes class, handle, or patch seam
remains in `sialib`. Existing callers retain the same
`sialib._thought_legacy_catalog()` and
`sialib._thought_mind_replay_catalog()` spellings because the ordinary
delegate publication loop exports them from the child. Release tests pin the
context set, ownership, import surface, per-phase rebinding, suppression, and
single ABI source; `tests/test_thought_recovery.py` remains the behavior gate.

The epoch lifecycle shares this durable memory-page owner: completeness
manifests, bounded consolidation scan/claims, rendering, and the originating
recovery marker move together.
Event-day admission and occurrence indexing share this owner.
Generic corpus publication and scheduled-maintenance orchestration remain core services
(`DREAM` is the compatibility ledger/action name).
Bounds, regular expressions and consolidation exception classes remain
parent-owned, so calls through each dynamically loaded core preserve its
patched dependencies and catch the same exception identity. The ordinary
export loop publishes the moved helpers; no context export or runtime member
changes. `tests/test_epoch_module_ownership.py` checks ownership and real
cross-alias calls, while the existing epoch and scheduled-maintenance behavior tests remain
unchanged. The release export tuple adds the moved functions so the same
exact-set and binding guards cover the expanded child.

The event-day appender and `_prepare_event_page_plan` use the same
`_plan_event_day_update` assignment pass. The new planner retains its
accepted rendered images, original page bytes and complete bounded read
dependencies, including absence witnesses and directory membership where
occurrence lookup requires them. Planning does not publish pages or clean
legacy staging entries. The existing `update_day_page` signature, return
triple and admitted Event objects remain compatible.

`_publish_event_page_plan` consumes the independently pinned original plan
without rerendering. It permits only exact original sources or declared
target images on retry; unrelated dependency changes refuse. Original
event-entry content and order remain bound, while title/count/timeline
regeneration does not preserve the entire old page as a literal prefix.
A failed publication can leave a retained target prefix, and its retry
preserves the original append/admission roster rather than claiming the
retry performed those appends.

`_compose_event_page_plans` admits complete day plans from one unchanged
original cut, preserving each member and its independently supplied pin.
The batch binds the compatible union of read dependencies and exact write
order; write/write and write/retained-page conflicts refuse rather than
reassigning events. Complete member documents, source-event counts and the
combined lookup roster retain their existing aggregate ceilings.
`_publish_event_page_plan_batch` validates all members before page effects
and uses the same guarded write engine as individual publication. Its
shared before-images preserve each member's original reads after a partial
write. Retry consumes the original sealed batch, never recomposition or
rerendering, and permits only its declared target and ancestor deltas.
`tests/test_event_page_batch.py` exercises this additional boundary.

The cross-organ closure is implemented and unreleased. Its
`_compose_event_page_batch_closure` contract admits one
original cross-organ cut while retaining complete original one-organ batches
and their independent pins. Only the additional dependency and effect union
is deduplicated; original per-organ fields and quota checks stay unchanged.
`_publish_event_page_batch_closure` uses one shared original-before view and
prefix publisher, so a declared sibling organ under an originally absent
ancestor is not mistaken for an unrelated mutation. Retry consumes the
sealed closure, never a new plan or batch.

The complete closure request, retained output and source-event roster share
the existing ceilings. Aggregate lookup-page and directory-entry rosters
use full relative paths and include declared targets and ancestor additions.
They are admitted roster bounds, not a cumulative syscall or inspection-work
counter; retained-byte accounting remains a separate constraint.
`tests/test_event_page_closure.py` covers this page-byte-only boundary.
It grants no source acknowledgment, live-state publication or readiness.

These lazy core wrappers hold the real reentrant corpus owner across all
reads, copies, writes and final checks. `siaeventplan` receives the explicit
owning namespace and introduces no separate binding lock. Result copying
and serialization finish before the final descriptor/hash checks and
complete no-hash named-path sweep. `tests/test_event_page_plan.py` exercises
the exact-byte, lease, retained-origin, dependency and interrupted-retry
boundaries. Page-byte publication is not live-loop admission, corpus/index
synchronization, cursor acknowledgment or readiness. Complete source-batch,
live-transition and status/memo admission remains a separate integration
requirement. The durable controller-source transaction described above is the
component boundary that joins those effects; calling these private page
helpers alone does not enable or prove a resident live loop.

The separate `_prepare_event_live_intake` boundary projects complete,
caller-supplied collector returns through independently pinned original
page batches into the closed live-intake schema. Its lazy `siaeventintake`
module receives the explicit core namespace but does not acquire a corpus lease
or read current source/configuration files. Selection, catalog, counting
profile and the complete live policy are explicit and fixed for the epoch.
Every declared collector appears, including empty returns; disabled or
ambiguous selections refuse rather than disappearing from that roster.

All return locations and duplicate plan inputs remain attributable.
Observations deduplicate only the declared epoch/source/Event association,
retaining its first controller clock, page version and native timestamp
metadata. Complete before and target page versions stay in version history;
current-version replacement requires the exact previously current bytes.
No observation or use is invented for before-images, and existing uses do
not transfer to a new version. Native stat integers and floating policy
values retain their separate admission domains within the complete byte cap.
The bridge supplies observations, not novelty decisions or typed uses.

Retained-page native grammar is checked against supplied exact bytes;
retained-epoch index bytes are absent from the plan, so their semantic and
index provenance remains inherited from its independent pin rather than
replayed here. Page-byte digests never stand in for whole native-capture
digests. The output retains upstream nonclaims and is prepared, not
published. It establishes neither collector execution, effective config,
source freshness, cursor/acknowledgment ordering nor a held-out cognitive
win. `tests/test_event_live_intake.py` covers this boundary. The durable
controller-source transaction may consume the bound result, but this pure
intake helper alone performs no publication, acknowledgment, or readiness
transition.

The separate `sialivegist.bind_replay_gist` contract binds a complete native
capture and the unchanged replay-gist result to every supplied live
observation. Supported native episodes require the exact normalized source
record, signed-occurrence identity, and unambiguous full marker/excerpt in
both the original observation version and the current captured page.
Their page-byte hashes may differ after an append; neither becomes the
whole capture hash. Missing required native witnesses refuse rather than
producing an empty success. Valid unsupported source/grammar dispositions
and complete ineligible cues remain distinct outcomes.

All native alternatives remain in the complete capture, replay artifact
and support roster. Unobserved alternatives are labeled fresh-capture-only:
they may support attributed gist content but create no controller
observations, encodings, retrievals or uses. Only existing learned
selections for replay-touched eligible cues become live proposals; every
candidate decision and the static control remain inspectable. The binder
retains its full raw inputs and upstream nonclaims. Its complete binder output
reservation reuses the original gist preflight calculation and accounts
for nested escaping and repeated documents before learning, without
changing existing artifact fields or limits.

The explicit v2 idle wrapper must match its complete policy, intake, epoch
and outer pulse clock. The v2 pulse also reserves its known repeated input
documents and binding before current or prior-state reconstruction. This is
not a complete advance bound for dynamic component traces or proposed gist
pages; component limits and complete final-output checks remain required.
The old v1 capture-hash gate remains unchanged;
there is no fallback between the contracts. These are pure prepared
proposals, not durable consolidation, publication, delivery or a cognitive
win. The eventual runtime must retain or revalidate fresh source
generations through publication; supplied-record correspondence does not
itself prove collector execution, authenticity, freshness or acknowledgment.
`tests/test_live_gist_binding.py` covers this separate boundary.

The separate delivery-input construction is implemented but not connected to
resident recall or source successors. `siacontrollerdeliveryinput.bind`
requires a complete inspected epoch, actual supplied parent state, cumulative
intake, policy, clock and independent pins. It preserves the committed
delivery prefix byte-for-byte, appending new inspected records only when
they bind that parent and its retained versions. Equal completion clocks do
not reorder previously consumed identities. Incomplete output, missing
history or substituted content/origin refuses; the result is
`bound-not-consumed`, not a publication or acknowledgment.

`siadelivery.hold_deliveries` holds the existing private directory lock and
all inspected record descriptors through caller computation. Its `read()`
returns the unchanged detached journal-v1 inspection; `current()` checks the
whole held roster. Normal context exit revalidates, all exits retire the
handle and close owned descriptors, and a caller exception remains its own
exception. The legacy one-shot inspector delegates to the same reader.
The additive `directory_identity()` accessor returns detached native
`dev`, `ino`, `mode`, `uid` and `gid` observations for the held directory,
bracketed by complete snapshot checks. It preserves journal-v1 read bytes
and does not turn a matching directory into adoption or writer authority.
Neither path creates missing journal directories or repairs pending output.
Source authority, journal adoption and the successor WAL cut still belong
to the separate outer integration. The inspection retains completion records,
not complete rank intents: it does not independently reproduce historical
ranking, prove human receipt/use, or establish a cognitive benchmark win.

`siacontrollerdeliveryepoch.prepare_epoch` now prepares source-bound journal
storage separately from capture and output authorization. It requires an
actually acknowledged legacy parent with empty deliveries, or exact retained
adoption authority; caller hashes alone cannot bootstrap missing history.
An immutable birth document binds the stable predecessor, epoch, policy and
limits. A pending memo marker precedes records-directory creation; a separate
adoption receipt pins the directory identity before the adopted memo marker.
Retries preserve exact documents and directory identity. Every derived path
and complete output reservation is checked before storage creation, and
interrupted directory/memo publication is persisted through held parent
descriptors before later effects depend on it. Missing adopted storage,
changed parents, pending successor WAL or pre-v3 deliveries refuse without
repair. The result is `adopted-not-enabled`: it emits no output, samples no
clock and does not consume a delivery or acknowledge a source batch.

This component is tested source construction, not a resident hook or an
installed runtime-ladder member. Existing source readers still reject v3.
The pending integration must retain adoption and journal descriptors through
capture, close that read-only interval before publishing the successor WAL,
and retain the outer corpus lease across both. A fully acknowledged source-v3
batch must independently retain the adoption before writers can be enabled.
Neither an adopted memo alone nor a successful storage test establishes a
cognitive mechanism win, durable output delivery or human receipt.

**Unscheduled — the cursors lane** remains last, because it is the substrate the
already-extracted `siasenses` child calls ~95× through the bound namespace;
extracting it adds a second delegate hop in the pulse hot path, so it moves
only under a dedicated performance and upgrade/rollback plan.

Each extraction ships as its own release with nothing else in it, gated by the
full suite and the real-gbrain contract lane. The longer-term sizing target is
`sialib.py` < 400 KB; no release is assigned to that target.

## The boundary that actually bit

Both shipped defects (issues #2 and #3) lived at the SIA↔gbrain subprocess
seam, and every unit test stubs that seam. The rule going forward: **any new
gbrain invocation shape must land with a probe in
`tests/test_gbrain_contract.py`**, which runs the real pinned binary locally
(when the toolchain is installed, or via `SIA_GBRAIN_BIN`) and in CI (which
builds the exact pin). A skip in that lane states that nothing was proven;
it is never a pass.
