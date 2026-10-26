# Replay-record element admission

Status: **TESTED scoped repair; full assurance INCOMPLETE.** Exact source hashes,
commands, negative results and raw outputs are retained in the
[evidence receipt](REPLAY-RECORD-TYPES-20261025.json).

Malformed replay `links` or `tags` could reach `set` and `sorted` before their
elements were admitted as strings. Nested JSON lists/dictionaries raised an
incidental `TypeError`; an unadmitted Python object's hash hook could run.
The decoder now checks element types after the original list/count checks and
before hashing or comparison. Invalid records deliberately raise the existing
`ValueError("event replay record is invalid")`. The source-batch wrapper keeps
its `source-event-record` refusal. Ordinary string collections still undergo
uniqueness, order, Event reconstruction, normalization and identity checks.

The unchanged baseline ran six added methods, with four failures and fourteen
subtest errors; other controls already passed. The repaired composition passed
65 tests in9.107s, including source binding, late alias mutation, interleaving
and refusal order. The original16-test current-policy/reuse roster completed
in51.260s with the sole original R05 reuse-count failure. Its later mutation and
VERSION assertions were not reached and receive no credit. Nothing was skipped
or marked expected-failure. Source endpoint hashes stayed unchanged in each run.

The frozen167-rule Ruff profile passes for the new test, runner and evidence
builder. Full `sialib.py` analysis fails with154 findings, identical before and
after; these are retained unresolved findings, not accepted deviations or a
zero-warning claim. Actual GPT-6.1 reviewed source and raw results without
independent execution. The archive builder reproduces the public artifacts.

This repairs checked-input handling under the Power of Ten baseline. It does
not establish exact-type admission for Python subclasses, hostile-process
isolation, runtime allocation bounds, loaded-code custody, semantic source
truth or formal proof. It is neither a performance optimization nor a cache.
R05 still requires both useful expensive reuse and fresh current-policy checks.
All existing native/SPARK/SDK, complete workload, compaction lifecycle, recovery,
installed, final-composition and release/marketplace gates remain mandatory.
