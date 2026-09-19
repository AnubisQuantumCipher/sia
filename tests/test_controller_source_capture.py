"""Actual collector returns, never source acknowledgment.

Root alone executes this fixture. It composes existing real Event/page/intake
fixtures and the original signed AEGIS fixture. The native keeper is real;
custom records are parsed by the real collector. Instrumented return controls
are explicitly synthetic and do not claim production collectors emitted an
otherwise unattainable duplicate. No resident source, engine or model is used.

Native envelope/epoch/receipt/cursor digests use ASCII canonical JSON with
finite floats and native integer identities. Nested Event/page/intake/policy
digests retain their ORIGINAL serializers. Input literals are fixture values;
clocks and component-policy numeric provenance remain test_live_loop's.

Journal acquisition, durable staging/readback and startup fences have separate
root-owned tests. This file does not authorize those effects or installation.
"""

import base64
import contextlib
import copy
import fcntl
import functools
import hashlib
import inspect
import json
import os
from pathlib import Path
import shutil
import stat
import unittest
from unittest import mock

from tests import test_calibration_benchmark as signed_tests
from tests import test_event_live_intake as intake_tests
from tests import test_event_page_plan as page_tests
from tests import test_live_loop as live_tests


EPOCH_KEYS = {
    "schema", "epoch_id", "started_at", "configuration", "expected_configuration_sha256",
    "source_catalog", "expected_source_catalog_sha256", "profile", "expected_profile_sha256",
    "live_policy", "expected_live_policy_sha256", "history", "expected_history_sha256",
    "predecessor", "non_claims",
}
BATCH_KEYS = {
    "schema", "status", "batch_id", "observed_at", "epoch", "epoch_sha256",
    "configuration_receipt", "source_returns", "cursor_proposal", "journal_proposals",
    "refusal_intents", "notification_baseline_attempt", "event_closure", "intake_projection",
    "non_claims", "batch_sha256",
}
CURSOR_KEYS = {"schema", "state_identity", "before", "before_value", "steps", "after", "after_sha256"}
CURSOR_STEP_KEYS = {"source_id", "removed_keys", "set_values", "after_sha256"}
REFUSAL_INTENT_KEYS = {"source_id", "record_refusals", "entry_refusals"}
CONFIG_RECEIPT_KEYS = {
    "schema", "scope", "observed_at", "config_file", "decoded_config", "active_config",
    "runtime_selection", "configuration_sha256", "source_catalog_sha256", "profile_sha256",
    "live_policy_sha256", "non_claims", "receipt_sha256",
}
CONFIG_NON_CLAIMS = [
    "This receipt observes current config.json bytes or absence and an equivalent active CONFIG value; it does not recover the bytes, file generation, or optional-source probes used at module import or the original load.",
    "Runtime collector names and configuration pins describe the held effective selection; they do not establish source installation, collector success, source freshness, or completeness outside that roster.",
    "Revalidation binds observed configuration and registry state at capture boundaries; it does not establish uninterrupted immutability against concurrent or hostile same-user changes.",
    "This configuration receipt is not a source return, durable source batch, cursor acknowledgment, live publication, or cognitive win.",
]
NON_CLAIMS = [
    "Collector completion means an admitted successful return from every declared source in this attempt; bounded windows, filtering and explicit record or entry refusals do not establish complete raw source history.",
    "Normalized Events, their source-return order and duplicates are retained; native Event timestamps remain metadata and do not replace the original integer controller observation clock.",
    "Cursor changes, journal cursor images and source-refusal rows are proposed effects only; capture and staging do not acknowledge cursors, settle refusals, publish pages or a live generation, or establish readiness.",
    "A notification baseline-attempt marker is an acquisition fence, not acknowledgment; its timestamp does not replace the supplied controller observation clock.",
    "Configuration receipts and collector execution are local observations, not source truth, uninterrupted source immutability, authenticated complete machine history, or a hostile same-user sandbox.",
    "All original configuration, source-return, event-plan, closure, intake and live-policy nonclaims remain controlling; this captured batch is not cognitive authorization or a held-out win.",
]
REFUSALS = (RuntimeError, ValueError, OSError)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def own(value, field):
    return digest({key: item for key, item in value.items() if key != field})


