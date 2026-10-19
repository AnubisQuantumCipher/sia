with SIA_Policy;

--  Untrusted request decoding only: a decoded proposal is never a grant.
package SIA_Request_Wire with SPARK_Mode, Pure is
   use SIA_Policy;
   type Frame is array (Positive range 1 .. 192) of Digest_Byte;
   type Operation is (Observe, Propose);
   type Request is record
      Action : Operation;
      Before_Phase, After_Phase : Natural range 0 .. 10;
      Capability, Source, Transaction, Payload, Predecessor_Receipt : Digest;
      Before_Generation, Target_Generation : Generation;
   end record;
   Empty_Request : constant Request :=
     (Action => Observe, Before_Phase => 0, After_Phase => 0,
      Capability | Source | Transaction | Payload | Predecessor_Receipt =>
        [others => 0], Before_Generation => 0, Target_Generation => 0);

   --  Explicit network-order relation; no native-layout reinterpretation.
   function Generation_Value (Bytes : Frame; Start : Positive)
      return Generation is
     (Generation (Bytes (Start)) * 2 ** 56 +
      Generation (Bytes (Start + 1)) * 2 ** 48 +
      Generation (Bytes (Start + 2)) * 2 ** 40 +
      Generation (Bytes (Start + 3)) * 2 ** 32 +
      Generation (Bytes (Start + 4)) * 2 ** 24 +
      Generation (Bytes (Start + 5)) * 2 ** 16 +
      Generation (Bytes (Start + 6)) * 2 ** 8 +
      Generation (Bytes (Start + 7)))
   with Global => null,
     Pre => Start in 169 | 177 and then Bytes (Start) <= 127;

   function Valid (Bytes : Frame; Length : Natural) return Boolean
     with Global => null;

   procedure Decode
     (Bytes : Frame; Length : Natural; Accepted : out Boolean;
      Item : out Request)
   with Global => null, Always_Terminates,
     Depends => (Accepted => (Bytes, Length), Item => (Bytes, Length)),
     Post => Accepted = Valid (Bytes, Length) and then
       (if not Accepted then Item = Empty_Request else
          Item.Action = (if Bytes (2) = 1 then Observe else Propose) and then
          Item.Before_Phase = Natural (Bytes (3)) and then
          Item.After_Phase = Natural (Bytes (4)) and then
          Item.Capability = Digest (Bytes (9 .. 40)) and then
          Item.Source = Digest (Bytes (41 .. 72)) and then
          Item.Transaction = Digest (Bytes (73 .. 104)) and then
          Item.Payload = Digest (Bytes (105 .. 136)) and then
          Item.Predecessor_Receipt = Digest (Bytes (137 .. 168)) and then
          Item.Before_Generation = Generation_Value (Bytes, 169) and then
          Item.Target_Generation = Generation_Value (Bytes, 177));
end SIA_Request_Wire;
