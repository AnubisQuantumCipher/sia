with SIA_Policy;
with SIA_Pack_Retirement;

--  Bounded ordered stream validation, not source authentication or I/O.
package SIA_Pack_Manifest_Wire with SPARK_Mode, Pure is
   use SIA_Policy;
   use SIA_Pack_Retirement;
   Magic : constant String := "SIA-PACK-RECORDS-v1" & ASCII.NUL;
   type Header is array (Positive range 1 .. 28) of Digest_Byte;
   type Record_Bytes is array (Positive range 1 .. 72) of Digest_Byte;
   type Count_Bytes is array (Positive range 1 .. 8) of Digest_Byte;

   function Count_Valid (Data : Count_Bytes) return Boolean is
     ((for all I in 1 .. 5 => Data (I) = 0) and then
      (Data (6) = 0 or else
       (Data (6) = 1 and then Data (7) = 0 and then Data (8) = 0)))
   with Global => null;
   function Count_Value (Data : Count_Bytes) return Input_Count is
     ((Natural (Data (6)) * 65_536 + Natural (Data (7)) * 256) + Natural (Data (8)))
   with Global => null, Pre => Count_Valid (Data);
   function Header_Valid (Data : Header; Length : Natural) return Boolean is
     (Length = Header'Length and then
      (for all I in Magic'Range => Data (I) = Character'Pos (Magic (I))) and then
      Count_Valid (Count_Bytes (Data (21 .. 28))))
   with Global => null;
   function Header_Count (Data : Header) return Input_Count is
     (Count_Value (Count_Bytes (Data (21 .. 28))))
   with Global => null, Pre => Header_Valid (Data, Header'Length);
   function Record_Valid (Data : Record_Bytes; Length : Natural) return Boolean is
     (Length = Record_Bytes'Length and then
      Count_Valid (Count_Bytes (Data (65 .. 72))) and then
      Count_Value (Count_Bytes (Data (65 .. 72))) /= 0)
   with Global => null;
   function Record_Value (Data : Record_Bytes) return Record_Reference is
     ((Digest (Data (1 .. 32)), Digest (Data (33 .. 64)),
       Count_Value (Count_Bytes (Data (65 .. 72)))))
   with Global => null, Pre => Record_Valid (Data, Record_Bytes'Length);

   type Cursor is private;
   function Is_Open (Item : Cursor) return Boolean with Global => null;
   function Is_Complete (Item : Cursor) return Boolean with Global => null;
   function Is_Rejected (Item : Cursor) return Boolean with Global => null;
   function Expected (Item : Cursor) return Input_Count with Global => null;
   function Consumed (Item : Cursor) return Input_Count with Global => null;
   function Last_Identity (Item : Cursor) return Digest with Global => null;
   function Acceptable (Item : Cursor; Data : Record_Bytes; Length : Natural) return Boolean is
     (Is_Open (Item) and then Consumed (Item) < Expected (Item) and then
      Record_Valid (Data, Length) and then
      (Consumed (Item) = 0 or else Before (Last_Identity (Item), Record_Value (Data).Identity)))
   with Global => null;

   procedure Start (Data : Header; Length : Natural; Item : out Cursor)
   with Global => null, Always_Terminates,
     Depends => (Item => (Data, Length)),
     Post => Is_Open (Item) = Header_Valid (Data, Length) and then
       not Is_Complete (Item) and then Is_Rejected (Item) = not Is_Open (Item) and then
       Consumed (Item) = 0 and then Last_Identity (Item) = Zero and then
       Expected (Item) = (if Header_Valid (Data, Length) then Header_Count (Data) else 0);

   procedure Take
     (Item : in out Cursor; Data : Record_Bytes; Length : Natural;
      Accepted : out Boolean; Value : out Record_Reference)
   with Global => null, Always_Terminates,
     Depends => (Item => (Item, Data, Length), Accepted => (Item, Data, Length),
                 Value => (Item, Data, Length)),
     Post => Expected (Item) = Expected (Item'Old) and then
       Accepted = Acceptable (Item'Old, Data, Length) and then
       (if Accepted then
           Is_Open (Item) and then Consumed (Item) = Consumed (Item'Old) + 1 and then
           Value = Record_Value (Data) and then Last_Identity (Item) = Value.Identity
        else Is_Rejected (Item) and then Consumed (Item) = Consumed (Item'Old) and then
           Last_Identity (Item) = Last_Identity (Item'Old) and then Value = Empty_Record);

   procedure Finish (Item : in out Cursor; Trailing_Bytes : Natural; Accepted : out Boolean)
   with Global => null, Always_Terminates,
     Depends => (Item => (Item, Trailing_Bytes), Accepted => (Item, Trailing_Bytes)),
     Post => Accepted = (Is_Open (Item'Old) and then
          Consumed (Item'Old) = Expected (Item'Old) and then Trailing_Bytes = 0) and then
       Is_Complete (Item) = Accepted and then Is_Rejected (Item) = not Accepted and then
       Expected (Item) = Expected (Item'Old) and then Consumed (Item) = Consumed (Item'Old) and then
       Last_Identity (Item) = Last_Identity (Item'Old);
private
   type Phase is (Open, Rejected, Complete);
   type Cursor is record
      Stage : Phase := Rejected;
      Total, Used : Input_Count := 0;
      Last : Digest := Zero;
   end record;
   function Is_Open (Item : Cursor) return Boolean is (Item.Stage = Open);
   function Is_Complete (Item : Cursor) return Boolean is (Item.Stage = Complete);
   function Is_Rejected (Item : Cursor) return Boolean is (Item.Stage = Rejected);
   function Expected (Item : Cursor) return Input_Count is (Item.Total);
   function Consumed (Item : Cursor) return Input_Count is (Item.Used);
   function Last_Identity (Item : Cursor) return Digest is (Item.Last);
end SIA_Pack_Manifest_Wire;
