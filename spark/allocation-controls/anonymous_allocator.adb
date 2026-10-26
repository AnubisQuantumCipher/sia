procedure Anonymous_Allocator is
   Value : constant access Integer := new Integer'(7);
begin
   if Value.all /= 7 then
      raise Program_Error;
   end if;
end Anonymous_Allocator;
