# Fixed current-evidence record boundary

This experimental increment decodes the proposed fixed 12,128-byte
Current_Evidence record in [the continuity protocol](../spark/CONTINUITY-WIRE.md).
Its contract preserves every context, identity, generation, witness and
observation field. Malformed representation returns the complete typed empty
record. All observation slots are checked, regardless of availability, and
both witnesses are checked regardless of their presence flags.

These are sender-supplied descriptors. Successful decoding does not establish
that a checkpoint is current, an original is retained, a witness is durable,
or an operation occurred. The existing policy can reject representable values,
including an absent but nonempty witness, model-authored permission reference,
and acknowledged operation with no result. The decoder preserves those values
for that decision. It does not generate authority or normalize them into success.

## Power of Ten adaptation and tests

| Safety intent | Concrete mechanism | Unresolved boundary |
| --- | --- | --- |
| 1–2: simple control flow and bounds | Pure static calls, fixed array ranges, total decoders, termination and prefix/frame contracts | No syscall deadline, WCET or end-to-end termination proof |
| 3: controlled allocation | Fixed byte/typed arrays and existing allocation restrictions | Physical stack capacity, runtime copies and whole-process resource budgets remain unqualified |
| 4: reviewable routines | Small extraction, header and record-decoding routines; separate test scenarios | Line count is a review aid, not a correctness argument |
| 5: meaningful contracts | Exact acceptance, complete field correspondence and complete typed-empty refusal | Modular dependencies and toolchain assumptions remain |
| 6: narrow scope | Null globals and explicit input/output dependencies | Composite loop temporaries have procedure scope because of the documented GNATprove restriction |
| 7: checked inputs/results | Header generations, both witnesses, all nested scalar codes and reserved bytes; nested decoder outcomes asserted | Digest equality and flags do not authenticate their producers |
| 8–9: explicit semantics and restricted indirection | Explicit wire mappings and bounded copies; no dispatch, pointers or metaprogramming added | Compiler/runtime implementation remains an external assumption |
| 10: strict analysis | Unchanged warnings-as-errors, proof settings and retained failures | Focused proof does not establish complete-project or installed-path acceptance |

This is an adaptation, not a quotation or compliance claim. The original
[Power of Ten assessment](POWER-OF-TEN-ASSESSMENT.md) remains controlling.

Tests use independent nonuniform literal header, witness and first/interior/last
observation vectors with complete expected-array comparisons. They distinguish
an all-zero wire record from the typed empty record, sweep header generation
and Boolean codes, mutate reserved header/witness positions, sweep selected
availability positions and reject malformed nested content in every slot.
The review-requested controls additionally exercise malformed nested content
under Missing, Retained and Retracted. Existing Unknown controls remain.
All earlier runtime harnesses remain in the project and acceptance runner.

## Evidence and open gates

The [scoped manifest](CONTINUITY-CURRENT-WIRE-EVIDENCE.json) binds retained
source overlays, base archive, exact commands, tool identities, logs and raw
reports. Its reproducible bundle excludes private storage-preflight metadata.
The retention script checks exact command arguments/caps and before/after tool
rosters; it is a consistency aid, not a qualified system acceptance gate.

Development v1 failed strict compilation because two expected digest aggregates
lacked a constrained type qualification. Adding `Digest'` fixed their bounds;
the original failure remains retained. Development v2 passed the strict build,
all thirteen runtime harnesses and the focused core proof, which discharged
73 reported checks without unresolved summary or raw diagnostics. The combined
harness proof reached its 120-second deadline without a fresh summary.

The subsequent v3 source adds the independent review's availability/refusal
controls. Its fresh strict build, all thirteen runtime harnesses and scoped
73-check core proof passed. Its combined harness proof also reached 120 seconds
without a fresh summary. Both terminal outcomes and unchanged tool identities
are retained; no prior source result substitutes for the changed tests.
The independent source follow-up confirmed that the new controls close its
concrete gap while preserving every original fixture and assertion.
An [independent evidence review](evidence/continuity-current-wire-review-v1.txt)
confirmed source/archive/report correspondence and the limited core scope.
It performed no proof replay and granted no complete-system acceptance.

One job, 512 MB per prover, the 10-second check limit and existing command
deadlines remain unchanged. No proof exclusion, warning suppression, assumption
annotation, original-case removal or additional permission is introduced.
The earlier full-project 600-second failure remains open. A passing core proof
or test subset cannot discharge it.

Next acceptance requires complete harness and full-project proof, raw/summary
coverage checks, exact committed-source reproduction and independent evidence
review. The next implementation step is outer framing and exact classifier
composition. Authenticated producers, I/O/resource qualification, original-event
capture, fault-tested publication and real harness restoration remain separate
requirements. This increment is uninstalled and establishes no universal
compaction, recall-latency or avionics guarantee.
