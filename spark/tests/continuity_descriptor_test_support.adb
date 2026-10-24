with SIA_Policy; use SIA_Policy;
with SIA_Continuity; use SIA_Continuity;
with SIA_Continuity.Approvals; use SIA_Continuity.Approvals;
with SIA_Continuity.Approvals.Descriptors;
use SIA_Continuity.Approvals.Descriptors;

--  Runtime mutation oracles, not deductively proved or authenticated inputs.
package body Continuity_Descriptor_Test_Support with SPARK_Mode => Off is
   Good : constant Descriptor_Bytes :=
     [1 => 83, 2 => 73, 3 => 65, 4 => 68, 5 => 83, 6 => 67, 7 => 48, 8 => 49,
      9 .. 40 => 1, 41 .. 72 => 2, 73 .. 104 => 3,
      105 .. 136 => 4, 137 .. 168 => 5, 169 .. 200 => 13,
      201 .. 232 => 14, 233 .. 264 => 15, 265 .. 296 => 16,
      297 .. 328 => 17, 329 .. 360 => 18, 361 .. 392 => 19,
      400 => 7, 408 => 8, 416 => 9,
      417 .. 448 => 20, 449 .. 480 => 21, 481 => 1, 482 => 1,
      others => 0];
   Expected_Scope : constant Context :=
     (Task_Id => [others => 1], Session_Id => [others => 2],
      Repository => [others => 3], Revision => [others => 4],
      Dirty => [others => 5]);
   Expected_Item : constant Current_Selection :=
     (Question => [others => 13], Question_Item => [others => 14],
      Response => [others => 15],
      Requested => (Proposal => [others => 16], Action => [others => 17],
                    Conditions => [others => 18]),
      Form => Queried_Decision, State => Current,
      Checkpoint_Id => [others => 19], Epoch => 7, Through => 8,
      Retention_Epoch => 9,
      Where_Now => (Lifecycle => [others => 20], Target_Turn => [others => 21]),
      others => <>);

   procedure No_Trust (Item : Current_Selection) is
   begin
      pragma Assert (Item.Descriptor = Zero);
      pragma Assert (Item.Source_State = Unknown_Source);
      pragma Assert (Item.Custody = Empty_Witness);
   end No_Trust;

   procedure Refused (Bytes : Descriptor_Bytes) is
      Accepted : Boolean := True;
      Scope : Context := Expected_Scope;
      Item : Current_Selection := (Expected_Item with delta
        Descriptor => [others => 77], Source_State => Authenticated,
        Custody => (True, True, (7, [others => 77])));
   begin
      Decode (Bytes, Accepted, Scope, Item);
      pragma Assert (not Accepted and Scope = Empty_Context);
      pragma Assert (Item = Empty_Selection);
      No_Trust (Item);
   end Refused;

   procedure Known_Fields is
      Accepted : Boolean;
      Scope : Context;
      Item : Current_Selection := (Expected_Item with delta
        Descriptor => [others => 77], Source_State => Authenticated,
        Custody => (True, True, (7, [others => 77])));
   begin
      Decode (Good, Accepted, Scope, Item);
      pragma Assert (Accepted and Scope = Expected_Scope);
      pragma Assert (Item = Expected_Item);
      No_Trust (Item);
   end Known_Fields;

   procedure Every_Byte_Matters is
      Bytes : Descriptor_Bytes;
      Accepted : Boolean;
      Scope : Context;
      Item : Current_Selection;
   begin
      for I in Descriptor_Bytes'Range loop
         Bytes := Good;
         Bytes (I) := Bytes (I) + 1;
         Decode (Bytes, Accepted, Scope, Item);
         No_Trust (Item);
         if I <= 8 or I >= 483 then
            pragma Assert (not Accepted);
            Refused (Bytes);
         else
            pragma Assert (Accepted);
            pragma Assert (Scope /= Expected_Scope or Item /= Expected_Item);
            pragma Assert (not Content_Matches
              (Bytes, Expected_Scope, Expected_Item));
         end if;
      end loop;
   end Every_Byte_Matters;

   procedure Every_Enum_Code is
      Forms : constant array (Digest_Byte range 0 .. 2) of Decision_Form :=
        [Unknown_Form, Queried_Decision, Direct_Instruction];
      States : constant array (Digest_Byte range 0 .. 4) of Currentness :=
        [Unknown_Current, Current, Revoked, Superseded, Expired];
      Bytes : Descriptor_Bytes;
      Accepted : Boolean;
      Scope : Context;
      Item : Current_Selection;
   begin
      for Code in Digest_Byte loop
         Bytes := Good;
         Bytes (481) := Code;
         Decode (Bytes, Accepted, Scope, Item);
         pragma Assert (Accepted = (Code <= 2));
         pragma Assert
           (Scope = (if Accepted then Expected_Scope else Empty_Context));
         No_Trust (Item);
         if Accepted then pragma Assert (Item.Form = Forms (Code)); end if;
         if not Accepted then Refused (Bytes); end if;
         Bytes := Good;
         Bytes (482) := Code;
         Decode (Bytes, Accepted, Scope, Item);
         pragma Assert (Accepted = (Code <= 4));
         pragma Assert
           (Scope = (if Accepted then Expected_Scope else Empty_Context));
         No_Trust (Item);
         if Accepted then pragma Assert (Item.State = States (Code)); end if;
         if not Accepted then Refused (Bytes); end if;
      end loop;
   end Every_Enum_Code;

   procedure Generation_Boundaries is
      Bytes : Descriptor_Bytes := Good;
      Accepted : Boolean;
      Scope : Context;
      Item : Current_Selection;
   begin
      for I in 393 .. 416 loop Bytes (I) := 255; end loop;
      Bytes (393) := 127;
      Bytes (401) := 127;
      Bytes (409) := 127;
      Decode (Bytes, Accepted, Scope, Item);
      pragma Assert (Accepted and Item.Epoch = Generation'Last);
      pragma Assert (Scope = Expected_Scope);
      pragma Assert (Item.Through = Generation'Last);
      pragma Assert (Item.Retention_Epoch = Generation'Last);
      for Offset in 0 .. 2 loop
         Bytes := Good;
         Bytes (393 + 8 * Offset) := 128;
         Refused (Bytes);
      end loop;
      for I in 393 .. 416 loop Bytes (I) := 0; end loop;
      Decode (Bytes, Accepted, Scope, Item);
      pragma Assert (Accepted and Item.Epoch = 0);
      pragma Assert (Scope = Expected_Scope);
      pragma Assert (Item.Through = 0 and Item.Retention_Epoch = 0);
   end Generation_Boundaries;

   procedure Nonuniform_Digests is
      Pattern : constant Digest :=
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
         16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31];
      Starts : constant array (Positive range 1 .. 14) of Positive :=
        [9, 41, 73, 105, 137, 169, 201, 233, 265, 297, 329, 361, 417, 449];
      Bytes : Descriptor_Bytes;
      Accepted : Boolean;
      Scope, Wanted_Scope : Context;
      Item, Wanted_Item : Current_Selection;
   begin
      for Field in Starts'Range loop
         Bytes := Good;
         Wanted_Scope := Expected_Scope;
         Wanted_Item := Expected_Item;
         for I in Pattern'Range loop
            Bytes (Starts (Field) + I - 1) := Pattern (I);
         end loop;
         case Field is
            when 1 => Wanted_Scope.Task_Id := Pattern;
            when 2 => Wanted_Scope.Session_Id := Pattern;
            when 3 => Wanted_Scope.Repository := Pattern;
            when 4 => Wanted_Scope.Revision := Pattern;
            when 5 => Wanted_Scope.Dirty := Pattern;
            when 6 => Wanted_Item.Question := Pattern;
            when 7 => Wanted_Item.Question_Item := Pattern;
            when 8 => Wanted_Item.Response := Pattern;
            when 9 => Wanted_Item.Requested.Proposal := Pattern;
            when 10 => Wanted_Item.Requested.Action := Pattern;
            when 11 => Wanted_Item.Requested.Conditions := Pattern;
            when 12 => Wanted_Item.Checkpoint_Id := Pattern;
            when 13 => Wanted_Item.Where_Now.Lifecycle := Pattern;
            when 14 => Wanted_Item.Where_Now.Target_Turn := Pattern;
         end case;
         Decode (Bytes, Accepted, Scope, Item);
         pragma Assert (Accepted and Scope = Wanted_Scope and Item = Wanted_Item);
         No_Trust (Item);
      end loop;
   end Nonuniform_Digests;

   procedure Mixed_Generations is
      Bytes : Descriptor_Bytes := Good;
      Accepted : Boolean;
      Scope : Context;
      Item : Current_Selection;
   begin
      Bytes (393 .. 400) := [1, 35, 69, 103, 137, 171, 205, 239];
      Bytes (401 .. 408) := [2, 48, 64, 80, 96, 112, 128, 144];
      Bytes (409 .. 416) := [3, 254, 220, 186, 152, 118, 84, 50];
      Decode (Bytes, Accepted, Scope, Item);
      pragma Assert (Accepted and Scope = Expected_Scope);
      --  Exact decimal oracles retained from JACKAL; not formal-bounded.
      pragma Assert (Item.Epoch = 81_985_529_216_486_895);
      pragma Assert (Item.Through = 157_696_700_917_514_384);
      pragma Assert (Item.Retention_Epoch = 287_910_120_178_209_842);
      No_Trust (Item);
   end Mixed_Generations;

   procedure Run is
   begin
      Known_Fields;
      Every_Byte_Matters;
      Every_Enum_Code;
      Generation_Boundaries;
      Nonuniform_Digests;
      Mixed_Generations;
      Refused ([others => 0]);
   end Run;
end Continuity_Descriptor_Test_Support;
