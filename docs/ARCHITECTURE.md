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
| `bin/siacontrollercandidate.py` | retained-source candidate preparation under the explicit caller's owner scopes (implemented, unreleased) |
| `bin/siasourceeffects.py` | crash-recoverable corpus/index/graph/status/live effects publication and committed receipt (implemented, unreleased) |
| `bin/siasourcegit.py` | descriptor-bound clean corpus Git generation (implemented, unreleased) |
| `bin/siasourceengine.py` | receipt-bound pinned-engine sync and source-page projection readback (implemented, unreleased) |
| `bin/siasourceack.py` | immutable batch archival, refusal settlement, cursor publication, and final readiness acknowledgment (implemented, unreleased) |
| `bin/siacontrollerdeliverywrapper.py` | storage-free held-parent and journal binding for successor input (implemented, unreleased) |
| `bin/siacontrollerdeliverywriter.py` | source-authorized output under a held adopted journal (implemented, unreleased) |
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

`siacontrollercandidate.prepare(owner, *, memo, admitted_status)` contains the
retained-batch-to-candidate algorithm. The existing
`_prepare_controller_source_live_candidate` facade keeps its keyword-only
contract and holds brainstem and corpus ownership around the complete ordinary
child call. The child uses the supplied resident namespace for callbacks,
paths and copying; it does not import a canonical core or return a suspended
context manager. Parent admission, pure replay and detached-copy checks remain
inside that lifetime. Extraction does not collect, publish, acknowledge or
activate an additional source cycle.

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
phase admits closed JSON for no-embed sync, stale-link extraction, mention
extraction, sync status, and a no-migrate projection of every changed source
page; the sync envelope must report zero inline embeddings. It runs
source-scoped stale embedding as an explicit process between
sync and extraction; the bounded human output is retained only by digest and
the later closed status document is its authority-bearing zero-unembedded
postcondition. This avoids treating the pinned engine's two-document
`sync --json` cost-gate stream as one result. Mention extraction admits either
one closed summary or the pinned extractor's exact `no_gazetteer` JSONL prelude
followed by an all-zero closed summary; every other multi-document stream is
refused. It emits a v4 generation that
binds those embed-stream digests plus the installed overlay digest and
post-overlay tree OID in addition to the source commit, lockfile, pin,
receipts and ELF; the effects reader retains explicit v2 and v3 admission for
historical generations rather than relabeling them. It
requires the requested commit to be the indexed commit, no unembedded chunks
or unacknowledged failures, no remaining stale links, and exact logical page
projection matches. It explicitly records that the projection operation did
not update retrieval bookkeeping or perform operation writes. That is an
operation-level contract, not a byte-for-byte claim about PGLite storage;
opening the engine may maintain its own lock or WAL files. Matching these
witnesses does not establish vector values, retrieval quality, or a cognitive
benchmark win.

Source effects use the complete graph-publication runner, not a single bounded
scan step. If a ready graph roster's retained page digest differs from the
current no-follow page read, graph export publishes only a partial diagnostic,
durably replaces the stale roster with a fresh scan generation, and the runner
drains that generation before source effects may continue. This also recovers
an interrupted corpus writer whose ordinary pre-write invalidation did not
survive to the later graph phase.

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

The additive `siasourceack.read_capturable_predecessor` observes that
historical predecessor after notification collection opens its acquisition
fence. It requires the actual complete memo, an independently supplied
compact predecessor and the exact marker with its independent digest. It
revalidates source/effects archives and actual status/graph/live publication,
holding their descriptors through full-result detachment. Its aggregate
retained-wire budget includes the request, held artifact bodies and result;
it is not a process-memory measurement. The distinct `capturable-not-ready`
result grants no readiness, acknowledgment, capture or writer authority.
Ordinary completed reads and ACK still reject the fenced state. An unrelated
fixed successor slot is neither interpreted nor adopted by this historical
reader; the separate capture/retention boundary must admit that slot.

