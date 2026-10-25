package body SIA_Pack_Plan_Wire with SPARK_Mode is
   function Record_Value (Data : Frame; Start : Record_Offset)
      return Record_Reference is
   begin
      return (Digest (Data (Start .. Start + 31)),
              Digest (Data (Start + 32 .. Start + 63)), Small_Value (Data, Start + 64));
   end Record_Value;

   function Roster_Value (Data : Frame; Start : Roster_Offset) return Roster is
   begin
      return (Count => Record_Count (Data (Start + 7)),
              Records => [for I in Record_Index =>
                 Record_Value (Data, Record_Start (Start, I))]);
   end Roster_Value;

   function Value (Data : Frame) return Plan is
   begin
      return
        (Scope => Scope_Value (Data),
         Identity => Digest (Data (9 .. 40)),
         Organ_Bytes => Small_Value (Data, 401),
         Selected => Small_Value (Data, 409),
         Fallback_Count => Small_Value (Data, 417),
         Prior => Roster_Value (Data, Prior_Start),
         Target => Roster_Value (Data, Target_Start),
         Represented => Roster_Value (Data, Represented_Start),
         Legacy_Present => [for I in Record_Index =>
            Data ((Presence_Start + I) - 1) = 1],
         Legacy_Generation => [for I in Record_Index => Digest
            (Data (Generations_Start + (I - 1) * 32 ..
                   (Generations_Start + I * 32) - 1))]);
   end Value;

   procedure Decode
     (Data : Frame; Length : Natural; Accepted : out Boolean; Item : out Plan)
   is
      Candidate : Plan;
   begin
      Accepted := False;
      Item := Empty_Plan;
      if Shape_Valid (Data, Length) then
         Candidate := Value (Data);
         if Valid_Retirement_Plan (Candidate) then
            Item := Candidate;
            Accepted := True;
         end if;
      end if;
   end Decode;
end SIA_Pack_Plan_Wire;
