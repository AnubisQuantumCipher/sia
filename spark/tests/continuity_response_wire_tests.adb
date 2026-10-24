with SIA_Policy;
with SIA_Continuity;
with SIA_Continuity_Transitions;
with SIA_Continuity_Frame_Wire;
with SIA_Continuity_Response_Wire;

procedure Continuity_Response_Wire_Tests with SPARK_Mode is
   use SIA_Policy;
   use SIA_Continuity;
   use SIA_Continuity_Transitions;
   use SIA_Continuity_Frame_Wire;
   use SIA_Continuity_Response_Wire;

   Malformed_Vector : constant Response_Bytes :=
     [1 => 83, 2 => 73, 3 => 65, 4 => 82, 5 | 8 => 1, others => 0];
   Restore_Vector : constant Response_Bytes :=
     [1 => 83, 2 => 73, 3 => 65, 4 => 82, 5 | 6 | 7 | 8 => 1, others => 0];
   Transition_Vector : constant Response_Bytes :=
     [1 => 83, 2 => 73, 3 => 65, 4 => 82, 5 | 8 => 1, 6 | 7 => 2, others => 0];
   Restore_Results : constant array (Restoration_Code) of Restoration :=
     [Invalid_Checkpoint, Identity_Mismatch, Stale_Checkpoint, Need_Evidence,
      Reconcile_Repository, Reconcile_Operations, References_Proposed];
   Transition_Results : constant array (Transition_Code) of Transition_Result :=
     [Invalid_Before, Invalid_After, Task_Mismatch, Predecessor_Mismatch,
      Watermark_Regression, Operation_Lost, Unsupported_Change,
      Need_Transition_Evidence, Transition_Proposed];

   procedure Refuse (Bytes : Response_Bytes)
   with Global => null, Always_Terminates, Pre => not Valid (Bytes)
   is
      Accepted : Boolean;
      Item : Frame_Decision :=
        (Transition_Request, References_Proposed, Transition_Proposed);
   begin
      Decode (Bytes, Accepted, Item);
      pragma Assert (not Accepted and then Item =
        Frame_Decision'(Malformed, Invalid_Checkpoint, Invalid_Before));
      for Kind in Request_Kind loop
         pragma Assert (not Matches (Bytes, Kind, 0));
         pragma Assert (not Matches (Bytes, Kind, 65));
      end loop;
   end Refuse;

   procedure Check_Literal_Results with Global => null, Always_Terminates is
      Accepted : Boolean;
      Item : Frame_Decision;
   begin
      --  Independent wire literals and protocol-code expectations, not just
      --  an encoder/decoder round trip sharing the same mapping.
      Decode (Malformed_Vector, Accepted, Item);
      pragma Assert (Accepted and then Item =
        Frame_Decision'(Malformed, Invalid_Checkpoint, Invalid_Before));
      for Value in Restoration_Code loop
         Decode ((Restore_Vector with delta 8 => Value), Accepted, Item);
         pragma Assert (Accepted and then Item = Frame_Decision'(
           Restore_Request, Restore_Results (Value), Invalid_Before));
         pragma Assert (Encode (Item) =
           Response_Bytes'(Restore_Vector with delta 8 => Value));
      end loop;
      for Value in Transition_Code loop
         Decode ((Transition_Vector with delta 8 => Value), Accepted, Item);
         pragma Assert (Accepted and then Item = Frame_Decision'(
           Transition_Request, Invalid_Checkpoint, Transition_Results (Value)));
         pragma Assert (Encode (Item) =
           Response_Bytes'(Transition_Vector with delta 8 => Value));
      end loop;
   end Check_Literal_Results;

   procedure Check_Unused_Values (R : Restoration; T : Transition_Result)
   with Global => null, Always_Terminates is
      Accepted : Boolean;
      Item : Frame_Decision;
      Bytes : Response_Bytes;
   begin
      Bytes := Encode ((Malformed, R, T));
      pragma Assert (Bytes = Malformed_Vector);
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item =
        Frame_Decision'(Malformed, Invalid_Checkpoint, Invalid_Before));
      Bytes := Encode ((Restore_Request, R, T));
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item =
        Frame_Decision'(Restore_Request, R, Invalid_Before));
      Bytes := Encode ((Transition_Request, R, T));
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item =
        Frame_Decision'(Transition_Request, Invalid_Checkpoint, T));
   end Check_Unused_Values;

   procedure Check_Unused_Families with Global => null, Always_Terminates is
   begin
      for R in Restoration loop
         for T in Transition_Result loop
            Check_Unused_Values (R, T);
         end loop;
      end loop;
   end Check_Unused_Families;

   procedure Check_Header with Global => null, Always_Terminates is
   begin
      Refuse ([others => 0]);
      for I in 1 .. 5 loop
         for Value in Digest_Byte loop
            if Value /= Malformed_Vector (I) then
               Refuse ((Malformed_Vector with delta I => Value));
               Refuse ((Restore_Vector with delta I => Value));
               Refuse ((Transition_Vector with delta I => Value));
            end if;
         end loop;
      end loop;
      for Value in Digest_Byte loop
         if Value /= 0 then
            Refuse ((Malformed_Vector with delta 6 => Value));
            Refuse ((Malformed_Vector with delta 7 => Value));
         end if;
         if Value /= 1 then
            Refuse ((Restore_Vector with delta 6 => Value));
            Refuse ((Restore_Vector with delta 7 => Value));
         end if;
         if Value /= 2 then
            Refuse ((Transition_Vector with delta 6 => Value));
            Refuse ((Transition_Vector with delta 7 => Value));
         end if;
      end loop;
   end Check_Header;

   procedure Check_Codes with Global => null, Always_Terminates is
      Accepted : Boolean;
      Item : Frame_Decision;
   begin
      for Value in Digest_Byte loop
         if Value /= 1 then
            Refuse ((Malformed_Vector with delta 8 => Value));
         end if;
         Decode ((Restore_Vector with delta 8 => Value), Accepted, Item);
         pragma Assert (Accepted = (Value in 1 .. 7));
         if Value not in 1 .. 7 then
            pragma Assert (Item = Frame_Decision'(
              Malformed, Invalid_Checkpoint, Invalid_Before));
         end if;
         Decode ((Transition_Vector with delta 8 => Value), Accepted, Item);
         pragma Assert (Accepted = (Value in 1 .. 9));
         if Value not in 1 .. 9 then
            pragma Assert (Item = Frame_Decision'(
              Malformed, Invalid_Checkpoint, Invalid_Before));
         end if;
      end loop;
   end Check_Codes;

   procedure Check_Reserved with Global => null, Always_Terminates is
   begin
      for I in 9 .. 64 loop
         for Value in Digest_Byte range 1 .. 255 loop
            Refuse ((Malformed_Vector with delta I => Value));
            Refuse ((Restore_Vector with delta I => Value));
            Refuse ((Transition_Vector with delta I => Value));
         end loop;
      end loop;
   end Check_Reserved;

   procedure Check_Process_Correlation
   with Global => null, Always_Terminates is
      Bytes : Response_Bytes;
   begin
      for Value in Restoration_Code loop
         Bytes := (Restore_Vector with delta 8 => Value);
         for Status in 0 .. 255 loop
            pragma Assert (Matches (Bytes, Restore_Request, Status) =
                           (Status = 0));
            pragma Assert (not Matches (Bytes, Transition_Request, Status));
            pragma Assert (not Matches (Bytes, Malformed, Status));
         end loop;
      end loop;
      for Value in Transition_Code loop
         Bytes := (Transition_Vector with delta 8 => Value);
         for Status in 0 .. 255 loop
            pragma Assert (Matches (Bytes, Transition_Request, Status) =
                           (Status = 0));
            pragma Assert (not Matches (Bytes, Restore_Request, Status));
            pragma Assert (not Matches (Bytes, Malformed, Status));
         end loop;
      end loop;
      for Status in 0 .. 255 loop
         pragma Assert (Matches (Malformed_Vector, Malformed, Status) =
                        (Status = 65));
         pragma Assert (not Matches (Malformed_Vector, Restore_Request, Status));
         pragma Assert
           (not Matches (Malformed_Vector, Transition_Request, Status));
      end loop;
      for Kind in Request_Kind loop
         pragma Assert (not Matches (Malformed_Vector, Kind, Integer'First));
         pragma Assert (not Matches (Restore_Vector, Kind, Integer'Last));
         pragma Assert (not Matches (Transition_Vector, Kind, -1));
      end loop;
   end Check_Process_Correlation;
begin
   Check_Literal_Results;
   Check_Unused_Families;
   Check_Header;
   Check_Codes;
   Check_Reserved;
   Check_Process_Correlation;
end Continuity_Response_Wire_Tests;
