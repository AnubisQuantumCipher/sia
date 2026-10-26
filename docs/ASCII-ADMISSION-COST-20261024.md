# Current-admission cost: ASCII sizing

Status: **scoped TESTED; R05 remains FAILED and system acceptance INCOMPLETE**.

Fresh validation's retained profile identified repeated text sizing as a major cost. After the existing exact-string and current-capacity checks, `siaeventplan._text_size` now returns the admitted ASCII character count when UTF-8 JSON requires no escaping. Raw ASCII text likewise needs no encoding. Quoted strings containing quote, backslash or control characters use the original path; DEL remains literal in UTF-8 JSON. Unicode and surrogate handling, bounded scratch, all limits and original refusal behavior remain. This adds no retained cache and skips no owner callback or current policy check.

## Exact-source evidence

The [portable evidence manifest](ASCII-ADMISSION-COST-20261024.json) binds the base commit, changed source, commands and original source inventories. Its gzip/base64 members preserve raw receipts, profiles, source variants, test output, static failures and independent review; each member's decoded byte length and SHA-256 were verified.

- Byte-size/Unicode roster: 21 tests PASS in 0.319 seconds, exit 0; exhaustive ASCII character/serializer controls, exact and one-short capacities, chunk boundaries, Unicode fallback and non-builtin refusal. The initial read-only mount failure happened before tests and remains retained.
- Integrated original page/intake/capture/reuse roster: 88 tests PASS in 28.635 seconds, exit 0. Original cases/assertions and the 60-second deadline remain unchanged.
- Original strict 167-rule static analysis remains NONPASS: eight product diagnostics have unchanged signatures; new test diagnostics are zero. Syntax compilation passed without executing source. No suppression or waiver.
- Actual GPT-6.1 source/raw review found no concrete blocker to this optimization under the scoped regression gates. It was not independent execution.

Observed source hashes were unchanged during each recorded run. These checks do not establish fixed-allocation Python behavior, WCET or full Power-of-Ten compliance.

## R05 experiment and remaining failure

Both profile runs used the same small private fixture. Fresh legacy validation measured 219569920 ns on the base and 116618648 ns on the candidate; compact validation measured 93114167 ns and 86061498 ns respectively. These are single cProfile observations, not a general speedup or maximum-load guarantee.

A separate private experiment bypassed the two outer admission caches on the current source plus this optimization. The original full 14-method roster completed in 53.557 seconds at its unchanged 60-second deadline, but FAILED its original reuse oracle: a repeated image invoked the combined validator twice. Policy-change controls passed, including changed decoder, source/event limits, nested policy and callbacks with changed closure/global state. The prior experiment's timeout remains historical evidence, not erased by this result.

The no-cache variant is NOT adopted. The integrated product still has its existing R05 cache defect. This result makes the next obligation more precise: retain always-current admission while establishing a genuinely closed reusable computation and preserving the original reuse/performance requirement. Renaming the combined validator or broadening its partial key would not satisfy that obligation. Full-capacity execution remains unqualified.

All original A01-A24, G1-G6, C01-C14, P01-P10 and R01-R46 obligations remain. Required proofs, Linux process/custody enforcement, actual harness continuity, installed lifecycle, held-out retrieval, recovery, CI and release/marketplace gates remain open. No main merge, installation, tag or release is claimed here.
