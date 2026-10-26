# Fenced-reader static repair — 2026-10-26

This bounded repair follows checkpoint `886a3087e41cdd3a69e3f901e2fcb9fc7b4d4381`. Its authority is **NONE**; system acceptance remains open.

The [derived evidence summary](FENCED-STATIC-REPAIR-20261026.json) binds the exact source, captures and actual GPT-6.1 independent source/receipt review. The reviewer found no concrete blocker in this scoped delta and performed no duplicate execution.

Six existing exception translations in the three fence heredocs now bind the caught exception and use `raise SystemExit(1) from error`. This preserves the cause and the silent exit-1 refusal protocol. `_compare_versions` now uses `zip(..., strict=True)`. Its sole direct caller supplies two tuples from `_version_parts`, whose anchored regex has exactly three decimal-component groups. This source invariant justifies the change; early return prevents a claim of arbitrary-input length validation. Length/lexicographic comparison remains, without integer conversion or a new digit cap.

`STATIC.json` records exit 0, empty findings and empty stderr under the unchanged frozen profile for exactly: the complete installer managed-file and runtime heredocs, the complete uninstaller managed-file heredoc, full `bin/siarelease.py`, and `tests/test_fenced_metadata_admission.py`. Both shell syntax checks returned 0. This is not whole-project analysis.

`FIFO-EXECUTION.json` records all 16 existing cases passing. `REGRESSION-EXECUTION.json` records nine passes: the previous eight selected original methods plus the existing downgrade-refusal test. Source hashes were unchanged across both executions. No fresh independent execution, large-component test, or direct fault injection at the installer's second runtime `lstat` catch is claimed for this wave.

The integration runner's roster-selection assertion failed before any test subprocess started; `ATTEMPT-01-PREFLIGHT-FAILURE.json` preserves that failure. Earlier six-B904 and one-B905 results remain historical failures, not rewritten passes. Neither R13, R40 nor whole-system assurance is closed; proof, installed and publication acceptance remain separate.

Receipts and raw-output hashes remain in the pinned local directory `r40-fenced-static-20261026-v1`. `EXECUTION.json` SHA-256: `66fef95738d9d5f2f406f2569aa850513b9368e671d1fe8fdcb777c918711e08`.
