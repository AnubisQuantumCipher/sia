# R05 UTF-8 pool: tested experiment, not a performance repair

Status: **TESTED component controls; NOT ADOPTED; R05 BOTH OPEN**.
Baseline source is `f330d3f31f55ab67df07112a966d703a9698b266`.
The candidate production files exist only inside the evidence archive; this
checkpoint changes no runtime behavior and retires no requirement.

The private candidate reuses exact byte-to-UTF-8 derivations while continuing
current validation, owner reads, policy callbacks and projector checks. It does
not reuse successful admission. A fixed pool accounts for building, retained
and pinned retired memo slots together. Stale generations cannot borrow reused
slots; clear prevents late publication; capacity exhaustion falls back to fresh
uncached validation. Projector aliases and the original cold seam are preserved.

The implementation declares eight slots, 64 entries per memo and a 1-MiB shallow
payload charge per memo. These are explicit implementation limits, not a proof
of total interpreter memory or physical plaintext erasure. Idle-slot selection
also does not guarantee retention of eight different serial batches.

## Executed evidence

All runs used read-only source snapshots, disposable HOME/tmp/cache/output,
disabled network and the unchanged root namespace/cleanup observer followed by
a UID1000 payload with no capabilities and no-new-privileges. Tracked terminal
cleanup and source/tool identities were verified. Observer-loss custody remains
UNKNOWN. No installation, service, firewall or provider changes occurred.

| Selection | Source | Tests | Raw unittest seconds | Outcome |
| --- | --- | ---: | ---: | --- |
| Fixed-pool failure controls | Candidate | 11 | 2.601 | PASS |
| Complete retained regression selection plus new controls | Candidate | 108 | 99.084 | PASS |
| Complete original delivery selection | Baseline | 17 | 100.714 | PASS; historical timing target missed |
| Complete original delivery selection | Candidate | 17 | 112.188 | PASS; historical timing target missed |
| Complete original resident selection | Baseline | 12 | 93.209 | PASS; historical timing target missed |
| Complete original resident selection | Candidate | 12 | 97.143 | PASS; historical timing target missed |

There were no test failures or skips in these completed runs. Original discovery
multiplicity, including a duplicated imported test, was retained. Exact nested
isolation fallback diagnostics remain in the raw logs; the outer executor still
provided its recorded private namespaces. Actual GPT-6.1 independently inspected
the source and retained results, without independently rerunning them.

The user explicitly removed engineering time/storage caps while retaining
product safety bounds. These complete observations therefore use the current
execution policy. They do not retroactively pass the historical timed runs or
establish acceptance under their former resource envelope. All four full-workload
observations miss the historical 60-second timing target. Single observations
establish neither reproducible slowdown nor material benefit.

The focused controls cover overflow without another memo, clear during building,
late publication, stale copied scopes, a real paused projector during revocation,
second-consumer fallback, final generation increment/exhaustion, hostile keys
against a populated slot, decode/hash/projector exceptions and full-validation
fallback masking an inherited memo. Existing reuse, fresh-policy, owner-trace,
alias and refusal-order tests remain unchanged.

## Current causal evidence and disposition

The unchanged historical profiler was refreshed on the current baseline and the
original genuine idle-capture case. That case passed in 24.195 profiled seconds.
The retained table contains 2,127 function rows. Its own-time observations include
`_count_ascii_json_string`: 4,461,184 calls / 3.29224246 seconds; sourcebatch
`_json_size`: 4,772 calls / 2.199154485 seconds; all built-in bytes decoding:
2,245 calls / 0.003314819 seconds. Inclusive costs overlap and must not be added.
The profile includes fixture preparation and assertions and changes execution
cost; it is not a product-operation latency or worst-case bound.

These observations do not justify adopting UTF-8 memoization as the required
expensive-work reuse. Further lifecycle integration of this candidate is deferred.
The next bounded observation must identify repeated closed derivations within
the genuine capture phase, retaining caller/boundary associations without plaintext
in the receipt. Flat totals alone do not justify skipping live-container traversal,
current owner serializers, ordered budget callbacks or their first refusals.

The source-backed lifecycle review also found that managed restore's exclusive
lease does not cover every direct library cache holder. A truthful purge must
wait for pinned readers, cover all participating processes and avoid a resident
trying to upgrade its own shared lifecycle lease synchronously. No such complete
integration was implemented or qualified by these runs.

## Failures, limits and retained artifacts

The first static pass found cleanup-variable and hostile-fixture hash-policy
diagnostics. They were repaired without suppression. The first regression audit
incorrectly collapsed duplicate test identifiers; it failed closed and remains
retained. The corrected auditor compares exact multiplicities and classified
stdout records; no product test was rerun or omitted to obtain a pass. The initial
static test variant was not separately hash-frozen, a retained evidence limit.
Inherited oversized Python routines remain explicit Power-of-Ten gaps.

The [generated manifest](R05-UTF8-POOL-EVIDENCE-20261026.json) binds the candidate
and baseline source, tests, execution configs, raw results, audits, reviews and
failure evidence in the [archive](evidence/r05-utf8-pool-20261026-v1.tar.gz).
Its generator has a byte-reproduction check. Configs retain original local paths
and hashed machine identifiers; this is not a standalone execution service.

All A01-A24, G1-G6, C01-C14, P01-P10, R01-R46 and EP01-EP10 obligations remain.
R05 BOTH still requires meaningful expensive reuse and fresh admission together.
Complete custody, compaction continuity, the Astra judge, installed composition,
release and marketplace acceptance remain open. Passing these selected controls
is neither whole-system assurance nor avionics certification.
