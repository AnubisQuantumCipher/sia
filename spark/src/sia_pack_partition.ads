with SIA_Policy;
with SIA_Pack_Retirement;
with SIA_Pack_Manifest_Wire;

--  Exact per-record merge correspondence. Callers must bind actual input streams
--  and their order to authenticated manifests; no filesystem or authority here.
package SIA_Pack_Partition with SPARK_Mode, Pure is
   use SIA_Policy;
   use SIA_Pack_Retirement;
   use SIA_Pack_Manifest_Wire;
   type Partition_State is private;
   type Step_Kind is (No_Step, Represented_Record, Fallback_Record);
   function Active (Item : Partition_State) return Boolean with Global => null;
   function Complete (Item : Partition_State) return Boolean with Global => null;
   function Rejected (Item : Partition_State) return Boolean with Global => null;
   function Selected (Item : Partition_State) return Cursor with Global => null;
   function Fallback (Item : Partition_State) return Cursor with Global => null;
   function Representation (Item : Partition_State) return Roster with Global => null;
   function Position (Item : Partition_State) return Record_Count with Global => null;
   function Consistent (Item : Partition_State) return Boolean with Global => null;
   function Can_Start (Selection_Header, Fallback_Header : Header;
                       Selection_Length, Fallback_Length : Natural; Records : Roster)
      return Boolean is
     (Header_Valid (Selection_Header, Selection_Length) and then
      Header_Valid (Fallback_Header, Fallback_Length) and then Valid_Roster (Records) and then
      Header_Count (Selection_Header) = Records.Count + Header_Count (Fallback_Header))
   with Global => null;

   function Next_Is_Represented (Item : Partition_State; Value : Record_Reference)
      return Boolean is
     (Position (Item) < Representation (Item).Count and then
      Value.Identity = Representation (Item).Records (Position (Item) + 1).Identity)
   with Global => null;
   function Acceptable
     (Item : Partition_State; Selection_Data, Fallback_Data : Record_Bytes;
      Selection_Length, Fallback_Length : Natural) return Boolean is
     (Active (Item) and then
      SIA_Pack_Manifest_Wire.Acceptable (Selected (Item), Selection_Data, Selection_Length) and then
      (if Next_Is_Represented (Item, Record_Value (Selection_Data)) then
           Fallback_Length = 0 and then Record_Value (Selection_Data) =
             Representation (Item).Records (Position (Item) + 1)
       else SIA_Pack_Manifest_Wire.Acceptable (Fallback (Item), Fallback_Data, Fallback_Length) and then
         Record_Value (Selection_Data) = Record_Value (Fallback_Data)))
   with Global => null;

   procedure Start
     (Selection_Header, Fallback_Header : Header; Selection_Length, Fallback_Length : Natural;
      Records : Roster; Item : out Partition_State)
   with Global => null, Always_Terminates,
     Depends => (Item => (Selection_Header, Fallback_Header, Selection_Length, Fallback_Length, Records)),
     Post => Consistent (Item) and then
       Active (Item) = Can_Start (Selection_Header, Fallback_Header, Selection_Length, Fallback_Length, Records) and then
       Rejected (Item) = not Active (Item) and then not Complete (Item) and then
       Position (Item) = 0 and then Consumed (Selected (Item)) = 0 and then
       Consumed (Fallback (Item)) = 0 and then
       (if Active (Item) then Representation (Item) = Records and then
          Expected (Selected (Item)) = Header_Count (Selection_Header) and then
          Expected (Fallback (Item)) = Header_Count (Fallback_Header));

   procedure Take
     (Item : in out Partition_State; Selection_Data, Fallback_Data : Record_Bytes;
      Selection_Length, Fallback_Length : Natural; Kind : out Step_Kind;
      Value : out Record_Reference)
   with Global => null, Always_Terminates,
     Depends => (Item => (Item, Selection_Data, Fallback_Data, Selection_Length, Fallback_Length),
       Kind => (Item, Selection_Data, Fallback_Data, Selection_Length, Fallback_Length),
       Value => (Item, Selection_Data, Fallback_Data, Selection_Length, Fallback_Length)),
     Pre => Consistent (Item),
     Post => Consistent (Item) and then Representation (Item) = Representation (Item'Old) and then
       (Kind /= No_Step) = Acceptable (Item'Old, Selection_Data, Fallback_Data, Selection_Length, Fallback_Length) and then
       (if Kind = No_Step then Rejected (Item) and then Value = Empty_Record and then
          Position (Item) = Position (Item'Old) and then
          Selected (Item) = Selected (Item'Old) and then Fallback (Item) = Fallback (Item'Old)
        else Active (Item) and then Value = Record_Value (Selection_Data) and then
          Consumed (Selected (Item)) = Consumed (Selected (Item'Old)) + 1 and then
          Expected (Selected (Item)) = Expected (Selected (Item'Old)) and then
          Expected (Fallback (Item)) = Expected (Fallback (Item'Old)) and then
          (if Kind = Represented_Record then
             Position (Item) = Position (Item'Old) + 1 and then
             Value = Representation (Item'Old).Records (Position (Item'Old) + 1) and then
             Fallback_Length = 0 and then Fallback (Item) = Fallback (Item'Old)
           else Position (Item) = Position (Item'Old) and then
             Value = Record_Value (Fallback_Data) and then
             Consumed (Fallback (Item)) = Consumed (Fallback (Item'Old)) + 1));

   procedure Finish
     (Item : in out Partition_State; Selection_Trailing, Fallback_Trailing : Natural;
      Accepted : out Boolean)
   with Global => null, Always_Terminates,
     Depends => (Item => (Item, Selection_Trailing, Fallback_Trailing),
                 Accepted => (Item, Selection_Trailing, Fallback_Trailing)),
     Pre => Consistent (Item),
     Post => Consistent (Item) and then
       Representation (Item) = Representation (Item'Old) and then
       Position (Item) = Position (Item'Old) and then
       Expected (Selected (Item)) = Expected (Selected (Item'Old)) and then
       Consumed (Selected (Item)) = Consumed (Selected (Item'Old)) and then
       Last_Identity (Selected (Item)) = Last_Identity (Selected (Item'Old)) and then
       Expected (Fallback (Item)) = Expected (Fallback (Item'Old)) and then
       Consumed (Fallback (Item)) = Consumed (Fallback (Item'Old)) and then
       Last_Identity (Fallback (Item)) = Last_Identity (Fallback (Item'Old)) and then
       Complete (Item) = Accepted and then
       Rejected (Item) = not Accepted and then
       Accepted = (Active (Item'Old) and then
          Consumed (Selected (Item'Old)) = Expected (Selected (Item'Old)) and then
          Consumed (Fallback (Item'Old)) = Expected (Fallback (Item'Old)) and then
          Position (Item'Old) = Representation (Item'Old).Count and then
          Selection_Trailing = 0 and then Fallback_Trailing = 0);
private
   type Phase is (Open, Failed, Done);
   type Partition_State is record
      Stage : Phase := Failed;
      Selection_Stream, Fallback_Stream : Cursor;
      Records : Roster := Empty_Roster;
      Used : Record_Count := 0;
   end record;
   function Active (Item : Partition_State) return Boolean is (Item.Stage = Open);
   function Complete (Item : Partition_State) return Boolean is (Item.Stage = Done);
   function Rejected (Item : Partition_State) return Boolean is (Item.Stage = Failed);
   function Selected (Item : Partition_State) return Cursor is (Item.Selection_Stream);
   function Fallback (Item : Partition_State) return Cursor is (Item.Fallback_Stream);
   function Representation (Item : Partition_State) return Roster is (Item.Records);
   function Position (Item : Partition_State) return Record_Count is (Item.Used);
   function Consistent (Item : Partition_State) return Boolean is
     (if Item.Stage /= Failed then
        Valid_Roster (Item.Records) and then Item.Used <= Item.Records.Count and then
        Expected (Item.Selection_Stream) = Item.Records.Count + Expected (Item.Fallback_Stream) and then
        Consumed (Item.Selection_Stream) = Item.Used + Consumed (Item.Fallback_Stream) and then
        (if Item.Stage = Open then Is_Open (Item.Selection_Stream) and then Is_Open (Item.Fallback_Stream)
         else Is_Complete (Item.Selection_Stream) and then Is_Complete (Item.Fallback_Stream) and then
           Item.Used = Item.Records.Count and then
           Consumed (Item.Selection_Stream) = Expected (Item.Selection_Stream) and then
           Consumed (Item.Fallback_Stream) = Expected (Item.Fallback_Stream)));
end SIA_Pack_Partition;
