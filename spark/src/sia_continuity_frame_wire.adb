package body SIA_Continuity_Frame_Wire with SPARK_Mode is
   procedure Decode
     (Bytes : Frame_Bytes; Accepted : out Boolean; Item : out Decoded_Request)
   is
      Nested_Accepted : Boolean;
      Event : Observation;
   begin
      Item := Empty_Request;
      Accepted := Valid (Bytes);
      if not Accepted then
         return;
      end if;
      Decode (Before_Payload (Bytes), Nested_Accepted, Item.Before);
      pragma Assert (Nested_Accepted);
      if Bytes (6) = 1 then
         Decode (Current_Payload (Bytes), Nested_Accepted, Item.Current);
         pragma Assert (Nested_Accepted);
         Item.Kind := Restore_Request;
      else
         Decode (After_Payload (Bytes), Nested_Accepted, Item.After);
         pragma Assert (Nested_Accepted);
         Item.Kind := Transition_Request;
         for I in Operation_Index loop
            Decode (Event_Payload (Bytes, I), Nested_Accepted, Event);
            pragma Assert (Nested_Accepted);
            Item.Events := (Item.Events with delta I => Event);
            pragma Loop_Invariant (Item.Kind = Transition_Request);
            pragma Loop_Invariant
              (Decoded_As (Before_Payload (Bytes), Item.Before));
            pragma Loop_Invariant
              (Decoded_As (After_Payload (Bytes), Item.After));
            pragma Loop_Invariant (Item.Current = Empty_Current);
            pragma Loop_Invariant
              (for all J in 1 .. I =>
                Decoded_As (Event_Payload (Bytes, J), Item.Events (J)));
         end loop;
      end if;
   end Decode;

   procedure Evaluate
     (Bytes : Frame_Bytes; Accepted : out Boolean; Item : out Decoded_Request;
      Result : out Frame_Decision)
   is
   begin
      Decode (Bytes, Accepted, Item);
      Result := Classify (Item);
   end Evaluate;
end SIA_Continuity_Frame_Wire;
