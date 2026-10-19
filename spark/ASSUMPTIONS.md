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
| G02 | Sender and clock are protected observations in the grant's principal/clock domains | Pure supplied-data comparison only; authoritative mapping/time UNPROVEN | Namespace-aware identity mapping, restart/rollback invalidation and monotonic clock fault tests |
| G03 | Grant revocation, inspection and effects are serialized; retries cannot duplicate effects | Comparator does not consume grants; enforcement UNPROVEN | No check/use bypass, durable operation identity and exactly defined retry/conflict behavior |
| E01 | Clients cannot bypass SPARK denial by writing corpus, journal or signing state | Dedicated-identity design only; enforcement UNPROVEN | Protected ownership and executable paths, hostile same-user direct-write tests and fail-closed missing-service tests |
| E02 | Local indexing cannot contact providers and judging is separately scoped | Restricted maintenance phases shipped in candidate; disposable namespace/host-listener/export/Unix-endpoint experiment TESTED; production OS boundary UNPROVEN | Separate network authority, actual engine/broker integration, working permitted-path control and forbidden-provider negative controls |
| E03 | Per-request, queue, connection, process, output and disk budgets are enforced | Fixed single-frame paths TESTED; service-wide boundedness UNPROVEN | SPARK admission bounds, OS limits, saturation/recovery and starvation controls |
| R01 | Filesystem/Git/index operations implement the abstract durable transition model | Bounded TLC model checked; component SIGKILL repairs TESTED; complete refinement UNPROVEN | Full front-door crash injection, replay, retained corruption cases and actual restart receipts |
| R02 | Recovery can authenticate data and receipts after off-host damage or credential compromise | UNRUN | Isolated off-host restore, revoked/compromised-key controls, tampered-receipt refusals and source comparison |
| C01 | Cognitive improvement claims reflect a frozen, held-out comparison | Historical diagnostic only; independent acceptance UNRUN | Independent dense-baseline evaluation, complete positive/negative measurements and reproducible artifacts |

Readiness and disclosure are separate obligations. `Observe_Only` does not
authorize arbitrary memory output or authorize an MCP consumer's later actions.
SIA evidence never grants WORLDLINE PRIME authority: each receiving system must
authenticate it through its own trusted boundary.

Before transferring authority, resolve the relevant enforcement rows with
evidence, or retain an explicit narrower claim. Do not turn missing evidence
into an implicit assumption or a Boolean supplied by the untrusted requester.
