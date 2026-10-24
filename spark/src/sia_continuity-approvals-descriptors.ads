with SIA_Continuity_Record_Wire;

--  Canonical metadata representation only. Authentication is never decoded.
package SIA_Continuity.Approvals.Descriptors with SPARK_Mode, Pure is
   use SIA_Continuity_Record_Wire;
   type Descriptor_Bytes is array (Positive range 1 .. 512) of Digest_Byte;
   subtype Form_Code is Digest_Byte range 0 .. 2;
   subtype State_Code is Digest_Byte range 0 .. 4;

   function Form_Value (Code : Form_Code) return Decision_Form is
     (case Code is
        when 0 => Unknown_Form, when 1 => Queried_Decision,
        when 2 => Direct_Instruction)
   with Global => null;

   function State_Value (Code : State_Code) return Currentness is
     (case Code is
        when 0 => Unknown_Current, when 1 => Current, when 2 => Revoked,
        when 3 => Superseded, when 4 => Expired)
   with Global => null;

   function Valid (Bytes : Descriptor_Bytes) return Boolean is
     (Bytes (1 .. 8) = [83, 73, 65, 68, 83, 67, 48, 49]
      and then Bytes (393) <= 127 and then Bytes (401) <= 127
      and then Bytes (409) <= 127
      and then Bytes (481) in Form_Code and then Bytes (482) in State_Code
      and then (for all I in 483 .. 512 => Bytes (I) = 0))
   with Global => null;

   subtype Digest_Offset is Natural range 0 .. 480;
   subtype Word_Offset is Natural range 0 .. 504;
   function Digest_Payload (Bytes : Descriptor_Bytes; Offset : Digest_Offset)
      return Digest
   with Global => null,
     Post => (for all I in Digest'Range =>
       Digest_Payload'Result (I) = Bytes (Offset + I));

   function Word_Payload (Bytes : Descriptor_Bytes; Offset : Word_Offset)
      return Word
   with Global => null,
     Post => (for all I in Word'Range =>
       Word_Payload'Result (I) = Bytes (Offset + I));

   function Prefix_Matches
     (Bytes : Descriptor_Bytes; Scope : Context; Item : Current_Selection)
      return Boolean is
     (Bytes (1 .. 8) = [83, 73, 65, 68, 83, 67, 48, 49]
      and then Scope.Task_Id = Digest_Payload (Bytes, 8)
      and then Scope.Session_Id = Digest_Payload (Bytes, 40)
      and then Scope.Repository = Digest_Payload (Bytes, 72)
      and then Scope.Revision = Digest_Payload (Bytes, 104)
      and then Scope.Dirty = Digest_Payload (Bytes, 136)
      and then Item.Question = Digest_Payload (Bytes, 168)
      and then Item.Question_Item = Digest_Payload (Bytes, 200)
      and then Item.Response = Digest_Payload (Bytes, 232)
      and then Item.Requested.Proposal = Digest_Payload (Bytes, 264)
      and then Item.Requested.Action = Digest_Payload (Bytes, 296)
      and then Item.Requested.Conditions = Digest_Payload (Bytes, 328)
      and then Item.Checkpoint_Id = Digest_Payload (Bytes, 360))
   with Global => null;

   function Generations_Match
     (Bytes : Descriptor_Bytes; Item : Current_Selection) return Boolean is
     (Bytes (393) <= 127 and then Bytes (401) <= 127
      and then Bytes (409) <= 127
      and then Item.Epoch = Word_Value (Word_Payload (Bytes, 392))
      and then Item.Through = Word_Value (Word_Payload (Bytes, 400))
      and then Item.Retention_Epoch = Word_Value (Word_Payload (Bytes, 408)))
   with Global => null;

   function Tail_Matches
     (Bytes : Descriptor_Bytes; Item : Current_Selection) return Boolean is
     (Bytes (481) in Form_Code and then Bytes (482) in State_Code
      and then (for all I in 483 .. 512 => Bytes (I) = 0)
      and then Item.Where_Now.Lifecycle = Digest_Payload (Bytes, 416)
      and then Item.Where_Now.Target_Turn = Digest_Payload (Bytes, 448)
      and then Item.Form = Form_Value (Bytes (481))
      and then Item.State = State_Value (Bytes (482)))
   with Global => null;

   --  All content, with no decoded authentication, self-digest or custody.
   function Content_Matches
     (Bytes : Descriptor_Bytes; Scope : Context; Item : Current_Selection)
      return Boolean is
     (Prefix_Matches (Bytes, Scope, Item)
      and then Generations_Match (Bytes, Item)
      and then Tail_Matches (Bytes, Item))
   with Global => null;

   procedure Unique
     (Left, Right : Descriptor_Bytes; Scope : Context; Item : Current_Selection)
   with Ghost, Global => null, Always_Terminates,
     Pre => Content_Matches (Left, Scope, Item)
       and then Content_Matches (Right, Scope, Item),
     Post => Left = Right;

   procedure Decode
     (Bytes : Descriptor_Bytes; Accepted : out Boolean;
      Scope : out Context; Item : out Current_Selection)
   with Global => null, Always_Terminates,
     Depends => (Accepted => Bytes, Scope => Bytes, Item => Bytes),
     Post => Accepted = Valid (Bytes)
       and then Item.Descriptor = Zero
       and then Item.Source_State = Unknown_Source
       and then Item.Custody = SIA_Continuity.Approvals.Empty_Witness
       and then
         (if Accepted then Content_Matches (Bytes, Scope, Item)
          else Scope = Empty_Context and then Item = Empty_Selection);
private
   procedure Recover_Digits (Bytes : Word)
   with Ghost, Global => null, Always_Terminates,
     Pre => Bytes (1) <= 127,
     Post => Word_Value (Bytes) / 2 ** 56 = Generation (Bytes (1))
       and then (Word_Value (Bytes) / 2 ** 48) mod 256 = Generation (Bytes (2))
       and then (Word_Value (Bytes) / 2 ** 40) mod 256 = Generation (Bytes (3))
       and then (Word_Value (Bytes) / 2 ** 32) mod 256 = Generation (Bytes (4))
       and then (Word_Value (Bytes) / 2 ** 24) mod 256 = Generation (Bytes (5))
       and then (Word_Value (Bytes) / 2 ** 16) mod 256 = Generation (Bytes (6))
       and then (Word_Value (Bytes) / 2 ** 8) mod 256 = Generation (Bytes (7))
       and then (Word_Value (Bytes) / 2 ** 0) mod 256 = Generation (Bytes (8));

   procedure Word_Unique (Left, Right : Word)
   with Ghost, Global => null, Always_Terminates,
     Pre => Left (1) <= 127 and then Right (1) <= 127
       and then Word_Value (Left) = Word_Value (Right),
     Post => Left = Right;

   procedure Prefix_Unique
     (Left, Right : Descriptor_Bytes; Scope : Context; Item : Current_Selection)
   with Ghost, Global => null, Always_Terminates,
     Pre => Prefix_Matches (Left, Scope, Item)
       and then Prefix_Matches (Right, Scope, Item),
     Post => (for all I in 1 .. 392 => Left (I) = Right (I));

   procedure Generations_Unique
     (Left, Right : Descriptor_Bytes; Item : Current_Selection)
   with Ghost, Global => null, Always_Terminates,
     Pre => Generations_Match (Left, Item) and then Generations_Match (Right, Item),
     Post => (for all I in 393 .. 416 => Left (I) = Right (I));

   procedure Tail_Unique
     (Left, Right : Descriptor_Bytes; Item : Current_Selection)
   with Ghost, Global => null, Always_Terminates,
     Pre => Tail_Matches (Left, Item) and then Tail_Matches (Right, Item),
     Post => (for all I in 417 .. 512 => Left (I) = Right (I));
end SIA_Continuity.Approvals.Descriptors;
