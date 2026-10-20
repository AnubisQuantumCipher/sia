with SIA_Request_Wire; use SIA_Request_Wire;
with SIA_Request_Admission; use SIA_Request_Admission;

procedure Request_Admission_Tests with SPARK_Mode is
   Base : constant Request :=
     (Action => Propose, Before_Phase => 2, After_Phase => 3,
      Capability => [others => 1], Source => [others => 2],
      Transaction => [others => 3], Payload => [others => 4],
      Predecessor_Receipt => [others => 5],
      Before_Generation => 6, Target_Generation => 7);
   Authority : constant Grant :=
     (Active => True, Subject => 1000, Not_Before => 10, Expires => 20,
      Expected => Base);

   procedure Check_Lifetime with Global => null, Always_Terminates is
      Changed : Grant := Authority;
   begin
      pragma Assert (Classify (Authority, 1000, 10, Base) = Proposal_Only);
      pragma Assert (Classify (Authority, 1000, 19, Base) = Proposal_Only);
      pragma Assert (Classify (Authority, 1000, 9, Base) = Denied);
      pragma Assert (Classify (Authority, 1000, 20, Base) = Denied);
      pragma Assert (Classify (Authority, 1001, 10, Base) = Denied);
      Changed.Active := False;
      pragma Assert (Classify (Changed, 1000, 10, Base) = Denied);
      Changed := Authority;
      Changed.Not_Before := 20;
      pragma Assert (Classify (Changed, 1000, 20, Base) = Denied);
      Changed.Not_Before := Tick'Last;
      pragma Assert (Classify (Changed, 1000, Tick'Last, Base) = Denied);
      Changed.Not_Before := 0;
      Changed.Expires := 0;
      pragma Assert (Classify (Changed, 1000, 0, Base) = Denied);
      Changed.Not_Before := 0;
      Changed.Expires := Tick'Last;
      pragma Assert (Classify (Changed, 1000, Tick'Last - 1, Base) = Proposal_Only);
      pragma Assert (Classify (Changed, 1000, Tick'Last, Base) = Denied);
   end Check_Lifetime;

   procedure Check_Identity (Index : Positive)
   with Global => null, Always_Terminates, Pre => Index <= 32
   is
      Changed : Request := Base;
   begin
      Changed.Capability (Index) := 0;
      pragma Assert (Classify (Authority, 1000, 10, Changed) = Denied);
      Changed := Base;
      Changed.Source (Index) := 0;
      pragma Assert (Classify (Authority, 1000, 10, Changed) = Denied);
      Changed := Base;
      Changed.Transaction (Index) := 0;
      pragma Assert (Classify (Authority, 1000, 10, Changed) = Denied);
      Changed := Base;
      Changed.Payload (Index) := 0;
      pragma Assert (Classify (Authority, 1000, 10, Changed) = Denied);
      Changed := Base;
      Changed.Predecessor_Receipt (Index) := 0;
      pragma Assert (Classify (Authority, 1000, 10, Changed) = Denied);
   end Check_Identity;

   procedure Check_Fields with Global => null, Always_Terminates is
      Changed : Request := Base;
      Read_Grant : Grant := Authority;
   begin
      Changed.Before_Phase := 1;
      pragma Assert (Classify (Authority, 1000, 10, Changed) = Denied);
      Changed := Base;
      Changed.After_Phase := 4;
      pragma Assert (Classify (Authority, 1000, 10, Changed) = Denied);
      Changed := Base;
      Changed.Before_Generation := 5;
      pragma Assert (Classify (Authority, 1000, 10, Changed) = Denied);
      Changed := Base;
      Changed.Target_Generation := 8;
      pragma Assert (Classify (Authority, 1000, 10, Changed) = Denied);
      Changed := Base;
      Changed.Action := Observe;
      pragma Assert (Classify (Authority, 1000, 10, Changed) = Denied);
      Read_Grant.Expected := Changed;
      pragma Assert (Classify (Read_Grant, 1000, 10, Changed) = Observe_Only);
      Changed.Capability := [others => 0];
      Read_Grant.Expected := Changed;
      pragma Assert (Classify (Read_Grant, 1000, 10, Changed) = Denied);
      Changed.Action := Propose;
      Read_Grant.Expected := Changed;
      pragma Assert (Classify (Read_Grant, 1000, 10, Changed) = Denied);
   end Check_Fields;
   procedure Check_Frame with Global => null, Always_Terminates is
      Bytes : Frame :=
        [1 => 1, 2 => 2, 3 => 2, 4 => 3,
         9 .. 40 => 1, 41 .. 72 => 2, 73 .. 104 => 3,
         105 .. 136 => 4, 137 .. 168 => 5, 176 => 6, 184 => 7,
         others => 0];
      Item : Request;
      Decision : Classification;
      Changed : Grant := Authority;
   begin
      Classify_Frame (Authority, 1000, 10, Bytes, 192, Item, Decision);
      pragma Assert (Item = Base and then Decision = Proposal_Only);
      Classify_Frame (Authority, 1001, 10, Bytes, 192, Item, Decision);
      pragma Assert (Item = Base and then Decision = Denied);
      Classify_Frame (Authority, 1000, 20, Bytes, 192, Item, Decision);
      pragma Assert (Item = Base and then Decision = Denied);
      Changed.Active := False;
      Classify_Frame (Changed, 1000, 10, Bytes, 192, Item, Decision);
      pragma Assert (Item = Base and then Decision = Denied);
      Bytes (105) := 0;
      Changed := Authority;
      Changed.Expected.Payload (1) := 0;
      Classify_Frame (Authority, 1000, 10, Bytes, 192, Item, Decision);
      pragma Assert (Item = Changed.Expected and then Decision = Denied);
      Bytes (105) := 4;
      Bytes (2) := 1;
      Changed := Authority;
      Changed.Expected.Action := Observe;
      Classify_Frame (Changed, 1000, 10, Bytes, 192, Item, Decision);
      pragma Assert (Item.Action = Observe and then Decision = Observe_Only);
      Bytes (5) := 1;
      Classify_Frame (Changed, 1000, 10, Bytes, 192, Item, Decision);
      pragma Assert (Item = Empty_Request and then Decision = Denied);
      Bytes (5) := 0;
      for Length in 0 .. 193 loop
         if Length /= 192 then
            Classify_Frame (Changed, 1000, 10, Bytes, Length, Item, Decision);
            pragma Assert (Item = Empty_Request and then Decision = Denied);
         end if;
      end loop;
      Bytes (169) := 128;
      Classify_Frame (Changed, 1000, 10, Bytes, 192, Item, Decision);
      pragma Assert (Item = Empty_Request and then Decision = Denied);
   end Check_Frame;
begin
   Check_Frame;
   Check_Lifetime;
   Check_Fields;
   for Index in 1 .. 32 loop
      Check_Identity (Index);
   end loop;
end Request_Admission_Tests;
