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
  that lane. They then took the standing invitation and reviewed the first
  module-split extraction (v1.5.2…v1.6.0) — four digest routines, the
  release/staging lists, `bin/siagraph.py`, the bind/invoke façade and the
  test mirror — running the release suite from a fresh clone at 0fb8332 on
  Arch (92/92 green) and installing v1.6.0 on their own machine. It returned
  no HIGH and no MEDIUM, three seams where a real property was held by
  discipline rather than by a check, and one report that the guided
  installer's terminal appeared only at the end of the install. The three
  seams are closed in 1.7.4; the terminal report traced to two defects on
  this side, closed in 1.7.4 and 1.7.5; and the review lane is standing for
  the remaining extractions on their own timeline.
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
