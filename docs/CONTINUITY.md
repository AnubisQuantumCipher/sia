# SIA continuity

SIA continuity is the backup and clean-machine recovery boundary for the
Omarchy Brain. The brain owns a storage-independent freeze/thaw contract:
freeze creates a signed portable capsule from documented authoritative roots;
verify authenticates and inspects it off-path; thaw applies it only under the
brain's lifecycle and receipt invariants. Repository adapters operate outside
that contract.

Throughout this document, **SIA means the Omarchy Brain**, never a similarly
named storage network. Repository and storage products keep their own names
and remain outside the brain's identity.

The CLI is the canonical continuity interface. The cockpit is a thin client
over the same request and status protocol: it may show state and request a
backup, but it does not own freeze, verification, lifecycle, or restore
semantics.

## Stable brain interface

The brain-native interface has no repository credentials, schedules, or
storage-provider behavior:

```text
freeze -> signed portable capsule
verify -> authenticated capsule facts, still independent of a repository
thaw   -> confirmed transactional adoption or complete refusal/rollback
```

The restic adapter consumes and produces capsules through that interface. A
future repository adapter must use the same interface rather than learning how
to copy SIA's live roots itself.

The authoritative roots are exactly:

- `~/.local/share/sia`
- `~/.local/state/sia`
- `~/.config/sia`

They are authorities, not instructions for a backup program to walk them
live. `sia continuity freeze` acquires SIA's owner leases, copies the portable
subset into a private completed capsule, releases the live leases, verifies
the copied SIA ledger, and signs a closed manifest of paths, metadata, digests,
corpus head, ledger head, omissions, and source receipt identity. Use
`sia continuity roots --json` for the versioned machine-readable contract. It
publishes the three absolute authority paths, exact scoped selection and
exclusion rules, and `do_not_walk_live: true`; adapters consume capsules and
must not interpret those paths as backup inputs.

Core verification returns authenticated capsule facts under the
`sia-verified-capsule-v1` schema. An adapter binds those facts to its opaque
snapshot identity through SIA's `prepare_binding` boundary, producing a
`sia-prepared-capsule-v1` receipt. Only that core-bound receipt can enter the
guarded thaw path; there is intentionally no raw live-thaw CLI.

## Why the first adapter is restic

The continuity stack is deliberately small:

```text
SIA freeze -> portable capsule -> restic encryption/snapshots
          -> operator-chosen external recovery repository
```

The repository may be a local disk used for drills, SFTP, an append-only REST
server, S3-compatible storage, or an rclone remote. Keeping that interface
generic makes recovery independent of any single storage product.

`install.sh` provisions SIA's private, version-pinned, checksum-verified restic
executable under `~/.local/share/sia/toolchain/restic`. Continuity does not
trust or require an ambient `restic` binary from `PATH`. Repository credentials
remain operator-owned secrets outside the capsule and source checkout.

## Protection boundary

The routine capsule includes the information required to authenticate and
recover SIA's memory:

- the complete corpus, including its Git history;
- the signed ledger, pending ledger rows, public key, and head pin;
- SIA's research directory;
- authoritative queues, cursors, thoughts, takes, and other retained state;
- operator-owned SIA configuration.

It deliberately excludes:

- the whole `.gbrain` tree: its `brain.pglite` database is a machine-local
  projection, while its config, installed schema pack, and managed receipt
  belong to the clean destination's runtime substrate;
- installed runtime code, Bun, gbrain, restic, models, and prior runtime
  generations, which come from a clean SIA install;
- lifecycle, owner, publication, and queue lock files;
- installer receipts and integration ownership records belonging to the
  destination machine;
- continuity configuration, credentials, repository key, job state, staging,
  and rollback data;
- the private ledger-signing key, which belongs in the separate offline
  identity recovery file and is never uploaded with a routine capsule.

Restore keeps the destination's installed runtime, managed receipts, corpus
root directory identity, exact corpus-v2 receipt, continuity credentials, and
installed `.gbrain` substrate. It authenticates and preserves the destination
`.gbrain` root identity, `config.json`, installed `sia-pack`, matching
`managed-install/schema-pack` receipt, and unknown children; those are not
recovered from the capsule. Through gbrain's supported interface, thaw creates
a fresh `brain.pglite` off-path, probes it, replaces only the live
`brain.pglite` projection and the two named repair/reap sidecars, then performs
a full sync from the restored corpus. The prior projection and sidecars exist
only as bounded rollback material and are retired after a settled outcome.

