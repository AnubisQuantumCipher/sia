# Continuity custody: implementation and evidence map

Status: **INCOMPLETE; real lifecycle dispatch remains NOT_ADMITTED.** This is
an integration dependency map, not an implementation, execution grant, new
process manager, or replacement acceptance standard. It preserves the original
A/G/C/P/R obligations and both R05 requirements. The sole integration owner
continues to own the existing carrier and frozen continuity adapter.

The source review found a missing composition boundary. The manager-image
witness supervises its own measurement child. The continuity supervisor starts
the workload before acquiring its handles. Neither implements the required
whole-job custody interface for the continuity workload. Making the witness
compile, or obtaining another successful observer classification, would not
by itself close that boundary.

## Exact inspected inputs

The companion `CONTINUITY-CUSTODY-INPUTS-20261025.json` records byte-derived
hashes, original paths, and snapshot names. The accompanying archive contains
only the listed inspection inputs, not a complete build or execution closure.
Its contents must not be executed as a qualification campaign.

- Product source: `a8e9385544f92cac072179bdf29dd8c8700c5c65`.
- Frozen adapter: `5c61b7afcb02af9ebfded2c5d2ada8f322822ba1`.
- Native candidate: existing `manager-send-lifetime-source-v1/source`.
- Native result: existing `manager-send-lifetime-compiler-preparation-v1/run`.
- Historical SDK result: existing `sdk-loop-finally-v8/full-result.json`.
- Current SDK evidence: [complete unchanged fixtures](SDK-FULL-RESOURCE-POLICY-20261025.md),
  [exact approved exceptions](SDK-EXCEPTION-RECONCILIATION-20261025.md), and
  [selected installed observation](SDK-INSTALLED-OBSERVATION-20261025.md).
- Independent custody review: existing `process-custody-review.txt`.

The map below uses snapshot prefixes `native/`, `adapter/`, `product/`, and
`evidence/`. Line locations refer to those exact snapshots. Hash correspondence
establishes inspection identity, not trustworthy execution or custody.

## Required operations and their current implementations

| Operation / required invariant | Actual implementation inspected | Current evidence and missing link |
| --- | --- | --- |
| Prepare an immutable operation and acquire custody **before payload entry** | `adapter/supervise.py:293` calls `Popen`, then `pidfd_open` and `enroll`. `native/manager_image_witness.c:499` opens work-cgroup controls before `create_child`; `create_child:386` uses `CLONE_PIDFD`, and `await_release:337` gates measurement. | **OBSERVED source ordering; continuity requirement UNPROVEN.** The native gating belongs to the fixed measurement child. There is no mapped implementation transferring equivalent pre-entry custody to the continuity payload. A stopped child or handle acquired after entry does not repair this ordering. |
| Bind the current manager, executable and service epoch; invalidate stale observations | `native/witness_measure.c:124` opens target pidfd/proc; `mw_measure:174` checks current process, executable metadata and held image. `native/ADMISSION-FORMAT.json` requires independent client FD hashing, current bus-owner joins and protected installed admission. | **SOURCE-ONLY candidate; native qualification FAILED.** A held executable identifies that file. This map does not infer that the process cannot re-exec after a sample. The lifetime consumer still needs an enforced current-generation/freshness protocol through the protected action, with re-exec and changed-owner refusal evidence. Configured hashes, PID/starttime and property strings cannot substitute. |
| Preserve the complete accepted UID/GID/supplementary-group and workload domain | The witness is a fixed root measurement service; `child_handle:266` validates its child's UID fields. `evidence/directbirth-credential-blocker.json` records the separate namespace route's unresolved complete credential map. | **UNPROVEN.** Witness-child credentials are not payload credentials. No qualified complete mapping was found in the inspected route. One-group or overflow-ID substitution would change the accepted domain; it is not an optimization or an implicit approval. Historical observed groups are not a new runtime allowlist. |
| Contain every descendant throughout the operation | `adapter/supervise.py:79` samples children of live enrolled parents. Native `own_work`, `kill_owned:473` and `fresh_empty:525` use held work-cgroup controls for the measurement child. | **UNPROVEN for continuity.** A descendant can be missed before reparenting. Native cleanup is scoped to its own work subgroup, not the original continuity workload. The whole-job consumer and effective containment profile have no qualified implementation/evidence join here. |
| Enforce the original absolute deadline after launcher, supervisor or observer death | Adapter `main:253` establishes work/terminal deadlines and checks them in its running process. The witness unit declares `RuntimeMaxSec=4`, startup/stop limits and control-group killing. | **UNPROVEN for continuity.** A Python deadline requires its process to run. The witness's separate unit profile is not the root-profile's original 30/35-second lifetime, and its timers are not a WCET proof. An independently surviving enforcer must retain the original start/deadline without resetting it on transfer. No unit installation or deadline change follows from this map. |
| Observe terminal state independently and distinguish payload result from cleanup | Native `wait_child:434`, `normal_cleanup:554`, and final reports bind child wait, fresh empty subgroup and removal for the measurement protocol. Adapter `terminal_observer.classify:193` checks correspondence and independently supplied inventory, keeping `acceptance=False`. | **SOURCE logic / historical mocked tests only for the adapter.** Actual dispatch and an independent producer of terminal observations remain missing. A matching JSON record, pidfd readiness, or a known-child wait cannot establish complete descendant cleanup. Missing/partial terminal evidence remains recovery debt. |
| Persist and reconcile uncertain operations before consequential retry | Adapter `persist:271` uses exclusive creation and file synchronization; an ordinary write failure returns `UNCERTAIN_DO_NOT_RETRY`. `product/PROTECTED-SLOT-CONTRACT.md` specifies separate current-authorized outcome query and durable intent/state/retirement reconciliation. | **UNPROVEN end to end.** Adapter persistence does not implement protected outcome reconciliation or parent-directory durability. The slot protocol is explicitly DESIGN ONLY. No implementation binds its transaction identity and independent current query authority to this lifecycle. A missing record cannot permit replay or manufacture completion. |
| Enforce Ada/SPARK decisions in the actual protected actuator | `product/sia_grant_lifetime.ads` defines scoped epoch checks. The slot contract requires an operation-specific decision and administrator-protected service/data ancestry. | **Conditional policy component, not runtime enforcement.** No actual restricted actuator is mapped for this continuity operation. Python expected fields, a summary, or a classifier result cannot grant authority. |

