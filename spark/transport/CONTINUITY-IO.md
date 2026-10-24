# One-request continuity process, experimental qualification plan

This increment addresses A22/C07/C11's bounded representation handoff, not original
capture, authentication, protected publication or installed restoration. No
live corpus is opened. All existing proof/runtime obligations remain required.
The Ada descriptor calls, GNAT runtime, Python supervisor, `prlimit`, libc,
loader and Linux are outside the pure SPARK proof boundary.

Before adapter qualification, strict compilation must produce stack-usage
reports. Qualification uses these prospectively selected conservative caps,
set before exec: address space 256 MiB, stack 16 MiB, CPU 10 seconds, file
descriptors 16, RLIMIT_NPROC 0, RLIMIT_FSIZE 0 and core files 0. These are
diagnostic ceilings, not measured memory requirements or WCET proofs. The
parent's normal deadline is 5 seconds (tests may only lower it), stdout 64
bytes, stderr 4096 bytes, input 32768 bytes and 8192 polling iterations.
The existing build cap remains 120 seconds. No proof/job/spending cap changes.
RLIMIT_FSIZE limits regular-file growth; it is not a file-write prohibition.
RLIMIT_NPROC is enforced against the real UID and has privilege exemptions;
it is not an authenticated process/cgroup boundary. Qualification must observe
the unprivileged identity and a fork refusal. Neither limit is a sandbox.
The single owner observes exit with WNOWAIT, retaining the unreaped leader
until group termination so the numeric process-group identity cannot be reused.
Cleanup attempts group termination even after leader exit and waits at most
one further second to reap the direct child; uncertainty refuses a result.
Termination and reaping errors are both checked; failed termination cannot
skip the reaping attempt. External child reapers are outside this owner contract.
Hostile same-UID group manipulation and generic descendant custody are not
qualified by this disposable no-descendant adapter.
Physical stack sufficiency and runtime usage must be observed on the exact
compiled target before the adapter is considered qualified even experimentally.
An incomplete/dynamic compiler stack report remains a visible limitation.

The child makes at most 32769 reads (including the extra-byte/EOF check) and
64 writes, with checked counts and no syscall retry. It cannot grant an action.
EINTR and other descriptor errors fail with status 74. EOF before/after the
exact frame emits the canonical malformed response/status 65. A valid request
is evaluated by the existing policy and encoded by the existing response core;
policy refusal still exits 0. The parent must ignore SIGPIPE before exec so
broken output becomes a checked error. Unsupervised signals or resource deaths
are failures, never policy results. The fixed loop counts do not bound blocking
syscall time: the parent must kill and reap a stalled child.

Qualification must retain exact source/binary/tool hashes, resource-limit
readback on the running process, normal restore and transition results,
malformed/truncated/excess frames, EOF waiting, fragmented input, descriptor
errors, process death, missing/mismatched executable, bounded output refusal,
response/status/family mismatch, deadline cleanup and original runtimes.
Literal expected values must be independent of a shared encoder. Compiler
stack reports and observed process limits do not prove the entire call graph,
Python allocation, physical RAM availability or host scheduling latency.

The supervisor pins an opened executable and records the exact input digest.
These local correlations do not authenticate an adversarial same-UID producer
or make self-asserted source descriptors true. Linux protected custody and a
qualified harness adapter remain mandatory later gates. There is no installed
entry point and no other-harness compatibility claim.
