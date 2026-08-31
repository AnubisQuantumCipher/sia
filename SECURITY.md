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
Custom-sense `match` and `exclude` filters admit only bounded literal
alternatives; regular-expression syntax refuses without advancing the cursor.
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
Outside the narrow signed legacy-take cutover and bounded pre-publication
thought-inbox compatibility lane, missing, invalid, or ambiguous legacy
metadata is exposed as `legacy-unlabeled`, never promoted to evidence, and
weighted conservatively like model prose. The inbox lane admits a stable,
bounded JSON list whose fully modern and metadata-free legacy rows may coexist.
For each row lacking both queue fields, it derives a repeatable queue identity
from the stable file bytes, modification time, and row position and a canonical
queued time from that file time, so an atomic rename into the draining claim
does not change identity. When origin is absent, `note`, `ponder`, and `grade`
prose plus `take` proposal notifications default to `model`, while other
accepted historical producer kinds retain the deterministic `derived` default;
that compatibility default never mints
`evidence`. An explicitly present canonical origin is validated and preserved.
Supplying only one queue field, malformed modern metadata, or an unknown field
on any row refuses the whole inbox instead of mixing guessed and authoritative
identity.
Judge-grade/ponder thoughts, take-proposal notifications, and agent/operator
notes are `model`; deterministic Brier recomputation or
ledger-transition handling does not upgrade the model verdict. Likewise, model
and legacy-unlabeled thoughts cannot mint typed domain relations. Only explicit
`derived` safety thoughts can use that lane; other links remain `mentions`.
The partial-graph `mentions` fallback applies only to SIA's schema-regex
projector. Failure of gbrain's separate person/company gazetteer/NER extraction
fails brain sync and retains publication debt rather than crossing lanes.

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

Graph publication does not yield after one durable directory page and let a
later corpus mutation dirty the projection again. While still holding the
corpus transaction/owner boundary, it advances successive individually bounded
cursor pages until the generation is complete. A finite aggregate generation
ceiling preserves churn, an unexpectedly large tree, or permanent refusal as
named debt instead of looping without bound. During installer first light,
`SIA_BACKFILL=1` similarly advances the take and intent natural-history
authorities together until their scan/sweep and shared audit phases converge,
or refuses at its finite ceiling. Within the paired scheduler, only the leader
may open a fresh audit; the follower may join or finish an active cycle but
cannot immediately reopen another after completing it. This convergence is
coordination among SIA writers, not a hostile same-user snapshot.

While publication is pending, those memory-dependent CLI commands and MCP
tools/resources refuse. `sia status` and `sia://status` remain available: their
readiness line is live, while pulse/graph fields and the cockpit are diagnostic
last-published snapshots. Note/proposal writes may still queue without exposing
indexed memory. The gate is not an access-control boundary: same-user code can
bypass SIA and read corpus or state files directly.

`sia ready` exposes that same live predicate as an operator/automation health
gate. It acquires the corpus-owner lease, prints a stable ready line or the
exact not-ready reason, and exits unsuccessfully for debt or malformed state.
The installer executes the newly published command after first light and before
later integrations; a zero pulse exit alone is therefore insufficient to
activate SIA. The command attests observed SIA readiness, not filesystem
integrity against same-UID interference after the lease is released.

Installer and uninstaller quiescence uses an exact systemd runtime start
barrier rather than a runtime mask, because SIA's local user unit has higher
fragment precedence than such a mask. The barrier is one no-follow-verified
regular file under the canonical private `XDG_RUNTIME_DIR`; validation binds
its exact owner, mode, link count, bytes, and stable generation and refuses a
foreign runtime unit fragment or any unexpected drop-in. Its reset plus false
`ConditionPathExists=!/` blocks indirect activation before service hooks, and
`RefuseManualStart=yes` blocks an explicit manager start. The user manager must
then attest the exact fragment/drop-in set, inactive zero-PID state, empty job,
and effective refusal.

Fresh installation publishes that drop-in while the main unit is absent, then
publishes the unit, reloads, and re-attests the combined state. To open the
final activation window, SIA atomically renames only its exact `.conf` file to
a non-`.conf` retired sibling, reloads, and verifies the unit is unbarriered.
The retired copy remains available for atomic restoration through live
executable/argument attestation and is discarded only after success. Uninstall
uses the same barrier and targeted retirement/removal; it never removes the
drop-in directory or an operator-owned drop-in. Failure retains or restores the
active barrier, or preserves the exact retired recovery copy after the main
unit has already been removed.

