# Runtime callback and last-chance boundary

OBSERVED / INCOMPLETE. This investigation preserves all product source, compiler
checks, contracts, test rosters and resource limits. It does not qualify a new
runtime, prove callback immutability or establish a cumulative stack bound.

## Exact linked runtime evidence

Three more runtime members used by the retained continuity executable were
reproduced from their accompanying sources and ALI-recorded compiler options:
`s-soflin.o`, `s-stalib.o` and `a-elchha.o`. All three compile commands exited zero
with empty streams. Entire original/rebuilt files compare byte-identically after
`objcopy --strip-debug`, with separate `cmp` confirmation. Full original objects,
rebuilt objects and input sources remain retained locally. No rebuilt object was
installed, linked into SIA or executed. The upstream `-gnatp` option reproduces
the vendor runtime; it is not a change to SIA's compiler or proof policy.

Their compiler stack reports contain 30, 5 and 1 rows respectively. The first
two reports contain static frames. The last-chance handler reports 112 bytes
with the `dynamic` qualifier, without `bounded`: 112 is not its upper bound.
Its source includes a variable-sized command-name buffer on one traceback path.
Descriptor-domain validation alone does not prove this path's complete bound.

The extended inspection combines 17 declared compiler reports. Direct emitted
edges reach 153 nodes from `main`, with 47 unresolved frame entries; the Ada
entrypoint reaches 127, with 28 unresolved entries. Both include the last-chance
handler. Unknown nodes, compiler ghost wrappers, indirect targets and native
callees remain unresolved. These counts do not measure coverage. Graph paths
are syntactic possibilities, not executed paths, feasibility proofs, complete
recursion analysis or stack sums.

## Defaults observed; setters retained

Static inspection of the exact linked ELF and one disposable debugger run
stopped at the Ada entrypoint after elaboration observed:

- Both exception-traceback flags and the trace-mode byte were zero; the source
  initializes the mode to `RM_Convention`.
- The traceback-decorator pointer, global exception actions and hook-initialized
  flag were null/zero.
- Secondary-stack, current-exception and task-termination soft links pointed to
  their non-tasking implementations.

The debugger child had the configured address-space, primary-stack, CPU,
descriptor, process, file-size and core limits, read back from `/proc`. It was
killed before input processing. The original binary hash was unchanged. This
was a debugger launch with a minimal environment, not `continuity_process.run`
or an installed harness lifecycle. The language/frame mismatch and unavailable
debugger cache-directory warnings are retained. No clean-debugger-output claim
is made. One stopped process does not establish values for every launch or their
invariance through every exception and finalization path.

The setter investigation is deliberately separate. Named registration routines
for global, unhandled and per-ID exception actions were absent from the retained
symbol table and direct instruction references. That is not proof of no equivalent,
inlined, indirect or foreign write. Trace-on, trace-off and decorator-registration
routines are present. A direct decorator-registration call exists in symbolic
traceback elaboration. Original archive-member relocation disassembly identifies
the GOT-based access to the symbolic-trace flag, its conditional branch and
stores to the decorator and trace-mode variables. These two writer objects were
extracted, not rebuilt or source/object-matched in this wave.

Do not prune callback paths from the observed defaults. Native initialization,
relocation/loader behavior, all reachable writers, aliasing and foreign-code
assumptions still need explicit closure. The earlier text-only symbol-reference
scan found no matches because linked instructions used register/GOT references;
that inadequate method is retained and is not evidence of writer absence.

## Rejected shortcut and diagnostic limitations

Replacing the adapter's `GNAT.OS_Lib` calls with direct C imports would not by
itself remove the relevant runtime subsystem: Ada's exception unit independently
imports symbolic traceback, which imports the OS library. No adapter rewrite
was made on that rationale.

The first graph parser rejected GCC's triangular ghost-node annotation. Its
failed version and failure record remain retained. The repaired grammar accepts
the observed annotation while preserving unknown frames. Controls reject unknown
syntax, conflicting frame definitions and missing endpoints, and keep an unknown
triangle node unresolved. Repeated derivation is byte-identical. The frozen Ruff
profile passes for the reproduction and graph scripts. These checks do not
qualify a general compiler-output parser or prove graph completeness.

## Acceptance and next step

This advances the Power-of-Ten control-flow, storage and indirection assessment
by binding selected runtime bodies and exposing unresolved failure-path costs.
It does not establish literal allocation-free Python/Linux operation, runtime-wide
rule compliance, a fresh SPARK proof or whole-system assurance.

Next, close the linked native-initialization and writer paths using relocation-
aware evidence and explicit foreign-code assumptions. Retain dynamic frame sizes
as unknown until their inputs, lifetimes and complete call paths have bounds.
All original acceptance gates, including R05 BOTH, protected runtime, repeated
compaction, held-out retrieval, off-host recovery, installed qualification and
release/marketplace publication, remain mandatory.

The [receipt](RUNTIME-CALLBACK-CLOSURE-20261025.json) binds the
[public diagnostic archive](evidence/runtime-callback-closure-20261025.tar.gz).
The archive contains reports, commands, observations, failures and identities;
the full matching toolchain, runtime sources and objects remain local. It is not
a self-contained offline reproduction kit. Existing GPT-6.1 review was read-only,
with no independent compilation, debugger execution or stack acceptance.
