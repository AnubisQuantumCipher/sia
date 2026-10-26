# Ordinary execution receipt persistence — 2026-10-26

TESTED / NOT CUSTODY ACCEPTANCE. The private engineering proof wrapper now
synchronizes a receipt file and its containing directory before acknowledging
publication. The previous writer synchronized only the file. The change is
retained here as evidence; it does not change SIA's installed runtime or admit
the native Codex continuity adapter.

## What changed

The writer accepts only its three original receipt names, creates each file
exclusively through an opened directory descriptor, and refuses symlinks and
overwrites. It compares the directory identity before and after the write.
Incremental JSON encoding avoids introducing a second complete materialization
of the receipt. Short writes, encoding errors, synchronization errors and close
errors produce `UNCERTAIN_DO_NOT_RETRY`; partial files remain for reconciliation.
Close errors do not replace an earlier failure.

The existing private directory and nonhostile ordinary-execution premises remain.
Directory comparisons do not authenticate the full pathname ancestry or resist a
hostile process with equivalent authority. Python allocation, the filesystem,
kernel and hardware are not formally verified by these controls.

An initial unexecuted candidate materialized the full encoded receipt. It was
superseded before execution. The first executed component candidate used mode
`0600`; the final candidate restores the original `0644` mode inside the observed
`0700` run directory so UID1000 can read root-owned receipts. The earlier candidate,
tests and results remain in the archive; they are not evidence for the final bytes.

A complete result file can exist even when final synchronization or close fails.
Acceptance therefore also requires the wrapper's observed successful exit and
agreement between its stdout, retained receipt and source pins. The integration
invoker records the actual child exit and stdout hash. It does not become a
surviving custodian. A separate tool-exit observation is explicitly model-recorded,
not a signed platform receipt.

## Executed evidence

| Observation | Exact retained result | Scope |
| --- | --- | --- |
| Component run | 18 methods PASS, 0.054 seconds | Incremental candidate imported as a module; wrapper main not dispatched |
| Normal wrapper integration | 18 methods PASS, 0.041 seconds | Final candidate used as the actual root wrapper and tested module |
| Acknowledgment chain | Outer tool exit 0; parent-recorded wrapper exit 0; stdout equals final receipt | One normal invocation |
| Source and cleanup | All 478 source hashes and byte counts match; tracked cleanup complete | Recorded canonical/tool/helper pins and tracked processes |
| Static checks | Selected strict 167-rule analysis has no diagnostics; no changed routine over 60 lines | Declared Python analysis selection, not proof |

Each executed roster contains 14 receipt methods and the four unchanged cleanup
error-path methods. Controls cover the original missing directory sync, exclusive
creation, symlink refusal, fixed names, encoding failures, short writes, file and
directory sync failures, retained primary and close failures, and parent rebound.
The final integration freshly verifies the mode repair and actual acknowledgment
path. Actual GPT-6.1 independently read the raw results and source bindings.

The [generated manifest](ORDINARY-RECEIPT-PERSISTENCE-EVIDENCE-20261026.json)
contains exact candidate, test, tool and evidence hashes. The
[archive](evidence/ordinary-receipt-repair-20261026-v1.tar.gz) retains raw outputs,
invocation configurations, reviewed sources, superseded versions, audits,
independent review records, and packaging/reproduction code. All source snapshot
rows are bound by hash and size; the complete snapshots are not reproduced in
this archive. Local paths are intentionally retained. The package reproduces
byte for byte with the retained generator's `--check` on the evidence host.

## Remaining acceptance boundary

Observer-loss and successor recovery remain UNKNOWN. These runs establish neither
hardware crash durability nor recovery after losing every local process handle.
They do not establish containment of external effects, native harness custody,
automatic compaction restoration or absence of duplicate actions.

The smallest next step is the existing actual-wrapper recovery boundary: retain
operation identity, establish prior namespace termination independently after
observer loss, and refuse successor admission when that cannot be established.
Fault cuts must observe termination before any witness cleanup could mask a
failure. Repeating the earlier proxy-creator-death test alone is insufficient.

No installation, service, firewall, provider, release or marketplace state changed.
R05 BOTH, C14, all original A/G/C/P/R/EP obligations, Astra judge qualification,
installed final composition and publication acceptance remain open. Earlier
source-bound SPARK proof receipts retain only their unchanged component scope;
they are not proof of this Python wrapper or the full SIA system.
