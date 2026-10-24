# Backup capture record-limit diagnostic

Status: TESTED diagnostic repair; recovery and release acceptance remain INCOMPLETE.

A capsule exceeding the existing whole-tree record limit previously produced only the generic failure sentence. The exact fixed refusal now produces `capsule-record-bound`. Only exact matching is used for this new reason; appended exception text is not echoed. No resource limit, included root, credential handling or success condition changes.

The original backup and continuity modules, including two new privacy/failure-propagation tests, passed: 160 tests in 3.979s under the existing isolated 60-second envelope. All inventoried inputs matched before and after. Independent actual GPT-6.1 source/raw review found no concrete blocker; it did not independently execute tests. The selected strict static profile reports the same 25 inherited diagnostics as the base. Zero-warning compliance is not established. Exact hashes and observation scope are in the adjacent JSON receipt.

Installed observation: the scheduler accepted an upload, while the separate worker exited 1 and durable status reported failed. That status retains no specific exception class, so its historical cause remains UNKNOWN. A later bounded metadata-only scan reached the installed record limit with directories unvisited. The scan used installed exclusions and did not read memory contents or contact the repository; it was unlocked and non-atomic and cannot establish a consistent capture or prove the earlier failure's cause. The older verified-copy status is not evidence of a fresh recoverable backup.

The operational next step is a bounded complete-capture design that preserves all selected history and the existing resource contract, followed by a successful managed capture, off-path restore, capsule verification and terminal receipt. Raising caps, silently omitting history, deleting corpus material or claiming restored operation from this diagnostic would not meet that requirement. No recovery request, credential change, live restore or installation was performed for this repair.

The private frame-fusion writer experiment remains FAILED/NOT_ADOPTED: four differential and 234 affected tests passed, but the original full writer roster timed out at its unchanged 60-second cap. R05's mandatory reuse and fresh-policy requirements remain open; the specific requirement-change question still needs an actual human response. Strict proof, real continuity lifecycle, installed qualification, controlled release and marketplace publication remain separate gates.
