with SIA_Policy;
with SIA_Pack_Retirement;
with SIA_Continuity_Record_Wire;

--  Canonical proposal decoding only. No hash authentication or effect authority.
package SIA_Pack_Plan_Wire with SPARK_Mode, Pure is
   use SIA_Policy;
   use SIA_Pack_Retirement;
   Frame_Length : constant := 16_384;
   type Frame is array (Positive range 1 .. Frame_Length) of Digest_Byte;
   subtype Small_Offset is Positive range 1 .. Frame_Length - 7;
   subtype Record_Offset is Positive range 433 .. 14_201;
   subtype Roster_Offset is Positive range 425 .. 9_657;
   Record_Width : constant := 72;
   Roster_Width : constant := 4_616;
   Prior_Start : constant := 425;
   Target_Start : constant := 5_041;
   Represented_Start : constant := 9_657;
   Presence_Start : constant := 14_273;
   Generations_Start : constant := 14_337;

   function Small_Valid (Data : Frame; Start : Small_Offset) return Boolean is
     (Data (Start) = 0 and Data (Start + 1) = 0 and
      Data (Start + 2) = 0 and Data (Start + 3) = 0 and
      Data (Start + 4) = 0 and
      (Data (Start + 5) = 0 or
       (Data (Start + 5) = 1 and Data (Start + 6) = 0 and
        Data (Start + 7) = 0)))
   with Global => null;
   function Small_Value (Data : Frame; Start : Small_Offset) return Input_Count is
     (((Natural (Data (Start + 5)) * 65_536) +
       (Natural (Data (Start + 6)) * 256)) + Natural (Data (Start + 7)))
   with Global => null, Pre => Small_Valid (Data, Start);

   function Record_Start (Start : Roster_Offset; Slot : Record_Index)
      return Record_Offset is ((Start + 8) + (Slot - 1) * Record_Width)
   with Global => null;
   function Record_Value (Data : Frame; Start : Record_Offset)
      return Record_Reference
   with Global => null, Pre => Small_Valid (Data, Start + 64),
     Post => Record_Value'Result.Identity = Digest (Data (Start .. Start + 31)) and
       Record_Value'Result.Content = Digest (Data (Start + 32 .. Start + 63)) and
       Record_Value'Result.Bytes = Small_Value (Data, Start + 64);

   function Roster_Valid (Data : Frame; Start : Roster_Offset) return Boolean is
     ((for all I in Start .. Start + 6 => Data (I) = 0) and
      Data (Start + 7) <= Max_Records and
      (for all I in Record_Index => Small_Valid (Data, Record_Start (Start, I) + 64)))
   with Global => null;
   function Roster_Decoded (Data : Frame; Start : Roster_Offset; Item : Roster)
      return Boolean is
     (Roster_Valid (Data, Start) and then
      (Item.Count = Record_Count (Data (Start + 7)) and
      (for all I in Record_Index => Item.Records (I) =
         Record_Value (Data, Record_Start (Start, I)))))
   with Global => null;
   pragma Annotate (GNATprove, Hide_Info, "Expression_Function_Body", Record_Start);
   function Roster_Value (Data : Frame; Start : Roster_Offset) return Roster
   with Global => null, Pre => Roster_Valid (Data, Start),
     Post => Roster_Decoded (Data, Start, Roster_Value'Result);

   function Shape_Valid (Data : Frame; Length : Natural) return Boolean is
     (Length = Frame_Length and Data (1) = 1 and
      (for all I in 2 .. 8 => Data (I) = 0) and Data (41) <= 127 and
      (Small_Valid (Data, 401) and then Small_Value (Data, 401) in Organ_Length) and
      Small_Valid (Data, 409) and Small_Valid (Data, 417) and
      Roster_Valid (Data, Prior_Start) and Roster_Valid (Data, Target_Start) and
      Roster_Valid (Data, Represented_Start) and
      (for all I in Presence_Start .. Generations_Start - 1 => Data (I) <= 1))
   with Global => null;

   function Scope_Value (Data : Frame) return Context is
     (((SIA_Continuity_Record_Wire.Word_Value
          (SIA_Continuity_Record_Wire.Word (Data (41 .. 48))),
        Digest (Data (49 .. 80))),
       Digest (Data (81 .. 112)), Digest (Data (113 .. 144)),
       Digest (Data (145 .. 176)), Digest (Data (177 .. 208)),
       Digest (Data (209 .. 240)), Digest (Data (241 .. 272)),
       Digest (Data (273 .. 304)), Digest (Data (305 .. 336)),
       Digest (Data (337 .. 368)), Digest (Data (369 .. 400))))
   with Global => null, Pre => Data (41) <= 127;

   function Decoded_As (Data : Frame; Length : Natural; Item : Plan) return Boolean is
     (Shape_Valid (Data, Length) and then
      (Item.Identity = Digest (Data (9 .. 40)) and Item.Scope = Scope_Value (Data) and
      Item.Organ_Bytes = Small_Value (Data, 401) and
      Item.Selected = Small_Value (Data, 409) and
      Item.Fallback_Count = Small_Value (Data, 417) and
      Roster_Decoded (Data, Prior_Start, Item.Prior) and
      Roster_Decoded (Data, Target_Start, Item.Target) and
      Roster_Decoded (Data, Represented_Start, Item.Represented) and
      (for all I in Record_Index =>
         Item.Legacy_Present (I) = (Data ((Presence_Start + I) - 1) = 1) and
         Item.Legacy_Generation (I) = Digest
           (Data (Generations_Start + (I - 1) * 32 .. (Generations_Start + I * 32) - 1)))))
   with Global => null;

   function Value (Data : Frame) return Plan
   with Global => null, Pre => Shape_Valid (Data, Frame_Length),
     Post => Decoded_As (Data, Frame_Length, Value'Result);

   procedure Decode
     (Data : Frame; Length : Natural; Accepted : out Boolean; Item : out Plan)
   with Global => null, Always_Terminates,
     Depends => (Accepted => (Data, Length), Item => (Data, Length)),
     Post => Accepted =
       (Shape_Valid (Data, Length) and then Valid_Retirement_Plan (Value (Data))) and then
       (if Accepted then Decoded_As (Data, Length, Item) and then Valid_Retirement_Plan (Item)
        else Item = Empty_Plan);
end SIA_Pack_Plan_Wire;
