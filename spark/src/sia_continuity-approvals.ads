--  Conditional correspondence policy, NOT an action-authority service.
--  Authenticated/custody observations must come from the protected producer;
--  this unit neither authenticates original bytes nor interprets human prose.
package SIA_Continuity.Approvals with SPARK_Mode, Pure is
   Empty_Context : constant Context := (others => [others => 0]);
   Empty_Witness : constant Witness :=
     (False, False, (Epoch => 0, Transaction => [others => 0]));
   type Authentication is (Unknown_Source, Rejected_Source, Authenticated);
   type Channel is
     (Unknown_Channel, Human_Input, Assistant_Question, Tool_Output,
      Automatic_Continuation, Imported_Content);
   type Decision is (Undetermined, Approved, Denied, Deferred, Ambiguous);
   type Currentness is (Unknown_Current, Current, Revoked, Superseded, Expired);
   type Decision_Form is (Unknown_Form, Queried_Decision, Direct_Instruction);

   type Action_Scope is record
      Proposal, Action, Conditions : Digest := Zero;
   end record;
   Empty_Action : constant Action_Scope := (others => [others => 0]);
   type Occurrence is record
      Lifecycle, Target_Turn : Digest := Zero;
   end record;
   Empty_Occurrence : constant Occurrence := (others => [others => 0]);
   type Request_Selection is record
      Descriptor, Question, Question_Item, Response : Digest := Zero;
      Requested : Action_Scope := Empty_Action;
   end record;
   Empty_Request : constant Request_Selection := (others => <>);
   type Request_Selections is array (Claim_Index) of Request_Selection;
   type Restore_Selection is record
      Where_Now : Occurrence := Empty_Occurrence;
      Requests : Request_Selections := [others => Empty_Request];
   end record;
   Empty_Restore_Selection : constant Restore_Selection := (others => <>);

   type Original_Event is record
      Scope : Context := Empty_Context;
      Identity, Content, Producer, Order_Domain : Digest := Zero;
      Sequence : Generation := 0;
      Speaker : Role := Tool;
      From : Origin := Legacy_Record;
      Route : Channel := Unknown_Channel;
      Source_State : Authentication := Unknown_Source;
      Custody : Witness := Empty_Witness;
      Question_Item, Reply_To : Digest := Zero;
      Requested : Action_Scope := Empty_Action;
      Answer : Decision := Undetermined;
   end record;
   Empty_Original : constant Original_Event := (others => <>);

   type Current_Selection is record
      Descriptor, Question, Question_Item, Response : Digest := Zero;
      Requested : Action_Scope := Empty_Action;
      Form : Decision_Form := Unknown_Form;
      State : Currentness := Unknown_Current;
      Source_State : Authentication := Unknown_Source;
      Custody : Witness := Empty_Witness;
      Checkpoint_Id : Digest := Zero;
      Epoch, Through, Retention_Epoch : Generation := 0;
      Where_Now : Occurrence := Empty_Occurrence;
   end record;
   Empty_Selection : constant Current_Selection := (others => <>);
   type Observation is record
      Checkpoint_Id, Claim_Id, Slot : Digest := Zero;
      Epoch : Generation := 0;
      Question, Response : Original_Event := Empty_Original;
      Selected : Current_Selection := Empty_Selection;
   end record;
   Empty_Observation : constant Observation := (others => <>);
   type Observations is array (Claim_Index) of Observation;

   type Link_Status is
     (Not_Checked, No_Observation, Reference_Correspondence,
      Unexpected_Observation, Unexpected_Selection, Duplicate_Response,
      Claim_Mismatch, Source_Unresolved,
      Original_Order_Unresolved, Reply_Link_Unresolved, Scope_Unresolved,
      Current_Unresolved, Unsupported_Form, Decision_Unresolved,
      Decision_Denied, Decision_Deferred, Decision_Ambiguous, Decision_Revoked,
      Decision_Superseded, Decision_Expired);

   function Active_Permission (Item : Checkpoint; I : Claim_Index)
      return Boolean is
     (I <= Item.Count and then Item.Claims (I).Kind = Permission_Reference
      and then (for all J in I + 1 .. Item.Count =>
                  Item.Claims (J).Slot /= Item.Claims (I).Slot))
   with Global => null;

   function Has_Permission (Item : Checkpoint) return Boolean is
     (for some I in Claim_Index => Active_Permission (Item, I))
   with Global => null;

   function Key_Matches
     (Item : Checkpoint; I : Claim_Index; Seen : Observation)
      return Boolean is
     (Seen.Checkpoint_Id = Item.Identity and then Seen.Epoch = Item.Epoch
      and then Seen.Claim_Id = Item.Claims (I).Identity
      and then Seen.Slot = Item.Claims (I).Slot
      and then Seen.Response.Identity = Item.Claims (I).Source_Record_Id
      and then Seen.Response.Sequence = Item.Claims (I).Sequence
      and then Seen.Response.Speaker = Item.Claims (I).Speaker
      and then Seen.Response.From = Item.Claims (I).From)
   with Global => null;

   function Original_Ready (Item : Checkpoint; Source : Original_Event)
      return Boolean is
     (Source.Scope = Item.Scope and then Source.Identity /= Zero
      and then Source.Content /= Zero and then Source.Producer /= Zero
      and then Source.Order_Domain /= Zero
      and then Source.Source_State = Authenticated
      and then Bound_Durable
        (Source.Custody, (Item.Retention_Epoch, Source.Content)))
   with Global => null;

   function Sources_Ready (Item : Checkpoint; Seen : Observation)
      return Boolean is
     (Original_Ready (Item, Seen.Question)
      and then Original_Ready (Item, Seen.Response)
      and then Seen.Question.Speaker = Assistant
      and then Seen.Question.From = Model_Record
      and then Seen.Question.Route = Assistant_Question
      and then Seen.Response.Speaker = User
      and then Seen.Response.From = Source_Record
      and then Seen.Response.Route = Human_Input)
   with Global => null;

   function Ordered (Item : Checkpoint; Seen : Observation)
      return Boolean is
     (Seen.Question.Order_Domain = Seen.Response.Order_Domain
      and then Seen.Question.Sequence /= 0
      and then Seen.Question.Sequence < Seen.Response.Sequence
      and then Seen.Response.Sequence <= Item.Through)
   with Global => null;

   function Reply_Matches (Seen : Observation) return Boolean is
     (Seen.Question.Identity /= Seen.Response.Identity
      and then Seen.Question.Question_Item /= Zero
      and then Seen.Question.Reply_To = Zero
      and then Seen.Question.Answer = Undetermined
      and then Seen.Response.Reply_To = Seen.Question.Identity
      and then Seen.Response.Question_Item = Seen.Question.Question_Item)
   with Global => null;

   function Scope_Matches (Seen : Observation) return Boolean is
     (Seen.Question.Requested.Proposal /= Zero
      and then Seen.Question.Requested.Action /= Zero
      and then Seen.Question.Requested.Conditions /= Zero
      and then Seen.Response.Requested = Seen.Question.Requested
      and then Seen.Selected.Requested = Seen.Question.Requested)
   with Global => null;

   function Selection_Matches
     (Item : Checkpoint; I : Claim_Index; Expected : Restore_Selection;
      Seen : Observation)
      return Boolean is
     (Expected.Where_Now.Lifecycle /= Zero
      and then Expected.Where_Now.Target_Turn /= Zero
      and then Seen.Selected.Where_Now = Expected.Where_Now
      and then Expected.Requests (I).Descriptor /= Zero
      and then Seen.Selected.Descriptor = Expected.Requests (I).Descriptor
      and then Seen.Selected.Question = Expected.Requests (I).Question
      and then Seen.Selected.Question_Item = Expected.Requests (I).Question_Item
      and then Seen.Selected.Response = Expected.Requests (I).Response
      and then Seen.Selected.Requested = Expected.Requests (I).Requested
      and then Seen.Selected.Question = Seen.Question.Identity
      and then Seen.Selected.Question_Item = Seen.Question.Question_Item
      and then Seen.Selected.Response = Seen.Response.Identity
      and then Seen.Selected.Checkpoint_Id = Item.Identity
      and then Seen.Selected.Epoch = Item.Epoch
      and then Seen.Selected.Through = Item.Through
      and then Seen.Selected.Retention_Epoch = Item.Retention_Epoch
      and then Seen.Selected.Source_State = Authenticated
      and then Bound_Durable
        (Seen.Selected.Custody, (Item.Epoch, Seen.Selected.Descriptor)))
   with Global => null;

   function Classify_Link
     (Item : Checkpoint; I : Claim_Index; Expected : Restore_Selection;
      Seen : Observation) return Link_Status is
     (if not Key_Matches (Item, I, Seen) then Claim_Mismatch
      elsif not Sources_Ready (Item, Seen) then Source_Unresolved
      elsif not Ordered (Item, Seen) then Original_Order_Unresolved
      elsif not Reply_Matches (Seen) then Reply_Link_Unresolved
      elsif not Scope_Matches (Seen) then Scope_Unresolved
      elsif not Selection_Matches (Item, I, Expected, Seen) then Current_Unresolved
      elsif Seen.Selected.Form /= Queried_Decision then Unsupported_Form
      elsif Seen.Selected.State = Unknown_Current then Current_Unresolved
      elsif Seen.Selected.State = Revoked then Decision_Revoked
      elsif Seen.Selected.State = Superseded then Decision_Superseded
      elsif Seen.Selected.State = Expired then Decision_Expired
      elsif Seen.Response.Answer = Denied then Decision_Denied
      elsif Seen.Response.Answer = Deferred then Decision_Deferred
      elsif Seen.Response.Answer = Ambiguous then Decision_Ambiguous
      elsif Seen.Response.Answer = Undetermined then Decision_Unresolved
      else Reference_Correspondence)
   with Global => null;

   function Slot_Status
     (Item : Checkpoint; I : Claim_Index; Expected : Restore_Selection;
      Seen : Observations) return Link_Status is
     (if Active_Permission (Item, I) then
         (if (for some J in 1 .. I - 1 =>
                Active_Permission (Item, J) and then
                Seen (J).Response.Identity = Seen (I).Response.Identity)
          then Duplicate_Response
          else Classify_Link (Item, I, Expected, Seen (I)))
      elsif Seen (I) /= Empty_Observation then Unexpected_Observation
      elsif Expected.Requests (I) /= Empty_Request then Unexpected_Selection
      else No_Observation)
   with Global => null;

   function Slots_Ready
     (Item : Checkpoint; Expected : Restore_Selection; Seen : Observations)
      return Boolean is
     (for all I in Claim_Index =>
        Slot_Status (Item, I, Expected, Seen) in
          No_Observation | Reference_Correspondence)
   with Global => null;

   type Resolution is record
      Base : Restoration;
      Detail : Link_Status;
      At_Claim : Claim_Count;
   end record;

   --  Total over every representable input. No caller precondition supplies
   --  the correspondence that this function must itself establish.
   function Restore
     (Item : Checkpoint; Current : Current_Evidence; Expected : Restore_Selection;
      Seen : Observations) return Resolution
   with Global => null,
     Post =>
       (if Classify (Item, Current) /= References_Proposed then
           Restore'Result = (Classify (Item, Current), Not_Checked, 0)
        elsif Slots_Ready (Item, Expected, Seen) then
           Restore'Result =
             (References_Proposed,
              (if Has_Permission (Item) then Reference_Correspondence
               else No_Observation), 0)
        else Restore'Result.Base = Need_Evidence
          and then Restore'Result.At_Claim /= 0
          and then Restore'Result.Detail = Slot_Status
            (Item, Restore'Result.At_Claim, Expected, Seen)
          and then Restore'Result.Detail not in
            No_Observation | Reference_Correspondence
          and then (for all J in 1 .. Restore'Result.At_Claim - 1 =>
            Slot_Status (Item, J, Expected, Seen) in
              No_Observation | Reference_Correspondence));
end SIA_Continuity.Approvals;
