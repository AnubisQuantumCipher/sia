with Ada.Text_IO;
with SIA_Policy;
with SIA_Pack_Retirement;
with SIA_Pack_Manifest_Wire;
with SIA_Pack_Partition;

procedure Pack_Manifest_Tests with SPARK_Mode => Off is
   use SIA_Policy;
   use SIA_Pack_Retirement;
   use SIA_Pack_Manifest_Wire;
   package Join renames SIA_Pack_Partition;
   use type Join.Step_Kind;
   Checks : Natural := 0;

   procedure Check (Condition : Boolean; Label_Text : String) is
   begin
      Checks := Checks + 1;
      if not Condition then
         raise Program_Error with Label_Text;
      end if;
   end Check;

   function Head (Count : Natural) return Header is
      Result : Header := [others => 0];
      Remaining : Natural := Count;
   begin
      for I in SIA_Pack_Manifest_Wire.Magic'Range loop
         Result (I) := Character'Pos (SIA_Pack_Manifest_Wire.Magic (I));
      end loop;
      for I in reverse 21 .. 28 loop
         Result (I) := Digest_Byte (Remaining mod 256);
         Remaining := Remaining / 256;
      end loop;
      Check (Remaining = 0, "header integer exhausted");
      return Result;
   end Head;

   function Reference (Key : Natural; Size : Byte_Count := 1) return Record_Reference is
      Result : Record_Reference := (Identity => Zero, Content => [others => 173], Bytes => Size);
      Remaining : Natural := Key;
   begin
      for I in reverse Digest'Range loop
         Result.Identity (I) := Digest_Byte (Remaining mod 256);
         Remaining := Remaining / 256;
      end loop;
      Check (Remaining = 0, "record identity exhausted");
      return Result;
   end Reference;

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
      Check (Remaining = 0, "record size exhausted");
      return Result;
   end Encode;

   procedure Counts_And_Bytes is
      H : Header;
      R : Record_Bytes;
      Expected_Record : Record_Reference;
      C : Cursor;
   begin
      Check (Is_Rejected (C), "default cursor refuses");
      for Count in Input_Count loop
         H := Head (Count);
         Start (H, 28, C);
         Check (Is_Open (C) and then Expected (C) = Count and then Consumed (C) = 0,
                "complete declared count domain");
      end loop;
      H := Head (Max_Inputs + 1);
      Start (H, 28, C);
      Check (Is_Rejected (C) and then Expected (C) = 0, "count overflow refuses");
      for Size in Byte_Count loop
         Expected_Record := Reference (65_536, Size);
         R := Encode (Expected_Record);
         Check (Record_Valid (R, 72) = (Size /= 0), "complete payload size domain");
         if Size /= 0 then
            Check (Record_Value (R) = Expected_Record, "complete record correspondence");
         end if;
      end loop;
      for I in 1 .. 20 loop
         H := Head (0);
         H (I) := H (I) xor 1;
         Check (not Header_Valid (H, 28), "every tag byte checked");
      end loop;
      for I in 21 .. 25 loop
         H := Head (0);
         H (I) := 1;
         Check (not Header_Valid (H, 28), "high count bytes refuse");
      end loop;
   end Counts_And_Bytes;

   procedure Cursor_Refusals is
      C : Cursor;
      Good : Boolean;
      Value : Record_Reference;
      R : constant Record_Bytes := Encode (Reference (0));
   begin
      for Length in 0 .. 27 loop
         Start (Head (1), Length, C);
         Check (Is_Rejected (C), "short header refuses");
      end loop;
      for Length in 0 .. 71 loop
         Start (Head (1), 28, C);
         Take (C, R, Length, Good, Value);
         Check (not Good and then Is_Rejected (C) and then Value = Empty_Record,
                "short record clears output");
      end loop;
      Start (Head (2), 28, C);
      Take (C, R, 72, Good, Value);
      Check (Good and then Value = Reference (0), "all-zero identity allowed");
      Take (C, R, 72, Good, Value);
      Check (not Good and then Value = Empty_Record, "duplicate identity refuses");
      Take (C, Encode (Reference (1)), 72, Good, Value);
      Check (not Good, "rejection sticky");
      Start (Head (2), 28, C);
      Take (C, Encode (Reference (2)), 72, Good, Value);
      Check (Good, "descending prefix accepted");
      Take (C, Encode (Reference (1)), 72, Good, Value);
      Check (not Good, "descending record refuses");
      Start (Head (1), 28, C);
      Finish (C, 0, Good);
      Check (not Good, "missing record refuses at end");
      Start (Head (0), 28, C);
      Finish (C, Natural'Last, Good);
      Check (not Good, "trailing bytes refuse");
      Start (Head (0), 28, C);
      Finish (C, 0, Good);
      Check (Good and then Is_Complete (C), "empty stream complete");
      Take (C, R, 72, Good, Value);
      Check (not Good and then Is_Rejected (C), "record after completion refuses");
   end Cursor_Refusals;

   procedure Full_Trace (Count : Input_Count; Packed : Boolean) is
      Records : Roster := Empty_Roster;
      State : Join.Partition_State;
      Kind : Join.Step_Kind;
      Value : Record_Reference;
      Good : Boolean;
      Stride : constant Positive := (if Count = 0 then 1 else Positive'Max (1, Count / Max_Records));
      Wanted : Record_Reference;
      R : Record_Bytes;
   begin
      if Packed then
         Records.Count := Record_Count'Min (Max_Records, Count);
         for I in 1 .. Records.Count loop
            Records.Records (I) := Reference (I * Stride);
         end loop;
      end if;
      Join.Start (Head (Count), Head (Count - Records.Count), 28, 28, Records, State);
      Check (Join.Active (State), "trace initialized");
      for I in 1 .. Count loop
         Wanted := Reference (I);
         R := Encode (Wanted);
         if Packed and then I mod Stride = 0 and then I / Stride <= Records.Count then
            Join.Take (State, R, [others => 255], 72, 0, Kind, Value);
            Check (Kind = Join.Represented_Record and then Value = Wanted, "represented step");
         else
            Join.Take (State, R, R, 72, 72, Kind, Value);
            Check (Kind = Join.Fallback_Record and then Value = Wanted, "fallback step");
         end if;
      end loop;
      Join.Finish (State, 0, 0, Good);
      Check (Good and then Join.Complete (State), "entire partition completed");
      Join.Take (State, Encode (Reference (1)), Encode (Reference (1)), 72, 72, Kind, Value);
      Check (Kind = Join.No_Step and then Join.Rejected (State), "completed partition cannot append");
   end Full_Trace;

   procedure Substitutions is
      Records : Roster := Empty_Roster;
      State : Join.Partition_State;
      Kind : Join.Step_Kind;
      Value : Record_Reference;
      Original : constant Record_Reference := Reference (1, 1234);
      R : constant Record_Bytes := Encode (Original);
      Changed : Record_Bytes;
      Good : Boolean;
   begin
      Records.Count := 1;
      Records.Records (1) := Original;
      for I in Record_Bytes'Range loop
         Changed := R;
         Changed (I) := Changed (I) xor 1;
         Join.Start (Head (1), Head (0), 28, 28, Records, State);
         Join.Take (State, Changed, R, 72, 0, Kind, Value);
         Check (Kind = Join.No_Step and then Value = Empty_Record, "represented byte substitution");
         Join.Finish (State, 0, 0, Good);
         Check (not Good, "substitution cannot complete");
         Join.Start (Head (1), Head (1), 28, 28, Empty_Roster, State);
         Join.Take (State, R, Changed, 72, 72, Kind, Value);
         Check (Kind = Join.No_Step and then Value = Empty_Record, "fallback byte substitution");
      end loop;
      Join.Start (Head (1), Head (0), 28, 28, Records, State);
      Join.Take (State, R, R, 72, 72, Kind, Value);
      Check (Kind = Join.No_Step, "represented step refuses extra fallback");
      Join.Start (Head (2), Head (0), 28, 28, Records, State);
      Check (Join.Rejected (State), "inconsistent declared partition refuses");
      Records.Records (2) := Original;
      Join.Start (Head (1), Head (0), 28, 28, Records, State);
      Check (Join.Rejected (State), "nonempty represented padding refuses");
   end Substitutions;

   procedure Incomplete_Traces is
      Records : Roster := Empty_Roster;
      State : Join.Partition_State;
      Kind : Join.Step_Kind;
      Value : Record_Reference;
      Good : Boolean;
      R : constant Record_Bytes := Encode (Reference (2));
   begin
      Check (Join.Rejected (State), "default partition refuses");
      Join.Take (State, R, R, 72, 72, Kind, Value);
      Check (Kind = Join.No_Step and then Value = Empty_Record, "uninitialized take refuses");
      Records.Count := 1;
      Records.Records (1) := Reference (1);
      Join.Start (Head (2), Head (1), 28, 28, Records, State);
      Join.Take (State, R, R, 72, 72, Kind, Value);
      Check (Kind = Join.Fallback_Record, "fallback before omitted representation");
      Join.Finish (State, 0, 0, Good);
      Check (not Good and then Join.Rejected (State), "omitted represented record refuses");
      Join.Start (Head (1), Head (1), 28, 28, Empty_Roster, State);
      Join.Take (State, R, R, 72, 72, Kind, Value);
      Check (Kind = Join.Fallback_Record, "complete fallback body");
      Join.Finish (State, 0, 1, Good);
      Check (not Good, "fallback trailing data refuses");
      Join.Start (Head (1), Head (1), 28, 28, Empty_Roster, State);
      Join.Take (State, R, R, 72, 72, Kind, Value);
      Check (Kind = Join.Fallback_Record, "complete selected body");
      Join.Finish (State, 1, 0, Good);
      Check (not Good, "selection trailing data refuses");
   end Incomplete_Traces;

   procedure Retained_Prefix is
      State : Join.Partition_State;
      Kind : Join.Step_Kind;
      Value : Record_Reference;
      Good : Boolean;
      Previous_Selection, Previous_Fallback : Cursor;
      R : constant Record_Bytes := Encode (Reference (1));
   begin
      Join.Start (Head (2), Head (2), 28, 28, Empty_Roster, State);
      Join.Take (State, R, R, 72, 72, Kind, Value);
      Check (Kind = Join.Fallback_Record, "prefix accepted");
      Previous_Selection := Join.Selected (State);
      Previous_Fallback := Join.Fallback (State);
      Join.Take (State, R, R, 72, 72, Kind, Value);
      Check (Kind = Join.No_Step and then Join.Rejected (State) and then
               Join.Selected (State) = Previous_Selection and then
               Join.Fallback (State) = Previous_Fallback and then
               Join.Position (State) = 0 and then Join.Representation (State) = Empty_Roster,
             "duplicate retains validated prefix");
      Join.Finish (State, 0, 0, Good);
      Check (not Good and then Join.Selected (State) = Previous_Selection and then
               Join.Fallback (State) = Previous_Fallback, "failed finish retains prefix");
      Join.Start (Head (1), Head (1), 28, 28, Empty_Roster, State);
      Join.Take (State, R, R, 72, 72, Kind, Value);
      Check (Kind = Join.Fallback_Record, "second trace accepted");
      Join.Finish (State, 0, 0, Good);
      Check (Good and then Consumed (Join.Selected (State)) = 1 and then
               Last_Identity (Join.Selected (State)) = Reference (1).Identity and then
               Consumed (Join.Fallback (State)) = 1 and then
               Last_Identity (Join.Fallback (State)) = Reference (1).Identity,
             "success retains prefix");
      Join.Finish (State, 0, 0, Good);
      Check (not Good and then Join.Rejected (State), "completion cannot be repeated");
   end Retained_Prefix;

   procedure Oversized_Lengths is
      C : Cursor;
      Good : Boolean;
      Value : Record_Reference;
      State : Join.Partition_State;
      Kind : Join.Step_Kind;
      R : constant Record_Bytes := Encode (Reference (1));
   begin
      Start (Head (0), Natural'Last, C);
      Check (Is_Rejected (C), "oversized header refuses");
      Start (Head (1), 28, C);
      Take (C, R, Natural'Last, Good, Value);
      Check (not Good and then Value = Empty_Record, "oversized record refuses");
      Join.Start (Head (1), Head (1), Natural'Last, 28, Empty_Roster, State);
      Check (Join.Rejected (State), "oversized selection header refuses");
      Join.Start (Head (1), Head (1), 28, Natural'Last, Empty_Roster, State);
      Check (Join.Rejected (State), "oversized fallback header refuses");
      Join.Start (Head (1), Head (1), 28, 28, Empty_Roster, State);
      Join.Take (State, R, R, Natural'Last, 72, Kind, Value);
      Check (Kind = Join.No_Step and then Value = Empty_Record, "oversized selection refuses");
      Join.Start (Head (1), Head (1), 28, 28, Empty_Roster, State);
      Join.Take (State, R, R, 72, Natural'Last, Kind, Value);
      Check (Kind = Join.No_Step and then Value = Empty_Record, "oversized fallback refuses");
   end Oversized_Lengths;
   --  Nonuniform bytes emitted by the pinned existing Python manifest producer.
   --  Full vector and producer hashes are retained in the evidence archive.
   procedure Python_Producer_Vector is
      H : constant Header := [83, 73, 65, 45, 80, 65, 67, 75, 45, 82, 69, 67, 79, 82, 68, 83, 45, 118, 49, 0, 0, 0, 0, 0, 0, 0, 0, 2];
      First : constant Record_Bytes := [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 0, 0, 0, 0, 0, 1, 0, 0];
      Second : constant Record_Bytes := [64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 0, 0, 0, 0, 0, 0, 0, 1];
      C : Cursor;
      Good : Boolean;
      Value : Record_Reference;
      Wanted : Record_Reference;
   begin
      Start (H, 28, C);
      Check (Is_Open (C) and then Expected (C) = 2, "Python producer header");
      for I in Digest'Range loop
         Wanted.Identity (I) := Digest_Byte (I - 1);
         Wanted.Content (I) := Digest_Byte (I + 31);
      end loop;
      Wanted.Bytes := 65_536;
      Take (C, First, 72, Good, Value);
      Check (Good and then Value = Wanted, "Python producer first complete record");
      for I in Digest'Range loop
         Wanted.Identity (I) := Digest_Byte (I + 63);
         Wanted.Content (I) := Digest_Byte (I + 95);
      end loop;
      Wanted.Bytes := 1;
      Take (C, Second, 72, Good, Value);
      Check (Good and then Value = Wanted, "Python producer second complete record");
      Finish (C, 0, Good);
      Check (Good, "Python producer stream complete");
   end Python_Producer_Vector;
begin
   Python_Producer_Vector;
   Counts_And_Bytes;
   Cursor_Refusals;
   Full_Trace (0, False);
   Full_Trace (1, True);
   Full_Trace (64, True);
   Full_Trace (Max_Inputs, True);
   Full_Trace (Max_Inputs, False);
   Substitutions;
   Incomplete_Traces;
   Retained_Prefix;
   Oversized_Lengths;
   Ada.Text_IO.Put_Line ("pack manifest controls PASS" & Checks'Image);
end Pack_Manifest_Tests;
