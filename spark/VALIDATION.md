# Initial policy validation

2026-10-19, aarch64 Linux. This records the unintegrated prototype, not a
released or installed authority kernel. Parent release baseline:
`1f6b6667b0bc5e29b29e6d2d8f2a7b71edcee46c`.

TESTED: `gprbuild -p -P spark/sia_assurance.gpr` with warnings as errors and
runtime assertions enabled; `spark/bin/policy_tests` exited successfully.
The first build rejected obsolete parenthesized array-aggregate syntax; the
source was corrected to Ada 2022 bracket syntax without suppressing warnings.

PROVED within the pure package and test harness scope: GNATprove FSF 16.1.0,
Why3 1.8.2+git, GPRbuild 26.0.0, command
`gnatprove -P spark/sia_assurance.gpr -U --mode=all --assumptions --memlimit=512 --timeout=10`.
Project options select level 2, one worker, full report, proof warnings and
warnings/checks as errors. The revised run reports all 39 checks proved,
zero justified and zero unproved checks. Both units are analyzed. Source has
no `pragma Assume`, proof suppression or SPARK-off region.

Independent GPT-6.1 source review accepted only the documented predicate
prototype scope and identified stronger test oracles and a readiness naming
hazard. The revised tests explicitly reject unavailable/not-observed source
states and an all-zero-epoch publication with matching witnesses. The renamed
`Publication_Joined` cannot be confused with the runtime's complete ready gate.
The reviewer did not independently execute the proof or tests.

Retained operator-local evidence directory `sia-assurance-evidence-20261019`
contains the source SHA256 manifest,
initial/revised proof logs and revised detailed summary. This path is an
operator evidence location, not a portable offline acceptance bundle.

UNPROVEN/UNRUN: authenticated witness creation, actual durability, temporal
ordering, replay prevention, protected actuator, IPC validation, OS isolation,
end-to-end resident integration, cross-platform CI, off-host recovery and
independent held-out cognitive evaluation. The policy is not wired into the
released Python runtime. Contracts specify exact Boolean acceptance predicates;
they do not prove input assertions true in the physical system.

## Durable-prefix reducer checkpoint

The subsequent reducer adds immediate-successor admission, predecessor-receipt
matching, exact latest-receipt replay classification and unchanged state on
refusal/retry. Its inputs still require authentication by the future protected
adapter. No filesystem operation is performed here.

TESTED: both `policy_tests` and `transaction_tests` pass with strict compiler
warnings and assertions enabled. Phase-triple tests use an independent
adjacency oracle; full-path tests use distinct receipts, and negative controls
include stale historical replay, wrong Apply/replay predecessors and coherent
foreign-epoch/foreign-digest requests with matching foreign witnesses.

PROVED in all four analyzed units: the same GNATprove command with
`--no-inlining` reports all 88 checks proved, zero justified and zero unproved.
The modular oracle is proved for arbitrary phase inputs and still executed
exhaustively by the test harness. No fixture or required rejection was removed.

FAILED attempts retained: the initial reducer proof reached the overall
180-second limit. A later run completed with five unproved test-harness checks
and reported prover time/memory limits. Separating the oracle into a bounded,
side-effect-free procedure and using modular analysis resolved those checks;
no assumption, suppression or weakened policy contract was introduced. The
initial attempt also overlapped a test-source edit and cannot establish a
stable-source result. The accepted modular run had no overlapping code edits.

Independent GPT-6.1 review found no blocker in the abstract reducer, but
required complete authenticated receipt binding and stronger negative tests.
Those requirements and tests are included. The reviewer did not independently
run GNATprove. Raw attempts and the accepted summary are retained in the same
operator-local evidence directory. Real crash/replay, signing protection,
IPC, model checking and integration acceptance remain UNRUN.

## Subsequent bounded-model and ACK process-death checkpoints

The bounded model and its negative/reachability controls subsequently passed;
see `model/README.md` and `model/RUNTIME-MAPPING.md` for exact scope and remaining
refinement obligations. This supersedes only the earlier model-checking UNRUN
status, not system integration acceptance.

TESTED: `python3 -m unittest tests.test_assurance_ack_process_death
tests.test_controller_source_ack
tests.test_controller_source_resident_v3_effects_prefix -v` passed 28 tests.
The new module contributes three tests covering real child SIGKILL at core and
journal ACK hooks, artifact-preserving completed retries, and a foreign cursor
negative control after child death. Independent GPT-6.1 source review identified
missing effects-archive snapshots and journal retry checks; both were added
before the accepted regression run. Raw output is retained as
`ack-process-death-reviewed.log` in the operator evidence directory.

