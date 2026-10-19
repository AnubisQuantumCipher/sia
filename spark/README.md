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
`gprbuild -p -P spark/sia_assurance.gpr` and `spark/bin/policy_tests`.
Proof: `gnatprove -P spark/sia_assurance.gpr -U --mode=all --assumptions`.
Inspect coverage, raw proof summaries, warnings, assumptions and exclusions;
exit status alone does not establish the intended acceptance requirements.

Keep runtime assertions enabled. The abstract input domain and proof result
do not validate hostile IPC representations, external processes, physical
durability, cryptography or Linux isolation. See `docs/ASSURANCE-GOAL.md`.
