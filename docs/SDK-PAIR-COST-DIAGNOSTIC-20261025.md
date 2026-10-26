# SDK pair-shape cost diagnostic

**Non-final diagnostic; the original full-suite timeout remains FAILED.**
No product code, original test body, fixture clock, resource limit or cleanup
obligation changed. No new optimization or native/lifecycle admission follows.

The v8 full run stopped while reporting
`SnapshotAndNames.test_pair_shape_type_and_missing_eof_exact_phase_after_positive`.
That final name identified the cumulative interruption point; it did not
establish a locally stuck test. A distinct diagnostic ran that complete original
method through unittest, including all registered cleanups, with only one
temporary timing wrapper around `clear_scratch`. The wrapper calls the original
body and records inclusive elapsed time. It does not instrument individual cells
or omit empty-slot retirement calls.

The original 30-second diagnostic limit, one five-second termination grace,
512 MiB address-space/file limits, core limit zero, nonblocking heavy lock and
private bwrap home/network isolation were preserved. The separate original
120-second full-suite ceiling was not rerun or raised.

Observed result: **one test PASS, no skips**, unittest elapsed **0.384 seconds**.
The raw outer test-and-cleanup interval was `384079104` nanoseconds. Scratch
cleanup was invoked `588` times, with `269430653` inclusive nanoseconds recorded.
These are measured values from this instrumented run, not a worst-case bound
or a controlled comparison against full discovery. Nested intervals may overlap;
the isolated import/fixture context differs from the complete suite.

All declared v8, baseline, predecessor-v7 and exposed-v4 source maps matched
before/after. The new wrapper and runner passed the existing strict static rule
profile. An independent actual GPT-6.1 reviewer inspected preparation, source
pins and raw results; it did not independently execute the diagnostic.

The result rules out treating the final test name as evidence of a reproduced
local hang. Scratch cleanup remains a cost center in this run. Neither fact
justifies removing helper calls, changing error/cleanup semantics, narrowing
fixtures or restarting an unchanged full suite. No preservation-supported faster
candidate was established here. The next repair must address cumulative cost
while preserving the complete original workload and observable cleanup contract.

## Recovered exception-policy scope

The original user delegation and existing owner decision already covered the
three exact SDK BLE001 exception sites. This was rechecked against the original
events whose identities appear in
[the authorization correction](R05-AUTHORIZATION-CORRECTION-20261024.json).
Current v8 `run_main` and `read_checked` function bytes still match those approved
functions. This does not approve R05 changes, new exception sites, changed
functions, global suppression, missing controls, or a zero-warning claim.
Current whole-source exception binding and required validation remain separate;
raw strict diagnostics remain NONPASS. The older proposal's pending label must
not erase the subsequent recorded limited decision after compaction.

The [evidence inventory](SDK-PAIR-COST-EVIDENCE-20261025.json) binds the inspection
and diagnostic snapshot. Its archive is forensic, not a portable execution
bundle or complete runtime dependency closure. SDK/native qualification,
protected custody, full proof, R05, installed continuity, recovery and release
gates remain open.
