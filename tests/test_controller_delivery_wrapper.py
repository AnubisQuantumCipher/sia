"""Storage-free wrapper contract over genuine detached held snapshots.

The root executes this private draft sequentially. Real temporary source
ACK, epoch preparation, successor capture, epoch hold and journal hold supply
the ordinary snapshots. Unicode in the actual fixture directory distinguishes
the source-native and UTF-8 hash families. Pure calls start only after those
acquisitions and may not inspect storage, ACK a source or recurse through
source.validate_batch.

Explicitly rehashed native-identity and hypothetical-v3 cases below are only
represented-byte consistency tests. They are not observed filesystem facts,
acknowledged v3 parents, source-schema authentication or writer permits. A
future WAL check must compare parent_source_schema to its actual predecessor;
the future candidate adapter must compare the entire actual parent generation.
No machine evidence, output receipt, numeric score or cognitive win is invented.
"""

import contextlib
import copy
import importlib
import inspect
import os
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import test_controller_delivery_epoch_hold as hold_tests
from tests import test_controller_delivery_epoch as epoch_tests
from tests import test_controller_source_ack as ack_tests


SCHEMA = "sia-controller-source-delivery-input-v1"
WRAPPER_KEYS = {
    "schema", "status", "parent_source_schema", "epoch_view",
    "expected_epoch_view_sha256", "expected_adoption_sha256",
    "journal", "expected_journal_sha256", "binding",
    "expected_binding_sha256", "non_claims", "input_sha256",
}
BUILD_PARAMETERS = (
    "owner", "parent_source_schema", "epoch_view", "expected_epoch_view_sha256",
    "expected_adoption_sha256", "journal", "expected_journal_sha256",
    "epoch", "expected_epoch_sha256", "projection", "expected_projection_sha256",
    "observed_at", "notification_baseline_attempt",
)
CONTEXT_PARAMETERS = (
    "epoch", "expected_epoch_sha256", "projection", "expected_projection_sha256",
    "observed_at", "notification_baseline_attempt",
)
VALIDATE_PARAMETERS = (
    "owner", "delivery_input", "expected_input_sha256", *CONTEXT_PARAMETERS,
)
REFUSALS = (ValueError, RuntimeError, OSError)


