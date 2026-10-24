# SDK complete-fixture diagnostic

The private empty-scratch candidate completed **179 tests in 90.147 seconds**
under the unchanged 120-second work limit. Source identities and hashes matched
before and after execution. This is TESTED fixture behavior, not adoption of the
candidate, SDK/native admission, installed-runtime qualification or release
acceptance. Earlier failures remain in the preceding qualification snapshot.

## What changed

The candidate still visits every scratch-array index. For an exact built-in
list of the required length, it omits a call only when the cell is already None
and the original retirement function and its code object remain installed.
After an actual call, and after reentering a guard following failure, it checks
eligibility again. Replacement callbacks still receive every subsequent index.
This retains the existing injected failure seam and avoids repeated known
no-op calls. It does not claim equivalence under arbitrary tracing, asynchronous
mutation, or resource failure at an omitted Python call entry.

Six new controls compare finalizer-driven helper replacement/restoration,
helper code mutation, list shrinkage, high-slot repopulation, earlier-slot
repopulation and observable call omission. The original fixture files are
unchanged from v4 except their required source ROOT relocation. The targeted
roster passed 23 tests in 9.988 seconds; the complete discovered roster passed
179 tests without reported skips. Neither roster is a formal proof.

The bounded empty-scratch cost diagnostic records these elapsed nanoseconds
for its fixed 256-sweep workload, in execution order:

| Implementation | Elapsed nanoseconds |
|---|---:|
| v4 baseline | 144765730 |
| v6 candidate | 78066900 |
| v6 candidate | 80507406 |
| v4 baseline | 137442962 |

These are local measurements, not worst-case bounds or a whole-system benchmark.
The earlier v5 candidate was slower in both orders and remains REJECTED; its
source and raw negative evidence are included alongside this successor.

## Remaining acceptance work

Omitting a function call changes profiling observations and possible call-entry
resource failures. The candidate explicitly records that difference. A fixture
pass does not authorize a new assumption or policy exception. This semantic
question must be resolved against the original contract before adoption.
The earlier-slot repopulation limitation also remains explicit.

Actual GPT-6.1 source review found no blocker to the bounded diagnostic; that
review did not independently run the tests. The three existing BLE001 sites
remain visible under their existing exact-site disposition. No blanket static
analysis waiver is introduced. The new controls and runners had no diagnostics
in the retained strict check.

The full suite used the existing nonblocking shared lock, per-process address
space and file limits, network-isolated read-only fixture environment, and one
five-second termination grace. These do not establish aggregate process-tree
memory bounds. No model call, production ingestion or observer main ran.

Retained-validation R05, strict C analysis, full SPARK obligations, protected
publication/query/recovery, actual harness continuity, installed lifecycle and
release/marketplace gates remain OPEN. The smallest next step is disposition of
the omitted-call contract difference, followed by a separately bound prospective
SDK observation only if qualified. No unchanged retry is required by this pass.

## Evidence use

The [inventory](evidence/sdk-empty-noop-diagnostic-20261024/inventory.json) binds
the [source and raw evidence snapshot](evidence/sdk-empty-noop-diagnostic-20261024/snapshot.tar.gz).
The prior [fixture snapshot](SDK-FIXTURE-QUALIFICATION-20261024.md) retains the
baseline and v4 source dependencies. These are forensic archives, not portable
execution bundles. Review without executing extracted members automatically.

Original filesystem identities, absolute paths and frozen observer output
bindings do not become valid after extraction. In particular, do not execute
the changed observer main against its predecessor's output directory. New
native execution requires fresh source, output and environment admission.
The retained builder supports `check SOURCE_DIRECTORY OUTPUT_DIRECTORY` to
reproduce packaging bytes; that check supplies no product authority.
