# Pure local retraction planner

Status: experimental semantic interface, not installed authorization, a wire
schema, a durable tombstone or completed graph retraction.

`SIA_Retraction` is the first local transition slice from
`RECORD-LIFECYCLE.md`. Its fixed records contain no variable-length payloads,
access values, queues, dependency walks, cryptographic implementation or I/O.
Every descriptor carries an opaque nonzero record identity, nonzero version,
immutable origin, content digest, exact parent-manifest digest and provenance
digest. Digests retain their full mathematical domain, including all zero;
only identity/operation tokens reserve zero. Hash equality is not evidence that
the caller authenticated the corresponding bytes.

The provenance digest must eventually bind capture/source identities, assertion
provenance, order and coverage using a frozen canonical schema. The parent
digest likewise needs an independently authenticated complete manifest.
Neither producer exists in this package. This interface does not allocate
record versions, discover parents or prove source-window completeness.

## State and decisions

`Plan_State` holds the immutable descriptor, current semantic epoch, stage and
retained retraction request. `Active` requires the canonical empty request.
`Retraction_Proposed` requires a valid retained request with the same descriptor
and its successor epoch. Epoch zero is invalid. A request binds the entire
descriptor, a nonzero operation token and exact before/after epochs. The
successor check first excludes exhaustion, then requires the next epoch.

`Plan` has no precondition excluding malformed supplied state. It returns:

| Decision | Candidate |
| --- | --- |
| Refused | Exactly the supplied state, including when that state is invalid |
| Proposed_Only | Same immutable descriptor; successor epoch; retained exact request; Retraction_Proposed stage |
| Identical_Proposal | Exactly the supplied previously proposed state and original request |

Only derived/model descriptors can be retraction targets. Source and
legacy-unlabeled targets refuse, including exact attempts to reinterpret their
origin or version. A changed descriptor, predecessor, operation or successor
cannot masquerade as the identical retained proposal.

The caller supplies a completeness observation for the exact parent manifest.
Only `Verified_Complete` permits a proposal or identical-proposal result.
`Observed_Empty`, `Not_Observed`, `Unavailable` and recovery debt refuse. An
authenticated complete empty manifest can be represented by its exact digest
and `Verified_Complete`; `Observed_Empty` alone is not such authentication.
This is a conditional semantic check, not an authenticated observation producer.

Retraction and source retirement are separate operations. This package has no
retirement state and no reactivation, purge, read or grant operation. Repeated
planning does not consume authority or establish durability. Result disclosure
through any future service must still pass current read/confidentiality checks.

## Contracts and integration boundary

The explicit `Global`, `Depends`, termination and postconditions specify exact
classification, immutable-descriptor preservation, unchanged refusal/retry and
valid-state preservation. An invalid initial state is not repaired implicitly.
The output can only become a proposed local transition; no caller may dispatch
it as protected effect permission.

Descendant eligibility remains UNKNOWN/blocked outside this package.
`Retraction_Proposed` cannot become terminal global retraction merely because
its local checks passed. Actual retrieval/derivation must enforce authenticated
ancestor/tombstone generation bindings or an atomically invalidated complete
bounded closure. Neither is implemented here.

Acceptance of this component requires strict build, all-unit proof with no
unresolved intended obligations, independent deterministic/adversarial controls,
exact source/toolchain reproduction and independent review. Those results still
do not establish grant authenticity, concurrency, signing, durable retention,
capture completeness, active-use blocking or installed behavior.
