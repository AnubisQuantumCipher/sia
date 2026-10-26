with Ada.Text_IO;
with SIA_Policy;
with SIA_Pack_Retirement;
package body Pack_Retirement_Test_Support is
   use SIA_Policy;
   use SIA_Pack_Retirement;
   Checks : Natural := 0;
   Execution : constant Digest := [others => 71];

   procedure Check (Condition : Boolean; Label_Text : String) is
   begin
      if not Condition then
         raise Program_Error with Label_Text;
      end if;
      Checks := Checks + 1;
   end Check;

   function Record_For (Value : Digest_Byte) return Record_Reference is
     ((Identity => [others => Value], Content => [others => Value + 17], Bytes => 1));

   function Fixture return Plan is
      Item : Plan := Empty_Plan;
   begin
      Item.Scope := ((7, [others => 1]), [others => 2], [others => 3],
                     [others => 4], [others => 5], [others => 6],
                     [others => 7], [others => 8], [others => 9],
                     [others => 10], [others => 11]);
      Item.Identity := [others => 12];
      Item.Selected := 4;
      Item.Fallback_Count := 1;
      Item.Prior.Count := 1;
      Item.Prior.Records (1) := Record_For (0);
      Item.Target.Count := 3;
      for I in 1 .. 3 loop
         Item.Target.Records (I) := Record_For (Digest_Byte (I - 1));
         Item.Legacy_Generation (I) := [others => Digest_Byte (I + 20)];
      end loop;
      Item.Represented := Item.Target;
      Item.Legacy_Present (2 .. 3) := [others => True];
      return Item;
   end Fixture;

   function Observe (Item : Plan; Slot : Record_Index) return Observation is
      Seen : Observation := Empty_Observation;
   begin
      Seen.Scope := Item.Scope;
      Seen.Plan_Id := Item.Identity;
      Seen.Execution := Execution;
      Seen.Target := Item.Target;
      --  Independent fixture: header 59 bytes, three 69-byte records.
      Seen.Frame_Bytes := 266;
      Seen.Intent := (True, True, (7, Item.Identity));
      Seen.File_Sync := (True, True, (7, Item.Scope.New_Target));
      Seen.Parent_Sync := Seen.File_Sync;
      Seen.Readback := Seen.File_Sync;
      Seen.Selection := (True, True, (7, Item.Scope.Selection));
      Seen.Legacy := Exact_Present;
      Seen.Original := Item.Represented.Records (Slot);
      Seen.Original_Generation := Item.Legacy_Generation (Slot);
      return Seen;
   end Observe;

   function Receipt (Item : Plan; Slot : Record_Index) return Retirement_Receipt is
     ((Item.Scope, Item.Identity, [others => 42], Slot,
       Item.Represented.Records (Slot), Item.Legacy_Generation (Slot),
       (True, True, (7, [others => 42]))));

   procedure Lifecycle is
      Item : constant Plan := Fixture;
      Seen : Observation := Observe (Item, 2);
   begin
      Check (Classify (Item, Seen, Execution, 2) = Unlink_Proposed, "present");
      Seen.Legacy := Absent;
      Check (Classify (Item, Seen, Execution, 2) = Refused, "unexplained absence");
      Seen.Retired := Receipt (Item, 2);
      Check (Classify (Item, Seen, Execution, 2) = Retirement_Recorded, "retired");
      Seen.Legacy := Exact_Present;
      Check (Classify (Item, Seen, Execution, 2) = Refused, "resurrection");
      Seen := Observe (Item, 1);
      Seen.Legacy := Absent;
      Check (Classify (Item, Seen, Execution, 1) = Originally_Absent, "prior absence");
      Seen.Legacy := Exact_Present;
      Check (Classify (Item, Seen, Execution, 1) = Refused, "unexpected presence");
      Seen := Observe (Item, 2);
      for State in Legacy_State loop
         if State = Unobserved or State = Conflicting then
            Seen.Legacy := State;
            Check (Classify (Item, Seen, Execution, 2) = Refused, "bad legacy state");
         end if;
      end loop;
      Seen := Observe (Item, 2);
      Check (Classify (Item, Seen, Execution, 3) = Refused, "wrong slot");
      Check (Classify (Item, Seen, Execution, 64) = Refused, "padding slot");
   end Lifecycle;

   procedure Change_Context (Scope : in out Context; Field : Positive) is
   begin
      case Field is
         when 1 => Scope.Transaction.Epoch := 8;
         when 2 => Scope.Transaction.Transaction (1) := 90;
         when 3 => Scope.Corpus (1) := 90;
         when 4 => Scope.Organ (1) := 90;
         when 5 => Scope.Prefix (1) := 90;
         when 6 => Scope.Revision (1) := 90;
         when 7 => Scope.Capture (1) := 90;
         when 8 => Scope.Selection (1) := 90;
         when 9 => Scope.Fallback (1) := 90;
         when 10 => Scope.Old_Target (1) := 90;
         when 11 => Scope.New_Target (1) := 90;
         when 12 => Scope.Permission (1) := 90;
         when others => raise Program_Error with "context test selector";
      end case;
   end Change_Context;

   procedure Context_Controls is
      Item : constant Plan := Fixture;
      Seen : Observation;
   begin
      for Field in 1 .. 12 loop
         Seen := Observe (Item, 2);
         Change_Context (Seen.Scope, Field);
         Check (Classify (Item, Seen, Execution, 2) = Refused, "scope mismatch");
         Seen := Observe (Item, 2);
         Seen.Legacy := Absent;
         Seen.Retired := Receipt (Item, 2);
         Change_Context (Seen.Retired.Scope, Field);
         Check (Classify (Item, Seen, Execution, 2) = Refused, "receipt scope mismatch");
      end loop;
   end Context_Controls;

   procedure Corrupt_Witness (Value : in out Witness; Field : Positive) is
   begin
      case Field is
         when 1 => Value.Present := False;
         when 2 => Value.Durable := False;
         when 3 => Value.Bound_To.Epoch := 8;
         when 4 => Value.Bound_To.Transaction (32) := 99;
         when others => raise Program_Error with "witness test selector";
      end case;
   end Corrupt_Witness;

   procedure Witness_Controls is
      Item : constant Plan := Fixture;
      Seen : Observation;
   begin
      for Field in 1 .. 4 loop
         for Subject in 1 .. 6 loop
            Seen := Observe (Item, 2);
            case Subject is
               when 1 => Corrupt_Witness (Seen.Intent, Field);
               when 2 => Corrupt_Witness (Seen.File_Sync, Field);
               when 3 => Corrupt_Witness (Seen.Parent_Sync, Field);
               when 4 => Corrupt_Witness (Seen.Readback, Field);
               when 5 => Corrupt_Witness (Seen.Selection, Field);
               when 6 =>
                  Seen.Legacy := Absent;
                  Seen.Retired := Receipt (Item, 2);
                  Corrupt_Witness (Seen.Retired.Custody, Field);
            end case;
            Check (Classify (Item, Seen, Execution, 2) = Refused, "bad witness");
         end loop;
      end loop;
   end Witness_Controls;

   procedure Substitutions is
      Item : constant Plan := Fixture;
      Seen : Observation;
   begin
      for Field in 1 .. 13 loop
         Seen := Observe (Item, 2);
         Seen.Legacy := Absent;
         Seen.Retired := Receipt (Item, 2);
         case Field is
            when 1 => Seen.Plan_Id (1) := 99;
            when 2 => Seen.Execution (1) := 99;
            when 3 => Seen.Target.Records (1).Content (1) := 99;
            when 4 => Seen.Frame_Bytes := 264;
            when 5 => Seen.Original.Identity (1) := 99;
            when 6 => Seen.Original.Content (1) := 99;
            when 7 => Seen.Original_Generation (1) := 99;
            when 8 => Seen.Retired.Plan_Id (1) := 99;
            when 9 => Seen.Retired.Identity (1) := 99;
            when 10 => Seen.Retired.Slot := 3;
            when 11 => Seen.Retired.Original.Identity (1) := 99;
            when 12 => Seen.Retired.Original.Content (1) := 99;
            when 13 => Seen.Retired.Original_Generation (1) := 99;
         end case;
         Check (Classify (Item, Seen, Execution, 2) = Refused, "substitution");
      end loop;
   end Substitutions;

   procedure Invalid_Plans is
      Item : Plan;
   begin
      for Field in 1 .. 12 loop
         Item := Fixture;
         case Field is
            when 1 => Item.Scope.Transaction.Epoch := 0;
            when 2 => Item.Selected := 65_536;
            when 3 => Item.Fallback_Count := 65_536;
            when 4 => Item.Target := Empty_Roster;
            when 5 => Item.Target.Records (1) := Record_For (3);
            when 6 => Item.Target.Records (2) := Item.Target.Records (1);
            when 7 => Item.Target.Records (1).Content (1) := 99;
            when 8 => Item.Target.Records (1).Bytes := 0;
            when 9 => Item.Target.Records (64) := Record_For (5);
            when 10 => Item.Legacy_Present (64) := True;
            when 11 => Item.Legacy_Generation (64) (1) := 99;
            when 12 => Item.Legacy_Present (2) := False;
         end case;
         Check (not Valid_Retirement_Plan (Item), "invalid plan");
      end loop;
      Item := Fixture;
      Item.Target.Records (1) := Record_For (1);
      Item.Target.Records (2) := Record_For (0);
      Check (not Valid_Retirement_Plan (Item), "permuted exact union");
      Item := Fixture;
      Item.Represented.Records (2) := Record_For (0);
      Check (not Valid_Retirement_Plan (Item), "represented duplicate");
   end Invalid_Plans;

   procedure Size_And_Capacity is
      Item : Plan := Fixture;
   begin
      Check (Encoded_Size (Item.Target, 1) = 266, "fixture encoding size");
      Item.Prior := Empty_Roster;
      Item.Target := Empty_Roster;
      Item.Target.Count := 64;
      for I in Record_Index loop
         Item.Target.Records (I) := Record_For (Digest_Byte (I - 1));
      end loop;
      Item.Represented := Item.Target;
      Item.Legacy_Present := [others => True];
      Item.Selected := 65_536;
      Item.Fallback_Count := 65_472;
      Check (Valid_Retirement_Plan (Item), "full roster and input domain");
      Check (Encoded_Size (Item.Target, 200) = 4_674, "maximum organ size");
      Item.Target.Records (64).Bytes := 61_062;
      Item.Represented := Item.Target;
      Check (Encoded_Size (Item.Target, 1) = 65_536, "exact frame ceiling");
      Check (Valid_Retirement_Plan (Item), "frame ceiling admitted");
      Item.Target.Records (64).Bytes := 61_063;
      Item.Represented := Item.Target;
      Check (not Valid_Retirement_Plan (Item), "frame ceiling overflow");
      Item.Target.Records (64).Bytes := 65_536;
      Check (Encoded_Size (Item.Target, 1) = 70_010, "logical sum wider than frame");
   end Size_And_Capacity;

   procedure Lexicographic_Controls is
      Lower_Value, Higher_Value : Digest;
   begin
      for I in Digest'Range loop
         Lower_Value := [others => 0];
         Higher_Value := [others => 0];
         Lower_Value (I) := 1;
         Higher_Value (I) := 2;
         if I < Digest'Last then
            Lower_Value (I + 1) := 255;
         end if;
         Check (Before (Lower_Value, Higher_Value), "first unequal byte decides");
         Check (not Before (Higher_Value, Lower_Value), "later byte cannot reverse order");
         Check (not Before (Lower_Value, Lower_Value), "strict order excludes equality");
      end loop;
   end Lexicographic_Controls;

   procedure Run is
   begin
      Lifecycle;
      Context_Controls;
      Witness_Controls;
      Substitutions;
      Invalid_Plans;
      Size_And_Capacity;
      Lexicographic_Controls;
      Ada.Text_IO.Put_Line ("pack retirement runtime controls PASS:" & Checks'Image);
   end Run;
end Pack_Retirement_Test_Support;
