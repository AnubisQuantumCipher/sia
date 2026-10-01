"""Frozen multi-day event-page composition and byte-only publication.

Only the owner executes this suite, sequentially in the existing isolated
EventPageRenderPlan fixture. Composition holds one real corpus owner and
admits a common ORIGINAL cut. Publication/retry admits only that cut plus the
batch's exact target/ancestor deltas. An already matching target is not proof
that this attempt wrote it. Individual v1 plans and publications stay intact.

The overall ceiling remains MAX_STATE_JSON_BYTES; constituent ceilings are
not multiplied by member count. This is still only a page-byte transaction,
not complete live-input/status/memo admission or cursor acknowledgment.
"""

import base64
import contextlib
import copy
import hashlib
import os
from pathlib import Path
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_event_page_plan as individual


BATCH_KEYS = {"schema", "organ", "members", "read_dependencies", "write_order",
              "new_directories", "non_claims", "batch_sha256"}
RESULT_KEYS = {"schema", "status", "batch_sha256", "members", "non_claims"}
NON_CLAIMS = individual.NON_CLAIMS + [
    "Batch composition does not resolve shared-page write conflicts or reassign event occurrences; conflicting member targets require a separately admitted original assignment cut.",
]
REFUSALS = individual.REFUSALS
canonical = individual.canonical
digest = individual.digest


def own(batch):
    return digest(canonical({key: value for key, value in batch.items()
                             if key != "batch_sha256"}))


