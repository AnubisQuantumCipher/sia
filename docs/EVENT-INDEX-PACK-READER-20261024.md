# Experimental captured dual-format event-index reader

Status: TESTED prerequisite, not activated, not accepted for migration or release.
The transport contract in `EVENT-INDEX-PACK-CONTRACT-20261024.md` remains binding.
No installed data, source-record limit, backup selection or capsule limit changed.

## Implementation boundary

`siaeventpackreader.read_captured` is an explicit experimental entry point. Normal
runtime lookup/publication does not import or call it. The original reader still
reads only its legacy file. Its existing canonical and epoch validation has been
extracted into the shared `_validate_event_index_raw` facade helper, with a fresh
raw byte bound before decoding. The current owner supplies that bound each time;
an explicit unbound dependency slot is populated through the existing binding.

The candidate reads the original legacy path and the proposed
`event-packs/<organ>/<first-two-hex>/<first-three-hex>.siaep` path through the
existing bounded dependency capture. It validates the entire frame and freshly
applies original canonical bytes, inner/outer identity, epoch/source manifest and
declared completeness checks to every contained record. The unkeyed pack digest
does not authenticate those records. A valid target cannot bypass a later invalid
record. If both representations contain the requested identity, their original
canonical bytes must agree exactly. A malformed pack refuses even with a valid
legacy leaf. A well-formed pack without the target permits the original legacy
fallback; it does not establish that the target never existed.

Both present and absent path observations are checked after validation. The caller
must hold the corpus lease and validate the complete capture, including root,
ancestors, epochs and byte observations, before acting. This prerequisite is not
enforced by a new protected service here. Capture and owner callbacks are existing
trusted Python interfaces, not cryptographically authenticated capabilities.
The before-view replay interface has not yet been qualified with packed inputs.

## Evidence and limits

The final selected roster passed 70 tests in 6.481s. It includes the unchanged
codec, event-epoch integrity, epoch merge and module ownership rosters, plus new
temporary-corpus/capture controls. The original isolated job envelope remained
60 seconds, 2 GiB address space, 512 MiB output-file cap and no core dumps, with
read-only source, private HOME/tmp, isolated network/PID namespaces and the
existing heavy-job lock. Inventoried source bytes matched before and after.
These are temporary single-owner fixtures, not installed corpus qualification.

Controls cover legacy-only/pack-only/equal duplicates, conflicting duplicates,
no target in a full pack with and without legacy fallback, malformed framing,
noncanonical records, rehashed false lineage, invalid unselected records,
current lowered record limits and fresh epoch policy, absent files appearing,
same-byte inode replacement, symlink leaf/parent refusal, and owner-facade
rebinding and parent overrides. The full-pack fixture supplies a controlled
canonical roster; it is not evidence that those occurrences were captured.

The unchanged selected strict static profile reports no diagnostics in the new
reader, new tests or named final test drivers. It reports 530 diagnostics in the
existing thought module, compared with 535 before this change; explicit binding
of the limit slot removes five undefined-name reports and adds none by diagnostic
code/message comparison. The first candidate's additional undefined-name report
and subsequent repair are retained. This is not zero-warning system acceptance,
nor a waiver of inherited findings. The dynamic owner facade remains an analysis
limitation; suppressions were not added.

## Power of Ten adaptation and next acceptance

This is a project adaptation, not Holzmann's wording or a compliance claim.
The candidate uses small routines, explicit refusal conditions and a loop bounded
by the codec's admitted record count. It writes nothing and introduces no success
cache. Python still allocates dynamically; raw capture reservations do not prove
the entire decoder, JSON parser, epoch traversal or interpreter's memory/timing.
Owner indirection and the complete capture protocol remain trusted dependencies.

Before integration: qualify aggregate lookup/dependency cost under original job
and state budgets, both live and before-view replay captures, complete capture
validation while the corpus lease is held, and enforcement through the SPARK
authority boundary. Preserve legacy fallback for oversized records and saturated
groups; no framing limit may silently narrow the original accepted domain.

Then implement exact-coverage durable publication and crash recovery, with source
generation/digest comparisons before any legacy retirement. Fault injection must
exercise every publication/retirement boundary and uncertainty must remain
visible. A complete reviewed migration and retained recovery evidence are required
before installed migration or file-retirement authorization. Actual capsule
capture, off-path restore, replay, installed qualification and release/catalog
readback remain open. No original A/G/C/P/R obligation or R05 approval changed.
