# Complete proof diagnostics

Status: fresh development build, all eight harnesses, full proof and complete
diagnostic validation passed. Independent completed-evidence review found no
blocker within that scope; fresh committed reproduction remains required.
No broader zero-warning or Power of Ten acceptance is claimed.

The raw `.spark` output behind the incremental continuity proof contains
miscellaneous warnings even though its final flow-detail rows are clean.
The existing project enabled warning errors and proof warnings, but did not
enable every optional diagnostic. The old summary validator only examined the
flow-detail channel. The retained inventory contains array-initialization
precision and arithmetic-reassociation warnings; it remains a failed
zero-warning check, not an approved deviation.

AdaCore documents that these diagnostics are normally disabled and describes
`-W=all` for enabling all tagged warnings. Warning errors act after category
selection; they do not enable disabled categories.
See [miscellaneous warnings](https://docs.adacore.com/spark2014-docs/html/ug/en/source/misc_warnings_table.html)
and [warning controls](https://docs.adacore.com/spark2014-docs/html/ug/en/source/how_to_use_gnatprove_in_a_team.html).

The repair requests all tagged warnings in the existing proof profile and
retains warning errors, proof warnings, all-unit coverage and resource caps.
Affected test loops use explicit whole-array delta updates on initialized
arrays. The same index/value mutation, fixture, loop invariant and expected
result remain. The request-wire sum now explicitly preserves its prior left
association. Warning disappearance alone is insufficient: all original
semantic obligations and runtime controls must still pass.

The summary validator additionally reads a bounded raw report for every
required unit. It refuses missing/malformed/oversized input, duplicate JSON
keys, non-JSON numeric constants, warning/error/unknown diagnostic severities
in `warn_error`, `flow` or `proof`, and missing or nonempty explicit
assumption/exclusion lists. Normal modular `assumptions` dependencies remain
distinct from `pragma_assume`. Informational messages remain visible in
retained output and are not mislabeled as warnings. This checks a report
format; it does not authenticate the tool, source or result. Those bindings
remain separate acceptance obligations.

Retained development evidence is under
`/home/sicarii/Work/sia-assurance-evidence-20261019/`:

- `continuity-raw-warning-inventory-v1.json`: exact raw-report identities and
  the discovered diagnostics.
- `proof-warning-gate-tests-v1.log`: the first 17 synthetic checks passed.
  Independent review then found uncovered `flow`/`proof` channels and accepted
  non-JSON numeric constants; this earlier pass does not close those gaps.
- `proof-warning-gate-tests-v2.log`: 18 strengthened positive/negative tests
  passed, including a duplicate key that would otherwise erase a warning,
  every diagnostic channel, malformed constants and modular-dependency control.
- `proof-warning-gate-real-negative-v1.json` and its log: the initial new checker
  correctly refused the earlier real report with disabled warnings.
- `proof-warning-gate-real-negative-v2.json` and its log: the strengthened
  all-channel checker also refused that real report.
- `continuity-policy-development-v10-result.json`: strict build and all eight
  runtime harnesses passed; the fresh all-unit proof timed out at 600 seconds.
  Its clean partial reports do not satisfy complete coverage.
- `proof-warning-gate-review-v2.txt`: independent model-generated review of the
  repaired gate, with the earlier findings retained. This is an assessment,
  not proof or execution evidence.

The partial proof records show CVC5 reaching its 10-second limit before Z3
discharges several continuity and request-wire checks. Development-v11 places
Z3 before CVC5 and Alt-Ergo, retaining the same prover set, obligations,
warnings, full-unit scope and resource caps. This is a changed verification
configuration, not an identical rerun. Prover selection is documented in the
[SPARK guide](https://docs.adacore.com/spark2014-docs/html/ug/en/appendix/alternative_provers.html).

Development-v11 completed the full campaign in a new source/build directory:
strict build, all eight runtime harnesses, full proof and raw/summary validation
returned zero. GNATprove reported all 788 checks discharged across the complete
16-unit scope, with no justified or unproved checks. The validator accepted all
required raw diagnostic channels and found no declared assumptions or exclusions.
The [derived receipt](PROOF-WARNING-EVIDENCE.json) binds source inputs,
before/after proof-tool identities, commands, raw reports and the
[versioned summary](evidence/proof-warning-v1.txt). Its generator also checked
the receipt and summary against retained bytes. This is a fresh development
overlay result; it is not yet committed-source reproduction or runtime
continuity acceptance.

The [independent completed-evidence review](evidence/proof-warning-development-review-v1.txt)
checked source/archive, tool, raw-report and retained-failure bindings. Its
model-generated assessment is separate from the command outputs.

The optional timing-wrapper launch first failed because `/usr/bin/time` is
absent. `continuity-policy-development-v11-launcher-failure.json` records that
pre-run failure; no proof had started. The unchanged runner then executed
without that optional wrapper. V10 and the earlier committed timeout remain
failed runs; V11 does not relabel either one.

The earlier 782 discharged obligations remain evidence for their recorded
source/profile. They do not establish zero-warning compliance. Fresh build,
every harness, full proof, complete raw diagnostics, independent review and
exact committed reproduction are required to accept this repair. None of
these controls establishes runtime continuity or system certification.
