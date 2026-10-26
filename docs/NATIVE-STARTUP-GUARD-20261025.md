# Checked native startup failures in the experimental continuity adapter

TESTED, not whole-system PROVED. Base source is
`b71976d497784dd62605cbbc31692dfb3b3036f8`. The SPARK authority core and all
original Ada restrictions, compiler flags, test cases and resource limits remain
unchanged. This change is confined to the experimental Linux descriptor adapter.
It is not an installed harness, marketplace release or new authorization service.

## Defect and narrow repair

The linked GNAT initializer calls `sigemptyset`, `sigaction` and `sigaltstack`
without testing their results. The retained native-member disassembly shows the
calls and subsequent control flow. Failure can therefore leave signal setup
incomplete while ordinary request processing continues.

The new C guard wraps the initializer's execution phase and these libc calls.
Arguments are forwarded once. Successful calls and failures outside that phase
retain their results and `errno`. An observed return of -1 during the phase
causes `_exit(74)`: no guard logging, retry, response or Ada finalization is
attempted while runtime setup is known to have failed. This is error propagation,
not an attestation that the expected handlers were installed or remain intact.

The normal GPR build compiles the guard with strict warnings, `-Werror`, GCC's
analyzer and stack reporting. Linker `--wrap` options select the interceptors;
`--require-defined` options seed archive extraction and require their definitions.
The initial integration failed to link because the C archive was scanned before
the runtime introduced its wrapper references. That failed project and raw output
are retained. The corrected normal project links without diagnostics.

## Source-bound observations and controls

- All 122 original SPARK Python tests passed with the initially linked guard.
  The integrated roster adds three native contract tests. Final execution reports
  **125 tests, OK, no skips, 11.712 seconds**. Complete source-manifest and all
  five executable digests match before and after that final run.
- Standalone controls check arguments, call count, results and `errno`, successful
  initialization, out-of-phase failures, and each guarded function's failure.
  CI executes these stub-based controls with required GCC analysis; it does not
  thereby execute or qualify the real GNAT initializer on every architecture.
- Seven native fault cases cover the observed initializer's `sigemptyset`, five
  `sigaction` calls and `sigaltstack`. Each exits 74 while stdin remains open and
  unwritten, with no protocol output. The fault injector emits its own explicit
  stderr marker; the guard emits none. These are deliberately injected returned
  errors, not naturally occurring kernel failures or a signal-delivery campaign.
- With only the guard's rejection removed, every injected case reaches the normal
  protocol response. This is a negative control for early termination, not proof
  that the supervising parent accepts the injected run: its stderr marker would
  cause parent refusal. No hidden parent bypass is claimed.
- Final normal-build disassembly binds runtime initialization to the phase wrapper,
  and the real initializer's setup calls to all three libc wrappers. Wrapper calls
  lead to the original initializer/libc symbols. Entire manually compiled and
  GPR-built guard objects match after debug stripping. This connects the injected
  candidate's guard body to normal-build output without claiming equal entire ELFs.
- Strict C compilation/analyzer output is empty. The frozen Ruff profile returns
  an empty JSON array for the new Python test and retained diagnostic scripts.
  The initial attempt without Ruff's configured absolute path failed with 127;
  that failure is retained, not counted as analysis.
- Existing actual GPT-6.1 review inspected source and raw results, with no
  independent execution. It found no concrete blocker to this non-final,
  inactive test-adapter checkpoint.

## Power-of-Ten adaptation for this change

These are project adaptations, not quotations of Holzmann's original rules.

| Rule | Scope and evidence |
|---|---|
| 1 | Guard has direct, acyclic control flow; no recursion or nonlocal jump. `_exit` is an explicit terminal refusal. Foreign callees remain outside this source claim. |
| 2 | No guard loops. Completion of libc and process exit is an environmental assumption, not a proved wall-clock bound. |
| 3 | One static `sig_atomic_t` phase flag; no guard allocation or variable-length storage. This does not establish allocation-free GNAT, Python or Linux. |
| 4 | Small single-purpose guard routines, directly reviewable in the retained source. |
| 5 | Explicit observed-error contract, positive/negative controls and retained failures. No readiness assertion or assumed success Boolean. |
| 6 | Phase state has file scope and internal linkage; only required linker wrappers are exported. |
| 7 | Meaningful setup return states checked during initialization; argument and errno forwarding controls retained. |
| 8 | One standard feature-test macro exposes the Linux/POSIX ABI; no conditional implementation variants. Link wrapping is explicit in GPR and final disassembly. |
| 9 | No guard-owned pointer dereference or dynamic dispatch; opaque libc pointers are forwarded. ABI, aliasing and foreign runtime behavior remain assumptions. |
| 10 | Strict warning/analyzer flags in the real GPR build and mandatory CI contract compilation; no warning suppression. Selected clean analysis is not whole-program proof. |

## Assumptions, limits and remaining acceptance

The observed frozen startup is treated as single-threaded and non-reentrant.
The phase flag is not a nesting counter, per-thread witness or general concurrent
initialization guard. Repeated, asynchronous and reentrant initialization remain
unqualified. Missing interception, hidden aliases, direct syscalls and arbitrary
shared-library internals are not detected by this mechanism. Required symbol
definitions alone do not prove call routing; retained final call targets matter.

The guard cannot handle failures before its phase, errors that do not return,
later handler replacement or incorrect successful installations. Native compiler,
linker, ABI, libc and kernel behavior remain part of the assumption ledger. No
new SPARK proof, cumulative stack bound, full native qualification, actual
compaction lifecycle, installed continuity or release acceptance follows.

The diagnostic `build_candidate.py` is retained as an executed one-shot campaign,
not shipped as a reusable build tool. It can overwrite named outputs on rerun;
reproduction must use a fresh output namespace. Do not rerun it over this evidence.

Next acceptance work must preserve these controls, qualify actual harness custody
and lifecycle behavior, and close the existing source-bound proof/runtime gates.
R05 BOTH, protected publication, held-out retrieval, recovery/off-host restoration,
installed lifecycle and marketplace publication remain open. The public archive
contains source deltas, identities and diagnostic records; it is not a standalone
offline toolchain or complete system-assurance package.


The [machine-readable receipt](NATIVE-STARTUP-GUARD-20261025.json) binds the
[retained diagnostic archive](evidence/native-startup-guard-20261025.tar.gz).
Its initial one-shot build script consumed the pristine base project. The later
normal GPR integration is separately represented by its source manifest and
commands; do not apply the initial manual-link script to the integrated project.
