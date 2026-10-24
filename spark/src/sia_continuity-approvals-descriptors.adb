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

   procedure Recover_Digits (Bytes : Word) is null;

   procedure Word_Unique (Left, Right : Word) is
   begin
      Recover_Digits (Left);
      Recover_Digits (Right);
   end Word_Unique;

   procedure Prefix_Unique
     (Left, Right : Descriptor_Bytes; Scope : Context; Item : Current_Selection)
   is null;

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
