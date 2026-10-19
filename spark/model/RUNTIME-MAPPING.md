# Runtime correspondence and remaining obligations

This is a source inspection map, not a proved refinement. The model's durable
intent and per-phase record are proposed protocol states; the released Python
runtime does not implement that exact model merely because names correspond.

| Abstract phase | Existing runtime boundary | Evidence still required |
| --- | --- | --- |
| Source_Retained through Effects_Committed | Source capture, publication, live-generation and effects receipt protocols preceding `siasourceack._acknowledge` | Fresh resident execution with actual Git/index operations and cuts inside each publication |
| Effects_Archived | `_EffectsArchiveSlot.publish`, then `effects-receipt-archive-durable` | Cuts within fixed atomic publication, including synchronization failure |
| Source_Archived | `_ArchiveSlot.move`, then `archive-durable` | Cuts between rename and synchronization of both parent directories |
| Refusals_Settled | Refusal settlement callbacks, then `refusals-durable` | Refusal-bearing batches with actual signed append/replay evidence |
| Journals_Durable | Each journal cursor publication and separate `journal-<scope>-durable` hook | Multiple cursor prefixes; model currently collapses these into one phase |
| Main_Cursor_Durable | Main cursor publication, then `cursor-state-durable` | Cuts within atomic cursor publication and durable third-state rejection |
| Ack_Committed | Final memo publication and `memo-durable` | Fresh interpreter revalidation of persisted readiness and every referenced artifact |

`_acknowledge` validates the durable memo, source batch, effects receipt and
live-generation join before publication. It rechecks artifact identities and
memo state between effects. Cursor authority accepts the exact before or target
state and refuses a third state. A completed ACK follows `_completed` and is
intended to be effectless. These are runtime checks, not SPARK-authorized writes.

The model separates `WriteEffect`, `SyncEffect` and `CommitRecord`. The current
component campaign cuts only at named hooks after publication functions return.
It therefore cannot establish that actual fsync/rename operations implement
those abstract actions under power loss. Filesystem and storage guarantees
remain assumptions until separately tested and documented.

## Component process-death campaign

`tests/test_assurance_ack_process_death.py` forks a child and sends that child
SIGKILL at each selected ACK boundary. The parent reaps it, reloads memo bytes,
recovers the transaction, and compares artifacts after a repeated ACK. Images
include both source and effects archives and their directories. Journal cuts
receive the same repeated-retry check. A foreign cursor after child death must
refuse without changing the observed artifacts or publishing readiness.

The existing fixture controls source capture and Git/index observations.
Recovery retains the parent's fixture and patches; it is not a clean resident
or interpreter restart. Core cuts use an empty source batch, so reaching the
refusals hook does not test signed refusal persistence. No live corpus is used.

The next acceptance campaign must launch a new resident process against a
disposable complete installation, independently reload every authority input,
exercise nonempty and refusal-bearing sources, and retain crash/replay receipts.
It must also test stale persisted readiness. Systemd service readiness is not
the memory-publication readiness predicate. None of these component results
authorizes transferring authority to the proposed SPARK service.

## Interruptions inside namespace publication

The extended component campaign now interrupts source archival immediately
after the real rename, and effects/main/journal publication at the queue's
`target-published` hook before directory synchronization. Recovery must fsync
each relevant parent before its corresponding ACK durable hook. Observations
are cleared after each hook so an earlier stage cannot satisfy a later stage.
Source archival requires both old and new parents; cursor and effects archive
recovery require the retained destination parent.

Synchronization-failure controls are armed only at the selected stage, require
the exact injected exception, and check pending authority and absent readiness.
Both source-archive parents receive separate failure injections. These tests
establish recovery ordering and error propagation under process interruption;
they still do not establish power-loss survival or filesystem refinement.
