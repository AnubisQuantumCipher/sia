with SIA_Policy; use SIA_Policy;
with SIA_Continuity; use SIA_Continuity;

procedure Continuity_Tests with SPARK_Mode is
   Initial : constant Checkpoint :=
     (Scope => (Task_Id => [others => 1], Session_Id => [others => 2],
                Repository => [others => 3], Revision => [others => 4],
                Dirty => [others => 5]),
      Identity => [others => 6], Previous => Zero, Capture => [others => 7],
      Epoch => 1, Through => 4, Retention_Epoch => 1,
      Coverage => [Goal | Acceptance | Source | Next_Action => Complete,
                   others => SIA_Continuity.Observed_Empty],
      Count => 4,
      Claims =>
        [1 => (Identity => [others => 1], Slot => [others => 1],
               Source_Record_Id => Zero, Sequence => 1, Kind => Goal,
               From => Source_Record, Speaker => User, Replaces => 0),
         2 => (Identity => [others => 2], Slot => [others => 2],
               Source_Record_Id => [others => 2], Sequence => 2,
               Kind => Acceptance, From => Source_Record,
               Speaker => User, Replaces => 0),
         3 => (Identity => [others => 3], Slot => [others => 3],
               Source_Record_Id => [others => 3], Sequence => 3,
               Kind => Source, From => Source_Record,
               Speaker => Tool, Replaces => 0),
         4 => (Identity => [others => 4], Slot => [others => 4],
               Source_Record_Id => [others => 4], Sequence => 4,
               Kind => Next_Action, From => Model_Record,
               Speaker => Assistant, Replaces => 0),
         others => Empty_Claim],
      Operations_Count => 0, Operations => [others => Empty_Operation]);

   Corrected_Six : constant Checkpoint :=
     (Initial with delta Count => 6, Through => 6,
      Claims =>
        (Initial.Claims with delta
         5 => (Initial.Claims (1) with delta Identity => [others => 5],
               Sequence => 5, Replaces => 1),
         6 => (Initial.Claims (1) with delta Identity => [others => 6],
               Sequence => 6, Replaces => 5)));

   Permission_Five : constant Checkpoint :=
     (Initial with delta Count => 5, Through => 5,
      Coverage => (Initial.Coverage with delta Permission_Reference => Complete),
      Claims =>
        (Initial.Claims with delta
         5 => (Identity => [others => 5], Slot => [others => 5],
               Source_Record_Id => [others => 5], Sequence => 5,
               Kind => Permission_Reference, From => Source_Record,
               Speaker => User, Replaces => 0)));

   Pending_Five : constant Checkpoint :=
     (Permission_Five with delta
      Coverage =>
        (Permission_Five.Coverage with delta
         Permission_Reference => SIA_Continuity.Observed_Empty,
         Pending_Approval => Complete),
      Claims =>
        (Permission_Five.Claims with delta
         5 => (Permission_Five.Claims (5) with delta
               Kind => Pending_Approval, From => Model_Record,
               Speaker => Assistant)));

   Uncertain_One : constant Checkpoint :=
     (Initial with delta Operations_Count => 1,
      Operations =>
        [1 => (Identity => [others => 8], Action => [others => 9],
               Source_Record_Id => Zero, Result_Record_Id => Zero,
               Stage => Uncertain, Has_Result => False),
         others => Empty_Operation]);

   procedure Uncertain_Properties (Item : Checkpoint)
   with Global => null, Always_Terminates,
     Pre => Item = Uncertain_One,
     Post => Valid (Item) and then Coverage_Ready (Item) and then
       Uncertain_Operations (Item)
   is
   begin
      pragma Assert (Valid_Operations (Item));
      pragma Assert (Valid (Item));
      pragma Assert (Coverage_Ready (Item));
      pragma Assert (Uncertain_Operations (Item));
   end Uncertain_Properties;

   --  Prove the common fixture facts once, then reuse the checked contract.
   --  The body and every call remain part of the complete proof campaign.
   procedure Initial_Properties
   with Global => null, Always_Terminates,
     Post => Valid (Initial) and then Coverage_Ready (Initial) and then
       not Uncertain_Operations (Initial)
   is
   begin
      pragma Assert (Valid (Initial));
      pragma Assert (Coverage_Ready (Initial));
      pragma Assert (not Uncertain_Operations (Initial));
   end Initial_Properties;

   procedure Corrected_Properties (Item : Checkpoint)
   with Global => null, Always_Terminates,
     Pre => Item = Corrected_Six,
     Post => Valid (Item) and then Coverage_Ready (Item) and then
       not Uncertain_Operations (Item)
   is
   begin
      pragma Assert (Valid_Claims (Item));
      pragma Assert (Coverage_Consistent (Item));
      pragma Assert (Valid (Item));
      pragma Assert (Coverage_Ready (Item));
      pragma Assert (not Uncertain_Operations (Item));
   end Corrected_Properties;

   procedure Invalid_Predecessor (Item : Checkpoint; I : Claim_Index)
   with Global => null, Always_Terminates,
     Pre => I <= Item.Count and then not Valid_Predecessor (Item, I),
     Post => not Valid (Item)
   is
   begin
      pragma Assert (not Valid_Claims (Item));
      pragma Assert (not Valid (Item));
   end Invalid_Predecessor;

   procedure Invalid_Sequence (Item : Checkpoint; I : Claim_Index)
   with Global => null, Always_Terminates,
     Pre => I > 1 and then I <= Item.Count and then
       Item.Claims (I).Sequence <= Item.Claims (I - 1).Sequence,
     Post => not Valid (Item)
   is
   begin
      pragma Assert (not Valid_Claims (Item));
      pragma Assert (not Valid (Item));
   end Invalid_Sequence;

   procedure Invalid_Claim (Item : Checkpoint; I : Claim_Index)
   with Global => null, Always_Terminates,
     Pre => I <= Item.Count and then not Valid_Claim (Item.Claims (I)),
     Post => not Valid (Item)
   is
   begin
      pragma Assert (not Valid_Claims (Item));
      pragma Assert (not Valid (Item));
   end Invalid_Claim;

   procedure Permission_Properties (Item : Checkpoint)
   with Global => null, Always_Terminates,
     Pre => Item = Permission_Five,
     Post => Valid (Item) and then Coverage_Ready (Item) and then
       not Uncertain_Operations (Item)
   is
   begin
      pragma Assert (Valid_Claims (Item));
      pragma Assert (Coverage_Consistent (Item));
      pragma Assert (Valid (Item));
      pragma Assert (Coverage_Ready (Item));
      pragma Assert (not Uncertain_Operations (Item));
   end Permission_Properties;

   procedure Pending_Properties (Item : Checkpoint)
   with Global => null, Always_Terminates,
     Pre => Item = Pending_Five,
     Post => Valid (Item) and then Coverage_Ready (Item) and then
       not Uncertain_Operations (Item)
   is
   begin
      pragma Assert (Valid_Claims (Item));
      pragma Assert (Coverage_Consistent (Item));
      pragma Assert (Valid (Item));
      pragma Assert (Coverage_Ready (Item));
      pragma Assert (not Uncertain_Operations (Item));
   end Pending_Properties;

   --  No precondition: partitioning active and padding ranges must preserve
   --  the original predicate for every representable checkpoint.
   procedure Check_Claim_Partition (Item : Checkpoint)
   with Global => null, Always_Terminates
   is
   begin
      pragma Assert
        (Valid_Claims (Item) =
           ((for all I in Claim_Index =>
               (if I <= Item.Count then
                  Valid_Claim (Item.Claims (I)) and then
                  Item.Claims (I).Sequence <= Item.Through and then
                  (if I > 1 then
                     Item.Claims (I - 1).Sequence < Item.Claims (I).Sequence)
                  and then Valid_Predecessor (Item, I)
                else Item.Claims (I) = Empty_Claim)) and then
            (for all I in 1 .. Item.Count =>
               (for all J in 1 .. Item.Count =>
                  (if I /= J then
                     Item.Claims (I).Identity /= Item.Claims (J).Identity)))));
   end Check_Claim_Partition;

   procedure Check_Operation_Partition (Item : Checkpoint)
   with Global => null, Always_Terminates
   is
   begin
      pragma Assert
        (Valid_Operations (Item) =
           ((for all I in Operation_Index =>
               (if I <= Item.Operations_Count then
                  Valid_Operation (Item.Operations (I))
                else Item.Operations (I) = Empty_Operation)) and then
            (for all I in 1 .. Item.Operations_Count =>
               (for all J in 1 .. Item.Operations_Count =>
                  (if I /= J then
                     Item.Operations (I).Identity /=
                       Item.Operations (J).Identity)))));
   end Check_Operation_Partition;

   --  Fixture-supplied observations, deliberately not an authenticity producer.
   function Observe (Item : Checkpoint) return Current_Evidence
   with Global => null, Pre => Item.Epoch /= 0,
     Post => Observe'Result.Scope = Item.Scope and then
       Fresh (Item, Observe'Result) and then Joined (Item, Observe'Result)
   is
   begin
      return
        (Scope => Item.Scope, Checkpoint_Id => Item.Identity,
         Capture => Item.Capture, Epoch => Item.Epoch, Through => Item.Through,
         Retention_Epoch => Item.Retention_Epoch,
         Manifest | Originals =>
           (Present => True, Durable => True,
            Bound_To => (Epoch => Item.Epoch, Transaction => Item.Identity)),
         Claims =>
           [for I in Claim_Index =>
              (State => (if I <= Item.Count then Retained else Unknown),
               Item => Item.Claims (I))],
         Operations =>
           [for I in Operation_Index =>
              (State => (if I <= Item.Operations_Count then Retained else Unknown),
               Item => Item.Operations (I))]);
   end Observe;

   --  Expose the expected decision's conditions at the caller boundary.
   --  Check still proves and executes the original classification assertion.
   function Expected
     (Item : Checkpoint; Current : Current_Evidence; Wanted : Restoration)
      return Boolean is
     (case Wanted is
         when Invalid_Checkpoint => not Valid (Item),
         when Identity_Mismatch =>
           Valid (Item) and then not Same_Task (Item, Current),
         when Stale_Checkpoint =>
           Valid (Item) and then Same_Task (Item, Current) and then
           not Fresh (Item, Current),
         when Need_Evidence =>
           Valid (Item) and then Same_Task (Item, Current) and then
           Fresh (Item, Current) and then
           (not Joined (Item, Current) or else not Coverage_Ready (Item)),
         when Reconcile_Repository =>
           Valid (Item) and then Same_Task (Item, Current) and then
           Fresh (Item, Current) and then Joined (Item, Current) and then
           Coverage_Ready (Item) and then
           (Item.Scope.Revision /= Current.Scope.Revision or else
            Item.Scope.Dirty /= Current.Scope.Dirty),
         when Reconcile_Operations | References_Proposed =>
           Valid (Item) and then Same_Task (Item, Current) and then
           Fresh (Item, Current) and then Joined (Item, Current) and then
           Coverage_Ready (Item) and then
           Item.Scope.Revision = Current.Scope.Revision and then
           Item.Scope.Dirty = Current.Scope.Dirty and then
           (Uncertain_Operations (Item) = (Wanted = Reconcile_Operations)))
   with Global => null;

   procedure Check
     (Item : Checkpoint; Current : Current_Evidence; Wanted : Restoration)
   with Global => null, Always_Terminates,
     Pre => Expected (Item, Current, Wanted)
   is
      Result : constant Restoration := Classify (Item, Current);
   begin
      pragma Assert (Result = Wanted);
   end Check;

   --  Preserve the coherent-observation controls without exposing a fresh
   --  observation array in every caller's proof context.
   procedure Check_Observed (Item : Checkpoint; Wanted : Restoration)
   with Global => null, Always_Terminates,
     Pre => Item.Epoch /= 0 and then
       (case Wanted is
           when Invalid_Checkpoint => not Valid (Item),
           when Need_Evidence =>
             Valid (Item) and then not Coverage_Ready (Item),
           when Reconcile_Operations =>
             Valid (Item) and then Coverage_Ready (Item) and then
             Uncertain_Operations (Item),
           when References_Proposed =>
             Valid (Item) and then Coverage_Ready (Item) and then
             not Uncertain_Operations (Item),
           when others => False)
   is
   begin
      Check (Item, Observe (Item), Wanted);
   end Check_Observed;

   procedure Check_Context_Byte (Item : Checkpoint; Index : Positive)
   with Global => null, Always_Terminates,
     Pre => Index <= 32 and then Item.Epoch /= 0 and then
       Valid (Item) and then Coverage_Ready (Item) and then
       not Uncertain_Operations (Item) and then
       Item.Scope.Task_Id (Index) /= 0 and then
       Item.Scope.Session_Id (Index) /= 0 and then
       Item.Scope.Repository (Index) /= 0 and then
       Item.Scope.Revision (Index) /= 0 and then
       Item.Scope.Dirty (Index) /= 0 and then
       Item.Identity (Index) /= 0 and then Item.Capture (Index) /= 0 and then
       Item.Claims (1).Source_Record_Id (Index) = 0
   is
      Current : Current_Evidence := Observe (Item);
   begin
      Current.Scope.Task_Id (Index) := 0;
      Check (Item, Current, Identity_Mismatch);
      Current := Observe (Item);
      Current.Scope.Session_Id (Index) := 0;
      Check (Item, Current, Identity_Mismatch);
      Current := Observe (Item);
      Current.Scope.Repository (Index) := 0;
      Check (Item, Current, Identity_Mismatch);
      Current := Observe (Item);
      Current.Scope.Revision (Index) := 0;
      Check (Item, Current, Reconcile_Repository);
      Current := Observe (Item);
      Current.Scope.Dirty (Index) := 0;
      Check (Item, Current, Reconcile_Repository);
      Current := Observe (Item);
      Current.Checkpoint_Id (Index) := 0;
      Check (Item, Current, Stale_Checkpoint);
      Current := Observe (Item);
      Current.Capture (Index) := 0;
      Check (Item, Current, Stale_Checkpoint);
      Current := Observe (Item);
      Current.Claims (1).Item.Source_Record_Id (Index) := 1;
      Check (Item, Current, Need_Evidence);
   end Check_Context_Byte;

   procedure Check_Freshness_And_Durability
   with Global => null, Always_Terminates
   is
      Current : Current_Evidence := Observe (Initial);
   begin
      Initial_Properties;
      Check (Initial, Current, References_Proposed);
      Current.Epoch := 2;
      Check (Initial, Current, Stale_Checkpoint);
      Current := Observe (Initial);
      Current.Through := 5;
      Check (Initial, Current, Stale_Checkpoint);
      Current := Observe (Initial);
      Current.Retention_Epoch := 2;
      Check (Initial, Current, Stale_Checkpoint);
      Current := Observe (Initial);
      Current.Manifest.Durable := False;
      Check (Initial, Current, Need_Evidence);
      Current := Observe (Initial);
      Current.Originals.Present := False;
      Check (Initial, Current, Need_Evidence);
      Current := Observe (Initial);
      Current.Originals.Bound_To.Transaction := Zero;
      Check (Initial, Current, Need_Evidence);
      Current := Observe (Initial);
      Current.Manifest.Bound_To.Epoch := 2;
      Check (Initial, Current, Need_Evidence);
   end Check_Freshness_And_Durability;

   procedure Check_Gaps with Global => null, Always_Terminates is
      Item : Checkpoint := Initial;
      Current : Current_Evidence := Observe (Initial);
   begin
      Initial_Properties;
      Item.Coverage (Goal) := Partial;
      Check (Item, Current, Need_Evidence);
      Item := Initial;
      Item.Coverage (Constraint) := SIA_Continuity.Not_Observed;
      Check (Item, Current, Need_Evidence);
      Item.Coverage (Constraint) := SIA_Continuity.Unavailable;
      Check (Item, Current, Need_Evidence);
      Item := Initial;
      Item.Coverage (Goal) := SIA_Continuity.Observed_Empty;
      Check (Item, Current, Invalid_Checkpoint);
      Item := Initial;
      for State in Availability loop
         Current.Claims (1).State := State;
         if State = Retained then
            Check (Item, Current, References_Proposed);
         else
            Check (Item, Current, Need_Evidence);
         end if;
      end loop;
      Current := Observe (Initial);
      Current.Claims (Max_Claims).State := Retained;
      Check (Item, Current, Need_Evidence);
   end Check_Gaps;

   procedure Check_Supersession with Global => null, Always_Terminates is
      Item : Checkpoint := Initial;
      Current : Current_Evidence;
   begin
      Initial_Properties;
      Item.Count := 5;
      Item.Through := 6;
      Item.Claims (5) := Item.Claims (1);
      Item.Claims (5).Identity := [others => 5];
      Item.Claims (5).Sequence := 5;
      Item.Claims (5).Replaces := 1;
      pragma Assert (Valid_Claims (Item));
      pragma Assert (Valid (Item));
      Current := Observe (Item);
      Check (Item, Current, References_Proposed);
      Item.Claims (5).Replaces := 0;
      pragma Assert (not Valid_Predecessor (Item, 5));
      Invalid_Predecessor (Item, 5);
      Check (Item, Current, Invalid_Checkpoint);
      Item.Claims (5).Replaces := 5;
      pragma Assert (not Valid_Predecessor (Item, 5));
      Invalid_Predecessor (Item, 5);
      Check (Item, Current, Invalid_Checkpoint);
      Item.Claims (5).Replaces := 1;
      Item.Claims (5).Speaker := Tool;
      pragma Assert (not Valid_Predecessor (Item, 5));
      Invalid_Predecessor (Item, 5);
      Check (Item, Current, Invalid_Checkpoint);
      Item.Claims (5).Speaker := User;
      Item.Count := 6;
      Item.Claims (6) := Item.Claims (5);
      Item.Claims (6).Identity := [others => 6];
      Item.Claims (6).Sequence := 6;
      pragma Assert (not Valid_Predecessor (Item, 6));
      Invalid_Predecessor (Item, 6);
      Check_Observed (Item, Invalid_Checkpoint);
      Item.Claims (6).Replaces := 5;
      pragma Assert_And_Cut (Item = Corrected_Six);
      Corrected_Properties (Item);
      pragma Assert (Valid_Claims (Item));
      pragma Assert (Valid (Item));
      Check_Observed (Item, References_Proposed);
      Item.Claims (6).Sequence := 5;
      pragma Assert_And_Cut
        (Item.Count = 6 and then Item.Epoch /= 0 and then
         Item.Claims (6).Sequence = Item.Claims (5).Sequence);
      pragma Assert (not Valid_Claims (Item));
      Invalid_Sequence (Item, 6);
      Check_Observed (Item, Invalid_Checkpoint);
   end Check_Supersession;

   procedure Check_Permission_Origin with Global => null, Always_Terminates is
      Item : Checkpoint := Initial;
   begin
      Initial_Properties;
      Item.Count := 5;
      Item.Through := 5;
      Item.Coverage (Permission_Reference) := Complete;
      Item.Claims (5) :=
        (Identity => [others => 5], Slot => [others => 5],
         Source_Record_Id => [others => 5], Sequence => 5,
         Kind => Permission_Reference, From => Source_Record,
         Speaker => User, Replaces => 0);
      pragma Assert_And_Cut (Item = Permission_Five);
      Permission_Properties (Item);
      Check_Observed (Item, References_Proposed);
      Item.Claims (5).From := Model_Record;
      Invalid_Claim (Item, 5);
      Check_Observed (Item, Invalid_Checkpoint);
      Item.Claims (5).Speaker := Assistant;
      Invalid_Claim (Item, 5);
      Check_Observed (Item, Invalid_Checkpoint);
      Item.Claims (5).Kind := Pending_Approval;
      Item.Coverage (Permission_Reference) := SIA_Continuity.Observed_Empty;
      Item.Coverage (Pending_Approval) := Complete;
      pragma Assert_And_Cut (Item = Pending_Five);
      Pending_Properties (Item);
      Check_Observed (Item, References_Proposed);
      Item.Claims (5).From := Source_Record;
      Invalid_Claim (Item, 5);
      Check_Observed (Item, Invalid_Checkpoint);
   end Check_Permission_Origin;

   procedure Check_Operations with Global => null, Always_Terminates is
      Item : Checkpoint := Initial;
      Current : Current_Evidence;
   begin
      Initial_Properties;
      Item.Operations_Count := 1;
      Item.Operations (1) :=
        (Identity => [others => 8], Action => [others => 9],
         Source_Record_Id => Zero, Result_Record_Id => Zero,
         Stage => Planned, Has_Result => False);
      for Stage in Operation_Phase loop
         Item.Operations (1).Stage := Stage;
         Item.Operations (1).Has_Result :=
           Stage in Observed_Complete | Acknowledged;
         if Stage in Dispatched | Uncertain then
            Check_Observed (Item, Reconcile_Operations);
         else
            Check_Observed (Item, References_Proposed);
         end if;
      end loop;
      Item.Operations (1).Stage := Observed_Complete;
      Item.Operations (1).Has_Result := False;
      Check_Observed (Item, Invalid_Checkpoint);
      Item.Operations (1).Stage := Uncertain;
      pragma Assert_And_Cut (Item = Uncertain_One);
      Uncertain_Properties (Item);
      Current := Observe (Item);
      Current.Operations (1).Item.Stage := Planned;
      Check (Item, Current, Need_Evidence);
      Current := Observe (Item);
      Current.Scope.Dirty := Zero;
      Check (Item, Current, Reconcile_Repository);
      Item.Operations_Count := 0;
      Check (Item, Current, Invalid_Checkpoint);
   end Check_Operations;

   procedure Check_Empty_And_Identity
   with Global => null, Always_Terminates
   is
      Item : Checkpoint := Initial;
   begin
      Initial_Properties;
      Item.Count := 0;
      Item.Claims := [others => Empty_Claim];
      Item.Coverage := [others => SIA_Continuity.Observed_Empty];
      Check_Observed (Item, Need_Evidence);
      Item := Initial;
      Item.Claims (Max_Claims) := Item.Claims (1);
      Check_Observed (Item, Invalid_Checkpoint);
      Item := Initial;
      Item.Claims (2).Identity := Item.Claims (1).Identity;
      Check_Observed (Item, Invalid_Checkpoint);
      Item := Initial;
      Item.Claims (1).Identity := Zero;
      Check_Observed (Item, Invalid_Checkpoint);
      Item := Initial;
      Item.Claims (1).Slot := Zero;
      Check_Observed (Item, Invalid_Checkpoint);
      Item := Initial;
      Item.Claims (1).Sequence := 0;
      Check_Observed (Item, Invalid_Checkpoint);
      Item := Initial;
      Item.Through := 3;
      Check_Observed (Item, Invalid_Checkpoint);
      Item := Initial;
      Item.Previous := Item.Identity;
      Check_Observed (Item, Invalid_Checkpoint);
      Item.Epoch := 2;
      Check_Observed (Item, Invalid_Checkpoint);
      Item.Previous := [others => 9];
      Check_Observed (Item, References_Proposed);
      Item.Epoch := Generation'Last;
      Item.Through := Generation'Last;
      Item.Retention_Epoch := Generation'Last;
      Check_Observed (Item, References_Proposed);
      Item.Previous := Zero;
      Check_Observed (Item, Invalid_Checkpoint);
      Item := Initial;
      Item.Epoch := 0;
      Check (Item, Observe (Initial), Invalid_Checkpoint);
   end Check_Empty_And_Identity;

   function Capacity_Claim (I : Claim_Index) return Claim is
     (if I <= 4 then Initial.Claims (I) else
         (Identity => [others => Digest_Byte (I)],
          Slot => [others => Digest_Byte (I)],
          Source_Record_Id => Zero, Sequence => Generation (I),
          Kind => Constraint, From => Source_Record,
          Speaker => User, Replaces => 0))
   with Global => null;

   procedure Check_Claim_Capacity
   with Global => null, Always_Terminates
   is
      Item : Checkpoint := Initial;
   begin
      Item.Count := Max_Claims;
      Item.Through := Generation (Max_Claims);
      Item.Coverage (Constraint) := Complete;
      for I in 5 .. Max_Claims loop
         Item.Claims := (Item.Claims with delta I => Capacity_Claim (I));
         pragma Loop_Invariant
           (for all J in Claim_Index =>
              Item.Claims (J) =
                (if J <= I then Capacity_Claim (J) else Empty_Claim));
      end loop;
      pragma Assert
        (for all I in Claim_Index =>
           Item.Claims (I).Identity (1) = Digest_Byte (I) and then
           Item.Claims (I).Slot (1) = Digest_Byte (I));
      pragma Assert
        (for all I in Claim_Index =>
           (for all J in Claim_Index =>
              (if I /= J then
                 Item.Claims (I).Identity (1) /= Item.Claims (J).Identity (1)
                 and then Item.Claims (I).Slot (1) /= Item.Claims (J).Slot (1))));
      pragma Assert
        (for all I in Claim_Index => Valid_Predecessor (Item, I));
      pragma Assert (Valid_Claims (Item));
      pragma Assert (Coverage_Consistent (Item));
      pragma Assert (Coverage_Ready (Item));
      pragma Assert (Valid (Item));
      Check_Observed (Item, References_Proposed);
      Item.Claims (Max_Claims).Sequence := Item.Claims (Max_Claims - 1).Sequence;
      pragma Assert_And_Cut
        (Item.Count = Max_Claims and then Item.Epoch /= 0 and then
         Item.Claims (Max_Claims).Sequence =
           Item.Claims (Max_Claims - 1).Sequence);
      pragma Assert (not Valid_Claims (Item));
      Check_Observed (Item, Invalid_Checkpoint);
   end Check_Claim_Capacity;

   function Capacity_Operation (I : Operation_Index) return Operation is
     (Identity => [others => Digest_Byte (I)],
      Action => [others => Digest_Byte (I)],
      Source_Record_Id => Zero, Result_Record_Id => Zero,
      Stage => Acknowledged, Has_Result => True)
   with Global => null;

   procedure Check_Operation_Capacity
   with Global => null, Always_Terminates
   is
      Item : Checkpoint := Initial;
      Current : Current_Evidence;
   begin
      Initial_Properties;
      Item.Operations_Count := Max_Operations;
      for I in Operation_Index loop
         Item.Operations :=
           (Item.Operations with delta I => Capacity_Operation (I));
         pragma Loop_Invariant
           (for all J in Operation_Index =>
              Item.Operations (J) =
                (if J <= I then Capacity_Operation (J) else Empty_Operation));
      end loop;
      pragma Assert
        (for all I in Operation_Index =>
           Item.Operations (I).Identity (1) = Digest_Byte (I));
      pragma Assert
        (for all I in Operation_Index =>
           (for all J in Operation_Index =>
              (if I /= J then
                 Item.Operations (I).Identity (1) /=
                   Item.Operations (J).Identity (1))));
      pragma Assert (Valid_Operations (Item));
      pragma Assert (Valid (Item));
      Check_Observed (Item, References_Proposed);
      Current := Observe (Item);
      Current.Operations (Max_Operations).State := Retracted;
      Check (Item, Current, Need_Evidence);
      Item.Operations (Max_Operations).Stage := Dispatched;
      Check_Observed (Item, Reconcile_Operations);
      Item.Operations (Max_Operations).Identity := Item.Operations (1).Identity;
      Check_Observed (Item, Invalid_Checkpoint);
      Item := Initial;
      Item.Operations_Count := 1;
      Item.Operations (1) :=
        (Identity => [others => 1], Action => [others => 1],
         Source_Record_Id => Zero, Result_Record_Id => [others => 1],
         Stage => Planned, Has_Result => False);
      Check_Observed (Item, Invalid_Checkpoint);
      Item.Operations (1).Has_Result := True;
      Check_Observed (Item, Invalid_Checkpoint);
      Item.Operations (1).Stage := Observed_Complete;
      Item.Operations (1).Action := Zero;
      Check_Observed (Item, Invalid_Checkpoint);
   end Check_Operation_Capacity;
begin
   Check_Claim_Partition (Initial);
   Check_Operation_Partition (Initial);
   Check_Freshness_And_Durability;
   Check_Gaps;
   Check_Supersession;
   Check_Permission_Origin;
   Check_Operations;
   Check_Empty_And_Identity;
   Check_Claim_Capacity;
   Check_Operation_Capacity;
   Initial_Properties;
   for Index in 1 .. 32 loop
      Check_Context_Byte (Initial, Index);
   end loop;
end Continuity_Tests;
