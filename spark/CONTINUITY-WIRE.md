# Bounded continuity transport, proposed version 1

Status: proposed format with fixed-frame decoding and typed classifier
composition under verification. A disposable one-request I/O prototype now
exists; installed integration remains unimplemented. See the
[I/O evidence report](../docs/CONTINUITY-IO.md) for its limited tested scope,
resource assumptions and retained review failures.
The transition policy's full-project proof is still incomplete. This proposal
does not replace the existing Python JSON proposal codec or relax any acceptance
gate.

The first implementation will be a disposable one-request process joining
bytes to the existing pure restore/transition classifiers. It will not access
the live corpus, publish checkpoints, resolve originals or execute operations.
It is useful for differential testing of the representation and conditional
decisions. A sender can fabricate matching evidence fields; syntax validation
does not authenticate those fields or establish their truth.

## Framing and scalar representation

All offsets in this document are zero-based. A field occupies exactly its
stated width. Records have no native Ada alignment, enum representation,
endianness, hidden padding or pointer fields on the wire.

Every request is exactly 32768 bytes followed by EOF. `used_length` must equal
the selected operation's canonical length, not merely fit inside the frame.
Every reserved byte and every byte from `used_length` to the end must be zero.
There is no alternate short-frame encoding and no concatenated-request mode.
The I/O adapter must detect one extra byte, refuse truncation/excess and impose
an external deadline; waiting for EOF is not itself a termination guarantee.

| Header offset | Width | Field |
| --- | --- | --- |
| 0 | 4 | ASCII `SIAC` |
| 4 | 1 | Version, exactly 1 |
| 5 | 1 | Operation: 1 restore, 2 transition |
| 6 | 2 | Unsigned big-endian `used_length` |
| 8 | 24 | Reserved, zero |

Digests are exactly 32 uninterpreted bytes. A generation is eight unsigned
big-endian bytes whose first byte must be at most 127. This restriction applies
to every generation, including witnesses and inactive records. Unknown enum
codes, Boolean bytes other than 0/1, counts outside their declared ranges, and
predecessor indices outside 0..64 refuse before constrained-type conversion.
No clamping, truncation, modulo conversion or skipped inactive slot is allowed.

The following mappings are explicit protocol values. A later Ada enum change
must not silently change them:

| Field | Byte values |
| --- | --- |
| Boolean | 0 False; 1 True |
| Claim kind | 0 Goal; 1 Acceptance; 2 Constraint; 3 Correction; 4 Decision; 5 Rejection; 6 Source; 7 Completed; 8 Verification; 9 Failure; 10 Next_Action; 11 Permission_Reference; 12 Pending_Approval |
| Origin | 0 Source_Record; 1 Derived_Record; 2 Model_Record; 3 Legacy_Record |
| Role | 0 User; 1 Assistant; 2 Tool; 3 System_Role |
| Coverage | 0 Not_Observed; 1 Unavailable; 2 Observed_Empty; 3 Partial; 4 Complete |
| Availability | 0 Unknown; 1 Missing; 2 Retained; 3 Retracted |
| Operation phase | 0 Planned; 1 Dispatched; 2 Uncertain; 3 Observed_Complete; 4 Acknowledged |
| Transition event | 1 Dispatch_Attempt; 2 Interruption; 3 Observed_Outcome; 4 Reconciled_Outcome; 5 Acknowledgment |

Claim count is 0..64, operation count is 0..16, and `Replaces` is 0..64.
Policy-invalid but representable values must survive decoding: for example,
an active zero identity, an absent witness with nonzero fields, a forward
predecessor or a nonempty inactive claim. The policy, rather than a decoder
normalization, classifies them. Invalid scalar encodings and nonzero reserved
bytes remain transport errors.

All-zero content digests are values. Presence is carried only by the relevant
flag/state. In particular, the canonical empty claim has Legacy_Record and Tool
codes; an entirely zero-filled claim is a different, representable record.
The canonical empty transition observation has event code 1. Neither record
may be silently synthesized from zero bytes.

## Fixed record layouts