Thaw restores the portable contents transactionally, records an explicit
signed adoption into the unchanged receipt-bound target root, and requires
SIA's ordinary first-light pulse, `sia ready`, and SIA signed-ledger
verification before core commit. Optional external subsystem chains do not
gate SIA continuity. A failed first light rolls back to the complete
pre-restore generation. The signed `RESTORE:adopt` ledger row is the durable
audit evidence; temporary intent, committed-receipt, private-key copies, old
projection, and operation tree are crash-recovery state and are retired after
commit or rollback settles.

## Automatic policy

Successful setup or connection enables two persistent user timers:

- an hourly freeze, local capsule verification, and encrypted upload of the
  completed capsule;
- a weekly `restic check` plus exact off-path restore and capsule verification
  of the newest SIA snapshot.

Persistent timers catch up after the machine was powered off. Jobs are
serialized and duplicate scheduled requests are coalesced. Closing the
cockpit does not stop a job. SIA never automatically applies a snapshot to the
live brain, forgets, prunes, or deletes repository snapshots. The weekly job
restores only into a private off-path verification stage. Manual
`sia backup now` uploads and immediately
runs the exact round-trip verification path. A newer scheduled upload is shown
as awaiting verification and cannot replace the last known verified recovery
copy. An authentic capsule classified
`recovery-only` remains useful recovery material, but it is not reported as a
ready verified copy.

The overall `verified` / **RECOVERY READY** state describes repository-copy
health, not the outcome of the most recent operation. It requires a concrete
`latest` row whose capsule round trip is verified, whose readiness is `ready`,
and whose SIA signing identity matches the configured brain binding. A restore
can independently finish with a correlated `operation.phase` of `verified`;
that reports the live restore outcome but does not invent a healthy repository
copy. If no ready identity-matching copy remains, the overall state stays
`recovery-only`, `failed`, or `blocked` even after a successful restore.

## Set up a new repository

Choose an off-machine repository and two recovery destinations that are not on
the computer being protected. The repository key unlocks the encrypted
snapshots. The identity key lets a replacement SIA continue the restored
signed history; it is deliberately not part of those snapshots. Then use the
cockpit's **Set up protection** sheet, or:

```bash
sia backup setup \
  --repository 's3:https://storage.example/bucket/sia' \
  --environment-file "$HOME/.sia-continuity-secrets/backend.env" \
  --recovery-key-out '/path/on/separate-media/sia-repository.key' \
  --identity-key-out '/path/on/offline-media/sia-identity.key'
```

SIA generates the repository password; it never appears in the command line,
status JSON, logs, or the backup itself. The local working copy is stored in
`~/.local/state/sia-continuity/repository.key` with owner-only permissions.
The two recovery outputs are the copies needed on a replacement computer.
Keep the identity file offline. Possession of it grants SIA's signing
authority; an ordinary remote snapshot must never contain it.

Setup binds continuity state to both the authenticated restic repository
configuration identity and the intended SIA capsule-signing public identity.
Every repository operation rechecks the repository identity. Uploaded
snapshots carry the brain identity as selection metadata, but that metadata is
only a hint until an off-path capsule signature verifies to the same public
identity. An untagged or foreign-identity capsule may be listed for explicit
inspection or deliberate recovery, but it cannot become the default healthy
copy or turn the cockpit green. A clean-machine identity transplant remains an
explicit restore ceremony using the separately held offline identity; it is
not silently normalized into routine backup health.

To export the signing identity separately from repository setup, prepare an
existing owner-private directory on offline media and run:

```bash
sia continuity export-identity \
  --output '/path/on/offline-media/sia-identity.key'
```

The command creates the file once with owner-only permissions and reports
only its path and public fingerprint. It refuses SIA authority roots,
continuity state, symlinked paths, non-private parent directories, and an
existing destination.

The optional backend environment file is also owner-only. It must be a real
absolute-path file outside every portable SIA root and outside SIA's
continuity working state; otherwise a credential path could be swept into the
capsule it authorizes. Path-bearing values such as `RCLONE_CONFIG` and
`GOOGLE_APPLICATION_CREDENTIALS` must likewise name owner-private files
outside those roots. SIA accepts a closed allowlist of backend variables and
refuses attempts to override the repository or repository-key path. Create
the environment file and each output's owner-controlled parent directory in
advance; recovery output files themselves must not already exist.

