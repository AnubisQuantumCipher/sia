# Protected-slot layout and domain-label proposal

Status: DESIGN PROPOSAL. Companion to `PROTECTED-SLOT-WIRE.md`; no decoder,
protected service, signing authority or migration is implemented by this file.
Offsets are zero-based, start-inclusive and end-exclusive. All records share
the following layout through Query_Target:

| Field | Start | End | Width |
| --- | --- | --- | --- |
| Magic | 0 | 8 | 8 |
| Kind | 8 | 9 | 1 |
| Profile | 9 | 10 | 1 |
| Prefix_reserved | 10 | 12 | 2 |
| Total_size | 12 | 16 | 4 |
| A.Issuer | 16 | 48 | 32 |
| A.Capability | 48 | 80 | 32 |
| A.Key | 80 | 112 | 32 |
| A.Clock | 112 | 144 | 32 |
| A.Boot | 144 | 176 | 32 |
| A.Service | 176 | 208 | 32 |
| A.Subject_UID | 208 | 216 | 8 |
| O.Fixture | 216 | 248 | 32 |
| O.Transaction | 248 | 280 | 32 |
| O.Protocol | 280 | 312 | 32 |
| O.Publication_issuer | 312 | 344 | 32 |
| O.Publication_key | 344 | 376 | 32 |
| O.Publication_clock | 376 | 408 | 32 |
| O.Publication_boot | 408 | 440 | 32 |
| O.Publication_service | 440 | 472 | 32 |
| O.Publication_capability | 472 | 504 | 32 |
| O.Predecessor_receipt | 504 | 536 | 32 |
| O.Payload_digest | 536 | 568 | 32 |
| O.Publication_subject_UID | 568 | 576 | 8 |
| O.Before_generation | 576 | 584 | 8 |
| O.Target_generation | 584 | 592 | 8 |
| O.Logical_payload_length | 592 | 600 | 8 |
| Query_Target | 600 | 632 | 32 |

Request tail:

| Field | Start | End | Width |
| --- | --- | --- | --- |
| Payload_Area | 632 | 4728 | 4096 |

Grant tail:

| Field | Start | End | Width |
| --- | --- | --- | --- |
| Not_Before | 632 | 640 | 8 |
| Expires | 640 | 648 | 8 |
| Action | 648 | 649 | 1 |
| Active | 649 | 650 | 1 |
| Reserved | 650 | 656 | 6 |
| Signature | 656 | 720 | 64 |

## Domain labels

In this proposal Label(text) means the exact case-sensitive ASCII bytes of
the displayed text followed by exactly one zero byte. No newline, length field,
second terminator, hexadecimal encoding or Unicode normalization is inserted.
Concatenation below is byte concatenation. SHA-256 results are raw digest bytes.

| Purpose | Exact text inside Label | Bytes following Label |
| --- | --- | --- |
| Immutable operation digest | `SIA-SLOT-OP-DIGEST/1` | canonical O, bytes [216,600) |
| Current request digest | `SIA-SLOT-REQUEST-DIGEST/1` | complete canonical request, bytes [0,4728) |
| Historical publication request digest | `SIA-SLOT-PUBLISH-DIGEST/1` | original canonical Publish request, bytes [0,4728) |
| Grant signature input | `SIA-SLOT-GRANT-SIGNATURE/1` | canonical grant before Signature, bytes [0,656) |

Each digest is SHA-256 of Label followed by the specified bytes. Grant signing
uses ordinary Ed25519 over the concatenated input, not Ed25519ph and not an
application-generated digest of the input. The signature profile and independent
administrator key pin remain required; a matching digest supplies no authority.
Current-request hashing includes Kind exactly once, at its position in the
prefix. It does not prepend a second kind byte. Historical-publication hashing
is defined only for canonical Publish envelopes with zero Query_Target. The
current and historical digests of the same Publish envelope remain distinct
domains; clients must not substitute one for the other.

The protocol identity in O remains SHA-256 of ASCII
`SIA-PROTECTED-SLOT-OPERATION/1` with **no terminator**, as specified in the
parent proposal. It is not computed with Label. Payload digests and configured
public-key IDs also retain their previously specified raw-byte SHA-256 rules.
State, receipt and intent signing domains remain unspecified; none may reuse
these labels or be inferred from them.

## Evidence and remaining acceptance

JACKAL returned `status=exact`, `formal=false` for each cumulative field-width
sum and tail boundary. For example, `parsed=16+6*32+8` returned `exact=216`;
`parsed=632+4096` returned `exact=4728`; and
`parsed=632+8+8+1+1+6+64` returned `exact=720`.
This is exact rational arithmetic outside the Lean certificate chain, not
formal-bounded evidence or protocol correctness. Full returned evidence is
retained as `protected-slot-layout-arithmetic-v1.json` in the engineering
evidence directory. Reproduce every boundary by summing the preceding widths;
do not treat the Markdown table or retained calculation log as an authenticator.

Independent canonical byte vectors, signed positive/negative vectors, mutation
controls, schema review and the remaining parent-contract prerequisites are
still required before protocol freeze. This proposal does not qualify a
cryptographic implementation or establish any enforced authorization property.
