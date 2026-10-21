with SIA_Policy;
with SIA_Continuity;
with SIA_Continuity_Checkpoint_Wire;

procedure Continuity_Checkpoint_Wire_Tests with SPARK_Mode is
   use SIA_Policy;
   use SIA_Continuity;
   use SIA_Continuity_Checkpoint_Wire;
   States : constant array (Coverage_Code) of Coverage_State :=
     [Not_Observed, Unavailable, Observed_Empty, Partial, Complete];

   procedure Check_Zero_And_Canonical
     with Global => null, Always_Terminates
   is
      Bytes : Checkpoint_Bytes := [others => 0];
      Item : Checkpoint;
      Accepted : Boolean;
   begin
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item.Count = 0);
      pragma Assert (Item /= Empty_Checkpoint);
      pragma Assert
        (for all I in Claim_Index => Item.Claims (I).From = Source_Record
         and then Item.Claims (I).Speaker = User);
      for I in Claim_Index loop
         Bytes := (Bytes with delta
           (320 + (I - 1) * 128) + 106 => 3,
           (320 + (I - 1) * 128) + 107 => 2);
         pragma Loop_Invariant
           (for all J in Claim_Index =>
              (if J <= I then
                  Bytes ((320 + (J - 1) * 128) + 106) = 3 and then
                  Bytes ((320 + (J - 1) * 128) + 107) = 2
               else
                  Bytes ((320 + (J - 1) * 128) + 106) = 0 and then
                  Bytes ((320 + (J - 1) * 128) + 107) = 0));
         pragma Loop_Invariant
           (for all J in Checkpoint_Bytes'Range =>
              (if J < 321 or else J > 8512 or else
                  (J - 321) mod 128 not in 105 .. 106
               then Bytes (J) = Bytes'Loop_Entry (J)));
      end loop;
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item = Empty_Checkpoint);
   end Check_Zero_And_Canonical;

   procedure Check_Header with Global => null, Always_Terminates is
      Bytes : Checkpoint_Bytes := [257 => 127, 258 .. 264 => 255,
        265 => 1, 266 => 2, 267 => 3, 268 => 4,
        269 => 5, 270 => 6, 271 => 7, 272 => 8, 280 => 9, others => 0];
      Item : Checkpoint;
      Accepted : Boolean;
   begin
      for I in Digest'Range loop
         Bytes := (Bytes with delta
           I => 1, 32 + I => 2, 64 + I => 3, 96 + I => 4,
           128 + I => 5, 160 + I => 6, 192 + I => 7, 224 + I => 8);
         pragma Loop_Invariant
           (for all J in 1 .. I =>
              Bytes (J) = 1 and then Bytes (32 + J) = 2 and then
              Bytes (64 + J) = 3 and then Bytes (96 + J) = 4 and then
              Bytes (128 + J) = 5 and then Bytes (160 + J) = 6 and then
              Bytes (192 + J) = 7 and then Bytes (224 + J) = 8);
         pragma Loop_Invariant
           (for all J in 257 .. Checkpoint_Bytes'Last =>
              Bytes (J) = Bytes'Loop_Entry (J));
      end loop;
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted);
      pragma Assert
        (Item.Scope = Context'(Task_Id => [others => 1],
         Session_Id => [others => 2], Repository => [others => 3],
         Revision => [others => 4], Dirty => [others => 5]));
      pragma Assert (Item.Identity = Digest'[others => 6] and then
                     Item.Previous = Digest'[others => 7] and then
                     Item.Capture = Digest'[others => 8]);
      pragma Assert (Item.Epoch = Generation'Last and then
                     Item.Through = 16#0102_0304_0506_0708# and then
                     Item.Retention_Epoch = 9);
   end Check_Header;

   procedure Check_Header_Order with Global => null, Always_Terminates is
      Bytes : constant Checkpoint_Bytes :=
        [for I in Checkpoint_Bytes'Range =>
           (if I <= 256 then Digest_Byte (I - 1) else 0)];
      Item : Checkpoint;
      Accepted : Boolean;
   begin
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted);
      pragma Assert (Item.Scope = Context'(
        Task_Id => [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
                    16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31],
        Session_Id => [32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45,
                       46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59,
                       60, 61, 62, 63],
        Repository => [64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77,
                       78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91,
                       92, 93, 94, 95],
        Revision => [96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107,
                     108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118,
                     119, 120, 121, 122, 123, 124, 125, 126, 127],
        Dirty => [128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139,
                  140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151,
                  152, 153, 154, 155, 156, 157, 158, 159]));
      pragma Assert (Item.Identity = Digest'[
        160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172,
        173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185,
        186, 187, 188, 189, 190, 191]);
      pragma Assert (Item.Previous = Digest'[
        192, 193, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204,
        205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217,
        218, 219, 220, 221, 222, 223]);
      pragma Assert (Item.Capture = Digest'[
        224, 225, 226, 227, 228, 229, 230, 231, 232, 233, 234, 235, 236,
        237, 238, 239, 240, 241, 242, 243, 244, 245, 246, 247, 248, 249,
        250, 251, 252, 253, 254, 255]);
   end Check_Header_Order;

   procedure Check_Claim_Order with Global => null, Always_Terminates is
      --  Fixed protocol bases, independently specified, not encoder output.
      Bytes : constant Checkpoint_Bytes := [294 => 64,
        320 + 1 => 1, 320 + 16 => 2, 320 + 32 => 3,
        320 + 33 => 4, 320 + 48 => 5, 320 + 64 => 6,
        320 + 65 => 7, 320 + 80 => 8, 320 + 96 => 9,
        320 + 102 => 1, 320 + 103 => 2, 320 + 104 => 3, 320 + 105 => 2,
        4288 + 1 => 11, 4288 + 16 => 12, 4288 + 32 => 13,
        4288 + 33 => 14, 4288 + 48 => 15, 4288 + 64 => 16,
        4288 + 65 => 17, 4288 + 80 => 18, 4288 + 96 => 19,
        4288 + 102 => 4, 4288 + 103 => 5, 4288 + 104 => 6,
        4288 + 105 => 4, 4288 + 106 => 2, 4288 + 107 => 1, 4288 + 108 => 1,
        8384 + 1 => 21, 8384 + 16 => 22, 8384 + 32 => 23,
        8384 + 33 => 24, 8384 + 48 => 25, 8384 + 64 => 26,
        8384 + 65 => 27, 8384 + 80 => 28, 8384 + 96 => 29,
        8384 + 102 => 7, 8384 + 103 => 8, 8384 + 104 => 9,
        8384 + 105 => 12, 8384 + 106 => 1, 8384 + 107 => 2, 8384 + 108 => 32,
        others => 0];
      Expected : constant Claim_Array := [
        1 => (Identity => [1 => 1, 16 => 2, 32 => 3, others => 0],
              Slot => [1 => 4, 16 => 5, 32 => 6, others => 0],
              Source_Record_Id => [1 => 7, 16 => 8, 32 => 9, others => 0],
              Sequence => 16#010203#, Kind => Constraint,
              From => Source_Record, Speaker => User, Replaces => 0),
        32 => (Identity => [1 => 11, 16 => 12, 32 => 13, others => 0],
               Slot => [1 => 14, 16 => 15, 32 => 16, others => 0],
               Source_Record_Id => [1 => 17, 16 => 18, 32 => 19, others => 0],
               Sequence => 16#040506#, Kind => Decision,
               From => Model_Record, Speaker => Assistant, Replaces => 1),
        64 => (Identity => [1 => 21, 16 => 22, 32 => 23, others => 0],
               Slot => [1 => 24, 16 => 25, 32 => 26, others => 0],
               Source_Record_Id => [1 => 27, 16 => 28, 32 => 29, others => 0],
               Sequence => 16#070809#, Kind => Pending_Approval,
               From => Derived_Record, Speaker => Tool, Replaces => 32),
        others => (Identity | Slot | Source_Record_Id => [others => 0],
                   Sequence => 0, Kind => Goal, From => Source_Record,
                   Speaker => User, Replaces => 0)];
      Item : Checkpoint;
      Accepted : Boolean;
   begin
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item.Count = 64);
      pragma Assert (Item.Claims = Expected);
   end Check_Claim_Order;

   procedure Check_Operation_Order with Global => null, Always_Terminates is
      Bytes : constant Checkpoint_Bytes := [295 => 16,
        8512 + 1 => 1, 8512 + 16 => 2, 8512 + 32 => 3,
        8512 + 33 => 4, 8512 + 48 => 5, 8512 + 64 => 6,
        8512 + 65 => 7, 8512 + 80 => 8, 8512 + 96 => 9,
        8512 + 97 => 10, 8512 + 112 => 11, 8512 + 128 => 12,
        8512 + 129 => 1, 8512 + 130 => 1,
        9520 + 1 => 21, 9520 + 16 => 22, 9520 + 32 => 23,
        9520 + 33 => 24, 9520 + 48 => 25, 9520 + 64 => 26,
        9520 + 65 => 27, 9520 + 80 => 28, 9520 + 96 => 29,
        9520 + 97 => 30, 9520 + 112 => 31, 9520 + 128 => 32, 9520 + 129 => 2,
        10672 + 1 => 41, 10672 + 16 => 42, 10672 + 32 => 43,
        10672 + 33 => 44, 10672 + 48 => 45, 10672 + 64 => 46,
        10672 + 65 => 47, 10672 + 80 => 48, 10672 + 96 => 49,
        10672 + 97 => 50, 10672 + 112 => 51, 10672 + 128 => 52,
        10672 + 129 => 4, 10672 + 130 => 1, others => 0];
      Expected : constant Operation_Array := [
        1 => (Identity => [1 => 1, 16 => 2, 32 => 3, others => 0],
              Action => [1 => 4, 16 => 5, 32 => 6, others => 0],
              Source_Record_Id => [1 => 7, 16 => 8, 32 => 9, others => 0],
              Result_Record_Id => [1 => 10, 16 => 11, 32 => 12, others => 0],
              Stage => Dispatched, Has_Result => True),
        8 => (Identity => [1 => 21, 16 => 22, 32 => 23, others => 0],
              Action => [1 => 24, 16 => 25, 32 => 26, others => 0],
              Source_Record_Id => [1 => 27, 16 => 28, 32 => 29, others => 0],
              Result_Record_Id => [1 => 30, 16 => 31, 32 => 32, others => 0],
              Stage => Uncertain, Has_Result => False),
        16 => (Identity => [1 => 41, 16 => 42, 32 => 43, others => 0],
               Action => [1 => 44, 16 => 45, 32 => 46, others => 0],
               Source_Record_Id => [1 => 47, 16 => 48, 32 => 49, others => 0],
               Result_Record_Id => [1 => 50, 16 => 51, 32 => 52, others => 0],
               Stage => Acknowledged, Has_Result => True),
        others => (Identity | Action | Source_Record_Id | Result_Record_Id =>
                      [others => 0], Stage => Planned, Has_Result => False)];
      Item : Checkpoint;
      Accepted : Boolean;
   begin
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item.Operations_Count = 16);
      pragma Assert (Item.Operations = Expected);
   end Check_Operation_Order;

   procedure Check_Coverage with Global => null, Always_Terminates is
      Bytes : Checkpoint_Bytes;
      Item : Checkpoint;
      Accepted : Boolean;
   begin
      for Kind in Claim_Kind loop
         for Code in Digest_Byte loop
            Bytes := [others => 0];
            Bytes := (Bytes with delta 281 + Claim_Kind'Pos (Kind) => Code);
            Decode (Bytes, Accepted, Item);
            pragma Assert (Accepted = (Code <= 4));
            pragma Assert
              (if Accepted then Item.Coverage (Kind) = States (Code)
               else Item = Empty_Checkpoint);
         end loop;
      end loop;
   end Check_Coverage;

   procedure Check_Counts with Global => null, Always_Terminates is
      Bytes : Checkpoint_Bytes;
      Item : Checkpoint;
      Accepted : Boolean;
   begin
      for Code in Digest_Byte loop
         Bytes := [294 => Code, others => 0];
         Decode (Bytes, Accepted, Item);
         pragma Assert (Accepted = (Code <= 64));
         pragma Assert (if Accepted then Item.Count = Natural (Code)
                        else Item = Empty_Checkpoint);
         Bytes := [295 => Code, others => 0];
         Decode (Bytes, Accepted, Item);
         pragma Assert (Accepted = (Code <= 16));
         pragma Assert (if Accepted then Item.Operations_Count = Natural (Code)
                        else Item = Empty_Checkpoint);
      end loop;
   end Check_Counts;

   procedure Check_Header_Refusals
     with Global => null, Always_Terminates
   is
      Bytes : Checkpoint_Bytes;
      Item : Checkpoint;
      Accepted : Boolean;
   begin
      for I in 296 .. 320 loop
         Bytes := [others => 0];
         Bytes := (Bytes with delta I => 1);
         Decode (Bytes, Accepted, Item);
         pragma Assert (not Accepted and then Item = Empty_Checkpoint);
      end loop;
      for Field in 0 .. 2 loop
         for Code in Digest_Byte loop
            Bytes := [others => 0];
            Bytes := (Bytes with delta 257 + Field * 8 => Code);
            Decode (Bytes, Accepted, Item);
            pragma Assert (Accepted = (Code <= 127));
            pragma Assert (if not Accepted then Item = Empty_Checkpoint);
         end loop;
      end loop;
   end Check_Header_Refusals;

   procedure Check_Inactive_Claims
     with Global => null, Always_Terminates
   is
      Bytes : Checkpoint_Bytes;
      Item : Checkpoint;
      Accepted : Boolean;
   begin
      for I in Claim_Index loop
         Bytes := [others => 0];
         Bytes := (Bytes with delta (320 + (I - 1) * 128) + 105 => 13);
         Decode (Bytes, Accepted, Item);
         pragma Assert (not Accepted and then Item = Empty_Checkpoint);
         Bytes := [others => 0];
         Bytes := (Bytes with delta (320 + (I - 1) * 128) + 128 => 1);
         Decode (Bytes, Accepted, Item);
         pragma Assert (not Accepted and then Item = Empty_Checkpoint);
         Bytes := [others => 0];
         Bytes := (Bytes with delta (320 + (I - 1) * 128) + 97 => 128);
         Decode (Bytes, Accepted, Item);
         pragma Assert (not Accepted and then Item = Empty_Checkpoint);
      end loop;
   end Check_Inactive_Claims;

   procedure Check_Inactive_Operations
     with Global => null, Always_Terminates
   is
      Bytes : Checkpoint_Bytes;
      Item : Checkpoint;
      Accepted : Boolean;
   begin
      for I in Operation_Index loop
         Bytes := [others => 0];
         Bytes := (Bytes with delta (8512 + (I - 1) * 144) + 129 => 5);
         Decode (Bytes, Accepted, Item);
         pragma Assert (not Accepted and then Item = Empty_Checkpoint);
         Bytes := [others => 0];
         Bytes := (Bytes with delta (8512 + (I - 1) * 144) + 130 => 2);
         Decode (Bytes, Accepted, Item);
         pragma Assert (not Accepted and then Item = Empty_Checkpoint);
         Bytes := [others => 0];
         Bytes := (Bytes with delta (8512 + (I - 1) * 144) + 144 => 1);
         Decode (Bytes, Accepted, Item);
         pragma Assert (not Accepted and then Item = Empty_Checkpoint);
      end loop;
   end Check_Inactive_Operations;

   procedure Check_Policy_Invalid_Preservation
     with Global => null, Always_Terminates
   is
      Bytes : constant Checkpoint_Bytes :=
        [8385 => 42, 8489 => 11, 8490 => 2, 8491 => 1, 8492 => 64,
         10673 => 43, 10801 => 4, others => 0];
      Item : Checkpoint;
      Accepted : Boolean;
   begin
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item.Count = 0
                     and then Item.Operations_Count = 0);
      pragma Assert (Item.Claims (64).Identity (1) = 42 and then
                     Item.Claims (64).Kind = Permission_Reference and then
                     Item.Claims (64).From = Model_Record and then
                     Item.Claims (64).Speaker = Assistant and then
                     Item.Claims (64).Replaces = 64);
      pragma Assert (not Valid_Claim (Item.Claims (64)));
      pragma Assert (Item.Operations (16).Identity (1) = 43 and then
                     Item.Operations (16).Stage = Acknowledged and then
                     not Item.Operations (16).Has_Result);
      pragma Assert (not Valid_Operation (Item.Operations (16)));
      pragma Assert (not Valid (Item));
   end Check_Policy_Invalid_Preservation;
begin
   Check_Zero_And_Canonical;
   Check_Header;
   Check_Header_Order;
   Check_Claim_Order;
   Check_Operation_Order;
   Check_Coverage;
   Check_Counts;
   Check_Header_Refusals;
   Check_Inactive_Claims;
   Check_Inactive_Operations;
   Check_Policy_Invalid_Preservation;
end Continuity_Checkpoint_Wire_Tests;
