# Recovery proof scope: acceptance remains open

Read-only source and retained-evidence reconciliation, 2026-10-25. This report
does not record a new compiler, GNATprove or runtime execution.

The canonical unfinished recovery files match the retained complete-package
attempt that exited 124 under its original 120-second limit:

The retained envelope is
`sia-assurance-evidence-20261019/takeover-recovery-records-early-generation-complete-unit-diagnostic-v1/receipt.json`
(SHA-256 `b118e5f676971b7ce2764e78e711a2ef7035e45679a7d642f5d3fb95d864da89`).
Its `complete-package-proof/result.json` is byte-identical to the copied
`ownership-transfer-20261024/recovery-scalar-relation-source-v1/retained-failure/result.json`
(SHA-256 `56a6e141dc3df2b49f403a64a310326438e7e9c954e0fd0d75069c1d01490a8a`).
These local evidence references describe the same failed execution, not two
independent runs.

| Input | SHA-256 |
| --- | --- |
| Specification | `049f60cec841ff7fe93d077c4b773d89abb6203254a05c7474dfd1b660307356` |
| Body | `4bdd9b66eaf8d9535746223481f0d5a12af5d45a034efe74ca66858ea607e253` |
| Original harness | `60aa00a7b59cef1b5dc5d5941c52989a43cedc5271ad661c577e1186c05a0088` |
| Project | `162eda509632bb7176386c2257fa7862086f119c2f7a3ba80fb95e2c744d5894` |

No final complete `.spark` result or summary was retained for that failed run.
Partial Why3 session timeout leaves identify affected entities but do not
establish the exact source formulas. In particular, a session ordinal such as
`def'vc.97` cannot be joined to a source `GP_Check97` solely by its number.
Warnings, missing reports and unsaved tasks remain visible unknowns.

The already prepared private scalar-relation candidate retains unchanged
encoder/decoder bodies and a frozen original predicate. It adds the Ghost
procedure `Recovery_Permit_Wire_Tests.Check_Operation_Relation_Equivalence`
to require universal equivalence without assuming its postcondition. The
candidate is UNCOMPILED / UNPROVEN / NOT ADOPTED. Its source review does not
establish equivalence or improved proof performance.

The retained package command uses `-u sia_recovery_records.adb`. That command
does not select the equivalence procedure in `recovery_permit_wire_tests.adb`.
A future successful package result must therefore not discharge the new
equivalence requirement. Qualification must retain separate, exact-source
evidence that the harness entity and its postcondition were actually analyzed
and proved, alongside complete package proof and every original runtime test.
Concrete Ghost calls are not independent runtime decoder tests. A banner,
exit status, or package summary alone cannot establish harness coverage.

Required future evidence includes the full source composition, exact commands
and toolchain, complete proof reports with entity/obligation coverage, all
warnings and assumptions, the original runtime roster and negative controls,
and independent review/execution required by the original acceptance plan.
The native supervision prerequisite and existing time/resource/job caps remain
binding. No job expansion or proof retry is authorized by this documentation.

Actual GPT-6.1 independently reconciled source hashes and retained failures.
It executed no build, proof or test. No additional source rewrite is justified
from timeout ordinals alone. The next recovery implementation step remains
qualification of the existing execution path, then the already prepared
candidate; there is no duplicate implementation or new acceptance claim.
