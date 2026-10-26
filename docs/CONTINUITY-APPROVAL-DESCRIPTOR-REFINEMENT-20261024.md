# Approval descriptor: completed focused refinement proof

**PROVED within the declared focused project; runtime TESTED; UNACTIVATED.**
This successor closes the descriptor proof obligations left open by the
[previous failed checkpoint](CONTINUITY-APPROVAL-DESCRIPTOR-20261024.md).
It does not close protected integration or whole-system acceptance.

## What changed and what was proved

The previous direct arithmetic argument was difficult for the provers, and
prefix equality required an explicit connection between extracted digests and
their source byte ranges. The implementation now proves those connections in
small private Ghost procedures:

- `Low_Digit` establishes the low-byte remainder for a bounded prefix and byte.
- `Recover_Digits` constructs bounded positional prefixes, proves their exact
  relationship to the original word value, and uses the low-byte lemma.
- `Digest_Unique` connects equal extracted digests to their exact byte ranges.
- `Prefix_Unique` applies that connection to every original prefix field and
  establishes equality of the format marker.

All helper bodies, overflow checks, call premises, assertions and postconditions
are analyzed. They are neither imported axioms nor assumed declarations.
The public specification before the private section is byte-identical to the
previous checkpoint. The production `Decode` body, original test sources,
focused project settings and dependencies are also byte-identical. No valid
input, fixed bound, required field, refusal or final uniqueness conclusion was
removed. The original aggregate assurance project remains unchanged.

The terminal `gnatprove -U --mode=all --assumptions --no-inlining` run reports
**all 351 checks proved: 150 flow, 201 prover, zero justified and zero unproved**.
Every descriptor entity appears in the complete detailed report, including the
supporting lemmas. The same strict project warnings, 120-second outer deadline,
512 MiB per-prover limit, 10-second prover timeout and single job were retained.
The full run exited 0; elapsed time was 87652745596 ns. No cap increase or
unchanged failed-source retry was used to obtain this result.

This proves the stated typed representation and uniqueness contracts under the
reported modular dependencies and toolchain assumptions. It does not prove
human authorship, approval semantics, collision resistance, external durability,
currentness of supplied evidence or protection against hostile same-user code.
Zero `pragma Assume` statements does not mean assumption-free verification.

## Runtime and independent evidence

The strict build and original plus expanded synthetic runtime controls exit 0.
The runtime support and main programs remain explicitly SPARK-off; their
execution is test evidence, not a proof of those test programs. Independent
oracles retain every-byte mutations, nonuniform digest values, named enum
meanings, mixed/boundary generations and stale authenticated output clearing.

The final negative changes the question byte order in both the decoder and its
specification. It builds successfully but fails the unchanged nonuniform digest
oracle at `continuity_descriptor_test_support.adb:183`, exit 1. Thus agreement
between a changed specification and implementation does not by itself satisfy
the independently retained representation oracle. The negative is not adopted.

Actual GPT-6.1 reviewed source, complete raw report, endpoint hashes and negative
receipts read-only. It did not independently execute the tools. The exact inputs,
commands, toolchain versions, complete proof report, diagnostics and retained
archive are recorded in the
[evidence receipt](CONTINUITY-APPROVAL-DESCRIPTOR-REFINEMENT-EVIDENCE-20261024.json).

## Failures remain visible

The original failed candidates and sealed v1 archive are retained unchanged.
This continuation adds the following history:

| Candidate | Result and disposition |
| --- | --- |
| 8 | Build/runtime pass; strict SPARK rejects missing arithmetic parentheses. Descriptor proof skipped. Warning retained as an error; explicit grouping repairs it. |
| 9 | Build/runtime pass; proof exits 124 at the original outer limit, with digit 7 recovery reported unresolved. Partial regional proofs do not make that run complete. |
| 10 | Full focused proof and runtime pass on unchanged endpoint source inventories; final coherent negative rejected. |
| Negative 8/9 | Source prepared but not built or executed; UNRUN. |

Power-of-Ten adaptations remain fixed storage and explicit ranges, bounded
nonrecursive control flow, short private routines, meaningful contracts,
checked refusal/output clearing, restricted indirection and strict analysis.
These are cross-language adaptations, not Holzmann quotations, whole-system
proof or avionics certification. Python/Linux/harness resources remain outside
this focused mathematical claim.

## Remaining acceptance

Next is protected producer integration: authenticate original question/response
records and independently selected request scope; bind these exact descriptor
bytes to custody/hash evidence; enforce current lifecycle, retention and
revocation; then qualify actual generic restoration and actuator behavior.
The existing refusal remains until that complete path qualifies. A parser or
model summary alone cannot establish this boundary.

AR-T01–AR-T22 remain ALL_UNRUN at the actual protected/generic boundary. Native
manager qualification, original full proof/writer/recovery/installed gates and
marketplace publication remain open. R05 is UNVERIFIED/PENDING; both useful
expensive reuse and fresh current-policy validation remain mandatory. This
checkpoint grants no new action authority and makes no installation, main merge,
release or marketplace claim.
