# Replay refusal order: prerequisite controls

Status: **TESTED prerequisite; R05 repair UNPROVEN**. This checkpoint changes
tests and evidence only. It enables no cache and changes no product behavior.

The ordered fold cannot safely be replaced by whole-entry callback evaluation
followed by reconstruction. Some callbacks are reached only after earlier
state checks. A failed before-image join stops the fold's version calls; a
version collision stops later fold calls and association hashing.

Correction to the earlier boundary review: image admission through `_images`
and `_union_images` already invokes the version provider. The refusal above
suppresses **subsequent fold calls**, not all version-provider calls. The new
controls retain those initial calls explicitly.

Six new controls exercise two-page fixtures: new-page success, missing before
join, first-version collision, existing-page success, mismatched existing
before-image, and collision after earlier private progress. Existing-page
admission checks new bytes before old bytes; the fold processes old bytes
before new bytes. The tests distinguish these orders. They require exact
refusal reasons and preserve the original first-only association hash tests.
A later collision may leave a private accumulator partial. The call must
raise and must not produce associations or a successful projection; this is
not a claim of rollback or filesystem transaction atomicity.

The complete selected page/intake/capture/memo/association preservation roster
plus these controls reported **102 tests passing in 29.643 seconds**, under
the original 60-second command deadline. Before/after hashes matched. The new
tests and runner produced no diagnostics under the retained strict rule set.
Existing product static diagnostics and the original stale-admission failures
remain open. The initial narrower roster reported 99 passes; its exact test
source and receipts remain in the local ownership-transfer evidence directory.

The committed result, raw output, runner and static receipt are in
`docs/evidence/replay-refusal-order-20261024/`. The runner retains original
machine paths and sandbox dependencies; it is evidence of this execution,
not a portable standalone acceptance harness. Independent review is source
and retained-output inspection, not independent test execution.

## Rejected SDK experiment

The reviewed v4 SDK graph subset reported 56 passes in 110.935 seconds.
A separate original late-deadline control passed in 1.766 seconds. Neither
is the complete SDK qualification. No clock replacement was adopted.

The v5 per-cell specialization was slower in both recorded measurement
orders and is **REJECTED**. Its raw observations and source/receipt hashes
are retained in `sdk-diagnostics.json`; complete raw local evidence remains
at the recorded paths. Semantic qualification and the complete v5 suite were
not run. No performance ratio, runtime bound or speed guarantee is claimed.
The prior full-suite timeout remains FAILED and the complete v4 suite UNRUN.

## Next boundary and required acceptance

Any reusable derivation must consume closed admitted data and bind its full
relevant predecessor state. Current owner-dependent admission cannot be
skipped because a prior result was cached. Grouping transitions requires
evidence that it preserves refusal precedence and callback traces.

These controls do not establish callback-mutation safety, compact-checkpoint
composition, arbitrary interpreter behavior, cache correctness or a speed
improvement. R05 still requires the original stale-admission, reuse and
resource contracts together. C analysis, full SPARK obligations, installed
continuity, recovery, release and marketplace gates remain separate and open.
No original cap, fixture, oracle or acceptance obligation is waived.
