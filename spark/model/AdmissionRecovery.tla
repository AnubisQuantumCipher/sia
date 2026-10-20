------------------------ MODULE AdmissionRecovery ------------------------
EXTENDS Naturals
CONSTANTS SkipIntentSync, SkipRecoveryGuard
VARIABLES intent, running, writeValid, recoveryEnabled, sampled,
          syncedHere, payload, effectHadSync, effectHadPermit, effectAfterExpiry, crashKind, effectCrashKind
vars == <<intent, running, writeValid, recoveryEnabled, sampled,
          syncedHere, payload, effectHadSync, effectHadPermit, effectAfterExpiry, crashKind, effectCrashKind>>

\* One exact authenticated operation. 0 absent, 1 staging, 2 final visible,
\* 3 synchronized. Authentication/currentness are external assumptions.
Init == /\ intent = 0 /\ running = TRUE /\ writeValid = TRUE
        /\ recoveryEnabled = TRUE /\ sampled = FALSE /\ syncedHere = FALSE
        /\ payload = FALSE /\ effectHadSync = FALSE /\ effectHadPermit = FALSE
        /\ effectAfterExpiry = FALSE /\ crashKind = 0 /\ effectCrashKind = 0

\* Candidate semantics: validity at this protected sample, not at later fsync.
SampleAndStage ==
  /\ running /\ intent = 0 /\ ~payload /\ writeValid /\ recoveryEnabled
  /\ sampled' = TRUE /\ intent' = 1 /\ crashKind' = 0
  /\ UNCHANGED <<running, writeValid, recoveryEnabled, syncedHere,
                payload, effectHadSync, effectHadPermit, effectAfterExpiry, effectCrashKind>>

PublishIntent ==
  /\ running /\ intent = 1 /\ sampled /\ recoveryEnabled
  /\ intent' = 2
  /\ UNCHANGED <<running, writeValid, recoveryEnabled, sampled, syncedHere,
                payload, effectHadSync, effectHadPermit, effectAfterExpiry, crashKind, effectCrashKind>>

SyncIntent ==
  /\ running /\ intent \in {2, 3} /\ sampled /\ recoveryEnabled
  /\ intent' = 3 /\ syncedHere' = TRUE
  /\ UNCHANGED <<running, writeValid, recoveryEnabled, sampled,
                payload, effectHadSync, effectHadPermit, effectAfterExpiry, crashKind, effectCrashKind>>

WritePayload ==
  /\ running /\ intent \in {2, 3} /\ sampled /\ ~payload
  /\ (SkipRecoveryGuard \/ recoveryEnabled)
  /\ (SkipIntentSync \/ syncedHere)
  /\ payload' = TRUE /\ effectHadSync' = syncedHere
  /\ effectHadPermit' = recoveryEnabled /\ effectAfterExpiry' = ~writeValid
  /\ effectCrashKind' = crashKind
  /\ UNCHANGED <<intent, running, writeValid, recoveryEnabled, sampled, syncedHere, crashKind>>

Expire ==
  /\ writeValid /\ writeValid' = FALSE
  /\ UNCHANGED <<intent, running, recoveryEnabled, sampled, syncedHere,
                payload, effectHadSync, effectHadPermit, effectAfterExpiry, crashKind, effectCrashKind>>

\* Overapproximation: disable may interleave with every model action.
\* No re-enable or replacement authority exists in this bounded configuration.
DisableRecovery ==
  /\ recoveryEnabled /\ recoveryEnabled' = FALSE
  /\ UNCHANGED <<intent, running, writeValid, sampled, syncedHere,
                payload, effectHadSync, effectHadPermit, effectAfterExpiry, crashKind, effectCrashKind>>

\* Unsynchronized final rename may survive or disappear; staging is never
\* a recovery admission. Synchronized intent survives this crash abstraction.
Crash ==
  /\ running /\ running' = FALSE /\ syncedHere' = FALSE
  /\ intent' \in (IF intent = 3 THEN {3}
                 ELSE IF intent = 2 THEN {0, 2} ELSE {0})
  /\ sampled' = (sampled /\ intent' # 0)
  /\ crashKind' = (IF intent' = 0 THEN 0
                    ELSE IF ~payload /\ intent = 2 THEN 1
                    ELSE IF ~payload /\ intent = 3 THEN 2 ELSE crashKind)
  /\ UNCHANGED <<writeValid, recoveryEnabled, payload,
                effectHadSync, effectHadPermit, effectAfterExpiry, effectCrashKind>>

Restart ==
  /\ ~running /\ running' = TRUE
  /\ UNCHANGED <<intent, writeValid, recoveryEnabled, sampled, syncedHere,
                payload, effectHadSync, effectHadPermit, effectAfterExpiry, crashKind, effectCrashKind>>

Next == SampleAndStage \/ PublishIntent \/ SyncIntent \/ WritePayload \/
        Expire \/ DisableRecovery \/ Crash \/ Restart
Spec == Init /\ [][Next]_vars

TypeOK == /\ intent \in 0..3
          /\ <<running, writeValid, recoveryEnabled, sampled, syncedHere,
               payload, effectHadSync, effectHadPermit, effectAfterExpiry>> \in
             [1..9 -> BOOLEAN]
          /\ crashKind \in 0..2 /\ effectCrashKind \in 0..2
PayloadSafe == payload => (effectHadSync /\ effectHadPermit /\ sampled)
SyncHasIntent == syncedHere => (running /\ intent = 3 /\ sampled)
\* Deliberately false reachability invariant: a valid earlier sample can
\* complete after expiry, as witnessed at the effect, not by expiry after an earlier effect.
NoExpiredCompletion == ~effectAfterExpiry
NoUnsyncedExpiredRecovery == ~(payload /\ effectAfterExpiry /\ effectCrashKind = 1)
NoDurableRecovery == ~(payload /\ effectCrashKind = 2)
=============================================================================
