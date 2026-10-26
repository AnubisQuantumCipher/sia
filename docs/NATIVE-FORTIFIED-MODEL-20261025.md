# Fortified memset analyzer-model mismatch — 2026-10-25

Disposition: OBSERVED installed-compiler diagnostic behavior and a matching
pinned-source arity defect. Proposed compiler patch is UNBUILT / NOT ADOPTED.
No SIA source, installed compiler, warning policy or production limits changed.

## Earlier SIA frontier

The original capped diagnostic remains SHA-256
`05b1fef546c156fca1d0a6c40c723d4513ba77ca3035cf011af978986a7105e6`.
The newly retained numbered window at lines 143695–143800 has SHA-256
`ab8e4196d91f80c7b785cff9c513b881e63e11161c69863c2d65af137a573ec1`.
Its extractor checked the complete source hash, size and unchanged metadata.

Line 143712 considers `__builtin___memset_chk(_1,0,256,_33)` inside
`outgoing_control`. The incoming region model at line 143725 becomes the
outgoing model at 143726: the latter conjures changed values for both the
transport region and the caller's `mw_state`, marked ESCAPED/TOUCHED. The
unknown-call uncertainty at 143727 and EN78→79 edge at 143799 are retained.
This is an explicit early loss of precision before the previously traced
deadline-fault split. It is not a claim to have enumerated every clobber or
proved this one call is the unique cause of the complete failed analysis.

## Pinned compiler source

References use package-named GCC revision
`301eb08fa2c5b6f3045260bf1294c2e2bacbcd90`. Exact fetched files, URLs, sizes,
hashes and original license notices are retained under `gcc-source/` and
`gcc-references.json`.

At local `kf.cc:713–716`, `kf_memset::matches_call_types_p` accepts only three
arguments, regardless of its checked-variant flag. The checked builtin is
registered with that flag set at local line 2319. It takes four arguments.
The name-based matcher in `known-function-manager.cc` rejects incompatible
calls. The retained `region-model.cc` then treats an unmatched builtin as
having unknown side effects. This is a specific source-level explanation
consistent with the installed trace, not a general binary/source equivalence
certificate.

The matcher also has an earlier builtin-code route that bypasses this
argument predicate. The inspected registrations here are name-based; this
finding does not claim the predicate controls every builtin dispatch route.

Primary sources:
[known memset handler](https://raw.githubusercontent.com/gcc-mirror/gcc/301eb08fa2c5b6f3045260bf1294c2e2bacbcd90/gcc/analyzer/kf.cc),
[known-function matcher](https://raw.githubusercontent.com/gcc-mirror/gcc/301eb08fa2c5b6f3045260bf1294c2e2bacbcd90/gcc/analyzer/known-function-manager.cc).

## Isolated installed-compiler reproduction

`fortified_probe.c` is diagnostic-only and was never linked or executed. It
compares an ordinary builtin fill with a checked builtin fill, using distinct
static arrays and markers. Both paths constrain the requested length to the
array; the checked path also constrains its capacity. The runner preserves
the original strict cc1 warning/analyzer/optimization options, including
`-Werror`, fortification declaration and both complexity warnings. It retains
the existing nonblocking heavy lock, memory limit and time limit, with a
smaller diagnostic-file limit. No full witness analysis was retried.

Installed cc1 SHA-256:
`01be12f35423d142ca7d54518108ad265c422eff61213308f39d480dfca8d897`.
Probe source SHA-256:
`c46238a186bc1c6bdd38708377508499567db4172985371567df65160bd4579b`.
All recorded input hashes match before and after. Command, environment, raw
outputs, elapsed time and compiler dump are under `run/`.

The compiler exits 1 because the deliberately requested `__analyzer_eval`
diagnostics are errors under `-Werror`. This is not a passing strict build.
Both marker queries print TRUE because earlier processing folds them to
`__analyzer_eval(1)`; they cannot establish preservation by the analyzer.
Both first-byte queries print UNKNOWN with variable-length fills. These
query results alone fail to distinguish the suspected model behavior.

The retained internal trace does distinguish it:

- Line 1169: ordinary fill leaves its marker `(int)42`, represents the target
  as a sized region filled with repeated zero, and reports
  `m_called_unknown_fn: FALSE`.
- Lines 1770–1772: checked fill starts with its marker `(int)42`, then conjures
  changed marker and target values and reports `m_called_unknown_fn: TRUE`.

Thus the reduced run reproduces the unknown-side-effect fallback in the
installed compiler. It does not reproduce the entire SIA state explosion or
prove a new compiler would complete SIA within the existing bounds.

## Proposed correction and required acceptance

`proposed-kf-memset-arity.patch` changes only the handler's argument-count
predicate: four for the checked variant, three for the ordinary variant.
`kf.cc.proposed` retains the complete proposed file. This is a review artifact,
not an installed toolchain, qualification result or release dependency.

The existing handler does not explicitly model the checked call's fourth
argument or failure termination. An arity correction alone must not be
advertised as complete fortification semantics. A qualified successor needs
regressions for ordinary and checked fills, invalid capacity, destination
bounds, malformed signatures, preserved unrelated state and subsequent
diagnostics, with clear treatment of terminating versus returning paths.
Compiler source/binary provenance, relevant upstream regression evidence and
the original full SIA analysis are still owed. No analyzer plugin, suppressed
warning, disabled fortification, root omission or unconditional fault writeback
is admitted by this result. No upstream message or issue was sent.

Smallest sound next step: review and qualify this model correction, including
its bounds/failure behavior, in an isolated versioned compiler route within
existing resource limits; if that route cannot be established, retain this
diagnostic and continue the existing R05/SDK/SPARK obligations. Do not launch
an unbudgeted full compiler build or repeat unchanged failed SIA analysis.
The necessary first-fault behavior stays intact. All original release,
installed-continuity and whole-system assurance gates remain open.
