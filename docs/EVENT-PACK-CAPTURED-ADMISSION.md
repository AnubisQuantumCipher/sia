# Captured proposal and complete-stream integration

Experimental, inactive test integration. The existing `pack_proposal_probe`
now exercises the captured Python proposal and both complete record manifests
through the actual compiled SPARK proposal gate. No installed command, source
authentication, protected write, migration or deletion is enabled.

## Contract and scope

The original one-argument invocation remains a complete-frame decoder probe:

```
pack_proposal_probe proposal.bin
```

The optional three-argument invocation adds structural stream admission:

```
pack_proposal_probe proposal.bin selection.bin fallback.bin
```

The adapter reads exactly the fixed proposal frame, decodes it, reads bounded
manifest headers and starts `SIA_Pack_Proposal` with the actual header lengths.
It consumes exactly the decoded selected count, at most 65,536 records. Each
step reads one fixed record buffer; fallback consumption follows the gate's
partition discriminator. Short records retain their actual lengths and refuse.
The final gate receives actual end-of-file observations for both streams.
Acceptance requires the complete returned plan to equal the decoded candidate.
Refusal clears the printed plan; file errors terminate without acceptance.
No complete manifest is allocated by the Ada adapter.

This is conditional correspondence. The adapter does **not** authenticate the
plan identity, manifest digests, caller, capture, permission reference, payload
hashes or source custody. Tests deliberately demonstrate acceptance of a changed
identity hash slot and matching but unauthenticated fallback records. That is
an explicit limitation, not evidence that those records are trustworthy.
The Python source capture's existing revalidation remains necessary, and is
not a substitute for the unresolved protected producer/actuator boundary.

## Verification

The original 367-test captured-proposal regression remains intact. Eleven added
tests bring the local composed run to **378 tests, no skips**, passing under the
original 60-second job limit and 5-second per-process deadline. They exercise:

- Actual legacy, pack-only and saturated-prior fallback captures; original files
  remain unchanged and complete re-encoded plans match.
- Every manifest-header and record truncation, semantic record-byte mutations,
  invalid tags/counts, trailing bytes, duplicate and reordered records.
- Full-target overlap, including the same identity with changed content;
  interleaved represented/fallback records and payload-length boundaries.
- Empty selection, 65,536 selected records, and the combined maximum of 64
  represented records with 65,536 selected records.
- Invalid/short/trailing proposal frames and failed manifest opens.

Independent GPT-6.1 execution copied the exact 21-file Ada build input into a
fresh stage, rebuilt it and reproduced all 378 tests without skips under the
same limits. Its regression wrapper took 52,471,900,507 ns. The owner fault
controls were independently reviewed, not independently rerun. Exact commands,
source and binary identities, tool pins, raw logs and historical failures are
retained in `EVENT-PACK-CAPTURED-ADMISSION-EVIDENCE-20261025.json` and its archive.

The strict build keeps assertions and all existing warnings enabled. Two
compiler refusals are retained: obsolete aggregate syntax in c1, and an
unobserved updated file state in c3. Both were repaired without suppressing
warnings or changing caps/domains. C2 passed 376 tests before cleanup repair;
those results do not qualify the final c4 source.

A compiled fault that replaces the fallback end-of-file observation with zero
causes the unchanged trailing-byte oracle to fail. Separately, three compiled
cleanup controls inject both close failures, a simultaneous primary consumption
failure, and a proposal-read failure followed by close failure. They verify
nonzero termination, no acceptance output, retained cleanup diagnostics and the
original primary error. Fault-injected executables are evidence only and are
not adopted.

The adapter and test driver remain outside SPARK. All sixteen production Ada
source files are byte-identical to the prior qualified proposal composition:
476 checks, zero justified/unproved, with independent fresh-source reproduction
recorded in `EVENT-PACK-PROPOSAL-ADMISSION-EVIDENCE-20261024.json`. This increment
does not claim a fresh proof, a whole-stream theorem, filesystem correctness or
formal verification of this I/O adapter. The new evidence file records exact
source reuse separately from fresh runtime execution.

## Cleanup and environmental limits

Both manifest closes are attempted before reporting ordinary cleanup failures.
The primary exception and each cleanup exception have separate retained slots;
the primary takes rethrow priority, followed by fallback and selection errors.
Normal callers also verify that file states are closed. The original frame
reader uses the same cleanup path.

This is not allocation-failure-independent cleanup: the Ada runtime's exception
retention can fail. A broken stderr stream can also prevent diagnostic delivery
or replace the intended rethrow. Runtime allocation, OS I/O behavior, process
termination and the compiler/runtime remain environmental assumptions. The
diagnostic opens ordinary named files and provides no hostile-writer snapshot,
descriptor custody, special-file rejection or production IPC boundary. Bounded
byte counts do not prove bounded I/O latency; external deadlines remain needed.

Without `SIA_PACK_PROPOSAL_PROBE`, discovery explicitly skips the compiled
integration tests. Such a run is **UNRUN**, not an adapter pass. Hosted CI adds
the new Python file to the existing pinned partial static profile; it does not
yet build this adapter or run the focused SPARK proof projects.

## Power of Ten and acceptance status

These are project adaptations, not Holzmann quotations. Direct control flow,
fixed buffer sizes, a validated loop bound, short helpers, explicit result
checks and strict warnings address portions of rules 1–7 and 10. Explicit
versioned fields and direct calls address portions of rules 8–9. Python fixture
allocation, Ada I/O/exception allocation, standard-library internals and OS
latency remain unproved; this does not establish complete rule compliance.

The smallest next integration step is independently authenticated source and
manifest custody at the protected boundary. Actual effect execution remains
gated on native qualification, source/policy admission, durable receipt/recovery
tests and the original complete assurance contract. The native analyzer failure,
full writer/proof/harness/retrieval/recovery/cockpit/installed gates and R05 both
requirements remain open. This checkpoint authorizes no main merge, release,
marketplace guarantee, whole-system proof or avionics certification.
