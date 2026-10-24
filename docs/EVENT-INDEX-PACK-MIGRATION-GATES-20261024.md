# Pack activation and migration gates

Status: design and current-source gap assessment, not an implemented protocol or
authorization. The tested experimental occurrence join is insufficient to enable
packed storage. Normal runtime remains legacy-only. Original EP01–EP10 and all
system assurance gates remain binding.

## Consumers that must agree

The current source has these distinct uses of event-index evidence:

| Consumer | Current source | Required qualification before retirement |
| --- | --- | --- |
| Cross-day occurrence lookup | `siathought._join_event_index_occurrences` | Experimental grouped fixture path exists; normal runtime, complete captures and all original semantic controls still require qualification |
| Consolidation conflict preflight | `siathought._preflight_event_index_entries` | Must see exact packed evidence as well as legacy evidence; absent legacy alone must not authorize a conflicting replacement |
| Consolidation index publication | `siathought._publish_event_index_entries` | Must retain idempotence and conflict refusal with packed entries, including old pack plus newly published legacy fallback |
| Compacted-source outcome inspection | `siaconsolidationoutcomes._verify_compacted_source` | Must prove every expected occurrence has exact index and epoch/source lineage after source removal; occurrence-reader tests do not qualify this consumer |
| Capsule and restore | Complete selected-root traversal and existing restore gates | Pack files, source history and migration evidence must be included in the actual bounded snapshot and verified after off-path restore |
| Installed clients and downgrade | CLI, resident daemon, MCP and supported harness paths | Qualify actual loaded implementations, not just files on disk; reconcile in-flight clients and enforce supported-version/format compatibility |

This is an inventory of named current call sites, not proof that dynamic dispatch,
external consumers or future code cannot introduce additional readers. A source
bound call-site inventory and runtime integration controls must accompany the
activation change. A legacy-only process cannot be assumed compatible after
retirement merely because the experimental reader passes.

The subsequent consumer checkpoint adds fixture evidence for preflight,
identical-entry publication/replay and actual compacted-source outcome inspection,
and repairs a legacy publication gap where the second read silently skipped a
conflicting entry. It also demonstrates a known write followed by stale-capture
refusal when a read-only substitution is used for new publication. See
`EVENT-INDEX-PACK-CONSUMERS-20261024.md`. This does not qualify the mutation
adapter, activate the reader or close the table's retirement requirements.

`EVENT-INDEX-DELTA-20261024.md` subsequently records an unactivated captured
legacy-fallback writer, exact intended-write observation and shared capture
ownership repair. Its fixtures include known effects followed by refusal and
fresh retry. It does not supply a durable migration journal, protected permission,
original payload authentication, source retirement or installed qualification.

## Transaction invariants

- The source of truth is the exact admitted legacy/pack bytes, their stable
  identities and original epoch/source lineage. A proposed packing plan, checksum
  or model summary cannot grant permission or establish semantic truth.
- One whole-operation admission binds task/corpus identity, current source
  revision and generations, organ/prefix, input and fallback roster, exact new
  bytes, expected old target, resource limits, authority scope and operation ID.
  Python supplies observations; the protected assurance boundary must decide.
- Every selected legacy input is represented by identical canonical bytes in the
  verified pack or remains as an exact legacy fallback. No truncation, implicit
  omission, reset of an aggregate budget, or silent replacement of an old pack.
- Before any selected legacy unlink, the complete represented roster, current
  lineage, target bytes and durability obligations must be verified. An existing
  target with different bytes is a conflict until an explicitly qualified
  replacement transition authorizes it; it is not a retry success.
- All meaningful filesystem, Git, journal, projection, receipt and signing
  results must be checked. Failed or uncertain durability blocks retirement and
  readiness. A successful rename alone is not durable publication.
- The existing generation/readiness/acknowledgment predicates remain required.
  Index metadata being absent from rendered prose does not waive corpus, ledger,
  projection or recovery requirements. No completion is inferred from scheduling.

## Proposed durable phases and recovery decisions

| Phase | Required durable evidence | Recovery after an interruption |
| --- | --- | --- |
| Prepared | Source-bound admitted plan and protected operation identity; old source still intact | Revalidate current inputs and authorization before attempting publication; changed inputs refuse |
| Target published | Bounded target write and checked file/parent durability; exact target generation and bytes verified | If target is absent, do not invent success; if different, refuse; if identical, re-establish all required durability and lineage before proceeding |
| Retirement in progress | Exact verified coverage plus authority for each selected input; checked directory durability and retained progress | Reconcile every selected input as exact-present or absent under this operation; unexpected bytes, missing target, unknown history or mismatched identity refuse |
| Storage transition complete | Complete selected roster reconciled, no unaccounted inputs, final directory/source generations retained | Continue the original corpus publication protocol; storage completion is not readiness or acknowledgment |
| Published | Matching durable corpus generation, projections, ledger/receipts and no recovery debt | Only the existing protected publication authority may allow reads or acknowledgment |

These are abstract obligations. No journal schema, signing format, actuator,
SPARK transition implementation or crash-consistency proof is supplied here.
Atomicity under power loss, filesystem semantics, Linux isolation and cryptographic
implementations remain explicit environmental and system-test obligations.

The failure campaign must interrupt before and after every durable operation,
including journal creation, target write/fsync/rename/parent fsync, target readback,
each legacy unlink and parent fsync, final reconciliation, corpus commit,
projection synchronization and acknowledgment. Include partial writes, ENOSPC,
I/O errors, stale generations, replacement/symlink attacks, duplicate/conflicting
targets, missing inputs, interrupted retries and concurrent supported clients.
Check exact recoverability, no duplicate external action, no invented success,
and the original resource envelope at every terminal outcome.

## Compatibility, correction and retention

An initial read-compatible deployment must qualify every required consumer before
storage retirement. Temporary duplicate representations are permitted only when
exactly equal. They consume real storage and capsule entries; duplicates are not
a backup-capacity repair. Actual post-transition source traversal must fit the
original capsule contract, including retained migration evidence and fallbacks.

Pack replacement/extension, source corrections, deletion and retention must each
have explicit source-bound transitions. The implementation must not make a
deleted/corrected record retrievable through an old pack, restored checkpoint or
derived descendant. An immutable-file shortcut that prevents authorized correction
is not acceptable. Conversely, cleanup cannot destroy required recovery evidence
or silently discard authoritative history. These policies remain unresolved until
the corresponding transitions and recovery tests exist.

A supported downgrade requires reconstructing and verifying complete legacy
coverage under a qualified transition before an old reader can become active.
Managed installers, resident services, MCP clients and offline restore procedures
must agree on the deployed format. Uncontrolled manually launched old binaries
or hostile same-user processes are not made safe by a cooperative corpus lease.

## Current acceptance position

EP01 wire framing and EP03/EP04 captured validation have scoped test evidence.
EP02 complete installed coverage and EP05 complete capacity/fallback planning are
still open. Complete-request fixtures and resource refusals add evidence, not a
maximum-domain proof. EP06/EP07 durable publication, retirement and recovery are
not implemented by the reader. EP08 actual capsule/restore, EP09 protected SPARK
authority, and EP10 full independent/installed/release qualification remain open.

The next implementation must first qualify all named consumers and a bounded,
deterministic exact-coverage plan. Then prove/admit the protected transition and
test its actual filesystem adapter. No live migration or legacy retirement should
precede those gates. This work does not resolve R05, qualify the failed full writer
or native admission, or establish avionics-level/whole-system assurance.