`Context` is five consecutive digests: Task_Id at 0, Session_Id at 32,
Repository at 64, Revision at 96 and Dirty at 128. Its width is 160 bytes.

Claim, width 128:

| Offset | Width | Field |
| --- | --- | --- |
| 0 | 32 | Identity |
| 32 | 32 | Slot |
| 64 | 32 | Source_Record_Id |
| 96 | 8 | Sequence |
| 104 | 1 | Kind |
| 105 | 1 | From |
| 106 | 1 | Speaker |
| 107 | 1 | Replaces |
| 108 | 20 | Reserved |

Operation, width 144:

| Offset | Width | Field |
| --- | --- | --- |
| 0 | 32 | Identity |
| 32 | 32 | Action |
| 64 | 32 | Source_Record_Id |
| 96 | 32 | Result_Record_Id |
| 128 | 1 | Stage |
| 129 | 1 | Has_Result |
| 130 | 14 | Reserved |

Witness, width 48:

| Offset | Width | Field |
| --- | --- | --- |
| 0 | 1 | Present |
| 1 | 1 | Durable |
| 2 | 8 | Bound_To.Epoch |
| 10 | 32 | Bound_To.Transaction |
| 42 | 6 | Reserved |

A claim observation is 144 bytes: State at 0, the full 128-byte Claim at 1,
and 15 reserved bytes at 129. An operation observation is 160 bytes: State at
0, the full 144-byte Operation at 1, and 15 reserved bytes at 145.

Checkpoint, width 10816:

| Offset | Width | Field |
| --- | --- | --- |
| 0 | 160 | Scope |
| 160 | 32 | Identity |
| 192 | 32 | Previous |
| 224 | 32 | Capture |
| 256 | 8 | Epoch |
| 264 | 8 | Through |
| 272 | 8 | Retention_Epoch |
| 280 | 13 | Coverage in the explicit claim-kind order above |
| 293 | 1 | Count |
| 294 | 1 | Operations_Count |
| 295 | 25 | Reserved |
| 320 | 64 records of 128 | Claims, including every inactive slot |
| 8512 | 16 records of 144 | Operations, including every inactive slot |

Current evidence, width 12128:

| Offset | Width | Field |
| --- | --- | --- |
| 0 | 160 | Scope |
| 160 | 32 | Checkpoint_Id |
| 192 | 32 | Capture |
| 224 | 8 | Epoch |
| 232 | 8 | Through |
| 240 | 8 | Retention_Epoch |
| 248 | 48 | Manifest witness |
| 296 | 48 | Originals witness |
| 344 | 8 | Reserved |
| 352 | 64 records of 144 | Claim observations |
| 9568 | 16 records of 160 | Operation observations |

Transition observation, width 448:

| Offset | Width | Field |
| --- | --- | --- |
| 0 | 32 | Before_Id |
| 32 | 32 | After_Id |
| 64 | 32 | Event_Record_Id |
| 96 | 32 | Outcome_Record_Id |
| 128 | 8 | Before_Epoch |
| 136 | 8 | After_Epoch |
| 144 | 144 | Before_Operation |
| 288 | 144 | After_Operation |
| 432 | 1 | State |
| 433 | 1 | Kind |
| 434 | 1 | Has_Outcome |
| 435 | 13 | Reserved |

The restore request contains Checkpoint at 32 and Current_Evidence at 10848.
Its `used_length` is exactly 22976. The transition request contains Before at
32, After at 10848, and all 16 transition observations at 21664 with stride
448. Its `used_length` is exactly 28832.

## Canonical checkpoint identity and external producers

For this proposed format, the checkpoint identity is SHA-256 of:

1. The exact ASCII bytes `SIA-CONTINUITY-CHECKPOINT-V1` followed by one zero byte.
2. Checkpoint bytes in the half-open interval `[0,160)`.
3. Checkpoint bytes in `[192,10816)`.

