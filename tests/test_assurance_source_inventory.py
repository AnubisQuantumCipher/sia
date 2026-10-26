"""Inventory controls; passing tests do not establish Python rule compliance."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    "source_inventory",
    Path(__file__).parents[1] / "scripts/assurance_source_inventory.py")
INVENTORY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INVENTORY)


class SourceInventory(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source.py"

    def test_reports_review_sites_without_executing_source(self):
        marker = self.root / "must-not-exist"
        self.source.write_text(
            f"open({str(marker)!r}, 'w').close()\n"
            "def routine():\n    global state\n"
            "    while state:\n        state = getattr(state, 'next')\n"
            + "    state = 1\n" * 60)
        result = INVENTORY.inventory([self.source])
        self.assertEqual(result["status"], "inventory-only")
        self.assertFalse(marker.exists())
        self.assertEqual(
            {x["kind"] for x in result["files"][0]["findings"]},
            {"physical-span-over-60", "expanded-mutable-scope",
             "while-bound-review", "dynamic-call-review"})

    def test_empty_findings_are_not_a_compliance_result(self):
        self.source.write_text("x = 1\n")
        result = INVENTORY.inventory([self.source])
        self.assertEqual(result["files"][0]["findings"], [])
        self.assertEqual(result["status"], "inventory-only")
        self.assertTrue(result["limitations"])

    def test_bad_source_symlink_and_limits_refuse(self):
        self.source.write_text("def broken(\n")
        with self.assertRaises(SyntaxError):
            INVENTORY.inventory([self.source])
        self.source.write_text("x = 1\n")
        link = self.root / "link.py"
        link.symlink_to(self.source)
        with self.assertRaises(OSError):
            INVENTORY.inventory([link])
        for field in ("MAX_BYTES", "MAX_TOTAL_BYTES", "MAX_NODES"):
            with self.subTest(field=field), mock.patch.object(INVENTORY, field, 1):
                with self.assertRaises(ValueError):
                    INVENTORY.inventory([self.source])
        for paths in ([], [self.source, self.source]):
            with self.assertRaises(ValueError):
                INVENTORY.inventory(paths)
        with mock.patch.object(INVENTORY, "MAX_FILES", 1):
            with self.assertRaises(ValueError):
                INVENTORY.inventory([self.source, self.root / "other.py"])

    def test_fifo_refuses_without_waiting_for_a_writer(self):
        fifo = self.root / "source.fifo"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            INVENTORY.inventory([fifo])


if __name__ == "__main__":
    unittest.main()
