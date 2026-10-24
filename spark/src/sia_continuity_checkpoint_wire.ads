with SIA_Policy;
with SIA_Continuity;
with SIA_Continuity_Record_Wire;
with SIA_Continuity_Observation_Wire;

--  Complete fixed-record representation; no authenticity or policy admission.
package SIA_Continuity_Checkpoint_Wire with SPARK_Mode, Pure is
   use SIA_Policy;
   use SIA_Continuity;
   use SIA_Continuity_Record_Wire;
   use SIA_Continuity_Observation_Wire;

   type Checkpoint_Bytes is array (Positive range 1 .. 10816) of Digest_Byte;
   subtype Coverage_Code is Digest_Byte range 0 .. 4;
   subtype Coverage_Offset is Positive range 281 .. 293;
   Coverage_Positions : constant array (Claim_Kind) of Coverage_Offset :=
     [Goal => 281, Acceptance => 282, Constraint => 283, Correction => 284,
      Decision => 285, Rejection => 286, Source => 287, Completed => 288,
      Verification => 289, Failure => 290, Next_Action => 291,
      Permission_Reference => 292, Pending_Approval => 293];
   Empty_Checkpoint : constant Checkpoint :=
     (Scope => (others => [others => 0]),
      Identity | Previous | Capture => [others => 0],
      Epoch | Through | Retention_Epoch => 0,
      Coverage => [others => Not_Observed], Count => 0, Operations_Count => 0,
      Claims => [others =>
        (Identity | Slot | Source_Record_Id => [others => 0], Sequence => 0,
         Kind => Goal, From => Legacy_Record, Speaker => Tool, Replaces => 0)],
      Operations => [others =>
        (Identity | Action | Source_Record_Id | Result_Record_Id => [others => 0],
         Stage => Planned, Has_Result => False)]);

   function Coverage_Value (Code : Coverage_Code) return Coverage_State is
     (case Code is
         when 0 => Not_Observed, when 1 => Unavailable,
         when 2 => Observed_Empty, when 3 => Partial, when 4 => Complete)
   with Global => null;

   function Context_Payload (Bytes : Checkpoint_Bytes) return Context_Bytes is
     ([for I in Context_Bytes'Range => Bytes (I)])
   with Global => null,
     Post => (for all I in Context_Bytes'Range =>
                Context_Payload'Result (I) = Bytes (I));

   function Claim_Payload (Bytes : Checkpoint_Bytes; Index : Claim_Index)
      return Claim_Bytes is
     ([for I in Claim_Bytes'Range => Bytes ((320 + (Index - 1) * 128) + I)])
   with Global => null,
     Post => (for all I in Claim_Bytes'Range =>
                Claim_Payload'Result (I) =
                  Bytes ((320 + (Index - 1) * 128) + I));

   function Operation_Payload
     (Bytes : Checkpoint_Bytes; Index : Operation_Index) return Operation_Bytes is
     ([for I in Operation_Bytes'Range =>
         Bytes ((8512 + (Index - 1) * 144) + I)])
   with Global => null,
     Post => (for all I in Operation_Bytes'Range =>
                Operation_Payload'Result (I) =
                  Bytes ((8512 + (Index - 1) * 144) + I));

   function Header_Valid (Bytes : Checkpoint_Bytes) return Boolean is
     (Bytes (257) <= 127 and then Bytes (265) <= 127 and then
      Bytes (273) <= 127 and then Bytes (294) <= Max_Claims and then
      Bytes (295) <= Max_Operations and then
      (for all I in Coverage_Offset => Bytes (I) in Coverage_Code) and then
      (for all I in 296 .. 320 => Bytes (I) = 0))
   with Global => null;

   function Valid (Bytes : Checkpoint_Bytes) return Boolean is
     (Header_Valid (Bytes) and then
      (for all I in Claim_Index => Valid (Claim_Payload (Bytes, I))) and then
      (for all I in Operation_Index => Valid (Operation_Payload (Bytes, I))))
   with Global => null;

   function Header_Decoded_As
     (Bytes : Checkpoint_Bytes; Item : Checkpoint) return Boolean is
     (Header_Valid (Bytes) and then
      Item.Scope = Context_Value (Context_Payload (Bytes)) and then
      Item.Identity = Digest (Bytes (161 .. 192)) and then
      Item.Previous = Digest (Bytes (193 .. 224)) and then
      Item.Capture = Digest (Bytes (225 .. 256)) and then
      Item.Epoch = Word_Value (Word (Bytes (257 .. 264))) and then
      Item.Through = Word_Value (Word (Bytes (265 .. 272))) and then
      Item.Retention_Epoch = Word_Value (Word (Bytes (273 .. 280))) and then
      Item.Count = Claim_Count (Bytes (294)) and then
      Item.Operations_Count = Operation_Count (Bytes (295)) and then
      (for all Kind in Claim_Kind => Item.Coverage (Kind) =
         Coverage_Value (Bytes (Coverage_Positions (Kind)))))
   with Global => null;

   function Decoded_As (Bytes : Checkpoint_Bytes; Item : Checkpoint)
      return Boolean is
     (Valid (Bytes) and then Header_Decoded_As (Bytes, Item) and then
      (for all I in Claim_Index =>
         Decoded_As (Claim_Payload (Bytes, I), Item.Claims (I))) and then
      (for all I in Operation_Index =>
         Decoded_As (Operation_Payload (Bytes, I), Item.Operations (I))))
   with Global => null;

   procedure Decode
     (Bytes : Checkpoint_Bytes; Accepted : out Boolean; Item : out Checkpoint)
   with Global => null, Always_Terminates,
     Depends => (Accepted => Bytes, Item => Bytes),
     Post => Accepted = Valid (Bytes) and then
       (if Accepted then Decoded_As (Bytes, Item) else Item = Empty_Checkpoint);
end SIA_Continuity_Checkpoint_Wire;
