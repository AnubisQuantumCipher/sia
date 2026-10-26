with SIA_Policy;
with SIA_Pack_Retirement;
with SIA_Pack_Manifest_Wire;
with SIA_Pack_Partition;

--  Conditional structural admission only. No digest authentication or effects.
package SIA_Pack_Proposal with SPARK_Mode, Pure is
   use SIA_Policy;
   use SIA_Pack_Retirement;
   use SIA_Pack_Manifest_Wire;
   package Partition renames SIA_Pack_Partition;
   use type Partition.Partition_State;
   type State is private;
   function Running (Item : State) return Boolean with Global => null;
   function Complete (Item : State) return Boolean with Global => null;
   function Refused (Item : State) return Boolean with Global => null;
   function Proposal (Item : State) return Plan with Global => null;
   function Streams (Item : State) return Partition.Partition_State with Global => null;
   function Consistent (Item : State) return Boolean with Global => null;

   function Can_Start
     (Candidate : Plan; Selection_Header, Fallback_Header : Header;
      Selection_Length, Fallback_Length : Natural) return Boolean is
     (Partition.Can_Start (Selection_Header, Fallback_Header,
                           Selection_Length, Fallback_Length, Candidate.Represented) and then
      Header_Count (Selection_Header) = Candidate.Selected and then
      Header_Count (Fallback_Header) = Candidate.Fallback_Count and then
      Valid_Retirement_Plan (Candidate))
   with Global => null;
   pragma Annotate (GNATprove, Hide_Info, "Expression_Function_Body", Valid_Retirement_Plan);
   function Outside_Target (Target : Roster; Identity : Digest) return Boolean is
     (for all I in 1 .. Target.Count => Target.Records (I).Identity /= Identity)
   with Global => null;
   function Allowed
     (Item : State; Selection_Data, Fallback_Data : Record_Bytes;
      Selection_Length, Fallback_Length : Natural) return Boolean is
     (Running (Item) and then
      Partition.Acceptable (Streams (Item), Selection_Data, Fallback_Data,
                            Selection_Length, Fallback_Length) and then
      (Partition.Next_Is_Represented (Streams (Item), Record_Value (Selection_Data)) or else
       Outside_Target (Proposal (Item).Target, Record_Value (Selection_Data).Identity)))
   with Global => null;
   function At_End (Item : State) return Boolean is
     (Running (Item) and
      Consumed (Partition.Selected (Streams (Item))) = Expected (Partition.Selected (Streams (Item))) and
      Consumed (Partition.Fallback (Streams (Item))) = Expected (Partition.Fallback (Streams (Item))) and
      Partition.Position (Streams (Item)) = Partition.Representation (Streams (Item)).Count)
   with Global => null;

   procedure Start
     (Candidate : Plan; Selection_Header, Fallback_Header : Header;
      Selection_Length, Fallback_Length : Natural; Item : out State)
   with Global => null, Always_Terminates,
     Depends => (Item => (Candidate, Selection_Header, Fallback_Header, Selection_Length, Fallback_Length)),
     Post => Consistent (Item) and not Complete (Item) and
       Running (Item) = Can_Start (Candidate, Selection_Header, Fallback_Header, Selection_Length, Fallback_Length) and
       Refused (Item) = not Running (Item) and
       Proposal (Item) = (if Running (Item) then Candidate else Empty_Plan) and
       Partition.Position (Streams (Item)) = 0 and
       Consumed (Partition.Selected (Streams (Item))) = 0 and
       Consumed (Partition.Fallback (Streams (Item))) = 0;

   procedure Take
     (Item : in out State; Selection_Data, Fallback_Data : Record_Bytes;
      Selection_Length, Fallback_Length : Natural; Accepted : out Boolean)
   with Global => null, Always_Terminates,
     Depends => (Item => (Item, Selection_Data, Fallback_Data, Selection_Length, Fallback_Length),
       Accepted => (Item, Selection_Data, Fallback_Data, Selection_Length, Fallback_Length)),
     Pre => Consistent (Item),
     Post => Consistent (Item) and then Proposal (Item) = Proposal (Item'Old) and then
       Accepted = Allowed (Item'Old, Selection_Data, Fallback_Data, Selection_Length, Fallback_Length) and then
       (if not Accepted then Refused (Item) and then Streams (Item) = Streams (Item'Old)
        else Running (Item) and then
          Consumed (Partition.Selected (Streams (Item))) = Consumed (Partition.Selected (Streams (Item'Old))) + 1 and then
          (if Partition.Next_Is_Represented (Streams (Item'Old), Record_Value (Selection_Data)) then
              Partition.Position (Streams (Item)) = Partition.Position (Streams (Item'Old)) + 1 and then
              Partition.Fallback (Streams (Item)) = Partition.Fallback (Streams (Item'Old))
           else Partition.Position (Streams (Item)) = Partition.Position (Streams (Item'Old)) and then
              Consumed (Partition.Fallback (Streams (Item))) = Consumed (Partition.Fallback (Streams (Item'Old))) + 1 and then
              Outside_Target (Proposal (Item).Target, Record_Value (Selection_Data).Identity)));

   procedure Finish
     (Item : in out State; Selection_Trailing, Fallback_Trailing : Natural;
      Accepted : out Boolean; Value : out Plan)
   with Global => null, Always_Terminates,
     Depends => (Item => (Item, Selection_Trailing, Fallback_Trailing),
       Accepted => (Item, Selection_Trailing, Fallback_Trailing),
       Value => (Item, Selection_Trailing, Fallback_Trailing)),
     Pre => Consistent (Item),
     Post => Consistent (Item) and Proposal (Item) = Proposal (Item'Old) and
       Accepted = (At_End (Item'Old) and Selection_Trailing = 0 and Fallback_Trailing = 0) and
       Complete (Item) = Accepted and Refused (Item) = not Accepted and
       Value = (if Accepted then Proposal (Item) else Empty_Plan) and
       Partition.Representation (Streams (Item)) = Partition.Representation (Streams (Item'Old)) and
       Partition.Position (Streams (Item)) = Partition.Position (Streams (Item'Old)) and
       Expected (Partition.Selected (Streams (Item))) = Expected (Partition.Selected (Streams (Item'Old))) and
       Consumed (Partition.Selected (Streams (Item))) = Consumed (Partition.Selected (Streams (Item'Old))) and
       Last_Identity (Partition.Selected (Streams (Item))) = Last_Identity (Partition.Selected (Streams (Item'Old))) and
       Expected (Partition.Fallback (Streams (Item))) = Expected (Partition.Fallback (Streams (Item'Old))) and
       Consumed (Partition.Fallback (Streams (Item))) = Consumed (Partition.Fallback (Streams (Item'Old))) and
       Last_Identity (Partition.Fallback (Streams (Item))) = Last_Identity (Partition.Fallback (Streams (Item'Old)));
private
   type Phase is (Failed, Open, Done);
   type State is record
      Stage : Phase := Failed;
      Candidate : Plan := Empty_Plan;
      Joined : Partition.Partition_State;
   end record;
   function Running (Item : State) return Boolean is (Item.Stage = Open);
   function Complete (Item : State) return Boolean is (Item.Stage = Done);
   function Refused (Item : State) return Boolean is (Item.Stage = Failed);
   function Proposal (Item : State) return Plan is (Item.Candidate);
   function Streams (Item : State) return Partition.Partition_State is (Item.Joined);
   function Consistent (Item : State) return Boolean is
     (Partition.Consistent (Item.Joined) and
      (if Item.Stage /= Failed then
         Partition.Representation (Item.Joined) = Item.Candidate.Represented and
         Expected (Partition.Selected (Item.Joined)) = Item.Candidate.Selected and
         Expected (Partition.Fallback (Item.Joined)) = Item.Candidate.Fallback_Count and
         (if Item.Stage = Open then Partition.Active (Item.Joined) else Partition.Complete (Item.Joined)) and
         Valid_Retirement_Plan (Item.Candidate)));
   pragma Annotate (GNATprove, Hide_Info, "Expression_Function_Body", Valid_Retirement_Plan);
end SIA_Pack_Proposal;
