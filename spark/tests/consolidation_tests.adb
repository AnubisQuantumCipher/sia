with SIA_Consolidation; use SIA_Consolidation;
with SIA_Policy;

procedure Consolidation_Tests with SPARK_Mode is
   First : constant Day_Identity :=
     (Day => [others => 1], Sources => [others => 2], Originals => [others => 3]);
   Second : constant Day_Identity :=
     (Day => [others => 4], Sources => Zero, Originals => [others => 6]);
   Expected : constant Batch :=
     (Transaction => (Epoch => 1, Transaction => [others => 7]),
      Identity => [others => 8], Before_Cursor => Zero,
      After_Cursor => [others => 9], Count => 2,
      Days => [1 => First, 2 => Second, others => Empty_Day]);
   Initial : constant State :=
     (Expected => Expected, Stage => Pending, Results => Empty_Results);
   Good : constant Observation :=
     (Expected => Expected,
      Results => [1 => Retained_Intact, 2 => Compacted_Exact,
                  others => SIA_Consolidation.Not_Observed]);
   Recorded_State : constant State :=
     (Expected => Expected, Stage => Recorded, Results => Good.Results);

   procedure Check
     (Current : State; Item : Observation; Wanted : Decision)
   with Global => null, Always_Terminates,
     Pre => Classify (Current, Item) = Wanted
   is
      Candidate : State;
      Result : Decision;
   begin
      Plan (Current, Item, Candidate, Result);
      pragma Assert (Result = Wanted);
      pragma Assert (Candidate.Expected = Current.Expected);
      if Wanted = Record_Proposed then
         pragma Assert (Candidate.Stage = Recorded);
         pragma Assert (Candidate.Results = Item.Results);
         pragma Assert (Valid_State (Candidate));
      else
         pragma Assert (Candidate = Current);
      end if;
   end Check;

   procedure Check_Results with Global => null, Always_Terminates is
      Item : Observation := Good;
   begin
      Check (Initial, Good, Record_Proposed);
      Check (Recorded_State, Good, Identical_Record);
      for Kind in Disposition loop
         Item.Results (1) := Kind;
         if Kind in Retained_Intact | Compacted_Exact then
            Check (Initial, Item, Record_Proposed);
         else
            Check (Initial, Item, Refused);
         end if;
      end loop;
      Item := Good;
      Item.Results (1) := Compacted_Exact;
      Check (Recorded_State, Item, Refused);
      Item := Good;
      Item.Results (2) := SIA_Consolidation.Not_Observed;
      Check (Initial, Item, Refused);
      Item := Good;
      Item.Results (Max_Days) := Retained_Intact;
      Check (Initial, Item, Refused);
   end Check_Results;

   procedure Check_Binding_Byte (Index : Positive)
   with Global => null, Always_Terminates, Pre => Index <= 32
   is
      Item : Observation := Good;
   begin
      Item.Expected.Transaction.Transaction (Index) := 0;
      Check (Initial, Item, Refused);
      Item := Good;
      Item.Expected.Identity (Index) := 0;
      Check (Initial, Item, Refused);
      Item := Good;
      Item.Expected.Before_Cursor (Index) := 1;
      Check (Initial, Item, Refused);
      Item := Good;
      Item.Expected.After_Cursor (Index) := 0;
      Check (Initial, Item, Refused);
      Item := Good;
      Item.Expected.Days (1).Day (Index) := 0;
      Check (Initial, Item, Refused);
      Item := Good;
      Item.Expected.Days (1).Sources (Index) := 0;
      Check (Initial, Item, Refused);
      Item := Good;
      Item.Expected.Days (1).Originals (Index) := 0;
      Check (Initial, Item, Refused);
   end Check_Binding_Byte;

   procedure Check_Invalid_State with Global => null, Always_Terminates is
      Current : State := Initial;
      Item : Observation := Good;
   begin
      Current.Expected.Count := 0;
      Item.Expected := Current.Expected;
      Check (Current, Item, Refused);
      Current := Initial;
      Current.Expected.Count := Max_Days;
      Item.Expected := Current.Expected;
      Check (Current, Item, Refused);
      Current := Initial;
      Current.Expected.Days (2) := Current.Expected.Days (1);
      Item.Expected := Current.Expected;
      Check (Current, Item, Refused);
      Current := Initial;
      Current.Expected.Days (Max_Days) := First;
      Item.Expected := Current.Expected;
      Check (Current, Item, Refused);
      Current := Initial;
      Current.Expected.After_Cursor := Current.Expected.Before_Cursor;
      Item.Expected := Current.Expected;
      Check (Current, Item, Refused);
      Current := Initial;
      Current.Results := Good.Results;
      Check (Current, Good, Refused);
      Current := Recorded_State;
      Current.Results (2) := Partial_Cleanup;
      Check (Current, Good, Refused);
   end Check_Invalid_State;

   procedure Check_Zero_And_Count with Global => null, Always_Terminates is
      Current : State := Initial;
      Item : Observation := Good;
   begin
      Current.Expected.Identity := Zero;
      Item.Expected := Current.Expected;
      Check (Current, Item, Refused);
      Current := Initial;
      Current.Expected.Transaction.Epoch := 0;
      Item.Expected := Current.Expected;
      Check (Current, Item, Refused);
      Current := Initial;
      Current.Expected.Days (1).Originals := Zero;
      Item.Expected := Current.Expected;
      Check (Current, Item, Refused);
      Current := Initial;
      Current.Expected.Days (1).Day := Zero;
      Item.Expected := Current.Expected;
      Check (Current, Item, Refused);
      Item := Good;
      Item.Expected.Count := 1;
      Check (Initial, Item, Refused);
      Item := Good;
      Item.Expected.Transaction.Epoch := 2;
      Check (Initial, Item, Refused);
   end Check_Zero_And_Count;

   procedure Check_Single_Day with Global => null, Always_Terminates is
      Current : State := Initial;
      Item : Observation := Good;
   begin
      Current.Expected.Count := 1;
      Current.Expected.Days (2) := Empty_Day;
      Current.Expected.Transaction.Transaction := Zero;
      Item.Expected := Current.Expected;
      Item.Results (2) := SIA_Consolidation.Not_Observed;
      Check (Current, Item, Record_Proposed);
      Current.Stage := Recorded;
      Current.Results := Item.Results;
      Check (Current, Item, Identical_Record);
   end Check_Single_Day;

   procedure Check_Capacity with Global => null, Always_Terminates is
      use type SIA_Policy.Digest;
      Current : State := Initial;
      Item : Observation := Good;
   begin
      Current.Expected.Count := Max_Days;
      for I in Day_Index loop
         Current.Expected.Days (I) :=
           (Day => [1 => SIA_Policy.Digest_Byte (I / 256),
                    2 => SIA_Policy.Digest_Byte (I mod 256), others => 0],
            Sources => Zero, Originals => [others => 3]);
         pragma Loop_Invariant
           (for all J in 1 .. I =>
              Integer (Current.Expected.Days (J).Day (1)) * 256 +
              Integer (Current.Expected.Days (J).Day (2)) = J);
         pragma Loop_Invariant
           (for all J in 1 .. I =>
              Current.Expected.Days (J).Originals = First.Originals);
      end loop;
      Item.Expected := Current.Expected;
      Item.Results := [others => Retained_Intact];
      Check (Current, Item, Record_Proposed);
      Current.Stage := Recorded;
      Current.Results := Item.Results;
      Check (Current, Item, Identical_Record);
      Item.Results (Max_Days) := Partial_Cleanup;
      Check (Current, Item, Refused);
   end Check_Capacity;
begin
   Check_Results;
   Check_Invalid_State;
   Check_Zero_And_Count;
   Check_Single_Day;
   Check_Capacity;
   for Index in 1 .. 32 loop
      Check_Binding_Byte (Index);
   end loop;
end Consolidation_Tests;
