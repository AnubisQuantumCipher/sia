# Protected-slot admission timing decision

Status: selected design for the new disposable protocol, not a commissioned
clock producer, implemented authority, complete protocol freeze or execution
proof. It resolves the sampled-versus-durable-validity choice in A01/G3.
Existing Observe/Proposal APIs and accepted grant/retry guarantees do not change.
The complete record schemas, resource/phase bounds and independent freshness
provider remain prerequisites for effects; this document authorizes no migration.

## Selected temporal promise

New publication requires validity at one protected admission sample S while
the exclusive protected lease is held. At S, the exact authenticated current
grant must be active and satisfy `Not_Before <= S < Expires`, with all principal,
request, boot, service, clock, predecessor and resource joins established.
This sample is the new protocol's logical admission linearization point.
It is conditional authorization for one exact operation, not durable evidence
that admission survived a crash or permission to perform an immediate payload
write. Missing authenticated producers still prevent real admission.

Natural expiry after S does not cancel that admission, including when expiry
precedes final-intent rename or synchronization. The retained intent records
the historical grant, exact S and domains. It must never claim that the grant
was valid throughout signing/fsync or at a later payload effect. This explicit
promise follows the existing experimental sampled model; the model did not
silently select production policy. No live API obtains this new effect meaning.

Completion additionally requires the exact independently current recovery
permit before each protected effect phase. An expired write grant cannot admit
another operation, create a missing intent after restart or disclose an outcome.
Disabling recovery prevents later phases after the serialized disable point;
it does not undo a completed effect. Query requires its separately scoped current
read authority. This publication choice does not settle Query disclosure timing;
that separate freeze obligation cannot inherit permission from publication.

## Required protected sequence

1. Hold the service-owned protected lease. Authenticate the running service and
   fixed stores, exact kernel principal, canonical request/payload, protected
   grant, current boot/service/clock domains, predecessor and resource admission.
   Establish the exact current recovery permit/control under the independent
   freshness/fencing contract. No client Boolean supplies any of these facts.
2. Read S from the selected protected clock and check the closed-domain tick
   representation and half-open grant interval. Unsupported/error/regressed
   observations refuse. Current recovery authority at S requires an exact
   authenticated provider/fencing witness binding fixture, permit, control epoch,
   operation and this serialized section. It must prevent a disable from
   linearizing between observation, S and the section's effects, or fence those
   effects if its authority is lost. A remote read response cached before S is
   insufficient. The lease spans this sample through intent publication and
   synchronization; administrator grant/control updates share that domain.
   A remote provider requires the separately accepted reservation/fencing and
   loss-of-contact protocol; the local lease alone supplies no such guarantee.
3. Bind every required admission value, including S and historical grant,
   in the canonical signed intent under its distinct pinned signer role.
   Stage and publish only those bytes. A model note, memory cache, client retry
   or unfinished staging file cannot reconstruct a lost admission.
4. Synchronize and verify the exact intent file and parent. No payload effect
   precedes successful current synchronization. A visible final rename does
   not establish that its previous parent sync succeeded.
5. Release the section after its bounded terminal outcome. Every subsequent
   payload/receipt/state/retirement phase reacquires the lease, authenticates
   the retained operation/artifacts and rechecks current recovery authority.
   It cannot reuse a previous phase's currentness witness. Outcome disclosure
   requires the independent current read gate.

Intent retention is the crash-recovery boundary, not a second admission sample.
If a crash loses staging or a pre-sync rename, an in-memory S is lost with it;
new admission requires fresh current write authority. If the final signed intent
survives, verify its exact schema/identity and current recovery permission,
then complete file/parent synchronization before any payload effect. Conflicting
or malformed final artifacts preserve debt. Neither successful synchronization
now nor a signature proves that an earlier synchronization occurred.

The existing five-second input/output deadlines are client-I/O limits. They
do not bound signing, disk synchronization, locking, revocation or recovery.
Those phase budgets, interruption rules and supported workload must be fixed
and qualified before commissioning. A timeout preserves uncertain outcomes;
it cannot clear debt, manufacture a fresh operation or accept an old success.

## Clock/domain choice and unproved producer

The new Linux fixture selects CLOCK_BOOTTIME and integer nanoseconds. It includes
Linux suspend time and avoids discontinuous wall-clock changes, according to
the [Linux man-pages clock reference](https://man7.org/linux/man-pages/man2/clock_gettime.2.html).
This is a clock-semantics choice, not a clock accuracy, VM-pause or WCET claim.
Nanosecond units do not imply nanosecond resolution. An unsupported clock refuses;
there is no fallback to realtime, an unspecified Python monotonic clock or a
caller-supplied timestamp. Clock failures or values outside the existing Tick
domain refuse before conversion; no wrap, clamp or truncated high bit is allowed.

The configured nonzero clock-domain identity must bind this algorithm/unit
selection, protected boot identity and commissioning scope through a frozen
canonical schema. The service domain is separately generated/authenticated at
restart; it cannot be copied from a request. Exact domain derivation and signed
record encodings remain OPEN. A remembered boot UUID or a local last-tick file
does not establish authenticity or rollback resistance. Same-boot samples must
not regress; equal samples are representable and do not prove elapsed time.

VM snapshot restoration, a replayed signed control or joint local rollback
cannot be repaired by this clock choice. The independent anchor and any remote
fencing must meet `model/CONTROL-FRESHNESS.md`; no local clock or second epoch
file substitutes. The observed local availability of CLOCK_BOOTTIME/Python's
integer API is only an API smoke observation, not an authenticated producer.
The primary-source URL, retrieved-byte digest and limitations are retained in
the external `admission-clock-primary-v1.json`/`.html` evidence files.

## Required acceptance matrix, currently UNRUN on a protected runtime

| Case | Required result |
| --- | --- |
| S before Not_Before, at Expires, empty/reversed interval, inactive grant | Refuse new admission; no intent/payload effect |
| S exactly Not_Before with every other prerequisite valid | Permit only exact conditional admission |
| Expiry between S and signing/rename/fsync | Preserve historical S; later completion still requires current recovery authority |
| Publication revocation or recovery disable committed before S | Refuse admission |
| Disable requested while admission section holds lease | No effective-revocation ACK before serialized durable disable; revalidate at next phase |
| Final rename survives crash before parent sync | Current recovery may synchronize the exact retained intent; no payload effect first |
| Final rename disappears or only staging survives | No recovery-based creation; require fresh new admission |
| Current permit missing/disabled/stale or provider unavailable | Preserve debt; no new recovery effect/signature/terminal completion |
| Restart with old intent and expired old write grant | New admission denied; exact recovery and separately current Query remain independent |
| Clock/domain mismatch, error, regression or out-of-domain tick | Refuse; no implicit domain replacement or overflow |
| Timed-out signing/sync/rename with unknown outcome | Reconcile exact retained operation/artifacts; no blind retry or new identity |
| Local state/control/clock rollback | Independent freshness/fencing must deny revoked authority; absence of that producer blocks commissioning |

The existing finite sampled model covers abstract expiry and intent-survival
paths only. It does not prove numeric clock boundaries, schema authentication,
phase deadlines, query disclosure, Linux syscalls or eventual recovery. Map
each row to the SPARK decision and actual fault cuts before calling the complete
temporal protocol accepted. Preserve its safety-negative and post-expiry
reachability counterexamples; post-expiry completion is an explicit contract
property, not evidence of continuous grant validity.
