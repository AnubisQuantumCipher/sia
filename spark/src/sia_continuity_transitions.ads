with SIA_Policy;
with SIA_Continuity;

--  Conditional comparison only. Independent producers must authenticate both
--  heads, retained events and outcome artifacts before runtime reliance.
package SIA_Continuity_Transitions with SPARK_Mode, Pure is
   use SIA_Policy;
   use SIA_Continuity;

   type Change_Kind is
     (No_Change, Dispatch_Attempt, Interruption, Observed_Outcome,
      Reconciled_Outcome, Acknowledgment, Unsupported);
   subtype Event_Kind is Change_Kind range Dispatch_Attempt .. Acknowledgment;
   type Observation is record
      State : Availability;
      Before_Id, After_Id : Digest;
      Before_Epoch, After_Epoch : Generation;
      Event_Record_Id : Digest;
      Kind : Event_Kind;
      Before_Operation, After_Operation : Operation;
      Has_Outcome : Boolean;
      Outcome_Record_Id : Digest;
   end record;
   Empty_Observation : constant Observation :=
     (State => Unknown,
      Before_Id | After_Id | Event_Record_Id => [others => 0],
      Before_Epoch | After_Epoch => 0, Kind => Dispatch_Attempt,
      Before_Operation | After_Operation =>
        (Identity | Action | Source_Record_Id | Result_Record_Id => [others => 0],
         Stage => Planned, Has_Result => False),
      Has_Outcome => False, Outcome_Record_Id => [others => 0]);
   type Observations is array (Operation_Index) of Observation;
   type Transition_Result is
     (Invalid_Before, Invalid_After, Task_Mismatch, Predecessor_Mismatch,
      Watermark_Regression, Operation_Lost, Unsupported_Change,
      Need_Transition_Evidence, Transition_Proposed);

   function Same_Operation (Before, After : Operation) return Boolean is
     (Before.Identity = After.Identity and then
      Before.Action = After.Action and then
      Before.Source_Record_Id = After.Source_Record_Id)
   with Global => null;

   function Same_Result (Before, After : Operation) return Boolean is
     (Before.Has_Result = After.Has_Result and then
      Before.Result_Record_Id = After.Result_Record_Id)
   with Global => null;

   function Required_Change (Before, After : Operation) return Change_Kind is
     (if Before = After then No_Change
      elsif Before.Stage = Planned and then After.Stage = Dispatched
        and then not After.Has_Result then Dispatch_Attempt
      elsif Before.Stage = Dispatched and then After.Stage = Uncertain
        and then Same_Result (Before, After) then Interruption
      elsif Before.Stage = Dispatched and then After.Stage = Observed_Complete
        and then After.Has_Result then Observed_Outcome
      elsif Before.Stage = Uncertain and then After.Stage = Observed_Complete
        and then After.Has_Result then Reconciled_Outcome
      elsif Before.Stage = Observed_Complete and then After.Stage = Acknowledged
        and then Same_Result (Before, After) then Acknowledgment
      else Unsupported)
   with Global => null;

   function Same_Task (Before, After : Checkpoint) return Boolean is
     (Before.Scope.Task_Id = After.Scope.Task_Id and then
      Before.Scope.Session_Id = After.Scope.Session_Id and then
      Before.Scope.Repository = After.Scope.Repository)
   with Global => null;

   function Next_Link (Before, After : Checkpoint) return Boolean is
     (Before.Epoch < Generation'Last and then
      After.Epoch = Before.Epoch + 1 and then After.Previous = Before.Identity)
   with Global => null;

   function Monotone (Before, After : Checkpoint) return Boolean is
     (After.Through >= Before.Through and then
      After.Retention_Epoch >= Before.Retention_Epoch)
   with Global => null;

   function Conserved (Before, After : Checkpoint) return Boolean is
     (After.Operations_Count >= Before.Operations_Count and then
      (for all I in 1 .. Before.Operations_Count =>
         Same_Operation (Before.Operations (I), After.Operations (I))))
   with Global => null;

   function Legal_Changes (Before, After : Checkpoint) return Boolean is
     ((for all I in 1 .. Before.Operations_Count =>
         Required_Change (Before.Operations (I), After.Operations (I)) /=
           Unsupported) and then
      (for all I in Before.Operations_Count + 1 .. After.Operations_Count =>
         After.Operations (I).Stage = Planned and then
         not After.Operations (I).Has_Result))
   with Global => null;

   function Bound_Event
     (Item : Observation; Before, After : Checkpoint; I : Operation_Index)
      return Boolean is
     (Item.State = Retained and then Item.Before_Id = Before.Identity and then
      Item.After_Id = After.Identity and then
      Item.Before_Epoch = Before.Epoch and then Item.After_Epoch = After.Epoch
      and then Item.Before_Operation = Before.Operations (I) and then
      Item.After_Operation = After.Operations (I) and then
      Item.Kind = Required_Change (Before.Operations (I), After.Operations (I))
      and then
        (if Item.Kind in Observed_Outcome | Reconciled_Outcome then
            Item.Has_Outcome and then
            Item.Outcome_Record_Id = After.Operations (I).Result_Record_Id
         else not Item.Has_Outcome and then Item.Outcome_Record_Id = Zero))
   with Global => null;

   function Changed (Before, After : Checkpoint; I : Operation_Index)
      return Boolean is
     (I <= Before.Operations_Count and then
      Before.Operations (I) /= After.Operations (I))
   with Global => null;

   function Events_Joined
     (Before, After : Checkpoint; Items : Observations) return Boolean is
     ((for all I in Operation_Index =>
         (if Changed (Before, After, I) then
             Bound_Event (Items (I), Before, After, I)
          else Items (I) = Empty_Observation)) and then
      (for all I in Operation_Index =>
         (for all J in Operation_Index =>
            (if I /= J and then Changed (Before, After, I) and then
                Changed (Before, After, J)
             then Items (I).Event_Record_Id /= Items (J).Event_Record_Id))))
   with Global => null;

   --  Proposal only: no publication, action, retry or acknowledgment grant.
   function Classify
     (Before, After : Checkpoint; Items : Observations) return Transition_Result
   with Global => null,
     Post => Classify'Result =
       (if not Valid (Before) then Invalid_Before
        elsif not Valid (After) then Invalid_After
        elsif not Same_Task (Before, After) then Task_Mismatch
        elsif not Next_Link (Before, After) then Predecessor_Mismatch
        elsif not Monotone (Before, After) then Watermark_Regression
        elsif not Conserved (Before, After) then Operation_Lost
        elsif not Legal_Changes (Before, After) then Unsupported_Change
        elsif not Events_Joined (Before, After, Items)
          then Need_Transition_Evidence
        else Transition_Proposed);
end SIA_Continuity_Transitions;
