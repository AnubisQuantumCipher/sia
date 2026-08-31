# Changelog

## 1.3.3 — 2026-08-31

- **Cockpit runtime compatibility hotfix** — the explicit live-readiness
  control now uses Quickshell `Process`'s public `started`/`running`/`exited`
  lifecycle rather than an unavailable Qt error callback. An unavailable
  local `sia` command therefore becomes an explicit `LIVE BLOCKED` result,
  and the whole v1.3 cockpit loads on the installed Omarchy shell.

## 1.3.2 — 2026-08-31

- **Cockpit fidelity pass** — preserves the graph-first Hermes Star Map and
  three-column layout while making the v1.3 cognitive and publication model
  visible at its real truth boundaries. A compact header ribbon now calls out
  the last-published graph snapshot, ledger transition, and projection debt;
  an explicit control runs the live `sia ready` predicate once instead of
  treating a healthy-looking snapshot as memory-read authorization. The UI
  retains and labels a last-known-good status/graph when an incoming snapshot
  is malformed; a live-check result is invalidated on close or new snapshot,
  missing debt is `unknown`, and a failed local readiness-command launch
  becomes an explicit blocked result rather than a stuck check.

- **Mind and agent operations made legible** — VITALS now surfaces active vs.
  demoted stability associations, SM-2 due/eligible review, pins, and the
  last-published durable agent handoff receipt. Workspace memories outside the
  graph's deterministic display window are marked `off-map` and remain
  unselectable there, rather than implying a missing graph node was selected.
  SOURCE HEALTH now carries publication debt, ledger-transition state, and
  nonempty retained-redaction counts.

- **Graph provenance and taxonomy** — the cockpit calls the displayed links
  corpus-linked relations, colors their type only for the inspected
  neighborhood, shows each node's persisted origin, and labels non-special
  graph records honestly instead of calling every package/project/note an
  entity. The full signed-ledger QA benchmark remains separately invoked by
  `sia bench`; the heuristic drift display does not impersonate answer scoring.

## 1.3.1 — 2026-08-31

- **Resident agent-queue deadlock repair** — the native thought-replay
  finalizer no longer opens a second exclusive lease for
  `agent-inbox/.queue.lock` before calling the queue's already
  lock-serialized `pending()` snapshot API. On Linux, independent `flock`
  file descriptions are not re-entrant: a brainstem that encountered an
  existing agent queue could block forever on its own lock after first-pulse
  status and memo publication, leaving memory truthfully stale. The repair
  takes exactly one queue lease and adds a regression guard that fails
  immediately on any nested acquisition rather than allowing a runner to
  hang. Existing request files remain authoritative retry input; deployment
  replaces the blocked brainstem through the normal lifecycle barrier.

## 1.3.0 — 2026-08-31

- **Race-closed systemd lifecycle barrier** — Install and uninstall no longer
  depend on a runtime mask that a local `~/.config/systemd/user` unit outranks.
  After exact unit-ownership-or-absence preflight they publish a descriptor-
  verified, no-follow runtime drop-in whose cleared/false
  `ConditionPathExists` blocks indirect activation and whose
  `RefuseManualStart` blocks explicit starts.
  Fresh installation provisions the drop-in while the unit is absent, then
  publishes, reloads, and attests the combined manager state before first
  light. Final activation atomically retires the `.conf` to a non-drop-in
  sibling, restores it on failure, and keeps that recovery copy until the live
  daemon executable and arguments are verified. Uninstall uses the same
  barrier and targeted exact-file cleanup, preserving operator drop-ins and
  retaining either the active guard or its exact retired recovery copy after
  incomplete removal. The documentation names the mechanism's same-UID,
  coordination-only threat boundary.

