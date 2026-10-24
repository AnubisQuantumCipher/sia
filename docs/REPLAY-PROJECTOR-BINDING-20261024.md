# Replay projector source binding

Status: **scoped TESTED; R05 and whole-system acceptance remain INCOMPLETE**.

Replay's existing final validation rejects content/hash/version disagreements. Five original probes confirmed those refusals; an initial source-local assessment that overlooked that check was corrected. The separate source-binding defect was reproduced with self-consistent substitutions: an owner projector could invent a historical before-image, update its hashes, and have it accepted as a retained page version. A later invocation could also alter an earlier returned dictionary consistently before final validation.

The repair compares each projector result with the already-admitted page bytes, subject, origin and digest. It checks the exact six native string fields against a canonical version identity. It then preserves the private version-map key through legacy and compact output assembly. Later internally consistent identity changes refuse; existing live validation still checks internal consistency. Existing callback invocation, collision checks, late-mutation refusal and final public detachment remain in the runtime path.

## Exact-source verification

The [companion JSON](REPLAY-PROJECTOR-BINDING-20261024.json) binds the base commit, changed code, original inventories, exact commands, raw outputs, failed variants and independent review. Gzip/base64 members preserve their byte lengths and SHA-256 digests.

- Original self-consistent historical substitution: FAILED as intended because the baseline accepted an invented page. Original five inconsistent-output probes: PASS, all refused through the existing page-content-or-origin-version-binding check.
- Initial detached-result candidate: FAILED one retained original late-mutation oracle. It is not adopted. Its proposed immediate-helper-detachment expectation is withdrawn; the original public-boundary refusal and detachment requirements remain.
- Intermediate candidate: original and focused 103 checks PASS, but the added cross-invocation case then FAILED. This result is retained and is not final acceptance.
- Final candidate: 126 checks PASS in 29.449 seconds within the unchanged 60-second deadline, exit 0; all observed sources unchanged. Includes original page planning, replay, source capture, memo, checkpoint bootstrap/delta, five mismatch probes, and new precise-refusal controls for both actual legacy and compact paths.
- Integrated checkout: 126 checks PASS in 28.978 seconds, exit 0 under the same 60-second deadline; observed source unchanged. Actual GPT-6.1 source/raw review found no concrete blocker to an explicitly incomplete checkpoint; it was not independent execution.
- Strict original 167-rule analysis remains NONPASS: ten product diagnostics remain, versus eleven in the three original product files. The sole removed diagnostic was the formerly unused JSON import, now used for canonical identity. No new diagnostics; new tests zero. Syntax compilation passed. No suppression or waiver.

## Boundaries and remaining work

These are Python runtime checks, not SPARK proofs. The helper is internal and requires the existing page-shape, raw-size and raw-digest admission. Native Python hashing/serialization, collision resistance and the admitted owner decoding/hash boundaries remain trusted. The returned callback mapping remains visible to the original late-mutation guards until final public detachment; arbitrary hostile interpreter mutation, frame inspection and ABA isolation are not proved. Allocation and execution are subject to the existing admitted ceilings, without a fixed-allocation Python or maximum-load/WCET claim.

This closes the reproduced projector cases under the retained tests. It does not repair the two outer policy-sensitive admission caches, establish a closed reusable reconstruction, or qualify maximum-load performance. The original R05 reuse oracle, current-callback requirements and all resource ceilings remain unchanged. No full-harness continuity, installed path, complete proof, recovery campaign, main merge, release or marketplace acceptance is claimed. All original A01-A24, G1-G6, C01-C14, P01-P10 and R01-R46 obligations remain.
