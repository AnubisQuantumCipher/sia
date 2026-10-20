with SIA_Policy;
with SIA_Request_Wire;

--  Pure comparison against an already-authoritative grant. This package does
--  not authenticate grant storage, credentials or the clock observation.
package SIA_Request_Admission with SPARK_Mode, Pure is
   use SIA_Policy;
   use SIA_Request_Wire;
   type User_Id is range 0 .. 2 ** 32 - 1;
   type Tick is range 0 .. 2 ** 63 - 1;
   type Grant is record
      Active : Boolean;
      Subject : User_Id;
      Not_Before, Expires : Tick;
      Expected : Request;
   end record;
   type Classification is (Denied, Observe_Only, Proposal_Only);

   function Matches
     (Authority : Grant; Sender : User_Id; Now : Tick; Item : Request)
      return Boolean is
     (Authority.Active and then Authority.Subject = Sender and then
      Authority.Not_Before <= Now and then Now < Authority.Expires and then
      Item.Capability /= Digest'(others => 0) and then
      Item = Authority.Expected)
   with Global => null;

   --  Proposal_Only means eligible for further validation, never permission
   --  to mutate. Observe_Only must never be dispatched to an effect handler.
   function Classify
     (Authority : Grant; Sender : User_Id; Now : Tick; Item : Request)
      return Classification
   with Global => null,
     Contract_Cases =>
       (not Matches (Authority, Sender, Now, Item) =>
          Classify'Result = Denied,
        Matches (Authority, Sender, Now, Item) and then Item.Action = Observe =>
          Classify'Result = Observe_Only,
        Matches (Authority, Sender, Now, Item) and then Item.Action = Propose =>
          Classify'Result = Proposal_Only);

   --  Compose syntax and grant comparison in one fail-closed entry. Neither
   --  classification authorizes effects; grant/credential/clock trust is external.
   procedure Classify_Frame
     (Authority : Grant; Sender : User_Id; Now : Tick;
      Bytes : Frame; Length : Natural; Item : out Request;
      Decision : out Classification)
   with Global => null, Always_Terminates,
     Depends => (Item => (Bytes, Length),
                 Decision => (Authority, Sender, Now, Bytes, Length)),
     Post =>
       (if not Valid (Bytes, Length) then
          Item = Empty_Request and then Decision = Denied
        else Decoded_As (Bytes, Length, Item) and then
          Decision = Classify (Authority, Sender, Now, Item));
end SIA_Request_Admission;