- **Crash-recoverable launch fence and owned-tree publication** — before an
  upgrade can mutate dependencies, the installer journals the exact existing
  CLI, brainstem, and MCP launcher generations and changes those inodes to
  mode `000`. Retried installs validate a lifecycle tombstone, an exact journal
  schema, unique bound paths, and the fenced inode identities. Single-file CAS
  recovery now runs before CLI ownership preflight and can validate an
  unreadable fenced file only from its metadata plus a journal-bound digest;
  moved generations tolerate only rename-induced metadata changes. Runtime and
  CLI preflights run again after the fence so their later CAS tokens include
  the `chmod` generation, and an already fenced CLI is not copied into another
  retained backup. Interrupted archive and publication phases recover the
  exact old or new generation while preserving independent replacements.
  Descriptor-rooted tree CAS now accepts the relative shared-library links in
  official runtime archives, but only when the private owned tree is stable,
  every regular file is single-link and non-group/world-writable, each symlink
  inode is itself stable/current-user-owned/single-link, each link is relative
  and non-escaping, and its complete chain ends at such a safe regular file.
  A post-walk pass now reopens every captured directory generation and rereads
  every link generation and target before and after referent acceptance, so a
  nested replacement cannot be accepted through a cached link target.
  Absolute, escaping, dangling, group/world-writable, hard-linked, and special
  entries refuse. gbrain self-upgrade verification now accepts only
  the pinned CLI's exact combined `off` plus provenance output, including its
  one exact DB-plane-shadowed variant; unexpected stdout or stderr refuses.

- **Legacy-state convergence without provenance guessing** — the graph
  projector now treats the corpus-root `README.md` as repository metadata,
  not a memory page. It retires only the byte-exact obsolete README refusal
  from an older projection state and preserves every candidate and unrelated
  error. A pre-v1.3 thought inbox whose rows lack both queue metadata fields
  receives deterministic identities from stable file bytes, modification
  time, and row position, plus a queued timestamp from that file time; the
  result is unchanged when the inbox is renamed into its draining claim.
  Fully modern and metadata-free legacy rows may coexist row by row. When
  origin is absent, legacy `note`, `ponder`, and `grade` prose plus `take`
  proposal notifications default to `model`, while other admitted kinds retain
  the historical `derived` default;
  an explicitly present canonical origin is validated and preserved. Partial
  queue metadata, unknown fields, and malformed modern identities still refuse
  the whole inbox. When a current source row collides byte-for-byte with a
  pre-identity event line, SIA still refuses to mint a guessed occurrence ID;
  it now signs a `legacy-event-identity` terminal refusal before advancing that
  source cursor, instead of retrying the unresolvable compatibility boundary
  forever.
  Runtime-loading tests now activate one process-wide temporary home before
  importing SIA, and a regression guard checks recognized runtime-loading
  patterns plus the currently enumerated import-time mutable paths so covered
  fixture defaults no longer point into the resident brain. New runtime modules
  or import-time path constants must be added to those enumerations.
  The extracted gbrain-bootstrap and corpus-bootstrap installer harnesses now
  source owner-private temporary test scripts instead of passing growing
  function bundles through `bash -c` or standard input, keeping the complete CI
  run independent of host argument-size and script-pipe behavior. The
  descendant-exit regression probe now treats a process that vanishes during
  its own `/proc` state read as completed rather than as a false test error.
  Installer and uninstaller process runners now use the already registered
  pollable pidfd as their non-reaping exit notification, retaining `P_PID` plus
  `WNOWAIT` only as the fallback; they no longer issue a redundant
  `waitid(P_PIDFD)` probe that
  was the interpreter crash site on one clean Python 3.12 runner.

- **Explicit readiness attestation and convergent bounded publication** —
  `sia ready` now evaluates the live memory-readiness predicate while holding
  the corpus-owner lease, emits a stable ready/not-ready line, and exposes the
  verdict as its process exit status. The installer calls that exact newly
  published CLI after its fatal first-light pulse and before desktop, MCP, or
  service activation. First light's `SIA_BACKFILL=1` path now advances both
  take and intent natural-history authorities until their scan/sweep and shared
  audit work converge, with a finite generation ceiling. Graph publication no
  longer advances only one cursor page outside first light: every normal
  publication holds the corpus lease while draining successive bounded pages
  to a complete generation, also under a finite aggregate ceiling. Large
  active corpora therefore do not alternate between a recovery-only partial
  graph and the next pulse's newly dirtied graph; churn or permanent refusal
  remains named publication debt.

