# Bounded continuity transport, proposed version 1

Status: proposed format with partial fixed-record decoding under verification.
The full-frame transport, I/O adapter and installed integration are unimplemented.
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
