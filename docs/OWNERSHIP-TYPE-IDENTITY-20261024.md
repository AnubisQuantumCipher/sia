# Exact type identity at ownership and publication boundaries

Status: **FAILED full writer qualification; candidate NOT ADOPTED**.
This follows the [JSON sizing repair](JSON-TYPE-IDENTITY-20261024.md) without
changing the pending R05 requirement decision, original tests, limits or gates.

## Problem and preserved contract

Equality-based type membership let a custom metaclass masquerade as a native
scalar or container. Plain-pin builders could retain an exotic object as a
scalar; registry validation could accept it; owner claim validation and native
memo admission could invoke foreign iteration/equality hooks. These are
in-process contract failures, not a demonstrated remote exploitation path.

The preserved six-module private candidate uses identity at those checks: delivery writer, installed engine,
cognitive registry, render container inventory, delivery wrapper owner basis,
and native publication memo. Legitimate writer tuples/floats, list-or-tuple
claims, registry scalars, native memo integers and finite floats remain allowed.
The actual sialib publication facade is exercised, including refusal before
serialization and byte equality for ordinary native memo input. No protected
publication, real engine execution or installed lifecycle is claimed here.

Pin construction and container inventory still require prior bounded/plain
admission; they are not newly general-purpose hostile graph validators. Pin
comparison still expects internally generated pins. Existing recursive code,
dynamic Python allocation and mutation-between-reads assumptions remain.
Identity checking does not establish interpreter isolation or whole-system proof.

## Retained verification

The unchanged original source and adversarial baseline are retained: seven
methods report 45 failures and three errors. Candidate focused controls pass seven methods in 0.345s. Publication/registry/
render controls pass 66 methods in 4.937s, and installed-engine boundaries pass
19 methods in 0.368s. The predeclared full writer roster exits 124 at 60s,
while test_real_output_then_next_capture_binding_and_pulse_keep_exact_nonempty_record
is active. There is no completion footer; the remainder is not passing or waived.
No failed roster was split to manufacture acceptance. The new regression file is explicitly included in each
candidate endpoint source inventory.

The candidate remains uncommitted in the isolated publication worktree; its
complete files and patch are retained as evidence. Only documentation/evidence
may be published in this checkpoint. Canonical runtime source is unchanged.

Selected strict static analysis reports 180 findings before and after, with
identical filename/code/message multiplicities: BLE001, B904, B905 and F821.
The existing publication module obtains names through runtime binding; that
explains some diagnostics but does not discharge or waive them. No new finding
is introduced by this patch; **zero-warning acceptance remains unfulfilled**.

Actual GPT-6.1 source review found no material blocker in this narrow change.
It is not independent execution or approval to retire any requirement. Exact
commands, hashes, originals and positive/negative outputs are retained in
[the evidence manifest](OWNERSHIP-TYPE-IDENTITY-20261024.json).

## Remaining acceptance

The remaining numeric/scalar equality gates need independent inspection and
controls, preserving each allowed type and callback/refusal order. Complete
writer qualification, existing R05 timeouts/reuse obligation, static closure,
SPARK proof, Linux authority enforcement, actual harness continuity, installed
qualification, release and marketplace gates remain separate obligations.
No merge, install, release, policy approval or certification follows here.