- **GitHub release documentation and clean-runner closure** — the README and
  manual now expose the completed v1.3 capability map, dual typed-edge lanes,
  exact Claude/Codex/Grok MCP registration commands and durable generic-client
  guard, configurable skill roots, calibration-domain continuation, repeatable
  benchmark chain selection, readiness recovery taxonomy, and graceful-
  degradation matrix. The whitepaper now states the actual always-on
  release-selected PPR policy and installer-controlled index rebuild boundary.
  The public docs also record community-directory readiness without claiming a
  listing: the public repository has the required root artifacts, documents the
  successful local release-preparation validation as non-commit-bound, and
  requires a rerun against the exact approval-gated Omarchy submission commit.
  Its ownership checklist still requires explicit maintainer confirmation, and
  validation is not a security review.
  `sia calibration --cursor` and the MCP tool's optional `cursor` now make the
  documented bounded domain continuation usable. The signed-ledger projection
  fixture binds the checkout keeper so a clean CI runner cannot depend on an
  ambient installed SIA. Cursor length is bounded at the MCP, CLI, and history
  parser boundaries, and rehearsing a suppressed unverified-JACKAL page now
  reports its no-reinforcement boundary instead of claiming a queued touch.

- **Non-destructive stability and rehearsal** — nodes and learned edges now
  carry an exponential retention lens that changes retrieval salience, never
  evidence retention. Operator-pinned or high-arousal pages—including pages
  raised by safety-class and urgent signals—enter a deterministic SM-2
  schedule; interaction-derived quality tiers are labeled as proxies, and
  schedule/reinforcement state advances only after a successful re-embedding.
  `sia memory`, pin/unpin, and `sia rehearse` expose the state without
  introducing another mind-state writer. Numeric state is finite and
  operationally capped, pin-only review state disappears on unpin, and
  interval calculation/lapse behavior follows the original SM-2 ordering.
- **Resident-agent memory surface** — the stdio MCP server now advertises
  static status/thought/calibration/cortex resources plus the guarded
  `sia://memory/{slug}` template. Tools carry bounded schemas, behavior
  annotations, structured content, and protocol errors. Agent notes use
  immutable mode-0600 request files; the brainstem materializes each note as
  model-origin prose and acknowledges the exact processed inode only after
  corpus commit, index sync, and durable queue removal. Every SIA-managed
  PGLite call shares one cross-process owner lease; full pulse/dream cycles and
  explicit operator corpus mutations share a transaction lease, and a lifetime
  brainstem lease refuses a second resident;
  the separate `sia_search` tool provides no-touch read-only retrieval for
  audits and MCP evaluations.
  It supports legacy negotiation through `2025-11-25` plus the stateless
  `2026-07-28` `server/discover` protocol, with revision-aware batch refusal,
  validated optional client metadata, modern result metadata, and cache-scope
  hints. Request-only notifications never execute tools, and resource failures
  retain protocol-level not-found, invalid-request, and infrastructure
  distinctions. Newline requests, batch cardinality, captured CLI output, and
  serialized responses are independently bounded.
- **Reproducible, ownership-aware bootstrap** — SIA installs a private pinned
  Bun, fetches gbrain by its full commit, verifies the frozen upstream lockfile,
  and compiles the installed gbrain executable from that checkout. Bun and
  Ollama archives are SHA-256 verified before extraction; the Ollama service is
  checked for the expected executable, service PID, loopback-only listener,
  model manifest, and every referenced content-addressed blob. Install and
  uninstall use lifecycle/brainstem/corpus/PGLite leases, no-follow managed-root
  checks, content receipts, durable generation-bound no-clobber file/tree
  publication, exact legacy-corpus recognition plus explicit consent for
  unrecognized adoption, durable generation/HEAD-bound `corpus-bootstrap` and
  `corpus-adoption` intents, off-path generation-bound no-clobber publication
  for a fresh absent corpus, and v2 corpus receipts bound to the canonical
  root's stable device/inode/mode/owner identity. Exact path-only receipts
  migrate once through a crash-resumable generation-CAS transition held under
  both lifecycle and corpus-owner leases; pre-lock inspection is read-only,
  mismatched v2 roots never auto-rebind, and the returned legacy generation is
  verified before retirement. The bootstrap also provides an exact crash-resumable
  `key → matching public key → signed GENESIS:init → matching head`
  ledger prefix, and an off-path `gbrain-bootstrap` with durable initialization
  and probe phases, post-probe generation binding, generation-CAS publication,
  and attributed recovery. The installer exercises
  actual pidfd, Ed25519 raw-signing, `renameat2`, and
  `O_TMPFILE`/`linkat` capabilities before managed-payload activation.
  Manual-only MCP client mutation retains exact inspection
  and non-ownership guards; plugin discovery is exact after an Omarchy rescan;
  external-command capture and deadlines are bounded; removal preserves
  consumers. A
  failed late upgrade leaves the brainstem disabled rather than running mixed
  dependencies. CI discovers the complete test suite, checks all Python entry
  points, validates shell syntax, and installs hash-pinned test dependencies.
