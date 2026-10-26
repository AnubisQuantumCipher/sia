# Complete declared-project flow analysis

Status: **FLOW_SCOPE_PASS_NO_DEDUCTIVE_PROOF**. Exact tested source is
`ddfe2690256a475b5164a6489efa85acca36a9d8`. This checkpoint changes evidence and
documentation only; it is not installed acceptance or a release.

GNATprove's report lists all 50 declared Ada units of `spark/sia_assurance.gpr`,
with complete coverage of the reported SPARK entities. Eleven test/support units
explicitly use `SPARK_Mode => Off` and report zero entities; their bodies were
not flow-analyzed or proved. The summary reports 1,522 flow checks:
data dependencies, flow dependencies, initialization and termination. There are
no reported errors, warnings, justified checks or `pragma Assume` records.
The exact invocation uses `-U --mode=flow --assumptions --no-inlining
--memlimit=512 --timeout=10 -j1` with the unchanged strict project configuration.

Every unit explicitly records that deductive proof was omitted because flow
mode was requested. This result establishes neither run-time safety nor
functional contracts. Separate transport/allocation projects are outside this
project's declared source scope. Earlier selected recovery proofs and runtime
tests remain separate evidence, not a whole-project deductive proof.

The non-SPARK units are `continuity_approval_test_support`,
`continuity_approval_tests`, `continuity_descriptor_test_support`,
`continuity_descriptor_tests`, `pack_manifest_tests`,
`pack_plan_wire_test_support`, `pack_plan_wire_tests`, `pack_proposal_probe`,
`pack_proposal_tests`, `pack_retirement_test_support` and `pack_retirement_tests`.
Their zero-entity report rows are scope exclusions, not coverage passes. The
original archive retains their source declarations and raw `.spark` records.

All 79 Ada/GPR/ADC input files match the final selected recovery-proof snapshot
and the published source. Source, execution configuration and tool identities
were checked before and after execution. The ordinary root observer established
private namespaces, then ran the fixed UID1000 payload without capabilities.
The observed exit was zero; tracked launcher, namespace init and leader were
terminal and reaped without cleanup signals or errors. Actual GPT-6.1 independently
read the raw results, unit coverage and bindings; it did not rerun the campaign.

The first preparation failed before source copying because its roster comparison
included non-Ada files. The next invocation failed during bwrap setup: two empty
mount-point directories were absent. GNATprove was not admitted in that attempt.
Both failures are retained. The exact failed setup was reconciled using the
unchanged durable storage primitive after 33 controls passed. Separate root
readback preserved its original pending inode and bytes under the retired name.
That disposition records failed setup, not successful work or general custody.
The corrected invocation adds only the two empty mount points.

At the original flow readback, this successful invocation had its own unresolved
pending intent. The later [exact completed-flow disposition](FLOW-DISPOSITION-20261026.md)
reconciled that invocation and preserved its original pending inode and bytes.
Neither the passing result nor its retirement authorizes replay or a successor.
A later proof invocation has separate admission and operation state; it must not
inherit this earlier pending-absence observation. Whole-project deductive evidence
still requires its own complete result under the existing strict settings, with
failures preserved. The [manifest](PROJECT-FLOW-EVIDENCE-20261026.json) and
[raw archive](evidence/project-flow-20261026-v1.tar.gz) bind the source, commands,
reports, failed attempts, reconciliation controls and independent readback.

Native compaction dispatch remains refused. Inspection found no justified new
native compiler attempt: a proposed flat polling loop repeats a historical
structural idea whose complete equivalence and withdrawn-restoration provenance
remain unresolved. The retained lifecycle recorder reserialized notifications;
those files cannot establish original wire bytes. No native extractor or custody
gate was enabled on that basis.

All original A/G/C/P/R/EP obligations, including R05 BOTH, remain. Native custody,
original-record and receiver joins, actual repeated compaction, the Astra judge,
protected runtime authority, installed composition, release and live marketplace
acceptance are open. This flow result is not whole-system assurance or avionics
certification.
