# Fenced metadata FIFO admission — 2026-10-26

Four Linux metadata readers now include `os.O_NONBLOCK` when opening a launch-fence journal or receipt. Previously, opening a FIFO with no writer could block before the existing regular-file check. The change lets that check reject the FIFO. Ownership, type, size, generation, schema, receipt and digest checks retain their existing behavior.

The four changed flag expressions are in `install.sh` functions `fenced_managed_file_authorized` and `fenced_runtime_authorized`, `uninstall.sh` function `fenced_managed_file_authorized`, and `bin/siarelease.py` function `authorize_fenced_runtime`. The last function is the actual `runtime-authorize-fence` CLI delegated to by the uninstaller's runtime authorization function. Each expression adds only `os.O_NONBLOCK`.

The base checkpoint is `09edd09cd64d2c6af63e326b67ac76a57c684085`. This is a bounded **TESTED FIFO behavior repair**, with authority **NONE** and assurance acceptance open. It is not a formal proof, installed qualification, release approval, or publication result.

The [derived evidence summary](FENCED-METADATA-FIFO-20261026.json) binds the tested source, raw capture hashes, actual independent execution and final scoped review. It is an unsigned summary; complete raw evidence remains local.

The new `tests/test_fenced_metadata_admission.py` exercises the three complete Python heredocs extracted from their current shell functions and the actual release CLI. Each consumer has four separate cases: a native journal FIFO with no writer, a native receipt FIFO with no writer, valid regular metadata, and a mismatched receipt digest. The managed installer case uses `check`, which actually reads the receipt. Both runtime fixtures contain the complete supported eight-member legacy v1 rung; their expected digest is constructed independently from the fixed member bytes and the v1 digest format, without calling the production digest function.

Each case owns a fresh private directory under `/dev/shm`. Actual metadata and bytes are compared before and after execution, including mode-zero member bytes read through parent-held, close-on-exec descriptors. Directory entries and executable source are also compared. The harness retains the existing three-second child deadline, permits one five-second reap attempt, bounds each output pipe at 4 KiB, and records the child PID and reap state. The former harness preparation used a `Popen` context manager whose implicit wait could defeat the cleanup deadline; independent review rejected it before any baseline execution. The corrected harness explicitly closes both pipes and propagates cleanup failure.

| Recorded run | Result | Scope and observations |
| --- | --- | --- |
| Baseline, 16:39:36–16:40:00 UTC | **FAILED**, exit 1; 16 tests, eight errors | All eight no-writer FIFO cases exceeded the three-second deadline. Their children were interrupted and reaped with exit `-9`; this is failure evidence, never a pass. The four regular controls and four mismatched-receipt controls passed. |
| Candidate, 16:41:22–16:41:23 UTC | **TESTED**, exit 0; 16 passed | No child timeout. Four accepted inputs returned 0, nine inline refusals returned 1, and three release-CLI refusals returned 2. |
| Independent candidate, 16:44:39–16:44:40 UTC | **TESTED**, exit 0; 16 passed | The actual `gpt-6.1-sol` reviewer `reconcile_review` performed a separate execution. The same expected exit distribution was recorded, with no timeout or cleanup error. |
| Selected original regressions, 16:42:04 UTC | **TESTED**, exit 0; eight passed | Eight unchanged methods from `tests/test_release.py`; their existing mocked runtime ladders and faults remain part of the declared test scope. |

Every baseline, candidate and independent case recorded matching before/after fixture observations and a reaped child. Each execution receipt records unchanged source hashes across its run. The independent source-review receipt identifies the reviewer model; it is an unsigned parent transcription, not a cryptographic attestation. The independent execution has its own raw outputs and receipt.

The original selection covers exact journal/tombstone authorization, retrying an already fenced CLI, strict named metadata parsing, runtime-ladder delegation, a stable attested mode-zero member, an oversized member, closure after inspection failure, and runtime-root generation replacement. It is not the full release test suite. Exact method names and command arguments are retained in `ORIGINAL-EXECUTION.json`.

