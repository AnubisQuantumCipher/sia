package body SIA_Continuity with SPARK_Mode is
   function Classify (Item : Checkpoint; Current : Current_Evidence)
      return Restoration is
   begin
      if not Valid (Item) then
         return Invalid_Checkpoint;
      elsif not Same_Task (Item, Current) then
         return Identity_Mismatch;
      elsif not Fresh (Item, Current) then
         return Stale_Checkpoint;
      elsif not Joined (Item, Current) or else not Coverage_Ready (Item) then
         return Need_Evidence;
      elsif Item.Scope.Revision /= Current.Scope.Revision or else
        Item.Scope.Dirty /= Current.Scope.Dirty
      then
         return Reconcile_Repository;
      elsif Uncertain_Operations (Item) then
         return Reconcile_Operations;
      else
         return References_Proposed;
      end if;
   end Classify;
end SIA_Continuity;
