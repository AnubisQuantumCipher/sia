--------------------- MODULE ConsolidationProgress ---------------------
EXTENDS Naturals, FiniteSets
CONSTANTS Days, Protected, Reinsert, ResetOnKeep
ASSUME /\ IsFiniteSet(Days) /\ Days \subseteq Nat
       /\ Protected \subseteq Days
VARIABLES live, pending, scanning, settled
vars == <<live, pending, scanning, settled>>

\* One unit is a successful bounded scan or one completed day claim.
\* Directory paging, failures, scheduling time, signing and publication are
\* outside this model. Protected includes every persistently retained day.
Init == /\ live = Days /\ pending = {}
        /\ scanning = TRUE /\ settled = FALSE

First == CHOOSE d \in pending : \A other \in pending : d <= other

Step ==
  /\ ~settled
  /\ IF scanning
     THEN /\ pending' = live /\ scanning' = FALSE
          /\ UNCHANGED <<live, settled>>
     ELSE IF pending = {}
          THEN /\ settled' = TRUE
               /\ UNCHANGED <<live, pending, scanning>>
          ELSE IF First \in Protected
               THEN /\ pending' = IF ResetOnKeep THEN {} ELSE pending \ {First}
                    /\ scanning' = ResetOnKeep
                    /\ UNCHANGED <<live, settled>>
               ELSE /\ live' = live \ {First}
                    /\ pending' = {} /\ scanning' = TRUE
                    /\ UNCHANGED settled

\* Adversarial recreation of a retired path prevents an unconditional
\* convergence claim. This is not asserted to be normal resident ingestion.
Recreate ==
  /\ Reinsert /\ ~settled /\ live # Days
  /\ live' = Days
  /\ UNCHANGED <<pending, scanning, settled>>

Next == Step \/ Recreate
Spec == Init /\ [][Next]_vars /\ WF_vars(Step)
TypeOK == /\ live \subseteq Days /\ pending \subseteq Days
          /\ scanning \in BOOLEAN /\ settled \in BOOLEAN
ProtectedRetained == Protected \subseteq live
SettledShape == settled => (~scanning /\ pending = {})
EventuallySettled == <>settled
=============================================================================
