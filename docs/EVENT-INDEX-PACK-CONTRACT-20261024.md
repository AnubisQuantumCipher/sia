# Lossless event-index packing: experimental contract

Status: transport codec TESTED; authoritative lookup, migration, SPARK proof,
installed operation and backup recovery UNPROVEN. This extends the recovery
work under A10/R19; it does not replace any assurance, continuity or release gate.

## Problem and chosen boundary

Installed capsule capture budgets every encountered filesystem child across all
selected roots, including children rejected by exclusions. A bounded metadata
observation reached that budget before completing the source traversal. A second
observation attributed 59,974 encountered files to the corpus event index. These
were unlocked observations, not consistent snapshots or proof of the previous
backup worker's failure cause.

The index is used for occurrence replay and exact epoch/source lineage. It cannot
be omitted as a disposable search projection. Paging a backup manifest or hiding
the original tree inside an archive would not preserve the existing source-record
contract. The proposed change is to the actual authoritative index representation:
lossless bounded packs plus exact legacy fallback. The capsule's current physical
source traversal and limits remain unchanged. No live files have been migrated,
retired, repacked, excluded or deleted.

`bin/siaeventpack.py` is an experimental transport only. No runtime lookup or
publication path imports it. It preserves opaque legacy bytes and grants no
provenance or publication authority. Its unkeyed digest detects corruption; an
attacker can replace payloads and recompute it. Existing source/epoch validation
and the assurance authority boundary must still reject unsupported claims.

## Wire and resource contract

One frame contains, in order: the ASCII magic `SIA-EVENT-PACK-1` plus LF; one byte
of organ length; the ASCII organ; a three-character lowercase hexadecimal prefix;
one byte of record count; a four-byte unsigned big-endian body length; the SHA-256
body digest; then the body. Each body record contains a 64-byte lowercase ASCII
hex event ID, a four-byte unsigned big-endian payload length, and the exact legacy
payload bytes. IDs are strictly increasing, unique and share the expected prefix.
The complete frame must be consumed; truncated or trailing data is refused.

The experimental frame is limited to 65,536 bytes and 64 records. The caller
supplies the expected organ and prefix. Payloads remain uninterpreted by this
codec. These are transport limits, not a replacement for the live owner's record,
JSON, source, epoch, lookup or resource policies. Future integration must freshly
apply those policies before granting any authoritative result.

Framing consumes capacity. A valid legacy record may not fit a pack, and a prefix
may exceed its record or byte capacity. Such records must retain their exact
legacy representation. Neither truncation nor a success cache is permitted.
The present codec is not a proof that every installed group can be packed or that
all future retained history will fit a finite storage budget.

## Required implementation and acceptance

| ID | Requirement | Present evidence / remaining work |
| --- | --- | --- |
| EP01 | Exact bytes, closed framing, routing, ordering, uniqueness, complete consumption and bounded count/length | Independent wire oracle, corruption/truncation and rehashed structural controls; TESTED |
| EP02 | Preserve every supported canonical legacy record | Temporary product-generated consolidation fixture round trip through the original reader; complete installed inventory and maximum-domain proof remain UNPROVEN |
| EP03 | Freshly validate inner event/organ identity, canonical bytes, payload/source identity, epoch lineage and completeness | Existing reader unchanged; forged lineage after valid transport is refused in a fixture; dual-format runtime integration UNRUN |
| EP04 | If both representations exist, compare exact canonical bytes; refuse conflicts or malformed packs even if a legacy leaf exists | Dual-format reader and adversarial controls UNIMPLEMENTED |
| EP05 | Saturated groups and oversized records remain readable via exact legacy fallback | Required design; complete coverage accounting and saturation implementation UNIMPLEMENTED |
| EP06 | Publish and verify a durable pack before retiring any represented legacy entry | Migration journal, filesystem receipts, source-bound comparison and failure injection UNIMPLEMENTED |
| EP07 | Interrupted migration never creates an authority gap or invents completion | Recovery must reconcile exact source/pack generations and uncertain operations; fault campaign UNRUN |
| EP08 | Preserve the original capsule source-record limit and root selection | Capsule implementation unchanged; full post-migration freeze/restore/replay remains UNRUN |
| EP09 | Protected authorization remains in the assurance core | Python codec provides untrusted ingress only; SPARK contracts, proof and enforced integration UNPROVEN |
| EP10 | Exact source evidence, strict analysis, independent review, installed qualification | Scoped source-bound tests and review retained; full system acceptance and release remain OPEN |

A migration transaction must record its exact input paths, byte digests and
source generation; publish a new pack without replacing an unreviewed generation;
verify every represented entry and its current lineage; then retire only exact
legacy inputs under the established authority and lease protocol. Duplicate
representations are permissible only when identical. A crash before, during or
after publication/retirement must leave recoverable evidence and must not be
reported as a completed migration. A complete, reviewed migration and retained
recovery evidence are required before seeking authorization for installed
migration or legacy-file retirement.

## Power of Ten and Ada/SPARK adaptation

The normative rules and rationale remain in the existing Power of Ten assessment.
The following are project adaptations, not quotations or claims of compliance:

- P01/P02: codec control flow has no recursion; loops are bounded by the admitted
  record count. SPARK must establish cursor progress and slice bounds using
  bounded byte-position and record-count subtypes before authority transfer.
- P03: frame and record counts are bounded, but Python allocates dynamically and
  its allocator/runtime memory behavior is not formally proved. A fixed-storage
  SPARK representation and measured whole-job budget remain required.
- P04/P05: short routines and explicit refusal conditions; round-trip tests are
  supplemented by an independent wire oracle and hostile frames. Whole-system
  correctness, cryptographic implementation and OS durability are not inferred.
- P06/P07: immutable bytes cross the codec boundary; no filesystem, network,
  migration or authorization capability is present. All framing failures refuse.
- P08/P09: no generated control flow, caller callbacks or raw pointer operations
  in the codec. CPython, regular expressions and hashlib remain assumptions.
- P10: the selected strict static profile and original lineage regression roster
  are retained. Scoped passing analysis is not comprehensive Python-runtime or
  Ada/SPARK proof, certification, or permission to release.

This design follows the available Ada high-integrity guidance on choosing a
tractable verification model before implementation. Planned SPARK obligations
include positive payload lengths, monotonic cursor progress, all slices within
an admitted fixed byte buffer, strict record ordering and complete frame
consumption. None has been compiled or discharged for this transport yet.

## Retained observations at this checkpoint

The final exact-source codec/legacy-lineage roster passed 49 tests in 6.295s
under the original isolated 60-second job envelope. The selected strict static
profile reported no diagnostics for this new codec, its tests and named drivers.
This does not close inherited repository-wide findings. Independent actual
GPT-6.1 source/raw review did not execute the tests.

A later index-only metadata scan acquired the existing corpus lease after an
initial nonblocking attempt correctly refused while the resident daemon held
it. Under the unchanged bounded observation envelope it encountered 62,507
filesystem entries and 59,974 legacy index files. Their recorded sizes and IDs
grouped into 16,034 proposed packs with no metadata-sized overflow group. The
scan did not read or validate legacy payloads or epoch lineage. It cannot prove
that those packs are valid, that the complete corpus fits after migration, or
that a backup can be restored. The earlier refusal and both observations remain
retained privately; only aggregate metadata is reported here.

Next: implement the dual-format reader with exact duplicate/conflict handling
and fresh original validation, then durable publication and crash-safe migration.
No migration, legacy-file retirement or installed format activation is authorized
by these test/review results.
