with SIA_Policy;
with SIA_Request_Wire;
with SIA_Request_Admission;

--  Pure epoch binding. Protected epoch production/retention is external.
package SIA_Grant_Lifetime with SPARK_Mode, Pure is
   use SIA_Policy;
   use SIA_Request_Wire;
   use SIA_Request_Admission;

   type Scope is record
      Boot, Service : Digest;
   end record;
   type Scoped_Grant is record
      Domain : Scope;
      Authority : Grant;
   end record;

   function Same_Domain (Retained, Current : Scope) return Boolean is
     (Retained.Boot /= Digest'(others => 0) and then
      Retained.Service /= Digest'(others => 0) and then Retained = Current)
   with Global => null;

   function Classify_Scoped
     (Retained : Scoped_Grant; Current : Scope;
      Sender : User_Id; Now : Tick; Item : Request) return Classification
   with Global => null,
     Contract_Cases =>
       (not Same_Domain (Retained.Domain, Current) =>
          Classify_Scoped'Result = Denied,
        Same_Domain (Retained.Domain, Current) =>
          Classify_Scoped'Result =
            Classify (Retained.Authority, Sender, Now, Item));
end SIA_Grant_Lifetime;
