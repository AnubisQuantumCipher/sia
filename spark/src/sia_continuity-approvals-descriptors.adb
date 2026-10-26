package body SIA_Continuity.Approvals.Descriptors with SPARK_Mode is
   function Digest_Payload (Bytes : Descriptor_Bytes; Offset : Digest_Offset)
      return Digest is
   begin
      return Digest (Bytes (Offset + 1 .. Offset + 32));
   end Digest_Payload;

   function Word_Payload (Bytes : Descriptor_Bytes; Offset : Word_Offset)
      return Word is
   begin
      return Word (Bytes (Offset + 1 .. Offset + 8));
   end Word_Payload;

   procedure Digest_Unique
     (Left, Right : Descriptor_Bytes; Offset : Digest_Offset) is null;

   procedure Low_Digit (High : Generation; Low : Digest_Byte) is null;

   procedure Recover_Digits (Bytes : Word) is
      P1 : constant Generation := Generation (Bytes (1));
      P2 : constant Generation := P1 * 256 + Generation (Bytes (2));
      P3 : constant Generation := P2 * 256 + Generation (Bytes (3));
      P4 : constant Generation := P3 * 256 + Generation (Bytes (4));
      P5 : constant Generation := P4 * 256 + Generation (Bytes (5));
      P6 : constant Generation := P5 * 256 + Generation (Bytes (6));
      P7 : constant Generation := P6 * 256 + Generation (Bytes (7));
      P8 : constant Generation := P7 * 256 + Generation (Bytes (8));
      Value : constant Generation := Word_Value (Bytes);
   begin
      pragma Assert (Value / 2 ** 56 = P1);
      pragma Assert (Value / 2 ** 48 = P2);
      pragma Assert (Value / 2 ** 40 = P3);
      pragma Assert (Value / 2 ** 32 = P4);
      pragma Assert (Value / 2 ** 24 = P5);
      pragma Assert (Value / 2 ** 16 = P6);
      pragma Assert (Value / 2 ** 8 = P7);
      pragma Assert (Value / 2 ** 0 = P8);
      Low_Digit (P1, Bytes (2));
      Low_Digit (P2, Bytes (3));
      Low_Digit (P3, Bytes (4));
      Low_Digit (P4, Bytes (5));
      Low_Digit (P5, Bytes (6));
      Low_Digit (P6, Bytes (7));
      Low_Digit (P7, Bytes (8));
   end Recover_Digits;

   procedure Word_Unique (Left, Right : Word) is
   begin
      Recover_Digits (Left);
      Recover_Digits (Right);
   end Word_Unique;

   procedure Prefix_Unique
     (Left, Right : Descriptor_Bytes; Scope : Context; Item : Current_Selection) is
   begin
      pragma Assert (for all I in 1 .. 8 => Left (I) = Right (I));
      Digest_Unique (Left, Right, 8);
      Digest_Unique (Left, Right, 40);
      Digest_Unique (Left, Right, 72);
      Digest_Unique (Left, Right, 104);
      Digest_Unique (Left, Right, 136);
      Digest_Unique (Left, Right, 168);
      Digest_Unique (Left, Right, 200);
      Digest_Unique (Left, Right, 232);
      Digest_Unique (Left, Right, 264);
      Digest_Unique (Left, Right, 296);
      Digest_Unique (Left, Right, 328);
      Digest_Unique (Left, Right, 360);
   end Prefix_Unique;

   procedure Generations_Unique
     (Left, Right : Descriptor_Bytes; Item : Current_Selection) is
   begin
      Word_Unique (Word_Payload (Left, 392), Word_Payload (Right, 392));
      Word_Unique (Word_Payload (Left, 400), Word_Payload (Right, 400));
      Word_Unique (Word_Payload (Left, 408), Word_Payload (Right, 408));
   end Generations_Unique;

   procedure Tail_Unique
     (Left, Right : Descriptor_Bytes; Item : Current_Selection) is null;

   procedure Unique
     (Left, Right : Descriptor_Bytes; Scope : Context; Item : Current_Selection) is
   begin
      Prefix_Unique (Left, Right, Scope, Item);
      Generations_Unique (Left, Right, Item);
      Tail_Unique (Left, Right, Item);
   end Unique;

   procedure Decode
     (Bytes : Descriptor_Bytes; Accepted : out Boolean;
      Scope : out Context; Item : out Current_Selection)
   is
   begin
      Scope := Empty_Context;
      Item := Empty_Selection;
      Accepted := Valid (Bytes);
      if not Accepted then
         return;
      end if;
      Scope :=
        (Task_Id => Digest_Payload (Bytes, 8),
         Session_Id => Digest_Payload (Bytes, 40),
         Repository => Digest_Payload (Bytes, 72),
         Revision => Digest_Payload (Bytes, 104),
         Dirty => Digest_Payload (Bytes, 136));
      Item.Question := Digest_Payload (Bytes, 168);
      Item.Question_Item := Digest_Payload (Bytes, 200);
      Item.Response := Digest_Payload (Bytes, 232);
      Item.Requested :=
        (Proposal => Digest_Payload (Bytes, 264),
         Action => Digest_Payload (Bytes, 296),
         Conditions => Digest_Payload (Bytes, 328));
      Item.Checkpoint_Id := Digest_Payload (Bytes, 360);
      Item.Epoch := Word_Value (Word_Payload (Bytes, 392));
      Item.Through := Word_Value (Word_Payload (Bytes, 400));
      Item.Retention_Epoch := Word_Value (Word_Payload (Bytes, 408));
      Item.Where_Now :=
        (Lifecycle => Digest_Payload (Bytes, 416),
         Target_Turn => Digest_Payload (Bytes, 448));
      Item.Form := Form_Value (Bytes (481));
      Item.State := State_Value (Bytes (482));
   end Decode;
end SIA_Continuity.Approvals.Descriptors;