The identity's own field is omitted. Every other checkpoint field, including
predecessor, coverage, counts, all slots and canonical padding, is included.
Only a syntactically valid canonical record may acquire this identity.
"Canonical" here does not mean policy-valid; policy-invalid identities or
inactive-record values remain representable. The
outer request header, current-evidence descriptors and detached transition
observations are not part of that preimage. They do not vary the identity of
the same checkpoint.

The byte decoder does not hash, authenticate or accept that identity as current.
The proposed hash schema is a future producer requirement. A separate qualified
producer must check the canonical preimage and custody; an input containing an
arbitrary identity must remain available for negative policy tests. Digest
equality is neither an authenticity check nor evidence that an outcome happened.

Source/result/event records retain separate domains and original provenance.
Their producer schemas are not defined by this wire format. Before any producer
or durable integration is accepted, its source, result **R**, event **E** and
detached observation **D** schemas must enforce the acyclic dependencies in
[CONTINUITY-TRANSITIONS.md](CONTINUITY-TRANSITIONS.md). In particular R and E
cannot depend on the successor checkpoint identity or D that binds them.
The record codec may be implemented and tested independently; production
identity generation and reference resolution remain blocked on that work.

## Bounded response and process outcomes

The process consumes one request and emits at most one fixed 64-byte response
followed by EOF. There is no text, echoed input, log or second message on stdout.
The parent must bound stdout/stderr, check exact response length and terminal
exit status, and retain the selected executable and exact request identity.
This process-local correlation is not an authenticated response protocol.

| Offset | Width | Field |
| --- | --- | --- |
| 0 | 4 | ASCII `SIAR` |
| 4 | 1 | Version, exactly 1 |
| 5 | 1 | Operation: 0 for malformed input, otherwise the requested 1 or 2 |
| 6 | 1 | Family: 0 transport error, 1 restoration, 2 transition |
| 7 | 1 | Result code from the table below |
| 8 | 56 | Reserved, zero |

| Family | Codes |
| --- | --- |
| Transport error | 1 Malformed_Frame; no partial policy result |
| Restoration | 1 Invalid_Checkpoint; 2 Identity_Mismatch; 3 Stale_Checkpoint; 4 Need_Evidence; 5 Reconcile_Repository; 6 Reconcile_Operations; 7 References_Proposed |
| Transition | 1 Invalid_Before; 2 Invalid_After; 3 Task_Mismatch; 4 Predecessor_Mismatch; 5 Watermark_Regression; 6 Operation_Lost; 7 Unsupported_Change; 8 Need_Transition_Evidence; 9 Transition_Proposed |

For a valid request, the operation and family must match. Every policy result,
including refusal, exits 0: zero means successful classification, not permission
or acceptance. Malformed input emits the canonical transport-error response
and exits 65. Read/write errors exit 74; a partial response can exist after a
write error and is never accepted. A failed executable, signal, deadline,
unrecognized status, extra output or mismatched response also refuses.
The parent must not interpret an exit code alone or retry any external action.
This adapter has no external-action path.

## Proof, testing and resource gates

The pure decoder must prove bounded indexing/arithmetic, initialization,
termination, full scalar/field correspondence and canonical empty output on
failure. Successful decoding preserves every field, including policy-invalid
inactive records. Composition must prove the returned classification is exactly
the existing policy's result on those decoded values.

Independent vectors and differential tests must cover each field and enum,
every count boundary, maximum generations, all-zero content digests, absent and
present outcomes, malformed scalar encodings in active and inactive records,
reserved/trailing bytes, truncation/excess, and valid policy refusals. I/O tests
must exercise bounded reads/writes, EOF, errors, process death, wrong/missing
binaries, malformed responses and response/exit mismatches. Neither an encoder
round trip nor shared generated fixtures alone is independent validation.

The I/O layer requires explicit read/write/retry limits and a qualified target
memory/stack/process budget before it can be executed as an adapter. Fixed wire
arrays do not establish physical memory capacity, syscall timing or WCET.
No new spending, concurrency or proof deadline is authorized by this document.
All original proof/runtime obligations and full-project gates remain required.

