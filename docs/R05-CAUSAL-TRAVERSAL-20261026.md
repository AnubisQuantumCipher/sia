# R05 capture observation and rejected traversal experiment

Status: **TESTED at the stated scope; candidate NOT ADOPTED; R05 BOTH OPEN**.
This checkpoint retains diagnostic source and raw evidence. It changes no
production runtime. The baseline carrier is
`8ed2675d1bd9a67e55f4ee25a21ca3008c50bebe`; its executable source is unchanged
from the earlier `f330d3f31f55ab67df07112a966d703a9698b266` checkpoint.

## What the capture observation established

A bounded observer wrapped the original idle-capture test's actual capture call
before fixture setup. It retained exactly one capture entry and exit, string
hashes and lengths, traversal/caller associations, and Python call edges. The
receipt contains no captured string plaintext. The original test and assertions
were unchanged. Its nine observer controls passed, and the original case passed
in 35.916 instrumented seconds.

The successful observation retained 1,309 distinct string entries, 25,400
associations, 3,288 traversals, 2,360,909 string calls and 2,472 Python call edges,
without an invalid-capacity flag. Source bindings and tracked cleanup were
independently checked by GPT-6.1. These are observations of synthetic test data,
not total heap bounds, product latency, or proof that memoization is safe.

Caller associations distinguish capture work from fixture assertions and expose
repeated inputs. They do not establish a closed derivation that may be reused
across validations while preserving current owner callbacks, mutation visibility,
ordered accounting and first refusal. No general escaping cache was implemented.

The preceding observation reached its association capacity. Its controls and
original case passed, but its diagnostic result remains
**INVALID_PARTIAL_OBSERVATION**, with all raw output retained. Earlier unexecuted
observer revisions had missing-hook, online-capacity and keyword-argument metadata
defects; their source and dispositions remain in the archive. Passing the final
observer does not retroactively validate those revisions.

## Traversal experiment and complete fixed workload results

The private candidate inlines the existing frame step within JSON sizing while
retaining callback order, current owner reads, key/colon refusal ordering and
child selection. It explicitly releases the temporary key before traversing the
child. The private `take` method remains present, but sizing no longer dispatches
an override of that method. This compatibility limit is retained. The candidate
implements no cross-validation cache and cannot discharge the reuse requirement.

| Selection | Source | Methods | Raw unittest seconds | Result |
| --- | --- | ---: | ---: | --- |
| Original traversal controls plus differential cases | Candidate | 18 | 0.050 | PASS |
| Complete original delivery selection | Candidate | 17 | 104.964 | PASS |
| Complete original delivery selection | Fresh baseline | 17 | 99.598 | PASS |
| Complete original resident selection | Candidate | 12 | 81.360 | PASS |

All completed selections had zero failures, errors or skips. Delivery runs each
retained 20 exact nested-isolation fallback diagnostics; resident retained 11.
The outer executor provided the recorded private namespaces. All source hashes
and byte counts, tool bindings, raw output classifications, exit results and
tracked cleanup were independently checked. This is a review of retained runs,
not an independent rerun. Observer-loss custody remains **UNKNOWN**.

The delivery pair demonstrates no speed benefit. A single observation per
variant does not establish a causal slowdown either. The candidate is therefore
**NOT ADOPTED**, and this fixed experiment is closed. Further performance runs
for this candidate are not the next step. The old 60-second timing observations
remain visible; the operator removed engineering caps while retaining product
safety bounds, so those observations are not silently reinstated as policy.

The initial snapshot preparation failed before execution because it attempted
to replace a read-only copy. The next preflight found stale byte-count metadata
and a vacuous mutation-test trigger. Both failures remain retained. The successful
preparer selects the candidate before making the snapshot read-only, derives
both hashes and lengths, and the corrected mutation control asserts that its
mutation actually occurred and the appended value was traversed.

## Evidence and remaining acceptance

The [generated manifest](R05-CAUSAL-TRAVERSAL-EVIDENCE-20261026.json) binds the
[diagnostic archive](evidence/r05-causal-traversal-20261026-v1.tar.gz), including
candidate/baseline traversal source, observer revisions, raw runs, reviews,
preflight failures and packaging code. Its `--check` mode reproduces archive
and manifest bytes. The archive binds original full-source snapshots; it does
not reproduce every unchanged source file or provide a standalone execution
service. Original local paths and hashed host identities are retained.

No installation, service, firewall, provider, model-spending or iPad action was
performed by these runs. No release or marketplace acceptance follows.

The next existing critical-path work is the continuity execution/recovery join.
Creator-death tests already exist; another equivalent proxy test would not close
the actual observer-loss gap. A wrapper death loses its local lock and process
handles. A successor requires durable operation identity and independently
established prior-work termination before retrying. Native lifecycle extraction,
receiver selection, association persistence and end-to-end compaction tests also
remain open. A harness-generated context summary is not SIA automatic restoration.

Every A01-A24, G1-G6, C01-C14, P01-P10, R01-R46 and EP01-EP10 obligation remains.
R05 still requires meaningful expensive reuse together with fresh admission.
The earlier selected recovery proofs remain applicable only to their unchanged
source and declared assumptions. Neither those proofs nor these tests establish
whole-system assurance or avionics certification.
