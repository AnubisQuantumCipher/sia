# Implementation gates and guidance inventory

Operator mission clarification received 2026-10-20 through the authorized
session handoff. This extends `ASSURANCE-GOAL.md`; it does not replace its
release, marketplace, held-out evaluation or off-host recovery obligations.
One implementation owner retains the assurance worktree. Independent GPT-6.1
review remains a separate acceptance activity. Avionics-style rigor is an
engineering aspiration, not certification or an error-free interpretation claim.

The explicit rule mapping, current violations and repair order are in
[`POWER-OF-TEN-ASSESSMENT.md`](POWER-OF-TEN-ASSESSMENT.md). The authoritative-source
research and proposed lifecycle obligations are in
[`AVIONICS-INSPIRED-ASSURANCE.md`](AVIONICS-INSPIRED-ASSURANCE.md). Both are
acceptance work under this mission, not optional feature work.

## Ada/SPARK resources

Installed skill entry points were inspected to select applicable guidance.
Topic chapters must be read when applying their specialized features; this
inventory is not a claim that every book or chapter has been read.

| Skill | Intended application |
| --- | --- |
| ada | Route language, integrity and machine-specific questions |
| ada-omarchy | Installed GNAT environment, all-unit proof, exact summary/assumption checks |
| spark-users-guide | Explicit contracts, flow dependencies, loop/subprogram termination, refinement and external assumptions |
| ada-high-integrity | Verifiable subset, requirements/structural testing, runtime and toolchain obligations |
| advanced-ada | Distinct domain types, valid-state records, visibility and representation boundaries |
| gnat-toolchain | Reproducible projects, strict diagnostics, supported compiler/prover switches |
| ada-programming | Package/type/lifetime boundaries and explicit exceptional behavior |
| ada-2005-amendment | Reference when using applicable language features; no requirement to introduce dispatch, allocation or tasking |

These are guidance resources, not acceptance evidence. User requirements
override conflicting generic examples: retain runtime checks at untrusted
boundaries, do not suppress proof failures or warnings to obtain acceptance,
and do not use unrestricted `-j0` in place of the existing resource caps.
Historical tool counts and reference-project proof claims must not be imported
as proof of SIA. Check development-guide syntax against installed tools.

## Concrete sequence

| Gate | Implementation work | Required completion evidence |
| --- | --- | --- |
| G1: authoritative lifecycle | Specify captured-source identity, sequence/capture gaps, immutable origin, publication, exact retrieval authority, explicit retirement and durable tombstones; separate retraction of derived records | Requirement/hazard/contract matrix; reviewed complete transitions and malformed cases; no implicit deletion or provenance escalation |
| G2: SPARK lifecycle core | Add bounded lifecycle decisions to the existing pure units; keep external authenticity/durability producers explicit; implement typed refusals and safe degraded capabilities | Strict build, complete all-unit flow/functional/termination proof, no unresolved intended checks/justifications/assumptions hidden in code, deterministic boundary and adversarial tests, independent review |
| G3: protected producers and actuator | Complete pinned issuer/store/epochs, canonical records, bounded IPC, signing custody, freshness provider and actual exclusive protected write path | Commissioning manifest; necessary privileges approved; direct bypass and stale-witness controls; actual revocation/rollback/expiry/isolation tests; no unauthenticated caller Boolean used as authority |
| G4: selected resident path | Establish installed executable/config/retained-state identity and observe actual dispatch; run complete source-to-publication failures on that path; qualify an explicit migration if required | Actual front-door execution and fresh exec restart, torn/reordered writes, exhaustion, corruption/replay and acknowledgment cuts, retained receipts; reversible migration plan where possible; no silent config switch |
| G5: derived memory and semantic evaluation | Version/evidence-link/retract/recompute summaries, embeddings and dreams while retaining original records; freeze independent held-out ground truth and abstention policy | Retraction/rebuild/source-retention tests; complete false-pass/false-fail and abstention measurements, baseline comparison, no model verdict relabeled as source truth |
| G6: recovery and release | Complete off-host damaged-data/compromised-credential/tampered-receipt exercises and independently executable verification; qualify selected installation and marketplace source | Exact source/toolchain/TCB/assumption manifest, independent reproduction and review, installed readback and exact marketplace acceptance; only scoped earned claims published |