def file_image(path):
    raw = path.read_bytes()
    return {"generation": page_tests.generation(path.stat()), "raw_bytes": len(raw),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_utf8_base64": base64.b64encode(raw).decode("ascii")}


class ControllerSourceCapture(unittest.TestCase):
    def setUp(self):
        self.bridge = intake_tests.EventLiveIntakeProjection(methodName="runTest")
        self.addCleanup(self.bridge.doCleanups)
        self.bridge.setUp()
        self.lib = self.bridge.lib
        self.pages = self.bridge.fixture
        self.root = self.pages.fixture.root
        self.assertTrue(callable(getattr(self.lib, "_capture_controller_source_batch", None)),
                        "missing actual collector-return capture API")
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.config_path = self.root / "config/config.json"
        self.cursors_path = self.root / "state/cursors.json"
        self.batch_path = self.root / "state/controller-source-batch.json"
        for name, path in (
                ("CONFIG_PATH", self.config_path), ("CURSORS_PATH", self.cursors_path),
                ("MEMO_PATH", self.root / "state/memo.json"),
                ("BRAINSTEM_OWNER_LOCK", self.root / "state/brainstem-owner.lock"),
                ("CONTROLLER_SOURCE_BATCH_PATH", self.batch_path)):
            self.stack.enter_context(mock.patch.object(self.lib, name, str(path)))
        native, _unused_corpus, registry = signed_tests._signed_fixture(str(self.root / "native"))
        native_destination = self.root / ".local/share/aegis"
        shutil.copytree(native, native_destination)
        self.stack.enter_context(mock.patch.object(self.lib, "AEGIS_LEDGER_TOOL", registry["aegis"][1]))
        self.policy = live_tests.policy_fixture()
        self.profile = copy.deepcopy(self.bridge.profile)
        self.custom_entries = [self.bridge.custom(name) for name in ("alpha", "empty")]
        Path(self.custom_entries[0]["path"]).write_text("first observed line\nsecond observed line\n", encoding="utf-8")
        Path(self.custom_entries[1]["path"]).write_text("", encoding="utf-8")
        disabled = sorted((set(self.lib.BASE_ORGANS) | set(self.lib.OPTIONAL_ORGANS)) - {"aegis"})
        self.install_config({"senses": {"disable": disabled}, "custom_senses": self.custom_entries})
        self.configure_selection(["sense_aegis"], self.custom_entries)
        self.before_cursors = {"aegis.lines": 0, "custom.alpha": 0, "custom.empty": 0,
                               "fixture.native_time": self.root.stat().st_mtime_ns,
                               "fixture.finite_float": 0.5}
        self.cursors_path.write_bytes(canonical(self.before_cursors))
        self.cursors_path.chmod(0o600)
        self.memo = {"fixture_unknown": {"retain": True}}
        Path(self.lib.MEMO_PATH).write_bytes(canonical(self.memo))
        Path(self.lib.MEMO_PATH).chmod(0o600)
        history = {"schema": "sia-controller-event-history-v1", "epoch_id": live_tests.EPOCH,
                   "started_at": live_tests.START, "complete": True, "entries": [],
                   "non_claims": list(intake_tests.SOURCE_NON_CLAIMS)}
        self.epoch = {"schema": "sia-controller-source-epoch-v1", "epoch_id": live_tests.EPOCH,
                      "started_at": live_tests.START, "configuration": self.configuration,
                      "source_catalog": self.catalog, "profile": self.profile, "live_policy": self.policy,
                      "history": history,
                      "predecessor": None,
                      "non_claims": list(NON_CLAIMS)}
        self.reseal_epoch()
        self.calls = []

    def install_config(self, value, *, reload=True, rebuild=True):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_bytes(canonical(value))
        self.config_path.chmod(0o600)
        if reload:
            self.lib.CONFIG = self.lib.load_config()
            self.assertEqual(self.lib.CONFIG_ERRORS, [])
        if rebuild:
            self.lib.ORGANS = self.lib._build_organs()
            self.lib.SENSES = [sense for sense in self.lib._ALL_SENSES
                               if self.lib._SENSE_ORGAN.get(sense.__name__) in self.lib.ORGANS]
            self.lib.SENSES.append(self.lib.sense_custom)

    def configure_selection(self, native_names, custom_entries):
        self.configuration = {"schema": "sia-controller-source-selection-v1",
                              "native_collectors": list(native_names),
                              "custom_collectors": copy.deepcopy(custom_entries),
                              "non_claims": list(intake_tests.SOURCE_NON_CLAIMS)}
        self.catalog = self.bridge.catalog_for(self.configuration)
        self.profile["live_policy_sha256"] = intake_tests.digest(self.policy)
        if hasattr(self, "epoch"):
            self.epoch.update(configuration=self.configuration, source_catalog=self.catalog,
                              profile=self.profile, live_policy=self.policy)
            self.reseal_epoch()

    def reseal_epoch(self):
        for field in ("configuration", "source_catalog", "profile", "live_policy", "history"):
            self.epoch["expected_" + field + "_sha256"] = intake_tests.digest(self.epoch[field])

    def request(self, epoch=None, memo=None, observed_at=live_tests.NOW):
        selected = self.epoch if epoch is None else epoch
        return {"memo": self.memo if memo is None else memo, "epoch": selected,
                "expected_epoch_sha256": digest(selected), "observed_at": observed_at}

    @contextlib.contextmanager
    def capture_boundary(self, *, allow_notify=False):
        with contextlib.ExitStack() as stack:
            for name in ("save_cursors", "_commit_sense_cursors", "_settle_source_refusals",
                         "_settle_source_record_refusals", "_settle_source_entry_refusals",
                         "_publish_event_page_plan", "_publish_event_page_plan_batch",
                         "_publish_event_page_batch_closure", "_stage_live_generation",
                         "_publish_staged_live_generation", "brain_sync", "gbrain", "gbrain_call",
                         "durable_ledger_append", "ledger_append", "save_mind", "export_status"):
                if hasattr(self.lib, name):
                    stack.enter_context(mock.patch.object(self.lib, name,
                        side_effect=AssertionError("capture reached forbidden effect: " + name)))
            if not allow_notify:
                stack.enter_context(mock.patch.object(self.lib, "_write_memo",
                    side_effect=AssertionError("capture wrote memo without notification acquisition")))
            yield

    def capture(self, epoch=None, memo=None, observed_at=live_tests.NOW):
        with self.capture_boundary(allow_notify="sense_notify" in self.configuration["native_collectors"]):
            return self.lib._capture_controller_source_batch(**self.request(epoch, memo, observed_at))

    def assert_brainstem_owned(self):
        self.pages.assert_owned()
        held = self.lib._BRAINSTEM_OWNER_FD.get()
        self.assertIsNotNone(held)
        descriptor = os.open(self.lib.BRAINSTEM_OWNER_LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            self.assertEqual((os.fstat(held).st_dev, os.fstat(held).st_ino),
                             (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino))
            with self.assertRaises(BlockingIOError):
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(descriptor)

    @contextlib.contextmanager
    def observe_returns(self, transform=None):
        original_native, original_custom = self.lib.sense_aegis, self.lib.sense_custom

        @functools.wraps(original_native)
        def native(cursors):
            self.assert_brainstem_owned()
            result = original_native(cursors)
            if transform is not None:
                result = transform("sense_aegis", result)
            self.calls.append(("sense_aegis", [self.lib._event_replay_record(event) for event in result]))
            return result

        @functools.wraps(original_custom)
        def custom(cursors, *args, **kwargs):
            self.assert_brainstem_owned()
            result = original_custom(cursors, *args, **kwargs)
            self.assertEqual(len(result), 3)
            events, errors, sources = result
            if transform is not None and sources:
                events = transform(sources[0], events)
                result = events, errors, sources
            self.calls.extend((source, [self.lib._event_replay_record(event) for event in events]) for source in sources)
            return result

        with mock.patch.object(self.lib, "sense_aegis", native), \
                mock.patch.object(self.lib, "sense_custom", custom), \
                mock.patch.object(self.lib, "SENSES", [native, custom]):
            yield

    def assert_receipt(self, receipt, observed_at=live_tests.NOW):
        self.assertEqual(set(receipt), CONFIG_RECEIPT_KEYS)
        self.assertEqual(receipt["schema"], "sia-controller-observed-configuration-v1")
        self.assertEqual(receipt["scope"], "current-file-equivalent-active-config-and-selected-roster-v1")
        self.assertEqual(receipt["observed_at"], observed_at)
        self.assertEqual(receipt["receipt_sha256"], own(receipt, "receipt_sha256"))
        self.assertEqual(receipt["non_claims"], CONFIG_NON_CLAIMS)
        self.assertEqual(receipt["config_file"], {
            "path": str(self.config_path), "status": "owned-regular", **file_image(self.config_path)})
        self.assertEqual(canonical(receipt["decoded_config"]), canonical(self.lib.CONFIG))
        self.assertEqual(receipt["active_config"], {"object_relation": "last-loaded-object",
            "active_load_valid": True, "errors": [], "config_sha256": digest(self.lib.CONFIG)})
        self.assertEqual(receipt["runtime_selection"], {
            "organs": [{"organ": key, "name": value[0], "description": value[1]}
                       for key, value in self.lib.ORGANS.items()],
            "senses": [sense.__name__ for sense in self.lib.SENSES],
            "custom_entries": [{"entry_index": index, "source_id": "sense_custom:" + entry["name"]}
                               for index, entry in enumerate(self.configuration["custom_collectors"])]})
        for field in ("configuration", "source_catalog", "profile", "live_policy"):
            self.assertEqual(receipt[field + "_sha256"], self.epoch["expected_" + field + "_sha256"])

    def assembled_request(self, batch):
        history = copy.deepcopy(batch["epoch"]["history"])
        batches = [] if batch["event_closure"] is None else batch["event_closure"]["batches"]
        history["entries"].append({"source_returns": batch["source_returns"],
            "expected_source_returns_sha256": batch["source_returns"]["returns_sha256"],
            "event_batches": [{"batch": item, "expected_batch_sha256": item["batch_sha256"]} for item in batches]})
        return {"history": history, "expected_history_sha256": intake_tests.digest(history),
                **{field: batch["epoch"][field] for field in (
                    "configuration", "expected_configuration_sha256", "source_catalog", "expected_source_catalog_sha256",
                    "profile", "expected_profile_sha256", "live_policy", "expected_live_policy_sha256")},
                "observed_at": batch["observed_at"]}

    def assert_batch(self, batch, epoch=None, observed_at=live_tests.NOW):
        selected = self.epoch if epoch is None else epoch
        self.assertEqual(set(batch), BATCH_KEYS)
        self.assertEqual(batch["schema"], "sia-controller-source-batch-v1")
        self.assertEqual(batch["status"], "captured-not-published")
        self.assertEqual(batch["batch_sha256"], own(batch, "batch_sha256"))
        self.assertEqual(canonical(batch["epoch"]), canonical(selected))
        self.assertEqual(batch["epoch_sha256"], digest(selected))
        self.assertEqual(batch["observed_at"], observed_at)
        self.assertIs(type(batch["observed_at"]), int)
        self.assertEqual(batch["non_claims"], NON_CLAIMS)
        self.assertLessEqual(len(canonical(batch)), self.lib.MAX_STATE_JSON_BYTES)
        self.assert_receipt(batch["configuration_receipt"], observed_at)
        returns = batch["source_returns"]
        self.assertEqual(returns["returns_sha256"], intake_tests.own(returns, "returns_sha256"))
        self.assertEqual(returns["batch_id"], batch["batch_id"])
        self.assertEqual(returns["observed_at"], observed_at)
        self.assertIs(returns["complete"], True)
        self.assertEqual([row["source_id"] for row in returns["runs"]],
                         [row["source_id"] for row in selected["source_catalog"]["sources"]])
        if self.calls:
            self.assertEqual(returns["runs"], [{"source_id": source, "events": events} for source, events in self.calls])
        proposal = batch["cursor_proposal"]
        self.assertEqual(set(proposal), CURSOR_KEYS)
        self.assertEqual(proposal["schema"], "sia-controller-cursor-proposal-v1")
        self.assertEqual(proposal["before"], file_image(self.cursors_path))
        self.assertEqual(canonical(proposal["before_value"]), canonical(self.before_cursors))
        state = self.cursors_path.parent.stat()
        self.assertEqual(proposal["state_identity"], {key: page_tests.generation(state)[key] for key in page_tests.DIRECTORY_KEYS})
        cursor = copy.deepcopy(proposal["before_value"])
        self.assertEqual([row["source_id"] for row in proposal["steps"]], [row["source_id"] for row in returns["runs"]])
        for step in proposal["steps"]:
            self.assertEqual(set(step), CURSOR_STEP_KEYS)
            self.assertEqual(step["removed_keys"], sorted(set(step["removed_keys"])))
            self.assertFalse(set(step["removed_keys"]) & set(step["set_values"]))
            for key in step["removed_keys"]:
                self.assertIn(key, cursor)
                del cursor[key]
            cursor.update(step["set_values"])
            self.assertEqual(step["after_sha256"], digest(cursor))
        self.assertEqual(canonical(cursor), canonical(proposal["after"]))
        self.assertEqual(proposal["after_sha256"], digest(proposal["after"]))
        self.assertEqual([row["source_id"] for row in batch["refusal_intents"]], [row["source_id"] for row in returns["runs"]])
        for intent in batch["refusal_intents"]:
            self.assertEqual(set(intent), REFUSAL_INTENT_KEYS)
        request = self.assembled_request(batch)
        self.assertEqual(canonical(batch["intake_projection"]), canonical(self.bridge.project(request)))

    def inert_before(self):
        return {"memo": Path(self.lib.MEMO_PATH).read_bytes(), "cursors": self.cursors_path.read_bytes(),
                "corpus": self.pages.snapshot(), "pending_renames": list(self.lib.PENDING_CURSOR_RENAMES)}

    def assert_inert(self, before, *, allow_notify=False):
        if not allow_notify:
            self.assertEqual(Path(self.lib.MEMO_PATH).read_bytes(), before["memo"])
        self.assertEqual(self.cursors_path.read_bytes(), before["cursors"])
        self.assertEqual(self.pages.snapshot(), before["corpus"])
        self.assertEqual(self.lib.PENDING_CURSOR_RENAMES, before["pending_renames"])
        self.assertFalse(self.batch_path.exists(), "capture must not implicitly stage its returned batch")

    def assert_named_refusal(self, callback, *, source_id=None, phase=None):
        with self.assertRaises(REFUSALS) as caught:
            callback()
        error = caught.exception
        self.assertIs(type(getattr(error, "reason", None)), str)
        self.assertRegex(error.reason, r"^[a-z][a-z0-9-]*$")
        self.assertTrue(getattr(error, "non_claims", None))
        if source_id is not None:
            self.assertEqual(getattr(error, "source_id", None), source_id)
        if phase is not None:
            self.assertEqual(getattr(error, "phase", None), phase)
        self.assertNotIn(str(self.root), str(error), "closed public refusal must not echo source paths")
        return error

    def test_exact_explicit_keyword_only_api(self):
        parameters = inspect.signature(self.lib._capture_controller_source_batch).parameters
        self.assertEqual(tuple(parameters), ("memo", "epoch", "expected_epoch_sha256", "observed_at"))
        for parameter in parameters.values():
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)

    def test_real_native_and_custom_returns_replay_through_original_plans_closure_and_intake(self):
        before = self.inert_before()
        with self.observe_returns():
            batch = self.capture()
            self.assert_batch(batch)
        self.assertEqual([source for source, _events in self.calls],
                         ["sense_aegis", "sense_custom:alpha", "sense_custom:empty"])
        self.assertTrue(self.calls[0][1], "real private keeper/native projection must emit rows")
        self.assertTrue(self.calls[1][1], "real custom parser must emit its selected lines")
        self.assertEqual(self.calls[-1][1], [])
        self.assertEqual(batch["journal_proposals"], [])
        self.assertIsNone(batch["notification_baseline_attempt"])
        self.assertTrue(all(not row["record_refusals"] and not row["entry_refusals"]
                            for row in batch["refusal_intents"]))
        grouped = {}
        for source, records in self.calls:
            for record in records:
                grouped.setdefault((record["organ"], record["ts"][:10]), []).append(record)
        closure = batch["event_closure"]
        self.assertEqual(closure["schema"], "sia-event-page-publication-closure-v1")
        for member in closure["batches"]:
            for plan in member["members"]:
                self.assertEqual(plan["input_records"], grouped.pop((plan["organ"], plan["date"])))
                self.pages.assert_plan(plan)
        self.assertEqual(grouped, {})
        self.assert_inert(before)

    def test_instrumented_duplicate_return_is_retained_without_duplicate_observation(self):
        # Instrument the return boundary AFTER invoking the real collector.
        # This intentionally synthetic duplicate is not attributed to its keeper.
        def duplicated(source, events):
            return events + [events[0]] if source == "sense_aegis" and events else events

        with self.observe_returns(duplicated):
            batch = self.capture()
            self.assert_batch(batch)
        records = batch["source_returns"]["runs"][0]["events"]
        self.assertEqual(records[0], records[-1])
        associations = [row for row in batch["intake_projection"]["associations"]
                        if row["source_id"] == "sense_aegis" and row["event_id"] == records[0]["event_id"]]
        self.assertEqual([row["return_index"] for row in associations], [0, len(records) - 1])
        self.assertEqual(associations[0]["observation_id"], associations[-1]["observation_id"])

    def test_all_successful_empty_returns_form_nonempty_history_without_fake_event_closure(self):
        selected = [self.custom_entries[-1]]
        disabled = sorted(set(self.lib.BASE_ORGANS) | set(self.lib.OPTIONAL_ORGANS))
        self.install_config({"senses": {"disable": disabled}, "custom_senses": selected})
        self.configure_selection([], selected)
        before = self.inert_before()
        batch = self.capture()
        self.assert_batch(batch)
        self.assertEqual(batch["source_returns"]["runs"], [{"source_id": "sense_custom:empty", "events": []}])
        self.assertIsNone(batch["event_closure"])
        self.assertEqual(self.assembled_request(batch)["history"]["entries"], [{
            "source_returns": batch["source_returns"],
            "expected_source_returns_sha256": batch["source_returns"]["returns_sha256"], "event_batches": []}])
        self.assertEqual(batch["intake_projection"]["intake"]["observations"], [])
        self.assert_inert(before)

    def test_complete_cursor_steps_preserve_native_numbers_and_original_file_bytes(self):
        batch = self.capture()
        self.assert_batch(batch)
        for key in ("fixture.native_time", "fixture.finite_float"):
            self.assertIs(type(batch["cursor_proposal"]["after"][key]), type(self.before_cursors[key]))
            self.assertEqual(canonical(batch["cursor_proposal"]["after"][key]), canonical(self.before_cursors[key]))
        self.assertEqual(batch["cursor_proposal"]["before"], file_image(self.cursors_path))
        self.assertNotEqual(canonical(batch["cursor_proposal"]["after"]), canonical(self.before_cursors))

    def test_native_failure_cannot_become_empty_complete_success(self):
        ledger = self.root / ".local/share/aegis/ledger.tsv"
        ledger.write_bytes(ledger.read_bytes() + b"not-a-signed-row\n")
        before = self.inert_before()
        with mock.patch.object(self.lib, "_prepare_event_page_plan",
                               side_effect=AssertionError("failed source reached planning")):
            self.assert_named_refusal(self.capture, source_id="sense_aegis", phase="collect")
        self.assert_inert(before)

    def test_custom_error_return_cannot_become_successful_empty_source(self):
        source = Path(self.custom_entries[0]["path"])
        retained = source.with_suffix(".original")
        source.rename(retained)
        source.symlink_to(retained)
        before = self.inert_before()
        with mock.patch.object(self.lib, "_prepare_event_page_plan",
                               side_effect=AssertionError("custom error reached planning")):
            self.assert_named_refusal(self.capture, source_id="sense_custom:alpha", phase="collect")
        self.assert_inert(before)

    def test_real_custom_record_refusal_is_retained_unsettled_without_raw_field_leakage(self):
        configured = copy.deepcopy(self.custom_entries)
        configured[0]["type"] = "jsonl"
        Path(configured[0]["path"]).write_text('{"private":"unselected-private-field"}\n', encoding="utf-8")
        current = copy.deepcopy(self.lib.CONFIG)
        current["custom_senses"] = configured
        self.install_config(current)
        self.configure_selection(["sense_aegis"], configured)
        before = self.inert_before()
        batch = self.capture()
        self.assert_batch(batch)
        row = next(row for row in batch["refusal_intents"] if row["source_id"] == "sense_custom:alpha")
        self.assertTrue(row["record_refusals"])
        self.assertEqual({item["reason"] for item in row["record_refusals"]}, {"missing-json-field"})
        trial = {self.lib.SOURCE_RECORD_REFUSALS_KEY: copy.deepcopy(row["record_refusals"])}
        self.assertEqual(self.lib._take_source_record_refusals(trial), row["record_refusals"])
        self.assertNotIn(self.lib.SOURCE_RECORD_REFUSALS_KEY, batch["cursor_proposal"]["after"])
        self.assertNotIn("unselected-private-field", canonical(batch).decode("utf-8"))
        self.assert_inert(before)

    def test_epoch_and_every_nested_pin_are_checked_before_collection(self):
        cases = []
        bad = self.request()
        bad["expected_epoch_sha256"] = "0" * 64
        cases.append(bad)
        for field in ("configuration", "source_catalog", "profile", "live_policy", "history"):
            epoch = copy.deepcopy(self.epoch)
            epoch["expected_" + field + "_sha256"] = "0" * 64
            cases.append(self.request(epoch))
        with mock.patch.object(self.lib, "_prepare_event_page_plan",
                               side_effect=AssertionError("bad input reached planner")), \
                mock.patch.object(self.lib, "_verified_builtin_attest_rows",
                                  side_effect=AssertionError("bad pin reached collector")):
            for request in cases:
                with self.subTest(field=request), self.capture_boundary():
                    self.assert_named_refusal(lambda: self.lib._capture_controller_source_batch(**request))

    def test_complete_input_capacity_precedes_copy_hash_and_collectors(self):
        request = self.request()
        ceiling = len(canonical(request)) - 1
        forbidden = mock.Mock(side_effect=AssertionError("preflight performed bounded work too late"))
        with mock.patch.object(self.lib, "MAX_STATE_JSON_BYTES", ceiling), \
                mock.patch.object(self.lib, "copy", page_tests._ModuleShim(self.lib.copy, deepcopy=forbidden)), \
                mock.patch.object(self.lib, "hashlib", page_tests._ModuleShim(self.lib.hashlib, sha256=forbidden)), \
                mock.patch.object(self.lib, "_verified_builtin_attest_rows", forbidden), self.capture_boundary():
            self.assert_named_refusal(lambda: self.lib._capture_controller_source_batch(**request))
        forbidden.assert_not_called()

    def test_event_roster_capacity_refuses_before_any_plan_or_stage(self):
        before = self.inert_before()
        with mock.patch.object(self.lib, "MAX_SOURCE_REPLAY_EVENTS", 1), \
                mock.patch.object(self.lib, "_prepare_event_page_plan",
                                  side_effect=AssertionError("over-bound returns reached planner")):
            self.assert_named_refusal(self.capture)
        self.assert_inert(before)

    def test_original_controller_clock_not_native_timestamp_or_bool(self):
        batch = self.capture()
        self.assert_batch(batch)
        self.assertEqual({row["observation_timestamp"] for row in batch["intake_projection"]["associations"]},
                         {live_tests.NOW})
        with mock.patch.object(self.lib, "_verified_builtin_attest_rows",
                               side_effect=AssertionError("invalid clock reached source")):
            for stamp in (True, float(live_tests.NOW), live_tests.START - 1):
                with self.subTest(clock=stamp):
                    self.assert_named_refusal(lambda: self.capture(observed_at=stamp))

    def select_notifications(self):
        disabled = sorted((set(self.lib.BASE_ORGANS) | set(self.lib.OPTIONAL_ORGANS)) - {"notify"})
        self.install_config({"senses": {"disable": disabled}, "custom_senses": []})
        self.configure_selection(["sense_notify"], [])
        return self.root / ".local/state/omarchy/notifications/history"

    def test_notification_acquisition_fence_is_durable_before_even_absent_source_probe(self):
        notification_path = self.select_notifications()
        before = self.inert_before()
        source_probe = self.lib._source_tree_path_generation
        reached = []

        def probe(path):
            if os.fspath(path) == str(notification_path):
                marker = self.lib.load_memo().get(self.lib.NOTIFY_BASELINE_ATTEMPT_KEY)
                self.assertIsNotNone(marker, "notification source was inspected before durable intent")
                reached.append(copy.deepcopy(marker))
            return source_probe(path)

        with mock.patch.object(self.lib, "_source_tree_path_generation", side_effect=probe):
            batch = self.capture()
        self.assertTrue(reached, "real notification source boundary was not reached")
        self.assertEqual(batch["notification_baseline_attempt"], reached[0])
        self.assertEqual(self.memo[self.lib.NOTIFY_BASELINE_ATTEMPT_KEY], reached[0])
        self.assertEqual(batch["observed_at"], live_tests.NOW)
        self.assertEqual(batch["cursor_proposal"]["after"]["notify.baseline"]["names"], [])
        self.assert_inert(before, allow_notify=True)

    def test_prior_notification_attempt_recovers_trial_instead_of_adopting_new_old_baseline(self):
        notification_path = self.select_notifications()
        marker = self.lib._mark_notify_baseline_attempt(self.memo)
        notification_path.mkdir(parents=True)
        (notification_path / "appeared-after-attempt.json").write_text(
            '{"app":"fixture","summary":"newly appeared name"}', encoding="utf-8")
        before = self.inert_before()
        recovered = self.lib._notify_recover_interrupted_baseline(copy.deepcopy(self.before_cursors))
        original = self.lib.sense_notify
        observed = []

        @functools.wraps(original)
        def notify(trial, **kwargs):
            self.assertEqual(canonical(trial), canonical(recovered),
                             "prior durable attempt must transform only the isolated source trial")
            events = original(trial, **kwargs)
            observed.append(([self.lib._event_replay_record(event) for event in events], copy.deepcopy(trial)))
            return events

        with mock.patch.object(self.lib, "sense_notify", notify), \
                mock.patch.object(self.lib, "SENSES", [notify, self.lib.sense_custom]):
            batch = self.capture()
        self.assertTrue(observed, "real notification collector was not called")
        self.assertEqual(batch["source_returns"]["runs"], [{"source_id": "sense_notify", "events": observed[0][0]}])
        self.assertEqual(canonical(batch["cursor_proposal"]["after"]), canonical(observed[0][1]))
        self.assertEqual(batch["cursor_proposal"]["after"]["notify.baseline"]["kind"], "opaque")
        self.assertEqual(batch["notification_baseline_attempt"], marker)
        self.assert_inert(before, allow_notify=True)

    def test_original_epoch_changed_during_real_later_source_read_is_not_adopted(self):
        source = Path(self.custom_entries[0]["path"])
        identity = self.lib._source_path_identity
        reached = []

        def observe(path, *args, **kwargs):
            answer = identity(path, *args, **kwargs)
            if os.fspath(path) == str(source):
                reached.append(True)
            return answer

        with mock.patch.object(self.lib, "_source_path_identity", side_effect=observe):
            self.capture()
        self.assertTrue(reached, "real later custom-source read hook was not reached")
        reached.clear()
        before = self.inert_before()

        def change(path, *args, **kwargs):
            answer = identity(path, *args, **kwargs)
            if os.fspath(path) == str(source) and not reached:
                reached.append(True)
                self.epoch["non_claims"].append("late caller change")
            return answer

        with mock.patch.object(self.lib, "_source_path_identity", side_effect=change):
            self.assert_named_refusal(self.capture)
        self.assertTrue(reached)
        self.assert_inert(before)

    def test_final_result_detachment_cannot_adopt_changed_nonclaims(self):
        real_copy = self.lib.copy.deepcopy
        reached = []

        def observing(value, *args, **kwargs):
            if type(value) is dict and value.get("schema") == "sia-controller-source-batch-v1" \
                    and "batch_sha256" in value:
                self.assertEqual(value["batch_sha256"], own(value, "batch_sha256"))
                reached.append(True)
            return real_copy(value, *args, **kwargs)

        with mock.patch.object(self.lib, "copy", page_tests._ModuleShim(self.lib.copy, deepcopy=observing)):
            self.capture()
        self.assertTrue(reached, "real final complete-batch detachment was not observed")
        reached.clear()
        before = self.inert_before()

        def changing(value, *args, **kwargs):
            if type(value) is dict and value.get("schema") == "sia-controller-source-batch-v1" \
                    and "batch_sha256" in value:
                self.assertEqual(value["batch_sha256"], own(value, "batch_sha256"))
                reached.append(True)
                value["non_claims"].clear()
            return real_copy(value, *args, **kwargs)

        with mock.patch.object(self.lib, "copy", page_tests._ModuleShim(self.lib.copy, deepcopy=changing)):
            self.assert_named_refusal(self.capture)
        self.assertTrue(reached)
        self.assert_inert(before)
