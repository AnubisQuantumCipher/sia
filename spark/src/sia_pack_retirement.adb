package body SIA_Pack_Retirement with SPARK_Mode is
   function Prefix_Sizes (Items : Roster; Organ_Bytes : Organ_Length)
      return Size_Array
   is
      Sizes : Size_Array := [others => 0];
      Total : Logical_Size :=
        ((((((Magic'Length + 1) + Organ_Bytes) + 3) + 1) + 4) + 32);
      I : Natural range 0 .. Max_Records + 1 := 0;
   begin
      --  Assign the complete static array range, including header and padding.
      while I <= Max_Records loop
         if I > 0 and then I <= Items.Count then
            Total := (Total + 68) + Items.Records (I).Bytes;
         end if;
         Sizes (I) := (if I <= Items.Count then Total else 0);
         pragma Loop_Variant (Decreases => (Max_Records + 1) - I);
         pragma Loop_Invariant (I <= Max_Records);
         pragma Loop_Invariant
           (Total = Sizes (Natural'Min (I, Items.Count)));
         pragma Loop_Invariant
           (Sizes (0) = ((((((Magic'Length + 1) + Organ_Bytes) + 3) + 1) + 4) + 32));
         pragma Loop_Invariant
           (for all J in 1 .. I =>
              (if J <= Items.Count then
                  Sizes (J) = (Sizes (J - 1) + 68) + Items.Records (J).Bytes
               else Sizes (J) = 0));
         pragma Loop_Invariant
           (for all J in I + 1 .. Max_Records => Sizes (J) = 0);
         pragma Loop_Invariant
           (for all J in Record_Count =>
              Sizes (J) <= Max_Header + J * (68 + Max_Frame_Bytes));
         I := I + 1;
      end loop;
      return Sizes;
   end Prefix_Sizes;

   function Classify
     (Item : Plan; Seen : Observation; Execution : Digest; Slot : Record_Index)
      return Decision
   is
      Result : Decision := Refused;
   begin
      if Common_Matches (Item, Seen, Execution) then
         if Unlink_Matches (Item, Seen, Slot) then
            Result := Unlink_Proposed;
         elsif Retired_Matches (Item, Seen, Slot) then
            Result := Retirement_Recorded;
         elsif Original_Absence_Matches (Item, Seen, Slot) then
            Result := Originally_Absent;
         end if;
      end if;
      return Result;
   end Classify;
end SIA_Pack_Retirement;
