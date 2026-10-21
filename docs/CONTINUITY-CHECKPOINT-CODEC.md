# Fixed checkpoint record boundary

This experimental increment implements the fixed 10,816-byte Checkpoint record
in [the proposed continuity protocol](../spark/CONTINUITY-WIRE.md). It does not
implement the outer frame, current-evidence record, authenticated producers,
checkpoint publication, original-event capture or a harness restoration hook.
The installed SIA runtime does not use it.

The decoder validates the header and every claim/operation slot, including
inactive slots, before constrained conversions. Successful decoding preserves
every field. Representable but policy-invalid records remain intact for the
existing policy to classify. Any malformed representation returns the complete
typed empty checkpoint. In particular, an all-zero wire record differs from
the typed empty: its claim origin/role codes denote Source_Record/User.
Neither successful decoding nor a model-origin note grants authority.

## Contract and baseline mapping

| Power of Ten intent, adapted to this boundary | Implementation and evidence | Remaining limit |
| --- | --- | --- |
| 1–2: simple control flow and bounded execution | Pure procedures, explicit finite array ranges, no recursion, termination and prefix/frame contracts | No wall-clock or filesystem/adapter termination proof |
| 3: controlled allocation | Fixed byte/record arrays; existing no-allocation compiler restrictions remain enabled | Physical stack capacity, runtime/library memory and process budgets unqualified |
| 4: small routines | Decoder and individual test routines remain below the approximate 60-line baseline | Shortness is an inventory property, not semantic correctness |
| 5: meaningful contracts | Exact acceptance relation, field correspondence, canonical-empty refusal, checked nested-decoder outcomes and loop frames | Contracts depend on the existing record/context primitives and toolchain assumptions |
| 6: limited scope | Pure package; null global effects; procedure-local decoder temporaries overwritten before use | GNATprove rejects composite block locals before loop invariants, so temporaries use procedure scope |
| 7: checked input and results | All scalar codes, counts, generation high bytes, reserved bytes and all nested slots checked | Representation does not authenticate a digest, source, approval or durability observation |
| 8–9: explicit semantics and restricted indirection | Named protocol mappings, explicit byte copies, static calls and array deltas; unchanged no-dispatch restrictions | Ada/runtime/compiler implementation remains part of the assumption boundary |
| 10: strict diagnostics | Warnings remain errors; raw diagnostics and exclusion lists inspected; failed attempts retained | Focused proof cannot replace complete-project or installed-path acceptance |

This is a cross-language adaptation, not a quotation of Holzmann's rules or
a compliance declaration. The [normative-source assessment](POWER-OF-TEN-ASSESSMENT.md)
and its unresolved system obligations remain controlling.

## Independent tests and retained failures

The harness checks all coverage/count byte values, generation boundaries,
reserved header positions, malformed inactive records, typed-empty refusal,
and preservation of model-authored permission records and acknowledged
operations without results for policy rejection. A nonuniform header vector
checks byte order. Independently specified first, interior and last claim and
operation vectors assert complete decoded arrays; they are not encoder output.
All prior harnesses and their original fixtures remain in the build and runner.

The [scoped evidence](CONTINUITY-CHECKPOINT-WIRE-EVIDENCE-V2.json) includes
exact source overlays, base revision, commands, tool hashes, raw reports and a
versioned reproducible archive. It retains these failures:

| Attempt | Observation |
| --- | --- |
| Development v1 | Compiler rejected variable-index ordinary aggregates; runtime/proof unrun |
| v2 | Build and all twelve runtimes passed; proof rejected arithmetic reassociation warnings |
| v3 | Core obligations discharged but array-initialization warnings failed the strict command |
| v4 | Block-local composite temporaries before loop invariants rejected by GNATprove |
| v5 | Procedure-local temporaries alone did not remove the array-initialization warnings |
| v6 | Whole-array delta updates passed the core proof: 77 reported checks; combined harness timed out at 120 seconds without a fresh summary |
| v7 | Stronger test loop frames preserved build/runtime/core passes; combined harness again timed out without a fresh summary |
| Canonical diagnostic v1 | Incorrect source-line selector generated no checks; failed, not proof evidence |
| Canonical diagnostic v2 | Derived selector analyzed the intended routine; 15 reported checks discharged under explicit limited scope |
| v8, unadopted | Alt-Ergo first for the new harness; build, all twelve runtimes and core proof passed, but the complete harness still timed out at 120 seconds |

The canonical diagnostic retains Z3 and CVC5 timeouts on loop preservation
followed by successful Alt-Ergo proofs. It does not establish the complete
harness. The subsequent candidate tried Alt-Ergo first only for the new
harness. Retained effective translator settings confirm all warnings,
all-mode analysis, no-inlining, one job, 512 MB and the 10-second check limit
remained enabled. It did not establish a complete harness result or an overall
performance improvement, so that project-file change is unadopted. Active
source matches the v7 checkpoint; the earlier evidence edition is retained.

The actual GPT-6.1 source reviewer closed the nonuniform-vector finding and
found no core mapping defect in the reviewed source. Source review does not
qualify a proof report or override a timed-out command.

The [subsequent independent evidence review](evidence/continuity-checkpoint-wire-review-v3.txt)
verified source/archive correspondence and the core's raw/summary result for
this non-final checkpoint. It did not replay the proof or close the remaining
harness, full-project, committed-reproduction or integration gates.

After that checkpoint was committed and pushed, a fresh archive of
`ac0a35857180381ff07feff7eef5046ed25789e3` reproduced the strict build,
all twelve runtime harnesses and the focused 77-check core proof. The
[committed-source evidence](CONTINUITY-CHECKPOINT-COMMITTED-EVIDENCE-V2.json)
binds the archive, complete source inventory, unchanged tool identities,
commands and raw reports. Its derivation checks the exact command roster,
copied/generated report equality and the existing strict report predicates.
This closes committed reproduction only for that declared scope. The known
failing complete-harness proof was not repeated or relabeled as passing.
An [independent read-only check](evidence/continuity-checkpoint-committed-review-v1.txt)
confirmed this correspondence, including the current command arguments and
tool rosters. The retainer is a consistency aid, not a qualified general
acceptance gate; its narrower automated checks remain explicit in the review.

## Remaining acceptance

Complete harness and full-project proof, source-bound raw/summary coverage,
complete committed-source reproduction, independent evidence review and target
resource qualification remain required. The prior full-project 600-second
failure is unchanged. No 900-second campaign is authorized or claimed.

The subsequent [Current_Evidence increment](CONTINUITY-CURRENT-CODEC.md) adds
that fixed-record decoder. Exact outer framing and comparison with the existing
classifiers remain next. Production integration
also requires independently authenticated source/currentness observations,
fault-tested publication and actual harness lifecycle tests. This increment
establishes no universal compaction, recall-latency or avionics assurance claim.
