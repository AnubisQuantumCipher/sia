with Ada.Text_IO;
with SIA_Policy;
with SIA_Pack_Retirement;
with SIA_Pack_Plan_Wire;
package body Pack_Plan_Wire_Test_Support is
   use SIA_Policy;
   use SIA_Pack_Retirement;
   use SIA_Pack_Plan_Wire;
   Checks : Natural := 0;

   procedure Check (Condition : Boolean; Label_Text : String) is
   begin
      if not Condition then
         raise Program_Error with Label_Text;
      end if;
      Checks := Checks + 1;
   end Check;

   function Pattern (Seed : Digest_Byte) return Digest is
      Result : Digest;
   begin
      for I in Result'Range loop
         Result (I) := Seed + Digest_Byte (I * 3);
      end loop;
      return Result;
   end Pattern;

   function Fixture return Plan is
      Item : Plan := Empty_Plan;
   begin
      Item.Identity := Pattern (1);
      Item.Scope := ((16#0102030405060708#, Pattern (2)),
                     Pattern (3), Pattern (4), Pattern (5), Pattern (6),
                     Pattern (7), Pattern (8), Pattern (9), Pattern (10),
                     Pattern (11), Pattern (12));
      Item.Organ_Bytes := 200;
      Item.Selected := 65_536;
      Item.Fallback_Count := 65_534;
      Item.Prior.Count := 1;
      Item.Prior.Records (1) := (Pattern (20), Pattern (30), 1);
      Item.Target.Count := 2;
      Item.Target.Records (1) := Item.Prior.Records (1);
      Item.Target.Records (2) := (Pattern (21), Pattern (31), 2);
      Item.Represented := Item.Target;
      Item.Legacy_Present (2) := True;
      Item.Legacy_Generation (1) := Pattern (40);
      Item.Legacy_Generation (2) := Pattern (41);
      return Item;
   end Fixture;

   procedure Put_Word (Data : in out Frame; Start : Positive; Value : Generation) is
      Remaining : Generation := Value;
   begin
      for I in reverse 0 .. 7 loop
         Data (Start + I) := Digest_Byte (Remaining mod 256);
         Remaining := Remaining / 256;
      end loop;
      if Remaining /= 0 then
         raise Program_Error with "test word representable";
      end if;
   end Put_Word;

   procedure Put_Digest (Data : in out Frame; Start : Positive; Value : Digest) is
   begin
      for I in Value'Range loop
         Data (Start + I - 1) := Value (I);
      end loop;
   end Put_Digest;

   procedure Put_Roster (Data : in out Frame; Start : Positive; Value : Roster) is
      Position : Positive := Start + 8;
   begin
      Put_Word (Data, Start, Generation (Value.Count));
      for I in Value.Records'Range loop
         Put_Digest (Data, Position, Value.Records (I).Identity);
         Put_Digest (Data, Position + 32, Value.Records (I).Content);
         Put_Word (Data, Position + 64, Generation (Value.Records (I).Bytes));
         Position := Position + 72;
      end loop;
   end Put_Roster;

   --  Independent literal offsets; no production offset/decoder helpers.
   function Encode_Oracle (Item : Plan) return Frame is
      Data : Frame := [others => 0];
   begin
      Data (1) := 1;
      Put_Digest (Data, 9, Item.Identity);
      Put_Word (Data, 41, Item.Scope.Transaction.Epoch);
      Put_Digest (Data, 49, Item.Scope.Transaction.Transaction);
      Put_Digest (Data, 81, Item.Scope.Corpus);
      Put_Digest (Data, 113, Item.Scope.Organ);
      Put_Digest (Data, 145, Item.Scope.Prefix);
      Put_Digest (Data, 177, Item.Scope.Revision);
      Put_Digest (Data, 209, Item.Scope.Capture);
      Put_Digest (Data, 241, Item.Scope.Selection);
      Put_Digest (Data, 273, Item.Scope.Fallback);
      Put_Digest (Data, 305, Item.Scope.Old_Target);
      Put_Digest (Data, 337, Item.Scope.New_Target);
      Put_Digest (Data, 369, Item.Scope.Permission);
      Put_Word (Data, 401, Generation (Item.Organ_Bytes));
      Put_Word (Data, 409, Generation (Item.Selected));
      Put_Word (Data, 417, Generation (Item.Fallback_Count));
      Put_Roster (Data, 425, Item.Prior);
      Put_Roster (Data, 5_041, Item.Target);
      Put_Roster (Data, 9_657, Item.Represented);
      for I in 1 .. 64 loop
         Data (14_272 + I) := (if Item.Legacy_Present (I) then 1 else 0);
         Put_Digest (Data, 14_337 + (I - 1) * 32, Item.Legacy_Generation (I));
      end loop;
      return Data;
   end Encode_Oracle;

   procedure Require_Refusal (Data : Frame; Length : Natural; Label_Text : String) is
      Accepted : Boolean;
      Item : Plan := Fixture;
   begin
      Decode (Data, Length, Accepted, Item);
      Check (not Accepted and then Item = Empty_Plan, Label_Text);
   end Require_Refusal;

   procedure Boundaries is
      Expected : Plan := Fixture;
      Data : Frame := Encode_Oracle (Expected);
      Accepted : Boolean;
      Item : Plan;
   begin
      Decode (Data, 16_384, Accepted, Item);
      Check (Accepted and then Item = Expected, "complete nonuniform correspondence");
      Require_Refusal (Data, 0, "empty input");
      Require_Refusal (Data, 16_383, "short input");
      Require_Refusal (Data, 16_385, "trailing input");
      Require_Refusal (Data, Natural'Last, "length overflow domain");
      Expected.Scope.Transaction.Epoch := Generation'Last;
      Data := Encode_Oracle (Expected);
      Decode (Data, 16_384, Accepted, Item);
      Check (Accepted and then Item = Expected, "maximum epoch");
      Data (41) := 128;
      Require_Refusal (Data, 16_384, "epoch high bit");
      Expected.Scope.Transaction.Epoch := 0;
      Require_Refusal (Encode_Oracle (Expected), 16_384, "zero epoch policy");
      Expected := Fixture;
      Expected.Identity := Zero;
      Data := Encode_Oracle (Expected);
      Decode (Data, 16_384, Accepted, Item);
      Check (Accepted and then Item = Expected, "zero digest not sentinel");
   end Boundaries;

   procedure Full_Roster is
      Expected : Plan := Fixture;
      Data : Frame;
      Accepted : Boolean;
      Item : Plan;
   begin
      Expected.Prior := Empty_Roster;
      Expected.Target.Count := 64;
      for I in Record_Index loop
         Expected.Target.Records (I) :=
           (Pattern (Digest_Byte (I)), Pattern (Digest_Byte (I + 64)), 1);
         Expected.Legacy_Present (I) := True;
         Expected.Legacy_Generation (I) := Pattern (Digest_Byte (I + 128));
      end loop;
      Expected.Represented := Expected.Target;
      Expected.Fallback_Count := 65_472;
      Data := Encode_Oracle (Expected);
      Decode (Data, 16_384, Accepted, Item);
      Check (Accepted and then Item = Expected, "full roster and count domains");
      Expected.Target.Records (64).Bytes := 65_536;
      Expected.Represented := Expected.Target;
      Require_Refusal (Encode_Oracle (Expected), 16_384, "complete frame capacity");
   end Full_Roster;

   procedure Every_Byte is
      Expected : constant Plan := Fixture;
      Original : constant Frame := Encode_Oracle (Expected);
      Data : Frame;
      Accepted : Boolean;
      Item : Plan;
   begin
      for I in Original'Range loop
         Data := Original;
         Data (I) := Data (I) xor 1;
         Decode (Data, 16_384, Accepted, Item);
         if Accepted then
            Check (Item /= Expected, "changed byte cannot disappear");
            Check (Encode_Oracle (Item) = Data, "exact accepted roundtrip");
         else
            Check (Item = Empty_Plan, "refusal has no partial plan");
         end if;
      end loop;
   end Every_Byte;

   procedure Shape_Refusal (Data : Frame; Label_Text : String) is
   begin
      Check (not Shape_Valid (Data, 16_384), Label_Text);
      Require_Refusal (Data, 16_384, Label_Text);
   end Shape_Refusal;

   procedure Scalar_Controls is
      Original : constant Frame := Encode_Oracle (Fixture);
      Data : Frame;
      Starts : constant array (1 .. 3) of Positive := [401, 409, 417];
   begin
      for Start of Starts loop
         for High in 0 .. 4 loop
            Data := Original;
            Data (Start + High) := 1;
            Shape_Refusal (Data, "bounded scalar high byte");
         end loop;
         Data := Original;
         Data (Start + 5) := 1;
         Data (Start + 7) := 1;
         Shape_Refusal (Data, "noncanonical 65536 tail");
      end loop;
      for Invalid in 0 .. 1 loop
         Data := Original;
         Put_Word (Data, 401, (if Invalid = 0 then 0 else 201));
         Shape_Refusal (Data, "organ outside closed range");
      end loop;
      for I in 14_273 .. 14_336 loop
         Data := Original;
         Data (I) := 2;
         Shape_Refusal (Data, "presence code 2");
         Data (I) := 255;
         Shape_Refusal (Data, "presence code 255");
      end loop;
   end Scalar_Controls;

   procedure Roster_Scalars is
      Original : constant Frame := Encode_Oracle (Fixture);
      Data : Frame;
      Starts : constant array (1 .. 3) of Positive := [425, 5_041, 9_657];
      Position : Positive;
   begin
      for Start of Starts loop
         for High in 0 .. 6 loop
            Data := Original;
            Data (Start + High) := 1;
            Shape_Refusal (Data, "roster count high byte");
         end loop;
         Data := Original;
         Data (Start + 7) := 65;
         Shape_Refusal (Data, "roster count 65");
         for Slot in 0 .. 63 loop
            Position := Start + 8 + Slot * 72 + 64;
            for High in 0 .. 4 loop
               Data := Original;
               Data (Position + High) := 1;
               Shape_Refusal (Data, "record length high byte");
            end loop;
            Data := Original;
            Data (Position + 5) := 1;
            Data (Position + 7) := 1;
            Shape_Refusal (Data, "record length noncanonical tail");
         end loop;
      end loop;
   end Roster_Scalars;

   procedure Policy_Controls is
      Expected : Plan;
      Data : Frame;
      Saved : Record_Reference;
   begin
      for Case_Number in 1 .. 4 loop
         Expected := Fixture;
         case Case_Number is
            when 1 => Expected.Target.Records (3).Bytes := 1;
            when 2 =>
               Saved := Expected.Target.Records (1);
               Expected.Target.Records (1) := Expected.Target.Records (2);
               Expected.Target.Records (2) := Saved;
            when 3 => Expected.Target.Records (1).Content (1) := 99;
            when 4 =>
               Expected := Empty_Plan;
               Expected.Scope.Transaction.Epoch := 1;
               Expected.Selected := 1;
               Expected.Fallback_Count := 1;
         end case;
         Data := Encode_Oracle (Expected);
         Check (Shape_Valid (Data, 16_384), "policy refusal distinct from malformed");
         Require_Refusal (Data, 16_384, "invalid padding/order/union/no-retirement");
      end loop;
   end Policy_Controls;

   procedure Run is
   begin
      Boundaries;
      Full_Roster;
      Every_Byte;
      Scalar_Controls;
      Roster_Scalars;
      Policy_Controls;
      Ada.Text_IO.Put_Line ("pack plan wire runtime controls PASS:" & Checks'Image);
   end Run;
end Pack_Plan_Wire_Test_Support;
