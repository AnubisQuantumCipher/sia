# Runtime architecture and the module map

This file exists because an outside review made a correct observation: the
core module is too large to review, and the project's own ethic — carve a
system into pieces a reader can hold — argues for splitting it. It records
what already lives in sibling modules, what constrains an extraction, and the
sanctioned order for doing it. Volatile measurements belong to the current
source and release checks rather than a second hand-maintained map here.

## What is already split

The runtime is not one file. These lanes were extracted in earlier releases
and are the pattern to follow:

| Module | Lane |
|---|---|
| `bin/siasenses.py` | sensing subsystem (extracted in v1.3.7) |
| `bin/siatakes.py` | predictions, judge, grading, calibration |
| `bin/siacapsule.py` | continuity capsules, freeze/thaw, restore |
| `bin/siabackup.py` | repository adapters and scheduled verification |
| `bin/siabench.py` | signed-ledger QA benchmark |
| `bin/siamind.py` | activation, bonding, PPR rerank, stability |
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
parent-owned), so it led rather than the originally-guessed thought-recovery
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

**v1.6.1 — thought pages + recovery/legacy replay are fully child-owned.**
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
ABI through `bind()`; no thought-specific ctypes class, handle, or patch seam
remains in `sialib`. Existing callers retain the same
`sialib._thought_legacy_catalog()` and
`sialib._thought_mind_replay_catalog()` spellings because the ordinary
delegate publication loop exports them from the child. Release tests pin the
context set, ownership, import surface, per-phase rebinding, suppression, and
single ABI source; `tests/test_thought_recovery.py` remains the behavior gate.

**Then: v1.6.2 — the cursors lane** last, because it is the substrate the
already-extracted `siasenses` child calls ~95× through the bound namespace;
extracting it adds a second delegate hop in the pulse hot path, so it moves
only after two façade extractions have proven under real upgrade/rollback.

Each extraction ships as its own release with nothing else in it, gated by the
full suite and the real-gbrain contract lane. Target: `sialib.py` < 400 KB by
v1.6.2.

## The boundary that actually bit

Both shipped defects (issues #2 and #3) lived at the SIA↔gbrain subprocess
seam, and every unit test stubs that seam. The rule going forward: **any new
gbrain invocation shape must land with a probe in
`tests/test_gbrain_contract.py`**, which runs the real pinned binary locally
(when the toolchain is installed, or via `SIA_GBRAIN_BIN`) and in CI (which
builds the exact pin). A skip in that lane states that nothing was proven;
it is never a pass.
