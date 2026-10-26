# Experimental one-request continuity I/O

This increment addresses A22/C07/C11. It joins the existing fixed request and
response codecs through a real disposable process. It does not capture history,
authenticate evidence, restore a real agent session or authorize an action.
No installed SIA path, live corpus or protected authority was changed.

`spark/transport/ada/continuity_probe.adb` reads exactly one 32768-byte frame
and checks EOF with a sentinel. It uses the existing SPARK frame evaluator and
response encoder, emits at most 64 bytes and exits with the defined policy,
malformed or I/O status. Read and write loops have explicit attempt bounds,
advance on successful counts and refuse errors; blocking requires the parent.
The descriptor calls and GNAT runtime are outside the pure proof boundary.

`spark/transport/continuity_process.py` pins the opened executable against a
supplied build digest, sets resource limits before exec, bounds each stream
and polling, and checks response/family/status together. It observes exit with
WNOWAIT, reserves the leader identity until process-group termination, then
reaps and compares the actual status. Termination errors cannot skip the reap
attempt. Uncertain cleanup refuses a result. The caller must own child reaping;
nondefault SIGCHLD refuses. Hostile same-UID processes and escaped descendants
are outside this experimental custody contract.

## Tested source and limits

The [v3 development manifest](CONTINUITY-IO-EVIDENCE-20261021-V2.json) binds
base `9d30f73168c34fbad97943217e7bfde892c6cf59`, five exact overlay files,
the complete source roster, commands, binary, stack reports and tool hashes.
Strict probe/original transport/policy builds passed. The new 17 controls,
the full 96 transport/support controls and all fifteen original Ada runtime
harnesses passed. These test sets overlap; their counts are not additive.
All pure SPARK sources match the earlier `74efd05` checkpoint. No new proof
was run or inferred from that identity comparison.

The prospectively declared [resource plan](../spark/transport/CONTINUITY-IO.md)
uses 256 MiB address space, 16 MiB stack, CPU 10 seconds, 16 descriptors,
RLIMIT_NPROC/FSIZE/CORE zero, a five-second exchange deadline and one-second
cleanup wait. Effective limits and SIGPIPE handling were read back on a running
ordinary-UID process; fork refusal was exercised. RLIMIT_FSIZE limits regular
file growth and NPROC has UID/privilege qualifications. Neither is a sandbox.

Compiler stack reports and two successful positive workloads are retained.
The wait4 observer records the child's lifecycle peak, including execution
setup, rather than isolated Ada stack usage. These observations show those
selected workloads completed under the selected limits. Complete call-graph
stack/RAM sufficiency, worst-case timing, parent Python allocation and host
scheduling remain unproved. Startup syscalls do not acquire a real-time bound
from the exchange deadline. The observer itself is outside the adapter budget.

Controls include literal positive restore/transition and policy refusals,
malformed/truncated/excess input, fragmented writes and EOF waiting, descriptor
and broken-pipe errors, missing/wrong/symlink/FIFO executables, an observed
hashing mutation, process death, a valid response without exit, output overflow,
response/status mismatch and actual direct-child reaping. Chunked writes can
coalesce in Linux; they are not exhaustive syscall-fragmentation evidence.
Exhaustive partial-write/EINTR, generic descendants, resource-exhaustion sizing
and installed harness qualification remain OPEN.

## Failures and independent scope

The [earlier manifest](CONTINUITY-IO-EVIDENCE-20261021.json) and its versioned
bundle retain v1/v2 source and successful subsets. Independent actual GPT-6.1
review found FIFO/cleanup/environment/limit-wording issues, then a group-ID
reuse window and skipped reap after a termination error. All were repaired;
passing v1 tests alone did not establish safe cleanup. A final defensive check
also rejects unknown response families at the direct-helper boundary. The
public run entry already rejected that out-of-contract requested family.

An initial resource-witness attempt failed because `/usr/bin/time` was absent,
before executing its workloads. That failure remains recorded; no measurement
is claimed from it. The subsequent bounded native wait4 observer supplied
the selected observations without installing software.

Actual GPT-6.1 source/correspondence reviews found no surviving scoped blocker;
they did not independently replay execution. The Python source inventory
reported no syntactic findings for the two new files. Its status is
`inventory-only`, never Power of Ten compliance or dynamic-runtime proof.
Development snapshots predate this descriptive WIRE/Goal documentation update;
the executable source remains unchanged. The subsequent
[committed-source reproduction](CONTINUITY-IO-COMMITTED-EVIDENCE-20261021.json)
binds `e7640a75b1c48fbfa3b2431f71ff558d65d8af9e`, empty overlay and an exact
fresh archive. The same strict builds, all seventeen new tests, the overlapping
96 controls and all fifteen Ada runtimes passed. Separate resource witnesses
bind that fresh binary too; their scope remains two selected executions.
No proof was rerun or claimed from this reproduction. Complete harness/full-project proofs,
authenticated producers, the protected actuator and actual Codex continuity
acceptance remain OPEN. No universal compaction, timeout or certification claim
follows from this checkpoint.
