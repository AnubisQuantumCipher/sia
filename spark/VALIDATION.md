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
