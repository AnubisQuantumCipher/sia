# Experimental Linux packet intake

`request_packet.py` receives one fixed-size proposal packet without waiting.
It is not installed, does not call the Ada decoder yet, and does not grant
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