G1/G2 can progress while G3's provider qualification remains unresolved.
Passing them cannot authorize migration or hide the missing enforcement.
No new spending, security privilege, concurrency cap or network authority is
implicitly granted by this sequence. The existing release remains separate.

The later operator-directed [agent-continuity mission](AGENT-CONTINUITY.md)
extends G1–G6 with original-event capture, structured source-bound checkpoints,
bounded conservative restoration, approval/uncertain-operation reconciliation
and repeated-compaction evaluation. Codex is the first qualification target;
other harnesses remain unqualified until separately exercised. This remains
one implementation owner and does not install the draft SOUL.md.

## Hazards and traceability requirements

Every row must ultimately point to immutable source, contract/proof obligation,
test invocation/output, independent review and installed-path evidence. The
locations below are starting points, not completed coverage.

| Hazard | Required property | Current starting point / gap |
| --- | --- | --- |
| Model prose becomes history | Origin never escalates through signing, dream or summary; unknown remains explicit | `SIA_Policy.Admit_Source_Evidence`; authenticated origin producer remains open |
| Captured data is silently lost or reordered | Preserve identities, sequence, provenance and explicit capture gaps; qualify coverage to successfully captured events | Source completeness type exists; complete lifecycle/gap/ordering contracts remain open |
| Retrieval or retirement bypasses authority | Exact current read/retire authority, authenticated generations, preserved audit/replay evidence | Protected Query proposal exists; full authoritative retirement policy remains open |
| Derived retraction deletes source | Retraction/version replacement affects derived identity only; authoritative source remains available under its own retention policy | End-to-end derived lifecycle acceptance remains open |
| Green tests exercise inactive code | Acceptance binds actual selected runtime and retained routing state | Config false was observed; branch-execution evidence remains open |
| Signed stale control resurrects permission | Independent freshness and serialized authorization/effect | `ControlFreshness.tla` conditional model; actual provider/enforcement remains open |
| Semantic confidence masks a false result | Independent ground truth, false-pass/false-fail accounting and explicit abstention | Held-out campaign remains open; signed/model judgment is not truth |

The observed `mind.controller_source: false` field is only a configuration
observation. `_reserved_pulse` also considers retained controller-source state.
Do not infer actual legacy or controller execution from that flag alone, or
toggle it merely to exercise a preferred test path. Inspect installed code,
validated retained state and actual dispatch evidence before making that claim.

### Installed observation on 2026-10-20

At 08:09:40 UTC, a corpus-lease-protected observation of the installed runtime
found the controller configuration disabled, no controller marker keys, and no
retained controller source path. The installed selection predicates therefore
selected legacy dispatch at that observation. The active systemd service
executes the installed `sia-brainstem`; observing its actual branch execution
and fault recovery remains required. Evidence:
`installed-dispatch-observation-v1.json` in the external assurance directory.

The accompanying bounded no-touch recall completed with exit 1 and the explicit
refusal `corpus consolidation recovery is pending`, rather than an outer
timeout. `sia ready` independently refused for the same reason. Individual
atomic file snapshots retained in `recall-consolidation-refusal-v1.json` show
a named consolidation transaction and outstanding scan days; these snapshots
are not a common transaction observation or proof of eventual completion.
The daemon was still completing pulses, and held the corpus lease during the
recall wait. Earlier successful readiness checks do not establish current
availability. Investigate recovery progress and retain the refusal; do not
clear its marker or bypass the read gate to make recall appear healthy.

The isolated consolidation recovery regression now injects a ledger-settlement
exception after scan completion. It requires the durable applied marker and
its ledger binding to survive reload, then requires retry to settle that exact
marker without repeating consolidation. Protected source bytes remain intact.
All three tests in `tests.test_consolidation_backlog_recovery` passed. Settlement
is a controlled mock: this does not establish real signed-ledger durability,
process-crash recovery, or installed recall availability.

`tests.test_consolidation_exec_recovery` adds separate interpreter executions
for preparation, SIGKILL immediately after the applied-marker writer returns,
and recovery. All runtime imports use an explicitly marked disposable HOME.
The recovery process observes the readiness refusal before settlement, must
not repeat consolidation, and emits a controlled witness of the exact retained
marker before marker removal. Original protected source bytes remain intact.
The combined exec and backlog suite passes five tests, including refusal of
worker invocation without an explicit fixture home. This closes that isolated
fresh-exec cut only: no signed-ledger qualification, resident front-door
execution, storage power-loss model, or production readiness is established.

