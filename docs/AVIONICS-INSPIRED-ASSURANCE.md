# Avionics-inspired assurance: obligations and limits

Research date: 2026-10-20. This is an engineering plan for SIA, not an aircraft
certification basis, compliance declaration or substitute for controlled
standards and qualified certification expertise.

## What an actual airborne project would require

There is no universal checklist that can establish “avionics level” for an
arbitrary Linux application. First define the aircraft function, installation,
operational environment, failure conditions and allocated assurance level.
System development and safety assessment determine the obligations; choosing
Level A as a marketing aspiration does not perform that work.
[FAA AC 20-174](https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_20-174.pdf)
recognizes ARP4754A for aircraft/system development assurance. Its recognized
edition must not silently be replaced by a newer publication without checking
the applicable approval basis.

[FAA AC 20-115D](https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_20-115D.pdf)
recognizes DO-178C/ED-12C and applicable supplements. An actual applicant must
satisfy the objectives for the assigned software level and retain the
associated lifecycle data. Work includes planning, development, verification,
configuration management, quality assurance and certification liaison.
The PSAC explains the approach and applicable supplements; DO-333 formal
methods guidance supplements rather than replaces DO-178C. Tool qualification
under DO-330 depends on intended tool use and verification credit.
An installed compiler or a clean proof log is not qualification evidence.
The AC is an acceptable means, not the sole means and not itself a regulation.

[FAA Order 8110.49A](https://www.faa.gov/documentLibrary/media/Order/FAA_Order_8110.49A.pdf)
describes FAA software approval activities. An internal model reviewer is not
an authorized certification representative. SIA's separate GPT-6.1 reviews
are useful engineering evidence but do not establish the personnel,
organizational or objective-specific independence required by an actual
approval program.

Requirements-based tests, traceability and structural coverage must be tied
to the selected level and target. For a Level A conventional testing path,
MC/DC is part of the structural-coverage expectations; a function-coverage
percentage or a passing harness is not equivalent. Formal-method credit needs
an explicit justified allocation of objectives, proof assumptions and residual
testing. Resolve uncovered/deactivated/dead code and source/object differences;
do not write tests solely to inflate a coverage number.
The FAA's [assurance-case research report TC-17/67](https://www.faa.gov/sites/faa.gov/files/aircraft/air_cert/design_approvals/air_software/TC-17-67.pdf)
discusses these coverage distinctions; it is research, not an approval rule.
The complete normative DO-178C/DO-333 objective tables have not been audited
here. Obtaining the controlled applicable standards and preparing an
objective-by-objective compliance matrix remains OPEN.

[FAA AC 20-193](https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_20-193.pdf)
addresses multicore processors, including resource interference and assurance
activities for their use. SIA's general-purpose Linux host, VM scheduling,
page faults, shared caches, storage and background jobs are not a qualified
real-time execution platform. CPU affinity, cgroups or a timeout alone do not
establish worst-case timing or robust partitioning.

An airborne product also needs applicable hardware and installation evidence.
[AC 20-152A](https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_20-152A.pdf)
addresses airborne electronic hardware assurance;
[AC 21-16G](https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_21-16G.pdf)
recognizes environmental qualification using DO-160. Neither can be replaced
by application tests. Network security and continued operation have their own
applicability assessment: for example,
[AC 119-1A](https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_119-1A.pdf)
addresses operational authorization of an aircraft network security program.
These references identify additional workstreams, not a declaration that this
particular desktop system falls under each aviation requirement.

## Practices to adopt for SIA

These are our engineering proposals, not a statement that each is mandated
identically for every airborne installation.

| Work package | Concrete SIA evidence required | Current gap |
| --- | --- | --- |
| Safety and security requirements | Hazard analysis for false evidence, lost history, stale authorization, disclosure, replay, unavailable memory and unsafe recovery; operational envelope and explicit degraded modes | Full hazard-to-requirement allocation OPEN |
| Controlled lifecycle | Reviewed plans, baselined requirements/design/interfaces, bidirectional traceability, change-impact analysis, problem reports, independent acceptance and reproducible release | Partial artifacts exist; complete chain OPEN |
| Small authority boundary | SPARK state transitions plus exclusive protected actuator, authenticated observations and restricted signing/network access | Pure contracts proved; installed enforcement OPEN |
| Verification | Requirements-derived positive/negative tests, proof, structural coverage, fault injection, target integration, recovery and adversarial evidence | Local subsets passed; full installed campaign OPEN |
| Resources and scheduling | Fixed core storage, stack/runtime accounting, per-request and whole-cycle bounds, queue admission, interference analysis and measured target behavior with explicit limitations | CPython does not satisfy allocation-free execution; no target WCET or complete resource-bound evidence exists for this Linux configuration |
| Tool/runtime evidence | Tool use/credit analysis, versions/options/libraries, known defects, runtime provenance, object-code/target verification and reproducible independent build | Hash receipts exist; qualification and target assurance OPEN |
| Delivery and operation | Exact installed identity, migration/rollback controls, off-host restore, tampered-receipt and compromised-key exercises, maintained issue process | v1.8.4 released; marketplace acceptance and full recovery campaign OPEN |

The recommended architecture keeps Python/search/models outside consequential
authority, with explicit bounded messages into a restricted deterministic core.
Isolation must be enforced by the operating system and verified on the target.
Where such enforcement or predictability cannot be established, record the
limitation and constrain the claim; do not rename the entire desktop platform
“high integrity.”

## Guidance reconciliation

Ada high-integrity skill chapters on verification, dynamic features and
runtime/tool evidence inform this plan, alongside the local GNAT and SPARK
guidance already inventoried in `ASSURANCE-IMPLEMENTATION-GATES.md`.
Their older DO-178B-era descriptions are not current regulatory authority.
In particular, the historical categorical statement that compilers cannot
be qualified must not override modern intended-use/tool-credit analysis.
Likewise, selecting Ravenscar does not alone prove timing or runtime behavior.
Preserve runtime checks, finite proof resources and all-unit scope.

Power of Ten compliance would improve analyzability. It would not establish
correct requirements, successful integration, confidentiality, hardware
reliability, cognitive accuracy, whole-system proof or avionics certification.
