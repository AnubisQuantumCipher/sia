# SIA — the Omarchy Brain

*Sia: the Egyptian personification of perception, who rode the solar barque
beside Hu and Heka.*

**Give your machine a memory.** SIA is a persistent, associative,
self-consolidating memory system for your Linux desktop. A resident daemon
tails the evidence your machine already produces — package installs,
journal errors, git commits, agent sessions, notifications, and any log
you point it at — into a git-versioned markdown corpus, indexed into a
typed knowledge graph with **local** embeddings. It remembers, connects,
thinks, dreams nightly, makes falsifiable predictions, and is **graded**
on them. You can watch it think, and you can ask it anything.

![The SIA cockpit](assets/cockpit.png)

Everything stays on your machine. No cloud calls, ever, except the ones
*you* configure for the optional judge (your own Codex or Claude CLI
subscription).

## What you get

- **A memory that accretes** — every event becomes a page in a git repo
  (*the corpus IS the brain*; the database is a rebuildable index), wired
  into a typed knowledge graph by [gbrain](https://github.com/garrytan/gbrain)
  with local `nomic-embed-text` embeddings via Ollama.
- **A mind, not just an index** — mechanisms from the memory literature,
  all deterministic, all behavior-defensible: importance decays with time
  and grows with world-originated use (ACT-R); co-recalled memories bond
  (Hebbian, with nightly decay and degree caps); recall spreads through
  the graph (Personalized PageRank as a benchmarked tie-breaker); genuine
  novelty and out-of-band activity — including the *silence* of a paced
  source — become thoughts; a 7-slot workspace holds its current
  attention; old episodes consolidate into weekly gists while rare
  high-severity days stay verbatim forever.
- **Outcome learning** — register falsifiable predictions with confidence
  and deadlines; an LLM judge grades them strictly against recalled
  evidence (TRUE / FALSE / UNRESOLVABLE — abstention audited); Brier
  calibration is pure arithmetic. Successful self-heals auto-*propose*
  hold-predictions with confidence computed from their own history — you
  commit each one by hand. Your machine keeps score on its own judgment,
  and on yours.
- **Prospective memory** — `sia intend "rotate the keys" --by 2026-10-01`:
  commitments the brain surfaces as their deadlines near and nags about
  when overdue, closing only on your word. And every night the dream runs
  a small recall **self-bench** whose trend the cockpit plots — the
  historian keeps receipts on its own memory.
- **A mission-control cockpit** — full-screen Quickshell overlay
  (`SUPER+SHIFT+B`): the living graph with radial time, hover
  neighborhoods, edge explanations, a thought stream, evidence-chain
  verdicts, and a SOURCE HEALTH truth boundary that admits incompleteness
  instead of hiding it. Plus a bar widget with the live event count.
- **Agents everywhere** — an MCP server (`sia_ask`, `sia_note`,
  `sia_propose_take`, …) mountable in Claude Code, Codex CLI, Grok, and
  anything MCP-capable, plus a skill for skill-reading harnesses. Agents
  read memory, leave labeled notes for future sessions, and *propose*
  predictions — only you commit them.
- **Evidence culture** — SIA keeps its own Ed25519 hash-chained run
  ledger; every answer carries a truth-boundary line; results are labeled
  `evidence` / `derived` / `model`; secret-shaped spans are redacted at
  the sense boundary; *absence of recall is never evidence of absence*.

## Install (Omarchy)

```bash
omarchy plugin add https://github.com/AnubisQuantumCipher/sia
cd ~/.config/omarchy/plugins/khephri.sia && ./install.sh
```

or standalone (CLI + MCP work without the Omarchy shell):

```bash
git clone https://github.com/AnubisQuantumCipher/sia && cd sia && ./install.sh
```

The installer sets up bun + gbrain, local Ollama embeddings, a fresh
brain with **your own keys and an empty corpus**, backfills your
machine's existing history as its first memories, starts the daemon,
enables the plugin and `SUPER+SHIFT+B`, installs the agent skill, and
registers the MCP server in whichever harnesses you have.

Requirements: Linux (Omarchy/Arch tested; x86_64 or aarch64), python3 +
python-cryptography, git, curl, ~2 GB disk for Ollama. Optional: the
Omarchy 4.x shell for the cockpit; a Codex or Claude CLI subscription
for the judge.

## Sixty seconds after install

```bash
sia status                          # the brain's vitals
sia ask "what happened today"       # semantic recall, cited + labeled
sia think                           # its inner monologue
sia take "the build will go green" --confidence 0.8 --by 2026-09-05
sia intend "rotate ledger keys" --by 2026-10-01   # prospective memory
sia note "hard-won context" --from me    # a memory for future sessions
```

Point it at your own programs in `~/.config/sia/config.json`:

```json
{ "custom_senses": [
    { "name": "myapp", "path": "~/logs/app.log", "type": "lines",
      "match": "ERROR|FATAL", "kind": "error", "tags": ["failed"] } ] }
```

## Documentation

- [**Field Manual**](docs/MANUAL.md) — cockpit tour, full CLI, thought
  glyphs, how the learning works, operations, troubleshooting.
- [**Whitepaper**](docs/WHITEPAPER.md) — architecture, the evidence
  model, every cognitive mechanism with its published formula and
  citation, the measurement instruments (`sia bench`,
  `sia judge-audit`), and the verification record.

## What this is (and is not)

A local, git-backed, origin-labeled memory that refuses to pretend a
language model is a witness. **It is not a brain** — it is a disciplined
historian with a small associative index and a cockpit. That is better
than a brain: a brain you cannot audit, a historian you can. The
cognitive-science names in the design are *ancestry, not warrants* —
every mechanism is a small, named, deterministic approximation, and the
whitepaper's rename test governs them.

## Honesty principles (the actual design)

1. Every answer declares what kind of answer it is.
2. Absence of recall is not evidence of absence.
3. A system that fails open must say so (SOURCE HEALTH).
4. The model may summarize and grade — never mint facts.
5. Records, not content: metadata and evidence streams only; secrets
   redacted at ingest; message bodies, clipboards, and keys are never read.
6. Nothing is silently deleted: consolidation is git-recoverable and
   every act is ledgered.

## Credits

Built on [gbrain](https://github.com/garrytan/gbrain) by Garry Tan.
Cognitive mechanisms trace to Anderson (ACT-R), Collins & Loftus, Nader,
Lisman & Grace, McGaugh, McClelland/McNaughton/O'Reilly, Dehaene, and to
HippoRAG, Generative Agents, Zep, and Letta — citations in the
whitepaper; the names are ancestry, the behavior is the contract.

MIT © 2026 Khephri Labs
