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
The later disposable lifecycle observations below supply a narrow manual
compaction/startup/resume witness; they do not qualify an installed SIA adapter.

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
| C13 | Checkpoint transitions conserve unresolved operations | Join the exact authenticated predecessor and successor. Pending includes planned, dispatched and uncertain operations. None may disappear or change action/source identity; dispatched/uncertain work cannot reset to planned. Completion requires exact outcome-reconciliation evidence. Capacity exhaustion refuses publication; it cannot silently evict unresolved work. |
| C14 | Restoration envelopes are scoped to one current lifecycle occurrence | Bind session, checkpoint/head, retention generation, lifecycle occurrence and target turn. A stale marker, missing/failed/stopped hook or a turn status alone cannot establish successful restoration. Recheck head and retention before use. |

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
execution was qualified by that first probe. The initial probe's coarse UNRUN receipt does not
override its retained successful start response or failed history-read response.

Next acceptance increment: authenticated bounded original-reference resolution
and conservative SPARK restore policy, then durable explicit checkpoint/resume
with crash prefixes, followed by actual desktop hook execution and held-out
compaction continuation. No experimental module has been installed or promoted
to the marketplace release.

## Conservative SPARK policy increment

[`SIA_Continuity`](../spark/CONTINUITY-POLICY.md) adds a fixed-capacity pure
classification of checkpoint structure and independently supplied current
evidence. It checks exact task/session/repository bindings, checkpoint/capture/
retention generations, source ordering and supersession, origin, coverage,
canonical padding, durable-witness bindings, current revision/dirty references
and uncertain operations. It has no action-grant result.

Complete proof acceptance remains OPEN. Development snapshots v2 through v7
built and passed their continuity runtime controls, but each all-unit proof
attempt reached the existing 600-second limit without a complete report.
Those failures remain in the external evidence directories; earlier runtime
passes do not establish the later edited source.
Development v8 built and passed its runtime controls, but its driver exited
with signal-derived status 143 before recording the proof result. The proof
receipt and complete report are absent. Its cause and proof outcome remain
UNKNOWN; it is not recorded as another completed timeout or a proof pass.

Focused diagnostics established the earlier core's reported obligations,
the repaired full-capacity claim test and the parameterized context-byte test.
The supersession diagnostic v7 and line diagnostic v3 were deliberately
interrupted and remain unproved. Supersession diagnostic v8 completed with one
unproved classification precondition for a correction that skips an intervening
replacement; all its other selected checks discharged. The repair introduces
checked invalidity lemmas and explicit expected-result conditions at the test
boundary. A shared coherent-observation helper retains the same observation
construction and runtime result assertion while reducing each caller's proof
context. These changes retain the original mutations and wanted outcomes.
Line diagnostic v4 proves only the later correction's validity assertion after
a checked state cut; all helper bodies and callers require the complete
campaign. No selected-line success,
intermediate solver file or zero-check report row substitutes for all-unit
coverage. Resource caps and original positive/negative controls are unchanged.

Operation diagnostic v9 retained two unproved classification preconditions.
An equality cut to the exact original uncertain-operation fixture and a
parameterized, checked fixture lemma discharged the 13 selected caller checks
in diagnostic v10. Diagnostic v11 separately discharged the lemma's seven
selected checks. Those two scoped successes still do not replace a complete
all-unit run, all runtime controls, coverage validation and independent review.
The same explicit fixture-parameter contract was then applied to the corrected,
permission and pending-approval fixture lemmas, retaining each equality cut,
mutation and expected classification. Diagnostic v12 discharged the 14 selected
permission-origin caller checks. Independent review found no weakened
obligation. The changed helper bodies and complete source still need their
full proof and runtime acceptance.

Diagnostics v13–v15 separately discharged each changed helper's eight
selected checks; v16 discharged the correction-chain caller's 28 selected
checks. The source did not require the additional five-claim fixture
decomposition considered during review. Fresh development-v9 built the
complete project and passed all eight runtime harnesses. Its full all-unit
proof reached the unchanged 600-second command limit, exit 124; no complete
coverage result was produced. This attempt remains unqualified. The final
read-only GPT-6.1 source review found no remaining blocker for this conditional
classifier, while preserving the external obligations below.

The explicitly incremental `continuity-policy-incremental-v1` continued a new
retained copy of development-v9's exact source and generated proof session.
The parent snapshot remains unchanged. Source, project/restrictions, tools
and copied session contents match their retained identities. The same full
`-U` command and strict coverage checker both exited zero. The final report
records 782 discharged checks across sixteen units, with no justified or
unproved checks and clean detail rows. Before/after tool hashes match.
Independent GPT-6.1 review checked these bindings and preserved the distinction
between an incremental result and a fresh reproduction.

The [incremental evidence manifest](CONTINUITY-POLICY-EVIDENCE.json) derives
source, command and artifact identities from those retained files. Build and
all eight runtime harness passes belong to the exact parent snapshot; the
complete proof belongs to its explicit continuation. This is not a fresh,
independent or single-command reproduction. The fresh committed-source runner
remains a separate open acceptance gate; no timeout, scope or verification
requirement is waived.

