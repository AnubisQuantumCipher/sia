with SIA_Policy;
with SIA_Continuity;
with SIA_Continuity_Transitions;
with SIA_Continuity_Observation_Wire;

procedure Continuity_Observation_Wire_Tests with SPARK_Mode is
   use SIA_Policy;
   use SIA_Continuity;
   use SIA_Continuity_Transitions;
   use SIA_Continuity_Observation_Wire;

   States : constant array (Availability_Code) of Availability :=
     [Unknown, Missing, Retained, Retracted];
   Events : constant array (Event_Code) of Event_Kind :=
     [Dispatch_Attempt, Interruption, Observed_Outcome,
      Reconciled_Outcome, Acknowledgment];
   First : constant Digest :=
     [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
      17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32];
   Second : constant Digest :=
     [33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48,
      49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64];
   Third : constant Digest :=
     [65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80,
      81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96];
   Fourth : constant Digest :=
     [97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110,
      111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124,
      125, 126, 127, 128];
   Fifth : constant Digest :=
     [255, 254, 253, 252, 251, 250, 249, 248, 247, 246, 245, 244, 243,
      242, 241, 240, 239, 238, 237, 236, 235, 234, 233, 232, 231, 230,
      229, 228, 227, 226, 225, 224];
   Empty_Transition : constant Transition_Observation_Bytes :=
     [434 => 1, others => 0];

   procedure Check_Context with Global => null, Always_Terminates is
      Bytes : Context_Bytes := [others => 0];
      Item : Context;
   begin
      Item := Context_Value (Bytes);
      pragma Assert (Item = Context'(others => Zero));
      for I in Digest'Range loop
         Bytes := (Bytes with delta
           I => First (I), 32 + I => Second (I), 64 + I => Third (I),
           96 + I => Fourth (I), 128 + I => Fifth (I));
         pragma Loop_Invariant
           (for all J in 1 .. I =>
              Bytes (J) = First (J) and then Bytes (32 + J) = Second (J)
              and then Bytes (64 + J) = Third (J)
              and then Bytes (96 + J) = Fourth (J)
              and then Bytes (128 + J) = Fifth (J));
      end loop;
      Item := Context_Value (Bytes);
      pragma Assert (Item.Task_Id = First and then Item.Session_Id = Second
                     and then Item.Repository = Third
                     and then Item.Revision = Fourth and then Item.Dirty = Fifth);
   end Check_Context;

   procedure Check_Availability with Global => null, Always_Terminates is
      Claim_Data : Claim_Observation_Bytes;
      Operation_Data : Operation_Observation_Bytes;
      Transition_Data : Transition_Observation_Bytes;
      Claim_Item : Claim_Observation;
      Operation_Item : Operation_Observation;
      Transition_Item : Observation;
      Accepted : Boolean;
   begin
      for Code in Digest_Byte loop
         Claim_Data := [1 => Code, others => 0];
         Decode (Claim_Data, Accepted, Claim_Item);
         pragma Assert (Accepted = (Code <= 3));
         pragma Assert
           (if Accepted then Claim_Item.State = States (Code)
            else Claim_Item = Empty_Claim_Observation);
         Operation_Data := [1 => Code, others => 0];
         Decode (Operation_Data, Accepted, Operation_Item);
         pragma Assert (Accepted = (Code <= 3));
         pragma Assert
           (if Accepted then Operation_Item.State = States (Code)
            else Operation_Item = Empty_Operation_Observation);
         Transition_Data := [433 => Code, 434 => 1, others => 0];
         Decode (Transition_Data, Accepted, Transition_Item);
         pragma Assert (Accepted = (Code <= 3));
         pragma Assert
           (if Accepted then Transition_Item.State = States (Code)
            else Transition_Item = Empty_Observation);
      end loop;
   end Check_Availability;

   procedure Check_Claim with Global => null, Always_Terminates is
      Bytes : Claim_Observation_Bytes := [others => 0];
      Item : Claim_Observation;
      Accepted : Boolean;
   begin
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item.State = Unknown
                     and then Item.Item /= Empty_Claim);
      Bytes := [1 => 3, 98 => 1, 99 => 2, 100 => 3, 101 => 4,
                102 => 5, 103 => 6, 104 => 7, 105 => 8,
                106 => 11, 107 => 2, 108 => 1, 109 => 64, others => 0];
      for I in Digest'Range loop
         Bytes := (Bytes with delta
           1 + I => First (I), 33 + I => Second (I), 65 + I => Third (I));
         pragma Loop_Invariant (Valid (Bytes));
         pragma Loop_Invariant
           (Bytes (1) = 3 and then Bytes (106) = 11 and then
            Bytes (107) = 2 and then Bytes (108) = 1 and then Bytes (109) = 64);
         pragma Loop_Invariant
           (for all J in 98 .. 105 => Bytes (J) = Digest_Byte (J - 97));
         pragma Loop_Invariant
           (for all J in 1 .. I =>
              Bytes (1 + J) = First (J) and then
              Bytes (33 + J) = Second (J) and then
              Bytes (65 + J) = Third (J));
      end loop;
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item.State = Retracted);
      pragma Assert
        (Item.Item = Claim'(Identity => First, Slot => Second,
         Source_Record_Id => Third, Sequence => 16#0102_0304_0506_0708#,
         Kind => Permission_Reference, From => Model_Record,
         Speaker => Assistant, Replaces => 64));
      pragma Assert (not Valid_Claim (Item.Item));
      Bytes := [107 => 3, 108 => 2, others => 0];
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item = Empty_Claim_Observation);
   end Check_Claim;

   procedure Check_Operation with Global => null, Always_Terminates is
      Bytes : Operation_Observation_Bytes := [130 => 4, others => 0];
      Item : Operation_Observation;
      Accepted : Boolean;
   begin
      for I in Digest'Range loop
         Bytes := (Bytes with delta
           1 + I => First (I), 33 + I => Second (I),
           65 + I => Third (I), 97 + I => Fourth (I));
         pragma Loop_Invariant (Valid (Bytes));
         pragma Loop_Invariant
           (Bytes (1) = 0 and then Bytes (130) = 4 and then Bytes (131) = 0);
         pragma Loop_Invariant
           (for all J in 1 .. I =>
              Bytes (1 + J) = First (J) and then
              Bytes (33 + J) = Second (J) and then
              Bytes (65 + J) = Third (J) and then
              Bytes (97 + J) = Fourth (J));
      end loop;
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item.State = Unknown);
      pragma Assert
        (Item.Item = Operation'(Identity => First, Action => Second,
         Source_Record_Id => Third, Result_Record_Id => Fourth,
         Stage => Acknowledged, Has_Result => False));
      pragma Assert (not Valid_Operation (Item.Item));
      Bytes := [others => 0];
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item = Empty_Operation_Observation);
   end Check_Operation;

   procedure Check_Transition_Ids with Global => null, Always_Terminates is
      Bytes : Transition_Observation_Bytes := Empty_Transition;
      Item : Observation;
      Accepted : Boolean;
   begin
      for I in Digest'Range loop
         Bytes := (Bytes with delta
           I => First (I), 32 + I => Second (I),
           64 + I => Third (I), 96 + I => Fourth (I));
         pragma Loop_Invariant (Valid (Bytes));
         pragma Loop_Invariant (Bytes (435) = 0);
         pragma Loop_Invariant
           (for all J in 1 .. I =>
              Bytes (J) = First (J) and then
              Bytes (32 + J) = Second (J) and then
              Bytes (64 + J) = Third (J) and then
              Bytes (96 + J) = Fourth (J));
      end loop;
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item.Before_Id = First and then
                     Item.After_Id = Second and then Item.Event_Record_Id = Third
                     and then Item.Outcome_Record_Id = Fourth
                     and then not Item.Has_Outcome);
   end Check_Transition_Ids;

   procedure Check_Transition_Operations
     with Global => null, Always_Terminates
   is
      Bytes : Transition_Observation_Bytes :=
        [273 => 1, 274 => 1, 417 => 4, 418 => 1, 434 => 4, others => 0];
      Item : Observation;
      Accepted : Boolean;
   begin
      for I in Digest'Range loop
         Bytes := (Bytes with delta
           144 + I => First (I), 176 + I => Second (I),
           208 + I => Third (I), 240 + I => Fourth (I),
           288 + I => Second (I), 320 + I => Third (I),
           352 + I => Fourth (I), 384 + I => Fifth (I));
         pragma Loop_Invariant (Valid (Bytes));
         pragma Loop_Invariant
           (Bytes (273) = 1 and then Bytes (274) = 1 and then
            Bytes (417) = 4 and then Bytes (418) = 1 and then Bytes (434) = 4);
         pragma Loop_Invariant
           (for all J in 1 .. I =>
              Bytes (144 + J) = First (J) and then
              Bytes (176 + J) = Second (J) and then
              Bytes (208 + J) = Third (J) and then
              Bytes (240 + J) = Fourth (J) and then
              Bytes (288 + J) = Second (J) and then
              Bytes (320 + J) = Third (J) and then
              Bytes (352 + J) = Fourth (J) and then
              Bytes (384 + J) = Fifth (J));
      end loop;
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item.Kind = Reconciled_Outcome);
      pragma Assert
        (Item.Before_Operation = Operation'
          (Identity => First, Action => Second, Source_Record_Id => Third,
           Result_Record_Id => Fourth, Stage => Dispatched, Has_Result => True));
      pragma Assert
        (Item.After_Operation = Operation'
          (Identity => Second, Action => Third, Source_Record_Id => Fourth,
           Result_Record_Id => Fifth, Stage => Acknowledged, Has_Result => True));
   end Check_Transition_Operations;

   procedure Check_Transition_Codes with Global => null, Always_Terminates is
      Bytes : Transition_Observation_Bytes;
      Item : Observation;
      Accepted : Boolean;
   begin
      Decode (Empty_Transition, Accepted, Item);
      pragma Assert (Accepted and then Item = Empty_Observation);
      for Code in Digest_Byte loop
         Bytes := [434 => Code, others => 0];
         Decode (Bytes, Accepted, Item);
         pragma Assert (Accepted = (Code in 1 .. 5));
         pragma Assert
           (if Accepted then Item.Kind = Events (Code)
            else Item = Empty_Observation);
         Bytes := [434 => 1, 435 => Code, others => 0];
         Decode (Bytes, Accepted, Item);
         pragma Assert (Accepted = (Code <= 1));
         pragma Assert
           (if Accepted then Item.Has_Outcome = (Code = 1)
            else Item = Empty_Observation);
      end loop;
   end Check_Transition_Codes;

   procedure Check_Transition_Epochs with Global => null, Always_Terminates is
      Bytes : Transition_Observation_Bytes;
      Item : Observation;
      Accepted : Boolean;
   begin
      for Code in Digest_Byte loop
         Bytes := [129 => Code, 434 => 1, others => 0];
         Decode (Bytes, Accepted, Item);
         pragma Assert (Accepted = (Code <= 127));
         pragma Assert
           (if Accepted then Item.Before_Epoch = Generation (Code) * 2 ** 56
            else Item = Empty_Observation);
         Bytes := [137 => Code, 434 => 1, others => 0];
         Decode (Bytes, Accepted, Item);
         pragma Assert (Accepted = (Code <= 127));
         pragma Assert
           (if Accepted then Item.After_Epoch = Generation (Code) * 2 ** 56
            else Item = Empty_Observation);
      end loop;
      Bytes := [129 | 137 => 127, 130 .. 136 | 138 .. 144 => 255,
                434 => 1, others => 0];
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item.Before_Epoch = Generation'Last
                     and then Item.After_Epoch = Generation'Last);
      Bytes := [129 => 1, 130 => 2, 131 => 3, 132 => 4, 133 => 5,
                134 => 6, 135 => 7, 136 => 8, 137 => 8, 138 => 7,
                139 => 6, 140 => 5, 141 => 4, 142 => 3, 143 => 2,
                144 => 1, 434 => 1, others => 0];
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then
                     Item.Before_Epoch = 16#0102_0304_0506_0708# and then
                     Item.After_Epoch = 16#0807_0605_0403_0201#);
   end Check_Transition_Epochs;

   procedure Check_Claim_Reserved with Global => null, Always_Terminates is
      Bytes : Claim_Observation_Bytes;
      Item : Claim_Observation;
      Accepted : Boolean;
   begin
      for Index in 110 .. 144 loop
         for Code in Digest_Byte range 1 .. 255 loop
            Bytes := (Claim_Observation_Bytes'[others => 0]
                      with delta Index => Code);
            Decode (Bytes, Accepted, Item);
            pragma Assert (not Accepted and then Item = Empty_Claim_Observation);
         end loop;
      end loop;
   end Check_Claim_Reserved;

   procedure Check_Operation_Reserved with Global => null, Always_Terminates is
      Bytes : Operation_Observation_Bytes;
      Item : Operation_Observation;
      Accepted : Boolean;
   begin
      for Index in 132 .. 160 loop
         for Code in Digest_Byte range 1 .. 255 loop
            Bytes := (Operation_Observation_Bytes'[others => 0]
                      with delta Index => Code);
            Decode (Bytes, Accepted, Item);
            pragma Assert
              (not Accepted and then Item = Empty_Operation_Observation);
         end loop;
      end loop;
   end Check_Operation_Reserved;

   procedure Check_Transition_Reserved with Global => null, Always_Terminates is
      Bytes : Transition_Observation_Bytes;
      Item : Observation;
      Accepted : Boolean;
   begin
      for Index in 275 .. 448 loop
         if Index in 275 .. 288 | 419 .. 432 | 436 .. 448 then
            for Code in Digest_Byte range 1 .. 255 loop
               Bytes := (Empty_Transition with delta Index => Code);
               Decode (Bytes, Accepted, Item);
               pragma Assert (not Accepted and then Item = Empty_Observation);
            end loop;
         end if;
      end loop;
   end Check_Transition_Reserved;

   procedure Check_State_Preservation with Global => null, Always_Terminates is
      Claim_Data : constant Claim_Observation_Bytes :=
        [2 => 11, 34 => 22, 66 => 33, 98 => 1, 105 => 8,
         106 => 11, 107 => 2, 108 => 1, 109 => 64, others => 0];
      Operation_Data : constant Operation_Observation_Bytes :=
        [2 => 11, 34 => 22, 66 => 33, 98 => 44, 130 => 4, 131 => 1, others => 0];
      Transition_Data : constant Transition_Observation_Bytes :=
        [1 => 11, 33 => 22, 65 => 33, 97 => 44, 129 => 1, 137 => 2,
         145 => 55, 177 => 66, 209 => 77, 241 => 88, 273 => 2,
         289 => 99, 321 => 111, 353 => 222, 385 => 255, 417 => 3,
         418 => 1, 434 => 4, others => 0];
      Claim_Base, Claim_Item : Claim_Observation;
      Operation_Base, Operation_Item : Operation_Observation;
      Transition_Base, Transition_Item : Observation;
      Accepted : Boolean;
   begin
      Decode (Claim_Data, Accepted, Claim_Base);
      pragma Assert (Accepted and then Claim_Base.Item /= Empty_Claim);
      Decode (Operation_Data, Accepted, Operation_Base);
      pragma Assert (Accepted and then Operation_Base.Item /= Empty_Operation);
      Decode (Transition_Data, Accepted, Transition_Base);
      pragma Assert (Accepted and then Transition_Base /= Empty_Observation);
      for Code in Availability_Code loop
         Decode ((Claim_Data with delta 1 => Code), Accepted, Claim_Item);
         pragma Assert (Accepted and then
                        Claim_Item = (Claim_Base with delta State => States (Code)));
         Decode ((Operation_Data with delta 1 => Code), Accepted, Operation_Item);
         pragma Assert (Accepted and then Operation_Item =
                          (Operation_Base with delta State => States (Code)));
         Decode ((Transition_Data with delta 433 => Code), Accepted,
                 Transition_Item);
         pragma Assert (Accepted and then Transition_Item =
                          (Transition_Base with delta State => States (Code)));
      end loop;
   end Check_State_Preservation;

   procedure Check_Inactive_Nested with Global => null, Always_Terminates is
      Claim_Data : Claim_Observation_Bytes;
      Operation_Data : Operation_Observation_Bytes;
      Transition_Data : Transition_Observation_Bytes;
      Claim_Item : Claim_Observation;
      Operation_Item : Operation_Observation;
      Transition_Item : Observation;
      Accepted : Boolean;
   begin
      for Code in Availability_Code loop
         for Index in 98 .. 109 loop
            if Index in 98 | 106 .. 109 then
               Claim_Data := (Claim_Observation_Bytes'[1 => Code, others => 0]
                              with delta Index => 255);
               Decode (Claim_Data, Accepted, Claim_Item);
               pragma Assert
                 (not Accepted and then Claim_Item = Empty_Claim_Observation);
            end if;
         end loop;
         for Index in 130 .. 131 loop
            Operation_Data :=
              (Operation_Observation_Bytes'[1 => Code, others => 0]
               with delta Index => 255);
            Decode (Operation_Data, Accepted, Operation_Item);
            pragma Assert
              (not Accepted and then Operation_Item = Empty_Operation_Observation);
         end loop;
         for Index in 273 .. 418 loop
            if Index in 273 .. 274 | 417 .. 418 then
               Transition_Data :=
                 (Transition_Observation_Bytes'
                   [433 => Code, 434 => 1, others => 0] with delta Index => 255);
               Decode (Transition_Data, Accepted, Transition_Item);
               pragma Assert
                 (not Accepted and then Transition_Item = Empty_Observation);
            end if;
         end loop;
      end loop;
   end Check_Inactive_Nested;
begin
   pragma Assert (Empty_Claim_Observation.Item = Empty_Claim and then
                  Empty_Operation_Observation.Item = Empty_Operation);
   Check_Context;
   Check_Availability;
   Check_Claim;
   Check_Operation;
   Check_Transition_Ids;
   Check_Transition_Operations;
   Check_Transition_Codes;
   Check_Transition_Epochs;
   Check_Claim_Reserved;
   Check_Operation_Reserved;
   Check_Transition_Reserved;
   Check_State_Preservation;
   Check_Inactive_Nested;
end Continuity_Observation_Wire_Tests;