The additive `retain_capturable_successor` and
`recover_capturable_successor` provide that separate storage boundary. Both
require the reserved sequence, admitted status, retained predecessor,
compact commit and independently pinned notification marker. They hold the
actual memo, status, graph, live artifacts and source/effects archives across
the write, and bind publication to held destination directory descriptors.
Retention leaves the full fenced memo unchanged; exact WAL retries preserve
its inode and replay its parent-directory durability barrier. Recovery
adopts only those validated bytes, replacing historical completion/readiness
with the existing pending receipt while preserving the marker. An absent
slot returns false; another pending authority or unrelated WAL refuses.
Legacy completed storage entrypoints remain strict. The complete request,
held bodies, capture view, successor and prospective memo representations
share a pre-effect wire budget; it does not measure process memory. These
entrypoints neither collect sources nor create a writer permit, and do not
reinterpret an already-pending memo as a completed predecessor.

An already-pending `recover_orphan` retry separately validates the exact
receipt and WAL, then flushes the held memo parent without rewriting either
file. This closes an interruption after pending-memo replacement but before
its directory barrier. It rechecks caller input and retained paths after the
flush and propagates failure; `read_pending` remains a non-repairing read.

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
   In v13 the authority and uninstaller are also installed runtime members.
   The stable launcher routes the exact `sia uninstall [--purge]` grammar to
   the flat-runtime lifetime mode before acquiring an ordinary shared launch
   lease. That mode seals the installed lifetime authority and uninstaller,
   then takes the exclusive release lease. The uninstaller holds its
   owner-controlled release-authority descriptor across plugin archival, so
   the final runtime check neither becomes circular nor loses its helper
   midway through removal.

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
normal and fenced consumers through the helper CLI, and cover the current v12
uninstall fence member by member. A separate descriptor-lifetime regression
archives the helper's containing plugin directory before the final digest and
proves the held authority remains usable and is then closed. The v13 closure
tests additionally prove the installed launcher reaches teardown before the
shared lease, rejects any grammar beyond optional `--purge`, scrubs ambient
release capabilities, and refuses a flat-runtime install entry.

The cumulative `sia-runtime-v13` member set adds `sialifetime.py` and
`uninstall.sh` to v12. The v12 set added the source-bound writer,
installed-engine and GET/render admission boundaries, expectations observer,
held recall projection, output compositor and CLI compositor to v11. The v11
rung added candidate preparation and the epoch, input, wrapper and journal
dependencies used by native source-v3 continuation to v10. The v10 rung added
the claim registry, idle input/disposition, live view and gist publication
modules to v9. The current rung's exact
members and selectors are declared in `bin/siarelease.py:RUNTIME_LADDER`.
The receipt reader continues to recognize complete historical trees.
Presence of any v13 selector chooses v13 even for an incomplete tree; a
missing peer refuses instead of validating the tree under an older salt.
This is unreleased packaging closure, not deployment, output activation,
automatic journal adoption, or a benchmark win. Every repository-local
import, including lazy imports, remains
subject to the unchanged transitive runtime-closure gate.

The resident brainstem separately observes the canonical, owner-controlled
Omarchy plugin manifest at startup and before each pulse. Missing or unsafe
registration causes the systemd intentional-stop exit before another pulse is
reserved; the halt remains ledger-visible and the log names `sia uninstall`.

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

The delivery-input binder is used by native v3 source capture; resident
recall dispatch remains separate construction. `siacontrollerdeliveryinput.bind`
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

`siadelivery.hold_delivery_writer` adds a mutable lifetime around one existing
private journal lock. Its mandatory native directory identity stays outside
live JSON arithmetic; an explicit outer-authority callback must return None
or raise. The callback is checked around record publication, writes, flush
and completion clock acquisition. Each exact own addition admits a fresh
complete roster while retaining the old file identities; other roster or
record changes refuse. Publication passes the held destination descriptor
to the existing fixed publisher, before staging or leaf effects.

