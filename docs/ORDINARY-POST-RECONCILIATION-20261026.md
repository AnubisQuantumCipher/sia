# Exact post-entry fixture reconciled — 2026-10-26

TESTED / ONE FIXED SENTINEL. The [post-admission observer cut](ORDINARY-POST-ADMISSION-CUT-20261026.md)
now has a retained `ABORTED_AFTER_ENTRY_FIXED_SENTINEL_NO_WORKLOAD` decision.
One exact root invocation and a separate readback both exited zero. The original
pending inode `263278` and bytes are preserved under their retired name. The
seven-record ledger contains the exact decision and unchanged previous history
and epoch; pending is absent. This supersedes that fixture's unresolved-pending
status, without turning the interrupted operation into successful work.

The pending SHA-256 is
`736bd21e915003d5c2ae226ebcba48cfb2a416a0bf799aeb42fd5e86646c1c25`;
the canonical persisted decision is
`421218bcd8d2ca9e5c613d7c66779e7f98363c2f30500ee9957a6fefcd8fdc1e`.
Admission requires both independently observed post-exec entries, all five roles
terminal/reaped before cleanup, no cleanup intervention, the exact harmless
sentinel command, complete invocation vectors, original pending identity and
the subsequent refusal/readback. Exact source, tools, host, lock and the closed
predecessor ledger are checked before writing.

The unchanged storage sequence exclusively creates and synchronizes the decision,
hardlinks and synchronizes the original pending inode, rechecks identity, unlinks
the blocking name, synchronizes the directory and checks closes. Any uncertainty
retains UNKNOWN without automatic retry or rollback. Previous history is checked
by bytes and metadata; its original inodes were not pre-mutation conditions.

The changed admission path passed 94 component methods in 0.443 seconds: the
original 21 normal-fixture and 33 pre-admission methods remain, alongside 40
current-candidate methods. Negative controls reject missing or aliased child
entry, changed process identity, credentials, capabilities, parent/namespace,
active-record binding, command vector and non-sentinel workload. An initial
syntax failure is retained with exact source; it occurred before tests or root
execution. Selected strict static checks report zero diagnostics and no routine
over 60 lines. These are not proofs of Python runtime or total resource bounds.

The executed eleven-file source manifest is
`d837359f39470776e5727462eb59b7d2cbcd3558984f2625b2129d97e29ce4d0`.
Actual GPT-6.1 independently reviewed source, results and readback. Tool exit
notes remain unsigned owner-recorded observations. The [generated manifest](ORDINARY-POST-RECONCILIATION-EVIDENCE-20261026.json)
and [40-member archive](evidence/ordinary-post-reconciliation-20261026-v1.tar.gz)
retain exact source, tests, failed draft, raw results, decisions and review;
byte reproduction passes. Prerequisite cut/refusal and inherited-source evidence
remain at `4ade8e3856e16678ffc37d76aec35c3cc69333b6` and its linked checkpoints.

This decision applies only to the known harmless sentinel and child. No workload
is replayed and no successor is admitted. Nonhostile root/host and filesystem
synchronization are assumptions; hardware crash consistency remains unproved.

The next concrete gap is pre-entry custody: the native adapter must not release
payload before ownership and durable operation binding have been acknowledged.
Its current dispatcher still refuses. Loss of the surviving witness, arbitrary
descendants and the typed original-native-record join remain separate mandatory
gaps. Native C14, repeated compaction, R05 BOTH, Astra judge, installed composition
and every original release/marketplace obligation remain open. No installed
product, service, firewall, provider, release or marketplace changed.