UNPROVEN: power-loss durability, fresh resident/interpreter recovery, actual
signed-refusal crash persistence, and correspondence between modeled durable
actions and runtime filesystem operations. The fixture controls Git/index
observations and recovers in the parent's fixture. No production runtime code
or installed service authority changed in this checkpoint.

## Release hold: interrupted archive publication

A subsequent deeper cut reproduced a durability gap. Killing the ACK child at
`siaqueue`'s `target-published` hook left a visible effects archive before its
parent-directory fsync. Recovery reached `effects-receipt-archive-durable`
without synchronizing that directory. The negative run is retained in
`ack-archive-durability-red.log`. This is an ordering failure, not observed
power-loss data loss.

The local repair synchronizes the pinned effects-archive parent and revalidates
the held generation before reporting the archive durable. The regression then
passed 29 tests (`ack-archive-durability-green.log`). Independent GPT-6.1 source
review confirmed equivalent recovery omissions in source archival and cursor
publication; those still require repair and failure controls. This checkpoint
is incomplete and must not be released. The prior final-main target is on hold
even if its existing CI passes. A qualified runtime fix and refreshed release
freeze are required before tagging. Completed read-only validation must remain
effectless; synchronization belongs in pending ACK recovery only.

## Source and cursor synchronization repair

The subsequent patch repairs both remaining recovery paths. Source archival
holds the old source parent through an explicit absence check, synchronizes
both rename parents, and rechecks the held generations. Exact-target cursor
recovery synchronizes its retained parent and revalidates before returning.
Fsync errors propagate without authorizing ACK completion.

TESTED: the extended targeted regression passed 31 tests, including real
process-death cuts inside source rename and main/system/user cursor publication.
Stage-specific failure controls verify the exact injected fsync error, both
source parents separately, and retained pending authority without readiness.
The accepted output is `ack-all-recovery-reviewed.log`; earlier failing
reproductions are retained in `ack-all-recovery-red.log`.

Independent GPT-6.1 source review found no correctness blocker in the repair
and confirmed completed-reader paths remain effectless. Its test-precision
feedback was incorporated before the accepted run. This closes the identified
component repair obligation, not release qualification: isolated runtime PR,
full CI, installed-machine verification, refreshed freeze and publication
readback remain required. Power-loss survival and the full assurance mission
remain unproved.

## Committed-source reproduction runner

`verify-policy.sh` reproduced the strict build, both runtime harnesses and
GNATprove from a fresh archive of commit
`d579861162548d5ceccf7192350869d0859434d3`. The retained detailed report covers
all four units and reports 88 total checks, with no justified or unproved
checks. Evidence is in `policy-reproduction-v1`; each command, exit status,
tool executable identity and complete source archive is retained. Existing
output-directory reuse is rejected. This is a scoped reproduction aid, not
the complete independently qualified offline system verifier.

Correction to that commit's message: Bash syntax checking passed, but
ShellCheck was unavailable (`command not found`), so the message's claim that
ShellCheck passed is incorrect. No ShellCheck result is claimed. The historical
commit is retained; this correction records the actual negative evidence.

Independent review identified a tool-identity gap: resolving a tool before a
directory change but later invoking its bare name could select a different
executable through relative PATH entries. Commit
`8bd12678ea98e9dae9cf58637b9fc23c563f7369` resolves absolute paths before any
directory change and uses those same paths for version, hash, build and proof.
Fresh normal and relative-PATH runs both passed build, harnesses and all 88
checks, with no justified/unproved checks (`policy-reproduction-v2` and
`policy-reproduction-relative-path`). Recorded build/proof command executables
match the absolute tool paths. This closes that specific evidence-binding gap;
dependencies, concurrent same-user mutation and toolchain qualification remain
outside the runner's guarantee.

## Request decoder development checkpoint

The fixed-capacity untrusted-request decoder builds under strict warnings and
its runtime harness passes. Initial compilation rejected an obsolete aggregate
syntax and an unsupported function aspect; those were corrected without
disabling warnings. The first proof attempt was intentionally stopped with
exit 143 after independent review identified missing accepted-field contracts;
its partial log is retained as `wire-proof-first-build.log`, not accepted proof.