The held writer is not source-v3 writer authorization: the caller must still
hold and validate the acknowledged source, original adoption and complete
live generation. It neither creates a journal nor reconstructs missing uses.
Read/reserve/deliver preserve the existing v1 record contracts. Completed
retries do not emit or sample a clock; interrupted attempts remain unknown.
A failed mutable call retires its handle, so durable retry reopens actual
records. Normal exit revalidates, exceptional exit preserves the caller's
exception, and only owned descriptors close. No episode or journal is deleted.

`siacontrollerdeliverywriter.deliver` supplies the separate source-v3 writer
authorization. Mandatory caller pins select the original adoption and
journal limits; the actual acknowledged source, full live generation and
absent successor WAL are checked under corpus ownership before the existing
journal writer is acquired. It never acquires the brainstem lease, prepares
an adoption, captures sources or acknowledges a pulse. It admits
caller-supplied rows and rendered body as premises, ranks against that actual
generation without changing row content/origin, and preserves the original
request identity and rank clock on exact completed retry.

The returned unchanged journal receipt means `write-all-and-flush-returned`
at the supplied binary sink. Its body scope remains
`result-body-before-queue-health-footer-v1`; it does not cover the health
footer, human reading, understanding or downstream use.
Incomplete journals, including intent-only prefixes, refuse this entry
without filtering or reconstructing missing output. A retained-clock ceiling
admits the complete journal prefix only; it is not a fresh clock or freshness
claim.

Copies are checked while journal/epoch descriptors remain held. After their
normal exits, callback-free checks compare the retained in-memory request,
selected owner identities and returned completion; no path is reacquired
and no fresh filesystem authority is claimed after release. Once a real
completion has returned, later wrapper refusal retains the conservative
`completed-unrecorded` output phase even if a fresh retry handle reports
`not-started`. That refusal does not erase the durable completion or permit
a resend. This front door does not enable CLI recall or validate the semantic
faithfulness of arbitrary rendered prose.

`siacontrollerdeliverywriter.render_and_deliver` adds callback rendering to
the same transaction without changing the original `deliver` contract.
Its mandatory `sia-controller-delivery-render-config-v1` configuration is
bound by `expected_render_config_sha256`. The `rank-prefix-v1` selection
requires exactly the available prefix selected by `display_limit` from
one actual held rank;
the configured body ceiling cannot exceed the admitted journal/live limits.
The callback receives detached rank/config values and their expected hashes,
then returns exactly `emitted_row_refs` and UTF-8 `output_utf8` bytes. It may
not alter its rank/config inputs. Admission, ranking, rendering, reservation,
write-all and flush all occur within the same corpus/epoch/journal lifetime;
the public premised-body writer is not called again and no second rank or
source acquisition is used between those stages.

Byte limits and the complete represented-wire budget are checked before
intent publication. Callback inputs and output references/bytes stay pinned
through output and normal ownership exits. The renderer is an explicit
caller operation, not a sandbox: there is
no semantic fidelity claim for arbitrary callback prose, and independent
callback side effects are not journaled. Body scope still excludes the
health footer. The controlled test renders a genuine same-origin activation
order change without changing source content/origin; this is not a cognitive
benchmark result. Configured activation and
exact front-door CLI version joins remain separate.

The controlled output-to-resident fixture carries a real short-write/flush
completion through the next native source-v3 capture, publication and ACK.
The new full generation and history retain the exact delivery and derived
service-output use, preserving its subject's content/source hashes and
origin. The original adoption and journal records are unchanged. Rows/body
remain caller premises and Git/index observations remain controlled; this
does not establish a deployed CLI loop or a cognitive retrieval win.

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

The separate `hold_epoch` reader requires existing adoption storage and a
nonnull independent pin. It first checks the core's entered corpus scope
and its live private descriptor against the named lease, without acquiring
one; raw inherited descriptors must first enter the ordinary core scope.
Within that caller-owned lease it
retains the source, status, memo and adoption descriptors, exact full parent
generation and records-directory identity. Its detached
`held-not-consumed` view revalidates on reads and normal context exit;
exceptional exit preserves the caller error and retires the handle before
closing owned descriptors. It never requests the resident brainstem lease
or creates, flushes, publishes or repairs epoch storage. A no-fsync
observation cannot replace preparation's interrupted-write recovery. The
journal is acquired separately and its held directory identity must be
joined to adoption before capture uses any records.