The additional signed exec lane initializes disposable Ed25519 keys with the
checkout's actual `sia-ledger`. After the applied-marker cut, another fresh
process performs real settlement and is killed before clearing the memo marker.
A final process recovers, checks the exact occurrence through `ledger_contains`,
and runs the keeper's signature/chain verification. The test requires unchanged
signed ledger bytes and head pin across the retry, one successor entry after
genesis, retained transaction identity and unchanged protected source bytes.
The exec, backlog and existing ledger-recovery suites pass 16 tests. This adds
actual local signed-settlement integration evidence at those cuts; it does not
provide an independent cryptographic verifier, protected key custody, a complete
resident-service campaign, or power-loss assurance.

Operational progress must retain its generation identity. The installed scan
changed from generation `96b25629f4dc480da64dd4fcf499ea58` with 21 pending days
to `88611c43a1e2486c8ccea4b0ccaaf2f7`, first scanning and later holding 60 pending
days. `_acknowledge_consolidation_claims` deliberately starts a conservative
rescan after source unlink. A falling within-generation count therefore does
not establish a global completion percentage or latency bound. The daemon
remained active; installed recall availability and a bounded recovery-latency
argument remain open. Do not remove the rescan or clear recovery debt merely
to improve that count.

[`Consolidation progress`](../spark/model/CONSOLIDATION-PROGRESS.md) records
the implementation's rescan structure, a finite liveness experiment and
negative controls for reset-on-keep and external source recreation. It leaves
directory-page refinement, successful operation assumptions, resident
scheduling and wall-clock bounds explicit. It does not close G4 or rule 2.
The subsequent real-filesystem characterization reproduces repeated cursor
resets from current-day atomic replacement under a reduced paging budget.
Recovery completes after those replacements cease. This is a tracked liveness
failure and a repair obligation, not a green acceptance result. The combined
backlog, exec, ledger and original `EpochMerge` suites pass 48 tests with that
negative behavior explicitly preserved.
The [immutable discovery candidate](../spark/CONSOLIDATION-SNAPSHOT.md)
adds a bounded Git tree reader and real immutable-ID tests. The combined
snapshot/recovery suite passes 50 tests. This primitive is deliberately not
wired into recovery: durable reference binding, schema migration, arrivals,
compatibility, source revalidation and positive churn recovery remain required.
The snapshot primitive now adds generation-bound commit retention references
and a separate admitted-pin check that cannot recreate missing state. Four
snapshot tests pass, including real packed-ref/GC retention and exact
missing-object negative controls. This is experimental reachability evidence;
admission durability, reference lifecycle and runtime integration remain open.
The experimental admission journal now distinguishes planned creation from
admitted state under the corpus lease. Ten admission/snapshot tests pass,
including interrupted prefixes, exact retries, missing-pin refusal and malformed
retained-state preservation. This remains outside the installed recovery path;
fresh-process/power-loss cuts and authenticated transaction binding remain open.

### Installed recovery completion observation

Later on 2026-10-20, bounded `sia ready` returned exit 0 (`SIA memory ready`).
The subsequent bounded `sia ask "SIA consolidation recovery and publication
readiness" --no-touch` also returned exit 0 with origin-labeled semantic results.
Its boundary reported live senses, passing chains, a complete graph, six spans
redacted at ingest and associative reranking disabled by measured default.
Model and legacy-unlabeled results remain non-evidence; absence of recall is
not evidence of absence.

A later atomic scan-file observation showed generation
`88611c43a1e2486c8ccea4b0ccaaf2f7` complete with no pending days or claims.
The commands and file read are separate observations, not one transaction
snapshot. Their summarized results and installed executable hashes are retained
in `installed-consolidation-recovery-completion-v1.json` externally; private
recalled content was not copied. This supersedes the earlier availability
refusal for that observation only. It does not fix the cursor-churn defect,
qualify the experimental snapshot modules, establish a recovery deadline or
guarantee future recall availability.

