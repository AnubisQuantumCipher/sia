with SIA_Policy;

--  Pure semantic proposals only: no grants, I/O, signatures or durable effects.
package SIA_Retraction with SPARK_Mode, Pure is
   use SIA_Policy;
   type Descriptor is record
      Identity, Content, Parents, Provenance : Digest;
      Version : Generation;
      From : Origin;
   end record;
   Empty_Descriptor : constant Descriptor :=
     (Identity => [others => 0], Content => [others => 0],
      Parents => [others => 0], Provenance => [others => 0],
      Version => 0, From => Legacy_Record);

   type Request is record
      Target : Descriptor;
      Operation : Digest;
      Before, After : Generation;
   end record;
   Empty_Request : constant Request :=
     (Target => (Identity => [others => 0], Content => [others => 0],
                 Parents => [others => 0], Provenance => [others => 0],
                 Version => 0, From => Legacy_Record),
      Operation => [others => 0],
      Before => 0, After => 0);
   type Phase is (Active, Retraction_Proposed);
   type Plan_State is record
      Item : Descriptor;
      Epoch : Generation;
      Stage : Phase;
      Retained : Request;
   end record;
   type Decision is (Refused, Proposed_Only, Identical_Proposal);

   function Valid_Descriptor (Item : Descriptor) return Boolean is
     (Item.Identity /= Digest'(others => 0) and then Item.Version /= 0)
   with Global => null;

   function Valid_Request (Item : Request) return Boolean is
     (Valid_Descriptor (Item.Target) and then
      Item.Target.From in Derived_Record | Model_Record and then
      Item.Operation /= Digest'(others => 0) and then
      Item.Before /= 0 and then Item.Before < Generation'Last and then
      Item.After = Item.Before + 1)
   with Global => null;

   function Valid_State (State : Plan_State) return Boolean is
     (Valid_Descriptor (State.Item) and then State.Epoch /= 0 and then
      (if State.Stage = Active then State.Retained = Empty_Request
       else Valid_Request (State.Retained) and then
         State.Retained.Target = State.Item and then
         State.Retained.After = State.Epoch))
   with Global => null;

   --  Parents describes an assumed exact manifest observation, not a producer.
   --  No classification establishes transitive descendant invalidation.
   function Classify
     (State : Plan_State; Item : Request;
      Parents : Completeness; Recovery_Debt : Boolean) return Decision
   with Global => null,
     Contract_Cases =>
       (not Valid_State (State) or else not Valid_Request (Item) or else
        Parents /= Verified_Complete or else Recovery_Debt => Classify'Result = Refused,
        Valid_State (State) and then Valid_Request (Item) and then
        Parents = Verified_Complete and then not Recovery_Debt =>
          Classify'Result =
            (if State.Stage = Active and then Item.Target = State.Item and then
                Item.Before = State.Epoch then Proposed_Only
             elsif State.Stage = Retraction_Proposed and then
                Item = State.Retained then Identical_Proposal else Refused));

   procedure Plan
     (State : Plan_State; Item : Request;
      Parents : Completeness; Recovery_Debt : Boolean;
      Candidate : out Plan_State; Result : out Decision)
   with Global => null, Always_Terminates,
     Depends => ((Candidate, Result) => (State, Item, Parents, Recovery_Debt)),
     Post =>
       (Result = Classify (State, Item, Parents, Recovery_Debt) and then
        Candidate.Item = State.Item and then
        (if Result = Proposed_Only then
           Candidate = Plan_State'(Item => State.Item, Epoch => Item.After,
                                  Stage => Retraction_Proposed, Retained => Item)
         else Candidate = State) and then
        (if Valid_State (State) then Valid_State (Candidate)));
end SIA_Retraction;
