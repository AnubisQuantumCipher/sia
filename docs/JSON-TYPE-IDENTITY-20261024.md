# Exact JSON container admission

Status: **TESTED scoped repair; static findings and broader assurance OPEN**.
This checkpoint changes exact-container checks in source-batch, live-loop,
event-plan, gist, cognitive selection, baseline, history and source-link
sizing/admission. It does not change the R05 reuse requirement or its pending
approval status, deadlines, capacities, fixtures or existing assertions.

## Defect and repair

Tuple membership compares classes using equality. A custom metaclass can
therefore make an exotic object or a container subclass appear to match dict
or list. The pre-repair checks admitted such objects or invoked user-defined
equality, length and iteration during admission. These functions promise
ordinary native JSON values. This is an in-process input-contract defect;
no remote code execution or hostile-interpreter isolation is established.

The repair compares the class with dict/list by identity. Event-plan evaluates
type(value) once after its existing limit/depth gate. Native scalar handling,
container traversal, callbacks, budgets and cycle checks remain unchanged.
Exotic values now reach the existing typed refusal before their hooks execute.
The ordinary Python builtins and runtime remain environmental assumptions.

This is a Python adaptation of Power-of-Ten checked-input and restricted-
indirection intent, not a quotation or a proof of runtime compliance.

## Evidence

The original eight implementations and initial adversarial test are retained.
The baseline runs four methods and reports 144 failing subtests: deceptive
metaclass equality and raising equality across root/nested objects and list/
dict subclasses. Positive native-value and cycle controls also run. The final
test explicitly marks its spoofing metaclass unhashable, correcting an initial
PLW1641 diagnostic. Initial and final test identities remain distinct.

The initial affected-module roster passes 234 tests in 20.423 seconds, but its
git-tracked input inventory omitted the newly untracked regression file.
That receipt is retained with the gap. The final bound-roster receipt explicitly
includes that file at both endpoints and passes 234 tests in 15.317 seconds.
These separate timings are observations, not a controlled performance comparison. Selected static analysis reports the same two findings before and
after the product repair: B905 in cognitive history and E731 in cognitive
selection. No new static finding remains; zero-warning acceptance is NOT met.
No suppression, warning waiver or interpreter-global alteration was introduced.

Source review by actual GPT-6.1 found no material blocker in the narrow repair;
it is not independent execution. All process, address-space, output-size and
job-lock limits remain unchanged. Endpoint hashes are not continuous loaded-
code custody. Commands, original files, source maps, failure logs and final
outputs are retained in [the manifest](JSON-TYPE-IDENTITY-20261024.json).

## Open scope

Other equality-based type checks remain, including native publication memo
admission and several scalar/ownership gates. They require their own source
inspection and tests; this patch does not claim repository-wide closure.
Several touched algorithms still use bounded recursion and dynamic Python
allocation; no fixed-memory or whole-system proof is claimed. The retained
R05 delivery/resident timeouts are not repaired or waived by these results.
Full SPARK, Linux enforcement, actual harness continuity, installed lifecycle,
independent acceptance and release/marketplace qualification remain open.
