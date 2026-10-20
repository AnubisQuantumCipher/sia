# Implementation gates and guidance inventory

Operator mission clarification received 2026-10-20 through the authorized
session handoff. This extends `ASSURANCE-GOAL.md`; it does not replace its
release, marketplace, held-out evaluation or off-host recovery obligations.
One implementation owner retains the assurance worktree. Independent GPT-6.1
review remains a separate acceptance activity. Avionics-style rigor is an
engineering aspiration, not certification or an error-free interpretation claim.

## Ada/SPARK resources

Installed skill entry points were inspected to select applicable guidance.
Topic chapters must be read when applying their specialized features; this
inventory is not a claim that every book or chapter has been read.

| Skill | Intended application |
| --- | --- |
| ada | Route language, integrity and machine-specific questions |
| ada-omarchy | Installed GNAT environment, all-unit proof, exact summary/assumption checks |
| spark-users-guide | Explicit contracts, flow dependencies, loop/subprogram termination, refinement and external assumptions |
| ada-high-integrity | Verifiable subset, requirements/structural testing, runtime and toolchain obligations |
| advanced-ada | Distinct domain types, valid-state records, visibility and representation boundaries |
| gnat-toolchain | Reproducible projects, strict diagnostics, supported compiler/prover switches |
| ada-programming | Package/type/lifetime boundaries and explicit exceptional behavior |
| ada-2005-amendment | Reference when using applicable language features; no requirement to introduce dispatch, allocation or tasking |

These are guidance resources, not acceptance evidence. User requirements
override conflicting generic examples: retain runtime checks at untrusted
boundaries, do not suppress proof failures or warnings to obtain acceptance,
and do not use unrestricted `-j0` in place of the existing resource caps.
Historical tool counts and reference-project proof claims must not be imported
as proof of SIA. Check development-guide syntax against installed tools.

## Concrete sequence

| Gate | Implementation work | Required completion evidence |
| --- | --- | --- |
| G1: authoritative lifecycle | Specify captured-source identity, sequence/capture gaps, immutable origin, publication, exact retrieval authority, explicit retirement and durable tombstones; separate retraction of derived records | Requirement/hazard/contract matrix; reviewed complete transitions and malformed cases; no implicit deletion or provenance escalation |
| G2: SPARK lifecycle core | Add bounded lifecycle decisions to the existing pure units; keep external authenticity/durability producers explicit; implement typed refusals and safe degraded capabilities | Strict build, complete all-unit flow/functional/termination proof, no unresolved intended checks/justifications/assumptions hidden in code, deterministic boundary and adversarial tests, independent review |
| G3: protected producers and actuator | Complete pinned issuer/store/epochs, canonical records, bounded IPC, signing custody, freshness provider and actual exclusive protected write path | Commissioning manifest; necessary privileges approved; direct bypass and stale-witness controls; actual revocation/rollback/expiry/isolation tests; no unauthenticated caller Boolean used as authority |
| G4: selected resident path | Establish installed executable/config/retained-state identity and observe actual dispatch; run complete source-to-publication failures on that path; qualify an explicit migration if required | Actual front-door execution and fresh exec restart, torn/reordered writes, exhaustion, corruption/replay and acknowledgment cuts, retained receipts; reversible migration plan where possible; no silent config switch |
| G5: derived memory and semantic evaluation | Version/evidence-link/retract/recompute summaries, embeddings and dreams while retaining original records; freeze independent held-out ground truth and abstention policy | Retraction/rebuild/source-retention tests; complete false-pass/false-fail and abstention measurements, baseline comparison, no model verdict relabeled as source truth |
| G6: recovery and release | Complete off-host damaged-data/compromised-credential/tampered-receipt exercises and independently executable verification; qualify selected installation and marketplace source | Exact source/toolchain/TCB/assumption manifest, independent reproduction and review, installed readback and exact marketplace acceptance; only scoped earned claims published |

G1/G2 can progress while G3's provider qualification remains unresolved.
Passing them cannot authorize migration or hide the missing enforcement.
No new spending, security privilege, concurrency cap or network authority is
implicitly granted by this sequence. The existing release remains separate.

## Hazards and traceability requirements

Every row must ultimately point to immutable source, contract/proof obligation,
test invocation/output, independent review and installed-path evidence. The
locations below are starting points, not completed coverage.

| Hazard | Required property | Current starting point / gap |
| --- | --- | --- |
| Model prose becomes history | Origin never escalates through signing, dream or summary; unknown remains explicit | `SIA_Policy.Admit_Source_Evidence`; authenticated origin producer remains open |
| Captured data is silently lost or reordered | Preserve identities, sequence, provenance and explicit capture gaps; qualify coverage to successfully captured events | Source completeness type exists; complete lifecycle/gap/ordering contracts remain open |
| Retrieval or retirement bypasses authority | Exact current read/retire authority, authenticated generations, preserved audit/replay evidence | Protected Query proposal exists; full authoritative retirement policy remains open |
| Derived retraction deletes source | Retraction/version replacement affects derived identity only; authoritative source remains available under its own retention policy | End-to-end derived lifecycle acceptance remains open |
| Green tests exercise inactive code | Acceptance binds actual selected runtime and retained routing state | Config false was observed; branch-execution evidence remains open |
| Signed stale control resurrects permission | Independent freshness and serialized authorization/effect | `ControlFreshness.tla` conditional model; actual provider/enforcement remains open |
| Semantic confidence masks a false result | Independent ground truth, false-pass/false-fail accounting and explicit abstention | Held-out campaign remains open; signed/model judgment is not truth |

The observed `mind.controller_source: false` field is only a configuration
observation. `_reserved_pulse` also considers retained controller-source state.
Do not infer actual legacy or controller execution from that flag alone, or
toggle it merely to exercise a preferred test path. Inspect installed code,
validated retained state and actual dispatch evidence before making that claim.

A safe degraded mode must enumerate allowed operations; "read only" is not
automatically safe when identity, confidentiality or publication is uncertain.
Failures and unknown outcomes remain visible and must not be renamed success.
