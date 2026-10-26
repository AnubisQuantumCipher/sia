# Nonrecursive page sizing: limited repair checkpoint

Status: **TESTED at the stated scope; R05 FAILED; release acceptance open**.
Base source is `28c2afed1570a59714891821dfa2888933b5d2e6`. The companion
JSON binds the exact changed bytes, executed source maps, commands, raw output,
failed variants and review. This change replaces recursive page-size traversal
in `bin/siaeventplan.py`; it does not change cache policy or resource ceilings.

## Preserved behavior and implementation

An explicit stack holds only active container ancestors, with each parent's
local remaining byte budget, iterator, accumulated size and depth. Dictionary
keys are sized before reading their current values. Ancestor registration still
precedes iterator construction. Shared noncyclic values are counted on each
occurrence; active cycles are refused. Native integer bit limits, scalar/type
refusals, delimiter accounting and the original depth checks are retained.

Frame ownership is registered with cleanup covering both constructor and
registration failures. Completion pops ownership before attempting removal.
The unwind helper attempts outer cleanups even if an inner cleanup raises,
preserving the exception precedence and context chain tested against the
original traversal. Its narrow BaseException handler propagates the failure;
it does not convert cancellation or interpreter exit into success. Native
BaseException context descriptors avoid new subclass attribute callbacks.

The traversal differential freezes the original `_size` body but shares the
current `_text_size` and `_refuse` helpers. It is not a completely independent
serializer. Serializer comparisons are separate, with the original stricter
integer-bit admission controls retained. The frozen recursive test reference
is diagnostic evidence, not production code or P01 compliance evidence.

## Results and failed attempts

| Check | Retained result |
| --- | --- |
| Final private focused traversal, differential, cleanup, ASCII and Unicode roster | 30 tests, PASS |
| Integrated original replay roster plus sizing controls | 161 tests in 33.073s; FAILED with the two existing stale-cache subtest failures |
| Original static profile on changed product, tests, reference and runner | NONPASS: same seven B905 product findings; no new findings or suppressions |
| Syntax of those files | PASS |
| Independent actual GPT-6.1 source/raw review | No further concrete blocker to a non-final checkpoint at the narrow scope; no independent execution |

The integrated run used the original 60-second deadline with five-second kill
grace, 2 GiB address-space and 512 MiB file ceilings, shared heavy-work lock,
read-only source, isolated home/network/PID namespace and fixed environment.
Before/after source maps match. The two failures are the intentionally retained
current-projector cache regression in legacy and compact capture formats.
The complete release roster, maximum-load behavior and hosted acceptance are
not established by this scoped run.

Negative evidence remains in the snapshot:

- Initial serializer expectations wrongly assumed the decimal representation
  could bypass the existing integer-bit bound. Three errors were corrected in
  the tests, without weakening the product bound.
- Constructing the iterator before ancestor registration changed callback
  ordering. The controlled mutation test failed; registration now comes first.
- A review found missing cleanup if frame registration allocation failed. The
  repaired implementation includes constructor and registration fault controls.
- v4 cleanup retried removals and skipped outer cleanup. Its new differential
  method had 14 failing subtests.
- v5 attempted all cleanup but lost an intermediate exception context. The
  focused roster retained two failing subtests.
- v6 used ordinary context attribute dispatch. A custom exception sentinel
  failed; v7 uses native descriptors and passes the sentinel.
- The first routine-span report matched an unrelated `__init__` by name.
  The qualified-class v2 report corrects that observation.

## Power of Ten adaptation and limits

These are SIA adaptations, not quotations from Holzmann. P01 benefits from
removing production recursion. For P02, each descent retains the original
finite local byte budget and depth check, and each unwind consumes a frame.
The size walk accounts for each visited value or refuses before its budget
is exhausted. This is a review argument under native-runtime assumptions,
not a SPARK termination proof or worst-case execution-time certificate.
Negative supplied depth remains accepted as before, so ancestry storage cannot
be described as universally bounded by the default depth limit. Supplied
callbacks and overloaded optional arguments do not acquire proved bounds.

P03 remains open for Python allocation: frames, sets, exceptions, integers and
the interpreter allocate dynamically. The wide-input traced-scratch control
does not prove process RSS, total-OOM cleanup, allocation success or hostile
interpreter isolation. P04's changed routines are short; their qualified source
spans are retained. P05/P07 are exercised by exact-limit, refusal-order,
cleanup and independent-serializer controls. P06/P09 keep frame state local
and native-container traversal explicit; Python's mutable runtime remains an
assumption. P08 adds no source-generation or conditional-build mechanism.
P10 remains NONPASS until the existing static findings and complete gates close.
No deviation has been accepted as a new policy or hidden behind this checkpoint.

## Performance observation, not a speed claim

The same nonempty retained fixture was profiled once for each source. These
are cProfile observations with cumulative process peak RSS, not paired latency
statistics, maximum-load qualification or a stable performance improvement.

| Format | Original fresh validation ns | Candidate fresh validation ns |
| --- | ---: | ---: |
| Legacy, 75209 native bytes | 133279431 | 135010937 |
| Compact, 82613 native bytes | 159274329 | 136995508 |

Raw profiles retain each function's own and inclusive time. Candidate `_size`
has no recursive calls, but its inclusive measured cost is higher in both
samples. Do not present this change as a cache optimization or a speed win.
R05 still requires current policy and callback admission on every call while
preserving the original combined-validator reuse oracle and resource ceilings.

All original assurance, SPARK, Linux enforcement, continuity, installed
lifecycle, recovery, release and exact-SHA marketplace gates remain binding.
Nothing here establishes universal compaction safety, cognitive improvement,
whole-system formal verification or avionics certification.
