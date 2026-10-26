# Exact interrupted-fixture reconciliation — 2026-10-26

TESTED / ONE PRE-ADMISSION FIXTURE. The interrupted operation from the
[actual observer cut](ORDINARY-OBSERVER-CUT-20261026.md) now has an explicit
manual decision: `ABORTED_BEFORE_ADMISSION`. One reviewed root invocation and
a separate read-only inspection both exited zero. The original pending inode
and SHA-256 `74faf232cf9bea62a5c9e72f9c32b3a4f435c35e448268a81963e43d226b4678`
are preserved under their retired name. The exact decision is present, pending
is absent, and the ledger identity, epoch and earlier history bytes/metadata
are unchanged. This result supersedes that report's unresolved-pending status
for this exact fixture only.

The procedure requires the original four-role termination observations before
cleanup, no cleanup signals, exact witness acknowledgment and the subsequent
pending refusal/readback. Closed evidence rosters, source, tool, host and lock
checks precede mutation. A bounded ledger scan rejects missing or extra names,
changed history and a replacement pending inode. It retains the previously
tested exclusive decision, file/directory synchronization, hardlink preservation,
identity rechecks, pending unlink, final synchronization and checked closes.

All 54 component methods passed in 0.180 seconds. This includes the original
21 normal-fixture methods, the original 13 storage methods against the changed
admission path, and additional interrupted-evidence, ledger and encoding controls.
Selected strict static checks report zero diagnostics; no routine exceeds
60 lines. These results do not prove the Python runtime or whole-system bounds.

Independent GPT-6.1 review found that the first readback compared persisted
canonical decision bytes to raw input formatting. The repaired readback computes
the writer's exact encoding. A real-writer regression uses noncanonical input
formatting, key order and Unicode. The earlier 53-test passing source remains
retained as UNRUN for actual reconciliation. It did not change the root ledger.

The executed nine-file source manifest is
`b6a26b85408b4ed60180fb4b1509551e9c7444d01fa5d0023918d5d05d048311`.
Actual GPT-6.1 independently checked source and retained results, including the
five-file ledger, original pending inode, canonical decision bytes and actual
exit observations. Tool-completion notes are unsigned owner-recorded observations.
Prior history files were checked by bytes and metadata; their original inodes
were not a pre-mutation admission condition.

The [generated manifest](ORDINARY-CUT-RECONCILIATION-EVIDENCE-20261026.json)
and [43-member archive](evidence/ordinary-cut-reconciliation-20261026-v1.tar.gz)
retain the exact procedure, tests, decisions, raw results, audits, review and
unexecuted draft. Byte reproduction passes. Prerequisite cut/refusal evidence and
the selected baseline snapshot remain in checkpoint
`c61d43cb291274f4904295423dbda9aa00e5d849`.

No workload was replayed and no successor was admitted. Any storage failure
remains UNKNOWN without automatic retry or rollback. Ordinary nonhostile root,
unchanged host assumptions and filesystem synchronization remain premises;
hardware crash consistency is unproved. The next existing control is an actual
post-admission observer cut with independently acknowledged payload entry and
an explicitly tracked descendant. Pre-entry and witness-loss custody, native C14,
repeated compaction, R05 BOTH, Astra judge, installed composition and every
original release/marketplace obligation remain open. No installed product,
service, firewall, provider, release or marketplace changed.
