# Exact event-pack coverage planning

Status: TESTED unactivated transport planner. No runtime imports this planner;
source-reference inventory is not proof of loaded-runtime custody. No installed
migration, source retirement, protected authorization or recovery is accepted.

## Complete input, explicit fallback

`siaeventpackplan.plan` handles one organ and one three-hex-digit prefix. Input
is an immutable, strictly ordered tuple of native `(identifier bytes, raw bytes)`
records and an optional existing pack. It returns an immutable tuple containing
pack bytes or `None`, represented inputs, and fallback inputs. Every admitted
input appears exactly once in the two disjoint input partitions, with identical
bytes. Prior records absent from the input remain in the pack but are not
invented as input-partition members. Representation is not deletion permission.

Complete native-shape, ordering, routing, count and logical-byte preflight occurs
before selection. Identical prior overlap consumes no extra pack slot; differing
overlap refuses the complete request. An invalid record never becomes fallback
merely because the pack is full. A valid raw record exceeding available frame
space remains legacy fallback. Current raw-policy violations, malformed prior
packs and aggregate input-limit violations refuse instead.

Selection is deterministic in input ID order. It preserves every old pack record,
continues after a non-fitting record, and globally sorts the final pack. It is
not a maximum-packing algorithm. Empty input without an old pack returns no pack;
empty input with an old pack preserves it. No-change and saturated operations
preserve the exact prior frame. Creating new storage is not an effect of planning.

The codec's validated `header_size` helper is now shared with its encoder. Tests
compare it to an independent wire oracle for short and maximum-length organs.
Existing codec wire and corruption controls remain in the expanded roster.

## Resource and authority boundary

The caller supplies a native tuple of current observed ceilings: request input
count, per-record raw bytes, and logical serialized input bytes. Hard ceilings
match current source constants: 65,536 records, 65,536 bytes per raw record and
16,777,216 logical input bytes. Smaller observed ceilings are enforced. These
caller-supplied values do not establish custody of current policy or permission.
The count limit bounds this request, not the complete corpus or all prior records.

Logical input accounting includes a header, the complete prior frame and each
input's 68-byte record framing plus payload, including identical overlap. It is
checked before building selection maps or candidate frames. Output remains
separately bounded by the codec's 64-record and 65,536-byte limits. Decoding and
encoding allocate temporary byte buffers; tuples, maps and sorting have Python
object overhead. Neither logical byte count proves total Python memory, absence
of allocation failure, or whole-transaction execution cost. Trusted helper
implementations and CPython remain explicit premises.

Original filesystem dependency-capture budgets remain separate. A caller cannot
reset those budgets per prefix, treat this partial group as a global inventory,
ignore fallback files in a capsule, or claim a complete migration from one plan.
Source payload truth, epoch lineage, exact generations, lease ownership and
protected SPARK decisions must still be established in the applying transaction.

## Verification and remaining gates

The final source passed **338 tests in 45.135s**, exit zero; whole-job elapsed was
45925560749 ns and endpoint source inventories matched. The unchanged prior
324-test roster ran with the new planner controls under the original isolated
60-second deadline, five-second grace, 2 GiB address-space, 512 MiB file-size,
zero-core and exclusive workload lock. No job cap was increased.

Controls cover independent framing, exact-fit/one-byte-over frames, long organ
names, oversized-first/smaller-later selection, full-pack saturation, interleaved
prior/new IDs, duplicate/conflicting overlap, empty/no-change cases, lowered
limits, malformed/rehashed prior frames and hostile native subclasses. A real
65,536-record synthetic input with small payloads verifies the complete partition;
the over-count and over-byte controls refuse. This is not simultaneous maximum
payload/count qualification or measured packing of the installed corpus.

The selected 167-rule profile reports zero findings for planner, codec, new tests
and retained drivers. Their routines are at most 60 physical lines. Original
whole-module/repository findings remain; this is not repository-wide P10 success.
No recurrence or recursion is introduced by the planner; finite native input
counts bound its loops, while Python/native sorting and allocation remain outside
SPARK proof. The original Power of Ten text is normative; these are adaptations,
not Holzmann quotations or compliance certification.

EP05 now has a tested exact transport partition and saturation policy. Complete
captured planning, current source authentication, full-domain cost compatibility,
protected transition proof, durable journal/publication/retirement and recovery
remain open. Correction, deletion, retention and downgrade are not implemented by
this planner. Next integrate a complete source-bound plan through the protected
transaction and fault-test its actual filesystem adapter before any activation.
All original assurance, installed recovery, harness and release/catalog gates
remain binding; universal lossless compaction is not claimed.

The renewed R05 approval claim is corrected in
`R05-AUTHORIZATION-RECURRENCE-20261024.md`. Original reuse and fresh-validation
requirements remain open; this transport planner does not rely on retiring them.
