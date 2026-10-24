# Writer cost investigation

Status: **FAILED full writer qualification; private scalar candidate NOT ADOPTED**.
This evidence-only checkpoint changes no runtime source or original test.
It follows the [ownership type-gate candidate](OWNERSHIP-TYPE-IDENTITY-20261024.md).
Both that six-module candidate and this scalar branch-order experiment remain
unadopted; smaller passing runs do not qualify the failed full writer roster.

| Retained run | Observed result | Scope |
| --- | --- | --- |
| Original next-capture test with periodic stack dumps | 1 PASS, 19.092s | Samples in source projection and live publication/ACK replay; one invalid frame retained |
| Same original test with coarse timing | 1 PASS, 18.747s | Overlapping inclusive categories and altered callable identities |
| Same original test with internal sizing samples | 1 PASS, 21.452s | Every original call executes; profile every 64th sizing call, at most 256 samples |
| Private scalar branch-order differential and original affected-module roster | 235 PASS, 14.073s | Original 234 methods plus scalar result, budget, callback trace and exception-identity comparisons |
| Original full writer roster with private scalar overlay | FAILED, exit 124 at unchanged 60s deadline | Stopped during real output/next capture; later roster cases remain unqualified |

The coarse run recorded 16,199 source JSON sizing calls, 10,621 native-byte
calls, 81 retained-batch validations and 74 pulse preparations. These categories
overlap. They cannot be summed into exclusive costs or interpreted as redundant
work. A serializer, policy callback or alias may change between invocations;
removing calls can change behavior or lose the size-before-allocation boundary.

The internal run profiled 253 sizing calls and recorded 4,285,469 function calls
within those samples. String counting, walker/frame dispatch and budget
accounting contribute measured work. Deterministic sampling and profiling
perturb execution; this is neither a representative-distribution guarantee nor
a worst-case execution-time bound. The individual successful test does not
establish a live installed recall diagnosis or prove absence of hangs.

The resulting private experiment moves the exact-string scalar branch before
the other identity tests. It retains one type read, every selected helper,
budget addition, owner math lookup and error path under ordinary builtin
bindings. Differential controls include exotic subclasses, escaping modes,
capacity failures, nonfinite numbers and injected callback exception identity.
Selected static checks pass. Actual GPT-6.1 source/raw review found no concrete
semantic blocker to the experiment; no independent execution is claimed.

The full roster still failed, so neither performance benefit nor adoption is
established. No unchanged retry, deadline increase, cached success or removal
of checks follows. A substantive next repair needs an explicit preservation
argument and exact-source evidence for the original complete workload.

The [manifest](WRITER-COST-20261024.json) retains commands, complete source
overlays, original source, raw outputs and source endpoint inventories. The
six underlying experimental source hashes are bound by the preceding manifest.
All five run inventories were unchanged at their endpoints; this is not
continuous loaded-code custody. The private source overlay is mounted explicitly
in the retained command. Python/runtime assumptions remain unproved.

R05 mandatory reuse and fresh-policy obligations remain open. No requirement
retirement approval, main merge, installation, release, marketplace acceptance,
whole-system proof or universal compaction guarantee is claimed.