The revised decoder has explicit accepted field mappings and a big-endian
generation relation. A nonuniform digest and JACKAL-checked multi-byte numeric
vector strengthen the initial tests. Proof log `wire-proof-semantic.log` is
pending at this checkpoint. No decoder proof completion, authenticated IPC,
transport bounds or integrated authority is claimed. See `REQUEST-WIRE.md`.

The semantic attempt was subsequently stopped with exit 143 to expose the
syntax predicate for modular callers. `wire-proof-modular.log` then completed
with exit 1: its analyzed units had no unproved checks, but no-effect warnings
violated the strict gate and the decoder implementation was absent from the
coverage report. It is failed, incomplete verification, not accepted proof.
The helpers now declare explicit `Global => null` and `Always_Terminates`
contracts. Every original case remains, with per-digest nonuniform vectors and
zero/maximum/multi-byte/overflow generation cases added. Strict build and all
three runtime harnesses pass. Independent review found the contracts/oracles
adequate within syntax-only scope; it did not execute the tests.

A fresh archived-source run of commit
`16986c7` is retained under `wire-reproduction-v1`. It must show complete
implementation and harness coverage as well as zero unresolved obligations
before acceptance. Its proof process remains pending at this checkpoint.

The archived `wire-reproduction-v1` proof exceeded its overall 180-second
deadline (exit 124); build and all three harnesses passed. Its partial results
are not accepted. A subsequent implementation-unit diagnostic completed with
exit 0 and reported all 181 checks proved, including decoder field mappings,
termination and generation arithmetic. This diagnostic is not the clean-source
whole-project acceptance run. Its log and summary are retained separately.

The runner now gives the expanded project a finite 600-second overall proof
budget; per-check timeout, memory, strict warnings and proof requirements are
unchanged. A report coverage gate requires all source spec/body units, complete
reported subprogram coverage and consistent discharged totals. Eight synthetic
tests pass, including missing spec-only units and malformed totals found by
independent review. The historical policy-only report passes against its own
source and is refused against the expanded source tree. This gate does not
authenticate reports or establish physical integration correctness.

The separate experimental Linux packet intake has ten passing tests using real
Unix sockets plus an injected descriptor-close error. They cover exact payload
and per-message credentials, a child sender, every short length, oversized
packets, non-concatenation, unexpected descriptor cleanup/truncation, socket
configuration and EOF. Independent source review found no blocker within this
single-receive scope and requested cleanup continuation after a close error;
that repair and negative control are included. The eight summary-gate tests
also pass. These are Python/Linux tests, not SPARK proofs, protected capability
admission, a complete service resource bound or decoder integration evidence.

## Complete decoder contract reproduction

The fresh `wire-reproduction-v2` archive at commit
`3ccb545245799c4d4018addbfb110c96ee2ece50` completed with exit 0 for strict
build, all three runtime harnesses, proof and the coverage gate. The report
contains all six units, all reported subprograms/packages analyzed, 195 checks,
zero justified checks and zero unproved checks. Every detailed flow entry
reports zero warnings and zero `pragma Assume` statements. The dependency
report relates the pure functions and their harnesses; it does not authenticate
external witnesses. Source archive, commands, executable hashes, outputs, exit
statuses and a SHA-256 manifest are retained in the evidence directory.

This accepts the stated pure policy/reducer/decoder contracts for that source
and toolchain. It does not prove the new Python packet intake, transport handoff,
protected actuator, physical durability, signature implementation or system
isolation. The earlier timeout and incomplete/warning-failed runs remain
retained negative evidence.

## Test-only socket-to-decoder boundary

Commit `5dc570d08194459140ffbfe67d24f6cd52be52b2` was archived into a fresh
`request-probe-reproduction-v1` directory, built under strict warnings and
tested there: build and all 26 Python test methods passed. The manifest binds
the source archive, actual adapter binary, tool executable paths/hashes,
commands and logs. This includes the prior packet and summary tests plus the
new socket-to-Ada integration cases. The pure proof source is unchanged.

The initial stream-file implementation failed on pipes with DEVICE_ERROR; its
failed test log is retained. The replacement descriptor adapter checks all
read/write results and limits reads to the frame plus one sentinel byte.
Independent review identified a masked raw-length oracle; tests now use valid
frame prefixes and a valid frame with trailing bytes, with a matching positive
control. Real descriptor read/write failure controls also pass. Small-chunk
writes may coalesce and are not deterministic syscall-fragmentation evidence.

