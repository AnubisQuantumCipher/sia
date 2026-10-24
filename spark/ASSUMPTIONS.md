# Assurance assumptions and enforcement obligations

This ledger separates mathematical input assumptions from observed enforcement.
Passing a pure predicate is not evidence that its caller supplied true facts.
The implementation is experimental; no row marked UNPROVEN may be described
as an installed guarantee. Evidence must bind the exact source and toolchain.

| ID | Boundary and assumption | Current evidence | Required before enforced acceptance |
| --- | --- | --- | --- |
| T01 | GNAT front end, prover translations, solvers and runtime implement their documented semantics | PROVED obligations conditional on recorded executable identities; full toolchain qualification UNPROVEN | Retain dependency/toolchain manifest, reproducible clean builds, supported architecture results and reviewed qualification scope |
| T02 | Local evidence archive, logs and exit records have not been replaced | OBSERVED archive/commit/hash equality independently checked for the accepted snapshots; hostile-account authenticity UNPROVEN | Protected signed evidence and independently obtained source/toolchain verification |
| P01 | `Admit_Source_Evidence` receives authenticated origin and complete source observation | Pure non-escalation predicate PROVED; origin producer UNPROVEN | Protected source identity and provenance receipts; model/derived/legacy substitution negative controls |
| P02 | `Witness.Present`, `Durable` and `Bound_To` reflect actual artifacts | Pure joins PROVED; Python component crash/fsync tests TESTED; full resident witness production UNPROVEN | Descriptor-bound observation, correct fsync ordering, exact generation joins and fresh resident restart fault campaign |
| P03 | Reducer starting state and receipt chain are authenticated and current | Pure successor/idempotence/refusal transitions PROVED; authenticated durable state UNPROVEN | Protected journal, signature/domain checks, replay/conflict tests, rollback resistance and crash recovery |
| P04 | A receipt digest covers every material operation/witness field | Canonical receipt requirements documented; cryptographic producer/verifier UNPROVEN | Versioned complete schema, canonical byte vectors, tampering tests, protected key and rotation/recovery evidence |
| W01 | Decoder receives the actual observed length and byte buffer | Syntax contracts PROVED; real packet-to-decoder test adapter TESTED | Production bounded handoff, no truncation or trailing-data ambiguity, source-bound installed binary |
| W02 | Linux recvmsg credentials and descriptor semantics match the platform contract | Ordinary child-sender and rights/truncation cleanup TESTED; namespace/principal mapping UNPROVEN | Explicit namespace policy, credential override threat tests and protected capability lookup |
| W03 | Test adapter raw addresses name valid fixed storage; GNAT descriptor calls honor bounds | Strict build, fixed-output integration and actual I/O error tests TESTED; adapter proof UNPROVEN | Reviewed production adapter contracts, hostile syscall/error tests and external resource/deadline enforcement |
| G01 | Grant record comes from a protected issuer/store, never the client | Exact comparison contracts PROVED and implementation TESTED; store/issuer UNPROVEN | OS-protected grant state, authenticated issuer, admissible operation validation and complete binding tests |
| G02 | Sender and clock are protected observations in the grant's principal/clock domains | Pure nonzero exact boot/service-domain gate PROVED; authoritative epoch production, mapping/time and bypass prevention UNPROVEN | Namespace-aware identity mapping, protected nonreused service identities, restart/rollback invalidation, monotonic clock fault tests and enforcement through the scoped gate |
| G03 | Grant revocation, inspection and effects are serialized; retries cannot duplicate effects | Comparator does not consume grants; enforcement UNPROVEN | No check/use bypass, durable operation identity and exactly defined retry/conflict behavior |
| E01 | Clients cannot bypass SPARK denial by writing corpus, journal or signing state | Dedicated-identity design only; enforcement UNPROVEN | Protected ownership and executable paths, hostile same-user direct-write tests and fail-closed missing-service tests |
| E02 | Local indexing cannot contact providers and judging is separately scoped | Restricted maintenance phases shipped in candidate; disposable namespace/host-listener/export/Unix-endpoint experiment TESTED; production OS boundary UNPROVEN | Separate network authority, actual engine/broker integration, working permitted-path control and forbidden-provider negative controls |
| E03 | Per-request, queue, connection, process, output and disk budgets are enforced | Fixed single-frame paths TESTED; service-wide boundedness UNPROVEN | SPARK admission bounds, OS limits, saturation/recovery and starvation controls |
| R01 | Filesystem/Git/index operations implement the abstract durable transition model | Bounded TLC model checked; component SIGKILL repairs TESTED; complete refinement UNPROVEN | Full front-door crash injection, replay, retained corruption cases and actual restart receipts |
| R02 | Recovery can authenticate data and receipts after off-host damage or credential compromise | UNRUN | Isolated off-host restore, revoked/compromised-key controls, tampered-receipt refusals and source comparison |
| R03 | Recovery-control freshness survives joint rollback of local records and epoch files | Experimental finite model only; actual independent anchor UNIMPLEMENTED/UNPROVEN | Independently pinned nonrollbackable provider; bounded current observation and compare-and-advance; serialized effects/revocation; joint-rollback, reset, lost-response and unavailable-provider tests |
| C01 | Cognitive improvement claims reflect a frozen, held-out comparison | Historical diagnostic only; independent acceptance UNRUN | Independent dense-baseline evaluation, complete positive/negative measurements and reproducible artifacts |
| AC01 | Continuity task/session/repository identity and current checkpoint/retention heads come from enrollment, independently of a proposal | Pure descriptor comparison only; protected enrollment and head production UNIMPLEMENTED | Exact enrolled source/custody, current-head and retention readback, rollback/race refusal, cross-task and cross-session controls |
| AC02 | Claim and operation observations describe retained originals with authenticated origin, order and scope | Reference format and pure comparison only; original resolution UNIMPLEMENTED | Bounded original-byte resolution, redaction lineage, descriptor binding, gap/retraction controls and protected producer qualification |
| AC03 | Checkpoint identities bind a complete canonical representation and its authenticated predecessor | Pure structural checks; canonical producer, historical continuity and publication UNIMPLEMENTED | Acyclic identity schemas, exact predecessor joins, durable publication/recovery and no omitted pending operations |
| AC04 | Transition observations bind real retained events and independent outcome artifacts | Conditional transition classifier under verification; event/outcome producers UNIMPLEMENTED | Exact event and result resolution, unchanged operation/action/source identities, reconciliation before retry, crash/uncertain-ACK controls |
| AC05 | The current lifecycle occurrence received the intended restoration packet and its original references | Disposable harness marker delivery OBSERVED; installed SIA adapter and semantic continuation UNIMPLEMENTED | Fresh occurrence/head binding, stopped/missing-hook refusal, actual installed-path lifecycle witness and held-out continuation evaluation |

Readiness and disclosure are separate obligations. `Observe_Only` does not
authorize arbitrary memory output or authorize an MCP consumer's later actions.
SIA evidence never grants WORLDLINE PRIME authority: each receiving system must
authenticate it through its own trusted boundary.

Before transferring authority, resolve the relevant enforcement rows with
evidence, or retain an explicit narrower claim. Do not turn missing evidence
into an implicit assumption or a Boolean supplied by the untrusted requester.
