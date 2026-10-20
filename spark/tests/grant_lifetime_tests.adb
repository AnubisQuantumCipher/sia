with SIA_Request_Wire; use SIA_Request_Wire;
with SIA_Request_Admission; use SIA_Request_Admission;
with SIA_Grant_Lifetime; use SIA_Grant_Lifetime;

procedure Grant_Lifetime_Tests with SPARK_Mode is
   Item : constant Request :=
     (Action => Propose, Before_Phase => 2, After_Phase => 3,
      Capability => [others => 1], Source => [others => 2],
      Transaction => [others => 3], Payload => [others => 4],
      Predecessor_Receipt => [others => 5],
      Before_Generation => 6, Target_Generation => 7);
   Retained : constant Scoped_Grant :=
     (Domain => (Boot => [others => 6], Service => [others => 7]),
      Authority => (Active => True, Subject => 1000,
                    Not_Before => 10, Expires => 20, Expected => Item));

   procedure Check_Changed_Domain (Index : Positive)
   with Global => null, Always_Terminates, Pre => Index <= 32
   is
      Current : Scope := Retained.Domain;
   begin
      Current.Boot (Index) := 0;
      pragma Assert
        (Classify_Scoped (Retained, Current, 1000, 10, Item) = Denied);
      Current := Retained.Domain;
      Current.Service (Index) := 0;
      pragma Assert
        (Classify_Scoped (Retained, Current, 1000, 10, Item) = Denied);
   end Check_Changed_Domain;

   procedure Check_Invalid_And_Matching with Global => null, Always_Terminates is
      Changed : Scoped_Grant := Retained;
      Observation : Request := Item;
   begin
      pragma Assert
        (Classify_Scoped (Retained, Retained.Domain, 1000, 10, Item) = Proposal_Only);
      Changed.Domain.Boot := [others => 0];
      pragma Assert
        (Classify_Scoped (Changed, Changed.Domain, 1000, 10, Item) = Denied);
      Changed := Retained;
      Changed.Domain.Service := [others => 0];
      pragma Assert
        (Classify_Scoped (Changed, Changed.Domain, 1000, 10, Item) = Denied);
      Changed := Retained;
      Changed.Authority.Active := False;
      pragma Assert
        (Classify_Scoped (Changed, Changed.Domain, 1000, 10, Item) = Denied);
      pragma Assert
        (Classify_Scoped (Retained, Retained.Domain, 1001, 10, Item) = Denied);
      pragma Assert
        (Classify_Scoped (Retained, Retained.Domain, 1000, 20, Item) = Denied);
      Observation.Action := Observe;
      Changed := Retained;
      Changed.Authority.Expected := Observation;
      pragma Assert
        (Classify_Scoped (Changed, Changed.Domain, 1000, 10, Observation) = Observe_Only);
   end Check_Invalid_And_Matching;
begin
   Check_Invalid_And_Matching;
   for Index in 1 .. 32 loop
      Check_Changed_Domain (Index);
   end loop;
end Grant_Lifetime_Tests;
