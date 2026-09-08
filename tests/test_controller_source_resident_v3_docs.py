"""Keep resident construction distinct from configured live activation."""

from pathlib import Path
import unittest


class ControllerSourceResidentV3Documentation(unittest.TestCase):
    def test_architecture_names_explicit_runner_and_remaining_activation_boundary(self):
        prose = (Path(__file__).resolve().parents[1] / "docs" / "ARCHITECTURE.md").read_text()
        for phrase in (
                "_run_controller_source_transaction_v3",
                "run_v3",
                "configured resident cycle remains v2",
                "retired status handoff",
                "capture-only",
                "journal remains empty"):
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase in prose, "missing resident boundary: " + phrase)
        self.assertFalse("not a completed v3 runner cycle" in prose,
                         "architecture still denies the actual resident integration")


if __name__ == "__main__":
    unittest.main()
