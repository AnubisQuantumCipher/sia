# Approval selection descriptor refinement

**FAILED PROOF / UNACTIVATED; actual protected integration remains OPEN.** This extends the
[conditional approval policy](CONTINUITY-APPROVAL-POLICY-20261024.md) with an
explicit byte-to-metadata contract. It is neither an original-conversation parser
nor an authenticated producer. No production wire, original assurance project,
installed path, fixed V5 pilot or source retention policy is changed.

The earlier policy required a descriptor bound to all selected fields, while
leaving that relationship to its future protected producer. The new child package
`SIA_Continuity.Approvals.Descriptors` defines one fixed selection descriptor and
checks all of its bytes. It specifies the representation obligation that a future
producer must establish; that producer must still authenticate its independently chosen
records and bind the exact descriptor bytes to its custody/hash evidence.

## Versioned byte layout

Indices are one-based; generations are unsigned big-endian values whose high bit
must be zero, matching the existing `Generation` domain. Digest bytes retain
original order. The format marker is ASCII `SIADSC01`.

| Bytes | Content |
| --- | --- |
| 1–8 | Exact format/version marker |
| 9–40 / 41–72 | Task / session digest |
| 73–104 / 105–136 / 137–168 | Repository / revision / uncommitted-state digest |
| 169–200 / 201–232 / 233–264 | Question event / question item / response digest |
| 265–296 / 297–328 / 329–360 | Proposal / action / conditions digest |
| 361–392 | Checkpoint digest |
| 393–400 / 401–408 / 409–416 | Epoch / through / retention epoch |
| 417–448 / 449–480 | Lifecycle / target turn digest |
| 481 | Form: 0 unknown, 1 queried decision, 2 direct instruction |
| 482 | Currentness: 0 unknown, 1 current, 2 revoked, 3 superseded, 4 expired |
| 483–512 | Reserved, all zero |

The length check was independently calculated with JACKAL: status **exact**,
`parsed=8+160+3*32+3*32+32+3*8+2*32+2+30`, result `512`, `formal=false`.
This arithmetic is outside the Lean certificate chain and does not verify code.
The decoder accepts a fixed typed array. A future transport must check actual
input length before constructing it; this package does not frame, read, truncate,
pad, authenticate or allocate an incoming network/file message. Its fixed size
is not permission to expand any existing aggregate input or context budget.

## Contracts and authority boundary

`Valid` rejects unknown versions, noncanonical reserved bytes, invalid enum codes
and out-of-domain generations. Zero digests, zero generations and syntactically
valid but policy-ineligible metadata remain representable; policy admission is a
separate obligation. A directly instructed decision remains unsupported by the
queried-decision policy even though its descriptor form is representable.

`Content_Matches` relates every meaningful byte to the selected metadata and
context. It intentionally does not assert authentication, digest correctness or
custody. `Decode` is total over the typed array domain, has no globals and returns
an empty context/selection on refusal. On **every** outcome, including successful
decoding, it returns `Descriptor = Zero`, `Source_State = Unknown_Source` and an
empty witness. A previous authenticated output is overwritten. A field called
current is data; it is not evidence that a current authority selected it.

The ghost `Unique` obligation requires that two valid encodings with the same
context and selection content are byte-identical. It does not claim hash
collision resistance, uniqueness of original human meaning or authenticity.
Its first direct proof attempt failed at the solver limit; the failure is
retained. Later candidates expose fixed byte regions and separate big-endian
word uniqueness lemmas. Candidates 4, 5 and 6 hit the unchanged outer proof
time limit without a complete summary. Candidate 7 replaces direct two-word
equality assertions with explicit quotient/remainder digit recovery obligations.
No lemma is imported or assumed. Every supporting body must be discharged; a
proved caller alone is insufficient. Candidate 7 also timed out (exit 124), with reported unresolved digit-recovery
(byte 3) and prefix-uniqueness postconditions. There is no complete final
summary. Partial caller successes do not establish the supporting lemmas.
Exact sources, commands, diagnostics, and negative controls are retained in the
[companion evidence receipt](CONTINUITY-APPROVAL-DESCRIPTOR-EVIDENCE-20261024.json).

This addresses only representation work; acceptance depends on complete proof. The protected producer must independently
select the request, authenticate original question/response sources and their
ordering, interpret decision semantics under its authorized policy, establish
currentness/revocation/retention, and hash/bind these exact bytes without a
check/use race. It must reject changes to fields, context or bytes after binding.
The descriptor excludes its own digest and custody to avoid circular encoding;
those are external protected evidence, never fields trusted from the wire.
The existing adapter refusal remains in place until the complete path qualifies.

## Validation and failures

The focused project includes the new child, existing policy and record decoder
dependencies, and the unchanged original approval runtime controls. New synthetic
runtime controls include exact expected fields, each byte mutation, every enum
code and its explicit meaning, each digest position with nonuniform bytes, mixed
big-endian generation words, generation boundaries, reserved/version refusals,
and stale authenticated output clearing on success and failure. JACKAL **exact**
word calculations supply the mixed-word decimal oracles; full `parsed` fields and
`formal=false` results are retained. These are runtime tests, not formal-bounded
arithmetic certificates or original-record/harness executions.

A coherent question-byte-order mutation changes both decoder and specification
in isolated negative sources. The strengthened independent fixture rejected
candidates 4, 5, 6 and 7 mutations at its nonuniform digest oracle; internal consistency or a proof against a changed specification is not a
substitute for the original representation contract. No mutant is adopted.

The first strict build failed on two unexamined test outputs. The tests were
repaired with meaningful context assertions; no warning was disabled. Initial
uniform vectors passed but independent review found their oracle weakness;
they remain preserved alongside the nonuniform successor. The final candidate strict build and runtime controls exit 0; its coherent
mutation builds but fails the independent oracle with exit 1. This does not
close the failed proof. All attempts retain
the original work/proof, process-memory, output and shared-lock limits.

Power-of-Ten adaptations: fixed storage and ranges, pure explicit mapping,
short routines, no recursion/dispatch/allocator, total refusal contracts,
unknown authentication on all outputs, strict compiler/prover checks, and
independent semantic vectors. Compiler/runtime trust and Python/Linux resources
remain outside this slice. This is not whole-system assurance or certification.

Next acceptance requires a protected producer using this representation, actual
bounded transport and freshness/custody binding, generic restore/actuator tests,
and the complete original lifecycle/fault campaign. AR-T01–AR-T22 remain ALL_UNRUN
at that boundary. Native manager qualification, original full gates and R05 remain
open; both useful expensive reuse and fresh current-policy validation are still
required. Nothing here authorizes installation, main merge or marketplace release.

The smallest remaining proof step is an independently discharged digit-recovery
argument and a fieldwise prefix correspondence lemma, followed by the complete
unchanged focused proof run. Do not rerun this same failed source, raise limits,
remove obligations, or treat this checkpoint as production qualification.
