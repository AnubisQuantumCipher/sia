with SIA_Policy; use SIA_Policy;
with SIA_Request_Wire; use SIA_Request_Wire;

procedure Request_Wire_Tests with SPARK_Mode is
   Base : constant Frame :=
     [1 => 1, 2 => 2, 3 => 1, 4 => 2, 176 => 2, 184 => 3,
      9 .. 40 => 11, 41 .. 72 => 22, 73 .. 104 => 33,
      105 .. 136 => 44, 137 .. 168 => 55, others => 0];
   Pattern : constant Digest :=
     [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
      17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32];

   procedure Check (Data : Frame; Length : Natural; Expected : Boolean)
   with Global => null, Always_Terminates,
     Pre => Expected = Valid (Data, Length)
   is
      OK : Boolean;
      Decoded : Request;
   begin
      Decode (Data, Length, OK, Decoded);
      pragma Assert (OK = Expected);
      pragma Assert (if not OK then Decoded = Empty_Request);
   end Check;

   procedure Check_Base with Global => null, Always_Terminates is
      OK : Boolean;
      Item : Request;
   begin
      Decode (Base, 192, OK, Item);
      pragma Assert (OK);
      pragma Assert (Item.Action = Propose and Item.Before_Phase = 1 and
                     Item.After_Phase = 2);
      pragma Assert (Item.Capability = Digest'(others => 11));
      pragma Assert (Item.Source = Digest'(others => 22));
      pragma Assert (Item.Transaction = Digest'(others => 33));
      pragma Assert (Item.Payload = Digest'(others => 44));
      pragma Assert (Item.Predecessor_Receipt = Digest'(others => 55));
      pragma Assert (Item.Before_Generation = 2 and Item.Target_Generation = 3);
   end Check_Base;

   procedure Check_Digest (Field : Natural) with Global => null, Always_Terminates, Pre => Field <= 4 is
      Bytes : Frame := Base;
      OK : Boolean;
      Item : Request;
   begin
      case Field is
         when 0 => Bytes (9 .. 40) := [1, 2, 3, 4, 5, 6, 7, 8,
            9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
            25, 26, 27, 28, 29, 30, 31, 32];
         when 1 => Bytes (41 .. 72) := [1, 2, 3, 4, 5, 6, 7, 8,
            9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
            25, 26, 27, 28, 29, 30, 31, 32];
         when 2 => Bytes (73 .. 104) := [1, 2, 3, 4, 5, 6, 7, 8,
            9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
            25, 26, 27, 28, 29, 30, 31, 32];
         when 3 => Bytes (105 .. 136) := [1, 2, 3, 4, 5, 6, 7, 8,
            9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
            25, 26, 27, 28, 29, 30, 31, 32];
         when others => Bytes (137 .. 168) := [1, 2, 3, 4, 5, 6, 7, 8,
            9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
            25, 26, 27, 28, 29, 30, 31, 32];
      end case;
      Decode (Bytes, 192, OK, Item);
      pragma Assert (OK);
      pragma Assert (Item.Capability =
        (if Field = 0 then Pattern else Digest'(others => 11)));
      pragma Assert (Item.Source =
        (if Field = 1 then Pattern else Digest'(others => 22)));
      pragma Assert (Item.Transaction =
        (if Field = 2 then Pattern else Digest'(others => 33)));
      pragma Assert (Item.Payload =
        (if Field = 3 then Pattern else Digest'(others => 44)));
      pragma Assert (Item.Predecessor_Receipt =
        (if Field = 4 then Pattern else Digest'(others => 55)));
   end Check_Digest;

   procedure Check_Generations with Global => null, Always_Terminates is
      Bytes : Frame := Base;
      OK : Boolean;
      Item : Request;
   begin
      Bytes (169 .. 176) := [1, 2, 3, 4, 5, 6, 7, 8];
      Bytes (177 .. 184) := [1, 2, 3, 4, 5, 6, 7, 8];
      Decode (Bytes, 192, OK, Item);
      pragma Assert (OK);
      pragma Assert (Item.Before_Generation = 72_623_859_790_382_856);
      pragma Assert (Item.Target_Generation = 72_623_859_790_382_856);
      Bytes (169 .. 176) := [127, 255, 255, 255, 255, 255, 255, 255];
      Bytes (177 .. 184) := [127, 255, 255, 255, 255, 255, 255, 255];
      Decode (Bytes, 192, OK, Item);
      pragma Assert (OK and Item.Before_Generation = Generation'Last and
                     Item.Target_Generation = Generation'Last);
      Bytes (169 .. 184) := [others => 0];
      Decode (Bytes, 192, OK, Item);
      pragma Assert (OK and Item.Before_Generation = 0 and
                     Item.Target_Generation = 0);
      Bytes (169) := 128;
      Check (Bytes, 192, False);
      Bytes := Base;
      Bytes (177) := 128;
      Check (Bytes, 192, False);
   end Check_Generations;

   procedure Check_Header (Value : Digest_Byte)
   with Global => null, Always_Terminates is
      Bytes : Frame := Base;
   begin
      Bytes (1) := Value;
      Check (Bytes, 192, Value = 1);
      Bytes := Base;
      Bytes (2) := Value;
      Check (Bytes, 192, Value in 1 .. 2);
      Bytes := Base;
      Bytes (3) := Value;
      Check (Bytes, 192, Value <= 10);
      Bytes := Base;
      Bytes (4) := Value;
      Check (Bytes, 192, Value <= 10);
   end Check_Header;

   procedure Check_Reserved (Index : Positive)
   with Global => null, Always_Terminates,
     Pre => Index in 5 .. 8 or else Index in 185 .. 192
   is
      Bytes : Frame := Base;
   begin
      Bytes (Index) := 1;
      Check (Bytes, 192, False);
   end Check_Reserved;

   procedure Check_Length (Length : Natural)
   with Global => null, Always_Terminates, Pre => Length /= 192
   is
   begin
      Check (Base, Length, False);
   end Check_Length;

begin
   Check_Base;
   Check_Generations;
   for Field in 0 .. 4 loop
      Check_Digest (Field);
   end loop;
   for Length in Natural range 0 .. 191 loop
      Check_Length (Length);
   end loop;
   Check_Length (193);
   Check_Length (Natural'Last);
   for Value in Digest_Byte loop
      Check_Header (Value);
   end loop;
   for Index in 1 .. 192 loop
      if Index in 5 .. 8 or else Index in 185 .. 192 then
         Check_Reserved (Index);
      end if;
   end loop;
end Request_Wire_Tests;
