"""Configuration-specific RED controls for the real source-capture boundary.

Root owns strictly sequential execution. The
fixture is composed rather than inherited. Its source parsers, staging and
recovery controls belong to test_controller_source_capture, not this module.

Configuration JSON has its existing native domain, including finite floats.
The live policy's typed numerical fields retain their independent grammar.
All raw-byte sizes, hashes and filesystem generations below are observations
made by the running test, not precomputed numerical oracles.
"""

import base64
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import unittest
from unittest import mock

from tests import test_controller_source_capture as capture_tests
from tests import test_corpus_version_capture as hash_tests
from tests import test_event_live_intake as intake_tests
from tests import test_event_page_plan as page_tests
from tests import test_live_loop as live_tests


CONFIG_NON_CLAIMS = [
    "This receipt observes current config.json bytes or absence and an equivalent active CONFIG value; it does not recover the bytes, file generation, or optional-source probes used at module import or the original load.",
    "Runtime collector names and configuration pins describe the held effective selection; they do not establish source installation, collector success, source freshness, or completeness outside that roster.",
    "Revalidation binds observed configuration and registry state at capture boundaries; it does not establish uninterrupted immutability against concurrent or hostile same-user changes.",
    "This configuration receipt is not a source return, durable source batch, cursor acknowledgment, live publication, or cognitive win.",
]
RECEIPT_KEYS = {
    "schema", "scope", "observed_at", "config_file", "decoded_config", "active_config",
    "runtime_selection", "configuration_sha256", "source_catalog_sha256", "profile_sha256",
    "live_policy_sha256", "non_claims", "receipt_sha256",
}
REFUSALS = (ValueError, RuntimeError, OSError)


def native_bytes(value):
    return capture_tests.canonical(value)


def native_digest(value):
    return hashlib.sha256(native_bytes(value)).hexdigest()


