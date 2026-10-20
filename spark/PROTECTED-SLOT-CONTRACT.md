# Disposable protected-slot acceptance contract

Status: DESIGN ONLY. This is the next implementation contract for A11/A12,
not an installed service, a proof, or permission to migrate live SIA data.
It follows the independent next-boundary review of checkpoint `0079f724`.
All obligations in `docs/ASSURANCE-GOAL.md` remain required.

## Purpose and authority

Implement one actual protected write and an independently verifiable outcome
query on disposable state. The existing `Observe_Only` and `Proposal_Only`
results remain unchanged. Neither result is effect authorization. A new,
operation-specific SPARK decision must admit the effect after authenticating
the predecessor and joining the request, protected grant and observations.

The desktop UID is an untrusted client. A dedicated system-service UID owns
only the disposable slot, intent, state, grant and fixture signing key. Its
executable, policy binary, dependencies, unit and configuration have
administrator-owned ancestry that the client cannot modify. The service has
no access to the resident corpus, resident key, source cursors or production
index. No fixture key or receipt may claim to be a production SIA identity.
Administrator/kernel compromise and arbitrary code execution as the dedicated
service UID remain outside this initial isolation claim.

The administrator provisions one exact publication grant and may provision one
current exact read grant in a separate fixed slot. Replacing that read grant
does not accumulate grant records or admit another publication. The service
cannot turn a client proposal into a grant. Grant inspection, revocation observation,
authorization and effect execution use one serialized service-owned critical
section. There is no second unscoped socket, CLI effect path or legacy fallback.
The service runs in the initial user namespace; unsupported namespace mappings
refuse. Packet credentials come from Linux, not request fields. The current
boot domain, fresh service domain and monotonic tick come from the protected
service, never from client arguments. Every service restart invalidates grants
for new admission. Recovery authority for retained admitted intent is separate.

## Operation contract

`Publish_Fixture` replaces the single fixed payload slot. Clients supply bytes,
never a pathname, descriptor, executable, environment, provider URL or shell
command. A request binds protocol/domain version, operation, capability,
principal, boot/service domains, transaction identity, exact payload digest and
length, predecessor receipt digest, before generation and target generation.
Admission requires the exact protected grant, current authenticated predecessor,
the unique representable next generation, and no outstanding recovery debt.
Exhausted generations refuse; no wrap or automatic reset is permitted.

`Query_Outcome` names the same immutable transaction and request digest and
requires its own read authorization. It returns only the retained status and
fixture receipt, never arbitrary payload or corpus content. A client timeout
means unknown outcome, not failure, success or permission to change identity.
An exact completed retry returns the original receipt without another write,
generation or signature. Reuse of an identity with different request bytes
refuses. A missing record is explicitly Unknown, never inferred success.

After restart or revocation, an administrator must provision a current scoped
read grant for the exact old operation before any outcome can be disclosed.
The read grant's current principal/time/boot/service domain authorizes access;
its target fields bind the immutable historical operation's protocol/key/domain
and request digest. These two domains are distinct and may not be substituted.
An expired write grant and knowledge of a transaction identity grant no read
authority. A completed `Publish_Fixture` retry follows this same read gate;
it cannot restart admission or renew its write grant. Before read authorization,
replies reveal no distinction between an unknown, conflicting or completed
operation. Typed Unknown/Conflict/Committed outcomes are available only after
that gate. Pending recovery continues from protected intent without treating
the client's retry as new authority.

The first slice retains one completed outcome and admits no second transaction
until a separately specified retirement protocol exists. It therefore cannot
silently discard replay evidence, reset generations or grow an unbounded log.
This deliberately bounded fixture is not the production transaction scheduler.
Bootstrap installs a signed genesis state bound to this fixture identity;
an absent or corrupt state after commissioning is recovery debt, not genesis.

## Encoding and finite resources

Before implementation, freeze a separate wire version with complete byte-offset
tables and golden vectors for request, grant, response, intent, state and signed
receipt. Do not reuse the old proposal frame as implicit write authority.
All integers use explicit network order, enums have closed values, reserved
bytes must be zero, and declared lengths must match actual observed bytes.
Unknown versions, extra fields/bytes, truncation and attached descriptors refuse.
Use domain-separated canonical signature inputs covering every material field;
a self-hash is not authentication. The cryptographic library stays in the TCB.
Schemas must also bind issuer identity, key identity/version, permitted signature
algorithm and clock domain. A changed protocol, key or domain cannot alias an
old operation. Freeze a separate query schema, closed typed errors and reply
ceilings. Initial-user-namespace principal mapping is administrator-provisioned;
credentials alone do not establish ownership of a capability.

The disposable payload ceiling is 4096 bytes. There is one active connection,
one admitted transaction and one retained completed result. No worker process
is created per request. A stalled client expires after a five-second input
deadline; output has a five-second deadline. Neither timeout clears durable
intent. The accept loop must have a bounded scheduling quantum and shutdown
path; service nontermination is intentional, per-request work must terminate.
No unbounded retry, diagnostic, temporary file or response accumulation.