- **Population-aware calibration guardrails** — Brier scores are recomputed
  with deterministic decimal arithmetic; single cases and small series cannot emit a
  judgment-quality headline, sparse confidence bins are withheld, both
  outcome classes are required for the machine-readable monitoring-eligibility
  flag, and excluded UNRESOLVABLE or malformed grades stay visible. Labeled
  case/aggregate metrics remain visible below the gate, which is a descriptive
  UI policy rather than statistical significance.
- **Bounded natural-history projections** — take and intent pages remain the
  source of truth while owner-private digest-bound direct rows, capped open
  sets, append-only paginated catalogs, and sharded calibration sufficient
  statistics remove whole-history scans from pulse, due, intent, readiness,
  and scorecard paths. Creates/closes use durable page/projection journals;
  signed grades project only after their exact keeper row is observable.
  Existing corpora enter through resumable directory-generation-bound pages
  with journaled-mutation overlay and a no-addition convergence pass. Unsigned
  legacy resolutions stay visible outside score denominators, and CLI history
  is cursor-paginated. Recurring bounded authority scan/catalog-sweep
  generations now reconcile external edits, repairs, replacements, and
  deletions. WAL-backed tombstones subtract exact prior sufficient statistics;
  edited resolved pages regain a scored contribution only when their exact new
  bytes have an observable signed grade, and readiness/calibration refuse
  incomplete or unstable authority checkpoints. Ready take and intent
  checkpoints now enter a shared, explicitly incomplete audit cycle before
  reading any row. Only the paired scheduler's leader may open a fresh cycle;
  its follower joins or finishes the active cycle and cannot immediately reopen
  another. Catalog limits and directory identities are pinned across
  crash-resumable slices; tombstones advance each cursor, a faster participant
  waits ready for its sibling, and global ready returns only after stable
  reloads find no catalog growth or pending transaction.
  Same-inode edits after the final observation remain an explicit nonclaim
  until a later pinned audit reaches them.
- **Explicit origin boundary** — new persisted memories use only `evidence`,
  `derived`, or `model`; outside the signed take cutover below and the bounded
  pre-publication thought-inbox compatibility mapping above, missing,
  malformed, or ambiguous legacy metadata is exposed as `legacy-unlabeled`,
  never promoted to evidence, and weighted like model prose. When an inbox row
  has no origin, the compatibility default maps known model-prose producer kinds
  to `model` and retains the historical `derived` default for its other
  accepted kinds; that default never mints `evidence`. An explicitly supplied
  canonical origin is validated and preserved.
  Judge-grade/ponder thoughts, take-proposal notifications, and agent/operator
  notes are `model`; deterministic Brier and ledger-transition arithmetic remain
  separate derived operations. Model and legacy-unlabeled thoughts cannot
  mint typed relations. JACKAL convenience-ledger rows and receipt filenames
  are explicitly unverified `derived` observations: claimed formal status is
  not inherited, categorical legacy assurance is suppressed, and these pages
  cannot serve as grading evidence. The retired formal glyph no longer implies
  front-door receipt verification from file presence.
