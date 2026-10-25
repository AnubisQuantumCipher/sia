# Integration test discipline repair

Status: **SELECTED STATIC AND REGRESSION PASS; FULL SIA ACCEPTANCE INCOMPLETE**.

The integrated account-guard and release test files carried ten findings in
the selected static-analysis profile. These changes remove those findings
while retaining the original fixtures and assertions:

- Assert that the test HOME isolation fixture actually took effect before
  loading runtime modules, preserving its required import side effect.
- Capture each restore fixture's callback values explicitly.
- Reuse the bootstrap script prefix already constructed from the same source.
- Label readiness-document subtests and assert archive source-extraction
  correspondence; remove an unused import.

Production runtime and installer source are unchanged. The exact base, staged
tree, commands, endpoint hashes and archive identity are in the companion
[evidence manifest](INTEGRATION-TEST-SCOPE-20261025.json).

The first combined regression run hit its original 60-second deadline after 59
completed OK lines. It had no complete-suite footer. A separate two-case
diagnostic subsequently passed the unfinished methods in 30.766 seconds under
the same original limit; that did not qualify the combined run.

The operator then explicitly approved one execution of the identical 61-test
roster with a 120-second deadline and 5-second kill grace. Every other limit
remained unchanged: 2 GiB address space, file cap, nonblocking heavy-job lock,
read-only source, disposable HOME and disabled network. That one invocation
completed **61 tests in 75.735 seconds, OK, with no skips**. Its wrapper measured
75956687115 ns. All 505 recorded endpoint hashes matched before and after; this
does not establish continuous loaded-code custody. No second invocation is
authorized by the consumed approval.

The selected frozen 167-rule static profile reports zero findings for the
affected implementation/test files and verification runners. This is not a
whole-repository zero-warning claim. Actual GPT-6.1 reviewed the source and raw
outputs without independently executing the tests. The public archive retains
the original timeout, separate diagnostic, explicit approval and complete pass.

This closes the scoped test-file repair only. R05 still requires useful
expensive-work reuse and fresh current-policy validation. Original full
SDK/native/SPARK, protected custody/publication, compaction, retrieval,
off-host recovery, installed lifecycle, final composition and release/marketplace
requirements remain open. No budget for those workloads changed. No service,
installed executable, model, release tag or marketplace listing changed.
