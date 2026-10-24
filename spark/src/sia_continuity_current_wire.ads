with SIA_Policy;
with SIA_Continuity;
with SIA_Continuity_Record_Wire;
with SIA_Continuity_Observation_Wire;

--  Representation only. A sender may fabricate these evidence descriptors;
--  decoding does not authenticate current heads, witnesses or source records.
package SIA_Continuity_Current_Wire with SPARK_Mode, Pure is
   use SIA_Policy;
   use SIA_Continuity;
   use SIA_Continuity_Record_Wire;
   use SIA_Continuity_Observation_Wire;

   type Current_Bytes is array (Positive range 1 .. 12128) of Digest_Byte;

   Empty_Current : constant Current_Evidence :=
     (Scope => (others => [others => 0]),
      Checkpoint_Id | Capture => [others => 0],
      Epoch | Through | Retention_Epoch => 0,
      Manifest | Originals =>
        (Present | Durable => False,
         Bound_To => (Epoch => 0, Transaction => [others => 0])),
      Claims => [others =>
        (State => Unknown,
         Item => (Identity | Slot | Source_Record_Id => [others => 0],
                  Sequence => 0, Kind => Goal, From => Legacy_Record,
                  Speaker => Tool, Replaces => 0))],
      Operations => [others =>
        (State => Unknown,
         Item => (Identity | Action | Source_Record_Id | Result_Record_Id =>
                    [others => 0], Stage => Planned, Has_Result => False))]);

   function Context_Payload (Bytes : Current_Bytes) return Context_Bytes is
     ([for I in Context_Bytes'Range => Bytes (I)])
   with Global => null,
     Post => (for all I in Context_Bytes'Range =>
                Context_Payload'Result (I) = Bytes (I));

   function Manifest_Payload (Bytes : Current_Bytes) return Witness_Bytes is
     ([for I in Witness_Bytes'Range => Bytes (248 + I)])
   with Global => null,
     Post => (for all I in Witness_Bytes'Range =>
                Manifest_Payload'Result (I) = Bytes (248 + I));

   function Originals_Payload (Bytes : Current_Bytes) return Witness_Bytes is
     ([for I in Witness_Bytes'Range => Bytes (296 + I)])
   with Global => null,
     Post => (for all I in Witness_Bytes'Range =>
                Originals_Payload'Result (I) = Bytes (296 + I));

   function Claim_Payload (Bytes : Current_Bytes; Index : Claim_Index)
      return Claim_Observation_Bytes is
     ([for I in Claim_Observation_Bytes'Range =>
         Bytes ((352 + (Index - 1) * 144) + I)])
   with Global => null,
     Post => (for all I in Claim_Observation_Bytes'Range =>
       Claim_Payload'Result (I) = Bytes ((352 + (Index - 1) * 144) + I));

   function Operation_Payload (Bytes : Current_Bytes; Index : Operation_Index)
      return Operation_Observation_Bytes is
     ([for I in Operation_Observation_Bytes'Range =>
         Bytes ((9568 + (Index - 1) * 160) + I)])
   with Global => null,
     Post => (for all I in Operation_Observation_Bytes'Range =>
       Operation_Payload'Result (I) = Bytes ((9568 + (Index - 1) * 160) + I));

   function Header_Valid (Bytes : Current_Bytes) return Boolean is
     (Bytes (225) <= 127 and then Bytes (233) <= 127 and then
      Bytes (241) <= 127 and then Valid (Manifest_Payload (Bytes)) and then
      Valid (Originals_Payload (Bytes)) and then
      (for all I in 345 .. 352 => Bytes (I) = 0))
   with Global => null;

   function Valid (Bytes : Current_Bytes) return Boolean is
     (Header_Valid (Bytes) and then
      (for all I in Claim_Index => Valid (Claim_Payload (Bytes, I))) and then
      (for all I in Operation_Index => Valid (Operation_Payload (Bytes, I))))
   with Global => null;

   function Header_Decoded_As (Bytes : Current_Bytes; Item : Current_Evidence)
      return Boolean is
     (Header_Valid (Bytes) and then
      Item.Scope = Context_Value (Context_Payload (Bytes)) and then
      Item.Checkpoint_Id = Digest (Bytes (161 .. 192)) and then
      Item.Capture = Digest (Bytes (193 .. 224)) and then
      Item.Epoch = Word_Value (Word (Bytes (225 .. 232))) and then
      Item.Through = Word_Value (Word (Bytes (233 .. 240))) and then
      Item.Retention_Epoch = Word_Value (Word (Bytes (241 .. 248))) and then
      Decoded_As (Manifest_Payload (Bytes), Item.Manifest) and then
      Decoded_As (Originals_Payload (Bytes), Item.Originals))
   with Global => null;

   function Decoded_As (Bytes : Current_Bytes; Item : Current_Evidence)
      return Boolean is
     (Header_Decoded_As (Bytes, Item) and then
      (for all I in Claim_Index =>
         Decoded_As (Claim_Payload (Bytes, I), Item.Claims (I))) and then
      (for all I in Operation_Index =>
         Decoded_As (Operation_Payload (Bytes, I), Item.Operations (I))))
   with Global => null;

   procedure Decode
     (Bytes : Current_Bytes; Accepted : out Boolean; Item : out Current_Evidence)
   with Global => null, Always_Terminates,
     Depends => (Accepted => Bytes, Item => Bytes),
     Post => Accepted = Valid (Bytes) and then
       (if Accepted then Decoded_As (Bytes, Item) else Item = Empty_Current);
end SIA_Continuity_Current_Wire;
