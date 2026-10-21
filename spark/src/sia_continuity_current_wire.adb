package body SIA_Continuity_Current_Wire with SPARK_Mode is
   procedure Decode_Header
     (Bytes : Current_Bytes; Item : in out Current_Evidence)
   with Global => null, Always_Terminates,
     Pre => Header_Valid (Bytes),
     Post => Header_Decoded_As (Bytes, Item) and then
       Item.Claims = Item.Claims'Old and then
       Item.Operations = Item.Operations'Old
   is
      Nested_Accepted : Boolean;
   begin
      Item.Scope := Context_Value (Context_Payload (Bytes));
      Item.Checkpoint_Id := Digest (Bytes (161 .. 192));
      Item.Capture := Digest (Bytes (193 .. 224));
      Item.Epoch := Word_Value (Word (Bytes (225 .. 232)));
      Item.Through := Word_Value (Word (Bytes (233 .. 240)));
      Item.Retention_Epoch := Word_Value (Word (Bytes (241 .. 248)));
      Decode (Manifest_Payload (Bytes), Nested_Accepted, Item.Manifest);
      pragma Assert (Nested_Accepted);
      Decode (Originals_Payload (Bytes), Nested_Accepted, Item.Originals);
      pragma Assert (Nested_Accepted);
   end Decode_Header;

   procedure Decode
     (Bytes : Current_Bytes; Accepted : out Boolean; Item : out Current_Evidence)
   is
      Nested_Accepted : Boolean;
      --  Total nested decoders overwrite these before use. Procedure scope
      --  avoids GNATprove's composite-block-local loop-invariant limitation.
      Decoded_Claim : Claim_Observation;
      Decoded_Operation : Operation_Observation;
   begin
      Item := Empty_Current;
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
end SIA_Continuity_Current_Wire;
