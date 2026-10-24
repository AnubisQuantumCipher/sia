with Continuity_Approval_Test_Support;
with Continuity_Descriptor_Test_Support;
procedure Continuity_Descriptor_Tests with SPARK_Mode => Off is
begin
   Continuity_Approval_Test_Support.Run;
   Continuity_Descriptor_Test_Support.Run;
end Continuity_Descriptor_Tests;
