# Compile-only allocation controls

This lane qualifies narrow GNAT compiler-policy observations. It does not
prove SIA, the runtime, stack bounds, physical resource containment or safe
reclamation. These fixtures are intentionally invalid under their selected
restrictions. They are never linked or executed, and this directory is outside
the existing project source directories.

Use GNAT 16.1.0, a new output directory, and the existing resource envelope:

```sh
source /home/sicarii/opt/gnat/env.sh
flock -n /home/sicarii/.worldline-heavy.lock \
  prlimit --as=2147483648 --fsize=536870912 --core=0 \
  timeout --kill-after=5s 60s python3 -B -W error \
  spark/check-allocation-controls.py \
  --compiler /home/sicarii/opt/gnat/gnat-aarch64-linux-16.1.0-1/bin/gcc \
  --output /new/output/directory
```

The runner uses five seconds per compiler process and five seconds of kill
grace. The outer deadline bounds the complete roster. Compiler and workspace
are trusted inputs; Python and subprocess behavior are unproved. These
per-process/file limits do not establish an aggregate service resource bound.

The shared ADC must match a closed, explicit list of all existing restrictions
and `Assertion_Policy (Check)`. A positive fixture must compile cleanly under
that configuration. Each of four named allocation restrictions also has a
clean positive control, a named negative diagnostic at the exact fixture line,
and an unrestricted baseline. Extra diagnostics, stdout, missing diagnostics,
timeouts and unexpected exits fail the lane. Diagnostic matching is specific
to the qualified compiler; a future diagnostic change requires review.

The first three unrestricted baselines still fail strict allocator warnings.
Those warnings are required evidence in these intentional-invalid control
cases, not suppressed production warnings or clean differential results.
Only the task fixture provides a clean unrestricted/restricted differential.
`Immediate_Reclamation` is accepted in the shared configuration; its runtime
semantics are not tested. Complete DYN02 access-type/pool checking is separate.
The original failed control attempts remain in the
[allocation-policy checkpoint](../../docs/ADA-ALLOCATION-POLICY-20261025.md).

`results.json`, source/configuration copies, compiler commands and raw stdout
and stderr remain in the new output directory. The runner refuses an existing
directory. Output reads are bounded to 16384 bytes; a larger diagnostic is a
failure, not truncated success. An interrupted run may lack a complete results
file; retained intermediate files cannot establish a pass.

The existing hosted test job now declares this lane before full unit discovery.
It downloads [GNAT FSF 16.1.0-1](https://github.com/alire-project/GNAT-FSF-builds/releases/tag/gnat-16.1.0-1)
for Linux x86_64, verifies archive SHA-256
`9f74f58a827a2ad40dd84c72a413e75ea52888e0d8f7e252fba4d26762402703`,
and checks the compiler version. The pin was cross-checked against the
[official Alire index](https://github.com/alire-project/alire-index/blob/master/index/gn/gnat_native/gnat_native-16.1.0.toml).
It adds no job or concurrency slot. Download and extraction have separate
60-second limits; compile controls retain their existing 60-second whole-run
limit. Hosted logs show the result and bounded diagnostic previews. A declared
workflow is not evidence that the hosted compiler lane has executed.

The seven Python gate tests exercise missing policy directives, byte limits,
unexpected diagnostics/exits, warning-only false positives and stale outputs.
They run in existing CI static and boundary-control steps. They test the result
gate, not GNAT semantics. Local aarch64 execution and hosted x86_64 execution
must be reported separately; neither substitutes for full-project proof,
installed Linux/Omarchy qualification or release acceptance.
