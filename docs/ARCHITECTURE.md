# Runtime architecture and the module map

This file exists because an outside review made a correct observation: the
core module is too large to review, and the project's own ethic — carve a
system into pieces a reader can hold — argues for splitting it. This is the
verified map of what is actually in `bin/sialib.py`, what already lives in
sibling modules, what constrains an extraction, and the sanctioned order for
doing it. It was measured against the tree at v1.5.1; re-verify line ranges
before acting on them.

## What is already split

The runtime is not one file. These lanes were extracted in earlier releases
and are the pattern to follow:

| Module | Size | Lane |
|---|---|---|
| `bin/siasenses.py` | ~119 KB | sensing subsystem (extracted in v1.3.7) |
| `bin/siatakes.py` | ~217 KB | predictions, judge, grading, calibration |
| `bin/siacapsule.py` | ~153 KB | continuity capsules, freeze/thaw, restore |
| `bin/siabackup.py` | ~149 KB | repository adapters and scheduled verification |
| `bin/siabench.py` | ~109 KB | signed-ledger QA benchmark |
| `bin/siamind.py` | ~91 KB | activation, bonding, PPR rerank, stability |
| `bin/siaqueue.py` | ~28 KB | agent note queue |
| `bin/siarestoreadmit.py` | ~11 KB | restore admission |
| `bin/siarelease.py` | ~6 KB | release stamping |

## What remains in `bin/sialib.py` (11.6k lines)

Measured lane map (banner comments; approximate ranges):

| Lane | Lines | Count |
|---|---|---|
| header / imports / paths | 1–59 | 59 |
| instance configuration | 60–349 | 290 |
| utilities (atomic IO, leases, lifecycle fds, redaction) | 350–1414 | 1,065 |
| cursors (source tailing, fingerprints, refusals) | 1415–2517 | 1,103 |
| senses façade (`_siasenses.bind`) | 2518–2627 | 110 |
| corpus (page IO, day pages; thought pages + recovery 3387–5257) | 2628–5258 | 2,631 |
| gbrain subprocess boundary | 5259–5515 | 257 |
| integrity (chain verifiers, ledger transitions) | 5516–6019 | 504 |
| thoughts (store, `think()`) | 6020–6279 | 260 |
| exports (graph projection, domain edges) | 6280–7279 | 1,000 |
| pulse (memo/readiness/notes; epochs; dream/rehearse) | 7280–11652 | 4,373 |

The marketplace static-analysis guard caps every scanned source file at
524,288 bytes (`tests/test_release.py`,
`test_marketplace_scanned_source_files_fit_the_static_limit`). `sialib.py`
sits within ~1–2% of that cap; the ceiling is an operational forcing
function, not a style preference.

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
3. **The runtime member set is versioned in several places at once.** A new
   module file requires a new `sia-runtime-vN` name set in
   `install.sh` (`runtime_tree_digest`), in `uninstall.sh` (twice), and in
   `tests/test_release.py` (`_runtime_digest`), plus `SIA_RELEASE_FILES`, the
   staging copy loop, the installer-content assertions, and the test
   runtime-copy lists. The receipt format versions the member set precisely
   so a partial tree can never validate as an older one — which also means
   every extraction is a deliberate receipt revision.

## Extraction progress

**v1.6.0 — DONE: the exports lane → `bin/siagraph.py`.** Four extraction maps
were run in parallel before cutting anything; the exports lane scored
decisively cleanest (one contiguous ~1,000-line block, 26 functions reachable
from four entry points, only 8 names referenced from 14 parent functions, no
import-time execution beyond constants, one exception class that stays
parent-owned), so it led rather than the originally-guessed thought-recovery
cluster. The move used the exact `siasenses` bind/invoke façade, added a
`sia-runtime-v5` member set to all four digest routines and the installer/test
file lists, and required no change to the graph/domain test suites — the façade
keeps every `sialib.<name>` working and mirrors test monkeypatches. `sialib.py`
dropped from 517 KB to 477 KB; the 857-test suite and a façade-identity smoke
(delegates resolve, `GraphProjectionPending` is one shared class across the
boundary, `except sialib.X` catches a `siagraph` raise) are green.

**Next: v1.6.1 — the thought-pages + recovery/legacy-replay cluster** (~1,870
lines, ~66 functions). Its verified map is on file: zero references from any
other `bin/` module, but two hazards the exports lane did not have — an
import-time ctypes block (`_THOUGHT_RECOVERY_LIBC` + `_ThoughtRecoveryDirent`,
which must stay parent-side) and two `@contextlib.contextmanager` decorators
(so the child imports `contextlib` itself). Its dedicated
`tests/test_thought_recovery.py` is the gate.

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