The additive `hold_capturable_epoch` uses the same immutable storage lifetime
after collection opens a notification-baseline fence. Its separate required
marker and digest are joined through `read_capturable_predecessor` to the
full actual memo; the view is `held-capturable-not-ready`, not a completed
state. Ordinary preparation and `hold_epoch` still require completion.
Neither held reader refreshes its memo or repairs storage. Capture must
acquire the appropriate hold after the collector's legal memo change, and
the fixed successor slot must remain absent throughout its lifetime.

`siacontrollerdeliverywrapper.build` retains that complete detached held
view, independently pinned adoption, complete journal and the replayed
delivery binding in a closed source-native envelope. Its matching
`validate` replays the entire binding with the supplied successor epoch,
projection, clock and notification context. Native directory identities
remain native integers; the outer envelope/view, birth/adoption and live
documents keep their distinct existing hash domains. The whole represented
request is bounded before copies or binding, and final detachment rechecks
the original request and owner basis. Neither function opens storage,
samples a clock, acknowledges a source or enables output.

This pure wrapper validates represented joins, not actual authority. Full
source-to-projection replay still belongs to source validation. The WAL
validator compares the declared parent schema and entire compact completion
to the actual retained predecessor, including its effects-receipt pin.
A v3 predecessor requires a v3 successor with the same independently
retained adoption pin; resealed legacy omissions or adoption rebasing refuse.
The live adapter compares its full parent generation to the independently
supplied generation. Matching only a state digest is insufficient.
A represented later-v3 continuation retains the original pinned adoption,
not a rebased birth. An empty legacy bootstrap journal proves no nonempty
delivery consumption or an end-to-end resident source-v3 loop.

`siasourcebatch.capture_successor_v3` is the additive acquisition front door.
It requires the full admitted status and completed source parent, journal
limits and independent adoption pin. A genuine epoch preflight precedes
collection. The shared collector then runs once; only its existing successful
notification marker/memo refresh can update that request's memo authority.
Final epoch and journal holds span wrapper construction, full batch hashing,
retained validation and detachment. They close before the last source named
sweep. The resulting v3 batch preserves the original source origins and v2
idle/gist contract and adds the complete delivery wrapper. Pure retained
validation never reopens the journal or reacquires current sources. Legacy
successor capture refuses a v3 predecessor rather than discarding its journal.

`siacontrollerliveinput.prepare_inputs_v3` separately requires the full
parent generation and its independent pin. It replays the real source gate,
compares the entire parent to the wrapper's retained generation and returns
the exact live preparation request with the complete bound delivery prefix.
It performs no storage I/O, acquisition or pulse execution. The legacy
adapter continues to refuse delivery-bearing input, including null members.

Resident candidate preparation dispatches v3 with the complete generation
returned by its actual reader and the memo's independently admitted receipt
pin. It never falls back to the wrapper's copy when current authority is
missing. Pure status replay uses the retained generation and a separately
supplied live-marker pin as represented premises only. Durable status handoff
independently joins the freshly read entire generation to the frozen batch
at its existing admission, retry and publication boundaries.

Source v3 shares the existing v2 content-effects format, including the
explicit gist disposition and content identity on nonidle pulses. Native
idle/gist publication, pending recovery and completed retry retain those
same receipt fields; the full source hash also binds the delivery wrapper.
Effects completion is still not acknowledgment or output authority.

The additive `_run_controller_source_transaction_v3` owning entry invokes
`siacontrollersourcerunner.run_v3` under continuous brainstem and corpus
leases. Every request supplies journal limits, their pin, the original
adoption pin, an initial-operation callback and a controller clock. Only
actually unadopted legacy completion permits a null adoption pin; existing
adoption must match the caller's independent pin. Initial/pending delegation
can still finish a legacy transaction without relabeling its source schema.
A retained source-v3 WAL is admitted and recovered before another sequence,
clock, epoch preparation or native collection. Without a WAL the runner
prepares or observes the actual adopted epoch, reserves the sequence,
captures native v3 input and retains it before publication and ACK.

