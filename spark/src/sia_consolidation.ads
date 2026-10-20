with SIA_Policy;

--  Pure batch-observation policy. Descriptors must come from authenticated
--  producers before this may guard effects. No I/O or durable ACK occurs here.
package SIA_Consolidation with SPARK_Mode, Pure is
   use SIA_Policy;
   Max_Days : constant := 1024;
   subtype Day_Count is Natural range 0 .. Max_Days;
   subtype Day_Index is Positive range 1 .. Max_Days;
   Zero : constant Digest := [others => 0];

   type Day_Identity is record
      Day, Sources, Originals : Digest;
   end record;
   Empty_Day : constant Day_Identity :=
     (Day => [others => 0], Sources => [others => 0],
      Originals => [others => 0]);
   type Day_Array is array (Day_Index) of Day_Identity;
   type Disposition is (Not_Observed, Retained_Intact, Compacted_Exact,
                        Partial_Cleanup, Evidence_Unavailable);
   type Disposition_Array is array (Day_Index) of Disposition;
   Empty_Results : constant Disposition_Array := [others => Not_Observed];

   type Batch is record
      Transaction : Binding;
      Identity, Before_Cursor, After_Cursor : Digest;
      Count : Day_Count;
      Days : Day_Array;
   end record;
   type Observation is record
      Expected : Batch;
      Results : Disposition_Array;
   end record;
   type Phase is (Pending, Recorded);
   type State is record
      Expected : Batch;
      Stage : Phase;
      Results : Disposition_Array;
   end record;
   type Decision is (Refused, Record_Proposed, Identical_Record);

   --  Zero is reserved for absent batch/day/original-reference identities.
   --  Transaction and source content digests retain their entire byte domain,
   --  including zero. Presence of a transaction is carried by its epoch.
   function Valid_Batch (Item : Batch) return Boolean is
     (Item.Transaction.Epoch /= 0 and then Item.Identity /= Zero and then
      Item.Before_Cursor /= Item.After_Cursor and then Item.Count /= 0 and then
      (for all I in Day_Index =>
         (if I <= Item.Count then
             Item.Days (I).Day /= Zero and then Item.Days (I).Originals /= Zero
          else Item.Days (I) = Empty_Day)) and then
      (for all I in 1 .. Item.Count =>
         (for all J in 1 .. Item.Count =>
            (if I /= J then Item.Days (I).Day /= Item.Days (J).Day))))
   with Global => null;

   --  Retained means exact live data remains; it does not mean compaction
   --  succeeded or authorize deleting that data or dropping its history.
   function Complete (Item : Batch; Results : Disposition_Array)
      return Boolean is
     (for all I in Day_Index =>
        (if I <= Item.Count then
            Results (I) in Retained_Intact | Compacted_Exact
         else Results (I) = Not_Observed))
   with Global => null;

   function Valid_State (Current : State) return Boolean is
     (Valid_Batch (Current.Expected) and then
      (if Current.Stage = Pending then Current.Results = Empty_Results
       else Complete (Current.Expected, Current.Results)))
   with Global => null;

   function Qualifies (Current : State; Item : Observation) return Boolean is
     (Valid_State (Current) and then Item.Expected = Current.Expected and then
      Complete (Current.Expected, Item.Results))
   with Global => null;

   function Classify (Current : State; Item : Observation) return Decision
   with Global => null,
     Contract_Cases =>
       (not Qualifies (Current, Item) => Classify'Result = Refused,
        Qualifies (Current, Item) and then Current.Stage = Pending =>
          Classify'Result = Record_Proposed,
        Qualifies (Current, Item) and then Current.Stage = Recorded and then
          Current.Results = Item.Results => Classify'Result = Identical_Record,
        others => Classify'Result = Refused);

   procedure Plan
     (Current : State; Item : Observation;
      Candidate : out State; Result : out Decision)
   with Global => null, Always_Terminates,
     Depends => ((Candidate, Result) => (Current, Item)),
     Post =>
       Result = Classify (Current, Item) and then
       Candidate.Expected = Current.Expected and then
       (if Result = Record_Proposed then
          Candidate.Stage = Recorded and then Candidate.Results = Item.Results
        else Candidate = Current) and then
       (if Valid_State (Current) then Valid_State (Candidate));
end SIA_Consolidation;
