# Recovery-control freshness obligation

Status: DESIGN and finite-model experiment. No protected freshness provider
is installed or accepted. This document does not reduce the rollback threat
model to obtain a working local demonstration.

## Required provider contract

The recovery control's signed epoch is authentic history, not a currentness
witness. An independent protected anchor must bind this commissioned fixture,
the exact recovery permit, the control-policy version and the allowed state.
For the initial one-operation fixture, the only transition is enabled epoch
zero to permanently disabled epoch one. No re-enable, reset, namespace
replacement, fresh genesis or key substitution is permitted.

The provider must expose bounded authenticated read and compare-and-advance
operations. A read is current at a defined linearization point; an advance
accepts only the exact predecessor identity and authorized successor. A success
acknowledgment requires durability outside the local state being protected
against rollback. Restoring the local SIA directory, its backups, or its VM
snapshot must not restore the provider to an earlier authorization state.
Unavailable, unauthenticated, conflicting or unexpected provider state refuses
effects and preserves debt. A missing anchor after commissioning is not epoch
zero. The service cannot create, erase or replace its own trusted anchor.

The provider identity, namespace, permit and allowed transitions must be pinned
independently of a caller's artifact. A raw counter without these bindings is
insufficient. Merely placing a signed epoch in another local file does not
establish independence from a joint rollback. A hardware or off-host provider
must demonstrate its actual persistence/reset/restore boundary; a provider's
name is not evidence of that property.

Protected lease ownership spans current observation through the associated
effect. The administrator's disable path uses the same serialization domain.
For an off-host provider, a local process lock alone cannot serialize remote
revocation: a separately specified distributed reservation/fencing protocol
and loss-of-contact behavior are required. This document does not authorize
substituting a cached remote response.

## Disable ordering and recovery

1. Under the protected lease, authenticate current identities and exact
   predecessor state, then compare-and-advance the independent anchor to disabled.
2. Publish and synchronize the exact signed disabled control record.
3. Read back the anchor and retained control, verify all joins, then acknowledge.

Failure between the first two steps leaves mismatch/debt and denies effects.
It cannot recover by restoring the old enabled permission. An uncertain advance
outcome requires a fresh authenticated provider observation, never a retry that
creates a new identity or assumes failure. Reconciliation may only complete the
same disabled record; its signer inputs must be canonically retained or
deterministically derivable from independently authenticated bindings.

The anchor advance is the revocation linearization point. The acknowledgment
comes later, after the matching durable record and readback. A completed effect
before that point is not undone. A successful acknowledgment means later effects
remain denied even if an old signed local record reappears.

Physical provider provisioning, exact wire/signature schemas, keys, deadlines,
failure codes, exhaustion behavior and commissioning remain OPEN. A fake
in-memory anchor or Boolean can exercise a model but cannot satisfy the service's
acceptance gate. Linux systems without an accepted provider retain the existing
released behavior; no new rollback-resistant authority claim is made.

## Finite model and negative controls

`ControlFreshness.tla` abstracts one permit and the one-way disable transition.
Both the enabled and disabled records are treated as validly signed, so the
negative cases do not depend on signature forgery. The independent anchor only
advances. The local record and a separate local anchor replica can be replayed.
The interval between anchor advancement and control publication is explicit.
Each action is an atomic abstraction of a durable serialized transition;
process execution, torn writes and syscall refinement are not modeled.

`NoRevokedEffect` checks the recorded effect-time revocation witness.
`AckSafe` requires a retained acknowledgment to imply that the independent
anchor advanced; it does not require a replayed local record to remain current.
The initial-effect and disable-acknowledgment reachability controls prevent
acceptance from relying only on unreachable success.

Two deliberately broken variants must violate `NoRevokedEffect`:

- checking the signed enabled record without an anchor;
- comparing it with a replayable local anchor replica.

The second variant demonstrates that adding another local epoch file does not
close the rollback requirement. It is not a test of any actual hardware or
remote provider. The positive result is conditional on a genuinely independent
anchor and atomic observation/effect serialization.

A targeted third negative configuration uses the replayable local anchor and
allows local replay and an effect only after a successful disable acknowledgment. It must still
violate `NoRevokedEffect`, requiring the disabled record to have been published
and acknowledged before both local components return to their enabled values.
The acknowledgment restriction is test instrumentation, not proposed service
behavior. It excludes an earlier bad effect followed by acknowledgment from
being mistaken for a post-acknowledgment rollback counterexample.

Run with the same pinned toolchain as the admission model:

```sh
JAVA_BIN=/path/to/verified/java TLA_JAR=/path/to/verified/tla2tools.jar \
  bash spark/check-control-model.sh NEW_OUTPUT_DIR
```

Retain raw traces, exit codes, source/tool hashes and commands. Independent
review and committed-source reproduction qualify this experimental artifact
only. Actual acceptance additionally requires joint-rollback, reset, lost
advance response, interruption before/after each durable step, credential
compromise, concurrency and unavailable-provider tests against the selected
protected implementation.