class ControllerSourceConfiguration(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        case = capture_tests.ControllerSourceCapture(methodName="runTest")
        try:
            case.setUp()
            yield case
        finally:
            case.doCleanups()

    def assert_receipt(self, case, receipt):
        self.assertEqual(set(receipt), RECEIPT_KEYS)
        self.assertEqual(receipt["schema"], "sia-controller-observed-configuration-v1")
        self.assertEqual(receipt["scope"], "current-file-equivalent-active-config-and-selected-roster-v1")
        self.assertEqual(receipt["observed_at"], live_tests.NOW)
        self.assertEqual(receipt["non_claims"], CONFIG_NON_CLAIMS)
        self.assertEqual(receipt["receipt_sha256"], native_digest(
            {key: value for key, value in receipt.items() if key != "receipt_sha256"}))
        file = receipt["config_file"]
        self.assertEqual(set(file), {"path", "status", "generation", "raw_utf8_base64", "raw_bytes", "raw_sha256"})
        self.assertEqual(file["path"], str(case.config_path))
        if case.config_path.exists():
            raw = case.config_path.read_bytes()
            self.assertEqual(file["status"], "owned-regular")
            self.assertEqual(file["generation"], page_tests.generation(case.config_path.stat()))
            self.assertEqual(file["raw_utf8_base64"], base64.b64encode(raw).decode("ascii"))
            self.assertEqual(file["raw_bytes"], len(raw))
            self.assertEqual(file["raw_sha256"], hashlib.sha256(raw).hexdigest())
            decoded = case.lib._strict_json_loads(raw)
        else:
            self.assertEqual(file["status"], "absent")
            for key in ("generation", "raw_utf8_base64", "raw_bytes", "raw_sha256"):
                self.assertIsNone(file[key])
            decoded = {}
        self.assertEqual(native_bytes(receipt["decoded_config"]), native_bytes(decoded))
        self.assertEqual(native_bytes(decoded), native_bytes(case.lib.CONFIG))
        active = receipt["active_config"]
        self.assertEqual(active, {
            "object_relation": "last-loaded-object" if case.lib.CONFIG is case.lib._LAST_LOADED_CONFIG
                               else "explicit-config-object",
            "active_load_valid": True, "errors": [], "config_sha256": native_digest(case.lib.CONFIG),
        })
        self.assertIs(case.lib._active_config_load_valid(), True)
        self.assertEqual(case.lib.CONFIG_ERRORS, [])
        selected = {row["name"] for row in case.configuration["custom_collectors"]}
        custom_entries = []
        for index, entry in enumerate(case.lib.CONFIG.get("custom_senses", [])):
            normalized = case.lib._validated_custom_sense_entry(entry)
            if normalized is not None and normalized["name"] in selected:
                custom_entries.append({"entry_index": index, "source_id": normalized["source_id"]})
        self.assertEqual(receipt["runtime_selection"], {
            "organs": [{"organ": organ, "name": values[0], "description": values[1]}
                       for organ, values in case.lib.ORGANS.items()],
            "senses": [sense.__name__ for sense in case.lib.SENSES],
            "custom_entries": custom_entries,
        })
        for name in ("configuration", "source_catalog", "profile", "live_policy"):
            self.assertEqual(receipt[name + "_sha256"], case.epoch["expected_" + name + "_sha256"])

    def refused(self, case):
        with self.assertRaises(REFUSALS):
            case.capture()

    @staticmethod
    def replace_same_config_bytes(case, retained_name):
        raw = case.config_path.read_bytes()
        mode = stat.S_IMODE(case.config_path.stat().st_mode)
        retained = case.root / retained_name
        case.config_path.rename(retained)
        case.config_path.write_bytes(raw)
        case.config_path.chmod(mode)
        return retained

    def test_capture_observes_current_equivalent_bytes_without_reloading_original_provenance(self):
        with self.fixture() as case:
            configured = copy.deepcopy(case.lib.CONFIG)
            configured["_comment"] = "equivalent configuration Ω"
            case.install_config(configured)
            original_raw = case.config_path.read_bytes()
            original_generation = page_tests.generation(case.config_path.stat())
            original_config = case.lib.CONFIG
            current_raw = json.dumps(original_config, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode("utf-8")
            case.config_path.write_bytes(b"\n" + current_raw + b"\n")
            self.assertIn("Ω".encode("utf-8"), case.config_path.read_bytes())
            self.assertEqual(native_bytes(case.lib._strict_json_loads(case.config_path.read_bytes())),
                             native_bytes(original_config))
            forbidden = mock.Mock(side_effect=AssertionError("capture reloaded configuration or rebuilt its registry"))
            with mock.patch.object(case.lib, "load_config", forbidden), \
                    mock.patch.object(case.lib, "_build_organs", forbidden):
                result = case.capture()
            forbidden.assert_not_called()
            receipt = result["configuration_receipt"]
            self.assert_receipt(case, receipt)
            self.assertIs(case.lib.CONFIG, original_config)
            self.assertEqual(receipt["active_config"]["object_relation"], "last-loaded-object")
            self.assertNotEqual(receipt["config_file"]["generation"], original_generation)
            self.assertNotEqual(receipt["config_file"]["raw_sha256"], hashlib.sha256(original_raw).hexdigest())

    def test_equivalent_explicit_config_object_is_labeled_as_an_override(self):
        with self.fixture() as case:
            loaded = case.lib.CONFIG
            case.lib.CONFIG = copy.deepcopy(loaded)
            self.assertIsNot(case.lib.CONFIG, case.lib._LAST_LOADED_CONFIG)
            result = case.capture()
            self.assert_receipt(case, result["configuration_receipt"])
            self.assertEqual(result["configuration_receipt"]["active_config"]["object_relation"],
                             "explicit-config-object")

    def test_actual_organ_insertion_order_has_an_explicit_native_tuple_projection(self):
        with self.fixture() as case:
            original = list(case.lib.ORGANS.items())
            case.lib.ORGANS = dict(reversed(original))
            self.assertNotEqual(list(case.lib.ORGANS.items()), original)
            self.assertTrue(all(type(value) is tuple for value in case.lib.ORGANS.values()))
            result = case.capture()
            self.assert_receipt(case, result["configuration_receipt"])

    def test_same_bytes_new_generation_before_capture_is_a_current_observation(self):
        with self.fixture() as case:
            generation = page_tests.generation(case.config_path.stat())
            retained = self.replace_same_config_bytes(case, "previous-config-observation.json")
            result = case.capture()
            self.assert_receipt(case, result["configuration_receipt"])
            self.assertEqual(case.config_path.read_bytes(), retained.read_bytes())
            self.assertNotEqual(result["configuration_receipt"]["config_file"]["generation"], generation)

    def test_absence_is_distinct_from_an_empty_json_file_and_binds_actual_explicit_roster(self):
        for absent in (True, False):
            with self.subTest(absent=absent), self.fixture() as case:
                case.install_config({}, rebuild=False)
                if absent:
                    case.config_path.unlink()
                    case.lib.CONFIG = case.lib.load_config()
                # Genuine native collector, private HOME, and an explicit
                # actual registry. No host journal/package collector runs.
                case.lib.ORGANS = {"agents": case.lib.BASE_ORGANS["agents"]}
                case.lib.SENSES = [case.lib.sense_agents, case.lib.sense_custom]
                case.configure_selection(["sense_agents"], [])
                case.reseal_epoch()
                result = case.capture()
                receipt = result["configuration_receipt"]
                self.assert_receipt(case, receipt)
                self.assertEqual(receipt["decoded_config"], {})
                self.assertEqual(receipt["config_file"]["status"], "absent" if absent else "owned-regular")

    def test_missing_config_cannot_match_an_active_nonempty_configuration(self):
        with self.fixture() as case:
            self.assertTrue(case.lib.CONFIG)
            case.config_path.unlink()
            self.refused(case)

    def test_finite_native_config_floats_survive_without_relaxing_live_integer_policy(self):
        for invalid_live_type in (False, True):
            with self.subTest(invalid_live_type=invalid_live_type), self.fixture() as case:
                value = copy.deepcopy(case.lib.CONFIG)
                value["judge"] = {"configuration_fixture_value": 1.0}
                case.install_config(value)
                if invalid_live_type:
                    case.policy["limits"]["max_versions"] = value["judge"]["configuration_fixture_value"]
                    case.profile["live_policy_sha256"] = intake_tests.digest(case.policy)
                case.reseal_epoch()
                if invalid_live_type:
                    self.refused(case)
                else:
                    result = case.capture()
                    self.assert_receipt(case, result["configuration_receipt"])
                    self.assertIs(type(result["configuration_receipt"]["decoded_config"]["judge"]
                                       ["configuration_fixture_value"]), float)

    def test_invalid_active_load_config_errors_or_unequal_config_refuse(self):
        for change in ("invalid-active-load", "recorded-errors", "unequal-active-value"):
            with self.subTest(change=change), self.fixture() as case:
                if change == "invalid-active-load":
                    case.lib._LAST_LOADED_CONFIG = case.lib.CONFIG
                    case.lib._LAST_CONFIG_LOAD_VALID = False
                    case.lib.CONFIG_ERRORS.clear()
                elif change == "recorded-errors":
                    case.lib.CONFIG_ERRORS.append({"config": "config.json", "error": "config-invalid-json"})
                    self.assertIs(case.lib._active_config_load_valid(), True)
                else:
                    case.lib.CONFIG = {**case.lib.CONFIG, "_comment": "unequal active fixture value"}
                    self.assertIs(case.lib._active_config_load_valid(), True)
                self.refused(case)

    def test_matching_file_and_config_cannot_hide_stale_disabled_or_ambiguous_selection(self):
        for change in ("disabled-native", "disabled-custom", "duplicate-canonical-custom"):
            with self.subTest(change=change), self.fixture() as case:
                value = copy.deepcopy(case.lib.CONFIG)
                if change == "disabled-native":
                    value["senses"]["disable"].append("aegis")
                elif change == "disabled-custom":
                    value["custom_senses"][0]["enabled"] = False
                else:
                    duplicate = copy.deepcopy(value["custom_senses"][0])
                    duplicate["name"] = duplicate["name"].upper()
                    value["custom_senses"].append(duplicate)
                # Observe a valid actual load and equivalent current bytes;
                # intentionally retain the old runtime registry and pinned
                # selection. Capture must refuse, never rebuild probes.
                case.install_config(value, rebuild=False)
                self.assertIs(case.lib._active_config_load_valid(), True)
                self.assertEqual(case.lib.CONFIG_ERRORS, [])
                self.assertEqual(native_bytes(case.lib.CONFIG), native_bytes(value))
                with mock.patch.object(case.lib, "_build_organs", side_effect=AssertionError("capture repaired stale selection")):
                    self.refused(case)

    def test_config_leaf_must_be_owned_regular_strict_json_and_not_a_symlink(self):
        for change in ("symlink", "directory", "hardlinked", "over-bound-valid-json",
                       "invalid-utf8", "duplicate-key", "nonfinite-json"):
            with self.subTest(change=change), self.fixture() as case:
                if change == "symlink":
                    retained = case.root / "retained-config.json"
                    case.config_path.rename(retained)
                    case.config_path.symlink_to(retained)
                elif change == "directory":
                    case.config_path.rename(case.root / "retained-config.json")
                    case.config_path.mkdir(mode=0o700)
                elif change == "hardlinked":
                    os.link(case.config_path, case.root / "linked-config.json")
                elif change == "over-bound-valid-json":
                    raw = case.config_path.read_bytes().ljust(case.lib.MAX_CONFIG_BYTES, b" ") + b" "
                    case.config_path.write_bytes(raw)
                    self.assertGreater(len(raw), case.lib.MAX_CONFIG_BYTES)
                    self.assertEqual(native_bytes(case.lib._strict_json_loads(raw)), native_bytes(case.lib.CONFIG))
                elif change == "invalid-utf8":
                    case.config_path.write_bytes(b"\xff")
                elif change == "duplicate-key":
                    case.config_path.write_bytes(b'{"custom_senses":[],"custom_senses":[]}')
                else:
                    case.config_path.write_bytes(b'{"judge":{"value":NaN}}')
                self.refused(case)

    def test_actual_source_callback_revalidates_config_registry_and_callable_identities(self):
        for change in ("noop", "equal-config-replacement", "config-value", "config-errors", "load-validity",
                       "organ-metadata", "organ-list", "organ-order", "sense-roster",
                       "same-name-callable", "same-bytes-file-replacement"):
            with self.subTest(change=change), self.fixture() as case:
                source_path = case.configuration["custom_collectors"][0]["path"]
                actual_identity = case.lib._source_path_identity
                reached = []

                def identity(path, *args, **kwargs):
                    result = actual_identity(path, *args, **kwargs)
                    if os.path.abspath(path) == source_path and not reached:
                        reached.append(True)
                        if change == "equal-config-replacement":
                            case.lib.CONFIG = copy.deepcopy(case.lib.CONFIG)
                        elif change == "config-value":
                            case.lib.CONFIG["_comment"] = "changed inside actual source callback"
                        elif change == "config-errors":
                            case.lib.CONFIG_ERRORS.append({"config": "config.json", "error": "config-invalid-json"})
                        elif change == "load-validity":
                            case.lib._LAST_CONFIG_LOAD_VALID = False
                        elif change == "organ-metadata":
                            organ = next(iter(case.lib.ORGANS))
                            name, _description = case.lib.ORGANS[organ]
                            case.lib.ORGANS[organ] = (name, "changed runtime organ description")
                        elif change == "organ-list":
                            organ = next(iter(case.lib.ORGANS))
                            case.lib.ORGANS[organ] = list(case.lib.ORGANS[organ])
                        elif change == "organ-order":
                            case.lib.ORGANS = dict(reversed(list(case.lib.ORGANS.items())))
                        elif change == "sense-roster":
                            case.lib.SENSES = [*case.lib.SENSES, case.lib.sense_agents]
                        elif change == "same-name-callable":
                            def impostor(*_args, **_kwargs):
                                raise AssertionError("same-name replacement collector executed")
                            impostor.__name__ = case.lib.sense_custom.__name__
                            case.lib.sense_custom = impostor
                        elif change == "same-bytes-file-replacement":
                            self.replace_same_config_bytes(case, "callback-original-config.json")
                    return result

                with mock.patch.object(case.lib, "_source_path_identity", side_effect=identity):
                    if change == "noop":
                        result = case.capture()
                        self.assert_receipt(case, result["configuration_receipt"])
                    else:
                        self.refused(case)
                self.assertTrue(reached, "actual custom-source identity callback was not exercised")

    def test_late_final_copy_and_digest_revalidate_configuration_generation(self):
        for boundary in ("copy", "digest"):
            for mutate in (False, True):
                with self.subTest(boundary=boundary, mutate=mutate), self.fixture() as case:
                    reached = []

                    def is_batch(value):
                        return type(value) is dict and value.get("schema") == "sia-controller-source-batch-v1" \
                            and type(value.get("configuration_receipt")) is dict \
                            and value["configuration_receipt"].get("schema") == "sia-controller-observed-configuration-v1"

                    def observe(value):
                        if is_batch(value) and not reached:
                            reached.append(True)
                            if mutate:
                                self.replace_same_config_bytes(case, "late-original-config.json")

                    def detached(value, *args, **kwargs):
                        if is_batch(value) and "batch_sha256" in value:
                            observe(value)
                        return copy.deepcopy(value, *args, **kwargs)

                    def finalized(raw):
                        try:
                            value = json.loads(raw)
                        except (UnicodeError, ValueError):
                            return
                        observe(value)

                    with contextlib.ExitStack() as stack:
                        if boundary == "copy":
                            stack.enter_context(mock.patch.object(
                                case.lib, "copy", page_tests._ModuleShim(copy, deepcopy=detached)))
                        else:
                            stack.enter_context(mock.patch.object(case.lib, "hashlib", hash_tests._HashShim(finalized)))
                        if mutate:
                            self.refused(case)
                        else:
                            result = case.capture()
                            self.assert_receipt(case, result["configuration_receipt"])
                    self.assertTrue(reached, "actual complete source-batch " + boundary + " boundary was not exercised")

