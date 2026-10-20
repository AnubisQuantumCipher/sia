with SIA_Policy;
with SIA_Continuity;
with SIA_Continuity_Record_Wire;

procedure Continuity_Record_Wire_Tests with SPARK_Mode is
   use SIA_Policy;
   use SIA_Continuity;
   use SIA_Continuity_Record_Wire;

   Expected_Kinds : constant array (Kind_Code) of Claim_Kind :=
     [Goal, Acceptance, Constraint, Correction, Decision, Rejection, Source,
      Completed, Verification, Failure, Next_Action, Permission_Reference,
      Pending_Approval];
   Expected_Origins : constant array (Origin_Code) of Origin :=
     [Source_Record, Derived_Record, Model_Record, Legacy_Record];
   Expected_Roles : constant array (Role_Code) of Role :=
     [User, Assistant, Tool, System_Role];
   Expected_Phases : constant array (Phase_Code) of Operation_Phase :=
     [Planned, Dispatched, Uncertain, Observed_Complete, Acknowledged];
   First_Digest : constant Digest :=
     [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
      17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32];
   Second_Digest : constant Digest :=
     [33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48,
      49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64];
   Third_Digest : constant Digest :=
     [65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80,
      81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96];
   Fourth_Digest : constant Digest :=
     [97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110,
      111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124,
      125, 126, 127, 128];

   procedure Check_Digest_Fields with Global => null, Always_Terminates is
      Claim_Data : Claim_Bytes := [others => 0];
      Operation_Data : Operation_Bytes := [others => 0];
      Witness_Data : Witness_Bytes := [others => 0];
      Claim_Item : Claim;
      Operation_Item : SIA_Continuity.Operation;
      Witness_Item : Witness;
      Accepted : Boolean;
   begin
      for I in Digest'Range loop
         Claim_Data := (Claim_Data with delta
           I => First_Digest (I), 32 + I => Second_Digest (I),
           64 + I => Third_Digest (I));
         Operation_Data := (Operation_Data with delta
           I => First_Digest (I), 32 + I => Second_Digest (I),
           64 + I => Third_Digest (I), 96 + I => Fourth_Digest (I));
         Witness_Data := (Witness_Data with delta 10 + I => Fourth_Digest (I));
         pragma Loop_Invariant
           (Valid (Claim_Data) and then Valid (Operation_Data) and then
            Valid (Witness_Data));
         pragma Loop_Invariant
           (for all J in 1 .. I =>
              Claim_Data (J) = First_Digest (J) and then
              Claim_Data (32 + J) = Second_Digest (J) and then
              Claim_Data (64 + J) = Third_Digest (J) and then
              Operation_Data (J) = First_Digest (J) and then
              Operation_Data (32 + J) = Second_Digest (J) and then
              Operation_Data (64 + J) = Third_Digest (J) and then
              Operation_Data (96 + J) = Fourth_Digest (J) and then
              Witness_Data (10 + J) = Fourth_Digest (J));
      end loop;
      Decode (Claim_Data, Accepted, Claim_Item);
      pragma Assert (Accepted and then Claim_Item.Identity = First_Digest
                     and then Claim_Item.Slot = Second_Digest and then
                     Claim_Item.Source_Record_Id = Third_Digest);
      Decode (Operation_Data, Accepted, Operation_Item);
      pragma Assert (Accepted and then Operation_Item.Identity = First_Digest
                     and then Operation_Item.Action = Second_Digest and then
                     Operation_Item.Source_Record_Id = Third_Digest and then
                     Operation_Item.Result_Record_Id = Fourth_Digest);
      Decode (Witness_Data, Accepted, Witness_Item);
      pragma Assert
        (Accepted and then Witness_Item.Bound_To.Transaction = Fourth_Digest);
   end Check_Digest_Fields;

   procedure Check_Claim_Values with Global => null, Always_Terminates is
      Bytes : Claim_Bytes := [others => 0];
      Item : Claim;
      Accepted : Boolean;
   begin
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item /= Empty_Claim);
      pragma Assert (Item.From = Source_Record and then Item.Speaker = User);
      pragma Assert (not Valid_Claim (Item));
      Bytes (106) := 3;
      Bytes (107) := 2;
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item = Empty_Claim);
      Bytes := [1 .. 32 => 17, 33 .. 64 => 34,
                97 => 1, 98 => 2, 99 => 3, 100 => 4, 101 => 5, 102 => 6,
                103 => 7, 104 => 8, 105 => 11, 108 => 64, others => 0];
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item.Identity = Digest'[others => 17]);
      pragma Assert (Item.Slot = Digest'[others => 34]);
      pragma Assert (Item.Source_Record_Id = Zero);
      pragma Assert (Item.Sequence = 16#0102_0304_0506_0708#);
      pragma Assert (Item.Kind = Permission_Reference and then
                     Item.From = Source_Record and then Item.Speaker = User);
      pragma Assert (Item.Replaces = 64);
      Bytes (106) := 2;
      Bytes (107) := 1;
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then not Valid_Claim (Item));
      pragma Assert (Item.Kind = Permission_Reference and then
                     Item.From = Model_Record and then Item.Speaker = Assistant);
   end Check_Claim_Values;

   procedure Check_Claim_Codes with Global => null, Always_Terminates is
      Bytes : Claim_Bytes;
      Item : Claim;
      Accepted : Boolean;
   begin
      for Code in Digest_Byte loop
         Bytes := [105 => Code, others => 0];
         Decode (Bytes, Accepted, Item);
         pragma Assert (Accepted = (Code <= 12));
         pragma Assert
           (if Accepted then Item.Kind = Expected_Kinds (Code)
            else Item = Empty_Claim);
         Bytes := [106 => Code, others => 0];
         Decode (Bytes, Accepted, Item);
         pragma Assert (Accepted = (Code <= 3));
         pragma Assert
           (if Accepted then Item.From = Expected_Origins (Code)
            else Item = Empty_Claim);
         Bytes := [107 => Code, others => 0];
         Decode (Bytes, Accepted, Item);
         pragma Assert (Accepted = (Code <= 3));
         pragma Assert
           (if Accepted then Item.Speaker = Expected_Roles (Code)
            else Item = Empty_Claim);
         Bytes := [108 => Code, others => 0];
         Decode (Bytes, Accepted, Item);
         pragma Assert (Accepted = (Code <= 64));
         pragma Assert
           (if Accepted then Item.Replaces = Natural (Code)
            else Item = Empty_Claim);
      end loop;
   end Check_Claim_Codes;

   procedure Check_Generations with Global => null, Always_Terminates is
      Claim_Data : Claim_Bytes;
      Witness_Data : Witness_Bytes;
      Claim_Item : Claim;
      Witness_Item : Witness;
      Accepted : Boolean;
   begin
      for Code in Digest_Byte loop
         Claim_Data := [97 => Code, others => 0];
         Decode (Claim_Data, Accepted, Claim_Item);
         pragma Assert (Accepted = (Code <= 127));
         pragma Assert (if not Accepted then Claim_Item = Empty_Claim);
         Witness_Data := [3 => Code, others => 0];
         Decode (Witness_Data, Accepted, Witness_Item);
         pragma Assert (Accepted = (Code <= 127));
         pragma Assert (if not Accepted then Witness_Item = Empty_Witness);
      end loop;
      Claim_Data := [97 => 127, 98 .. 104 => 255, others => 0];
      Decode (Claim_Data, Accepted, Claim_Item);
      pragma Assert (Accepted and then Claim_Item.Sequence = Generation'Last);
      Witness_Data := [3 => 127, 4 .. 10 => 255, others => 0];
      Decode (Witness_Data, Accepted, Witness_Item);
      pragma Assert
        (Accepted and then Witness_Item.Bound_To.Epoch = Generation'Last);
   end Check_Generations;

   procedure Check_Operation_Values with Global => null, Always_Terminates is
      Bytes : Operation_Bytes := [others => 0];
      Item : SIA_Continuity.Operation;
      Accepted : Boolean;
   begin
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item = Empty_Operation);
      Bytes := [1 .. 32 => 17, 33 .. 64 => 34, 65 .. 96 => 51,
                129 => 4, 130 => 1, others => 0];
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Valid_Operation (Item));
      pragma Assert (Item.Identity = Digest'[others => 17] and then
                     Item.Action = Digest'[others => 34] and then
                     Item.Source_Record_Id = Digest'[others => 51]);
      pragma Assert (Item.Stage = Acknowledged and then Item.Has_Result
                     and then Item.Result_Record_Id = Zero);
      Bytes (130) := 0;
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then not Valid_Operation (Item));
      pragma Assert (Item.Stage = Acknowledged and then not Item.Has_Result);
      Bytes (129) := 0;
      Bytes (97) := 255;
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then not Valid_Operation (Item));
      pragma Assert (Item.Result_Record_Id (1) = 255);
   end Check_Operation_Values;

   procedure Check_Operation_Codes with Global => null, Always_Terminates is
      Bytes : Operation_Bytes;
      Item : SIA_Continuity.Operation;
      Accepted : Boolean;
   begin
      for Code in Digest_Byte loop
         Bytes := [129 => Code, others => 0];
         Decode (Bytes, Accepted, Item);
         pragma Assert (Accepted = (Code <= 4));
         pragma Assert
           (if Accepted then Item.Stage = Expected_Phases (Code)
            else Item = Empty_Operation);
         Bytes := [130 => Code, others => 0];
         Decode (Bytes, Accepted, Item);
         pragma Assert (Accepted = (Code <= 1));
         pragma Assert
           (if Accepted then Item.Has_Result = (Code = 1)
            else Item = Empty_Operation);
      end loop;
   end Check_Operation_Codes;

   procedure Check_Witness with Global => null, Always_Terminates is
      Bytes : Witness_Bytes;
      Item : Witness;
      Accepted : Boolean;
   begin
      for Code in Digest_Byte loop
         Bytes := [1 => Code, others => 0];
         Decode (Bytes, Accepted, Item);
         pragma Assert (Accepted = (Code <= 1));
         pragma Assert
           (if Accepted then Item.Present = (Code = 1)
            else Item = Empty_Witness);
         Bytes := [2 => Code, others => 0];
         Decode (Bytes, Accepted, Item);
         pragma Assert (Accepted = (Code <= 1));
         pragma Assert
           (if Accepted then Item.Durable = (Code = 1)
            else Item = Empty_Witness);
      end loop;
      Bytes := [2 => 1, 3 => 1, 4 => 2, 5 => 3, 6 => 4,
                7 => 5, 8 => 6, 9 => 7, 10 => 8, 11 .. 42 => 51,
                others => 0];
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then not Item.Present and then Item.Durable);
      pragma Assert (Item.Bound_To.Epoch = 16#0102_0304_0506_0708#);
      pragma Assert (Item.Bound_To.Transaction = Digest'[others => 51]);
      pragma Assert (not Bound_Durable (Item, Item.Bound_To));
   end Check_Witness;

   procedure Check_Claim_Reserved with Global => null, Always_Terminates is
      Bytes : Claim_Bytes;
      Item : Claim;
      Accepted : Boolean;
   begin
      for Index in 109 .. 128 loop
         for Code in Digest_Byte range 1 .. 255 loop
            Bytes := (Claim_Bytes'[others => 0] with delta Index => Code);
            Decode (Bytes, Accepted, Item);
            pragma Assert (not Accepted and then Item = Empty_Claim);
         end loop;
      end loop;
   end Check_Claim_Reserved;

   procedure Check_Operation_Reserved with Global => null, Always_Terminates is
      Bytes : Operation_Bytes;
      Item : SIA_Continuity.Operation;
      Accepted : Boolean;
   begin
      for Index in 131 .. 144 loop
         for Code in Digest_Byte range 1 .. 255 loop
            Bytes := (Operation_Bytes'[others => 0] with delta Index => Code);
            Decode (Bytes, Accepted, Item);
            pragma Assert (not Accepted and then Item = Empty_Operation);
         end loop;
      end loop;
   end Check_Operation_Reserved;

   procedure Check_Witness_Reserved with Global => null, Always_Terminates is
      Bytes : Witness_Bytes;
      Item : Witness;
      Accepted : Boolean;
   begin
      for Index in 43 .. 48 loop
         for Code in Digest_Byte range 1 .. 255 loop
            Bytes := (Witness_Bytes'[others => 0] with delta Index => Code);
            Decode (Bytes, Accepted, Item);
            pragma Assert (not Accepted and then Item = Empty_Witness);
         end loop;
      end loop;
   end Check_Witness_Reserved;
begin
   Check_Digest_Fields;
   Check_Claim_Values;
   Check_Claim_Codes;
   Check_Generations;
   Check_Operation_Values;
   Check_Operation_Codes;
   Check_Witness;
   Check_Claim_Reserved;
   Check_Operation_Reserved;
   Check_Witness_Reserved;
end Continuity_Record_Wire_Tests;
