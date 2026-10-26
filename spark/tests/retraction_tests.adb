with SIA_Policy; use SIA_Policy;
with SIA_Retraction; use SIA_Retraction;

procedure Retraction_Tests with SPARK_Mode is
   Original : constant Descriptor :=
     (Identity => [others => 1], Content => [others => 2],
      Parents => [others => 3], Provenance => [others => 4],
      Version => 5, From => Derived_Record);
   Initial : constant Plan_State :=
     (Item => Original, Epoch => 7, Stage => Active,
      Retained => Empty_Request);
   Proposal : constant Request :=
     (Target => Original, Operation => [others => 6], Before => 7, After => 8);
   Retraction : constant Plan_State :=
     (Item => Original, Epoch => 8, Stage => Retraction_Proposed,
      Retained => Proposal);

   --  Every independently expected call must prove this precondition;
   --  it is not an Assume. Candidate assertions also exercise Plan's contract.
   procedure Check
     (State : Plan_State; Item : Request; Expected : Decision;
      Parents : Completeness := Verified_Complete; Debt : Boolean := False)
   with Global => null, Always_Terminates,
     Pre => Classify (State, Item, Parents, Debt) = Expected
   is
      Candidate : Plan_State;
      Result : Decision;
   begin
      Plan (State, Item, Parents, Debt, Candidate, Result);
      pragma Assert (Result = Expected);
      pragma Assert (Candidate.Item = State.Item);
      if Expected = Proposed_Only then
         pragma Assert (Candidate.Epoch = Item.After);
         pragma Assert (Candidate.Stage = Retraction_Proposed);
         pragma Assert (Candidate.Retained = Item);
         pragma Assert (Valid_State (Candidate));
      else
         pragma Assert (Candidate = State);
      end if;
   end Check;

   procedure Check_Origins with Global => null, Always_Terminates is
      State : Plan_State := Initial;
      Item : Request := Proposal;
   begin
      for Kind in Origin loop
         State.Item.From := Kind;
         Item.Target := State.Item;
         if Kind in Derived_Record | Model_Record then
            Check (State, Item, Proposed_Only);
         else
            Check (State, Item, Refused);
         end if;
      end loop;
      Check (Initial, Proposal, Proposed_Only);
      Check (Retraction, Proposal, Identical_Proposal);
      for Coverage in Completeness loop
         if Coverage /= Verified_Complete then
            Check (Initial, Proposal, Refused, Coverage);
            Check (Retraction, Proposal, Refused, Coverage);
         end if;
      end loop;
      Check (Initial, Proposal, Refused, Debt => True);
      Check (Retraction, Proposal, Refused, Debt => True);
   end Check_Origins;

   procedure Check_Byte (Index : Positive)
   with Global => null, Always_Terminates, Pre => Index <= 32
   is
      Changed : Request := Proposal;
   begin
      Changed.Target.Identity (Index) := 0;
      Check (Initial, Changed, Refused);
      Check (Retraction, Changed, Refused);
      Changed := Proposal;
      Changed.Target.Content (Index) := 0;
      Check (Initial, Changed, Refused);
      Check (Retraction, Changed, Refused);
      Changed := Proposal;
      Changed.Target.Parents (Index) := 0;
      Check (Initial, Changed, Refused);
      Check (Retraction, Changed, Refused);
      Changed := Proposal;
      Changed.Target.Provenance (Index) := 0;
      Check (Initial, Changed, Refused);
      Check (Retraction, Changed, Refused);
      Changed := Proposal;
      Changed.Operation (Index) := 0;
      Check (Retraction, Changed, Refused);
      --  A different nonzero new operation is allowed before retention.
      Check (Initial, Changed, Proposed_Only);
   end Check_Byte;

   procedure Check_Scalars with Global => null, Always_Terminates is
      Changed : Request := Proposal;
   begin
      Changed.Target.Version := 6;
      Check (Initial, Changed, Refused);
      Check (Retraction, Changed, Refused);
      Changed := Proposal;
      Changed.Target.From := Model_Record;
      Check (Initial, Changed, Refused);
      Check (Retraction, Changed, Refused);
      Changed := Proposal;
      Changed.Before := 6;
      Changed.After := 7;
      Check (Initial, Changed, Refused);
      Check (Retraction, Changed, Refused);
      Changed := Proposal;
      Changed.After := 9;
      Check (Initial, Changed, Refused);
      Check (Retraction, Changed, Refused);
      Changed := Proposal;
      Changed.Operation := [others => 0];
      Check (Initial, Changed, Refused);
      Check (Retraction, Changed, Refused);
   end Check_Scalars;

   procedure Check_Malformed_Retained with Global => null, Always_Terminates is
      State : Plan_State := Initial;
   begin
      State.Retained := Proposal;
      Check (State, Proposal, Refused);
      State := Retraction;
      State.Retained := Empty_Request;
      Check (State, Proposal, Refused);
      State := Retraction;
      State.Retained.Target.Content := [others => 0];
      Check (State, Proposal, Refused);
      State := Retraction;
      State.Retained.Operation := [others => 0];
      Check (State, Proposal, Refused);
      State := Retraction;
      State.Retained.After := 9;
      Check (State, Proposal, Refused);
      State := Retraction;
      State.Epoch := 9;
      Check (State, Proposal, Refused);
      State := Retraction;
      State.Item.From := Source_Record;
      State.Retained.Target := State.Item;
      Check (State, State.Retained, Refused);
   end Check_Malformed_Retained;

   procedure Check_Zero with Global => null, Always_Terminates is
      State : Plan_State := Initial;
      Item : Request := Proposal;
   begin
      State.Item.Identity := [others => 0];
      Item.Target := State.Item;
      Check (State, Item, Refused);
      State := Initial;
      Item := Proposal;
      State.Item.Version := 0;
      Item.Target := State.Item;
      Check (State, Item, Refused);
      State := Initial;
      Item := Proposal;
      State.Epoch := 0;
      Item.Before := 0;
      Item.After := 1;
      Check (State, Item, Refused);
      --  Non-identity digests retain their full value domain.
      State := Initial;
      State.Item.Content := [others => 0];
      State.Item.Parents := [others => 0];
      State.Item.Provenance := [others => 0];
      Item := Proposal;
      Item.Target := State.Item;
      Check (State, Item, Proposed_Only);
   end Check_Zero;

   procedure Check_Exhaustion with Global => null, Always_Terminates is
      State : Plan_State := Initial;
      Item : Request := Proposal;
      Last : Plan_State;
   begin
      State.Item.Version := Generation'Last;
      State.Epoch := Generation'Last - 1;
      Item.Target := State.Item;
      Item.Before := Generation'Last - 1;
      Item.After := Generation'Last;
      Check (State, Item, Proposed_Only);
      Last := (Item => State.Item, Epoch => Generation'Last,
               Stage => Retraction_Proposed, Retained => Item);
      Check (Last, Item, Identical_Proposal);
      State.Epoch := Generation'Last;
      Item.Before := Generation'Last;
      Check (State, Item, Refused);
      Item.After := 0;
      Check (State, Item, Refused);
      Item := Proposal;
      Item.After := 0;
      Check (Initial, Item, Refused);
   end Check_Exhaustion;
begin
   Check_Origins;
   Check_Scalars;
   Check_Malformed_Retained;
   Check_Zero;
   Check_Exhaustion;
   for Index in 1 .. 32 loop
      Check_Byte (Index);
   end loop;
end Retraction_Tests;
