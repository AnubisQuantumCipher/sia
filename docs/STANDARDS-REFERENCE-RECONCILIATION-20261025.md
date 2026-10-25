# Exact Ada assurance references recovered

Status: **reference identity verified; implementation compliance remains OPEN**.

The previously missing Ada 95 guide and mismatched modern-guide prerequisite
are resolved. Fresh downloads from the publishers match the exact SHA-256
values in the received standards addendum. The existing Power of Ten PDF was
also rehashed and still matches. The different pre-existing modern PDF was
preserved; it was not substituted for the required edition.

| Reference | Exact required identity | Source |
| --- | --- | --- |
| Ada 95 Quality and Style, SPC-94093-CMC, 01.00.10, October 1995 | `99fa731c2919b05979fcc8b403893a9dc73df2e0a6f4a6d5647e60402f54f542` | [Ada Information Clearinghouse](https://www.adaic.org/resources/add_content/docs/95style/95style.pdf) |
| Rogers and Frank, Guidelines for Safe and Secure Ada/SPARK, Release 2026-09, September 26, 2026 | `275000573798eac672dd60b4bb4f4997a9ff37c66eeee535503f0e858662b4e4` | [AdaCore](https://learn.adacore.com/pdf_books/courses/Guidelines_for_Safe_and_Secure_Ada_SPARK.pdf) |
| Holzmann, Power of Ten | `2217f41df961b9ed25cc072700b6332d6193799ed09d83be48bf791d05025f54` | [Original paper](https://spinroot.com/gerard/pdf/P10.pdf) |

[The receipt](STANDARDS-REFERENCE-RECONCILIATION-20261025.json) records download
URLs, byte identities, HTTP outcomes, local artifact paths, extracted-text
identities and the original addendum identity. Publisher URLs can change;
future readers must compare bytes with these pins. Download identity is not
an endorsement, proof result or completed source assessment.

## Contract-inheritance correction

The exact modern PDF's section 8.7.2, printed page 74, reverses the combination
of inherited class-wide preconditions and postconditions. Use the language
semantics in [Ada 2022 RM 6.1.1, paragraphs 33–35](https://www.adaic.org/resources/add_content/standards/22rm/html/RM-6-1-1.html):
enabled applicable class-wide preconditions accept if any holds; enabled
applicable postconditions must all hold. Specific preconditions are checked
separately. Evaluation order is not fixed. This is a source comparison, not a
new compiler test or proof. The downloaded guide remains unchanged.

## Integration with existing obligations

Continue the [Power of Ten assessment](POWER-OF-TEN-ASSESSMENT.md) and
[completion path](ASSURANCE-CRITICAL-PATH-20261024.md), using these exact
references. Required coverage remains DYN01–06, RCL01–03, CON01–03,
RPP01–14, EXU01–04, OOP01–07, SWE01–04, and applicable Ada 95 chapters 2–10.
Allocation, concurrency and dispatch alternatives require explicit policy
selection; they are not simultaneous implementation mandates.

Each applicability decision must retain its existing A/G/C/P/R obligation,
component and exact source composition, enforcement, unchanged budget,
command/tool/configuration, receipt, outcome and remaining blocker. Distinguish
literal compliance, language adaptation, justified non-applicability,
approved deviation and unresolved gap. No mapping row can substitute for its
required semantic oracle, proof or independent integrated execution.

The complete applicability mapping and implementation repairs remain open.
This increment closes reference availability and confirms the reported
semantic correction only. It changes no product code, resource ceiling,
acceptance obligation, installed path, release or marketplace state.
