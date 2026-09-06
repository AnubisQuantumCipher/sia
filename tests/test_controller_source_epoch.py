"""Production-owned initial controller-source epoch construction.

The fixture supplies an inert owner namespace: collector callables raise if
invoked, so these tests distinguish policy/configuration construction from
source observation.  The checked-in policy is an engineering selection, not
benchmark evidence or a neurocognitive claim.
"""

import copy
import hashlib
import importlib
import inspect
import json
import math
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "bin"))

OBSERVED_AT = 2000000000
EXPECTED_POLICY_SHA256 = "299d4fb5ff7ffe8d466d997780b8c67346ac4201b96dd0b3d62801ccc486e787"
POLICY = {
    "schema": "sia-live-loop-policy-v2",
    "scope": "complete-controller-observations-since-declared-epoch-v1",
    "time_unit": "unix-seconds-integer",
    "encoding": {
        "v": 1, "algorithm": "dirichlet-prequential-information-v1",
        "time_unit": "unix-seconds-integer", "pseudocount": 1,
        "signal": "relative-novelty", "strength_base": 1,
        "strength_scale": 1, "strength_cap": 8,
        "max_events": 4096, "max_symbols": 256, "max_contexts": 256,
    },
    "activation": {
        "v": 1, "algorithm": "log-sum-power-law-v1",
        "time_unit": "unix-seconds-integer", "decay": 1,
        "age_offset_seconds": 1, "tie_break": "stable-input-order",
        "unavailable": "last", "max_uses": 4096,
        "max_total_uses": 4096, "max_candidates": 256,
    },
    "workspace": {
        "v": 1, "algorithm": "activation-competition-held-payload-v1",
        "time_unit": "unix-seconds-integer", "slots": 1,
        "ignition_threshold": -2, "hold_seconds": 10,
        "max_hold_seconds": 60, "tie_break": "stable-input-order",
        "release_policy": "expire-or-explicit",
        "consumer_roster": ["resident-status", "context-selection"],
        "max_candidates": 256, "max_consumers": 16,
        "max_content_bytes": 4096, "max_payload_bytes": 65536,
        "max_broadcast_bytes": 1048576,
    },
    "coretrieval": {
        "v": 1, "algorithm": "joint-activity-product-v1",
        "time_unit": "unix-seconds-integer", "learning_rate": 0.5,
        "excluded_subjects": [],
        "hygiene": {
            "algorithm": "elapsed-period-retention-v1", "period_seconds": 2,
            "retention_per_period": 0.5, "weight_floor": 0,
            "degree_cap": 256, "cap_order": "weight-desc-pair-id",
        },
        "max_nodes": 256, "max_deliveries": 4096,
        "max_activities_per_delivery": 256, "max_total_activities": 4096,
        "max_pair_updates": 4096, "max_pairs": 4096,
        "max_graph_edges": 4096,
    },
    "novelty_admission": {
        "comparison": "strength-at-least-v1", "threshold": 2,
        "aggregation": "any-admitted-occurrence-per-version-v1",
        "explicit_delivery": "admit-without-novelty-filter-v1",
    },
    "activation_events": ["encoding-admitted", "service-output-completed"],
    "workspace_release": "expiry-only-v1",
    "recall_order": "origin-slot-preserving-activation-v1",
    "delivery_body": "result-body-before-queue-health-footer-v1",
    "delivery_activity": 1,
    "idle": "bound-native-episodes-replay-gist-fresh-derived-only-v2",
    "limits": {
        "max_input_bytes": 16777216, "max_output_bytes": 16777216,
        "max_versions": 256, "max_observations": 4096,
        "max_deliveries": 4096, "max_rows": 256,
        "max_content_bytes": 1048576, "max_delivery_bytes": 1048576,
    },
}
SOURCE_NON_CLAIMS = [
    "These caller-supplied source selections and returns do not witness config.json, effective runtime configuration, installed sources, collector execution, cursor state, or acknowledgments.",
    "Completeness covers the declared collector-return roster only, not raw source records, omitted native history, or non-event controller observations.",
]
PROFILE = {
    "schema": "sia-controller-source-return-profile-v1",
    "scope": "source-return-frequency-not-raw-record-or-content-novelty-v1",
    "time_unit": "unix-seconds-integer", "symbol": "source-id-v1",
    "context": "controller-source-return", "source_order": "catalog-order-v1",
    "event_order": "collector-return-order-v1",
    "association_identity": "epoch-source-event-id-v1",
    "repeated_association": "retain-first-clock-version-and-metadata-v1",
    "native_timestamp": "first-normalized-event-ts-metadata-only-v1",
    "current_versions": "stable-subject-order-replace-exact-before-v1",
}


