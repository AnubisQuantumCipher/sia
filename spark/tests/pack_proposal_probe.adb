with Ada.Command_Line;
with Ada.Exceptions;
with Ada.Sequential_IO;
with Ada.Text_IO;
with SIA_Policy;
with SIA_Pack_Retirement;
with SIA_Pack_Plan_Wire;
with SIA_Pack_Manifest_Wire;
with SIA_Pack_Partition;
with SIA_Pack_Proposal;
with Pack_Plan_Wire_Test_Support;

--  Test-only file adapter. No deployment, privilege or authentication boundary.
procedure Pack_Proposal_Probe with SPARK_Mode => Off is
   use SIA_Policy;
   use SIA_Pack_Retirement;
   use SIA_Pack_Plan_Wire;
   package Byte_IO is new Ada.Sequential_IO (Digest_Byte);
   package Manifest renames SIA_Pack_Manifest_Wire;
   package Partition renames SIA_Pack_Partition;
   package Gate renames SIA_Pack_Proposal;
   use type Ada.Exceptions.Exception_Id;

   procedure Read_Header
     (Input : Byte_IO.File_Type; Data : out Manifest.Header;
      Length : out Natural) is
   begin
      Data := [others => 0];
      Length := 0;
      for I in Data'Range loop
         exit when Byte_IO.End_Of_File (Input);
         Byte_IO.Read (Input, Data (I));
         Length := I;
      end loop;
   end Read_Header;

   procedure Read_Record
     (Input : Byte_IO.File_Type; Data : out Manifest.Record_Bytes;
      Length : out Natural) is
   begin
      Data := [others => 0];
      Length := 0;
      for I in Data'Range loop
         exit when Byte_IO.End_Of_File (Input);
         Byte_IO.Read (Input, Data (I));
         Length := I;
      end loop;
   end Read_Record;

   function Consume
     (Candidate : Plan; Selection, Fallback : Byte_IO.File_Type)
      return Boolean is
      Selected_Header, Fallback_Header : Manifest.Header;
      Selected_Row, Fallback_Row : Manifest.Record_Bytes;
      Selected_Length, Fallback_Length : Natural;
      Item : Gate.State;
      Accepted : Boolean;
      Result : Plan;
   begin
      Read_Header (Selection, Selected_Header, Selected_Length);
      Read_Header (Fallback, Fallback_Header, Fallback_Length);
      Gate.Start (Candidate, Selected_Header, Fallback_Header,
                  Selected_Length, Fallback_Length, Item);
      if not Gate.Running (Item) then
         return False;
      end if;
      for I in 1 .. Candidate.Selected loop
         pragma Assert
           (Manifest.Consumed (Partition.Selected (Gate.Streams (Item))) = I - 1);
         Read_Record (Selection, Selected_Row, Selected_Length);
         Fallback_Row := [others => 0];
         Fallback_Length := 0;
         if Manifest.Record_Valid (Selected_Row, Selected_Length) and then
           not Partition.Next_Is_Represented
             (Gate.Streams (Item), Manifest.Record_Value (Selected_Row))
         then
            Read_Record (Fallback, Fallback_Row, Fallback_Length);
         end if;
         Gate.Take (Item, Selected_Row, Fallback_Row,
                    Selected_Length, Fallback_Length, Accepted);
         if not Accepted then
            return False;
         end if;
      end loop;
      Gate.Finish (Item, Boolean'Pos (not Byte_IO.End_Of_File (Selection)),
                   Boolean'Pos (not Byte_IO.End_Of_File (Fallback)), Accepted, Result);
      if Result /= (if Accepted then Candidate else Empty_Plan) then
         raise Program_Error with "stream result differs from admission";
      end if;
      return Accepted;
   end Consume;

   procedure Close_Input (Input : in out Byte_IO.File_Type) is
   begin
      if Byte_IO.Is_Open (Input) then
         Byte_IO.Close (Input);
         if Byte_IO.Is_Open (Input) then
            raise Program_Error with "manifest input remains open";
         end if;
      end if;
   end Close_Input;

   procedure Capture_Close
     (Input : in out Byte_IO.File_Type;
      Failure : out Ada.Exceptions.Exception_Occurrence) is
   begin
      Ada.Exceptions.Save_Occurrence (Failure, Ada.Exceptions.Null_Occurrence);
      Close_Input (Input);
   exception
      when Problem : others =>
         Ada.Exceptions.Save_Occurrence (Failure, Problem);
   end Capture_Close;

   procedure Report
     (Label : String; Failure : Ada.Exceptions.Exception_Occurrence) is
   begin
      if Ada.Exceptions.Exception_Identity (Failure) /= Ada.Exceptions.Null_Id then
         Ada.Text_IO.Put_Line
           (Ada.Text_IO.Standard_Error,
            Label & ": " & Ada.Exceptions.Exception_Information (Failure));
      end if;
   end Report;

   procedure Close_Streams
     (Selection, Fallback : in out Byte_IO.File_Type;
      Primary : Ada.Exceptions.Exception_Occurrence) is
      Fallback_Error, Selection_Error : Ada.Exceptions.Exception_Occurrence;
   begin
      --  Attempt both before reporting or re-raising any failure.
      Capture_Close (Fallback, Fallback_Error);
      Capture_Close (Selection, Selection_Error);
      Report ("primary input failure", Primary);
      Report ("fallback cleanup failure", Fallback_Error);
      Report ("selection cleanup failure", Selection_Error);
      if Ada.Exceptions.Exception_Identity (Primary) /= Ada.Exceptions.Null_Id then
         Ada.Exceptions.Reraise_Occurrence (Primary);
      elsif Ada.Exceptions.Exception_Identity (Fallback_Error) /= Ada.Exceptions.Null_Id then
         Ada.Exceptions.Reraise_Occurrence (Fallback_Error);
      elsif Ada.Exceptions.Exception_Identity (Selection_Error) /= Ada.Exceptions.Null_Id then
         Ada.Exceptions.Reraise_Occurrence (Selection_Error);
      end if;
   end Close_Streams;

   function Streams_Admit (Candidate : Plan) return Boolean is
      Selection, Fallback : Byte_IO.File_Type;
      Accepted : Boolean;
   begin
      begin
         Byte_IO.Open (Selection, Byte_IO.In_File, Ada.Command_Line.Argument (2));
         Byte_IO.Open (Fallback, Byte_IO.In_File, Ada.Command_Line.Argument (3));
         Accepted := Consume (Candidate, Selection, Fallback);
      exception
         when Problem : others =>
            Close_Streams (Selection, Fallback, Problem);
            raise;
      end;
      Close_Streams (Selection, Fallback, Ada.Exceptions.Null_Occurrence);
      if Byte_IO.Is_Open (Selection) or else Byte_IO.Is_Open (Fallback) then
         raise Program_Error with "manifest cleanup incomplete";
      end if;
      return Accepted;
   end Streams_Admit;

   procedure Load (Data : out Frame) is
      Input, Unused : Byte_IO.File_Type;
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
         when Problem : others =>
            Close_Streams (Input, Unused, Problem);
            raise;
      end;
      Close_Streams (Input, Unused, Ada.Exceptions.Null_Occurrence);
      if Byte_IO.Is_Open (Input) or else Byte_IO.Is_Open (Unused) then
         raise Program_Error with "proposal cleanup incomplete";
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
   if Ada.Command_Line.Argument_Count not in 1 | 3 then
      raise Constraint_Error with "proposal, optionally selection and fallback, required";
   end if;
   Load (Data);
   Decode (Data, Data'Length, Accepted, Item);
   if Accepted and then Ada.Command_Line.Argument_Count = 3 then
      Accepted := Streams_Admit (Item);
      if not Accepted then
         Item := Empty_Plan;
      end if;
   end if;
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
