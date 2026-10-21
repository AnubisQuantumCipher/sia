# Preserve running assurance verification

A non-final checkpoint push previously canceled the experimental branch's
running CI suite. That discards its opportunity to produce a terminal result
and makes frequent evidence-preserving checkpoints compete with verification.

The experimental branch retains its existing concurrency group, with
`cancel-in-progress: false`. One workflow in that group may run while the
latest checkpoint waits. No job, resource limit, verification step, permission
or release/PR concurrency group changes. GitHub's default single pending slot
can still replace an older pending run; this is not an archive of every push.
The scheduling semantics are documented in
[GitHub's concurrency guidance](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

Acceptance requires live readback that the prior run remains intact and the
new source's run is queued or executes after it. A queued run is unverified.
Each source still needs its own terminal checks, and complete local SPARK
proof, independent acceptance, installation and marketplace gates remain
separate. This scheduling repair cannot turn an old pass into a new-source
pass or qualify a timed-out proof.
