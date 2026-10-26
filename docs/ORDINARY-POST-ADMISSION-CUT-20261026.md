# Actual post-admission observer cut — 2026-10-26

TESTED / ONE FIXED LINEAGE. The payload and its one child independently
announced post-exec entry before the observer was killed. All five tracked roles
were terminal and reaped before witness cleanup. Cleanup sent no signals and
reported no errors. A fresh-output invocation then refused at the existing
pending record, before process creation. Separate privileged readback matched
the pending bytes. The pending operation remains unresolved.

The instrumented driver changes only the wrapper's wait seam, after its original
durable active record and actual admission send. Sending the command is not an
execution acknowledgment: the sentinel separately transfers its own process
descriptor, forks one child, and the child transfers its own descriptor. The
witness checks peer credentials, parentage, command, interpreter, namespaces,
start identities and live handles. Both sentinel processes then wait indefinitely,
without timer or EOF exits and without useful external work.

The actual leader was `1982543`, its child `1982557`, and the observer `1982410`.
The launcher and namespace init were also tracked. Killing only the stopped
observer produced wait status `-9`; all five process descriptors reported
terminal/reaped mask `17` before cleanup. Preliminary observations are retained
separately from the final successful result. No observer final receipt exists.
The independent witness survived throughout; witness loss remains unqualified.

Execution manifest:
`e7d616e7b9e3e590d25b35cf3d3e985fcfcee5af3de3057f8f2eb83f532e986a`.
The actual invoker returned zero and its retained stdout matches the witness
result. Source, tool, host and predecessor-ledger checks were made before
execution; source and tool checks were repeated afterward. The inherited
478-file snapshot is bound to source `4ff2268179610297f67b1fd586e725c22ab66d12`;
this does not test every source in the later publication carrier.

The negative-control manifest is
`3eeae9a2708c0b594ade7bc9b9af8e0adb4af6860532d1d4226fdbe4fbad900f`.
It preserves the wrapper and isolation, relocates disposable paths, and invokes
the wrapper directly. Actual exit was one with `create-pending`,
`FileExistsError`, errno `17`. The entry record exists; downstream receipts,
payload logs and all six writable output directories remain absent or empty.
Authentication failure or any other nonzero exit would not qualify.

Pending SHA-256 remained
`736bd21e915003d5c2ae226ebcba48cfb2a416a0bf799aeb42fd5e86646c1c25`.
It still says `UNRESOLVED_DO_NOT_RETRY`. Tool-completion and separate terminal
readback notes are explicitly unsigned owner-recorded observations; they are
not platform-signed attestations. The readback JSON normalizes PTY CRLF to LF.

All 27 component controls passed, including the original eight pre-admission
controls and additional schema, identity, partial-acquisition, readiness and
cleanup-failure cases. They use mocked process facts plus a real local self-pidfd
transfer; they are distinct from the actual root execution. Selected strict
static checks report zero diagnostics and no routine over 60 lines. Python's
runtime and total memory consumption are not formally proved bounded.

Early GPT-6.1 review found an unchecked record type could escape retained error
handling. Closed schema validation and malformed-input controls repaired it
before the frozen passing test run. The early untested source was not separately
hash-frozen; that limitation remains explicit. Independent GPT-6.1 result review
confirmed the actual cut and refusal. It also noted the original auditors did
not mechanically compare complete invoker command vectors. The current vectors
matched by inspection; the package verifier now checks them explicitly without
rewriting the historical audits.

The [generated manifest](ORDINARY-POST-ADMISSION-CUT-EVIDENCE-20261026.json)
and [107-member archive](evidence/ordinary-post-cut-20261026-v1.tar.gz) retain
the exact source, raw controls/results, decisions, audits and reviews. Byte
reproduction passes. The baseline snapshot and fixed helper sources remain in
the prerequisite archive at `c61d43cb291274f4904295423dbda9aa00e5d849`; the exact
prior reconciliation is at `28fb59d441db57e1277e490058f55b724d628892`. Host
executables are hash-bound dependencies and are not bundled.

This result qualifies only the instrumented fixed sentinel/child cut. It does
not qualify arbitrary descendants, loss of the surviving witness, pre-entry
custody, durable workload completion, or safe replay. The next step is an exact
disposition for this interrupted fixture, preserving its intent and observations,
followed by the remaining custody/lifecycle controls. No free lock or completed
file grants successor authority.

Native C14, repeated-compaction continuity, R05 BOTH, Astra judge qualification,
full assurance, installed composition and every original release/marketplace
obligation remain open. No installed product, service, firewall, provider,
release or marketplace changed. This is not whole-system assurance or avionics
certification.
