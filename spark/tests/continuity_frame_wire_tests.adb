with SIA_Policy;
with SIA_Continuity;
with SIA_Continuity_Transitions;
with SIA_Continuity_Checkpoint_Wire;
with SIA_Continuity_Current_Wire;
with SIA_Continuity_Frame_Wire;

procedure Continuity_Frame_Wire_Tests with SPARK_Mode is
   use SIA_Policy;
   use SIA_Continuity;
   use SIA_Continuity_Transitions;
   use SIA_Continuity_Checkpoint_Wire;
   use SIA_Continuity_Current_Wire;
   use SIA_Continuity_Frame_Wire;

   --  Independent literal frame vectors, not produced by an encoder.
   Restore_Vector : constant Frame_Bytes :=
     [1 => 83, 2 => 73, 3 => 65, 4 => 67, 5 | 6 => 1, 7 => 89, 8 => 192,
      33 => 11, 64 => 12, 193 => 13, 257 => 14, 296 => 1,
      10849 => 21, 11009 => 22, 11041 => 23, 11080 => 2,
      11098 => 1, 11138 => 24, others => 0];
   Transition_Vector : constant Frame_Bytes :=
     [1 => 83, 2 => 73, 3 => 65, 4 => 67, 5 => 1, 6 => 2, 7 => 112, 8 => 160,
      33 => 11, 193 => 12, 296 => 1, 10849 => 21, 11009 => 22,
      21665 => 31, 21696 => 32, 21697 => 33, 21800 => 1, 21808 => 2,
      21809 => 34, 21937 => 4, 21938 => 1, 22097 => 2, 22099 => 1,
      24801 => 41, 25233 => 3, 28385 => 51, 28817 => 1,
      22098 | 22546 | 22994 | 23442 | 23890 | 24338 | 24786 | 25234 |
      25682 | 26130 | 26578 | 27026 | 27474 | 27922 | 28370 | 28818 => 1,
      others => 0];
   Zero_Claim : constant Claim :=
     (Identity | Slot | Source_Record_Id => [others => 0], Sequence => 0,
      Kind => Goal, From => Source_Record, Speaker => User, Replaces => 0);
   Zero_Checkpoint : constant Checkpoint :=
     (Empty_Checkpoint with delta Claims => [others => Zero_Claim]);
   Zero_Current : constant Current_Evidence :=
     (Empty_Current with delta Claims =>
       [others => (State => Unknown, Item => Zero_Claim)]);

   procedure Refuse (Bytes : Frame_Bytes)
   with Global => null, Always_Terminates,
     Pre => not Valid (Bytes)
   is
      Accepted : Boolean;
      Item : Decoded_Request;
      Result : Frame_Decision;
   begin
      Evaluate (Bytes, Accepted, Item, Result);
      pragma Assert (not Accepted and then Item = Empty_Request);
      pragma Assert
        (Result = Frame_Decision'(Malformed, Invalid_Checkpoint, Invalid_Before));
   end Refuse;

   procedure Check_Restore with Global => null, Always_Terminates is
      Accepted : Boolean;
      Item : Decoded_Request;
      Result : Frame_Decision;
      Expected_Before : constant Checkpoint :=
        (Zero_Checkpoint with delta
          Scope => (Zero_Checkpoint.Scope with delta
            Task_Id => [1 => 11, 32 => 12, others => 0]),
          Identity => [1 => 13, others => 0],
          Capture => [1 => 14, others => 0], Epoch => 1);
      Expected_Current : constant Current_Evidence :=
        (Zero_Current with delta
          Scope => (Zero_Current.Scope with delta
            Task_Id => [1 => 21, others => 0]),
          Checkpoint_Id => [1 => 22, others => 0],
          Capture => [1 => 23, others => 0], Epoch => 2,
          Manifest => (Present => False, Durable => True,
            Bound_To => (Epoch => 0,
              Transaction => [32 => 24, others => 0])));
   begin
      Evaluate (Restore_Vector, Accepted, Item, Result);
      pragma Assert (Accepted);
      pragma Assert (Item = Decoded_Request'(
        Restore_Request, Expected_Before, Empty_Checkpoint, Expected_Current,
        [others => Empty_Observation]));
      pragma Assert (Result = Frame_Decision'(
        Restore_Request, Invalid_Checkpoint, Invalid_Before));
      --  Representable absent/nonempty witnesses survive to policy refusal.
      pragma Assert (not Item.Current.Manifest.Present);
      pragma Assert (Item.Current.Manifest.Durable);
   end Check_Restore;

   procedure Check_Transition with Global => null, Always_Terminates is
      Accepted : Boolean;
      Item : Decoded_Request;
      Result : Frame_Decision;
      Expected_Before : constant Checkpoint :=
        (Zero_Checkpoint with delta
          Scope => (Zero_Checkpoint.Scope with delta
            Task_Id => [1 => 11, others => 0]),
          Identity => [1 => 12, others => 0], Epoch => 1);
      Expected_After : constant Checkpoint :=
        (Zero_Checkpoint with delta
          Scope => (Zero_Checkpoint.Scope with delta
            Task_Id => [1 => 21, others => 0]),
          Identity => [1 => 22, others => 0]);
      Expected_Events : constant Observations :=
        [1 => (Empty_Observation with delta State => Retained,
          Before_Id => [1 => 31, 32 => 32, others => 0],
          After_Id => [1 => 33, others => 0], Before_Epoch => 1,
          After_Epoch => 2, Has_Outcome => True,
          Before_Operation => (Empty_Operation with delta
            Identity => [1 => 34, others => 0], Stage => Acknowledged,
            Has_Result => True)),
         8 => (Empty_Observation with delta State => Retracted,
           Before_Id => [1 => 41, others => 0]),
         16 => (Empty_Observation with delta State => Missing,
           Before_Id => [1 => 51, others => 0]), others => Empty_Observation];
   begin
      Evaluate (Transition_Vector, Accepted, Item, Result);
      pragma Assert (Accepted);
      pragma Assert (Item = Decoded_Request'(
        Transition_Request, Expected_Before, Expected_After, Empty_Current,
        Expected_Events));
      pragma Assert (Result = Frame_Decision'(
        Transition_Request, Invalid_Checkpoint, Invalid_Before));
   end Check_Transition;

   --  Test-only scalar byte specifications. No production encoder is used.
   --  Every map is total; an untouched position keeps its incoming byte.
   subtype Frame_Index is Positive range
     Frame_Bytes'First .. Frame_Bytes'Last;
   subtype Claim_Prefix is Natural range 0 .. Claim_Index'Last;
   subtype Active_Prefix is Natural range 0 .. 4;
   subtype Coverage_Prefix is Natural range 0 .. 325;
   subtype Cell_Base is Natural range 0 .. 10848 + 352;
   subtype Cell_Stride is Positive range 128 .. 144;
   subtype Cell_Offset is Positive range 1 .. 144;
   type Fixture_Kinds is array (Positive range 1 .. 4) of Digest_Byte;
   Expected_Kinds : constant Fixture_Kinds := [0, 1, 6, 10] with Ghost;

   function At_Cell
     (P : Frame_Index; Base : Cell_Base; Stride : Cell_Stride;
      Offset : Cell_Offset; Through : Claim_Prefix) return Boolean is
     (Through > 0 and then P >= Base + Offset and then
      (P - (Base + Offset)) mod Stride = 0 and then
      (P - (Base + Offset)) / Stride < Through)
   with Ghost, Global => null;

   function Cell_Order
     (P : Frame_Index; Base : Cell_Base; Stride : Cell_Stride)
      return Claim_Prefix is
     (if P >= Base + 1 and then
         (P - (Base + 1)) / Stride < Claim_Index'Last
      then Claim_Prefix ((P - (Base + 1)) / Stride + 1) else 0)
   with Ghost, Global => null;

   function Kind_Byte
     (Index : Claim_Prefix; Kinds : Fixture_Kinds) return Digest_Byte is
     (if Index in Kinds'Range then Kinds (Index) else 0)
   with Ghost, Global => null;

   function Restore_Initial_Byte (P : Frame_Index) return Digest_Byte is
     (case P is
        when 1 => 83, when 2 => 73, when 3 => 65, when 4 => 67,
        when 5 | 6 => 1, when 7 => 89, when 8 => 192,
        when 33 | 10849 => 1, when 65 | 10881 => 2,
        when 97 | 10913 => 3, when 193 | 11009 => 6,
        when 296 | 11080 => 1, when 304 | 11088 | 326 => 4,
        when others => 0)
   with Ghost, Global => null;

   function Transition_Initial_Byte (P : Frame_Index) return Digest_Byte is
     (case P is
        when 1 => 83, when 2 => 73, when 3 => 65, when 4 => 67,
        when 5 => 1, when 6 => 2, when 7 => 112, when 8 => 160,
        when 33 | 10849 => 1, when 65 | 10881 => 2,
        when 97 | 10913 => 3, when 193 | (10848 + 193) => 6,
        when 11009 => 7, when 296 => 1, when (10848 + 264) => 2,
        when 22098 | 22546 | 22994 | 23442 | 23890 | 24338 | 24786 |
          25234 | 25682 | 26130 | 26578 | 27026 | 27474 | 27922 |
          28370 | 28818 => 1,
        when others => 0)
   with Ghost, Global => null;

   function Restore_Canonical_Written
     (P : Frame_Index; Through : Claim_Prefix) return Boolean is
     (At_Cell (P, 32 + 320, 128, 106, Through) or else
      At_Cell (P, 32 + 320, 128, 107, Through) or else
      At_Cell (P, 10848 + 352, 144, 107, Through) or else
      At_Cell (P, 10848 + 352, 144, 108, Through))
   with Ghost, Global => null;

   function Restore_Canonical_Byte
     (Old_Byte : Digest_Byte; P : Frame_Index; Through : Claim_Prefix)
      return Digest_Byte is
     (if At_Cell (P, 32 + 320, 128, 106, Through) or else
         At_Cell (P, 10848 + 352, 144, 107, Through) then 3
      elsif At_Cell (P, 32 + 320, 128, 107, Through) or else
         At_Cell (P, 10848 + 352, 144, 108, Through) then 2
      else Old_Byte)
   with Ghost, Global => null;

   function Restore_Coverage_Byte
     (Old_Byte : Digest_Byte; P : Frame_Index; Through : Coverage_Prefix)
      return Digest_Byte is
     (if P in 313 .. Through then 2 else Old_Byte)
   with Ghost, Global => null;

   function Restore_Fixed_Byte
     (Old_Byte : Digest_Byte; P : Frame_Index) return Digest_Byte is
     (case P is
        when 313 | 314 | 319 | 323 => 4,
        when (10848 + 249) | (10848 + 250) | (10848 + 258) |
          (10848 + 297) | (10848 + 298) | (10848 + 306) => 1,
        when (10848 + 259) | (10848 + 307) => 6,
        when others => Old_Byte)
   with Ghost, Global => null;

   function Restore_Before_Active_Byte
     (Old_Byte : Digest_Byte; P : Frame_Index; Through : Active_Prefix;
      Kinds : Fixture_Kinds) return Digest_Byte is
     (if At_Cell (P, 32 + 320, 128, 1, Through) or else
         At_Cell (P, 32 + 320, 128, 33, Through) or else
         At_Cell (P, 32 + 320, 128, 104, Through)
      then Digest_Byte (Cell_Order (P, 32 + 320, 128))
      elsif At_Cell (P, 32 + 320, 128, 105, Through)
      then Kind_Byte (Cell_Order (P, 32 + 320, 128), Kinds)
      elsif At_Cell (P, 32 + 320, 128, 106, Through) or else
         At_Cell (P, 32 + 320, 128, 107, Through) then 0
      else Old_Byte)
   with Ghost, Global => null;

   function Restore_Current_Active_Byte
     (Old_Byte : Digest_Byte; P : Frame_Index; Through : Active_Prefix;
      Kinds : Fixture_Kinds) return Digest_Byte is
     (if At_Cell (P, 10848 + 352, 144, 1, Through) then 2
      elsif At_Cell (P, 10848 + 352, 144, 2, Through) or else
         At_Cell (P, 10848 + 352, 144, 34, Through) or else
         At_Cell (P, 10848 + 352, 144, 105, Through)
      then Digest_Byte (Cell_Order (P, 10848 + 352, 144))
      elsif At_Cell (P, 10848 + 352, 144, 106, Through)
      then Kind_Byte (Cell_Order (P, 10848 + 352, 144), Kinds)
      elsif At_Cell (P, 10848 + 352, 144, 107, Through) or else
         At_Cell (P, 10848 + 352, 144, 108, Through) then 0
      else Old_Byte)
   with Ghost, Global => null;

   function Restore_Active_Written
     (P : Frame_Index; Through : Active_Prefix) return Boolean is
     (At_Cell (P, 32 + 320, 128, 1, Through) or else
      At_Cell (P, 32 + 320, 128, 33, Through) or else
      At_Cell (P, 32 + 320, 128, 104, Through) or else
      At_Cell (P, 32 + 320, 128, 105, Through) or else
      At_Cell (P, 32 + 320, 128, 106, Through) or else
      At_Cell (P, 32 + 320, 128, 107, Through) or else
      At_Cell (P, 10848 + 352, 144, 1, Through) or else
      At_Cell (P, 10848 + 352, 144, 2, Through) or else
      At_Cell (P, 10848 + 352, 144, 34, Through) or else
      At_Cell (P, 10848 + 352, 144, 105, Through) or else
      At_Cell (P, 10848 + 352, 144, 106, Through) or else
      At_Cell (P, 10848 + 352, 144, 107, Through) or else
      At_Cell (P, 10848 + 352, 144, 108, Through))
   with Ghost, Global => null;

   function Restore_Active_Byte
     (Old_Byte : Digest_Byte; P : Frame_Index; Through : Active_Prefix;
      Kinds : Fixture_Kinds) return Digest_Byte is
     (Restore_Current_Active_Byte
       (Restore_Before_Active_Byte (Old_Byte, P, Through, Kinds),
        P, Through, Kinds))
   with Ghost, Global => null;

   function Transition_Canonical_Written
     (P : Frame_Index; Through : Claim_Prefix) return Boolean is
     (At_Cell (P, 32 + 320, 128, 106, Through) or else
      At_Cell (P, 32 + 320, 128, 107, Through) or else
      At_Cell (P, 10848 + 320, 128, 106, Through) or else
      At_Cell (P, 10848 + 320, 128, 107, Through))
   with Ghost, Global => null;

   function Transition_Canonical_Byte
     (Old_Byte : Digest_Byte; P : Frame_Index; Through : Claim_Prefix)
      return Digest_Byte is
     (if At_Cell (P, 32 + 320, 128, 106, Through) or else
         At_Cell (P, 10848 + 320, 128, 106, Through) then 3
      elsif At_Cell (P, 32 + 320, 128, 107, Through) or else
         At_Cell (P, 10848 + 320, 128, 107, Through) then 2
      else Old_Byte)
   with Ghost, Global => null;

   function Restore_Expected_Byte (P : Frame_Index) return Digest_Byte is
     (Restore_Active_Byte
       (Restore_Fixed_Byte
         (Restore_Coverage_Byte
           (Restore_Canonical_Byte
             (Restore_Initial_Byte (P), P, Claim_Index'Last), P, 325), P),
        P, 4, Expected_Kinds))
   with Ghost, Global => null;

   function Transition_Expected_Byte (P : Frame_Index) return Digest_Byte is
     (Transition_Canonical_Byte
       (Transition_Initial_Byte (P), P, Claim_Index'Last))
   with Ghost, Global => null;

   procedure Set_Restore_Canonical (Bytes : in out Frame_Bytes)
   with Global => null, Always_Terminates, Depends => (Bytes => Bytes),
     Post => (for all P in Frame_Index =>
       Bytes (P) = Restore_Canonical_Byte
         (Bytes'Old (P), P, Claim_Index'Last))
   is
   begin
      for I in Claim_Index loop
         Bytes := (Bytes with delta
           ((32 + 320 + (I - 1) * 128) + 106) => 3,
           ((32 + 320 + (I - 1) * 128) + 107) => 2,
           ((10848 + 352 + (I - 1) * 144) + 107) => 3,
           ((10848 + 352 + (I - 1) * 144) + 108) => 2);
         pragma Assert
           (for all P in Frame_Index =>
             (if not Restore_Canonical_Written (P, I)
              then Bytes (P) = Bytes'Loop_Entry (P)));
         pragma Loop_Invariant
           (for all P in Frame_Index =>
             Bytes (P) = Restore_Canonical_Byte (Bytes'Loop_Entry (P), P, I));
      end loop;
   end Set_Restore_Canonical;

   procedure Set_Restore_Coverage (Bytes : in out Frame_Bytes)
   with Global => null, Always_Terminates, Depends => (Bytes => Bytes),
     Post => (for all P in Frame_Index =>
       Bytes (P) = Restore_Coverage_Byte (Bytes'Old (P), P, 325))
   is
   begin
      for I in 313 .. 325 loop
         Bytes := (Bytes with delta I => 2);
         pragma Assert
           (for all P in Frame_Index =>
             (if P not in 313 .. I
              then Bytes (P) = Bytes'Loop_Entry (P)));
         pragma Loop_Invariant
           (for all P in Frame_Index =>
             Bytes (P) = Restore_Coverage_Byte (Bytes'Loop_Entry (P), P, I));
      end loop;
   end Set_Restore_Coverage;

   procedure Set_Restore_Fixed (Bytes : in out Frame_Bytes)
   with Global => null, Always_Terminates, Depends => (Bytes => Bytes),
     Post => (for all P in Frame_Index =>
       Bytes (P) = Restore_Fixed_Byte (Bytes'Old (P), P))
   is
   begin
      Bytes := (Bytes with delta 313 | 314 | 319 | 323 => 4,
        (10848 + 249) | (10848 + 250) | (10848 + 258) => 1,
        (10848 + 297) | (10848 + 298) | (10848 + 306) => 1,
        (10848 + 259) | (10848 + 307) => 6);
   end Set_Restore_Fixed;

   procedure Set_Restore_Active
     (Bytes : in out Frame_Bytes; Kinds : Fixture_Kinds)
   with Global => null, Always_Terminates,
     Depends => (Bytes => (Bytes, Kinds)),
     Post => (for all P in Frame_Index =>
       Bytes (P) = Restore_Active_Byte (Bytes'Old (P), P, 4, Kinds))
   is
   begin
      for I in 1 .. 4 loop
         Bytes := (Bytes with delta
           ((32 + 320 + (I - 1) * 128) + 1) => Digest_Byte (I),
           ((32 + 320 + (I - 1) * 128) + 33) => Digest_Byte (I),
           ((32 + 320 + (I - 1) * 128) + 104) => Digest_Byte (I),
           ((32 + 320 + (I - 1) * 128) + 105) => Kinds (I),
           ((32 + 320 + (I - 1) * 128) + 106) => 0,
           ((32 + 320 + (I - 1) * 128) + 107) => 0,
           ((10848 + 352 + (I - 1) * 144) + 1) => 2,
           ((10848 + 352 + (I - 1) * 144) + 2) => Digest_Byte (I),
           ((10848 + 352 + (I - 1) * 144) + 34) => Digest_Byte (I),
           ((10848 + 352 + (I - 1) * 144) + 105) => Digest_Byte (I),
           ((10848 + 352 + (I - 1) * 144) + 106) => Kinds (I),
           ((10848 + 352 + (I - 1) * 144) + 107) => 0,
           ((10848 + 352 + (I - 1) * 144) + 108) => 0);
         pragma Assert
           (for all P in Frame_Index =>
             (if not Restore_Active_Written (P, I)
              then Bytes (P) = Bytes'Loop_Entry (P)));
         pragma Loop_Invariant
           (for all P in Frame_Index =>
             Bytes (P) = Restore_Active_Byte
               (Bytes'Loop_Entry (P), P, I, Kinds));
      end loop;
   end Set_Restore_Active;

   procedure Set_Transition_Canonical (Bytes : in out Frame_Bytes)
   with Global => null, Always_Terminates, Depends => (Bytes => Bytes),
     Post => (for all P in Frame_Index =>
       Bytes (P) = Transition_Canonical_Byte
         (Bytes'Old (P), P, Claim_Index'Last))
   is
   begin
      for I in Claim_Index loop
         Bytes := (Bytes with delta
           ((32 + 320 + (I - 1) * 128) + 106) => 3,
           ((32 + 320 + (I - 1) * 128) + 107) => 2,
           ((10848 + 320 + (I - 1) * 128) + 106) => 3,
           ((10848 + 320 + (I - 1) * 128) + 107) => 2);
         pragma Assert
           (for all P in Frame_Index =>
             (if not Transition_Canonical_Written (P, I)
              then Bytes (P) = Bytes'Loop_Entry (P)));
         pragma Loop_Invariant
           (for all P in Frame_Index =>
             Bytes (P) = Transition_Canonical_Byte
               (Bytes'Loop_Entry (P), P, I));
      end loop;
   end Set_Transition_Canonical;

   function Ready_Restore return Frame_Bytes
   with Global => null,
     Post => (for all P in Frame_Index =>
       Ready_Restore'Result (P) = Restore_Expected_Byte (P))
       and then Restore_Valid (Ready_Restore'Result)
   is
      Bytes : Frame_Bytes :=
        [1 => 83, 2 => 73, 3 => 65, 4 => 67, 5 | 6 => 1, 7 => 89, 8 => 192,
         33 | 10849 => 1, 65 | 10881 => 2, 97 | 10913 => 3,
         193 | 11009 => 6, 296 | 11080 => 1, 304 | 11088 | 326 => 4,
         others => 0];
      Kinds : constant array (Positive range 1 .. 4) of Digest_Byte :=
        [0, 1, 6, 10];
   begin
      --  Explicit wire offsets, independent of production payload helpers.
      Set_Restore_Canonical (Bytes);
      Set_Restore_Coverage (Bytes);
      Set_Restore_Fixed (Bytes);
      Set_Restore_Active (Bytes, Fixture_Kinds (Kinds));
      return Bytes;
   end Ready_Restore;

   function Ready_Transition return Frame_Bytes
   with Global => null,
     Post => (for all P in Frame_Index =>
       Ready_Transition'Result (P) = Transition_Expected_Byte (P))
   is
      Bytes : Frame_Bytes :=
        [1 => 83, 2 => 73, 3 => 65, 4 => 67, 5 => 1, 6 => 2, 7 => 112, 8 => 160,
         33 | 10849 => 1, 65 | 10881 => 2, 97 | 10913 => 3,
         193 | (10848 + 193) => 6, 11009 => 7, 296 => 1,
         (10848 + 264) => 2,
         22098 | 22546 | 22994 | 23442 | 23890 | 24338 | 24786 | 25234 |
         25682 | 26130 | 26578 | 27026 | 27474 | 27922 | 28370 | 28818 => 1,
         others => 0];
   begin
      Set_Transition_Canonical (Bytes);
      return Bytes;
   end Ready_Transition;

   procedure Check_Policy_Paths with Global => null, Always_Terminates is
      procedure Check_Original_Restore (Restore_Bytes : Frame_Bytes)
      with Global => null, Always_Terminates,
        Pre => (for all P in Frame_Index =>
          Restore_Bytes (P) = Restore_Expected_Byte (P))
          and then Restore_Valid (Restore_Bytes)
      is
         Accepted : Boolean;
         Item : Decoded_Request;
         Result : Frame_Decision;
      begin
         pragma Assert (Restore_Bytes (33) = 1);
         pragma Assert (Restore_Bytes (65) = 2);
         pragma Assert (Restore_Bytes (97) = 3);
         pragma Assert (Restore_Bytes (193) = 6);
         Evaluate (Restore_Bytes, Accepted, Item, Result);
         pragma Assert (Item.Kind = Restore_Request);
         pragma Assert (Item.Before.Scope.Task_Id (1) = 1);
         pragma Assert (Item.Before.Scope.Session_Id (1) = 2);
         pragma Assert (Item.Before.Scope.Repository (1) = 3);
         pragma Assert (Item.Before.Identity (1) = 6);
         pragma Assert (SIA_Continuity.Valid (Item.Before));
         pragma Assert (Accepted and then Result.Restore_Value = References_Proposed);
      end Check_Original_Restore;

      procedure Check_Revised_Restore (Restore_Bytes : Frame_Bytes)
      with Global => null, Always_Terminates,
        Pre => (for all P in Frame_Index =>
          Restore_Bytes (P) = Restore_Expected_Byte (P))
          and then Restore_Valid (Restore_Bytes)
      is
         Accepted : Boolean;
         Item : Decoded_Request;
         Result : Frame_Decision;
      begin
         Evaluate ((Restore_Bytes with delta 10945 => 9), Accepted, Item, Result);
         pragma Assert (Accepted and then Result.Restore_Value = Reconcile_Repository);
      end Check_Revised_Restore;

      procedure Check_Restore_Policy_Paths with Global => null, Always_Terminates is
         Restore_Bytes : constant Frame_Bytes := Ready_Restore;
      begin
         Check_Original_Restore (Restore_Bytes);
         Check_Revised_Restore (Restore_Bytes);
      end Check_Restore_Policy_Paths;

      procedure Check_Transition_Policy_Paths with Global => null, Always_Terminates is
         Accepted : Boolean;
         Item : Decoded_Request;
         Result : Frame_Decision;
         Transition_Bytes : constant Frame_Bytes := Ready_Transition;
      begin
         Evaluate (Transition_Bytes, Accepted, Item, Result);
         pragma Assert (Accepted and then Result.Transition_Value = Transition_Proposed);
         Evaluate ((Transition_Bytes with delta 10881 => 9), Accepted, Item, Result);
         pragma Assert (Accepted and then Result.Transition_Value = Task_Mismatch);
      end Check_Transition_Policy_Paths;
   begin
      Check_Restore_Policy_Paths;
      Check_Transition_Policy_Paths;
   end Check_Policy_Paths;

   procedure Check_Header with Global => null, Always_Terminates is
   begin
      Refuse ([others => 0]);
      for I in 1 .. 8 loop
         for Code in Digest_Byte loop
            if Code /= Restore_Vector (I) then
               Refuse ((Restore_Vector with delta I => Code));
            end if;
            if Code /= Transition_Vector (I) then
               Refuse ((Transition_Vector with delta I => Code));
            end if;
         end loop;
      end loop;
      --  A known operation with the other operation's canonical length refuses.
      Refuse ((Restore_Vector with delta 7 => 112, 8 => 160));
      Refuse ((Transition_Vector with delta 7 => 89, 8 => 192));
   end Check_Header;

   procedure Check_Padding with Global => null, Always_Terminates is
   begin
      for I in 9 .. 32 loop
         Refuse ((Restore_Vector with delta I => 1));
         Refuse ((Transition_Vector with delta I => 1));
      end loop;
      for I in 22977 .. Frame_Bytes'Last loop
         Refuse ((Restore_Vector with delta I => 1));
      end loop;
      for I in 28833 .. Frame_Bytes'Last loop
         Refuse ((Transition_Vector with delta I => 1));
      end loop;
   end Check_Padding;

   procedure Check_Nested_Claims with Global => null, Always_Terminates is
   begin
      for I in Claim_Index loop
         --  Inactive checkpoint claims and unavailable current observations.
         Refuse ((Restore_Vector with delta
           ((32 + 320 + (I - 1) * 128) + 105) => 255));
         Refuse ((Transition_Vector with delta
           ((10848 + 320 + (I - 1) * 128) + 105) => 255));
         Refuse ((Restore_Vector with delta
           ((10848 + 352 + (I - 1) * 144) + 106) => 255));
      end loop;
   end Check_Nested_Claims;

   procedure Check_Nested_Operations with Global => null, Always_Terminates is
   begin
      for I in Operation_Index loop
         Refuse ((Restore_Vector with delta
           ((32 + 8512 + (I - 1) * 144) + 130) => 2));
         Refuse ((Transition_Vector with delta
           ((10848 + 8512 + (I - 1) * 144) + 130) => 2));
         Refuse ((Restore_Vector with delta
           ((10848 + 9568 + (I - 1) * 160) + 131) => 2));
         Refuse ((Transition_Vector with delta
           ((21664 + (I - 1) * 448) + 434) => 0));
         Refuse ((Transition_Vector with delta
           ((21664 + (I - 1) * 448) + 274) => 2));
         for J in 436 .. 448 loop
            Refuse ((Transition_Vector with delta
              ((21664 + (I - 1) * 448) + J) => 1));
         end loop;
      end loop;
   end Check_Nested_Operations;

   procedure Check_Nested_Headers with Global => null, Always_Terminates is
   begin
      Refuse ((Restore_Vector with delta 289 => 128));
      Refuse ((Transition_Vector with delta 289 => 128));
      Refuse ((Transition_Vector with delta (10848 + 257) => 128));
      Refuse ((Restore_Vector with delta (10848 + 225) => 128));
      Refuse ((Restore_Vector with delta 11097 => 2));
      for I in 296 .. 320 loop
         Refuse ((Restore_Vector with delta (32 + I) => 1));
         Refuse ((Transition_Vector with delta (10848 + I) => 1));
      end loop;
      for I in 345 .. 352 loop
         Refuse ((Restore_Vector with delta (10848 + I) => 1));
      end loop;
   end Check_Nested_Headers;
begin
   Check_Restore;
   Check_Transition;
   Check_Policy_Paths;
   Check_Header;
   Check_Padding;
   Check_Nested_Claims;
   Check_Nested_Operations;
   Check_Nested_Headers;
end Continuity_Frame_Wire_Tests;
