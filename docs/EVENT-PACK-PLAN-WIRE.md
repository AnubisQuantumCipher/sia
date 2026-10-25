# Event-pack retirement proposal wire, version 1

Experimental and inactive. This representation is a prerequisite for connecting
captured source observations to `SIA_Pack_Retirement`, not an authenticated plan,
protected permit or installed migration path. The full migration and assurance
gates remain controlling.

## Fixed layout

Exactly 16,384 bytes, with unsigned integers in network byte order. Every scalar
occupies eight bytes, except the one-byte version and presence flags. Digests are
32 raw bytes. Zero digest values remain valid; they are not absence sentinels.
Positions below are one-based, matching the Ada source. No native structure layout
or pointer reinterpretation is used.

| Positions | Field |
|---|---|
| 1 | Version, exactly 1 |
| 2–8 | Reserved, all zero |
| 9–40 | Supplied plan identity |
| 41–48 | Transaction epoch, at most 2^63−1 |
| 49–80 | Transaction identity |
| 81–112 | Corpus identity |
| 113–144 | Organ identity |
| 145–176 | Prefix identity |
| 177–208 | Source revision |
| 209–240 | Capture identity |
| 241–272 | Selection manifest identity |
| 273–304 | Fallback manifest identity |
| 305–336 | Previous target identity |
| 337–368 | New target identity |
| 369–400 | Permission-scope reference |
| 401–408 | Organ byte length, 1–200 |
| 409–416 | Selected count, 0–65,536 |
| 417–424 | Fallback count, 0–65,536 |
| 425–5,040 | Prior roster |
| 5,041–9,656 | Target roster |
| 9,657–14,272 | Represented roster |
| 14,273–14,336 | Original legacy presence, 64 flags, each exactly 0 or 1 |
| 14,337–16,384 | Original legacy generations, 64 digests |

Each roster has an eight-byte count (0–64), followed by exactly 64 records of
72 bytes each: identity digest, content digest, eight-byte payload length
(0–65,536). Inactive record slots must be entirely zero. Active records require
positive payload lengths and strictly ordered identities. Unused presence and
generation slots must be zero. All these policy constraints are enforced by the
existing retirement predicate after structural decoding.

Independent layout arithmetic was checked through JACKAL with status `exact`,
not `formal-bounded`:
`parsed=8+32+8+11*32+3*8+3*(8+64*(32+32+8))+64+64*32`, result `16384`.
That arithmetic is outside its Lean certificate chain and establishes no program
correctness or authentication claim.

## Decode contract

The future byte-stream adapter must check actual length before constructing the
fixed array. The Ada entrypoint also checks the supplied length, version, reserved
bytes, integer domains and presence encoding. Its explicit correspondence
predicate relates every decoded plan field to the specified bytes.

`Decode` admits only structurally valid frames whose decoded value satisfies
`Valid_Retirement_Plan`. Otherwise it returns `Accepted=False` and `Empty_Plan`.
This is policy-qualified proposal decoding; a structurally valid fallback-only
transport outcome can be refused because it is outside the retirement slice.
It is not evidence that the separate transport planner rejected that outcome.
`Value` is a structural decoder under an explicit precondition, not an authority
entrypoint. A caller must not mistake its return value for admission.

The existing continuity word decoder supplies the epoch arithmetic. All input
counts, roster capacities and logical-size domains remain unchanged. Fixed-domain
array aggregates introduce no dynamic allocation, mutable loop state or callbacks.
An absent original remains distinguishable through its presence flag and required
prior coverage, rather than by interpreting zero digest bytes as absence.

## Plan identity preimage and authentication boundary

The proposed identity derivation is SHA-256 over this exact concatenation:

1. ASCII bytes `SIA-PACK-PLAN-BINDING-v1`, followed by one zero byte.
2. Frame bytes 1–8, including version and reserved bytes.
3. Frame bytes 41–16,384, in their existing order, without normalization.

Exactly bytes 9–40, the identity's own slot, are excluded. Every other byte is
covered. A producer must place the derived digest in that slot. Computing and
checking this derivation is a separate refinement obligation: this decoder does
neither. A modified identity can decode successfully; tests must expose that
limitation rather than pretend it authenticates the frame. Even a correctly
computed unkeyed hash does not authenticate the producer or grant permission.

Protected admission must bind the exact frame/preimage to independently selected
operation identity, original sources, current capture and policy, permission
scope, and durable witnesses. No execution identity, custody receipt or durability
witness is created by decoding. Python may propose these bytes; it cannot grant
itself publication or retirement authority. Native-boundary qualification remains
a prerequisite to actual protected effects.

