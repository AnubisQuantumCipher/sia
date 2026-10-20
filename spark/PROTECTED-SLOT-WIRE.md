# Protected-slot request and grant wire proposal

Status: DESIGN PROPOSAL, not a frozen protocol or installed decoder. This
specifies the request/grant portion of `PROTECTED-SLOT-CONTRACT.md`. Receipt,
state, intent and response schemas, complete budgets, vectors, proofs and
protected commissioning remain open. The original proposal wire is unchanged.

## Encoding

Concatenate fields in the order below with no alignment or native padding.
Integers are unsigned big-endian. A digest is 32 raw bytes, not hexadecimal
text. Protected identity assignments must be nonzero and come from administrator
configuration, never from client self-assertion. Content digests admit the full
SHA-256 output domain; zero is not an absence sentinel. Scalar generation values
must fit the existing `SIA_Policy.Generation`; reject the high bit before any
conversion. UID fields use eight bytes with the upper four bytes zero; the
service additionally requires the administrator-configured initial-namespace
principal mapping. UID zero is excluded from requester and historical publisher
roles in this disposable protocol; administrative provisioning is separate.
Syntax admission alone grants no authority.

Every record starts with this prefix:

| Field | Width | Admitted value |
| --- | --- | --- |
| Magic/version | 8 bytes | ASCII `SIASLOT1` |
| Record kind | 1 byte | 1 Publish request, 2 Query request, 3 Grant |
| Signature profile | 1 byte | 1, fixture Ed25519 profile only |
| Reserved | 2 bytes | all zero |
| Total record size | 4 bytes | exact fixed size for the record kind |

Profile 1 uses SHA-256 for content/identity digests and Ed25519 for grant
signatures. These are design choices matching existing library availability,
not cryptographic qualification or inherited proof. The service trusts only
administrator-pinned public keys; a record contains no self-authorizing public
key. A key ID is SHA-256 of the raw configured public key. Unsupported profiles
refuse rather than negotiate or downgrade. Fixture and production key spaces
are disjoint. Requests are not signed: their profile selects the grant profile,
not request authenticity. Only an exact protected grant and kernel-observed
principal can supply authority. Receipt/state signer profiles and independent
key pins require their own schemas.

## Current authorization context A

| Ordered field | Width | Meaning |
| --- | --- | --- |
| Issuer | 32 bytes | pinned administrator issuer identity |
| Capability | 32 bytes | exact current publication or read grant identity |
| Key | 32 bytes | grant verification key identity |
| Clock | 32 bytes | configured current monotonic clock-domain identity |
| Boot | 32 bytes | current protected boot-domain identity |
| Service | 32 bytes | current protected service-instance identity |
| Subject UID | 8 bytes | kernel-mapped requester principal |

All request values are claims. The service compares them with its protected
grant and actual observations; it never adopts them as current state. A query
uses current read authority, even when its target transaction used an older
publication capability, key, clock, boot or service domain.

## Immutable operation identity O

| Ordered field | Width | Meaning |
| --- | --- | --- |
| Fixture | 32 bytes | administrator-pinned disposable store identity |
| Transaction | 32 bytes | exact admitted immutable operation identity |
| Protocol | 32 bytes | fixed digest of this operation protocol identity |
| Publication issuer | 32 bytes | historical publication-grant issuer |
| Publication key | 32 bytes | historical publication-grant verification key |
| Publication clock | 32 bytes | historical admission clock domain |
| Publication boot | 32 bytes | historical admission boot domain |
| Publication service | 32 bytes | historical admission service domain |
| Publication capability | 32 bytes | historical exact publication grant |
| Predecessor receipt | 32 bytes | authenticated before-state receipt digest |
| Payload digest | 32 bytes | SHA-256 of exactly the logical payload bytes |
| Publication subject UID | 8 bytes | historical publisher principal |
| Before generation | 8 bytes | exact authenticated predecessor generation |
| Target generation | 8 bytes | unique representable successor |
| Logical payload length | 8 bytes | at most 4096 bytes |

The protocol identity is SHA-256 of the ASCII bytes
`SIA-PROTECTED-SLOT-OPERATION/1`, without a terminator. It is a pinned
version identifier, not a hash of this Markdown or a self-description. A schema
change requires a new protocol/version and cannot reinterpret old records.
The publication subject is retained separately from the querying principal;
otherwise a cross-principal query could erase who originally held write authority.

New publication requires A's issuer, capability, key, clock, boot, service and
subject to equal the corresponding historical fields in O. Query authorization
does not rewrite O to make those fields match the new service. Its independently
issued read grant binds both current A and the exact historical O. New Publish
also requires the exact authenticated fixture/predecessor and a nonzero strict
representable successor. Query validates historical generations against retained
authenticated state; successor-shaped numbers alone establish nothing.

## Requests

