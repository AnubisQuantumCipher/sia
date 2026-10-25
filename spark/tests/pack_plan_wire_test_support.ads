--  Independent runtime encoding oracle; outside SPARK proof.
with SIA_Pack_Plan_Wire;
with SIA_Pack_Retirement;
package Pack_Plan_Wire_Test_Support with SPARK_Mode => Off is
   function Encode_Oracle (Item : SIA_Pack_Retirement.Plan)
      return SIA_Pack_Plan_Wire.Frame;
   procedure Run;
end Pack_Plan_Wire_Test_Support;
