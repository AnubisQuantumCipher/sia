# Tree-CAS synchronized-member admission repair

The installer could block while synchronizing a staged tree if a regular member
was replaced by a FIFO after `lstat` and before the native read-only `open`.
The regular-file flags now include `O_NONBLOCK`, allowing the existing descriptor
type and identity checks to reject that substitution. The ordinary generation
path still uses `O_PATH`, including safe mode-zero launch files. The journal
reader already added `O_NONBLOCK`, so its effective flags are unchanged.

A private baseline executes the complete extracted installer heredoc. One
instrumentation hook pauses after the original regular-file observation, then
returns directly into the unchanged native `os.open` after substitution. The
observer recorded three native `openat` samples for the exact directory, flags
and `value` pathname, each sleeping in `wait_for_partner` on the real no-writer
FIFO. It then killed that exact child through its pidfd and retained its actual
-9 wait result. Normal publication and four other substitution controls met
their separate oracles. All twelve baseline child records and original bytes
remain preserved; the interruption is counterexample evidence, not a proof pass.

The final candidate passes six additive methods and twelve actual child calls:
normal publication, FIFO, symlink, directory, missing member, and ordinary
generation with a FIFO substitution. Refusals require exit 1, an exact original
diagnostic, empty success output, unchanged target bytes, the retained original
staged inode and bytes, no backup and no publication journal. Normal publication
must install the desired bytes and preserve the prior target as backup. Every
child has an actual terminal result without timeout; a separate readback found
all six candidate fixture roots absent after cleanup.

Seven unchanged original recovery, generation, race, symlink, mode and isolation
methods pass. The first candidate placed the added flag directly in the open
expression, which failed an existing source assertion in the mode-zero control.
That source and failure remain saved. Moving the flag into the existing
function-local flag definition preserves the original conditional and the
entire original test. The final candidate and original selections were rerun
against the final source; no assertion was weakened.

The complete updated CI static step passes locally with empty diagnostics and
stderr under its unchanged frozen rule profile. Both new Python test files are
included in that step. Shell syntax and patch whitespace checks pass. Actual
GPT-6.1 independently reviewed the final production/test/CI sources and local
receipts without an unresolved finding; it did not replay the tests. Hosted CI
is a separate gate and is not claimed to pass here.

[The generated evidence index](evidence/TREE-SYNC-ADMISSION-20261026.json) binds
source hashes, preserved failures, baseline and candidate receipts, static
qualification and independent review. Full local evidence is retained under
`/home/sicarii/Work/sia-assurance-evidence-20261019/ownership-transfer-20261024/r13-tree-sync-admission-20261026-v1`
and its referenced sibling directories. Final snapshots do not prove absence of
transient effects or qualify installed execution.

This closes one demonstrated blocking open. Full R13/R40, R05 BOTH, native
custody, whole-project proof, actual compaction, judge, installed composition,
recovery and release remain open. The old proof remains interrupted. A fresh
proof still requires qualified aggregate storage, capacity, exact source and
tool identities, and custody admission.
