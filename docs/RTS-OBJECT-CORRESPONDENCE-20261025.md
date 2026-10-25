# Runtime object correspondence and frame reports

OBSERVED reproduction of three runtime archive members, with debug information
excluded. No SIA source, compiler policy, executable, installed path or toolchain
was changed. Rebuilt objects were never installed, linked into SIA or executed.

## Correspondence established

The original s-secsta.o, s-memory.o and a-except.o members were extracted from the
same libgnat.a identity recorded for the linked continuity probe. For each unit,
source files named by its installed ALI dependency records were copied and hashed.
The ALI-recorded compiler options were reproduced with additional stack/callgraph
reporting. Each bounded compilation exited zero with empty output streams.

The upstream runtime options include -gnatp. This is a reproduction of the existing
prebuilt runtime's configuration, NOT permission to suppress SIA's checks or
warnings. No SIA project flags or full proof/test roots were modified. Upstream
options and ALI metadata are not evidence that the runtime meets SIA's policy.

Original and rebuilt objects were separately processed by objcopy --strip-debug.
Their entire resulting files compare equal byte-for-byte, independently checked
by cmp. Executable/data, relocation, exception/unwind and symbol information remain
in the retained objects; this was not a selective comparison of function bodies.
Full original and rebuilt objects are also retained. Debug-inclusive object equality
is not claimed. Tool identities, commands, source maps and comparisons are recorded.

The s-secsta result contains 24 compiler frame rows; s-memory has 3; a-except has
151. These are report rows, not unique whole-program routines or coverage totals.
The first two units' rows are static. The exception object has 11 dynamic rows
WITHOUT GCC's bounded qualifier. Their reported byte numbers must not be used as
upper bounds. This is missing bound evidence, not proof of infinite resource use.

## Remaining runtime boundary

The reproduced secondary-stack callgraph includes a Get_Sec_Stack indirect-call
placeholder and imported allocator, handler and unwind operations. The exception
callgraph includes indirect handlers/traceback wrappers and secondary allocation.
Correspondence for these three objects does not close those callees or callbacks,
prove heap budgets, establish cumulative stack maxima, or show which paths run for
particular SIA inputs. No sums of individual frame sizes are presented as bounds.

This evidence strengthens the link between selected accompanying runtime sources,
new compiler reports and the runtime archive actually used by the preceding probe.
It does not reconstruct the vendor build's full custody, authenticate dynamic
libraries on later execution, or prove the complete runtime/compiler correct.
Original/current source and archive endpoint hashes match; continuous custody is
not established by endpoint equality.

Each compile retained the nonblocking heavy-work lock, one compiler process,
60-second limit plus 5-second termination grace, 2147483648-byte address-space and
536870912-byte file limits, with zero core allowance. No caps were raised.
The earlier full17-process-module result belongs to its original linked binary;
this wave performs no new runtime test and cannot enlarge that result's scope.

## Next step and acceptance

The next useful analysis is the reachable runtime error/exception and callback
closure of the actual continuity entrypoint. Use these matching-object reports as
inputs and keep unbounded/unknown frame contributions visible. Do not expand every
runtime unit indiscriminately or replace unknown costs with zero. Before a fixed
storage guarantee is accepted, dynamic sizes and callback targets/lifetimes need
source-bound limits, and the complete call paths must fit the actual primary and
secondary provision including failure paths. A different RTS or changed reporting
behavior requires preservation and full original qualification, not silent adoption.

No full DYN02/DYN06 compliance, new proof, independent execution, installed
continuity, whole-system assurance or certification is claimed. R05 BOTH and every
original proof, custody, continuity, retrieval, recovery, installation, release and
marketplace acceptance gate remains mandatory.

## Evidence and reproduction limits

The [receipt](RTS-OBJECT-CORRESPONDENCE-20261025.json) binds the
[public report archive](evidence/rts-object-correspondence-20261025.tar.gz).
Every archive member was read back against its source hash. Original runtime
sources, ALI metadata and original/rebuilt object bytes remain in the retained
local evidence directory named by the receipt. They are not bundled here.
Reproduction requires the matching installed GNAT runtime/toolchain and declared
source hashes; this public archive alone is not a complete offline toolchain.
Existing independent GPT-6.1 read-only review confirmed all three stripped-object
byte comparisons and the reported scope, without compiling or executing anything.
