# Experimental Linux packet intake

`request_packet.py` receives one fixed-size proposal packet without waiting.
It is not installed and does not grant
capabilities, publish state or sign receipts. Python holds no new authority.

The caller supplies a connected, nonblocking Unix `SOCK_SEQPACKET` socket
with `SO_PASSCRED` enabled before input arrives. The receiver allocates a
192-byte payload buffer and a fixed ancillary buffer, consumes at most one
packet, and returns `None` when the queue is currently empty. It refuses short
or truncated packets, truncated control data, absent/duplicate credentials,
unexpected controls and attached descriptors. Delivered descriptors are closed
even though the packet is refused; Linux must close descriptors omitted by
ancillary truncation. Transport errors propagate without a successful result.
Every delivered descriptor receives one close attempt even if another close
raises. A cleanup failure refuses the packet; it is never silently accepted or
retried. Linux close errors can leave the descriptor's state ambiguous, so the
future service must retire that connection/worker rather than continue on an
assumed clean state. Other `OSError` failures also propagate to that owner and
must not cause unlimited retry.

Returned credentials are kernel-supplied **per-message** PID/UID/GID. The test
passes a sending socket to a child and checks the child's PID, rather than
mistaking the socket creator for the sender. Credentials alone are not an
authorized capability; PID reuse, permitted credential overrides and account
compromise require the future protected authorization design. Requests contain
no trusted durability or signature-valid flags.

Each packet is one request. Short packets are never combined. Multiple valid
packets are separate requests and require separate authorization. This module
does not drain a queue, accept connections, retry, spawn workers or choose a
deadline. A future service must enforce finite connection/queue/process budgets,
fair scheduling and bounded request lifetimes; one bounded receive does not
establish bounded service resource use. Python runtime allocation and kernel
buffers are outside the SPARK proof boundary.

Run the real Linux tests from the repository root:

```sh
python3 -m unittest discover -s spark/tests -p test_request_packet.py -v
```

Acceptance still requires the Ada decoder handoff and differential tests,
capability-bound dispatcher, protected observations, Linux ownership/isolation,
exhaustion tests and the complete resident recovery campaign. This module is
not a security boundary against an unrestricted process under its own UID.

## Test-only decoder integration

`ada/request_probe.adb` is a separate, non-SPARK executable I/O adapter for
testing the receiver's actual bytes against `SIA_Request_Wire.Decode`. It reads
at most the frame plus one sentinel byte, requires EOF for an exact frame,
and emits a fixed response: acceptance byte followed by canonical encoding
of the decoded fields, or an all-zero refusal response. Read/write errors
return a failing process status. Serialization uses decoded fields, not an
input echo. This is a syntax result, not authorization or shadow policy.

The initial Stream_IO adapter failed with DEVICE_ERROR on Linux pipes; its
failed integration output is retained. The replacement uses GNAT.OS_Lib
descriptor calls over fixed, in-scope byte storage. Those raw-address calls,
the GNAT runtime and this serializer are outside the proved package boundary.
Blocking calls require an external process deadline. This adapter must not be
installed as a resident authority or used as an unrestricted subprocess broker.

Build and test (source the GNAT environment first):

```sh
gprbuild -p -P spark/transport/request_probe.gpr
timeout --kill-after=5s 60s python3 -m unittest discover -s spark/tests -p 'test_*.py' -v
```

The test driver exercises every supported action/phase pair with reproducible
nonuniform field bytes, integer boundaries, reserved/header refusals, valid
prefixes and valid frames with trailing bytes, EOF waiting and actual descriptor
error returns. The small-chunk writer test permits kernel coalescing; it is not
a controlled proof of syscall fragmentation. Output capture is bounded by this
specific fixed-output test executable, not by a generic subprocess limiter.
Acceptance evidence must build the executable from a fresh committed archive
and retain binary/source hashes and commands; mere binary presence is not
source-binding evidence. The production handoff, authenticated dispatch and
actual shadow policy comparison remain unimplemented.

## Pure decoder-to-admission composition

`SIA_Request_Admission.Classify_Frame` composes decoding and exact-grant
comparison without trusting a caller-supplied syntax-acceptance flag. Invalid
frames return the empty request and `Denied`; valid frames retain their exact
decoded fields and receive the pure classifier result. A valid denied request
still contains untrusted decoded fields, so consumers must never dispatch on
those fields while ignoring the decision. `Proposal_Only` is still not permission
to mutate. The original decoder contract remains unchanged.

The committed-source reproduction at `20924429c26e2d203ae095d6d3d9205266642e02`
passed strict build, all four runtime harnesses, and all 269 reported proof
checks across eight units, with no justified or unproved obligations. Independent
GPT-6.1 review checked the retained archive, manifest, source, outputs and coverage
without rerunning them. This establishes the pure composition contracts only.
It does not yet connect kernel credentials or a protected grant store to an
installed service, and does not change released behavior.

