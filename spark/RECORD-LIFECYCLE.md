# Authoritative record lifecycle requirements

Status: DESIGN, source-audited starting point for A16–A18/G1. No production
authority, storage migration, retention deletion or compatibility change.

## Source-backed compatibility boundaries

At checkpoint `0af6043ccad441be1ce285ebf029ea44c90e9d87`:

- `siamind.origin_class` accepts explicit origin labels and uses a shipped
  namespace/type table for unlabeled records. Ordinary epochs are evidence;
  JACKAL event/epoch pages are forced derived. `tests/test_sia.py` contains
  explicit compatibility expectations. This classification is not source-event
  authentication.
- `sialib.corpus_origin` reads bounded corpus frontmatter through no-follow
  descriptors; malformed/ambiguous input falls back to legacy-unlabeled.
  Capturing page bytes does not authenticate the event described by the page.
- `siathought.consolidate_corpus` commits before consolidation, requires tracked
  clean sources, protects safety/pinned/open-take days, publishes deterministic
  epoch manifests and removes admitted day files from the working tree.
  Original-byte preservation depends on retained Git history and recovery;
  not every original event remains in current epoch text.
- `siacheckpointcycle.retire` retires controller memo authority under a receipt
  while retaining source/checkpoint/effect archives. It is not general record
  deletion. `siatakes._history_project_retirement` projects tombstones for
  specialized natural-history rows with predecessor/event checks; it is not
  the general source-retention policy either.

These are code-inspection observations, not a new operational fault campaign.
Do not relabel all existing epochs or remove compatibility fixtures to make a
new invariant pass. Protected-record admission needs its own versioned,
authenticated origin/producer bindings. Legacy classification and protected
admission remain distinct until an explicitly qualified migration.

## Immutable identity and separate claims

An admitted record binds exact content digest, producer identity/source domain,
capture identity and ordinal, origin, schema and provenance/parent references.
Changing body or origin creates a new record, not a historical rewrite.
Capture establishes that a producer observed particular bytes under declared
conditions, not that every statement in those bytes is true or every machine
event was captured. A captured model quotation remains a model assertion.
Signatures authenticate bindings, not semantic truth.

| Property | Required meaning |
| --- | --- |
| Record-byte completeness | Exact bytes versus truncated/failed capture, separate from source-window coverage |
| Window coverage | Not observed, unavailable, observed empty or verified complete for an explicit source/window |
| Capture order | Monotonic order within a named capture domain; domain changes/rollover explicit |
| Source-declared time/order | Retained source assertions, distinct from protected capture observations |
| Gap | Known bounded missing interval or explicitly unknown extent; never fabricated emptiness |
| Origin | Immutable source observation, deterministic derivation, model interpretation or legacy-unlabeled |
| Semantic assessment | Separate versioned evaluation with ground-truth provenance and abstention |

Unknown gap extent must not become a fabricated numeric interval. Capturing a
single record does not establish complete window coverage. Counter exhaustion
refuses until an explicitly authorized new domain exists; no wrap or reset.

Artifact provenance and assertion provenance require separate immutable
bindings: authenticating a source log does not authenticate a quoted model's
claim as fact. Do not attempt to express both by rewriting one legacy label.

## SPARK transition requirements

Each operation needs its own exact authenticated grant and current
domain/generation/predecessor joins. Read, publication and retirement authority
are not interchangeable. This table does not freeze schemas or manufacture
trusted observations.

| Operation | Required transition |
| --- | --- |
| Admit capture | New exact identity, validated producer/context/body and explicit completeness; retain original before capture acknowledgment |
| Commit publication | Retained record plus complete generation-bound witnesses; no ready/ack with recovery debt |
| Retrieve | Current exact read grant and admissible retained publication; preserve origin/coverage labels and disclosure limits |
| Publish derivation | New derived/model identity and exact versioned parent manifest; preserve every parent byte, label, coverage claim, identity and grant |
| Retract derivation | Exact target/version and authority; durable tombstone blocks ordinary active use; source parents unchanged |
| Recompute derivation | New identity/version linked to retained parents and algorithm/model configuration; never overwrite the retracted identity or tombstone |
| Retire source from active projection | Explicit retention authority, verified accessible retained original, durable retirement receipt and separate historical read policy |
| Purge authoritative bytes | Not authorized by this mission or initial API; requires separate explicit deletion policy and acceptance |

Retraction preserves the historical audit record. Descendants of a retracted
derivation cannot silently remain eligible for active use: invalidate them or
explicitly validate a new derivation. Failed recomputation cannot reactivate an
old result. Index rebuild/restore must not resurrect retracted/retired aliases.

Preserving parent grants means preserving historical bindings for audit, never
inheriting permission to read or derive after expiry/revocation. New use needs
its own current exact authorization. Missing parent or dependency-closure
evidence is unknown/ineligible, not evidence of no dependencies.

Before freeze, define retraction and projection-retirement as independent
dimensions or one complete precedence table. Cover repeated retraction,
retirement after retraction, ancestor retraction after descendant retirement,
exact replay versus conflicting retry, and recovery debt at each transition.
Do not mark global retraction terminal while a stale descendant remains usable:
either invalidate an authenticated bounded complete closure atomically or
require every active-use boundary to validate current ancestor/tombstone
bindings. A local parent list without completeness evidence cannot suffice.

Retirement must distinguish historical availability, projection absence,
intentional retirement, corruption and unknown outcome. A missing working-tree
file is insufficient. A Git object identifier alone is not evidence of
accessible durable off-host recovery.

## Implementation and acceptance sequence

1. Define bounded immutable descriptors and explicit lifecycle states. Separate
   origin/content/capture/coverage from projection state; specify every refusal
   and unchanged-state postcondition.
2. Prove a deterministic transition planner preserves immutable fields, rejects
   provenance escalation and forbids implicit reactivation/deletion. Its output
   is a proposed transition until protected observations/effects are established.
   Existing observation/proposal classifiers never gain effect authority.
3. Define bounded dependency manifests and parent eligibility. Prove retraction
   cannot make a descendant newly eligible; do not infer full graph propagation
   from a single-record predicate.
4. Bind the planner to the protected actuator and selected resident path.
   Enforce actual durability, identities, disclosure, currentness and resources;
   expose typed degraded/unknown outcomes.
5. Test missing/truncated/reordered capture, exhaustion/domain rollover, every
   identity-field mutation, stale/revoked grants, lost acknowledgment, replayed
   parents, interrupted retirement and rebuild/restore. Include positive
   original-history retrieval and negative bypass controls.

Freeze descriptor/manifest bounds against actual producer/storage budgets
before implementation acceptance. Blanket refusal does not establish that the
required useful operation works. Require strict complete-unit proof,
deterministic/adversarial tests, actual selected-path faults and independent
review on exact source. Capture, authenticity, durability and recovery remain
unproved at the system boundary until the real producer/effect evidence passes.

Independent review recommends the first planner implement only a proposed
retraction of one fixed derived/model descriptor. It must preserve immutable
fields/parents, reject source-record targets and changed identities, return
unchanged state on refusal and preserve the exact original proposal on
identical retry. No I/O, signing, deletion, read grant or terminal descendant
invalidation is implied. Descriptor bounds, replay/conflict state and precise
output classifications must be frozen before this planner is implemented.
