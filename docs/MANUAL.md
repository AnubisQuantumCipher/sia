# SIA — The Omarchy Brain · User's Manual

*Sia: the Egyptian personification of perception, who rode the solar barque
beside Hu (utterance) and Heka (magic).*

SIA gives your machine an associative memory. Everything this computer
already records — package installs, journal errors, git commits, agent
sessions, notifications, and any log you point it at — flows into one
brain that remembers, connects, thinks, dreams, predicts, and is graded on
its predictions. You can watch it think, and you can ask it anything.

**Senses.** Six base senses work on any Omarchy/Arch box: pacman, the
systemd journal, git repos under `~/Projects`, agent-session metadata,
desktop notifications, and Quattro's agent usage meters. Optional
integrations (signed evidence chains and subsystem ledgers such as
JACKAL, SEKHMET, Custos, AEGIS, WORLDLINE, omarchy-guardian) activate
automatically when their data exists. And you can point SIA at YOUR own
programs with custom senses in `~/.config/sia/config.json`:

```json
{ "custom_senses": [
    { "name": "myapp", "path": "~/logs/app.log", "type": "lines",
      "match": "ERROR|FATAL", "kind": "error", "tags": ["failed"] } ] }
```

---

## 1. Sixty-second start

| Do this | You get |
|---|---|
| Look at the top bar | 󰧑 + a number = the brain and today's event count |
| Press **SUPER+SHIFT+B** (or click 󰧑) | the full-screen cockpit |
| `sia status` | one-screen state of the brain |
| `sia ask "what happened with wireplumber"` | semantic recall with citations |
| `sia think` | the brain's recent thoughts |
| `sia ponder` | a deep reflection over its memories by your configured judge model |

The brain's heartbeat (a "pulse") fires every 60 seconds. It dreams every
night at 03:33.

## 2. The cockpit

Summoned with SUPER+SHIFT+B; leaves with **Esc**, ✕, or
`omarchy-shell shell hide khephri.sia`.

**Header** — name, live state chip (`OK` / `THINKING` / `DEGRADED` /
`FAILED` / `STALE`), pulse number and age, clock.

**Left rail** (scrolls):
- **VITALS** — memories, links, events today, thoughts kept, mind traces
  (ACT-R–tracked memories) and Hebbian bonds.
- **PULSE ACTIVITY** — sparkline of the last ~90 heartbeats.
- **WORKSPACE — n OF 7 SLOTS** — the brain's *conscious contents*: the few
  memories that currently win the competition for attention (Global
  Workspace theory: ignition threshold, max two slots per organ,
  incumbents resist eviction). Click a slot to lock it in the graph.
- **ORGANS** — every sense, sorted by today's activity, with last-event age.
- **EVIDENCE CHAINS** — per-chain verification verdicts, SIA's own signed
  ledger head, last dream, and a **verify now** button that re-runs the
  real verifiers live.
- **BELIEFS** — open/due/graded predictions, mean Brier score
  (0.0 = prophet, 0.25 = coin-flip), and **RECALL TREND** — the nightly
  self-bench line (hit@5 over a date-seeded sample). A falling line
  says: run the full `sia bench`.
- **INTENTS** — prospective memory: open commitments with their
  countdowns; overdue turns urgent. (Panel appears once you have one.)
- **SOURCE HEALTH** — the truth boundary: snapshot completeness, memory
  counts by kind, any sense errors or sync failures. If something failed,
  it says so here instead of quietly looking complete.

**Center — the living graph.** Time is radial: the cortex at the center,
organs on the inner ring, every memory at a radius set by its age (oldest
inner, newest at the rim) with faint day rings. Nodes glow when freshly
touched.

- **Hover** a node → its whole neighborhood lights and labels; everything
  else dims.
- **Click** a node → lock the selection (click empty space to release).
- **Inspector** (right rail) → the locked/hovered memory's title, type,
  age, in/out degree, and every connection with its type *and the text it
  was extracted from* — why the edge exists.
- **Legend chips** are filters — click `memory`, `thought`, `entity`… to
  hide that kind.
- **⟲ replay** (or the **R** key) — animate the brain growing from its
  oldest memory to now.

**Right rail** — the inspector (above) and the **THOUGHT STREAM**, the
brain's inner monologue, newest first, urgent items in red.

**Footer** — latest-thought ticker and the key map.

## 3. The CLI

Everything lives under one command: `sia`.

### Asking and reading

```
sia status                    # one-screen state
sia ask "question"            # semantic recall: dense embeddings seeded
                              #   through the knowledge graph (spreading
                              #   activation) and re-ranked by ACT-R
                              #   activation. Recalling STRENGTHENS the
                              #   memories returned (reconsolidation).
sia recall <slug>             # read one memory page verbatim
sia think                     # recent thoughts
sia graph                     # graph snapshot statistics
sia context                   # bounded context pack for agents/sessions
```

Notes on `ask`: results show a blended score; "no matches" is not proof of
absence — the brain only finds what shares meaning with your words. If
ollama is down, search degrades to keyword-only and says so.

