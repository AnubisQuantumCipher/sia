# Candidate sampled-admission and recovery model

Status: experimental finite model of a proposed temporal contract. Not a
frozen protocol or executable refinement; no production authority changes.

The existing `SIA_Request_Admission.Matches` compares a supplied observation tick
against a half-open grant interval. `Classify` and `Classify_Scoped` return only
observation/proposal classifications, never effect authority. They prove no
clock authenticity or later filesystem timing property.

The candidate new effect protocol uses **validity at the protected admission
sample**, explicitly not validity throughout subsequent signing or fsync.
That sample authorizes one exact operation, with its historical grant and
sampled context retained in the signed intent. Time expiry after the sample
does not cancel that operation. Current independent recovery permission still
gates all continuation effects. This is a proposed contract for the new
protocol, not a reinterpretation of existing APIs.

For an implementation, the new-admission section must hold the protected
lease from checking the current grant, credentials, domains and predecessor
through sampling, signing and publishing/synchronizing intent. Administrator
grant revocation shares that lease. A revocation request cannot claim to have
taken effect before its serialized update; natural clock expiry may occur
while the section runs. No sample or staged file authorizes reconstruction
after a crash. Only a retained authenticated final-named intent can enter
the separately authorized synchronization/recovery path.

This choice is still subject to independent review and full protocol freeze.
An operator requiring expiry to cancel all later completion needs a different
explicit contract, not an unsupported stronger claim about this one.

## Abstraction and checks

`AdmissionRecovery.tla` describes one exact authenticated operation. Intent has
absent, staging, final-visible and synchronized states. Crash discards staging;
an unsynchronized final rename may either survive or disappear. A synchronized
intent survives at this abstraction level. Restart clears the current
execution's synchronization witness, so retained visibility cannot substitute
for synchronization before payload effects.

The write grant can expire between any actions. Independent recovery
permission can be disabled between any actions and is never re-enabled.
This overapproximates interleaving relative to the intended serialized
sections. The model records synchronization and permission witnesses at the
payload effect, so subsequent revocation does not pretend to undo the effect.
Its post-expiry reachability witness is also recorded at the effect; merely
expiring a grant after an earlier effect does not satisfy that control.

The positive configuration checks types, payload safety and the current
synchronization witness. The negative configuration deliberately omits the
sync prerequisite and must violate `PayloadSafe`. The reachability configuration
must violate the deliberately false `NoExpiredCompletion` invariant without
violating safety. This demonstrates the candidate temporal promise rather
than hiding post-expiry completion behind an unreachable branch.

A second negative configuration bypasses recovery permission at the payload
effect and must also violate `PayloadSafe`. Separate reachability controls
require an unsynchronized final intent to survive a crash, then restart,
resynchronize and produce an effect after expiry; and a synchronized intent to
survive a crash, restart and resynchronize before effect. The monitor is reset
if intent is lost or a new admission occurs, and its value is retained at the
effect. It cannot manufacture a recovery witness from a later crash after an
ordinary completion. These controls establish modeled path reachability,
not physical crash recovery.

Run:

```sh
JAVA_BIN=/path/to/verified/java TLA_JAR=/path/to/verified/tla2tools.jar \
  bash spark/check-admission-model.sh NEW_OUTPUT_DIR
```

The runner pins TLC, uses one worker, a bounded heap and timeout, refuses
existing output directories, and requires exact exit/diagnostic pairs.
Raw counterexamples remain in that directory. Java provenance is external,
as with the existing publication-model runner.
Executable/JAR paths are canonicalized before directory changes. The runner
records source/tool hashes and per-lane commands. Distribution metadata calls
the pinned archive release `1.7.4`; its executable emits
`TLC2 Version 2.19 of 08 August 2024 (rev: 5a47802)`. Both identifiers are
retained rather than conflated.

## Unproved boundary

Authentication, exact immutable identity joins, current control freshness,
signature custody, file/parent synchronization and serialized observation
are assumptions here, not implemented producers. `sampled` is an abstraction
of an authenticated retained admission record, never a client Boolean.
The model does not distinguish monotonic-clock numeric values, old/new
boot/service identities, torn records, signing failures, syscall refinements,
hostile record replacement, receipt/state retirement, Query, disk exhaustion,
multiple operations or off-host restore. It proves no liveness or bounded
completion time. Disable may intentionally leave debt indefinitely.

Before freezing a service, extend the exact state/dependency tables, specify
clock units and protected freshness, freeze all record schemas and budgets,
prove the SPARK effect decision, and run the actual Linux fault campaign.
