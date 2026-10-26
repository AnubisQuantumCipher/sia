# Request capacity observations and policy-check repair

Status: TESTED experimental boundary repair and bounded fixture observations.
Normal runtime remains legacy-only. No installed activation, migration, recovery
acceptance, resource-cap increase or R05 requirement change follows.

## Reproduced defects and repair

The reader previously compared a current owner limit to an admitted limit using
ordinary inequality. A Boolean could compare equal to an integer limit, and an
object with a deceptive comparison method could suppress detection. Retained
negative controls reproduced both failures. The current guard requires exact
native `int` type before comparing values, so those hooks are not invoked.

An additional retained negative control changed the record limit from inside the
last `capture.check_file` callback. The earlier guard ran before that callback and
missed it. The reader now retains the early guard and repeats it after the final
capture check. This protects the helper's synchronous endpoint; it does not
freeze policy through later caller actions or authenticate callbacks. Caller
lease and complete capture validation remain required.

A real capture-reservation test completes the first full group, then exhausts the
shared budget in a later group and verifies that `found` receives no partial
additions. The budget object's attempted reservation is not rolled back; the
failed operation and capture must be discarded. This is not allocation-failure
atomicity of a later successful `found.update`.

The final original-plus-new roster passed 140 tests in 11.797s under the unchanged
60-second isolated job, 2 GiB address-space, 512 MiB file and zero core limits.
Selected final reader, test and named driver static analysis reports zero
findings. No measured function in that scope exceeds 60 source lines. Original
system warning/proof/acceptance obligations remain open. Before/after source
inventories match for the regression and both final measurement jobs.

## Actual maximum-count refusal observations

The real preparation front door received 65,536 unique fixture events. It refused
the original complete-byte limit before opening the corpus capture. This is an
expected refusal, not support for successfully preparing that many events.
The public front door decorates the inner capacity error with bounded diagnostic
context. The first observer expected the undecorated message and failed; its raw
failure is retained. The corrected observer checks the original exception cause.
No product behavior was changed to make that observer pass.

Separate lookup-subpath observations used 65,536 absent identities through the
actual `_Capture`, in one-prefix and mixed-prefix shapes. Every case refused the
original 16,777,216-byte budget, returned no found entries, and closed the capture
root descriptor. These observations do not exercise maximum populated packs,
epoch parsing costs, successful maximum-domain lookup or complete memory bounds.

| Shape | Reader | Read calls | File observations | Attempted budget at refusal | Elapsed ns |
| --- | --- | ---: | ---: | ---: | ---: |
| one-prefix | legacy | 15054 | 15053 | 16777374 | 248537523 |
| one-prefix | packed | 15286 | 15051 | 16778208 | 7845740344 |
| mixed-prefix | legacy | 15000 | 14999 | 16777770 | 248774115 |
| mixed-prefix | packed | 14996 | 14995 | 16777804 | 8457767267 |

The over-limit value is the attempted reservation at refusal, not an admitted
allocation. Reservation metadata, Python allocator behavior, descriptor limits
and total process memory are separate concerns. Process high-water RSS is a
cumulative observation, not an independent per-case peak or a formal bound.
Both readers refuse within the original job envelope in these observations.
The experimental reader is slower and retains additional observations; those
costs must not be hidden by the earlier pack-only improvement.

## Complete fixture preparation, publication and retry

A separate job runs 1,024 novel fixture events through the actual leased
preparation, publication and retry front doors for legacy and experimental joins.
Both produce three pages with exactly equal final bytes and exactly one entry per
event after retry. The candidate observes both storage routes, including absence;
there are no populated packs in this particular workload. Populated-pack replay
has separate smaller-fixture evidence and is not inferred from this result.

| Reader | Prepare ns | Publish ns | Retry ns | Serialized plan bytes |
| --- | ---: | ---: | ---: | ---: |
| legacy | 391321238 | 1209362626 | 485555487 | 1082614 |
| packed | 606781340 | 1914908483 | 744260522 | 1147461 |

The full per-capture reservation/file/directory observations and exact page hashes
are retained in the companion evidence JSON. These are single-run measurements,
not WCET, performance non-regression, maximum-domain acceptance or an installed
latency guarantee. The successful workload and the deliberate large-request
refusals are distinct results. All earlier measurements, including intermediate
source versions, are retained under their own source pins.

## Consequences for activation

The resource evidence supports retaining the experiment and its boundary repair.
It does not justify removing observations, resetting budgets, raising limits or
accepting a smaller semantic domain. Additional route observations can exhaust
an unchanged aggregate budget earlier; equivalence of the whole previously
accepted workload domain has not been established. That compatibility obligation
must be resolved before activation.

Source inspection found readers outside the occurrence join: consolidation
preflight, index publication and compacted-source outcome verification still use
the legacy entry point. Retirement before qualifying those consumers can break
replay or conflict validation even if occurrence tests pass. The accompanying
`EVENT-INDEX-PACK-MIGRATION-GATES-20261024.md` records this inventory, proposed
phase invariants and fault campaign. It is a design, not an implemented migration
or authority grant.

The next work is complete consumer integration and deterministic exact-coverage
planning, followed by protected SPARK authorization, durable transaction adapter
and fault-injected recovery. Maximum populated-domain cost, correction/deletion
through packed descendants, supported downgrade, installed capsule/off-path
restore and all original system/release gates remain open. Power-of-Ten-inspired
checked inputs, short routines and explicit failure paths do not prove the Python
runtime, the whole SIA system or avionics certification.