The systemd barrier is paired with a filesystem launch fence. Before the first
dependency mutation, the installer durably records the old CLI, brainstem, and
MCP launcher inodes, modes, and digests and changes those exact files to mode
`000`. Retry trusts an unreadable generation only when the lifecycle tombstone,
strict launch-fence schema, unique path entry, inode identity, and retained
digest all agree. Pending single-file CAS recovery runs before CLI ownership
preflight. Because fencing changes mode and change time, runtime and CLI
ownership are preflighted again afterward; later publication never reuses the
pre-fence generation token. File-CAS recovery distinguishes an exact canonical
pre-operation generation from the same journal-bound file after rename, where
only the expected rename-induced metadata change is tolerated. A concurrent or
independently modified canonical, stage, or backup generation is preserved and
refuses. These checks coordinate SIA's own installer; the retained digest is
not a privilege boundary against arbitrary same-UID code.

Descriptor-rooted multi-file publication accepts symbolic links only for the
narrow archive shape needed by managed runtimes. The tree parent, root, and
directories must be current-user-owned and non-group/world-writable; regular
files must additionally have one link. A symbolic link must itself be stable,
current-user-owned, single-link, relative, and lexically contained, and its
complete in-tree chain must terminate at a current-user-owned, single-link,
non-group/world-writable regular file. Link text and metadata participate in
the generation digest. After the initial walk, every recorded directory path
is reopened from the descriptor root and matched to its captured generation;
every symlink generation and target text is reread before and after its
referent is accepted. Nested replacement therefore refuses. Absolute,
escaping, dangling, special, group/world-writable, and hard-linked-file shapes
refuse rather than being normalized.

gbrain's self-upgrade switch is verified through the pinned executable after
configuration. The bounded command helper captures stdout and stderr together;
the installer accepts only the exact combined form consisting of `off` plus
gbrain's file/env-plane provenance line, with or without its one exact
DB-plane-shadowed suffix. Extra diagnostics, a changed provenance string, or a
different value refuse activation.

This protocol closes SIA's own systemd lifecycle race; it is not privilege
separation from arbitrary code already running under the same UID. Such code
can modify user-owned runtime files or bypass the installer. Descriptor,
generation, and manager-state checks make interference visible at observed
boundaries and fail closed, but do not turn the daemon into a hostile same-user
sandbox.

The daemon runs unsandboxed as your user (like any Omarchy plugin — read
the code before installing). The QML surfaces render dynamic snapshot strings
with `Text.PlainText`; the cockpit's only process actions are fixed
`~/.local/bin/sia verify` and `~/.local/bin/sia ready` invocations. PGLite admits one owner: all SIA-managed
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
that a graph was published. The installer-created corpus-root `README.md` is
repository metadata rather than a canonical memory page and is skipped by
exact name at the graph root. Upgrade recovery removes only the byte-exact
obsolete README refusal emitted by the old projector; it cannot erase another
failure or a candidate page. Skill discovery uses no-follow descriptor opens
and admits only real, directly contained skill directories with real, directly
contained regular `SKILL.md` files. Each admitted manifest has a single bounded
content capture whose before/after/current-path identity is checked again after
the root scan. Its sanitized description, head digest, and metadata become one
snapshot row and event identity; event and entity rendering do not reread it.
An unstable manifest makes the root partial and preserves prior rows instead
of asserting absence. This blocks symlink traversal and mixed-read publication
in that sense; it does not make installed skill content trustworthy or exclude
a same-user mutation after the final observation.

Tests that import runtime modules activate a process-wide temporary home before
those imports. A regression test checks recognized syntactic runtime-loading
patterns and the currently enumerated import-time mutable paths. Its module and
path enumerations must be extended when contributors add another runtime module
or import-time path constant. This prevents covered fixtures from inheriting
the operator's resident SIA paths; it is a test-harness containment control,
not a runtime sandbox or a proof that arbitrary future test code cannot name an
external path explicitly.

The repository-side Omarchy directory contract is publication metadata, not a
security claim. Local manifest validation must be rerun against the exact
submission commit; that result, automated marketplace validation, and any
eventual listing establish compatibility/discoverability only. Submission
remains maintainer-approval-gated, and the official marketplace explicitly does
not treat a listing as a security review.

**Reporting**: open a GitHub issue for non-sensitive matters; for
sensitive reports, use GitHub's private vulnerability reporting on this
repository.
