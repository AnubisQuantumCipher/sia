# Linked continuity runtime diagnostic

OBSERVED / TESTED at the experimental test-adapter boundary. Complete static
allocation and stack sufficiency remain UNPROVEN. No product source changed.

Exact archived source: f3511696c9b1de80ab9fe3389a2aff051426bfdb.
The complete existing continuity project compiled using -c -U, original switches
and -fstack-usage -fcallgraph-info=su,da; its existing sole main then bound/linked
with a linker map and input trace. Both commands exited zero, with empty stderr.
Compile stdout is empty; link stdout intentionally records linker inputs.
Each command retained the 60-second cap, 5-second termination grace, one worker,
2147483648-byte address-space and 536870912-byte file caps, zero core limit and
nonblocking shared heavy-work lock. No source roots, contracts or tests removed.

## Binary evidence

The linked file identity is recorded in linked-identity.json, including hashes of
all input paths printed by the linker. Those are post-link observations, not an
atomic build-input custody attestation. Generated binder source and per-object
reports are retained. The binder provisions one default-sized secondary stack,
assigns Default_Stack_Size := -1 and invokes runtime initialization. A provisioned
initial secondary chunk is not a fixed total secondary-stack allocation ceiling.

The linker map includes libgnat.a(s-secsta.o), with its inclusion attributed to
a-except.o's SS_Allocate dependency. Exact linked-binary disassembly shows:

1. system__secondary_stack__ss_allocate calls allocate_dynamic.
2. allocate_dynamic contains a call to __gnat_malloc.
3. __gnat_malloc contains calls to malloc@plt.

This establishes a compiled allocation path in this exact binary. It does NOT
establish that the path was taken in the tests, quantify its request sizes or
prove reachability for every input. It rules out claiming that absence of a direct
allocation edge in an application-unit report alone establishes a heap-free binary.
Source-to-all-prebuilt-runtime-object correspondence remains unproved.

ELF dynamic metadata names libc.so.6 and ld-linux-aarch64.so.1; the interpreter is
/lib/ld-linux-aarch64.so.1. The file is not a wholly static runtime closure. The
link input identities do not authenticate libraries actually loaded by every
future run or establish hostile same-user custody.

## Unchanged original runtime controls

The complete original test_continuity_process.py module ran against this exact
new binary: 17 tests, OK, no skips (unittest reports 0.767s). Its literal vectors
cover restore/transition and policy refusal, malformed/truncated/excess input,
fragmented input/EOF waiting, descriptor errors, signal/deadline death, mismatched
executable and result identities, cleanup failure and unprivileged fork refusal.
Live resource-limit readback appears in runtime.stdout: stack 16777216 bytes,
address space 268435456 bytes, CPU 10 seconds, nofile16, nproc0, fsize0, core0.
The binary hash is equal before and after. The full test module was retained;
this is not the whole transport/Python/main runtime roster or system acceptance.
The unchanged tests establish observed successful/failed behaviors, not worst-case
stack usage, WCET, physical-memory sufficiency or zero heap allocation.

## Next engineering decision

Keep source-level allocation restrictions and full contracts. Neither the earlier
No_Secondary_Stack rejection nor this binary evidence justifies deleting diagnostic
or exception behavior. Separate the intended authority core's storage contract
from imported runtime capabilities, then establish complete bounded call/exception/
callback closure and exhaustion behavior for the exact composed entrypoint. A
restricted runtime alternative requires full behavioral equivalence and original
proof/test qualification; it cannot be substituted merely to obtain a green check.
Missing runtime bounds remain UNKNOWN rather than zero-cost assumptions.

This test-only adapter has no installed entrypoint and grants no runtime authority.
Full proof, R05 BOTH, source authentication, protected publication, actual harness
continuity, retrieval, recovery, installed Linux/Omarchy and release/marketplace
acceptance remain OPEN. No policy deviation or assurance certification is claimed.

## Retained evidence

The [receipt](LINKED-CONTINUITY-RUNTIME-20261025.json) binds the binary identity
and [portable evidence archive](evidence/linked-continuity-runtime-20261025.tar.gz):
source archive, build/runtime commands and logs, binder, map, selected disassembly,
per-object reports and identities. All archive members were read back unchanged.
Existing independent GPT-6.1 read-only review found no correction to the scoped
claims; it did not perform independent execution or establish system acceptance.

## Follow-up: selected runtime object correspondence

A [later reproduction diagnostic](RTS-OBJECT-CORRESPONDENCE-20261025.md)
matched the entire debug-stripped secondary-stack, memory-wrapper and exception
objects from the same runtime archive. Its exception reports expose dynamic
frames without compiler upper bounds. This strengthens selected source/object
correspondence; complete call paths, callbacks and stack budgets remain unresolved.
