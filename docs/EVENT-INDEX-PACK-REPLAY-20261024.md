# Captured pack replay and bounded group lookup

Status: TESTED experimental prerequisites. No runtime activation, migration,
legacy retirement, installed recovery or release acceptance. The earlier pack
transport/reader contracts and every original assurance obligation remain binding.

## Replay evidence

Temporary fixtures substitute the reader into the existing
`_prepare_event_page_plan` and `_publish_event_page_plan` entry points. The actual
`_Capture` and `_BeforeView` implementations run under the real fixture corpus
lease. Complete capture validation runs with that lease held. This exercises
dependency serialization, replay and page publication rather than serialization
alone. It does not qualify the resident daemon or the installed source corpus.

The controls include a packed retained event plus a new event, publication and
retry without a duplicate new entry; omission of a pack dependency followed by
rehashing; same-byte pack replacement; both legacy and pack appearance after an
observed absence; fresh epoch-policy refusal; and the original aggregate plan
limit. An exhausted capture-reservation control refuses before rereading retained
pack bytes or decoding them. Original page publication/order tests remain in the
roster; counting completed capture calls alone would not prove effect ordering.

The final roster passed 123 tests in 9.427s. Original codec, captured-reader,
event-epoch integrity, epoch merge, module ownership and complete event-page-plan
tests remain included. Tests use unchanged 60-second isolated jobs, 2 GiB address
space, 512 MiB file cap, zero core files and the existing heavy-job lock. Inventoried
source bytes match before and after. Earlier 116/117-test results remain retained.

## Measured cost and the new operation

A full canonical fixture group exposed repeated whole-pack validation: looking up
its identities individually repeatedly validates every contained record. A new
`read_group_captured` operation accepts an exact sorted, unique tuple containing
one through 64 identities with the same organ and three-hex prefix. It reads all
requested legacy observations, decodes and freshly validates the complete pack
once, freshly validates every present requested legacy record, compares duplicate
bytes and checks every present/absent path. A changed record-byte policy during
the group refuses. No validated result is retained between calls.

Every packed record is checked, including unrequested records. A valid requested
record cannot bypass a later invalid record. A duplicate legacy record still
invokes its own fresh validator even if its bytes equal the packed record. The
singleton entry point delegates to a singleton group and retains that behavior;
a stateful validator accepting the pack and refusing the legacy duplicate is a
negative control. Repeated group calls repeat epoch validation.

This is an explicit new operation contract. It has a different callback trace
from repeated singleton operations and is not claimed to be their transparent
replacement under arbitrary stateful callbacks. Caller integration must partition
the complete originally bounded request while preserving one aggregate capture
and budget. It must not reset allowances per group. Saturated-prefix or oversized
legacy records retain their original fallback; this API does not perform packing.
Normal runtime lookup remains legacy-only and does not import this reader.

One bounded measurement produced these observations for 64 fixture identities:

| Operation | Epoch validations | Elapsed nanoseconds | Retained capture reservation bytes |
| --- | ---: | ---: | ---: |
| Original legacy lookups | 64 | 40085814 | 182498 |
| Packed singleton lookups | 4096 | 1677030484 | 126575 |
| One packed group | 64 | 42612356 | 126575 |

Returned canonical entries matched exactly. The process high-water RSS observation
was 61640 KiB at each stage; this is a cumulative process observation, not separate
peak memory for each operation. Reservation bytes are not complete interpreter
memory. The original slower observation is retained too. This fixture uses a
controlled canonical roster, not proof of captured occurrences, maximum request
cost, worst-case execution time or installed latency. No resource cap was raised.

## Remaining gates and engineering adaptation

The group routines are short, explicitly bounded and side-effect-free with respect
to corpus writes. They preserve fresh validation and propagate refusal. These are
Power-of-Ten-inspired project controls, not quotations or formal compliance.
Python allocation, dynamic owner callbacks, parser/epoch costs, cryptography and
Linux I/O remain separate trust and resource obligations. The selected static
profile is clean for the new/changed reader, new tests and named final drivers;
inherited thought-module findings remain open as previously recorded.

Next: integrate grouping into the actual occurrence-lookup request while retaining
the original aggregate identity/state limits and final capture checks, then qualify
complete request cost and original callback/semantic controls. Follow with exact
coverage, durable pack publication, fault-injected migration/reconciliation and
verified legacy retirement. Protected SPARK authority, native admission, actual
capsule/off-path restore/replay and release/catalog qualification remain open.
Neither this API nor its measurements change R05 or grant pending approval.
