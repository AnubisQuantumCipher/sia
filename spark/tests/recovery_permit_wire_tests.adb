with SIA_Policy;
with SIA_Recovery_Records;

--  Representation harness only. No signature verifier or provider is invoked.
procedure Recovery_Permit_Wire_Tests with SPARK_Mode is
   use SIA_Policy;
   use SIA_Recovery_Records;

   function Frozen_Operation_Decoded_As
     (Bytes : Permit_Bytes; Item : Operation_Fields) return Boolean is
     (Permit_Scalars_Valid (Bytes) and then
      (Item.Fixture = Permit_Digest (Bytes, 80) and
      Item.Transaction = Permit_Digest (Bytes, 112) and
      Item.Protocol = Permit_Digest (Bytes, 144) and
      Item.Publication_Issuer = Permit_Digest (Bytes, 176) and
      Item.Publication_Key = Permit_Digest (Bytes, 208) and
      Item.Publication_Clock = Permit_Digest (Bytes, 240) and
      Item.Publication_Boot = Permit_Digest (Bytes, 272) and
      Item.Publication_Service = Permit_Digest (Bytes, 304) and
      Item.Publication_Capability = Permit_Digest (Bytes, 336) and
      Item.Predecessor_Receipt = Permit_Digest (Bytes, 368) and
      Item.Payload_Digest = Permit_Digest (Bytes, 400) and
      Item.Publication_Subject_UID = Word_Value (Permit_Word (Bytes, 432)) and
      Item.Before_Generation = Word_Value (Permit_Word (Bytes, 440)) and
      Item.Target_Generation = Word_Value (Permit_Word (Bytes, 448)) and
      Generation (Item.Logical_Payload_Length) =
        Word_Value (Permit_Word (Bytes, 456))))
   with Ghost, Global => null;

   --  No precondition: both predicates must agree for every typed input.
   --  This obligation is UNPROVEN until the original qualified proof runs.
   procedure Check_Operation_Relation_Equivalence
     (Bytes : Permit_Bytes; Item : Operation_Fields)
   with Ghost, Global => null, Always_Terminates,
     Post => Operation_Decoded_As (Bytes, Item) =
       Frozen_Operation_Decoded_As (Bytes, Item)
   is
   begin
      null;
   end Check_Operation_Relation_Equivalence;

   function Filled (Value : Digest_Byte) return Digest is ([others => Value])
   with Global => null;

   --  Literal schema oracle: no encoder, reader or Check function constructs it.
   Canonical_Permit : constant Permit_Bytes :=
     [1 => 83, 2 => 73, 3 => 65, 4 => 82, 5 => 69, 6 => 67, 7 => 48, 8 => 49,
      9 => 1, 10 => 1, 15 => 3, 16 => 72,
      17 .. 48 => 1, 49 .. 80 => 2, 81 .. 112 => 3, 113 .. 144 => 4,
      145 .. 176 => 5, 177 .. 208 => 6, 209 .. 240 => 7, 241 .. 272 => 8,
      273 .. 304 => 9, 305 .. 336 => 10, 337 .. 368 => 11,
      440 => 1, 456 => 1, 529 .. 560 => 12, 561 .. 592 => 13,
      593 .. 624 => 14, 625 => 1, 633 .. 664 => 15, 665 .. 696 => 16,
      697 => 1, 705 .. 736 => 17, 737 .. 768 => 18, 769 => 1, others => 0];
   Expected_Operation : constant Operation_Fields :=
     (Fixture => Filled (3), Transaction => Filled (4), Protocol => Filled (5),
      Publication_Issuer => Filled (6), Publication_Key => Filled (7),
      Publication_Clock => Filled (8), Publication_Boot => Filled (9),
      Publication_Service => Filled (10), Publication_Capability => Filled (11),
      Predecessor_Receipt | Payload_Digest => Zero_Digest,
      Publication_Subject_UID => 1, Before_Generation => 0,
      Target_Generation => 1, Logical_Payload_Length => 0);
   Expected_Permit : constant Permit_Record :=
     (Content =>
       (Issuer => Filled (1), Key => Filled (2), Operation => Expected_Operation,
        Historical_Publish_Digest | Predecessor_State_Digest => Zero_Digest,
        Recovery_Policy => Filled (12),
        Intent_Signer => (Filled (13), Filled (14), 1),
        Receipt_Signer => (Filled (15), Filled (16), 1),
        State_Signer => (Filled (17), Filled (18), 1)),
      Signature => [others => 0]);
   Canonical_Control : constant Control_Bytes :=
     [1 => 83, 2 => 73, 3 => 65, 4 => 82, 5 => 69, 6 => 67, 7 => 48, 8 => 49,
      9 => 2, 10 => 1, 15 => 1, 16 => 96,
      17 .. 48 => 1, 49 .. 80 => 2, 81 .. 112 => 3, 145 .. 176 => 12,
      177 .. 208 => 19, 209 .. 240 => 20, 241 .. 272 => 21, others => 0];
   Expected_Control : constant Control_Record :=
     (Bindings => (Issuer => Filled (1), Key => Filled (2), Fixture => Filled (3),
       Permit_Signed_Digest => Zero_Digest, Recovery_Policy => Filled (12),
       Control_Policy => Filled (19), Provider_Id => Filled (20),
       Anchor_Namespace => Filled (21)),
      Epoch => 0, State => Enabled, Signature => [others => 0]);

   type Permit_Identity is
     (Issuer_Id, Key_Id, Fixture_Id, Transaction_Id, Protocol_Id,
      Publication_Issuer_Id, Publication_Key_Id, Clock_Id, Boot_Id, Service_Id,
      Capability_Id, Recovery_Policy_Id, Intent_Issuer_Id, Intent_Key_Id,
      Receipt_Issuer_Id, Receipt_Key_Id, State_Issuer_Id, State_Key_Id);
   Permit_Identity_Offsets : constant array (Permit_Identity) of Natural :=
     [Issuer_Id => 16, Key_Id => 48, Fixture_Id => 80,
      Transaction_Id => 112, Protocol_Id => 144,
      Publication_Issuer_Id => 176, Publication_Key_Id => 208,
      Clock_Id => 240, Boot_Id => 272, Service_Id => 304,
      Capability_Id => 336, Recovery_Policy_Id => 528,
      Intent_Issuer_Id => 560, Intent_Key_Id => 592,
      Receipt_Issuer_Id => 632, Receipt_Key_Id => 664,
      State_Issuer_Id => 704, State_Key_Id => 736];
   type Control_Identity is
     (Control_Issuer_Id, Control_Key_Id, Control_Fixture_Id,
      Control_Recovery_Id, Control_Policy_Id, Provider_Id_Field, Namespace_Id);
   Control_Identity_Offsets : constant array (Control_Identity) of Natural :=
     [Control_Issuer_Id => 16, Control_Key_Id => 48,
      Control_Fixture_Id => 80, Control_Recovery_Id => 144,
      Control_Policy_Id => 176, Provider_Id_Field => 208,
      Namespace_Id => 240];
   Role_Profile_Positions : constant array (Positive range 1 .. 3) of Positive :=
     [625, 697, 769];

   procedure Lemma_Generation_UID_Class (Value : Generation; Data : Word)
   with Ghost, Global => null, Always_Terminates,
     Pre => Data = Generation_Bytes (Value),
     Post => Data (1) <= 127 and then Word_Value (Data) = Value and then
       ((for all I in 1 .. 4 => Data (I) = 0) = (Value <= Subject_UID'Last))
   is
   begin
      pragma Assert (Data (1) <= 127);
      pragma Assert (Word_Value (Data) = Value);
      pragma Assert
        (if Value <= Subject_UID'Last then (for all I in 1 .. 4 => Data (I) = 0));
      pragma Assert
        (if (for all I in 1 .. 4 => Data (I) = 0) then
           Word_Value (Data) <= Subject_UID'Last);
   end Lemma_Generation_UID_Class;

   procedure Put_Word
     (Bytes : in out Permit_Bytes; Offset : Natural; Value : Generation)
   with Global => null, Always_Terminates,
     Depends => (Bytes => (Bytes, Offset, Value)),
     Pre => Offset <= Permit_Bytes'Length - Word'Length,
     Post => Permit_Word (Bytes, Offset) = Generation_Bytes (Value) and then
       (for all J in Permit_Bytes'Range =>
         (if J not in Offset + 1 .. Offset + 8 then Bytes (J) = Bytes'Old (J))) and then
       Permit_Word (Bytes, Offset) (1) <= 127 and then
       Word_Value (Permit_Word (Bytes, Offset)) = Value and then
       ((for all I in 1 .. 4 => Permit_Word (Bytes, Offset) (I) = 0) =
         (Value <= Subject_UID'Last))
   is
      Data : constant Word := Generation_Bytes (Value);
   begin
      Lemma_Generation_UID_Class (Value, Data);
      for I in Word'Range loop
         Bytes (Offset + I) := Data (I);
         pragma Loop_Invariant
           (for all J in 1 .. I => Bytes (Offset + J) = Data (J));
         pragma Loop_Invariant
           (for all J in Permit_Bytes'Range =>
             (if J not in Offset + 1 .. Offset + I then
                Bytes (J) = Bytes'Loop_Entry (J)));
         pragma Loop_Variant (Decreases => Word'Last - I);
      end loop;
   end Put_Word;

   --  These ghost lemmas are obligations, not assumptions. They require proof
   --  over the full guarded domains before any caller success is accepted.
   procedure Lemma_Append_Byte (Prefix : Generation; Digit : Digest_Byte)
   with Ghost, Global => null, Always_Terminates,
     Pre => Prefix <= Generation'Last / 256,
     Post => (Prefix * 256 + Generation (Digit)) / 256 = Prefix and then
       (Prefix * 256 + Generation (Digit)) mod 256 = Generation (Digit)
   is
   begin
      null;
   end Lemma_Append_Byte;

   procedure Lemma_Word_Digits (Data : Word)
   with Ghost, Global => null, Always_Terminates,
     Pre => Data (1) <= 127,
     Post => Data = Generation_Bytes (Word_Value (Data))
   is
      P1 : constant Generation := Generation (Data (1));
      P2 : constant Generation := P1 * 256 + Generation (Data (2));
      P3 : constant Generation := P2 * 256 + Generation (Data (3));
      P4 : constant Generation := P3 * 256 + Generation (Data (4));
      P5 : constant Generation := P4 * 256 + Generation (Data (5));
      P6 : constant Generation := P5 * 256 + Generation (Data (6));
      P7 : constant Generation := P6 * 256 + Generation (Data (7));
      P8 : constant Generation := P7 * 256 + Generation (Data (8));
   begin
      Lemma_Append_Byte (P1, Data (2));
      Lemma_Append_Byte (P2, Data (3));
      Lemma_Append_Byte (P3, Data (4));
      Lemma_Append_Byte (P4, Data (5));
      Lemma_Append_Byte (P5, Data (6));
      Lemma_Append_Byte (P6, Data (7));
      Lemma_Append_Byte (P7, Data (8));
      pragma Assert (P8 = Word_Value (Data));
      pragma Assert ((P8 / 2 ** 8) / 256 = P8 / 2 ** 16);
      pragma Assert ((P8 / 2 ** 16) / 256 = P8 / 2 ** 24);
      pragma Assert ((P8 / 2 ** 24) / 256 = P8 / 2 ** 32);
      pragma Assert ((P8 / 2 ** 32) / 256 = P8 / 2 ** 40);
      pragma Assert ((P8 / 2 ** 40) / 256 = P8 / 2 ** 48);
      pragma Assert ((P8 / 2 ** 48) / 256 = P8 / 2 ** 56);
      pragma Assert (Generation (Data (1)) = Word_Value (Data) / 2 ** 56);
      pragma Assert
        (Generation (Data (2)) = (Word_Value (Data) / 2 ** 48) mod 256);
      pragma Assert
        (Generation (Data (3)) = (Word_Value (Data) / 2 ** 40) mod 256);
      pragma Assert
        (Generation (Data (4)) = (Word_Value (Data) / 2 ** 32) mod 256);
      pragma Assert
        (Generation (Data (5)) = (Word_Value (Data) / 2 ** 24) mod 256);
      pragma Assert
        (Generation (Data (6)) = (Word_Value (Data) / 2 ** 16) mod 256);
      pragma Assert
        (Generation (Data (7)) = (Word_Value (Data) / 2 ** 8) mod 256);
      pragma Assert (Generation (Data (8)) = Word_Value (Data) mod 256);
      declare
         Reencoded : constant Word := Generation_Bytes (Word_Value (Data));
      begin
         pragma Assert (Reencoded (1) = Data (1));
         for I in Word'Range loop
            pragma Assert (Reencoded (I) = Data (I));
            pragma Loop_Invariant
              (for all J in Word'First .. I => Reencoded (J) = Data (J));
            pragma Loop_Variant (Decreases => Word'Last - I);
         end loop;
         pragma Assert (Reencoded = Data);
      end;
   end Lemma_Word_Digits;

   procedure Lemma_Word_Unique (Left, Right : Word)
   with Ghost, Global => null, Always_Terminates,
     Pre => Left (1) <= 127 and then Right (1) <= 127 and then
       Word_Value (Left) = Word_Value (Right),
     Post => Left = Right
   is
   begin
      Lemma_Word_Digits (Left);
      Lemma_Word_Digits (Right);
   end Lemma_Word_Unique;

   procedure Lemma_Permit_Envelope_Unique (Left, Right : Permit_Bytes)
   with Ghost, Global => null, Always_Terminates,
     Pre => Permit_Envelope_Valid (Left) and then Permit_Envelope_Valid (Right),
     Post => (for all I in 1 .. 16 => Left (I) = Right (I))
   is
      L : constant Word := [1 .. 4 => 0, 5 => Left (13), 6 => Left (14),
                            7 => Left (15), 8 => Left (16)];
      R : constant Word := [1 .. 4 => 0, 5 => Right (13), 6 => Right (14),
                            7 => Right (15), 8 => Right (16)];
   begin
      pragma Assert (for all I in 1 .. 12 => Left (I) = Right (I));
      pragma Assert (Word_Value (L) = Permit_Bytes'Length);
      pragma Assert (Word_Value (R) = Permit_Bytes'Length);
      Lemma_Word_Unique (L, R);
   end Lemma_Permit_Envelope_Unique;

   procedure Lemma_Control_Envelope_Unique (Left, Right : Control_Bytes)
   with Ghost, Global => null, Always_Terminates,
     Pre => Control_Envelope_Valid (Left) and then Control_Envelope_Valid (Right),
     Post => (for all I in 1 .. 16 => Left (I) = Right (I))
   is
      L : constant Word := [1 .. 4 => 0, 5 => Left (13), 6 => Left (14),
                            7 => Left (15), 8 => Left (16)];
      R : constant Word := [1 .. 4 => 0, 5 => Right (13), 6 => Right (14),
                            7 => Right (15), 8 => Right (16)];
   begin
      pragma Assert (for all I in 1 .. 12 => Left (I) = Right (I));
      pragma Assert (Word_Value (L) = Control_Bytes'Length);
      pragma Assert (Word_Value (R) = Control_Bytes'Length);
      Lemma_Word_Unique (L, R);
   end Lemma_Control_Envelope_Unique;

   procedure Lemma_Permit_Digest_Region
     (Left, Right : Permit_Bytes; Offset : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset <= Permit_Bytes'Length - Digest'Length and then
       Permit_Digest (Left, Offset) = Permit_Digest (Right, Offset),
     Post => (for all I in Digest'Range => Left (Offset + I) = Right (Offset + I))
   is
   begin
      null;
   end Lemma_Permit_Digest_Region;

   procedure Lemma_Control_Digest_Region
     (Left, Right : Control_Bytes; Offset : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset <= Control_Bytes'Length - Digest'Length and then
       Control_Digest (Left, Offset) = Control_Digest (Right, Offset),
     Post => (for all I in Digest'Range => Left (Offset + I) = Right (Offset + I))
   is
   begin
      null;
   end Lemma_Control_Digest_Region;

   procedure Lemma_Permit_Word_Region
     (Left, Right : Permit_Bytes; Offset : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset <= Permit_Bytes'Length - Word'Length and then
       Permit_Word (Left, Offset) = Permit_Word (Right, Offset),
     Post => (for all I in Word'Range => Left (Offset + I) = Right (Offset + I))
   is
   begin
      null;
   end Lemma_Permit_Word_Region;

   procedure Lemma_Control_Word_Region
     (Left, Right : Control_Bytes; Offset : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset <= Control_Bytes'Length - Word'Length and then
       Control_Word (Left, Offset) = Control_Word (Right, Offset),
     Post => (for all I in Word'Range => Left (Offset + I) = Right (Offset + I))
   is
   begin
      null;
   end Lemma_Control_Word_Region;

   procedure Lemma_Permit_Scalars_Unique
     (Left, Right : Permit_Bytes; Item : Operation_Fields)
   with Ghost, Global => null, Always_Terminates,
     Pre => Operation_Decoded_As (Left, Item) and then
       Operation_Decoded_As (Right, Item),
     Post => (for all I in 433 .. 464 => Left (I) = Right (I))
   is
   begin
      Lemma_Word_Unique (Permit_Word (Left, 432), Permit_Word (Right, 432));
      Lemma_Permit_Word_Region (Left, Right, 432);
      Lemma_Word_Unique (Permit_Word (Left, 440), Permit_Word (Right, 440));
      Lemma_Permit_Word_Region (Left, Right, 440);
      Lemma_Word_Unique (Permit_Word (Left, 448), Permit_Word (Right, 448));
      Lemma_Permit_Word_Region (Left, Right, 448);
      Lemma_Word_Unique (Permit_Word (Left, 456), Permit_Word (Right, 456));
      Lemma_Permit_Word_Region (Left, Right, 456);
   end Lemma_Permit_Scalars_Unique;

   procedure Lemma_Role_Byte
     (Left, Right : Permit_Bytes; Offset : Natural; I : Positive)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset in 560 | 632 | 704 and then I in Word'Range and then
       Permit_Role_Valid (Left, Offset) and then Permit_Role_Valid (Right, Offset),
     Post => Left ((Offset + 64) + I) = Right ((Offset + 64) + I)
   is
   begin
      if I = 1 then
         pragma Assert (Left ((Offset + 64) + I) = 1 and
           Right ((Offset + 64) + I) = 1);
      else
         pragma Assert (Left ((Offset + 64) + I) = 0 and
           Right ((Offset + 64) + I) = 0);
      end if;
   end Lemma_Role_Byte;

   procedure Lemma_Permit_Role_Padding (Left, Right : Permit_Bytes)
   with Ghost, Global => null, Always_Terminates,
     Pre => Permit_Fields_Valid (Left) and then Permit_Fields_Valid (Right),
     Post => (for all I in 625 .. 632 => Left (I) = Right (I)) and then
       (for all I in 697 .. 704 => Left (I) = Right (I)) and then
       (for all I in 769 .. 776 => Left (I) = Right (I))
   is
   begin
      for K in 625 .. 632 loop
         Lemma_Role_Byte (Left, Right, 560, K - 624);
         pragma Assert (624 + (K - 624) = K);
         pragma Assert (Left (K) = Right (K));
         pragma Loop_Invariant
           (for all J in 625 .. K => Left (J) = Right (J));
         pragma Loop_Variant (Decreases => 632 - K);
      end loop;
      for K in 697 .. 704 loop
         Lemma_Role_Byte (Left, Right, 632, K - 696);
         pragma Assert (696 + (K - 696) = K);
         pragma Assert (Left (K) = Right (K));
         pragma Loop_Invariant
           (for all J in 697 .. K => Left (J) = Right (J));
         pragma Loop_Variant (Decreases => 704 - K);
      end loop;
      for K in 769 .. 776 loop
         Lemma_Role_Byte (Left, Right, 704, K - 768);
         pragma Assert (768 + (K - 768) = K);
         pragma Assert (Left (K) = Right (K));
         pragma Loop_Invariant
           (for all J in 769 .. K => Left (J) = Right (J));
         pragma Loop_Variant (Decreases => 776 - K);
      end loop;
   end Lemma_Permit_Role_Padding;

   procedure Lemma_Permit_Signature_Region (Left, Right : Permit_Bytes)
   with Ghost, Global => null, Always_Terminates,
     Pre => Permit_Signature (Left) = Permit_Signature (Right),
     Post => (for all I in Signature_Bytes'Range =>
       Left (776 + I) = Right (776 + I))
   is
   begin
      null;
   end Lemma_Permit_Signature_Region;

   procedure Lemma_Control_Signature_Region (Left, Right : Control_Bytes)
   with Ghost, Global => null, Always_Terminates,
     Pre => Control_Signature (Left) = Control_Signature (Right),
     Post => (for all I in Signature_Bytes'Range =>
       Left (288 + I) = Right (288 + I))
   is
   begin
      null;
   end Lemma_Control_Signature_Region;

   procedure Lemma_Permit_Digest_At
     (Left, Right : Permit_Bytes; Offset : Natural; K : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset <= Permit_Bytes'Length - Digest'Length and then
       K in Offset + 1 .. Offset + Digest'Length and then
       Permit_Digest (Left, Offset) = Permit_Digest (Right, Offset),
     Post => Left (K) = Right (K)
   is
   begin
      pragma Assert (K - Offset in Digest'Range);
      pragma Assert (Permit_Digest (Left, Offset) (K - Offset) = Permit_Digest (Right, Offset) (K - Offset));
      pragma Assert (Offset + (K - Offset) = K);
   end Lemma_Permit_Digest_At;

   procedure Lemma_Permit_Signature_At
     (Left, Right : Permit_Bytes; K : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => K in 776 + 1 .. 776 + Signature_Bytes'Length and then
       Permit_Signature (Left) = Permit_Signature (Right),
     Post => Left (K) = Right (K)
   is
   begin
      pragma Assert (K - 776 in Signature_Bytes'Range);
      pragma Assert (Permit_Signature (Left) (K - 776) = Permit_Signature (Right) (K - 776));
      pragma Assert (776 + (K - 776) = K);
   end Lemma_Permit_Signature_At;

   procedure Lemma_Control_Digest_At
     (Left, Right : Control_Bytes; Offset : Natural; K : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset <= Control_Bytes'Length - Digest'Length and then
       K in Offset + 1 .. Offset + Digest'Length and then
       Control_Digest (Left, Offset) = Control_Digest (Right, Offset),
     Post => Left (K) = Right (K)
   is
   begin
      pragma Assert (K - Offset in Digest'Range);
      pragma Assert (Control_Digest (Left, Offset) (K - Offset) = Control_Digest (Right, Offset) (K - Offset));
      pragma Assert (Offset + (K - Offset) = K);
   end Lemma_Control_Digest_At;

   procedure Lemma_Control_Signature_At
     (Left, Right : Control_Bytes; K : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => K in 288 + 1 .. 288 + Signature_Bytes'Length and then
       Control_Signature (Left) = Control_Signature (Right),
     Post => Left (K) = Right (K)
   is
   begin
      pragma Assert (K - 288 in Signature_Bytes'Range);
      pragma Assert (Control_Signature (Left) (K - 288) = Control_Signature (Right) (K - 288));
      pragma Assert (288 + (K - 288) = K);
   end Lemma_Control_Signature_At;

   procedure Lemma_Permit_Digests_At
     (Left, Right : Permit_Bytes; Item : Permit_Record; K : Positive)
   with Ghost, Global => null, Always_Terminates,
     Pre => Permit_Decoded_As (Left, Item) and then Permit_Decoded_As (Right, Item)
       and then K in 17 .. 432 | 465 .. 624 | 633 .. 696 | 705 .. 768,
     Post => Left (K) = Right (K)
   is
   begin
      if K in 17 .. 48 then
         Lemma_Permit_Digest_At (Left, Right, 16, K);
      elsif K in 49 .. 80 then
         Lemma_Permit_Digest_At (Left, Right, 48, K);
      elsif K in 81 .. 112 then
         Lemma_Permit_Digest_At (Left, Right, 80, K);
      elsif K in 113 .. 144 then
         Lemma_Permit_Digest_At (Left, Right, 112, K);
      elsif K in 145 .. 176 then
         Lemma_Permit_Digest_At (Left, Right, 144, K);
      elsif K in 177 .. 208 then
         Lemma_Permit_Digest_At (Left, Right, 176, K);
      elsif K in 209 .. 240 then
         Lemma_Permit_Digest_At (Left, Right, 208, K);
      elsif K in 241 .. 272 then
         Lemma_Permit_Digest_At (Left, Right, 240, K);
      elsif K in 273 .. 304 then
         Lemma_Permit_Digest_At (Left, Right, 272, K);
      elsif K in 305 .. 336 then
         Lemma_Permit_Digest_At (Left, Right, 304, K);
      elsif K in 337 .. 368 then
         Lemma_Permit_Digest_At (Left, Right, 336, K);
      elsif K in 369 .. 400 then
         Lemma_Permit_Digest_At (Left, Right, 368, K);
      elsif K in 401 .. 432 then
         Lemma_Permit_Digest_At (Left, Right, 400, K);
      elsif K in 465 .. 496 then
         Lemma_Permit_Digest_At (Left, Right, 464, K);
      elsif K in 497 .. 528 then
         Lemma_Permit_Digest_At (Left, Right, 496, K);
      elsif K in 529 .. 560 then
         Lemma_Permit_Digest_At (Left, Right, 528, K);
      elsif K in 561 .. 592 then
         Lemma_Permit_Digest_At (Left, Right, 560, K);
      elsif K in 593 .. 624 then
         Lemma_Permit_Digest_At (Left, Right, 592, K);
      elsif K in 633 .. 664 then
         Lemma_Permit_Digest_At (Left, Right, 632, K);
      elsif K in 665 .. 696 then
         Lemma_Permit_Digest_At (Left, Right, 664, K);
      elsif K in 705 .. 736 then
         Lemma_Permit_Digest_At (Left, Right, 704, K);
      else
         Lemma_Permit_Digest_At (Left, Right, 736, K);
      end if;
   end Lemma_Permit_Digests_At;

   procedure Lemma_Control_Digests_At
     (Left, Right : Control_Bytes; Item : Control_Record; K : Positive)
   with Ghost, Global => null, Always_Terminates,
     Pre => Control_Decoded_As (Left, Item) and then Control_Decoded_As (Right, Item)
       and then K in 17 .. 272,
     Post => Left (K) = Right (K)
   is
   begin
      if K in 17 .. 48 then
         Lemma_Control_Digest_At (Left, Right, 16, K);
      elsif K in 49 .. 80 then
         Lemma_Control_Digest_At (Left, Right, 48, K);
      elsif K in 81 .. 112 then
         Lemma_Control_Digest_At (Left, Right, 80, K);
      elsif K in 113 .. 144 then
         Lemma_Control_Digest_At (Left, Right, 112, K);
      elsif K in 145 .. 176 then
         Lemma_Control_Digest_At (Left, Right, 144, K);
      elsif K in 177 .. 208 then
         Lemma_Control_Digest_At (Left, Right, 176, K);
      elsif K in 209 .. 240 then
         Lemma_Control_Digest_At (Left, Right, 208, K);
      else
         Lemma_Control_Digest_At (Left, Right, 240, K);
      end if;
   end Lemma_Control_Digests_At;

   procedure Lemma_Unique_Permit
     (Left, Right : Permit_Bytes; Item : Permit_Record)
   with Ghost, Global => null, Always_Terminates,
     Pre => Permit_Decoded_As (Left, Item) and then Permit_Decoded_As (Right, Item),
     Post => Left = Right
   is
   begin
      Lemma_Permit_Envelope_Unique (Left, Right);
      Lemma_Permit_Digest_Region (Left, Right, 16);
      Lemma_Permit_Digest_Region (Left, Right, 48);
      Lemma_Permit_Digest_Region (Left, Right, 80);
      Lemma_Permit_Digest_Region (Left, Right, 112);
      Lemma_Permit_Digest_Region (Left, Right, 144);
      Lemma_Permit_Digest_Region (Left, Right, 176);
      Lemma_Permit_Digest_Region (Left, Right, 208);
      Lemma_Permit_Digest_Region (Left, Right, 240);
      Lemma_Permit_Digest_Region (Left, Right, 272);
      Lemma_Permit_Digest_Region (Left, Right, 304);
      Lemma_Permit_Digest_Region (Left, Right, 336);
      Lemma_Permit_Digest_Region (Left, Right, 368);
      Lemma_Permit_Digest_Region (Left, Right, 400);
      Lemma_Permit_Scalars_Unique (Left, Right, Item.Content.Operation);
      Lemma_Permit_Digest_Region (Left, Right, 464);
      Lemma_Permit_Digest_Region (Left, Right, 496);
      Lemma_Permit_Digest_Region (Left, Right, 528);
      Lemma_Permit_Digest_Region (Left, Right, 560);
      Lemma_Permit_Digest_Region (Left, Right, 592);
      Lemma_Permit_Digest_Region (Left, Right, 632);
      Lemma_Permit_Digest_Region (Left, Right, 664);
      Lemma_Permit_Digest_Region (Left, Right, 704);
      Lemma_Permit_Digest_Region (Left, Right, 736);
      Lemma_Permit_Role_Padding (Left, Right);
      Lemma_Permit_Signature_Region (Left, Right);
      for I in Permit_Bytes'Range loop
         if I in 17 .. 432 | 465 .. 624 | 633 .. 696 | 705 .. 768 then
            Lemma_Permit_Digests_At (Left, Right, Item, I);
         elsif I in 777 .. 840 then
            Lemma_Permit_Signature_At (Left, Right, I);
         end if;
         pragma Assert (Left (I) = Right (I));
         pragma Loop_Invariant
           (for all J in Permit_Bytes'First .. I => Left (J) = Right (J));
         pragma Loop_Variant (Decreases => Permit_Bytes'Last - I);
      end loop;
      pragma Assert (for all I in Permit_Bytes'Range => Left (I) = Right (I));
   end Lemma_Unique_Permit;

   procedure Lemma_Unique_Control
     (Left, Right : Control_Bytes; Item : Control_Record)
   with Ghost, Global => null, Always_Terminates,
     Pre => Control_Decoded_As (Left, Item) and then
       Control_Decoded_As (Right, Item),
     Post => Left = Right
   is
   begin
      Lemma_Control_Envelope_Unique (Left, Right);
      Lemma_Control_Digest_Region (Left, Right, 16);
      Lemma_Control_Digest_Region (Left, Right, 48);
      Lemma_Control_Digest_Region (Left, Right, 80);
      Lemma_Control_Digest_Region (Left, Right, 112);
      Lemma_Control_Digest_Region (Left, Right, 144);
      Lemma_Control_Digest_Region (Left, Right, 176);
      Lemma_Control_Digest_Region (Left, Right, 208);
      Lemma_Control_Digest_Region (Left, Right, 240);
      Lemma_Word_Unique (Control_Word (Left, 272), Control_Word (Right, 272));
      Lemma_Control_Word_Region (Left, Right, 272);
      pragma Assert (Left (281) = Right (281));
      pragma Assert (Control_Fields_Valid (Left));
      pragma Assert (Control_Fields_Valid (Right));
      for K in 282 .. 288 loop
         pragma Assert (Left (280 + (K - 280)) = 0);
         pragma Assert (Right (280 + (K - 280)) = 0);
         pragma Loop_Invariant (for all J in 282 .. K => Left (J) = Right (J));
         pragma Loop_Variant (Decreases => 288 - K);
      end loop;
      pragma Assert (for all I in 282 .. 288 => Left (I) = Right (I));
      Lemma_Control_Signature_Region (Left, Right);
      for I in Control_Bytes'Range loop
         if I in 17 .. 272 then
            Lemma_Control_Digests_At (Left, Right, Item, I);
         elsif I in 289 .. 352 then
            Lemma_Control_Signature_At (Left, Right, I);
         end if;
         pragma Assert (Left (I) = Right (I));
         pragma Loop_Invariant
           (for all J in Control_Bytes'First .. I => Left (J) = Right (J));
         pragma Loop_Variant (Decreases => Control_Bytes'Last - I);
      end loop;
      pragma Assert (for all I in Control_Bytes'Range => Left (I) = Right (I));
   end Lemma_Unique_Control;


   --  Full typed record domains: the Pre is exactly the encoder's domain.
   procedure Check_Permit_Record (Value : Permit_Record)
   with Global => null, Always_Terminates, Pre => Valid_Permit_Record (Value) is
      Snapshot : constant Permit_Record := Value;
      Bytes : Permit_Bytes;
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      Encode_Permit (Value, Bytes);
      declare
         Bytes_Snapshot : constant Permit_Bytes := Bytes;
      begin
         Decode_Permit (Bytes, Bytes'Length, Status, Item);
         pragma Assert (Status = Decoded and then Item = Snapshot);
         pragma Assert (Bytes = Bytes_Snapshot and then Value = Snapshot);
      end;
   end Check_Permit_Record;

   procedure Check_Control_Record (Value : Control_Record)
   with Global => null, Always_Terminates, Pre => Valid_Control_Record (Value) is
      Snapshot : constant Control_Record := Value;
      Bytes : Control_Bytes;
      Item : Control_Record;
      Status : Decode_Status;
   begin
      Encode_Control (Value, Bytes);
      declare
         Bytes_Snapshot : constant Control_Bytes := Bytes;
      begin
         Decode_Control (Bytes, Bytes'Length, Status, Item);
         pragma Assert (Status = Decoded and then Item = Snapshot);
         pragma Assert (Bytes = Bytes_Snapshot and then Value = Snapshot);
      end;
   end Check_Control_Record;

   procedure Check_Literal_Permit with Global => null, Always_Terminates is
      Snapshot : constant Permit_Bytes := Canonical_Permit;
      Bytes : Permit_Bytes;
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      Decode_Permit (Canonical_Permit, 840, Status, Item);
      pragma Assert (Status = Decoded and then Item = Expected_Permit);
      declare
         Item_Snapshot : constant Permit_Record := Item;
      begin
         Encode_Permit (Item, Bytes);
         Lemma_Unique_Permit (Bytes, Snapshot, Item);
         pragma Assert (Bytes = Snapshot and then Canonical_Permit = Snapshot);
         pragma Assert (Item = Item_Snapshot and then Expected_Permit = Item_Snapshot);
      end;
      Check_Permit_Record (Expected_Permit);
      pragma Assert (not Valid_Permit_Record (Empty_Permit));
   end Check_Literal_Permit;

   procedure Check_Literal_Controls with Global => null, Always_Terminates is
      Enabled_Item, Disabled_Item : Control_Record;
      Enabled_Bytes : constant Control_Bytes := Canonical_Control;
      Disabled_Bytes : constant Control_Bytes :=
        (Canonical_Control with delta 280 => 1, 281 => 1);
      Roundtrip : Control_Bytes;
      Status : Decode_Status;
   begin
      Decode_Control (Enabled_Bytes, 352, Status, Enabled_Item);
      pragma Assert (Status = Decoded and then Enabled_Item = Expected_Control);
      Decode_Control (Disabled_Bytes, 352, Status, Disabled_Item);
      pragma Assert (Status = Decoded and then
        Disabled_Item = (Expected_Control with delta Epoch => 1, State => Disabled));
      declare
         Enabled_Snapshot : constant Control_Record := Enabled_Item;
         Disabled_Snapshot : constant Control_Record := Disabled_Item;
      begin
         Encode_Control (Enabled_Item, Roundtrip);
         Lemma_Unique_Control (Roundtrip, Enabled_Bytes, Enabled_Item);
         pragma Assert (Roundtrip = Enabled_Bytes);
         Encode_Control (Disabled_Item, Roundtrip);
         Lemma_Unique_Control (Roundtrip, Disabled_Bytes, Disabled_Item);
         pragma Assert (Roundtrip = Disabled_Bytes);
         pragma Assert (Declared_Disable_Step (Enabled_Item, Disabled_Item));
         pragma Assert (not Declared_Disable_Step (Disabled_Item, Enabled_Item));
         pragma Assert (not Declared_Disable_Step (Enabled_Item, Enabled_Item));
         pragma Assert (not Declared_Disable_Step (Disabled_Item, Disabled_Item));
         pragma Assert (Enabled_Item = Enabled_Snapshot and then
           Disabled_Item = Disabled_Snapshot);
      end;
      --  A prior local decoded disabled value cannot make stale syntax fail.
      Decode_Control (Enabled_Bytes, 352, Status, Enabled_Item);
      pragma Assert (Status = Decoded and then Enabled_Item = Expected_Control);
      pragma Assert (Enabled_Bytes = Canonical_Control and then
        Disabled_Bytes = (Canonical_Control with delta 280 => 1, 281 => 1));
      Check_Control_Record (Enabled_Item);
      Check_Control_Record (Disabled_Item);
      pragma Assert (not Valid_Control_Record (Empty_Control));
   end Check_Literal_Controls;

   --  Neither parameter has a narrowed length domain; proof must cover Natural.
   procedure Check_Permit_Length (Length : Natural)
   with Global => null, Always_Terminates is
      Snapshot : constant Permit_Bytes := Canonical_Permit;
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      Decode_Permit (Canonical_Permit, Length, Status, Item);
      pragma Assert
        (if Length = 840 then Status = Decoded and then Item = Expected_Permit
         else Status = Length_Refused and then Item = Empty_Permit);
      pragma Assert (Canonical_Permit = Snapshot);
   end Check_Permit_Length;

   procedure Check_Control_Length (Length : Natural)
   with Global => null, Always_Terminates is
      Snapshot : constant Control_Bytes := Canonical_Control;
      Item : Control_Record;
      Status : Decode_Status;
   begin
      Decode_Control (Canonical_Control, Length, Status, Item);
      pragma Assert
        (if Length = 352 then Status = Decoded and then Item = Expected_Control
         else Status = Length_Refused and then Item = Empty_Control);
      pragma Assert (Canonical_Control = Snapshot);
   end Check_Control_Length;

   procedure Check_Lengths with Global => null, Always_Terminates is
   begin
      for Length in 0 .. 840 loop
         Check_Permit_Length (Length);
         pragma Loop_Variant (Decreases => 840 - Length);
      end loop;
      Check_Permit_Length (841);
      Check_Permit_Length (Natural'Last);
      for Length in 0 .. 352 loop
         Check_Control_Length (Length);
         pragma Loop_Variant (Decreases => 352 - Length);
      end loop;
      Check_Control_Length (353);
      Check_Control_Length (Natural'Last);
   end Check_Lengths;

   procedure Check_Permit_Prefix (Position : Positive; Code : Digest_Byte)
   with Global => null, Always_Terminates, Pre => Position in 1 .. 16 is
      Bytes : constant Permit_Bytes :=
        (Canonical_Permit with delta Position => Code);
      Snapshot : constant Permit_Bytes := Bytes;
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      if Code = Canonical_Permit (Position) then
         pragma Assert (Bytes = Canonical_Permit);
      elsif Permit_Envelope_Valid (Bytes) then
         Lemma_Permit_Envelope_Unique (Bytes, Canonical_Permit);
         pragma Assert (Bytes (Position) = Canonical_Permit (Position));
      end if;
      Decode_Permit (Bytes, 840, Status, Item);
      pragma Assert
        (if Code = Canonical_Permit (Position) then Status = Decoded
         else Status = Envelope_Refused and then Item = Empty_Permit);
      pragma Assert (Bytes = Snapshot);
   end Check_Permit_Prefix;

   procedure Check_Control_Prefix (Position : Positive; Code : Digest_Byte)
   with Global => null, Always_Terminates, Pre => Position in 1 .. 16 is
      Bytes : constant Control_Bytes :=
        (Canonical_Control with delta Position => Code);
      Snapshot : constant Control_Bytes := Bytes;
      Item : Control_Record;
      Status : Decode_Status;
   begin
      Decode_Control (Bytes, 352, Status, Item);
      pragma Assert
        (if Code = Canonical_Control (Position) then Status = Decoded
         else Status = Envelope_Refused and then Item = Empty_Control);
      pragma Assert (Bytes = Snapshot);
   end Check_Control_Prefix;

   procedure Check_Permit_Role_Byte (Position : Positive; Code : Digest_Byte)
   with Global => null, Always_Terminates,
     Pre => Position in 625 .. 632 | 697 .. 704 | 769 .. 776 is
      Bytes : constant Permit_Bytes :=
        (Canonical_Permit with delta Position => Code);
      Snapshot : constant Permit_Bytes := Bytes;
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      pragma Assert (Permit_Envelope_Valid (Bytes));
      if Code = Canonical_Permit (Position) then
         pragma Assert (Bytes = Canonical_Permit);
      elsif Permit_Fields_Valid (Bytes) then
         if Position in 625 .. 632 then
            Lemma_Role_Byte (Bytes, Canonical_Permit, 560, Position - 624);
         elsif Position in 697 .. 704 then
            Lemma_Role_Byte (Bytes, Canonical_Permit, 632, Position - 696);
         else
            Lemma_Role_Byte (Bytes, Canonical_Permit, 704, Position - 768);
         end if;
         pragma Assert (Bytes (Position) = Canonical_Permit (Position));
      end if;
      Decode_Permit (Bytes, 840, Status, Item);
      pragma Assert
        (if Code = Canonical_Permit (Position) then Status = Decoded
         else Status = Field_Refused and then Item = Empty_Permit);
      pragma Assert (Bytes = Snapshot);
   end Check_Permit_Role_Byte;

   procedure Check_Control_Reserved (Position : Positive; Code : Digest_Byte)
   with Global => null, Always_Terminates, Pre => Position in 282 .. 288 is
      Bytes : constant Control_Bytes :=
        (Canonical_Control with delta Position => Code);
      Snapshot : constant Control_Bytes := Bytes;
      Item : Control_Record;
      Status : Decode_Status;
   begin
      pragma Assert (Control_Envelope_Valid (Bytes));
      if Code = 0 then
         pragma Assert (Bytes = Canonical_Control);
      elsif Control_Fields_Valid (Bytes) then
         pragma Assert (Position - 280 in Word'Range);
         pragma Assert (Bytes (280 + (Position - 280)) = 0);
      end if;
      Decode_Control (Bytes, 352, Status, Item);
      pragma Assert
        (if Code = 0 then Status = Decoded
         else Status = Field_Refused and then Item = Empty_Control);
      pragma Assert (Bytes = Snapshot);
   end Check_Control_Reserved;

   procedure Check_Envelope_Bytes with Global => null, Always_Terminates is
   begin
      for Position in 1 .. 16 loop
         for Code in Digest_Byte loop
            Check_Permit_Prefix (Position, Code);
            Check_Control_Prefix (Position, Code);
         end loop;
      end loop;
      for Role in Role_Profile_Positions'Range loop
         for Offset in 0 .. 7 loop
            for Code in Digest_Byte loop
               Check_Permit_Role_Byte (Role_Profile_Positions (Role) + Offset, Code);
            end loop;
         end loop;
      end loop;
      for Position in 282 .. 288 loop
         for Code in Digest_Byte loop
            Check_Control_Reserved (Position, Code);
         end loop;
      end loop;
   end Check_Envelope_Bytes;

   procedure Check_Permit_Zero_Identity (Field : Permit_Identity)
   with Global => null, Always_Terminates is
      Offset : constant Natural := Permit_Identity_Offsets (Field);
      Bytes : constant Permit_Bytes :=
        [for J in Permit_Bytes'Range =>
           (if J in Offset + 1 .. Offset + Digest'Length
            then 0 else Canonical_Permit (J))];
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      pragma Assert (Offset <= Permit_Bytes'Length - Digest'Length);
      pragma Assert (for all I in Digest'Range => Bytes (Offset + I) = 0);
      pragma Assert
        (for all J in Permit_Bytes'Range =>
           (if J not in Offset + 1 .. Offset + Digest'Length then
              Bytes (J) = Canonical_Permit (J)));
      declare
         Snapshot : constant Permit_Bytes := Bytes;
      begin
         Decode_Permit (Bytes, 840, Status, Item);
         pragma Assert (Status = Field_Refused and then Item = Empty_Permit);
         pragma Assert (Bytes = Snapshot);
      end;
   end Check_Permit_Zero_Identity;

   procedure Check_Control_Zero_Identity (Field : Control_Identity)
   with Global => null, Always_Terminates is
      Offset : constant Natural := Control_Identity_Offsets (Field);
      Bytes : constant Control_Bytes :=
        [for J in Control_Bytes'Range =>
           (if J in Offset + 1 .. Offset + Digest'Length
            then 0 else Canonical_Control (J))];
      Item : Control_Record;
      Status : Decode_Status;
   begin
      pragma Assert (Offset <= Control_Bytes'Length - Digest'Length);
      pragma Assert (for all I in Digest'Range => Bytes (Offset + I) = 0);
      pragma Assert
        (for all J in Control_Bytes'Range =>
           (if J not in Offset + 1 .. Offset + Digest'Length then
              Bytes (J) = Canonical_Control (J)));
      declare
         Snapshot : constant Control_Bytes := Bytes;
      begin
         Decode_Control (Bytes, 352, Status, Item);
         pragma Assert (Status = Field_Refused and then Item = Empty_Control);
         pragma Assert (Bytes = Snapshot);
      end;
   end Check_Control_Zero_Identity;

   procedure Check_Identities with Global => null, Always_Terminates is
   begin
      for Field in Permit_Identity loop
         Check_Permit_Zero_Identity (Field);
      end loop;
      for Field in Control_Identity loop
         Check_Control_Zero_Identity (Field);
      end loop;
   end Check_Identities;

   procedure Lemma_Permit_Record_Unique
     (Bytes : Permit_Bytes; Left, Right : Permit_Record)
   with Ghost, Global => null, Always_Terminates,
     Pre => Permit_Decoded_As (Bytes, Left) and then Permit_Decoded_As (Bytes, Right),
     Post => Left = Right
   is
   begin
      null;
   end Lemma_Permit_Record_Unique;

   procedure Check_Permit_Content_Byte (Position : Positive; Code : Digest_Byte)
   with Global => null, Always_Terminates,
     Pre => Position in 369 .. 432 | 465 .. 528 | 777 .. 840 is
      Bytes : constant Permit_Bytes :=
        (Canonical_Permit with delta Position => Code);
      Snapshot : constant Permit_Bytes := Bytes;
      Expected : Permit_Record := Expected_Permit;
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      if Position in 369 .. 400 then
         Expected.Content.Operation.Predecessor_Receipt (Position - 368) := Code;
      elsif Position in 401 .. 432 then
         Expected.Content.Operation.Payload_Digest (Position - 400) := Code;
      elsif Position in 465 .. 496 then
         Expected.Content.Historical_Publish_Digest (Position - 464) := Code;
      elsif Position in 497 .. 528 then
         Expected.Content.Predecessor_State_Digest (Position - 496) := Code;
      else
         pragma Assert (Position in 777 .. 840);
         Expected.Signature (Position - 776) := Code;
      end if;
      declare
         Expected_Snapshot : constant Permit_Record := Expected;
      begin
         pragma Assert (Check_Permit (Bytes, Permit_Bytes'Length) = Decoded);
         pragma Assert (Valid_Permit_Record (Expected_Snapshot));
         pragma Assert (Expected_Snapshot.Content.Issuer = Permit_Digest (Bytes, 16));
         pragma Assert (Expected_Snapshot.Content.Key = Permit_Digest (Bytes, 48));
         pragma Assert (Operation_Decoded_As (Bytes, Expected_Snapshot.Content.Operation));
         pragma Assert (Expected_Snapshot.Content.Historical_Publish_Digest =
           Permit_Digest (Bytes, 464));
         pragma Assert (Expected_Snapshot.Content.Predecessor_State_Digest =
           Permit_Digest (Bytes, 496));
         pragma Assert (Expected_Snapshot.Content.Recovery_Policy = Permit_Digest (Bytes, 528));
         pragma Assert (Permit_Signers_Decoded_As (Bytes, Expected_Snapshot.Content));
         pragma Assert (Expected_Snapshot.Signature = Permit_Signature (Bytes));
         pragma Assert (Permit_Decoded_As (Bytes, Expected_Snapshot));
         Decode_Permit (Bytes, 840, Status, Item);
         pragma Assert (Status = Decoded);
         Lemma_Permit_Record_Unique (Bytes, Item, Expected_Snapshot);
         pragma Assert (Status = Decoded and then Item = Expected_Snapshot);
         pragma Assert (Bytes = Snapshot and then Expected = Expected_Snapshot);
      end;
   end Check_Permit_Content_Byte;

   procedure Check_Control_Content_Byte (Position : Positive; Code : Digest_Byte)
   with Global => null, Always_Terminates,
     Pre => Position in 113 .. 144 | 289 .. 352 is
      Bytes : constant Control_Bytes :=
        (Canonical_Control with delta Position => Code);
      Snapshot : constant Control_Bytes := Bytes;
      Expected : Control_Record := Expected_Control;
      Item : Control_Record;
      Status : Decode_Status;
   begin
      if Position in 113 .. 144 then
         Expected.Bindings.Permit_Signed_Digest (Position - 112) := Code;
      else
         pragma Assert (Position in 289 .. 352);
         Expected.Signature (Position - 288) := Code;
      end if;
      declare
         Expected_Snapshot : constant Control_Record := Expected;
      begin
         Decode_Control (Bytes, 352, Status, Item);
         pragma Assert (Status = Decoded and then Item = Expected_Snapshot);
         pragma Assert (Bytes = Snapshot and then Expected = Expected_Snapshot);
      end;
   end Check_Control_Content_Byte;

   procedure Check_Content_Bytes with Global => null, Always_Terminates is
   begin
      for Position in Permit_Bytes'Range loop
         if Position in 369 .. 432 | 465 .. 528 | 777 .. 840 then
            for Code in Digest_Byte loop
               Check_Permit_Content_Byte (Position, Code);
            end loop;
         end if;
      end loop;
      for Position in Control_Bytes'Range loop
         if Position in 113 .. 144 | 289 .. 352 then
            for Code in Digest_Byte loop
               Check_Control_Content_Byte (Position, Code);
            end loop;
         end if;
      end loop;
   end Check_Content_Bytes;

   --  No scalar parameter Pre: all Generation pairs, UID values and lengths.
   procedure Lemma_Permit_Digest_Equal
     (Left, Right : Permit_Bytes; Offset : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset <= Permit_Bytes'Length - Digest'Length and then
       (for all I in Digest'Range => Left (Offset + I) = Right (Offset + I)),
     Post => Permit_Digest (Left, Offset) = Permit_Digest (Right, Offset)
   is
   begin
      null;
   end Lemma_Permit_Digest_Equal;

   procedure Lemma_Permit_Role_Preserved
     (Left, Right : Permit_Bytes; Offset : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset in 560 | 632 | 704 and then
       (for all J in Offset + 1 .. Offset + 72 => Left (J) = Right (J)),
     Post => Permit_Role_Valid (Left, Offset) = Permit_Role_Valid (Right, Offset)
   is
   begin
      Lemma_Permit_Digest_Equal (Left, Right, Offset);
      Lemma_Permit_Digest_Equal (Left, Right, Offset + 32);
      pragma Assert (Left (Offset + 65) = Right (Offset + 65));
      pragma Assert
        (for all J in Offset + 66 .. Offset + 72 => Left (J) = Right (J));
   end Lemma_Permit_Role_Preserved;

   procedure Lemma_Permit_Static_Frame (Bytes : Permit_Bytes)
   with Ghost, Global => null, Always_Terminates,
     Pre => (for all I in Permit_Bytes'Range =>
       (if I not in 433 .. 464 then Bytes (I) = Canonical_Permit (I))),
     Post => Permit_Envelope_Valid (Bytes) and then
       Permit_Identities_Valid (Bytes) and then
       Permit_Role_Valid (Bytes, 560) and then
       Permit_Role_Valid (Bytes, 632) and then Permit_Role_Valid (Bytes, 704)
   is
   begin
      Lemma_Permit_Digest_Equal (Bytes, Canonical_Permit, 16);
      Lemma_Permit_Digest_Equal (Bytes, Canonical_Permit, 48);
      Lemma_Permit_Digest_Equal (Bytes, Canonical_Permit, 80);
      Lemma_Permit_Digest_Equal (Bytes, Canonical_Permit, 112);
      Lemma_Permit_Digest_Equal (Bytes, Canonical_Permit, 144);
      Lemma_Permit_Digest_Equal (Bytes, Canonical_Permit, 176);
      Lemma_Permit_Digest_Equal (Bytes, Canonical_Permit, 208);
      Lemma_Permit_Digest_Equal (Bytes, Canonical_Permit, 240);
      Lemma_Permit_Digest_Equal (Bytes, Canonical_Permit, 272);
      Lemma_Permit_Digest_Equal (Bytes, Canonical_Permit, 304);
      Lemma_Permit_Digest_Equal (Bytes, Canonical_Permit, 336);
      Lemma_Permit_Digest_Equal (Bytes, Canonical_Permit, 528);
      Lemma_Permit_Role_Preserved (Bytes, Canonical_Permit, 560);
      Lemma_Permit_Role_Preserved (Bytes, Canonical_Permit, 632);
      Lemma_Permit_Role_Preserved (Bytes, Canonical_Permit, 704);
   end Lemma_Permit_Static_Frame;

   procedure Lemma_Permit_Word_Byte
     (Left, Right : Permit_Bytes; Offset : Natural; Index : Positive)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset <= Permit_Bytes'Length - Word'Length and then
       Index in Word'Range and then
       Permit_Word (Left, Offset) = Permit_Word (Right, Offset),
     Post => Left (Offset + Index) = Right (Offset + Index)
   is
   begin
      pragma Assert
        (Permit_Word (Left, Offset) (Index) = Left (Offset + Index));
      pragma Assert
        (Permit_Word (Right, Offset) (Index) = Right (Offset + Index));
      pragma Assert
        (Permit_Word (Left, Offset) (Index) =
         Permit_Word (Right, Offset) (Index));
   end Lemma_Permit_Word_Byte;

   procedure Lemma_Generation_Scalars
     (Bytes : Permit_Bytes; Before, Target : Generation)
   with Ghost, Global => null, Always_Terminates,
     Pre =>
       Permit_Word (Bytes, 432) = Permit_Word (Canonical_Permit, 432) and then
       Permit_Word (Bytes, 456) = Permit_Word (Canonical_Permit, 456) and then
       Permit_Word (Bytes, 440) = Generation_Bytes (Before) and then
       Permit_Word (Bytes, 448) = Generation_Bytes (Target),
     Post => Permit_Scalars_Valid (Bytes) =
       (Before < Generation'Last and then Target = Before + 1)
   is
   begin
      Lemma_Permit_Word_Region (Bytes, Canonical_Permit, 432);
      Lemma_Permit_Word_Region (Bytes, Canonical_Permit, 456);
      Lemma_Permit_Word_Byte (Bytes, Canonical_Permit, 456, 1);
      pragma Assert (Bytes (457) = Canonical_Permit (457));
      pragma Assert (Bytes (457) = 0);
      pragma Assert (for all I in 1 .. 4 => Bytes (432 + I) = 0);
      pragma Assert (Word_Value (Permit_Word (Bytes, 432)) = 1);
      pragma Assert (Bytes (441) <= 127);
      pragma Assert (Bytes (449) <= 127);
      pragma Assert (Bytes (457) <= 127);
      pragma Assert (Word_Value (Permit_Word (Bytes, 456)) = 0);
      pragma Assert (Word_Value (Permit_Word (Bytes, 440)) = Before);
      pragma Assert (Word_Value (Permit_Word (Bytes, 448)) = Target);
   end Lemma_Generation_Scalars;

   procedure Check_Generation_Domain (Before, Target : Generation)
   with Global => null, Always_Terminates is
      Bytes : Permit_Bytes := Canonical_Permit;
      Before_Word : constant Word := Generation_Bytes (Before) with Ghost;
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      Put_Word (Bytes, 440, Before);
      pragma Assert (Permit_Word (Bytes, 440) = Before_Word);
      Put_Word (Bytes, 448, Target);
      pragma Assert (Permit_Word (Bytes, 440) = Before_Word);
      pragma Assert (Word_Value (Permit_Word (Bytes, 440)) = Before);
      Lemma_Permit_Static_Frame (Bytes);
      pragma Assert (Permit_Word (Bytes, 432) = Permit_Word (Canonical_Permit, 432));
      pragma Assert (Permit_Word (Bytes, 456) = Permit_Word (Canonical_Permit, 456));
      Lemma_Generation_Scalars (Bytes, Before, Target);
      pragma Assert
        (Check_Permit (Bytes, Permit_Bytes'Length) =
           (if Before < Generation'Last and then Target = Before + 1
            then Decoded else Field_Refused));
      declare
         Snapshot : constant Permit_Bytes := Bytes;
      begin
         Decode_Permit (Bytes, 840, Status, Item);
         if Before < Generation'Last and then Target = Before + 1 then
            pragma Assert (Status = Decoded);
            pragma Assert (Operation_Decoded_As (Bytes, Item.Content.Operation));
            pragma Assert (Item.Content.Operation.Before_Generation =
              Word_Value (Permit_Word (Bytes, 440)));
            pragma Assert (Item.Content.Operation.Target_Generation =
              Word_Value (Permit_Word (Bytes, 448)));
            pragma Assert (Item.Content.Operation.Before_Generation = Before);
            pragma Assert (Item.Content.Operation.Target_Generation = Target);
         else
            pragma Assert (Status = Field_Refused);
            pragma Assert (Item = Empty_Permit);
         end if;
         pragma Assert
           (if Before < Generation'Last and then Target = Before + 1 then
              Status = Decoded and then Item.Content.Operation.Before_Generation = Before
                and then Item.Content.Operation.Target_Generation = Target
            else Status = Field_Refused and then Item = Empty_Permit);
         pragma Assert (Bytes = Snapshot);
      end;
   end Check_Generation_Domain;

   procedure Check_UID_Domain (Value : Generation)
   with Global => null, Always_Terminates is
      Bytes : Permit_Bytes := Canonical_Permit;
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      Put_Word (Bytes, 432, Value);
      Lemma_Permit_Static_Frame (Bytes);
      pragma Assert (Permit_Word (Bytes, 440) =
        Permit_Word (Canonical_Permit, 440));
      pragma Assert (Permit_Word (Bytes, 448) =
        Permit_Word (Canonical_Permit, 448));
      pragma Assert (Permit_Word (Bytes, 456) =
        Permit_Word (Canonical_Permit, 456));
      declare
         Snapshot : constant Permit_Bytes := Bytes;
      begin
         Decode_Permit (Bytes, 840, Status, Item);
         pragma Assert
           (if Value in 1 .. Subject_UID'Last then Status = Decoded and then
              Item.Content.Operation.Publication_Subject_UID = Value
            else Status = Field_Refused and then Item = Empty_Permit);
         pragma Assert (Bytes = Snapshot);
      end;
   end Check_UID_Domain;

   procedure Check_Payload_Domain (Value : Generation)
   with Global => null, Always_Terminates is
      Bytes : Permit_Bytes := Canonical_Permit;
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      Put_Word (Bytes, 456, Value);
      Lemma_Permit_Static_Frame (Bytes);
      pragma Assert (Permit_Word (Bytes, 432) =
        Permit_Word (Canonical_Permit, 432));
      pragma Assert (Permit_Word (Bytes, 440) =
        Permit_Word (Canonical_Permit, 440));
      pragma Assert (Permit_Word (Bytes, 448) =
        Permit_Word (Canonical_Permit, 448));
      declare
         Snapshot : constant Permit_Bytes := Bytes;
      begin
         Decode_Permit (Bytes, 840, Status, Item);
         pragma Assert
           (if Value <= Generation (Payload_Count'Last) then Status = Decoded and then
              Generation (Item.Content.Operation.Logical_Payload_Length) = Value
            else Status = Field_Refused and then Item = Empty_Permit);
         pragma Assert (Bytes = Snapshot);
      end;
   end Check_Payload_Domain;

   procedure Check_UID_Upper (Position : Positive; Code : Digest_Byte)
   with Global => null, Always_Terminates, Pre => Position in 433 .. 436 is
      Bytes : constant Permit_Bytes := (Canonical_Permit with delta Position => Code);
      Snapshot : constant Permit_Bytes := Bytes;
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      Decode_Permit (Bytes, 840, Status, Item);
      pragma Assert
        (if Code = 0 then Status = Decoded
         else Status = Field_Refused and then Item = Empty_Permit);
      pragma Assert (Bytes = Snapshot);
   end Check_UID_Upper;

   procedure Check_Scalar_High (Position : Positive; Code : Digest_Byte)
   with Global => null, Always_Terminates, Pre => Position in 441 | 449 | 457 is
      Bytes : constant Permit_Bytes := (Canonical_Permit with delta Position => Code);
      Snapshot : constant Permit_Bytes := Bytes;
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      Decode_Permit (Bytes, 840, Status, Item);
      pragma Assert
        (if Code >= 128 then Status = Field_Refused and then Item = Empty_Permit);
      pragma Assert (Bytes = Snapshot);
   end Check_Scalar_High;

   procedure Check_Payload_High (Position : Positive; Code : Digest_Byte)
   with Global => null, Always_Terminates, Pre => Position in 457 .. 462 is
      Bytes : constant Permit_Bytes := (Canonical_Permit with delta Position => Code);
      Snapshot : constant Permit_Bytes := Bytes;
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      Decode_Permit (Bytes, 840, Status, Item);
      pragma Assert
        (if Code = 0 then Status = Decoded
         else Status = Field_Refused and then Item = Empty_Permit);
      pragma Assert (Bytes = Snapshot);
   end Check_Payload_High;

   procedure Check_Control_Pair (Epoch, State_Code : Digest_Byte)
   with Global => null, Always_Terminates is
      Bytes : constant Control_Bytes :=
        (Canonical_Control with delta 280 => Epoch, 281 => State_Code);
      Snapshot : constant Control_Bytes := Bytes;
      Item : Control_Record;
      Status : Decode_Status;
   begin
      Decode_Control (Bytes, 352, Status, Item);
      pragma Assert
        (if Epoch <= 1 and then State_Code = Epoch then Status = Decoded and then
           Item.Epoch = Natural (Epoch) and then
           Item.State = (if State_Code = 0 then Enabled else Disabled)
         else Status = State_Refused and then Item = Empty_Control);
      pragma Assert (Bytes = Snapshot);
   end Check_Control_Pair;

   procedure Check_Control_Epoch_Upper (Position : Positive; Code : Digest_Byte)
   with Global => null, Always_Terminates, Pre => Position in 273 .. 279 is
      Bytes : constant Control_Bytes := (Canonical_Control with delta Position => Code);
      Snapshot : constant Control_Bytes := Bytes;
      Item : Control_Record;
      Status : Decode_Status;
   begin
      Decode_Control (Bytes, 352, Status, Item);
      pragma Assert
        (if Code = 0 then Status = Decoded
         else Status = State_Refused and then Item = Empty_Control);
      pragma Assert (Bytes = Snapshot);
   end Check_Control_Epoch_Upper;

   procedure Check_Raw_Scalar_Bytes with Global => null, Always_Terminates is
      High_Positions : constant array (1 .. 3) of Positive := [441, 449, 457];
   begin
      for Code in Digest_Byte loop
         for Position in 433 .. 436 loop
            Check_UID_Upper (Position, Code);
         end loop;
         for I in High_Positions'Range loop
            Check_Scalar_High (High_Positions (I), Code);
         end loop;
         for Position in 457 .. 462 loop
            Check_Payload_High (Position, Code);
         end loop;
         for Position in 273 .. 279 loop
            Check_Control_Epoch_Upper (Position, Code);
         end loop;
         for State_Code in Digest_Byte loop
            Check_Control_Pair (Code, State_Code);
         end loop;
      end loop;
   end Check_Raw_Scalar_Bytes;

   procedure Check_Scalar_Boundaries with Global => null, Always_Terminates is
      Bytes : constant Permit_Bytes :=
        (Canonical_Permit with delta 457 .. 464 => 255);
      Snapshot : constant Permit_Bytes := Bytes;
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      Check_UID_Domain (0);
      Check_UID_Domain (1);
      Check_UID_Domain (Subject_UID'Last);
      Check_UID_Domain (Subject_UID'Last + 1);
      Check_UID_Domain (Generation'Last);
      Check_Generation_Domain (0, 1);
      Check_Generation_Domain (Generation'Last - 1, Generation'Last);
      Check_Generation_Domain (Generation'Last, 0);
      Check_Generation_Domain (1, 1);
      Check_Generation_Domain (1, 0);
      Check_Generation_Domain (0, 2);
      for Length in Payload_Count loop
         Check_Payload_Domain (Generation (Length));
      end loop;
      Check_Payload_Domain (4097);
      Check_Payload_Domain (Generation'Last);
      Decode_Permit (Bytes, 840, Status, Item);
      pragma Assert (Status = Field_Refused and then Item = Empty_Permit);
      pragma Assert (Bytes = Snapshot);
   end Check_Scalar_Boundaries;

   procedure Check_Precedence with Global => null, Always_Terminates is
      Permit : constant Permit_Bytes :=
        (Canonical_Permit with delta 1 => 0, 625 => 0, 769 => 255);
      Control : constant Control_Bytes :=
        (Canonical_Control with delta 1 => 0, 282 => 1, 281 => 1);
      Field_First : constant Control_Bytes :=
        (Canonical_Control with delta 282 => 1, 281 => 1);
      P : Permit_Record;
      C : Control_Record;
      Status : Decode_Status;
   begin
      Decode_Permit (Permit, 839, Status, P);
      pragma Assert (Status = Length_Refused and then P = Empty_Permit);
      Decode_Permit (Permit, 840, Status, P);
      pragma Assert (Status = Envelope_Refused and then P = Empty_Permit);
      Decode_Control (Control, 351, Status, C);
      pragma Assert (Status = Length_Refused and then C = Empty_Control);
      Decode_Control (Control, 352, Status, C);
      pragma Assert (Status = Envelope_Refused and then C = Empty_Control);
      pragma Assert (Control_Envelope_Valid (Field_First));
      pragma Assert (Field_First (282) = 1);
      pragma Assert (not Control_Fields_Valid (Field_First));
      Decode_Control (Field_First, 352, Status, C);
      pragma Assert (Status = Field_Refused and then C = Empty_Control);
      pragma Assert
        (Permit = (Canonical_Permit with delta 1 => 0, 625 => 0, 769 => 255)
         and then Control = (Canonical_Control with delta 1 => 0, 282 => 1, 281 => 1)
         and then Field_First = (Canonical_Control with delta 282 => 1, 281 => 1));
   end Check_Precedence;

   type Operation_Material is
     (O_Fixture, O_Transaction, O_Protocol, O_Issuer, O_Key, O_Clock,
      O_Boot, O_Service, O_Capability, O_Predecessor, O_Payload,
      O_UID, O_Before, O_Target, O_Length);
   function Changed_Operation (Field : Operation_Material) return Operation_Fields
   with Global => null,
     Post => Changed_Operation'Result =
     (case Field is
       when O_Fixture =>
         (Expected_Operation with delta Fixture => Filled (254)),
       when O_Transaction =>
         (Expected_Operation with delta Transaction => Filled (254)),
       when O_Protocol =>
         (Expected_Operation with delta Protocol => Filled (254)),
       when O_Issuer =>
         (Expected_Operation with delta Publication_Issuer => Filled (254)),
       when O_Key =>
         (Expected_Operation with delta Publication_Key => Filled (254)),
       when O_Clock =>
         (Expected_Operation with delta Publication_Clock => Filled (254)),
       when O_Boot =>
         (Expected_Operation with delta Publication_Boot => Filled (254)),
       when O_Service =>
         (Expected_Operation with delta Publication_Service => Filled (254)),
       when O_Capability =>
         (Expected_Operation with delta Publication_Capability => Filled (254)),
       when O_Predecessor =>
         (Expected_Operation with delta Predecessor_Receipt => Filled (254)),
       when O_Payload =>
         (Expected_Operation with delta Payload_Digest => Filled (254)),
       when O_UID =>
         (Expected_Operation with delta Publication_Subject_UID => 2),
       when O_Before | O_Target =>
         (Expected_Operation with delta Before_Generation => 1, Target_Generation => 2),
       when O_Length =>
         (Expected_Operation with delta Logical_Payload_Length => 1))
   is
      Result : Operation_Fields := Expected_Operation;
   begin
      case Field is
         when O_Fixture => Result.Fixture := Filled (254);
         when O_Transaction => Result.Transaction := Filled (254);
         when O_Protocol => Result.Protocol := Filled (254);
         when O_Issuer => Result.Publication_Issuer := Filled (254);
         when O_Key => Result.Publication_Key := Filled (254);
         when O_Clock => Result.Publication_Clock := Filled (254);
         when O_Boot => Result.Publication_Boot := Filled (254);
         when O_Service => Result.Publication_Service := Filled (254);
         when O_Capability => Result.Publication_Capability := Filled (254);
         when O_Predecessor => Result.Predecessor_Receipt := Filled (254);
         when O_Payload => Result.Payload_Digest := Filled (254);
         when O_UID => Result.Publication_Subject_UID := 2;
         when O_Before | O_Target =>
            Result.Before_Generation := 1;
            Result.Target_Generation := 2;
         when O_Length => Result.Logical_Payload_Length := 1;
      end case;
      return Result;
   end Changed_Operation;

   procedure Check_Operation_Material (Field : Operation_Material)
   with Global => null, Always_Terminates is
      Value : constant Permit_Record := (Expected_Permit with delta
        Content => (Expected_Permit.Content with delta
          Operation => Changed_Operation (Field)));
      Snapshot : constant Permit_Record := Value;
      Expected_Snapshot : constant Permit_Record := Expected_Permit;
   begin
      pragma Assert (Value.Content.Operation /= Expected_Operation);
      pragma Assert (Valid_Permit_Record (Value));
      pragma Assert (not Same_Permit_Content (Value, Expected_Permit));
      if Field = O_Before then
         pragma Assert (Value.Content.Operation.Before_Generation /=
           Expected_Operation.Before_Generation);
      elsif Field = O_Target then
         pragma Assert (Value.Content.Operation.Target_Generation /=
           Expected_Operation.Target_Generation);
      end if;
      Check_Permit_Record (Value);
      pragma Assert (Value = Snapshot and then Expected_Permit = Expected_Snapshot);
   end Check_Operation_Material;

   type Permit_Material is
     (P_Issuer, P_Key, P_Historical, P_Predecessor_State, P_Recovery_Policy,
      P_Intent_Issuer, P_Intent_Key, P_Intent_Profile, P_Receipt_Issuer,
      P_Receipt_Key, P_Receipt_Profile, P_State_Issuer, P_State_Key, P_State_Profile);
   function Changed_Permit (Field : Permit_Material) return Permit_Record
   with Global => null,
     Post => Changed_Permit'Result =
     (Expected_Permit with delta Content =>
      (case Field is
       when P_Issuer =>
         (Expected_Permit.Content with delta Issuer => Filled (254)),
       when P_Key =>
         (Expected_Permit.Content with delta Key => Filled (254)),
       when P_Historical =>
         (Expected_Permit.Content with delta Historical_Publish_Digest => Filled (254)),
       when P_Predecessor_State =>
         (Expected_Permit.Content with delta Predecessor_State_Digest => Filled (254)),
       when P_Recovery_Policy =>
         (Expected_Permit.Content with delta Recovery_Policy => Filled (254)),
       when P_Intent_Issuer =>
         (Expected_Permit.Content with delta Intent_Signer => (Expected_Permit.Content.Intent_Signer with delta Issuer => Filled (254))),
       when P_Intent_Key =>
         (Expected_Permit.Content with delta Intent_Signer => (Expected_Permit.Content.Intent_Signer with delta Key => Filled (254))),
       when P_Intent_Profile =>
         (Expected_Permit.Content with delta Intent_Signer => (Expected_Permit.Content.Intent_Signer with delta Profile => 0)),
       when P_Receipt_Issuer =>
         (Expected_Permit.Content with delta Receipt_Signer => (Expected_Permit.Content.Receipt_Signer with delta Issuer => Filled (254))),
       when P_Receipt_Key =>
         (Expected_Permit.Content with delta Receipt_Signer => (Expected_Permit.Content.Receipt_Signer with delta Key => Filled (254))),
       when P_Receipt_Profile =>
         (Expected_Permit.Content with delta Receipt_Signer => (Expected_Permit.Content.Receipt_Signer with delta Profile => 0)),
       when P_State_Issuer =>
         (Expected_Permit.Content with delta State_Signer => (Expected_Permit.Content.State_Signer with delta Issuer => Filled (254))),
       when P_State_Key =>
         (Expected_Permit.Content with delta State_Signer => (Expected_Permit.Content.State_Signer with delta Key => Filled (254))),
       when P_State_Profile =>
         (Expected_Permit.Content with delta State_Signer => (Expected_Permit.Content.State_Signer with delta Profile => 0))))
   is
      Result : Permit_Record := Expected_Permit;
   begin
      case Field is
         when P_Issuer => Result.Content.Issuer := Filled (254);
         when P_Key => Result.Content.Key := Filled (254);
         when P_Historical => Result.Content.Historical_Publish_Digest := Filled (254);
         when P_Predecessor_State =>
            Result.Content.Predecessor_State_Digest := Filled (254);
         when P_Recovery_Policy => Result.Content.Recovery_Policy := Filled (254);
         when P_Intent_Issuer => Result.Content.Intent_Signer.Issuer := Filled (254);
         when P_Intent_Key => Result.Content.Intent_Signer.Key := Filled (254);
         when P_Intent_Profile => Result.Content.Intent_Signer.Profile := 0;
         when P_Receipt_Issuer => Result.Content.Receipt_Signer.Issuer := Filled (254);
         when P_Receipt_Key => Result.Content.Receipt_Signer.Key := Filled (254);
         when P_Receipt_Profile => Result.Content.Receipt_Signer.Profile := 0;
         when P_State_Issuer => Result.Content.State_Signer.Issuer := Filled (254);
         when P_State_Key => Result.Content.State_Signer.Key := Filled (254);
         when P_State_Profile => Result.Content.State_Signer.Profile := 0;
      end case;
      return Result;
   end Changed_Permit;

   procedure Check_Permit_Material (Field : Permit_Material)
   with Global => null, Always_Terminates is
      Value : constant Permit_Record := Changed_Permit (Field);
      Snapshot : constant Permit_Record := Value;
      Expected_Snapshot : constant Permit_Record := Expected_Permit;
   begin
      pragma Assert (not Same_Permit_Content (Value, Expected_Permit));
      if Field in P_Intent_Profile | P_Receipt_Profile | P_State_Profile then
         pragma Assert (not Valid_Permit_Record (Value));
      else
         pragma Assert (Valid_Permit_Record (Value));
         Check_Permit_Record (Value);
      end if;
      pragma Assert (Value = Snapshot and then Expected_Permit = Expected_Snapshot);
   end Check_Permit_Material;

   type Control_Material is
     (C_Issuer, C_Key, C_Fixture, C_Permit, C_Recovery_Policy,
      C_Control_Policy, C_Provider, C_Namespace);
   function Changed_Control (Field : Control_Material) return Control_Record
   with Global => null,
     Post => Changed_Control'Result =
     (Expected_Control with delta Bindings =>
      (case Field is
       when C_Issuer =>
         (Expected_Control.Bindings with delta Issuer => Filled (254)),
       when C_Key =>
         (Expected_Control.Bindings with delta Key => Filled (254)),
       when C_Fixture =>
         (Expected_Control.Bindings with delta Fixture => Filled (254)),
       when C_Permit =>
         (Expected_Control.Bindings with delta Permit_Signed_Digest => Filled (254)),
       when C_Recovery_Policy =>
         (Expected_Control.Bindings with delta Recovery_Policy => Filled (254)),
       when C_Control_Policy =>
         (Expected_Control.Bindings with delta Control_Policy => Filled (254)),
       when C_Provider =>
         (Expected_Control.Bindings with delta Provider_Id => Filled (254)),
       when C_Namespace =>
         (Expected_Control.Bindings with delta Anchor_Namespace => Filled (254))))
   is
      Result : Control_Record := Expected_Control;
   begin
      case Field is
         when C_Issuer => Result.Bindings.Issuer := Filled (254);
         when C_Key => Result.Bindings.Key := Filled (254);
         when C_Fixture => Result.Bindings.Fixture := Filled (254);
         when C_Permit => Result.Bindings.Permit_Signed_Digest := Filled (254);
         when C_Recovery_Policy => Result.Bindings.Recovery_Policy := Filled (254);
         when C_Control_Policy => Result.Bindings.Control_Policy := Filled (254);
         when C_Provider => Result.Bindings.Provider_Id := Filled (254);
         when C_Namespace => Result.Bindings.Anchor_Namespace := Filled (254);
      end case;
      return Result;
   end Changed_Control;

   procedure Check_Control_Material (Field : Control_Material)
   with Global => null, Always_Terminates is
      Value : constant Control_Record := Changed_Control (Field);
      Disabled_Value : constant Control_Record :=
        (Value with delta Epoch => 1, State => Disabled);
      Snapshot : constant Control_Record := Value;
      Expected_Snapshot : constant Control_Record := Expected_Control;
   begin
      pragma Assert (Valid_Control_Record (Value));
      pragma Assert (not Same_Control_Bindings (Value, Expected_Control));
      pragma Assert (not Same_Control_Content (Value, Expected_Control));
      pragma Assert (not Declared_Disable_Step (Expected_Control, Disabled_Value));
      Check_Control_Record (Value);
      Check_Control_Record (Disabled_Value);
      pragma Assert (Value = Snapshot and then Expected_Control = Expected_Snapshot);
   end Check_Control_Material;

   procedure Check_Material_Comparisons with Global => null, Always_Terminates is
   begin
      for Field in Operation_Material loop
         Check_Operation_Material (Field);
      end loop;
      for Field in Permit_Material loop
         Check_Permit_Material (Field);
      end loop;
      for Field in Control_Material loop
         Check_Control_Material (Field);
      end loop;
   end Check_Material_Comparisons;

   --  Full Digest declaration domain; a true data join is never authentication.
   procedure Check_Declared_Digest (Value : Digest)
   with Global => null, Always_Terminates is
      Control : constant Control_Record := (Expected_Control with delta
        Bindings => (Expected_Control.Bindings with delta Permit_Signed_Digest => Value));
      Wrong_Fixture : constant Control_Record := (Control with delta
        Bindings => (Control.Bindings with delta Fixture => Filled (254)));
      Wrong_Policy : constant Control_Record := (Control with delta
        Bindings => (Control.Bindings with delta Recovery_Policy => Filled (254)));
      Snapshot : constant Digest := Value;
      Control_Snapshot : constant Control_Record := Control;
      Fixture_Snapshot : constant Control_Record := Wrong_Fixture;
      Policy_Snapshot : constant Control_Record := Wrong_Policy;
      Permit_Snapshot : constant Permit_Record := Expected_Permit;
   begin
      pragma Assert (Control_Declares_Permit (Expected_Permit, Control, Value));
      pragma Assert (Control_Declares_Permit
        (Expected_Permit, Control, Filled (255)) = (Value = Filled (255)));
      pragma Assert (not Control_Declares_Permit (Expected_Permit, Wrong_Fixture, Value));
      pragma Assert (not Control_Declares_Permit (Expected_Permit, Wrong_Policy, Value));
      pragma Assert (Value = Snapshot and then Control = Control_Snapshot and then
        Wrong_Fixture = Fixture_Snapshot and then Wrong_Policy = Policy_Snapshot and then
        Expected_Permit = Permit_Snapshot);
   end Check_Declared_Digest;

   procedure Lemma_Permit_Signature_Bytes
     (Bytes : Permit_Bytes; Value : Signature_Bytes)
   with Ghost, Global => null, Always_Terminates,
     Pre => Permit_Signature (Bytes) = Value,
     Post => (for all I in Signature_Bytes'Range => Bytes (776 + I) = Value (I))
   is
   begin
      null;
   end Lemma_Permit_Signature_Bytes;

   procedure Lemma_Permit_Digest_Bytes
     (Bytes : Permit_Bytes; Offset : Natural; Value : Digest)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset <= Permit_Bytes'Length - Digest'Length and then
       Permit_Digest (Bytes, Offset) = Value,
     Post => (for all I in Digest'Range => Bytes (Offset + I) = Value (I))
   is
   begin
      null;
   end Lemma_Permit_Digest_Bytes;

   procedure Lemma_Control_Signature_Bytes
     (Bytes : Control_Bytes; Value : Signature_Bytes)
   with Ghost, Global => null, Always_Terminates,
     Pre => Control_Signature (Bytes) = Value,
     Post => (for all I in Signature_Bytes'Range => Bytes (288 + I) = Value (I))
   is
   begin
      null;
   end Lemma_Control_Signature_Bytes;

   procedure Lemma_Control_Digest_Bytes
     (Bytes : Control_Bytes; Offset : Natural; Value : Digest)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset <= Control_Bytes'Length - Digest'Length and then
       Control_Digest (Bytes, Offset) = Value,
     Post => (for all I in Digest'Range => Bytes (Offset + I) = Value (I))
   is
   begin
      null;
   end Lemma_Control_Digest_Bytes;

   procedure Lemma_Permit_Digest_Value_At
     (Bytes : Permit_Bytes; Value : Digest; Offset : Natural; K : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset <= Permit_Bytes'Length - Digest'Length and then
       K in Offset + 1 .. Offset + Digest'Length and then
       Permit_Digest (Bytes, Offset) = Value,
     Post => Bytes (K) = Value (K - Offset)
   is
   begin
      pragma Assert (K - Offset in Digest'Range);
      pragma Assert (Permit_Digest (Bytes, Offset) (K - Offset) = Value (K - Offset));
      pragma Assert (Offset + (K - Offset) = K);
   end Lemma_Permit_Digest_Value_At;

   procedure Lemma_Permit_Signature_Value_At
     (Bytes : Permit_Bytes; Value : Signature_Bytes; K : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => K in 776 + 1 .. 776 + Signature_Bytes'Length and then
       Permit_Signature (Bytes) = Value,
     Post => Bytes (K) = Value (K - 776)
   is
   begin
      pragma Assert (K - 776 in Signature_Bytes'Range);
      pragma Assert (Permit_Signature (Bytes) (K - 776) = Value (K - 776));
      pragma Assert (776 + (K - 776) = K);
   end Lemma_Permit_Signature_Value_At;

   procedure Lemma_Control_Digest_Value_At
     (Bytes : Control_Bytes; Value : Digest; Offset : Natural; K : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset <= Control_Bytes'Length - Digest'Length and then
       K in Offset + 1 .. Offset + Digest'Length and then
       Control_Digest (Bytes, Offset) = Value,
     Post => Bytes (K) = Value (K - Offset)
   is
   begin
      pragma Assert (K - Offset in Digest'Range);
      pragma Assert (Control_Digest (Bytes, Offset) (K - Offset) = Value (K - Offset));
      pragma Assert (Offset + (K - Offset) = K);
   end Lemma_Control_Digest_Value_At;

   procedure Lemma_Control_Signature_Value_At
     (Bytes : Control_Bytes; Value : Signature_Bytes; K : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => K in 288 + 1 .. 288 + Signature_Bytes'Length and then
       Control_Signature (Bytes) = Value,
     Post => Bytes (K) = Value (K - 288)
   is
   begin
      pragma Assert (K - 288 in Signature_Bytes'Range);
      pragma Assert (Control_Signature (Bytes) (K - 288) = Value (K - 288));
      pragma Assert (288 + (K - 288) = K);
   end Lemma_Control_Signature_Value_At;

   procedure Lemma_Permit_Signature_Constant (Bytes : Permit_Bytes)
   with Ghost, Global => null, Always_Terminates,
     Pre => Permit_Signature (Bytes) = Signature_Bytes'(others => 255),
     Post => (for all K in 777 .. 840 => Bytes (K) = 255) and then
       (for all I in Signature_Bytes'Range => Bytes (776 + I) = 255)
   is
      Value : constant Signature_Bytes := [others => 255];
   begin
      for K in 777 .. 840 loop
         Lemma_Permit_Signature_Value_At (Bytes, Value, K);
         pragma Assert (Bytes (K) = 255);
         pragma Loop_Invariant (for all J in 777 .. K => Bytes (J) = 255);
         pragma Loop_Variant (Decreases => 840 - K);
      end loop;
      for I in Signature_Bytes'Range loop
         Lemma_Permit_Signature_Value_At (Bytes, Value, 776 + I);
         pragma Assert (Bytes (776 + I) = 255);
         pragma Loop_Invariant
           (for all J in Signature_Bytes'First .. I => Bytes (776 + J) = 255);
         pragma Loop_Variant (Decreases => Signature_Bytes'Last - I);
      end loop;
   end Lemma_Permit_Signature_Constant;

   procedure Lemma_Control_Signature_Constant (Bytes : Control_Bytes)
   with Ghost, Global => null, Always_Terminates,
     Pre => Control_Signature (Bytes) = Signature_Bytes'(others => 255),
     Post => (for all K in 289 .. 352 => Bytes (K) = 255) and then
       (for all I in Signature_Bytes'Range => Bytes (288 + I) = 255)
   is
      Value : constant Signature_Bytes := [others => 255];
   begin
      for K in 289 .. 352 loop
         Lemma_Control_Signature_Value_At (Bytes, Value, K);
         pragma Assert (Bytes (K) = 255);
         pragma Loop_Invariant (for all J in 289 .. K => Bytes (J) = 255);
         pragma Loop_Variant (Decreases => 352 - K);
      end loop;
      for I in Signature_Bytes'Range loop
         Lemma_Control_Signature_Value_At (Bytes, Value, 288 + I);
         pragma Assert (Bytes (288 + I) = 255);
         pragma Loop_Invariant
           (for all J in Signature_Bytes'First .. I => Bytes (288 + J) = 255);
         pragma Loop_Variant (Decreases => Signature_Bytes'Last - I);
      end loop;
   end Lemma_Control_Signature_Constant;

   procedure Lemma_Maximal_Content_Bytes (Bytes : Permit_Bytes)
   with Ghost, Global => null, Always_Terminates,
     Pre => Permit_Digest (Bytes, 368) = Filled (255) and then
       Permit_Digest (Bytes, 400) = Filled (255) and then
       Permit_Digest (Bytes, 464) = Filled (255) and then
       Permit_Digest (Bytes, 496) = Filled (255) and then
       Permit_Signature (Bytes) = Signature_Bytes'(others => 255),
     Post => (for all I in 369 .. 432 => Bytes (I) = 255) and then
       (for all I in 465 .. 528 => Bytes (I) = 255) and then
       (for all I in 777 .. 840 => Bytes (I) = 255)
   is
   begin
      for K in 369 .. 432 loop
         if K <= 400 then
            Lemma_Permit_Digest_Value_At (Bytes, Filled (255), 368, K);
         else
            Lemma_Permit_Digest_Value_At (Bytes, Filled (255), 400, K);
         end if;
         pragma Assert (Bytes (K) = 255);
         pragma Loop_Invariant (for all J in 369 .. K => Bytes (J) = 255);
         pragma Loop_Variant (Decreases => 432 - K);
      end loop;
      for K in 465 .. 528 loop
         if K <= 496 then
            Lemma_Permit_Digest_Value_At (Bytes, Filled (255), 464, K);
         else
            Lemma_Permit_Digest_Value_At (Bytes, Filled (255), 496, K);
         end if;
         pragma Assert (Bytes (K) = 255);
         pragma Loop_Invariant (for all J in 465 .. K => Bytes (J) = 255);
         pragma Loop_Variant (Decreases => 528 - K);
      end loop;
      Lemma_Permit_Signature_Constant (Bytes);
   end Lemma_Maximal_Content_Bytes;

   procedure Check_Signature_Separation with Global => null, Always_Terminates is
      Permit : constant Permit_Record :=
        (Expected_Permit with delta Signature => [others => 255]);
      Control : constant Control_Record :=
        (Expected_Control with delta Signature => [others => 255]);
      P_Bytes : Permit_Bytes;
      C_Bytes : Control_Bytes;
      Permit_Snapshot : constant Permit_Record := Permit;
      Control_Snapshot : constant Control_Record := Control;
   begin
      pragma Assert (Same_Permit_Content (Permit, Expected_Permit));
      pragma Assert (Permit /= Expected_Permit);
      pragma Assert (Same_Control_Bindings (Control, Expected_Control));
      pragma Assert (Same_Control_Content (Control, Expected_Control));
      pragma Assert (Control /= Expected_Control);
      Encode_Permit (Permit, P_Bytes);
      Encode_Control (Control, C_Bytes);
      Lemma_Permit_Signature_Bytes (P_Bytes, Permit.Signature);
      Lemma_Control_Signature_Bytes (C_Bytes, Control.Signature);
      Lemma_Permit_Signature_Constant (P_Bytes);
      Lemma_Control_Signature_Constant (C_Bytes);
      pragma Assert (P_Bytes /= Canonical_Permit and then
        (for all I in Signature_Bytes'Range => P_Bytes (776 + I) = 255));
      pragma Assert (C_Bytes /= Canonical_Control and then
        (for all I in Signature_Bytes'Range => C_Bytes (288 + I) = 255));
      pragma Assert (Permit = Permit_Snapshot and then Control = Control_Snapshot);
      Check_Permit_Record (Permit);
      Check_Control_Record (Control);
   end Check_Signature_Separation;

   procedure Check_Control_Content_Maximum
   with Global => null, Always_Terminates is
      Value : constant Control_Record := (Expected_Control with delta
        Bindings => (Expected_Control.Bindings with delta
          Permit_Signed_Digest => Filled (255)), Signature => [others => 255]);
      Snapshot : constant Control_Record := Value;
      Bytes : Control_Bytes;
      Item : Control_Record;
      Status : Decode_Status;
   begin
      Encode_Control (Value, Bytes);
      Lemma_Control_Digest_Bytes (Bytes, 112, Value.Bindings.Permit_Signed_Digest);
      Lemma_Control_Signature_Bytes (Bytes, Value.Signature);
      for K in 113 .. 144 loop
         Lemma_Control_Digest_Value_At (Bytes, Filled (255), 112, K);
         pragma Assert (Bytes (K) = 255);
         pragma Loop_Invariant (for all J in 113 .. K => Bytes (J) = 255);
         pragma Loop_Variant (Decreases => 144 - K);
      end loop;
      Lemma_Control_Signature_Constant (Bytes);
      pragma Assert ((for all I in 113 .. 144 => Bytes (I) = 255) and then
        (for all I in 289 .. 352 => Bytes (I) = 255));
      declare
         Bytes_Snapshot : constant Control_Bytes := Bytes;
      begin
         Decode_Control (Bytes, 352, Status, Item);
         pragma Assert (Status = Decoded and then Item = Snapshot);
         pragma Assert (Bytes = Bytes_Snapshot and then Value = Snapshot);
      end;
   end Check_Control_Content_Maximum;

   procedure Check_Control_State_Comparisons
   with Global => null, Always_Terminates is
      Epoch_Only : constant Control_Record := (Expected_Control with delta Epoch => 1);
      State_Only : constant Control_Record := (Expected_Control with delta State => Disabled);
      Epoch_Snapshot : constant Control_Record := Epoch_Only;
      State_Snapshot : constant Control_Record := State_Only;
      Expected_Snapshot : constant Control_Record := Expected_Control;
   begin
      pragma Assert (Same_Control_Bindings (Epoch_Only, Expected_Control));
      pragma Assert (Same_Control_Bindings (State_Only, Expected_Control));
      pragma Assert (not Same_Control_Content (Epoch_Only, Expected_Control));
      pragma Assert (not Same_Control_Content (State_Only, Expected_Control));
      pragma Assert (not Valid_Control_Record (Epoch_Only));
      pragma Assert (not Valid_Control_Record (State_Only));
      pragma Assert (not Declared_Disable_Step (Expected_Control, Epoch_Only));
      pragma Assert (not Declared_Disable_Step (Expected_Control, State_Only));
      pragma Assert (Epoch_Only = Epoch_Snapshot and then State_Only = State_Snapshot
        and then Expected_Control = Expected_Snapshot);
   end Check_Control_State_Comparisons;

   procedure Check_Maximal_Record with Global => null, Always_Terminates is
      Value : constant Permit_Record := (Expected_Permit with delta
        Content => (Expected_Permit.Content with delta
          Operation => (Expected_Permit.Content.Operation with delta
            Publication_Subject_UID => Subject_UID'Last,
            Before_Generation => Generation'Last - 1,
            Target_Generation => Generation'Last,
            Logical_Payload_Length => Payload_Count'Last,
            Predecessor_Receipt => Filled (255), Payload_Digest => Filled (255)),
          Historical_Publish_Digest => Filled (255),
          Predecessor_State_Digest => Filled (255)),
        Signature => [others => 255]);
      Snapshot : constant Permit_Record := Value;
      Bytes : Permit_Bytes;
      Item : Permit_Record;
      Status : Decode_Status;
   begin
      pragma Assert (Valid_Permit_Record (Value));
      Encode_Permit (Value, Bytes);
      pragma Assert ((for all I in 433 .. 436 => Bytes (I) = 0) and then
        (for all I in 437 .. 440 => Bytes (I) = 255));
      pragma Assert (Bytes (441) = 127 and then Bytes (448) = 254 and then
        Bytes (449) = 127 and then Bytes (456) = 255);
      pragma Assert (Bytes (463) = 16 and then Bytes (464) = 0);
      Lemma_Permit_Digest_Bytes (Bytes, 368, Value.Content.Operation.Predecessor_Receipt);
      Lemma_Permit_Digest_Bytes (Bytes, 400, Value.Content.Operation.Payload_Digest);
      Lemma_Permit_Digest_Bytes (Bytes, 464, Value.Content.Historical_Publish_Digest);
      Lemma_Permit_Digest_Bytes (Bytes, 496, Value.Content.Predecessor_State_Digest);
      Lemma_Permit_Signature_Bytes (Bytes, Value.Signature);
      Lemma_Maximal_Content_Bytes (Bytes);
      pragma Assert
        ((for all I in 369 .. 432 => Bytes (I) = 255) and then
         (for all I in 465 .. 528 => Bytes (I) = 255) and then
         (for all I in 777 .. 840 => Bytes (I) = 255));
      declare
         Bytes_Snapshot : constant Permit_Bytes := Bytes;
      begin
         Decode_Permit (Bytes, 840, Status, Item);
         pragma Assert (Status = Decoded and then Item = Snapshot);
         pragma Assert (Bytes = Bytes_Snapshot and then Value = Snapshot);
      end;
   end Check_Maximal_Record;
begin
   Check_Operation_Relation_Equivalence (Canonical_Permit, Expected_Operation);
   Check_Operation_Relation_Equivalence ([others => 0], Empty_Operation);
   Check_Operation_Relation_Equivalence ([others => 255], Empty_Operation);
   Check_Literal_Permit;
   Check_Literal_Controls;
   Check_Lengths;
   Check_Envelope_Bytes;
   Check_Identities;
   Check_Content_Bytes;
   Check_Raw_Scalar_Bytes;
   Check_Scalar_Boundaries;
   Check_Precedence;
   Check_Material_Comparisons;
   Check_Declared_Digest (Zero_Digest);
   Check_Declared_Digest (Filled (255));
   Check_Signature_Separation;
   Check_Control_Content_Maximum;
   Check_Control_State_Comparisons;
   Check_Maximal_Record;
end Recovery_Permit_Wire_Tests;
