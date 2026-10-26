package body SIA_Policy with SPARK_Mode is
   function Admit_Source_Evidence
     (From : Origin; State : Completeness; Authenticated : Boolean)
      return Boolean is
   begin
      return From = Source_Record and then Authenticated
        and then State = Verified_Complete;
   end Admit_Source_Evidence;

   function Publication_Joined (State : Publication) return Boolean is
   begin
      return not State.Recovery_Debt
        and then Source_Complete (State.Source_State)
        and then Bound_Durable (State.Corpus, State.Target)
        and then Bound_Durable (State.Index, State.Target)
        and then Bound_Durable (State.Graph, State.Target)
        and then Bound_Durable (State.Ledger, State.Target);
   end Publication_Joined;

   function Acknowledge
     (State : Publication; Archive, Cursors : Witness) return Boolean is
   begin
      return Publication_Joined (State)
        and then Bound_Durable (Archive, State.Target)
        and then Bound_Durable (Cursors, State.Target);
   end Acknowledge;
end SIA_Policy;
