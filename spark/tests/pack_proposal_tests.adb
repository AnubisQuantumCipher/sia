with Ada.Text_IO;
with SIA_Policy;
with SIA_Pack_Retirement;
with SIA_Pack_Manifest_Wire;
with SIA_Pack_Partition;
with SIA_Pack_Plan_Wire;
with SIA_Pack_Proposal;
with Pack_Plan_Wire_Test_Support;

procedure Pack_Proposal_Tests with SPARK_Mode => Off is
   use SIA_Policy;
   use SIA_Pack_Retirement;
   use SIA_Pack_Manifest_Wire;
   package Gate renames SIA_Pack_Proposal;
   package Join renames SIA_Pack_Partition;
   use type Join.Partition_State;
   Checks : Natural := 0;
   procedure Check (Condition : Boolean; Label_Text : String) is
   begin
      Checks := Checks + 1;
      if not Condition then
         raise Program_Error with Label_Text;
      end if;
   end Check;

   function Reference (Key : Natural) return Record_Reference is
      Result : Record_Reference := (Zero, [others => 173], 1);
      Remaining : Natural := Key;
   begin
      for I in reverse Digest'Range loop
         Result.Identity (I) := Digest_Byte (Remaining mod 256);
         Remaining := Remaining / 256;
      end loop;
      Check (Remaining = 0, "identity exhausted");
      return Result;
   end Reference;

   function Head (Count : Natural) return Header is
      Result : Header := [others => 0];
      Remaining : Natural := Count;
      Tag : constant String := "SIA-PACK-RECORDS-v1" & ASCII.NUL;
   begin
      for I in Tag'Range loop
         Result (I) := Character'Pos (Tag (I));
      end loop;
      for I in reverse 21 .. 28 loop
         Result (I) := Digest_Byte (Remaining mod 256);
         Remaining := Remaining / 256;
      end loop;
      Check (Remaining = 0, "header exhausted");
      return Result;
   end Head;

   function Encode (Value : Record_Reference) return Record_Bytes is
      Result : Record_Bytes := [others => 0];
      Remaining : Natural := Value.Bytes;
   begin
      for I in Digest'Range loop
         Result (I) := Value.Identity (I);
         Result (I + 32) := Value.Content (I);
      end loop;
      for I in reverse 65 .. 72 loop
         Result (I) := Digest_Byte (Remaining mod 256);
         Remaining := Remaining / 256;
      end loop;
      Check (Remaining = 0, "payload count exhausted");
      return Result;
   end Encode;

   function Candidate (Count : Input_Count; Packed : Record_Count) return Plan is
      Result : Plan := Empty_Plan;
   begin
      Check (Count >= Packed, "fixture count domain");
      Result.Scope.Transaction.Epoch := 1;
      Result.Selected := Count;
      Result.Fallback_Count := Count - Packed;
      if Packed = 0 then
         Result.Prior.Count := 1;
         Result.Prior.Records (1) := Reference (0);
         Result.Target := Result.Prior;
      else
         Result.Represented.Count := Packed;
         for I in 1 .. Packed loop
            Result.Represented.Records (I) := Reference (I);
            Result.Legacy_Present (I) := True;
         end loop;
         Result.Target := Result.Represented;
      end if;
      Check (Valid_Retirement_Plan (Result), "fixture retirement valid");
      return Result;
   end Candidate;

   procedure Full_Trace (Count : Input_Count; Packed : Record_Count) is
      Original : constant Plan := Candidate (Count, Packed);
      Data : constant SIA_Pack_Plan_Wire.Frame := Pack_Plan_Wire_Test_Support.Encode_Oracle (Original);
      Decoded, Value : Plan;
      Item : Gate.State;
      Good : Boolean;
      R : Record_Bytes;
   begin
      SIA_Pack_Plan_Wire.Decode (Data, Data'Length, Good, Decoded);
      Check (Good and then Decoded = Original, "actual proposal decoder correspondence");
      Gate.Start (Decoded, Head (Count), Head (Count - Packed), 28, 28, Item);
      Check (Gate.Running (Item), "composed start");
      for I in 1 .. Count loop
         R := Encode (Reference (I));
         Gate.Take (Item, R, R, 72, (if I <= Packed then 0 else 72), Good);
         Check (Good, "complete maximum-domain stream");
      end loop;
      Gate.Finish (Item, 0, 0, Good, Value);
      Check (Good and then Gate.Complete (Item) and then Value = Original, "complete exact plan result");
      Gate.Finish (Item, 0, 0, Good, Value);
      Check (not Good and then Value = Empty_Plan, "completion cannot be reused");
   end Full_Trace;

   procedure Target_Overlap is
      P : Plan := Candidate (1, 0);
      Item : Gate.State;
      Prefix : Join.Partition_State;
      Good : Boolean;
      Value : Plan;
      Record_Value : Record_Reference;
      R : Record_Bytes;
   begin
      P.Prior.Count := Max_Records;
      for I in Record_Index loop
         P.Prior.Records (I) := Reference (I - 1);
      end loop;
      P.Target := P.Prior;
      for I in Record_Index loop
         Gate.Start (P, Head (1), Head (1), 28, 28, Item);
         Check (Gate.Running (Item), "full prior start");
         Prefix := Gate.Streams (Item);
         Record_Value := P.Target.Records (I);
         R := Encode (Record_Value);
         Gate.Take (Item, R, R, 72, 72, Good);
         Check (not Good and then Gate.Streams (Item) = Prefix, "fallback target identity refuses");
         Gate.Finish (Item, 0, 0, Good, Value);
         Check (not Good and then Value = Empty_Plan, "overlap cannot publish result");
         Record_Value.Content (1) := Record_Value.Content (1) xor 1;
         R := Encode (Record_Value);
         Gate.Start (P, Head (1), Head (1), 28, 28, Item);
         Gate.Take (Item, R, R, 72, 72, Good);
         Check (not Good, "conflicting same-identity fallback also refuses");
      end loop;
   end Target_Overlap;

   procedure Failure_States is
      P : Plan := Candidate (2, 1);
      Item : Gate.State;
      Value : Plan;
      Good : Boolean;
      Prefix : Join.Partition_State;
      R : constant Record_Bytes := Encode (Reference (1));
   begin
      Gate.Finish (Item, 0, 0, Good, Value);
      Check (not Good and then Value = Empty_Plan, "default refuses");
      Gate.Start (P, Head (3), Head (2), 28, 28, Item);
      Check (Gate.Refused (Item) and then Gate.Proposal (Item) = Empty_Plan,
             "balanced manifests cannot replace plan counts");
      Gate.Start (P, Head (2), Head (1), 27, 28, Item);
      Check (Gate.Refused (Item), "short header refuses");
      Gate.Start (P, Head (2), Head (1), 28, Natural'Last, Item);
      Check (Gate.Refused (Item), "long header refuses");
      Gate.Start (P, Head (2), Head (1), 28, 28, Item);
      Gate.Take (Item, R, R, 72, 0, Good);
      Check (Good, "represented prefix accepted");
      Prefix := Gate.Streams (Item);
      Gate.Take (Item, R, R, 72, 72, Good);
      Check (not Good and then Gate.Refused (Item) and then Gate.Streams (Item) = Prefix,
             "duplicate preserves prefix and refuses");
      Gate.Take (Item, Encode (Reference (2)), Encode (Reference (2)), 72, 72, Good);
      Check (not Good and then Gate.Streams (Item) = Prefix, "failure sticky");
      Gate.Finish (Item, 0, 0, Good, Value);
      Check (not Good and then Value = Empty_Plan, "failed stream cannot yield proposal");
      Gate.Start (P, Head (2), Head (1), 28, 28, Item);
      Gate.Take (Item, R, R, 72, 0, Good);
      Check (Good, "new prefix accepted");
      Gate.Finish (Item, 0, 0, Good, Value);
      Check (not Good and then Value = Empty_Plan, "early finish refuses");
      P.Scope.Transaction.Epoch := 0;
      Gate.Start (P, Head (2), Head (1), 28, 28, Item);
      Check (Gate.Refused (Item), "invalid decoded plan refuses");
   end Failure_States;

   procedure Composition_Counterexample is
      P : constant Plan := Candidate (1, 0);
      R : constant Record_Bytes := Encode (P.Target.Records (1));
      Joined : Join.Partition_State;
      Item : Gate.State;
      Kind : Join.Step_Kind;
      Record_Value : Record_Reference;
      Value : Plan;
      Good : Boolean;
      use type Join.Step_Kind;
   begin
      Join.Start (Head (1), Head (1), 28, 28, Empty_Roster, Joined);
      Join.Take (Joined, R, R, 72, 72, Kind, Record_Value);
      Check (Kind = Join.Fallback_Record and then Record_Value = P.Target.Records (1),
             "standalone partition has no target knowledge");
      Join.Finish (Joined, 0, 0, Good);
      Check (Good, "standalone valid partition can overlap target");
      Gate.Start (P, Head (1), Head (1), 28, 28, Item);
      Gate.Take (Item, R, R, 72, 72, Good);
      Check (not Good, "composed target exclusion rejects same input");
      Gate.Finish (Item, 0, 0, Good, Value);
      Check (not Good and then Value = Empty_Plan, "counterexample cannot yield admitted plan");
   end Composition_Counterexample;

   procedure Trailing_Refusals is
      P : constant Plan := Candidate (1, 1);
      R : constant Record_Bytes := Encode (Reference (1));
      Item : Gate.State;
      Value : Plan;
      Good : Boolean;
   begin
      for Side in 0 .. 1 loop
         Gate.Start (P, Head (1), Head (0), 28, 28, Item);
         Gate.Take (Item, R, R, 72, 0, Good);
         Check (Good, "complete body before trailing data");
         Gate.Finish (Item, Side, 1 - Side, Good, Value);
         Check (not Good and then Value = Empty_Plan, "either trailing stream refuses");
      end loop;
   end Trailing_Refusals;
begin
   Full_Trace (0, 0);
   Full_Trace (1, 1);
   --  Safe exact coverage need not be the producer's greedy packing choice.
   Full_Trace (2, 1);
   Full_Trace (Max_Records, Max_Records);
   Full_Trace (Max_Inputs, Max_Records);
   Full_Trace (Max_Inputs, 0);
   Target_Overlap;
   Failure_States;
   Composition_Counterexample;
   Trailing_Refusals;
   Ada.Text_IO.Put_Line ("pack proposal controls PASS" & Checks'Image);
end Pack_Proposal_Tests;
