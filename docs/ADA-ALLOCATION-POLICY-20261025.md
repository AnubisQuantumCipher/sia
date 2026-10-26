# Explicit Ada allocation restrictions

Status: **TESTED compiler-policy increment; system acceptance OPEN**.

The shared `spark/restrictions.adc` now explicitly includes the modern guide's
DYN01 restrictions (`No_Anonymous_Allocators`, `No_Coextensions`,
`No_Access_Parameter_Allocators`, `Immediate_Reclamation`) and the static-policy
`No_Task_Allocators` restriction from DYN02. Every original restriction and
`Assertion_Policy (Check)` remains. No source routine, test, project roster,
warning policy, resource ceiling or runtime authority changed.

The tested composition is commit `369bc98a4a275f6fc601e98afdd8c8e4cdc5aa79`
plus exactly this ADC change. All ten existing project files reference it.
The receipt and source archive below bind the exact bytes. The compiler is
GNAT FSF 16.1.0 on Linux aarch64 with GPRBuild 26.0.0. Compiler acceptance is
not evidence of complete runtime-library enforcement or semantics.

## Observed verification

- Strict all-source compilation (`gprbuild -q -p -j1 -c -U`) and the original
  main build/link succeeded with empty output streams. All 15 original main
  runtime executables succeeded. The remaining project builds and their
  standalone test mains succeeded in 20 recorded phases.
- The complete `spark/tests/test_*.py` suite passed 110 tests. The original
  captured-pack regression passed 378 tests with the candidate-built native
  probe and no skips. Original tests and refusal cases were preserved.
- Positive no-allocation controls compiled cleanly for the four explicit
  allocator restrictions. Their negative controls reported the intended
  named restriction at the allocator. The first three unrestricted controls
  already failed strict allocator warnings: they establish recognition and
  diagnosis, **not unique causation of rejection**. The task control's final
  version has a clean unrestricted/restricted differential.
- Earlier controls remain FAILED: the initial allocator baseline warning;
  the positive fixture's collision with `Standard.Positive`; the coextension
  and parameter allocator baseline warnings; and the task fixture's unrelated
  always-false comparison warning. The last defect was repaired in the test
  fixture, without suppressing warnings. Intentional allocating/task fixtures
  were compiled only, never executed.

Per build: 60 seconds, 5-second termination grace, one build worker. Standalone
Ada test mains: 5 seconds each. The newly composed remaining-project supervisor
has a 600-second aggregate bound; it does not enlarge any per-build deadline.
Both Python protocol rosters retain 60-second whole-run deadlines and 5-second
grace. Address-space and output-file limits remain 2147483648 and 536870912
bytes. The pack run retains its original isolated filesystem/network/process
environment and zero core-file allowance. These are job limits, not proved
whole-service or descendant resource bounds.

An existing independent GPT-6.1 reviewer inspected the exact configuration,
controls, diagnostics and terminal records and found no blocker to this narrow,
non-final checkpoint. This was read-only review, **not independent execution**.
Some records retain a runner-observed unchanged Boolean rather than both full
endpoint maps. Admission maps and a separately timed current readback are
retained; the latter does not retroactively establish at-run custody. Link and
remaining-project summaries do not independently establish complete tool/input
custody. No fresh full GNATprove campaign is claimed for this configuration.

## Guideline mapping and remaining work

This table is an engineering adaptation, not a quotation from Holzmann or the
Ada guide. The [exact references](STANDARDS-REFERENCE-RECONCILIATION-20261025.md)
remain normative. Common links are A07 resource authority, A13 reproducible
acceptance, A21 traceability, and Power of Ten rules 3, 6, 9 and 10. The existing
[Power of Ten assessment](POWER-OF-TEN-ASSESSMENT.md) remains open where its
source, runtime or enforcement scope is incomplete.

