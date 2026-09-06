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
| `bin/siatakes.py` | predictions, judge, grading, calibration |
| `bin/siacapsule.py` | continuity capsules, freeze/thaw, restore |
| `bin/siabackup.py` | repository adapters and scheduled verification |
| `bin/siabench.py` | signed-ledger QA benchmark |
| `bin/siamind.py` | usage salience, co-return reinforcement, PPR rerank, stability |
| `bin/siaqueue.py` | agent note queue |
| `bin/siarestoreadmit.py` | restore admission |
| `bin/siarelease.py` | release checks and runtime-receipt authority |

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
normal and fenced consumers through the helper CLI, and cover the current v6
uninstall fence member by member. A separate descriptor-lifetime regression
archives the helper's containing plugin directory before the final digest and
proves the held authority remains usable and is then closed.

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

These lazy core wrappers hold the real reentrant corpus owner across all
reads, copies, writes and final checks. `siaeventplan` receives the explicit
owning namespace and introduces no separate binding lock. Result copying
and serialization finish before the final descriptor/hash checks and
complete no-hash named-path sweep. `tests/test_event_page_plan.py` exercises
the exact-byte, lease, retained-origin, dependency and interrupted-retry
boundaries. Page-byte publication is not live-loop admission, corpus/index
synchronization, cursor acknowledgment or readiness. Complete source-batch,
live-transition and status/memo admission remains a separate integration
requirement; these private helpers do not enable a resident live loop.

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
