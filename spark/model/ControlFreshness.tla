------------------------ MODULE ControlFreshness ------------------------
EXTENDS Naturals
CONSTANTS IgnoreAnchor, ReplayableAnchor, PostAckRollbackOnly
VARIABLES anchor, localAnchor, record, revoked, badEffect, effect, acknowledged
vars == <<anchor, localAnchor, record, revoked, badEffect, effect, acknowledged>>

\* Epoch 0 is an exact enabled permit; epoch 1 disables it permanently.
\* Both records have valid signatures. Only the independent anchor is assumed
\* nonrollbackable. This assumption needs a real protected implementation.
Init == /\ anchor = 0 /\ localAnchor = 0 /\ record = 0
        /\ revoked = FALSE /\ badEffect = FALSE
        /\ effect = FALSE /\ acknowledged = FALSE

\* Reserve disable in the anchor first. A crash before publishing the matching
\* record leaves mismatch/debt; it must not restore the old permission.
AdvanceAnchor ==
  /\ anchor = 0 /\ anchor' = 1 /\ localAnchor' = 1 /\ revoked' = TRUE
  /\ UNCHANGED <<record, badEffect, effect, acknowledged>>

PublishDisabled ==
  /\ anchor = 1 /\ record' = 1
  /\ UNCHANGED <<anchor, localAnchor, revoked, badEffect, effect, acknowledged>>

ReplayOldRecord ==
  /\ (~PostAckRollbackOnly \/ acknowledged)
  /\ record = 1 /\ record' = 0
  /\ UNCHANGED <<anchor, localAnchor, revoked, badEffect, effect, acknowledged>>

ReplayLocalAnchor ==
  /\ (~PostAckRollbackOnly \/ acknowledged)
  /\ localAnchor = 1 /\ localAnchor' = 0
  /\ UNCHANGED <<anchor, record, revoked, badEffect, effect, acknowledged>>

ObservedAnchor == IF ReplayableAnchor THEN localAnchor ELSE anchor

\* An atomic gate+effect is an assumption of shared serialization, not its proof.
UsePermit ==
  /\ (~PostAckRollbackOnly \/ acknowledged)
  /\ record = 0 /\ (IgnoreAnchor \/ record = ObservedAnchor)
  /\ effect' = TRUE /\ badEffect' = (badEffect \/ revoked)
  /\ UNCHANGED <<anchor, localAnchor, record, revoked, acknowledged>>

AckDisable ==
  /\ anchor = 1 /\ record = 1 /\ acknowledged' = TRUE
  /\ UNCHANGED <<anchor, localAnchor, record, revoked, badEffect, effect>>

Next == AdvanceAnchor \/ PublishDisabled \/ ReplayOldRecord \/
        ReplayLocalAnchor \/ UsePermit \/ AckDisable
Spec == Init /\ [][Next]_vars

TypeOK == /\ anchor \in 0..1 /\ localAnchor \in 0..1 /\ record \in 0..1
          /\ <<revoked, badEffect, effect, acknowledged>> \in [1..4 -> BOOLEAN]
NoRevokedEffect == ~badEffect
AckSafe == acknowledged => (revoked /\ anchor = 1)
\* Positive controls prevent success being inferred from an unreachable gate.
NoInitialEffect == ~effect
NoDisableAcknowledgment == ~acknowledged
=============================================================================