Before commissioning, derive complete frame/receipt byte ceilings, descriptor
inventory and peak disk/memory/process budgets from the frozen schemas and
implementation. Bind them in the installation manifest and enforce them with
kernel controls as well as checks. A disk limit must not rely only on a free
space observation. Kernel socket queues require an explicit bounded policy.
These derived budgets and wire tables are OPEN prerequisites, not defaults to
guess at runtime. Overflow or unavailable limits refuse commissioning.

## Durable states and acknowledgment

1. **Genesis/committed:** authenticate the current signed state and its payload
   and receipt joins. Verify the complete request and protected grant. Refuse
   any third state or existing recovery debt before new admission.
2. **Intent durable:** persist the exact admitted request, predecessor identity,
   target, payload identity and recovery authority. Synchronize file and parent
   and verify their held identities before allowing the payload effect.
3. **Payload durable:** stage, synchronize and publish the exact payload; retain
   the intent. Reopen and verify payload bytes and affected directory durability.
4. **Receipt durable:** construct the complete canonical receipt from actual
   observations, sign, persist it and verify it with the independent verifier.
   Retain its exact bytes for retries and recovery. The invariant is one canonical
   accepted receipt for this immutable operation, not one signer invocation.
5. **State committed:** publish the signed state binding payload and receipt,
   synchronize its affected parents and revalidate every join. This state still
   carries retirement debt and cannot return a terminal Committed response.
6. **Retirement durable:** retire the exact intent and synchronize its parent,
   then revalidate the signed state and absence of required recovery debt.
   Only this state may return terminal Committed. An interrupted unlink or its
   parent synchronization must be completed during recovery; observing absence
   alone does not prove retirement durability. A fresh restart revalidates these
   completion prerequisites before serving an outcome.

The authenticated committed state retains the complete operation identity and
recovery bindings needed even when intent is absent. On startup, that signed
state plus the exact joined receipt and payload permits reconciliation of an
absent intent: validate the fixed parent and complete its synchronization before
clearing retirement debt. This is a startup recovery operation, not a repeated
signature or publication. Absent intent with no valid committed state, or any
conflicting present intent, refuses. Never initialize genesis or infer a clean
terminal state from absence alone.

Each row must be expanded into individual create/write/fsync/rename/sign/readback
cuts before implementation acceptance. Signing before durable receipt retention
creates an ambiguity window; the chosen signing/retention protocol must specify
recovery without claiming that an unretained signature proves completion.
Completed retries never invoke the signer again. Before completion, any permitted
re-signing must reproduce the canonical admitted content under the exact retained
key/domain, and its behavior must be specified before freeze. Deterministic bytes
would not prove one invocation. State signatures are distinct operations with
their own domain separator and retry identity; they cannot reuse receipt authority.
An observed target name after a crash does not establish parent synchronization.
Recovery completes required synchronization, as the ACK repair already requires.

Recovery uses authenticated retained intent and its exact before/after states,
or the authenticated committed-state finalization branch defined above when
intent is absent. It does not accept a new expired/revoked grant as fresh admission or
discard previously durable intent merely because the old service epoch ended.
The specification must separately resolve revocation during pending recovery,
key availability/rotation, signature uncertainty and third-state corruption.
Those unresolved cases fail closed with retained debt, never automatic rollback.

## Evidence before activation

First implement bounded shadow comparison against the existing accepted and
negative fixtures. Preserve the old APIs, tests and decisions. Shadow output
has no effect authority and cannot become an automatic fallback.

Require a complete SPARK contract and proof for the new effect decision and
state transitions, plus a bounded model with early-commit, replay and conflict
negative controls. Input authentication remains an explicit adapter obligation.
Then stage a reviewable commissioning manifest and rollback/uninstall procedure;
obtain the necessary administrator execution through the normal approval path.
Do not mutate live accounts, services or data merely to prepare that manifest.
The manifest must enumerate disposable accounts, paths, units, socket permissions,
keys, credential mappings and effective resource limits. Authorized disposable
test commissioning precedes its acceptance campaign; accepted operational
activation is a later gate. A failed commissioning prerequisite must not select
a weaker same-UID mode. Live resident accounts, paths and services are excluded
from both disposable commissioning and cleanup.

Disposable acceptance must include real separate-UID publication/query positive
controls, desktop write/rename/chmod/unlink/key/code/descriptor bypass refusals,
missing or wrong policy/signer refusals, fresh-exec crashes at every durable cut,
response loss, concurrent/conflicting retries, revocation and restart controls,
resource saturation with recovery, and an independent offline receipt verifier.
Bind source, toolchain, installed bytes, actual ownership, commands and results.
Retain negative results and obtain independent GPT-6.1 review before declaring
the disposable boundary accepted or permitting operational activation.

Successful disposable acceptance advances only this fixture boundary. It does
not establish production SIA readiness, source truth, full publication recovery,
provider containment, cognitive improvement or off-host recovery. Production
migration must preserve existing identities and complete its own acceptance.
