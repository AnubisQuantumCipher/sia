with SIA_Policy;

--  Frozen representation only. No signature, currentness or effect authority.
package SIA_Recovery_Records with SPARK_Mode, Pure is
   use SIA_Policy;
   type Permit_Bytes is array (Positive range 1 .. 840) of Digest_Byte;
   type Control_Bytes is array (Positive range 1 .. 352) of Digest_Byte;
   type Signature_Bytes is array (Positive range 1 .. 64) of Digest_Byte;
   type Word is array (Positive range 1 .. 8) of Digest_Byte;
   subtype Subject_UID is Generation range 0 .. 16#FFFF_FFFF#;
   subtype Payload_Count is Natural range 0 .. 4096;
   subtype Control_Epoch is Natural range 0 .. 1;
   type Control_State is (Enabled, Disabled);
   type Decode_Status is
     (Decoded, Length_Refused, Envelope_Refused, Field_Refused, State_Refused);
   Zero_Digest : constant Digest := [others => 0];
   Magic : constant Word := [83, 73, 65, 82, 69, 67, 48, 49];

   type Operation_Fields is record
      Fixture, Transaction, Protocol, Publication_Issuer, Publication_Key,
        Publication_Clock, Publication_Boot, Publication_Service,
        Publication_Capability, Predecessor_Receipt, Payload_Digest : Digest;
      Publication_Subject_UID : Subject_UID;
      Before_Generation, Target_Generation : Generation;
      Logical_Payload_Length : Payload_Count;
   end record;
   type Signer_Assignment is record
      Issuer, Key : Digest;
      Profile : Digest_Byte;
   end record;
   type Permit_Content is record
      Issuer, Key : Digest;
      Operation : Operation_Fields;
      Historical_Publish_Digest, Predecessor_State_Digest, Recovery_Policy : Digest;
      Intent_Signer, Receipt_Signer, State_Signer : Signer_Assignment;
   end record;
   type Permit_Record is record
      Content : Permit_Content;
      Signature : Signature_Bytes;
   end record;
   type Control_Bindings is record
      Issuer, Key, Fixture, Permit_Signed_Digest, Recovery_Policy,
        Control_Policy, Provider_Id, Anchor_Namespace : Digest;
   end record;
   type Control_Record is record
      Bindings : Control_Bindings;
      Epoch : Control_Epoch;
      State : Control_State;
      Signature : Signature_Bytes;
   end record;
   Empty_Operation : constant Operation_Fields :=
     (Fixture | Transaction | Protocol | Publication_Issuer | Publication_Key |
      Publication_Clock | Publication_Boot | Publication_Service |
      Publication_Capability | Predecessor_Receipt | Payload_Digest => [others => 0],
      Publication_Subject_UID => 0, Before_Generation | Target_Generation => 0,
      Logical_Payload_Length => 0);
   Empty_Signer : constant Signer_Assignment :=
     (Issuer | Key => [others => 0], Profile => 0);
   Empty_Permit : constant Permit_Record :=
     (Content =>
       (Issuer | Key => [others => 0],
        Operation =>
          (Fixture | Transaction | Protocol | Publication_Issuer | Publication_Key |
           Publication_Clock | Publication_Boot | Publication_Service |
           Publication_Capability | Predecessor_Receipt | Payload_Digest => [others => 0],
           Publication_Subject_UID => 0, Before_Generation | Target_Generation => 0,
           Logical_Payload_Length => 0),
        Historical_Publish_Digest | Predecessor_State_Digest | Recovery_Policy =>
          [others => 0],
        Intent_Signer | Receipt_Signer | State_Signer =>
          (Issuer | Key => [others => 0], Profile => 0)),
      Signature => [others => 0]);
   Empty_Control : constant Control_Record :=
     (Bindings => (others => [others => 0]), Epoch => 0, State => Enabled,
      Signature => [others => 0]);

   --  Offsets below retain the frozen zero-based table convention.
   function Permit_Digest (Bytes : Permit_Bytes; Offset : Natural)
      return Digest is ([for I in Digest'Range => Bytes (Offset + I)])
   with Global => null,
     Pre => Offset <= Permit_Bytes'Length - Digest'Length,
     Post => (for all I in Digest'Range =>
       Permit_Digest'Result (I) = Bytes (Offset + I));

   function Permit_Word (Bytes : Permit_Bytes; Offset : Natural)
      return Word is ([for I in Word'Range => Bytes (Offset + I)])
   with Global => null,
     Pre => Offset <= Permit_Bytes'Length - Word'Length,
     Post => (for all I in Word'Range =>
       Permit_Word'Result (I) = Bytes (Offset + I));

   function Permit_Signature (Bytes : Permit_Bytes) return Signature_Bytes
   with Global => null,
     Post => (for all I in Signature_Bytes'Range =>
       Permit_Signature'Result (I) = Bytes (776 + I));

   function Control_Digest (Bytes : Control_Bytes; Offset : Natural)
      return Digest is ([for I in Digest'Range => Bytes (Offset + I)])
   with Global => null,
     Pre => Offset <= Control_Bytes'Length - Digest'Length,
     Post => (for all I in Digest'Range =>
       Control_Digest'Result (I) = Bytes (Offset + I));

   function Control_Word (Bytes : Control_Bytes; Offset : Natural)
      return Word is ([for I in Word'Range => Bytes (Offset + I)])
   with Global => null,
     Pre => Offset <= Control_Bytes'Length - Word'Length,
     Post => (for all I in Word'Range =>
       Control_Word'Result (I) = Bytes (Offset + I));

   function Control_Signature (Bytes : Control_Bytes) return Signature_Bytes
   with Global => null,
     Post => (for all I in Signature_Bytes'Range =>
       Control_Signature'Result (I) = Bytes (288 + I));

   --  Inspect every malformed unsigned word before calling this conversion.
   function Word_Value (Bytes : Word) return Generation is
     (((((((Generation (Bytes (1)) * 2 ** 56 +
      Generation (Bytes (2)) * 2 ** 48) +
      Generation (Bytes (3)) * 2 ** 40) +
      Generation (Bytes (4)) * 2 ** 32) +
      Generation (Bytes (5)) * 2 ** 24) +
      Generation (Bytes (6)) * 2 ** 16) +
      Generation (Bytes (7)) * 2 ** 8) + Generation (Bytes (8)))
   with Global => null, Pre => Bytes (1) <= 127;

   function Generation_Bytes (Value : Generation) return Word
   with Global => null,
     Post => Generation_Bytes'Result (1) <= 127 and then
       Word_Value (Generation_Bytes'Result) = Value and then
       Generation_Bytes'Result =
       ([Digest_Byte ((Value / 2 ** 56) mod 256),
         Digest_Byte ((Value / 2 ** 48) mod 256),
         Digest_Byte ((Value / 2 ** 40) mod 256),
         Digest_Byte ((Value / 2 ** 32) mod 256),
         Digest_Byte ((Value / 2 ** 24) mod 256),
         Digest_Byte ((Value / 2 ** 16) mod 256),
         Digest_Byte ((Value / 2 ** 8) mod 256), Digest_Byte (Value mod 256)]);

   function Valid_Operation (Item : Operation_Fields) return Boolean is
     (Item.Fixture /= Zero_Digest and then Item.Transaction /= Zero_Digest and then
      Item.Protocol /= Zero_Digest and then
      Item.Publication_Issuer /= Zero_Digest and then
      Item.Publication_Key /= Zero_Digest and then
      Item.Publication_Clock /= Zero_Digest and then
      Item.Publication_Boot /= Zero_Digest and then
      Item.Publication_Service /= Zero_Digest and then
      Item.Publication_Capability /= Zero_Digest and then
      Item.Publication_Subject_UID > 0 and then
      Item.Before_Generation < Generation'Last and then
      Item.Target_Generation = Item.Before_Generation + 1)
   with Global => null;

   function Valid_Signer (Item : Signer_Assignment) return Boolean is
     (Item.Issuer /= Zero_Digest and then Item.Key /= Zero_Digest and then
      Item.Profile = 1)
   with Global => null;

   function Valid_Permit_Record (Item : Permit_Record) return Boolean is
     (Item.Content.Issuer /= Zero_Digest and then
      Item.Content.Key /= Zero_Digest and then
      Valid_Operation (Item.Content.Operation) and then
      Item.Content.Recovery_Policy /= Zero_Digest and then
      Valid_Signer (Item.Content.Intent_Signer) and then
      Valid_Signer (Item.Content.Receipt_Signer) and then
      Valid_Signer (Item.Content.State_Signer))
   with Global => null;

   function Valid_Control_Record (Item : Control_Record) return Boolean is
     (Item.Bindings.Issuer /= Zero_Digest and then
      Item.Bindings.Key /= Zero_Digest and then
      Item.Bindings.Fixture /= Zero_Digest and then
      Item.Bindings.Recovery_Policy /= Zero_Digest and then
      Item.Bindings.Control_Policy /= Zero_Digest and then
      Item.Bindings.Provider_Id /= Zero_Digest and then
      Item.Bindings.Anchor_Namespace /= Zero_Digest and then
      ((Item.Epoch = 0 and then Item.State = Enabled) or else
       (Item.Epoch = 1 and then Item.State = Disabled)))
   with Global => null;

   function Permit_Envelope_Valid (Bytes : Permit_Bytes) return Boolean is
     ((for all I in Word'Range => Bytes (I) = Magic (I)) and then
      Bytes (9) = 1 and then Bytes (10) = 1 and then
      Bytes (11) = 0 and then Bytes (12) = 0 and then
      (((Generation (Bytes (13)) * 2 ** 24 +
         Generation (Bytes (14)) * 2 ** 16) +
         Generation (Bytes (15)) * 2 ** 8) + Generation (Bytes (16))) = 840)
   with Global => null;

   function Control_Envelope_Valid (Bytes : Control_Bytes) return Boolean is
     ((for all I in Word'Range => Bytes (I) = Magic (I)) and then
      Bytes (9) = 2 and then Bytes (10) = 1 and then
      Bytes (11) = 0 and then Bytes (12) = 0 and then
      (((Generation (Bytes (13)) * 2 ** 24 +
         Generation (Bytes (14)) * 2 ** 16) +
         Generation (Bytes (15)) * 2 ** 8) + Generation (Bytes (16))) = 352)
   with Global => null;

   function Permit_Scalars_Valid (Bytes : Permit_Bytes) return Boolean is
     ((for all I in 1 .. 4 => Bytes (432 + I) = 0) and then
      Word_Value (Permit_Word (Bytes, 432)) > 0 and then
      Bytes (441) <= 127 and then Bytes (449) <= 127 and then
      Bytes (457) <= 127 and then
      Word_Value (Permit_Word (Bytes, 456)) <= Generation (Payload_Count'Last) and then
      Word_Value (Permit_Word (Bytes, 440)) < Generation'Last and then
      Word_Value (Permit_Word (Bytes, 448)) =
        Word_Value (Permit_Word (Bytes, 440)) + 1)
   with Global => null;

   function Permit_Identities_Valid (Bytes : Permit_Bytes) return Boolean is
     (Permit_Digest (Bytes, 16) /= Zero_Digest and
      Permit_Digest (Bytes, 48) /= Zero_Digest and
      Permit_Digest (Bytes, 80) /= Zero_Digest and
      Permit_Digest (Bytes, 112) /= Zero_Digest and
      Permit_Digest (Bytes, 144) /= Zero_Digest and
      Permit_Digest (Bytes, 176) /= Zero_Digest and
      Permit_Digest (Bytes, 208) /= Zero_Digest and
      Permit_Digest (Bytes, 240) /= Zero_Digest and
      Permit_Digest (Bytes, 272) /= Zero_Digest and
      Permit_Digest (Bytes, 304) /= Zero_Digest and
      Permit_Digest (Bytes, 336) /= Zero_Digest and
      Permit_Digest (Bytes, 528) /= Zero_Digest)
   with Global => null;

   function Permit_Role_Valid (Bytes : Permit_Bytes; Offset : Natural)
      return Boolean is
     (Permit_Digest (Bytes, Offset) /= Zero_Digest and then
      Permit_Digest (Bytes, Offset + 32) /= Zero_Digest and then
      Bytes (Offset + 65) = 1 and then
      (for all I in Word'Range =>
        (if I > 1 then Bytes ((Offset + 64) + I) = 0)))
   with Global => null, Pre => Offset in 560 | 632 | 704;

   function Permit_Fields_Valid (Bytes : Permit_Bytes) return Boolean is
     (Permit_Identities_Valid (Bytes) and then Permit_Scalars_Valid (Bytes) and then
      Permit_Role_Valid (Bytes, 560) and then
      Permit_Role_Valid (Bytes, 632) and then Permit_Role_Valid (Bytes, 704))
   with Global => null;

   function Control_Fields_Valid (Bytes : Control_Bytes) return Boolean is
     (Control_Digest (Bytes, 16) /= Zero_Digest and then
      Control_Digest (Bytes, 48) /= Zero_Digest and then
      Control_Digest (Bytes, 80) /= Zero_Digest and then
      Control_Digest (Bytes, 144) /= Zero_Digest and then
      Control_Digest (Bytes, 176) /= Zero_Digest and then
      Control_Digest (Bytes, 208) /= Zero_Digest and then
      Control_Digest (Bytes, 240) /= Zero_Digest and then
      (for all I in Word'Range => (if I > 1 then Bytes (280 + I) = 0)))
   with Global => null;

   function Control_State_Valid (Bytes : Control_Bytes) return Boolean is
     ((for all I in Word'Range => (if I < 8 then Bytes (272 + I) = 0)) and then
      Bytes (280) <= 1 and then Bytes (281) <= 1 and then
      Bytes (280) = Bytes (281))
   with Global => null;

   function Check_Permit (Bytes : Permit_Bytes; Observed_Length : Natural)
      return Decode_Status is
     (if Observed_Length /= Permit_Bytes'Length then Length_Refused
      elsif not Permit_Envelope_Valid (Bytes) then Envelope_Refused
      elsif not Permit_Fields_Valid (Bytes) then Field_Refused else Decoded)
   with Global => null;

   function Check_Control (Bytes : Control_Bytes; Observed_Length : Natural)
      return Decode_Status is
     (if Observed_Length /= Control_Bytes'Length then Length_Refused
      elsif not Control_Envelope_Valid (Bytes) then Envelope_Refused
      elsif not Control_Fields_Valid (Bytes) then Field_Refused
      elsif not Control_State_Valid (Bytes) then State_Refused else Decoded)
   with Global => null;

   --  Total scalar relation: every raw-word guard precedes its conversion.
   --  Digest arrays are deliberately outside this proof boundary.
   function Operation_Scalars_Decoded_As
     (UID_Bytes, Before_Bytes, Target_Bytes, Length_Bytes : Word;
      UID : Subject_UID; Before, Target : Generation; Length : Payload_Count)
      return Boolean is
     ((for all I in 1 .. 4 => UID_Bytes (I) = 0) and then
      Word_Value (UID_Bytes) > 0 and then
      Before_Bytes (1) <= 127 and then Target_Bytes (1) <= 127 and then
      Length_Bytes (1) <= 127 and then
      Word_Value (Length_Bytes) <= Generation (Payload_Count'Last) and then
      Word_Value (Before_Bytes) < Generation'Last and then
      Word_Value (Target_Bytes) = Word_Value (Before_Bytes) + 1 and then
      UID = Word_Value (UID_Bytes) and then
      Before = Word_Value (Before_Bytes) and then
      Target = Word_Value (Target_Bytes) and then
      Generation (Length) = Word_Value (Length_Bytes))
   with Global => null;

   function Operation_Decoded_As
     (Bytes : Permit_Bytes; Item : Operation_Fields) return Boolean is
     (Operation_Scalars_Decoded_As
        (Permit_Word (Bytes, 432), Permit_Word (Bytes, 440),
         Permit_Word (Bytes, 448), Permit_Word (Bytes, 456),
         Item.Publication_Subject_UID, Item.Before_Generation,
         Item.Target_Generation, Item.Logical_Payload_Length) and then
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
      Item.Payload_Digest = Permit_Digest (Bytes, 400)))
   with Global => null;

   function Permit_Signers_Decoded_As
     (Bytes : Permit_Bytes; Item : Permit_Content) return Boolean is
     (Item.Intent_Signer.Issuer = Permit_Digest (Bytes, 560) and then
      Item.Intent_Signer.Key = Permit_Digest (Bytes, 592) and then
      Item.Intent_Signer.Profile = Bytes (625) and then
      Item.Receipt_Signer.Issuer = Permit_Digest (Bytes, 632) and then
      Item.Receipt_Signer.Key = Permit_Digest (Bytes, 664) and then
      Item.Receipt_Signer.Profile = Bytes (697) and then
      Item.State_Signer.Issuer = Permit_Digest (Bytes, 704) and then
      Item.State_Signer.Key = Permit_Digest (Bytes, 736) and then
      Item.State_Signer.Profile = Bytes (769))
   with Global => null;

   function Permit_Decoded_As (Bytes : Permit_Bytes; Item : Permit_Record)
      return Boolean is
     (Check_Permit (Bytes, Permit_Bytes'Length) = Decoded and then
      Valid_Permit_Record (Item) and then
      Item.Content.Issuer = Permit_Digest (Bytes, 16) and then
      Item.Content.Key = Permit_Digest (Bytes, 48) and then
      Operation_Decoded_As (Bytes, Item.Content.Operation) and then
      Item.Content.Historical_Publish_Digest = Permit_Digest (Bytes, 464) and then
      Item.Content.Predecessor_State_Digest = Permit_Digest (Bytes, 496) and then
      Item.Content.Recovery_Policy = Permit_Digest (Bytes, 528) and then
      Permit_Signers_Decoded_As (Bytes, Item.Content) and then
      Item.Signature = Permit_Signature (Bytes))
   with Global => null;

   function Control_Bindings_Decoded_As
     (Bytes : Control_Bytes; Item : Control_Bindings) return Boolean is
     (Item.Issuer = Control_Digest (Bytes, 16) and then
      Item.Key = Control_Digest (Bytes, 48) and then
      Item.Fixture = Control_Digest (Bytes, 80) and then
      Item.Permit_Signed_Digest = Control_Digest (Bytes, 112) and then
      Item.Recovery_Policy = Control_Digest (Bytes, 144) and then
      Item.Control_Policy = Control_Digest (Bytes, 176) and then
      Item.Provider_Id = Control_Digest (Bytes, 208) and then
      Item.Anchor_Namespace = Control_Digest (Bytes, 240))
   with Global => null;

   function Control_Decoded_As (Bytes : Control_Bytes; Item : Control_Record)
      return Boolean is
     (Check_Control (Bytes, Control_Bytes'Length) = Decoded and then
      Valid_Control_Record (Item) and then
      Control_Bindings_Decoded_As (Bytes, Item.Bindings) and then
      Generation (Item.Epoch) = Word_Value (Control_Word (Bytes, 272)) and then
      Item.State = (if Bytes (281) = 0 then Enabled else Disabled) and then
      Item.Signature = Control_Signature (Bytes))
   with Global => null;

   procedure Decode_Permit
     (Bytes : Permit_Bytes; Observed_Length : Natural;
      Status : out Decode_Status; Item : out Permit_Record)
   with Global => null, Always_Terminates,
     Depends => (Status => (Bytes, Observed_Length),
                 Item => (Bytes, Observed_Length)),
     Post => Status = Check_Permit (Bytes, Observed_Length) and then
       (if Status = Decoded then Valid_Permit_Record (Item) and then
          Permit_Decoded_As (Bytes, Item) else Item = Empty_Permit);

   procedure Decode_Control
     (Bytes : Control_Bytes; Observed_Length : Natural;
      Status : out Decode_Status; Item : out Control_Record)
   with Global => null, Always_Terminates,
     Depends => (Status => (Bytes, Observed_Length),
                 Item => (Bytes, Observed_Length)),
     Post => Status = Check_Control (Bytes, Observed_Length) and then
       (if Status = Decoded then Valid_Control_Record (Item) and then
          Control_Decoded_As (Bytes, Item) else Item = Empty_Control);

   procedure Encode_Permit (Item : Permit_Record; Bytes : out Permit_Bytes)
   with Global => null, Always_Terminates, Depends => (Bytes => Item),
     Pre => Valid_Permit_Record (Item),
     Post => Check_Permit (Bytes, Permit_Bytes'Length) = Decoded and then
       Permit_Decoded_As (Bytes, Item);

   procedure Encode_Control (Item : Control_Record; Bytes : out Control_Bytes)
   with Global => null, Always_Terminates, Depends => (Bytes => Item),
     Pre => Valid_Control_Record (Item),
     Post => Check_Control (Bytes, Control_Bytes'Length) = Decoded and then
       Control_Decoded_As (Bytes, Item);

   function Same_Permit_Content (Left, Right : Permit_Record) return Boolean is
     (Left.Content = Right.Content) with Global => null;
   function Same_Control_Bindings (Left, Right : Control_Record)
      return Boolean is (Left.Bindings = Right.Bindings) with Global => null;
   function Same_Control_Content (Left, Right : Control_Record)
      return Boolean is
     (Same_Control_Bindings (Left, Right) and then
      Left.Epoch = Right.Epoch and then Left.State = Right.State)
   with Global => null;
   --  Declared digest is untrusted data; a true join grants no authority.
   function Control_Declares_Permit
     (Permit : Permit_Record; Control : Control_Record;
      Declared_Permit_Signed_Digest : Digest) return Boolean is
     (Control.Bindings.Fixture = Permit.Content.Operation.Fixture and then
      Control.Bindings.Recovery_Policy = Permit.Content.Recovery_Policy and then
      Control.Bindings.Permit_Signed_Digest = Declared_Permit_Signed_Digest)
   with Global => null;
   function Declared_Disable_Step (Before, After : Control_Record)
      return Boolean is
     (Valid_Control_Record (Before) and then Valid_Control_Record (After) and then
      Same_Control_Bindings (Before, After) and then
      Before.Epoch = 0 and then Before.State = Enabled and then
      After.Epoch = 1 and then After.State = Disabled)
   with Global => null;
end SIA_Recovery_Records;
