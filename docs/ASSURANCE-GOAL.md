# SIA assurance engineering goal

Operator-directed scope, 2026-10-19. Baseline:
`1f6b6667b0bc5e29b29e6d2d8f2a7b71edcee46c`.
This is a requirements and acceptance ledger, not a completed assurance claim.

## Delivery obligations

Finish issue #33, retain reporter credit, verify the installed runtime, publish
1.8.4, request exact-commit marketplace verification, and read back the catalog.
Marketplace approval is external; a submitted request is not publication.
Keep experimental assurance work isolated. The initial release target was held
for the reproduced ACK directory-synchronization gap. PRs #38 and #39 closed
its obsolete freeze and merged the runtime repair; repaired main passed CI and
normal local installation. PR #40 then passed both candidate CI runs and merged
the declaration-only freeze. Its merged tree matches the tested candidate.
Final merged-main CI passed on `7371c8e2f152aec47f07843821447067991d96fc`.
The annotated v1.8.4 tag and [published release](https://github.com/AnubisQuantumCipher/sia/releases/tag/v1.8.4)
were read back, including reporter credit. The [final issue reply](https://github.com/AnubisQuantumCipher/sia/issues/33#issuecomment-6285535056)
was posted and its exact body read back. [Marketplace request #12332](https://github.com/omacom/omarchy-plugin-marketplace/issues/12332)
requests verification/publication of that exact commit; its body was read back.
The initial post-request catalog still showed v1.8.3. A later retained readback
on 2026-10-21 UTC shows v1.8.4 and the correct upstream commit, but verification
still covers an older snapshot: update-unverified, Manual setup, and standard
installation unavailable. Marketplace approval/publication remains
an external gate. Main remains frozen; experimental work stays on this separate
branch. These release observations do not qualify the experimental assurance
branch or any protected service.

The subsequent marketplace review reported a different-account Ollama API
boundary failure. The single owner reproduced it in a private namespace and
is developing an isolated administrator-owned account guard in
`codex/sia-ollama-account-boundary-20261020`. That candidate and its retained
negative controls do not change frozen main or qualify the installed system.
Marketplace publication remains blocked on resolving the concrete finding and
the existing exact-source acceptance/review gates.
The candidate is retained in [draft PR #41](https://github.com/AnubisQuantumCipher/sia/pull/41),
including the full-CI failures and subsequent test-fixture repairs. Isolated
kernel and sudo-delegation evidence does not qualify the host's administrator
configuration. Both corrected-head full CI runs passed, each reporting 3868
tests with 21 skips; gbrain-contract and marketplace-freeze also passed.
The existing actual GPT-6.1 reviewer closed the runbook finding and found no
concrete surviving bypass or regression in the scoped final deltas. Pinned
administrator-installation files and a command sheet are prepared, but host
authentication, commissioning and the actual lifecycle acceptance remain open.
The same owner continues the assurance branch with these obligations
visible, without treating a release blocker as a reason to stop implementation.

The expanded goal is a reliable Linux/Omarchy memory system with enforced
authority boundaries. Python may propose and execute bounded work; Ada/SPARK
decides consequential policy; Linux must enforce protected writes, identity,
signing authority, and network separation. Existing contracts, deterministic
fixtures, accepted cases, negative controls and compatibility must survive.

## Required work and acceptance

| ID | Obligation | Required acceptance evidence | Current status |
|---|---|---|---|
| A01 | Freeze threat model, transition tables, capabilities and resource bounds | Source-backed model, assumptions and requirements traceability | IN PROGRESS |
| A02 | Provenance authority | SPARK contracts and proofs rejecting escalation of model, derived or legacy content; independently tested legitimate transitions | PARTIAL: pure admission predicate proved/tested; authenticated origin producer and enforcement UNRUN |
| A03 | Publication and acknowledgment authority | Generation-bound durability, corpus/index/graph/ledger joins, no recovery debt; proofs plus real adapter evidence | PARTIAL: pure joined-publication/ACK predicates proved/tested; pure durable-prefix reducer proved; full resident adapter evidence UNRUN |
| A04 | Disclosure authority | Narrow recipient/evidence/byte/operation authorization; local indexing denied provider-network access by Linux; positive and negative controls | PARTIAL: disposable namespace controls and real gbrain offline indexing tested; exact-commit export excludes dirty fixture tokens; scoped embedding broker and production network controls UNRUN |
| A05 | Recovery and continuity authority | Exact predecessor/successor admission, crash/replay model and fault-injection receipts | PARTIAL: pure reducer proved; bounded single-transaction crash model checked with negative/reachability controls; component SIGKILL and fsync-failure controls tested with recovery repairs; fresh resident restart and restore UNRUN |
| A06 | Identity and receipt authority | Rejected replay, tampering, mismatched generations and unauthorized transitions; protected signing authority | PARTIAL: pure nonzero boot/service domain comparison proved and scoped grant records tested; authenticated epoch production, replay consumption and protected signing UNRUN |
| A07 | Resource authority | Proved bounds for requests, counters, queues and admission; exhaustion tests and OS limits | PARTIAL: fixed-capacity decoder and exact-grant comparison proved in complete ten-unit run (293 checks proved); packet intake tested; disposable cgroup process admission and single/paired-process memory exhaustion tested; production service budgets, disk bounds and hostile same-user isolation UNPROVEN |
| A08 | Cognitive claim admission | Frozen held-out evaluation against dense baseline; independent reproduction; no unearned improvement claims | UNRUN: historical refused campaigns inventoried; no current qualifying reproduction or cognitive improvement established |
| A09 | Resident source-to-publication campaign | Full front-door execution with failures at durable transitions, restart/replay, retained negative results | PARTIAL: forked resident workers killed before and after orphan adoption; retained transaction recovery and pre-adoption wrong-pin refusal tested with controlled Git/index observers; fresh service exec and complete real-engine campaign UNRUN |
| A10 | Off-host recovery campaign | Damaged data, revoked/compromised credentials and tampered receipts tested without touching live evidence | UNRUN |
| A11 | Bounded versioned IPC and migration | Shadow comparison first; differential legitimate/adversarial tests; authority transfer only after evidence; missing/mismatched kernel refuses | PARTIAL: syntax decoder and exact-grant comparison contracts proved; Linux packet intake, bounded version-separated v1/v2 grant readers and loaded-grant test handoff reproduced; scoped production handoff, protected grant store, shadow policy and migration UNRUN |
| A12 | Linux enforcement and bypass resistance | Restricted actuator actually owns protected state; hostile same-user tests; no Python bypass of denial | UNRUN |
| A13 | Reproducible acceptance and controlled release | Exact source/toolchain, strict CI, offline verifier, independent GPT-6.1 review, installed readback and marketplace receipt | PARTIAL: fresh committed-source policy runner and bounded-model runner tested; v1.8.4 release/tag readback complete and marketplace request filed; complete offline system verifier, portable proof CI and marketplace publication UNRUN |
| A14 | Documentation and pictures | Audit measured versus illustrative figures; proposed versus implemented diagrams; accurate proof and maturity claims | PARTIAL: repository claims corrected and historical preview inspected; unattached illustrative visualization unavailable; final enforced-architecture documentation pending |
| A15 | Recall reliability | Preserve lock/readiness gates; diagnose actual deadlines; bounded waiting and explicit failure; repeat real recall | PARTIAL: caller cutoff diagnosed, guidance corrected, repeated installed-runtime readiness and no-touch recall passed; universal latency not established |
| A16 | Authoritative history and capture gaps | Preserved original provenance, identity and ordering; explicit missing/unavailable capture; guarantees scoped to successfully captured events | PARTIAL: origin/completeness predicates exist; complete lifecycle and gap acceptance OPEN |
| A17 | Authoritative retrieval and retirement | SPARK-governed current read/retire decisions, durable replay/tombstone evidence and no bypass | OPEN: protected Query proposed; full retirement and production mediation UNRUN |
| A18 | Replaceable derived memory | Versioned evidence-linked dreams/summaries/embeddings; retraction and rebuild preserve authoritative history | End-to-end acceptance UNRUN |
| A19 | Semantic accuracy and abstention | Independent held-out ground truth, false-pass/false-fail measurements and explicit abstention; no LLM truth authority | UNRUN; complements A08 without replacing its baseline comparison |
| A20 | Selected installed path and explicit migration | Actual dispatch bound to installed source/config/retained state; fault campaign on selected path; qualified migration without silent configuration or privilege changes | OPEN; raw controller_source false observed, actual dispatch not established by that field alone |
| A21 | Full traceability and guidance | Hazards/requirements to contracts, source, proof, independent review and exact installed/released tests; relevant Ada/SPARK guidance applied | IN PROGRESS; staged gates and resource inventory recorded |
| A22 | Agent compaction continuity | Authorized original-event capture, source-bound structured checkpoints, bounded conservative restore, approval and uncertain-operation reconciliation; repeated-compaction evaluation against an uncompacted baseline | OPEN: current Codex sense records metadata only; no qualified SIA task-restoration adapter |
| A23 | Qualified harness lifecycle integration | Actual current Codex hooks exercised at compaction/resume, installed-source readback and retained outputs; each other harness separately qualified | PARTIAL: disposable desktop startup/resume/manual-compaction hooks and marker delivery observed with a deterministic local provider; actual SIA adapter, automatic compaction, semantic continuation and installed-path qualification OPEN |
| A24 | Detachable cockpit | Reuse the existing model, visual tree, readers, guarded operations and lifecycle lease; verify presentation switches and installed path | PARTIAL: native Quickshell window, 176 regression tests and disposable component/packaged-Omarchy lifecycle tests passed; exact source/evidence published on the experimental branch; full CI, live desktop activation and marketplace installation OPEN |

The 2026-10-20 compaction-continuity expansion is binding scope in this same
single-owner session. Its initial gap assessment, requirements and staged
acceptance campaign are in
[`AGENT-CONTINUITY.md`](AGENT-CONTINUITY.md). It adds to A05/A16–A21 and the
existing gates; it does not replace consolidation recovery, protected authority,
release or marketplace obligations. The separately drafted SOUL.md remains
under operator review and must not be installed by this mission.

Source completeness must distinguish observed empty, not observed, unavailable,
and verified complete. Authentication of a model record never makes its content
source evidence or factual truth. SIA recall never grants WORLDLINE PRIME or
other systems' authorization; those systems authenticate evidence independently.

## Proof boundary

The [raw-diagnostic gate repair](PROOF-WARNING-GATE.md) records optional
warnings discovered behind earlier clean flow-summary rows. Historical
discharged-check results retain their stated source and scope; they do not
establish all-channel zero-warning acceptance. Current acceptance must include
the complete raw diagnostic roster as well as the summary and all-unit result.

Prove deterministic policy, initialization, absence of run-time errors,
termination, provenance non-escalation, readiness and resource invariants.
Do not infer filesystem durability, actual cryptographic validity, process
isolation, network containment or empirical retrieval quality from those proofs.
An adapter-provided Boolean is an assumption until the producing boundary is
implemented and tested. Record filesystem, crypto, imported functions,
subprocess, kernel and toolchain assumptions explicitly.

Model publication and restore as finite state machines (TLA+), including crashes
at every durable transition. Align model actions with SPARK transitions and
actual Linux/Python operations. Preserve counterexamples and failed tests.
Require zero unresolved intended critical obligations and no silent assumptions
or justifications used to erase failures. Keep runtime checks enabled at
untrusted boundaries even when internal code is proved.

## Implementation order

The 2026-10-20 operator clarification is carried in
[`ASSURANCE-IMPLEMENTATION-GATES.md`](ASSURANCE-IMPLEMENTATION-GATES.md),
including the relevant Ada/SPARK skill inventory, lifecycle/retirement,
derived-memory and selected-runtime gates. It extends the sequence below.

1. Establish current source-backed boundaries and contracts.
2. Implement and prove a small provenance/publication vertical slice; test it.
3. Add bounded shadow IPC and differential evidence without changing released
   authority. A shadow decision is observational, not protection.
4. Implement the restricted actuator and privileged separation, then demonstrate
   no-bypass enforcement before transferring authority.
5. Complete recovery, identity, disclosure, resource and cognitive gates and the
   acceptance campaigns; update claims and release only qualifying behavior.

The operator added one bounded cockpit change on 2026-10-20:
[`sia cockpit --window`](COCKPIT-WINDOW.md), reusing the existing model,
readers, guarded command paths and UI. It does not relax any assurance gate
or authorize a second runtime or database owner. No other substantial unrelated
cognitive feature, cockpit feature or source adapter is part of this goal.
Research mechanisms may fail to beat retrieval; in that
case retain the negative evidence and remove unsupported improvement claims.

The next protected-service design is specified in
[`spark/PROTECTED-SLOT-CONTRACT.md`](../spark/PROTECTED-SLOT-CONTRACT.md).
It requires a separate effect decision, actual disposable protected ownership,
durable retirement and independently authorized outcome queries. It remains
DESIGN ONLY. The independently reviewed request/grant proposal is in
[`spark/PROTECTED-SLOT-WIRE.md`](../spark/PROTECTED-SLOT-WIRE.md). It separates
current authorization from immutable operation identity and the historical
publication-request digest; requires exact request-kind/grant-action/slot joins;
and admits outcome reads only through current read authority. Unsupported
completed-Publish retry envelopes uniformly refuse; existing APIs and accepted
retry guarantees remain unchanged. The independently reviewed
[`spark/PROTECTED-SLOT-LAYOUT.md`](../spark/PROTECTED-SLOT-LAYOUT.md) proposes
exact field offsets and distinct hash/signature domain labels; its arithmetic
is JACKAL `exact`, not protocol proof. Initial public-key byte/signature fixtures
and an independently authored checker are in
[`spark/tests/PROTECTED-SLOT-VECTORS.md`](../spark/tests/PROTECTED-SLOT-VECTORS.md);
they test fixed examples and signature mutations, not protected authority.
The non-final recovery proposal in
[`spark/PROTECTED-SLOT-RECOVERY.md`](../spark/PROTECTED-SLOT-RECOVERY.md)
separates new publication, exact-operation recovery and current read authority.
It treats a visible signed intent as requiring durability reconciliation and
requires current recovery permission during uninterrupted continuation too.
Admission timing, independently protected control freshness, persistent schemas
and bounded phase execution remain OPEN; this is not an implemented or accepted
recovery service.
An experimental sampled-admission model is documented in
[`spark/model/ADMISSION-RECOVERY.md`](../spark/model/ADMISSION-RECOVERY.md).
It exposes completion after grant expiry and checks the abstract intent-sync
requirement, with a deliberately broken negative control. Model evidence does
not authenticate observations or qualify the eventual Linux implementation.
The independent-anchor requirements and rollback counterexamples are in
[`spark/model/CONTROL-FRESHNESS.md`](../spark/model/CONTROL-FRESHNESS.md).
Provider commissioning and actual rollback-resistant freshness remain UNPROVEN;
a second local signed epoch file is not an accepted substitute.
Complete malformed-input policy and portable verification, complete
resource budgets, clock domains and signing/recovery schemas still must be
completed and frozen before implementation acceptance. These proposals do not replace the
full production obligations above or permit live-data migration.

## Claims requiring verification

The source-backed lifecycle requirements and compatibility boundaries are in
[`spark/RECORD-LIFECYCLE.md`](../spark/RECORD-LIFECYCLE.md). They distinguish
captured bytes from complete source coverage, logical retraction/retirement
from deletion, and legacy origin classification from authenticated admission.
The first pure local retraction planner is described in
[`spark/RETRACTION-PLANNER.md`](../spark/RETRACTION-PLANNER.md). Strict development
build and all six runtime harnesses passed. Committed-source reproduction at
`376a54102eaff64383fc2f54c5a0d1ef68f0819f` discharged 386 reported checks across
twelve fully analyzed units, with no justified or unproved checks. Independent
GPT-6.1 review verified the retained source archive, tool identities and results
(`retraction-reproduction-v1` and `retraction-review-v2.txt` in the external
assurance evidence directory). This is PROVED pure-contract behavior under the
recorded toolchain and supplied premises, plus TESTED harness executions.
Authenticated parent observations, protected integration and global descendant
invalidation remain unimplemented; no installed authority or full lifecycle
acceptance follows. Local evidence custody remains an assumption.

The operator supplied a documentation-based assessment, not a certification.
Its quoted retrieval figures are historical repository diagnostics, not answer
accuracy or new measurements. Its illustrated source-health and calibration
percentages were explicitly illustrative. Locate actual assets before editing;
do not invent measurements or claim an unattached visualization was corrected.
Related SEKHMET, Custos and JACKAL proof claims do not establish SIA's proof.

All progress reports distinguish PROVED, TESTED, OBSERVED, ASSUMED, UNPROVEN,
FAILED and UNRUN, with scope and source identity. Completion requires evidence,
not the existence of this ledger or a green subset of the requirements.
