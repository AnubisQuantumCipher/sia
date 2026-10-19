# Exact request grant comparison

Status: experimental pure policy; not installed authorization or shadow service.

`SIA_Request_Admission` compares a decoded request with one already-authoritative
grant. The grant is active, binds one numeric sender UID and the **entire**
request record, and has a half-open validity interval `[Not_Before, Expires)`.
No wildcard fields or subsets are accepted. An empty or reversed interval
admits no tick. The all-zero capability identity is never admitted, even if it
matches a grant. No time arithmetic or counter increment can wrap.

The classification is `Denied`, `Observe_Only` or `Proposal_Only`. None creates
a durable effect, receipt, capability or publication. A matching Observe
request cannot produce Proposal_Only. A matching proposal must subsequently
pass operation semantics, transaction/predecessor checks and actual protected
effect validation. Matching bytes are not sufficient for those checks. Read
disclosure, held generation readiness and output permissions remain required
after Observe_Only; this result is not permission to return arbitrary memory.

## Preconditions of a future enforced deployment

The grant must come from a protected, authenticated store controlled by a
trusted issuer. Untrusted clients must never supply their own grant object,
active state, subject, interval or expected request as authority. A plain Ada
record type does not enforce that storage boundary. Grant issuance, revocation,
receipt signatures and durable replay state are not implemented here.

The sender must be mapped from kernel credentials in the configured namespace;
UID matching alone is not enduring human identity. The clock tick must be a
protected monotonic observation in the grant's clock domain. Restart, namespace
or clock-domain changes must invalidate or explicitly revalidate grants before
classification. Untrusted client time is not accepted authority. The grant
store and dispatcher must serialize revocation checks with the protected effect
to avoid a check/use race. These are acceptance requirements, not proved facts.

Exact retries may match the same grant again. That never bypasses the separate
transaction reducer's idempotence and conflict checks. This policy does not
allocate generations or authorize a claimed durable effect from a request.

## Evidence scope

The new harness checks validity endpoints, reversed/empty intervals, maximum
tick boundaries, changed sender and revocation, every byte of each identity,
each other material request field, operation isolation and a zero capability.
Strict build and runtime tests pass; complete archived proof is pending.
The original policy, reducer and decoder tests remain unchanged.
