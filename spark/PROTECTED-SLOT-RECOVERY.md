# Protected-slot recovery authority proposal

Status: DESIGN PROPOSAL, not a frozen schema, implemented recovery path or
enforced permission. This resolves policy choices left open by
`PROTECTED-SLOT-CONTRACT.md`; canonical persistent-record schemas, proofs,
fault cuts and commissioning still must be completed. Existing APIs and
accepted retry behavior remain unchanged.

## Separate authorities

New publication, recovery of an admitted operation, and outcome disclosure are
distinct decisions. None implies either of the others.

- New publication requires the current exact publication grant and all current
  principal, clock, boot, service, predecessor and resource joins.
- Recovery requires authenticated retained admission evidence and independently
  provisioned current recovery permission for that exact operation. A visible
  final intent is not evidence that its previous directory sync succeeded.
- Outcome disclosure requires the current exact Query grant and the original
  immutable operation/publication-request identity. Recovery alone returns no
  outcome to an unauthenticated client.

Before new admission, the administrator must provision a separate recovery
permit for the intended operation. It binds fixture, protocol, complete O,
historical Publish request digest, predecessor state/receipt identities, target
payload identity, the recovery-policy version, and the permitted intent,
receipt and state signer identities/profiles. It permits completion of that
admission only; it cannot authorize a different request, another generation,
another transaction, rollback, new genesis or disclosure.

The permit resides in a fixed administrator-controlled slot whose ancestry
the service and desktop UIDs cannot replace. Its signature is checked against
an independently configured administrator recovery-issuer key. No client
pathname or embedded key selects authority. This is a new persistent record,
not an extension silently appended to an existing request or grant. Its byte
schema, purpose label, golden vectors and byte budget remain required before
freeze. It must not reuse any request/grant signature or hash domain.

The administrator also controls a bounded current recovery-control record:
the exact permit identity, control epoch and enabled/disabled state. Admission
and every recovery critical section require its authenticated, current enabled
view. Revocation/replacement must serialize with observation and execution
through the same protected service lease. The root-owned control plane, durable
epoch publication and rollback detection remain implementation obligations;
a stale signed file or a client-supplied epoch is not a current observation.
The monotonic freshness anchor must be independent of the possibly rolled-back
control record. Its protected storage, atomic update/readback, restart behavior
and bounded retention remain OPEN; no currentness producer is implemented.
Issuer, key/profile, allowed actions and fixture role need independent pins.
Separate signature-purpose names do not establish separate OS key custody.

## Intent publication and durability uncertainty

This proposal chooses narrowly authorized reconciliation of an authenticated
final-named intent. A restart may verify that intent and, under the exact current
recovery permit/control, complete its file and parent synchronization. It must
not infer historical durability from visibility, timestamps or an encoded flag.
No payload effect is permitted until those synchronizations succeed in the
current execution. A failed synchronization preserves debt.

An absent final intent with only pre-admission staging grants no such authority.
Creating or publishing an intent then requires fresh new-admission authority;
staging is never promoted under recovery permission alone. Final intent creation
requires:

- the canonical original Publish envelope and exact protected publication grant;
- actual admission principal, boot/service/clock domains and admission tick;
- the exact recovery permit and control epoch observed during admission;
- authenticated predecessor state and receipt identities;
- canonical target payload identity and fixed signer/domain assignments.

These values are authenticated in the intent under its separately pinned
intent-signing role. The original envelope must bind the same O and historical
request digest retained in every later record. A signature only authenticates
the encoded statement; descriptor observations and durable ordering must still
justify its claims. The intent's own final publication and parent synchronization
must complete before any payload effect.

The temporal admission contract remains OPEN: validity at an authenticated
sampled admission tick and validity through durable intent publication are
different guarantees. The lease does not stop time. Neither this proposal nor
an earlier validity Boolean establishes the latter guarantee. Freeze the
admission linearization rule, expiry checks and corresponding crash table
before implementing either interpretation; do not change existing grant
lifetime semantics by implication.

The experimental candidate and its finite model are described in
`model/ADMISSION-RECOVERY.md`: validity at the protected sample, with current
independent recovery permission gating later effects. This candidate explicitly
allows post-expiry completion and does not yet close the temporal freeze gate.

For an authenticated final intent, write-grant expiry, write-grant removal or a
new service epoch prevents new admission but does not erase retained evidence.
Recovery uses the retained historical context and the current independently
enabled recovery permit. It never rewrites historical A to match the new service.
The restarted service still must authenticate its own current identity and
protected store; accepting an old intent does not exempt executable or ownership
checks.

Ordinary uninterrupted continuation requires the same recovery authority as
restart recovery. The proposed lock discipline is one serialized section per
durable phase, with exact current permit/control revalidation before each
phase's signing or filesystem effects. Release the lease after each phase;
the next phase cannot reuse the preceding control observation.
On reacquisition, revalidate the authenticated predecessor/artifact generations
and all operation joins too; cached policy verdicts or earlier witnesses cannot
remain authority across lease release. Administrator
updates must participate in this same protected protocol. Revocation becomes
effective only at its serialized durable control update, not when requested.
Phase deadlines, failure interruption, lock fairness and bounded revocation
latency remain freeze obligations; no numeric latency guarantee is established.

## Revocation and key availability

The recovery rows below govern incomplete transitions and startup reconciliation.
After completion has been independently established for the running service,
an effectless Query uses its own current read authority and retained verification
trust; it does not require a new publication or recovery permission. A restart
that requires retirement reconciliation must finish that recovery first.

