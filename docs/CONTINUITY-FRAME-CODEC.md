# Fixed continuity request boundary

This experimental increment joins the proposed 32,768-byte request frame to the
existing pure continuity classifiers. It validates the magic, version, closed
operation code, exact operation-specific length, reserved header, every nested
record and every trailing byte. Restore and transition records retain all
representable fields, including values the policy rejects. Malformed input
returns the entire canonical empty request and only the malformed decision.
Unused request and result families are canonical.

`Evaluate` specifies complete decoded-field correspondence and exactly the
existing restore/transition classifier result. Fixed payload helpers state
byte correspondence explicitly. There is no I/O, checkpoint publication,
identity authentication, source resolution or external-action path. Sender
descriptors and proposal classifications establish no authority.

## Evidence and retained failures

The [source-bound manifest](CONTINUITY-FRAME-WIRE-EVIDENCE.json) and its
reproducible bundle retain all three development attempts, source overlays,
base archive, tool identities, commands, logs and raw diagnostics. Private
storage status is excluded from the bundle.

- **FAILED v1:** strict compilation rejected the unqualified `Decision` type
  because a claim-kind literal has the same name. The new type is explicitly
  named `Frame_Decision`; no warning or diagnostic is suppressed.
- **TESTED v2:** strict compilation and all fourteen runtime harnesses passed.
  The scoped core proof discharged 58 reported checks. The complete frame
  harness reached its 120-second deadline without a fresh summary.
- **TESTED v3:** adds the independent review's missing `Refuse` precondition
  and nonconstant policy-path controls. Strict compilation and all fourteen
  runtimes pass. The scoped core proof again discharged 58 checks, with all
  fourteen entities analyzed and no justified/unproved or non-information raw
  diagnostics. The complete harness again reached 120 seconds without a
  fresh summary. Its callers and complete assertions remain **UNPROVEN**.

Core proof is modular on existing dependency contracts. These overlapping
reports are not summed or treated as full-project coverage. The earlier
600-second full-project failure remains open; no new full-project run or
larger proof budget is claimed.

After checkpoint `15b613aec79c7ebb5374941d4c1087b986b1d066` was pushed and
read back, a fresh archive with no overlay repeated strict compilation,
all fourteen runtimes and the scoped 58-check frame-core proof. The
[committed reproduction](CONTINUITY-FRAME-COMMITTED-EVIDENCE.json) binds the
complete source inventory, exact commands/caps, equal tool rosters and raw
reports. The [actual GPT-6.1 correspondence review](evidence/continuity-frame-committed-review-v1.txt)
confirmed that limited scope without replaying proof. The unchanged failing
complete harness and full-project campaign were not repeated or relabeled.

Tests include independent nonuniform frame vectors distinguishing both
checkpoint positions, current evidence, and first/interior/last transition
observations with complete expected-record comparisons. Header byte sweeps,
all reserved/trailing positions and malformed nested slots test complete
refusal after distinctive otherwise-valid content. Raw fixtures exercise
`References_Proposed`, `Reconcile_Repository`, `Transition_Proposed` and
`Task_Mismatch`; a constant first-refusal dispatcher cannot satisfy them.
The positive transition has no changed operations. It does not independently
qualify changed-operation event composition; existing transition tests and
the exact decoder/classifier contracts retain their separate obligations.

The actual GPT-6.1 read-only reviewer found the two concrete harness gaps and
confirmed their repair. It did not replay proof or grant complete acceptance.
Both reports are preserved in the evidence bundle.

## Power of Ten adaptation

| Rules and safety intent | Mechanism here | Remaining limitation |
| --- | --- | --- |
| 1–2: simple flow and execution bounds | Static calls, finite array ranges, total decoder and termination contracts | No stream/EOF deadline, syscall bound or WCET claim |
| 3: controlled allocation | Fixed arrays and unchanged allocation restrictions | Physical stack, compiler copies and whole-process capacity unqualified |
| 4: reviewable routines | Small extraction, decoding and composition routines; separate scenarios | Size alone proves nothing |
| 5: meaningful assertions | Exact acceptance, field correspondence, complete refusal and exact classification | Complete caller/harness proof remains open |
| 6: narrow authority and scope | Pure packages, null globals, explicit dependencies | One procedure-local observation temporary accommodates the prover restriction |
| 7: checked inputs and results | Closed codes, exact lengths, nested validation and checked nested outcomes | Representation is not authentic evidence |
| 8–9: explicit semantics and indirection | Explicit protocol values and fixed payload copies; no pointers/dispatch | Compiler and runtime remain assumptions |
| 10: strict analysis | Unchanged warnings-as-errors and proof gates; failures retained | No whole-system compliance or certification claim |

These are cross-language adaptations, not Holzmann quotations. The original
[Power of Ten assessment](POWER-OF-TEN-ASSESSMENT.md) remains controlling.
JACKAL checked framing/vector arithmetic as `exact`, not `formal-bounded`;
the full responses are retained in the bundle. This does not validate the
chosen protocol or prove code correctness.

Next implementation is the bounded response and one-request I/O adapter with
explicit resource qualification and differential process tests. Fixed Ada
arrays alone cannot establish truncation/excess/EOF handling, process failure,
authentication, capture completeness or actual harness restoration. Complete
proof/reproduction, independent acceptance, producer custody, fault-tested
publication and installed continuity remain required. This increment is
uninstalled and grants no universal compaction or recall guarantee.
