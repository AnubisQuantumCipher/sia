package body SIA_Pack_Partition with SPARK_Mode is
   procedure Start
     (Selection_Header, Fallback_Header : Header; Selection_Length, Fallback_Length : Natural;
      Records : Roster; Item : out Partition_State)
   is
   begin
      Item := (others => <>);
      SIA_Pack_Manifest_Wire.Start (Selection_Header, Selection_Length, Item.Selection_Stream);
      SIA_Pack_Manifest_Wire.Start (Fallback_Header, Fallback_Length, Item.Fallback_Stream);
      if Can_Start (Selection_Header, Fallback_Header, Selection_Length, Fallback_Length, Records) then
         Item.Records := Records;
         Item.Stage := Open;
      end if;
   end Start;

   procedure Take
     (Item : in out Partition_State; Selection_Data, Fallback_Data : Record_Bytes;
      Selection_Length, Fallback_Length : Natural; Kind : out Step_Kind;
      Value : out Record_Reference)
   is
      Good : Boolean;
      Other : Record_Reference;
   begin
      Kind := No_Step;
      Value := Empty_Record;
      if not Acceptable (Item, Selection_Data, Fallback_Data, Selection_Length, Fallback_Length) then
         Item.Stage := Failed;
         return;
      end if;
      SIA_Pack_Manifest_Wire.Take (Item.Selection_Stream, Selection_Data, Selection_Length, Good, Value);
      pragma Assert (Good);
      if Next_Is_Represented (Item, Value) then
         Item.Used := Item.Used + 1;
         Kind := Represented_Record;
      else
         SIA_Pack_Manifest_Wire.Take (Item.Fallback_Stream, Fallback_Data, Fallback_Length, Good, Other);
         pragma Assert (Good and then Other = Value);
         Kind := Fallback_Record;
      end if;
   end Take;

   procedure Finish
     (Item : in out Partition_State; Selection_Trailing, Fallback_Trailing : Natural;
      Accepted : out Boolean)
   is
      Selection_Good, Fallback_Good : Boolean;
   begin
      Accepted := False;
      if Item.Stage /= Open then
         Item.Stage := Failed;
         return;
      end if;
      SIA_Pack_Manifest_Wire.Finish (Item.Selection_Stream, Selection_Trailing, Selection_Good);
      SIA_Pack_Manifest_Wire.Finish (Item.Fallback_Stream, Fallback_Trailing, Fallback_Good);
      Accepted := Selection_Good and then Fallback_Good and then Item.Used = Item.Records.Count;
      Item.Stage := (if Accepted then Done else Failed);
   end Finish;
end SIA_Pack_Partition;
