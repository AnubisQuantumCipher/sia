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
