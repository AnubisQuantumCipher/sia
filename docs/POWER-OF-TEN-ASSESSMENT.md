# Power of Ten baseline and SIA adaptations

Status: initial source assessment, not compliance acceptance. This extends
`ASSURANCE-GOAL.md` and `ASSURANCE-IMPLEMENTATION-GATES.md`.

Normative source: Gerard J. Holzmann, [The Power of Ten – Rules for Developing
Safety Critical Code](https://spinroot.com/gerard/pdf/P10.pdf), read in full,
including every rationale, on 2026-10-20. The downloaded original PDF and full
text extraction are retained in the external assurance evidence directory.
The original remains authoritative; the summaries and adaptations below are
SIA engineering decisions, not quotations or replacement wording by Holzmann.
The operator's local copy was found under
`Work/omp-gpt6-commissioning-20261017/private-standards-20261018-v1/`.
Its PDF and complete text extraction match the downloaded original byte-for-byte.
PDF SHA-256: `2217f41df961b9ed25cc072700b6332d6193799ed09d83be48bf791d05025f54`.

Assessment source baseline: `075ecae2f97a95304f603eff23d10cbc30c0f82f`.
The pure-core proof evidence remains bound to `376a541`; the strengthened
report gate to `6450636`. No runtime-wide compliance score is meaningful.

Later diagnostic finding at the continuity checkpoint `2794db2`: clean
flow-summary rows did not include every raw proof diagnostic. Optional
array-initialization and operator-reassociation warnings were disabled by the
then-selected profile. Its all-channel zero-warning acceptance is FAILED.
The [warning-gate repair](PROOF-WARNING-GATE.md) enables all tagged warnings,
preserves the original test mutations/contracts, and checks every unit's raw
diagnostic channels. The stricter fresh development campaign passed build,
every harness, all 788 reported proof checks and the raw/summary validator.
Fresh committed reproduction also passed at `1f71a97`, with independent
evidence review. Historical scoped proof results, timeouts and the discovered
warning evidence are retained. This scoped gate result is not runtime-wide
Power of Ten compliance.

## Rule mapping

The “intent” column is a concise paraphrase of each rationale. Every other
column describes our application and observations, not the original C rules.
OPEN means evidence is missing; FAILED means an identified mismatch. Neither
is an approved deviation.

| Rule / intent | SPARK authority-core adaptation and current evidence | Python / Linux adaptation and current mismatch | Required repair, automated check and acceptance |
| --- | --- | --- | --- |
| 1 — Simple control flow makes verification tractable. | `restrictions.adc` prohibits recursion; pure packages expose explicit decisions. All-unit proof covers the current core, not the future actuator. | FAILED for a closed static call graph: `siathought` rebinds globals; owner dictionaries dispatch calls in `siasourceeffects`. Exceptions introduce nonlocal paths. | Replace authority-path dynamic delegation with explicit interfaces; inventory call graph and strongly connected components, including cross-module calls. Treat unresolved calls as UNKNOWN, not acyclic. Review exception paths and cancellation state. Compiler restrictions plus complete call-graph evidence are required. |
| 2 — Bounded iteration prevents runaway execution. | Fixed wire/digest domains and termination contracts have scoped proof. This is not a wall-clock bound. | OPEN for complete recovery cycles, lease waits and subprocess trees. `sia-brainstem` is intentionally a service with an explicit stop path. Live consolidation spans pulses and withholds reads. | Prove per-operation and whole-cycle progress measures, with environment assumptions and bounded retries. Specify service progress, shutdown and failure states separately. Test deadline expiry, lock contention and starvation. A timeout is containment, not proof of completion or WCET. |
| 3 — Predictable storage avoids allocator hazards and exhaustion. | Explicit allocators/deallocation are prohibited. Initial configuration lacks a prohibition on implicit heap allocation; total stack/runtime memory remains OPEN. | FAILED literal compliance: CPython, JSON, Git, gbrain and their libraries allocate during operation. Cgroups constrain damage but do not establish allocation-free behavior or successful completion. | Add compiler enforcement for implicit allocation; retain bounded arrays and explicit maximum request sizes. Analyze stack, secondary stack, linked runtime and subprocess/storage budgets. Keep allocating components outside protected authority; test OOM, disk/inode/descriptor exhaustion. Do not call containment equivalent to the original rule. |
| 4 — Small logical units enable local review. | Small core routines are reviewable, but an automatic semantic routine-size gate remains OPEN. Contracts need separate review rather than compressed formatting. | FAILED: AST physical spans at the baseline include `consolidate_corpus` 375 lines and `_pulse_transaction_guarded` 977. These counts are diagnostic, not the paper's normalized statement metric. | Split by explicit state transition with preserved error ordering and receipts; retain original fixtures. Add bounded AST inventory and Ada parser-based routine metrics; flag overlong functions, including tests. Acceptance needs behavior-equivalence and failure-path evidence, not merely smaller wrappers. |
| 5 — Meaningful assertions expose anomalous states. | Pre/Post, Global/Depends and preservation contracts are proved within premises; meaningfulness and requirements completeness still require review. Keep runtime checks enabled. | OPEN: Python `assert` can disappear under optimization and cannot serve as an input/authority check. Exceptions must preserve recoverable state. | Inventory checks per routine, including side effects, response and requirement. Use explicit validation/refusal at hostile boundaries. Negative controls must show false premises are rejected. Do not pad counts. A proved nontrivial SPARK contract is not discarded merely because proof establishes it: distinguish proof from a vacuous tautology and record this adaptation. |
| 6 — Narrow scope limits corruption and eases diagnosis. | Pure core and `Global => null` provide scoped information-flow evidence. | FAILED narrow-scope intent in global owner rebinding and shared mutable module configuration. Same-user permissions do not isolate hostile peers. | Use immutable typed context and minimum-capability handles; segregate protected storage/signing identity. Check global writes and imported ambient authority. Require actual UID/permission/bypass evidence; naming a variable private is insufficient. |
| 7 — Validate parameters and deliberately handle results. | Types, request parsing, result enums and refusal preservation are proved/tested locally. Caller-supplied authenticity predicates are not authentic evidence. | OPEN for every subprocess, partial write, close/fsync, parser and cancellation result. Existing negative tests cover subsets only. | Inventory effect calls and error propagation; make intentionally ignored results explicit and justified. Test partial writes, nonzero exits, malformed/oversized inputs and ambiguous completion. Verify result/error handling through the resident front door. |
| 8 — Avoid hidden semantics and configuration explosion. | No C preprocessor is needed for current core; generics/build switches still require configuration identity. | FAILED analogous transparency: dynamic module installation/rebinding hides effective implementations; runtime configuration and retained state choose different paths. | Freeze supported configurations and hash effective code/configuration. Check exec/eval, dynamic imports, generated code and rebinding as review findings, not automatically equivalent C violations. Require selected-path tests for each supported configuration. |
| 9 — Restricted indirection keeps data and calls analyzable. | No dispatch/access-to-subprogram is compiler-enforced; unrestricted access types, aliasing and FFI still require explicit exclusion/review as the core expands. | FAILED literal compliance: Python references, callbacks, owner maps and native-library pointers remain. | Keep consequential decisions in the bounded core; explicit tagged operations at the adapter boundary. Check access declarations/conversions and unresolved indirect calls; independently test aliasing/reentrancy and native boundaries. CPython cannot earn literal pointer-rule compliance by adding type hints. |
| 10 — Strict diagnostics and regular analysis expose defects early. | `sia_assurance.gpr` enables strict warnings, assertions and validity checks; the runner preserves full-unit proof and the gate rejects unproved/justified checks and non-clean detail rows. | OPEN for comprehensive daily Python/shell/native analysis and zero-warning closure. Passing unit tests or compilation is not that evidence. | Pin analyzers and complete scope; run strict checks in CI and daily with retained outputs. No silent suppression. Track findings until repaired or explicitly approved as deviations; evaluate analyzer failure/unknown output as a failed gate. |

## Interpretation constraints

The original permits early error returns; this baseline does not invent a
single-return requirement. Its service-loop exception is not permission to
leave ordinary loops unbounded. SIA's stoppable service cannot literally claim
proved nontermination: model the running, shutdown and fault states instead.
The original discusses disabling assertions; SIA retains checks at untrusted
boundaries under the operator's stronger policy.

The rule-5 inventory must report assertion/contract density, side effects,
failure response and linked requirement separately. Two superficial checks
do not establish meaningful density, and proof does not waive that inventory.
Record any proposed replacement of the literal density criterion as a
deviation needing approval; the current core has no blanket density acceptance.
Rule-1/9 inventories must explicitly include Ada `goto`, access declarations,
unchecked conversions, address operations, imported functions and FFI
transitive calls. The currently listed restrictions alone do not exclude all
of these.

GNATprove discharging a meaningful contract is not the same as inserting a
constant-true assertion to satisfy a density metric. Contract strength,
feasible preconditions, external assumptions and negative controls are separate
obligations. A semantic check must not be removed to make a literal count or
syntactic scan look green.

No deviation is approved by this document. Each proposed exception needs its
affected rule and source, necessity, hazard/risk analysis, compensating
controls, owner, expiration/review trigger and explicit operator approval
before becoming accepted policy. Existing violations remain visible during
repair; they do not become grandfathered compliance.

## Implementation order and required evidence

1. Preserve the original PDF and source/tool identities. Keep the literal C
   baseline distinct from the adaptation matrix.
2. Close implicit-allocation enforcement in the pure core. Rebuild, execute
   every harness and repeat all-unit proof from a clean committed archive.
   Stack/runtime budgets remain OPEN even if that restriction passes.
3. Add transparent inventory checks before broad refactoring: routine sizes,
   globals, dynamic dispatch, loops, effect calls and analyzer coverage.
   Such inventory is an aid to review, not a sound Python proof engine.
4. Diagnose and complete the installed recovery/availability investigation
   using the existing readiness invariant; repair demonstrated defects.
   Preserve the live refusal and demonstrate backlog completion; do not clear
   debt just to admit reads.
5. Refactor authority/effect transitions behind frozen interfaces and exact
   regression controls. Complete authenticated producers, protected actuator,
   currentness, recovery and disclosure enforcement from G3/G4.
6. Build bidirectional requirement/hazard/contract/test/source evidence and
   independent target reproduction. Close every applicable rule for the
   declared scope before claiming that scope complies.

Each acceptance record must name exact source, configuration, toolchain,
commands/exits, positive and negative controls, raw outputs, reviewer and
remaining assumptions. No inference of whole-system safety or certification
follows from this coding baseline.

## First repair verification

At source `4c72a49b95e325ae9e6a9ea1ebeb91152f4eb249`, the project adds
`No_Implicit_Heap_Allocations` (the installed compiler's exact restriction
identifier). Fresh archived-source build, six harnesses, all-unit GNATprove
and the strict report gate passed. The summary reports 386 discharged checks
across twelve units, no justified/unproved checks, and clean detail rows.
Raw evidence: `power-of-ten-reproduction-v1` in the external assurance
directory. Independent GPT-6.1 review in `power-of-ten-evidence-review-v1.txt`
verified the source/configuration archive, tool hashes, harness exits and
reported proof scope without repeating the heavy run.
This closes the missing compiler restriction for that source
configuration only; total stack, runtime allocation, resource admission,
target timing and the rest of rule 3 remain OPEN.

## Repeatable Python inventory

Run from the repository root:

```sh
python3 scripts/assurance_source_inventory.py \
  bin/*.py bin/sia bin/sia-brainstem bin/sia-ledger bin/sia-mcp bin/sia-intent-review
python3 -m unittest tests.test_assurance_source_inventory -v
```

The tool reads bounded regular source files, hashes their exact bytes, parses
without importing inspected code, and emits `inventory-only`. Its successful
exit means inventory execution completed, never compliance. It rejects
unsupported/oversized inputs rather than returning a partial report.
Final-component symlinks and nonregular files refuse; parent-directory symlinks
and hard links are not excluded. Paths remain operator-selected and are not
an authenticated containment interface.
CPython parser allocations are not statically bounded by this tool; run the
inventory under an external process budget when inspecting untrusted source.
The node cap is checked after parsing and is not a parser-memory guarantee.

The initial runtime pass (`power-of-ten-runtime-inventory-v2.json`, external
evidence directory) covers 95 files and reports 317 physical-span findings,
121 while-loop review sites, 692 direct dynamic-call sites and 31 expanded-scope
sites. These overlap and are not counts of independently established defects.
Aliases, callbacks, implicit dispatch, native code, call-graph cycles and
semantic loop bounds require further analysis. Retain all findings; do not
create an exception baseline that silently grants compliance.

## Consolidation routine repair

The consolidation executor is split into explicit source-validation,
preparation, publication and cleanup routines. Its original entry point keeps
scan acknowledgment; the reusable effects routine cannot acknowledge claims.
`tests.test_consolidation_executor.ConsolidationRoutineBudget` enforces the
sixty-physical-line ceiling for the fourteen named routines. The full affected
regression selection passes 90 tests, including unchanged original epoch,
backlog, crash-recovery, ownership and export cases. Exact-source reproduction
is recorded with the [snapshot work](../spark/CONSOLIDATION-SNAPSHOT.md).

This addresses local reviewability under rule 4 and exposes effect boundaries
for subsequent work. It does not close the dynamic facade/call-graph problem
under rules 1 and 9, prove termination or fixed allocation, or qualify the
snapshot consumer. Existing violations remain open without an approved waiver.

## Source-outcome checking

Source `4082ac8190ab68e1f818f60494192b0023fdef5a` adds a read-only observer
that reconstructs expected marker-index entries from exact retained source
digests instead of trusting a successful executor return or an incomplete
epoch roster. Its 116-test archive reproduction includes wrong-index,
missing-index, history-loss, search-exhaustion and fresh-process recovery
controls. This contributes evidence for explicit checked results and failure
handling under rules 5 and 7. Search counts and individual command output are
bounded, but aggregate latency, allocation and lease waiting remain unproved
under rules 2 and 3. No acknowledgment or authority transfer follows.

The five changed Python implementation/test files have no findings in the
limited source inventory, retained with development-v2. That observation is
not a compliance result: the inventory does not resolve indirect calls or
prove semantic loop bounds. Source and complete scope are recorded in
`spark/CONSOLIDATION-SNAPSHOT.md`; failures and larger unresolved rules remain
visible in this assessment.

## Pre-effect original retention

Source `5667541ed7e76964e75dd3e524d79e4dbda2451b` strengthens checked input/result and recovery
ordering: the experimental consumer pins and verifies every selected original
before execution intent, then refuses lost or mismatched retained state.
Its 127-test archived-source reproduction covers real process cuts, source
versions newer than admission, Git GC and failed writes/pin creation.
The bounded record can leave a planned pin on final-record size refusal;
sources remain live, and this partial retention is explicit. The protocol
still relies on cooperative ownership, dynamic Python/Git allocation and
unproved aggregate resource bounds. It is evidence toward rules 5 and 7,
not closure of rules 1, 2, 3, 6 or 9, nor whole-system assurance.
