----------------------- MODULE EventPackMigration -----------------------
EXTENDS Naturals, FiniteSets
CONSTANT Fault
VARIABLE s

\* One admitted exact plan, serialized protected writer; identities/bytes and
\* authority are premises, not client-supplied Boolean evidence. This finite
\* configuration has two represented legacy records, a fallback and old pack.
Represented == {"a", "b"}
Fallback == {"f"}
Prior == {"p"}
Legacy == Represented \cup Fallback
Original == Legacy \cup Prior
NewRecords == Represented \cup (IF Fault = "prior" THEN {} ELSE Prior)
Coverage(version) == CASE version = 0 -> Prior
                      [] version = 1 -> NewRecords
                      [] OTHER -> {}

\* Target: 0 old exact, 1 new exact, 2 invalid. Intent: 0 absent,
\* 1 final-visible unsynced, 2 durable. Temp: 0 absent, 1 partial, 2 exact.
Init == s = [running |-> TRUE, intent |-> 0, temp |-> 0,
             tempSynced |-> FALSE, target |-> 0, targetData |-> TRUE,
             durableTarget |-> 0, legacy |-> Legacy, durableLegacy |-> Legacy,
             checked |-> FALSE, badIntentRetirement |-> FALSE,
             complete |-> FALSE, phase |-> 0, ready |-> FALSE,
             partialCrashes |-> 0, completionCrashes |-> 0,
             survivedRename |-> FALSE, completionRename |-> FALSE]

Prepare == /\ s.running /\ s.intent = 0 /\ s.legacy = Legacy
           /\ s' = [s EXCEPT !.intent = 1]
SyncIntent == /\ s.running /\ s.intent = 1
              /\ s' = [s EXCEPT !.intent = 2]
BeginWrite == /\ s.running /\ s.temp = 0 /\ s.target # 1
              /\ (s.intent = 2 \/ (Fault = "intent" /\ s.intent = 1))
              /\ s' = [s EXCEPT !.temp = 1, !.tempSynced = FALSE]
FinishWrite == /\ s.running /\ s.temp = 1
               /\ s' = [s EXCEPT !.temp = 2]
SyncFile == /\ s.running /\ s.temp = 2
            /\ s' = [s EXCEPT !.tempSynced = TRUE]
Rename == /\ s.running /\ s.temp = 2
          /\ (s.tempSynced \/ Fault = "data")
          /\ s' = [s EXCEPT !.target = 1, !.targetData = s.tempSynced,
                    !.temp = 0, !.tempSynced = FALSE, !.checked = FALSE]
SyncTargetParent ==
  /\ s.running /\ s.target = 1
  /\ s' = [s EXCEPT !.durableTarget = IF s.targetData THEN 1 ELSE 2]
Verify ==
  /\ s.running /\ s.target = 1
  /\ (s.intent = 2 \/ Fault = "intent")
  /\ (s.targetData \/ Fault = "data")
  /\ (s.durableTarget = 1 \/ Fault \in {"data", "parent"})
  /\ s' = [s EXCEPT !.checked = TRUE]
Retire(record) ==
  /\ s.running /\ s.checked /\ record \in s.legacy
  /\ record \in (IF Fault = "coverage" THEN Legacy ELSE Represented)
  /\ s' = [s EXCEPT !.legacy = @ \ {record},
                    !.badIntentRetirement = @ \/ s.intent # 2]
SyncLegacyParent == /\ s.running /\ s.checked
                    /\ s' = [s EXCEPT !.durableLegacy = s.legacy]
Complete ==
  /\ s.running /\ s.checked /\ ~s.complete
  /\ (Fault = "complete" \/
       (s.legacy = Fallback /\ s.durableLegacy = Fallback /\
        s.durableTarget = 1 /\ s.intent = 2))
  /\ s' = [s EXCEPT !.complete = TRUE,
                    !.completionCrashes = s.partialCrashes,
                    !.completionRename = s.survivedRename]

\* Abstract original publication barrier, not a second implementation of its
\* filesystem effects. Every phase is assumed durable and source-bound.
PublishPhase == /\ s.running /\ s.checked /\ s.complete /\ s.phase < 10
                /\ s' = [s EXCEPT !.phase = @ + 1]
Ready == /\ s.running /\ s.checked /\ s.complete
         /\ (s.phase = 10 \/ Fault = "ready")
         /\ s' = [s EXCEPT !.ready = TRUE]

CrashTargets ==
  IF s.durableTarget # 0 THEN {s.durableTarget}
  ELSE IF s.target = 1 THEN (IF s.targetData THEN {0, 1} ELSE {0, 2})
  ELSE {0}
Partial == s.legacy \cap Represented # Represented /\
           s.legacy \cap Represented # {}
Crash ==
  /\ s.running
  /\ \E target \in CrashTargets,
        kept \in {k \in SUBSET s.durableLegacy : s.legacy \subseteq k},
        intent \in (IF s.intent = 1 THEN {0, 1} ELSE {s.intent}):
       s' = [s EXCEPT !.running = FALSE, !.intent = intent,
             !.temp = 0, !.tempSynced = FALSE, !.target = target,
             !.targetData = (target # 2), !.durableTarget = target,
             !.legacy = kept, !.durableLegacy = kept,
             !.checked = FALSE, !.ready = FALSE,
             !.partialCrashes = IF Partial /\ s.checked /\ @ < 2
                               THEN @ + 1 ELSE @,
             !.survivedRename = @ \/
                 (s.target = 1 /\ s.durableTarget = 0 /\ target = 1)]
Restart == /\ ~s.running /\ s' = [s EXCEPT !.running = TRUE]

Next == Prepare \/ SyncIntent \/ BeginWrite \/ FinishWrite \/ SyncFile \/
        Rename \/ SyncTargetParent \/ Verify \/ (\E r \in Legacy: Retire(r)) \/
        SyncLegacyParent \/ Complete \/ PublishPhase \/ Ready \/ Crash \/ Restart
Spec == Init /\ [][Next]_s

TypeOK == s \in [running: BOOLEAN, intent: 0..2, temp: 0..2,
                 tempSynced: BOOLEAN, target: 0..2, targetData: BOOLEAN,
                 durableTarget: 0..2, legacy: SUBSET Legacy,
                 durableLegacy: SUBSET Legacy, checked: BOOLEAN,
                 badIntentRetirement: BOOLEAN, complete: BOOLEAN,
                 phase: 0..10, ready: BOOLEAN, partialCrashes: 0..2,
                 completionCrashes: 0..2, survivedRename: BOOLEAN,
                 completionRename: BOOLEAN]
Retained == Original \subseteq s.legacy \cup Coverage(s.durableTarget)
RetirementSafe == Fallback \subseteq s.legacy /\
                  Legacy \ s.legacy \subseteq Coverage(s.durableTarget)
IntentSafe == ~s.badIntentRetirement
CompleteSafe == s.complete =>
  (s.durableLegacy = Fallback /\ s.durableTarget = 1 /\ s.intent = 2)
ReadySafe == s.ready =>
  (s.running /\ s.checked /\ s.complete /\ s.phase = 10)

\* False invariants witness real paths; monitors are captured at completion
\* so later crashes cannot manufacture an earlier recovery success.
NoCompletion == ~s.complete
NoReady == ~s.ready
NoRepeatedPartialRecovery == s.completionCrashes # 2
NoRenameRecovery == ~s.completionRename
=============================================================================