One narrower recovery state is intentionally not replayed into a changed
meaning. If a batch is retained but no live binding or downstream effect has
started, and its embedded live-policy pin differs from the checked-in policy,
the v3 runner invokes the source-publication supersession transaction. That
transaction atomically moves the unchanged batch to the private
`controller-source-superseded/` archive, publishes a deterministic
`preserved-not-published` receipt, and replaces the memo last. Each durability
cut is retryable. It never acknowledges a cursor, publishes content, mutates
origin, or treats old bytes as input to the replacement policy; fresh capture
begins only after the old evidence is durably retained.

The original resident fixtures now complete legacy-to-v3 and v3-to-v3
cycles, including actual interruption/retry beneath a notification fence.
Their journal remains empty and their Git/index observations remain
controlled; they prove neither nonempty delivery consumption nor external
engine behavior. The configured resident cycle enters v3 with the existing
closed journal limits and selects an existing original adoption only from the
persisted epoch marker while holding brainstem and corpus ownership. The v3
runner still validates the actual epoch and source storage independently.
This code route does not itself edit configuration, start a service, enable a
writer or extend the installed runtime ladder. Publication retains the outer
corpus lease across capture and fixed-slot retention.

After live publication, a retired status handoff is represented by matching
source, binding, effects and compact live receipt identities. The dispatcher
selects recovery from those joins; actual effects replay and source ACK
still validate the retained artifacts. Idle effects replay uses the retained
batch's observation clock, not a new clock or the wrapper's self-declaration.
Historical graph/status snapshots created before private publication may be
exact owner-held single-link files at mode `0644`. The source-effects boundary
has one explicit migration lane for those two inputs: it reseals the same
descriptor to `0600`, proves the named inode and bytes did not change, and
refuses every other mode. Both publishers now request `0600` explicitly;
candidate and generation files never enter the migration lane.
An empty closure/gist disposition still publishes graph/status/live state
and ACK, while its receipt retains null corpus/index generations.
A fully acknowledged source-v3 batch must independently retain the adoption
before writers can be enabled.
Neither an adopted memo alone nor a successful storage test establishes a
cognitive mechanism win, durable output delivery or human receipt.
Notification collection can create a pending acquisition fence in the memo;
the completed reader deliberately rejects that state. The distinct
capture-only source reader above now supplies historical predecessor
admission for the capture-held epoch. Its separate fenced successor storage
path and resident dispatch are implemented above. Source-bound writer
authorization uses the separate strict front door above. Operator opt-in and
fresh resident observation remain separate activation work, not a relaxed
completed/readiness or writer gate.

`siainstalledexpectations.observe_installed_expectations` supplies the
additive, unreleased local-selection input to the installed-engine boundary.
While the real corpus owner is held, it opens the selected pin, managed pin
receipt, overlay runtime receipt and ELF through no-follow descriptor chains;
requires their installed path, source, fields, digests and artifact generations
to agree; and returns a detached
`sia-installed-overlay-engine-expectations-v1` document plus its digest. It
does not run the engine, read the index, observe a clock, produce output or
authorize cognition. This is exact local receipt/artifact consistency, not
independently authenticated build provenance: a hostile same-user process
that coherently replaces every local file remains outside the claim.

`siainstalledengine.hold_overlay_engine` supplies an additive, unreleased
installed-artifact lifetime for explicit version, ordinary GET and singleton
render-projection calls. The caller must already hold the actual corpus
lease and supply complete `sia-installed-overlay-engine-expectations-v1`
expectations, their independent `expected_expectations_sha256`, and an
`authority_current` callback. Expected source commit, lockfile, overlay and
artifact hashes are caller authority; a receipt cannot select its own expected runtime.
Actual managed pin/receipt files and the ELF executable are held and checked
against those expectations under real corpus and engine ownership. This is
not source ACK, index freshness or controller readiness by itself.

