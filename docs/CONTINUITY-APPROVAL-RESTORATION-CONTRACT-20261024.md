# Approval restoration: original-event linkage contract

Status: **UNIMPLEMENTED / NOT ACCEPTED**. This design closes a specification
gap under C04/C06/C08/C10/C11/C14 and R02; it does not grant an approval, retire
R05 reuse, change a resource limit, or qualify a harness. The incident and its
original-event hashes are retained in
`R05-AUTHORIZATION-RECURRENCE-20261024.json`.

## Verified source frontier

At assurance commit `4c3a262e6bca0d73730bc4eda5651a3a0dc24673`, the Python
proposal codec retains permission references but only returns UNVERIFIED data.
`SIA_Continuity.Valid_Claim` requires user/source classifications for permission
references; those classifications are supplied premises. `Classify` can return
`References_Proposed`, never an action grant. Neither representation carries
the original question, response-to-question relationship or action conditions.

The separate Codex worker at `5c61b7afcb02af9ebfded2c5d2ada8f322822ba1`
also has no successful action-authority path: `require_action_authority` always
refuses. Its preserved resolver checks original-record correspondence and
retention, but does not authenticate human authorship or approval semantics.
The V5 `recovered_context` path accepts only its fixed synthetic public prompts,
with user/model/source classifications. It is not a general permission-record
restorer. Adding an approval parser inside that fixed pilot would not establish
production coverage. Preserve all V5 source bytes, cases and oracles.

This is a missing production boundary, not a demonstrated permission-grant
bypass in those functions. The observed R05 failure was the implementation
owner inferring approval from an old visible message outside an admitted
restoration path. A new parser alone cannot prevent a consumer from ignoring
its refusal or acting outside the protected actuator.

## Versioned contract and authority ceiling

Introduce a separate queried-decision evidence contract, explicitly versioned
at both the generic restoration adapter and its protected SPARK boundary.
Do not reinterpret proposal-v1, change the fixed existing SPARK wire in place,
or relabel a free-form historical reply as a structured decision. Direct user
instructions without a preceding question remain a distinct authorization
source; this contract must not invent a question for them or claim to cover
their interpretation.

For a queried decision, the following joins are mandatory:

| Obligation | Required retained evidence and rejection condition |
| --- | --- |
| AR01 original source | Exact original question and response bytes, original identities, producer identity and task/session binding. A model summary, tool acknowledgment, role label, timestamp or unkeyed digest cannot authenticate human authorship. Missing source custody leaves authority unresolved. |
| AR02 ordering | Question precedes response in independently established original order. Both records are within the captured range. Reordering a projection or resetting sequence numbers after compaction cannot establish this relation. Cross-stream order requires a witnessed join; wall-clock comparison alone is insufficient. |
| AR03 reply link | The original response identifies the exact question item and question event, or an independently authenticated decision record supplies that exact link. A later message, a nearby message, matching words or the last visible human message is not a substitute. |
| AR04 action and conditions | Exact proposal revision, action identity, parameters, target, permitted effects and conditions match the independently selected pending request. An approval of implementation discretion cannot waive an unrelated test or requirement. Material proposal changes require a new scoped decision. |
| AR05 classification | Distinguish human input, automatic goal continuation, assistant/model record, tool acknowledgment and imported content using authenticated producer evidence. A transport role of user is insufficient. Unknown provenance cannot become a human decision. |
| AR06 decision semantics | Preserve approval, denial, deferral and ambiguity separately. The evidence join checks correspondence; it must not guess a decision from free text. An unresolved semantic classification remains unresolved until the responsible authority establishes it. No timeout implies approval. |
| AR07 currentness | Join the current task, request, lifecycle, checkpoint/head and retention generation. Preserve supersession, revocation and expiry. An original valid decision can cease to authorize a current action; a newer summary cannot revive it. |
| AR08 complete dependencies | Restore the original question, linked response, action scope and currentness evidence within one shared context/input budget. Missing records, truncated tool results, omitted conditions or budget exhaustion expose a gap and block the dependent action; no partial positive. |
| AR09 operation state | Independently reconcile an interrupted action by stable operation identity before retry. A valid decision is neither proof of execution nor permission to duplicate a completed effect. |
| AR10 enforcement | Python may gather and check representation; consequential admission must be decided in the protected SPARK authority and enforced at the actuator. No adapter result, note, summary or caller Boolean substitutes for that decision. |

The pure evidence join may report correspondence or a fixed unresolved/refusal
reason. Correspondence is **not** an action grant. Restore original data and its
limitations without promoting retrieved text to controlling instructions.
When action evidence is unresolved, unrelated authorized work may continue;
request clarification only for the dependent decision that cannot be established.

## Integration order and preserved requirements

1. Specify the bounded typed SPARK input/output and its refinement from original
   records. Include source/order/action/currentness witnesses and each refusal
   state above. Freeze byte, item, sequence and processing bounds using the
   existing approved envelope; a necessary limit change requires its own review
   and explicit approval. No new numeric allowance is granted by this document.
2. Implement the evidence join in a general original-record restoration path,
   alongside the preserved fixed V5 pilot. A conditional pure proof must state
   which authenticated/current-source properties its producer supplies. Do not
   add a standalone parser and describe it as integrated protection.
3. Bind the join to actual documented capture/restore events and the protected
   publication and actuator paths. Refuse unavailable native mappings. Preserve
   `require_action_authority` refusal until the complete replacement is qualified;
   no positive action path is authorized by passing synthetic cases.
4. Run every case in the companion frozen roster, the original continuity
   fixtures and unchanged full workloads. Then run actual repeated compaction,
   restart and handoff with the same original decisions and source identities.
   Compare resumed actions with an independently frozen uncompacted baseline.

The R05 question remains pending/unverified. Both useful expensive reuse and
fresh current-policy validation remain mandatory and open. Existing capture,
retention, native containment, protected publication, proof, recovery, release
and marketplace obligations remain binding. This increment is requirements
and source evidence, not a new passing test subset or product acceptance.

## Acceptance evidence

Retain exact source/toolchain identities, strict analysis and complete proof
outputs with all assumptions and failures; source-bound runtime and fault
receipts; original question/response/action joins; current revocation evidence;
and independent review/execution. Report semantic decision accuracy separately
from representation consistency and mathematically proved policy properties.
The actual old-SDK-reply/later-R05 case must remain unresolved through repeated
compactions, regardless of display order. A correctly linked positive must
restore its evidence without itself issuing a grant. Protected authority and
actuator tests must separately establish each permitted effect and refusal.

This adapts Power of Ten controls: bounded nonrecursive joins, fixed core
storage, short routines, explicit contracts, narrow authority, checked results,
restricted dispatch and strict analysis. Python/harness allocation, source
authenticity, filesystem custody and human-intent interpretation remain outside
those pure proofs. These are adaptations, not Holzmann quotations, whole-system
assurance or avionics certification.
