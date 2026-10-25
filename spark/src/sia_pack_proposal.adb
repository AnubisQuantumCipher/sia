package body SIA_Pack_Proposal with SPARK_Mode is
   procedure Start
     (Candidate : Plan; Selection_Header, Fallback_Header : Header;
      Selection_Length, Fallback_Length : Natural; Item : out State)
   is
      pragma Annotate (GNATprove, Hide_Info, "Expression_Function_Body", Valid_Retirement_Plan);
   begin
      Item := (others => <>);
      if Can_Start (Candidate, Selection_Header, Fallback_Header, Selection_Length, Fallback_Length) then
         Partition.Start (Selection_Header, Fallback_Header, Selection_Length,
                          Fallback_Length, Candidate.Represented, Item.Joined);
         Item.Candidate := Candidate;
         Item.Stage := Open;
      end if;
   end Start;

   procedure Take
     (Item : in out State; Selection_Data, Fallback_Data : Record_Bytes;
      Selection_Length, Fallback_Length : Natural; Accepted : out Boolean)
   is
      pragma Annotate (GNATprove, Hide_Info, "Expression_Function_Body", Valid_Retirement_Plan);
      Kind : Partition.Step_Kind;
      Value : Record_Reference;
      use type Partition.Step_Kind;
   begin
      Accepted := Allowed (Item, Selection_Data, Fallback_Data, Selection_Length, Fallback_Length);
      if not Accepted then
         Item.Stage := Failed;
         return;
      end if;
      Partition.Take (Item.Joined, Selection_Data, Fallback_Data,
                      Selection_Length, Fallback_Length, Kind, Value);
      pragma Assert (Kind /= Partition.No_Step and then Value = Record_Value (Selection_Data));
   end Take;

   procedure Finish
     (Item : in out State; Selection_Trailing, Fallback_Trailing : Natural;
      Accepted : out Boolean; Value : out Plan)
   is
      pragma Annotate (GNATprove, Hide_Info, "Expression_Function_Body", Valid_Retirement_Plan);
   begin
      Accepted := False;
      Value := Empty_Plan;
      if Item.Stage /= Open then
         Item.Stage := Failed;
         return;
      end if;
      Partition.Finish (Item.Joined, Selection_Trailing, Fallback_Trailing, Accepted);
      Item.Stage := (if Accepted then Done else Failed);
      if Accepted then
         Value := Item.Candidate;
      end if;
   end Finish;
end SIA_Pack_Proposal;
