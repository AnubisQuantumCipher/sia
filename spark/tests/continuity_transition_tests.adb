with SIA_Policy; use SIA_Policy;
with SIA_Continuity; use SIA_Continuity;
with SIA_Continuity_Transitions;

procedure Continuity_Transition_Tests with SPARK_Mode is
   package T renames SIA_Continuity_Transitions;
   use type T.Change_Kind;
   use type T.Transition_Result;
   None : constant T.Observations := [others => T.Empty_Observation];
   Work : constant Operation :=
     (Identity => [others => 1], Action => [others => 2],
      Source_Record_Id | Result_Record_Id => Zero,
      Stage => Planned, Has_Result => False);
   Initial : constant Checkpoint :=
     (Scope => (Task_Id => [others => 1], Session_Id => [others => 2],
                Repository => [others => 3], Revision | Dirty => Zero),
      Identity => [others => 10], Previous | Capture => Zero,
      Epoch => 1, Through => 0, Retention_Epoch => 0,
      Coverage => [others => SIA_Continuity.Not_Observed],
      Count => 0, Claims => [others => Empty_Claim],
      Operations_Count => 1,
      Operations => [1 => Work, others => Empty_Operation]);
   Sent : constant Checkpoint :=
     (Initial with delta Identity => [others => 11],
      Previous => Initial.Identity, Epoch => 2,
      Operations => [1 => (Work with delta Stage => Dispatched),
                     others => Empty_Operation]);
   Doubt : constant Checkpoint :=
     (Sent with delta Identity => [others => 12],
      Previous => Sent.Identity, Epoch => 3,
      Operations => [1 => (Work with delta Stage => Uncertain),
                     others => Empty_Operation]);
   Done : constant Checkpoint :=
     (Doubt with delta Identity => [others => 13],
      Previous => Doubt.Identity, Epoch => 4,
      Operations => [1 => (Work with delta Stage => Observed_Complete,
                          Has_Result => True),
                     others => Empty_Operation]);
   Acked : constant Checkpoint :=
     (Done with delta Identity => [others => 14],
      Previous => Done.Identity, Epoch => 5,
      Operations => [1 => (Work with delta Stage => Acknowledged,
                          Has_Result => True),
                     others => Empty_Operation]);

   --  Synthetic resolved fields only. This fixture does not authenticate E/R.
   function Event
     (Before, After : Checkpoint; Kind : T.Event_Kind;
      I : Operation_Index := 1; Record_Id : Digest := Zero)
      return T.Observation
   with Global => null,
     Pre => Kind = T.Required_Change
       (Before.Operations (I), After.Operations (I)),
     Post => T.Bound_Event (Event'Result, Before, After, I) and then
       Event'Result.Event_Record_Id = Record_Id
   is
   begin
      return
        (State => Retained, Before_Id => Before.Identity,
         After_Id => After.Identity, Before_Epoch => Before.Epoch,
         After_Epoch => After.Epoch, Event_Record_Id => Record_Id,
         Kind => Kind, Before_Operation => Before.Operations (I),
         After_Operation => After.Operations (I),
         Has_Outcome => Kind in T.Observed_Outcome | T.Reconciled_Outcome,
         Outcome_Record_Id =>
           (if Kind in T.Observed_Outcome | T.Reconciled_Outcome
            then After.Operations (I).Result_Record_Id else Zero));
   end Event;

   function Expected
     (Before, After : Checkpoint; Items : T.Observations;
      Wanted : T.Transition_Result) return Boolean is
     (case Wanted is
         when T.Invalid_Before => not Valid (Before),
         when T.Invalid_After => Valid (Before) and then not Valid (After),
         when T.Task_Mismatch =>
           Valid (Before) and then Valid (After) and then
           not T.Same_Task (Before, After),
         when T.Predecessor_Mismatch =>
           Valid (Before) and then Valid (After) and then
           T.Same_Task (Before, After) and then not T.Next_Link (Before, After),
         when T.Watermark_Regression =>
           Valid (Before) and then Valid (After) and then
           T.Same_Task (Before, After) and then T.Next_Link (Before, After)
           and then not T.Monotone (Before, After),
         when T.Operation_Lost | T.Unsupported_Change |
              T.Need_Transition_Evidence | T.Transition_Proposed =>
           Valid (Before) and then Valid (After) and then
           T.Same_Task (Before, After) and then T.Next_Link (Before, After)
           and then T.Monotone (Before, After) and then
           (case Wanted is
               when T.Operation_Lost => not T.Conserved (Before, After),
               when T.Unsupported_Change =>
                 T.Conserved (Before, After) and then
                 not T.Legal_Changes (Before, After),
               when others =>
                 T.Conserved (Before, After) and then
                 T.Legal_Changes (Before, After) and then
                 (T.Events_Joined (Before, After, Items) =
                    (Wanted = T.Transition_Proposed))))
   with Global => null;

   procedure Check
     (Before, After : Checkpoint; Items : T.Observations;
      Wanted : T.Transition_Result)
   with Global => null, Always_Terminates,
     Pre => Expected (Before, After, Items, Wanted)
   is
   begin
      pragma Assert (T.Classify (Before, After, Items) = Wanted);
   end Check;

   procedure Check_Unchanged (Before, After : Checkpoint)
   with Global => null, Always_Terminates,
     Pre => Valid (Before) and then Valid (After) and then
       T.Same_Task (Before, After) and then T.Next_Link (Before, After) and then
       T.Monotone (Before, After) and then
       Before.Operations_Count = After.Operations_Count and then
       Before.Operations = After.Operations
   is
   begin
      Check (Before, After, None, T.Transition_Proposed);
   end Check_Unchanged;

   procedure Fixture_Properties
   with Global => null, Always_Terminates,
     Post => Valid (Initial) and then Valid (Sent) and then
       Valid (Doubt) and then Valid (Done) and then Valid (Acked)
   is
   begin
      pragma Assert (Valid (Initial));
      pragma Assert (Valid (Sent));
      pragma Assert (Valid (Doubt));
      pragma Assert (Valid (Done));
      pragma Assert (Valid (Acked));
   end Fixture_Properties;

   procedure Check_Chain
   with Global => null, Always_Terminates,
     Pre => Valid (Initial) and then Valid (Sent) and then
       Valid (Doubt) and then Valid (Done) and then Valid (Acked)
   is
      Immediate : constant Checkpoint :=
        (Done with delta Previous => Sent.Identity, Epoch => 3);
   begin
      Check (Initial, Sent, [1 => Event (Initial, Sent, T.Dispatch_Attempt),
                            others => T.Empty_Observation],
             T.Transition_Proposed);
      Check (Sent, Doubt, [1 => Event (Sent, Doubt, T.Interruption),
                          others => T.Empty_Observation],
             T.Transition_Proposed);
      Check (Doubt, Done, [1 => Event (Doubt, Done, T.Reconciled_Outcome),
                          others => T.Empty_Observation],
             T.Transition_Proposed);
      Check (Sent, Immediate,
             [1 => Event (Sent, Immediate, T.Observed_Outcome),
              others => T.Empty_Observation], T.Transition_Proposed);
      Check (Done, Acked, [1 => Event (Done, Acked, T.Acknowledgment),
                          others => T.Empty_Observation],
             T.Transition_Proposed);
      Check (Doubt, Done, None, T.Need_Transition_Evidence);
   end Check_Chain;

   procedure Check_Headers
   with Global => null, Always_Terminates,
     Pre => Valid (Initial) and then Valid (Sent)
   is
      Items : constant T.Observations :=
        [1 => Event (Initial, Sent, T.Dispatch_Attempt),
         others => T.Empty_Observation];
   begin
      Check ((Initial with delta Identity => Zero), Sent, Items,
             T.Invalid_Before);
      Check (Initial, (Sent with delta Identity => Zero), Items, T.Invalid_After);
      Check (Initial, (Sent with delta Scope =>
               (Sent.Scope with delta Task_Id => [others => 9])),
             Items, T.Task_Mismatch);
      Check (Initial, (Sent with delta Scope =>
               (Sent.Scope with delta Session_Id => [others => 9])),
             Items, T.Task_Mismatch);
      Check (Initial, (Sent with delta Scope =>
               (Sent.Scope with delta Repository => [others => 9])),
             Items, T.Task_Mismatch);
      Check (Initial, (Sent with delta Previous => [others => 9]), Items,
             T.Predecessor_Mismatch);
      Check (Initial, (Sent with delta Epoch => 3), Items,
             T.Predecessor_Mismatch);
      Check ((Initial with delta Through => 1), Sent, Items,
             T.Watermark_Regression);
      Check ((Initial with delta Retention_Epoch => 1), Sent, Items,
             T.Watermark_Regression);
   end Check_Headers;

   procedure Check_Conservation
   with Global => null, Always_Terminates,
     Pre => Valid (Doubt) and then Valid (Done)
   is
   begin
      Check (Doubt, (Done with delta Operations_Count => 0,
                     Operations => [others => Empty_Operation]),
             None, T.Operation_Lost);
      Check (Doubt, (Done with delta Operations =>
               [1 => (Done.Operations (1) with delta Identity => [others => 3]),
                others => Empty_Operation]), None, T.Operation_Lost);
      Check (Doubt, (Done with delta Operations =>
               [1 => (Done.Operations (1) with delta Action => [others => 3]),
                others => Empty_Operation]), None, T.Operation_Lost);
      Check (Doubt, (Done with delta Operations =>
               [1 => (Done.Operations (1) with delta
                      Source_Record_Id => [others => 3]),
                others => Empty_Operation]), None, T.Operation_Lost);
      Check (Doubt, (Done with delta Operations =>
               [1 => Work, others => Empty_Operation]),
             None, T.Unsupported_Change);
      Check (Doubt, (Done with delta Operations =>
               [1 => Doubt.Operations (1), others => Empty_Operation]),
             None, T.Transition_Proposed);
   end Check_Conservation;

   procedure Check_Event_Bindings
   with Global => null, Always_Terminates,
     Pre => Valid (Doubt) and then Valid (Done)
   is
      Good : constant T.Observation := Event (Doubt, Done, T.Reconciled_Outcome);
      procedure Refuse (Item : T.Observation)
      with Global => null, Always_Terminates,
        Pre => not T.Bound_Event (Item, Doubt, Done, 1)
      is
      begin
         Check (Doubt, Done, [1 => Item, others => T.Empty_Observation],
                T.Need_Transition_Evidence);
      end Refuse;
   begin
      Refuse ((Good with delta State => Unknown));
      Refuse ((Good with delta State => Missing));
      Refuse ((Good with delta State => Retracted));
      Refuse ((Good with delta Before_Id => Zero));
      Refuse ((Good with delta After_Id => Zero));
      Refuse ((Good with delta Before_Epoch => 0));
      Refuse ((Good with delta After_Epoch => 0));
      Refuse ((Good with delta Before_Operation => Empty_Operation));
      Refuse ((Good with delta After_Operation => Empty_Operation));
      Refuse ((Good with delta Kind => T.Observed_Outcome));
      Refuse ((Good with delta Has_Outcome => False));
      Refuse ((Good with delta Outcome_Record_Id => [others => 1]));
      Check (Doubt, Done, [1 | 2 => Good, others => T.Empty_Observation],
             T.Need_Transition_Evidence);
   end Check_Event_Bindings;

   procedure Check_Event_Operation_Fields
   with Global => null, Always_Terminates,
     Pre => Valid (Doubt) and then Valid (Done)
   is
      Good : constant T.Observation := Event (Doubt, Done, T.Reconciled_Outcome);
      Before : constant Operation := Good.Before_Operation;
      After : constant Operation := Good.After_Operation;
      procedure Refuse (Item : T.Observation)
      with Global => null, Always_Terminates,
        Pre => not T.Bound_Event (Item, Doubt, Done, 1)
      is
      begin
         Check (Doubt, Done, [1 => Item, others => T.Empty_Observation],
                T.Need_Transition_Evidence);
      end Refuse;
   begin
      Refuse ((Good with delta Before_Operation =>
                 (Before with delta Identity => Zero)));
      Refuse ((Good with delta Before_Operation =>
                 (Before with delta Action => Zero)));
      Refuse ((Good with delta Before_Operation =>
                 (Before with delta Source_Record_Id => [others => 1])));
      Refuse ((Good with delta Before_Operation =>
                 (Before with delta Result_Record_Id => [others => 1])));
      Refuse ((Good with delta Before_Operation =>
                 (Before with delta Stage => Dispatched)));
      Refuse ((Good with delta Before_Operation =>
                 (Before with delta Has_Result => True)));
      Refuse ((Good with delta After_Operation =>
                 (After with delta Identity => Zero)));
      Refuse ((Good with delta After_Operation =>
                 (After with delta Action => Zero)));
      Refuse ((Good with delta After_Operation =>
                 (After with delta Source_Record_Id => [others => 1])));
      Refuse ((Good with delta After_Operation =>
                 (After with delta Result_Record_Id => [others => 1])));
      Refuse ((Good with delta After_Operation =>
                 (After with delta Stage => Acknowledged)));
      Refuse ((Good with delta After_Operation =>
                 (After with delta Has_Result => False)));
   end Check_Event_Operation_Fields;

   procedure Check_Event_Uniqueness
   with Global => null, Always_Terminates,
     Pre => Valid (Initial) and then Valid (Sent)
   is
      Before : constant Checkpoint :=
        (Initial with delta Operations_Count => 2,
         Operations =>
           [1 => Work, 2 => (Work with delta Identity => [others => 2]),
            others => Empty_Operation]);
      After : constant Checkpoint :=
        (Sent with delta Operations_Count => 2,
         Operations =>
           [1 => Sent.Operations (1),
            2 => (Sent.Operations (1) with delta Identity => [others => 2]),
            others => Empty_Operation]);
      First : constant T.Observation :=
        Event (Before, After, T.Dispatch_Attempt, 1);
      Second : constant T.Observation :=
        Event (Before, After, T.Dispatch_Attempt, 2);
   begin
      Check (Before, After, [1 => First, 2 => Second,
                            others => T.Empty_Observation],
             T.Need_Transition_Evidence);
      Check (Before, After,
             [1 => First, 2 => (Second with delta Event_Record_Id => [others => 1]),
              others => T.Empty_Observation], T.Transition_Proposed);
      Check (Initial, Sent,
             [1 => (Event (Initial, Sent, T.Dispatch_Attempt) with delta
                    Has_Outcome => True),
              others => T.Empty_Observation], T.Need_Transition_Evidence);
      Check (Initial, Sent,
             [1 => (Event (Initial, Sent, T.Dispatch_Attempt) with delta
                    Outcome_Record_Id => [others => 1]),
              others => T.Empty_Observation], T.Need_Transition_Evidence);
   end Check_Event_Uniqueness;

   procedure Check_Provisional
   with Global => null, Always_Terminates,
     Pre => Valid (Sent) and then Valid (Doubt) and then Valid (Done)
   is
      Old : constant Checkpoint :=
        (Sent with delta Operations =>
           [1 => (Sent.Operations (1) with delta Has_Result => True,
                  Result_Record_Id => [others => 9]),
            others => Empty_Operation]);
      New_Item : constant Checkpoint :=
        (Doubt with delta Operations =>
           [1 => (Old.Operations (1) with delta Stage => Uncertain),
            others => Empty_Operation]);
   begin
      Check (Old, (Doubt with delta Operations => Old.Operations),
             None, T.Transition_Proposed);
      Check (Old, New_Item, [1 => Event (Old, New_Item, T.Interruption),
                            others => T.Empty_Observation],
             T.Transition_Proposed);
      Check (Old, Doubt, None, T.Unsupported_Change);
      Check (Old, (Doubt with delta Operations =>
               [1 => (Old.Operations (1) with delta
                      Result_Record_Id => [others => 8]),
                others => Empty_Operation]), None, T.Unsupported_Change);
      Check (New_Item, Done,
             [1 => Event (New_Item, Done, T.Reconciled_Outcome),
              others => T.Empty_Observation], T.Transition_Proposed);
   end Check_Provisional;

   procedure Check_Completion_And_Append
   with Global => null, Always_Terminates,
     Pre => Valid (Initial) and then Valid (Sent) and then
       Valid (Done) and then Valid (Acked)
   is
      Appended : constant Checkpoint :=
        (Sent with delta Operations_Count => 2,
         Operations => [1 => Work, 2 => (Work with delta Identity => [others => 2]),
                        others => Empty_Operation]);
   begin
      Check (Initial, Appended, None, T.Transition_Proposed);
      Check (Initial, (Appended with delta Operations =>
               (Appended.Operations with delta
                2 => (Appended.Operations (2) with delta Stage => Dispatched))),
             None, T.Unsupported_Change);
      Check (Initial, (Appended with delta Operations =>
               (Appended.Operations with delta 2 => Work)),
             None, T.Invalid_After);
      Check (Initial, (Sent with delta Operations => Done.Operations),
             None, T.Unsupported_Change);
      Check (Done, (Acked with delta Operations =>
               [1 => (Acked.Operations (1) with delta
                      Result_Record_Id => [others => 1]),
                others => Empty_Operation]), None, T.Unsupported_Change);
   end Check_Completion_And_Append;

   procedure Check_Empty
   with Global => null, Always_Terminates,
     Pre => Valid (Initial) and then Valid (Sent)
   is
      Before : constant Checkpoint :=
        (Initial with delta Operations_Count => 0,
         Operations => [others => Empty_Operation]);
      Empty_After : constant Checkpoint :=
        (Sent with delta Operations_Count => 0,
         Operations => [others => Empty_Operation]);
      Planned_After : constant Checkpoint :=
        (Sent with delta Operations => Initial.Operations);
   begin
      Check (Before, Empty_After, None, T.Transition_Proposed);
      Check (Before, Planned_After, None, T.Transition_Proposed);
      Check (Before, Sent, None, T.Unsupported_Change);
   end Check_Empty;

   procedure Check_Mixed
   with Global => null, Always_Terminates,
     Pre => Valid (Initial) and then Valid (Sent)
   is
      Before : constant Checkpoint :=
        (Initial with delta Operations_Count => 2,
         Operations =>
           [1 => Work, 2 => (Work with delta Identity => [others => 2],
                            Stage => Uncertain),
            others => Empty_Operation]);
      After : constant Checkpoint :=
        (Sent with delta Operations_Count => 3,
         Operations =>
           [1 => Work, 2 => (Before.Operations (2) with delta
                            Stage => Observed_Complete, Has_Result => True),
            3 => (Work with delta Identity => [others => 3]),
            others => Empty_Operation]);
      Change : constant T.Observation :=
        Event (Before, After, T.Reconciled_Outcome, 2);
   begin
      Check (Before, After, [2 => Change, others => T.Empty_Observation],
             T.Transition_Proposed);
      Check (Before, After, None, T.Need_Transition_Evidence);
      Check (Before, After, [1 | 2 => Change, others => T.Empty_Observation],
             T.Need_Transition_Evidence);
      Check (Before, After, [2 | 3 => Change, others => T.Empty_Observation],
             T.Need_Transition_Evidence);
   end Check_Mixed;

   --  Prove the complete phase relation for symbolic phase parameters,
   --  then exercise every original enum pair through this checked interface.
   procedure Check_Phase_Pair (Old_Stage, New_Stage : Operation_Phase)
   with Global => null, Always_Terminates
   is
      Before : constant Operation :=
        (Work with delta Stage => Old_Stage,
         Has_Result => Old_Stage in Observed_Complete | Acknowledged);
      After : constant Operation :=
        (Work with delta Stage => New_Stage,
         Has_Result => New_Stage in Observed_Complete | Acknowledged);
   begin
      pragma Assert (Valid_Operation (Before) and Valid_Operation (After));
      pragma Assert
        ((T.Required_Change (Before, After) /= T.Unsupported) =
           (Old_Stage = New_Stage or else
            (Old_Stage = Planned and then New_Stage = Dispatched) or else
            (Old_Stage = Dispatched and then
               New_Stage in Uncertain | Observed_Complete) or else
            (Old_Stage = Uncertain and then New_Stage = Observed_Complete)
            or else
            (Old_Stage = Observed_Complete and then
               New_Stage = Acknowledged)));
   end Check_Phase_Pair;

   procedure Check_Phase_Edges
   with Global => null, Always_Terminates
   is
   begin
      for Old_Stage in Operation_Phase loop
         for New_Stage in Operation_Phase loop
            Check_Phase_Pair (Old_Stage, New_Stage);
         end loop;
      end loop;
   end Check_Phase_Edges;

   procedure Check_Unchanged_Phases
   with Global => null, Always_Terminates,
     Pre => Valid (Initial) and then Valid (Sent)
   is
      Before, After : Checkpoint;
      Item : Operation;
   begin
      for Phase in Operation_Phase loop
         Item := (Work with delta Stage => Phase,
                  Has_Result => Phase /= Planned);
         Before := (Initial with delta
                    Operations => [1 => Item, others => Empty_Operation]);
         After := (Sent with delta Operations => Before.Operations);
         Check_Unchanged (Before, After);
      end loop;
   end Check_Unchanged_Phases;

   procedure Check_Repeated_Uncertainty
   with Global => null, Always_Terminates,
     Pre => Valid (Doubt) and then Valid (Done)
   is
      Again : constant Checkpoint :=
        (Doubt with delta Identity => [others => 15],
         Previous => Doubt.Identity, Epoch => 4);
      Still : constant Checkpoint :=
        (Again with delta Identity => [others => 16],
         Previous => Again.Identity, Epoch => 5);
      Final_Item : constant Checkpoint :=
        (Done with delta Identity => [others => 17],
         Previous => Still.Identity, Epoch => 6);
   begin
      Check_Unchanged (Doubt, Again);
      Check_Unchanged (Again, Still);
      Check (Still, Final_Item,
             [1 => Event (Still, Final_Item, T.Reconciled_Outcome),
              others => T.Empty_Observation], T.Transition_Proposed);
      Check (Again, (Still with delta Operations_Count => 0,
                     Operations => [others => Empty_Operation]),
             None, T.Operation_Lost);
   end Check_Repeated_Uncertainty;

   procedure Check_Capacity
   with Global => null, Always_Terminates,
     Pre => Valid (Initial)
   is
      Full : constant Checkpoint :=
        (Initial with delta Operations_Count => Max_Operations,
         Operations =>
           [for I in Operation_Index =>
              (Work with delta Identity => [others => Digest_Byte (I)])]);
      Following : constant Checkpoint :=
        (Full with delta Identity => [others => 11], Previous => Full.Identity,
         Epoch => 2);
      Swapped : constant Checkpoint :=
        (Following with delta Operations =>
           (Following.Operations with delta
            1 => Full.Operations (2), 2 => Full.Operations (1)));
   begin
      pragma Assert
        (for all I in Operation_Index =>
           Full.Operations (I).Identity (1) = Digest_Byte (I));
      pragma Assert
        (for all I in Operation_Index =>
           (for all J in Operation_Index =>
              (if I /= J then
                 Full.Operations (I).Identity (1) /=
                   Full.Operations (J).Identity (1))));
      pragma Assert (Valid_Operations (Full));
      pragma Assert (Valid (Full));
      pragma Assert (Valid (Following));
      pragma Assert (Valid (Swapped));
      Check_Unchanged (Full, Following);
      Check (Full, Swapped, None, T.Operation_Lost);
   end Check_Capacity;

   procedure Check_Maxima
   with Global => null, Always_Terminates,
     Pre => Valid (Initial)
   is
      Last_Before : constant Checkpoint :=
        (Initial with delta Epoch => Generation'Last - 1,
         Previous => [others => 9], Through | Retention_Epoch => Generation'Last);
      Last_After : constant Checkpoint :=
        (Last_Before with delta Epoch => Generation'Last,
         Identity => [others => 11], Previous => Last_Before.Identity,
         Scope => (Initial.Scope with delta Revision | Dirty => [others => 9]));
   begin
      Check_Unchanged (Last_Before, Last_After);
      Check (Last_After, (Last_After with delta Identity => [others => 12],
                          Previous => Last_After.Identity),
             None, T.Predecessor_Mismatch);
   end Check_Maxima;

begin
   Fixture_Properties;
   Check_Chain;
   Check_Headers;
   Check_Conservation;
   Check_Event_Bindings;
   Check_Event_Operation_Fields;
   Check_Event_Uniqueness;
   Check_Provisional;
   Check_Completion_And_Append;
   Check_Empty;
   Check_Mixed;
   Check_Phase_Edges;
   Check_Unchanged_Phases;
   Check_Repeated_Uncertainty;
   Check_Capacity;
   Check_Maxima;
end Continuity_Transition_Tests;
