# Checked-fill diagnostic plugin: failed build

Disposition: FAILED_NOT_ADOPTED. This isolated experiment did not produce a
shared library. No plugin was installed, loaded, or exercised against SIA.
The original plugin-free native analyzer gate remains unchanged and incomplete.

The retained upstream checked-memset arity defect motivated a small diagnostic
model using this compiler's actual analyzer event channel. The first source,
preserved as `checked_memset_model.initial.cc`, was rejected by source review:
an UNKNOWN pre-phase recheck could become a false overflow claim, and
state-dependent pre/post matching could suppress original unknown effects.

The revised source keeps matching dependent on direct builtin identity and
compatible signature, retains fill/dereference/return in the original PRE
phase, and distinguishes proved sufficient capacity, proved insufficient
capacity, and unresolved capacity. Unresolved capacity causes an explicit
unsupported-analysis error and terminated path. Missing analysis context is
fatal. This intentionally restricted diagnostic would reject unknown cases;
it is not a general checked-memset model or an admitted narrowing of SIA's
input domain. Diagnostics downstream of a rejected path would be unobserved.

One build ran with the existing nonblocking heavy lock, bounded address space,
file size and timeout, private HOME/TMPDIR, and strict compiler warnings.
`build/result.json` contains the exact command, environment, elapsed time and
selected input hashes before/after. `build/stderr` retains the complete failure.
`finding.json` derives diagnostic counts and hashes from those bytes. The
installed GCC headers emitted errors under the strict warning set; no primary
owned-source error was observed. That absence does not establish that this
source compiles. No warning suppression, system-header masking, changed limit
or unchanged retry was used.

Tracked identities cover the plugin header tree and selected compiler tools.
They do not cover every C++/system header or dynamic tool dependency; the
dependency file is retained. This is not complete toolchain provenance.

Actual GPT-6.1 independently reviewed the source and failed-build records;
it performed no execution. Registration, interception, sufficient/insufficient/
unknown capacity, invalid destinations, return identity, name collisions,
absent-plugin comparison and downstream diagnostics are all UNRUN.
The registration replacement leak and remaining compiler-interface assumptions
are also unresolved. No passing strict build, proof, product acceptance, or
compiler qualification follows.

The bounded route ends with this negative result. Further work returns to the
existing SIA obligations; another compiler experiment needs a concrete new
preservation argument and an admitted strict build path, not relaxed checks.

[Exact-source evidence package](NATIVE-FORTIFIED-PLUGIN-20261025.json).

The initial storage preflight filtered the string pin registry as though its
entries were objects. Its empty filtered list is not evidence of an unpinned
root. `storage-pin-readback.json` corrects that observation: the evidence root
is pinned. No offload or fresh backup qualification occurred.
