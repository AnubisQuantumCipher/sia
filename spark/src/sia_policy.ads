--  Pure policy only. External observations are not authenticated by this unit.
package SIA_Policy with SPARK_Mode, Pure is
   type Origin is (Source_Record, Derived_Record, Model_Record, Legacy_Record);
   type Completeness is
     (Not_Observed, Unavailable, Observed_Empty, Verified_Complete);
   type Generation is range 0 .. 2 ** 63 - 1;
   No_Generation : constant Generation := 0;
   type Digest_Byte is mod 2 ** 8;
   type Digest is array (1 .. 32) of Digest_Byte;

   type Binding is record
      Epoch : Generation;
      Transaction : Digest;
   end record;

   type Witness is record
      Present : Boolean;
      Durable : Boolean;
      Bound_To : Binding;
   end record;

   type Publication is record
      Target : Binding;
      Corpus : Witness;
      Index : Witness;
      Graph : Witness;
      Ledger : Witness;
      Recovery_Debt : Boolean;
      Source_State : Completeness;
   end record;

   function Same_Binding (Left, Right : Binding) return Boolean is
     (Left.Epoch = Right.Epoch and then
      Left.Transaction = Right.Transaction)
   with Global => null;

   function Bound_Durable (Item : Witness; Target : Binding) return Boolean is
     (Item.Present and then Item.Durable and then
      Target.Epoch /= No_Generation and then
      Same_Binding (Item.Bound_To, Target))
   with Global => null;

   function Source_Complete (State : Completeness) return Boolean is
     (State = Observed_Empty or else State = Verified_Complete)
   with Global => null;

   --  Evidence means provenance of a source record, never factual truth.
   function Admit_Source_Evidence
     (From : Origin; State : Completeness; Authenticated : Boolean)
      return Boolean
   with Global => null,
     Post => Admit_Source_Evidence'Result =
       (From = Source_Record and then State = Verified_Complete and then
        Authenticated);

   function Publication_Joined (State : Publication) return Boolean
   with Global => null,
     Post => Publication_Joined'Result =
       (Source_Complete (State.Source_State) and then
        not State.Recovery_Debt and then
        Bound_Durable (State.Corpus, State.Target) and then
        Bound_Durable (State.Index, State.Target) and then
        Bound_Durable (State.Graph, State.Target) and then
        Bound_Durable (State.Ledger, State.Target));

   --  Cursor/archive witnesses must be observed after their durable effects.
   function Acknowledge
     (State : Publication; Archive, Cursors : Witness) return Boolean
   with Global => null,
     Post => Acknowledge'Result =
       (Publication_Joined (State) and then Bound_Durable (Archive, State.Target) and then
        Bound_Durable (Cursors, State.Target));
end SIA_Policy;
