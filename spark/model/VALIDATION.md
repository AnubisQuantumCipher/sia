# Bounded publication model validation

TESTED / MODEL-CHECKED, 2026-10-19. TLC release artifact 1.7.4 reports TLC2
2.19, revision 5a47802. Tool artifact hashes are in `toolchain.json`.
The Java archive was checked against the publisher's SHA256; TLC was checked
against its published SHA1 and pinned by locally computed SHA256. These are
tool provenance checks, not tool qualification or proof of tool correctness.

The `spark/check-model.sh` reproduction passed all three lanes with a private
temporary directory per lane, one worker, bounded heap and per-lane timeout:

- Correct model: exit 0, 176 generated states, 93 distinct states, no queued
  states left, and no safety-invariant error.
- Premature-readiness mutation: exit 12 with `ReadySafe` violated after the
  first completed phase. This failure is the expected negative control.
- Correct model plus deliberately false `NotReadyYet`: exit 12 after reaching
  final phase 10, synchronized effect 10, retired intent and readiness true.
  No earlier safety invariant failed. This witnesses nonvacuous readiness.

Independent GPT-6.1 source review found no blocker in the stated single-
transaction atomic-action abstraction. It did not independently run TLC.
Raw outputs, counterexamples, tool manifest and reproduced run are retained
in the operator-local `sia-assurance-evidence-20261019` evidence directory.

The runtime executable is ARM aarch64 and Java reports `os.arch=aarch64`.
TLC's banner also contains an `x86_64` VM label; that label does not establish
a separate x86 execution or cross-platform validation.

UNPROVEN: unbounded behavior, eventual progress, multi-transaction allocation,
cryptographic receipt authentication, cumulative artifact durability, actual
filesystem operations, persisted readiness rejection, restore migration and
the relation between this model, Ada and the installed Python runtime. The
model relies on the assumptions explicitly listed in its README. Passing it
does not authorize transferring runtime authority or advertising system proof.