Both request kinds are `Prefix || A || O || Query_Target || Payload_Area`.
Query_Target is a separate 32-byte field: Publish requires all zero bytes;
Query requires the historical publication request digest retained in authenticated
intent/committed state and its receipt. A Query grant binds this exact target
in addition to O. The historical digest hashes the original complete canonical
Publish envelope, whose Query_Target was zero, so no circular hash exists.
The original digest must be retained before any effect; it cannot be reconstructed
from a new Query envelope. Zero in this field is interpreted by record kind,
never as permission to omit a Query target comparison. Both kinds have a fixed
4096-byte payload area. Publish requires its logical payload bytes first and
all remaining bytes zero. The digest covers only the logical bytes; admission
must verify it before any effect. Empty logical content is allowed only with
the matching digest and exact grant, never inferred from missing input.

Query requires the entire payload area zero. O still describes the historical
publication, including its original payload length and digest. A Query request
never supplies replacement payload data and never changes the slot. Reject any
different actual packet length (including disagreement with the prefix),
noncanonical padding or unsupported ancillary data. Required kernel credentials
use a fixed bounded recvmsg control buffer; truncation, rights or unsupported
controls refuse, and any delivered descriptors must be closed. Credential
namespace mapping must be independently configured; uncertainty refuses. One SEQPACKET message is one frame; no prefix concatenation or
trailing frame is accepted as one request.

The immutable operation digest is domain-separated SHA-256 over the exact
encoded O. A separate current request digest covers the request kind and the
complete request bytes, using a distinct frozen domain label. A third distinct
label identifies the historical publication request digest. They are not interchangeable: a current query envelope
must not be used as the historical publication or recovery identity. Complete
hash/signature domain labels and vectors must be frozen before implementation.

## Protected grants

A grant is `Prefix || A || O || Query_Target || Not_Before || Expires || Action || Active ||
Reserved || Signature`, where both time fields use eight bytes, Action and
Active each use one byte, Reserved is six zero bytes and Signature is 64 bytes.
Action is exactly 1 Publish or 2 Query; Active is exactly 0 or 1. Both time
scalars must fit `SIA_Request_Admission.Tick`; reject the high bit before
conversion. Units, clock sampling and domain production remain explicit freeze
prerequisites: no implementation may choose them implicitly. The policy
requires an active grant and `Not_Before <= observed_tick < Expires`; an empty
or reversed interval grants nothing. Requests contain no authoritative clock tick.

Signature input is a fixed grant-domain label followed by every preceding grant
byte, including prefix, A, O, Query_Target, interval, action, active state and
reserved bytes.
The label and canonical vectors remain a freeze prerequisite. Missing signatures,
wrong configured keys or any mutation refuse. The service must not trust an
artifact's claimed issuer/key to replace the administrator's independent pin.
One publication-grant file and one current read-grant file are retained under
the protected store lease; no client path selects a different file. Revocation
or replacement must serialize with observation and effect/query execution.

Dispatch is exact: Publish kind requires Action=Publish from the fixed
publication-grant slot; Query kind requires Action=Query from the fixed read-grant
slot. Slot roles and fixture identities are independently configured and bound
by signed Action and O.Fixture. Signature validity or matching identities cannot
compensate for a wrong kind, action or slot. Every current A field, exact O,
Query_Target, active interval, sender mapping and protected current observation
must join before effects or disclosure. Publish grants require Query_Target zero.

Completed Publish retry envelopes are unsupported in this first wire proposal.
They receive uniform refusal, with no effect or outcome disclosure, even with
current write permission. Clients must send an explicit Query with current read
authority to retrieve a retained result. Never reinterpret an old Publish as a
Query or renew its historical A. This narrows the parent contract's retry transport,
not its read-authorization requirement; a future retry envelope needs a separate
specification and review. Test mutation controls in both kind/action directions.
Unknown, conflicting and completed outcomes remain indistinguishable until the
exact read gate has passed.

## Arithmetic evidence and open work

JACKAL returned `status=exact`, outside the Lean certificate chain:

| Quantity | Echoed parsed expression | exact |
| --- | --- | --- |
| O bytes | `parsed=11*32+4*8` | 384 |
| Request bytes | `parsed=16+6*32+8+11*32+4*8+32+4096` | 4728 |
| Signed grant bytes | `parsed=16+6*32+8+11*32+4*8+32+8+8+1+1+6+64` | 720 |

These are arithmetic results only, not protocol correctness or formal-bounded
claims. The original draft omitted the historical publisher UID; the admitted
proposal includes that field and the separate Query_Target rather than reusing
its earlier smaller totals. The retained v1 arithmetic is superseded for frames.
A disposable local library observation signed and verified a test message and
reported a 64-byte signature; it does not qualify the cryptographic library.

Before freeze, complete explicit field offsets and golden/mutation vectors;
hash/signature labels; monotonic units and domain producers; key rotation and
historical verification; any future completed-Publish retry envelopes;
receipt/state/intent/response schemas; typed errors and output ceilings; OS
queue/disk/memory/process budgets; and the new SPARK effect policy/model.
Vectors must include every field mutation/reordering, wrong keys/issuers/actions/
slots, zero/max/high-bit scalars, nonzero historical lengths with zero Query
padding, and uniform unauthorized outcomes. No parser, signer, privileged service
or protected write is implemented here.
