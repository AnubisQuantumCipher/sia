# Continuity adapter: current named host inputs

An owner-run read-only observation matched all **1,056 named files, 88
directories and eight native dependency aliases** against the existing
continuity wrapper manifests. Declared startup absences passed; no site `.pth`
hook was found. The process exited zero, observer source remained unchanged,
and input manifest hashes matched before and after. No candidate or wrapper
module was imported or executed.

This is **OBSERVED_NAMED_ENDPOINTS_MATCH**, not runtime qualification. File
comparisons enforce the fields supplied by each manifest; not every manifest
pins all nine observed identity fields. Directories receive identity checks,
not complete directory-entry comparisons. Before/after describes the manifests
and individual file reads, not two full host snapshots or continuous custody.
Startup-name observation does not establish all import-resolution behavior.

The first attempt ran inside a read-only bwrap namespace and returned NONPASS:
root-owned endpoints appeared as UID/GID 65534. A one-file control reproduced
that ownership remapping while direct host metadata and bytes matched their
baseline. The complete successor used the identical observer outside that
namespace and matched the declared inputs. Both results remain retained; the
first is not evidence of host corruption.

The observer used the existing nonblocking heavy-job lock, a 30-second work
limit with one five-second termination grace, 2 GiB per-process address-space,
512 MiB file-size and zero-core limits. Named source reads have explicit file,
roster and aggregate byte limits. The original strict rule profile reported
zero diagnostics for this observer. These controls do not establish aggregate
process-tree containment, filesystem WCET or protection against same-user races.

Actual GPT-6.1 reviewed the source and raw evidence without independently
executing the observer. The [inventory](evidence/continuity-host-observation-20261024/inventory.json)
binds its [forensic snapshot](evidence/continuity-host-observation-20261024/snapshot.tar.gz),
including the expected manifests, original negative result and successor.
Packaging reproduction is not product acceptance; archived absolute paths and
filesystem identities are historical data, not fresh execution authority.

Next: finish the continuity adapter's remaining static and active-schema
corrections, qualify current root/child import and native-profile observations,
external cleanup and final inventory, then separately execute original/adapted
formatter controls before any complete synthetic adapter campaign. Revalidate
host endpoints at dispatch. No native hook, actual compaction, authenticated
delivery, durable acknowledgment, installed update or release is qualified by
this observation. All original SIA assurance and marketplace gates remain open.