## Test-only composed admission handoff

`admission_probe` is a separate descriptor/CLI adapter built by the same probe
project. It takes fixture grant UID, observed sender UID, clock tick and grant
action (`observe` or `propose`) as four arguments. It uses a fixed expected request
and grant interval defined in its source, consumes at most one frame plus a
sentinel, and emits exactly one classification byte: D, O or P. Invalid metadata
or I/O errors fail the process; malformed frames produce D. The parent supplies
a finite deadline and closes input at EOF.

`test_admission_probe.py` passes actual receiver payload/UID values through this
adapter. Metadata is then command-line input, not authenticated IPC: the test
controls the grant and clock and could substitute another UID. No service, grant
store, effect handler or production dispatcher is installed. The raw descriptor
adapter and Python orchestration are outside the SPARK proof boundary.

Controls cover valid observation/proposal, sender/action/time mismatches, every
single-byte mutation, malformed metadata and scalar limits, short/trailing input,
read errors and output errors. Run the existing `test_*.py` command after building
both probes. A fresh archive of aa620d001825d87024457df202f699251eb52925
passed the strict probe build and 33 Python controls. Independent GPT-6.1 review
checked the retained source bindings and outputs without rerunning them.
The first strict adapter build's Unreferenced warning failure is retained.

## Bounded grant-record observation

`grant_record.py` reads one fixed `grant.record` name relative to an already
authorized directory descriptor. The service must hold an exclusive grant-store
lease throughout observation and use. Directory ancestry, descriptor provenance,
separate service identity and lease enforcement are external obligations.
The reader checks service ownership, private modes, a single regular-file link,
bounded size, complete read and unchanged held-file/name/directory observations.
It closes its file descriptor; the caller retains its directory descriptor.
Both `GrantRefusal` and `OSError`, including close errors, must fail closed.
Cleanup uncertainty must be retained rather than retried as apparent success.

The ASCII format has a version line and five fixed ordered fields: subject,
not-before, expires, active and a lowercase hexadecimal request frame. It has
one final newline and is bounded to 1024 bytes. Decimal encodings are canonical.
Parsing preserves inactive grants, invalid policy intervals and syntax-invalid
request frames for SPARK to reject. Parsing does not authorize an operation or
authenticate the grant's issuer, clock, protected ancestry or installation.
Metadata comparisons are observations under the trusted lease, not protection
against a hostile process holding the service UID.

The eleven development controls cover independent field values, malformed
records, actual permission/link/special-file failures, changes during reading,
short reads, read errors and descriptor cleanup. Foreign ownership and isolated
name mismatch are synthetic observations; they do not establish a separate-UID
boundary. A fresh archive of 975bd37a13dfb7088df0200a9fa82a14478182b4
passed all eleven controls with unchanged source inventories. Independent
GPT-6.1 review verified the manifest, archive/commit/extraction equality and
retained outputs without rerunning tests. This accepts bounded observation
under the stated assumptions only.
Production grant commissioning, protected dispatch and bypass-resistance tests
remain unimplemented. Run the focused controls with:

```sh
timeout --kill-after=5s 60s python3 -B -W error::ResourceWarning -m unittest discover -s spark/tests -p test_grant_record.py -v
```

## Test-only loaded-grant handoff

`grant_probe` receives exactly two frames on standard input, grant first and
request second, followed by EOF. Six bounded canonical decimal arguments carry
grant subject, observed sender, current tick, not-before, expiry and active bit.
It decodes the grant frame before invoking the composed request classifier;
an invalid grant frame returns D. Input/output errors and malformed metadata
fail the process. The parent must enforce a deadline while waiting for EOF.

`test_grant_probe.py` connects the private disposable grant reader and actual
SEQPACKET receiver to this adapter. It checks independent observation/proposal
outcomes, matching nonuniform payloads, each changed grant byte, identity,
revocation and interval refusals, invalid frames, exact input length, canonical
metadata and descriptor failures. Run the existing `test_*.py` command after
building all three probes. A fresh archive of
`7f604a037f37f9e828ee110d1c46efc4cc1c0c0e` passed the strict build and all
53 transport/support controls. Independent GPT-6.1 review verified archive,
manifest and source bindings, including unchanged pure sources relative to
the accepted proof, without rerunning the tools. Acceptance covers the
fixture handoff only; the raw I/O adapter is not proved.

This is an execution-path test, not a protected service: the Python test driver
can substitute the grant, sender or clock. The grant record does not bind a boot
or service epoch. No production caller may treat this executable or its output
as authenticated authority, a mutation permit or a disclosure authorization.
The earlier failed build due to Decode argument ordering is retained.
