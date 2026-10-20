# Agent continuity across compaction

Operator mission expansion, 2026-10-20. Status: requirements and initial
source-backed gap assessment; implementation acceptance OPEN. One owner retains
the existing assurance worktree, changes, proof campaigns and negative evidence.
No universal no-loss, correct-recall or error-free continuation claim is made.

## Observed gaps

At base `313159eb3c3a69f804178e42ac007bb8791f4edb`,
`bin/siasenses.py:sense_codex` deliberately captures session metadata, not
conversation/tool bodies. Session existence and growth cannot recover an early
constraint, approval scope or interrupted operation. Existing `siacheckpoint*`
modules concern corpus transactions/publication; those contracts are useful
dependencies, not demonstrated agent working-context restoration.

On the inspected machine, `codex --version` reports `codex-cli 0.159.2`.
The user hook configuration contains one herdr SessionStart handler. Its inspected
script reports session identity to herdr; it does not restore SIA task state.
A separate process-ancestry observation found this session's host executable at
`/usr/lib/chatgpt/resources/codex`, reporting `0.162.0-alpha.17.2`, beneath the
ChatGPT desktop process. The shell CLI is therefore not the qualification target.
Neither version inspection nor generated protocol schemas establish actual
hook execution. That still requires a lifecycle witness from the desktop binary.

