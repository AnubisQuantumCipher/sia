with SIA_Policy;
with SIA_Continuity;

--  Fixed record decoding only. No framing, authentication or authority.
package SIA_Continuity_Record_Wire with SPARK_Mode, Pure is
   use SIA_Policy;
   use SIA_Continuity;

   type Word is array (Positive range 1 .. 8) of Digest_Byte;
   type Claim_Bytes is array (Positive range 1 .. 128) of Digest_Byte;
   type Operation_Bytes is array (Positive range 1 .. 144) of Digest_Byte;
   type Witness_Bytes is array (Positive range 1 .. 48) of Digest_Byte;
   subtype Kind_Code is Digest_Byte range 0 .. 12;
   subtype Origin_Code is Digest_Byte range 0 .. 3;
   subtype Role_Code is Digest_Byte range 0 .. 3;
   subtype Phase_Code is Digest_Byte range 0 .. 4;
   Empty_Witness : constant Witness :=
     (Present => False, Durable => False,
      Bound_To => (Epoch => 0, Transaction => [others => 0]));

   function Word_Value (Bytes : Word) return Generation is
     (((((((Generation (Bytes (1)) * 2 ** 56 +
      Generation (Bytes (2)) * 2 ** 48) +
      Generation (Bytes (3)) * 2 ** 40) +
      Generation (Bytes (4)) * 2 ** 32) +
      Generation (Bytes (5)) * 2 ** 24) +
      Generation (Bytes (6)) * 2 ** 16) +
      Generation (Bytes (7)) * 2 ** 8) +
      Generation (Bytes (8)))
   with Global => null, Pre => Bytes (1) <= 127;

   function Kind_Value (Code : Kind_Code) return Claim_Kind is
     (case Code is
         when 0 => Goal, when 1 => Acceptance, when 2 => Constraint,
         when 3 => Correction, when 4 => Decision, when 5 => Rejection,
         when 6 => Source, when 7 => Completed, when 8 => Verification,
         when 9 => Failure, when 10 => Next_Action,
         when 11 => Permission_Reference, when 12 => Pending_Approval)
   with Global => null;

   function Origin_Value (Code : Origin_Code) return Origin is
     (case Code is
         when 0 => Source_Record, when 1 => Derived_Record,
         when 2 => Model_Record, when 3 => Legacy_Record)
   with Global => null;

   function Role_Value (Code : Role_Code) return Role is
     (case Code is
         when 0 => User, when 1 => Assistant,
         when 2 => Tool, when 3 => System_Role)
   with Global => null;

   function Phase_Value (Code : Phase_Code) return Operation_Phase is
     (case Code is
         when 0 => Planned, when 1 => Dispatched, when 2 => Uncertain,
         when 3 => Observed_Complete, when 4 => Acknowledged)
   with Global => null;

   function Valid (Bytes : Claim_Bytes) return Boolean is
     (Bytes (97) <= 127 and then Bytes (105) in Kind_Code and then
      Bytes (106) in Origin_Code and then Bytes (107) in Role_Code and then
      Bytes (108) <= Max_Claims and then
      (for all I in 109 .. 128 => Bytes (I) = 0))
   with Global => null;

   function Valid (Bytes : Operation_Bytes) return Boolean is
     (Bytes (129) in Phase_Code and then Bytes (130) <= 1 and then
      (for all I in 131 .. 144 => Bytes (I) = 0))
   with Global => null;

   function Valid (Bytes : Witness_Bytes) return Boolean is
     (Bytes (1) <= 1 and then Bytes (2) <= 1 and then Bytes (3) <= 127
      and then (for all I in 43 .. 48 => Bytes (I) = 0))
   with Global => null;

   function Decoded_As (Bytes : Claim_Bytes; Item : Claim) return Boolean is
     (Valid (Bytes) and then
      Item.Identity = Digest (Bytes (1 .. 32)) and then
      Item.Slot = Digest (Bytes (33 .. 64)) and then
      Item.Source_Record_Id = Digest (Bytes (65 .. 96)) and then
      Item.Sequence = Word_Value (Word (Bytes (97 .. 104))) and then
      Item.Kind = Kind_Value (Bytes (105)) and then
      Item.From = Origin_Value (Bytes (106)) and then
      Item.Speaker = Role_Value (Bytes (107)) and then
      Item.Replaces = Claim_Count (Bytes (108)))
   with Global => null;

   function Decoded_As
     (Bytes : Operation_Bytes; Item : SIA_Continuity.Operation) return Boolean is
     (Valid (Bytes) and then
      Item.Identity = Digest (Bytes (1 .. 32)) and then
      Item.Action = Digest (Bytes (33 .. 64)) and then
      Item.Source_Record_Id = Digest (Bytes (65 .. 96)) and then
      Item.Result_Record_Id = Digest (Bytes (97 .. 128)) and then
      Item.Stage = Phase_Value (Bytes (129)) and then
      Item.Has_Result = (Bytes (130) = 1))
   with Global => null;

   function Decoded_As
     (Bytes : Witness_Bytes; Item : Witness) return Boolean is
     (Valid (Bytes) and then
      Item.Present = (Bytes (1) = 1) and then
      Item.Durable = (Bytes (2) = 1) and then
      Item.Bound_To.Epoch = Word_Value (Word (Bytes (3 .. 10))) and then
      Item.Bound_To.Transaction = Digest (Bytes (11 .. 42)))
   with Global => null;

   procedure Decode
     (Bytes : Claim_Bytes; Accepted : out Boolean; Item : out Claim)
   with Global => null, Always_Terminates,
     Depends => (Accepted => Bytes, Item => Bytes),
     Post => Accepted = Valid (Bytes) and then
       (if Accepted then Decoded_As (Bytes, Item) else Item = Empty_Claim);

   procedure Decode
     (Bytes : Operation_Bytes; Accepted : out Boolean;
      Item : out SIA_Continuity.Operation)
   with Global => null, Always_Terminates,
     Depends => (Accepted => Bytes, Item => Bytes),
     Post => Accepted = Valid (Bytes) and then
       (if Accepted then Decoded_As (Bytes, Item) else Item = Empty_Operation);

   procedure Decode
     (Bytes : Witness_Bytes; Accepted : out Boolean; Item : out Witness)
   with Global => null, Always_Terminates,
     Depends => (Accepted => Bytes, Item => Bytes),
     Post => Accepted = Valid (Bytes) and then
       (if Accepted then Decoded_As (Bytes, Item) else Item = Empty_Witness);
end SIA_Continuity_Record_Wire;
