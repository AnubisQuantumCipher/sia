---
name: sia
description: Use SIA, this machine's persistent memory (the Omarchy Brain), from any agent session. Trigger whenever the user asks what happened on this machine, when something occurred, about crashes/upgrades/healings/chains/agent activity — or says "ask sia", "sia", "remember this", "leave a note", "predict". Also use at the START of substantive work on this box to recall relevant history, and at the END to leave a note for future sessions. Covers sia ask/recall/status/think/note/take/grade/calibration and the honesty rules that govern them.
---

# SIA — the Omarchy Brain

This machine has a persistent, associative memory. A daemon
(`sia-brainstem`) tails every evidence stream (JACKAL ledger, SEKHMET/
Custos/AEGIS signed chains, WORLDLINE, pacman, journald, git, agent
sessions, notifications) into a git-versioned corpus indexed by gbrain
with local embeddings. You — this session — are one of its organs.

## Commands (also exposed as MCP server `sia` where mounted)

```
sia ask "question"        # semantic recall, cited, origin-labeled
sia recall <slug>         # one memory page verbatim
sia status                # brain state, chains, organs
sia think                 # recent thoughts (its inner monologue)
sia note "text" --from <you>      # leave a labeled note for future sessions
sia takes / sia calibration       # predictions and the Brier scorecard
sia take "claim" --confidence 0.8 --by DATE --domain d   # user-held take
sia take --accept <n>|all         # commit queued proposals (HUMAN decision)
```

## When to use

- **Session start / before re-deriving machine history**: `sia ask` first.
  Package changes, crashes, healings, chain verifications, prior agent
  sessions are all recallable.
- **When you learn something durable about this machine**: `sia note
  "..." --from <your-harness-name>`. Notes are model-origin memories —
  recallable and graphed, permanently labeled agent prose, weighted below
  evidence. Write them for your successors, not as scratch.
- **When you make a testable claim about this machine's future**: propose
  a take (MCP `sia_propose_take`, or tell the user to run `sia take`).
  Agents propose; only the operator commits. the configured judge grades takes
  against recalled evidence when due; Brier calibration is arithmetic.

## Honesty rules (non-negotiable)

- Results are labeled `[evidence]` / `[derived]` / `[model]` — never cite
  a `[model]` memory (synthesis/, notes/) as if it were evidence.
- Every `sia ask` answer ends with a truth-boundary line (sense
  freshness, chain verdicts, recall mode). Repeat degradations to the
  user; never present an answer over a stale brain as current.
- **Absence of recall is not evidence of absence.**
- Never touch `~/.local/share/sia/.gbrain/` directly — PGLite is
  single-writer (the daemon). All agent writes go through `sia note` /
  the proposal queue. Reads retry around pulse locks automatically.
- The cockpit is SUPER+SHIFT+B; full docs:
  `~/.config/omarchy/plugins/khephri.sia/docs/MANUAL.md`.