- **Signed legacy-take cutover and read gate** — the required installer
  first-light pulse labels current-schema pre-origin open takes
  `origin: derived` and resolved takes `origin: model`, making historical judge
  explanations inert. Exact v1.2 producer pages enter a separately labeled
  compatibility normalization; malformed graded pages refuse instead of being
  guessed, and invalid legacy open deadlines remain visibly blocked from
  grading. Owner-private journals in
  `~/.local/state/sia/take-migrations/` bind source and target digests. The
  exact target is signed as `MIGRATE:take-origin` with `model-inert-v1` or
  `legacy-v1-normalize` before `sync_needed` is persisted and the corpus page
  is atomically replaced. First light then commits git, syncs PGLite, exports
  the graph, and clears the marker last, before desktop/MCP/service integration.
  Memory-dependent CLI and MCP reads refuse until a successful `sia pulse` has
  reconciled publication; status keeps a live readiness line over its
  last-published pulse/graph snapshot.
- **Generalized write-ahead publication and generation-stable reads** — every
  shipped SIA corpus writer — `pulse`, `dream`, `take`, `intent`, `grade`, and
  `ponder` — now holds the corpus transaction lease and persists `sync_needed`
  publication debt before any page create, rewrite, or unlink. The marker
  clears only after git commit or clean verification, PGLite sync, and graph
  export all succeed. Readiness also blocks pending
  `~/.local/state/sia/grade-transactions/` journals. Gated CLI commands retain
  the lease from the readiness check through the returned result, and MCP
  memory calls inherit that subprocess boundary, so each answer comes from the
  same corpus generation. Pulse sequence reservation shares the heartbeat's
  lease, and DREAM settles between memory-backed phases and around each grade
  before later indexed-memory work.
- **Custom-sense field privacy and bounded exclusion** — JSONL custom senses
  now refuse and digest-bind a physical record whose configured field is
  absent. They never fall back to rendering the raw object or unrelated
  fields, and the next record remains reachable after the refusal is signed.
  `match` and the new `exclude` field use the same finite literal-alternative
  grammar; neither evaluates regular expressions, and invalid configuration
  leaves the source cursor unchanged.
- **Fail-closed grading evidence** — completed-empty evidence retrieval may be
  judged UNRESOLVABLE, while a failed or malformed retrieval now refuses
  before invoking the judge, writes no grade, and leaves the take open.
- **Honest nightly retrieval tripwire** — the small date-seeded legacy probe
  now exports explicitly heuristic slug-match/reciprocal-rank fields and
  non-claims. Dream receipts, thoughts, and the cockpit label it as slug drift;
  only the signed-ledger QA benchmark scores reader answers. Pre-bounded
  oversized or malformed trend history is upgraded from a stable no-follow
  tail, compacted to recent complete rows, and visibly marked as legacy
  truncation without stranding receipt settlement or readiness.
- **Signed-ledger QA self-benchmark** — keeper-accepted ledger snapshots with
  observed no-follow byte, inode, metadata, and verifier-digest checks
  now generate extraction, temporal, update, multi-event aggregation, and abstention
  questions with row/head provenance. Question-only exports are separated
  from mode-0600 digest-bound answer keys outside the corpus. Source slugs,
  observed timestamps, chain/file provenance, and witness bindings live only
  in owner-private artifacts; the mode-0600 private manifest also binds the
  allow-listed public manifest, public IDs are answer-independent, and the
  publication audit canonicalizes compatibility-Unicode plus repeated URL/HTML
  encodings before checking private dates and slugs. Conflict grouping and IDs
  share that consumer view; unsafe control, bidi-format, surrogate, and
  noncharacter text cannot enter public question/XML fields.
  Present-question retrieval now requires a returned source-page chunk to
  carry its private digest-bound exact event excerpt; page slug/title matches
  alone are wrong evidence, and aggregate counts require all contributing
  event excerpts in the scored window.
  Thresholds are fit only on a deterministic calibration split, unidentified
  thresholds are unscored, and missing answers never count as `ABSTAIN`.
  Unknown, rejected, and empty runs refuse. Source-page bytes are digest-bound
  into dataset identity and revalidated before and after live queries under the
  corpus-owner lease. The reserved Custos built-in retains its legacy
  canonical-Unix, full-signed-line SHA-256 grammar and records that format and
  its native hashes in provenance; other/custom chains remain strict
  attest-ledger v1. Custom-chain intake also binds the configured verifier to
  the executable position (or the immediate script operand of SIA's current
  Python interpreter) and rejects merely mentioning it later in an unrelated
  command. Exact ledger argv membership does not prove that arbitrary custom
  code semantically consumes the argument. The checks explicitly do not claim
  to exclude same-user in-place ABA between observations.
