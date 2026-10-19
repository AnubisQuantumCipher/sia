# Disposable indexer isolation experiment

This is an executable Linux feasibility test, not an installed SIA sandbox or
proof of host security. It never mounts the live corpus or signing state.

The driver creates disposable source/secret files and a host loopback listener.
A host client first reaches that listener. Bubblewrap then creates explicit
user, network, PID, IPC and UTS namespaces; drops capabilities; disables further
user namespaces; clears the environment; exposes only read-only `/usr`, a
read-only source export, the probe, and one Unix test endpoint. The child has
its own proc/dev mounts and inherits no extra descriptors. Failure to create
the requested isolation fails the test; there is no permissive fallback.

The child must read the export, fail its write with EROFS, fail to find the
unexported host fixture at its actual path, fail to reach the host listener,
and complete the fixed request/response over the exposed Unix endpoint. The
driver checks that the host export is unchanged and all five requested namespace
identities differ. The child reports zero effective, permitted and ambient
capabilities and `NoNewPrivs=1`. A user-namespace creation that succeeds on the
host must fail inside the child with ENOSPC. The probe calls the syscall via
`os.unshare` and checks the actual errno; an unrelated command failure cannot
satisfy this control. Both the permitted path and the refused path
have positive controls. These are observations of this experiment, not a proof
that every privilege-escalation mechanism has been excluded.

Run from a source checkout on the supported Linux machine:

```sh
timeout --kill-after=5s 30s python3 spark/isolation/check_indexer_boundary.py NEW_EVIDENCE_DIR
```

The new private output directory retains the command, child output/exit,
tool/source hashes and result. Temporary fixture data is removed by the driver;
it contains no live project data. Socket waits and the child process have finite
timeouts. Generic hostile executables are not supported by this test harness;
its captured output bound relies on this known fixed-output probe.
For reproducible acceptance, execute a fresh retained `git archive` of the
committed scripts and bind that archive, command, output and exit records in an
outer manifest. Post-run hashes from a mutable checkout alone are insufficient.

The Unix endpoint is a fixed test responder, not Ollama and not an arbitrary
network proxy. Production adoption still requires an embedding-specific broker
that validates operations, payload limits and allowed models without forwarding
arbitrary URLs or socket requests. No real model-provider transmission was
attempted or measured. The observed host-listener refusal and distinct network
namespace support this mechanism; they do not replace adversarial testing of
the actual engine, broker, inherited descriptors and supported distributions.

This experiment does not stop another process outside the sandbox under the
desktop UID from modifying that user's state. The authoritative service must
still own protected storage and keys under a separate identity. Resource limits,
syscall policy, broker authorization, service installation and recovery remain
unimplemented. Root/kernel compromise and malicious installed system binaries
are outside this experiment's guarantee.

## Real offline engine lane

`check_engine_boundary.py GBRAIN_BINARY NEW_EVIDENCE_DIR` runs the supplied
actual gbrain binary in the namespace configuration against disposable state.
It initializes PGLite without embeddings, adds the source, syncs without pulls,
embeddings or extraction, checks database identity, retrieves the committed
page body, checks source-scoped keyword results and resynchronizes. No live
SIA corpus or engine configuration is mounted.

The first dirty-working-tree negative control FAILED: gbrain indexed an
uncommitted file despite the read-only mount (`engine-boundary-v2`). The test
now clones the exact fixture commit without local/hardlink optimization,
checks out that commit detached, verifies clean status and mounts this export.
The origin deliberately retains an untracked file and a modified tracked page.
Both dirty tokens must be absent from the tested search results while the
original committed body remains retrievable before/after resync. File-content
inventories of the origin and export must remain unchanged; these inventories
do not establish metadata or complete filesystem-tree identity.

This finding corrects a former test comment about gbrain's walker. SIA's
existing publication path commits corpus changes and checks Git cleanliness;
the failed raw-engine export experiment does not demonstrate a released-runtime
bypass. A protected production exporter must independently validate source
identity, links, resource bounds, publication generation and crash behavior.
The fixture clone helper is not that production implementation.

Each engine invocation has configured per-file, descriptor, CPU and elapsed-time
limits. CPU/descriptor limits apply per process, not cumulatively to descendants.
Aggregate disk and memory bounds remain UNPROVEN; use a disposable, monitored
working area with capacity for this experiment. The source export and root
mount are read-only, while explicit state/temp mounts and proc/dev semantics
remain distinct. Do not claim an exclusive writable-path or syscall allowlist.

Acceptance must run a committed archived driver and retain all command/output/
exit records plus source, tool, engine, receipt/pin and fixture bindings. The
script accepts an explicit engine path; the installed receipt/pin relationship
must be verified separately. This is TESTED offline engine behavior under the
recorded configuration, not embedding, provider containment or installed SIA
authority. The earlier namespace probe's observations remain separate evidence.
