with SIA_Policy;
with SIA_Continuity;
with SIA_Continuity_Current_Wire;

procedure Continuity_Current_Wire_Tests with SPARK_Mode is
   use SIA_Policy;
   use SIA_Continuity;
   use SIA_Continuity_Current_Wire;

   procedure Check_Zero with Global => null, Always_Terminates is
      Bytes : Current_Bytes := [others => 0];
      Item : Current_Evidence;
      Accepted : Boolean;
      Expected : constant Current_Evidence :=
        (Empty_Current with delta Claims => [others =>
          (State => Unknown,
           Item => (Identity | Slot | Source_Record_Id => [others => 0],
                    Sequence => 0, Kind => Goal, From => Source_Record,
                    Speaker => User, Replaces => 0))]);
   begin
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item = Expected);
      pragma Assert (Item /= Empty_Current);
      Bytes := (Bytes with delta 345 => 1);
      Decode (Bytes, Accepted, Item);
      pragma Assert (not Accepted and then Item = Empty_Current);
   end Check_Zero;

   procedure Check_Header_Order with Global => null, Always_Terminates is
      Bytes : constant Current_Bytes :=
        [1 => 1, 16 => 2, 32 => 3, 33 => 4, 48 => 5, 64 => 6,
         65 => 7, 80 => 8, 96 => 9, 97 => 10, 112 => 11, 128 => 12,
         129 => 13, 144 => 14, 160 => 15, 161 => 16, 176 => 17, 192 => 18,
         193 => 19, 208 => 20, 224 => 21,
         225 => 127, 226 .. 232 => 255, 238 => 1, 239 => 2, 240 => 3,
         246 => 4, 247 => 5, 248 => 6, others => 0];
      Item : Current_Evidence;
      Accepted : Boolean;
   begin
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted);
      pragma Assert (Item.Scope = Context'(
        Task_Id => [1 => 1, 16 => 2, 32 => 3, others => 0],
        Session_Id => [1 => 4, 16 => 5, 32 => 6, others => 0],
        Repository => [1 => 7, 16 => 8, 32 => 9, others => 0],
        Revision => [1 => 10, 16 => 11, 32 => 12, others => 0],
        Dirty => [1 => 13, 16 => 14, 32 => 15, others => 0]));
      pragma Assert
        (Item.Checkpoint_Id = Digest'[1 => 16, 16 => 17, 32 => 18, others => 0]);
      pragma Assert
        (Item.Capture = Digest'[1 => 19, 16 => 20, 32 => 21, others => 0]);
      pragma Assert (Item.Epoch = Generation'Last);
      pragma Assert (Item.Through = 16#010203#);
      pragma Assert (Item.Retention_Epoch = 16#040506#);
   end Check_Header_Order;

   procedure Check_Witnesses with Global => null, Always_Terminates is
      Bytes : constant Current_Bytes :=
        [249 | 250 => 1, 251 => 127, 252 .. 258 => 255,
         259 => 1, 274 => 2, 290 => 3,
         297 => 0, 298 => 1, 304 => 4, 305 => 5, 306 => 6,
         307 => 7, 322 => 8, 338 => 9, others => 0];
      Item : Current_Evidence;
      Accepted : Boolean;
   begin
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted);
      pragma Assert (Item.Manifest = Witness'(
        Present | Durable => True,
        Bound_To => (Epoch => Generation'Last,
                     Transaction => [1 => 1, 16 => 2, 32 => 3, others => 0])));
      pragma Assert (Item.Originals = Witness'(
        Present => False, Durable => True,
        Bound_To => (Epoch => 16#040506#,
                     Transaction => [1 => 7, 16 => 8, 32 => 9, others => 0])));
      --  An absent but nonempty witness is representable, never normalized.
      pragma Assert (not Bound_Durable (Item.Originals, Item.Originals.Bound_To));
   end Check_Witnesses;

   procedure Check_Claim_Order with Global => null, Always_Terminates is
      --  Independently specified first, interior and last protocol records.
      Bytes : constant Current_Bytes := [353 => 1,
        354 => 1, 369 => 2, 385 => 3, 386 => 4, 401 => 5, 417 => 6,
        418 => 7, 433 => 8, 449 => 9, 455 => 1, 456 => 2, 457 => 3,
        458 => 2,
        4817 => 2, 4818 => 11, 4833 => 12, 4849 => 13,
        4850 => 14, 4865 => 15, 4881 => 16,
        4882 => 17, 4897 => 18, 4913 => 19,
        4919 => 4, 4920 => 5, 4921 => 6,
        4922 => 4, 4923 => 2, 4924 => 1, 4925 => 1,
        9425 => 3, 9426 => 21, 9441 => 22, 9457 => 23,
        9458 => 24, 9473 => 25, 9489 => 26,
        9490 => 27, 9505 => 28, 9521 => 29,
        9527 => 7, 9528 => 8, 9529 => 9,
        9530 => 11, 9531 => 2, 9532 => 1, 9533 => 32, others => 0];
      Expected : constant Claim_Observations := [
        1 => (State => Missing, Item =>
          (Identity => [1 => 1, 16 => 2, 32 => 3, others => 0],
           Slot => [1 => 4, 16 => 5, 32 => 6, others => 0],
           Source_Record_Id => [1 => 7, 16 => 8, 32 => 9, others => 0],
           Sequence => 16#010203#, Kind => Constraint, From => Source_Record,
           Speaker => User, Replaces => 0)),
        32 => (State => Retained, Item =>
          (Identity => [1 => 11, 16 => 12, 32 => 13, others => 0],
           Slot => [1 => 14, 16 => 15, 32 => 16, others => 0],
           Source_Record_Id => [1 => 17, 16 => 18, 32 => 19, others => 0],
           Sequence => 16#040506#, Kind => Decision, From => Model_Record,
           Speaker => Assistant, Replaces => 1)),
        64 => (State => Retracted, Item =>
          (Identity => [1 => 21, 16 => 22, 32 => 23, others => 0],
           Slot => [1 => 24, 16 => 25, 32 => 26, others => 0],
           Source_Record_Id => [1 => 27, 16 => 28, 32 => 29, others => 0],
           Sequence => 16#070809#, Kind => Permission_Reference,
           From => Model_Record, Speaker => Assistant, Replaces => 32)),
        others => (State => Unknown, Item =>
          (Identity | Slot | Source_Record_Id => [others => 0], Sequence => 0,
           Kind => Goal, From => Source_Record, Speaker => User, Replaces => 0))];
      Item : Current_Evidence;
      Accepted : Boolean;
   begin
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item.Claims = Expected);
      pragma Assert (not Valid_Claim (Item.Claims (64).Item));
   end Check_Claim_Order;

   procedure Check_Operation_Order with Global => null, Always_Terminates is
      Bytes : constant Current_Bytes := [9569 => 1,
        9570 => 1, 9585 => 2, 9601 => 3, 9602 => 4, 9617 => 5, 9633 => 6,
        9634 => 7, 9649 => 8, 9665 => 9,
        9666 => 10, 9681 => 11, 9697 => 12, 9698 => 1, 9699 => 1,
        10689 => 2, 10690 => 21, 10705 => 22, 10721 => 23,
        10722 => 24, 10737 => 25, 10753 => 26,
        10754 => 27, 10769 => 28, 10785 => 29,
        10786 => 30, 10801 => 31, 10817 => 32, 10818 => 2,
        11969 => 3, 11970 => 41, 11985 => 42, 12001 => 43,
        12002 => 44, 12017 => 45, 12033 => 46,
        12034 => 47, 12049 => 48, 12065 => 49,
        12066 => 50, 12081 => 51, 12097 => 52, 12098 => 4, others => 0];
      Expected : constant Operation_Observations := [
        1 => (State => Missing, Item =>
          (Identity => [1 => 1, 16 => 2, 32 => 3, others => 0],
           Action => [1 => 4, 16 => 5, 32 => 6, others => 0],
           Source_Record_Id => [1 => 7, 16 => 8, 32 => 9, others => 0],
           Result_Record_Id => [1 => 10, 16 => 11, 32 => 12, others => 0],
           Stage => Dispatched, Has_Result => True)),
        8 => (State => Retained, Item =>
          (Identity => [1 => 21, 16 => 22, 32 => 23, others => 0],
           Action => [1 => 24, 16 => 25, 32 => 26, others => 0],
           Source_Record_Id => [1 => 27, 16 => 28, 32 => 29, others => 0],
           Result_Record_Id => [1 => 30, 16 => 31, 32 => 32, others => 0],
           Stage => Uncertain, Has_Result => False)),
        16 => (State => Retracted, Item =>
          (Identity => [1 => 41, 16 => 42, 32 => 43, others => 0],
           Action => [1 => 44, 16 => 45, 32 => 46, others => 0],
           Source_Record_Id => [1 => 47, 16 => 48, 32 => 49, others => 0],
           Result_Record_Id => [1 => 50, 16 => 51, 32 => 52, others => 0],
           Stage => Acknowledged, Has_Result => False)),
        others => (State => Unknown, Item =>
          (Identity | Action | Source_Record_Id | Result_Record_Id =>
             [others => 0], Stage => Planned, Has_Result => False))];
      Item : Current_Evidence;
      Accepted : Boolean;
   begin
      Decode (Bytes, Accepted, Item);
      pragma Assert (Accepted and then Item.Operations = Expected);
      pragma Assert (not Valid_Operation (Item.Operations (16).Item));
   end Check_Operation_Order;

   procedure Check_Header_Codes with Global => null, Always_Terminates is
      Generations : constant array (1 .. 5) of Positive :=
        [225, 233, 241, 251, 299];
      Flags : constant array (1 .. 4) of Positive := [249, 250, 297, 298];
      Bytes : Current_Bytes;
      Item : Current_Evidence;
      Accepted : Boolean;
   begin
      for Position of Generations loop
         for Code in Digest_Byte loop
            Bytes := [others => 0];
            Bytes := (Bytes with delta Position => Code);
            Decode (Bytes, Accepted, Item);
            pragma Assert (Accepted = (Code <= 127));
            pragma Assert (if not Accepted then Item = Empty_Current);
         end loop;
      end loop;
      for Position of Flags loop
         for Code in Digest_Byte loop
            Bytes := [others => 0];
            Bytes := (Bytes with delta Position => Code);
            Decode (Bytes, Accepted, Item);
            pragma Assert (Accepted = (Code <= 1));
            pragma Assert (if not Accepted then Item = Empty_Current);
         end loop;
      end loop;
   end Check_Header_Codes;

   procedure Check_Header_Reserved with Global => null, Always_Terminates is
      Bytes : Current_Bytes;
      Item : Current_Evidence;
      Accepted : Boolean;
   begin
      for Position in 291 .. 352 loop
         if Position in 291 .. 296 | 339 .. 352 then
            Bytes := [others => 0];
            Bytes := (Bytes with delta Position => 1);
            Decode (Bytes, Accepted, Item);
            pragma Assert (not Accepted and then Item = Empty_Current);
         end if;
      end loop;
   end Check_Header_Reserved;

   procedure Check_Claim_Refusal with Global => null, Always_Terminates is
      Positions : constant array (1 .. 9) of Positive :=
        [1, 98, 106, 107, 108, 109, 110, 130, 144];
      Values : constant array (1 .. 9) of Digest_Byte :=
        [4, 128, 13, 4, 4, 65, 1, 1, 1];
      Bytes : Current_Bytes;
      Item : Current_Evidence;
      Accepted : Boolean;
   begin
      for I in Claim_Index loop
         for Fault in Positions'Range loop
            Bytes := [others => 0];
            Bytes := (Bytes with delta
              (352 + (I - 1) * 144) + Positions (Fault) => Values (Fault));
            Decode (Bytes, Accepted, Item);
            pragma Assert (not Accepted and then Item = Empty_Current);
         end loop;
      end loop;
   end Check_Claim_Refusal;

   procedure Check_Operation_Refusal with Global => null, Always_Terminates is
      Positions : constant array (1 .. 6) of Positive :=
        [1, 130, 131, 132, 146, 160];
      Values : constant array (1 .. 6) of Digest_Byte := [4, 5, 2, 1, 1, 1];
      Bytes : Current_Bytes;
      Item : Current_Evidence;
      Accepted : Boolean;
   begin
      for I in Operation_Index loop
         for Fault in Positions'Range loop
            Bytes := [others => 0];
            Bytes := (Bytes with delta
              (9568 + (I - 1) * 160) + Positions (Fault) => Values (Fault));
            Decode (Bytes, Accepted, Item);
            pragma Assert (not Accepted and then Item = Empty_Current);
         end loop;
      end loop;
   end Check_Operation_Refusal;

   procedure Check_Available_Refusal with Global => null, Always_Terminates is
      Bytes : Current_Bytes;
      Item : Current_Evidence;
      Accepted : Boolean;
   begin
      --  Missing, retained and retracted states never bypass nested checks.
      --  The per-slot tests above separately cover Unknown and bad state codes.
      for Code in Digest_Byte range 1 .. 3 loop
         for I in Claim_Index loop
            Bytes := [others => 0];
            Bytes := (Bytes with delta
              (352 + (I - 1) * 144) + 1 => Code,
              (352 + (I - 1) * 144) + 110 => 1);
            Decode (Bytes, Accepted, Item);
            pragma Assert (not Accepted and then Item = Empty_Current);
         end loop;
         for I in Operation_Index loop
            Bytes := [others => 0];
            Bytes := (Bytes with delta
              (9568 + (I - 1) * 160) + 1 => Code,
              (9568 + (I - 1) * 160) + 132 => 1);
            Decode (Bytes, Accepted, Item);
            pragma Assert (not Accepted and then Item = Empty_Current);
         end loop;
      end loop;
   end Check_Available_Refusal;

   procedure Check_Availability with Global => null, Always_Terminates is
      Positions : constant array (1 .. 6) of Positive :=
        [353, 4817, 9425, 9569, 10689, 11969];
      Bytes : Current_Bytes;
      Item : Current_Evidence;
      Accepted : Boolean;
   begin
      for Position of Positions loop
         for Code in Digest_Byte loop
            Bytes := [others => 0];
            Bytes := (Bytes with delta Position => Code);
            Decode (Bytes, Accepted, Item);
            pragma Assert (Accepted = (Code <= 3));
            pragma Assert (if not Accepted then Item = Empty_Current);
         end loop;
      end loop;
   end Check_Availability;
begin
   Check_Zero;
   Check_Header_Order;
   Check_Witnesses;
   Check_Claim_Order;
   Check_Operation_Order;
   Check_Header_Codes;
   Check_Header_Reserved;
   Check_Claim_Refusal;
   Check_Operation_Refusal;
   Check_Available_Refusal;
   Check_Availability;
end Continuity_Current_Wire_Tests;