- **Domain-typed corpus edges** — the graph exporter now loads every
  `link_types[].inference.regex` rule from SIA's validated schema pack and
  applies it to explicit wikilinks at Markdown-record scope. Link targets are
  masked before matching (so an entity named `diagnose-crash` cannot mint a
  crash relation), only explicitly `derived` integrity/healing/crash/refusal
  thoughts can inherit their cited evidence sentence, and model/legacy thoughts
  and entity-description pages remain neutral. A malformed/unsafe pack falls
  back to `mentions` while marking the graph snapshot partial. That fallback is
  exclusive to the schema-regex lane. The standard gbrain person/company
  gazetteer lane now runs separately after each sync (`--by-mention --ner`,
  source-scoped to SIA); its failure fails brain sync and retains publication
  debt instead of invoking the regex fallback.
- **Bounded long-horizon projections** — the nightly slug tripwire now probes
  only its fixed pages and bounded organ directories, with no recursive corpus
  walk and an explicit refusal when a negative probe cannot be established.
  Graph publication uses a durable, no-follow directory cursor and retains
  only the capped cockpit window; supported corpus writers restart that
  projection before mutation, and publication/read readiness remain closed
  until the generation is fully scanned without refusal. Valid nodes and
  unique display edges beyond the deterministic cockpit caps now publish as
  complete-with-omissions, with separate counts and an explicit non-absence
  boundary; PGLite remains the full recall surface. Weekly
  consolidation likewise advances a durable bounded cursor, persists exact
  per-day source claims before any epoch mutation, and never treats a partial
  directory page as evidence that a source disappeared. Its eligibility
  cutoff is pinned for the entire incomplete generation and rolls forward only
  after the cursor and admitted work converge. First-light may drain
  bounded graph batches, but has a fixed convergence ceiling and preserves
  named debt on refusal. An incomplete consolidation generation now retains
  its originating DREAM marker and exact ledger binding; each pulse recovers
  one bounded unit, while the marker remains unapplied and unsigned through
  every claim batch and post-removal rescan. Readiness returns only after the
  persisted cursor, candidate queue, and claims converge. Every gbrain query,
  sync, extraction, embedding, and DREAM invocation now shares one combined
  stdout/stderr byte ceiling, strict UTF-8 admission, deadline, and fresh
  process-group cleanup; output overflow, malformed encoding, and surviving
  descendants refuse without unbounded resident-process capture.
- The schema pack now declares the `skill` entity type introduced with the
  skills organ, preventing skill descriptions from being treated as relation
  records.
- **Forecast and keeper integrity** — new takes and queued proposals require a
  deadline strictly after their UTC commit date. The tool-free Claude grader
  is disabled by default, requires an explicit model identifier when enabled,
  records `claude:<model-id>`, and is blinded to forecast confidence; Codex
  grading refuses at the local-read boundary. Judge input and combined output
  are bounded with concurrent pipe draining and process-group termination;
  invalid answer encoding refuses. Take/proposal records reject
  non-finite confidence, neutralize terminal control characters, and use
  bounded aggregate spools.
- **Crash-safe signed transitions and bounded state** — the SIA ledger binds
  its signer to the public key before mutation, durably journals one pending
  row, appends with `O_APPEND` plus `fsync`, atomically advances the pin, and
  repairs only an exact independently verified torn suffix. Pulse and dream
  lifecycle facts first enter a bounded immutable transition queue, survive a
  keeper failure, and acknowledge source requests only after the exact signed
  row exists. Note, touch, proposal, and transition queues have both item and
  aggregate-byte ceilings; malformed or symlinked authoritative state refuses
  without following or silently resetting it. Configured and partially
  installed evidence chains remain visible as refusals instead of silently
  shrinking verification scope. Transition occurrence IDs distinguish
  identical lifecycle facts while exact crash recovery remains idempotent;
  pulse sequences are reserved durably before effects.