The proposed size and offset arithmetic was checked using JACKAL, status
`exact`, not `formal-bounded`; full responses are retained externally in
`continuity-wire-arithmetic-v1.json`, `-v2.json` and `-v3.json`. Examples include
`parsed=320+64*128 exact=8512`,
`parsed=352+64*144 exact=9568` and
`parsed=4*32+16+2*144+3+13 exact=448`.
These results do not prove the chosen field inventory, layout correspondence,
decoder, cryptographic producer or target resource bounds.

## Initial record implementation and failures

`SIA_Continuity_Record_Wire` implements only fixed Claim, Operation and Witness
records. Its contracts specify complete scalar/field correspondence, bounded
conversion and the actual typed empty output on failure. The new harness uses
literal vectors, complete scalar-byte sweeps and nonzero mutations of every
reserved position. It explicitly preserves syntactically representable records
that the policy refuses, including model-authored permission claims and absent
results on acknowledged operations.

Development-v1 passed the strict build and all ten runtime harnesses. Its
focused codec proof refused the `operator-reassociation` warning before
analysis, exit 1; the subsequent harness proof was unrun. The repair explicitly
parenthesizes each addition in the big-endian generation relation. The original
source, warning and receipt remain retained in
`continuity-record-wire-development-v1`. No warning is suppressed.

Development-v2 passed strict compilation, all runtime harnesses and the focused
codec proof (82 reported checks). The separate harness proof discharged its
reported obligations but exited 1 because no-effect and imprecise array-update
warnings remained. This is a failed diagnostic, not acceptance. Test routines
now explicitly declare their null global effects and termination requirement;
whole-array delta updates retain the same byte mutations and invariants while
making full initialization explicit. All original controls and the new
nonuniform digest vectors remain. Raw reports and exact v2 source are retained.

Development-v3 then passed strict compilation, all ten runtime harnesses and
both focused proof commands. The first report covers the codec with 82 reported
checks; the second report covers the harness and codec with 230 reported checks.
These totals overlap and must not be summed. Saved raw reports have no
unresolved diagnostics, skipped proofs or Assume statements.
The [scoped evidence manifest](../docs/CONTINUITY-RECORD-WIRE-EVIDENCE.json)
binds source, commands, reported scope, retained failures and tool identities.
Both commands used one initially fresh source/build directory. They are not a
fresh full-project proof, full-project raw-coverage acceptance or a committed
reproduction. Those gates, all remaining record/framing codecs and actual I/O
qualification remain open.

The [independent read-only review](../docs/evidence/continuity-record-wire-review-v3.txt)
checked this scoped checkpoint and its retained failures. No `pragma Assume`
or skip annotations were found; ordinary modular dependency assumptions remain.
The review does not grant full-project or integration acceptance.

## Observation codecs in progress

The unaccepted observation increment adds Context field mapping and fixed Claim,
Operation and Transition observation decoding. Its source review found no
semantic blocker and requested a positive nonempty preservation test across
every availability state; that test was added.

Development-v1 failed compilation because the pure package's typed-empty
constants referenced non-static composite constants from another unit.
Explicit equivalent record aggregates repair that initialization, with an
assertion retaining equality to the original empty values. Development-v2
then failed the strict compiler's value-conversion-copy warnings at nested
record boundaries. Runtime harnesses and focused proofs were not run.
Both source snapshots and failed build receipts remain in the external
`continuity-observation-wire-development-v1` and `-v2` directories.
No warning is suppressed and this source has no acceptance.

Development-v3 then failed compilation because `Always_Terminates` was applied
to ordinary pure functions. The installed compiler rejects that aspect there;
SPARK already requires ordinary functions to terminate. The repair keeps
`Always_Terminates` on the Decode procedures and uses each payload's fixed
array range and exact byte-correspondence postcondition. It does not add a
termination waiver. Explicit fixed-range aggregates replace the implicit
slice conversions without changing the distinct wire types.

