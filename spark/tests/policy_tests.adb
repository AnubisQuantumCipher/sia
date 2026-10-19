with SIA_Policy;

procedure Policy_Tests with SPARK_Mode is
   use SIA_Policy;
   Target : constant Binding :=
     (Epoch => 1, Transaction => [others => 17]);
   Good : constant Witness :=
     (Present => True, Durable => True, Bound_To => Target);
   Published : constant Publication :=
     (Target => Target, Corpus => Good, Index => Good, Graph => Good,
      Ledger => Good, Recovery_Debt => False,
      Source_State => Verified_Complete);

   procedure Check_Provenance with Global => null is
   begin
      for Kind in Origin loop
         for State in Completeness loop
            pragma Assert
              (not Admit_Source_Evidence (Kind, State, False));
            if Kind = Source_Record and State = Verified_Complete then
               pragma Assert (Admit_Source_Evidence (Kind, State, True));
            else
               pragma Assert
                 (not Admit_Source_Evidence (Kind, State, True));
            end if;
         end loop;
      end loop;
   end Check_Provenance;

   procedure Reject_Witness (Bad : Witness) with
     Global => null, Pre => not Bound_Durable (Bad, Target)
   is
      Candidate : Publication := Published;
   begin
      Candidate.Corpus := Bad;
      pragma Assert (not Publication_Joined (Candidate));
      Candidate := Published;
      Candidate.Index := Bad;
      pragma Assert (not Publication_Joined (Candidate));
      Candidate := Published;
      Candidate.Graph := Bad;
      pragma Assert (not Publication_Joined (Candidate));
      Candidate := Published;
      Candidate.Ledger := Bad;
      pragma Assert (not Publication_Joined (Candidate));
      pragma Assert (not Acknowledge (Published, Bad, Good));
      pragma Assert (not Acknowledge (Published, Good, Bad));
   end Reject_Witness;

   procedure Check_Publication with Global => null is
      Candidate : Publication := Published;
      Bad : Witness := Good;
   begin
      pragma Assert (Publication_Joined (Published));
      pragma Assert (Acknowledge (Published, Good, Good));
      Candidate.Recovery_Debt := True;
      pragma Assert (not Publication_Joined (Candidate));
      pragma Assert (not Acknowledge (Candidate, Good, Good));
      Candidate := Published;
      for State in Completeness loop
         Candidate.Source_State := State;
         case State is
            when Observed_Empty | Verified_Complete =>
               pragma Assert (Publication_Joined (Candidate));
            when Not_Observed | Unavailable =>
               pragma Assert (not Publication_Joined (Candidate));
         end case;
      end loop;
      Bad.Present := False;
      Reject_Witness (Bad);
      Bad := Good;
      Bad.Durable := False;
      Reject_Witness (Bad);
      Bad := Good;
      Bad.Bound_To.Epoch := 2;
      Reject_Witness (Bad);
      Bad := Good;
      for Position in Digest'Range loop
         Bad.Bound_To.Transaction (Position) := 18;
         Reject_Witness (Bad);
         Bad := Good;
      end loop;
      Candidate := Published;
      Candidate.Target.Epoch := No_Generation;
      pragma Assert (not Publication_Joined (Candidate));
      Candidate.Corpus.Bound_To := Candidate.Target;
      Candidate.Index.Bound_To := Candidate.Target;
      Candidate.Graph.Bound_To := Candidate.Target;
      Candidate.Ledger.Bound_To := Candidate.Target;
      pragma Assert (not Publication_Joined (Candidate));
   end Check_Publication;
begin
   Check_Provenance;
   Check_Publication;
end Policy_Tests;
