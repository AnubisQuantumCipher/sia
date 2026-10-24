# Intake roster repair and rejected string cache

Status: narrow pairing repair TESTED; string cache NOT ADOPTED; R05 FAILED.
Base source: `02d95d5441fc3185bd08e83d376577aea3178471`.

## Intake source pairing

`siaeventintake._fold_entry` paired the declared sources with collector returns
using plain `zip`. A decoder callback could shorten either or both rosters,
or extend them, without a roster refusal at that boundary. The retained direct
fold controls demonstrate six accepted mutations. Two initial mismatches also
invoked the decoder when they should refuse before it. This is a direct-fold
finding, not a demonstrated bypass through the complete public admission path.

Both the shape validator and replay fold now use an iterator bounded by the
initial source count. Unequal initial lengths, early exhaustion and residual
growth refuse with `complete-collector-roster`. Each original element is read
when its turn arrives; the repair does not take a replacement snapshot or
change alias ownership. Body exceptions remain outside the iterator's error
translation. No owner admission or cache behavior changes.

Evidence retained under `intake-paired-rosters-v1` in the companion bundle:

- Original source: four test methods, eight failing controls; valid-fold and
  decoder-exception identity controls pass. Raw failures are retained.
- Candidate: 94 tests pass in 8.753 seconds, including complete replay,
  checkpoint/delta, association and refusal/alias ordering controls.
- Original static analysis: two B905 findings. Candidate, new tests and runner:
  zero findings under the pinned 167-rule profile; syntax checks pass.
- Runtime: original 60-second deadline, five-second kill grace, 2-GiB address
  space and 512-MiB file limits, private home/network/PID namespace and read-only
  source. Source maps are unchanged before and after each run.
- Actual GPT-6.1 source/raw review found no blocker to this narrow repair.
  The reviewer did not independently execute tests.

Same-length replacement, ABA changes, inner event-list growth and arbitrary
callback execution remain outside this repair. It does not prove complete
termination, fixed allocation, hostile-interpreter isolation or P02 compliance.

## String reuse experiment rejected

The private candidate reused only UTF-8 length and short-escape counts for
exact native strings, in 128 slots with a 4,096-character admission ceiling.
It preserved current chunk limits, escape-pattern reads and subclass callbacks.
The candidate passed 207 tests in 16.609 seconds and the same strict static
profile. Those results support only the tested primitive/regression scope.

The unchanged larger synthetic workload produced a full cold validation
observation of 2,400,971,226 ns, compared with the earlier baseline observation
of 2,354,794,990 ns. These are single observations, not a statistical speed
comparison or latency bound. Useful complete-validation benefit was not
established. The workload still exits 1 with `FAILED_STALE_ADMISSION`: changing
the current source capacity permits warm admission while cold admission refuses
`source-catalog-capacity`.

The cache also retains text beyond caller lifetime without a qualified deletion,
forget or restore hook. Clearing references would not establish zeroization.
The candidate is retained only as evidence; it is not installed or imported by
the product. The original combined-validator reuse test and both outer caches
remain unchanged. No test-instrumentation reconciliation has been accepted.

## Evidence and next acceptance boundary

[The companion bundle](INTAKE-PAIRING-AND-REUSE-20261024.json) retains candidate
and original source, runners, source maps, raw outputs, static results,
the synthetic input image and source records, and both source/raw reviews.
Its embedded builder supports byte-identical `--check` reproduction from the
declared evidence layout and verifies reconstruction of the split input image.
The bundle is package-integrity evidence, not acceptance authority.

Keep the string cache rejected unless a materially different measured case and
qualified lifecycle justify reopening it. The next R05 work must identify a
useful closed derivation while retaining current owner checks, callback order,
first-mapping aliases and all original reuse/rejection/workload/resource gates.
Repeating the rejected primitive experiment or merely renaming the complete
validator does not satisfy that requirement.

All original assurance, SPARK proof, harness lifecycle, installed-runtime,
recovery, held-out retrieval and release/marketplace gates remain open as
recorded in the execution board. No whole-system assurance, avionics
certification, universal harness support or lossless-compaction guarantee is
claimed here.

## Later terminal-deletion counterexample

The subsequent [bounded-traversal repair](INTAKE-BOUNDED-TRAVERSAL-20261024.md)
found that iterator exhaustion alone missed deletion of an already-yielded final
row. The earlier evidence above covers its original controls, not that terminal
case. Final cardinality checks now close the demonstrated edge case in all
three pairing helpers. New original failures and candidate evidence are retained;
same-length/ABA mutation and complete system bounds remain unproved.
