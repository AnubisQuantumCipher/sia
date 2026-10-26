with SIA_Policy;

--  Conditional correspondence only. Authenticated producers must establish
--  exact manifests, digests, current observations and durable receipts. This
--  package grants no capability and performs no filesystem effects.
package SIA_Pack_Retirement with SPARK_Mode, Pure is
   use SIA_Policy;
   Max_Records : constant := 64;
   Max_Frame_Bytes : constant := 65_536;
   Max_Inputs : constant := 65_536;
   subtype Record_Count is Natural range 0 .. Max_Records;
   subtype Record_Index is Positive range 1 .. Max_Records;
   subtype Input_Count is Natural range 0 .. Max_Inputs;
   subtype Byte_Count is Natural range 0 .. Max_Frame_Bytes;
   subtype Organ_Length is Positive range 1 .. 200;
   Zero : constant Digest := [others => 0];
   Empty_Witness : constant Witness := (False, False, (0, [others => 0]));

   type Record_Reference is record
      Identity, Content : Digest := Zero;
      Bytes : Byte_Count := 0;
   end record;
   Empty_Record : constant Record_Reference := (others => <>);
   type Record_Array is array (Record_Index) of Record_Reference;
   type Roster is record
      Count : Record_Count := 0;
      Records : Record_Array := [others => Empty_Record];
   end record;
   Empty_Roster : constant Roster := (others => <>);
   type Digest_Array is array (Record_Index) of Digest;
   type Presence_Array is array (Record_Index) of Boolean;

   type Context is record
      Transaction : Binding := (0, Zero);
      Corpus, Organ, Prefix, Revision, Capture : Digest := Zero;
      Selection, Fallback, Old_Target, New_Target, Permission : Digest := Zero;
   end record;
   Empty_Context : constant Context := (others => <>);
   type Plan is record
      Scope : Context := Empty_Context;
      Identity : Digest := Zero;
      Organ_Bytes : Organ_Length := 1;
      Selected, Fallback_Count : Input_Count := 0;
      Prior, Target, Represented : Roster := Empty_Roster;
      Legacy_Present : Presence_Array := [others => False];
      Legacy_Generation : Digest_Array := [others => Zero];
   end record;
   Empty_Plan : constant Plan := (others => <>);

   function Contains (Items : Roster; Item : Record_Reference) return Boolean is
     (for some I in 1 .. Items.Count => Items.Records (I) = Item)
   with Global => null;

   function Before (Left, Right : Digest) return Boolean is
     (for some I in Digest'Range =>
        Left (I) < Right (I) and then
        (for all J in Digest'First .. I - 1 => Left (J) = Right (J)))
   with Global => null;

   --  Zero digest bytes are valid, including an all-zero event identity.
   --  Count/positive payload length distinguish active slots from padding.
   function Valid_Roster (Items : Roster) return Boolean is
     ((for all I in Record_Index =>
         (if I <= Items.Count then Items.Records (I).Bytes /= 0
          else Items.Records (I) = Empty_Record)) and then
      (for all I in 2 .. Items.Count =>
         Before (Items.Records (I - 1).Identity, Items.Records (I).Identity)))
   with Global => null;

   --  Maximum logical sum before the frame ceiling is applied. This is not
   --  a runtime stack or allocator-memory claim.
   Magic : constant String := "SIA-EVENT-PACK-1" & ASCII.LF;
   Max_Header : constant := Magic'Length + 1 + Organ_Length'Last + 3 + 1 + 4 + 32;
   Max_Logical_Size : constant := Max_Header + Max_Records * (68 + Max_Frame_Bytes);
   subtype Logical_Size is Natural range 0 .. Max_Logical_Size;
   type Size_Array is array (Record_Count) of Logical_Size;
   function Prefix_Sizes (Items : Roster; Organ_Bytes : Organ_Length)
      return Size_Array
   with Global => null,
     Post =>
       Prefix_Sizes'Result (0) = ((((((Magic'Length + 1) + Organ_Bytes) + 3) + 1) + 4) + 32) and then
       (for all I in 1 .. Items.Count =>
          Prefix_Sizes'Result (I) = (Prefix_Sizes'Result (I - 1) + 68) +
            Items.Records (I).Bytes) and then
       (for all I in Items.Count + 1 .. Max_Records => Prefix_Sizes'Result (I) = 0) and then
       (for all I in Record_Count =>
          Prefix_Sizes'Result (I) <= Max_Header + I * (68 + Max_Frame_Bytes));
   function Encoded_Size (Items : Roster; Organ_Bytes : Organ_Length)
      return Logical_Size is
     (Prefix_Sizes (Items, Organ_Bytes) (Items.Count))
   with Global => null;

   function Exact_Union (Item : Plan) return Boolean is
     ((for all I in 1 .. Item.Prior.Count =>
         Contains (Item.Target, Item.Prior.Records (I))) and then
      (for all I in 1 .. Item.Represented.Count =>
         Contains (Item.Target, Item.Represented.Records (I))) and then
      (for all I in 1 .. Item.Target.Count =>
         Contains (Item.Prior, Item.Target.Records (I)) or else
         Contains (Item.Represented, Item.Target.Records (I))))
   with Global => null;

   function Valid_Retirement_Plan (Item : Plan) return Boolean is
     (Item.Scope.Transaction.Epoch /= 0 and then
      Item.Selected = Item.Represented.Count + Item.Fallback_Count and then
      Item.Target.Count /= 0 and then Valid_Roster (Item.Prior) and then
      Valid_Roster (Item.Target) and then Valid_Roster (Item.Represented) and then
      Exact_Union (Item) and then
      Encoded_Size (Item.Target, Item.Organ_Bytes) <= Max_Frame_Bytes and then
      (for all I in Record_Index =>
         (if I <= Item.Represented.Count then
             (if not Item.Legacy_Present (I) then
                 Contains (Item.Prior, Item.Represented.Records (I)))
          else not Item.Legacy_Present (I) and then
            Item.Legacy_Generation (I) = Zero)))
   with Global => null;

   type Legacy_State is (Unobserved, Exact_Present, Absent, Conflicting);
   type Retirement_Receipt is record
      Scope : Context := Empty_Context;
      Plan_Id, Identity : Digest := Zero;
      Slot : Record_Count := 0;
      Original : Record_Reference := Empty_Record;
      Original_Generation : Digest := Zero;
      Custody : Witness := Empty_Witness;
   end record;
   Empty_Receipt : constant Retirement_Receipt := (others => <>);
   type Observation is record
      Scope : Context := Empty_Context;
      Plan_Id, Execution : Digest := Zero;
      Target : Roster := Empty_Roster;
      Frame_Bytes : Byte_Count := 0;
      Intent, File_Sync, Parent_Sync, Readback, Selection : Witness := Empty_Witness;
      Legacy : Legacy_State := Unobserved;
      Original : Record_Reference := Empty_Record;
      Original_Generation : Digest := Zero;
      Retired : Retirement_Receipt := Empty_Receipt;
   end record;
   Empty_Observation : constant Observation := (others => <>);

   function Target_Binding (Item : Plan) return Binding is
     (Binding'(Item.Scope.Transaction.Epoch, Item.Scope.New_Target))
   with Global => null;
   function Common_Matches
     (Item : Plan; Seen : Observation; Execution : Digest) return Boolean is
     (Valid_Retirement_Plan (Item) and then Seen.Scope = Item.Scope and then
      Seen.Plan_Id = Item.Identity and then Seen.Execution = Execution and then
      Seen.Target = Item.Target and then
      Seen.Frame_Bytes = Encoded_Size (Item.Target, Item.Organ_Bytes) and then
      Bound_Durable (Seen.Intent, (Item.Scope.Transaction.Epoch, Item.Identity)) and then
      Bound_Durable (Seen.File_Sync, Target_Binding (Item)) and then
      Bound_Durable (Seen.Parent_Sync, Target_Binding (Item)) and then
      Bound_Durable (Seen.Readback, Target_Binding (Item)) and then
      Bound_Durable (Seen.Selection,
                     (Item.Scope.Transaction.Epoch, Item.Scope.Selection)))
   with Global => null;

   function Source_Matches
     (Item : Plan; Seen : Observation; Slot : Record_Index) return Boolean is
     (Slot <= Item.Represented.Count and then
      Seen.Original = Item.Represented.Records (Slot) and then
      Seen.Original_Generation = Item.Legacy_Generation (Slot))
   with Global => null;
   function Receipt_Matches
     (Item : Plan; Seen : Retirement_Receipt; Slot : Record_Index) return Boolean is
     (Seen.Scope = Item.Scope and then Seen.Plan_Id = Item.Identity and then
      Seen.Slot = Slot and then Seen.Original = Item.Represented.Records (Slot) and then
      Seen.Original_Generation = Item.Legacy_Generation (Slot) and then
      Bound_Durable (Seen.Custody, (Item.Scope.Transaction.Epoch, Seen.Identity)))
   with Global => null;

   function Unlink_Matches
     (Item : Plan; Seen : Observation; Slot : Record_Index) return Boolean is
     (Source_Matches (Item, Seen, Slot) and then Item.Legacy_Present (Slot) and then
      Seen.Legacy = Exact_Present and then not Seen.Retired.Custody.Present)
   with Global => null;
   function Retired_Matches
     (Item : Plan; Seen : Observation; Slot : Record_Index) return Boolean is
     (Source_Matches (Item, Seen, Slot) and then Item.Legacy_Present (Slot) and then
      Seen.Legacy = Absent and then Receipt_Matches (Item, Seen.Retired, Slot))
   with Global => null;
   function Original_Absence_Matches
     (Item : Plan; Seen : Observation; Slot : Record_Index) return Boolean is
     (Source_Matches (Item, Seen, Slot) and then not Item.Legacy_Present (Slot) and then
      Seen.Legacy = Absent and then not Seen.Retired.Custody.Present)
   with Global => null;

   type Decision is (Refused, Unlink_Proposed, Retirement_Recorded, Originally_Absent);
   function Classify
     (Item : Plan; Seen : Observation; Execution : Digest; Slot : Record_Index)
      return Decision
   with Global => null,
     Contract_Cases =>
       (not Common_Matches (Item, Seen, Execution) => Classify'Result = Refused,
        Common_Matches (Item, Seen, Execution) and then Unlink_Matches (Item, Seen, Slot) =>
          Classify'Result = Unlink_Proposed,
        Common_Matches (Item, Seen, Execution) and then Retired_Matches (Item, Seen, Slot) =>
          Classify'Result = Retirement_Recorded,
        Common_Matches (Item, Seen, Execution) and then Original_Absence_Matches (Item, Seen, Slot) =>
          Classify'Result = Originally_Absent,
        others => Classify'Result = Refused);
end SIA_Pack_Retirement;
