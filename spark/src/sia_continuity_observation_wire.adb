package body SIA_Continuity_Observation_Wire with SPARK_Mode is
   procedure Decode
     (Bytes : Claim_Observation_Bytes; Accepted : out Boolean;
      Item : out Claim_Observation)
   is
      Nested_Accepted : Boolean;
   begin
      Item := Empty_Claim_Observation;
      Accepted := Valid (Bytes);
      if not Accepted then
         return;
      end if;
      Item.State := Availability_Value (Bytes (1));
      Decode (Claim_Payload (Bytes), Nested_Accepted, Item.Item);
      pragma Assert (Nested_Accepted);
   end Decode;

   procedure Decode
     (Bytes : Operation_Observation_Bytes; Accepted : out Boolean;
      Item : out Operation_Observation)
   is
      Nested_Accepted : Boolean;
   begin
      Item := Empty_Operation_Observation;
      Accepted := Valid (Bytes);
      if not Accepted then
         return;
      end if;
      Item.State := Availability_Value (Bytes (1));
      Decode (Operation_Payload (Bytes), Nested_Accepted, Item.Item);
      pragma Assert (Nested_Accepted);
   end Decode;

   procedure Decode
     (Bytes : Transition_Observation_Bytes; Accepted : out Boolean;
      Item : out Observation)
   is
      Nested_Accepted : Boolean;
   begin
      Item := Empty_Observation;
      Accepted := Valid (Bytes);
      if not Accepted then
         return;
      end if;
      Item.Before_Id := Digest (Bytes (1 .. 32));
      Item.After_Id := Digest (Bytes (33 .. 64));
      Item.Event_Record_Id := Digest (Bytes (65 .. 96));
      Item.Outcome_Record_Id := Digest (Bytes (97 .. 128));
      Item.Before_Epoch := Word_Value (Word (Bytes (129 .. 136)));
      Item.After_Epoch := Word_Value (Word (Bytes (137 .. 144)));
      Decode (Before_Payload (Bytes),
              Nested_Accepted, Item.Before_Operation);
      pragma Assert (Nested_Accepted);
      Decode (After_Payload (Bytes),
              Nested_Accepted, Item.After_Operation);
      pragma Assert (Nested_Accepted);
      Item.State := Availability_Value (Bytes (433));
      Item.Kind := Event_Value (Bytes (434));
      Item.Has_Outcome := (Bytes (435) = 1);
   end Decode;
end SIA_Continuity_Observation_Wire;