Setup and all repository work are queued durable operations. Keep the accepted
request id and poll status until that exact operation reaches a terminal phase;
do not infer completion from the queueing command's success. Before enabling
or starting either schedule, SIA authenticates the managed
receipts and exact installed bytes for both service/timer pairs, then attests
systemd's effective fragment paths, drop-in set, timer targets, active jobs,
and resulting state. A foreign fragment, unowned drop-in, replaced receipt, or
unexpected effective unit refuses setup/connect/resume rather than executing
under the unit manager's substituted definition.

After setup has completed its repository probe and enabled the schedules, make
the first copy and inspect it:

```bash
sia backup status
# wait for the exact setup request to finish before continuing
sia backup now
sia backup status
sia backup list
sia backup check
```

## Choose a destination

Start with a destination whose recovery behavior is already understood: an
off-machine disk, an append-only rest server, or an established S3/rclone
bucket with independent versioning. Keep destructive repository credentials
off the live SIA computer where the backend permits that model. Product-specific
storage adapters are intentionally outside the continuity core.

A repository on the protected computer's only disk is suitable for an
isolated restore drill, not disaster protection. Continuity is not complete
until an actual off-machine destination is configured and a clean-machine
drill succeeds without reading anything from the source machine.

## Recover on another computer

Install the same or a newer compatible SIA release first. Reconnect the
repository with the separately stored recovery key:

```bash
sia backup connect \
  --repository 's3:https://storage.example/bucket/sia' \
  --environment-file "$HOME/.sia-continuity-secrets/backend.env" \
  --recovery-key-file '/path/on/separate-media/sia-repository.key'
sia backup status
# wait for the exact connection request to finish before continuing
sia backup list
```

Wait for the accepted connection request to complete before listing or
preparing snapshots. On a clean target, the fresh local signing identity does
not match the source snapshots yet. `latest` deliberately means the newest
snapshot matching the currently bound identity, so clean-target recovery must
use `sia backup list`, choose the full intended source snapshot id, and prepare
that exact id. Do not weaken the filter or guess from a shortened ambiguous id.

Prepare a snapshot off-path. Preparation downloads it, checks the repository
authentication, validates the closed capsule schema and every payload digest,
and publishes a prepared-restore receipt without changing the live brain.

Before restic may materialize snapshot payload bytes, SIA reads the snapshot's
metadata listing and admits only relative capsule paths, supported regular-file
and directory nodes, and the configured entry-count, aggregate-byte, and depth
bounds. An oversized, malformed, special-node, or traversal-shaped listing is
refused before restore. Failure cleanup walks the private stage without relying
on the admission catalog that just refused, so a partial transport failure
cannot strand an attacker-shaped tree as trusted prepared state.

Then request preparation and inspect its status:

```bash
sia restore prepare EXACT_SNAPSHOT_ID
sia restore status
```

An existing machine restoring its own identity may use `sia restore prepare
latest`. A clean target's prepared receipt instead reports
`identity_matches: false`, and apply requires the separately held offline
identity file. After core thaw has recorded the signed adoption and passed its
internal readiness/ledger proof—but before the resident brainstem restart—the
adapter atomically rebinds `~/.config/sia/continuity.json` from the fresh target
identity to the adopted source public identity while preserving the debt-bound
repository id, endpoint, and environment binding. A mismatch or interrupted
rebind remains recovery debt and non-green.

That rebind does not promote the snapshot or make protection green. The
post-restart proof can mark only the correlated restore operation verified.
Run `sia backup check` afterward; only its new repository round trip can
promote the now-identity-matching snapshot into `latest` ready health.

Wait until status publishes the prepared id, exact snapshot id, and current
target ledger head bound to that preparation. A queued or merely running
request is not a prepared restore.

Apply only the displayed prepared receipt. The CLI requires exactly one bounded
JSON line on standard input. Its closed
schema must contain `schema_version: 1`, the literal phrase `RESTORE`, the
exact snapshot identifier, the full current target ledger head displayed by
preparation, and `corpus_receipt_re_adopt: true`. The identity-key option is
omitted when the current machine already owns the matching signing key.

For example, after substituting only the values printed by the prepared
receipt:

```bash
printf '%s\n' \
  '{"schema_version":1,"phrase":"RESTORE","snapshot_id":"EXACT_SNAPSHOT_ID","ledger_head":"FULL_CURRENT_TARGET_LEDGER_HEAD","corpus_receipt_re_adopt":true}' \
  | sia restore apply PREPARED_ID --confirm-stdin \
      --identity-key-file '/path/on/offline-media/sia-identity.key'
```