class EventPagePlanBatch(unittest.TestCase):
    def setUp(self):
        # Composition, not inheritance: the individual suite is not rerun as
        # an accidental second test roster under this class.
        self.fixture = individual.EventPageRenderPlan(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.corpus = self.fixture.corpus
        for name in ("_compose_event_page_plans", "_publish_event_page_plan_batch"):
            self.assertTrue(callable(getattr(self.lib, name, None)),
                            "missing event-plan batch API: " + name)

    def plans(self, *, historical=False):
        if historical:
            self.fixture.fixture._source()
            dates = ("2026-01-06", "2026-01-07")
        else:
            dates = (self.fixture.day, "2026-01-07")
        return [self.fixture.prepare(
            [self.fixture.event(day, "native:batch:" + day)], day=day)
                for day in dates]

    def compose(self, plans, *, expected=None):
        pins = [plan["plan_sha256"] for plan in plans] if expected is None else expected
        return self.lib._compose_event_page_plans(
            plans=plans, expected_plan_sha256s=pins)

    def publish(self, batch, *, expected=None):
        pin = batch["batch_sha256"] if expected is None else expected
        return self.lib._publish_event_page_plan_batch(
            batch=batch, expected_batch_sha256=pin)

    def write_pages(self, batch):
        members = {plan["plan_sha256"]: plan for plan in batch["members"]}
        return [next(page for page in members[row["plan_sha256"]]["pages"]
                     if page["slug"] == row["slug"])
                for row in batch["write_order"]]

    def assert_batch(self, batch, plans):
        self.assertEqual(set(batch), BATCH_KEYS)
        self.assertEqual(batch["schema"], "sia-event-page-render-batch-v1")
        self.assertEqual(batch["organ"], "org")
        self.assertEqual(batch["batch_sha256"], own(batch))
        self.assertEqual(batch["non_claims"], NON_CLAIMS)
        self.assertEqual(batch["members"], sorted(plans, key=lambda plan: plan["date"]))
        self.assertLessEqual(len(canonical(batch)), self.lib.MAX_STATE_JSON_BYTES)
        for member in batch["members"]:
            self.fixture.assert_plan(member)
        expected_order = [
            {"plan_sha256": plan["plan_sha256"], "slug": page["slug"]}
            for plan in batch["members"] for page in plan["pages"] if page["write"]]
        self.assertEqual(batch["write_order"], expected_order)
        deps = batch["read_dependencies"]
        self.assertEqual(set(deps), {"schema", "corpus_identity", "directories", "files"})
        self.assertEqual(deps["schema"], "sia-event-page-read-dependencies-v1")
        files, directories = {}, {}
        for member in batch["members"]:
            source = member["read_dependencies"]
            self.assertEqual(deps["corpus_identity"], source["corpus_identity"])
            for row in source["files"]:
                if row["relative"] in files:
                    self.assertEqual(files[row["relative"]], row)
                files[row["relative"]] = row
            for row in source["directories"]:
                relative, before = row["relative"], row["before"]
                if relative not in directories:
                    directories[relative] = copy.deepcopy(row)
                    continue
                prior = directories[relative]["before"]
                if prior is None or before is None:
                    self.assertEqual(prior, before)
                    continue
                self.assertEqual(prior["identity"], before["identity"])
                if prior["entries"] is None:
                    directories[relative] = copy.deepcopy(row)
                elif before["entries"] is not None:
                    self.assertEqual(prior["entries"], before["entries"])
        self.assertEqual(deps["files"], [files[name] for name in sorted(files)])
        self.assertEqual(deps["directories"], [directories[name] for name in sorted(directories)])
        ancestors = set()
        for page in self.write_pages(batch):
            parent = Path(page["slug"] + ".md").parent
            while parent != Path("."):
                ancestors.add(parent.as_posix())
                parent = parent.parent
        self.assertEqual(batch["new_directories"], sorted(
            name for name in ancestors if directories[name]["before"] is None))

    def assert_result(self, result, batch):
        self.assertEqual(set(result), RESULT_KEYS)
        self.assertEqual(result["schema"], "sia-event-page-render-batch-publication-v1")
        self.assertEqual(result["status"], "page-bytes-published")
        self.assertEqual(result["batch_sha256"], batch["batch_sha256"])
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertEqual(len(result["members"]), len(batch["members"]))
        for publication, plan in zip(result["members"], batch["members"]):
            self.fixture.assert_result(publication, plan)
            for page in plan["pages"]:
                self.assertEqual(Path(self.lib.corpus_path(page["slug"])).read_bytes(),
                                 self.fixture.raw(page))
        self.assertLessEqual(len(canonical(result)), self.lib.MAX_STATE_JSON_BYTES)

    @contextlib.contextmanager
    def no_render(self):
        with mock.patch.object(self.lib, "_render_event_shard", side_effect=AssertionError("batch rerendered")), \
                mock.patch.object(self.lib, "_plan_event_day_update", side_effect=AssertionError("batch reassigned events")), \
                mock.patch.object(self.lib, "update_day_page", side_effect=AssertionError("batch called legacy appender")):
            yield

    def assert_compose_refused(self, plans, *, expected=None):
        before = self.fixture.snapshot()
        with self.no_render(), \
                mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("composition wrote")), \
                self.assertRaises(REFUSALS):
            self.compose(plans, expected=expected)
        self.assertEqual(self.fixture.snapshot(), before)

    def assert_publish_refused(self, batch, *, expected=None):
        before = self.fixture.snapshot()
        with self.no_render(), \
                mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("write before batch refusal")), \
                mock.patch.object(self.lib, "_before_corpus_mutation", side_effect=AssertionError("mutation before batch refusal")), \
                self.assertRaises(REFUSALS):
            self.publish(batch, expected=expected)
        self.assertEqual(self.fixture.snapshot(), before)

    def test_shared_cut_composition_is_readonly_and_publication_preserves_individual_results(self):
        plans = self.plans(historical=True)
        original, before = copy.deepcopy(plans), self.fixture.snapshot()
        with self.no_render(), \
                mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("composition wrote")), \
                mock.patch.object(self.lib, "_before_corpus_mutation", side_effect=AssertionError("composition mutated")):
            batch = self.compose(plans)
        self.assertEqual(self.fixture.snapshot(), before)
        self.assertEqual(plans, original)
        self.assert_batch(batch, original)
        with self.no_render():
            result = self.publish(batch)
        self.assert_result(result, batch)
        self.assertEqual(plans, original)
        before = self.fixture.snapshot()
        with self.no_render(), mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("complete retry rewrote")):
            self.assertEqual(self.publish(batch), result)
        self.assertEqual(self.fixture.snapshot(), before)

    def test_architecture_names_the_original_batch_cut_and_retry_boundary(self):
        architecture = (Path(__file__).resolve().parents[1] / "docs/ARCHITECTURE.md").read_text()
        for phrase in ("_compose_event_page_plans", "_publish_event_page_plan_batch",
                       "original sealed batch", "shared before-images",
                       "write/write", "write/retained-page"):
            self.assertIn(phrase, architecture)

    def _mutate_earlier_member_during_last_pin(self, *, publishing, whole_batch=False):
        plans = self.plans(historical=True)
        batch = self.compose(plans) if publishing else None
        members = batch["members"] if publishing else plans
        last_body = canonical({key: value for key, value in members[-1].items()
                               if key != "plan_sha256"})
        changed = []

        def finalized(raw):
            if raw == last_body and not changed:
                self.fixture.assert_owned()
                (batch if whole_batch else members[0])["non_claims"].clear()
                changed.append(True)

        with mock.patch.object(self.lib, "hashlib", individual.capture_tests._HashShim(finalized)):
            if publishing:
                self.assert_publish_refused(batch)
            else:
                self.assert_compose_refused(plans)
        self.assertTrue(changed, "actual last-member pin finalization was not reached")

    def test_composition_cannot_adopt_an_earlier_member_changed_during_later_pin(self):
        self._mutate_earlier_member_during_last_pin(publishing=False)

    def test_publication_cannot_adopt_an_earlier_member_changed_during_later_pin(self):
        self._mutate_earlier_member_during_last_pin(publishing=True)

    def test_publication_cannot_adopt_changed_batch_nonclaims_after_whole_batch_pin(self):
        self._mutate_earlier_member_during_last_pin(publishing=True, whole_batch=True)

    def test_later_member_replays_shared_original_bytes_after_earlier_day_changed(self):
        _old, source, _record = self.fixture.fixture._source()
        old_raw = source.read_bytes()
        plans = self.plans()
        first, later = plans
        relative = source.relative_to(self.corpus).as_posix()
        self.assertTrue(any(page["slug"] + ".md" == relative and page["write"]
                            for page in first["pages"]))
        original_page = next(page for page in first["pages"]
                             if page["slug"] + ".md" == relative)
        self.assertIsNotNone(original_page["before"])
        original_generation = tuple(original_page["before"]["generation"][key]
                                    for key in ("device", "inode", "size", "mtime_ns", "ctime_ns"))
        self.assertIn(relative, {row["relative"] for row in later["read_dependencies"]["files"]})
        self.assertNotIn(relative, {page["slug"] + ".md" for page in later["pages"]})
        batch = self.compose(plans)
        last_page = self.write_pages(batch)[-1]
        last_path = self.lib.corpus_path(last_page["slug"])
        actual_write = self.lib.atomic_write
        stopped = []

        def stop_later(path, data, **kwargs):
            if os.fspath(path) == last_path:
                stopped.append(last_path)
                raise OSError("synthetic stop before later day")
            return actual_write(path, data, **kwargs)

        with mock.patch.object(self.lib, "atomic_write", side_effect=stop_later), self.assertRaises(REFUSALS):
            self.publish(batch)
        self.assertEqual(stopped, [last_path])
        self.assertNotEqual(source.read_bytes(), old_raw)
        observed = []
        actual_read = self.lib._read_event_page

        def read(slug, **kwargs):
            result = actual_read(slug, **kwargs)
            # The same public reader also parses frozen target images. Only
            # source reads carry the original scan's expected generation;
            # target-parser reads legitimately contain the new page bytes.
            expected_generation = kwargs.get("expected_generation")
            if slug + ".md" == relative and kwargs.get("dependency_capture") is not None \
                    and expected_generation is not None:
                observed.append((expected_generation, result.encode("utf-8")))
            return result

        with self.no_render(), mock.patch.object(self.lib, "_read_event_page", side_effect=read):
            result = self.publish(batch)
        self.assertTrue(observed, "retry did not exercise the original shared-reader path")
        for expected_generation, raw in observed:
            self.assertEqual(expected_generation, original_generation)
            self.assertEqual(raw, old_raw)
        self.assert_result(result, batch)

    def test_partial_batch_retry_keeps_original_append_rosters_without_recomposition(self):
        plans = self.plans()
        batch = self.compose(plans)
        original = copy.deepcopy(batch)
        writes = self.write_pages(batch)
        first_path = Path(self.lib.corpus_path(writes[0]["slug"]))
        last_path = self.lib.corpus_path(writes[-1]["slug"])
        actual_write = self.lib.atomic_write
        stopped = []

        def interrupt(path, data, **kwargs):
            if os.fspath(path) == last_path:
                stopped.append(last_path)
                raise OSError("synthetic cross-day interruption")
            return actual_write(path, data, **kwargs)

        with self.no_render(), mock.patch.object(self.lib, "atomic_write", side_effect=interrupt), self.assertRaises(REFUSALS):
            self.publish(batch)
        self.assertEqual(stopped, [last_path])
        self.assertEqual(first_path.read_bytes(), self.fixture.raw(writes[0]))
        self.assertFalse(Path(last_path).exists())
        self.assert_compose_refused(plans)
        with self.no_render(), \
                mock.patch.object(self.lib, "_compose_event_page_plans", side_effect=AssertionError("retry recomposed")):
            result = self.publish(batch)
        self.assert_result(result, original)
        self.assertEqual(batch, original)

    def test_new_ancestor_only_interruption_retries_original_declared_directory_delta(self):
        batch = self.compose(self.plans())
        self.assertIn("events", batch["new_directories"])
        self.assertIn("events/org", batch["new_directories"])
        actual_ensure = self.lib.ensure_durable_directory
        made = []

        def interrupt(path, *args, **kwargs):
            result = actual_ensure(path, *args, **kwargs)
            if os.path.abspath(path) == str(self.corpus / "events/org"):
                made.append(os.fspath(path))
                raise OSError("synthetic interruption after owned ancestor creation")
            return result

        with mock.patch.object(self.lib, "ensure_durable_directory", side_effect=interrupt), self.assertRaises(REFUSALS):
            self.publish(batch)
        self.assertTrue(made)
        self.assertTrue((self.corpus / "events/org").is_dir())
        self.assertEqual(list((self.corpus / "events/org").iterdir()), [])
        with self.no_render():
            result = self.publish(batch)
        self.assert_result(result, batch)

    def test_existing_individual_publisher_keeps_its_original_foreign_delta_refusal(self):
        plans = self.plans(historical=True)
        first, later = plans
        self.fixture.publish(first)
        self.fixture.assert_refused_without_writes(later)

    def test_complete_scans_retain_legacy_staging_entries_without_cleanup(self):
        _old, source, _record = self.fixture.fixture._source()
        staging = source.parent / ".page.fixture.new"
        staging.write_bytes(b"retained legacy staging bytes\n")
        staging.chmod(0o600)
        retained = {"generation": individual.generation(staging.stat()),
                    "raw": staging.read_bytes()}
        plans = [self.fixture.prepare(
            [self.fixture.event(day, "native:batch:" + day)], day=day)
                 for day in ("2026-01-06", "2026-01-07")]
        batch = self.compose(plans)
        directory = next(row for row in batch["read_dependencies"]["directories"]
                         if row["relative"] == "events/org")
        self.assertIn({"name": staging.name, "generation": retained["generation"]},
                      directory["before"]["entries"])
        with self.no_render():
            result = self.publish(batch)
        self.assert_result(result, batch)
        self.assertEqual({"generation": individual.generation(staging.stat()),
                          "raw": staging.read_bytes()}, retained)

    def test_shared_readonly_targets_keep_all_original_retained_admission_versions(self):
        self.fixture.fixture._source()
        plans = [self.fixture.prepare([self.fixture.event(day)], day=day)
                 for day in ("2026-01-06", "2026-01-07")]
        shared = [{page["slug"] for page in plan["pages"]} for plan in plans]
        self.assertEqual(shared[0], shared[-1])
        self.assertTrue(shared[0])
        self.assertTrue(all(not page["write"] for plan in plans for page in plan["pages"]))
        batch = self.compose(plans)
        self.assert_batch(batch, plans)
        self.assertEqual(batch["write_order"], [])
        self.assertEqual(batch["new_directories"], [])
        before = self.fixture.snapshot()
        with self.no_render(), mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("readonly targets changed")):
            result = self.publish(batch)
        self.assert_result(result, batch)
        self.assertEqual(self.fixture.snapshot(), before)

    def test_write_write_overlap_refuses_without_merging_frozen_target_images(self):
        plans = [self.fixture.prepare([self.fixture.event(occurrence=occurrence)])
                 for occurrence in ("native:batch:first", "native:batch:second")]
        self.assertEqual([page["slug"] for page in plans[0]["pages"]],
                         [page["slug"] for page in plans[-1]["pages"]])
        self.assertNotEqual(plans[0]["plan_sha256"], plans[-1]["plan_sha256"])
        self.assert_compose_refused(plans)

    def test_batch_requires_a_nonempty_unique_day_roster_from_one_organ(self):
        plans = self.plans()
        template = self.fixture.event()
        foreign_event = self.lib.Event(
            "other", template.ts, template.kind, template.summary,
            set(template.links), set(template.tags), occurrence="native:batch:other")
        foreign = self.fixture.prepare([foreign_event], organ="other")
        for members in ([], [plans[0], plans[0]], [plans[0], foreign]):
            with self.subTest(members=[plan["plan_sha256"] for plan in members]):
                self.assert_compose_refused(members)

    def test_write_readonly_page_overlap_refuses_instead_of_rewriting_retained_version(self):
        self.fixture.fixture._source()
        write = self.fixture.prepare([self.fixture.event(occurrence="native:batch:new")])
        retained = self.fixture.prepare([self.fixture.event("2026-01-07")], day="2026-01-07")
        self.assertTrue(any(page["write"] for page in write["pages"]))
        self.assertTrue(all(not page["write"] for page in retained["pages"]))
        self.assertEqual({page["slug"] for page in write["pages"]},
                         {page["slug"] for page in retained["pages"]})
        self.assert_compose_refused([write, retained])

    def test_same_native_occurrence_cannot_be_independently_appended_across_days(self):
        plans = [self.fixture.prepare([self.fixture.event(day)], day=day)
                 for day in (self.fixture.day, "2026-01-07")]
        self.assertEqual(plans[0]["appended_event_ids"], plans[-1]["appended_event_ids"])
        self.assertTrue(plans[0]["appended_event_ids"])
        self.assertNotEqual(plans[0]["day_slugs"], plans[-1]["day_slugs"])
        self.assert_compose_refused(plans)

    def test_member_pin_roster_and_batch_external_pin_are_independent_authority(self):
        plans = self.plans()
        pins = [plan["plan_sha256"] for plan in plans]
        foreign = self.fixture.prepare([self.fixture.event(occurrence="native:batch:foreign")])
        for supplied in ([], list(reversed(pins)), [foreign["plan_sha256"] for _plan in plans]):
            with self.subTest(pins=supplied):
                self.assert_compose_refused(plans, expected=supplied)
        batch = self.compose(plans, expected=pins)
        self.assert_publish_refused(batch, expected=foreign["plan_sha256"])
        changed = copy.deepcopy(batch)
        changed["non_claims"] = []
        changed["batch_sha256"] = own(changed)
        self.assert_publish_refused(changed, expected=batch["batch_sha256"])
        self.assert_publish_refused(changed)

    def test_conflicting_original_file_generations_refuse_a_mixed_capture_cut(self):
        _old, source, _record = self.fixture.fixture._source()
        first = self.fixture.prepare([self.fixture.event("2026-01-06", "native:batch:first")], day="2026-01-06")
        self.fixture.replace_same_bytes(source, "retained-between-plans.md")
        later = self.fixture.prepare([self.fixture.event("2026-01-07", "native:batch:later")], day="2026-01-07")
        relative = source.relative_to(self.corpus).as_posix()
        first_row = next(row for row in first["read_dependencies"]["files"] if row["relative"] == relative)
        later_row = next(row for row in later["read_dependencies"]["files"] if row["relative"] == relative)
        self.assertEqual(first_row["before"]["raw_sha256"], later_row["before"]["raw_sha256"])
        self.assertNotEqual(first_row["before"]["generation"], later_row["before"]["generation"])
        self.assert_compose_refused([first, later])

    def test_rehashed_missing_dependency_anchor_and_scan_member_refuse_before_writes(self):
        batch = self.compose(self.plans(historical=True))
        relative = self.fixture.slug + ".md"
        changes = []
        missing_file = copy.deepcopy(batch)
        files = missing_file["read_dependencies"]["files"]
        removed = next(row for row in files if row["relative"] == relative)
        files.remove(removed)
        changes.append(missing_file)
        missing_anchor = copy.deepcopy(batch)
        rows = missing_anchor["read_dependencies"]["directories"]
        rows.remove(next(row for row in rows if row["relative"] == "events"))
        changes.append(missing_anchor)
        missing_entry = copy.deepcopy(batch)
        row = next(row for row in missing_entry["read_dependencies"]["directories"]
                   if row["relative"] == "events/org")
        entries = row["before"]["entries"]
        entry = next(entry for entry in entries if entry["name"] == Path(relative).name)
        entries.remove(entry)
        changes.append(missing_entry)
        for changed in changes:
            changed["batch_sha256"] = own(changed)
            with self.subTest(dependencies=changed["read_dependencies"]):
                self.assert_publish_refused(changed)

    def test_rehashed_omission_from_every_member_does_not_hide_an_actual_scan_entry(self):
        batch = self.compose(self.plans(historical=True))
        relative = self.fixture.slug + ".md"
        changed = copy.deepcopy(batch)
        old_pins = [plan["plan_sha256"] for plan in changed["members"]]
        for deps in [changed["read_dependencies"]] + [plan["read_dependencies"] for plan in changed["members"]]:
            deps["files"] = [row for row in deps["files"] if row["relative"] != relative]
            row = next(row for row in deps["directories"] if row["relative"] == "events/org")
            row["before"]["entries"] = [entry for entry in row["before"]["entries"]
                                          if entry["name"] != Path(relative).name]
        for member in changed["members"]:
            member["plan_sha256"] = individual.own(member)
        remap = dict(zip(old_pins, [plan["plan_sha256"] for plan in changed["members"]]))
        for row in changed["write_order"]:
            row["plan_sha256"] = remap[row["plan_sha256"]]
        changed["batch_sha256"] = own(changed)
        self.assert_publish_refused(changed)

    def test_rehashed_write_order_or_new_ancestor_delta_must_equal_derived_member_effects(self):
        batch = self.compose(self.plans())
        changes = []
        reversed_writes = copy.deepcopy(batch)
        reversed_writes["write_order"].reverse()
        self.assertNotEqual(reversed_writes["write_order"], batch["write_order"])
        changes.append(reversed_writes)
        missing_write = copy.deepcopy(batch)
        missing_write["write_order"].pop()
        changes.append(missing_write)
        foreign_ancestor = copy.deepcopy(batch)
        foreign_ancestor["new_directories"].append("epochs/org")
        foreign_ancestor["new_directories"].sort()
        changes.append(foreign_ancestor)
        for changed in changes:
            changed["batch_sha256"] = own(changed)
            with self.subTest(order=changed["write_order"], ancestors=changed["new_directories"]):
                self.assert_publish_refused(changed)

    def test_foreign_child_in_declared_created_directory_is_not_an_own_write_delta(self):
        batch = self.compose(self.plans())
        directory = self.corpus / "events/org"
        directory.mkdir(parents=True)
        (directory / "foreign.txt").write_bytes(b"unadmitted directory member\n")
        self.assert_publish_refused(batch)

    def test_symlink_cannot_satisfy_a_declared_new_ancestor(self):
        batch = self.compose(self.plans())
        outside = self.fixture.fixture.root / "outside-corpus"
        outside.mkdir()
        (self.corpus / "events").symlink_to(outside, target_is_directory=True)
        self.assert_publish_refused(batch)
        self.assertEqual(list(outside.iterdir()), [])

    def test_unchanged_byte_replacement_of_nonwrite_shared_source_refuses(self):
        batch = self.compose(self.plans(historical=True))
        source = Path(self.lib.corpus_path(self.fixture.slug))
        self.fixture.replace_same_bytes(source, "retained-before-batch-publish.md")
        self.assert_publish_refused(batch)

    def test_missing_shared_source_refuses_without_reassigning_occurrences(self):
        batch = self.compose(self.plans(historical=True))
        source = Path(self.lib.corpus_path(self.fixture.slug))
        source.rename(self.fixture.fixture.root / "retained-missing-source.md")
        self.assert_publish_refused(batch)

    def test_unrelated_existing_directory_member_is_not_exempted_by_day_writes(self):
        batch = self.compose(self.plans(historical=True))
        (self.corpus / "events/org/unadmitted.txt").write_bytes(b"unadmitted sibling\n")
        self.assert_publish_refused(batch)

    def test_real_owner_covers_admission_projection_hash_copy_write_and_final_checks(self):
        plans = self.plans(historical=True)
        phase, observed, written = ["compose"], [], []
        actual_owner = self.lib.corpus_owner
        actual_identity = self.lib._source_path_identity
        actual_project = self.lib._corpus_page_version_from_bytes
        actual_write = self.lib.atomic_write

        def probe(boundary):
            self.fixture.assert_owned()
            observed.append((phase[0], boundary))

        @contextlib.contextmanager
        def owned():
            with actual_owner() as descriptor:
                probe("owner-enter")
                try:
                    yield descriptor
                finally:
                    probe("owner-exit")

        def identity(path, *args, **kwargs):
            corpus_path = os.path.commonpath((os.path.abspath(path), str(self.corpus))) == str(self.corpus)
            if corpus_path:
                probe("named-check")
            result = actual_identity(path, *args, **kwargs)
            if corpus_path:
                probe("readback-check" if written else "named-return")
            return result

        def project(*args, **kwargs):
            probe("projection")
            result = actual_project(*args, **kwargs)
            probe("projection-return")
            return result

        def detach(*args, **kwargs):
            probe("copy")
            result = copy.deepcopy(*args, **kwargs)
            probe("copy-return")
            return result

        def write(path, data, **kwargs):
            probe("write")
            result = actual_write(path, data, **kwargs)
            written.append(os.fspath(path))
            probe("write-return")
            return result

        with mock.patch.object(self.lib, "corpus_owner", owned), \
                mock.patch.object(self.lib, "_source_path_identity", side_effect=identity), \
                mock.patch.object(self.lib, "_corpus_page_version_from_bytes", side_effect=project), \
                mock.patch.object(self.lib, "copy", individual._ModuleShim(copy, deepcopy=detach)), \
                mock.patch.object(self.lib, "hashlib", individual.capture_tests._HashShim(lambda _raw: probe("hash"))), \
                mock.patch.object(self.lib, "atomic_write", side_effect=write):
            batch = self.compose(plans)
            self.fixture.assert_owner_released()
            phase[0] = "publish"
            result = self.publish(batch)
            self.fixture.assert_owner_released()
        self.assert_result(result, batch)
        for operation in ("compose", "publish"):
            for boundary in ("owner-enter", "projection", "hash", "copy", "named-check", "owner-exit"):
                self.assertIn((operation, boundary), observed)
        self.assertIn(("publish", "write"), observed)
        self.assertIn(("publish", "readback-check"), observed)

    def test_batch_helpers_preserve_the_callers_nested_owner_lease(self):
        with self.lib.corpus_owner():
            descriptor = self.lib._CORPUS_OWNER_FD.get()
            plans = self.plans()
            batch = self.compose(plans)
            self.fixture.assert_owned()
            self.assertEqual(self.lib._CORPUS_OWNER_FD.get(), descriptor)
            result = self.publish(batch)
            self.fixture.assert_owned()
            self.assertEqual(self.lib._CORPUS_OWNER_FD.get(), descriptor)
        self.fixture.assert_owner_released()
        self.assert_result(result, batch)

    def test_late_real_target_hash_replacement_refuses_success_and_retains_published_prefix(self):
        batch = self.compose(self.plans(historical=True))
        source = Path(self.lib.corpus_path(self.fixture.slug))
        first = self.write_pages(batch)[0]
        target = Path(self.lib.corpus_path(first["slug"]))
        target_raw = self.fixture.raw(first)
        actual_write = self.lib.atomic_write
        written, changed = [], []

        def write(path, data, **kwargs):
            result = actual_write(path, data, **kwargs)
            if os.fspath(path) == str(target):
                written.append(str(target))
            return result

        def finalized(raw):
            if written and raw == target_raw and not changed:
                self.fixture.assert_owned()
                self.assertEqual(target.read_bytes(), target_raw)
                changed.append(self.fixture.replace_same_bytes(source, "retained-batch-readback.md"))

        with mock.patch.object(self.lib, "atomic_write", side_effect=write), \
                mock.patch.object(self.lib, "hashlib", individual.capture_tests._HashShim(finalized)), \
                self.assertRaises(REFUSALS):
            self.publish(batch)
        self.assertTrue(written)
        self.assertTrue(changed, "real target readback digest boundary did not execute")
        self.assertEqual(target.read_bytes(), target_raw)
        self.assertEqual(source.read_bytes(), changed[0].read_bytes())
        self.fixture.assert_owner_released()

    def test_final_batch_result_copy_cannot_hide_a_late_shared_dependency_replacement(self):
        batch = self.compose(self.plans(historical=True))
        original = copy.deepcopy(batch)
        source = Path(self.lib.corpus_path(self.fixture.slug))
        changed = []

        def detach(value, *args, **kwargs):
            result = copy.deepcopy(value, *args, **kwargs)
            if type(value) is dict and value.get("schema") == "sia-event-page-render-batch-publication-v1" and not changed:
                self.fixture.assert_owned()
                for page in self.write_pages(batch):
                    self.assertEqual(Path(self.lib.corpus_path(page["slug"])).read_bytes(), self.fixture.raw(page))
                changed.append(self.fixture.replace_same_bytes(source, "retained-batch-result-copy.md"))
            return result

        with mock.patch.object(self.lib, "copy", individual._ModuleShim(copy, deepcopy=detach)), self.assertRaises(REFUSALS):
            self.publish(batch)
        self.assertTrue(changed, "actual detached batch-result boundary did not execute")
        self.assertEqual(batch, original)
        self.assertEqual(source.read_bytes(), changed[0].read_bytes())
        self.fixture.assert_owner_released()

    def test_batch_and_publication_are_detached_without_mutating_individual_plan_bytes(self):
        plans = self.plans()
        original = copy.deepcopy(plans)
        batch = self.compose(plans)
        pinned_batch = copy.deepcopy(batch)
        plans[0]["input_records"].clear()
        self.assertEqual(batch, pinned_batch)
        result = self.publish(batch)
        self.assert_result(result, pinned_batch)
        result["members"][0]["admissions"].clear()
        self.assertEqual(batch, pinned_batch)
        self.assertEqual(batch["members"], original)

    def test_aggregate_batch_cap_precedes_copy_decode_hash_projection_or_mutation(self):
        plans = self.plans(historical=True)
        batch = self.compose(plans)
        # Boundaries come from the complete fixture documents, not a manual
        # byte estimate. Every individual plan fits; the enclosing list and
        # batch do not. No new production cap is introduced.
        boundary = max(len(canonical(plan)) for plan in plans)
        for plan in plans:
            self.assertLessEqual(len(canonical(plan)), boundary)
        self.assertGreater(len(canonical(plans)), boundary)
        self.assertGreater(len(canonical(batch)), boundary)
        pins = [plan["plan_sha256"] for plan in plans]
        pin = batch["batch_sha256"]
        before = self.fixture.snapshot()
        forbidden = mock.Mock(side_effect=AssertionError("expensive callback before complete batch byte admission"))
        with mock.patch.object(self.lib, "MAX_STATE_JSON_BYTES", boundary), \
                mock.patch.object(self.lib, "copy", individual._ModuleShim(copy, deepcopy=forbidden)), \
                mock.patch.object(self.lib, "hashlib", individual._ModuleShim(hashlib, sha256=forbidden)), \
                mock.patch.object(self.lib, "base64", individual._ModuleShim(base64, b64encode=forbidden, b64decode=forbidden), create=True), \
                mock.patch.object(self.lib, "_corpus_page_version_from_bytes", forbidden), \
                mock.patch.object(self.lib, "_before_corpus_mutation", forbidden), \
                mock.patch.object(self.lib, "atomic_write", forbidden):
            with self.assertRaises(REFUSALS):
                self.compose(plans, expected=pins)
            with self.assertRaises(REFUSALS):
                self.publish(batch, expected=pin)
        forbidden.assert_not_called()
        self.assertEqual(self.fixture.snapshot(), before)

    def test_original_source_event_ceiling_applies_across_members_before_copy_or_hash(self):
        plans = self.plans()
        batch = self.compose(plans)
        boundary = max(len(plan["input_records"]) for plan in plans)
        self.assertGreater(sum(len(plan["input_records"]) for plan in plans), boundary)
        pins = [plan["plan_sha256"] for plan in plans]
        pin = batch["batch_sha256"]
        forbidden = mock.Mock(side_effect=AssertionError("materialization before aggregate event-count admission"))
        with mock.patch.object(self.lib, "MAX_SOURCE_REPLAY_EVENTS", boundary), \
                mock.patch.object(self.lib, "copy", individual._ModuleShim(copy, deepcopy=forbidden)), \
                mock.patch.object(self.lib, "hashlib", individual._ModuleShim(hashlib, sha256=forbidden)), \
                mock.patch.object(self.lib, "base64", individual._ModuleShim(base64, b64encode=forbidden, b64decode=forbidden), create=True), \
                mock.patch.object(self.lib, "atomic_write", forbidden):
            with self.assertRaises(REFUSALS):
                self.compose(plans, expected=pins)
            with self.assertRaises(REFUSALS):
                self.publish(batch, expected=pin)
        forbidden.assert_not_called()

    def test_combined_event_lookup_roster_is_admitted_before_any_batch_write(self):
        plans = self.plans(historical=True)
        batch = self.compose(plans)
        existing = {path.relative_to(self.corpus).as_posix()
                    for path in (self.corpus / "events/org").glob("*.md")}
        targets = [{page["slug"] + ".md" for page in plan["pages"] if page["write"]}
                   for plan in plans]
        boundary = max(len(existing | member_targets) for member_targets in targets)
        for member_targets in targets:
            self.assertLessEqual(len(existing | member_targets), boundary)
        self.assertGreater(len(existing.union(*targets)), boundary)
        with mock.patch.object(self.lib, "MAX_EVENT_LOOKUP_PAGES", boundary):
            self.assert_compose_refused(plans)
            self.assert_publish_refused(batch)

    def test_individual_page_ceiling_still_applies_before_batch_decode_or_hash(self):
        plans = self.plans()
        batch = self.compose(plans)
        # Actual byte length of a fixture delimiter, not a manually derived
        # numerical result or a new production ceiling.
        boundary = len(b"\n")
        for page in self.write_pages(batch):
            self.assertGreater(page["raw_bytes"], boundary)
        pins = [plan["plan_sha256"] for plan in plans]
        pin = batch["batch_sha256"]
        forbidden = mock.Mock(side_effect=AssertionError("decoded or hashed over-bound constituent page"))
        with mock.patch.object(self.lib, "MAX_EVENT_PAGE_BYTES", boundary), \
                mock.patch.object(self.lib, "copy", individual._ModuleShim(copy, deepcopy=forbidden)), \
                mock.patch.object(self.lib, "hashlib", individual._ModuleShim(hashlib, sha256=forbidden)), \
                mock.patch.object(self.lib, "base64", individual._ModuleShim(base64, b64encode=forbidden, b64decode=forbidden), create=True), \
                mock.patch.object(self.lib, "atomic_write", forbidden):
            with self.assertRaises(REFUSALS):
                self.compose(plans, expected=pins)
            with self.assertRaises(REFUSALS):
                self.publish(batch, expected=pin)
        forbidden.assert_not_called()


if __name__ == "__main__":
    unittest.main()