- **Fixed-slot publication and touch-tail recovery** — corpus/state snapshots,
  take journals, agent requests, mind state, and benchmark artifacts now use
  one owner-private, no-follow, same-filesystem staging slot outside each
  scanned authority instead of randomized sibling temporary files. A killed
  writer can leave only that fixed slot, and retries close every file and
  directory `fsync` boundary. Touch producers use bounded atomic whole-file
  RMW under their queue lease. A legacy unterminated physical record is first
  recorded by exact generation, offset, full-file digest, and suffix digest;
  only after revalidation is that suffix removed. Literal LF frames records,
  complete malformed rows remain refusal debt, and active plus draining
  generations share fixed byte and physical-record ceilings. Destructive purge
  now validates, lease-checks, removes, and parent-fsyncs the two fixed slots
  outside the retained roots; an unsafe or unexpected slot is preserved and
  makes purge incomplete instead of leaving a crash payload behind unnoticed.
- **Retrievable SIA lifecycle facts** — a keeper-verified base sense projects
  signed non-`PULSE:*`, non-`DREAM:bench` rows into `events/sia/`. Fresh installs
  sign the truthful `INSTALL:runtime` and `INSTALL:index` facts, providing a
  standalone corpus with answer-bearing held-out benchmark observations without
  feeding ingest or benchmark output back into itself.
- **Fail-closed ingestion and nightly publication** — journal ingestion binds
  a bounded cursor catalog to a separately bounded full-row pass. Valid
  prefixes can settle; the first malformed or over-bound row advances only
  after an exact cursor re-query and a durable named refusal. Catalog churn,
  an incomplete row, timeout, or process failure retains the prior cursor.
  Claude/Codex metadata trees persist every admitted directory
  generation and revalidate the bounded catalog before a clean generation may
  prune disappeared sessions; nested churn or refusal taints the whole cycle.
  Notification tails advance only over the processed batch; authoritative
  cursors, memo, and thought stores use no-follow regular-file reads. Untrusted
  summaries are control-stripped and structurally inert before
  Markdown/QML/CLI publication. A skipped or failed
  gbrain dream preserves the last successful timestamp for retry, while final
  corpus commit, index sync, and graph publication failures become signed,
  visible errors instead of being discarded; graph publication exceptions are
  recorded as `graph-fail`, not success. Failed index sync or graph export
  leaves durable publication debt that an idle pulse must settle; WORLDLINE
  uses a stable composite pagination cursor; consolidation binds source-byte
  lineage and replays interrupted cleanup without double-counting.
  Skill manifests now use a single bounded content capture with no-follow
  before/after/current-path identity checks. The captured inert description,
  head digest, and file metadata ride in the cursor snapshot and event
  occurrence; rendering never reopens the manifest, and any unstable manifest
  makes its whole root partial without proving a removal.

## 1.2.0 — 2026-08-29

The skills-organ release: the brain now knows what its agents can do.

- **Skills organ (15th sense)** — `sense_skills` scans the personal
  skill roots (`~/.claude/skills`, `~/.agents/skills`, `~/.omp/skills`,
  `~/.copilot/skills`, `~/.config/agents/skills`; override via config
  `skills.roots`) every pulse, admitting only real directories directly under
  each real root with a real directly contained regular `SKILL.md`; root,
  child, and manifest opens use no-follow semantics. It dedups by skill name
  and diffs against
  a snapshot carried in the cursor state — so the snapshot commits only
  after the corpus write, like every other sense. Installs, updates
  (captured `SKILL.md` identity and bounded-head digest), and removals become
  events under `organs/skills`,
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
- **Nightly retrieval drift tripwire** — the dream runs a date-seeded sample
  of heuristic corpus-conditioned slug probes and appends slug-match@5 and
  reciprocal slug rank to the trend the cockpit plots (BELIEFS → SLUG DRIFT).
  It is not an answer-quality score; drift says to run the full `sia bench`.
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
