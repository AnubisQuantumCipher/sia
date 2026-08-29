# Changelog

## 1.2.0 — 2026-08-29

The skills-organ release: the brain now knows what its agents can do.

- **Skills organ (15th sense)** — `sense_skills` scans the personal
  skill roots (`~/.claude/skills`, `~/.agents/skills`, `~/.omp/skills`,
  `~/.copilot/skills`, `~/.config/agents/skills`; override via config
  `skills.roots`) every pulse, dedups by skill name, and diffs against
  a snapshot carried in the cursor state — so the snapshot commits only
  after the corpus write, like every other sense. Installs, updates
  (SKILL.md mtime), and removals become events under `organs/skills`,
  and every skill is its own evidence page `skills/<name>` carrying the
  `description:` from its frontmatter (YAML block scalars `>`/`|`
  handled). First catalog on this box: 35 skills, one pulse.
- **Skill nodes in the cockpit graph** — pages of type `skill` get
  their own color and a sixth legend/filter chip; the graph status line
  moved one line up so the wider legend row no longer collides with it.
- Skill descriptions pass `clip()`/`redact()` at the sense boundary, so
  a hostile SKILL.md cannot inject wikilinks, markdown structure, or
  secret-shaped spans into the corpus.


## 1.1.0 — 2026-08-29

The "grows the proof, not the costume" release. Four additions, each
deterministic, none adding a cognitive claim:

- **Evidence-derived take proposals** — a successful fabric heal
  auto-proposes "this heal will hold" with confidence
  `clamp(held/judged, 0.55, 0.95)` from that action's own corpus
  history (prior 0.70 under thin history). Proposals queue; only
  `sia take --accept` commits. The calibration population now grows
  by itself without loosening propose-don't-mint.
- **Nightly recall self-bench** — the dream runs a date-seeded sample
  of the corpus-ground-truth question set and appends hit@5/MRR to a
  trend the cockpit plots (BELIEFS → RECALL TREND). A falling line
  says: run the full `sia bench`.
- **Cross-organ coincidence thoughts** — two organs breaking their own
  empirical bands in the same window becomes a ⋈ thought stating both
  counts and the pair's sighting ordinal — an observation, never a
  cause. Pair history accumulates for a future (measured) hypothesis
  lane.
- **Prospective memory** — `sia intend "…" --by DATE`: dated
  commitments as corpus pages, surfaced at ≤48 h, nagged daily when
  overdue (➤, urgent), closed only on the operator's word. A due-date
  lane, not a mechanism.

Also: Codex CLI sessions are a first-class organ (metadata only);
`sia verify` reports gbrain pin drift; cockpit text is native-rendered
and pixel-aligned (no scroll shimmer); BELIEFS panel wraps correctly;
10 new unit tests (24 total) run in CI. The whole release was
adversarially reviewed pre-push (13 confirmed findings — including a
non-ASCII intent-close crasher, a proposals-file writer race now closed
with an flock shared by daemon/CLI/MCP, and a pulse-killing status
export — all fixed and regression-tested).

## 1.0.0 — 2026-08-29

**First public cut** of a reference deployment — not settled science.
The verification record in the whitepaper is a lab notebook (defects
found and fixed in review, one take graded, a 13-question corpus-
conditioned bench); calibration awaits a population of graded takes.
Run it on a machine you can watch. The instruments (`sia bench`,
`sia judge-audit`, `tests/`) are shipped so you can check it yourself,
not take the notebook's word.

- 6 base senses (pacman, journald, git, agent sessions, notifications,
  Quattro agent meters) + auto-detected optional integrations + config-
  driven custom senses for your own programs.
- gbrain/PGLite brain with local Ollama embeddings; git-versioned corpus
  as the source of truth; custom schema pack with typed link verbs.
- Deterministic cognitive core: source-weighted ACT-R activation, Hebbian
  bonding with nightly hygiene, PPR tie-breaker retrieval (benchmarked),
  novelty gating, empirical-band surprise incl. absence detection,
  7-slot global workspace, weekly consolidation with rarity-based
  flashbulb preservation, seeded lateral-bridge musing.
- Outcome learning: takes → configurable LLM judge (codex/claude CLI,
  abstention-audited) → Brier calibration; agents propose, humans commit.
- Ed25519 hash-chained run ledger (fsync-hardened); ingest redaction;
  truth-boundary footers; measurement instruments (`sia bench`,
  `sia judge-audit`).
- Omarchy Quattro plugin: bar widget + full-screen cockpit (radial-time
  graph, inspector with edge provenance, thought stream, SOURCE HEALTH).
- MCP server + agent skill for Claude Code, Codex, Grok, OMP, and any
  MCP-capable harness.
