package body SIA_Continuity_Response_Wire with SPARK_Mode is
   procedure Decode
     (Bytes : Response_Bytes; Accepted : out Boolean; Item : out Frame_Decision)
   is
   begin
      Item := (Malformed, Invalid_Checkpoint, Invalid_Before);
      Accepted := Valid (Bytes);
      if not Accepted then
         return;
      end if;
      if Bytes (6) = 1 then
         Item := (Restore_Request, Restoration_Value (Bytes (8)), Invalid_Before);
      elsif Bytes (6) = 2 then
         Item := (Transition_Request, Invalid_Checkpoint,
                  Transition_Value (Bytes (8)));
      end if;
   end Decode;
end SIA_Continuity_Response_Wire;
