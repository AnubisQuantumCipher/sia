# Ordinary execution recovery latch — 2026-10-26

TESTED / INCOMPLETE RECOVERY. The private engineering wrapper now records an
unresolved operation in one shared ledger before launching work. Acquiring the
heavy lock does not bypass a pending record. A normal actual-wrapper run passed
all 37 selected methods; a fresh-output invocation then refused before launch,
preserving the first intent byte for byte. This is a refusal mechanism, not a
complete recovery or safe-successor protocol, and it is not installed SIA behavior.

## Enforcement and scope

The candidate checks fixed ancestry, the provisioned directory identity and an
epoch binding while holding the existing heavy lock. It creates `pending.json`
exclusively, writes the intent, synchronizes file and directory, rechecks directory
identity and checks closes before entering `execute`. An existing record always
refuses, including empty, malformed or apparently completed records. Changing the
output directory, source revision or boot binding does not clear a pending record.

The intent binds the execution manifest, source revision, host/boot, epoch, heavy
lock and output directory. The execution manifest in turn binds configuration,
wrapper, helpers and tool/source inventories. The ledger has one fixed pending
slot; there is no history scan, automatic initialization, clearing or retirement
API. Initialization was a separate explicit, once-only operation. Root created a
private `0700` disposable engineering directory and a `0444` public epoch identity
under `/var/tmp`; the epoch is not a credential.

The normal run intentionally leaves the pending record unresolved even after its
observed successful exit. A complete final receipt alone cannot certify a later
successful acknowledgment. Retirement needs a separate verified decision. Earlier
wrappers that do not consult this ledger are outside this enforcement scope.
Root interference, storage rollback, hardware durability and complete custody
are not established by this candidate.

## Source-bound observations

| Control | Retained result | What it establishes |
| --- | --- | --- |
| Component run | 37 methods PASS, 0.073 seconds | Original 18 receipt/cleanup controls plus latch controls; candidate loaded as a module |
| Ledger initialization | Actual tool exit 0; identity and epoch read back | One explicit initialization, not crash-safe recovery qualification |
| Actual wrapper | 37 methods PASS, 0.197 seconds; actual outer and wrapper exits 0 | Normal main path, matching stdout/final receipt and tracked terminal cleanup |
| Subsequent invocation | Expected exit 1, `create-pending` / `FileExistsError` / EEXIST17 | Pending intent refuses a fresh-output invocation before execute/Popen |
| Preservation | Before/after pending bytes identical; same heavy-lock identity | Refusal does not replace or clear predecessor state |

The refusal ran zero tests. It produced no active/final execution receipt, proof
stdout/stderr, socket or payload-directory output. Its nonzero exit is the expected
negative-control result, not a successful workload. Raw refusal output is retained.
All execution-file pins, 478 source hashes and byte counts, canonical bindings,
tools and helpers were checked for each executed path. Actual GPT-6.1 independently
confirmed the raw rosters, bindings, acknowledgment, cleanup and preserved refusal.

The source-binding assertion was strengthened after review; the initial circular
test oracle and misleading free-lock test name are preserved in an unexecuted
snapshot. A subsequent unnecessary-lambda static failure was repaired without
suppression. The initialization draft's loop-variable shadowing failure is also
retained and was repaired before execution. No failed draft was dispatched.
The final selected strict static checks report no diagnostics, with no new routine
over 60 lines. This is neither formal Python verification nor complete Power of Ten
compliance. Mocked main-path unit tests remain distinct from the actual wrapper run.

Exact source and raw-result hashes are in the
[generated manifest](ORDINARY-RECOVERY-LATCH-EVIDENCE-20261026.json). The
[109-member archive](evidence/ordinary-recovery-latch-20261026-v1.tar.gz) contains
source, raw outputs, configurations, explicit failure/UNRUN dispositions, audits,
independent review records and the deterministic generator. `--check` reproduces
the package byte for byte on the evidence host. Source snapshots are bound by
hash and size but are not fully reproduced. Local paths are disclosed. Captured
tool returns and tool-exit notes are not signed platform receipts; no credential
input is retained.

## Still open

The root-owned pending record remains present and unresolved. Do not delete it,
substitute a new ledger or use a free lock as evidence that retry is safe. Before
another admitted operation through this candidate, qualify a source-bound
retirement/reconciliation decision. Then exercise actual observer-death cuts
around launch, handle acquisition, admission and final publication. Observe
termination before witness cleanup so the witness cannot mask a failed control.
Intent persistence does not close the pre-entry custody gap or reconcile external
effects. This campaign did not inject observer loss.

No installed product, service, firewall, provider, release or marketplace state
changed. The only additional host fixture is the declared private engineering
ledger. C14/native lifecycle and receiver integration, repeated compaction,
R05 BOTH, Astra judge, installed final composition, all original A/G/C/P/R/EP
obligations, merge/release and marketplace acceptance remain open. Existing SPARK
receipts apply only to their unchanged selected source and assumptions; they do
not prove this wrapper or whole-system recovery.
