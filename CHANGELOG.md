# Changelog

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