def custom(name, organ, path, *, enabled=True):
    return {
        "name": name, "organ": organ, "description": name + " events",
        "path": path, "type": "lines", "enabled": enabled,
        "match": "", "exclude": "", "field": "message", "kind": "event",
        "tags": [organ],
    }


class InitialControllerSourceEpoch(unittest.TestCase):
    def setUp(self):
        try:
            self.component = importlib.import_module("siacontrollerepoch")
        except ModuleNotFoundError as exc:
            self.fail("production initial controller epoch builder must exist: " + str(exc))
        self.source = importlib.import_module("siasourcebatch")
        self.calls = []

        def collector():
            self.calls.append("native-one")
            raise AssertionError("epoch construction invoked a collector")

        collector.__name__ = "sense_native_one"

        def collector_two():
            self.calls.append("native-two")
            raise AssertionError("epoch construction invoked a collector")

        collector_two.__name__ = "sense_native_two"

        def custom_collector():
            self.calls.append("custom")
            raise AssertionError("epoch construction invoked a collector")

        custom_collector.__name__ = "sense_custom"
        self.native_one = collector
        self.native_two = collector_two
        self.custom_collector = custom_collector
        self.alpha = custom("alpha", "alpha", "/tmp/sia-source-alpha")
        self.off = custom("off", "off", "/tmp/sia-source-off", enabled=False)
        self.hidden = custom("hidden", "hidden", "/tmp/sia-source-hidden")
        self.omega = custom("omega", "omega", "/tmp/sia-source-omega")
        config = {
            "senses": {"disable": ["hidden"]},
            "custom_senses": [self.alpha, self.off, self.hidden, self.omega],
        }

        def sanitize(value):
            return value.lower().strip().replace(" ", "-")

        def validate(entry):
            allowed = {
                "_comment", "name", "organ", "description", "path", "type",
                "enabled", "match", "exclude", "field", "kind", "tags",
            }
            if type(entry) is not dict or set(entry) - allowed:
                raise ValueError("fixture custom contract")
            if "enabled" in entry and type(entry["enabled"]) is not bool:
                raise ValueError("fixture enabled contract")
            if entry.get("enabled") is False:
                return None
            if type(entry.get("name")) is not str or not entry["name"].strip():
                raise ValueError("fixture name contract")
            name = sanitize(entry["name"])
            raw_organ = entry.get("organ", name)
            if type(raw_organ) is not str or not raw_organ.strip():
                raise ValueError("fixture organ contract")
            organ = sanitize(raw_organ)
            description = entry.get("description", "custom evidence stream")
            path = entry.get("path")
            stream_type = entry.get("type", "lines")
            match, exclude = entry.get("match", ""), entry.get("exclude", "")
            field, kind = entry.get("field", "message"), entry.get("kind", "event")
            tags = entry.get("tags", [])
            if type(description) is not str or type(path) is not str or not path.strip() \
                    or stream_type not in {"lines", "jsonl"} \
                    or type(match) is not str or type(exclude) is not str \
                    or type(field) is not str or not field.strip() \
                    or type(kind) is not str or not kind.strip() \
                    or type(tags) is not list \
                    or any(type(tag) is not str or not tag.strip() for tag in tags):
                raise ValueError("fixture field contract")
            return {
                "name": name, "source_id": "sense_custom:" + name,
                "organ": organ, "description": description,
                "path": os.path.expanduser(path), "stream_type": stream_type,
                "match_literals": tuple(match.split("|")) if match else (),
                "exclude_literals": tuple(exclude.split("|")) if exclude else (),
                "field": field, "kind": sanitize(kind),
                "tags": {sanitize(tag) for tag in tags} | {organ},
            }

        self.owner = {
            "copy": copy, "hashlib": hashlib, "json": json, "math": math,
            "os": os,
            "HOME": "/owned/sia", "MAX_CONFIG_PATH_CHARS": 4096,
            "MAX_STATE_JSON_BYTES": 16777216,
            "MAX_SOURCE_REPLAY_EVENTS": 4096,
            "MAX_SOURCE_REPLAY_SOURCES": 256,
            "MAX_LEDGER_PENDING_RECORDS": 4096,
            "MAX_CONFIG_BYTES": 1048576,
            "CONFIG": config, "CONFIG_ERRORS": [],
            "ORGANS": {
                "one": ("One", "first native source"),
                "two": ("Two", "second native source"),
                "alpha": ("Alpha", "first custom source"),
                "alpha-feed": ("Alpha Feed", "abbreviated custom source"),
                "hidden": ("Hidden", "disabled custom source"),
                "omega": ("Omega", "last custom source"),
            },
            "_SENSE_ORGAN": {
                "sense_native_one": "one", "sense_native_two": "two",
            },
            "SENSES": [collector, collector_two, custom_collector],
            "sense_native_one": collector, "sense_native_two": collector_two,
            "sense_custom": custom_collector,
            "sanitize_slugpart": sanitize,
            "_validated_custom_sense_entry": validate,
        }

    def build(self, owner=None):
        return self.component.build_initial(
            self.owner if owner is None else owner, observed_at=OBSERVED_AT)

    def assert_refusal(self, callback, reason):
        with self.assertRaises(self.component.ControllerEpochRefusal) as caught:
            callback()
        self.assertEqual(caught.exception.reason, reason)
        self.assertTrue(caught.exception.non_claims)
        self.assertEqual(self.calls, [])

    def test_literal_policy_is_independent_valid_and_pinned(self):
        source_text = Path(self.component.__file__).read_text(encoding="utf-8")
        self.assertNotIn("from tests", source_text)
        self.assertNotIn("import tests", source_text)
        self.assertEqual(self.component.LIVE_POLICY, POLICY)
        self.assertEqual(self.component.EXPECTED_LIVE_POLICY_SHA256,
                         EXPECTED_POLICY_SHA256)
        self.component._live._policy(copy.deepcopy(self.component.LIVE_POLICY))
        self.assertEqual(self.source._component_sha(self.owner, POLICY),
                         EXPECTED_POLICY_SHA256)

    def test_builds_capture_ready_initial_epoch_from_exact_active_order(self):
        signature = inspect.signature(self.component.build_initial)
        self.assertEqual(tuple(signature.parameters), ("owner", "observed_at"))
        self.assertEqual(signature.parameters["owner"].kind,
                         inspect.Parameter.POSITIONAL_OR_KEYWORD)
        self.assertEqual(signature.parameters["observed_at"].kind,
                         inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(signature.parameters["observed_at"].default,
                      inspect.Parameter.empty)
        result = self.build()
        self.assertEqual(set(result), {"epoch", "expected_epoch_sha256", "observed_at"})
        self.assertEqual(result["observed_at"], OBSERVED_AT)
        epoch = result["epoch"]
        configuration = {
            "schema": "sia-controller-source-selection-v1",
            "native_collectors": ["sense_native_one", "sense_native_two"],
            "custom_collectors": [self.alpha, self.omega],
            "non_claims": SOURCE_NON_CLAIMS,
        }
        catalog = {
            "schema": "sia-controller-source-catalog-v1",
            "configuration_sha256": self.source._component_sha(self.owner, configuration),
            "sources": [
                {"source_id": "sense_native_one", "collector": "sense_native_one",
                 "organ": "one", "custom_name": None},
                {"source_id": "sense_native_two", "collector": "sense_native_two",
                 "organ": "two", "custom_name": None},
                {"source_id": "sense_custom:alpha", "collector": "sense_custom",
                 "organ": "alpha", "custom_name": "alpha"},
                {"source_id": "sense_custom:omega", "collector": "sense_custom",
                 "organ": "omega", "custom_name": "omega"},
            ],
            "non_claims": SOURCE_NON_CLAIMS,
        }
        self.assertEqual(epoch["configuration"], configuration)
        self.assertEqual(epoch["source_catalog"], catalog)
        self.assertEqual(epoch["profile"], {
            **PROFILE, "live_policy_sha256": EXPECTED_POLICY_SHA256,
            "non_claims": SOURCE_NON_CLAIMS,
        })
        self.assertEqual(epoch["history"], {
            "schema": "sia-controller-event-history-v1",
            "epoch_id": epoch["epoch_id"], "started_at": OBSERVED_AT,
            "complete": True, "entries": [], "non_claims": SOURCE_NON_CLAIMS,
        })
        self.assertIsNone(epoch["predecessor"])
        for name in ("configuration", "source_catalog", "profile", "live_policy", "history"):
            self.assertEqual(epoch["expected_" + name + "_sha256"],
                             self.source._component_sha(self.owner, epoch[name]))
        self.assertEqual(result["expected_epoch_sha256"],
                         self.source.native_sha(self.owner, epoch))
        self.source._validate_epoch(
            self.owner, epoch, result["expected_epoch_sha256"], OBSERVED_AT,
            initial=True)
        self.source._runtime_projection(self.owner, epoch)
        self.assertLessEqual(len(self.source.native_bytes(self.owner, result)),
                             self.owner["MAX_STATE_JSON_BYTES"])
        self.assertEqual(self.calls, [])

    def test_result_is_detached_from_owner_and_checked_in_policy(self):
        result = self.build()
        retained = copy.deepcopy(result)
        self.owner["CONFIG"]["custom_senses"][0]["description"] = "changed"
        self.owner["SENSES"].clear()
        self.assertEqual(result, retained)
        result["epoch"]["live_policy"]["schema"] = "changed"
        self.assertEqual(self.component.LIVE_POLICY, POLICY)
        self.assertEqual(self.calls, [])

    def test_normalizes_abbreviated_custom_entries_against_owned_home(self):
        abbreviated = [
            {
                "_comment": "declaration-only prose", "name": "Alpha Feed",
                "path": "~/.local/state/alpha/../alpha.log",
            },
            {"name": "off", "enabled": False},
            {"name": "hidden", "path": "~/hidden.log"},
            {
                "name": "Omega", "organ": "omega",
                "description": "omega JSON events",
                "path": "/tmp/sia-source/../omega.jsonl", "type": "jsonl",
                "match": "accepted|retained", "exclude": "ignored",
                "field": "payload", "kind": "Build Event",
                "tags": ["Zeta", "omega", "zeta"],
            },
        ]
        owner = dict(self.owner)
        owner["CONFIG"] = {
            "senses": {"disable": ["hidden"]},
            "custom_senses": abbreviated,
        }
        original = copy.deepcopy(owner["CONFIG"])
        result = self.build(owner)
        selected = result["epoch"]["configuration"]["custom_collectors"]
        self.assertEqual(selected, [
            {
                "name": "alpha-feed", "organ": "alpha-feed",
                "description": "custom evidence stream",
                "path": "/owned/sia/.local/state/alpha.log", "type": "lines",
                "enabled": True, "match": "", "exclude": "",
                "field": "message", "kind": "event", "tags": ["alpha-feed"],
            },
            {
                "name": "omega", "organ": "omega",
                "description": "omega JSON events", "path": "/tmp/omega.jsonl",
                "type": "jsonl", "enabled": True,
                "match": "accepted|retained", "exclude": "ignored",
                "field": "payload", "kind": "build-event",
                "tags": ["omega", "zeta"],
            },
        ])
        self.assertEqual(owner["CONFIG"], original)
        self.assertEqual(
            [row["source_id"] for row in result["epoch"]["source_catalog"]["sources"]
             if row["collector"] == "sense_custom"],
            ["sense_custom:alpha-feed", "sense_custom:omega"])
        projection, custom_indexes, _identities = \
            self.source._runtime_projection(owner, result["epoch"])
        self.assertEqual(projection["custom_entries"], [
            {"entry_index": 0, "source_id": "sense_custom:alpha-feed"},
            {"entry_index": 3, "source_id": "sense_custom:omega"},
        ])
        self.assertEqual(custom_indexes, {
            "sense_custom:alpha-feed": 0, "sense_custom:omega": 3,
        })
        self.assertEqual(self.calls, [])

    def test_abbreviated_custom_foreign_keys_types_and_paths_refuse_without_collection(self):
        cases = (
            ({"name": "alpha", "path": "~/alpha.log", "foreign": True},
             "runtime-custom-selection"),
            ({"name": "alpha", "path": "~/alpha.log", "enabled": "yes"},
             "runtime-custom-selection"),
            ({"name": "alpha", "path": "~/alpha.log", "type": "csv"},
             "runtime-custom-selection"),
            ({"name": "alpha", "path": "relative/alpha.log"},
             "custom-selection-path"),
            ({"name": "alpha", "path": "~another/alpha.log"},
             "custom-selection-path"),
        )
        for entry, reason in cases:
            owner = dict(self.owner)
            owner["CONFIG"] = {
                "senses": {"disable": []}, "custom_senses": [entry],
            }
            with self.subTest(entry=entry):
                self.assert_refusal(lambda owner=owner: self.build(owner), reason)

    def test_refuses_bad_clock_config_errors_empty_roster_and_drift_before_collectors(self):
        for bad_clock in (False, 1.0, -1):
            with self.subTest(clock=bad_clock):
                self.assert_refusal(
                    lambda bad_clock=bad_clock: self.component.build_initial(
                        self.owner, observed_at=bad_clock),
                    "controller-clock")

        bad = dict(self.owner)
        bad["CONFIG_ERRORS"] = ["invalid-active-config"]
        bad["_validated_custom_sense_entry"] = mock.Mock(
            side_effect=AssertionError("CONFIG_ERRORS reached custom validation"))
        self.assert_refusal(lambda: self.build(bad), "active-configuration-errors")
        bad["_validated_custom_sense_entry"].assert_not_called()

        empty = dict(self.owner)
        empty["CONFIG"] = {
            "senses": {"disable": []},
            "custom_senses": [custom(
                "off", "off", "/tmp/sia-source-off", enabled=False)],
        }
        empty["SENSES"] = [self.custom_collector]
        self.assert_refusal(lambda: self.build(empty), "no-active-source")

        drift = dict(self.owner)

        def replacement():
            raise AssertionError("identity drift callable invoked")

        replacement.__name__ = "sense_native_one"
        drift["sense_native_one"] = replacement
        self.assert_refusal(lambda: self.build(drift), "runtime-sense-identity")

        with mock.patch.object(
                self.component, "EXPECTED_LIVE_POLICY_SHA256", "0" * 64):
            self.assert_refusal(self.build, "live-policy-pin")


if __name__ == "__main__":
    unittest.main()
