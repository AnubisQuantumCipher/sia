package body SIA_Continuity_Checkpoint_Wire with SPARK_Mode is
   procedure Decode_Header (Bytes : Checkpoint_Bytes; Item : in out Checkpoint)
   with Global => null, Always_Terminates,
     Pre => Header_Valid (Bytes),
     Post => Header_Decoded_As (Bytes, Item) and then
       Item.Claims = Item.Claims'Old and then
       Item.Operations = Item.Operations'Old
   is
   begin
      Item.Scope := Context_Value (Context_Payload (Bytes));
      Item.Identity := Digest (Bytes (161 .. 192));
      Item.Previous := Digest (Bytes (193 .. 224));
      Item.Capture := Digest (Bytes (225 .. 256));
      Item.Epoch := Word_Value (Word (Bytes (257 .. 264)));
      Item.Through := Word_Value (Word (Bytes (265 .. 272)));
      Item.Retention_Epoch := Word_Value (Word (Bytes (273 .. 280)));
      Item.Count := Claim_Count (Bytes (294));
      Item.Operations_Count := Operation_Count (Bytes (295));
      for Kind in Claim_Kind loop
         Item.Coverage (Kind) :=
           Coverage_Value (Bytes (Coverage_Positions (Kind)));
         pragma Loop_Invariant
           (for all K in Claim_Kind'First .. Kind =>
              Item.Coverage (K) =
                Coverage_Value (Bytes (Coverage_Positions (K))));
      end loop;
   end Decode_Header;

   procedure Decode
     (Bytes : Checkpoint_Bytes; Accepted : out Boolean; Item : out Checkpoint)
   is
      Nested_Accepted : Boolean;
      --  Procedure scope avoids a GNATprove limitation on composite locals
      --  declared inside loops before a loop invariant. Both are overwritten
      --  by a total decoder before each read and cannot escape this call.
      Decoded_Claim : Claim;
      Decoded_Operation : SIA_Continuity.Operation;
   begin
      Item := Empty_Checkpoint;
      Accepted := Valid (Bytes);
      if not Accepted then
         return;
      end if;
      Decode_Header (Bytes, Item);
      for I in Claim_Index loop
         Decode (Claim_Payload (Bytes, I), Nested_Accepted, Decoded_Claim);
         pragma Assert (Nested_Accepted);
         Item.Claims := (Item.Claims with delta I => Decoded_Claim);
         pragma Loop_Invariant (Header_Decoded_As (Bytes, Item));
         pragma Loop_Invariant
           (for all J in 1 .. I =>
              Decoded_As (Claim_Payload (Bytes, J), Item.Claims (J)));
      end loop;
      for I in Operation_Index loop
         Decode (Operation_Payload (Bytes, I),
                 Nested_Accepted, Decoded_Operation);
         pragma Assert (Nested_Accepted);
         Item.Operations := (Item.Operations with delta I => Decoded_Operation);
         pragma Loop_Invariant (Header_Decoded_As (Bytes, Item));
         pragma Loop_Invariant
           (for all J in Claim_Index =>
              Decoded_As (Claim_Payload (Bytes, J), Item.Claims (J)));
         pragma Loop_Invariant
           (for all J in 1 .. I =>
              Decoded_As (Operation_Payload (Bytes, J), Item.Operations (J)));
      end loop;
   end Decode;
end SIA_Continuity_Checkpoint_Wire;