### Deep thinking (the configured judge — your own Codex or Claude CLI)

```
sia ponder                    # open-ended reflection over recent memory
sia ponder "question"         # focused reflection
sia deep "question"           # same as ponder with a required question
```

Ponder writes a labeled `synthesis/…` page and drops a ✦ thought. It may
end by *proposing* predictions — proposals wait in a queue and are not
memories until you commit them with `sia take --accept <n>|all`
(a model that mints the takes it later helps grade is too neat a loop).
Model output never masquerades as deterministic thought: every synthesis
is labeled with the model that produced it.

### Predictions and grading (outcome learning)

```
sia take "claim" --confidence 0.8 --by 2026-09-05 --domain crash-cause
sia takes                     # list all predictions and status
sia grade                     # grade everything due now (configured judge)
sia grade <id>                # grade one take regardless of due date
sia calibration               # Brier scorecard per domain
```

A take is graded strictly against recalled evidence: **TRUE**, **FALSE**,
or **UNRESOLVABLE** — the judge (configured in `~/.config/sia/config.json`: your Codex or Claude CLI) is forbidden from guessing, and a failed
evidence lookup yields an honest UNRESOLVABLE, not a coin flip. Brier
scoring and calibration are pure arithmetic. The nightly dream grades up
to three due takes on its own.

**Evidence-derived proposals.** When a self-healing integration reports
a successful heal, the brain *proposes* a hold-take on its own: "this
heal will hold — no repeat within 7 days," with a confidence computed
arithmetically from that action's own history in the corpus (fraction
of past heals that held; prior 0.70 under thin history). No model is
involved, and nothing is committed until you run `sia take --accept` —
this is how the calibration population grows without loosening the
propose-don't-mint rule.

### Intents (prospective memory)

```
sia intend "rotate the ledger keys" --by 2026-10-01
sia intend --list             # open intents with countdowns
sia intend --done <id> [note] # close one, on your word only
```

The one thing a pure historian lacks: remembering **to do**, not just
what happened. An intent is a corpus page like any memory; the brain
surfaces it as a thought when the deadline is within 48 hours and nags
once a day when overdue (urgent, red). It never closes an intent
itself — that is a due-date lane, not a mechanism.

### Integrity

```
sia verify                    # re-verify every signed chain with its own
                              #   keeper's verifier, live
sia ledger                    # SIA's own signed run ledger: head + verify
```

### Maintenance (daemon must be stopped first)

```
systemctl --user stop sia-brainstem
sia pulse                     # run one heartbeat by hand
sia dream                     # run the nightly cycle now (consolidation,
                              #   musing, grading, self-bench, gbrain dream)
systemctl --user start sia-brainstem
```

## 4. Reading the thought stream

| Glyph | Kind | Meaning |
|---|---|---|
| ⛓ | integrity | a signed chain's verification state changed |
| ✚ | healing | a self-healing integration acted (optional) |
| ∅ | refusal | a subsystem refused rather than guess (optional) |
| ≻ | collapse | a WORLDLINE reality collapsed (optional) |
| ✖ | crash | a coredump was observed (urgent, red) |
| ∎ | formal | a Lean-checked receipt entered memory |
| σ | anomaly | statistical cohort anomaly (real baseline only) |
| ◉ | attention | the most salient memory shifted |
| ✧ | novelty | something genuinely new appeared (first sighting, 30-day return, or isolation) |
| Δ | surprise | a count above everything its time-band has shown (sample size reported); includes **absence** for paced organs |
| ∞ | association | the nightly musing found two distant memories joined only by an obscure path |
| ☾ | dream | the consolidation cycle's report |
| ✦ | ponder | a judge-model synthesis landed |
| ⊢ | take | a prediction was registered, proposed, or came due |
| ⚖ | grade | a prediction was judged |
| ◎ | calibration | the running scorecard was restated |
| ⋈ | coincidence | two organs went out-of-band in the same window (a stated observation, never a cause) |
| ➤ | intent | a prospective-memory commitment is due soon or overdue |
| ≟ | bench | the nightly recall self-check reported its numbers |
| ✉ | note | an agent or the operator left a labeled note for future sessions |

Every thought is deterministic and cites its evidence — except ✦/⚖, which
are explicitly model-assisted and labeled as such.

## 5. How it learns (the short version)

- **The graph wires itself** — wikilinks in evidence become typed edges.
- **Bonds strengthen with use** — co-occurring and co-*recalled* memories
  gain Hebbian weight; every question you ask reshapes the brain.
- **Importance is learned from use** — ACT-R activation (recency +
  frequency, power-law decay) decides what surfaces and what sinks.
- **Rhythms are learned** — per-organ hourly baselines make surprise
  measurable against each band's own history (count vs previous max vs
  sample size), including the silence of a paced source; when two organs
  exceed their bands in the same window, the coincidence itself becomes
  a thought stating both counts — an observation, never a cause.
- **Sleep turns episodes into knowledge** — day memories older than 14
  days consolidate into weekly epochs; crash/refusal/integrity days stay
  verbatim forever (flashbulb rule); originals always remain in git.
