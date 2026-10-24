package body SIA_Grant_Lifetime with SPARK_Mode is
   function Classify_Scoped
     (Retained : Scoped_Grant; Current : Scope;
      Sender : User_Id; Now : Tick; Item : Request) return Classification
   is
   begin
      if not Same_Domain (Retained.Domain, Current) then
         return Denied;
      end if;
      return Classify (Retained.Authority, Sender, Now, Item);
   end Classify_Scoped;
end SIA_Grant_Lifetime;
