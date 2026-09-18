"""Cross-organ page publication closure contract.

Real existing Event/plan/batch fixtures are composed without inheriting their
test rosters. Every complete original one-organ batch remains independently
pinned and unchanged. Only the additional closure admits shared original
ancestors and its exact declared page/directory deltas across organs.

Capacity controls measure fixture documents and full relative path rosters;
they introduce no numerical oracle or larger production limit. Inspection
capacity means the admitted directory-entry roster, NOT cumulative syscalls
or a claim that retained-byte accounting bounds runtime inspection work.
This remains page-byte publication, not source acknowledgment or readiness.
"""

import base64
import contextlib
import copy
import hashlib
import inspect
import os
from pathlib import Path
import stat
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_event_page_batch as batch_tests
from tests import test_event_page_plan as page_tests
from tests import test_event_live_intake as intake_tests


CLOSURE_KEYS = {"schema", "batches", "read_dependencies", "write_order",
                "new_directories", "non_claims", "closure_sha256"}
RESULT_KEYS = {"schema", "status", "closure_sha256", "batches", "non_claims"}
NON_CLAIMS = batch_tests.NON_CLAIMS + [
    "Cross-organ closure publication admits only the original batches' declared page and ancestor deltas; it does not grant a batch authority over another organ or imply source acknowledgment.",
]
REFUSALS = page_tests.REFUSALS
canonical = page_tests.canonical
digest = page_tests.digest


def own(value):
    return digest(canonical({key: item for key, item in value.items() if key != "closure_sha256"}))


