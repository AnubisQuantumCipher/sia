with Ada.Command_Line;
with GNAT.OS_Lib;
with SIA_Policy; use SIA_Policy;
with SIA_Request_Wire; use SIA_Request_Wire;
with SIA_Request_Admission; use SIA_Request_Admission;
with SIA_Grant_Lifetime; use SIA_Grant_Lifetime;

--  Test-only handoff. Arguments and input are NOT authenticated authority.
--  Input: retained boot/service, current boot/service, grant/request frames.
--  Each domain is 32 bytes. EOF and an external deadline are required.
procedure Scoped_Grant_Probe is
   package CLI renames Ada.Command_Line;
   package OS renames GNAT.OS_Lib;
   Grant_Bytes, Request_Bytes : Frame := [others => 0];
   Authority : Grant;
   Retained_Domain, Current_Domain : Scope;
   Item : Request;
   Accepted : Boolean;
   Decision : Classification := Denied;
   Sender : User_Id;
   Now : Tick;

   function Arguments_Valid return Boolean is
   begin
      if CLI.Argument_Count /= 6 then
         return False;
      end if;
      for Index in 1 .. 5 loop
         declare
            Value : constant String := CLI.Argument (Index);
         begin
            if Value'Length not in 1 .. 19 or else
              (for some C of Value => C not in '0' .. '9') or else
              (Value'Length > 1 and then Value (Value'First) = '0')
            then
               return False;
            end if;
         end;
      end loop;
      return CLI.Argument (6) in "0" | "1";
   end Arguments_Valid;

   function Read_Domain (Value : out Digest) return Boolean is
      Count : Integer;
   begin
      Value := [others => 0];
      for Index in Value'Range loop
         Count := OS.Read (OS.Standin, Value (Index)'Address, 1);
         if Count /= 1 then
            return False;
         end if;
      end loop;
      return True;
   end Read_Domain;

   function Read_Pair return Boolean is
      One : Digest_Byte := 0;
      Count : Integer;
   begin
      pragma Assert (Digest_Byte'Size = 8);
      for Index in 1 .. Frame'Length * 2 loop
         Count := OS.Read (OS.Standin, One'Address, 1);
         if Count /= 1 then
            return False;
         end if;
         if Index <= Frame'Length then
            Grant_Bytes (Index) := One;
         else
            Request_Bytes (Index - Frame'Length) := One;
         end if;
      end loop;
      Count := OS.Read (OS.Standin, One'Address, 1);
      return Count = 0;
   end Read_Pair;

   procedure Write_Decision is
      Value : constant Character :=
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
   Authority.Not_Before := Tick'Value (CLI.Argument (4));
   Authority.Expires := Tick'Value (CLI.Argument (5));
   Authority.Active := CLI.Argument (6) = "1";
   if not Read_Domain (Retained_Domain.Boot) or else
     not Read_Domain (Retained_Domain.Service) or else
     not Read_Domain (Current_Domain.Boot) or else
     not Read_Domain (Current_Domain.Service) or else not Read_Pair
   then
      CLI.Set_Exit_Status (CLI.Failure);
      return;
   end if;
   Decode (Grant_Bytes, Frame'Length, Accepted, Authority.Expected);
   if Accepted then
      Decode (Request_Bytes, Frame'Length, Accepted, Item);
      if Accepted then
         Decision := Classify_Scoped
           ((Domain => Retained_Domain, Authority => Authority),
            Current_Domain, Sender, Now, Item);
      end if;
   end if;
   Write_Decision;
exception
   when Constraint_Error =>
      CLI.Set_Exit_Status (CLI.Failure);
end Scoped_Grant_Probe;
