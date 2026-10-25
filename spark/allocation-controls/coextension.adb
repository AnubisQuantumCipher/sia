procedure Coextension is
   type Holder (Value : access Integer) is limited null record;
   Item : Holder (new Integer'(7));
begin
   if Item.Value.all /= 7 then
      raise Program_Error;
   end if;
end Coextension;
