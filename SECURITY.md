# Security & privacy

**Model**: SIA's built-in senses ingest *records, not content* — subsystem ledgers,
logs, reflogs, notification summaries, and session file metadata (never agent
message bodies or clipboards). Built-in senses do not open private keys. An
operator-configured custom sense reads the exact file/JSONL field named in its
configuration. A JSONL record missing that field is a named refusal; SIA never
falls back to ingesting the raw object or unrelated fields. Do not point a
custom sense at message bodies, clipboards, password stores,
keys, or other secret-bearing content. The separate SIA ledger keeper
necessarily reads its own signing key for authorized signed transitions.
Secret-shaped spans (key blocks, JWTs,
tokens, `.ssh` paths, password fields) are redacted at the sense
boundary, before anything reaches the corpus or git; every omission is
counted in SOURCE HEALTH. All storage and embeddings are local; embeddings
use a loopback-only Ollama socket. The only external-network paths owned by
this repository are the installer's downloads and the optional judge through
your configured Claude CLI authentication/account/provider; its normal billing
and data terms apply. The judge runs from an empty directory with
built-in tools, MCP, customizations, session persistence, slash commands, and
browser integration disabled; an explicit model identifier is required and
recorded. Its prompt and combined output are byte-bounded, stdout and stderr
are drained concurrently, invalid UTF-8 answers refuse, and timeout or overflow
terminates the judge process group. Codex grading refuses because its documented read-only sandbox still
permits local reads and exposes no documented inference-only switch. The stdio
MCP server makes no cloud or external network call itself; configured retrieval
can use the loopback Ollama service. A configured MCP consumer receives the
memory it requests and may forward that content to its own model/provider;
that consumer's billing and data terms apply. Likewise, the local `sia` CLI
prints requested memory to its caller. Scripts, pipes, terminal capture, and
agents that consume that output are outside SIA's confidentiality enforcement.
Agent/operator notes persist and can be returned across this boundary. Do not
store credentials, secrets, or private content in them: pattern-based redaction
is defense in depth, not authorization to persist sensitive prose.
MCP ownership markers and keep-runtime guards protect lifecycle decisions;
they are not access-control or egress controls.

The corpus ownership receipt binds the canonical root's stable device, inode,
full mode, and owner. It excludes timestamps, contents, and Git `HEAD`, so
normal in-place memory activity does not invalidate ownership. Validation
requires a real, current-user-owned directory without group/world write bits.
A mismatched v2 receipt refuses and is never repaired by rebinding it to the
new path occupant. Exact path-only legacy receipts have one compatibility
migration: only after the installer lifecycle and corpus-owner leases are held,
SIA captures the root identity, generation-CAS replaces the receipt, captures
the root again, verifies v2, and validates then retires the returned legacy
generation. Pre-lock preflight is read-only and cannot recover that receipt CAS
or retire an intent. The migration authenticates the observed transition; it
cannot prove that the directory present under an old path-only receipt is the
same historical directory that originally received it. Same-user code can
still replace files or directories and remains outside SIA's sandbox boundary.

Journal ingestion does not trust the requested row cap as a memory bound. It
first catalogs an ordered bounded cursor window, then streams binary stdout
and stderr concurrently with explicit per-record, aggregate-byte, row-count,
and deadline ceilings while binding each full row to that catalog. A valid
prefix is admitted. At the first malformed or over-bound row, SIA re-queries
that exact catalog cursor; only an exact returned-cursor match permits a named
refusal to be signed and the temporary cursor to settle through that row. If
journal churn or vacuum prevents exact rebinding, or if output is unterminated,
timed out, or the producer fails, the temporary cursor is deleted and the
prior durable cursor remains. Refusal state and admitted pages become durable
before cursor publication. Existing and temporary cursor files are bounded,
owner-checked, no-follow regular files.
Claude/Codex session discovery similarly treats absence as an authority claim:
its paginated cursor catalogs a bounded generation token for every traversed
directory, carries any refusal across the whole generation, and revalidates
the catalog before pruning. Nested rename, disappearance, replacement, page
reset, or capacity refusal retains prior session metadata until a later clean
root-to-EOF generation. These checks protect SIA's conclusions; they are not a
filesystem access-control boundary against arbitrary same-user code.

