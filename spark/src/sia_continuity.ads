with SIA_Policy;

--  Conditional reference-restoration policy. Producers must authenticate
--  current heads, source descriptors and durability before runtime reliance.
--  No result is an action grant or permission to retry an external operation.
package SIA_Continuity with SPARK_Mode, Pure is
   use SIA_Policy;
   Zero : constant Digest := [others => 0];
   Max_Claims : constant := 64;
   Max_Operations : constant := 16;
   subtype Claim_Count is Natural range 0 .. Max_Claims;
   subtype Claim_Index is Positive range 1 .. Max_Claims;
   subtype Operation_Count is Natural range 0 .. Max_Operations;
   subtype Operation_Index is Positive range 1 .. Max_Operations;

   type Context is record
      Task_Id, Session_Id, Repository, Revision, Dirty : Digest;
   end record;
   type Claim_Kind is
     (Goal, Acceptance, Constraint, Correction, Decision, Rejection,
      Source, Completed, Verification, Failure, Next_Action,
      Permission_Reference, Pending_Approval);
   type Role is (User, Assistant, Tool, System_Role);
   type Coverage_State is
     (Not_Observed, Unavailable, Observed_Empty, Partial, Complete);
   type Coverage_Array is array (Claim_Kind) of Coverage_State;
   type Claim is record
      Identity, Slot, Source_Record_Id : Digest;
      Sequence : Generation;
      Kind : Claim_Kind;
      From : Origin;
      Speaker : Role;
      Replaces : Claim_Count;
   end record;
   Empty_Claim : constant Claim :=
     (Identity => [others => 0], Slot => [others => 0],
      Source_Record_Id => [others => 0], Sequence => 0, Kind => Goal,
      From => Legacy_Record, Speaker => Tool, Replaces => 0);
   type Claim_Array is array (Claim_Index) of Claim;

   type Operation_Phase is
     (Planned, Dispatched, Uncertain, Observed_Complete, Acknowledged);
   type Operation is record
      Identity, Action, Source_Record_Id, Result_Record_Id : Digest;
      Stage : Operation_Phase;
      Has_Result : Boolean;
   end record;
   Empty_Operation : constant Operation :=
     (Identity => [others => 0], Action => [others => 0],
      Source_Record_Id => [others => 0], Result_Record_Id => [others => 0],
      Stage => Planned, Has_Result => False);
   type Operation_Array is array (Operation_Index) of Operation;

   type Checkpoint is record
      Scope : Context;
      Identity, Previous, Capture : Digest;
      Epoch, Through, Retention_Epoch : Generation;
      Coverage : Coverage_Array;
      Count : Claim_Count;
      Claims : Claim_Array;
      Operations_Count : Operation_Count;
      Operations : Operation_Array;
   end record;
   type Availability is (Unknown, Missing, Retained, Retracted);
   type Claim_Observation is record
      State : Availability;
      Item : Claim;
   end record;
   type Claim_Observations is array (Claim_Index) of Claim_Observation;
   type Operation_Observation is record
      State : Availability;
      Item : Operation;
   end record;
   type Operation_Observations is
     array (Operation_Index) of Operation_Observation;
   type Current_Evidence is record
      Scope : Context;
      Checkpoint_Id, Capture : Digest;
      Epoch, Through, Retention_Epoch : Generation;
      Manifest, Originals : Witness;
      Claims : Claim_Observations;
      Operations : Operation_Observations;
   end record;
   type Restoration is
     (Invalid_Checkpoint, Identity_Mismatch, Stale_Checkpoint,
      Need_Evidence, Reconcile_Repository, Reconcile_Operations,
      References_Proposed);

   function Valid_Claim (Item : Claim) return Boolean is
     (Item.Identity /= Zero and then Item.Slot /= Zero and then
      Item.Sequence /= 0 and then
      (if Item.Speaker = Assistant then Item.From = Model_Record) and then
      (if Item.Kind = Permission_Reference then
         Item.Speaker = User and then Item.From = Source_Record))
   with Global => null;

   function Valid_Predecessor (Item : Checkpoint; I : Claim_Index)
      return Boolean is
     (if Item.Claims (I).Replaces = 0 then
         (for all J in 1 .. I - 1 =>
            Item.Claims (J).Slot /= Item.Claims (I).Slot)
      else Item.Claims (I).Replaces < I and then
         Item.Claims (Item.Claims (I).Replaces).Slot = Item.Claims (I).Slot
         and then Item.Claims (Item.Claims (I).Replaces).Kind =
           Item.Claims (I).Kind
         and then Item.Claims (Item.Claims (I).Replaces).From =
           Item.Claims (I).From
         and then Item.Claims (Item.Claims (I).Replaces).Speaker =
           Item.Claims (I).Speaker
         and then
           (for all J in Item.Claims (I).Replaces + 1 .. I - 1 =>
              Item.Claims (J).Slot /= Item.Claims (I).Slot))
   with Global => null;

   function Valid_Claims (Item : Checkpoint) return Boolean is
     ((for all I in 1 .. Item.Count =>
         Valid_Claim (Item.Claims (I)) and then
         Item.Claims (I).Sequence <= Item.Through and then
         (if I > 1 then
            Item.Claims (I - 1).Sequence < Item.Claims (I).Sequence)
         and then Valid_Predecessor (Item, I)) and then
      (for all I in Item.Count + 1 .. Max_Claims =>
         Item.Claims (I) = Empty_Claim) and then
      (for all I in 1 .. Item.Count =>
         (for all J in 1 .. Item.Count =>
            (if I /= J then
               Item.Claims (I).Identity /= Item.Claims (J).Identity))))
   with Global => null;

   function Coverage_Consistent (Item : Checkpoint) return Boolean is
     (for all Kind in Claim_Kind =>
        ((Item.Coverage (Kind) in Partial | Complete) =
           (for some I in 1 .. Item.Count => Item.Claims (I).Kind = Kind)))
   with Global => null;

   function Coverage_Ready (Item : Checkpoint) return Boolean is
     ((for all Kind in Claim_Kind =>
         Item.Coverage (Kind) in Observed_Empty | Complete) and then
      Item.Coverage (Goal) = Complete and then
      Item.Coverage (Acceptance) = Complete and then
      Item.Coverage (Source) = Complete and then
      Item.Coverage (Next_Action) = Complete)
   with Global => null;

   function Valid_Operation (Item : Operation) return Boolean is
     (Item.Identity /= Zero and then Item.Action /= Zero and then
      (if not Item.Has_Result then Item.Result_Record_Id = Zero) and then
      (if Item.Stage = Planned then not Item.Has_Result) and then
      (if Item.Stage in Observed_Complete | Acknowledged then Item.Has_Result))
   with Global => null;

   function Valid_Operations (Item : Checkpoint) return Boolean is
     ((for all I in 1 .. Item.Operations_Count =>
         Valid_Operation (Item.Operations (I))) and then
      (for all I in Item.Operations_Count + 1 .. Max_Operations =>
         Item.Operations (I) = Empty_Operation) and then
      (for all I in 1 .. Item.Operations_Count =>
         (for all J in 1 .. Item.Operations_Count =>
            (if I /= J then
               Item.Operations (I).Identity /= Item.Operations (J).Identity))))
   with Global => null;

   function Valid (Item : Checkpoint) return Boolean is
     (Item.Scope.Task_Id /= Zero and then Item.Scope.Session_Id /= Zero and then
      Item.Scope.Repository /= Zero and then Item.Identity /= Zero and then
      Item.Epoch /= 0 and then Item.Identity /= Item.Previous and then
      ((Item.Epoch = 1) = (Item.Previous = Zero)) and then
      Valid_Claims (Item) and then Coverage_Consistent (Item) and then
      Valid_Operations (Item))
   with Global => null;

   function Same_Task (Item : Checkpoint; Current : Current_Evidence)
      return Boolean is
     (Item.Scope.Task_Id = Current.Scope.Task_Id and then
      Item.Scope.Session_Id = Current.Scope.Session_Id and then
      Item.Scope.Repository = Current.Scope.Repository)
   with Global => null;

   function Fresh (Item : Checkpoint; Current : Current_Evidence)
      return Boolean is
     (Item.Identity = Current.Checkpoint_Id and then
      Item.Epoch = Current.Epoch and then Item.Capture = Current.Capture and then
      Item.Through = Current.Through and then
      Item.Retention_Epoch = Current.Retention_Epoch)
   with Global => null;

   function Joined (Item : Checkpoint; Current : Current_Evidence)
      return Boolean is
     (Bound_Durable (Current.Manifest,
                    (Epoch => Item.Epoch, Transaction => Item.Identity)) and then
      Bound_Durable (Current.Originals,
                    (Epoch => Item.Epoch, Transaction => Item.Identity)) and then
      (for all I in Claim_Index =>
         Current.Claims (I).Item = Item.Claims (I) and then
         Current.Claims (I).State =
           (if I <= Item.Count then Retained else Unknown)) and then
      (for all I in Operation_Index =>
         Current.Operations (I).Item = Item.Operations (I) and then
         Current.Operations (I).State =
           (if I <= Item.Operations_Count then Retained else Unknown)))
   with Global => null;

   function Uncertain_Operations (Item : Checkpoint) return Boolean is
     (for some I in 1 .. Item.Operations_Count =>
        Item.Operations (I).Stage in Dispatched | Uncertain)
   with Global => null;

   --  Successful comparison only permits proposing references. Completion,
   --  permission and next-action semantics remain source/consumer obligations.
   function Classify (Item : Checkpoint; Current : Current_Evidence)
      return Restoration
   with Global => null,
     Post => Classify'Result =
       (if not Valid (Item) then Invalid_Checkpoint
        elsif not Same_Task (Item, Current) then Identity_Mismatch
        elsif not Fresh (Item, Current) then Stale_Checkpoint
        elsif not Joined (Item, Current) or else not Coverage_Ready (Item)
          then Need_Evidence
        elsif Item.Scope.Revision /= Current.Scope.Revision or else
              Item.Scope.Dirty /= Current.Scope.Dirty
          then Reconcile_Repository
        elsif Uncertain_Operations (Item) then Reconcile_Operations
        else References_Proposed);
end SIA_Continuity;
