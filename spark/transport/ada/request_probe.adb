with Ada.Streams; use Ada.Streams;
with Ada.Command_Line;
with GNAT.OS_Lib;
with SIA_Policy; use SIA_Policy;
with SIA_Request_Wire; use SIA_Request_Wire;

--  Test-only Linux I/O adapter. Runtime I/O and this serialization are not
--  SPARK-proved. The test owner enforces a deadline and closes input at EOF.
procedure Request_Probe is
   package OS renames GNAT.OS_Lib;
   Bytes : Frame := [others => 0];
   Response : Stream_Element_Array (1 .. 193) := [others => 0];
   Length : Natural := 0;
   Accepted : Boolean;
   Item : Request;
   IO_OK : Boolean := True;

   procedure Read_Frame is
      One : Stream_Element := 0;
      Count : Integer;
   begin
      pragma Assert (Stream_Element'Size = 8);
      for Index in 1 .. 193 loop
         Count := OS.Read (OS.Standin, One'Address, 1);
         exit when Count = 0;
         if Count /= 1 then
            IO_OK := False;
            return;
         end if;
         Length := Index;
         if Index <= 192 then
            Bytes (Index) := Digest_Byte (One);
         end if;
      end loop;
   end Read_Frame;

   procedure Write_Response is
      Position : Stream_Element_Offset := Response'First;
      Count, Remaining : Integer;
   begin
      for Attempt in 1 .. 193 loop
         exit when Position > Response'Last;
         Remaining := Integer (Response'Last - Position + 1);
         Count := OS.Write (OS.Standout, Response (Position)'Address, Remaining);
         if Count <= 0 or else Count > Remaining then
            IO_OK := False;
            return;
         end if;
         Position := Position + Stream_Element_Offset (Count);
      end loop;
      IO_OK := Position > Response'Last;
   end Write_Response;

   procedure Put_Digest (Start : Stream_Element_Offset; Value : Digest) is
   begin
      for Index in Value'Range loop
         Response (Start + Stream_Element_Offset (Index - 1)) :=
           Stream_Element (Value (Index));
      end loop;
   end Put_Digest;

   procedure Put_Generation
     (Start : Stream_Element_Offset; Value : Generation)
   is
      Remaining : Generation := Value;
   begin
      for Offset in reverse Stream_Element_Offset range 0 .. 7 loop
         Response (Start + Offset) := Stream_Element (Remaining mod 256);
         Remaining := Remaining / 256;
      end loop;
   end Put_Generation;

   procedure Encode_Result is
   begin
      if not Accepted then
         return;
      end if;
      Response (1) := 1;
      Response (2) := 1;
      Response (3) := (if Item.Action = Observe then 1 else 2);
      Response (4) := Stream_Element (Item.Before_Phase);
      Response (5) := Stream_Element (Item.After_Phase);
      Put_Digest (10, Item.Capability);
      Put_Digest (42, Item.Source);
      Put_Digest (74, Item.Transaction);
      Put_Digest (106, Item.Payload);
      Put_Digest (138, Item.Predecessor_Receipt);
      Put_Generation (170, Item.Before_Generation);
      Put_Generation (178, Item.Target_Generation);
   end Encode_Result;
begin
   Read_Frame;
   if not IO_OK then
      Ada.Command_Line.Set_Exit_Status (Ada.Command_Line.Failure);
      return;
   end if;
   Decode (Bytes, Length, Accepted, Item);
   Encode_Result;
   Write_Response;
   if not IO_OK then
      Ada.Command_Line.Set_Exit_Status (Ada.Command_Line.Failure);
   end if;
end Request_Probe;
