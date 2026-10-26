# Candidate event-pack migration crash protocol

This is a finite design model for EP06/EP07, not an implemented migration,
SPARK proof, Linux durability test, or permission to retire source files.
The captured planner still returns a proposal. Normal runtime remains legacy-only.

The gap addressed is per-record retirement: the original publication model has
phase ordering but no relation between a packed replacement and its originals.
This model separates intent visibility/durability, partial/exact temporary
writes, file synchronization, rename, target-parent synchronization, readback,
each unlink, legacy-parent synchronization, final reconciliation, and subsequent
publication. A rename or successful write does not imply durable coverage.

## Finite domain and assumptions

The fixed configuration contains two represented legacy identities (`a`, `b`),
one fallback (`f`), and one record already in the prior pack (`p`). An identity
denotes exact bytes and lineage admitted by the existing captured-plan contract.
It does **not** stand for any record with the same user-supplied ID. Coverage
sets abstract verified byte equality; they do not implement hashes, provenance,
epoch validation or source authentication. No arbitrary-size induction is claimed.

One authenticated plan, operation identity, current protected permission and
serialized writer are environmental premises. Authentication, revocation,
concurrent writers, stale generations and malicious replacement are not modeled.
The model must not be used to turn an observation Boolean into effect authority.
The separate admission/recovery model and protected-service obligations remain.

Successful synchronization is assumed to establish the modeled durable state.
File synchronization and directory synchronization are separate. An unsynced
rename may disappear or persist on crash; unsynced file contents may be invalid.
Unsynced unlinks may individually persist or revert. Synchronized state survives.
Temporary files are discarded on crash; this omits actual orphan cleanup/resource
growth. Partial writes are represented but not ENOSPC/error-code behavior. A failed
operation with no effect is abstract stuttering; ambiguous effects require real
adapter reconciliation. Neither this abstraction nor its runner proves filesystem
atomicity, actual fsync behavior, bounded completion, off-host restore or liveness.

Final storage reconciliation is a separate durable completion marker. The eleven
original publication phase values are retained as an abstract durable counter;
their corpus/projection/ledger/ACK evidence is an assumption here, not re-proved
by this model. Readiness requires the last phase and current reconciliation.
Restart clears readback and readiness; it never converts rename visibility into
retirement authority. The intent remains retained throughout this one operation.

## Checks and controls

- `TypeOK`: every state stays in the explicit finite domain.
- `Retained`: all original records remain available through visible originals
  or durable exact pack coverage, including records in the prior pack.
- `RetirementSafe`: fallback stays present and every unlinked legacy record
  already has durable exact coverage.
- `IntentSafe`: no retirement occurred without durable operation intent.
- `CompleteSafe`: completion requires the complete durable legacy roster,
  durable new pack and durable intent.
- `ReadySafe`: readiness requires current readback, storage completion and
  the original final publication phase.

Seven single-fault configurations deliberately bypass intent sync, file sync,
parent sync, represented-only retirement, prior-record preservation, complete
roster reconciliation, or final publication. Each must fail its named invariant.
These are test mutations, not selectable runtime policies.

Four false invariants require counterexamples reaching completion, final readiness,
completion after repeated crashes during partial retirement, and completion after a rename
survives without prior directory synchronization. The recovery monitors are
captured at completion; a later crash cannot manufacture that witness. The crash
counter saturates and never limits permitted crashes. Counted partial-retirement
crashes require current readback, so another counted crash requires restart and
re-verification. They may occur at the same partial roster; this does not witness
two distinct rounds of retirement progress. No fairness is assumed.

Run `JAVA_BIN=... TLA_JAR=... bash spark/check-event-pack-model.sh NEW_OUTPUT_DIR`.
The existing pinned TLC toolchain, one worker, 256 MiB heap and 120-second per-lane
deadline apply. The runner preserves commands, raw logs and expected-failure
traces, refuses existing output directories, and checks source/tool hashes again
afterward. Java distribution provenance remains an operator obligation. Model
checking is finite exploration, not a mathematical proof over all pack sizes.

## Integration obligations remain open

The next implementation must bind this transition table to the authenticated
bounded plan and a SPARK decision, then enforce it in the protected Linux
actuator. It must reconcile uncertain effects before retries and test every
durable cut with actual files. Protected native qualification is still failed;
this model neither bypasses nor closes that prerequisite. Resource accounting,
correction/deletion/retention, version downgrade, complete corpus inventory,
consumer deployment, capsule recovery and installed qualification remain open.
The original publication, admission and all assurance gates remain binding.
