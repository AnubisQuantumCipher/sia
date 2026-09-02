---
name: sia
description: Use SIA, this machine's persistent memory (the Omarchy Brain), from any agent session. Trigger whenever the user asks what happened on this machine, when something occurred, about crashes/upgrades/healings/chains/agent activity — or says "ask sia", "sia", "remember this", "leave a note", "predict", "memory stability", or "rehearse". Also use at the START of substantive work on this box to recall relevant history, and at the END to leave a note for future sessions. Covers recall, no-touch search, notes, predictions, calibration, stability/rehearsal, the signed-ledger benchmark, and SIA's honesty rules.
---

# SIA — the Omarchy Brain

This machine has a persistent, associative memory. A daemon
(`sia-brainstem`) tails the enabled evidence streams available here (base
pacman/journal/git/session/notification sources plus optional JACKAL,
SEKHMET/Custos/AEGIS, WORLDLINE, Guardian, and configured custom senses) into
a git-versioned corpus indexed by gbrain with local embeddings. You — this
session — are one of its organs.

## CLI commands (a core subset is exposed by MCP server `sia` where mounted)

```
sia ask "question"        # semantic recall, cited, origin-labeled
sia ask "question" --no-touch  # audit/eval read that does not reinforce memory
sia recall <slug>         # one memory page verbatim
sia status                # brain state, chains, organs
sia ready                 # live exit-status gate for reconciled memory
sia think                 # recent thoughts (its inner monologue)
sia note "text" --from <you>      # leave a labeled note for future sessions
sia takes / sia calibration       # predictions and the Brier scorecard
sia take "claim" --confidence 0.8 --by DATE --domain d   # user-held take
sia take --accept <proposal-id>|all # commit immutable proposal(s) (HUMAN decision)
sia memory / sia memory <slug>    # stability, pin, and review state
sia rehearse [slug]               # list due reviews or deliberately recall one
sia bench                         # signed-ledger held-out memory self-benchmark
```

## When to use

- **Session start / before re-deriving machine history**: `sia ask` first.
  Package changes, crashes, healings, chain verifications, prior agent
  sessions are recallable when their source was enabled, observed, and
  retained.
- **When you learn something durable about this machine**: `sia note
  "..." --from <your-harness-name>`. Notes are model-origin memories —
  recallable and graphed, permanently labeled agent prose, weighted below
  evidence. Write them for your successors, not as scratch. Never put
  credentials, secrets, or private content in a note: notes persist and can be
  returned to configured consumers, while SIA's redaction is pattern-based
  defense in depth rather than a secrecy guarantee.
- **When you make a testable claim about this machine's future**: propose
  a take (MCP `sia.propose_take`, or tell the user to run `sia take`).
  Agents propose; only the operator commits. the configured judge grades takes
  against recalled evidence when due; Brier scores use deterministic decimal
  arithmetic and remain descriptive over an operator-selected population.
- **For an audit or evaluation**: use the MCP `sia.search` tool or CLI
  `--no-touch` forms. Ordinary recall intentionally reinforces memory; the
  no-touch lane does not mutate rehearsal or graph state.

## Honesty rules (non-negotiable)

- New persisted origin metadata has exactly three classes: `[evidence]`,
  `[derived]`, and `[model]`. Missing, malformed, or ambiguous legacy metadata
  is surfaced as `[legacy-unlabeled]`; it is never evidence and is weighted
  conservatively like `[model]`. Never cite model or legacy-unlabeled memory as
  evidence. Judge-grade/ponder thoughts, take-proposal notifications, and
  agent/operator notes are model; deterministic transition and Brier arithmetic
  do not relabel the verdict.
- Typed domain relations come from event/epoch evidence or an explicitly
  `[derived]` integrity/healing/crash/refusal thought. Model and
  legacy-unlabeled thoughts may link pages only with generic `mentions`.
- Every `sia ask` answer ends with a truth-boundary line (sense
  freshness, chain verdicts, recall mode). Repeat degradations to the
  user; never present an answer over a stale brain as current.
- `sia status` remains available during recovery and labels its live
  readiness reason; its pulse and graph fields are the last published
  snapshot. Use `sia ready` when automation needs a success/failure gate.
- **Absence of recall is not evidence of absence.**
- Never touch `~/.local/share/sia/.gbrain/` directly. PGLite admits one
  owner, so every SIA-managed daemon/CLI/MCP/benchmark operation uses the
  same cross-process lease. Agent notes go through immutable request files
  and the brainstem acknowledges them only after corpus commit and index
  sync. This coordination is advisory, not a hostile same-user sandbox.
- SIA's MCP server also exposes byte-bounded `sia://status`, `sia://thoughts`,
  `sia://calibration`, `sia://cortex`, and `sia://memory/{slug}` resources.
- The local MCP server makes no cloud or external network calls; configured
  retrieval can use a loopback Ollama service. Its client receives the requested
  memory and may send it to a model/provider. The same trust boundary applies to
  scripts, pipes, or agents that capture `sia` CLI output.
- Open the cockpit from its bar widget; `SUPER+SHIFT+B` is available only when
  the operator explicitly enabled that optional binding. Full docs are at
  `~/.config/omarchy/plugins/khephri.sia/docs/MANUAL.md` for an Omarchy install.
  For a standalone install, use `docs/MANUAL.md` in the checkout used to
  install SIA; if neither path remains, fall back to `sia --help` and the MCP
  tool/resource descriptions.
