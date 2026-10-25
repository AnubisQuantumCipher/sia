# Native error normalization: rejected diagnostic

**FAILED_NOT_ADOPTED.** The strict IO analyzer still failed under its original
limits. No production or installed code changed, and no native acceptance follows.

The candidate changed only the right-hand side in `mw_fail`:

```c
/* Previous */
s->faults[phase]=error!=0 ? error : EIO;
/* Candidate */
s->faults[phase]=error + EIO * (error == 0);
```

The surrounding conditional store was preserved. Source review supported the
case argument for the admitted Linux integer definition of `EIO`: nonzero
errors remain unchanged and zero becomes `EIO`, without adding writes to an
already populated fault slot. The six header-chain records matched the pinned
SDK inventory. JACKAL returned `exact`, `formal=false` for the separate
polynomial identities; that is not C semantics or overflow proof.

The hypothesis was that removing the source ternary could reduce analyzer
branching. The retained compiler supergraph instead contains
`if (error_8(D) == 0)`. The intended branch removal did not materialize.

The new translation unit and two byte-identical headers occupied a separate
three-file namespace. Checks still covered the complete predecessor namespace
and all 492 previous dependency entries. The composed endpoint readback covered
508 entries, within the unchanged 512-entry limit. Compiler flags, helper roots,
generic domains, warnings and resource limits were preserved; only source and
output paths changed.

Preparation controls passed: **56 tests, no skips** (40 inherited/rebound and
16 added namespace/dependency controls). The frozen partial Python static
profile reported no findings. These results qualify only the tested preparation
behavior, not the C implementation or complete Python runtime.

The sole compiler attempt returned **-25**, with 19 emitted
`analyzer-too-complex` diagnostics. Its dump reached the original 536870912-byte
limit and remained incomplete; the dependency file was missing and assembly
empty. All 508 endpoint pins matched before/after. The absence of additional
diagnostics in an incomplete run proves no helper passed. The candidate is
rejected; this result supports neither a repeat nor a new variant.

Two administrative failures are also retained. A prelaunch helper incorrectly
used an 8 MiB read limit rather than the established 64 MiB limit, and the shell
then incorrectly invoked the observer despite that failure. The observer failed
before dispatch because its output directory did not exist. A corrected
admission completed before the separate, sole compiler invocation. A first
sealing attempt compared full stat records including access time and failed;
the failed path/delta was not recorded. The final seal used the established nine
identity fields and rechecked the admitted endpoints. Neither failure is erased
or counted as a compiler success.

An independent actual GPT-6.1 reviewer inspected source, controls, terminal
receipts and the selected dump excerpt. It performed no independent execution
or whole-dump semantic review. The [evidence inventory](NATIVE-ERROR-NORMALIZATION-EVIDENCE-20261025.json)
binds a selected forensic archive; it is not a portable build package or complete
dependency closure. The full incomplete dump remains locally retained and
hash-bound.

The next native attempt requires a different, evidence-supported design that
preserves the original behavior and analysis scope. Raising limits, hiding
diagnostics, removing roots or repeating this source is not justified. R05,
SDK runtime, full SPARK proof, protected publication/recovery, harness continuity,
installed qualification and release/marketplace acceptance remain open.
