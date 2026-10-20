package body SIA_Consolidation with SPARK_Mode is
   function Classify (Current : State; Item : Observation) return Decision is
   begin
      if not Qualifies (Current, Item) then
         return Refused;
      elsif Current.Stage = Pending then
         return Record_Proposed;
      elsif Current.Results = Item.Results then
         return Identical_Record;
      else
         return Refused;
      end if;
   end Classify;

   procedure Plan
     (Current : State; Item : Observation;
      Candidate : out State; Result : out Decision)
   is
   begin
      Result := Classify (Current, Item);
      Candidate := Current;
      if Result = Record_Proposed then
         Candidate.Stage := Recorded;
         Candidate.Results := Item.Results;
      end if;
   end Plan;
end SIA_Consolidation;
