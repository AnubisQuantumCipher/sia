# SIA assurance policy prototype

This branch contains a policy prototype. It is not installed, not an authority
in the released runtime, and not evidence that SIA is formally verified.

`SIA_Policy` specifies provenance admission and joined publication/ACK
predicates. It is intentionally pure and bounded. Digest equality binds the
transaction identity but does not compute or authenticate the digest.
External witnesses remain untrusted until an enforcing actuator obtains and
validates them. A Boolean supplied by Python cannot establish durability.

`Observed_Empty` permits publication of an observed empty source but cannot
admit a nonexistent record as source evidence. An empty batch still needs
valid witnesses for the resulting published generation, possibly reusing
unchanged corpus/index content. The adapter must bind that reuse explicitly;
it must never fabricate a new corpus commit or sync operation.

`Publication_Joined` here is a publication predicate, not the released CLI's complete
readiness gate. `Acknowledge` additionally requires durable archive and cursor
witnesses. Runtime readiness must not open before the acknowledgment protocol
is finished. State-transition and crash-recovery proofs are still required.

Build/test: source the installed GNAT environment, then run
`gprbuild -p -P spark/sia_assurance.gpr`, `spark/bin/policy_tests`, and
`spark/bin/transaction_tests`.
Proof: `gnatprove -P spark/sia_assurance.gpr -U --mode=all --assumptions --no-inlining --memlimit=512 --timeout=10`.
Inspect coverage, raw proof summaries, warnings, assumptions and exclusions;
exit status alone does not establish the intended acceptance requirements.

For a clean committed checkout, source the GNAT environment and run
`spark/verify-policy.sh NEW_OUTPUT_DIR`. On this shared machine invoke it under
the existing nonblocking heavy-work lock. It archives the exact committed
`spark` tree into a new retained directory, builds there without old objects,
runs every declared policy harness and the strict proof command with finite deadlines, and
retains commands, exit statuses, output, source identity and tool executable
hashes. It refuses an existing output directory or uncommitted tree.
The caller must supply enough storage and the qualified toolchain. Executable
hashes do not identify all prover libraries or establish toolchain qualification.
No download, installation, network access or automatic acceptance decision is
performed by the runner. Inspect the retained obligations and assumptions;
this is a reproducibility aid, not the completed offline system verifier.

See `ASSUMPTIONS.md` for the explicit boundary and enforcement ledger, and
`REQUEST-ADMISSION.md` for the experimental exact-grant comparison policy.

Keep runtime assertions enabled. The abstract input domain and proof result
do not validate hostile IPC representations, external processes, physical
durability, cryptography or Linux isolation. See `docs/ASSURANCE-GOAL.md`.

`SIA_Continuity` adds a conditional reference-restoration classifier for bounded
checkpoints. See [`CONTINUITY-POLICY.md`](CONTINUITY-POLICY.md) for its contract,
producer assumptions and current verification status. Its result cannot grant
an action, establish an approval or authorize retrying an uncertain operation.

The fixed checkpoint record decoder and its independent vectors are described
in [`CONTINUITY-CHECKPOINT-CODEC.md`](../docs/CONTINUITY-CHECKPOINT-CODEC.md).
Its focused core proof and runtime passes are separate from the incomplete
combined-harness/full-project proof. No installed adapter calls it yet.

`SIA_Transactions` adds a pure reducer for one transaction's durable prefix.
It admits only the immediate successor, treats an exact most-recent receipt
retry as already applied, and preserves state on refusal or retry. It cannot
roll back or wrap from ACK to capture. `transaction_tests` checks all phase
triples, a complete path, retries and conflicting receipt/transaction inputs.

The reducer records an already-observed durable effect; it does not authorize
an unperformed write or make its own state durable. Its caller must authenticate
the starting state, the operation-specific receipt and the effect witness,
and durably commit the reduced state with a recoverable journal. Individual
filesystem operations, journal cursor substeps, acquisition fences and the
next transaction's generation allocation still require refinement. Recovery
from a real process crash has not been demonstrated by these pure tests.

The runner also checks reported coverage against every spec/body unit in the
supported source directories. Missing units, incomplete coverage, malformed
totals, justified checks and unproved checks refuse success. Each unit must have
the reported number of unique, source-bound detail rows in the supported
GNATprove format, with zero flow errors, outstanding flow checks, warnings and
`pragma Assume` statements, and a proved result. Unknown detail formats refuse
acceptance rather than silently dropping diagnostics. This checks report
structure, not authenticity or system assurance. The strengthened gate also
checks each required unit's raw diagnostic channels and explicit exclusion
lists, with bounded input and duplicate-key rejection. The project requests
all tagged warnings with `-W=all`; warning errors alone do not enable disabled
categories. See [`PROOF-WARNING-GATE.md`](../docs/PROOF-WARNING-GATE.md) for the
discovered gap, retained negative evidence and qualification status.
Its synthetic negative tests
run with `python3 -m unittest discover -s spark/tests -p test_proof_summary.py -v`.
