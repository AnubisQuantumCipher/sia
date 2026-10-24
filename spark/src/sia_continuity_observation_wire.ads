with SIA_Policy;
with SIA_Continuity;
with SIA_Continuity_Transitions;
with SIA_Continuity_Record_Wire;

--  Representation only: availability flags and bindings are not authenticated.
package SIA_Continuity_Observation_Wire with SPARK_Mode, Pure is
   use SIA_Policy;
   use SIA_Continuity;
   use SIA_Continuity_Transitions;
   use SIA_Continuity_Record_Wire;

   type Context_Bytes is array (Positive range 1 .. 160) of Digest_Byte;
   type Claim_Observation_Bytes is
     array (Positive range 1 .. 144) of Digest_Byte;
   type Operation_Observation_Bytes is
     array (Positive range 1 .. 160) of Digest_Byte;
   type Transition_Observation_Bytes is
     array (Positive range 1 .. 448) of Digest_Byte;
   subtype Availability_Code is Digest_Byte range 0 .. 3;
   subtype Event_Code is Digest_Byte range 1 .. 5;

   Empty_Claim_Observation : constant Claim_Observation :=
     (State => Unknown,
      Item => (Identity | Slot | Source_Record_Id => [others => 0],
               Sequence => 0, Kind => Goal, From => Legacy_Record,
               Speaker => Tool, Replaces => 0));
   Empty_Operation_Observation : constant Operation_Observation :=
     (State => Unknown,
      Item => (Identity | Action | Source_Record_Id | Result_Record_Id =>
                 [others => 0], Stage => Planned, Has_Result => False));

   function Context_Value (Bytes : Context_Bytes) return Context is
     (Task_Id => Digest (Bytes (1 .. 32)),
      Session_Id => Digest (Bytes (33 .. 64)),
      Repository => Digest (Bytes (65 .. 96)),
      Revision => Digest (Bytes (97 .. 128)),
      Dirty => Digest (Bytes (129 .. 160)))
   with Global => null;

   function Availability_Value (Code : Availability_Code)
      return Availability is
     (case Code is
         when 0 => Unknown, when 1 => Missing,
         when 2 => Retained, when 3 => Retracted)
   with Global => null;

   function Event_Value (Code : Event_Code) return Event_Kind is
     (case Code is
         when 1 => Dispatch_Attempt, when 2 => Interruption,
         when 3 => Observed_Outcome, when 4 => Reconciled_Outcome,
         when 5 => Acknowledgment)
   with Global => null;

   --  Copy each fixed payload explicitly.  The wire containers have distinct
   --  types; a conversion of their slices would hide a compiler-generated copy.
   function Claim_Payload (Bytes : Claim_Observation_Bytes)
      return Claim_Bytes is
     ([for I in Claim_Bytes'Range => Bytes (I + 1)])
   with Global => null,
     Post => (for all I in Claim_Bytes'Range =>
                Claim_Payload'Result (I) = Bytes (I + 1));

   function Operation_Payload (Bytes : Operation_Observation_Bytes)
      return Operation_Bytes is
     ([for I in Operation_Bytes'Range => Bytes (I + 1)])
   with Global => null,
     Post => (for all I in Operation_Bytes'Range =>
                Operation_Payload'Result (I) = Bytes (I + 1));

   function Before_Payload (Bytes : Transition_Observation_Bytes)
      return Operation_Bytes is
     ([for I in Operation_Bytes'Range => Bytes (I + 144)])
   with Global => null,
     Post => (for all I in Operation_Bytes'Range =>
                Before_Payload'Result (I) = Bytes (I + 144));

   function After_Payload (Bytes : Transition_Observation_Bytes)
      return Operation_Bytes is
     ([for I in Operation_Bytes'Range => Bytes (I + 288)])
   with Global => null,
     Post => (for all I in Operation_Bytes'Range =>
                After_Payload'Result (I) = Bytes (I + 288));

   function Valid (Bytes : Claim_Observation_Bytes) return Boolean is
     (Bytes (1) in Availability_Code and then
      Valid (Claim_Payload (Bytes)) and then
      (for all I in 130 .. 144 => Bytes (I) = 0))
   with Global => null;

   function Valid (Bytes : Operation_Observation_Bytes) return Boolean is
     (Bytes (1) in Availability_Code and then
      Valid (Operation_Payload (Bytes)) and then
      (for all I in 146 .. 160 => Bytes (I) = 0))
   with Global => null;

   function Valid (Bytes : Transition_Observation_Bytes) return Boolean is
     (Bytes (129) <= 127 and then Bytes (137) <= 127 and then
      Valid (Before_Payload (Bytes)) and then
      Valid (After_Payload (Bytes)) and then
      Bytes (433) in Availability_Code and then
      Bytes (434) in Event_Code and then Bytes (435) <= 1 and then
      (for all I in 436 .. 448 => Bytes (I) = 0))
   with Global => null;

   function Decoded_As
     (Bytes : Claim_Observation_Bytes; Item : Claim_Observation)
      return Boolean is
     (Valid (Bytes) and then Item.State = Availability_Value (Bytes (1))
      and then Decoded_As (Claim_Payload (Bytes), Item.Item))
   with Global => null;

   function Decoded_As
     (Bytes : Operation_Observation_Bytes; Item : Operation_Observation)
      return Boolean is
     (Valid (Bytes) and then Item.State = Availability_Value (Bytes (1))
      and then Decoded_As (Operation_Payload (Bytes), Item.Item))
   with Global => null;

   function Decoded_As
     (Bytes : Transition_Observation_Bytes; Item : Observation)
      return Boolean is
     (Valid (Bytes) and then
      Item.Before_Id = Digest (Bytes (1 .. 32)) and then
      Item.After_Id = Digest (Bytes (33 .. 64)) and then
      Item.Event_Record_Id = Digest (Bytes (65 .. 96)) and then
      Item.Outcome_Record_Id = Digest (Bytes (97 .. 128)) and then
      Item.Before_Epoch = Word_Value (Word (Bytes (129 .. 136))) and then
      Item.After_Epoch = Word_Value (Word (Bytes (137 .. 144))) and then
      Decoded_As (Before_Payload (Bytes),
                  Item.Before_Operation) and then
      Decoded_As (After_Payload (Bytes),
                  Item.After_Operation) and then
      Item.State = Availability_Value (Bytes (433)) and then
      Item.Kind = Event_Value (Bytes (434)) and then
      Item.Has_Outcome = (Bytes (435) = 1))
   with Global => null;

   procedure Decode
     (Bytes : Claim_Observation_Bytes; Accepted : out Boolean;
      Item : out Claim_Observation)
   with Global => null, Always_Terminates,
     Depends => (Accepted => Bytes, Item => Bytes),
     Post => Accepted = Valid (Bytes) and then
       (if Accepted then Decoded_As (Bytes, Item)
        else Item = Empty_Claim_Observation);

   procedure Decode
     (Bytes : Operation_Observation_Bytes; Accepted : out Boolean;
      Item : out Operation_Observation)
   with Global => null, Always_Terminates,
     Depends => (Accepted => Bytes, Item => Bytes),
     Post => Accepted = Valid (Bytes) and then
       (if Accepted then Decoded_As (Bytes, Item)
        else Item = Empty_Operation_Observation);

   procedure Decode
     (Bytes : Transition_Observation_Bytes; Accepted : out Boolean;
      Item : out Observation)
   with Global => null, Always_Terminates,
     Depends => (Accepted => Bytes, Item => Bytes),
     Post => Accepted = Valid (Bytes) and then
       (if Accepted then Decoded_As (Bytes, Item) else Item = Empty_Observation);
end SIA_Continuity_Observation_Wire;