Restore always stages and re-verifies the capsule before live mutation. It
then takes the exclusive lifecycle and brain-owner leases, writes a durable
rollback journal and boot barrier, preserves the target root inode and exact
receipt bytes, authenticates the installed `.gbrain` substrate, publishes only
the rebuilt PGLite projection through gbrain, and records the adoption
transition. Core commit is withheld until the projection is ready and the SIA
ledger verifies.

Apply returns an acceptance receipt before the worker runs. Treat only an
exactly correlated terminal status—matching request id, operation, prepared
id, readiness, and ledger-verification fields—as restore success. A core thaw
result is not yet green: the stable supervisor must restart and attest the
resident brainstem, then freshly recheck readiness, the signed ledger, and the
exact adoption row. The corpus-owner lease spans that observation, the resident
PID recheck, recovery-debt retirement, and terminal publication so those facts
cannot be assembled from different corpus generations. The effective
`sia-brainstem.service` fragment and managed receipt are re-attested before
restart; while the restore gate is active, only SIA's exact runtime barrier
drop-in is permitted, and the service is not started until that drop-in is
retired. A terminal restore operation may then be `verified`, but overall
`verified` remains reserved for an independently ready, identity-matching
repository copy.

The cockpit follows the same sequence and requires those values to be typed;
Cancel remains the default. It calls the canonical CLI and cannot bypass its
ceremony or acceptance receipt. Never copy a prepared tree directly over a
running or uninstalled SIA tree.

## Recover an interrupted restore

Restore has three durable recovery layers under
`~/.local/state/sia-continuity/`:

- `restore-supervisor.json` binds the accepted apply or recovery operation,
  pinned runtime generation, child result, and restart attestation;
- `restore-runtime-mask` records the restore-owned brainstem runtime gate;
- `restore-in-progress.json` is the core thaw barrier and points at its
  authenticated rollback journal/capsule.

The supervisor or runtime-gate artifacts can exist even when a crash occurred
after apply acceptance but before core thaw created its barrier. Conversely, a
core barrier means live adoption reached the phase that requires capsule-core
recovery. Any one of the three is recovery debt: normal brain and continuity
operations refuse rather than guessing that the generation is usable. Do not
delete any of them, the target corpus receipt, rollback journal/capsule, or
retained operation material. Run:

```bash
sia restore recover
```

The stable restore launcher reacquires the exclusive lifecycle and owner
leases and reconciles the exact supervisor/runtime phase. If a core barrier is
present, capsule core authenticates its journal and rollback capsule, then
either finishes an already committed cleanup phase or restores the exact
pre-restore generation. If core thaw never started or already finished, the
launcher instead reconciles the durable supervisor intent and coherent live
state without inventing a snapshot choice. This command therefore needs no
new confirmation document.

The brainstem is restarted only after core debt is resolved. The supervisor
then binds a fresh health/ledger/adoption observation to the exact resident
PID and one corpus generation. It retires the accepted request and every
restore-owned supervisor/runtime debt before publishing terminal status; green
is the final durable write, never a promise made while a fail-closed barrier is
still active. If retirement fails or the process crashes first, recovery debt
and a non-green status remain.
Follow with `sia ready`, `sia ledger`, and `sia restore status`.

## Threat boundary

Continuity is designed to protect against disk loss, accidental local
deletion, a broken upgrade, and migration to a clean computer. The repository
contents and metadata are encrypted and authenticated by restic, and the
capsule adds a closed manifest that is checked before live mutation.

It does not claim to protect against:

- compromise of the source computer while it is unlocked;
- loss of every copy of the recovery key;
- deletion of the repository by an actor with destructive backend access;
- a backup destination that exists only on the same physical disk;
- data written after the newest successful snapshot.

Use an off-machine destination, retain the recovery secrets separately, avoid
granting unnecessary backend permissions, enable provider-side versioning or
immutability where compatible, and periodically perform a clean-machine
restore drill. A green backup event is useful; a verified restore is the real
proof that the recovery path works.

The acceptance test is deliberately strict: a clean compatible SIA install
must provide its own destination runtime, `.gbrain` substrate, schema pack,
and managed receipts; restore from the external repository; preserve that
destination substrate and receipt-bound corpus root; publish only a newly
built PGLite projection through gbrain; restart the resident brainstem; reach
`sia ready`; verify the signed SIA history and exact adoption row; and use no
files scavenged from the failed computer.