class ControllerDeliveryWrapper(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("siacontrollerdeliverywrapper")
        except ModuleNotFoundError as exc:
            self.fail("missing pure controller delivery wrapper: " + str(exc))
        self.assertTrue(callable(getattr(self.module, "build", None)))
        self.assertTrue(callable(getattr(self.module, "validate", None)))
        self.assertTrue(hasattr(self.module, "NON_CLAIMS"))
        self.fixture = hold_tests.ControllerDeliveryEpochHold(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.epoch_module = self.fixture.module
        self.source = importlib.import_module("siasourcebatch")
        self.binding = importlib.import_module("siacontrollerdeliveryinput")
        self.journal = importlib.import_module("siadelivery")
        self.live = importlib.import_module("sialiveloop")
        self.ack = importlib.import_module("siasourceack")

    @contextlib.contextmanager
    def snapshot(self, *, fenced=False):
        with self.fixture.epoch.completed() as values:
            case, retained, committed, status, generation, original_root = values
            # Real non-ASCII path, not fabricated page/origin metadata. The
            # native held-view hash must differ from its UTF-8 component hash.
            root = original_root.with_name(original_root.name + "-λ")
            with mock.patch.object(case.lib, epoch_tests.ROOT_KEY, str(root)):
                adopted = self.fixture.epoch.prepare(case, retained, committed, status)
                marker = None
                if fenced:
                    with self.fixture.epoch.idle.source_owner(case):
                        marker = copy.deepcopy(case.lib._mark_notify_baseline_attempt(
                            case.live.memo))
                _request, batch = self.fixture.epoch.idle.capture_successor(
                    case, retained, committed)
                self.assertEqual(batch["notification_baseline_attempt"], marker)
                self.assertEqual(batch["schema"], "sia-controller-source-batch-v2")
                request = self.fixture.request(case, retained, committed, status, adopted)
                if fenced:
                    request.update({
                        "notification_baseline_attempt": marker,
                        "expected_notification_baseline_attempt_sha256":
                            self.source.native_sha(case.lib.__dict__, marker),
                    })
                operation = self.epoch_module.hold_capturable_epoch \
                    if fenced else self.epoch_module.hold_epoch
                with self.fixture.reader_scope(case):
                    with operation(case.lib.__dict__, **request) as held_epoch:
                        epoch_view = held_epoch.read()
                        with self.journal.hold_deliveries(
                                directory=epoch_view["records_directory"],
                                epoch_id=retained["epoch"]["epoch_id"],
                                limits=self.fixture.epoch.limits) as held_journal:
                            self.assertEqual(held_journal.directory_identity(),
                                             epoch_view["records_identity"])
                            journal = held_journal.read()
                            self.assertTrue(journal["complete"])
                            self.assertEqual(journal["records"], [])
                            self.assertEqual(journal["pending"], [])
                            held_journal.current()
                            held_epoch.current()
                self.fixture.closed(held_epoch)
                kw = {
                    "parent_source_schema": retained["schema"],
                    "epoch_view": epoch_view,
                    "expected_epoch_view_sha256": self.source.native_sha(
                        case.lib.__dict__, epoch_view),
                    "expected_adoption_sha256": adopted["expected_adoption_sha256"],
                    "journal": journal,
                    "expected_journal_sha256": self.live._sha(journal),
                    "epoch": batch["epoch"], "expected_epoch_sha256": batch["epoch_sha256"],
                    "projection": batch["intake_projection"],
                    "expected_projection_sha256": batch["intake_projection"]["projection_sha256"],
                    "observed_at": batch["observed_at"],
                    "notification_baseline_attempt": marker,
                }
                yield SimpleNamespace(case=case, retained=retained, committed=committed,
                    generation=generation, adopted=adopted, root=root, batch=batch,
                    owner=case.lib.__dict__, kw=kw)

    def images(self, f):
        return (f.case.images(), epoch_tests._tree(f.root),
                ack_tests._path_image(f.case.effects_archive_path()),
                copy.deepcopy(f.case.live.memo))

    @contextlib.contextmanager
    def no_io(self, f):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("pure delivery wrapper reached storage/authority")

        with contextlib.ExitStack() as stack:
            for target in ("builtins.open", "os.open", "os.stat", "os.lstat",
                           "os.scandir", "os.listdir", "os.mkdir", "os.fsync", "time.time"):
                stack.enter_context(mock.patch(target, side_effect=forbidden))
            for owner, name in (
                    (self.source, "validate_batch"), (self.source, "_collect"),
                    (self.ack, "read_completed"),
                    (self.ack, "read_capturable_predecessor"),
                    (self.epoch_module, "prepare_epoch"),
                    (self.epoch_module, "hold_epoch"),
                    (self.epoch_module, "hold_capturable_epoch"),
                    (self.journal, "hold_deliveries"),
                    (self.journal, "inspect_deliveries"),
                    (self.journal, "reserve_delivery"),
                    (self.journal, "deliver_reserved"),
                    (f.case.lib, "load_memo"), (f.case.lib, "_write_memo"),
                    (f.case.lib, "_read_committed_live_generation"),
                    (f.case.lib, "_require_status_admission_unchanged"),
                    (f.case.lib, "brainstem_owner"), (f.case.lib, "corpus_owner"),
                    (f.case.lib, "utcnow")):
                stack.enter_context(mock.patch.object(owner, name, side_effect=forbidden))
            yield

    def build(self, f, **changes):
        return self.module.build(f.owner, **{**f.kw, **changes})

    def validate(self, f, value, **changes):
        request = {name: f.kw[name] for name in CONTEXT_PARAMETERS}
        request.update({"delivery_input": value, "expected_input_sha256": value["input_sha256"]})
        request.update(changes)
        return self.module.validate(f.owner, **request)

    def native_seal(self, f, value, field):
        value[field] = self.source.native_sha(
            f.owner, {key: item for key, item in value.items() if key != field})

    def component_seal(self, f, value, field):
        value[field] = self.source._component_sha(
            f.owner, {key: item for key, item in value.items() if key != field})

    def live_seal(self, value, field):
        value[field] = self.live._sha({key: item for key, item in value.items() if key != field})

    def repin_view(self, f, kw):
        kw["expected_epoch_view_sha256"] = self.source.native_sha(f.owner, kw["epoch_view"])

    def reject_build(self, f, kw):
        before = (copy.deepcopy(kw), self.images(f))
        with self.no_io(f), self.assertRaises(REFUSALS):
            self.module.build(f.owner, **kw)
        self.assertEqual((kw, self.images(f)), before)

    def reject_view(self, f, value, **changes):
        before = (copy.deepcopy(value), copy.deepcopy(changes), self.images(f))
        with self.no_io(f), self.assertRaises(REFUSALS):
            self.validate(f, value, **changes)
        self.assertEqual((value, changes, self.images(f)), before)

    def assert_wrapper(self, f, result, *, kw=None):
        kw = f.kw if kw is None else kw
        self.assertIs(type(result), dict)
        self.assertEqual(set(result), WRAPPER_KEYS)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["status"], "bound-not-consumed")
        for name in ("parent_source_schema", "epoch_view", "expected_epoch_view_sha256",
                     "expected_adoption_sha256", "journal", "expected_journal_sha256"):
            self.assertEqual(result[name], kw[name])
        self.assertEqual(result["non_claims"], list(self.module.NON_CLAIMS))
        parent = kw["epoch_view"]["parent_generation"]
        expected_binding = self.binding.bind(
            journal=kw["journal"], expected_journal_sha256=kw["expected_journal_sha256"],
            previous_state=parent["transition"]["state"],
            expected_previous_state_sha256=parent["state_sha256"],
            intake=kw["projection"]["intake"],
            expected_intake_sha256=kw["projection"]["intake_sha256"],
            policy=kw["epoch"]["live_policy"],
            expected_policy_sha256=kw["epoch"]["expected_live_policy_sha256"],
            observed_at=kw["observed_at"])
        self.assertEqual(result["binding"], expected_binding)
        self.assertEqual(result["expected_binding_sha256"], expected_binding["binding_sha256"])
        self.assertEqual(result["input_sha256"], self.source.native_sha(
            f.owner, {key: item for key, item in result.items() if key != "input_sha256"}))

    def test_exact_api_and_represented_only_non_claims(self):
        for operation, expected in ((self.module.build, BUILD_PARAMETERS),
                                    (self.module.validate, VALIDATE_PARAMETERS)):
            parameters = inspect.signature(operation).parameters
            self.assertEqual(tuple(parameters), expected)
            for name, parameter in parameters.items():
                self.assertIs(parameter.default, inspect.Parameter.empty)
                self.assertEqual(parameter.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD
                                 if name == "owner" else inspect.Parameter.KEYWORD_ONLY)
        claims = self.module.NON_CLAIMS
        self.assertIsInstance(claims, (list, tuple))
        self.assertTrue(claims)
        for subject in (r"parent|schema", r"storag|filesystem", r"readiness|acknowledg",
                        r"writer|output", r"complete.{0,32}histor|histor.{0,32}complete",
                        r"cognit|biolog", r"held[- ]?out"):
            with self.subTest(subject=subject):
                self.assertTrue(any(re.search(subject, claim, re.I)
                    and re.search(r"\b(no|not|never|without|cannot)\b", claim, re.I)
                    for claim in claims), "missing represented-only denial: " + subject)

    def test_genuine_held_snapshot_builds_deterministically_with_exact_hash_families(self):
        with self.snapshot() as f:
            before = (copy.deepcopy(f.kw), self.images(f))
            utf8_view_sha = self.source._component_sha(f.owner, f.kw["epoch_view"])
            self.assertNotEqual(utf8_view_sha, f.kw["expected_epoch_view_sha256"])
            with self.no_io(f):
                first = self.build(f)
                self.assert_wrapper(f, first)
                self.assertIsNone(self.validate(f, first))
                second = self.build(f)
                self.assertEqual(self.source.native_bytes(f.owner, second),
                                 self.source.native_bytes(f.owner, first))
                self.assertNotEqual(first["input_sha256"], self.source._component_sha(
                    f.owner, {key: value for key, value in first.items() if key != "input_sha256"}))
                first["epoch_view"]["parent_generation"].clear()
                first["epoch_view"]["epoch_adoption"]["adoption"].clear()
                first["journal"]["non_claims"].clear()
                first["binding"]["deliveries"].clear()
                first["non_claims"].clear()
                self.assertEqual(self.build(f), second)
            self.assertEqual((f.kw, self.images(f)), before)
            wrong = dict(f.kw, expected_epoch_view_sha256=utf8_view_sha)
            self.reject_build(f, wrong)

    def test_native_identity_outside_live_integer_domain_is_preserved_without_io(self):
        with self.snapshot() as f:
            kw = copy.deepcopy(f.kw)
            view = kw["epoch_view"]
            # Explicit representation-only adversary, not observed stat.
            # Use the already declared native identity ceiling unchanged.
            identity = copy.deepcopy(view["records_identity"])
            identity["ino"] = self.epoch_module._IDENTITY_CEILING
            self.assertGreater(identity["ino"], self.live.MAX_SAFE_INTEGER)
            adoption = view["epoch_adoption"]["adoption"]
            adoption["records_identity"] = copy.deepcopy(identity)
            self.component_seal(f, adoption, "adoption_sha256")
            view["epoch_adoption"]["expected_adoption_sha256"] = adoption["adoption_sha256"]
            view["records_identity"] = copy.deepcopy(identity)
            kw["expected_adoption_sha256"] = adoption["adoption_sha256"]
            self.repin_view(f, kw)
            with self.assertRaises(self.live.LiveLoopRefusal):
                self.live._canonical(view)
            before = (copy.deepcopy(kw), self.images(f))
            with self.no_io(f):
                result = self.module.build(f.owner, **kw)
                self.assert_wrapper(f, result, kw=kw)
                self.assertIsNone(self.validate(f, result))
            actual = result["epoch_view"]["records_identity"]["ino"]
            self.assertIs(type(actual), int)
            self.assertEqual(actual, identity["ino"])
            self.assertEqual((kw, self.images(f)), before)

    def test_context_pins_parent_joins_and_complete_journal_are_required(self):
        with self.snapshot() as f:
            for name in ("expected_epoch_view_sha256", "expected_adoption_sha256",
                         "expected_journal_sha256", "expected_epoch_sha256",
                         "expected_projection_sha256"):
                with self.subTest(pin=name):
                    kw = copy.deepcopy(f.kw)
                    kw[name] = "0" * 64
                    self.reject_build(f, kw)
            for selected in ("schema", "clock", "source-parent", "live-parent", "pending"):
                with self.subTest(selected=selected):
                    kw = copy.deepcopy(f.kw)
                    if selected == "schema":
                        kw["parent_source_schema"] = "unadmitted-source-schema"
                    elif selected == "clock":
                        kw["observed_at"] = f.retained["observed_at"]
                        self.assertNotEqual(kw["observed_at"], f.kw["observed_at"])
                    elif selected == "source-parent":
                        kw["epoch"]["predecessor"]["source_batch_sha256"] = "0" * 64
                        kw["expected_epoch_sha256"] = self.source.native_sha(f.owner, kw["epoch"])
                    elif selected == "live-parent":
                        kw["epoch_view"]["expected_parent_generation_sha256"] = "0" * 64
                        self.repin_view(f, kw)
                    else:
                        kw["journal"]["complete"] = False
                        kw["journal"]["pending"] = [f.batch["batch_id"][:32]]
                        kw["expected_journal_sha256"] = self.live._sha(kw["journal"])
                    self.reject_build(f, kw)

    def test_rehashed_wrapper_tampering_cannot_replace_complete_binding_replay(self):
        with self.snapshot() as f:
            with self.no_io(f):
                original = self.build(f)
            for selected in ("outer-status", "unknown-field", "binding-status",
                             "binding-clock", "binding-boundary", "binding-deliveries"):
                with self.subTest(selected=selected):
                    changed = copy.deepcopy(original)
                    if selected == "outer-status":
                        changed["status"] = "acknowledged"
                    elif selected == "unknown-field":
                        changed["unadmitted"] = True
                    else:
                        binding = changed["binding"]
                        if selected == "binding-status":
                            binding["status"] = "consumed"
                        elif selected == "binding-clock":
                            binding["observed_at"] = f.retained["observed_at"]
                        elif selected == "binding-boundary":
                            binding["journal_non_claims"] = []
                        else:
                            binding["deliveries"]["records"] = [{"not-a-completion": True}]
                            binding["deliveries_sha256"] = self.live._sha(binding["deliveries"])
                        self.live_seal(binding, "binding_sha256")
                        changed["expected_binding_sha256"] = binding["binding_sha256"]
                    self.native_seal(f, changed, "input_sha256")
                    self.reject_view(f, changed)
            self.reject_view(f, original, expected_input_sha256="0" * 64)
            # Directly reject a self-consistent fake binder result too: build
            # must validate the returned component before sealing it as input.
            forged = copy.deepcopy(original["binding"])
            forged["status"] = "consumed"
            self.live_seal(forged, "binding_sha256")
            with self.no_io(f), mock.patch.object(self.binding, "bind", return_value=forged), \
                    self.assertRaises(REFUSALS):
                self.build(f)

    def test_fence_and_held_view_pairing_are_exact_not_optional_labels(self):
        with self.snapshot(fenced=True) as f:
            self.assertEqual(f.kw["epoch_view"]["schema"],
                             "sia-controller-delivery-epoch-capture-view-v1")
            with self.no_io(f):
                result = self.build(f)
                self.assert_wrapper(f, result)
                self.assertIsNone(self.validate(f, result))
            for selected in ("missing-context-fence", "different-fence", "fence-pin", "ordinary-view"):
                with self.subTest(selected=selected):
                    kw = copy.deepcopy(f.kw)
                    if selected == "missing-context-fence":
                        kw["notification_baseline_attempt"] = None
                    elif selected == "different-fence":
                        kw["notification_baseline_attempt"]["id"] = "0" * 32
                    elif selected == "fence-pin":
                        kw["epoch_view"]["expected_notification_baseline_attempt_sha256"] = "0" * 64
                        self.repin_view(f, kw)
                    else:
                        view = kw["epoch_view"]
                        view["schema"] = "sia-controller-delivery-epoch-view-v1"
                        view["status"] = "held-not-consumed"
                        view.pop("notification_baseline_attempt")
                        view.pop("expected_notification_baseline_attempt_sha256")
                        view["non_claims"] = list(self.epoch_module.HELD_NON_CLAIMS)
                        self.repin_view(f, kw)
                    self.reject_build(f, kw)
            self.reject_view(f, result, notification_baseline_attempt=None)

    def test_legacy_bootstrap_and_hypothetical_v3_continuity_have_distinct_rules(self):
        with self.snapshot() as f:
            kw = copy.deepcopy(f.kw)
            view = kw["epoch_view"]
            original_adoption = copy.deepcopy(view["epoch_adoption"])
            # Representation-only hypothetical: use the observed successor
            # batch digest as a later source-commit identity, but do NOT claim
            # that v2 capture was published or became an acknowledged v3.
            # The pure wrapper cannot certify the parent_source_schema claim.
            later_source_pin = f.batch["batch_sha256"]
            self.assertNotEqual(later_source_pin, f.committed["source_batch_sha256"])
            view["parent_committed"]["source_batch_sha256"] = later_source_pin
            kw["epoch"]["predecessor"]["source_batch_sha256"] = later_source_pin
            kw["expected_epoch_sha256"] = self.source.native_sha(f.owner, kw["epoch"])
            self.repin_view(f, kw)
            self.reject_build(f, kw)  # legacy bootstrap no longer joins parent
            kw["parent_source_schema"] = "sia-controller-source-batch-v3"
            before = (copy.deepcopy(kw), self.images(f))
            with self.no_io(f):
                result = self.module.build(f.owner, **kw)
                self.assert_wrapper(f, result, kw=kw)
                self.assertIsNone(self.module.validate(f.owner,
                    delivery_input=result, expected_input_sha256=result["input_sha256"],
                    **{name: kw[name] for name in CONTEXT_PARAMETERS}))
            self.assertEqual(result["epoch_view"]["epoch_adoption"], original_adoption)
            self.assertEqual(result["expected_adoption_sha256"], f.kw["expected_adoption_sha256"])
            self.assertEqual((kw, self.images(f)), before)
            # Rebirth cannot silently replace the independently supplied pin.
            changed = copy.deepcopy(kw)
            adopted = changed["epoch_view"]["epoch_adoption"]
            adopted["birth"]["bootstrap_parent"]["source_batch_sha256"] = later_source_pin
            self.component_seal(f, adopted["birth"], "birth_sha256")
            adopted["expected_birth_sha256"] = adopted["birth"]["birth_sha256"]
            adopted["adoption"]["birth_sha256"] = adopted["birth"]["birth_sha256"]
            self.component_seal(f, adopted["adoption"], "adoption_sha256")
            adopted["expected_adoption_sha256"] = adopted["adoption"]["adoption_sha256"]
            self.repin_view(f, changed)
            self.reject_build(f, changed)

    def test_complete_capacity_admission_precedes_binding_and_final_copy_rechecks_inputs(self):
        with self.snapshot() as f:
            owner = dict(f.owner)
            owner["MAX_STATE_JSON_BYTES"] = 1
            with self.no_io(f), mock.patch.object(self.binding, "bind", side_effect=AssertionError(
                    "oversized wrapper replayed binding before whole-input admission")), \
                    self.assertRaises(REFUSALS):
                self.module.build(owner, **f.kw)
            original_copy = copy.deepcopy
            fired = []

            def during_result_copy(value, *args, **kwargs):
                detached = original_copy(value, *args, **kwargs)
                if type(value) is dict and value.get("schema") == SCHEMA and not fired:
                    fired.append(True)
                    f.kw["epoch_view"]["records_identity"]["ino"] = \
                        self.epoch_module._IDENTITY_CEILING
                return detached

            before = self.images(f)
            with self.no_io(f), mock.patch.object(copy, "deepcopy", side_effect=during_result_copy), \
                    self.assertRaises(REFUSALS):
                self.build(f)
            self.assertTrue(fired, "builder's final detached wrapper was not exercised")
            self.assertEqual(self.images(f), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