### Snapshot admission process-death evidence

The experimental snapshot admission journal now has actual SIGKILL cuts after
planned persistence, pin creation/readback and admitted persistence. Separate
fresh interpreters recover and replay the same exact request; the parent checks
the journal prefix, reference identity, original source bytes and unchanged
maintenance marker. Fresh recovery also refuses missing admitted pins,
conflicting planned pins and deliberately truncated journals without repairing
their retained state. The combined admission exec, exception, snapshot and
original consolidation exec suites pass 20 tests.

This is component process-death evidence, not a resident front-door campaign or
storage power-loss qualification. Snapshot traversal integration, legacy debt
migration, late arrivals, pin lifecycle and recovery bounds remain required.
The scanner's continuing-write characterization is still an unresolved defect.

The subsequent admitted discovery component now joins the retained journal,
exact commit pin and immutable tree ancestry under the real corpus lease.
Its continued-write test completes the original snapshot while preserving a
later eligible arrival outside that snapshot's coverage. Batched/single-unit
traversal, empty trees, cutoff/shard cases and failure-after-progress retry are
tested. The combined discovery and existing recovery suites pass 32 tests.
The old resident scanner is unchanged: this is component integration, not the
completed runtime repair.

A retained negative control shows that a caller can supply a forged completed
cursor. Structural checks do not prove traversal history. Durable cursor/batch
ownership, named transaction consumption and protected authority remain required
before any discovery completion can clear recovery debt. See
[`Admitted immutable traversal`](../spark/CONSOLIDATION-SNAPSHOT.md#admitted-immutable-traversal)
for scope and remaining gates.

The new delivery staging record atomically retains a candidate batch with its
before/after cursors. Pending work replays and cannot be skipped by supplying a
new cursor or acknowledgment. It now hands off to the original live-claim
observation logic, retaining all selected candidate paths and the original
batch. Execution and retirement remain unimplemented.

Independent review found a staging-specific source-loss gap: legacy replay's
valid epoch-lineage exception could allow missing sources before the new
consumer executed anything. The real-lineage negative control reproduced the
failure. A staging-specific live-presence check now refuses that case without
changing legacy recovery. Failed evidence is retained. Actual process-death
tests also exercise batch and claim persistence with fresh-interpreter replay;
these do not establish resident or power-loss acceptance. Prototype serialization
capacity and the remaining consumer protocol still require qualification.

A safe degraded mode must enumerate allowed operations; "read only" is not
automatically safe when identity, confidentiality or publication is uncertain.
Failures and unknown outcomes remain visible and must not be renamed success.

### Marketplace readback after admission process-death tests

At `2026-10-20T09:19:48.684842+00:00`, verification request
[#12332](https://github.com/omacom/omarchy-plugin-marketplace/issues/12332)
remained OPEN with `validated`, `security-review-required` and `plugin-update`
labels. The deployed catalog still reported SIA v1.8.3, `update-unverified`
coverage and `installAvailable: false`. Raw issue/catalog responses are retained
in `marketplace-readback-after-admission-exec-v1` externally. The v1.8.4
marketplace publication gate remains open; passing the experimental component
tests does not approve or publish that release.

### Staging checkpoint reproduction

The exact committed-source staging archive passes 86 focused tests, including
original epoch recovery, module ownership, typed replay refusal and actual
process-death staging cuts. See the source/hash/command receipt in
[`CONSOLIDATION-SNAPSHOT.md`](../spark/CONSOLIDATION-SNAPSHOT.md). The independent
GPT-6.1 review found no remaining blocker for staging after the retained fixes.
The next obligation is the actual consumer's execution/retirement protocol; no
new code is installed or promoted to publication authority by this result.

The legacy claim executor has now been decomposed into reviewable routines,
with scan acknowledgment kept at the original entry point. Its committed
source `6251b4924a25ab16f96756c8b04e9ce0907d5388` passes 90 targeted checks
from a fresh archive, including original recovery regressions, retained-claim
and index-failure replay controls, and the local sixty-line routine budget.
See `CONSOLIDATION-SNAPSHOT.md` for the source/archive receipt and retained
initial test failures. This prepares reusable effects; staged execution
intent, completion/retirement, installed migration and G4 acceptance remain
open. No existing readiness gate or protected ownership requirement changes.

The subsequent execution-attempt consumer persists intent before epoch
effects and retains cursor, claims and maintenance debt after return.
Source `c54080e9e36305aa1141d6ff29b74dafa46060ea` passes 104 targeted tests
from its Git archive, including fresh-process SIGKILL recovery and a
repaired final-journal-size edge with retained pre-repair failure evidence.
The returned state explicitly does not establish event-index completeness;
a real missing-leaf control demonstrates this limitation. Source-outcome
qualification, all-batch completion, cursor retirement, installed migration
and G4 acceptance remain open. No acknowledgment or settlement is added.

The selected-source outcome observer now rechecks exact source bytes, epoch
lineage and reconstructed marker-index records under the corpus lease.
The development suite passes 116 tests, including observation in a fresh
interpreter after each retained SIGKILL/recovery cut. Missing/wrong index
evidence, partial same-day cleanup and unavailable original history refuse
without changing claims or debt. Coverage is explicitly selected-claims-only;
legacy unmarked prose, epoch summary/count semantics and authenticated
execution history are outside this observation claim. Later live originals
are not yet independently pinned, and a real GC negative control demonstrates
the resulting safe refusal. Durable source retention and all-batch retirement
are still required; see `CONSOLIDATION-SNAPSHOT.md` for exact scope and evidence.

The same 116-test selection passes from the fresh Git archive of
`4082ac8190ab68e1f818f60494192b0023fdef5a` in
`consolidation-outcomes-reproduction-v1`. Independent GPT-6.1 review found no
blocker for the stated read-only selected-source scope and did not rerun the
suite. This is TESTED component behavior, not a proved or installed retirement
boundary. The next prerequisite is durable, identity-bound retention of every
claimed original before any destructive effect, including versions observed
after snapshot admission; admission and claim identity must survive crash,
replay and real history GC without replacing mismatched pins.

The candidate now implements that pre-effect original retention: a separate
planned/pinned/retained protocol binds the full admitted claim identity to an
exact precommit and verifies every claimed source before execution intent.
Executing, returned and outcome-observation paths require the retained direct
pin and cannot repair its loss. This removes opportunistic history search from
delivery verification. Qualification is recorded with the snapshot work.
The single outstanding claim-set journal still needs a defined lifecycle;
all-batch completion, protected retirement authority, installed migration and
G4 resident acceptance remain OPEN. Content retention does not authenticate
origin, execution history or current permission to delete.

Original-retention source `5667541ed7e76964e75dd3e524d79e4dbda2451b` passes 127 targeted tests from
its fresh archive. The record, archive hash and retained failed-fixture output
are indexed in `CONSOLIDATION-SNAPSHOT.md`. Exact originals are now pinned
before effects within the experimental consumer. Whole-batch progression,
retained-day eligibility, pin/journal lifecycle and the resident acceptance
campaign remain open; successful selected-claim recovery cannot clear them.

### Consolidation policy and agent-continuity checkpoint

Source `1e3e6de7281142ac08005274ffa452dcbad341b7` adds the pure
[consolidation observation planner](../spark/CONSOLIDATION-POLICY.md), with a
complete archived strict proof/runtime result and independent evidence review.
It does not advance a cursor or retire originals. The original-retention and
full-consumer progression gates remain open.

The [agent-continuity proposal codec](AGENT-CONTINUITY.md) has retained scoped
parser/process/dependency tests and independent review. It returns unverified
references only. Actual capture, protected source resolution, SPARK restoration,
durable checkpoint publication, harness compaction and held-out continuation
remain open. The desktop metadata-resume probe is not substituted for them.

A fresh installed no-touch recall on 2026-10-20 completed with exit zero; its
retained boundary reports live senses, passing chains, a complete graph, six
redacted spans and associative reranking disabled by measured default. Model
and legacy-unlabeled memories remain non-evidence, and absence of recall is not
evidence of absence. `installed-recall-continuity-start-v1.json` retains command
and timing metadata without raw memories. This does not install the experimental
continuity codec or guarantee recall deadlines. Marketplace request #12332 was
still OPEN and security-review-required at the latest issue observation; the
latest bounded catalog probes did not establish current listing state. Neither
issue validation nor this branch's tests establish marketplace publication.
