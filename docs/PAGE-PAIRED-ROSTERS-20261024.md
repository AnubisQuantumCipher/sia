# Page-plan paired rosters: bounded refusal repair

Status: **TESTED for the stated scope; complete assurance remains open**.
Base source is `147d9eeeb8d0fc69b0fe50e820c8a072267a4cfb`. The companion
JSON retains exact source maps, raw output, commands, original failing source,
negative controls and source review. This repair changes no cache or test gate.

## Defect and repair

`_member_pins` and `_batch_pins` check initial roster lengths, then hash entries
while iterating ordinary `zip`. An owner digest callback can shorten one or
both rosters during the first digest. The remaining entries are silently
skipped, and validation returns successfully. Growing both rosters extends
work beyond the admitted initial count. The original source fails all twelve
new mutation subtests across member/batch and left/right/both growth/shrinkage.

The new `_paired_rows` captures the initial length, rejects unequal lengths,
and yields within that bound using strict zip. It checks one terminal advance
after the bounded traversal to reject residual growth. Premature exhaustion or
iterator mismatch uses the caller's existing refusal reason. Caller-body
exceptions occur outside that translation and retain their original identity.

Both pin-validation passes and complete page-admission pairing use this helper.
Fixed native-stat tuple pairing and the private event tuple/record-comprehension
pair use `strict=True` directly. No `strict=False`, suppression or truncated
fallback is introduced. The original body order and live value reads remain.

## Verification

| Scope | Result |
| --- | --- |
| Original source, two focused methods | FAILED: twelve roster-mutation subtests |
| Candidate, same two methods | PASS |
| Candidate plus initial mismatch, body-error and live-replacement controls, original page/batch/closure/replay/source-pairing and sizing rosters | 167 tests PASS in 12.768s |
| Original page module, pinned 167-rule static profile | NONPASS: seven B905 findings |
| Candidate page module, new test and execution runner, same static profile | PASS: zero findings, no suppressions |
| Syntax for those sources | PASS |
| Actual GPT-6.1 source/raw review | No concrete blocker found at the scoped checkpoint; no independent execution |

The runtime roster retained the original 60-second limit with five-second kill
grace, 2 GiB address-space and 512 MiB file limits, shared heavy-work lock,
read-only source and isolated home/network/PID namespace. Before/after source
maps match. Public product and test bytes are identical to the overlaid sources
used in that run. Publishing those bytes is not a new execution or a full-suite
pass. The frozen reference and failed baseline remain diagnostic evidence.

## Power of Ten adaptation and remaining limits

These are SIA adaptations, not quotations from Holzmann. P02 uses the initial
admitted roster length to bound yielded work; terminal mismatch is checked.
P05/P07 require a refusal for truncated or extended pin rosters and preserve
body errors. P09 retains explicit live iteration rather than silently replacing
caller-visible aliases with snapshots. P10 clears the seven findings in this
module under the pinned analysis profile; it does not establish zero warnings
throughout SIA or whole-system rule compliance.

Same-length replacement and ABA mutation are not detected by this helper. It
preserves live reads, with surrounding content and identity checks still
required. A caller that stops consuming a generator early has not established
roster equality; the changed validation loops consume it fully before success.
Native interpreter behavior and dynamic allocation remain assumptions. This
is not a SPARK proof, a fixed-allocation guarantee or hostile-interpreter
isolation. Current callback semantics and complete domain/resource gates stay
binding.

R05 stale admission remains FAILED. No original memo assertion, callback
requirement, resource cap or reuse guarantee is waived. The SDK, C/SPARK,
protected effects, installed continuity/recovery and release/marketplace gates
remain independent obligations. No merge, installation or release acceptance
follows from this scoped repair.

## Later terminal-deletion counterexample

The subsequent [bounded-traversal repair](INTAKE-BOUNDED-TRAVERSAL-20261024.md)
found that iterator exhaustion alone missed deletion of an already-yielded final
row. The earlier evidence above covers its original controls, not that terminal
case. Final cardinality checks now close the demonstrated edge case in all
three pairing helpers. New original failures and candidate evidence are retained;
same-length/ABA mutation and complete system bounds remain unproved.
