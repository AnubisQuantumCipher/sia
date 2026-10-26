package body SIA_Recovery_Records with SPARK_Mode is

   function Permit_Signature (Bytes : Permit_Bytes) return Signature_Bytes is
      Result : constant Signature_Bytes :=
        [for I in Signature_Bytes'Range => Bytes (776 + I)];
   begin
      pragma Assert
        (for all I in Signature_Bytes'Range =>
          Result (I) = Bytes (776 + I));
      pragma Assert
        (for all J in Digest'Range =>
          Result (J) = Bytes (776 + J) and then
          Result (Digest'Length + J) = Bytes (776 + Digest'Length + J));
      return Result;
   end Permit_Signature;

   function Control_Signature (Bytes : Control_Bytes) return Signature_Bytes is
      Result : constant Signature_Bytes :=
        [for I in Signature_Bytes'Range => Bytes (288 + I)];
   begin
      pragma Assert
        (for all I in Signature_Bytes'Range =>
          Result (I) = Bytes (288 + I));
      pragma Assert
        (for all J in Digest'Range =>
          Result (J) = Bytes (288 + J) and then
          Result (Digest'Length + J) = Bytes (288 + Digest'Length + J));
      return Result;
   end Control_Signature;

   procedure Put_Permit_Digest
     (Bytes : in out Permit_Bytes; Offset : Natural; Value : Digest)
   with Global => null, Always_Terminates,
     Depends => (Bytes => (Bytes, Offset, Value)),
     Pre => Offset <= Permit_Bytes'Length - Digest'Length,
     Post => Permit_Digest (Bytes, Offset) = Value and then
       (for all J in Permit_Bytes'Range =>
         (if J not in Offset + 1 .. Offset + Digest'Length then
            Bytes (J) = Bytes'Old (J)))
   is
   begin
      for I in Digest'Range loop
         Bytes (Offset + I) := Value (I);
         pragma Loop_Invariant
           (for all J in Digest'First .. I => Bytes (Offset + J) = Value (J));
         pragma Loop_Invariant
           (for all J in Permit_Bytes'Range =>
             (if J not in Offset + 1 .. Offset + I then
                Bytes (J) = Bytes'Loop_Entry (J)));
         pragma Loop_Variant (Decreases => Digest'Last - I);
      end loop;
   end Put_Permit_Digest;

   procedure Put_Permit_Word
     (Bytes : in out Permit_Bytes; Offset : Natural; Value : Generation)
   with Global => null, Always_Terminates,
     Depends => (Bytes => (Bytes, Offset, Value)),
     Pre => Offset <= Permit_Bytes'Length - Word'Length,
     Post => Permit_Word (Bytes, Offset) = Generation_Bytes (Value) and then
       (for all J in Permit_Bytes'Range =>
         (if J not in Offset + 1 .. Offset + Word'Length then
            Bytes (J) = Bytes'Old (J)))
   is
      Data : constant Word := Generation_Bytes (Value);
   begin
      for I in Word'Range loop
         Bytes (Offset + I) := Data (I);
         pragma Loop_Invariant
           (for all J in Word'First .. I => Bytes (Offset + J) = Data (J));
         pragma Loop_Invariant
           (for all J in Permit_Bytes'Range =>
             (if J not in Offset + 1 .. Offset + I then
                Bytes (J) = Bytes'Loop_Entry (J)));
         pragma Loop_Variant (Decreases => Word'Last - I);
      end loop;
   end Put_Permit_Word;

   procedure Put_Permit_Signature
     (Bytes : in out Permit_Bytes; Value : Signature_Bytes)
   with Global => null, Always_Terminates, Depends => (Bytes => (Bytes, Value)),
     Post => Permit_Signature (Bytes) = Value and then
       (for all J in 1 .. 776 => Bytes (J) = Bytes'Old (J))
   is
   begin
      for I in Digest'Range loop
         Bytes (776 + I) := Value (I);
         Bytes (776 + Digest'Length + I) := Value (Digest'Length + I);
         pragma Loop_Invariant
           (for all J in Digest'First .. I =>
             Bytes (776 + J) = Value (J) and then
             Bytes (776 + Digest'Length + J) = Value (Digest'Length + J));
         pragma Loop_Invariant
           (for all J in Permit_Bytes'Range =>
             (if J not in 776 + 1 .. 776 + I and then
                 J not in 776 + Digest'Length + 1 .. 776 + Digest'Length + I
              then Bytes (J) = Bytes'Loop_Entry (J)));
         pragma Loop_Variant (Decreases => Digest'Last - I);
      end loop;
   end Put_Permit_Signature;

   procedure Put_Permit_Prefix (Bytes : in out Permit_Bytes)
   with Global => null, Always_Terminates, Depends => (Bytes => Bytes),
     Post => Permit_Envelope_Valid (Bytes) and then
       (for all J in 17 .. Permit_Bytes'Last => Bytes (J) = Bytes'Old (J))
   is
   begin
      for I in Word'Range loop
         Bytes (I) := Magic (I);
         pragma Loop_Invariant
           (for all J in Word'First .. I => Bytes (J) = Magic (J));
         pragma Loop_Invariant
           (for all J in Permit_Bytes'Range =>
             (if J not in 1 .. I then Bytes (J) = Bytes'Loop_Entry (J)));
         pragma Loop_Variant (Decreases => Word'Last - I);
      end loop;
      Bytes (9) := 1;
      Bytes (10) := 1;
      Bytes (11) := 0;
      Bytes (12) := 0;
      Bytes (13) := 0;
      Bytes (14) := 0;
      Bytes (15) := 3;
      Bytes (16) := 72;
   end Put_Permit_Prefix;

   procedure Put_Control_Digest
     (Bytes : in out Control_Bytes; Offset : Natural; Value : Digest)
   with Global => null, Always_Terminates,
     Depends => (Bytes => (Bytes, Offset, Value)),
     Pre => Offset <= Control_Bytes'Length - Digest'Length,
     Post => Control_Digest (Bytes, Offset) = Value and then
       (for all J in Control_Bytes'Range =>
         (if J not in Offset + 1 .. Offset + Digest'Length then
            Bytes (J) = Bytes'Old (J)))
   is
   begin
      for I in Digest'Range loop
         Bytes (Offset + I) := Value (I);
         pragma Loop_Invariant
           (for all J in Digest'First .. I => Bytes (Offset + J) = Value (J));
         pragma Loop_Invariant
           (for all J in Control_Bytes'Range =>
             (if J not in Offset + 1 .. Offset + I then
                Bytes (J) = Bytes'Loop_Entry (J)));
         pragma Loop_Variant (Decreases => Digest'Last - I);
      end loop;
   end Put_Control_Digest;

   procedure Put_Control_Word
     (Bytes : in out Control_Bytes; Offset : Natural; Value : Generation)
   with Global => null, Always_Terminates,
     Depends => (Bytes => (Bytes, Offset, Value)),
     Pre => Offset <= Control_Bytes'Length - Word'Length,
     Post => Control_Word (Bytes, Offset) = Generation_Bytes (Value) and then
       (for all J in Control_Bytes'Range =>
         (if J not in Offset + 1 .. Offset + Word'Length then
            Bytes (J) = Bytes'Old (J)))
   is
      Data : constant Word := Generation_Bytes (Value);
   begin
      for I in Word'Range loop
         Bytes (Offset + I) := Data (I);
         pragma Loop_Invariant
           (for all J in Word'First .. I => Bytes (Offset + J) = Data (J));
         pragma Loop_Invariant
           (for all J in Control_Bytes'Range =>
             (if J not in Offset + 1 .. Offset + I then
                Bytes (J) = Bytes'Loop_Entry (J)));
         pragma Loop_Variant (Decreases => Word'Last - I);
      end loop;
   end Put_Control_Word;

   procedure Put_Control_Signature
     (Bytes : in out Control_Bytes; Value : Signature_Bytes)
   with Global => null, Always_Terminates, Depends => (Bytes => (Bytes, Value)),
     Post => Control_Signature (Bytes) = Value and then
       (for all J in 1 .. 288 => Bytes (J) = Bytes'Old (J))
   is
   begin
      for I in Digest'Range loop
         Bytes (288 + I) := Value (I);
         Bytes (288 + Digest'Length + I) := Value (Digest'Length + I);
         pragma Loop_Invariant
           (for all J in Digest'First .. I =>
             Bytes (288 + J) = Value (J) and then
             Bytes (288 + Digest'Length + J) = Value (Digest'Length + J));
         pragma Loop_Invariant
           (for all J in Control_Bytes'Range =>
             (if J not in 288 + 1 .. 288 + I and then
                 J not in 288 + Digest'Length + 1 .. 288 + Digest'Length + I
              then Bytes (J) = Bytes'Loop_Entry (J)));
         pragma Loop_Variant (Decreases => Digest'Last - I);
      end loop;
   end Put_Control_Signature;

   procedure Put_Control_Prefix (Bytes : in out Control_Bytes)
   with Global => null, Always_Terminates, Depends => (Bytes => Bytes),
     Post => Control_Envelope_Valid (Bytes) and then
       (for all J in 17 .. Control_Bytes'Last => Bytes (J) = Bytes'Old (J))
   is
   begin
      for I in Word'Range loop
         Bytes (I) := Magic (I);
         pragma Loop_Invariant
           (for all J in Word'First .. I => Bytes (J) = Magic (J));
         pragma Loop_Invariant
           (for all J in Control_Bytes'Range =>
             (if J not in 1 .. I then Bytes (J) = Bytes'Loop_Entry (J)));
         pragma Loop_Variant (Decreases => Word'Last - I);
      end loop;
      Bytes (9) := 2;
      Bytes (10) := 1;
      Bytes (11) := 0;
      Bytes (12) := 0;
      Bytes (13) := 0;
      Bytes (14) := 0;
      Bytes (15) := 1;
      Bytes (16) := 96;
   end Put_Control_Prefix;

   function Operation_Value (Bytes : Permit_Bytes) return Operation_Fields is
     (Fixture => Permit_Digest (Bytes, 80),
      Transaction => Permit_Digest (Bytes, 112),
      Protocol => Permit_Digest (Bytes, 144),
      Publication_Issuer => Permit_Digest (Bytes, 176),
      Publication_Key => Permit_Digest (Bytes, 208),
      Publication_Clock => Permit_Digest (Bytes, 240),
      Publication_Boot => Permit_Digest (Bytes, 272),
      Publication_Service => Permit_Digest (Bytes, 304),
      Publication_Capability => Permit_Digest (Bytes, 336),
      Predecessor_Receipt => Permit_Digest (Bytes, 368),
      Payload_Digest => Permit_Digest (Bytes, 400),
      Publication_Subject_UID => Subject_UID (Word_Value (Permit_Word (Bytes, 432))),
      Before_Generation => Word_Value (Permit_Word (Bytes, 440)),
      Target_Generation => Word_Value (Permit_Word (Bytes, 448)),
      Logical_Payload_Length => Payload_Count (Word_Value (Permit_Word (Bytes, 456))))
   with Global => null, Pre => Permit_Scalars_Valid (Bytes),
     Post => Operation_Decoded_As (Bytes, Operation_Value'Result);

   function Signer_Value (Bytes : Permit_Bytes; Offset : Natural)
      return Signer_Assignment is
     (Issuer => Permit_Digest (Bytes, Offset),
      Key => Permit_Digest (Bytes, Offset + 32), Profile => Bytes (Offset + 65))
   with Global => null, Pre => Offset in 560 | 632 | 704,
     Post => Signer_Value'Result.Issuer = Permit_Digest (Bytes, Offset) and then
       Signer_Value'Result.Key = Permit_Digest (Bytes, Offset + 32) and then
       Signer_Value'Result.Profile = Bytes (Offset + 65);

   function Bindings_Value (Bytes : Control_Bytes) return Control_Bindings is
     (Issuer => Control_Digest (Bytes, 16),
      Key => Control_Digest (Bytes, 48),
      Fixture => Control_Digest (Bytes, 80),
      Permit_Signed_Digest => Control_Digest (Bytes, 112),
      Recovery_Policy => Control_Digest (Bytes, 144),
      Control_Policy => Control_Digest (Bytes, 176),
      Provider_Id => Control_Digest (Bytes, 208),
      Anchor_Namespace => Control_Digest (Bytes, 240))
   with Global => null,
     Post => Control_Bindings_Decoded_As (Bytes, Bindings_Value'Result);

   procedure Lemma_UID_Word (UID : Subject_UID; Bytes : Word)
   with Ghost, Global => null, Always_Terminates,
     Pre => Bytes = Generation_Bytes (UID),
     Post => (for all I in 1 .. 4 => Bytes (I) = 0) and then
       Word_Value (Bytes) = UID
   is
   begin
      null;
   end Lemma_UID_Word;

   procedure Lemma_Permit_Scalar_Validity
     (Bytes : Permit_Bytes; UID : Subject_UID;
      Before, Target : Generation; Length : Payload_Count)
   with Ghost, Global => null, Always_Terminates,
     Pre => Operation_Scalars_Decoded_As
       (Permit_Word (Bytes, 432), Permit_Word (Bytes, 440),
        Permit_Word (Bytes, 448), Permit_Word (Bytes, 456),
        UID, Before, Target, Length),
     Post => Permit_Scalars_Valid (Bytes)
   is
   begin
      null;
   end Lemma_Permit_Scalar_Validity;

   procedure Put_Operation_Scalars
     (Bytes : in out Permit_Bytes; UID : Subject_UID;
      Before, Target : Generation; Length : Payload_Count)
   with Global => null, Always_Terminates,
     Depends => (Bytes => (Bytes, UID, Before, Target, Length)),
     Pre => UID > 0 and then Before < Generation'Last and then
       Target = Before + 1,
     Post => Operation_Scalars_Decoded_As
       (Permit_Word (Bytes, 432), Permit_Word (Bytes, 440),
        Permit_Word (Bytes, 448), Permit_Word (Bytes, 456),
        UID, Before, Target, Length) and then
       Permit_Scalars_Valid (Bytes) and then
       (for all J in Permit_Bytes'Range =>
         (if J not in 433 .. 464 then Bytes (J) = Bytes'Old (J)))
   is
      UID_Word : constant Word := Generation_Bytes (UID) with Ghost;
      Before_Word : constant Word := Generation_Bytes (Before) with Ghost;
      Target_Word : constant Word := Generation_Bytes (Target) with Ghost;
      Length_Word : constant Word := Generation_Bytes (Generation (Length)) with Ghost;
   begin
      Lemma_UID_Word (UID, UID_Word);
      Put_Permit_Word (Bytes, 432, UID);
      pragma Assert (Permit_Word (Bytes, 432) = UID_Word);
      Put_Permit_Word (Bytes, 440, Before);
      pragma Assert (Permit_Word (Bytes, 432) = UID_Word);
      pragma Assert (Permit_Word (Bytes, 440) = Before_Word);
      Put_Permit_Word (Bytes, 448, Target);
      pragma Assert (Permit_Word (Bytes, 432) = UID_Word);
      pragma Assert (Permit_Word (Bytes, 440) = Before_Word);
      pragma Assert (Permit_Word (Bytes, 448) = Target_Word);
      Put_Permit_Word (Bytes, 456, Generation (Length));
      pragma Assert (Permit_Word (Bytes, 432) = UID_Word);
      pragma Assert (Permit_Word (Bytes, 440) = Before_Word);
      pragma Assert (Permit_Word (Bytes, 448) = Target_Word);
      pragma Assert (Permit_Word (Bytes, 456) = Length_Word);
      Lemma_Permit_Scalar_Validity (Bytes, UID, Before, Target, Length);
   end Put_Operation_Scalars;

   procedure Put_Operation (Bytes : in out Permit_Bytes; Item : Operation_Fields)
   with Global => null, Always_Terminates, Depends => (Bytes => (Bytes, Item)),
     Pre => Valid_Operation (Item),
     Post => Operation_Decoded_As (Bytes, Item) and then
       Permit_Scalars_Valid (Bytes) and then
       (for all J in Permit_Bytes'Range =>
         (if J not in 81 .. 464 then Bytes (J) = Bytes'Old (J)))
   is
   begin
      Put_Permit_Digest (Bytes, 80, Item.Fixture);
      Put_Permit_Digest (Bytes, 112, Item.Transaction);
      Put_Permit_Digest (Bytes, 144, Item.Protocol);
      Put_Permit_Digest (Bytes, 176, Item.Publication_Issuer);
      Put_Permit_Digest (Bytes, 208, Item.Publication_Key);
      Put_Permit_Digest (Bytes, 240, Item.Publication_Clock);
      Put_Permit_Digest (Bytes, 272, Item.Publication_Boot);
      Put_Permit_Digest (Bytes, 304, Item.Publication_Service);
      Put_Permit_Digest (Bytes, 336, Item.Publication_Capability);
      Put_Permit_Digest (Bytes, 368, Item.Predecessor_Receipt);
      Put_Permit_Digest (Bytes, 400, Item.Payload_Digest);
      Put_Operation_Scalars
        (Bytes, Item.Publication_Subject_UID, Item.Before_Generation,
         Item.Target_Generation, Item.Logical_Payload_Length);
   end Put_Operation;

   procedure Put_Signer
     (Bytes : in out Permit_Bytes; Offset : Natural; Item : Signer_Assignment)
   with Global => null, Always_Terminates,
     Depends => (Bytes => (Bytes, Offset, Item)),
     Pre => Offset in 560 | 632 | 704 and then Valid_Signer (Item),
     Post => Permit_Role_Valid (Bytes, Offset) and then
       Permit_Digest (Bytes, Offset) = Item.Issuer and then
       Permit_Digest (Bytes, Offset + 32) = Item.Key and then
       Bytes (Offset + 65) = Item.Profile and then
       (for all J in Permit_Bytes'Range =>
         (if J not in Offset + 1 .. Offset + 72 then Bytes (J) = Bytes'Old (J)))
   is
      Data : constant Word := [1 => Item.Profile, others => 0];
   begin
      Put_Permit_Digest (Bytes, Offset, Item.Issuer);
      Put_Permit_Digest (Bytes, Offset + 32, Item.Key);
      for I in Word'Range loop
         Bytes ((Offset + 64) + I) := Data (I);
         pragma Loop_Invariant
           (for all J in Word'First .. I => Bytes ((Offset + 64) + J) = Data (J));
         pragma Loop_Invariant
           (for all J in Permit_Bytes'Range =>
             (if J not in Offset + 65 .. (Offset + 64) + I then
                Bytes (J) = Bytes'Loop_Entry (J)));
         pragma Loop_Variant (Decreases => Word'Last - I);
      end loop;
   end Put_Signer;

   procedure Build_Decoded_Permit
     (Bytes : Permit_Bytes; Item : out Permit_Record)
   with Global => null, Always_Terminates,
     Depends => (Item => Bytes),
     Pre => Check_Permit (Bytes, Permit_Bytes'Length) = Decoded,
     Post => Valid_Permit_Record (Item) and then
       Permit_Decoded_As (Bytes, Item)
   is
   begin
      pragma Assert
        (for all I in 1 .. 4 => Bytes (432 + I) = 0);
      Item :=
        (Content =>
          (Issuer => Permit_Digest (Bytes, 16), Key => Permit_Digest (Bytes, 48),
           Operation => Operation_Value (Bytes),
           Historical_Publish_Digest => Permit_Digest (Bytes, 464),
           Predecessor_State_Digest => Permit_Digest (Bytes, 496),
           Recovery_Policy => Permit_Digest (Bytes, 528),
           Intent_Signer => Signer_Value (Bytes, 560),
           Receipt_Signer => Signer_Value (Bytes, 632),
           State_Signer => Signer_Value (Bytes, 704)),
         Signature => Permit_Signature (Bytes));
   end Build_Decoded_Permit;

   procedure Decode_Permit
     (Bytes : Permit_Bytes; Observed_Length : Natural;
      Status : out Decode_Status; Item : out Permit_Record)
   is
   begin
      Item := Empty_Permit;
      Status := Check_Permit (Bytes, Observed_Length);
      if Status /= Decoded then
         return;
      end if;
      Build_Decoded_Permit (Bytes, Item);
   end Decode_Permit;

   procedure Decode_Control
     (Bytes : Control_Bytes; Observed_Length : Natural;
      Status : out Decode_Status; Item : out Control_Record)
   is
   begin
      Item := Empty_Control;
      Status := Check_Control (Bytes, Observed_Length);
      if Status /= Decoded then
         return;
      end if;
      Item :=
        (Bindings => Bindings_Value (Bytes),
         Epoch => Control_Epoch (Word_Value (Control_Word (Bytes, 272))),
         State => (if Bytes (281) = 0 then Enabled else Disabled),
         Signature => Control_Signature (Bytes));
   end Decode_Control;

   procedure Lemma_Permit_Word_Equal
     (Left, Right : Permit_Bytes; Offset : Natural)
   with Ghost, Global => null, Always_Terminates,
     Pre => Offset <= Permit_Bytes'Length - Word'Length and then
       (for all I in Word'Range => Left (Offset + I) = Right (Offset + I)),
     Post => Permit_Word (Left, Offset) = Permit_Word (Right, Offset)
   is
   begin
      null;
   end Lemma_Permit_Word_Equal;

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

   procedure Lemma_Permit_First_Roles_Preserved (Left, Right : Permit_Bytes)
   with Ghost, Global => null, Always_Terminates,
     Pre => (for all J in 561 .. 704 => Left (J) = Right (J)),
     Post => Permit_Role_Valid (Left, 560) = Permit_Role_Valid (Right, 560) and then
       Permit_Role_Valid (Left, 632) = Permit_Role_Valid (Right, 632)
   is
   begin
      Lemma_Permit_Role_Preserved (Left, Right, 560);
      Lemma_Permit_Role_Preserved (Left, Right, 632);
   end Lemma_Permit_First_Roles_Preserved;

   procedure Lemma_Permit_Signers_Preserved (Left, Right : Permit_Bytes)
   with Ghost, Global => null, Always_Terminates,
     Pre => (for all J in 561 .. 776 => Left (J) = Right (J)),
     Post => Permit_Role_Valid (Left, 560) = Permit_Role_Valid (Right, 560) and then
       Permit_Role_Valid (Left, 632) = Permit_Role_Valid (Right, 632) and then
       Permit_Role_Valid (Left, 704) = Permit_Role_Valid (Right, 704)
   is
   begin
      Lemma_Permit_First_Roles_Preserved (Left, Right);
      Lemma_Permit_Role_Preserved (Left, Right, 704);
   end Lemma_Permit_Signers_Preserved;

   procedure Lemma_Permit_Prefix
     (Left, Right : Permit_Bytes; Item : Operation_Fields)
   with Ghost, Global => null, Always_Terminates,
     Pre => (for all J in 1 .. 464 => Left (J) = Right (J)),
     Post =>
       Permit_Envelope_Valid (Left) = Permit_Envelope_Valid (Right) and then
       Permit_Scalars_Valid (Left) = Permit_Scalars_Valid (Right) and then
       Operation_Decoded_As (Left, Item) = Operation_Decoded_As (Right, Item) and then
       Permit_Digest (Left, 16) = Permit_Digest (Right, 16) and then
       Permit_Digest (Left, 48) = Permit_Digest (Right, 48)
   is
   begin
      pragma Assert
        (Permit_Envelope_Valid (Left) = Permit_Envelope_Valid (Right));
      Lemma_Permit_Word_Equal (Left, Right, 432);
      Lemma_Permit_Word_Equal (Left, Right, 440);
      Lemma_Permit_Word_Equal (Left, Right, 448);
      Lemma_Permit_Word_Equal (Left, Right, 456);
      pragma Assert (Permit_Scalars_Valid (Left) = Permit_Scalars_Valid (Right));
      Lemma_Permit_Digest_Equal (Left, Right, 16);
      Lemma_Permit_Digest_Equal (Left, Right, 48);
      Lemma_Permit_Digest_Equal (Left, Right, 80);
      Lemma_Permit_Digest_Equal (Left, Right, 112);
      Lemma_Permit_Digest_Equal (Left, Right, 144);
      Lemma_Permit_Digest_Equal (Left, Right, 176);
      Lemma_Permit_Digest_Equal (Left, Right, 208);
      Lemma_Permit_Digest_Equal (Left, Right, 240);
      Lemma_Permit_Digest_Equal (Left, Right, 272);
      Lemma_Permit_Digest_Equal (Left, Right, 304);
      Lemma_Permit_Digest_Equal (Left, Right, 336);
      Lemma_Permit_Digest_Equal (Left, Right, 368);
      Lemma_Permit_Digest_Equal (Left, Right, 400);
      pragma Assert
        (Operation_Scalars_Decoded_As
           (Permit_Word (Left, 432), Permit_Word (Left, 440),
            Permit_Word (Left, 448), Permit_Word (Left, 456),
            Item.Publication_Subject_UID, Item.Before_Generation,
            Item.Target_Generation, Item.Logical_Payload_Length) =
         Operation_Scalars_Decoded_As
           (Permit_Word (Right, 432), Permit_Word (Right, 440),
            Permit_Word (Right, 448), Permit_Word (Right, 456),
            Item.Publication_Subject_UID, Item.Before_Generation,
            Item.Target_Generation, Item.Logical_Payload_Length));
      pragma Assert
        (Operation_Decoded_As (Left, Item) = Operation_Decoded_As (Right, Item));
   end Lemma_Permit_Prefix;

   procedure Put_Permit_Tail (Bytes : in out Permit_Bytes; Item : Permit_Record)
   with Global => null, Always_Terminates, Depends => (Bytes => (Bytes, Item)),
     Pre => Valid_Permit_Record (Item) and then Permit_Envelope_Valid (Bytes) and then
       Permit_Scalars_Valid (Bytes) and then
       Operation_Decoded_As (Bytes, Item.Content.Operation) and then
       Permit_Digest (Bytes, 16) = Item.Content.Issuer and then
       Permit_Digest (Bytes, 48) = Item.Content.Key,
     Post => Check_Permit (Bytes, Permit_Bytes'Length) = Decoded and then
       Permit_Decoded_As (Bytes, Item) and then
       (for all J in 1 .. 464 => Bytes (J) = Bytes'Old (J))
   is
      Prefix : constant Permit_Bytes := Bytes with Ghost;
   begin
      Put_Permit_Digest (Bytes, 464, Item.Content.Historical_Publish_Digest);
      Put_Permit_Digest (Bytes, 496, Item.Content.Predecessor_State_Digest);
      Put_Permit_Digest (Bytes, 528, Item.Content.Recovery_Policy);
      Lemma_Permit_Prefix (Prefix, Bytes, Item.Content.Operation);
      pragma Assert
        (Permit_Envelope_Valid (Bytes) and then Permit_Scalars_Valid (Bytes) and then
         Permit_Identities_Valid (Bytes));
      Put_Signer (Bytes, 560, Item.Content.Intent_Signer);
      Lemma_Permit_Prefix (Prefix, Bytes, Item.Content.Operation);
      pragma Assert
        (Permit_Envelope_Valid (Bytes) and then Permit_Scalars_Valid (Bytes) and then
         Permit_Identities_Valid (Bytes) and then Permit_Role_Valid (Bytes, 560));
      declare
         Before_Receipt : constant Permit_Bytes := Bytes with Ghost;
      begin
         Put_Signer (Bytes, 632, Item.Content.Receipt_Signer);
         Lemma_Permit_Role_Preserved (Before_Receipt, Bytes, 560);
      end;
      Lemma_Permit_Prefix (Prefix, Bytes, Item.Content.Operation);
      pragma Assert
        (Permit_Envelope_Valid (Bytes) and then Permit_Scalars_Valid (Bytes) and then
         Permit_Identities_Valid (Bytes) and then Permit_Role_Valid (Bytes, 560) and then
         Permit_Role_Valid (Bytes, 632));
      declare
         Before_State : constant Permit_Bytes := Bytes with Ghost;
      begin
         Put_Signer (Bytes, 704, Item.Content.State_Signer);
         Lemma_Permit_First_Roles_Preserved (Before_State, Bytes);
      end;
      Lemma_Permit_Prefix (Prefix, Bytes, Item.Content.Operation);
      pragma Assert (Permit_Envelope_Valid (Bytes) and then Permit_Fields_Valid (Bytes));
      declare
         Before_Signature : constant Permit_Bytes := Bytes with Ghost;
      begin
         Put_Permit_Signature (Bytes, Item.Signature);
         pragma Assert
           (for all J in 529 .. 560 => Before_Signature (J) = Bytes (J));
         Lemma_Permit_Digest_Equal (Before_Signature, Bytes, 528);
         pragma Assert (Permit_Digest (Bytes, 528) /= Zero_Digest);
         pragma Assert
           (for all J in 561 .. 776 => Before_Signature (J) = Bytes (J));
         Lemma_Permit_Signers_Preserved (Before_Signature, Bytes);
      end;
      Lemma_Permit_Prefix (Prefix, Bytes, Item.Content.Operation);
      pragma Assert (Permit_Envelope_Valid (Bytes) and then Permit_Fields_Valid (Bytes));
      pragma Assert (Check_Permit (Bytes, Permit_Bytes'Length) = Decoded);
   end Put_Permit_Tail;

   procedure Encode_Permit (Item : Permit_Record; Bytes : out Permit_Bytes) is
   begin
      Bytes := [others => 0];
      Put_Permit_Prefix (Bytes);
      pragma Assert (Permit_Envelope_Valid (Bytes));
      Put_Permit_Digest (Bytes, 16, Item.Content.Issuer);
      Put_Permit_Digest (Bytes, 48, Item.Content.Key);
      pragma Assert
        (Permit_Envelope_Valid (Bytes) and then
         Permit_Digest (Bytes, 16) /= Zero_Digest and then
         Permit_Digest (Bytes, 48) /= Zero_Digest);
      Put_Operation (Bytes, Item.Content.Operation);
      pragma Assert
        (Permit_Envelope_Valid (Bytes) and then Permit_Scalars_Valid (Bytes) and then
         Permit_Digest (Bytes, 16) /= Zero_Digest and then
         Permit_Digest (Bytes, 48) /= Zero_Digest);
      Put_Permit_Tail (Bytes, Item);
   end Encode_Permit;

   procedure Encode_Control (Item : Control_Record; Bytes : out Control_Bytes) is
   begin
      Bytes := [others => 0];
      Put_Control_Prefix (Bytes);
      Put_Control_Digest (Bytes, 16, Item.Bindings.Issuer);
      Put_Control_Digest (Bytes, 48, Item.Bindings.Key);
      Put_Control_Digest (Bytes, 80, Item.Bindings.Fixture);
      Put_Control_Digest (Bytes, 112, Item.Bindings.Permit_Signed_Digest);
      Put_Control_Digest (Bytes, 144, Item.Bindings.Recovery_Policy);
      Put_Control_Digest (Bytes, 176, Item.Bindings.Control_Policy);
      Put_Control_Digest (Bytes, 208, Item.Bindings.Provider_Id);
      Put_Control_Digest (Bytes, 240, Item.Bindings.Anchor_Namespace);
      Put_Control_Word (Bytes, 272, Generation (Item.Epoch));
      Bytes (281) := (if Item.State = Enabled then 0 else 1);
      Put_Control_Signature (Bytes, Item.Signature);
   end Encode_Control;

   procedure Lemma_Radix_48 (Value : Generation)
   with Ghost, Global => null, Always_Terminates,
     Post =>
       Value / 2 ** 48 =
         (Value / 2 ** 56) * 256 + (Value / 2 ** 48) mod 256
   is
   begin
      null;
   end Lemma_Radix_48;

   procedure Lemma_Radix_40 (Value : Generation)
   with Ghost, Global => null, Always_Terminates,
     Post =>
       Value / 2 ** 40 =
         (Value / 2 ** 48) * 256 + (Value / 2 ** 40) mod 256
   is
   begin
      null;
   end Lemma_Radix_40;

   procedure Lemma_Radix_32 (Value : Generation)
   with Ghost, Global => null, Always_Terminates,
     Post =>
       Value / 2 ** 32 =
         (Value / 2 ** 40) * 256 + (Value / 2 ** 32) mod 256
   is
   begin
      null;
   end Lemma_Radix_32;

   procedure Lemma_Radix_24 (Value : Generation)
   with Ghost, Global => null, Always_Terminates,
     Post =>
       Value / 2 ** 24 =
         (Value / 2 ** 32) * 256 + (Value / 2 ** 24) mod 256
   is
   begin
      null;
   end Lemma_Radix_24;

   procedure Lemma_Radix_16 (Value : Generation)
   with Ghost, Global => null, Always_Terminates,
     Post =>
       Value / 2 ** 16 =
         (Value / 2 ** 24) * 256 + (Value / 2 ** 16) mod 256
   is
   begin
      null;
   end Lemma_Radix_16;

   procedure Lemma_Radix_8 (Value : Generation)
   with Ghost, Global => null, Always_Terminates,
     Post =>
       Value / 2 ** 8 =
         (Value / 2 ** 16) * 256 + (Value / 2 ** 8) mod 256
   is
   begin
      null;
   end Lemma_Radix_8;

   procedure Lemma_Radix_0 (Value : Generation)
   with Ghost, Global => null, Always_Terminates,
     Post =>
       Value =
         (Value / 2 ** 8) * 256 + Value mod 256
   is
   begin
      null;
   end Lemma_Radix_0;

   function Generation_Bytes (Value : Generation) return Word is
      Result : constant Word :=
        ([Digest_Byte ((Value / 2 ** 56) mod 256),
          Digest_Byte ((Value / 2 ** 48) mod 256),
          Digest_Byte ((Value / 2 ** 40) mod 256),
          Digest_Byte ((Value / 2 ** 32) mod 256),
          Digest_Byte ((Value / 2 ** 24) mod 256),
          Digest_Byte ((Value / 2 ** 16) mod 256),
          Digest_Byte ((Value / 2 ** 8) mod 256), Digest_Byte (Value mod 256)]);
   begin
      pragma Assert
        (Result =
        ([Digest_Byte ((Value / 2 ** 56) mod 256),
          Digest_Byte ((Value / 2 ** 48) mod 256),
          Digest_Byte ((Value / 2 ** 40) mod 256),
          Digest_Byte ((Value / 2 ** 32) mod 256),
          Digest_Byte ((Value / 2 ** 24) mod 256),
          Digest_Byte ((Value / 2 ** 16) mod 256),
          Digest_Byte ((Value / 2 ** 8) mod 256), Digest_Byte (Value mod 256)]) );
      pragma Assert (Value / 2 ** 56 = Generation (Result (1)));
      Lemma_Radix_48 (Value);
      pragma Assert
        (Value / 2 ** 48 =
           (Value / 2 ** 56) * 256 + Generation (Result (2)));
      Lemma_Radix_40 (Value);
      pragma Assert
        (Value / 2 ** 40 =
           (Value / 2 ** 48) * 256 + Generation (Result (3)));
      Lemma_Radix_32 (Value);
      pragma Assert
        (Value / 2 ** 32 =
           (Value / 2 ** 40) * 256 + Generation (Result (4)));
      Lemma_Radix_24 (Value);
      pragma Assert
        (Value / 2 ** 24 =
           (Value / 2 ** 32) * 256 + Generation (Result (5)));
      Lemma_Radix_16 (Value);
      pragma Assert
        (Value / 2 ** 16 =
           (Value / 2 ** 24) * 256 + Generation (Result (6)));
      Lemma_Radix_8 (Value);
      pragma Assert
        (Value / 2 ** 8 =
           (Value / 2 ** 16) * 256 + Generation (Result (7)));
      Lemma_Radix_0 (Value);
      pragma Assert
        (Value = (Value / 2 ** 8) * 256 + Generation (Result (8)));
      pragma Assert (Result (1) <= 127);
      pragma Assert (Word_Value (Result) = Value);
      return Result;
   end Generation_Bytes;
end SIA_Recovery_Records;
