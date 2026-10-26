# Release metadata and ordinary runtime FIFO admission — 2026-10-26

Two remaining read opens in `bin/siarelease.py` now include `O_NONBLOCK` before
the existing descriptor-type checks. A no-writer FIFO therefore reaches the
named refusal instead of waiting for a writer. The stable owned reader serves
installer runtime, resident runtime, and first-light completion metadata. The
ordinary runtime-member reader serves both runtime digest and fence validation.
The existing owner, link, mode, size, generation, version, digest and receipt
checks remain unchanged. The change grants no additional authority.

The baseline at `57fa2a1e03f0e1daa384f252771743036a9b3e4f` ran the same eleven
new cases before either flag change. All five FIFO cases exceeded their frozen
three-second deadlines; each timed-out child was killed and reaped with exit
`-9`. The six controls returned their expected results. The suite exited `1`;
this failure and its raw outputs remain retained.

After the two flag changes, all eleven cases pass. The three metadata FIFOs and
both runtime FIFO consumers return exit `2`, empty stdout and their exact named
refusal. Supported regular metadata, absent optional metadata, both downgrade
refusals, and both runtime CLI positives retain their expected behavior. The
runtime fixtures use the complete supported eight-member legacy rung with
ordinary mode `0600` files and an independently constructed digest. The fence
case exercises ordinary reading, not the separate mode-zero `O_PATH` branch.

Each case uses a fresh private `/dev/shm` directory, bounded input and output,
explicit child termination/reaping, and before/after source and fixture checks.
The checks compare actual bytes, identities, metadata and directory membership;
access time is excluded because reads may change it. A separate actual GPT-6.1
execution passes the same eleven cases and verifies child and fixture cleanup.
The original sixteen fence cases and nine unchanged selected regressions also
pass. The existing installer downgrade test remains unchanged.

The frozen strict analyzer reports zero findings for the full release module,
new test module and existing fence-test module. CI now includes the release
module and new test in both existing suppression and analysis rosters. The
complete updated CI static-analysis run block executes locally with exit `0`,
empty diagnostics and empty stderr. Functional runs preceded the final CI-only
roster addition; product and test hashes did not change. This is local execution
of that step, not a full hosted-CI pass.

Source identities, baseline/candidate observations and retained receipt hashes
are in [the evidence record](RELEASE-METADATA-FIFO-20261026.json). The regression
is reproducible from the repository root with:

```sh
/usr/bin/python3 -I -S -B -W error tests/test_release_metadata_admission.py -v
```

This establishes TESTED behavior for these finite FIFO and regular-file cases.
It does not establish universal device/filesystem latency, incompatible lease
behavior, hostile namespace-race containment, or the full R13 per-call matrix.
An incompatible regular-file lease may refuse rather than block. The five-open
source inventory in this module is not a whole-repository reader inventory.
Comprehensive R40 analysis and installed lifecycle acceptance remain open.

The prior full proof remains operator-interrupted with payload exit `143`; its
exact reconciliation is not proof success or successor authority. No proof was
restarted by this repair. The prepared proof still requires an aggregate working
space budget and safe capacity beyond the reserve. Eleven non-SPARK test/support
units remain explicit exclusions. Native custody, actual compaction, R05 BOTH,
Astra/max judge, installed acceptance and all release gates remain incomplete.
