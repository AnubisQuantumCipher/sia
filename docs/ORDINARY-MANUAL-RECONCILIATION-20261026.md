# Manual reconciliation of one completed fixture — 2026-10-26

TESTED / EXACT NORMAL FIXTURE ONLY. The completed normal run from the
[ordinary recovery latch campaign](ORDINARY-RECOVERY-LATCH-20261026.md) now has
an explicit reconciliation decision. One reviewed invocation archived its pending
record, preserving the exact bytes, and removed only the blocking pending name.
Actual exit 0 and a separate read-only inspection confirmed the fixed ledger
identity, unchanged epoch, exact decision/archive roster and pending absence.
No workload was launched by this procedure.

The procedure first rechecks its closed source and evidence rosters, the original
snapshot and canonical source bytes, toolchain, host and heavy-lock identity.
Under that lock it creates an exclusive decision, synchronizes the decision and
directory, creates an exclusive hardlink to the pending record, verifies identity
and content, synchronizes the archive name, rechecks immediately before unlinking
pending, synchronizes again and checks every close. The archived record retains
its original unresolved status; interpreting it requires the separate decision.
This is an operator-authorized manual action, not an automatic recovery policy.

## Evidence and limits

All 21 component methods passed in 0.082 seconds. They exercise real disposable
storage and mocked admission, including partial writes, synchronization failures,
existing artifacts, identity replacement, unlink failure, close failure and
missing or changed evidence. They do not kill the actual observer. Selected
strict static analysis reported zero diagnostics; no routine exceeds 60 lines.
These observations do not establish full Python Power of Ten compliance.

Independent GPT-6.1 review found an initial missing source recheck, an open evidence
roster and missing admission controls. Those gaps were repaired before execution;
the initial unexecuted source is retained. The same model reviewed the final
source, bindings, raw test results and actual reconciliation readback. A temporary
model-capacity failure is recorded separately from the completed review.

Any storage error stops the procedure. A failure after unlink but before completed
synchronization or close is UNKNOWN, with no automatic retry or rollback. The
protocol assumes ordinary nonhostile root and no concurrent privileged mutation;
the heavy lock does not constrain unrelated root processes. No hardware crash
test was performed. Captured tool completion notes are unsigned observations.

The [generated manifest](ORDINARY-MANUAL-RECONCILIATION-EVIDENCE-20261026.json)
and [31-member archive](evidence/ordinary-manual-reconciliation-20261026-v1.tar.gz)
retain source, decisions, raw results, audits and review. The included generator
reproduces the archive byte for byte. Original normal-run evidence and source
snapshot bindings remain in the prerequisite latch checkpoint; this small archive
does not duplicate them or make the full source snapshot independently available.

## Remaining work

This decision authorizes neither replay of the completed run nor a general
successor. The wrapper still needs explicit refusal of a previously retired
manifest before new dispatch is qualified. The next existing test is an actual,
source-bound observer-death cut before payload admission, with termination observed
before any witness cleanup. Post-admission descendants remain a separate cut.

This procedure changes only the declared disposable engineering ledger. It does
not change installed SIA, services, firewall, provider, release or marketplace
state. Observer-loss recovery, whole-job custody, C14/native restoration, repeated
compaction, R05 BOTH, Astra judge, installed final composition and every original
A/G/C/P/R/EP obligation remain open. Existing SPARK results retain their original
source and assumption scope; they do not prove this manual Python procedure.
