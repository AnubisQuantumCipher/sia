# Partial Python correctness analysis

This increment adds a pinned correctness-analysis lane for
`scripts/assurance_acceptance_manifest.py` and its unittest module. It does not
close Power of Ten rule 10, the complete source inventory, or system acceptance.
Holzmann's original paper remains normative; the analyzer configuration below
is a project control, not a quotation or substitute for that paper.

## Prospective scope and enforcement

Ruff 0.17.1 is hash-locked to its official Linux aarch64 and x86_64 wheels.
The local aarch64 executable was verified and exercised; the x86_64 CI lane
still requires its own execution evidence. CI retains the existing hashed
dependencies and adds the pinned analyzer without a source-build fallback.

Independent review selected syntax/runtime-name errors, common bug patterns,
built-in shadowing, broad exception problems, Pylint error/warning checks and
unused suppressions as a finite first lane. The corresponding selectors
`E4,E7,E9,F,B,A,BLE,PLE,PLW,RUF100` expand to the
[frozen list of 167 stable rules](evidence/assurance-ruff-rules-v1.txt).
CI checks the list's byte limit and exact hash before passing it to the pinned
analyzer; an empty or altered list cannot silently remove checks. It analyzes both named
files regardless of Git ignore settings, disables fixes, preview and caching,
ignores no diagnostics through inline suppression, and rejects suppression
directives in source. No ignore list or warning waiver is introduced.

The lane uses one analyzer thread, a 30-second execution deadline and a
5-second kill escalation. Each input is limited to 1 MiB. Success requires
exit zero, empty stderr and an empty JSON diagnostic list, parsed within a
1 MiB output limit. Malformed output, warnings, configuration errors and
timeouts fail the step. These are containment controls, not a proved memory,
stack, termination or worst-case execution-time bound for Ruff or CPython.
Console diagnostic previews are limited to 64 KiB per channel; truncating a
preview cannot turn a failed process or nonempty stderr into success. The
parser bound does not establish an operating-system quota on output files.

## Repairs and retained results

Both paired-roster `zip` calls now specify `strict=True`, preserving the
existing exact roster/length guards. An unexpected later length mismatch
therefore cannot silently truncate a comparison. The CLI's existing explicit
refusal boundary handles `ValueError`. One unused variable in the newer
numeric-row regression was renamed; its complete mutation set and oracles
remain. No original unittest assertion or exception test was replaced.

On the retained development overlay, all 26 acceptance-manifest tests pass
with warnings treated as errors. All four original numeric-roster
counterexamples refuse. The actual draft remains `INCOMPLETE`, with
`authority: NONE` and 434 metadata gaps. This module-only run is separate from
the earlier combined 30-test run that also included four inventory tests.
The selected analysis reports no diagnostics or stderr, and the exact CI
shell block passes locally. Remote CI and fresh committed-source reproduction
remain separate gates.
The [versioned evidence](ASSURANCE-PYTHON-ANALYSIS-EVIDENCE-V1.json) separates
the historical checker repair from the later CI configuration and preserves
the failed baseline and intermediate configuration. Local empty-rule and
suppression controls refused as expected; their receipts lack per-fixture
input hash maps, so independent sealed replay remains required.
The analysis-document hash binds its snapshot before this evidence-link
paragraph was added; the CI, analyzer inputs and frozen rule bytes are unchanged.

## Findings outside this lane

The original unfiltered `ALL` baseline exited 1 with 1,832 findings and
incompatible-docstring configuration warnings. That failed diagnostic remains
retained. It was an exploratory inventory, not an adopted policy requiring
incompatible conventions. It is never relabeled as passed by the smaller lane.

The following applicability work remains visible:

- Complexity findings in `depth_check` and `check_case_oracle`, interface
  findings in `obligation` and `check_power_control`, and resource/protocol
  literals require explicit review and any justified repairs. No threshold
  was raised to fit this source.
- S603 flags the existing real-process CLI refusal test. Review found a fixed
  argument list, a known interpreter/checker and no shell or untrusted command
  construction. The finding remains a documented review obligation; the
  subprocess test and its error oracle remain intact, with no suppression.
- Pytest migration rules do not apply to this unittest runner. Its assertions
  and exception oracles are preserved. Mutually exclusive docstring rules
  cannot define one coherent convention. Quote, formatting, annotation,
  import, naming and package-layout suggestions remain distinct from evidence
  of a correctness defect; none establishes a proof or grants acceptance.
- Exception-layout, comprehension and performance suggestions require
  semantic review before any change. No automatic fixes were used.

Comprehensive security and type analysis, complete call graphs, bounded
allocation and iteration, native/runtime dependencies, daily analysis and the
rest of the Python/shell/native source remain OPEN. Selecting this incremental
lane does not waive any applicable requirement or accept a known violation as
compliant. Any actual policy deviation still requires the operator's explicit
approval and written risk justification under the existing assurance rules.