- **Judgment is graded** — predictions meet outcomes; Brier calibration
  accumulates; ponder sees its own track record. Successful heals
  auto-*propose* hold-takes (deterministic confidence from their own
  history) so the calibration population grows — you still commit
  every one by hand.
- **Recall is measured nightly** — the dream runs a small date-seeded
  retrieval self-bench and plots the trend in the cockpit; the
  historian keeps receipts on its own memory.

## 6. Where everything lives

| Thing | Path |
|---|---|
| The memory itself (markdown, git) | `~/.local/share/sia/corpus/` |
| The brain index (gbrain/PGLite) | `~/.local/share/sia/.gbrain/` |
| Daemon + engine code | `~/.local/share/sia/bin/` |
| Signed run ledger + keys | `~/.local/share/sia/ledger.tsv`, `pub.hex` |
| Research reports | `~/.local/share/sia/research/` |
| Live snapshots (widget/cockpit) | `~/.local/state/sia/*.json` |
| Plugin (bar + cockpit) | `~/.config/omarchy/plugins/khephri.sia/` |
| Services | `sia-brainstem.service`, `ollama.service` (user) |
| CLI | `~/.local/bin/sia` |

**The corpus is the brain.** The database is a rebuildable index over it.
Back up `~/.local/share/sia/corpus` (it is a git repo — its history *is*
the brain's verbatim past) plus `ledger.tsv`/`pub.hex`/`key.hex`, and you
have everything. To rebuild the index from scratch:

```
systemctl --user stop sia-brainstem
mv ~/.local/share/sia/.gbrain/brain.pglite{,.old}
GBRAIN_HOME=~/.local/share/sia gbrain init --pglite \
    --embedding-model ollama:nomic-embed-text
GBRAIN_HOME=~/.local/share/sia gbrain sources add sia \
    --path ~/.local/share/sia/corpus
cd ~/.local/share/sia/corpus && GBRAIN_HOME=~/.local/share/sia gbrain sync --source sia
systemctl --user start sia-brainstem
```

## 7. Agents everywhere

Every agent harness on this machine can use the brain:

| Harness | Lane |
|---|---|
| Claude Code | MCP server `sia` (user scope) + the `sia` skill |
| Codex CLI | `[mcp_servers.sia]` in config.toml |
| Grok | `grok mcp add sia` |
| OMP (oh-my-pi) | the `sia` skill via ~/.claude/skills |

(`install.sh` registers each of these automatically where the harness is
present.)
| anything MCP-capable | `python3 ~/.local/share/sia/bin/sia-mcp` (stdio) |

MCP tools: `sia_ask`, `sia_recall`, `sia_status`, `sia_think`,
`sia_note`, `sia_propose_take`, `sia_calibration`. The server never
opens the database — reads go through the retrying CLI, writes through
the append-only queues the daemon drains. Agents propose takes; only
you commit them (`sia take --accept`). Agent notes are model-origin,
labeled, and weighted below evidence.

## 8. Troubleshooting

- **Bar icon dim / "brainstem not reporting"** —
  `systemctl --user status sia-brainstem`, then `journalctl --user -u
  sia-brainstem -n 30`.
- **`sia ask` says keyword-only** — ollama is down:
  `systemctl --user restart ollama`.
- **"already open through gbrain serve"** — something else holds the
  single-writer brain; SIA's own commands retry around the daemon's brief
  pulse locks automatically.
- **Widget vanished after an Omarchy update** — quattro upgrades can
  rewrite `shell.json`; run `omarchy plugin enable khephri.sia`.
- **Edited plugin QML but nothing changed** — the hot-reloader can serve
  stale code; `omarchy-restart-shell`. (Each shell restart may coredump a
  `hyprland-dialog` helper — an Omarchy quirk SIA will dutifully report
  as a crash thought.)
- **SOURCE HEALTH shows a sense error** — that sense failed this pulse;
  its events are safe (cursors only advance after durable writes) and it
  retries next pulse.

## 9. What SIA will never do

- Read your Claude/Codex **message bodies**, clipboard, password stores,
  or any private key. Senses ingest *metadata and evidence records* only —
  and secret-shaped spans (key blocks, tokens, JWTs, `.ssh` paths,
  password fields) are **redacted at the sense boundary**, before
  anything reaches the corpus or git; every omission is counted in
  SOURCE HEALTH and the `sia ask` boundary footer.
- Send anything to the cloud on its own. Embeddings are local (Ollama);
  the only model calls are the ones **you** trigger (`ponder`, `deep`,
  `grade`) or the capped nightly grading — all on your Codex
  subscription, all labeled.
- Silently delete. Consolidation compacts only what git provably holds;
  flashbulb days stay verbatim; the signed ledger records every act.
- Guess. Refusals, UNRESOLVABLE grades, and "snapshot partial" are
  first-class answers.

## 10. Uninstall

```
./uninstall.sh           # removes daemon/plugin/CLI; keeps your memory
./uninstall.sh --purge   # also erases the corpus, ledger, and keys
```

---

*Companion document: `WHITEPAPER.md` — the architecture, the science, and
the verification record.*
