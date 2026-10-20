# Consolidation progress and availability boundary

Status: bounded model experiment, not a production termination proof or time
bound. It does not authorize dropping scan debt, shrinking capture coverage,
removing conservative rescans or acknowledging unfinished publication.

## What the implementation does

`_advance_consolidation_scan` walks a bounded directory page, retaining its
cursor. `_prepare_consolidation_claims` selects a bounded candidate-day batch.
`consolidate_corpus` either retains a day or publishes its admitted epoch/index
lineage before unlink. `_acknowledge_consolidation_claims` removes completed
claims from the pending list. Any observed source unlink starts a fresh scan.
`_recover_pending_consolidation` retains the named transaction until scan debt
is empty, then persists applied state, settles its ledger and clears the marker.

This explains why a lower pending-day count does not mean a fixed amount of
work remains. Retained days can be revisited after every source-removing batch.
The installed daemon also performs other pulse work between recovery units.
The observed per-cycle duration and scheduler wait are measurements, not bounds.

## Finite abstraction and assumptions

`ConsolidationProgress.tla` models a fixed, finite set of eligible day identities
and a fixed subset that must be retained. A scan obtains that set atomically;
one processing step examines its first candidate. Keeping a day advances the
pending list. Removing one restarts the scan, matching the conservative policy.
The positive configuration checks eventual scan completion under weak fairness
of successful processing. Its `settled` variable denotes scan completion only;
it does not model the real applied-marker or signed-ledger settlement.

The positive instance has four days, of which the first two are retained.
TLC reports 13 generated and distinct states, with the liveness property and
declared invariants passing. This is finite-instance model checking, not a
proof for arbitrary corpus sizes. Source-to-model refinement remains OPEN.

The abstraction assumes each scan/processing step succeeds and returns.
Directory paging/reset, changing protection/window decisions, crashes,
capacity refusal, queue exhaustion, filesystem/Git latency, provider work and
ledger/publication completion are outside its positive result. In particular,
fairness does not supply a maximum scheduling delay or wall-clock deadline.

Two negative configurations retain counterexamples:

- `keep-reset-negative` deliberately restarts after a protected day instead
  of advancing. TLC finds a fair cycle that never completes. This is an
  injected regression, not the behavior claimed for current production code.
- `reinsert-negative` permits an external writer to recreate removed paths.
  TLC finds a fair cycle that repeatedly removes and recreates a day. This
  illustrates why unconditional completion cannot be claimed under arbitrary
  external writes; it is not evidence that the resident ingestor does this.

Both negative runs exit with TLC's temporal-property violation status, while
the positive run succeeds. Raw traces and command receipts are retained under
the external `consolidation-progress-model-development-v1` evidence directory.
The initial runs emitted a JVM garbage-collector recommendation; reproduction
uses the recommended collector instead of suppressing that warning.

## Required operational closure

1. Bind the actual recovery transaction to its cutoff, source identities,
   generation transitions and selected resident path. Observe why generations
   restart without logging private source contents.
2. Establish a progress argument covering directory scans, resets, claims,
   retention, source removal, ledger settlement and publication together.
   State the assumptions about admitted writers and eventual quiescence.
3. Define measurable maximum work and accepted scheduling/resource budgets.
   A subprocess timeout does not bound lease wait, retries, total recovery,
   filesystem stalls or the surrounding CPython/Linux runtime.
4. Test multi-generation recovery and new/changed source arrivals through
   the actual resident entry and fresh-process restart, with original source
   retention and acknowledgment gates intact.
5. Demonstrate completed recovery and normal no-touch recall on the installed
   machine. Until then availability remains incomplete, regardless of green
   finite models or isolated tests.

No recovery-latency guarantee or Power-of-Ten rule 2 compliance is earned by
this experiment alone. The smallest safe performance change must first retain
the same source-observation, lineage, replay and publication guarantees.

## Reproduced cursor-invalidation gap

Status: FAILED liveness condition under repeated current-day replacement;
repair OPEN. The characterization test
`ConsolidationBacklogRecovery.test_current_day_replacement_restarts_paged_scan_until_quiescence`
uses real corpus Git, Linux directory cookies, scan checkpoints and atomic file
replacement. It reduces the scan entry budget to two to force pagination over
a small fixture. All old days are pinned and the replacement page is newer
than the fixed cutoff. Twelve recovery/replacement rounds retain the same
pending transaction, produce multiple scan generations and never settle.
After replacements stop, the same recovery path completes within the test's
bounded retry allowance and every source byte remains unchanged.

This passing characterization test records undesirable behavior; it is not
acceptance of that behavior. Settlement is controlled in this fixture. It is
not a complete daemon execution or proof of infinite execution. The shipped
scan entry budget is 1024; the reduced-budget fixture exercises its cursor
logic, not a measured full-size production workload.

The relevant production interaction is visible in code:
`_bounded_source_entries` treats changed directory identity as a cursor reset;
`_advance_consolidation_scan` restarts its generation on that reset;
`_recover_before_pulse` may return with consolidation still pending; and
`_pulse_transaction_guarded` can then sense and atomically update event pages.
Therefore eventual stability of eligible old bytes alone is insufficient for
the current algorithm: unrelated newer pages share the directory namespace.
The earlier finite model's atomic scan does not cover this interaction.

The observed installed backlog had completed directory scans between
source-removal rescans. This experiment does not diagnose its current wait as
this pagination failure.

Repair requirements:

- Make discovery progress independent of ordinary updates outside its admitted
  eligible snapshot, while preserving exact source identity checks before
  consolidation and retaining newly arriving evidence.
- Define and persist the snapshot/transaction boundary, including later-arriving
  old events, restart, source replacement, and cutoff rollover. An immutable
  authoritative namespace snapshot is a candidate, not an accepted design.
- Do not ignore changed directory cookies, skip an unvisited suffix, discard
  arrivals, silently raise resource ceilings, or suspend capture without a
  qualified durable buffering/overflow policy.
- Require a positive regression with continuing current-day updates, complete
  eligible coverage, source retention and eventual settlement, followed by
  selected resident-path and fresh-process tests. Preserve this characterization
  as historical evidence when the expected behavior is deliberately repaired.
