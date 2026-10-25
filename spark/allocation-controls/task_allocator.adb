with Ada.Task_Identification;
with Ada.Text_IO;

procedure Task_Allocator is
   task type Worker;
   task body Worker is
   begin
      null;
   end Worker;
   type Worker_Reference is access Worker;
   Item : constant Worker_Reference := new Worker;
begin
   Ada.Text_IO.Put_Line (Ada.Task_Identification.Image (Item.all'Identity));
end Task_Allocator;
