with Pack_Plan_Wire_Test_Support;
with Pack_Retirement_Test_Support;
procedure Pack_Plan_Wire_Tests with SPARK_Mode => Off is
begin
   Pack_Retirement_Test_Support.Run;
   Pack_Plan_Wire_Test_Support.Run;
end Pack_Plan_Wire_Tests;
