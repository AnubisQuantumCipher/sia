package body SIA_Transactions with SPARK_Mode is
   function Decide (Current : State; Item : Request) return Decision is
      Result : Decision := Refuse;
   begin
      if Bound_Request (Current, Item) then
         if Current.Completed = Item.Before
           and then Current.Last_Receipt = Item.Predecessor_Receipt
         then
            Result := Apply;
         elsif Current.Completed = Item.After
           and then Current.Last_Receipt = Item.Receipt
           and then Current.Previous_Receipt = Item.Predecessor_Receipt
         then
            Result := Already_Applied;
         end if;
      end if;
      return Result;
   end Decide;

   procedure Reduce
     (Current : in out State; Item : Request; Result : out Decision) is
   begin
      Result := Decide (Current, Item);
      if Result = Apply then
         Current.Previous_Receipt := Current.Last_Receipt;
         Current.Completed := Item.After;
         Current.Last_Receipt := Item.Receipt;
      end if;
   end Reduce;
end SIA_Transactions;
