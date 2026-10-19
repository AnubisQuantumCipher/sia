# Publication crash model

This bounded TLA+ model covers one transaction across the eleven phase values
in `SIA_Transactions.Phase` (initial retained source through committed ACK).
It separates a durable intent, a buffered effect, synchronized effect, durable
phase record, intent retirement and readiness. Crash is enabled between each
action and discards only the buffered state. Restart retains the durable
prefix and may repeat the next action. No fairness or eventual-success claim
is made; arbitrarily repeated crashes are allowed.

Check `TypeOK`, `DurablePrefix` and `ReadySafe` using `Publication.cfg`.
`Publication-negative.cfg` deliberately enables premature readiness and must
produce a `ReadySafe` counterexample. A passing negative configuration is a
failed test, not a successful model check.
`Publication-reachability.cfg` keeps the correct readiness rule but adds the
deliberately false `NotReadyYet` invariant. Its counterexample must reach final
readiness without violating any safety invariant, demonstrating that the
readiness implication is not satisfied merely because readiness is unreachable.

Assumptions: each durable action is atomic at this abstraction level; the
protected actor authenticates exact transaction/receipt identities and
serializes writers; successful synchronization preserves a durable prefix.
The model does not yet include torn writes, hostile receipt replacement,
multiple transactions/generation allocation, network disclosure, individual
journal cursors, actual filesystem rename/fsync behavior or restore migration.
The Ada reducer checks receipt/predecessor equality that is abstracted here.
Neither model subsumes the other; executable refinement and real fault
injection are still required before authority transfer.
In particular, readiness is volatile in this model. A persisted runtime ready
file must be rejected on restart until its generation and recovery state have
been revalidated; clearing an abstract Boolean does not prove that gate.

Run TLC with a bounded heap and one worker. Preserve tool hashes, command,
complete output and negative-control counterexample. Model checking this
finite configuration is not a proof of the full installed system.

The checked tool releases and hashes are in `toolchain.json`; tools are build
dependencies only. Official TLC usage is documented at
<https://github.com/tlaplus/tlaplus/blob/master/USE.md>.
Set `JAVA_BIN` and `TLA_JAR` to the verified tools and run
`spark/check-model.sh NEW_OUTPUT_DIR`. The runner checks the TLC SHA256, uses
private temporary directories, a bounded heap and per-lane deadline, retains
raw output, and requires the exact expected exit and diagnostic in each lane.
It refuses an existing output directory. Java provenance remains an operator
toolchain obligation; the runner records its version but does not certify it.
