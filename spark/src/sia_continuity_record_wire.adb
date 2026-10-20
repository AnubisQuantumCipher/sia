package body SIA_Continuity_Record_Wire with SPARK_Mode is
   procedure Decode
     (Bytes : Claim_Bytes; Accepted : out Boolean; Item : out Claim)
   is
   begin
      Item := Empty_Claim;
      Accepted := Valid (Bytes);
      if not Accepted then
         return;
      end if;
      Item.Identity := Digest (Bytes (1 .. 32));
      Item.Slot := Digest (Bytes (33 .. 64));
      Item.Source_Record_Id := Digest (Bytes (65 .. 96));
      Item.Sequence := Word_Value (Word (Bytes (97 .. 104)));
      Item.Kind := Kind_Value (Bytes (105));
      Item.From := Origin_Value (Bytes (106));
      Item.Speaker := Role_Value (Bytes (107));
      Item.Replaces := Claim_Count (Bytes (108));
   end Decode;

   procedure Decode
     (Bytes : Operation_Bytes; Accepted : out Boolean;
      Item : out SIA_Continuity.Operation)
   is
   begin
      Item := Empty_Operation;
      Accepted := Valid (Bytes);
      if not Accepted then
         return;
      end if;
      Item.Identity := Digest (Bytes (1 .. 32));
      Item.Action := Digest (Bytes (33 .. 64));
      Item.Source_Record_Id := Digest (Bytes (65 .. 96));
      Item.Result_Record_Id := Digest (Bytes (97 .. 128));
      Item.Stage := Phase_Value (Bytes (129));
      Item.Has_Result := (Bytes (130) = 1);
   end Decode;

   procedure Decode
     (Bytes : Witness_Bytes; Accepted : out Boolean; Item : out Witness)
   is
   begin
      Item := Empty_Witness;
      Accepted := Valid (Bytes);
      if not Accepted then
         return;
      end if;
      Item.Present := (Bytes (1) = 1);
      Item.Durable := (Bytes (2) = 1);
      Item.Bound_To.Epoch := Word_Value (Word (Bytes (3 .. 10)));
      Item.Bound_To.Transaction := Digest (Bytes (11 .. 42));
   end Decode;
end SIA_Continuity_Record_Wire;
