package body SIA_Pack_Manifest_Wire with SPARK_Mode is
   procedure Start (Data : Header; Length : Natural; Item : out Cursor) is
   begin
      Item := (others => <>);
      if Header_Valid (Data, Length) then
         Item.Stage := Open;
         Item.Total := Header_Count (Data);
      end if;
   end Start;

   procedure Take
     (Item : in out Cursor; Data : Record_Bytes; Length : Natural;
      Accepted : out Boolean; Value : out Record_Reference)
   is
   begin
      Accepted := False;
      Value := Empty_Record;
      if Item.Stage = Open and then Item.Used < Item.Total and then
        Record_Valid (Data, Length) and then
        (Item.Used = 0 or else Before (Item.Last, Record_Value (Data).Identity))
      then
         Value := Record_Value (Data);
         Item.Used := Item.Used + 1;
         Item.Last := Value.Identity;
         Accepted := True;
      else
         Item.Stage := Rejected;
      end if;
   end Take;

   procedure Finish (Item : in out Cursor; Trailing_Bytes : Natural; Accepted : out Boolean) is
   begin
      Accepted := Item.Stage = Open and then Item.Used = Item.Total and then Trailing_Bytes = 0;
      Item.Stage := (if Accepted then Complete else Rejected);
   end Finish;
end SIA_Pack_Manifest_Wire;