class EventPagePublicationClosure(unittest.TestCase):
    def setUp(self):
        self.case = batch_tests.EventPagePlanBatch(methodName="runTest")
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.fixture, self.lib, self.corpus = self.case.fixture, self.case.lib, self.case.corpus
        for name in ("_compose_event_page_batch_closure", "_publish_event_page_batch_closure"):
            self.assertTrue(callable(getattr(self.lib, name, None)),
                            "missing cross-organ closure API: " + name)

    def event(self, organ, day, occurrence):
        base = self.fixture.event(day, occurrence)
        return self.lib.Event(organ, base.ts, base.kind, base.summary,
                              [organ], [organ], occurrence=base.occurrence)

    def batches(self, *, historical=False, retained=False, organs=("alpha", "beta")):
        if historical:
            for organ in organs:
                event = self.event(organ, self.fixture.day, "native:closure:old:" + organ)
                plan = self.fixture.prepare([event], organ=organ)
                self.fixture.publish(plan)
        result = []
        for organ in organs:
            day = self.fixture.day if retained or not historical else "2026-01-07"
            occurrence = ("native:closure:old:" if retained else "native:closure:new:") + organ
            event = self.event(organ, day, occurrence)
            plan = self.fixture.prepare([event], organ=organ, day=day)
            result.append(self.case.compose([plan]))
        return result

    def compose(self, batches, *, expected=None):
        return self.lib._compose_event_page_batch_closure(
            batches=batches, expected_batch_sha256s=(
                [batch["batch_sha256"] for batch in batches] if expected is None else expected))

    def publish(self, closure, *, expected=None):
        return self.lib._publish_event_page_batch_closure(
            closure=closure, expected_closure_sha256=(
                closure["closure_sha256"] if expected is None else expected))

    def expected(self, batches):
        """Fixture projection of declared rosters, not a second source reader."""
        ordered = sorted(batches, key=lambda batch: batch["organ"])
        files, directories, writes, created = {}, {}, [], set()
        root = ordered[0]["read_dependencies"]["corpus_identity"]
        for batch in ordered:
            deps = batch["read_dependencies"]
            self.assertEqual(canonical(root), canonical(deps["corpus_identity"]))
            for row in deps["files"]:
                prior = files.setdefault(row["relative"], row)
                self.assertEqual(canonical(prior), canonical(row))
            for row in deps["directories"]:
                name, before = row["relative"], row["before"]
                if name not in directories:
                    directories[name] = row
                    continue
                previous = directories[name]["before"]
                if previous is None or before is None:
                    self.assertEqual(canonical(previous), canonical(before))
                else:
                    self.assertEqual(canonical(previous["identity"]), canonical(before["identity"]))
                    if previous["entries"] is None:
                        directories[name] = row
                    elif before["entries"] is not None:
                        self.assertEqual(canonical(previous["entries"]), canonical(before["entries"]))
            writes.extend({"batch_sha256": batch["batch_sha256"], **row}
                          for row in batch["write_order"])
            created.update(batch["new_directories"])
        body = {"schema": "sia-event-page-publication-closure-v1", "batches": ordered,
                "read_dependencies": {"schema": "sia-event-page-read-dependencies-v1",
                                      "corpus_identity": root,
                                      "directories": [directories[name] for name in sorted(directories)],
                                      "files": [files[name] for name in sorted(files)]},
                "write_order": writes, "new_directories": sorted(created),
                "non_claims": list(NON_CLAIMS)}
        return {**body, "closure_sha256": own(body)}

    def assert_closure(self, closure, originals):
        self.assertEqual(set(closure), CLOSURE_KEYS)
        self.assertEqual(canonical(closure), canonical(self.expected(originals)))
        self.assertLessEqual(len(canonical(closure)), self.lib.MAX_STATE_JSON_BYTES)
        for batch in closure["batches"]:
            self.assertEqual(set(batch), batch_tests.BATCH_KEYS)
            self.assertEqual(batch["batch_sha256"], batch_tests.own(batch))
            self.assertEqual(batch["non_claims"], batch_tests.NON_CLAIMS)
            for plan in batch["members"]:
                self.fixture.assert_plan(plan)

    def assert_result(self, result, closure):
        self.assertEqual(set(result), RESULT_KEYS)
        self.assertEqual(result["schema"], "sia-event-page-closure-publication-v1")
        self.assertEqual(result["status"], "page-bytes-published")
        self.assertEqual(result["closure_sha256"], closure["closure_sha256"])
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertEqual(len(result["batches"]), len(closure["batches"]))
        for result_batch, batch in zip(result["batches"], closure["batches"], strict=True):
            self.case.assert_result(result_batch, batch)
        self.assertLessEqual(len(canonical(result)), self.lib.MAX_STATE_JSON_BYTES)

    def writes(self, closure):
        batches = {batch["batch_sha256"]: batch for batch in closure["batches"]}
        result = []
        for row in closure["write_order"]:
            batch = batches[row["batch_sha256"]]
            plan = next(plan for plan in batch["members"] if plan["plan_sha256"] == row["plan_sha256"])
            result.append(next(page for page in plan["pages"] if page["slug"] == row["slug"]))
        return result

    @contextlib.contextmanager
    def no_render(self):
        with self.case.no_render(), \
                mock.patch.object(self.lib, "_compose_event_page_plans",
                                  side_effect=AssertionError("closure recomposed an original batch")):
            yield

    def refuse_compose(self, batches, *, expected=None):
        before = self.fixture.snapshot()
        with self.no_render(), \
                mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("composition wrote")), \
                mock.patch.object(self.lib, "_before_corpus_mutation", side_effect=AssertionError("composition mutated")), \
                self.assertRaises(REFUSALS):
            self.compose(batches, expected=expected)
        self.assertEqual(self.fixture.snapshot(), before)

    def refuse_publish(self, closure, *, expected=None):
        before = self.fixture.snapshot()
        with self.no_render(), \
                mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("write before closure refusal")), \
                mock.patch.object(self.lib, "_before_corpus_mutation", side_effect=AssertionError("mutation before closure refusal")), \
                self.assertRaises(REFUSALS):
            self.publish(closure, expected=expected)
        self.assertEqual(self.fixture.snapshot(), before)

    def test_public_closed_keyword_only_inputs(self):
        for name, fields in (
                ("_compose_event_page_batch_closure", {"batches", "expected_batch_sha256s"}),
                ("_publish_event_page_batch_closure", {"closure", "expected_closure_sha256"})):
            parameters = inspect.signature(getattr(self.lib, name)).parameters
            self.assertEqual(set(parameters), fields)
            for parameter in parameters.values():
                self.assertIs(parameter.default, inspect.Parameter.empty)
                self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_absent_shared_ancestor_composes_readonly_and_publishes_complete_original_batches(self):
        batches = self.batches()
        original, before = copy.deepcopy(batches), self.fixture.snapshot()
        self.assertFalse((self.corpus / "events").exists())
        self.assertTrue(all("events" in batch["new_directories"] for batch in batches))
        with self.no_render(), mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("compose wrote")):
            closure = self.compose(batches)
        self.assert_closure(closure, original)
        self.assertEqual(batches, original)
        self.assertEqual(self.fixture.snapshot(), before)
        self.assertEqual(closure["new_directories"], sorted({name for batch in batches for name in batch["new_directories"]}))
        with self.no_render():
            result = self.publish(closure)
        self.assert_result(result, closure)
        self.assertEqual(batches, original)
        before = self.fixture.snapshot()
        with self.no_render(), mock.patch.object(self.lib, "atomic_write", side_effect=AssertionError("retry rewrote")):
            self.assertEqual(self.publish(closure), result)
        self.assertEqual(self.fixture.snapshot(), before)

    def test_caller_order_binds_pins_before_deterministic_organ_sort(self):
        batches = self.batches()
        expected = self.compose(batches)
        reversed_batches = list(reversed(batches))
        with self.no_render():
            self.assertEqual(self.compose(reversed_batches), expected)
        self.refuse_compose(reversed_batches, expected=[batch["batch_sha256"] for batch in batches])
        self.assertEqual([batch["organ"] for batch in expected["batches"]], sorted(batch["organ"] for batch in batches))

    def test_nonempty_unique_organ_and_exact_pin_rosters(self):
        batches = self.batches()
        self.refuse_compose([], expected=[])
        self.refuse_compose(tuple(batches), expected=[batch["batch_sha256"] for batch in batches])
        self.refuse_compose([batches[0], copy.deepcopy(batches[0])])
        for pins in ([], [batches[0]["batch_sha256"]], ["0" * 64 for _ in batches],
                     tuple(batch["batch_sha256"] for batch in batches)):
            with self.subTest(pins=pins):
                self.refuse_compose(batches, expected=pins)
        closure = self.compose(batches)
        self.refuse_publish(closure, expected="0" * 64)
        self.refuse_publish(closure, expected="missing-independent-pin")

    def test_partial_cross_organ_prefix_retries_original_closure_without_replanning(self):
        batches = self.batches()
        closure = self.compose(batches)
        original = copy.deepcopy(closure)
        pages = self.writes(closure)
        first = Path(self.lib.corpus_path(pages[0]["slug"]))
        last = self.lib.corpus_path(pages[-1]["slug"])
        actual_write, stopped = self.lib.atomic_write, []

        def interrupt(path, data, **kwargs):
            if os.fspath(path) == last:
                stopped.append(last)
                raise OSError("synthetic cross-organ prefix interruption")
            return actual_write(path, data, **kwargs)

        with self.no_render(), mock.patch.object(self.lib, "atomic_write", side_effect=interrupt), self.assertRaises(REFUSALS):
            self.publish(closure)
        self.assertEqual(stopped, [last])
        self.assertEqual(first.read_bytes(), self.fixture.raw(pages[0]))
        self.assertFalse(Path(last).exists())
        self.refuse_compose(batches)
        # The new closure does not weaken the old standalone batch's foreign
        # sibling-delta rule or mutate its original absence witness.
        self.case.assert_publish_refused(batches[-1])
        with self.no_render(), mock.patch.object(self.lib, "_compose_event_page_batch_closure",
                                                 side_effect=AssertionError("retry recomposed closure")):
            result = self.publish(closure)
        self.assert_result(result, original)
        self.assertEqual(closure, original)

    def test_ancestor_only_prefix_is_an_exact_declared_delta(self):
        closure = self.compose(self.batches())
        actual_ensure, stopped = self.lib.ensure_durable_directory, []
        target = self.corpus / closure["new_directories"][-1]

        def interrupt(path, *args, **kwargs):
            result = actual_ensure(path, *args, **kwargs)
            if os.path.abspath(path) == str(target):
                stopped.append(str(target))
                raise OSError("synthetic stop after declared ancestor creation")
            return result

        with mock.patch.object(self.lib, "ensure_durable_directory", side_effect=interrupt), self.assertRaises(REFUSALS):
            self.publish(closure)
        self.assertTrue(stopped)
        self.assertTrue(target.is_dir())
        with self.no_render():
            result = self.publish(closure)
        self.assert_result(result, closure)

    def test_foreign_created_sibling_or_entry_is_not_an_admitted_closure_delta(self):
        closure = self.compose(self.batches())
        foreign = self.corpus / "events/foreign"
        foreign.mkdir(parents=True, mode=0o700)
        (foreign / "unplanned.txt").write_bytes(b"retained foreign fixture bytes")
        self.refuse_publish(closure)

    def test_symlink_cannot_satisfy_a_declared_new_organ_ancestor(self):
        closure = self.compose(self.batches())
        (self.corpus / "events").mkdir(mode=0o700)
        outside = self.fixture.fixture.root / "outside-closure"
        outside.mkdir(mode=0o700)
        (self.corpus / "events/alpha").symlink_to(outside, target_is_directory=True)
        self.refuse_publish(closure)

    def test_conflicting_shared_before_directory_cuts_refuse_even_with_rehashed_batches(self):
        batches = self.batches()
        changed = copy.deepcopy(batches)
        batch = changed[-1]
        # deepcopy preserves aliases across original batch/member rosters.
        # Establish all original absences before changing any occurrence.
        for document in [batch, *batch["members"]]:
            row = next(row for row in document["read_dependencies"]["directories"] if row["relative"] == "events")
            self.assertIsNone(row["before"])
        for document in [batch, *batch["members"]]:
            row = next(row for row in document["read_dependencies"]["directories"] if row["relative"] == "events")
            row["before"] = {"identity": copy.deepcopy(document["read_dependencies"]["corpus_identity"]), "entries": None}
        for plan in batch["members"]:
            previous = plan["plan_sha256"]
            plan["plan_sha256"] = page_tests.own(plan)
            for row in batch["write_order"]:
                if row["plan_sha256"] == previous:
                    row["plan_sha256"] = plan["plan_sha256"]
        batch["new_directories"].remove("events")
        batch["batch_sha256"] = batch_tests.own(batch)
        self.refuse_compose(changed)

    def test_rehashed_closure_union_and_effect_rosters_do_not_create_authority(self):
        closure = self.compose(self.batches())
        for change in ("file-omission", "directory-omission", "write-omission", "write-order", "ancestor-omission", "foreign-write", "nonclaims"):
            changed = copy.deepcopy(closure)
            if change == "file-omission":
                changed["read_dependencies"]["files"].pop()
            elif change == "directory-omission":
                changed["read_dependencies"]["directories"].pop()
            elif change == "write-omission":
                changed["write_order"].pop()
            elif change == "write-order":
                changed["write_order"].reverse()
            elif change == "ancestor-omission":
                changed["new_directories"].pop()
            elif change == "foreign-write":
                changed["write_order"][0]["slug"] = "events/foreign/2026-01-05"
            else:
                changed["non_claims"] = []
            changed["closure_sha256"] = own(changed)
            with self.subTest(change=change):
                self.refuse_publish(changed)

    def test_fully_rehashed_member_target_still_replays_native_page_grammar(self):
        batches = self.batches()
        batch, plan = batches[0], batches[0]["members"][0]
        page = next(page for page in plan["pages"] if page["write"])
        raw = self.fixture.raw(page)
        self.assertIn(b"sia_counts:", raw)
        invalid = raw.replace(b"sia_counts:", b"discarded_counts:", 1)
        previous = plan["plan_sha256"]
        self.fixture.retarget(plan, page, invalid)
        for row in batch["write_order"]:
            if row["plan_sha256"] == previous:
                row["plan_sha256"] = plan["plan_sha256"]
        batch["batch_sha256"] = batch_tests.own(batch)
        self.refuse_compose(batches)
        self.refuse_publish(self.expected(batches))

    def test_changed_or_replaced_historical_source_blocks_all_organs_before_writes(self):
        batches = self.batches(historical=True)
        closure = self.compose(batches)
        source = self.corpus / ("events/alpha/" + self.fixture.day + ".md")
        retained = self.fixture.replace_same_bytes(source, "retained-closure-original.md")
        self.assertEqual(source.read_bytes(), retained.read_bytes())
        self.refuse_compose(batches)
        self.refuse_publish(closure)

    def test_unplanned_entry_in_existing_other_organ_is_not_hidden_by_target_delta(self):
        closure = self.compose(self.batches(historical=True))
        (self.corpus / "events/beta/unplanned.txt").write_bytes(b"foreign closure scan member")
        self.refuse_publish(closure)

    def test_actual_later_batch_pin_cannot_adopt_changed_earlier_batch_or_closure(self):
        batches = self.batches()
        original = copy.deepcopy(batches)
        closure = self.compose(batches)
        later_bytes = canonical({key: value for key, value in batches[-1].items() if key != "batch_sha256"})
        reached = []
        with mock.patch.object(self.lib, "hashlib", page_tests.capture_tests._HashShim(
                lambda raw: reached.append(True) if raw == later_bytes else None)):
            self.assertEqual(self.compose(batches), closure)
        self.assertTrue(reached, "the actual later independent batch hash was not reached")
        for phase in ("compose", "publish-earlier-batch", "publish-closure"):
            inputs = copy.deepcopy(original)
            supplied = self.expected(inputs)
            changed = []

            def finalize(raw):
                if raw == later_bytes and not changed:
                    self.fixture.assert_owned()
                    target = (inputs[0] if phase == "compose" else
                              supplied["batches"][0] if phase == "publish-earlier-batch" else supplied)
                    target["non_claims"].clear()
                    changed.append(True)

            with self.subTest(phase=phase), \
                    mock.patch.object(self.lib, "hashlib", page_tests.capture_tests._HashShim(finalize)):
                if phase == "compose":
                    self.refuse_compose(inputs)
                else:
                    self.refuse_publish(supplied)
            self.assertTrue(changed, "actual later batch-pin finalization did not execute")

    def test_final_publication_copy_cannot_hide_late_read_dependency_replacement(self):
        closure = self.compose(self.batches(historical=True))
        source = self.corpus / ("events/alpha/" + self.fixture.day + ".md")
        changed = []

        def detached(value, *args, **kwargs):
            result = copy.deepcopy(value, *args, **kwargs)
            if type(value) is dict and value.get("schema") == "sia-event-page-closure-publication-v1" and not changed:
                self.fixture.assert_owned()
                for page in self.writes(closure):
                    self.assertEqual(Path(self.lib.corpus_path(page["slug"])).read_bytes(), self.fixture.raw(page))
                changed.append(self.fixture.replace_same_bytes(source, "retained-closure-result-copy.md"))
            return result

        with mock.patch.object(self.lib, "copy", page_tests._ModuleShim(copy, deepcopy=detached)), self.assertRaises(REFUSALS):
            self.publish(closure)
        self.assertTrue(changed, "actual final closure-result detachment was not reached")
        self.assertEqual(source.read_bytes(), changed[0].read_bytes())
        self.fixture.assert_owner_released()

    def test_one_real_owner_covers_all_organs_callbacks_writes_and_final_checks(self):
        batches = self.batches()
        phase, observed, descriptors = ["compose"], [], {}
        original_owner = self.lib.corpus_owner
        original_project = self.lib._corpus_page_version_from_bytes
        original_identity, original_write = self.lib._source_path_identity, self.lib.atomic_write

        def probe(label):
            self.fixture.assert_owned()
            descriptor = self.lib._CORPUS_OWNER_FD.get()
            self.assertEqual(descriptor, descriptors.setdefault(phase[0], descriptor))
            observed.append((phase[0], label))

        @contextlib.contextmanager
        def owned():
            with original_owner() as descriptor:
                probe("owner-enter")
                try:
                    yield descriptor
                finally:
                    probe("owner-exit")

        def project(*args, **kwargs):
            probe("projection")
            return original_project(*args, **kwargs)

        def identity(path, *args, **kwargs):
            if os.path.commonpath((os.path.abspath(path), str(self.corpus))) == str(self.corpus):
                probe("named-check")
            return original_identity(path, *args, **kwargs)

        def detached(*args, **kwargs):
            probe("copy")
            return copy.deepcopy(*args, **kwargs)

        def write(path, data, **kwargs):
            probe("write")
            return original_write(path, data, **kwargs)

        with self.no_render(), mock.patch.object(self.lib, "corpus_owner", owned), \
                mock.patch.object(self.lib, "_corpus_page_version_from_bytes", side_effect=project), \
                mock.patch.object(self.lib, "_source_path_identity", side_effect=identity), \
                mock.patch.object(self.lib, "copy", page_tests._ModuleShim(copy, deepcopy=detached)), \
                mock.patch.object(self.lib, "hashlib", page_tests.capture_tests._HashShim(lambda _raw: probe("hash"))), \
                mock.patch.object(self.lib, "atomic_write", side_effect=write):
            closure = self.compose(batches)
            self.fixture.assert_owner_released()
            phase[0] = "publish"
            result = self.publish(closure)
            self.fixture.assert_owner_released()
        self.assert_result(result, closure)
        for operation in ("compose", "publish"):
            for boundary in ("owner-enter", "hash", "copy", "projection", "named-check", "owner-exit"):
                self.assertIn((operation, boundary), observed)
        self.assertIn(("publish", "write"), observed)

    def test_final_detachment_cannot_adopt_changed_closed_result_nonclaims(self):
        batches = self.batches()
        original_batches = copy.deepcopy(batches)
        closure = self.compose(batches)
        for phase in ("compose", "publish"):
            schema = ("sia-event-page-publication-closure-v1" if phase == "compose"
                      else "sia-event-page-closure-publication-v1")
            reached, changed = [], []

            def final_result(value):
                return type(value) is dict and value.get("schema") == schema \
                    and "closure_sha256" in value

            def unchanged(value, *args, **kwargs):
                if final_result(value):
                    reached.append(True)
                return copy.deepcopy(value, *args, **kwargs)

            def tampered(value, *args, **kwargs):
                if final_result(value):
                    self.fixture.assert_owned()
                    self.assertEqual(value["non_claims"], NON_CLAIMS)
                    if phase == "compose":
                        self.assertEqual(value["closure_sha256"], own(value))
                    else:
                        self.assertEqual(value["closure_sha256"], closure["closure_sha256"])
                    value["non_claims"].clear()
                    changed.append(True)
                return copy.deepcopy(value, *args, **kwargs)

            with self.subTest(phase=phase):
                with mock.patch.object(self.lib, "copy", page_tests._ModuleShim(copy, deepcopy=unchanged)):
                    baseline = self.compose(batches) if phase == "compose" else self.publish(closure)
                self.assertTrue(reached, "the real final result detachment was not exercised")
                if phase == "compose":
                    self.assert_closure(baseline, original_batches)
                else:
                    self.assert_result(baseline, closure)
                with mock.patch.object(self.lib, "copy", page_tests._ModuleShim(copy, deepcopy=tampered)), \
                        self.assertRaises(REFUSALS):
                    if phase == "compose":
                        self.compose(batches)
                    else:
                        self.publish(closure)
                self.assertTrue(changed, "the actual final-copy mutation was not exercised")
                self.assertEqual(batches, original_batches)
                # Publication changes the real filesystem, not the original
                # closure. Compare all retained bytes and pins without asking
                # the original-before fixture to assert those paths absent.
                self.assertEqual(canonical(closure), canonical(self.expected(original_batches)))
                self.assertEqual(closure["closure_sha256"], own(closure))
                self.assertEqual(closure["non_claims"], NON_CLAIMS)

    def test_nested_owner_and_detached_results_preserve_original_batch_bytes(self):
        with self.lib.corpus_owner():
            descriptor = self.lib._CORPUS_OWNER_FD.get()
            batches = self.batches()
            original = copy.deepcopy(batches)
            closure = self.compose(batches)
            self.fixture.assert_owned()
            self.assertEqual(descriptor, self.lib._CORPUS_OWNER_FD.get())
            result = self.publish(closure)
            self.fixture.assert_owned()
            self.assertEqual(descriptor, self.lib._CORPUS_OWNER_FD.get())
        self.fixture.assert_owner_released()
        self.assert_result(result, closure)
        self.assertEqual(batches, original)
        result["batches"][0]["members"][0]["admissions"].clear()
        self.assertEqual(closure["batches"], original)
        batches[0]["members"].clear()
        self.assertEqual(closure["batches"], original)

    @contextlib.contextmanager
    def no_expensive_corpus_work(self):
        forbidden = mock.Mock(side_effect=AssertionError("work before complete closure admission"))
        original_open = self.lib._open_source_nofollow

        def opened(path, *args, **kwargs):
            if os.path.commonpath((os.path.abspath(path), str(self.corpus))) == str(self.corpus):
                return forbidden()
            return original_open(path, *args, **kwargs)

        with mock.patch.object(self.lib, "copy", page_tests._ModuleShim(copy, deepcopy=forbidden)), \
                mock.patch.object(self.lib, "hashlib", page_tests._ModuleShim(hashlib, sha256=forbidden)), \
                mock.patch.object(self.lib, "base64", page_tests._ModuleShim(base64, b64encode=forbidden, b64decode=forbidden), create=True), \
                mock.patch.object(self.lib, "_open_source_nofollow", side_effect=opened), \
                mock.patch.object(self.lib, "_read_event_page", forbidden), \
                mock.patch.object(self.lib, "_corpus_page_version_from_bytes", forbidden), \
                mock.patch.object(self.lib, "_before_corpus_mutation", forbidden), \
                mock.patch.object(self.lib, "atomic_write", forbidden):
            yield
        forbidden.assert_not_called()

    def test_whole_input_and_repeated_member_bytes_precede_copy_hash_decode_and_corpus_io(self):
        batches = self.batches()
        closure = self.compose(batches)
        pins = [batch["batch_sha256"] for batch in batches]
        request = {"batches": batches, "expected_batch_sha256s": pins}
        boundary = max(len(canonical(batch)) for batch in batches)
        self.assertGreater(len(canonical(request)), boundary)
        self.assertGreater(len(canonical(closure)), boundary)
        before = self.fixture.snapshot()
        with mock.patch.object(self.lib, "MAX_STATE_JSON_BYTES", boundary), self.no_expensive_corpus_work():
            with self.assertRaises(REFUSALS):
                self.compose(batches, expected=pins)
            with self.assertRaises(REFUSALS):
                self.publish(closure)
        self.assertEqual(self.fixture.snapshot(), before)

    def test_complete_extra_union_output_is_reserved_before_copy_hash_or_corpus_io(self):
        batches = self.batches()
        pins = [batch["batch_sha256"] for batch in batches]
        boundary = len(canonical({"batches": batches, "expected_batch_sha256s": pins}))
        expected = self.expected(batches)
        self.assertGreater(len(canonical(expected)), boundary)
        self.assertTrue(all(len(canonical(batch)) <= boundary for batch in batches))
        before = self.fixture.snapshot()
        with mock.patch.object(self.lib, "MAX_STATE_JSON_BYTES", boundary), self.no_expensive_corpus_work(), self.assertRaises(REFUSALS):
            self.compose(batches, expected=pins)
        self.assertEqual(self.fixture.snapshot(), before)

    def test_global_source_event_roster_is_not_reset_per_organ(self):
        batches = self.batches()
        closure = self.compose(batches)
        counts = [sum(len(plan["input_records"]) for plan in batch["members"]) for batch in batches]
        boundary = max(counts)
        self.assertGreater(sum(counts), boundary)
        with mock.patch.object(self.lib, "MAX_SOURCE_REPLAY_EVENTS", boundary), self.no_expensive_corpus_work():
            with self.assertRaises(REFUSALS):
                self.compose(batches)
            with self.assertRaises(REFUSALS):
                self.publish(closure)

    @staticmethod
    def capacity_rosters(batch):
        paths, entries = set(), set()
        for row in batch["read_dependencies"]["directories"]:
            before = row["before"]
            if before is None or before["entries"] is None:
                continue
            for entry in before["entries"]:
                relative = row["relative"] + "/" + entry["name"]
                entries.add(relative)
                if stat.S_ISREG(entry["generation"]["mode"]) and entry["name"].endswith(".md"):
                    paths.add(relative)
        for plan in batch["members"]:
            paths.update(slug + ".md" for slug in plan["day_slugs"])
        entries.update(row["slug"] + ".md" for row in batch["write_order"])
        entries.update(batch["new_directories"])
        return paths, entries

    def test_full_path_union_rosters_preserve_per_organ_caps_and_cover_declared_new_deltas(self):
        for retained in (False, True):
            # Each branch gets its own real existing fixture: no source reset,
            # deletion or stale generations are used to reuse a written cut.
            if retained:
                case = EventPagePublicationClosure(methodName="runTest")
                self.addCleanup(case.doCleanups)
                case.setUp()
            else:
                case = self
            batches = case.batches(historical=retained, retained=retained,
                                   organs=("alpha", "beta", "gamma") if retained else ("alpha", "beta"))
            closure = case.compose(batches)
            rosters = [case.capacity_rosters(batch) for batch in batches]
            for index, cap in enumerate(("MAX_EVENT_LOOKUP_PAGES", "MAX_EVENT_DIRECTORY_INSPECTIONS")):
                boundary = max(len(roster[index]) for roster in rosters)
                if retained and cap == "MAX_EVENT_DIRECTORY_INSPECTIONS":
                    # Preserve the existing separate EOF-probe allowance.
                    # The expanded full-path union must still exceed it.
                    boundary += case.lib.MAX_EVENT_DIRECTORY_INSPECTIONS - case.lib.MAX_EVENT_LOOKUP_PAGES
                whole = set().union(*(roster[index] for roster in rosters))
                self.assertGreater(len(whole), boundary)
                with self.subTest(retained=retained, cap=cap), mock.patch.object(case.lib, cap, boundary):
                    # The old one-organ checks remain unmodified and admit;
                    # only the new full-path closure union must now refuse.
                    for batch in batches:
                        self.assertEqual(case.case.compose(batch["members"]), batch)
                    case.refuse_compose(batches)
                    case.refuse_publish(closure)

    def test_complete_original_batches_remain_consumable_by_existing_pure_intake(self):
        fixture = intake_tests.EventLiveIntakeProjection(methodName="runTest")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        for entry in fixture.configuration["custom_collectors"]:
            entry["organ"] = entry["name"]
            entry["tags"] = [entry["name"]]
        fixture.catalog = fixture.catalog_for(fixture.configuration)
        supplied = {}
        for source in fixture.catalog["sources"]:
            if source["custom_name"] == "empty":
                continue
            base = fixture.event(occurrence="native:closure:intake:" + source["custom_name"])
            supplied[source["source_id"]] = [fixture.lib.Event(
                source["organ"], base.ts, base.kind, base.summary,
                [source["organ"]], [source["organ"]], occurrence=base.occurrence)]
        entry = fixture.entry(supplied)
        batches = [row["batch"] for row in entry["event_batches"]]
        pins = [row["expected_batch_sha256"] for row in entry["event_batches"]]
        original = copy.deepcopy(entry)
        request = fixture.request([entry])
        expected = fixture.project(request)
        closure = fixture.lib._compose_event_page_batch_closure(batches=batches, expected_batch_sha256s=pins)
        result = fixture.lib._publish_event_page_batch_closure(
            closure=closure, expected_closure_sha256=closure["closure_sha256"])
        self.assertEqual(result["status"], "page-bytes-published")
        self.assertEqual(closure["batches"], batches)
        self.assertEqual(entry, original)
        projected = fixture.project(request)
        self.assertEqual(projected, expected)
        fixture.assert_projection(projected, request)
        self.assertEqual([row["admission"]["event_batch_sha256"] for row in projected["associations"]], pins)


class EventPageClosureArchitecture(unittest.TestCase):
    def test_architecture_names_original_cross_organ_publication_boundary(self):
        architecture = (Path(__file__).resolve().parents[1] / "docs/ARCHITECTURE.md").read_text()
        for phrase in ("_compose_event_page_batch_closure", "_publish_event_page_batch_closure",
                       "original cross-organ cut", "complete original one-organ batches",
                       "directory-entry rosters"):
            self.assertIn(phrase, architecture)


if __name__ == "__main__":
    unittest.main()
