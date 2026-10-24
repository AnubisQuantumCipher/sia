package body SIA_Request_Wire with SPARK_Mode is
   procedure Decode
     (Bytes : Frame; Length : Natural; Accepted : out Boolean;
      Item : out Request)
   is
   begin
      Item := Empty_Request;
      Accepted := Valid (Bytes, Length);
      if not Accepted then
         return;
      end if;
      Item.Action := (if Bytes (2) = 1 then Observe else Propose);
      Item.Before_Phase := Natural (Bytes (3));
      Item.After_Phase := Natural (Bytes (4));
      Item.Capability := Digest (Bytes (9 .. 40));
      Item.Source := Digest (Bytes (41 .. 72));
      Item.Transaction := Digest (Bytes (73 .. 104));
      Item.Payload := Digest (Bytes (105 .. 136));
      Item.Predecessor_Receipt := Digest (Bytes (137 .. 168));
      Item.Before_Generation := Generation_Value (Bytes, 169);
      Item.Target_Generation := Generation_Value (Bytes, 177);
   end Decode;
end SIA_Request_Wire;
