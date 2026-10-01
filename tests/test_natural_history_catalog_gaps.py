#!/usr/bin/env python3
"""Focused regression coverage for natural-history catalog gaps."""

import importlib.util
import os
import sys
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")
sys.path.insert(0, BIN)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


siatakes = _load(
    "siatakes_catalog_gaps", os.path.join(BIN, "siatakes.py"))


class NaturalHistoryCatalogGaps(unittest.TestCase):
    def test_primary_page_readers_refuse_missing_catalog_entry(self):
        for kind, read_page in (
                ("take", siatakes.list_takes_page),
                ("intent", siatakes.list_intents_page)):
            state = {
                "next_catalog": 1,
                "legacy": {"complete": True},
                "authority": {"complete": False, "checkpoint": {}},
            }
            with self.subTest(kind=kind), \
                    mock.patch.object(
                        siatakes, "_load_history_state",
                        return_value=state), \
                    mock.patch.object(
                        siatakes, "_read_history_json",
                        return_value=None), \
                    mock.patch.object(
                        siatakes, "_history_direct") as direct, \
                    self.assertRaisesRegex(
                        ValueError,
                        "natural-history catalog entry is missing"):
                read_page()
            direct.assert_not_called()

    def test_domain_page_reader_refuses_missing_catalog_entry(self):
        state = {"next_domain": 1, "applied_event": -1}
        with mock.patch.object(
                siatakes, "natural_history_debt", return_value=False), \
                mock.patch.object(
                    siatakes, "_load_history_state", return_value=state), \
                mock.patch.object(
                    siatakes, "_read_history_json", return_value=None), \
                mock.patch.object(
                    siatakes, "_history_domain_path") as domain_path, \
                self.assertRaisesRegex(
                    ValueError,
                    "natural-history domain catalog entry is missing"):
            siatakes.list_calibration_domains_page()
        domain_path.assert_not_called()


if __name__ == "__main__":
    unittest.main()
