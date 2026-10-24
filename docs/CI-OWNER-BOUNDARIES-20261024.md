# Facade import and test-home boundary repair

Status: **TESTED at the scoped original controls; static NONPASS and system acceptance INCOMPLETE**.

On base `fef55575abfa025af2bd143d741241df0bab9249`, the original facade-import and runtime-test isolation checks both failed. `siathought` imported `os` and `siaqueue` directly although the child contract requires owner-supplied dependencies. The plugin registration fixture did not activate the repository's isolated home before handling runtime source.

The repair declares the two unbound dependency slots and lets normal `sialib` binding supply them. It leaves every function body and partial-bind behavior unchanged. Initial unbound use fails, but a later partial binding can retain earlier dependencies; this is not a complete-owner or fail-closed rebinding repair. The plugin fixture now imports `sia_test_home` before source handling and creates its temporary directory under `ISOLATED_HOME`. Original cases, assertions and child timeouts remain unchanged.

## Evidence

The [exact-source manifest](CI-OWNER-BOUNDARIES-20261024.json) includes commands, source maps, raw test outcomes, full static diagnostics, retained-artifact hashes and independent review. Original base failures remain visible. The first removal-only candidate passed 49 tests but exposed additional undefined dependency diagnostics. The final explicit-slot candidate passed the same 49 tests in 34.056 seconds; integrated execution passed 49 in 34.252 seconds. Both exited 0 with unchanged observed source maps under the original 120-second envelope and resource limits.

Original strict 167-rule static analysis remains **NONPASS**: the final product has the same 535 diagnostic-signature multiset as its original; the test has zero diagnostics. Syntax compilation passed without executing source. No rules, warnings or failure records were suppressed. This checkpoint does not waive the static gate. The actual GPT-6.1 reviewer inspected final source and raw evidence and found no concrete blocker to this explicitly incomplete draft checkpoint; the reviewer did not execute the tests independently.

## Remaining acceptance

R05 policy-sensitive admission caching, full CI, outstanding SPARK proofs, Linux enforcement and lifecycle qualification, actual harness continuity, recovery and retrieval evaluation, and all original A/G/C/P/R obligations remain open. The scoped evidence does not qualify installed behavior or authorize release. No main merge, installation, tag, release or marketplace change is part of this checkpoint. The seven inherited unfinished paths remain preserved.