Strict static analysis remains **FAILED** for the combined scope. `CANDIDATE-STATIC.json` retains six inherited B904 diagnostics in unchanged exception-handling statements in the three embedded programs, and one inherited B905 diagnostic in the full `bin/siarelease.py` at `_compare_versions`. `STATIC-BASELINE-COMPARISON.json` confirms that the six B904 diagnostics match the base checkpoint, ignoring only the temporary parent directory. The full-file B905 also appears in the retained baseline analysis. The comparison receipt separately records exit 0 with no findings for the current new test and exit 0 with empty output for both shell syntax checks. No diagnostic was suppressed or accepted as a policy deviation. CI source adds the new test to the existing frozen-rule and suppression checks; this note claims no CI execution result.

The tested candidate source hashes are:

| Repository path | SHA-256 |
| --- | --- |
| `tests/test_fenced_metadata_admission.py` | `21e90e0b5c1471a05cfb6e205fae4240d12e90d9249709de8c713035107d65ed` |
| `install.sh` | `487a01239597f87ac39d121de5a77ff7f8e6f635913eaa63921e74e1fb4db914` |
| `uninstall.sh` | `d02f86ea64faa9ddee8f09fbf5f34d74538faf93dfe047991918a61899fd74a8` |
| `bin/siarelease.py` | `be8c31e1bba5ff5b4d14b96a6035e4f59c6026ca9c5d28a7f13d89bb6888d1ef` |
| `.github/workflows/ci.yml` | `c16e9bb92c9976d50689e7043bc84fa234c5f8899207769b112898d763feebe3` |

Raw evidence remains local under the existing evidence-root storage pin, in the directory named:

```text
r13-fenced-metadata-20261026-v1/
```

The following names are relative to that local evidence directory. The public note identifies the directory by basename and the contents by hash; private filesystem paths are omitted. Execution receipts include the commands, source hashes before and after, environment scope, return status, and hashes of the corresponding complete stdout/stderr files.

| Receipt | SHA-256 |
| --- | --- |
| `BASELINE-EXECUTION.json` | `5cc295c09cf4f1a8e55a8d15178faea8b16798370886e4c01b907fc59dac6748` |
| `CANDIDATE-EXECUTION.json` | `fe77776412db35a55b0d2326db7476b9fe4074bcded74d087de279ab2a931472` |
| `INDEPENDENT-EXECUTION.json` | `c8286647bf07da81aeaa2309a22326f80faa4ef76a7303ec229daeb148b5bbb1` |
| `ORIGINAL-EXECUTION.json` | `bb2755929595b8395684282397ce94e4f33a8299b4f50d0a02f48dea18501c69` |
| `CANDIDATE-STATIC.json` | `1eca5a379df89c17620f400fc26adc58e27fafeb14736e368797e26c8589e90f` |
| `STATIC-BASELINE-COMPARISON.json` | `8f20bd08cdcc76e8d913435e65956d7cd08bbcd86128d8ce2e1945201f31420f` |
| `INDEPENDENT-SOURCE-REVIEW.json` | `8b3cd329879eacdbcf84a0318ee56e7cd96c908547eef0f4b7c69898e9ab5a23` |

The native case records are `BASELINE-STDOUT.jsonl` (`790e1b5a571a37e2e5e767b9ed7d75c3f06522b15fe79ccf17e66437cea1c2e7`), `CANDIDATE-STDOUT.jsonl` (`2d4db46bd935cdfc8813e9f7ada6a2cfe504ce5651dca6e2f7d9a5e89699234e`), and `INDEPENDENT-STDOUT.jsonl` (`33ee4a65f84849b85a818132bbe59dd10a786113d6df146b127b023f94321352`). The rejected, unexecuted preparation is preserved as `test-preparation-v1.py`, SHA-256 `d2c1e023661b61a4c232d4463900ed3432139983c75abeba21d82a8a2b566afb`, with `TEST-PREPARATION-V1-REVIEW.json` retaining its rejection.

All mandatory mission obligations remain open for whole-system completion: A01–A24, G1–G6, C01–C14, P01–P10, R01–R46 and EP remain binding. This note changes no acceptance row. In particular, it does not close R13, establish an exhaustive inventory or closure of other readers, prove a universal device or filesystem I/O latency bound, establish hostile-same-user containment, or qualify the full installer/uninstaller. Full-project proof, native custody, installed acceptance and publication gates require their own exact-source evidence. The remaining acceptance work must retain these negative results and resolve the applicable static findings without weakening the existing gates.
