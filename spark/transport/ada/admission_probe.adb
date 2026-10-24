with Ada.Command_Line;
with GNAT.OS_Lib;
with SIA_Policy; use SIA_Policy;
with SIA_Request_Wire; use SIA_Request_Wire;
with SIA_Request_Admission; use SIA_Request_Admission;

--  Test-only fixture. Command-line credentials/grants are NOT authenticated.
--  The parent test supplies a deadline. No effect handler exists here.
procedure Admission_Probe is
   package CLI renames Ada.Command_Line;
   package OS renames GNAT.OS_Lib;
   Bytes : Frame := [others => 0];
   Length : Natural := 0;
   Item : Request;
   Decision : Classification;
   Sender : User_Id;
   Now : Tick;
   Authority : Grant :=
     (Active => True, Subject => 0, Not_Before => 10, Expires => 20,
      Expected =>
        (Action => Propose, Before_Phase => 2, After_Phase => 3,
         Capability => [others => 1], Source => [others => 2],
         Transaction => [others => 3], Payload => [others => 4],
         Predecessor_Receipt => [others => 5],
         Before_Generation => 6, Target_Generation => 7));

   function Arguments_Valid return Boolean is
   begin
      if CLI.Argument_Count /= 4 then
         return False;
      end if;
      for Index in 1 .. 3 loop
         declare
            Value : constant String := CLI.Argument (Index);
         begin
            if Value'Length not in 1 .. 19 or else
              (for some C of Value => C not in '0' .. '9')
            then
               return False;
            end if;
         end;
      end loop;
      return CLI.Argument (4) in "observe" | "propose";
   end Arguments_Valid;

   function Read_Frame return Boolean is
      One : Digest_Byte := 0;
      Count : Integer;
   begin
      pragma Assert (Digest_Byte'Size = 8);
      for Index in 1 .. 193 loop
         Count := OS.Read (OS.Standin, One'Address, 1);
         exit when Count = 0;
         if Count /= 1 then
            return False;
         end if;
         Length := Index;
         if Index <= Frame'Last then
            Bytes (Index) := One;
         end if;
      end loop;
      return True;
   end Read_Frame;

   procedure Write_Decision is
      Value : aliased Character :=
        (case Decision is
           when Denied => 'D', when Observe_Only => 'O',
           when Proposal_Only => 'P');
      Count : Integer;
   begin
      Count := OS.Write (OS.Standout, Value'Address, 1);
      if Count /= 1 then
         CLI.Set_Exit_Status (CLI.Failure);
      end if;
   end Write_Decision;
begin
   if not Arguments_Valid then
      CLI.Set_Exit_Status (CLI.Failure);
      return;
   end if;
   Authority.Subject := User_Id'Value (CLI.Argument (1));
   Sender := User_Id'Value (CLI.Argument (2));
   Now := Tick'Value (CLI.Argument (3));
   Authority.Expected.Action :=
     (if CLI.Argument (4) = "observe" then Observe else Propose);
   if not Read_Frame then
      CLI.Set_Exit_Status (CLI.Failure);
      return;
   end if;
   Classify_Frame (Authority, Sender, Now, Bytes, Length, Item, Decision);
   pragma Assert
     (if Valid (Bytes, Length) then Decoded_As (Bytes, Length, Item)
      else Item = Empty_Request);
   Write_Decision;
exception
   when Constraint_Error =>
      CLI.Set_Exit_Status (CLI.Failure);
end Admission_Probe;
