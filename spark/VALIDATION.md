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
