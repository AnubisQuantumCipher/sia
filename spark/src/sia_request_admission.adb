package body SIA_Request_Admission with SPARK_Mode is
   function Classify
     (Authority : Grant; Sender : User_Id; Now : Tick; Item : Request)
      return Classification
   is
   begin
      if not Matches (Authority, Sender, Now, Item) then
         return Denied;
      elsif Item.Action = Observe then
         return Observe_Only;
      else
         return Proposal_Only;
      end if;
   end Classify;

   procedure Classify_Frame
     (Authority : Grant; Sender : User_Id; Now : Tick;
      Bytes : Frame; Length : Natural; Item : out Request;
      Decision : out Classification)
   is
      Accepted : Boolean;
   begin
      Decode (Bytes, Length, Accepted, Item);
      Decision := Denied;
      if Accepted then
         Decision := Classify (Authority, Sender, Now, Item);
      end if;
   end Classify_Frame;
end SIA_Request_Admission;
