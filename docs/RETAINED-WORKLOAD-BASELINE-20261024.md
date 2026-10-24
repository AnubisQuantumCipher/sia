# Retained validation: larger synthetic failing baseline

Status: **R05 FAILED; diagnostic workload established; no cache repair**.
Source is `f1bdc848971bfcd39a4c9255afffee73eca59ca4`. Production code and the
original memo test are unchanged by this checkpoint.

## Historical claim and measured scope

Commit `ec713cacd2ff77905996e55b9f245bce88897b55` reports a maintainer capture
of 12.7 MB with 1,046 events, roughly one second for its identity digest and
78 seconds for one validation. That commit does not include the measurement
artifact. Those figures remain historical commit-reported observations.

The new workload explicitly configures 104 synthetic custom sources with ten
lines each, plus the existing signed AEGIS fixture. It runs the real private
collector, page-plan, closure and retained-validation paths. Every custom
source's returned count must match its requested count. The resulting batch
contains **1,046 events across 105 sources**, and is **3,771,273 bytes** in both
completed experiments. File identities and native metadata differ between runs;
the exact retained images and their hashes are preserved separately.

This is not the historical workload: its image is smaller, its source
composition differs, and it exercises legacy batch validation rather than a
large compact capture. It does not replace the missing historical artifact,
maximum-load qualification or either format's original acceptance obligations.

## Results and failures

| Experiment | Retained outcome |
| --- | --- |
| v1: two large custom files | FAILED requested event-count assertion. Each custom collector emits ten individual events plus an overflow summary; the batch had 28 events and 144,588 bytes. No validation profile ran. |
| v2: 104 new sources without initial cursors | FAILED requested event-count assertion. The actual collectors established EOF baselines, yielding only the six native fixture events and a 261,796-byte batch. No validation profile ran. |
| v3: explicit initial zero cursors, following the original fixture convention | PASS diagnostic execution, exit 0; exact 1,046-event roster and unchanged inputs. Total process observation: 21,478,389,159 ns. |
| v3: profiled fresh `_validate_batch_image` | 8,330,086,550 ns; reported process peak RSS 175,880 KiB. This call excludes the public wrapper's initial identity work. |
| v4: unprofiled complete public `validate_batch`, cold | Accepted; 2,354,794,990 ns. Includes current wrapper work, validation and memo insertion. |
| v4: same public call, warm | Accepted; 156,219,385 ns. |
| v4: warm call after lowering current source capacity | **Incorrectly accepted**; 149,623,277 ns. |
| v4: cleared-cache call under that same changed capacity | Refused with `source-catalog-capacity`; 243,090,131 ns. |
| v4 whole diagnostic | **FAILED_STALE_ADMISSION**, process exit 1; total 15,740,750,901 ns, unchanged inputs. |

The v1 count addition returned JACKAL `status=exact parsed=6+11+11 exact=28`.
That arithmetic is outside the Lean certificate chain and proves no code property.

The lowered limit is a negative control, not a product configuration change.
The v4 probe requires normal cold/warm acceptance and effective cold refusal
before it compares changed-policy outcomes. It deliberately exits unsuccessfully
for the demonstrated mismatch; the failure is not an expected-failure marker.

All runs retain the original 60-second deadline and five-second kill grace,
2 GiB address-space limit, 512 MiB file limit, shared heavy-work lock and
read-only source with isolated home, network and PID namespace. Corpus, memo,
cursors and pending-rename fixture snapshots remain unchanged after completed
capture/validation. No installed source or provider is used. The timing samples
are individual observations; they establish no latency bound, WCET or speedup.

## Cost frontier and next implementation

The v3 profile records 3.764997858 inclusive seconds in page `_size`,
1.997430431 in source `_json_size` and 1.712923809 in page `_text_size`.
These times overlap and must not be added. The profile identifies repeated
native sizing as a useful experiment target; it does not justify bypassing it.

The next bounded experiment may reuse an owner-independent string-sizing
computation keyed by exact immutable text and complete encoding context. It
must preserve current type/limit admission, public helper seams, callback/read/
refusal order, mutable-container traversal, allocation limits and invalid-input
behavior. Storage, lookup, retained text, eviction and correction/deletion
semantics belong in the cost and privacy assessment. A smaller helper cache is
not automatically the required expensive-derivation reuse boundary.

The user delegated the pending instrumentation decision. The owner selected
conditional reconciliation of the combined-function call-count assertion only
after a useful closed derivation is implemented and qualified. The original
fixture, changed-image and VERSION controls, detached results, current-policy
refusals, full workload and resource ceilings remain required. No original
assertion or cache has changed. A renamed validator, partial dependency key,
no-cache adoption or inexpensive-helper oracle does not satisfy this decision.

## Evidence and reproducibility

Companion volumes A and B retain exact probe/runner source, before/after input
maps, raw stdout/stderr, profiles, source input text, failed preparations and
source/raw reviews. Each volume obeys the existing 128-member, 2 MiB per-member
and 8 MiB total/raw/encoded limits. Large images are split into 1 MiB pieces;
ordered reconstruction is checked against the original complete byte count and
SHA-256. Two volumes keep each artifact within those limits; no execution cap
has changed. The builder's `--check` reproduces both volumes byte for byte.

The pinned 167-rule profile reports zero findings for the executed v3/v4 probe
and runner sources; the evidence builder also passes. Actual GPT-6.1 source/raw
review found no blocker to retaining these narrowly labeled diagnostics. There
was no independent execution. Native interpreter, fixture and OS behavior
remain assumptions; this is no formal proof or whole-system assurance claim.

Reproduction uses the retained isolated runner and the exact named source.
Its paths identify this machine; review and deliberately map them to an isolated
checkout/output directory on another host. Never execute decoded artifacts
merely because a manifest hash matches. Native identities make new capture
bytes host/run-specific; compare the stated contracts and retain new hashes.

Full R05, original SPARK/SDK/C/Linux/continuity, installed recovery, release and
marketplace gates remain open. These measurements authorize no merge or release.
