# Source-bound GNATprove overload accounting

Status: experimental checker repair; full assurance gate remains OPEN.

The original report checker rejected distinct Ada overloads as duplicate names.
Accepting every different line number would instead allow a specification and
its body to replace a missing entity. The repair retains ordinary duplicate-name
rejection and introduces a closed exception registry for reviewed declarations.

`spark/proof-overloads.json` is policy shipped beside `check-proof-summary.py`.
Pin both files together with the source, report, raw diagnostics, successful
command and toolchain. The checker never searches the current directory for
policy. Missing or malformed policy refuses, even for an unrelated fixture.
Unrelated source roots need not contain the registered modules and receive no
exceptions for absent modules.

The initial registry covers `Valid`, `Decoded_As`, and `Decode` in the record
and observation wire specifications. Each has distinct parameter types for
claim, operation and witness/transition representations. Their full specification
bytes were reviewed; SHA-256 and exact declaration lines bind those exceptions
to that revision. The short declaration-token check detects misplaced registry
entries; it does not parse Ada signatures or establish their correctness.

For a registered source present under the supplied root's `src` or `tests`,
the checker requires its exact file hash and the complete name/file/line set.
Missing whole groups, substituted or repeated locations, body locations,
ambiguous paths and changed source bytes refuse. Source symlinks and symlinked
immediate source directories refuse. This is not hostile-filesystem isolation:
the qualified checkout must remain stable during inspection. Ancestor custody,
concurrent mutation, tool authenticity and execution success are external gates.

Existing unit inventory, nonzero analysis, exact unit coverage, clean detail
rows, discharged totals, raw warnings and exclusion checks remain mandatory.
The original synthetic tests are unchanged. A focused report containing test
units outside SPARK still fails the original full-project gate.

## Scope and controls

These are project adaptations of the Power of Ten safety intent, not quotations
of Holzmann's rules and not a claim of full compliance.

| Control | Application and remaining limitation |
| --- | --- |
| Simple control flow | Direct validation helpers; no new recursion. Python JSON and regular-expression internals are outside that claim. |
| Execution bounds | Registry bytes and source/group/location counts are capped. No Python worst-case execution-time proof; process deadlines remain required. |
| Allocation | Policy at most 65,536 bytes; registered source reads at most 4 MiB plus refusal sentinel. Python dynamically allocates; fixed-memory compliance is UNPROVEN. |
| Small routines | New helper bodies remain below the approximate 60-line review target. |
| Contracts | Exact source and location correspondence, full exception coverage, deliberate typed refusals and adversarial controls. No mathematical proof of Python. |
| Narrow scope | Exceptions apply only to reviewed names and source revisions. No CWD policy discovery. |
| Checked results | Strict schema, duplicate-key rejection, exact integer types, safe filenames and hash checks precede exceptions. |
| Transparent semantics | Explicit JSON registry; no source generation or signature inference. Registry edits require source review. |
| Restricted indirection | Ordinary Python/library calls; no eval, plugin loading or dynamic production dispatch added. Runtime indirection remains. |
| Strict analysis | Existing pinned Ruff correctness profile expanded to checker and both test files; no suppression. This profile is partial static analysis, not comprehensive Power of Ten enforcement. |

## Verification and use

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error \
  timeout --kill-after=5s 60s python3 -m unittest discover \
  -s spark/tests -p 'test_proof_summary*.py' -v
python3 -B spark/check-proof-summary.py spark PATH_TO_COMPLETE_REPORT
```

The second command also reads `spark/obj/gnatprove/*.spark`; a report alone is
insufficient. Synthetic fixtures validate checker behavior, not proof execution.
The retained focused pack-plan report demonstrates the original false refusal,
corrected overload-detail acceptance, and continued full-gate refusal. It is
historical evidence, not a fresh GNATprove run.

See `PROOF-SUMMARY-OVERLOADS-EVIDENCE-20261024.json` for exact source hashes,
test/static results and retained evidence. Independent review was read-only;
it did not independently execute the tests. Full-system proof, protected runtime
enforcement, installed behavior, release and marketplace qualification remain
open. This repair confers no avionics certification or publication authority.
