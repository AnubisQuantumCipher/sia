# Retained ledger stage refusal repair

The repository assurance review identified a retained `.head.pin.stage` FIFO
that blocks before file-type validation. The committed ledger at
`83183ba595120600b2a3fc07359e6de26e193ceb` has the same bytes as the reviewed
failure source. This repair addresses that specific availability defect under
A05/A07/A20/A21, with exact-source reproduction and release under A13/G6.

The retained-stage reader now opens with `O_NONBLOCK` in addition to its existing
no-follow and close-on-exec flags. Every regular-file, owner, link, mode, size,
payload and generation check remains. Malformed stages remain available for
inspection. When an existing stage is encountered, the writer also clears its
closed anonymous-stage descriptor before calling the fallible reader. This
prevents a second close from hiding the real refusal as `Bad file descriptor`
and preventing the directory descriptor from being closed.

The new regression prepares a real signed interrupted append in a disposable
directory and invokes the actual ledger CLI. FIFO `head` and `verify` must
refuse within their fixed child deadlines with a named reason and unchanged
history, pin, pending record and malformed stage. Symlinks, wrong modes, wrong
sizes, incorrect bytes and hard links also refuse without adoption. The
positive case requires adoption of the exact retained inode, settlement of the
same signed tail, preservation of source/key bytes and an idempotent second
`head`. All original recovery tests remain unchanged.

The [raw evidence](LEDGER-STAGE-REFUSAL-EVIDENCE-20261021.json) embeds the exact
commands, runner, source inventories, logs, static diagnostics and independent
actual GPT-6.1 review with per-file hashes. The original source fails the new
suite with two FIFO deadline errors and five masked-refusal failures; its exact
stage positive case passes. With the two-site repair, all four new test methods
pass, and all 39 original ledger tests pass with warnings treated as errors.
Independent review checked those outputs; it did not rerun them.
A subsequent actual GPT-6.1 executor independently reproduced all four new and
39 original cases from committed `e9aeef01f1d7a842476fc8ac2da9c49ac8ab8ff5`,
with no source overlays. The [later raw record](REVIEW-REPAIRS-EVIDENCE-20261021.json)
keeps that execution distinct from the earlier source review.

The new test has no diagnostics under the existing pinned partial Ruff profile.
The ledger retains six pre-existing diagnostics, without suppression. Those,
analogous blocking reads, broader resource/liveness guarantees, protected
authority, full-project proof, installed-path testing and release remain open.
This is a tested repair, not whole-system Power of Ten compliance or acceptance.

Reproduce the relevant tests from the exact source:

```sh
python3 -B -W error -m unittest -v tests.test_ledger_stage_recovery
python3 -B -W error -m unittest -v tests.test_ledger_init_recovery tests.test_ledger_recovery tests.test_sia.Ledger
```

Use an outer 120-second deadline for each retained campaign. Its child deadline
is three seconds. These are test bounds, not claimed filesystem WCET. Production
`head` and `verify` remain recovery-capable operations and are not read-only
inspection commands. No live ledger or installed service was changed here.
