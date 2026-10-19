--------------------------- MODULE Publication ---------------------------
EXTENDS Naturals

CONSTANTS LastPhase, EarlyReady
VARIABLES phase, effect, intent, buffered, running, ready
vars == <<phase, effect, intent, buffered, running, ready>>

Init == /\ phase = 0 /\ effect = 0 /\ intent = 0 /\ buffered = 0
        /\ running = TRUE /\ ready = FALSE

Prepare == /\ running /\ intent = 0 /\ phase < LastPhase
           /\ intent' = phase + 1 /\ ready' = FALSE
           /\ UNCHANGED <<phase, effect, buffered, running>>

WriteEffect == /\ running /\ intent = phase + 1
               /\ buffered' = intent
               /\ UNCHANGED <<phase, effect, intent, running, ready>>

SyncEffect == /\ running /\ intent = phase + 1 /\ buffered = intent
              /\ effect' = buffered
              /\ UNCHANGED <<phase, intent, buffered, running, ready>>

CommitRecord == /\ running /\ intent = phase + 1 /\ effect = intent
                /\ phase' = intent
                /\ UNCHANGED <<effect, intent, buffered, running, ready>>

RetireIntent == /\ running /\ intent # 0 /\ phase = intent
                /\ effect = phase /\ intent' = 0
                /\ UNCHANGED <<phase, effect, buffered, running, ready>>

PublishReady == /\ running /\ intent = 0
                /\ IF EarlyReady THEN phase > 0 ELSE phase = LastPhase
                /\ ready' = TRUE
                /\ UNCHANGED <<phase, effect, intent, buffered, running>>

Crash == /\ running /\ running' = FALSE /\ ready' = FALSE
         /\ buffered' = effect
         /\ UNCHANGED <<phase, effect, intent>>

Restart == /\ ~running /\ running' = TRUE
           /\ UNCHANGED <<phase, effect, intent, buffered, ready>>

Next == Prepare \/ WriteEffect \/ SyncEffect \/ CommitRecord
        \/ RetireIntent \/ PublishReady \/ Crash \/ Restart

Spec == Init /\ [][Next]_vars

TypeOK == /\ phase \in 0..LastPhase /\ effect \in 0..LastPhase
          /\ intent \in 0..LastPhase /\ buffered \in 0..LastPhase
          /\ running \in BOOLEAN /\ ready \in BOOLEAN

DurablePrefix == /\ phase <= effect /\ effect <= phase + 1
                 /\ (intent = 0 => effect = phase)
                 /\ (intent # 0 => intent = phase \/ intent = phase + 1)

ReadySafe == ready =>
  (running /\ phase = LastPhase /\ effect = LastPhase /\ intent = 0)

\* Deliberately false invariant used only to witness reachable final readiness.
NotReadyYet == ~ready

=============================================================================
