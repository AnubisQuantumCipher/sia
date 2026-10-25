# Stack and secondary-allocation diagnostic

Status: OBSERVED compiler reports; complete stack/resource guarantee UNPROVEN.
Source: 52107954fd197b51d940551b88353af720306e14, unchanged archived SPARK inputs.
No implementation, installed path, contracts, restrictions, root roster or caps changed.

## Completed observations

The original main project and both existing transport projects compiled with their
original switches plus `-fstack-usage -fcallgraph-info=su,da`, using `-c -U -j1`.
Each completed with exit zero and empty stdout/stderr. The retained command records
bind each project and the original 60-second limit plus 5-second termination grace,
2147483648-byte address-space limit, 536870912-byte file limit and nonblocking shared
heavy-work lock. These process limits do not prove descendant or runtime bounds.

The combined inventory contains 102 `.su` / `.ci` report pairs and 1324 rows,
including repeated core units compiled under the three project configurations.
These counts are observations, not unique-routine or whole-system coverage counts.
Two distinct Decode_Header functions are `dynamic,bounded`: checkpoint 9696 bytes
and current 10288 bytes. The report sites align with retained contract snapshots.
This qualifier is not evidence of unbounded allocation. Largest listed main-project
frame is continuity_frame_wire_tests at 748848 bytes. SIA_Pack_Proposal.Take is
241248 and Finish 156048 bytes. The continuity test adapter reports 68928 bytes.
These are compiler-reported individual frames, NEVER cumulative stack maxima.

Only the pack_proposal_probe report contains explicit direct SS_Allocate edges in
this report set, at its full exception-information concatenation. That observation
DOES NOT establish absence of secondary allocation in imported libraries, callees,
exception handlers, indirect callbacks, binder initialization or deployed programs.
The transport adapters are test-only Linux descriptor adapters, not installed
resident qualification. Their reports include unresolved RTS/OS/memory/check calls.

## Rejected restriction diagnostic

A separate copy appended `pragma Restrictions (No_Secondary_Stack);` to the shared
configuration without changing the complete main-project compile roster. It failed
with exit 4 at pack_proposal_probe lines 120, 149, 150 and 167: full exception reporting
and Ada.Command_Line.Argument results. The compiler may stop before other errors;
this is not an exhaustive negative inventory. This pragma was NOT ADOPTED.
The primary source copy and published ADC remain unchanged.

## Runtime localization and assumptions

Six exact installed runtime source files are retained and hashed. This is source
inspection, NOT established correspondence to linked prebuilt runtime objects.
The diagnostic did not bind, link or execute the programs.

- `a-comlin.adb:58-71`: Argument sizes a String using imported Len_Arg, then calls
  imported Fill_Arg. This path establishes no SIA-specific argument-size bound.
  Native Python tests use temporary paths but do not establish a general argv bound.
- `a-exexda.adb:510-525,704-727`: Exception_Information includes tailored traceback
  output. A registered wrapper is called indirectly. No wrapper-output bound is
  established by this inspection.
- `a-except.ads:244-276` and `s-parame.ads:178`: bounded occurrence fields do not by
  themselves bound total formatted exception information or transient storage.
- `s-parame.ads:96` selects dynamic secondary stacks in installed source;
  `s-secsta.adb:175-198,660-664` can allocate a new heap chunk or raise Storage_Error.
  This does not prove which prebuilt runtime objects a final binary uses.

## Decision and next acceptance work

Preserve contracts, original tests and full failure diagnostics. No semantics-
preserving repair has yet been demonstrated. Removing Old snapshots, truncating
exception information or splitting an existing single output operation would alter
contracts or potentially observable failure behavior. No such change is authorized
as a silent policy exception.

DYN06 and Power of Ten rules 2, 3, 7, 9 and 10 remain open for the composition.
The next supported step is a complete, version-bound call/stack analysis for the
actual linked authority entrypoints, including binder/elaboration, runtime and C
calls, exception paths, callbacks, primary and secondary stack provision and
exhaustion behavior. A compiler frame inventory is an input to that analysis,
not a replacement. Missing callable bodies must remain unknown, never zero cost.
The allocation controls do not imply RTS-wide No_Secondary_Stack enforcement.

Original full proof, R05 BOTH, protected authority, continuity, retrieval, recovery,
installed Linux/Omarchy and release/marketplace gates remain unchanged. No release
acceptance, certification, deviation approval or new mathematical proof is claimed.

## References

GCC 16.1 Developer Options and the GNAT stack guide were retrieved and hashed in
references.json. Per-function report meanings follow GCC documentation; runtime-
specific secondary-stack behavior must not be generalized from another RTS profile.
The source archive, admission/results, raw compiler diagnostics and per-object
reports are retained. Endpoint source hashes equal admission; continuous custody
and compiler/backend-to-library correspondence are not established by that equality.

## Evidence and review

The [receipt](ADA-STACK-DIAGNOSTIC-20261025.json) binds the exact compiler reports,
source archive and rejected restriction diagnostic in the [portable archive](evidence/ada-stack-diagnostic-20261025.tar.gz).
All archive members were read back against their source hashes. Installed runtime
source files and downloaded reference pages remain in local evidence; the archive
includes their identities, not a claim that they match linked runtime binaries.
Existing independent GPT-6.1 read-only review found no correction to this scoped
evidence checkpoint. It did not execute builds or establish whole-stack acceptance.

References: [GCC 16.1 developer options](https://gcc.gnu.org/onlinedocs/gcc-16.1.0/gcc/Developer-Options.html)
and [GNAT stack guide](https://docs.adacore.com/gnat_ugx-docs/html/gnat_ugx/gnat_ugx/the_stacks.html).
