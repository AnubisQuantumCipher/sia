with SIA_Policy; use SIA_Policy;
with SIA_Request_Wire; use SIA_Request_Wire;

procedure Request_Wire_Tests with SPARK_Mode is
   Base : constant Frame :=
     [1 => 1, 2 => 2, 3 => 1, 4 => 2, 176 => 2, 184 => 3,
      9 .. 40 => 11, 41 .. 72 => 22, 73 .. 104 => 33,
      105 .. 136 => 44, 137 .. 168 => 55, others => 0];
   Bytes : Frame;
   Accepted : Boolean;
   Item : Request;

   procedure Check (Data : Frame; Length : Natural; Expected : Boolean)
   with Pre => Expected = Valid (Data, Length)
   is
      OK : Boolean;
      Decoded : Request;
   begin
      Decode (Data, Length, OK, Decoded);
      pragma Assert (OK = Expected);
      pragma Assert (if not OK then Decoded = Empty_Request);
   end Check;

begin
   Decode (Base, 192, Accepted, Item);
   pragma Assert (Accepted);
   pragma Assert (Item.Action = Propose and Item.Before_Phase = 1 and
                  Item.After_Phase = 2);
   pragma Assert (Item.Capability = Digest'(others => 11));
   pragma Assert (Item.Source = Digest'(others => 22));
   pragma Assert (Item.Transaction = Digest'(others => 33));
   pragma Assert (Item.Payload = Digest'(others => 44));
   pragma Assert (Item.Predecessor_Receipt = Digest'(others => 55));
   pragma Assert (Item.Before_Generation = 2 and Item.Target_Generation = 3);
   Bytes := Base;
   Bytes (169 .. 176) := [1, 2, 3, 4, 5, 6, 7, 8];
   Bytes (9 .. 40) := [1, 2, 3, 4, 5, 6, 7, 8,
                       9, 10, 11, 12, 13, 14, 15, 16,
                       17, 18, 19, 20, 21, 22, 23, 24,
                       25, 26, 27, 28, 29, 30, 31, 32];
   Decode (Bytes, 192, Accepted, Item);
   pragma Assert (Accepted);
   pragma Assert (Item.Before_Generation = 72_623_859_790_382_856);
   pragma Assert (Item.Capability = Digest'[1, 2, 3, 4, 5, 6, 7, 8,
      9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
      25, 26, 27, 28, 29, 30, 31, 32]);
   for Length in Natural range 0 .. 191 loop
      Check (Base, Length, False);
   end loop;
   Check (Base, 193, False);
   Check (Base, Natural'Last, False);
   for Value in Digest_Byte loop
      Bytes := Base;
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
   end loop;
   for Index in 1 .. 192 loop
      if Index in 5 .. 8 or else Index in 185 .. 192 then
         Bytes := Base;
         Bytes (Index) := 1;
         Check (Bytes, 192, False);
      end if;
   end loop;
   Bytes := Base;
   Bytes (169) := 128;
   Check (Bytes, 192, False);
   Bytes := Base;
   Bytes (177) := 128;
   Check (Bytes, 192, False);
end Request_Wire_Tests;
