# SDK v8 and continuity supervisor: incomplete qualification

**No executable adoption, install, merge or release is established here.**
This checkpoint retains current source and both positive and negative results.
The previous immutable v6/v7 evidence remains unchanged.

## SDK cleanup successor

v8 retains every retirement-helper call and mutable helper lookup. The loop
records its last attempted index in a finally block, preserving continuation
after a captured cell failure without per-cell index bookkeeping. Original
test bodies are unchanged apart from required source-root relocation. Neither
helper-code introspection nor an empty-slot fast path is reintroduced.

The targeted controls passed 26 tests in 10.821 seconds. The isolated audit
control observed no helper-code audit accesses, occupied leftovers, recorded
errors or overflow. Source pins remained unchanged. These results do not prove
arbitrary asynchronous-interruption behavior or native allocation safety.

Full discovery still exited **124 at the original 120-second work limit**,
without a complete unittest summary. It is FAILED at that gate. The single
five-second termination grace and other resource limits were unchanged. Strict
analysis of the full source roster retains the three previously recorded
BLE001 sites; this is not a zero-warning source. The new diagnostic sources
and runners have zero findings under the retained strict rule profile.

## Current cost observations

A separate per-method diagnostic discovered 182 tests and recorded 90 completed
method intervals before exit 124 at the same cap. Its final unmatched start
identifies an interrupted IO census method, not the cause of the timeout.
Reporting overhead is included; it is not a controlled comparison against the
uninstrumented full run.

A focused cProfile run of the complete persistent-late-key frontier method
exited 124 at its 30-second diagnostic cap without producing a profile report.
That failure yields no function-level cost attribution.

A lower-overhead diagnostic temporarily wrapped five method boundaries while
calling the original bodies and retaining every case. It passed the selected
test in 8.014 seconds. The raw inclusive observations were:

| Boundary | Calls | Inclusive elapsed nanoseconds |
| --- | ---: | ---: |
| Harness construction | 72 | 2218277392 |
| Harness positive validation | 72 | 4425072819 |
| Harness close | 143 | 124430832 |
| Late-key case | 72 | 1243712497 |
| Checker scratch clear | 12468 | 6352340365 |

These are overlapping, instrumented intervals: do not sum them or infer a
worst-case bound. They support investigating scratch clearing on this current
source. They do not justify omitting cell calls, callbacks, positive controls
or original fixtures. No unchanged full-suite retry or raised cap followed.

## Continuity supervisor controls

Worker source at `fac4b86d79daa4a481e908557ed1fa601923c94d` introduces an
absolute terminal deadline, bounded streaming inventory and retained kernel
process handles. Owner execution of its 18 injected controls passed in 0.016
seconds with recorded source hashes and metadata unchanged. The run preserved
the 30-second limit, one five-second grace, resource envelope and shared lock.

Process creation, identity observations, signals and reaping are mocked in
these controls. No configured preflight, formatter or full adapter suite was
dispatched. Passing the failed-receipt control means the expected failure was
recognized; it does not establish a successful receipt write.

Real dispatch remains blocked by three concrete source gaps:

1. Validate the SIGCHLD premise before relying on an unreaped child's numeric
   PID; exclusive reaping remains an explicit environmental assumption.
2. Preserve primary revalidation failure and unresolved handle state when a
   handle-close operation also fails.
3. Attempt iterator and descriptor cleanup independently, preserving the
   primary failure and close failures without blind retries of ambiguous closes.

The retained owner disposition specifies additive failure controls and keeps
the existing adapter/provider/formatter sources frozen. Actual GPT-6.1 review
of source and raw supervisor/method-timing evidence is not independent test
execution. Real cleanup, import qualification and continuity remain unproved.

## Evidence and remaining obligations

The [inventory](evidence/sdk-v8-supervisor-controls-20261024/inventory.json)
binds the [source and raw results](evidence/sdk-v8-supervisor-controls-20261024/snapshot.tar.gz).
The archive is forensic, not a portable execution bundle: historical absolute
paths, filesystem identities and output locations must not be reused as a new
execution grant. Earlier immutable archives supply the historical dependencies.

The SDK full gate, R05 policy-sensitive cache validity, strict C/SPARK work,
protected process lifetime and effects, actual compaction/recovery, installed
lifecycle, release and exact-SHA marketplace publication remain OPEN. These
results are neither whole-system assurance nor avionics certification.