Development-v4 passed the unchanged strict compiler flags and all eleven
runtime harnesses. Its focused observation-core proof passed with 84 reported
checks, zero justified and zero unproved checks, under the reported modular
dependency assumptions. The subsequent harness proof reached its unchanged
120-second diagnostic deadline, exit 124, before producing a complete report.
The saved harness-named summary can contain the preceding core summary and
must not be treated as a completed harness result. The raw command result is
authoritative about completion. Full-project proof, framing/authentication,
adapter integration and installed continuity remain unqualified.

The independent read-only source review of the v4 codec and harness found no
new semantic blocker or omitted original control. It confirmed the typed-empty
aggregates, fixed payload bounds, field correspondence and preservation test
across every availability state. That review does not turn the incomplete
harness proof into acceptance. Exact source, tool identities, raw logs and all
failed diagnostics remain in the external development directories.
The [scoped evidence manifest](../docs/CONTINUITY-OBSERVATION-WIRE-EVIDENCE.json)
binds this exact uncommitted overlay and explicitly rejects the stale
harness-named summary. A revised diagnostic driver removes the preceding
summary before each proof command and refuses zero exit without a fresh
summary; mocked stale/fresh controls passed. That runner repair is not another
prover execution and does not discharge the incomplete harness proof.

Separate fresh diagnostics on the same overlay completed `Check_Context`
(26 reported checks) and `Check_Availability` (9 reported checks). Both produced
fresh summaries with unchanged tool identities. They cover only the named
subprograms; their counts are not a full-harness total or integration evidence.

Development-v5 then ran the full project from another fresh source directory.
Strict build and all eleven runtime harnesses passed. The all-unit proof
reached its unchanged 600-second deadline, exit 124, without a fresh summary;
the complete coverage validator therefore did not run. Partial unit reports
and prover attempts remain diagnostic data, not full-project acceptance.
The manifest retains this timeout, the earlier harness timeout and the rejected
stale summary. Neither the proof budget nor the required scope was weakened.

Work on this increment remains preserved while the same owner repairs the
different-account Ollama finding on marketplace request #12332 in a separate
exact-release worktree. `a861e0f` is the preceding record-codec checkpoint.
This observation increment remains a non-final source checkpoint: it is not
installed, released, or accepted as a complete proof or continuity adapter.

## Complete Checkpoint record increment

`SIA_Continuity_Checkpoint_Wire` now decodes the complete fixed Checkpoint record,
including every inactive slot, under an exact field-correspondence contract.
The [implementation/evidence report](../docs/CONTINUITY-CHECKPOINT-CODEC.md)
retains the source-bound strict build and twelve runtime passes, the scoped
77-check core proof, failed combined-harness proofs and the unadopted prover-order
experiment. These are experimental representation results. The outer frame,
actual I/O, authentication and installed task restoration remain unimplemented
or unqualified; the full-project proof remains open.

## Complete Current_Evidence record increment

`SIA_Continuity_Current_Wire` preserves the fixed current-evidence header,
both witness records and all claim/operation observations. Availability and
presence never exempt nested fields from representation validation. The
[source-bound report](../docs/CONTINUITY-CURRENT-CODEC.md) records independent
vectors, complete refusal controls, strict diagnostics and remaining proof
gates. A decoded descriptor is still a sender claim, not an authenticated
observation or authority to restore context.

## Complete request-frame increment

`SIA_Continuity_Frame_Wire` validates the complete fixed in-memory request and
composes the existing classifiers under an exact decoded-field/result contract.
The [scoped report](../docs/CONTINUITY-FRAME-CODEC.md) retains the failed build,
strict compilation/runtime passes, scoped core proof, incomplete harness proof
and independent review findings. Stream framing, response bytes, process
resource qualification and authenticated installed restoration remain open.

## Fixed response increment

`SIA_Continuity_Response_Wire` implements the fixed response representation,
canonical unused result families and syntax/family/exit matching. The
[scoped report](../docs/CONTINUITY-RESPONSE-CODEC.md) preserves literal protocol
controls, a strict-retention refusal caused by overloaded report names, the
explicit-name repair, current core proof and incomplete harness proofs.
`Matches` does not authenticate a process/request instance or recompute the
original request's classification. Actual stream supervision remains open.
