# Captured pack proposal and plan identity

Experimental, inactive, source-correspondence implementation. This joins the
existing captured transport planner to the existing SPARK retirement proposal
wire. It does not authenticate a producer or authorize publication or deletion.
The original transport entrypoint and its legitimate no-target outcomes remain
unchanged. The new retirement-proposal entrypoint refuses a no-target outcome.

`siaeventpackcapture.prepare_proposal` returns the immutable tuple:

```
(frame, selection_manifest, fallback_manifest, capture_manifest, transport_result)
```

The caller owns the same live capture and corpus lease throughout. One attempt
per organ/prefix retains its reservation even on failure. Later use requires
fresh source, policy and authority validation. The observation is not atomic,
perpetual, a complete corpus inventory or an authenticated source assertion.

## Exact representation

Each record manifest is ASCII `SIA-PACK-RECORDS-v1` plus a zero byte, an
eight-byte unsigned network-order count, then ordered records consisting of raw
identity digest (32 bytes), SHA-256 of exact payload bytes (32 bytes), and an
eight-byte unsigned payload length. Empty manifests retain their header/count.
Selection includes every caller-selected identity; represented and fallback
inputs form its exact partition. Fallback records must still have captured,
byte-identical legacy originals. Target records are exactly the union of prior
and represented records; differing overlap, extra records and omissions refuse.

Generation digests cover the complete existing capture generation mapping.
Presence comes from that same capture, including explicit absence. A represented
original's absence is not inferred from pack membership. The prior target is
also observed through the capture and distinguishes absence from present bytes.
All prior records remain subject to the original lineage/conflict checks.

Except PlanID, digest preimages have the form:

```
ASCII("SIA-PACK-") || label || ASCII("-v1") || NUL || payload
```

| Label | Exact payload |
| --- | --- |
| `CORPUS` | Canonical JSON of actual capture root identity |
| `ORGAN`, `PREFIX` | Validated route's exact ASCII bytes |
| `CAPTURE` | Complete capture manifest bytes |
| `SELECTION`, `FALLBACK` | Corresponding complete record manifest bytes |
| `TARGET` | One zero byte for absent prior; one byte of value 1 followed by exact pack bytes for a present target |
| `LEGACY-GENERATION` | Canonical JSON of the complete observed legacy generation |

Canonical JSON uses the existing bounded serializer: sorted keys, compact
separators, UTF-8, no ASCII escaping or non-finite values. The capture manifest
has schema `sia-pack-capture-v1`, ordered policy names/values and the complete
existing `capture.dependencies()` representation. It is taken after source
reads. It covers captured dependencies, not all files in the corpus.

The existing wire's epoch, transaction, revision and permission fields receive
an exact native tuple supplied by the caller. These remain **untrusted reference
inputs**. The protected boundary must independently select and match their
meaning and authority; including them in a hash does not establish either.

PlanID follows the existing wire contract: SHA-256 of ASCII
`SIA-PACK-PLAN-BINDING-v1`, NUL, frame bytes 1–8 and 41–16,384. Only its own
identity slot is excluded. The Python `identity_matches` helper checks this
representation relationship only. The SPARK decoder deliberately does not check
the hash. Both checks and independently authenticated observations are needed at
the future protected boundary; neither current component grants effects.

## Resource accounting and source validation

Before source planning, the new reservation covers four complete manifest-sized
buffers, eight fixed frames and 4,096 bytes of generation scratch. Four manifest
buffers conservatively cover retained selection plus transient reference bytes,
joined bytes and fallback output. Eight frames cover bounded rosters, generation
digests and frame construction/hash copies. Existing planner reservations remain
in force; no whole-operation budget is reset or raised.

Before creating the dependency view, another logical envelope reserves 4,096
bytes plus 1,024 per captured file/directory. Existing strings, generations and
directory entries are borrowed. After bounded size calculation, twice the exact
serialized JSON size plus 4,096 is reserved before serialization. These are
logical payload/envelope charges, **not a proof of CPython object allocation,
peak heap use, allocation-failure behavior or maximum-domain throughput**.

After all serialization, hashing and framing, the wrapper checks current policy,
the complete retained capture, then policy again. Missing leases, foreign
captures, changed generations/bytes, changed relevant policy and resource
exhaustion refuse. Cooperative lease and endpoint checks do not isolate hostile
same-process code or detect every transient change.

## Verification and retained failures

The first Python candidate passed 366 tests, but its reservation argument and
cross-language qualification were incomplete. The revised source passed the
original regression workload plus new controls: **367 tests, no skips**, including
the actual pinned native probe, under the unchanged 60-second isolated job cap.

The test-only Ada probe reads exactly one fixed frame, invokes the actual SPARK
decoder and prints every field re-encoded by the existing independent test
oracle. Complete byte comparison covers legacy-only, pack-only and saturated
prior/fallback plans. Controls exercise malformed policy fields, short/trailing
input, and a changed identity slot that remains decodable but fails the Python
hash check. This last control explicitly preserves the authentication limitation.

Strict compiler warnings initially refused the probe's unused updated file state
and newly redundant body imports. Those failures and source snapshots are
retained. Checked closed-file state and removal of redundant imports repaired the
issues without suppression. The final strict build passes. All original Ada
fixture bodies remain intact, apart from the redundant imports: **188 retirement
and 19,508 wire controls pass**. The test oracle's existing encoder is now exported
for the probe; no production Ada/SPARK source changed in this increment.

A coherent substitution of the captured generation digest, followed by normal
frame hashing, causes the unchanged independent complete-frame fixture to fail.
Other controls cover coherent source/target substitution, omitted selection,
fallback substitution, post-hash source/policy changes and every frame-byte hash
mutation. These finite tests are not proof of source authenticity or retrieval
semantics. No fresh GNATprove execution is claimed here.

The probe is test infrastructure, not qualified production IPC, filesystem
cleanup or error-preservation behavior. Its test is explicitly skip-capable on
machines lacking the probe; a skipped run is not integration evidence. The local
qualification receipt records the actual binary and execution without skips.

See `EVENT-PACK-CAPTURED-PROPOSAL-EVIDENCE-20261024.json` for commands, source and
binary hashes, output and failure artifacts. Static checks use the existing
pinned partial correctness profile without suppression. Independent GPT-6.1
review is read-only, not independent test execution.

## Power of Ten and remaining gates

These are project adaptations, not quotations of Holzmann's original rules.
Direct bounded traversal and small helpers address rules 1, 2 and 4. Explicit
logical reservations address part of rule 3; dynamic-runtime allocation remains
unproved. Source correspondence, exact native types, retained failures and final
revalidation address rules 5–7. Explicit versioned layouts and fixed dispatch
address parts of rules 8–9; Python runtime/library behavior remains trusted.
Strict Ada compilation and scoped static checks address part of rule 10. The
existing normative assessment and full original assurance obligations still apply.

The prior wire report's historical statement that the general proof checker
rejects overloads is superseded by checkpoint `2c8c387` and
`PROOF-SUMMARY-OVERLOADS.md`; full-system proof acceptance remains open.

Next required work is an authenticated, current protected producer/admission
path, source/manifest custody verification, actual durability and retirement
reconciliation, fault injection, and installed/capsule compatibility. The native
witness's strict-analysis failure remains unresolved. Original full writer,
proof, harness, held-out retrieval, recovery, cockpit, release and marketplace
gates are not waived. R05 remains UNVERIFIED/PENDING: useful expensive reuse and
fresh policy validation are both mandatory. No SOUL installation or live
migration is enabled. This increment is not whole-system or avionics assurance.
