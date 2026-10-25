procedure Parameter_Allocator is
   procedure Consume (Value : access Integer) is
   begin
      if Value.all /= 7 then
         raise Program_Error;
      end if;
   end Consume;
begin
   Consume (new Integer'(7));
end Parameter_Allocator;
