with Ada.Command_Line;
with GNAT.OS_Lib;
with SIA_Policy;
with SIA_Continuity_Frame_Wire;
with SIA_Continuity_Response_Wire;

--  Test-only Linux descriptor adapter, outside the SPARK proof boundary.
--  The supervising parent bounds resources, ignores SIGPIPE and closes input.
procedure Continuity_Probe is
   package OS renames GNAT.OS_Lib;
   package Requests renames SIA_Continuity_Frame_Wire;
   package Responses renames SIA_Continuity_Response_Wire;
   use type Requests.Request_Kind;
   Input : Requests.Frame_Bytes := [others => 0];
   Output : Responses.Response_Bytes;
   Item : Requests.Decoded_Request;
   Result : Requests.Frame_Decision;
   Accepted : Boolean;
   Length : Natural := 0;
   IO_OK : Boolean := True;

   procedure Read_Frame is
      Count, Remaining : Integer;
      Sentinel : aliased SIA_Policy.Digest_Byte := 0;
   begin
      --  At most one read per byte plus one sentinel read. Each positive read
      --  advances Length. Blocking syscalls still require the parent deadline.
      for Attempt in 1 .. Requests.Frame_Bytes'Length + 1 loop
         if Length = Requests.Frame_Bytes'Length then
            Count := OS.Read (OS.Standin, Sentinel'Address, 1);
            if Count = 1 then
               Length := Length + 1;
            elsif Count /= 0 then
               IO_OK := False;
            end if;
            return;
         end if;
         Remaining := Requests.Frame_Bytes'Length - Length;
         Count := OS.Read (OS.Standin, Input (Length + 1)'Address, Remaining);
         if Count = 0 then
            return;
         elsif Count < 0 or else Count > Remaining then
            IO_OK := False;
            return;
         end if;
         Length := Length + Count;
      end loop;
      IO_OK := False;
   end Read_Frame;

   procedure Write_Response is
      Position : Natural := 0;
      Count, Remaining : Integer;
   begin
      for Attempt in 1 .. Responses.Response_Bytes'Length loop
         Remaining := Responses.Response_Bytes'Length - Position;
         Count := OS.Write (OS.Standout, Output (Position + 1)'Address, Remaining);
         if Count <= 0 or else Count > Remaining then
            IO_OK := False;
            return;
         end if;
         Position := Position + Count;
         if Position = Responses.Response_Bytes'Length then
            return;
         end if;
      end loop;
      IO_OK := False;
   end Write_Response;
begin
   pragma Assert (SIA_Policy.Digest_Byte'Size = 8);
   Read_Frame;
   if not IO_OK then
      Ada.Command_Line.Set_Exit_Status (74);
      return;
   end if;
   if Length = Requests.Frame_Bytes'Length then
      Requests.Evaluate (Input, Accepted, Item, Result);
      pragma Assert (Accepted = (Result.Kind /= Requests.Malformed));
   else
      Result := Requests.Classify (Requests.Empty_Request);
   end if;
   Output := Responses.Encode (Result);
   Write_Response;
   Ada.Command_Line.Set_Exit_Status
     (if IO_OK then Ada.Command_Line.Exit_Status
        (Responses.Expected_Exit (Result.Kind)) else 74);
end Continuity_Probe;
