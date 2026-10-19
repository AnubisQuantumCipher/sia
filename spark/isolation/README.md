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