| Observation | Required behavior |
| --- | --- |
| Publication grant revoked with only pre-admission staging | No new admission or payload effect; no recovery inferred from staging |
| Final authenticated intent visible but prior parent sync unknown | Exact current recovery permission may authorize intent synchronization; no payload effect until synchronization succeeds |
| Publication grant expires after final intent publication; exact recovery permission remains enabled | Reconcile durability first, then resume only the retained operation through its admitted before/after states |
| Recovery permission disabled, missing, stale, conflicting or unauthenticated | Preserve debt; no further recovery effect, signing or terminal completion |
| Recovery control changes while another critical section owns the lease | Serialize; acknowledge revocation only after the preceding section exits and the new control record is durable |
| Old signing key unavailable and no complete valid retained signed artifact exists | Preserve debt; do not sign under a replacement key or change historical identity |
| Original valid signed artifact exists and its pinned verification key remains trusted | Verify and reuse those exact bytes; possession of a new signing key is irrelevant |
| Verification trust for a required historical key is withdrawn or uncertain | Refuse the dependent state/receipt/intent; retain evidence for administrator recovery |
| Proposed key/profile rotation during pending recovery | Refuse automatic migration; require a separately specified and accepted transition |

Revocation is not retroactive undo of a completed durable effect and does not
prove that previously disclosed bytes can be recalled. A disable request may
wait for the currently serialized section; the caller cannot infer effective
revocation from merely submitting it. The section's completion/deadline and
administrator response must be explicit in the implementation. Failure to make
the control update durable cannot produce a successful revocation acknowledgment.

The initial fixture does not implement key rotation, remediation of withdrawn
verification trust, or re-enabling a disabled recovery permit. Ordinary control
disable must preserve debt and refuse subsequent effects. Replacement keys,
permits or an unexplained enabled record cannot resurrect the operation.
It preserves the operation and fails closed when unsupported remediation occurs.
This is not permission to silently drop production rotation requirements.

## Signature uncertainty and canonical replay

Receipt content is determined by the admitted operation and the durable
observations required by its schema. It must not include a fresh retry timestamp,
current service epoch, random nonce or other changing value. Any necessary
observation value must be authenticated and durably retained before its first
signing attempt. The same stability requirement applies to state content.
Intent creation uses fresh admission observations under the still-to-be-frozen
temporal contract; recovery may reuse its authenticated final bytes but cannot
manufacture a missing intent from staging or client-supplied replacements.
Their purpose labels and signer roles are distinct; a receipt signature cannot
be interpreted as a state or intent signature.

If the final signed artifact is present, verify the complete canonical bytes,
independent key pin and all operation/predecessor joins before reuse. An invalid
or conflicting final artifact is corruption, never a request to overwrite it.
The pre-final staging namespace needs an explicit finite recovery table: only
declared interrupted-write states may be discarded or completed. No broad
cleanup rule may erase a conflicting signed record.

For post-intent receipt/state artifacts only, if no accepted final artifact is
present, the original signing attempt may have
occurred without durable retention. Current recovery permission may allow
re-signing exactly the retained canonical input under the original designated
key/profile. Every signer-input field must come from the authenticated final
intent or a named authenticated successor record in the frozen dependency
schema; a missing field cannot be supplied by a retrying client.
This claims one canonical accepted artifact, not one signer
invocation. No receipt or terminal response is accepted before durable retention,
independent verification and the parent contract's state/retirement joins.
If canonical reconstruction or signing identity is uncertain, retain debt.

Completed authorized queries return retained receipt bytes without signing or
writing again. Startup reconciliation of interrupted intent retirement remains
a separately authorized recovery action, including required parent
synchronization. An absent intent does not by itself establish completion or
permit genesis. The committed state must retain sufficient authenticated recovery
bindings for the parent's absent-intent finalization branch: exact original
permit identity, original admission control epoch and canonical intent identity,
as well as the operation, predecessor, receipt and payload joins. Current
authenticated control must enable that exact permit before synchronization or
debt retirement. This branch cannot sign, create a new publication or infer
admission from an absent file.

Persistent record dependencies must be acyclic. The permit binds the request,
predecessor, payload and assigned signers, not a future intent signature.
Intent binds the permit; receipt binds intent; committed state binds intent and
receipt. Receipt must not depend on the future signed committed-state digest.
Exact canonical unsigned/signed digest domains and dependency vectors remain
required before freeze.

## Required negative controls and remaining freeze work

Exercise expiry and revocation on each side of durable intent; restart with
changed current boot/service domains; read-grant absence after successful
recovery; stale control epochs; conflicting permits; changed protocol, issuer,
fixture, signer and payload; unavailable/withdrawn keys; and revocation racing a
held recovery section. Observe both permitted progress and refused effects.
Include the final-intent rename/before-parent-sync crash cut with expiry or
write-grant revocation before restart. Also test uninterrupted phase transitions
against recovery revocation, and signing input reconstruction with each required
authenticated field absent or substituted.

Inject process death and synchronization failure before and after each signing,
staging write, final rename, directory synchronization and intent retirement.
Retain failures and check actual bytes and signing attempts: repeated invocation
is distinct from duplicated accepted publication. A negative test must not count
an unrelated process/tool failure as the intended refusal.

Freeze persistent permit/control/intent/state/receipt/response schemas and
their domain labels, exact clocks/epochs, staging-state tables, finite
file/descriptor/disk budgets and acknowledgment conditions before implementation.
Prove the corresponding SPARK decisions and transitions, then test the actual
protected adapters. This document supplies no authenticated Boolean producer,
crash-consistency proof, protected service or operational acceptance.
