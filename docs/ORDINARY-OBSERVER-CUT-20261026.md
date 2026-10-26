# Observer loss before admission and subsequent refusal — 2026-10-26

TESTED / INSTRUMENTED ENGINEERING FIXTURE. One actual root observer was stopped
immediately after recording the active process identities, before admitting the
UID1000 payload, then killed by an independent witness. The observer, launcher,
namespace init and payload leader were all observed terminal and reaped before
the witness attempted cleanup. Cleanup sent no signals and reported no errors.
The payload sentinel did not run. The pending operation record remained unresolved.

A later invocation with a fresh output directory stopped at `create-pending` with
`FileExistsError` / EEXIST17, before payload launch. Its actual exit was 1. A separate
root readback retained the same pending bytes. This is the expected refusal, not a
successful workload or permission to retry the interrupted operation.

## Source and observations

The execution wrapper is SHA-256
`aee6fd5047505fb523359e666f49966e75409f8b3b5d748a7848e33e9b7d8b6d`.
The cut manifest is
`fba159b884fc1a46a88df326f54e1ce4ba05e771fb16b4b22d5005b05f1fd5c4`;
the fresh-output refusal manifest is
`989c52a65db249674627f17555bc9e8c9316f4ddd32a8af0341bb6322835b181`.
Both bind 478 baseline source files from
`4ff2268179610297f67b1fd586e725c22ab66d12`, with canonical byte checks,
fixed helpers, tools, host, boot, epoch, output and heavy-lock identities.
No new GNATprove invocation occurred in this campaign.

The instrumented driver calls the actual wrapper's original receipt writer,
then stops itself at the selected boundary. A retained process handle binds the
witness's kill to that observer. The witness records raw process status, start
ticks, parent relationships and namespace identities. The UID1000 leader has
the expected groups, no capabilities and NoNewPrivs set. This does not assert
that the privileged observer or launcher has no capabilities.

The final witness result and actual outer exit 0 agree. The separate preliminary
before-cleanup record retains its conservative `FAILED_OR_UNKNOWN` label; the
later result classifies the completed checks without rewriting that record.
The killed observer produced no final execution receipt. The pending SHA-256 is
`74faf232cf9bea62a5c9e72f9c32b3a4f435c35e448268a81963e43d226b4678`.
Its exact value binds this cut's manifest and output identity, not a generic job.

## Guard and failure evidence

The wrapper now checks two exact history names under the existing lock before
creating pending intent: the retired record and reconciliation decision for the
same manifest. An existing object of any kind refuses; unexpected lookup errors
propagate. These are two bounded lookups, without a history scan. All 44 component
methods pass, including the original 37. A changed manifest can still represent
the same semantic operation, so this is not general replay prevention.

Eight instrumentation controls pass, including partial handle-acquisition failure
and refusal to count cleanup-assisted termination as an unassisted result. Selected
strict static checks report zero diagnostics and no routine exceeds 60 lines.
This does not establish whole-Python Power of Ten compliance or formal proof.

The archive retains the earlier failed guard test oracle and omitted original
cleanup roster, the failed mock path fixture, and unexecuted instrumentation
drafts rejected during review. Their results are not replaced by the passing
candidate. Independent actual GPT-6.1 reviews checked source, raw results,
identity bindings, termination before cleanup, and the subsequent refusal.

## Reproduction and remaining obligations

The [generated manifest](ORDINARY-OBSERVER-CUT-EVIDENCE-20261026.json) and
[646-member archive](evidence/ordinary-observer-cut-20261026-v1.tar.gz) retain
the exact execution sources, selected baseline snapshot, fixed helpers, raw
outputs, failed drafts, decisions, audits and reviews. The included generator
reproduces the archive byte for byte from the bound local evidence layout.
The archive permits offline byte inspection; it is not a portable executor.
Host binaries are hash-bound, not bundled. Tool-completion notes and the exact
refusal exception are unsigned model-recorded observations; local outer receipts
independently retain actual exit and source bindings.

This result assumes the declared ordinary, nonhostile root/host environment and
an available external witness. Witness loss, pre-entry acquisition gaps,
post-admission descendants, hardware crash consistency and general successor
admission remain UNKNOWN or UNRUN. The new pending record must remain unresolved
until a separate evidence-bound reconciliation decision is qualified. The earlier
manual reconciliation covered a different, completed normal fixture.

The next existing recovery step is to reconcile this exact interrupted fixture
without inferring generic retry authority, then qualify the remaining actual
boundary cuts. Native C14 lifecycle/receiver integration and repeated compaction,
R05 BOTH, Astra judge, installed final composition and release/marketplace gates
remain open. All A/G/C/P/R/EP obligations and original failing assertions remain.
No installed SIA, service, firewall, provider, release or marketplace changed.
