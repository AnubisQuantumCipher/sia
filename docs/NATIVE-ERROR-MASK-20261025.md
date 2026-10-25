# Native unsigned-mask normalization: rejected diagnostic

**FAILED_NOT_ADOPTED.** One strict full-translation-unit compiler attempt failed
under the original limits. No production or installed code changed. This result
does not authorize a retry, native dispatch, merge to main or release.

The earlier [normalization attempt](NATIVE-ERROR-NORMALIZATION-20261025.md)
failed after GCC reconstructed its zero-input branch. This separate candidate
used unsigned operations to construct a zero mask, then added `EIO` only for a
zero error. The original conditional store, first-error behavior, false return,
all callers and the complete signed-input domain remained in scope. Explicit
static assertions selected the unsigned width and positive fallback range.
The two accompanying headers were byte-identical to the predecessor, and inverse
substitution reconstructed the complete previous translation unit.

A manually written 32-bit SMT model checked output equivalence, signed cast
range and addition overflow. Z3 returned `unsat` for the counterexample query;
wrong-shift, missing-fallback and missing-range controls each returned `sat`.
This is **MODEL_CHECKED**, not a verified translation of C, certified solver
proof, compiler-correctness result or whole-system proof. Store and aliasing
behavior are outside the expression model. Source structure, rather than that
model, supports the argument that those effects were preserved. Conditional
named-scalar accounting also does not establish native stack or timing bounds.
JACKAL returned `exact`, `formal=false` for that separate scalar arithmetic;
its rational lane does not cover the bit-vector/C semantics checked here.

## Preparation and the retained context failure

The first preparation passed 56 controls but its live dependency check refused
a changed shared `MEMORY.md` file before any compiler invocation. Its packet and
failure remain intact. A separate V2 packet explicitly records the predecessor
context row and the newly selected row in both inner and outer dependency maps.
Every noncontext predecessor dependency remains literal. Context is not approval.

V2 passed 68 preparation controls, including unauthorized projection, stale and
conflicting context, substitution, drift and map-overflow refusals. Its 512-entry
before/after endpoint snapshots matched, within the unchanged map limit. The
frozen partial Python static profile reported no findings. These checks qualify
only the tested preparation behavior. They do not prove the Python runtime.

The failed normalization attempt's 508-entry map remains authenticated history.
Each dependency unique to that attempt, and its source-parent/PCH checks, has an
explicit disposition. The new packet starts from the authenticated 492-entry
predecessor; it does not silently reduce or repin the failed packet. Original
source projections, SDK checks, roots, compiler warnings, output/dependency
checks, and resource limits remain required.

An administrative metadata read initially used a 1 MiB document limit for an
existing terminal receipt governed by the original 2 MiB receipt limit. It
refused before completing the metadata. The refusal is retained; the follow-up
used the already established receipt limit for that file only. No compiler or
resource limit was increased.

## Actual compiler result

The sole compiler attempt exited **-25 (SIGXFSZ)**. It emitted **19
analyzer-too-complex diagnostics**, reached the original 536870912-byte dump
limit, left assembly empty, and produced no dependency file. The controller and
outer observer returned failure. All 512 outer endpoint pins matched; inner
before/after records also matched. Those matches establish observed input
stability, not successful compilation or hostile-writer protection.

Selected dump lines 161–192 show straight-line unsigned mask operations,
addition and the fault-slot store in `mw_fail.part.0`. Unlike the previous
candidate, the intended local transformation materialized. The remaining
diagnostics include that store under direct and namespace-mediated send paths,
plus send/namespace terminal points. This bounded excerpt establishes neither
a unique cause nor completion of the truncated analysis.

An existing actual GPT-6.1 reviewer independently inspected source, endpoint
hashes, raw receipts, diagnostics and the selected excerpt. It performed no
compiler/control execution or whole-dump semantic review. The independently
reviewed conclusion is **FAILED_NOT_ADOPTED**. No unchanged retry or further
syntax-only normalization variant is justified by this evidence.

The [evidence inventory](NATIVE-ERROR-MASK-EVIDENCE-20261025.json) binds a selected
forensic archive, including exact candidate source and the manual model. It is
host-bound diagnostic material, not a portable build package. The full incomplete
dump remains local and hash-bound; the archive contains only its selected excerpt.

The next native step needs substantive causal evidence from the retained send
and fault-state paths before another source change. Full native qualification,
SPARK composition, R05 BOTH, SDK runtime, protected publication/recovery, actual
harness continuity, installed qualification and release/marketplace acceptance
remain open. Passing Power-of-Ten checks or this expression model would not
establish whole-system assurance or avionics certification.
