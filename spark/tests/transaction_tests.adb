with SIA_Policy;
with SIA_Transactions;

procedure Transaction_Tests with SPARK_Mode is
   use SIA_Policy;
   use SIA_Transactions;
   Target : constant Binding :=
     (Epoch => 7, Transaction => [others => 11]);
   Good : constant Witness :=
     (Present => True, Durable => True, Bound_To => Target);
   Receipt : constant Digest := [others => 13];

   procedure Check_Triple (At_Phase, From_Phase, To_Phase : Phase)
     with Global => null, Always_Terminates
   is
      Current : constant State :=
        (Transaction => Target, Completed => At_Phase,
         Last_Receipt => Receipt, Previous_Receipt => Receipt);
      Item : constant Request :=
        (Transaction => Target, Before => From_Phase,
         After => To_Phase, Receipt => Receipt,
         Predecessor_Receipt => Receipt, Effect => Good);
   begin
      if Phase'Pos (To_Phase) - Phase'Pos (From_Phase) /= 1 then
         pragma Assert (Decide (Current, Item) = Refuse);
      elsif At_Phase = From_Phase then
         pragma Assert (Decide (Current, Item) = Apply);
      elsif At_Phase = To_Phase then
         pragma Assert (Decide (Current, Item) = Already_Applied);
      else
         pragma Assert (Decide (Current, Item) = Refuse);
      end if;
   end Check_Triple;

   procedure Check_Pairs with Global => null, Always_Terminates is
   begin
      for At_Phase in Phase loop
         for From_Phase in Phase loop
            for To_Phase in Phase loop
               Check_Triple (At_Phase, From_Phase, To_Phase);
            end loop;
         end loop;
      end loop;
   end Check_Pairs;

   procedure Check_Retry with Global => null is
      Current : State :=
        (Transaction => Target, Completed => Source_Retained,
         Last_Receipt => [others => 0], Previous_Receipt => [others => 0]);
      Item : Request :=
        (Transaction => Target, Before => Source_Retained,
         After => Corpus_Committed, Receipt => Receipt,
         Predecessor_Receipt => [others => 0], Effect => Good);
      Outcome : Decision;
      Saved : State;
   begin
      Saved := Current;
      Item.Predecessor_Receipt (1) := 1;
      Reduce (Current, Item, Outcome);
      pragma Assert (Outcome = Refuse and Current = Saved);
      Item.Predecessor_Receipt := [others => 0];
      Reduce (Current, Item, Outcome);
      pragma Assert (Outcome = Apply);
      Saved := Current;
      Reduce (Current, Item, Outcome);
      pragma Assert (Outcome = Already_Applied and Current = Saved);
      Item.Receipt (1) := 14;
      Reduce (Current, Item, Outcome);
      pragma Assert (Outcome = Refuse and Current = Saved);
      Item.Receipt := Receipt;
      Item.Effect.Durable := False;
      Reduce (Current, Item, Outcome);
      pragma Assert (Outcome = Refuse and Current = Saved);
      Item.Effect := Good;
      Item.Transaction.Epoch := 8;
      Item.Effect.Bound_To := Item.Transaction;
      Reduce (Current, Item, Outcome);
      pragma Assert (Outcome = Refuse and Current = Saved);
      Item.Transaction := Target;
      Item.Transaction.Transaction (1) := 12;
      Item.Effect.Bound_To := Item.Transaction;
      Reduce (Current, Item, Outcome);
      pragma Assert (Outcome = Refuse and Current = Saved);
      Item.Transaction := Target;
      Item.Effect := Good;
      Item.Predecessor_Receipt (1) := 1;
      Reduce (Current, Item, Outcome);
      pragma Assert (Outcome = Refuse and Current = Saved);
   end Check_Retry;

   procedure Check_Path with Global => null is
      Current : State :=
        (Transaction => Target, Completed => Source_Retained,
         Last_Receipt => [others => 0], Previous_Receipt => [others => 0]);
      Item : Request :=
        (Transaction => Target, Before => Source_Retained,
         After => Corpus_Committed, Receipt => Receipt,
         Predecessor_Receipt => [others => 0], Effect => Good);
      Outcome : Decision;
   begin
      for Step in Source_Retained .. Main_Cursor_Durable loop
         pragma Loop_Invariant (Current.Completed = Step);
         pragma Loop_Invariant (Current.Transaction = Target);
         Item.Before := Step;
         Item.After := Phase'Succ (Step);
         Item.Predecessor_Receipt := Current.Last_Receipt;
         Item.Receipt :=
           (Item.Receipt with delta 1 => Digest_Byte (Phase'Pos (Step)));
         Reduce (Current, Item, Outcome);
         pragma Assert (Outcome = Apply);
         Reduce (Current, Item, Outcome);
         pragma Assert (Outcome = Already_Applied);
      end loop;
      pragma Assert (Current.Completed = Ack_Committed);
      Item.Before := Source_Retained;
      Item.After := Corpus_Committed;
      Item.Predecessor_Receipt := [others => 0];
      Item.Receipt := Receipt;
      Item.Receipt (1) := 0;
      Reduce (Current, Item, Outcome);
      pragma Assert (Outcome = Refuse);
      pragma Assert (Current.Completed = Ack_Committed);
      Item.Before := Ack_Committed;
      Item.After := Source_Retained;
      Reduce (Current, Item, Outcome);
      pragma Assert (Outcome = Refuse);
      pragma Assert (Current.Completed = Ack_Committed);
   end Check_Path;
begin
   Check_Pairs;
   Check_Retry;
   Check_Path;
end Transaction_Tests;
