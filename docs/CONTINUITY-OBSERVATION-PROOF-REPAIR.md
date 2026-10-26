# Continuity observation proof repair

Status: focused proof repair; complete project qualification remains failed.

The source checkpoint `9463b588843ec05b3cd39208e15eb2d75f1e72f5`
retained incomplete proof evidence. A fresh diagnostic of
`Check_Transition_Operations` now identifies a specific unresolved obligation:
preserving `Valid (After_Payload (Bytes))` across an arbitrary loop iteration.
GNATprove reported one unproved assertion among 45 checks. This is a proof
failure; it is not a witnessed decoder failure or permission to waive the
invariant. The original source, raw diagnostics and failed summary remain
retained in `continuity-observation-transition-operations-diagnostic-v1`.
The [failed summary](evidence/continuity-observation-frame-before-v1.txt)
preserves its exact declared scope.

The repair adds a frame invariant stating that bytes outside the two operation
digest regions equal their values at loop entry. It makes the unchanged scalar
and reserved-byte facts available at the loop's proof cut point. The original
assignments, vectors, validity invariant and result assertions remain intact.
There is no authority-code change, assumption, proof exclusion, warning
suppression, increased resource cap or narrower input domain.

The new focused diagnostic discharged all 47 reported checks in the same
single subprogram, including initialization and preservation of the added
invariant. It used the original 120-second command deadline, 10-second prover
limit, 512-MB prover limit and one job. Its fresh summary and raw diagnostics
are retained in `continuity-observation-transition-operations-diagnostic-v2`.
The [passing summary](evidence/continuity-observation-frame-after-v2.txt)
records that same focused scope with the additional invariant obligations.
The separate unchanged `Check_Claim` diagnostic discharged 30 checks. These
scopes must not be added together or substituted for the all-unit gate.

An [independent GPT-6.1 source review](evidence/continuity-observation-frame-review-v1.txt)
found no blocker and confirmed that the
original tests were preserved. That reviewer did not independently inspect
the diagnostic receipts in that review. The model-generated assessment is
separate from compiler and prover evidence.

The subsequent full development-v6 campaign passed the strict build and all
eleven runtime harnesses, then reached the unchanged 600-second proof deadline
with exit 124 and no fresh final summary. Its completed observation-harness raw
report has no non-information diagnostics. Other units remained incomplete;
coverage validation was UNRUN. This is not complete project qualification.
The [derived manifest](CONTINUITY-OBSERVATION-FRAME-EVIDENCE.json) binds the
archives, source overlays, commands, tools, logs and focused reports. Its
generator reproduced the manifest byte-for-byte and refused to render it while
the full campaign was still running. Development-v5 and all focused failures
remain retained without relabeling.

This change applies the Power of Ten intent of explicit, reviewable contracts
and tractable verification. It does not establish fixed-memory behavior of
Python/Linux, authenticate observation inputs, qualify a harness adapter or
demonstrate semantic continuity through compaction.

Acceptance still requires the complete strict build, every original runtime
harness, full-project GNATprove and raw/summary coverage gate, followed by
fresh committed-source reproduction and independent evidence review. The
600-second full-project deadline remains unchanged. A missing summary, a
timeout or an unfinished run remains a failure to establish acceptance.