The opaque handle exposes `read`, `current`, `version(timeout=...)`,
`get(subject=..., timeout=...)` and `project(...)`. The exact internal helper
`_run_installed_gbrain` executes the held descriptor-backed executable through
SIA's bounded process provider; its literal argv sites remain visible to the
unchanged real-gbrain coverage scanner. The original executable, corpus and
owner descriptors remain held across execution and returned-copy checks.
Own descriptors close on normal and exceptional exits; borrowed caller
leases are not closed. A failed handle retires without automatic repair or
retry. Caller exceptions survive cleanup failures.

Ordinary `get` fixes its argv to `get <subject> --source sia`, admits a
canonical bounded subject and requires an explicit timeout. It creates no
projection request scratch and does not pass `--no-migrate`. Its separately
named `sia-installed-overlay-engine-get-transport-v1` result has status
`captured-unadmitted-get`, exact subject/request/binding pins and unmodified
strict-UTF-8 stdout/stderr with their byte digests. `GET_NON_CLAIMS` and
`InstalledEngineGetRefusal` retain the ordinary-GET boundary through later
currentness and normal-exit failures. Connection migrations and retrieval
bookkeeping may occur; the GET transport makes no no-write assertion and
does not establish whether either effect occurred. Captured output is not
source-version admission, displayed-field admission or output delivery.

`siacontrollerrecallcli.recall_from_current_source` supplies the additive,
unreleased front-door composition immediately below future CLI routing. Its
caller can select only a canonical subject, bounded timeout, request identity,
binary sink and completion clock. Under the corpus owner it derives the
acknowledged source-v3 batch and committed live generation, the persisted
delivery adoption, closed journal limits, singleton literal render policy and
the installed-engine expectations observation above, then passes those exact
inputs to `siacontrollerrecalloutput.recall_and_deliver`. It accepts no
caller-authored source, epoch, engine, rank or rendering authority and has no
legacy GET fallback. This module does not itself alter configuration, route
`sia recall`, install a runtime, queue reinforcement or establish a held-out
cognitive win.

Host-bound GET additionally requires literal `GBRAIN_BRAIN_ID=host` in the
sterile child environment; `GBRAIN_HOME` alone is not brain selection. The
fixed-host correction is a prerequisite for that claim, not a caller-selectable
brain override. It fixes the brain axis without constraining trusted host
backend configuration, remote URL/thin-client routing or ordinary GET's
migration/bookkeeping behavior. Configured activation remains separate.

Projection accepts only `get_page_render_projection`, bounded strict-UTF-8
request bytes, their independent digest and an explicit timeout. Its params
transport is an identity-bound regular leaf in a held private directory,
not a kernel-sealed file. The request descriptors remain held across the
process; changed request scratch is retained rather than removed by an
unsafe cleanup. The existing version/projection transport schema, keys and
statuses stay separate from GET; shared projection nonclaims describe only
projection calls, and their exact text participates in the relevant pins.

`captured-unadmitted-projection` deliberately does not authorize displayed
memory: the caller must still validate the actual response and its source
generation. The separately named GET render-projection operation compares
the original full source/version/origin binding, a current source-qualified
page/tag snapshot and the actual engine Markdown serializer. Logical
`contentHash` equality is separate from complete displayed-field equality;
excluded bookkeeping metadata must not disappear from the display check.
Canonical GET Markdown is not raw source-file bytes, and no new source
identity is manufactured to make them equal. This operation performs no
retrieval bookkeeping or application writes; that statement excludes
request scratch, the preceding ordinary GET and storage connection effects.
It is CLI-only, uses the explicit no-migrate params-file route and grants
no JACKAL status or cognitive benchmark result.

These transport and receipt schemas describe the implementation contract,
not an executed test result. Compiling a candidate and reading its version
does not prove its held GET/projection contract. The separately selected
compiled lane in `tests/test_gbrain_contract.py` requires external candidate
expectations and real temporary CLI/engine operations; a skip proves nothing.
Source/display admission, delivery composition and configured activation
remain separate gates. No retained observation is fresh authority after its
descriptor lifetime ends, and this context does not validate later exits of
an enclosing caller-owned scope.

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
