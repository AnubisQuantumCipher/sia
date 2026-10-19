# Experimental request frame v1

Status: untrusted decoding prototype, not an installed IPC service or authority.
`SIA_Request_Wire` consumes a fixed-capacity byte buffer and a separately supplied
observed length. A future transport must bound reads before allocation, measure
actual bytes, reject excess/trailing input, and authenticate the peer. This
package cannot establish that a caller supplied the real observed length.
The experimental Linux packet receiver in `transport/` now measures and bounds
one actual packet, with socket tests. It is not yet connected to this decoder
or installed as a service; peer credentials do not grant mutation authority.

| Byte positions | Field | Encoding |
| --- | --- | --- |
| 1 | Version | Exactly 1 |
| 2 | Operation | 1 Observe; 2 Propose |
| 3, 4 | Before and after phase | Ordinals 0 through 10 in the documented transaction order |
| 5–8 | Reserved | All zero |
| 9–40 | Capability identity | Opaque digest |
| 41–72 | Source identity | Opaque digest |
| 73–104 | Transaction identity | Opaque digest |
| 105–136 | Payload identity | Opaque digest |
| 137–168 | Predecessor receipt | Opaque digest |
| 169–176 | Before generation | Big-endian unsigned value fitting `SIA_Policy.Generation` |
| 177–184 | Target generation | Same encoding |
| 185–192 | Reserved | All zero |

Exactly 192 observed bytes are required. Unknown versions, operations, phase
values, nonzero reserved bytes and integer overflow refuse. Refusal returns a
fully initialized empty request and `Accepted=False`. Acceptance means only
that the wire representation is supported. It does not authenticate any digest,
validate the capability, admit a phase transition, assert a durable effect,
or authorize publication. Even a well-formed all-zero identity must pass the
future protected authorization boundary before it has any effect.

The frame contains no paths, text, pointers, signature-valid or durability
booleans. Fixed positions prevent duplicate-field interpretations. Proposed
phase changes map to the existing transaction reducer only after protected
observations authenticate the predecessor and requested operation. Observe
must remain read-only in the future dispatcher. Generic Propose is not itself
a mutation grant or a complete effect receipt; the larger receipt schema in
`docs/ASSURANCE-PROTOCOL.md` remains required.

Initial tests cover field extraction, invalid version/operation/phase bytes,
every short length, oversized lengths, reserved bytes and generation overflow.
Each digest field independently receives a nonuniform pattern while other
fields remain distinct. Both generation fields exercise multi-byte, zero,
maximum-value and overflow vectors.
Independent source review found the accepted-field contracts and test oracles
adequate for the stated syntax-only scope. The fresh archived-source run at
`3ccb545245799c4d4018addbfb110c96ee2ece50` passed all 195 checks across
the policy, reducer, decoder and harness units, with none justified or unproved.
The test helper precondition must be proved at every fixture call; its own
acceptance assertion is not a second independent proof. Missing acceptance includes
decoder/transport integration, expanded boundary/adversarial cases,
authenticated witness creation, shadow differential tests
and Linux-enforced authority separation. Do not describe this prototype as
fulfilling the entire IPC or resource-authority requirement.

The generation golden vector was checked with JACKAL status `exact`,
`parsed=1*256^7+2*256^6+3*256^5+4*256^4+5*256^3+6*256^2+7*256+8`,
result `72623859790382856`. This is exact rational arithmetic, not
`formal-bounded` and not evidence of decoder correctness. The initial call
used the wrong argument name and was refused with `plugin-args-schema`; the
corrected request used the same exact lane, without a weaker fallback.