The source producer still owes complete selection/fallback manifests, actual
original presence/generations, canonical pack bytes, current lineage, route and
source binding, budget preservation and later revalidation. Digest labels and a
matching sum of counts do not discharge those obligations.

## Verification scope and remaining obligations

The focused project includes the original retirement controls plus independent
nonuniform complete-field vectors, maximum scalar/count/roster cases, length
refusals and a mutation at every frame byte. Accepted mutations must change the
decoded value and round-trip byte-for-byte through a test-only independent
encoder; refusals must clear the output. A coherent decoder/specification field
swap must be rejected by the independent fixture. These are runtime controls,
not proof of semantic source truth.

Required evidence before acceptance: exact-source strict build and complete scoped
proof, runtime and coherent-negative results, raw warning/exclusion audit and
independent review. General encoder/decoder round-trip and canonical-uniqueness
proof remain separate obligations beyond decoder correspondence; finite mutation
tests do not establish them. No producer, signing/authentication, protected IPC,
Linux crash refinement, whole-system resource proof or installed-path guarantee
is supplied by this package. Do not enable migration from this checkpoint.

## Retained qualification

Candidate c6 passed strict compilation, the unchanged runtime workload (188
retirement controls and 19,508 wire controls), and the complete focused proof
under the existing resource caps. GNATprove reported 309 checks: 141 flow and
168 prover checks, with zero justified or unproved checks. The scope comprises
all 69 production entities in the five declared production units. Four runtime
test units are explicitly outside SPARK. Raw diagnostics and declared exclusions
are checked separately from summary totals.

A coherent Corpus/Organ swap in both the decoder and its shared correspondence
definition compiled, then failed the unchanged independent runtime fixture.
Earlier strict-warning failures, full-scope timeouts and a deliberately unrun
candidate remain in the evidence archive. The roster-only diagnostic is retained
as diagnosis; it is not substituted for the complete c6 run.

The general repository report checker currently keys declarations by name alone
and rejects legitimate overloads. It remains unchanged and its full-system gate
remains open. This focused audit instead requires the exact name, file and line
of every declaration in its pinned flat-package specifications, alongside the
complete expected unit roster. It accepted the real report and refused 414
synthetic omissions, duplicates, wrong source locations, wrong names and warning
mutations, plus 27 unit-roster omissions, duplicates and substitutions. A review-found
unit-uniqueness bug in the first scoped auditor was reproduced and fixed; its
original source and failure are retained. This is a supported-layout audit, not a general Ada parser or proof
authentication mechanism.

## Power of Ten application

These are SIA adaptations, not quotations of Holzmann's original rules. The
[existing assessment](POWER-OF-TEN-ASSESSMENT.md) retains the normative source,
broader Python/Linux gaps and original obligations.

| Rule | Application and evidence boundary |
|---|---|
| 1 | Direct field mapping and conditional refusal; no recursion, nonlocal jumps or callbacks in this decoder. |
| 2 | Fixed-domain aggregates cover all roster/presence/generation slots; focused proof includes termination. No Linux scheduling or latency bound follows. |
| 3 | Fixed array and record capacities with checked arithmetic; no explicit allocator. Whole-process stack, heap and runtime resource qualification remain open. |
| 4 | Small separate scalar, record, roster, context and plan functions; review covers each mapping. |
| 5 | Complete field correspondence, guarded conversion preconditions, retirement-policy admission and empty output on refusal. Independent mutation controls supplement contracts. |
| 6 | Pure package, null globals, local intermediate values and no effect capability. A caller must not mistake structural Value for admission. |
| 7 | Version, actual supplied length, reserved bytes, scalar ranges, presence codes and policy constraints checked. The future stream adapter still owes actual byte-length validation before array construction. |
| 8 | Explicit versioned layout and source roster; no generated dispatch or conditional authority variants. Compiler/toolchain correctness remains assumed. |
| 9 | Static calls and fixed values; no raw pointer reinterpretation or dynamic dispatch. No protected IPC is implemented here. |
| 10 | Strict compiler warnings, flow/proof warnings as errors, complete focused coverage, raw exclusion checks and retained failures. Original full-system gates remain open. |

Python/Linux limitations, all original acceptance workloads, R05 and release
requirements remain open where previously open. No migration or installed-path
activation is authorized by this evidence. This is not certification.