| Guideline | Component and selected policy | Classification and enforcement evidence | Required change or remaining evidence |
| --- | --- | --- | --- |
| DYN01 | Ada project sources: forbid anonymous allocators, coextensions and access-parameter allocators; request immediate reclamation | Literal compiler-policy implementation; strict build and named negative controls TESTED | Actual `Immediate_Reclamation` behavior has no runtime oracle here. Imported/prebuilt libraries and RTS coverage remain UNPROVEN. |
| DYN02 | Ada authority: retain traditional static allocation policy | Partial literal implementation: original `No_Allocators`, now explicit `No_Task_Allocators`; original `No_Implicit_Heap_Allocations` and `No_Unchecked_Deallocation` retained | Full exclusion of access-to-object types and user pools needs semantic checking. A token search is not that check. No complete DYN02 compliance claim. |
| DYN03 | Alternative policy permitting access to declared objects | Justified non-applicability as an unselected alternative for the intended static authority policy | Do not silently relax DYN02 or call alternative-policy non-selection proof of the current implementation. Any policy change requires the existing deviation process. |
| DYN04 | Alternative allowing allocation during startup only | Justified non-applicability as an unselected alternative | No startup allocation exception was introduced. Python/Linux runtime allocation remains outside the Ada guarantee. |
| DYN05 | Alternative using application-defined storage pools | Justified non-applicability as an unselected alternative | No pool design is adopted. A bounded pool alone would not prove safe object lifetime or aliasing. |
| DYN06 | Ada authority, adapters and environment task | Unresolved gap: no complete maximum-stack analysis | Establish call-chain, secondary-stack, interrupt/RTS and external-call assumptions and compare bounds with provisioned stacks. `gnatstack` was unresolved on the configured PATH, not proved absent from the machine. No-heap restrictions do not bound stack. |
| RCL01 | Ada sources: exclude unchecked deallocation rather than permit and prove each use | Literal exclusion mechanism retained; whole-composition compliance unresolved | Confirm semantic/runtime closure and foreign ownership boundaries. Python object/descriptor cleanup needs separate tested lifetime contracts. |
| RCL02 | Same Ada exclusion policy | Literal exclusion mechanism retained; no claim about all foreign frees | Audit C/Linux/FFI allocation provenance and cleanup on failures separately. |
| RCL03 | Same Ada exclusion policy; no application pool selected | Literal exclusion mechanism retained; no pool correctness claim | Imported dependencies and runtime storage ownership remain in the assumption ledger. |
| CON01 | Ravenscar is an alternative concurrency policy | Unresolved applicability for any future Ada service; not enabled by this change | Define the actual task/scheduling model before selecting a profile. `No_Task_Allocators` does not forbid task declarations. |
| CON02 | Jorvik is an alternative to Ravenscar | Unresolved applicability; neither profile is claimed | Do not combine alternative profiles as simultaneous mandates. Python/Linux orchestration does not inherit either profile. |
| CON03 | Ada shared state and Python/Linux service coordination | Unresolved integrated guarantee | Qualify protected/shared-state access and process authority in the actual runtime. Cooperative locks alone do not protect against hostile same-user processes. |

For Python and Linux, these controls are language adaptations: bounded decoding,
admission budgets, checked resource acquisition/release and enforced process
limits must surround the small authority core. Dynamic allocation, garbage
collection, kernel buffering and general-purpose scheduling prevent a literal
whole-runtime static-allocation claim. Existing resource, custody, publication,
continuity, recovery and installed acceptance obligations remain controlling.

The shared ADC is automatically consumed by the existing project builds.
Hosted CI does not yet qualify this GNAT allocation-control lane. A compiler
control lane, semantic access-type/pool checking, stack evidence and fresh
complete proof are still required. `gnatcheck` was unresolved on the configured
PATH; this is an observation, not a claim that regex checks can replace it.

RPP01–14, EXU01–04, OOP01–07, SWE01–04 and applicable Ada 95 chapters 2–10 still
need complete implementation mapping and acceptance. This increment supplies
no deviation approval and closes none of the full-system or release gates.

## Reproducible evidence

[The receipt](ADA-ALLOCATION-POLICY-20261025.json) binds the changed ADC, tool and
input records, raw results, original failure controls, reviewer scope and
[portable evidence archive](evidence/ada-allocation-policy-20261025.tar.gz).
Extract into a new directory; inspect the manifest and commands before use.
The archive retains the exact tracked SPARK inputs and control fixtures, not
production credentials or a deployed installation. Current binary identities
are recorded; binaries and generated object directories are excluded.

The smallest next step is a reproducible compiler-control CI lane and semantic
qualification of the selected static policy, followed by the original complete
proof and integrated resource gates. Do not rerun unchanged failed proof or
runtime campaigns without a concrete repair and its preservation argument.
