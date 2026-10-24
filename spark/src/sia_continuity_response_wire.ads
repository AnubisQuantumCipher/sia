with SIA_Policy;
with SIA_Continuity;
with SIA_Continuity_Transitions;
with SIA_Continuity_Frame_Wire;

--  Fixed representation and result/exit correlation only. No I/O or authority.
package SIA_Continuity_Response_Wire with SPARK_Mode, Pure is
   use SIA_Policy;
   use SIA_Continuity;
   use SIA_Continuity_Transitions;
   use SIA_Continuity_Frame_Wire;

   type Response_Bytes is array (Positive range 1 .. 64) of Digest_Byte;
   subtype Restoration_Code is Digest_Byte range 1 .. 7;
   subtype Transition_Code is Digest_Byte range 1 .. 9;

   function Operation_Code (Kind : Request_Kind) return Digest_Byte is
     (case Kind is
        when Malformed => 0, when Restore_Request => 1,
        when Transition_Request => 2)
   with Global => null;

   function Restoration_Number (Value : Restoration) return Restoration_Code is
     (case Value is
        when Invalid_Checkpoint => 1, when Identity_Mismatch => 2,
        when Stale_Checkpoint => 3, when Need_Evidence => 4,
        when Reconcile_Repository => 5, when Reconcile_Operations => 6,
        when References_Proposed => 7)
   with Global => null;

   function Transition_Number (Value : Transition_Result) return Transition_Code is
     (case Value is
        when Invalid_Before => 1, when Invalid_After => 2,
        when Task_Mismatch => 3, when Predecessor_Mismatch => 4,
        when Watermark_Regression => 5, when Operation_Lost => 6,
        when Unsupported_Change => 7, when Need_Transition_Evidence => 8,
        when Transition_Proposed => 9)
   with Global => null;

   function Restoration_Value (Value : Restoration_Code) return Restoration is
     (case Value is
        when 1 => Invalid_Checkpoint, when 2 => Identity_Mismatch,
        when 3 => Stale_Checkpoint, when 4 => Need_Evidence,
        when 5 => Reconcile_Repository, when 6 => Reconcile_Operations,
        when 7 => References_Proposed)
   with Global => null;

   function Transition_Value (Value : Transition_Code) return Transition_Result is
     (case Value is
        when 1 => Invalid_Before, when 2 => Invalid_After,
        when 3 => Task_Mismatch, when 4 => Predecessor_Mismatch,
        when 5 => Watermark_Regression, when 6 => Operation_Lost,
        when 7 => Unsupported_Change, when 8 => Need_Transition_Evidence,
        when 9 => Transition_Proposed)
   with Global => null;

   function Canonical (Item : Frame_Decision) return Frame_Decision is
     (case Item.Kind is
        when Malformed => (Malformed, Invalid_Checkpoint, Invalid_Before),
        when Restore_Request =>
          (Restore_Request, Item.Restore_Value, Invalid_Before),
        when Transition_Request =>
          (Transition_Request, Invalid_Checkpoint, Item.Transition_Value))
   with Global => null;

   function Valid (Bytes : Response_Bytes) return Boolean is
     (Bytes (1) = 83 and then Bytes (2) = 73 and then Bytes (3) = 65 and then
      Bytes (4) = 82 and then Bytes (5) = 1 and then Bytes (6) = Bytes (7)
      and then
        (case Bytes (6) is
           when 0 => Bytes (8) = 1,
           when 1 => Bytes (8) in Restoration_Code,
           when 2 => Bytes (8) in Transition_Code,
           when others => False)
      and then (for all I in 9 .. 64 => Bytes (I) = 0))
   with Global => null;

   function Decoded_As (Bytes : Response_Bytes; Item : Frame_Decision)
      return Boolean is
     (Valid (Bytes) and then Bytes (6) = Operation_Code (Item.Kind) and then
      Item = Canonical (Item) and then Bytes (8) =
        (case Item.Kind is
           when Malformed => 1,
           when Restore_Request => Restoration_Number (Item.Restore_Value),
           when Transition_Request => Transition_Number (Item.Transition_Value)))
   with Global => null;

   function Encode (Item : Frame_Decision) return Response_Bytes is
     ([1 => 83, 2 => 73, 3 => 65, 4 => 82, 5 => 1,
       6 | 7 => Operation_Code (Item.Kind),
       8 => (case Item.Kind is
               when Malformed => 1,
               when Restore_Request => Restoration_Number (Item.Restore_Value),
               when Transition_Request => Transition_Number (Item.Transition_Value)),
       others => 0])
   with Global => null,
     Post => Decoded_As (Encode'Result, Canonical (Item));

   procedure Decode
     (Bytes : Response_Bytes; Accepted : out Boolean; Item : out Frame_Decision)
   with Global => null, Always_Terminates,
     Depends => (Accepted => Bytes, Item => Bytes),
     Post => Accepted = Valid (Bytes) and then
       (if Accepted then Decoded_As (Bytes, Item)
        else Item = Frame_Decision'(Malformed, Invalid_Checkpoint, Invalid_Before));

   function Expected_Exit (Kind : Request_Kind) return Natural is
     (if Kind = Malformed then 65 else 0)
   with Global => null;

   --  Malformed/65 is a transport refusal. This does not authenticate the
   --  process/request instance or recompute the original request's policy.
   function Matches
     (Bytes : Response_Bytes; Requested : Request_Kind; Process_Exit : Integer)
      return Boolean is
     (Valid (Bytes) and then Bytes (6) = Operation_Code (Requested) and then
      Process_Exit = Expected_Exit (Requested))
   with Global => null;
end SIA_Continuity_Response_Wire;
