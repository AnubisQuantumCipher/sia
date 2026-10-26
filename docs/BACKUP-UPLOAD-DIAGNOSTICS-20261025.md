# Backup upload failure diagnostics

**Non-final checkpoint. Not installed; recovery acceptance remains open.**

The retained October 24 upload failure did not identify whether capture,
repository invocation, response handling or cleanup failed. This change cannot
reconstruct that missing evidence. Future handled failures carry a closed phase
code in the existing status detail, alongside the existing operation/request ID.

The worker distinguishes:

- `not-attempted`: the repository-upload invocation boundary was not reached.
- `outcome-unknown`: invocation began, but no valid snapshot response was decoded.
  Internal preflight might have prevented dispatch; a remote write might also
  have happened. This code deliberately does not decide between those cases.
- `snapshot-reported`: a syntactically valid snapshot identifier was returned.
  This is not proof of durability, integrity, successful restoration or readiness.

Failures name capture, capsule validation, uploading-status publication,
repository invocation, response decoding, repository checking, off-path
verification, result construction or capsule cleanup. Restic nonzero exits retain
their bounded numeric status without interpreting its cause or copying output.
Existing fixed capsule refusal codes remain available. Arbitrary suffixes,
exception messages, argv, credentials, URLs, environment and stderr are excluded
from the new diagnostic clause.

The typed upload error retains its original exception as cause and any ordinary
independent cleanup exception in memory. Blocked classification and fatal
exception propagation remain. Status receives only closed diagnostic codes;
neither raw exception is persisted by this mechanism. No new success state,
permission, snapshot retry, network call or status-schema field is introduced.

## Source-bound evidence

The [evidence record](BACKUP-UPLOAD-DIAGNOSTICS-EVIDENCE-20261025.json) binds
the exact source, commands and [forensic archive](evidence/backup-upload-diagnostics-20261025.tar.gz).
The archive is not an automatic execution grant; historical absolute paths must
not be reused as custody evidence for another environment.

- Final composed roster: **172 tests pass, no skips**, including all 160 original
  backup/continuity tests without edits and 12 diagnostic tests.
- The original 60-second campaign, 2 GiB address-space and 512 MiB output-file
  ceilings were retained. Observed unittest time was 4.125 seconds; the enclosing
  process measurement was 4575668540 nanoseconds. These are not worst-case bounds.
- The negative candidate falsely labels invocation `not-attempted`; the unchanged
  oracle rejects both invocation-failure and malformed-response cases.
- New test/runner static checks pass the frozen rule profile. Full backup-module
  analysis still reports **15 inherited findings**. The baseline had 16; the
  previously unused subprocess import now supports timeout classification.
  This is not a full strict-analysis pass, and no finding is suppressed or waived.
- Independent source/raw review identified and then checked repairs for lost
  named reasons and hostile metaclass equality. The final review found no blocker
  to this non-final checkpoint. **No independent execution was performed.**

Earlier results remain: the first original-roster run failed because its runner
lacked `__main__.__file__` and a required installer fixture; both were repaired
without modifying original tests. An intermediate adversarial metaclass fixture
also failed the strict hash/equality rule; its explicit identity hash repaired
that finding. Earlier passes do not substitute for final-source execution.

## Limits and remaining acceptance

The Restic process, network and failure injection are mocked in the new tests.
Actual worker status persistence is exercised in isolated temporary roots. No
live backup, restore, credential operation or service restart was performed.
Process death, allocation failure or failure to publish status can still prevent
diagnostic delivery. Cleanup diagnostics do not prove complete cleanup; remote
outcomes still require independent reconciliation before retry. Existing request
retirement behavior is preserved, and this change does not implement a durable
uncertain-operation journal or automatic retry prevention.

Power-of-Ten adaptations here are finite phase vocabulary, short added routines,
checked diagnostic inputs/results, narrow state and explicit failure retention.
Python allocation, runtime dispatch and OS behavior are not formally proved.
The source identity is bound by campaign evidence, not authenticated by a runtime
diagnostic string. No additional Ada/SPARK authority path is introduced.

R05 useful reuse plus fresh admission, SDK full-workload limits, strict native
analysis, full composed SPARK proof, protected publication/query, installed
continuity, held-out retrieval, off-host recovery and release/marketplace gates
remain unchanged and open. Passing this roster is not whole-system assurance or
avionics certification.
