# SDK cleanup regression and bounded successor result

**v6 is REJECTED for adoption. v7 remains INCOMPLETE after a full-suite timeout.**
The earlier v6 fixture pass remains a real test result; subsequent adversarial
evidence demonstrates that it did not establish the cleanup contract.

## Audit-hook regression

The v6 fast path reads the retirement helper's `__code__`. On the observed
CPython runtime this invokes the `object.__getattr__` audit event. An isolated
child installed a hook that denies only that exact helper/code lookup. Both
v6 checker and probe retried the lookup 8192 times, left occupied slots 0, 4096
and 8191 unchanged, retained the first 64 actual OSError objects, and set the
overflow indicator. The v4 baseline cleared all three slots with zero such
audit calls and zero recorded errors. The diagnostic exited zero because it
successfully reproduced this regression; it is a product failure, not a pass.

The retained CPython v3.14.7 funcobject.c source contains the corresponding
PySys_Audit call. That source supports the mechanism; it does not attest the
machine's interpreter build. The actual isolated observation is the local
behavioral evidence. See the [upstream implementation](https://github.com/python/cpython/blob/v3.14.7/Objects/funcobject.c).

No hook was installed in a production process. The earlier v6 archive remains
unchanged, including its 179-test pass and unresolved call-omission difference.
No fallback, audit waiver or omitted-error acceptance was adopted.

## All-call successor

v7 starts from v4 and preserves every retirement call. It stores the last
attempted index directly, calculating the next start once per guarded attempt.
This avoids per-cell increment arithmetic without code introspection or the
v6 no-op specialization. The original fixtures remain literal except required
ROOT relocation. Five finalizer controls remain; the candidate-specific v6
profiling control now requires every original call. Three additional synthetic
controls exercise first range failure, consumed-but-unyielded index failure,
and persistent range failure with bounded actual-error retention.

The targeted roster passed **26 tests in 11.342 seconds**. A separate audit-hook
control found zero code-access audit calls, no occupied retained slots and no
recorded errors in both v7 checker and probe. All source pins matched before
and after these runs. These are TESTED cases, not native allocation proofs.

The complete discovered suite then **timed out with exit 124** at the original
120-second work limit, while executing the seven-anchor distinctness test.
There is no complete unittest summary or full-suite pass. Source pins still
matched. The original one five-second termination grace and resource limits
were preserved. No unchanged retry or cap increase followed.

The fixed 256-sweep cost diagnostic recorded elapsed nanoseconds in order:
v4 145289039, v7 117242299, v7 112591545, v4 137557712. These measurements show
a local cost reduction in that workload; the full-suite timeout demonstrates
that this was insufficient for qualification. They are not worst-case bounds.

## Disposition and next evidence

Neither candidate is adopted, installed or authorized for observer-main/native
execution. The unchanged original SDK observations do not qualify these
changed sources. Guard-recording failure, arbitrary asynchronous interruption,
native allocation behavior and earlier-slot repopulation remain explicit
limitations. The original exact-site static exceptions remain visible; the
new audit control and runner passed the original strict profile without
diagnostics. No broader static-analysis waiver was introduced.

The next attempt requires a concrete source change with a preservation argument
for actual-error retention, callback order and all required cleanup effects,
plus bounded cost evidence. A green subset or a larger timeout cannot close
the full-suite requirement. R05, strict C/SPARK, protected runtime, actual
continuity, installed lifecycle and release/marketplace gates remain OPEN.

The [inventory](evidence/sdk-sweep-negative-results-20261024/inventory.json)
binds the [source and raw evidence](evidence/sdk-sweep-negative-results-20261024/snapshot.tar.gz).
Prior v4/v6 dependencies remain in the earlier immutable snapshots. These are
forensic archives, not portable execution bundles. Do not execute extracted
observer mains or reuse their historical output and filesystem identities.
