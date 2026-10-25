with Ada.Command_Line;
with Ada.Sequential_IO;
with Ada.Text_IO;
with SIA_Policy;
with SIA_Pack_Retirement;
with SIA_Pack_Plan_Wire;
with Pack_Plan_Wire_Test_Support;

--  Test-only file adapter. No deployment, privilege or authentication boundary.
procedure Pack_Proposal_Probe with SPARK_Mode => Off is
   use SIA_Policy;
   use SIA_Pack_Retirement;
   use SIA_Pack_Plan_Wire;
   package Byte_IO is new Ada.Sequential_IO (Digest_Byte);

   procedure Load (Data : out Frame) is
      Input : Byte_IO.File_Type;
   begin
      Byte_IO.Open (Input, Byte_IO.In_File, Ada.Command_Line.Argument (1));
      begin
         for I in Data'Range loop
            if Byte_IO.End_Of_File (Input) then
               raise Constraint_Error with "short proposal";
            end if;
            Byte_IO.Read (Input, Data (I));
         end loop;
         if not Byte_IO.End_Of_File (Input) then
            raise Constraint_Error with "trailing proposal bytes";
         end if;
      exception
         when others =>
            Byte_IO.Close (Input);
            if Byte_IO.Is_Open (Input) then
               raise Program_Error with "proposal input remains open";
            end if;
            raise;
      end;
      Byte_IO.Close (Input);
      if Byte_IO.Is_Open (Input) then
         raise Program_Error with "proposal input remains open";
      end if;
   end Load;

   procedure Print_Hex (Data : Frame) is
      Hex_Digits : constant String := "0123456789abcdef";
   begin
      for Value of Data loop
         Ada.Text_IO.Put (Hex_Digits (Natural (Value / 16) + 1));
         Ada.Text_IO.Put (Hex_Digits (Natural (Value mod 16) + 1));
      end loop;
      Ada.Text_IO.New_Line;
   end Print_Hex;

   Data : Frame;
   Accepted : Boolean;
   Item : Plan;
begin
   if Ada.Command_Line.Argument_Count /= 1 then
      raise Constraint_Error with "one proposal file required";
   end if;
   Load (Data);
   Decode (Data, Data'Length, Accepted, Item);
   if Accepted then
      Ada.Text_IO.Put_Line ("ACCEPTED");
      Print_Hex (Pack_Plan_Wire_Test_Support.Encode_Oracle (Item));
   else
      if Item /= Empty_Plan then
         raise Program_Error with "refusal did not clear output";
      end if;
      Ada.Text_IO.Put_Line ("REFUSED");
   end if;
end Pack_Proposal_Probe;