Fresh committed-source reproduction at
`2794db2390e4f7e3cb3cff0d5b910d2967ac6dd8` passed the strict build and all eight
harnesses, then reached the same 600-second proof limit, exit 124. Evidence:
`continuity-policy-committed-v1`; no completed coverage acceptance follows.
Inspection also found default-disabled miscellaneous warnings in the earlier
raw proof output that were outside the original summary checker's scope.
The [diagnostic-gate repair](PROOF-WARNING-GATE.md) is a new qualification
obligation. Clean flow-summary rows never established all-channel zero-warning
compliance.

The stricter development-v11 campaign subsequently completed from a fresh
archive plus an explicitly recorded working-tree overlay. It enabled all tagged
warnings, checked all raw diagnostic channels and tried the same provers in
Z3/CVC5/Alt-Ergo order. Strict build, all eight harnesses, the full proof
(788 reported checks) and coverage validation passed under the unchanged
resource caps. [Warning-gate evidence](PROOF-WARNING-GATE.md) records the exact
scope and retained failures. Fresh committed reproduction remains pending.

Witness production, protected freshness, original-reference resolution and
cross-checkpoint operation history remain external obligations. In particular,
the package cannot detect a producer that omits an uncertain operation from a
new checkpoint. Its most permissive result proposes references only; it cannot
establish that continuing an operation is authorized or safe.

## Desktop lifecycle observations

`codex-lifecycle-probe-v2` used a disposable, credential-free instance of the
actual desktop executable. Startup and resume `SessionStart` hooks and a manual
`PreCompact` hook executed and returned explicit stop responses. The startup/
resume turns nevertheless reported `completed`, while the pre-compaction stop
reported `interrupted`. Thus a harness turn status alone cannot establish a
model response, successful compaction or completion of the requested work.

`codex-lifecycle-probe-v3` allowed two manual compactions and resumed the exact
same thread in a fresh app-server process. It used a loopback deterministic
Responses fixture, not a model. Raw harness notifications and the fixture event
file record startup, two pre/post-compaction pairs with compact SessionStart,
and resume. Subsequent provider requests contained the fixed hook markers in
developer-role messages. Compact SessionStart ran before the next requested
turn; this is not evidence of automatic in-turn compaction.

The actual desktop binary reported `0.162.0-alpha.17.2`; its retained hash was
independently compared with the installed executable. The review is retained
as `codex-lifecycle-review-v1.txt`. No probe was rerun by the reviewer.
Provider request bodies were not persisted: marker-role observations depend on
the inspected recorder, with byte counts and request hashes retained. Fixture
response text and usage values are synthetic and are not retrieval scores,
context-budget measurements or successful semantic continuation.

The resumed request retained both an older compact marker and the new resume
marker. The adapter must therefore bind and supersede restoration generations
explicitly; it cannot assume the harness automatically removes stale context.
Raw retrieved instructions must not be placed into developer context.

Visible warnings are retained: the pre/post hooks ignore an inapplicable
context-limit field, the synthetic model uses fallback metadata, and the
harness warns about repeated compaction. The probes are not zero-warning
qualification. They use bounded requests and deadlines but do not establish
complete process/memory/stderr limits, hostile custody, or network isolation.
The parent user `AGENTS.md` remained an instruction source; these fixtures are
credential-free but not hermetic with respect to inherited instructions.

This closes only the question of whether the selected binary executes these
specific hooks and delivers fixed markers in this controlled lifecycle.
Automatic compaction, hook timeout/trust failures, capture privacy/completeness,
source-authenticated restoration, real-model held-out continuation and
production SIA installation remain OPEN. The official
[hook contract](https://learn.chatgpt.com/docs/hooks) and
[app-server protocol guidance](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
guided the probe; observed behavior and retained failures control its claims.

## Next runtime integration contract

The independent read-only review in `continuity-integration-review-v1.txt`
identified self-confirming producer inputs and lost cross-checkpoint operations
as concrete blockers. The next slice is an explicit disposable resolver joined
to a versioned SPARK adapter; automatic hooks and action execution are later
acceptance steps.

The resolver selects its enrolled task manifest and current head independently
of the proposal. It reads originals under a finite aggregate budget, verifies
their canonical byte identities and exact role/origin/sequence descriptors,
checks current retention/retraction state and constructs observations from those
reads. It must refuse a missing record, changed head or revocation observed
during resolution. Hash agreement establishes a byte binding; protected custody,
truth of content and authorization remain separate requirements.

The pure transition validator must enforce C13 against the authenticated
predecessor, including omission and reset negatives. The adapter must enforce
C14 even when the harness retains an older marker beside the new one or reports
`completed` after a stopped hook. Its receipt must distinguish hook execution,
reference resolution, context delivery and semantic continuation; none implies
the next stage.

Acceptance includes maximum capacity, missing originals, head/retention races,
uncertain-operation omission/reset, stale and simultaneous markers, stopped-hook
completion, exact Python/SPARK representation comparisons and fresh-process
replay. This contract is not an implementation or a qualification result.
