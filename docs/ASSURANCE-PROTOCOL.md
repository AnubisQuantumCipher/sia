# Authority and transaction refinement contract

Status: DESIGN, not implemented enforcement. Baseline and complete acceptance
scope are in `ASSURANCE-GOAL.md`. The initial pure predicates are only one
component of this design.

## Authority domains

The operator's desktop account runs CLI, MCP, UI and source adapters. Treat
their requests and supplied evidence as untrusted at the new boundary. Do not
give that account write access to protected authoritative storage or the new
signing key. Another process under the same unrestricted UID is insufficient.

A dedicated service identity owns the authoritative corpus, transaction
journal and signing authority. Its installed executable and policy binary
must be administrator-owned and not writable by clients. A narrow broker
authenticates the caller, decodes the bounded protocol, obtains observations
from protected descriptors, asks the policy, executes exactly the admitted
operation and verifies its post-state. The broker is part of the trusted
computing base until its operations are separately verified. A SPARK verdict
does not make an unverified broker trustworthy.

Indexing receives a read-only export for one authorized generation and writes
only its disposable projection area. It cannot modify the authoritative
corpus, transaction journal or signing identity. Its Linux confinement must
deny provider egress while allowing only the intended local embedding path.
Ordinary loopback TCP is not selective authority: a network namespace with a
deliberately exposed embedding endpoint or equivalent enforced broker is
required. This design decision needs an executable containment test before
choosing the shipping implementation.

Judging uses a different service and a grant binding recipient, operation,
exact evidence digest, byte ceiling, transaction identity and expiry/replay
state. It cannot fetch arbitrary corpus content or inherit unrestricted
indexer access. An operator-authorized memory reply can still be forwarded by
an MCP consumer; SIA cannot promise confidentiality after that authorized
delivery. Administrator/kernel compromise remains outside this boundary.

Migration must preserve existing signing identity, receipt compatibility,
rollback and recovery paths. Do not silently move a live corpus or replace a
key. First build and test the authority domains on disposable state, then
define an explicit, recoverable installation migration with rollback evidence.

## Protocol requirements

Use a versioned, fixed maximum-size frame. Decode integer widths, enumeration
values, lengths, reserved fields and trailing bytes explicitly. No pointers,
native record layouts, dynamic object deserialization or caller-chosen paths
cross the boundary. Unknown version/operation, malformed UTF-8 where text is
allowed, overflow, truncation, duplicate fields and excess input all refuse.

Every command binds the caller's authorized capability, operation, source
identity, transaction digest, predecessor generation, target generation and
payload digest. A query receives observations only; it cannot create a write
grant. Grants cannot be reused for another recipient, payload or transition.
Authenticate a durable predecessor before choosing the next generation;
generation exhaustion refuses rather than wrapping.

The authenticated receipt schema must include the protocol version, operation,
caller capability identity, transaction binding, before and after phases,
predecessor receipt digest, complete effect/witness manifest and result. Its
digest is over a canonical bounded encoding; the signature covers that digest
and its domain separator. Matching receipt digests count as the same operation
only after this schema and signature are verified. No caller-selected subset
of material fields may be omitted. The durable state record must authenticate
the current phase and receipt chain. An arbitrary deserialized state, even if
its Ada representation is valid, must never become authoritative.

Requests cannot supply authoritative `durable`, `signature_valid` or
`recovery_complete` flags. Only the protected observation boundary may create
such typed witnesses after actual readback/verification. Each witness binds
the exact artifact, transaction and operation, not just an epoch number.
Readiness holds its generation lease through returned evidence detachment.

Failures are typed: malformed input, unauthorized caller, wrong predecessor,
wrong transaction, missing artifact, invalid signature, incomplete durability,
resource exhaustion, recovery debt, replay conflict and unavailable service.
Timeout never implies successful mutation. A client with an unknown outcome
queries the same operation identity; it does not issue a fresh transaction to
hide ambiguity. Bounded retries preserve failure receipts.

## Durable transition table

This table refines the existing source-effects/ACK ordering. It is a design
mapping, not a claim that one model step is one atomic filesystem operation.
The implementation must enumerate individual rename/fsync boundaries beneath
each row before crash testing.

| Durable state | Next admitted operation | Required evidence before advancing |
|---|---|---|
| Retained source and live binding | Publish corpus closure | Exact immutable batch, admitted provenance, held predecessor and bounded complete plan |
| Corpus committed | Synchronize projection | Actual Git object/tree and clean generation witness for the admitted closure |
| Index bound | Export graph/status | Pinned engine and source-scoped readback bound to the same corpus generation |
| Graph/status bound | Publish live/effects receipt | Graph/status/live candidate joined; pending WAL retained until post-state readback |
| Effects committed | Archive effects receipt | Exact retained source, effects and live-generation join; runtime readiness still closed |
| Effects archived | Archive source | Reopened immutable effects archive and exact batch identity |
| Source archived | Settle refusals | Declared refusals only; no deletion or invented source success |
| Refusals settled | Publish each journal cursor | Each cursor is exact before or target; bounded declared order |
| Journal cursors durable | Publish main cursor | All journals and archives still match; main is exact before or target |
| Main cursor durable | Commit ACK/ready memo | All identities revalidated; pending authorities retired and ready receipt published last |
| ACK committed | Serve memory or begin next capture | Complete committed record, no recovery debt, independently revalidated readiness |

Empty sources and unchanged corpus/index content must use explicit witnessed
reuse, not fabricated writes. Source completeness remains distinct from the
number of produced pages. The notification acquisition fence and capturable
predecessor are not readiness and cannot be mapped to ACK committed.

## Recovery rules

For each individual durable operation, recovery admits only its authenticated
before state or exact intended after state. A third state refuses. An exact
completed retry returns the original result without another signed transition;
a repeated operation ID with different bytes refuses. Recovery does not infer
success from missing files, timestamps, a client's timeout, or a green status
projection. Retain intent, before/after identities and receipt until completion
is independently observable.

Crashes may occur before or after each write, rename, fsync, receipt append and
cursor publication. The model must include lost volatile state, durable-prefix
replay, corrupt/missing artifacts and stale observations. Safety must hold
without fairness; eventual completion may assume only explicitly documented
eventual availability and scheduling. Endless crashes do not imply liveness.

## Acceptance before authority transfer

Require a finite-state publication/restore model with stated bounds and checked
safety properties; SPARK transitions corresponding to that model; independent
test oracles; actual crash injection and restart through the resident front
door; refusal of hostile IPC, replay and direct same-user writes; network
negative controls with a working authorized positive control; and independent
offline reproduction. Preserve model counterexamples and failed executions.

The Linux/crypto/filesystem observation layer remains an explicit assumption
until its acceptance evidence exists. No new release claim may describe this
design, the pure predicate proof or a shadow comparison as enforced system
assurance.
