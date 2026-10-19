with SIA_Policy;

--  Abstract durable-prefix reducer. Receipt authenticity is an external duty.
package SIA_Transactions with SPARK_Mode, Pure is
   use SIA_Policy;

   type Phase is
     (Source_Retained, Corpus_Committed, Index_Bound, Graph_Status_Bound,
      Effects_Committed, Effects_Archived, Source_Archived, Refusals_Settled,
      Journals_Durable, Main_Cursor_Durable, Ack_Committed);

   type State is record
      Transaction : Binding;
      Completed : Phase;
      Last_Receipt : Digest;
      Previous_Receipt : Digest;
   end record;

   type Request is record
      Transaction : Binding;
      Before : Phase;
      After : Phase;
      Receipt : Digest;
      Predecessor_Receipt : Digest;
      Effect : Witness;
   end record;

   type Decision is (Refuse, Apply, Already_Applied);

   function Successor (Before, After : Phase) return Boolean is
     (Before /= Phase'Last and then
      Phase'Pos (After) = Phase'Pos (Before) + 1)
   with Global => null;

   function Bound_Request (Current : State; Item : Request) return Boolean is
     (Same_Binding (Current.Transaction, Item.Transaction) and then
      Bound_Durable (Item.Effect, Item.Transaction) and then
      Successor (Item.Before, Item.After))
   with Global => null;

   function Decide (Current : State; Item : Request) return Decision
   with Global => null,
     Contract_Cases =>
       (not Bound_Request (Current, Item) => Decide'Result = Refuse,
        Bound_Request (Current, Item) and then
          Current.Completed = Item.Before and then
          Current.Last_Receipt = Item.Predecessor_Receipt =>
            Decide'Result = Apply,
        Bound_Request (Current, Item) and then
          Current.Completed = Item.After and then
          Current.Last_Receipt = Item.Receipt and then
          Current.Previous_Receipt = Item.Predecessor_Receipt =>
            Decide'Result = Already_Applied,
        others => Decide'Result = Refuse);

   --  Only updates the abstract state. It performs no durable filesystem I/O.
   procedure Reduce
     (Current : in out State; Item : Request; Result : out Decision)
   with Global => null,
     Depends => (Current => (Current, Item), Result => (Current, Item)),
     Always_Terminates,
     Post =>
       Result = Decide (Current'Old, Item) and then
       Current.Transaction = Current'Old.Transaction and then
       (if Result = Apply then
          Current.Completed = Item.After and then
          Current.Last_Receipt = Item.Receipt and then
          Current.Previous_Receipt = Current'Old.Last_Receipt and then
          Successor (Current'Old.Completed, Current.Completed)
        else Current = Current'Old);
end SIA_Transactions;
