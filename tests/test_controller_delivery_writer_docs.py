"""Describe source-authorized output without claiming consumer execution."""

from pathlib import Path
import unittest


class ControllerDeliveryWriterDocumentation(unittest.TestCase):
    def test_architecture_names_writer_and_unchanged_output_scope(self):
        prose = (Path(__file__).resolve().parents[1] / "docs" / "ARCHITECTURE.md").read_text()
        for phrase in (
                "siacontrollerdeliverywriter.deliver",
                "result-body-before-queue-health-footer-v1",
                "write-all-and-flush-returned",
                "caller-supplied rows and rendered body",
                "Incomplete journals, including intent-only",
                "configured resident cycle enters v3"):
            with self.subTest(phrase=phrase):
                self.assertTrue(phrase in prose, "missing output boundary: " + phrase)


if __name__ == "__main__":
    unittest.main()
