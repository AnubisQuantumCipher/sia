# Continuity launcher descriptor contract

TESTED boundary clarification. The experimental continuity supervisor now accepts
only an exact Python int in the nonnegative, signed 32-bit Linux C-int descriptor
domain. It checks the native int width and rejects unsupported ABIs. Type and
range checks occur before comparisons with user-defined objects or decimal path
formatting. Descriptor zero remains valid; the executable path and all existing
prlimit arguments are unchanged for valid descriptors.

The existing internal caller obtains its descriptor from os.open. No defect was
reproduced in that normal path. This change makes the helper's representation
contract explicit; it does not establish descriptor liveness, exclusive custody,
or ownership. It does not bound every possible launcher argv[0], prove that an
exception path executes, or establish complete primary/secondary stack bounds.
Python allocation and scheduling remain environmental assumptions.

## Source-bound verification

Both original transport projects were freshly compiled with their complete -c -U
source rosters and then normally bound/linked, preserving all project switches.
All four commands exited zero with empty output streams. The complete original
SPARK Python roster plus the new controls passed: 122 tests, no skips, 11.173
seconds on the final test snapshot. The original continuity-process test file is
byte-identical to the base commit. All five probe binary hashes match before and
after both test runs. This is not the repository-wide Python suite or a fresh
GNATprove campaign.

New controls cover valid endpoints, wrong types, bool/int subclasses, hostile
formatting/comparison hooks, oversized integers, unsupported native ABI, and no
child launch when an invalid pin result is injected. The last control mocks
cleanup: real close(-1) raises OSError, so it does not qualify invalid-descriptor
cleanup or error precedence. Removing only the new guards makes the selected
adversarial tests fail; those negative results remain in the evidence.

The frozen Ruff profile passes with no suppressions, empty diagnostics and empty
stderr. CI now includes the source and test in both the analyzer and suppression
scan, and runs the new tests without requiring a probe binary. Hosted execution
of this new step is pending; local results do not establish hosted success.
Existing GPT-6.1 review found no remaining source blocker for this narrow change.
That review was read-only and did not independently build or execute the code.

Each build/test retained the shared nonblocking heavy-work lock and existing
60-second limit, 5-second termination grace, 2147483648-byte address-space limit,
536870912-byte file limit and zero core allowance. No caps were raised.

## Evidence and remaining acceptance

The [receipt](CONTINUITY-DESCRIPTOR-DOMAIN-20261025.json) identifies the tested
source, tools, commands and [public evidence archive](evidence/continuity-descriptor-domain-20261025.tar.gz).
The local directory retains the complete snapshot and fresh binaries. The public
archive contains the source manifest, changed Python files, commands, output,
binary hashes, review and negative controls. It is not an offline toolchain.
The source manifest describes the tested snapshot before these report files were
added; it does not purport to be the final commit's complete tree manifest.

Runtime exception/callback closure and dynamic frame bounds remain the next
assurance investigation. No historical unknown frame cost becomes zero because
this helper is bounded. All original assurance, R05 BOTH, recovery, continuity,
installed-operation, release and marketplace gates remain required. No deployed
continuity guarantee, whole-system proof or certification follows from this change.