## One composition contract, no new execution lane

The existing route must eventually supply these operations through one reviewed
lifetime interface. These are required responsibilities, not implemented API
names or permission to materialize a privileged service:

1. **Prepare:** bind the original operation/source/workload, complete credentials,
   current authority and epoch, output identities, resource inventory, and one
   absolute start/deadline. Retain uncertain acquisition outcomes.
2. **Acquire:** establish complete custody and an independent surviving deadline
   enforcer while payload entry is still prohibited. Validate the actual held
   identities and current manager/authority observations.
3. **Release:** permit the exact bound payload once, only through the protected
   decision. If any required observation changes, refuse entry and reconcile
   acquired resources; a successful earlier sample is insufficient.
4. **Terminate and observe:** retain capability ownership through cleanup;
   separately report payload termination, complete descendant terminal state,
   releases, deadline outcome and evidence-publication outcome.
5. **Reconcile:** authenticate the retained operation under current query or
   recovery authority. Do not reissue an uncertain external operation merely
   because a process died or its terminal record is absent.

All fields need bounded encodings and exact provenance. Source/fixture hashes,
expected values and returned Booleans are descriptive until the actual runtime
establishes their joins. Complete existing resource budgets remain prerequisites;
this document invents no descriptor/process/queue allowances. The worker's
165-source, 46-wrapper and 32-stage inventories still require exact composition
verification before execution; the small inspection archive is not a substitute.

## Current failures and the next implementation decision

The retained original native attempt is `INCOMPLETE_NONPASS`, exit `-25`, with strict
complexity diagnostics, a capped analyzer dump, missing dependency output and
empty assembly. No behavior-preserving next native change is established.
Do not suppress warnings, omit roots or hide helpers. The operator subsequently
removed outer engineering time/memory/file caps while retaining product safety
bounds. That change does not erase emitted diagnostics or grant runtime custody.
Compiler/model exploration remains on hold. A new source hypothesis must preserve generic aliases, prior escapes,
actual error distinctions, send counts and all effect/clock ordering before
another original-scope attempt is admissible.

The historical SDK v8 full run exited `124` under its original 120-second cap. The final
unfinished method names where the cumulative run stopped; it does not prove
that method caused the timeout. All original cleanup calls and observable
effects remain required. Under the revised engineering policy the unchanged
complete roster passed all 182 tests. The exact approved exception correspondence
also passed its original seven controls; strict raw analysis remains NONPASS
with its three approved findings.

A subsequent actual installed SDK observation used only a fresh cohort-input
root and private invocation directories. Its preflight and observation exited
zero with matching source bindings, 142 module records, 28 mapped file origins
and empty diagnostics. A failed predecessor launcher and its narrow identity
comparison repair remain retained. See the source-bound observation receipt
linked above. This completes that selected observation, not the missing custody
interface, a general consumer gate, whole SDK ABI proof or worker admission.

**Next implementation decision:** keep the existing route and frozen worker;
the selected SDK fixture/observation prerequisites now have evidence at their
declared scope. Resolve the remaining native strict-analysis obligation without
reopening unapproved compiler/model research. Before connecting qualified prerequisites to worker dispatch,
fill every missing consumer/enforcer/reconciliation cell above with actual
source and evidence. Compiler success is necessary for this candidate but is
not sufficient for dispatch. If no such repair can be justified, record the
specific blocker; do not start a replacement process manager, assume a policy
waiver, or turn this map into another passing classifier.

## Acceptance evidence still required

Retain the complete original native/SDK/static/proof scopes and production safety
bounds; apply the operator's revised outer engineering policy separately. Then
exercise the existing finite root-profile matrix: failure before/after
acquisition, supervisor and observer death, manager re-exec, leader exit with
descendants, startup failure, original deadline exhaustion, partial/missing
terminal records, ambiguous closes, and recovery. Verify actual complete
credentials and containment. Death must not reset the deadline, and uncertain
effects must not be duplicated.

Only after that qualification may the selected Codex lifecycle demonstrate
actual compaction/restart against the frozen uncompacted baseline, with repeated
compactions, original evidence, later corrections and permission scope restored.
Protected publication/query, held-out retrieval, off-host recovery, installed
identity and marketplace publication remain separate acceptance gates.

This change is documentation and exact-input preservation. No native execution,
new test/proof pass, independently executed lifecycle, installation or release
is claimed. Power-of-Ten/SPARK inspiration does not establish whole-system
assurance or avionics certification.