The [official Codex hook documentation](https://learn.chatgpt.com/docs/hooks)
documents SessionStart on startup/resume/compact and pre/post compaction events.
It describes restored additional context as developer context and requires
non-managed hook trust. Consequently SIA must not place raw retrieved instructions
in that channel. Actual support, trust and timing in the selected host still need
an execution witness. Other harnesses, including OMP and Hermes, remain separate
UNQUALIFIED targets.

## Required contracts

| ID | Contract | Failure behavior and evidence |
| --- | --- | --- |
| C01 | Capture only enrolled tasks and permitted event classes; redact before SIA persistence; explicit byte/event/time/storage budgets | Refuse or record a typed gap on unsupported, oversized, missing, truncated or excluded input. Never mark a skipped source range complete. Credential-pattern tests do not prove all secrets detectable. |
| C02 | Preserve source identity, session, source offset/order, role, origin, integrity and redaction lineage | A model summary remains model-origin; captured user/tool text proves recorded bytes, not truth or current authority. Ordering gaps and source replacement must be visible. |
| C03 | A durable ACK identifies an exact accepted source range and manifest | ACK only after required original records, checkpoint dependencies and publication metadata are durable. Retry after uncertain ACK queries that same operation; never invent success. Filesystem and protected-store assumptions stay explicit. |
| C04 | Checkpoints contain task/session identity, goal/acceptance, corrections, constraints, decisions/reasons, rejected approaches, exact source/dirty-state refs, work/results/failures, active operations, next action and permission references | Every material claim links original evidence. Missing required dependencies blocks actionable restoration. Summary text cannot authenticate its own premises. |
| C05 | Supersession is explicit and source-ordered | Later correction replaces only the referenced scope. Conflicts, cycles, missing predecessors, concurrent writers and unknown ordering refuse actionable restoration. No silent last-file-wins policy. |
| C06 | Restore joins current task, session/handoff, repository, revision, dirty state and checkpoint generation | Identity or revision changes require reconciliation; old proof/test passes cannot transfer automatically. A deliberate handoff requires an explicit bound record. |
| C07 | Retrieval is bounded and progressive | Restore a bounded decision packet plus references. Budget exhaustion, omitted evidence and unresolved facts are exposed. Follow-up retrieval preserves original references and origin. Storage alone is not successful recall. |
| C08 | Restored approvals are references to exact original approvals and action scope, never new grants | The current authority boundary must validate them. Retrieved malicious instructions and model prose cannot authorize actions. Missing, expired, superseded or ambiguous authorization blocks that action. |
| C09 | Operation state distinguishes planned, dispatched, uncertain, observed-complete and acknowledged | Reconcile external state by stable operation identity before retrying a write. Tool truncation, interruption and absent results do not mean success or failure. |
| C10 | Correction, deletion, retention and revocation propagate through derived descendants | Restore checks current tombstones/generation. Retained backups, embeddings and summaries are in scope; no resurrection from an old checkpoint. |
| C11 | Pure SPARK validity/planning policy is enforced in the actual adapter path | Proof covers supplied premises only. Authenticate producers and protect writes under existing G2/G3 gates; no Python Boolean may substitute for evidence. |
| C12 | Harness support is demonstrated, source/version bound and limited to observed events | Actual pre/post compact or documented equivalent lifecycle, restart and installed path readback. Hook timeout/trust/absence is a visible gap, not compatibility. |

## Stages and acceptance

1. **Inventory and freeze contracts (G1).** Map capture sources, existing
   redaction, retention and transaction facilities; record host identity and
   documented hooks. Freeze event/checkpoint/operation schemas, unsupported
   cases, bounds, threat model and privacy enrollment. Preserve in-flight
   consolidation proofs and all earlier gates.
2. **Pure validity and conservative restore (G2).** Add bounded Ada/SPARK policy
   with no allocation or recursion, explicit source/order/supersession bindings,
   contracts and refusal reasons. Build strict, prove all intended obligations,
   retain failures and review independently. This does not establish semantic
   accuracy or protected authority.
3. **Capture/publication integration (G3/G4).** Reuse qualified source transaction
   machinery where its contracts fit. Implement exact-range durable ACK,
   crash recovery, source references and revocation. Test every durable prefix,
   torn input, quota exhaustion and uncertain effect. No unreviewed whole-home
   transcript ingestion or blanket public archive.
4. **Codex adapter qualification (G4).** First provide explicit checkpoint/resume
   with strict budgets. Then exercise documented hooks in an isolated enrolled
   session, preserving existing hooks. Verify actual emitted restoration and
   next action through lifecycle execution before installation claims.
5. **Held-out continuity campaign (G5).** Freeze scenarios and expected critical
   facts before evaluation, compare with an uncompacted baseline, and retain
   all outcomes. Include repeated compact/restart, buried constraints, later
   corrections, rejected fixes, source changes, concurrent sessions, truncation,
   missing records, stale summaries, conflicts and retrieved prompt injection.
   Measure fact retrieval, missed constraints, wrong continuation, invented
   approval/completion, duplicate actions, latency and resource use. Separate
   deterministic protocol tests from model continuation quality.
6. **Recovery, review and release (G6).** Independent GPT-6.1 review, exact-source
   build/proof/test archive and offline verifier, installed adapter identity and
   demonstrated lifecycle. Retain explicit capture/retrieval limitations and
   separate experimental results from deployed guarantees. Existing marketplace
   freeze and publication gates still apply.

## Power of Ten adaptation

This table applies the existing normative-source assessment; it does not quote
or replace Holzmann's rules or claim CPython compliance.

| Control | Continuity application |
| --- | --- |
| 1–2 | Acyclic phase transitions; bounded decoding, range scans, evidence joins and supersession walks; explicit service scheduling/termination assumptions |
| 3 | Fixed SPARK arrays; capture/context/queue/disk budgets and refusal before exhaustion; CPython and harness allocation remain outside static allocation proof |
| 4–5 | Short parsing and policy routines; meaningful contracts for exact joins, conserved identities, missing evidence and refusal state |
| 6–7 | Task-scoped capabilities, minimal retained private data; validate every schema/result, including hook failures and uncertain side effects |
| 8–9 | Explicit versioned adapters; no eval, imported instruction execution or dynamic policy dispatch from retrieved data |
| 10 | Strict compiler/prover/static checks, malformed inputs, fault campaigns, exact source/toolchain receipts and visible deviations |

Passing these controls does not establish whole-system assurance, semantic
understanding, universal harness support or avionics certification. The smallest
sound implementation increment is an explicit bounded checkpoint/restore
contract with refusal controls, followed by a witnessed Codex lifecycle adapter.

## First format increment: unverified reference proposals

`bin/siacontinuitypacket.py` is an experimental Python proposal codec. It does
not read original evidence, persist records, restore a model context, issue a
grant or execute a proposed action. Every returned packet is `UNVERIFIED`.
This is preparatory integration code, not a Python substitute for G2/G3.

The closed schema retains task/session/repository/revision/dirty/capture
bindings, checkpoint identity/generation/predecessor, observed source sequence,
coverage classifications, typed evidence references and uncertain operation
states. Binding values are SHA-256 descriptor references, including the revision
descriptor; a native Git SHA-1 must not be padded or relabeled as SHA-256.
Their producers, contents, authenticity and freshness remain unimplemented
premises. The returned input SHA-256 binds exact supplied proposal bytes only.

Claims preserve the complete supersession chain and source references. A
replacement must identify the current predecessor in the same slot with the
same kind/origin/role; branching, missing or forward predecessors refuse.
Cross-category corrections require a later explicit contract, not guessed
semantic supersession. Assistant prose cannot declare evidence origin.
Coverage is retained as a proposal, never independently established by parsing.
`partial` preserves captured references without asserting complete coverage.
Operations are point-in-time proposals with evidence references: the codec does
not validate their history or allow a later checkpoint to reset an uncertain
effect to planned. Cross-checkpoint operation transitions and tombstones require
the later authoritative reconciliation contract.

No free-text instructions or source body can occupy a reference field. Output
has a caller-selected byte ceiling and is all-or-refuse, without truncation.
The parser caps input bytes, container depth, claim/operation counts and numeric
range before further processing; CPython still allocates dynamically. Fixed
refusal codes do not echo rejected private content. No claim of complete secret
detection, source retention or prompt-injection resistance follows.

Deterministic tests cover malformed input, bounds, identity changes, supersession,
origin contradictions, approval references without grants, uncertain operations
and repeated fresh-process projection. These process tests are explicitly not
Codex compaction, semantic retrieval or an uncompacted-baseline evaluation.
Next: authenticate and resolve references, define/prove the conservative SPARK
restore policy, then qualify explicit durable checkpoint/resume and actual hooks.

## Retained evidence and current acceptance

At source `1e3e6de7281142ac08005274ffa452dcbad341b7`, fresh selected-source reproduction passed
21 tests: the 18 continuity-codec controls and three installed-runtime dependency
closure checks, with Python warnings treated as errors. The archive contains
`bin`, `scripts`, `tests`, `install.sh` and `uninstall.sh`; it is not a full-repo
archive. SHA-256: `50f25c23cae0730e2e26ce6c8a26e989a7fa991a08c53db417327083db9f0314`. Evidence:
`continuity-packet-reproduction-v1` and `continuity-packet-review-v2.txt`.
Independent GPT-6.1 review verified archive/source, interpreter identity and raw
outputs without rerunning tests. The source inventory remains inventory-only;
no syntax findings is not Power of Ten compliance. Standard formatted exception
tracebacks suppress decoder causes, but Python exception context/locals can
still hold input in memory; arbitrary exception-object logging is not approved.

`codex-host-identity-v1.json` retains the inspected executable/configuration
hashes and process lineage. An ancestor outside the desktop host could not be
read (permission error); the visible desktop executable was independently
versioned. A disposable credential-free instance of that same executable listed
the fixture hook first as untrusted and then as trusted after exact-definition
review. This did not change production hook configuration.

The disposable `thread/start` succeeded, but `thread/read` with
`includeTurns=true` returned `list_turns is not supported yet`. Its successful
start response was reconciled before continuing: a fresh server resumed that
same thread using `excludeTurns=true`, with no duplicate start. The prompt-input
diagnostic did not contain the fixture hook marker. These observations are
retained in `codex-lifecycle-probe-v1`; they establish metadata restart only.
No model turn, actual compaction, restored next-action correctness or hook
execution has been qualified. The initial probe's coarse UNRUN receipt does not
override its retained successful start response or failed history-read response.

Next acceptance increment: authenticated bounded original-reference resolution
and conservative SPARK restore policy, then durable explicit checkpoint/resume
with crash prefixes, followed by actual desktop hook execution and held-out
compaction continuation. No experimental module has been installed or promoted
to the marketplace release.
