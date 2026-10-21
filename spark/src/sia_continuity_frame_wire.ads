with SIA_Policy;
with SIA_Continuity;
with SIA_Continuity_Transitions;
with SIA_Continuity_Checkpoint_Wire;
with SIA_Continuity_Current_Wire;
with SIA_Continuity_Observation_Wire;

--  One fixed request in memory. No I/O, identity authentication or action grant.
package SIA_Continuity_Frame_Wire with SPARK_Mode, Pure is
   use SIA_Policy;
   use SIA_Continuity;
   use SIA_Continuity_Transitions;
   use SIA_Continuity_Checkpoint_Wire;
   use SIA_Continuity_Current_Wire;
   use SIA_Continuity_Observation_Wire;

   type Frame_Bytes is array (Positive range 1 .. 32768) of Digest_Byte;
   type Request_Kind is (Malformed, Restore_Request, Transition_Request);
   type Decoded_Request is record
      Kind : Request_Kind;
      Before, After : Checkpoint;
      Current : Current_Evidence;
      Events : Observations;
   end record;

   function Empty_Request return Decoded_Request is
     (Kind => Malformed, Before | After => Empty_Checkpoint,
      Current => Empty_Current, Events => [others => Empty_Observation])
   with Global => null;

   function Before_Payload (Bytes : Frame_Bytes) return Checkpoint_Bytes is
     ([for I in Checkpoint_Bytes'Range => Bytes (32 + I)])
   with Global => null,
     Post => (for all I in Checkpoint_Bytes'Range =>
       Before_Payload'Result (I) = Bytes (32 + I));

   function After_Payload (Bytes : Frame_Bytes) return Checkpoint_Bytes is
     ([for I in Checkpoint_Bytes'Range => Bytes (10848 + I)])
   with Global => null,
     Post => (for all I in Checkpoint_Bytes'Range =>
       After_Payload'Result (I) = Bytes (10848 + I));

   function Current_Payload (Bytes : Frame_Bytes) return Current_Bytes is
     ([for I in Current_Bytes'Range => Bytes (10848 + I)])
   with Global => null,
     Post => (for all I in Current_Bytes'Range =>
       Current_Payload'Result (I) = Bytes (10848 + I));

   function Event_Payload (Bytes : Frame_Bytes; Index : Operation_Index)
      return Transition_Observation_Bytes is
     ([for I in Transition_Observation_Bytes'Range =>
       Bytes ((21664 + (Index - 1) * 448) + I)])
   with Global => null,
     Post => (for all I in Transition_Observation_Bytes'Range =>
       Event_Payload'Result (I) =
         Bytes ((21664 + (Index - 1) * 448) + I));

   function Header_Valid (Bytes : Frame_Bytes) return Boolean is
     (Bytes (1) = 83 and then Bytes (2) = 73 and then
      Bytes (3) = 65 and then Bytes (4) = 67 and then Bytes (5) = 1 and then
      (for all I in 9 .. 32 => Bytes (I) = 0))
   with Global => null;

   function Restore_Valid (Bytes : Frame_Bytes) return Boolean is
     (Header_Valid (Bytes) and then Bytes (6) = 1 and then
      Bytes (7) = 89 and then Bytes (8) = 192 and then
      (for all I in 22977 .. Frame_Bytes'Last => Bytes (I) = 0) and then
      Valid (Before_Payload (Bytes)) and then Valid (Current_Payload (Bytes)))
   with Global => null;

   function Transition_Valid (Bytes : Frame_Bytes) return Boolean is
     (Header_Valid (Bytes) and then Bytes (6) = 2 and then
      Bytes (7) = 112 and then Bytes (8) = 160 and then
      (for all I in 28833 .. Frame_Bytes'Last => Bytes (I) = 0) and then
      Valid (Before_Payload (Bytes)) and then Valid (After_Payload (Bytes))
      and then (for all I in Operation_Index =>
        Valid (Event_Payload (Bytes, I))))
   with Global => null;

   function Valid (Bytes : Frame_Bytes) return Boolean is
     (Restore_Valid (Bytes) or else Transition_Valid (Bytes))
   with Global => null;

   function Decoded_As (Bytes : Frame_Bytes; Item : Decoded_Request)
      return Boolean is
     (case Item.Kind is
        when Malformed => False,
        when Restore_Request => Restore_Valid (Bytes) and then
          Decoded_As (Before_Payload (Bytes), Item.Before) and then
          Decoded_As (Current_Payload (Bytes), Item.Current) and then
          Item.After = Empty_Checkpoint and then
          Item.Events = Observations'[others => Empty_Observation],
        when Transition_Request => Transition_Valid (Bytes) and then
          Decoded_As (Before_Payload (Bytes), Item.Before) and then
          Decoded_As (After_Payload (Bytes), Item.After) and then
          Item.Current = Empty_Current and then
          (for all I in Operation_Index =>
            Decoded_As (Event_Payload (Bytes, I), Item.Events (I))))
   with Global => null;

   procedure Decode
     (Bytes : Frame_Bytes; Accepted : out Boolean; Item : out Decoded_Request)
   with Global => null, Always_Terminates,
     Depends => (Accepted => Bytes, Item => Bytes),
     Post => Accepted = Valid (Bytes) and then
       (if Accepted then Decoded_As (Bytes, Item) else Item = Empty_Request);

   --  Unused result families are canonical. None of these values is authority.
   type Frame_Decision is record
      Kind : Request_Kind;
      Restore_Value : Restoration;
      Transition_Value : Transition_Result;
   end record;

   function Classify (Item : Decoded_Request) return Frame_Decision is
     (case Item.Kind is
        when Malformed =>
          (Malformed, Invalid_Checkpoint, Invalid_Before),
        when Restore_Request =>
          (Restore_Request, Classify (Item.Before, Item.Current), Invalid_Before),
        when Transition_Request =>
          (Transition_Request, Invalid_Checkpoint,
           Classify (Item.Before, Item.After, Item.Events)))
   with Global => null;

   procedure Evaluate
     (Bytes : Frame_Bytes; Accepted : out Boolean; Item : out Decoded_Request;
      Result : out Frame_Decision)
   with Global => null, Always_Terminates,
     Depends => (Accepted => Bytes, Item => Bytes, Result => Bytes),
     Post => Accepted = Valid (Bytes) and then
       (if Accepted then Decoded_As (Bytes, Item) else Item = Empty_Request)
       and then Result = Classify (Item);
end SIA_Continuity_Frame_Wire;
