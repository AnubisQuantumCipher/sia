# Admission-test isolation repair

The unchanged suite-wide isolation guard rejected two new admission-test modules
because they named runtime files before activating the standard test-home helper.
The selected FIFO tests had passed without exercising that integration guard.
The current-source baseline reproduced both failures. Both modules now import
`sia_test_home` before their runtime references and assert its active home in
`setUp`. Their separate child environments and private `/dev/shm` fixtures are
unchanged. No checker exemption or original test change was made.

The two original isolation methods and all 32 admission fixture methods pass.
All 32 child records retain actual reaped results, unchanged fixture snapshots,
and no timeout; a later readback found their private roots absent. The complete
existing CI static step passes locally with empty diagnostics. These are local
results, not a hosted-CI or system-acceptance pass.

The first combined run retained one environment error: its `-S` option hid the
installed cryptography package from the original full-path guard. The succeeding
runner keeps Python isolation (`-I`) and loads installed cryptography 50.0.1.
The unsuccessful run and the original two failing guard subtests are preserved.

Evidence is retained under
`/home/sicarii/Work/sia-assurance-evidence-20261019/ownership-transfer-20261024/test-isolation-repair-20261026-v1`.
`EVIDENCE-AUDIT.json` SHA256 is
`9f2c11810354bb24b72a8318d9360117bdff99a83ae54869d469da552d241747`.
The original guard SHA256 remains
`61e2a69514e93277867a9634009a5dffc914f4a1a7ad36005d092de189e078e5`.
Actual GPT-6.1 independently reviewed the two-file change and raw receipts with
no findings; this was a source/receipt review, not another test execution.
`INDEPENDENT-REVIEW.json` SHA256 is
`b4ed9c40f029e1f01be68a0481eedd6d24a2d1829bd2a19e75c5a7bfd98b7631`.

R05 expensive reuse/BOTH, complete R13/R40, project proof, native custody,
actual compaction, judge, installed composition, recovery and publication gates
remain open. Storage source qualification is separate and has not restarted proof.
