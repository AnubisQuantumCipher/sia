# Bounded event-pack manifest and partition validation

Experimental and inactive. This adds source-level SPARK contracts for a missing
part of the [retirement policy](EVENT-PACK-RETIREMENT-POLICY.md): complete ordered
selection/fallback correspondence with the represented roster. It creates no
permission, authenticated witness, source acknowledgment or filesystem effect.
No installed or marketplace path calls these packages.

## Format and state transition contract

`SIA_Pack_Manifest_Wire` validates the existing Python proposal manifest format:
the 20-byte tag consisting of ASCII `SIA-PACK-RECORDS-v1` and one zero byte, then an
eight-byte unsigned network-order count. The entire header is 28 bytes. Each
record is 72 bytes: identity digest, content digest, then an eight-byte unsigned
payload length. Counts range from 0 through 65,536; active payload lengths range
from 1 through 65,536. Digests are 32 bytes; all-zero identities remain valid.

The cursor accepts exactly the declared count in strictly increasing identity
order. Invalid length, encoding, duplicate/out-of-order identity, extra record,
incomplete stream or trailing data refuses. Refusal is sticky until an explicit
`Start` creates a new stream. Repeated completion and appending after completion
refuse. Rejected records clear the returned value and preserve prefix counters
and last identity. `Finish` preserves these observations on success and failure.

`SIA_Pack_Partition` holds two cursors and the existing fixed 64-record represented
roster. At initialization, the selection count must equal represented plus
fallback counts and the represented roster must be valid, ordered and padded.
Each admitted selection record must equal either the next represented record
or the next fallback record **in identity, content and length**. A represented
step consumes no fallback record. A fallback step consumes exactly one matching
fallback record. Selection ordering prevents repeated identities across steps.

Completion requires every declared selection and fallback record and every
represented slot to have been consumed, with no trailing data in either stream.
Completed-state consistency records these equalities explicitly. Rejected steps
preserve both entire cursors, representation and represented position. Completion
preserves the representation, position, counts and last identities. The module
returns intermediate classifications for validation only: they must never cause
effects before complete-stream admission and the separate authority checks.

This is a modular proof of the written transitions, count relationships and
per-step correspondence, supported by complete bounded runtime traces. It is
not a separately formalized theorem over an archived history of every step.
The streaming implementation does not retain such a history or authenticate it.

## Refinement and trust obligations still open

The adapter must bind actual byte lengths and EOF to the fixed buffers and
supplied lengths, feed the complete intended streams in order, and bind those
streams and the represented roster to the same plan, capture, source revision,
current policy, operation and permission scope. The core cannot establish truth
from caller-supplied bytes or counts. A valid unkeyed digest is not authorization.

Authenticated custody, selection completeness with respect to actual source,
plan/manifest hashing, shared aggregate resource admission, prior-content truth,
protected effects, crash consistency and installed integration remain separate
obligations. No proof here turns model summaries into evidence or prevents a
caller from presenting a different, internally consistent stream. Full proof,
native-boundary qualification, R05 reuse plus fresh policy validation, actual
continuity tests, recovery and controlled release gates are unchanged.

## Exact-source evidence and reproduction

The [evidence index](EVENT-PACK-MANIFEST-PARTITION-EVIDENCE-20261024.json) binds the
source files, commands, outputs, raw proof report and independent review.
Candidate c1 failed strict compilation because the test encoder used an
ambiguous `Magic` name. C2 qualified the name and passed, but independent review
found missing state-preservation guarantees in the specification. C3 strengthens
those contracts without changing bodies or admitted domains and adds retained
prefix and oversized-length tests. Earlier evidence is retained, not substituted
for the final c4 results. C4 retains c3 production source and adds a
nonuniform vector actually emitted by the existing Python manifest producer.

C4 passed strict compilation, 787,650 manifest runtime checks, the unchanged 188
retirement controls, and the full focused proof: 207 checks discharged (120 flow,
87 prover), zero justified or unproved. All 57 production entities in four units
were analyzed. Three runtime test units are explicitly outside SPARK. No
`pragma Assume`, skipped production proof or noninformational raw diagnostic was
admitted. Ordinary modular dependency assumptions refer to the analyzed units.

Tests cover every declared count and payload length, full maximum-size mixed and
fallback-only traces, zero/one/full represented rosters, every tag byte, every
record-byte substitution, ordering, truncation, oversized lengths, trailing data,
omission, padding, sticky refusal and prefix preservation. These finite controls
are not exhaustive over all digest values or all possible trace interleavings.
A coherent mutant decodes content from the identity bytes in both streams. It
builds, then the unchanged independent oracle fails on the Python producer complete-record
correspondence check. The focused report auditor also rejects its retained malformed
report controls; it is a pinned-layout tool, not a general Ada parser or proof
execution authenticator. Independent GPT-6.1 review inspected source and raw
evidence; it did not independently execute the campaign.

```sh
source /home/sicarii/opt/gnat/env.sh
gprbuild -p -P spark/pack_manifest.gpr -j1
spark/pack-manifest-bin/pack_retirement_tests
spark/pack-manifest-bin/pack_manifest_tests
gnatprove -P spark/pack_manifest.gpr -U --mode=all --assumptions \
  --no-inlining --memlimit=512 --timeout=10 -j1
```

The retained runner uses the existing exclusive heavy-job lock, 60-second build
and runtime limits, 120-second proof limit, five-second termination grace,
2-GiB address-space limit, 512-MiB file limit and disabled core dumps. These are
operational limits, not proved worst-case execution time or process memory bounds.
The production packages have no heap allocation or I/O; test and evidence tools
use runtime facilities outside that assurance boundary.

## Power of Ten adaptation

These are SIA adaptations, not quotations. The original normative paper and
[full assessment](POWER-OF-TEN-ASSESSMENT.md) remain controlling.

| Rule | Control and evidence boundary |
|---|---|
| 1 | Direct calls and explicit refusal branches; no recursion, nonlocal jumps or dispatch. |
| 2 | Fixed-size decoding and bounded digest/roster predicates; termination checked. Stream totals are bounded, but scheduling and wall-clock latency are not proved. |
| 3 | Two fixed cursors and one fixed roster; compiler rejects allocators and implicit heap allocation. Whole-process stack and Python/Linux allocation remain unproved. |
| 4 | Small separate decoding, state and partition routines; source review checks purpose and local reasoning. |
| 5 | Exact admission/refusal, prefix preservation and completion contracts; independent semantic mutation control catches a coherent wrong decoder. |
| 6 | Private state, pure packages, no I/O, permissions or mutable global state. |
| 7 | Checked lengths, counts, order and full record equality; explicit rejected state and cleared output. Actual framing remains an adapter obligation. |
| 8 | Explicit source roster and fixed project configuration; no generated policy or conditional-build variants. |
| 9 | No access types, callbacks or dynamic dispatch; direct bounded data flow. |
| 10 | Strict warnings as errors, complete focused proof, raw scope audit and retained failures. CI/system proof is not inferred from local evidence. |

Next acceptance work is an authenticated, bounded adapter that connects these
checks to the actual proposal bytes and enforces complete admission before any
effect. It must preserve the existing capture, policy and resource gates and be
tested against missing, substituted and concurrently changed evidence. Nothing
here establishes whole-system assurance, universal continuity or certification.