Persisted origin metadata is restricted to `evidence`, `derived`, and `model`.
Outside the narrow signed legacy-take cutover, missing, invalid, or ambiguous
legacy metadata is exposed as `legacy-unlabeled`, never promoted to evidence,
and weighted conservatively like model prose. Judge-grade/ponder thoughts and
agent/operator notes are `model`; deterministic Brier recomputation or
ledger-transition handling does not upgrade the model verdict. Likewise, model
and legacy-unlabeled thoughts cannot mint typed domain relations. Only explicit
`derived` safety thoughts can use that lane; other links remain `mentions`.

The take cutover addresses a narrower historical risk: pre-origin judge prose
could contain Markdown, wikilinks, or HTML-like controls. SIA's own graph
exporter already ignores the grade section, but gbrain indexes raw corpus pages
and backlinks. Current-schema pre-origin open takes therefore migrate to
`origin: derived`; resolved takes migrate to `origin: model` with the judge
explanation rendered as inert prose. Only exact v1.2 producer pages enter the
compatibility-normalization lane. Other malformed graded pages refuse rather
than receiving guessed provenance.

Each migration uses an owner-private journal in
`~/.local/state/sia/take-migrations/` that binds the source and target digests.
The exact target is signed as `MIGRATE:take-origin` with kind
`model-inert-v1` or `legacy-v1-normalize`; `sync_needed` is then made durable
before atomic page replacement. Corpus commit, PGLite sync, and graph export
must all succeed before the marker is cleared. Recovery recognizes an existing
exact row instead of signing it twice. These guarantees authenticate the
authorized transformation and its publication order; they do not prove the
model verdict, its historical prose, or its cited memories true.

That migration ordering is one instance of the generalized corpus publication
barrier. Every shipped SIA corpus writer — `pulse`, `dream`, `take`, `intent`,
`grade`, and `ponder` — holds the corpus transaction lease and persists
`sync_needed` publication debt before creating, rewriting, or unlinking a page.
Failure to persist the marker prevents the mutation. The debt remains until git
commit or clean verification, PGLite sync, and graph export all succeed; a
commit, sync, or graph failure cannot be reported ready.

The pulse sequence reservation shares the same lease as the heartbeat, so its
whole-memo write cannot erase an existing marker. DREAM settles between
memory-backed phases and around each grade before later PGLite/graph use.
Readiness also blocks an unfinished journal under
`~/.local/state/sia/grade-transactions/`, even if no page replacement is yet
visible, as well as pending legacy migration. A gated CLI request retains the
lease through its returned result; MCP-backed memory reads inherit that child
process boundary, keeping readiness and output in the same corpus generation.

While publication is pending, those memory-dependent CLI commands and MCP
tools/resources refuse. `sia status` and `sia://status` remain available: their
readiness line is live, while pulse/graph fields and the cockpit are diagnostic
last-published snapshots. Note/proposal writes may still queue without exposing
indexed memory. The gate is not an access-control boundary: same-user code can
bypass SIA and read corpus or state files directly.

The daemon runs unsandboxed as your user (like any Omarchy plugin — read
the code before installing). The QML surfaces render dynamic snapshot strings
with `Text.PlainText`; the cockpit's sole process action is a fixed
`~/.local/bin/sia verify` invocation. PGLite admits one owner: all SIA-managed
daemon, CLI, benchmark, and MCP-derived operations share an advisory
cross-process lease. Whole pulse/dream cycles and explicit operator corpus
mutations share a separate transaction lease, and a lifetime brainstem lease
refuses a second resident daemon. The brainstem alone materializes agent notes:
they enter immutable mode-0600 request files and are acknowledged only after
commit plus index sync. This coordination is not a hostile same-user sandbox;
unrelated programs can bypass SIA and must not be described as serialized.

Graph page-read and extraction gaps remain visible as a partial SOURCE HEALTH
snapshot. A graph-publication exception is exposed and signed as
`PULSE:ingest ... graph-fail`; the signed row records the failure, not a claim
that a graph was published. Skill discovery uses no-follow descriptor opens
and admits only real, directly contained skill directories with real, directly
contained regular `SKILL.md` files. Each admitted manifest has a single bounded
content capture whose before/after/current-path identity is checked again after
the root scan. Its sanitized description, head digest, and metadata become one
snapshot row and event identity; event and entity rendering do not reread it.
An unstable manifest makes the root partial and preserves prior rows instead
of asserting absence. This blocks symlink traversal and mixed-read publication
in that sense; it does not make installed skill content trustworthy or exclude
a same-user mutation after the final observation.

**Reporting**: open a GitHub issue for non-sensitive matters; for
sensitive reports, use GitHub's private vulnerability reporting on this
repository.