This is TESTED integration through an isolated test subprocess, not a proved
I/O adapter, resident shadow policy, capability admission or installed authority.

## Exact-grant classifier checkpoint

The new pure classifier builds with strict warnings and its runtime harness
passes. An initial unused-context warning failed the strict build and was
corrected by removing that unused context, without weakening flags. Independent
GPT-6.1 source review found no blocker for comparison/classification scope.
Its zero-expiry control was tightened to remove a masking not-before failure;
the original test remains in history. A fresh archived run of
`a967012cc0caaac2715ff7efd3c62436eef4b885` is retained under
`admission-reproduction-v1`; complete proof is pending at this checkpoint.
No grant-store authentication, replay consumption, disclosure permission or
protected mutation is established. See `REQUEST-ADMISSION.md` and `ASSUMPTIONS.md`.

The archived admission run subsequently completed: all four harnesses, build,
proof and coverage returned zero. The report contains all eight units and 240
proved checks with none justified/unproved. Independent GPT-6.1 evidence review
checked all manifest hashes, exact archive-to-commit and extracted-source
equality, coverage and exits; no blocker for pure-contract acceptance was found.
No protected deployment claim follows from this result.

## Disposable indexer isolation

The experiment at `67becc0bc3678202e812b8326fb0bfe51c6ecf9b` was run from
a retained committed archive under `indexer-reproduction-v1`. Pre-run source
hashes match post-run files; the outer manifest binds the archive, commands,
child/driver output, exits and report. The host-listener positive control,
isolated refusal, read-only export, hidden actual host fixture and explicit
Unix test endpoint all passed. User/PID/IPC/UTS/network namespace identities
differed, effective/permitted/ambient capabilities were zero and NoNewPrivs was
set. User-namespace creation succeeded outside and failed inside the sandbox.

Earlier checkout runs are retained as development evidence; independent review
required the committed-source reproduction and direct effective-state checks.
This is TESTED platform feasibility, not production engine egress containment,
protected source ownership, a real embedding broker or whole-host isolation.

## Real offline engine and committed export

`engine-boundary-v2` is retained FAILED evidence: the actual installed gbrain
indexed an untracked page from a read-only working-tree mount. The experiment
was corrected to expose a clean detached checkout of the exact fixture commit.
The origin retained both an untracked page and modified tracked page. The
corrected lane retrieves the committed body exactly and neither dirty token
appears in the tested source-scoped search before or after resync. Inventoried
file paths/content hashes remain unchanged; metadata/tree identity is not
claimed. Existing source Git/engine generation regression tests also pass
(13 tests). The misleading walker comment in the earlier contract fixture was
corrected; no released-runtime bypass was established.

Source `c6539dfd157e880495c3a5d055fee6401913aa1a` was archived and executed
under `engine-reproduction-v1`. The copied engine matches the installed binary
receipt; receipt source/version/lock/overlay identities match archived GBRAIN_PIN.
The manifest binds archive, source inventory, engine/receipt, commands, outputs,
exit records and fixture inventory files. Initialization, source registration,
sync, database probe, retrieval/search and resync all passed. No embedding,
provider transmission, protected production exporter or installed-service
authority is established. Per-file/descriptor/CPU/time limits are configured;
aggregate memory/disk and descendant resource budgets remain UNPROVEN.

The subsequent experimental precheck and engine lane at
`6d75da71b12da59df9ec9e30fbc2fe3956af6dc8` passed from a committed archive
under `engine-reproduction-v2`. Nine focused tests reject unsupported Git
entry modes, malformed paths and file/count/declared-byte budget violations.
The real offline engine sequence also passed. Independent GPT-6.1 review
verified all manifest hashes, pre-run inventory, archive/extracted-source
identity, focused and engine exits, and receipt/pin consistency without
repeating execution. Accepted status is TESTED for the disposable fixture only.
Clone/object-storage budgets, arbitrary-repository admission, protected export
ownership and production authority remain outside this result.

CI now explicitly discovers the Python proof-summary, packet and experimental
export controls with finite deadlines and ResourceWarning errors. Their local
runs passed (respectively eight, ten and nine tests); the new CI step itself
requires remote execution. This does not run GNATprove or the Ada I/O adapter,
and does not replace their separate committed-source acceptance lanes.
