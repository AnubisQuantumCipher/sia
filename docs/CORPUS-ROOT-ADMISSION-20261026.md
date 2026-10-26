# Corpus-root receipt admission repair — 2026-10-26

**TESTED / SCOPED / NOT SYSTEM ACCEPTANCE.** The installer helper
`corpus_receipt_recorded_root` previously opened its receipt before checking
that the descriptor represented a regular file. A no-writer FIFO blocked that
check. The open now includes `O_NONBLOCK`; both existing exception handlers
also retain explicit causes. Receipt parsing, numeric-token output and silent
exit-1 refusals are unchanged.

The archive-retirement fallback can reach this helper after the safer legacy
receipt reader refuses. This finding is source-based caller reachability;
the new behavioral controls execute the complete extracted Python helper,
not the entire installer or installed archive lifecycle.

The retained baseline ran five cases: the FIFO exceeded its three-second
deadline and was killed and reaped; four controls passed. All five repaired
cases pass, including exact regular-file output, wrong corpus, absence and
invalid UTF-8 refusals. A separate actual GPT-6.1 execution passes the same
five cases. Those helper runs preserve source/fixture bytes, metadata and
directory membership and observe each child reaped. The two unchanged original
corpus migration/consent methods also pass; their outer receipt does not supply
individual child-cleanup records.

The first static attempt failed because Ruff was absent from PATH; it is
preserved. The corrected pinned invocation retained two existing B904 findings.
After repair, the complete updated CI static block passes locally with the
unchanged frozen rule set. CI now extracts this complete helper and analyzes it
alongside the new test, with suppression checks on both. Six actual extraction
controls pass: valid input, missing/duplicate marker, missing terminator,
oversized input and a suppression directive. These are extraction controls,
not a hosted CI pass. Separate shell syntax and diff checks pass.

[Source and evidence bindings](CORPUS-ROOT-ADMISSION-20261026.json) include the
actual independent review and retained failures. This repair does not establish
universal device/filesystem latency, concurrent-substitution safety, stable
complete reads, the full R13 matrix or comprehensive R40 analysis. Incompatible
regular-file leases may refuse under nonblocking admission. No consequential
authorization decision is added to Python.

Whole-project proof remains interrupted; its reconciliation grants no successor
authority. Aggregate proof-output containment, native custody, actual compaction,
R05 BOTH, judge, installed composition, recovery/retrieval and release gates
remain open. No original requirement or failing assertion is retired.
