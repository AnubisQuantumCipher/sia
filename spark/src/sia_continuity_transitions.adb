package body SIA_Continuity_Transitions with SPARK_Mode is
   function Classify
     (Before, After : Checkpoint; Items : Observations) return Transition_Result
   is
   begin
      if not Valid (Before) then
         return Invalid_Before;
      elsif not Valid (After) then
         return Invalid_After;
      elsif not Same_Task (Before, After) then
         return Task_Mismatch;
      elsif not Next_Link (Before, After) then
         return Predecessor_Mismatch;
      elsif not Monotone (Before, After) then
         return Watermark_Regression;
      elsif not Conserved (Before, After) then
         return Operation_Lost;
      elsif not Legal_Changes (Before, After) then
         return Unsupported_Change;
      elsif not Events_Joined (Before, After, Items) then
         return Need_Transition_Evidence;
      else
         return Transition_Proposed;
      end if;
   end Classify;
end SIA_Continuity_Transitions;
