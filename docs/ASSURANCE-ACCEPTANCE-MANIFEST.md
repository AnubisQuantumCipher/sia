# Experimental acceptance traceability manifest

This increment addresses A21 and the additive completion contract. It does not
complete A21 or accept any system behavior. The generator preserves A01–A24,
G1–G6, C01–C14 and ten additional mandatory Power of Ten rows. The rule text
in [the assessment](POWER-OF-TEN-ASSESSMENT.md) is an adaptation; Holzmann's
original paper and rationales remain normative. The new
[contract epoch](ASSURANCE-COMPLETION-CONTRACT-20261021-V2.txt) makes the rule
assessment a completion requirement. Earlier contract artifacts remain intact.

Run from the checkout root:

```sh
python3 -B scripts/assurance_acceptance_manifest.py draft > draft.json
python3 -B scripts/assurance_acceptance_manifest.py audit --manifest draft.json
python3 -B -m unittest tests.test_assurance_acceptance_manifest -v
```

`draft` emits data to stdout and never installs or executes it. `audit` returns
0 for `STRUCTURALLY_VALID`, 2 for `INCOMPLETE`, and 1 for `REFUSED`. Every result
has `authority: NONE`. An audit success means only the implemented metadata
checks passed. It cannot authorize effects, release, or mission completion.
The versioned draft deliberately leaves candidate identity, campaign cases,
oracles, dependency bases and Power of Ten controls OPEN. Its findings are
work to finish, not waived obligations.

## Checks implemented

The plan binds the exact normative document bytes and rows. Removing,
reordering, adding or weakening an obligation refuses. Minimum scope, positive
and negative role, and required evidence kinds are joined on the same case;
a component refusal cannot replace installed success or recovery. Linked
cases carry source, configuration, toolchain, workload, fault cut, command,
environment, approved deadline class, resource-plan reference, oracle reference
and expected result. Commands are data and are never run by the checker.

Numeric-looking table IDs are examined before validating their supported width.
Unsupported, padded or suffixed IDs refuse even with different Markdown cell
spacing. Independent review reproduced an earlier omission of `A100`, `G10`,
`C100` and rule `100`; the failing counterexamples are preserved with the
[repair evidence](ASSURANCE-ACCEPTANCE-MANIFEST-EVIDENCE-V1.json).

The intended proof roster is derived from the selected project's current
`src` and `tests` Ada files, project and restrictions bytes. G2 requires a
full-project positive proof case. Scoped or invented units cannot substitute.
The existing [raw proof gate](../spark/check-proof-summary.py) remains required:
this tool compares declared unit identities and does not parse proof
obligations, validate discharged checks or replace that gate.

Evidence references require matching file hashes, plan, source, configuration,
toolchain, scope and expected execution result. Execution and independent
execution need distinct declared producers and run identities. Review records
declare actual `gpt-6.1-sol` and the reviewed source/configuration/scope/cases.
A review cannot substitute for required independent execution. These declarations
are metadata: authentication, actual model identity and execution provenance
still require independent evidence verification.

Each Power of Ten rule requires separate applicability records for production,
adapters, scripts, tests, libraries, experiments and third-party/runtime
assumptions. Each record needs an exact source inventory and explicit adapted
controls linked to check commands, outcomes and evidence through case IDs.
OPEN, FAILED, UNPROVEN, ASSUMED and OBSERVED controls, remaining violations or
missing checks prevent structural closure. A `PROVED` declaration additionally
requires a proof evidence role. No deviation is accepted by this implementation;
an apparent approval in prose is insufficient. Dynamic-runtime allocation and
indirection limitations must remain visible. They cannot be erased by a proved
SPARK component or an empty violation list without substantive review.

## Limits and remaining acceptance work

This is a minimum metadata checker, not the complete semantic criterion oracle.
The exhaustive, independently reviewed campaign roster is still OPEN. It must
enumerate each durable cut, bypass condition, recovery class, capture gap,
continuity failure, held-out evaluation criterion and P10 control. One arbitrary
negative case, a generic success artifact or a source inventory cannot establish
that coverage. The checker does not judge the adequacy of the referenced
oracles, ground truth, source scopes, adaptations or compensating controls.
Final acceptance must retain the detailed criteria and their actual outputs;
minimum scope/role joins alone cannot close an obligation.

Plan freezing compares canonical bytes with a separately referenced snapshot.
It does not authenticate when freezing occurred, its issuer, approvals or the
truth of a receipt. Synthetic test receipts exercise structural checks only.
They are not system, proof or compliance evidence. Original failed campaigns,
unresolved proof obligations and installed/harness limitations stay binding.

Inputs are regular files, at most 1 MiB each; JSON depth, nodes, collections,
strings and integer widths are capped. One audit permits at most 1,024 reads
and 16 MiB of referenced bytes. Exhaustion refuses without a partial success.
Reference paths are relative, at most sixteen components, and opened from one
pinned root descriptor with no-follow directory walks. This prevents a parent
symlink from redirecting a reference. It is not authenticated file custody or
an atomic source snapshot: hard links, hostile inode writes and mount changes
remain environmental assumptions. File identity/size/timestamps are checked
around reads. Filesystem operations still require external wall-time containment.

CPython and JSON allocate dynamically. Byte/traversal limits constrain this
tool's work; they do not prove allocation-free behavior, stack use or WCET.
The checker grants no SPARK authority and changes no installed runtime. Strict
warning tests and the source inventory are useful checks, not whole-program
Power of Ten compliance or avionics certification.
CI treats Python warnings as errors for the focused checker suite. Comprehensive
pinned Python static analysis remains OPEN; the bounded AST inventory alone
cannot close that requirement or prove a complete call graph.

The smallest sound next step is to freeze the detailed criterion and oracle
roster, including numeric workload/resource budgets, while completing the
protected-slot schema/freshness design. Then qualify the disposable protected
effect and outcome-query slice under its existing gates. No final acceptance
run may fit thresholds retrospectively to a result.
