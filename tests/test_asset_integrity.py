#!/usr/bin/env python3
"""Release assets have one named source of truth."""

from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parent.parent


class CanonicalCockpitPreview(unittest.TestCase):
    def test_preview_is_single_sourced_and_described_as_an_example(self):
        preview = REPO / "preview.png"
        duplicate = REPO / "assets" / "cockpit.png"
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        installer = (REPO / "install.sh").read_text(encoding="utf-8")

        self.assertTrue(preview.is_file())
        self.assertGreater(preview.stat().st_size, 0)
        self.assertFalse(duplicate.exists())
        self.assertIn("](preview.png)", readme)
        self.assertIn("Example SIA cockpit", readme)
        self.assertNotIn("assets/cockpit.png", readme)
        self.assertNotIn("assets/cockpit.png", installer)


if __name__ == "__main__":
    unittest.main(verbosity=2)
