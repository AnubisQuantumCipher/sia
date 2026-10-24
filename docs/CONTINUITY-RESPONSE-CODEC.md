# Fixed continuity response boundary

This experimental increment implements the proposed 64-byte `SIAR` response
from [the continuity protocol](../spark/CONTINUITY-WIRE.md). It has explicit
operation, family and result maps; every reserved byte is zero. Decode is total:
malformed representation returns a false acceptance flag and the entire typed
malformed result. A valid transport-refusal response returns true acceptance
with the malformed result; acceptance describes the representation only.

Encode canonicalizes unused typed result families. `Matches` requires valid
syntax, the expected request family and the specified terminal exit status.
`Matches(..., Malformed, 65)` is a correlated transport refusal. Every normal
policy classification, including a policy refusal, requires status zero and
the matching restore/transition family. Status zero alone is insufficient.
An I/O-error status, signal, wrong family or malformed bytes cannot match.

This function does not authenticate the process or bind a response to one
request instance. Nor does it recompute the original request's classification.
The future parent must pin the executable, retain the exact request, supervise
one process, check exact stream length and terminal status, and preserve that
correlation. The child must compose the existing Evaluate result with Encode.
There is no I/O, source access, mutation or action grant in this increment.

## Tests and Power of Ten adaptation

Independent literal wire vectors exercise every restoration and transition
result in both directions. Tests cover every pair of unused-family enum values,
all header/operation/family byte values, closed result-code ranges, every
reserved position with every nonzero byte, complete refusal output and all
one-byte process statuses for every valid result. Negative and extreme integer
statuses also refuse. These do not simulate actual process death or pipe errors.
Every original runtime harness remains; this is the fifteenth harness.

The existing [Power of Ten assessment](POWER-OF-TEN-ASSESSMENT.md) controls this
adaptation. Static cases and fixed finite loops preserve rules 1–2's control-flow
and execution-bound intent. Fixed arrays, allocation restrictions and small
pure routines address rules 3–4 without claiming physical memory qualification.
Exact correspondence, canonical refusal and explicit null global effects
address rules 5–7. Explicit maps and static calls avoid hidden enum numbering or
dispatch (rules 8–9). Unchanged strict compiler/prover settings, independent
vectors and retained gate failures address rule 10. This is neither a quotation
of Holzmann nor whole-runtime compliance, whole-system proof or certification.

## Retained failure and current limits

Development v1 passed strict compilation, all fifteen runtimes and the GNATprove
core command, reporting 31 discharged checks across thirteen entities. Its
complete harness proof reached the existing 120-second limit without a fresh
summary. The strict evidence retainer then **FAILED**: two legitimate overloads
both appeared as `SIA_Continuity_Response_Wire.Code`, and the unchanged detail
checker rejects duplicate names. That result is not accepted as a clean retained
core proof. The source, raw diagnostics, retainer and reproduced refusal remain.

The repair names the forward maps `Restoration_Number` and `Transition_Number`.
No map, decoder contract, fixture, gate or proof limit is weakened. Independent
actual GPT-6.1 review confirmed the semantic preservation. The conservative
checker limitation remains visible: any future checker repair must distinguish
verified declarations/locations/signatures while still rejecting duplicated
rows. This increment does not silently broaden its accepted report format.

Development v2's final results are retained in the
[source-bound evidence](CONTINUITY-RESPONSE-WIRE-EVIDENCE.json). Strict
build/all fifteen runtimes and the scoped 31-check core proof pass. Its complete
harness proof also reached 120 seconds without a fresh summary. Ordinary modular contracts
and external toolchain assumptions remain. The complete project proof, prior
600-second failure, authenticated producer and installed restoration obligations
remain open. No larger proof budget, source exclusion or assumption is added.

Fresh committed reproduction of `74efd05673719ce5a740d83510c652c5a956c930`
then repeated strict compilation, all fifteen runtimes and the scoped 31-check
core proof from an archive with no overlay. The
[committed receipt](CONTINUITY-RESPONSE-COMMITTED-EVIDENCE.json) binds source,
exact commands/caps, equal tool rosters and clean raw diagnostics. The
[actual GPT-6.1 correspondence review](evidence/continuity-response-and-restart-review-v1.txt)
confirmed that limited scope without replay. The unchanged failing complete
harness and full-project campaigns remain unproved and were not repeated.

Next is the one-request Linux descriptor adapter and bounded parent supervision.
Before executing it, qualify declared stack/memory/process limits, retain static
stack information and test actual EOF, short/excess input, read/write errors,
deadlines, process death and mismatched output/status. No live installation or
universal compaction/recall guarantee follows from this representation layer.
