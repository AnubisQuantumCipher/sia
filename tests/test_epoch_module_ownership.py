"""Epoch materialization keeps one owner across dynamically loaded cores."""

import ast
import importlib.util
import inspect
from pathlib import Path
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home


REPO = Path(__file__).resolve().parents[1]
CORE_PATH = REPO / "bin/sialib.py"
CHILD_PATH = REPO / "bin/siathought.py"

# The exact lifecycle moves as one unit. Event-day admission, generic corpus
# publication and DREAM orchestration retain their existing owners.
EPOCH_EXPORTS = frozenset({
    "_acknowledge_consolidation_claims",
    "_advance_consolidation_scan",
    "_bind_consolidation_ledger",
    "_bounded_event_directory_entries",
    "_canonical_consolidation_day",
    "_canonical_consolidation_scan",
    "_canonical_epoch_event_ids",
    "_canonical_epoch_source_manifest",
    "_claimed_consolidation_paths",
    "_clear_consolidation_marker",
    "_consolidation_scan_debt",
    "_consolidation_scan_path",
    "_ensure_structured_consolidation_marker",
    "_epoch_exemplars",
    "_epoch_json_field",
    "_epoch_slug_for_day",
    "_event_index_entries_for_sources",
    "_fresh_consolidation_scan",
    "_load_consolidation_scan",
    "_mark_consolidation_applied",
    "_mark_consolidation_pending",
    "_merge_epoch_event_ids",
    "_merge_epoch_source_manifest",
    "_pending_consolidation_marker",
    "_prepare_consolidation_claims",
    "_read_epoch_state",
    "_recover_pending_consolidation",
    "_render_bounded_epoch",
    "_render_epoch_source_manifest",
    "_save_consolidation_scan",
    "_settle_consolidation_ledger",
    "_write_bounded_epoch",
    "_write_epoch_source_manifest",
    "consolidate_corpus",
})


def _load_core(name):
    spec = importlib.util.spec_from_file_location(name, CORE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EpochModuleOwnership(unittest.TestCase):
    def setUp(self):
        self.first = _load_core("sialib_epoch_owner_first")
        self.second = _load_core("sialib_epoch_owner_second")
        self.child = self.first._siathought
        self.assertIs(self.child, self.second._siathought)
        self.addCleanup(self.child.bind, self.first.__dict__)

    def test_exact_epoch_lifecycle_is_child_owned_and_parent_published(self):
        actual = {
            name for name in self.child._EXPORTED_FUNCTIONS
            if "epoch" in name or "consolidat" in name
            or name in {"_bounded_event_directory_entries",
                        "_event_index_entries_for_sources"}
        }
        self.assertEqual(actual, EPOCH_EXPORTS)
        core_tree = ast.parse(CORE_PATH.read_text(encoding="utf-8"))
        core_definitions = {
            node.name for node in core_tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        }
        self.assertTrue(EPOCH_EXPORTS.isdisjoint(core_definitions))
        for name in sorted(EPOCH_EXPORTS):
            with self.subTest(export=name):
                target = self.child._ORIGINAL_CHILD_FUNCTIONS[name]
                self.assertTrue(inspect.isfunction(target))
                self.assertEqual(
                    Path(target.__code__.co_filename).resolve(), CHILD_PATH)
                for owner in (self.first, self.second):
                    facade = getattr(owner, name)
                    self.assertIs(facade.__wrapped__, target)
                    self.assertIs(facade._sia_senses_delegate, True)

    def test_epoch_calls_preserve_context_exports_and_parent_state(self):
        self.assertEqual(self.child._CONTEXT_EXPORTS, frozenset({
            "_thought_legacy_catalog", "_thought_mind_replay_catalog",
        }))
        self.assertTrue(EPOCH_EXPORTS.isdisjoint(
            self.child._CONTEXT_EXPORTS))
        with mock.patch.multiple(
                self.first, SHARE="/first/share", CORPUS="/first/share/corpus",
                STATE="/first/state"), mock.patch.multiple(
                self.second, SHARE="/second/share",
                CORPUS="/second/share/corpus", STATE="/second/state"):
            self.assertEqual(self.first._consolidation_scan_path(),
                             "/first/state/consolidation-scan.json")
            self.assertEqual(self.second._consolidation_scan_path(),
                             "/second/state/consolidation-scan.json")
            self.assertEqual(self.first._consolidation_scan_path(),
                             "/first/state/consolidation-scan.json")

    def test_each_alias_binds_external_and_internal_patched_dependencies(self):
        slug = "epochs/org/2026-w02"
        text = "---\ntype: epoch\n---\n# retained epoch\n"
        first_generation, second_generation = object(), object()
        with mock.patch.object(
                self.first, "_read_event_page", return_value=text) as first_read, \
                mock.patch.object(
                    self.second, "_read_event_page", return_value=text) \
                as second_read, mock.patch.object(
                    self.first, "_epoch_json_field",
                    side_effect=RuntimeError("first parent patch")), \
                mock.patch.object(
                    self.second, "_epoch_json_field",
                    side_effect=RuntimeError("second parent patch")):
            for owner, generation, label in (
                    (self.first, first_generation, "first parent patch"),
                    (self.second, second_generation, "second parent patch"),
                    (self.first, first_generation, "first parent patch")):
                with self.assertRaisesRegex(RuntimeError, label):
                    owner._read_epoch_state(
                        slug, expected_generation=generation)
            self.assertEqual(first_read.call_args_list, [
                mock.call(slug, expected_generation=first_generation),
                mock.call(slug, expected_generation=first_generation),
            ])
            second_read.assert_called_once_with(
                slug, expected_generation=second_generation)

    def test_capacity_and_completeness_exceptions_stay_parent_owned(self):
        slug = "epochs/org/2026-w02"
        event_ids = ["a" * 64]
        child_tree = ast.parse(CHILD_PATH.read_text(encoding="utf-8"))
        child_classes = {node.name for node in child_tree.body
                         if isinstance(node, ast.ClassDef)}
        for name in ("ConsolidationCapacityError",
                     "ConsolidationCompletenessError"):
            self.assertNotIn(name, child_classes)
            self.assertNotIn(name, self.child._EXPORTED_FUNCTIONS)
            self.assertIsNot(getattr(self.first, name),
                             getattr(self.second, name))
        with mock.patch.object(self.first, "MAX_EPOCH_EVENT_IDS", 0), \
                mock.patch.object(self.second, "MAX_EPOCH_EVENT_IDS", 1):
            for owner in (self.first, self.second, self.first):
                if owner is self.first:
                    with self.assertRaises(owner.ConsolidationCapacityError):
                        owner._canonical_epoch_event_ids(event_ids, slug)
                else:
                    self.assertEqual(owner._canonical_epoch_event_ids(
                        event_ids, slug), event_ids)
                self.assertIs(self.child.ConsolidationCapacityError,
                              owner.ConsolidationCapacityError)
        legacy = {"text": "retained legacy epoch",
                  "event_ids_declared": False, "ndays": 1,
                  "sources": [], "slug": slug}
        for owner in (self.first, self.second, self.first):
            with self.assertRaises(owner.ConsolidationCompletenessError):
                owner._merge_epoch_event_ids(legacy, [], [])
            self.assertIs(self.child.ConsolidationCompletenessError,
                          owner.ConsolidationCompletenessError)


if __name__ == "__main__":
    unittest.main()
