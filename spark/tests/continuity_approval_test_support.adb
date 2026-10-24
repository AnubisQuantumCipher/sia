with SIA_Policy; use SIA_Policy;
with SIA_Continuity; use SIA_Continuity;
with SIA_Continuity.Approvals; use SIA_Continuity.Approvals;

--  Executable independent mutation oracles, not part of the deductive proof.
--  No source authentication, actual harness or actuator is exercised here.
package body Continuity_Approval_Test_Support with SPARK_Mode => Off is
   Scope : constant Context :=
     (Task_Id => [others => 1], Session_Id => [others => 2],
      Repository => [others => 3], Revision => [others => 4],
      Dirty => [others => 5]);
   Place : constant Occurrence :=
     (Lifecycle => [others => 20], Target_Turn => [others => 21]);
   Action : constant Action_Scope :=
     (Proposal => [others => 12], Action => [others => 13],
      Conditions => [others => 14]);
   Choice : constant Request_Selection :=
     (Descriptor => [others => 45], Question => [others => 200],
      Question_Item => [others => 11], Response => [others => 5],
      Requested => Action);
   Expected : constant Restore_Selection :=
     (Where_Now => Place, Requests => [5 => Choice, others => Empty_Request]);
   Initial : constant Checkpoint :=
     (Scope => Scope, Identity => [others => 30], Previous => Zero,
      Capture => [others => 31], Epoch => 1, Through => 5,
      Retention_Epoch => 1,
      Coverage => [Goal | Acceptance | Source | Next_Action |
                   Permission_Reference => Complete, others => Observed_Empty],
      Count => 5, Claims =>
        [1 => ([others => 1], [others => 1], [others => 1], 1,
               Goal, Source_Record, User, 0),
         2 => ([others => 2], [others => 2], [others => 2], 2,
               Acceptance, Source_Record, User, 0),
         3 => ([others => 3], [others => 3], [others => 3], 3,
               Source, Source_Record, Tool, 0),
         4 => ([others => 4], [others => 4], [others => 4], 4,
               Next_Action, Model_Record, Assistant, 0),
         5 => ([others => 5], [others => 5], [others => 5], 5,
               Permission_Reference, Source_Record, User, 0),
         others => Empty_Claim],
      Operations_Count => 0, Operations => [others => Empty_Operation]);
   Question : constant Original_Event :=
     (Scope => Scope, Identity => [others => 200], Content => [others => 9],
      Producer => [others => 40], Order_Domain => [others => 41], Sequence => 4,
      Speaker => Assistant, From => Model_Record, Route => Assistant_Question,
      Source_State => Authenticated, Custody => (True, True, (1, [others => 9])),
      Question_Item => [others => 11], Reply_To => Zero,
      Requested => Action, Answer => Undetermined);
   Response : constant Original_Event :=
     (Question with delta Identity => [others => 5], Content => [others => 10],
      Sequence => 5, Speaker => User, From => Source_Record, Route => Human_Input,
      Custody => (True, True, (1, [others => 10])),
      Reply_To => Question.Identity, Answer => Approved);
   Good : constant Observation :=
     (Checkpoint_Id => Initial.Identity, Claim_Id => Initial.Claims (5).Identity,
      Slot => Initial.Claims (5).Slot, Epoch => 1,
      Question => Question, Response => Response,
      Selected =>
        (Descriptor => [others => 45], Question => Question.Identity,
         Question_Item => Question.Question_Item,
         Response => Response.Identity, Requested => Action,
         Form => Queried_Decision, State => Current, Source_State => Authenticated,
         Custody => (True, True, (1, [others => 45])),
         Checkpoint_Id => Initial.Identity, Epoch => 1, Through => 5,
         Retention_Epoch => 1, Where_Now => Place));

   function Current_For (Item : Checkpoint) return Current_Evidence is
      Result : Current_Evidence :=
        (Scope => Item.Scope, Checkpoint_Id => Item.Identity,
         Capture => Item.Capture, Epoch => Item.Epoch, Through => Item.Through,
         Retention_Epoch => Item.Retention_Epoch,
         Manifest | Originals => (True, True, (Item.Epoch, Item.Identity)),
         Claims => [others => (Unknown, Empty_Claim)],
         Operations => [others => (Unknown, Empty_Operation)]);
   begin
      for I in Claim_Index loop
         Result.Claims (I) :=
           ((if I <= Item.Count then Retained else Unknown), Item.Claims (I));
      end loop;
      for I in Operation_Index loop
         Result.Operations (I) :=
           ((if I <= Item.Operations_Count then Retained else Unknown),
            Item.Operations (I));
      end loop;
      return Result;
   end Current_For;

   procedure Expect (Seen : Observation; Want : Link_Status) is
      Result : constant Resolution := Restore
        (Initial, Current_For (Initial), Expected,
         [5 => Seen, others => Empty_Observation]);
   begin
      pragma Assert (Result.Detail = Want);
      if Want = Reference_Correspondence then
         pragma Assert (Result.Base = References_Proposed and Result.At_Claim = 0);
      else
         pragma Assert (Result.Base = Need_Evidence and Result.At_Claim = 5);
      end if;
   end Expect;

   procedure Check_Identity is
   begin
      Expect ((Good with delta Claim_Id => Zero), Claim_Mismatch);
      Expect ((Good with delta Slot => Zero), Claim_Mismatch);
      Expect ((Good with delta Checkpoint_Id => Zero), Claim_Mismatch);
      Expect ((Good with delta Epoch => 2), Claim_Mismatch);
      Expect ((Good with delta Response =>
        (Response with delta Identity => Zero)), Claim_Mismatch);
      Expect ((Good with delta Response =>
        (Response with delta Sequence => 4)), Claim_Mismatch);
      Expect ((Good with delta Response =>
        (Response with delta Speaker => Tool)), Claim_Mismatch);
      Expect ((Good with delta Response =>
        (Response with delta From => Model_Record)), Claim_Mismatch);
   end Check_Identity;

   procedure Check_Source is
   begin
      Expect ((Good with delta Question =>
        (Question with delta Source_State => Unknown_Source)), Source_Unresolved);
      Expect ((Good with delta Response =>
        (Response with delta Source_State => Rejected_Source)), Source_Unresolved);
      Expect ((Good with delta Response =>
        (Response with delta Producer => Zero)), Source_Unresolved);
      Expect ((Good with delta Question =>
        (Question with delta Content => Zero)), Source_Unresolved);
      Expect ((Good with delta Response =>
        (Response with delta Custody => Empty_Witness)), Source_Unresolved);
      Expect ((Good with delta Question =>
        (Question with delta Scope => (Scope with delta Task_Id => Zero))),
        Source_Unresolved);
      Expect ((Good with delta Response =>
        (Response with delta Scope => (Scope with delta Session_Id => Zero))),
        Source_Unresolved);
      for Route in Channel loop
         if Route /= Human_Input then
            Expect ((Good with delta Response =>
              (Response with delta Route => Route)), Source_Unresolved);
         end if;
      end loop;
   end Check_Source;

   procedure Check_Ordering_And_Reply is
   begin
      for Sequence in Generation range 5 .. 6 loop
         Expect ((Good with delta Question =>
           (Question with delta Sequence => Sequence)), Original_Order_Unresolved);
      end loop;
      Expect ((Good with delta Question =>
        (Question with delta Sequence => 0)), Original_Order_Unresolved);
      Expect ((Good with delta Response =>
        (Response with delta Order_Domain => [others => 99])),
        Original_Order_Unresolved);
      Expect ((Good with delta Question =>
        (Question with delta Question_Item => Zero)), Reply_Link_Unresolved);
      Expect ((Good with delta Response =>
        (Response with delta Question_Item => [others => 99])), Reply_Link_Unresolved);
      Expect ((Good with delta Response =>
        (Response with delta Reply_To => [others => 99])), Reply_Link_Unresolved);
      Expect ((Good with delta Question =>
        (Question with delta Answer => Approved)), Reply_Link_Unresolved);
   end Check_Ordering_And_Reply;

   procedure Check_Scope is
   begin
      Expect ((Good with delta Response => (Response with delta Requested =>
        (Action with delta Proposal => [others => 99]))), Scope_Unresolved);
      Expect ((Good with delta Response => (Response with delta Requested =>
        (Action with delta Action => [others => 99]))), Scope_Unresolved);
      Expect ((Good with delta Response => (Response with delta Requested =>
        (Action with delta Conditions => [others => 99]))), Scope_Unresolved);
      Expect ((Good with delta Selected => (Good.Selected with delta Requested =>
        (Action with delta Conditions => [others => 99]))), Scope_Unresolved);
      Expect ((Good with delta Question => (Question with delta Requested =>
        (Action with delta Conditions => Zero))), Scope_Unresolved);
   end Check_Scope;

   procedure Check_Current is
   begin
      Expect ((Good with delta Selected =>
        (Good.Selected with delta Question => Zero)), Current_Unresolved);
      Expect ((Good with delta Selected =>
        (Good.Selected with delta Question_Item => Zero)), Current_Unresolved);
      Expect ((Good with delta Selected =>
        (Good.Selected with delta Response => Zero)), Current_Unresolved);
      Expect ((Good with delta Selected =>
        (Good.Selected with delta Checkpoint_Id => Zero)), Current_Unresolved);
      Expect ((Good with delta Selected =>
        (Good.Selected with delta Epoch => 2)), Current_Unresolved);
      Expect ((Good with delta Selected =>
        (Good.Selected with delta Through => 4)), Current_Unresolved);
      Expect ((Good with delta Selected =>
        (Good.Selected with delta Retention_Epoch => 2)), Current_Unresolved);
      Expect ((Good with delta Selected =>
        (Good.Selected with delta Source_State => Unknown_Source)), Current_Unresolved);
      Expect ((Good with delta Selected =>
        (Good.Selected with delta Custody => Empty_Witness)), Current_Unresolved);
      Expect ((Good with delta Selected =>
        (Good.Selected with delta Where_Now => Empty_Occurrence)), Current_Unresolved);
      Expect ((Good with delta Selected =>
        (Good.Selected with delta Form => Direct_Instruction)), Unsupported_Form);
   end Check_Current;

   procedure Check_Decisions is
   begin
      Expect ((Good with delta Selected =>
        (Good.Selected with delta State => Unknown_Current)), Current_Unresolved);
      Expect ((Good with delta Selected =>
        (Good.Selected with delta State => Revoked)), Decision_Revoked);
      Expect ((Good with delta Selected =>
        (Good.Selected with delta State => Superseded)), Decision_Superseded);
      Expect ((Good with delta Selected =>
        (Good.Selected with delta State => Expired)), Decision_Expired);
      Expect ((Good with delta Response =>
        (Response with delta Answer => Denied)), Decision_Denied);
      Expect ((Good with delta Response =>
        (Response with delta Answer => Deferred)), Decision_Deferred);
      Expect ((Good with delta Response =>
        (Response with delta Answer => Undetermined)), Decision_Unresolved);
      Expect ((Good with delta Response =>
        (Response with delta Answer => Ambiguous)), Decision_Ambiguous);
   end Check_Decisions;

   procedure Check_Empty_And_Extra is
      Item : Checkpoint := Initial;
      Result : Resolution;
   begin
      Expect (Empty_Observation, Claim_Mismatch);
      Result := Restore (Initial, Current_For (Initial), Expected,
                         [5 | 64 => Good, others => Empty_Observation]);
      pragma Assert (Result = (Need_Evidence, Unexpected_Observation, 64));
      Result := Restore (Initial, Current_For (Initial), Expected,
                         [4 => Good, others => Empty_Observation]);
      pragma Assert (Result = (Need_Evidence, Unexpected_Observation, 4));
      Item.Count := 4;
      Item.Claims (5) := Empty_Claim;
      Item.Coverage (Permission_Reference) := Observed_Empty;
      Result := Restore (Item, Current_For (Item), Empty_Restore_Selection,
                         [others => Empty_Observation]);
      pragma Assert (Result = (References_Proposed, No_Observation, 0));
   end Check_Empty_And_Extra;

   procedure Check_History is
      Item : Checkpoint := Initial;
      Seen : Observations := [others => Empty_Observation];
      Selected : Restore_Selection := Empty_Restore_Selection;
      Result : Resolution;
   begin
      Selected.Where_Now := Place;
      Item.Count := 6;
      Item.Through := 6;
      Item.Claims (6) := (Item.Claims (5) with delta Identity => [others => 6],
        Source_Record_Id => [others => 6], Sequence => 6, Replaces => 5);
      Seen (6) := (Good with delta Claim_Id => [others => 6],
        Response => (Response with delta Identity => [others => 6], Sequence => 6),
        Selected => (Good.Selected with delta Response => [others => 6], Through => 6));
      Selected.Requests (6) := (Choice with delta Response => [others => 6]);
      pragma Assert (not Active_Permission (Item, 5) and Active_Permission (Item, 6));
      Result := Restore (Item, Current_For (Item), Selected, Seen);
      pragma Assert (Result = (References_Proposed, Reference_Correspondence, 0));
      Seen (6).Selected.State := Revoked;
      Result := Restore (Item, Current_For (Item), Selected, Seen);
      pragma Assert (Result = (Need_Evidence, Decision_Revoked, 6));
      Seen (5) := Good;
      Result := Restore (Item, Current_For (Item), Selected, Seen);
      pragma Assert (Result = (Need_Evidence, Unexpected_Observation, 5));
      pragma Assert (Item.Claims (5) = Initial.Claims (5));
   end Check_History;

   procedure Parent_Expect
     (Item : Checkpoint; Evidence : Current_Evidence; Want : Restoration) is
   begin
      pragma Assert (Classify (Item, Evidence) = Want);
      pragma Assert (Restore (Item, Evidence, Empty_Restore_Selection,
        [others => Empty_Observation]) = (Want, Not_Checked, 0));
   end Parent_Expect;

   procedure Check_Parent_Precedence is
      Item : Checkpoint := Initial;
      Evidence : Current_Evidence := Current_For (Initial);
   begin
      Item.Identity := Zero;
      Parent_Expect (Item, Evidence, Invalid_Checkpoint);
      Item := Initial;
      Evidence.Scope.Session_Id := Zero;
      Parent_Expect (Item, Evidence, Identity_Mismatch);
      Evidence := Current_For (Item);
      Evidence.Epoch := 2;
      Parent_Expect (Item, Evidence, Stale_Checkpoint);
      Evidence := Current_For (Item);
      Evidence.Manifest.Durable := False;
      Parent_Expect (Item, Evidence, Need_Evidence);
      Evidence := Current_For (Item);
      Evidence.Scope.Revision := Zero;
      Parent_Expect (Item, Evidence, Reconcile_Repository);
      Item.Operations_Count := 1;
      Item.Operations (1) :=
        (Identity => [others => 50], Action => [others => 51],
         Source_Record_Id => [others => 52], Result_Record_Id => Zero,
         Stage => Uncertain, Has_Result => False);
      Parent_Expect (Item, Current_For (Item), Reconcile_Operations);
   end Check_Parent_Precedence;

   procedure Check_Full_Roster is
      Item : Checkpoint := Initial;
      Seen : Observations := [others => Empty_Observation];
      Selected : Restore_Selection := Empty_Restore_Selection;
      Result : Resolution;
   begin
      Selected.Where_Now := Place;
      Item.Count := Max_Claims;
      Item.Through := Max_Claims;
      for I in Claim_Index range 5 .. Max_Claims loop
         Item.Claims (I) :=
           (Identity | Slot | Source_Record_Id => [others => Digest_Byte (I)],
            Sequence => Generation (I), Kind => Permission_Reference,
            From => Source_Record, Speaker => User, Replaces => 0);
         Seen (I) := (Good with delta Claim_Id => [others => Digest_Byte (I)],
           Slot => [others => Digest_Byte (I)],
           Response => (Response with delta Identity => [others => Digest_Byte (I)],
             Sequence => Generation (I)),
           Selected => (Good.Selected with delta Response => [others => Digest_Byte (I)],
             Through => Max_Claims));
         Selected.Requests (I) :=
           (Choice with delta Response => [others => Digest_Byte (I)]);
      end loop;
      Result := Restore (Item, Current_For (Item), Selected, Seen);
      pragma Assert (Result = (References_Proposed, Reference_Correspondence, 0));
      Seen (64).Response.Identity := Seen (5).Response.Identity;
      Result := Restore (Item, Current_For (Item), Selected, Seen);
      pragma Assert (Result = (Need_Evidence, Duplicate_Response, 64));
   end Check_Full_Roster;
   procedure Check_Coherent_Substitution is
      Changed : Observation := Good;
      Other_Action : constant Action_Scope :=
        (Proposal => [others => 80], Action => [others => 81],
         Conditions => [others => 82]);
   begin
      Changed.Question.Identity := [others => 201];
      Changed.Question.Question_Item := [others => 83];
      Changed.Question.Requested := Other_Action;
      Changed.Response.Reply_To := Changed.Question.Identity;
      Changed.Response.Question_Item := Changed.Question.Question_Item;
      Changed.Response.Requested := Other_Action;
      Changed.Selected.Question := Changed.Question.Identity;
      Changed.Selected.Question_Item := Changed.Question.Question_Item;
      Changed.Selected.Requested := Other_Action;
      Expect (Changed, Current_Unresolved);
   end Check_Coherent_Substitution;
   procedure Check_Independent_Selection is
      Selected : Restore_Selection := Expected;
      Seen : constant Observations := [5 => Good, others => Empty_Observation];
      Result : Resolution;
   begin
      Selected.Requests (5) := Empty_Request;
      Result := Restore (Initial, Current_For (Initial), Selected, Seen);
      pragma Assert (Result = (Need_Evidence, Current_Unresolved, 5));
      Selected := Expected;
      Selected.Requests (64) := Choice;
      Result := Restore (Initial, Current_For (Initial), Selected, Seen);
      pragma Assert (Result = (Need_Evidence, Unexpected_Selection, 64));
      Selected := Expected;
      Selected.Where_Now.Lifecycle := [others => 98];
      Result := Restore (Initial, Current_For (Initial), Selected, Seen);
      pragma Assert (Result = (Need_Evidence, Current_Unresolved, 5));
      Selected := Expected;
      Selected.Where_Now.Target_Turn := [others => 98];
      Result := Restore (Initial, Current_For (Initial), Selected, Seen);
      pragma Assert (Result = (Need_Evidence, Current_Unresolved, 5));
      Expect ((Good with delta Selected =>
        (Good.Selected with delta Descriptor => [others => 98])), Current_Unresolved);
      Expect ((Good with delta Selected => (Good.Selected with delta
        Custody => (True, True, (1, Initial.Identity)))), Current_Unresolved);
   end Check_Independent_Selection;

   procedure Check_Coherent_Item_And_Action is
      Changed : Observation := Good;
      Other_Action : constant Action_Scope :=
        (Action with delta Conditions => [others => 98]);
   begin
      Changed.Question.Question_Item := [others => 98];
      Changed.Response.Question_Item := Changed.Question.Question_Item;
      Changed.Selected.Question_Item := Changed.Question.Question_Item;
      Expect (Changed, Current_Unresolved);
      Changed := Good;
      Changed.Question.Requested := Other_Action;
      Changed.Response.Requested := Other_Action;
      Changed.Selected.Requested := Other_Action;
      Expect (Changed, Current_Unresolved);
   end Check_Coherent_Item_And_Action;

   procedure Run is
   begin
      Check_Coherent_Substitution;
      Check_Independent_Selection;
      Check_Coherent_Item_And_Action;
      Expect (Good, Reference_Correspondence);
      Check_Identity;
      Check_Source;
      Check_Ordering_And_Reply;
      Check_Scope;
      Check_Current;
      Check_Decisions;
      Check_Empty_And_Extra;
      Check_History;
      Check_Parent_Precedence;
      Check_Full_Roster;
   end Run;
end Continuity_Approval_Test_Support;
