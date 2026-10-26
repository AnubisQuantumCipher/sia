# Recovery codec: selected proof and runtime checkpoint

The recovery-record package and its complete selected harness now discharge
their recorded obligations. This is an incomplete engineering checkpoint,
not installed-system acceptance, release approval or avionics certification.

The source adds the recovery permit/control codecs, explicit scalar and
role-preservation contracts, and proof lemmas for byte representation. The
harness retains the original admissibility predicate as an equivalence
obligation, original assertions, full generation domains and refusal controls.
The project includes the recovery runtime main. The inherited continuity-frame
harness repair is included because it was part of the tested source composition.

| Evidence | Observed result | Scope |
| --- | --- | --- |
| Strict build and original runtime roster | Build plus all 16 mains passed | Exact project/source composition; assertions and strict warnings enabled |
| `sia_recovery_records.adb` | 795 checks; 160 flow, 635 prover; zero justified/unproved | Complete selected unit, 69/69 entities |
| `recovery_permit_wire_tests.adb` | 1,211 checks; 233 flow, 978 prover; zero justified/unproved | Complete selected harness, 86/86 entities; no region selector |
| Independent GPT-6.1 readback | Source, tools, raw reports and tracked cleanup matched | Independent inspection, not independently repeated execution |

The earlier unit proof remains applicable: comparison of every recorded source
row found only harness changes, with the same compiler/prover identities and
project configuration. The complete harness was then proved on the final
snapshot. Counts from these runs are separate scopes and must not be added to
claim whole-project coverage.

The recorded proof commands use the project file with `--mode=all --assumptions
--no-inlining --memlimit=512 --timeout=10 -j1`, selecting each complete unit with
`-u`. These are the retained solver settings. There was no outer engineering
timeout. Strict build evidence records `-gnatwa`, `-gnatwe`, `-gnatVa` and
`-gnata`. No skipped proof, `pragma Assume`, justified checks, non-info diagnostic
or premature proof stop was accepted.

The [machine-readable manifest](RECOVERY-SELECTED-PROOF-EVIDENCE-20261026.json)
binds all source files, exact commands, tool identities and the
[raw evidence archive](evidence/recovery-selected-20261026-v1.tar.gz).
Archive members include the successful unit/harness/build reports, independent
readbacks, and failed v5 through v9 attempts. The v6 through v9 attempts were
limited diagnostics and are labeled as such by their original commands. Their
failures remain failures; later success does not rewrite them. The earlier
incomplete, timed-out campaign remains described in
[the historical scope report](RECOVERY-PROOF-SCOPE-20261025.md).

The archive contains original runner/configuration records for inspection.
They reference the original local paths and are not a standalone deployment or
execution service. Hash correspondence does not authenticate evidence producers
or establish the truth of their inputs. Reproduction needs the recorded tools,
source, project switches and an independently qualified execution environment.

The root observer established private execution namespaces and a fixed UID1000
payload with no capabilities. Tracked launcher, init and leader cleanup passed.
Observer-loss custody is still UNKNOWN; successful cleanup in these runs does
not qualify every supervision failure case.

Whole-project proof, complete Power-of-Ten compliance, protected authority and
signer custody, source-to-publication crash acceptance, real harness compaction
continuity, R05 BOTH, the Astra judge, installed composition, release and live
marketplace acceptance remain open. All original A, G, C, P, R and EP obligations
remain binding. No runtime installation, service, firewall, provider or release
change is made by this checkpoint.

The smallest next implementation step is the bounded cache-ownership repair
already identified by the R05 regression work, followed by its original reuse,
current-policy and lifecycle controls. Its selected regression results cannot
replace the remaining performance, concurrency or retention evidence. The
continuity and other system obligations stay on the existing critical path.
