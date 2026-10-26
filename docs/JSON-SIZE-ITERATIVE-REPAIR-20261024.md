# Iterative source-batch JSON admission

The source-batch byte counter previously used one Python call frame for each
nested value. Valid data near its declared depth limit could therefore encounter
an unrelated interpreter recursion limit before byte admission completed.
The replacement uses explicit ancestry frames and retains the existing depth,
cycle, exact-type, Unicode, integer, nonfinite-number and byte-capacity refusals.
It does not change serialization, authority, caching, capture or publication APIs.

The traversal retains dictionary values before sizing their keys, preserving
the original callback order and native iterator behavior. Shared noncyclic
containers remain valid. Frames grow with ancestry, not container width.
This is a Power-of-Ten rule 1 improvement; Python allocation, imported helpers,
dynamic runtime behavior and wall-clock bounds remain unproved. It is not a
claim of fixed-memory execution or complete Power-of-Ten compliance.

## Evidence

The [receipt](JSON-SIZE-ITERATIVE-REPAIR-20261024.json) retains exact source hashes,
commands, raw output, failures, static findings and source-stability checks.
The complete previous source module is retained as
`tests/fixtures/json-size-recursive-baseline.py`, used only by differential tests.
It matches the parent revision's source bytes. Original ASCII/Unicode and
capture/epoch tests are unchanged.

* Initial isolated sizing diagnostic: 21 tests passed in 0.099 seconds.
* Original capture/epoch/sizing composition: 36 tests passed in 4.132 seconds.
* First integrated roster: 44 tests, one failure in 4.102 seconds. The test used
  a fixed global recursion limit and incorrectly assumed the same harness stack
  depth as the first diagnostic. The old witness and raw failure remain retained.
* Corrected integrated roster: 44 tests passed in 4.911 seconds. The witness now
  measures the bounded current harness stack and sets a relative remaining call
  allowance. It still requires the original to raise RecursionError and the
  unchanged iterative implementation to return the serializer's byte count for
  the same input. No original data case or assertion was removed.

The integrated run used an isolated home, read-only source, a private PID and
network namespace, the nonblocking shared lock and the existing resource limits.
Source hashes remained unchanged. This is synthetic fixture evidence; it does
not qualify production collectors, a native manager, installed paths or durability.

Strict analysis remains **NONPASS** at seven pre-existing B905 sites outside the
changed code. Their exact counterparts also appear in the historical fixture.
The new functions and final test introduce no findings under the retained strict
profile. Initial test lint findings and their correction remain in the receipt;
no warning suppression or policy exception was added.

Actual GPT-6.1 source and raw-result review is separate from owner execution;
it is not independent test execution. This is a non-final source checkpoint on
the existing assurance carrier, not permission to merge, install or release.
Full project analysis/proof, R05 cache validity, SDK and credential-preserving
job lifetime, protected runtime, actual continuity/recovery, installed lifecycle,
release and marketplace gates remain open.
