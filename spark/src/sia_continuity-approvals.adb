package body SIA_Continuity.Approvals with SPARK_Mode is
   function Restore
     (Item : Checkpoint; Current : Current_Evidence; Expected : Restore_Selection;
      Seen : Observations) return Resolution
   is
      Base : constant Restoration := Classify (Item, Current);
      Status : Link_Status;
   begin
      if Base /= References_Proposed then
         return (Base, Not_Checked, 0);
      end if;
      for I in Claim_Index loop
         Status := Slot_Status (Item, I, Expected, Seen);
         if Status not in No_Observation | Reference_Correspondence then
            return (Need_Evidence, Status, I);
         end if;
         pragma Loop_Invariant
           (for all J in 1 .. I => Slot_Status (Item, J, Expected, Seen) in
              No_Observation | Reference_Correspondence);
      end loop;
      return
        (References_Proposed,
         (if Has_Permission (Item) then Reference_Correspondence
          else No_Observation), 0);
   end Restore;
end SIA_Continuity.Approvals;
