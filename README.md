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

The memory-content runtime stays on your machine: ingestion, indexing,
retrieval, and embedding make no cloud calls. The judge is disabled by default.
If you explicitly configure a Claude model, that separate tool-free CLI path
may send the recalled context you ask it to judge or synthesize. It runs with
built-in tools, MCP, customizations, session persistence, and project discovery
disabled from an empty directory.
Configured Codex CLI grading refuses because its documented read-only sandbox
still permits reads and currently exposes no documented no-tool mode.
An MCP consumer is another operator-configured trust boundary: it receives the
memory it requests over stdio and may forward that content to its own
model/provider, whose data terms apply. The same boundary applies to scripts,
pipes, and agents that capture memory printed by the local `sia` CLI; SIA
cannot control what those callers do with returned content.

## What you get

- **A memory that accretes** — every admitted event becomes a durable record
  in a git-versioned day page —
  (*the corpus IS the brain*; the database is a rebuildable index), wired
  into a typed knowledge graph by [gbrain](https://github.com/garrytan/gbrain)
  with local `nomic-embed-text:v1.5` embeddings via Ollama.
  SIA also projects keeper-verified lifecycle rows from its own signed ledger
  into `events/sia/`, excluding `PULSE:*`, `DREAM:bench`, and terminal
  `SOURCE:refuse` rows so ingestion, evaluation, and source-capacity refusals
  cannot feed themselves. A fresh installer signs the truthful
  `INSTALL:runtime` and `INSTALL:index` facts, placing truthful, answer-bearing
  observations in a standalone corpus for the held-out benchmark.
- **A mind, not just an index** — mechanisms from the memory literature,
  all deterministic, all behavior-defensible: importance decays with time
  and grows with world-originated use (ACT-R); co-recalled memories bond
  (Hebbian, with nightly decay and degree caps); recall spreads through
  the graph (Personalized PageRank as a benchmarked tie-breaker); a
  non-destructive stability lens demotes stale associations without deleting
  evidence, while high-arousal or operator-pinned memories follow a nightly
  SM-2 rehearsal schedule whose state advances only after re-embedding
  succeeds; genuine novelty and out-of-band activity — including the
  *silence* of a paced
  source — become thoughts; a 7-slot workspace holds its current
  attention; old episodes consolidate into weekly gists while declared
  safety-class days remain verbatim. Every compacted original remains
  recoverable in git.
- **Outcome learning** — register falsifiable predictions with confidence
  and strictly future UTC deadlines; a tool-free Claude judge grades them
  strictly against recalled evidence without seeing the forecast confidence
  (TRUE / FALSE / UNRESOLVABLE — abstention audited); Brier
  scoring uses deterministic decimal arithmetic. Calibration reports are
  population-aware: a lone grade is labeled a single case, unresolved/malformed grades
  are excluded visibly, sparse confidence bins are withheld, and even a
  display-gate-eligible series remains descriptive because takes are not a
  random sample. Successful self-heals auto-*propose* hold-predictions with
  confidence computed from their own history — you commit each one by hand.
- **Prospective memory** — `sia intend "rotate the keys" --by 2026-10-01`:
  commitments the brain surfaces as their deadlines near and nags about
  when overdue, closing only on your word. Every night the dream also runs
  a small deterministic **slug-retrieval drift tripwire** whose trend the
  cockpit plots. It measures heuristic slug-family proximity, not answer
  correctness; the signed-ledger QA benchmark is the scored instrument. That
  benchmark credits present evidence only when the returned chunk contains
  its private, digest-bound source excerpt; a page slug or title alone never
  counts as answer-bearing retrieval. Public exports omit source slugs,
  observed timestamps, and witness bindings so a dated page cannot disclose a
  temporal answer; the publication audit canonicalizes common reversible
  Unicode, URL, and HTML encodings before checking that boundary, while the
  same canonical wording governs conflicts and public IDs. Unsafe control,
  bidi-format, surrogate, and noncharacter text is ineligible for question
  fields. Exact ledger bindings remain in owner-private artifacts. A
  pre-bounded legacy trend is upgraded from a stable no-follow tail: only
  recent complete rows survive, and any discarded history is declared in
  SOURCE HEALTH without blocking the DREAM receipt or memory readiness.
- **A mission-control cockpit** — full-screen Quickshell overlay
  (`SUPER+SHIFT+B`): the living graph with radial time, hover
  neighborhoods, edge explanations, a thought stream, evidence-chain
  verdicts, and a SOURCE HEALTH truth boundary that admits incompleteness
  instead of hiding it. Plus a bar widget with the live event count.
- **Agents everywhere** — an MCP server mountable in Claude Code, Codex
  CLI, Grok, and anything MCP-capable, plus a skill for skill-reading
  harnesses. Tools support reinforcing recall, a read-only search lane for
  audits/evaluations, and carefully labeled writes; MCP
  resources mount status, thoughts, calibration, the cortex, and
  `sia://memory/{slug}` pages. Agent notes enter an immutable per-request
  spool; the brainstem alone materializes them and acknowledges each exact
  request only after commit and index sync. Agent and operator notes are
  explicitly `model`-origin prose exceptions to evidence-backed event memory.
  Notes persist and may be returned to configured consumers, so do not put
  credentials, secrets, or private content in them; pattern-based redaction is
  defense in depth, not a secrecy guarantee. Agents may *propose*
  predictions; only you commit them.
- **Evidence culture** — SIA keeps its own Ed25519 hash-chained run
  ledger; every `sia ask`/search answer carries a truth-boundary line and one
  of the three canonical persisted origin labels: `evidence` / `derived` /
  `model`. Outside the narrow signed take-upgrade lane described below,
  missing, invalid, or ambiguous legacy origin metadata is surfaced as the
  explicit `legacy-unlabeled` boundary, never promoted to evidence, and
  weighted conservatively like `model`. Judge grades, ponder output, and
  agent/operator notes are `model`; deterministic transition handling and
  Brier recomputation remain separately derived operations and do not upgrade
  a model verdict. JACKAL integration records are a narrower boundary: SIA
  observes the bounded convenience ledger and receipt filenames as `derived`,
  unverified recall only. It does not infer a mathematical status or artifact
  verification from those files, and excludes those pages from grading
  evidence; verification must be rerun through JACKAL's own front door.
  Secret-shaped spans are redacted at
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

The installer sets up a SIA-private Bun + compiled gbrain toolchain and local
Ollama embeddings. On a fresh install it creates **your own keys and an empty
corpus**, then backfills the historical tail/ledger sources that support
replay; live-only streams establish their cursor at install time. Upgrades
verify and retain the existing signing identity and corpus. It starts the daemon,
enables the plugin, safely installs the agent skill when its destination is
new or SIA-managed, and inspects any named supported agent harness it detects.
It never performs a name-only MCP add or remove: when a registration is absent,
the installer prints that harness's exact manual command. Point generic clients
explicitly at `python3 ~/.local/share/sia/bin/sia-mcp`, and create a
keep-runtime guard under `~/.local/state/sia/mcp-consumer-guards/` before
relying on that registration. Any entry in that directory conservatively
preserves the CLI/runtime during uninstall; remove it only after retiring the
corresponding external consumer. Rerunning the installer after a manual named-
harness registration lets it inspect and guard the exact external registration.
It does not replace a desktop
binding by default. To explicitly consent to replacing Omarchy's
`SUPER+SHIFT+B` Browser
binding (Browser remains on `SUPER+SHIFT+RETURN`), run
`SIA_INSTALL_KEYBINDING=1 ./install.sh`; the cockpit is always available from
the bar widget.

### v1.3 publication barrier and legacy-take cutover

SIA treats corpus Markdown, its git commit, the PGLite index, and the exported
graph as one publication unit. Every shipped SIA corpus writer — `pulse`,
`dream`, `take`, `intent`, `grade`, and `ponder` — holds the corpus transaction
lease and durably records `sync_needed` publication debt before creating,
rewriting, or unlinking a page. Agent notes become pages only inside `pulse`,
under the same barrier. If the debt write fails, the corpus mutation does not
run. Direct `take`, `intent`, and `ponder` commands may intentionally leave the
debt for the next pulse; indexed memory remains unavailable meanwhile.

Publication debt clears only after the corpus is successfully committed (or
verified clean) in git, PGLite sync succeeds, and graph export succeeds. A
failure in any stage leaves the marker set for retry. The pulse sequence is
reserved in the same lease as its heartbeat, so a whole-memo write cannot lose
an existing debt marker. DREAM also settles publication between memory-backed
phases and around each grade, so no later phase queries an older PGLite/graph
generation.

The installer's first-light pulse is a required upgrade transaction, not
background cleanup. Before desktop changes, MCP registration, or brainstem
enablement, it reconciles old take pages while the resident brainstem is
stopped. A current-schema pre-origin open take becomes `origin: derived`; a
pre-origin resolved take becomes `origin: model`, and its historical judge
justification is rewritten as `Model justification (inert prose): ...` so
Markdown, wikilinks, and HTML-like controls cannot act as graph input. Pages
that exactly match the v1.2 producer are compatibility-normalized as well;
their original field digests remain in `sia_take.legacy_v1`, and an invalid
legacy open deadline is explicitly blocked from grading rather than guessed.

Every migration target is first recorded in an owner-private journal under
`~/.local/state/sia/take-migrations/` with source and target digests. The exact
target is then signed in SIA's ledger as `MIGRATE:take-origin`, using
`model-inert-v1` or `legacy-v1-normalize`; only afterward is `sync_needed`
durably set and the page atomically replaced. The pulse commits the corpus,
syncs PGLite, publishes the graph, and clears `sync_needed` last. Recovery
reuses the journal and exact signed row, so a crash does not require a second
signature.

Take and intent corpus pages remain the source of truth, but resident paths no
longer rescan their complete directories. Owner-private natural-history state
under `~/.local/state/sia/natural-history/` keeps digest-bound direct records,
a capped open set, append-only paginated catalogs, and exact Decimal
calibration sufficient statistics. A take/intent create or mutation is
journaled before its page changes; the journal is acknowledged only after the
page and projection are durable. A grade enters calibration only after its
exact content-bound `GRADE:take` row is observable. Historical rows page with
`sia takes --limit N --cursor CURSOR` (and intents with
`sia intend --history --cursor CURSOR`), while due/open/summary reads stay
bounded by the admitted open-set cap.

Existing corpora enter through a fixed, resumable directory-generation
baseline. Each pulse inspects only a bounded page; a changed directory
generation restarts conservatively, while journaled supported mutations and
direct event identities prevent a behind-cursor update from being lost or
double-counted. After bootstrap, a recurring bounded authority generation
scans corpus pages and sweeps the append-only catalog. Exact live rows are
generation-marked; deleted or replaced identities are WAL-tombstoned, which
idempotently removes their open-set and aggregate contributions. A changed
resolved page contributes to calibration only if its new exact bytes have an
observable `GRADE:take` row. Readiness and calibration consult bounded debt
and directory-checkpoint metadata and stay closed during an incomplete or
unstable scan/sweep. A resolved legacy page without an observable exact signed
grade remains visible as `invalid_resolved` and never enters a score
denominator. On the next resident authority pass, the ready take and intent
checkpoints enter one shared incomplete `audit` cycle: each catalog limit and
directory checkpoint is pinned once, and readiness/calibration remain closed
across every bounded slice, including tombstones. A participant that finishes
first stays ready while its sibling completes; neither starts another cycle
alone. Global ready is republished only
after the same generation reaches that limit, the catalog head still equals
the pin, no transaction is pending, and the directory checkpoint is unchanged.
Parent-directory churn restarts reconciliation immediately. An in-place
same-inode edit made after the final observation is not claimed visible until
a later pinned audit reaches it; this is bounded eventual reconciliation, not
instantaneous coherence against a hostile same-user writer.

The cockpit graph and weekly consolidation have the same long-horizon rule.
Graph export advances an owner-private, generation-bound corpus cursor and
retains only its capped display window; it opens selected pages no-follow and
digest-checks them again while extracting edges. Every supported corpus writer
restarts the projection before mutation. Consolidation advances a separate
durable cursor, then records an exact bounded day/source claim before it may
write an epoch or unlink a shard. Neither path infers absence from a partial
directory page. If one DREAM invocation cannot finish the generation, its
exact named consolidation transaction remains unapplied and unsigned. Each
later pulse recovers one bounded unit of that same DREAM transaction—including
claim application and its post-removal rescan—and readiness stays closed until
the cursor, candidate queue, and claims all converge. Pending scans, changed
generations, and permanent refusals remain visible as projection debt.
Once a generation is otherwise complete, valid nodes or unique display edges beyond the
cockpit's deterministic display caps are published as complete-with-omissions:
the JSON and SOURCE HEALTH report separate node/edge omission counts and state
that they imply no absence. The full corpus-backed PGLite index remains the
authoritative recall surface; a display omission never deletes memory.

Journal sensing first catalogs a bounded cursor window, then drains binary
stdout and stderr concurrently under per-record, aggregate-byte, row-count,
and deadline ceilings while binding every full row to its catalog cursor. A
valid prefix may settle. The first malformed or over-bound row advances only
after an exact cursor re-query and a durable named refusal; journal churn,
unterminated output, timeout, or producer failure deletes the temporary cursor
and retains the prior durable cursor. Claude/Codex session discovery is
metadata-only and paginated. It retains a bounded generation token for every
traversed directory and revalidates those tokens through a durable validation
cursor; session absence is allowed to prune state only after a complete,
unchanged, refusal-free root-to-EOF generation. A missing, renamed, reset, or
capacity-refused nested frame therefore preserves prior session state for a
later clean baseline.

Readiness blocks on any publication debt, any pending journal under
`~/.local/state/sia/grade-transactions/`, or a pending/discoverable take
migration, intent baseline, or natural-history transaction. Memory-dependent
CLI commands hold the corpus lease from that check
through the returned result, keeping the answer in the same corpus generation;
their MCP tools/resources inherit the same refusal and generation boundary.
They report `SIA memory read refused` until a successful `sia pulse` reconciles
the debt. `sia status` and `sia://status` remain available: their readiness line
is live, while the pulse/graph fields and cockpit are last-published snapshots.
Note and take-proposal writes may queue without exposing indexed memory.

If first light reports `legacy take migration refused`, do not delete the
journal or `sync_needed` marker. Compare the named page with its corpus git
history, restore or deliberately repair its provenance, then rerun `install.sh`
or run a successful `sia pulse` while the brainstem is stopped. After an
installer mutation, failure deliberately leaves the brainstem disabled and
stopped.

Requirements: Linux (Omarchy/Arch tested; x86_64 or aarch64) with pollable
pidfds exposed through Python's `os.pidfd_open`, `python3` with an
Ed25519-capable `python-cryptography`, `git`, `curl`, `tar`, `unzip`, `sha256sum`,
`zstd`, `flock`, `ss` from `iproute2`, a systemd user session
(`systemctl`), and roughly 2 GB of disk for
Ollama. The bootstrap downloads Bun and Ollama from pinned release URLs and
verifies their published SHA-256 digests before extraction. It checks out the
full gbrain commit in `GBRAIN_PIN`, verifies the pinned upstream `bun.lock`,
installs with `--frozen-lockfile`, compiles the executable, and binds its
receipt to the commit, lock, version, and binary digest under
`~/.local/share/sia/toolchain`. The Ollama service must use SIA's exact unit
without drop-ins, report the pinned runtime version, and expose only a
service-owned loopback listener. Because the pinned Ollama release cannot pull a
registry manifest by digest, SIA pulls the semantic
`nomic-embed-text:v1.5` tag, then requires the pinned manifest digest in the
running service's effective `OLLAMA_MODELS` directory and hashes every
referenced blob. Existing untagged gbrain databases remain compatible through
a verified local `latest` alias. An existing different alias is preserved and
requires `SIA_REPLACE_NOMIC_LATEST=1 ./install.sh` before replacement.
Unowned/custom Ollama units and runtimes are never adopted: replacing them
requires the separately printed `SIA_REPLACE_OLLAMA_UNIT=1` and/or
`SIA_REPLACE_OLLAMA_RUNTIME=1` consent, after which SIA installs its managed
artifacts. `SIA_ALLOW_UNPINNED_OLLAMA=1` weakens only the post-start executable
identity/version check; model-manifest/blob and loopback-owner checks still run.
If a pull/copy fails or the post-pull digest/blob check rejects the result, SIA
refuses the install without attributing the shared post-command manifest to
itself. That manifest is preserved rather than overwritten, and the exact
pre-operation snapshot is retained at the printed private backup path for
operator-directed recovery. No rejected generation passes SIA's activation
gate; content-addressed, unreferenced blobs may remain in Ollama's shared store.
Managed filesystems must support same-filesystem atomic rename and
`renameat2(RENAME_NOREPLACE)`; the SIA share filesystem must also support
`O_TMPFILE` with `linkat(AT_EMPTY_PATH)` for crash-closed signed-ledger
publication. The installer probes these runtime capabilities on the actual
managed filesystems before replacing or activating managed payloads and
refuses with a named cause when the host cannot provide them.
Optional: the Omarchy 4.x shell for the cockpit. Judge calls remain off until
you set `judge.backend` to `claude` and provide an explicit `judge.model`.

When a standalone checkout installs over an existing Omarchy plugin tree, the
new allowlisted snapshot is assembled in a sibling staging directory and
published through a durable generation-bound no-clobber journal. The exact
observed prior generation is archived before the staged tree may claim an
absent canonical name; a concurrent replacement is preserved and makes the
install refuse. `.git`, tests, caches, and runtime state are not copied. The
prior tree is retained under a printed hidden sibling path so local files are
recoverable; review and remove that backup manually after the upgrade. The
installed multi-file runtime uses the same journaled publication rule. After
host dependency, architecture, Python-cryptography, corpus, and brainstem-unit
ownership preflights pass, an upgrade stops an active owned/adoptable
brainstem before private toolchain and Ollama validation or mutation. A failure
before the first successful installer mutation restores its prior
enablement/activity; after that mutation, a failure leaves the brainstem
disabled and stopped
instead of restarting it against mixed dependencies. Fix the reported cause
and rerun `install.sh`. Prior runtime trees are retained at the printed hidden
sibling path.

The shared agent skill never overwrites an unmarked or locally modified
`~/.claude/skills/sia/SKILL.md`. Use the printed repository path manually, or
set `SIA_REPLACE_AGENT_SKILL=1` to consent; the old file is retained beside the
replacement. In a standalone install, its documentation link falls back to
`docs/MANUAL.md` in the checkout used to install SIA, then to `sia --help` if
that checkout is no longer available. For Claude, Codex, and Grok, an existing
**unmarked** `sia` MCP registration is left user-owned and unchanged, even
when its shape is exact; SIA writes a durable non-ownership guard for an exact
or SIA-referencing external registration. A missing registration is never
added by the installer, which prints the harness's exact manual command instead.
Historical ownership markers are recovered only against an exact current
registration; unresolved or invalid marker state fails closed. Uninstall
performs no name-only removal and prints a manual removal command when
appropriate. Registrations that reference SIA, indeterminate inspections, and
explicit consumer guards retain the CLI/runtime. An unrelated mismatched
registration is preserved but does not by itself retain SIA's runtime.

An unreceipted nonempty corpus is recognized as legacy SIA only when `.git/` is
a real directory, `README.md` is a regular non-symlink containing the exact
marker line `# SIA corpus — this machine's memory`, and the release checkout's
`bin/sia-ledger verify` accepts the share tree. It is then adopted
automatically. Other nonempty corpora require explicit
`SIA_ADOPT_EXISTING_CORPUS=1` consent and must already be real git working
trees. Exact-content regular unmarked managed files—including the brainstem
and Ollama units and the CLI—are the narrow auto-adoption exception: their
release-source digest is recorded without replacement. Modified unmarked
files and unowned runtime trees require the corresponding printed
`SIA_REPLACE_*` consent; symlinked managed roots are always refused.
SIA-marker-owned Bun/gbrain trees may be upgraded or repaired automatically,
with the previous tree retained at a printed sibling path. The runtime receipt
hashes only the allowlisted shipped runtime members and requires each of those
names to be a regular file; it does not attest to extra entries. Replacement
and removal archive the complete prior runtime tree, including extras, at a
printed sibling path.

Corpus creation and adoption are durable, attributed transitions rather than
directory-shape guesses. A fresh bootstrap records either an absent corpus or
the exact owned-empty generation and resumes only producer-exact partial
work. An absent corpus is assembled in an intent-bound off-path tree, advances
through `prepared`/`publishing`/`published`, and can claim the canonical name
only by generation-bound `renameat2(RENAME_NOREPLACE)`. Adoption records the
legacy/explicit mode, stable tree generation, and
Git `HEAD`; its v2 receipt is made durable before the intent is retired. The
receipt binds the canonical corpus directory's stable device, inode, full mode,
and owner identity. It deliberately excludes timestamps, contents, and Git
`HEAD`, so ordinary in-place memory and repository changes remain valid. The
root must remain a real, current-user-owned directory without group/world write
bits. Replacing, changing ownership/mode, or restoring the root invalidates the
receipt and is never auto-rebound; recovery requires deliberate inspection,
receipt rotation, and explicit re-adoption. Exact path-only receipts from older
SIA releases migrate once under the installer lifecycle and corpus-owner locks
using a generation-CAS transition. That compatibility migration binds the root
present at migration time; it does not prove that root is the historical
original. Preserve
an interrupted `managed-install/corpus-bootstrap` or `corpus-adoption` record
and rerun the installer—deleting it does not grant adoption authority.

Signed-ledger initialization likewise accepts only its exact durable prefix:
`key.hex`, then the matching `pub.hex`, then one canonical signed
`GENESIS:init` row in `ledger.tsv`, then the matching `head.pin`. A non-prefix
combination or pending transition journal refuses closed; do not delete or
recreate individual ledger components. A genuinely absent gbrain database is
initialized off-path under a durable `managed-install/gbrain-bootstrap`
`prepared`/`initializing`/`publishing`/`probing`/`published` transition,
checked through gbrain's
supported health probe, and published by tree-generation compare-and-swap. A
valid preexisting database is health-checked and used in place. Unattributed
partial bootstrap workspaces and unhealthy stores are preserved and refused;
direct `.gbrain` rebuilds are unsupported.

When Omarchy is installed, failure to enable the plugin is likewise fatal
instead of being reported as success. The installer first requests an Omarchy
plugin rescan, then requires an exact `khephri.sia` catalog entry before it
attempts enablement. The discovery parser accepts extra fields, but refuses
malformed/non-list JSON, a missing exact ID, a failed rescan, or a failed
enablement; it does not guess from the directory name.
The optional keybinding is written with one atomic replacement and rolled back
if a live Hyprland session rejects it. An incomplete, duplicated, or malformed
SIA marker block is never edited automatically: the installer/uninstaller
preserves the whole bindings file, reports a nonzero result, and asks you to
repair the markers manually.

## Sixty seconds after install

```bash
sia status                          # the brain's vitals
sia ask "what happened today"       # semantic recall, cited + labeled
sia think                           # its inner monologue
sia take "the build will go green" --confidence 0.8 --by 2026-09-05
sia intend "rotate ledger keys" --by 2026-10-01   # prospective memory
sia note "hard-won context" --from me    # a memory for future sessions
sia memory                          # stability, pins, and reviews due
sia memory --pin organs/journal     # protect/qualify a page for rehearsal
sia calibration                    # population-aware descriptive scorecard
sia bench generate --out /tmp/sia-qa  # signed-ledger QA + private MCP eval
```

Point it at your own programs in `~/.config/sia/config.json`:

```json
{ "custom_senses": [
    { "name": "myapp", "path": "~/logs/app.log", "type": "lines",
      "match": "ERROR|FATAL", "kind": "error", "tags": ["failed"] } ] }
```

`match` is a bounded list of literal substrings separated by `|`; regular
expression operators are refused so a configured pattern cannot monopolize
the resident writer. For `type: "jsonl"`, SIA admits only the exact configured
`field`; a record missing it is a named refusal and its other fields are never
rendered into memory.

## Documentation

- [**Field Manual**](docs/MANUAL.md) — cockpit tour, full CLI, thought
  glyphs, how the learning works, operations, troubleshooting.
- [**Whitepaper**](docs/WHITEPAPER.md) — architecture, the evidence
  model, every cognitive mechanism with its published formula and
  citation, the measurement instruments (`sia bench`,
  `sia judge-audit`), and the verification record.

## Remove

Run the uninstaller from the plugin/repository directory:

```bash
./uninstall.sh           # removes code/UI; keeps corpus, ledger, keys, queues, config
./uninstall.sh --purge   # also attempts to erase retained SIA data and config
```

Default removal preserves these data categories—corpus, ledger,
signing identity/head, queues and state snapshots, research, private
toolchain, and operator config—not byte-for-byte intact directory trees. It
removes or archives managed integration metadata and active code within them,
and archives the active plugin tree to a printed hidden sibling path instead
of deleting possible local additions. SIA's private Bun/gbrain toolchain
therefore remains under the retained share root; `--purge` removes it with
that root. Ollama, its user service, and the local model remain because they
may be shared. Removal reports an aggregate nonzero result if any requested
operation fails. Review
`uninstall.sh` before using `--purge` if the corpus or signing keys have not
been backed up.
If the brainstem cannot be stopped, removal preserves its runtime and unit;
`--purge` is blocked rather than deleting memory under a possibly live daemon.
Likewise, any surviving or indeterminate service/plugin consumer keeps both
the recovery CLI and runtime available and blocks `--purge`; for MCP, only a
registration that references SIA, an indeterminate inspection, or an explicit
consumer guard does so. An unrelated mismatched MCP registration is preserved
without retaining SIA's runtime. Plugin code is not archived unless
disablement succeeds. An unowned or locally modified runtime
tree also blocks purge until you inspect/remove it manually or restore a
valid SIA ownership receipt. External SIA MCP consumers—including clients SIA
cannot inspect—are represented by files under
`~/.local/state/sia/mcp-consumer-guards/`; those guards are deliberately never
removed automatically.
`--purge` is destructive but not transactional: after blocker checks, it
attempts the state, share, and config root removals independently. A later
failure can leave an earlier root already removed; there is no rollback, so
back up every retained data category first and inspect the aggregate result.
The fixed publication slots at `~/.local/state/.sia.sia-stage` and
`~/.local/share/.sia.sia-stage` are also part of purge. The uninstaller removes
only the exact owner-private shape it creates; an unsafe, malformed, busy, or
unexpected fixed stage is preserved, named, and makes purge incomplete rather
than risking unrelated data. A crash-left `payload` is non-authoritative
staging data and must never be manually published or trusted.

## What this is (and is not)

A local, git-backed, origin-labeled memory that refuses to pretend a
language model is a witness. **It is not a brain** — it is a disciplined
historian with a small associative index and a cockpit. That is better
than a brain: a brain you cannot audit, a historian you can. The
cognitive-science names in the design are *ancestry, not warrants* —
every mechanism is a small, named, deterministic approximation, and the
whitepaper's rename test governs them.

## Honesty principles (the actual design)

1. Every recall answer (`sia ask`/search) declares its origin and truth boundary.
2. Absence of recall is not evidence of absence.
3. A system that fails open must say so (SOURCE HEALTH).
4. The model may summarize and grade — never mint facts. Its grades, ponder
   output, and agent/operator notes remain `model` even where SIA separately
   applies deterministic transition or Brier arithmetic.
5. Records, not content: built-in senses use metadata and evidence streams;
   secrets are redacted at ingest, and built-in senses never open agent message
   bodies, clipboards, or private keys. Operator-configured custom senses read
   the file/field explicitly named in config and must not target secret or
   content stores. The separate ledger keeper necessarily reads SIA's own
   signing key when it signs an authorized transition.
6. SIA does not silently delete or guess: consolidation is git-recoverable,
   named lifecycle transitions (boot, pulse ingests, dreams, and grades) are
   ledgered, and refusal/partial states remain explicit. Graph read/export
   failures are visible in SOURCE HEALTH; a pulse that cannot publish its graph
   records the signed result `graph-fail`.

## Credits

Built on [gbrain](https://github.com/garrytan/gbrain) by Garry Tan.
Cognitive mechanisms trace to Anderson (ACT-R), Collins & Loftus, Nader,
Lisman & Grace, McGaugh, McClelland/McNaughton/O'Reilly, Dehaene, and to
HippoRAG, Generative Agents, Zep, and Letta — citations in the
whitepaper; the names are ancestry, the behavior is the contract.

MIT © 2026 Khephri Labs
