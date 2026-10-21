# Continuity response harness proof repair

This is a scoped test-harness proof repair, not full-project or installed
acceptance. The [source-bound evidence](CONTINUITY-RESPONSE-HARNESS-REPAIR-EVIDENCE-V1.json)
retains the original failures and the repaired source separately.

On the unchanged source, a diagnostic of `Check_Literal_Results` passed. The
separate `Check_Unused_Families` diagnostic reached its existing 120-second
deadline with exit 124 and no fresh summary. That result localized a costly
helper; it did not identify a false assertion or a decoder execution defect.
The original complete-harness timeouts also remain historical failures.

The repair moves the existing family-check body into a statically called
`Check_Unused_Values`, parameterized by the original `Restoration` and
`Transition_Result` types. Both original loops, their complete domains,
statement order, literals and assertions remain. The helper is proved for
arbitrary admitted parameter values. No precondition, assumption, proof
exclusion, warning suppression, resource increase or production-code change
was introduced. Its local outputs are overwritten before use; no prior
iteration's state was consumed by the original body.

Independent actual GPT-6.1 source review found no concrete preservation
blocker. The retained execution uses committed `b947dbd` plus exactly the
reviewed test-file overlay. Under the unchanged strict profile and limits:

- The new helper's focused proof passed, reporting 9 checks.
- The strict project build and all fifteen original runtime harnesses passed.
- The complete response-harness proof passed, reporting 90 checks and all
  nine source declarations analyzed. Justified and unproved columns are empty;
  raw channels contain no non-information diagnostics or explicit
  `pragma_assume`, `skip_proof` or `skip_flow_proof` exclusions.

These overlapping scopes must not be added together. Ordinary modular
dependencies remain recorded; the transport, authenticated producers,
protected authority and installed continuity are outside this proof.
The improvement makes the retained assertions tractable through a smaller
proof boundary. Runtime tests still exercise every original combination.

The [fresh committed-source reproduction](CONTINUITY-RESPONSE-COMMITTED-EVIDENCE-V1.json)
at `1292d328ebc27680a040a263a7445cb04b2d82bd` uses a new archive with no
overlay. Strict build, all fifteen original runtimes and complete response-unit
proof pass again, with 90 reported checks and all nine intended declarations.
Source/tool identities stayed unchanged and the raw diagnostic/exclusion
inspection passed. No focused helper proof was rerun; the result is a separate
committed execution, not a relabeling of the development overlay.

Complete all-unit proof and its original raw/summary coverage gate remain required;
the inherited full-project timeout is not closed by this unit result.
All other A/G/C and Power of Ten obligations remain binding.
