# Maintainers and review lanes

SIA is maintained by **Khephri Labs** ([@AnubisQuantumCipher](https://github.com/AnubisQuantumCipher)),
who holds release authority and the marketplace verify chain.

## Credited reviewers

Two outside contributors found SIA within a day of its marketplace listing and
each improved it with a receipts-grade contribution. Both hold standing review
invitations for the lanes they know best:

- **[@m10ust](https://github.com/m10ust)** — the installer / runtime member-set
  / receipts lane. Root-caused the fresh-machine install failure
  ([#2](https://github.com/AnubisQuantumCipher/sia/issues/2)) with a full
  reproduction and workaround, then verified the fix. Their audit of the
  installer's transactional hygiene is the project's only outside audit of
  that lane.
- **[@webdevtodayjason](https://github.com/webdevtodayjason)** — the Obsidian
  organ and its records-not-content contract, which exists because of their
  proposal and working sidecar reference
  ([#1](https://github.com/AnubisQuantumCipher/sia/issues/1)).

## The ladder

Trust here grows by earned scope, in the open, on the contributor's own
timeline — never by an early grant that neither side has structure for:

1. **Credited reviewer** (current): named in the changelog and here; standing
   invitation to review their lane in each release.
2. **Lane collaborator**: on sustained engagement, triage access and an
   explicit say over changes in their lane before those changes ship.
3. **Co-maintainer**: after real review cycles, `main` becomes
   branch-protected (pull requests plus status checks required) and write
   access follows — safe by construction, not by hope.

Progression is offered, never assumed; declining any step costs nothing and
is not revisited uninvited. What moves someone along the ladder is the same
thing that started it: real engagement with real evidence.
