package body SIA_Retraction with SPARK_Mode is
   function Classify
     (State : Plan_State; Item : Request;
      Parents : Completeness; Recovery_Debt : Boolean) return Decision
   is
      Result : Decision := Refused;
   begin
      if Valid_State (State) and then Valid_Request (Item) and then
        Parents = Verified_Complete and then not Recovery_Debt
      then
         if State.Stage = Active and then Item.Target = State.Item and then
           Item.Before = State.Epoch
         then
            Result := Proposed_Only;
         elsif State.Stage = Retraction_Proposed and then Item = State.Retained then
            Result := Identical_Proposal;
         end if;
      end if;
      return Result;
   end Classify;

   procedure Plan
     (State : Plan_State; Item : Request;
      Parents : Completeness; Recovery_Debt : Boolean;
      Candidate : out Plan_State; Result : out Decision)
   is
   begin
      Candidate := State;
      Result := Classify (State, Item, Parents, Recovery_Debt);
      if Result = Proposed_Only then
         Candidate := (Item => State.Item, Epoch => Item.After,
                       Stage => Retraction_Proposed, Retained => Item);
      end if;
   end Plan;
end SIA_Retraction;
