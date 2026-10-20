# Protected-slot design fixtures

`protected_slot_vectors.json` contains deterministic byte/signature fixtures
for the proposed protocol in `../PROTECTED-SLOT-WIRE.md` and
`../PROTECTED-SLOT-LAYOUT.md`. These are DESIGN artifacts, not a frozen protocol,
authorized operations, cryptographic qualification or production grant files.

**The signing seeds are intentionally public. Never provision these keys,
identities or grant bytes into a service.** The synthetic predecessor digest
does not identify an authenticated receipt. Administrator pins, kernel principals,
protected current observations, clock validity, store/slot roles and actual
durable state are not supplied by these fixtures.

Each case is a separate independent example, not a sequence of transactions
against one store. The examples deliberately reuse fixture and transaction
identities; attempting to publish all cases sequentially would conflict.

The fixtures exercise:

- Empty logical content with its actual SHA-256 digest.
- Nonempty `abc` content followed by zero payload padding.
- A payload occupying the complete admitted payload area.
- A Query preserving the original O and historical Publish digest while using
  a different issuer, capability, signing key, clock, boot, service and subject.
  Query payload padding remains zero even when the historical length is nonzero.
- Distinct operation/current-request/historical-Publish digest domains and
  ordinary Ed25519 grant signatures over the specified domain-prefixed bytes.

Generate to a temporary file and compare before replacing a checked-in fixture:

```sh
(
  set -eu
  fixture_output=$(mktemp)
  trap 'rm -f -- "$fixture_output"' EXIT
  python3 -B spark/tests/make_slot_vectors.py > "$fixture_output"
  cmp spark/tests/protected_slot_vectors.json "$fixture_output"
)
```

The generator uses Python `cryptography` for disposable Ed25519 fixtures. It is
not imported into the runtime or an authorization boundary. Equal regeneration
only checks determinism of that producer; independent field/signature checking,
malformed-input policy, mutation/refusal tests and the remaining protocol freeze
requirements must be assessed separately.

The independently authored checker does not import the generator:

```sh
python3 -B -m unittest discover -s spark/tests -p test_protected_slot_vectors.py -v
```

It reconstructs expected bytes and digest inputs and uses the OpenSSL CLI for
public-key derivation, positive signature checks and mutation controls. OpenSSL
must be installed; missing tooling is a failure, not a skipped test. This is a
separate interface, not necessarily independent cryptographic code: Python's
`cryptography` package may use the same underlying OpenSSL implementation.
The negative checker currently recognizes the specifically observed OpenSSL
3.6.4 provider diagnostic, including its source location. A different diagnostic
raises an error requiring review; an arbitrary nonzero exit never qualifies as
signature rejection. Simulated process and tool failures exercise this rule.
This is a host-specific test contract, not a portable verifier qualification.

These positive byte fixtures do not establish a parser's behavior for malformed
messages, a verifier's key-encoding acceptance policy, replay/revocation handling,
or any authority/effect decision. No such implementation is introduced here.
