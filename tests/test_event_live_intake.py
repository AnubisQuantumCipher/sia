"""Caller-supplied collector returns -> complete pure live intake.

The real Event, event-plan and live-loop fixtures are composed, never inherited as an accidental repeated test roster. Fixture
page publication/consolidation occurs only during setup, outside the pure
bridge call. Every source/configuration/clock claim here is synthetic.

This is NOT the future runtime source-batch transaction: no config.json file,
installed collector, cursor, pending source replay, or acknowledgment is
captured. All declared collectors appear even when their return list is empty.
Plan input_records retain duplicate original returns; observation identities
deduplicate only the explicit epoch/source/Event unit. Native metadata never
supplies the observation clock. Full component policies remain explicit.

Clock fixtures are imported unchanged from test_live_loop, whose complete
JACKAL parsed/status/nonclaims documentation remains controlling. No new
numeric score, clock conversion, threshold result or arithmetic oracle is
introduced. Actual component scores are exercised, not locally reconstructed.
"""

import base64
import contextlib
import copy
import hashlib
import importlib
import inspect
import os
from pathlib import Path
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_event_page_plan as page_tests
from tests import test_live_loop as live_tests


SOURCE_NON_CLAIMS = [
    "These caller-supplied source selections and returns do not witness config.json, effective runtime configuration, installed sources, collector execution, cursor state, or acknowledgments.",
    "Completeness covers the declared collector-return roster only, not raw source records, omitted native history, or non-event controller observations.",
]
NON_CLAIMS = live_tests.NON_CLAIMS + SOURCE_NON_CLAIMS + [
    "This pure projection binds supplied collector returns to frozen page versions; it does not publish a live generation, observe service output, settle source debt, or establish pulse/cursor/acknowledgment ordering.",
    "Event-page source hashes remain exact page-byte hashes; this projection does not synthesize a native capture, gist input, or pre-epoch use trace.",
    "Retained-epoch semantic and index provenance is inherited from the independently pinned render plan; this pure projection does not replay index bytes absent from that plan.",
]
RESULT_KEYS = {"schema", "status", "bindings", "associations", "intake", "intake_sha256",
               "source_non_claims", "non_claims", "projection_sha256"}
ASSOCIATION_KEYS = {"source_returns_sha256", "source_id", "return_index", "event_id",
                    "semantic_id", "admission", "observation_id", "observation_version_sha256",
                    "observation_timestamp", "status"}
ADMISSION_KEYS = {"event_batch_sha256", "plan_sha256", "slug", "version_sha256", "disposition"}
INTAKE_KEYS = {"schema", "epoch_id", "started_at", "complete", "pages", "current_versions",
               "symbols", "contexts", "observations"}
PAGE_KEYS = {"subject", "content", "origin", "source_sha256", "content_sha256", "version_sha256"}
OBSERVATION_KEYS = {"id", "timestamp", "version_sha256", "symbol", "context", "native_timestamp"}
REFUSALS = page_tests.REFUSALS
canonical = page_tests.canonical
bytes_digest = page_tests.digest


def digest(value):
    return bytes_digest(canonical(value))


def own(value, field):
    return digest({key: item for key, item in value.items() if key != field})


def observation_id(source_id, event_id):
    return digest({"schema": "sia-controller-event-association-v1",
                   "epoch_id": live_tests.EPOCH, "source_id": source_id, "event_id": event_id})


class EventLiveIntakeProjection(unittest.TestCase):
    def setUp(self):
        self.fixture = page_tests.EventPageRenderPlan(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib = self.fixture.lib
        self.assertTrue(callable(getattr(self.lib, "_prepare_event_live_intake", None)),
                        "missing pure event/live intake bridge: _prepare_event_live_intake")
        self.live = importlib.import_module("sialiveloop")
        self.policy = live_tests.policy_fixture()
        self.configuration = {
            "schema": "sia-controller-source-selection-v1", "native_collectors": [],
            "custom_collectors": [self.custom(name) for name in ("alpha", "beta", "empty")],
            "non_claims": list(SOURCE_NON_CLAIMS),
        }
        self.catalog = self.catalog_for(self.configuration)
        self.profile = {
            "schema": "sia-controller-source-return-profile-v1",
            "scope": "source-return-frequency-not-raw-record-or-content-novelty-v1",
            "time_unit": "unix-seconds-integer", "symbol": "source-id-v1",
            "context": "controller-source-return", "source_order": "catalog-order-v1",
            "event_order": "collector-return-order-v1",
            "association_identity": "epoch-source-event-id-v1",
            "repeated_association": "retain-first-clock-version-and-metadata-v1",
            "native_timestamp": "first-normalized-event-ts-metadata-only-v1",
            "current_versions": "stable-subject-order-replace-exact-before-v1",
            "live_policy_sha256": digest(self.policy), "non_claims": list(SOURCE_NON_CLAIMS),
        }

    def custom(self, name):
        return {"name": name, "organ": "org", "description": "Synthetic declared source",
                "path": str(self.fixture.fixture.root / (name + ".log")), "type": "lines",
                "enabled": True, "match": "", "exclude": "", "field": "message",
                "kind": "obs", "tags": ["org"]}

    def catalog_for(self, configuration):
        sources = [{"source_id": collector, "collector": collector,
                    "organ": self.lib._SENSE_ORGAN[collector], "custom_name": None}
                   for collector in configuration["native_collectors"]]
        for entry in configuration["custom_collectors"]:
            normalized = self.lib._validated_custom_sense_entry(entry)
            sources.append({"source_id": normalized["source_id"], "collector": "sense_custom",
                            "organ": normalized["organ"], "custom_name": normalized["name"]})
        return {"schema": "sia-controller-source-catalog-v1",
                "configuration_sha256": digest(configuration), "sources": sources,
                "non_claims": list(SOURCE_NON_CLAIMS)}

    def event(self, day=None, occurrence="native:intake:first"):
        return self.fixture.event(day, occurrence)

    def entry(self, supplied, *, stamp=live_tests.NOW, batch_id="first-source-return"):
        runs, grouped = [], {}
        for source in self.catalog["sources"]:
            events = supplied.get(source["source_id"], [])
            records = [self.lib._event_replay_record(event) for event in events]
            runs.append({"source_id": source["source_id"], "events": records})
            for event, record in zip(events, records, strict=True):
                # Preserve ALL duplicate returned records. Individual plans
                # retain that exact input roster; admissions are unique.
                grouped.setdefault((event.organ, record["ts"][:10]), []).append(event)
        by_organ = {}
        for (organ, day), events in sorted(grouped.items()):
            plan = self.fixture.prepare(events, day=day, organ=organ)
            by_organ.setdefault(organ, []).append(plan)
        batches = []
        for _organ, plans in sorted(by_organ.items()):
            batch = self.lib._compose_event_page_plans(
                plans=plans, expected_plan_sha256s=[plan["plan_sha256"] for plan in plans])
            batches.append({"batch": batch, "expected_batch_sha256": batch["batch_sha256"]})
        returns = {"schema": "sia-controller-source-returns-v1", "batch_id": batch_id,
                   "epoch_id": live_tests.EPOCH, "observed_at": stamp, "complete": True,
                   "configuration_sha256": digest(self.configuration),
                   "source_catalog_sha256": digest(self.catalog), "profile_sha256": digest(self.profile),
                   "live_policy_sha256": digest(self.policy), "runs": runs,
                   "non_claims": list(SOURCE_NON_CLAIMS)}
        returns["returns_sha256"] = digest(returns)
        return {"source_returns": returns, "expected_source_returns_sha256": returns["returns_sha256"],
                "event_batches": batches}

    def request(self, entries=None):
        if entries is None:
            entries = [self.entry({
                "sense_custom:alpha": [self.event()],
                "sense_custom:beta": [self.event("2026-01-07", "native:intake:other")],
            })]
        history = {"schema": "sia-controller-event-history-v1", "epoch_id": live_tests.EPOCH,
                   "started_at": live_tests.START, "complete": True, "entries": entries,
                   "non_claims": list(SOURCE_NON_CLAIMS)}
        return {"history": history, "expected_history_sha256": digest(history),
                "source_catalog": self.catalog, "expected_source_catalog_sha256": digest(self.catalog),
                "configuration": self.configuration, "expected_configuration_sha256": digest(self.configuration),
                "profile": self.profile, "expected_profile_sha256": digest(self.profile),
                "live_policy": self.policy, "expected_live_policy_sha256": digest(self.policy),
                "observed_at": entries[-1]["source_returns"]["observed_at"]}

    def publish_entry_fixture(self, entry):
        for row in entry["event_batches"]:
            self.lib._publish_event_page_plan_batch(
                batch=row["batch"], expected_batch_sha256=row["expected_batch_sha256"])

    @contextlib.contextmanager
    def pure_boundary(self):
        # All paths are established during fixture construction. The bridge
        # may use existing pure validators/parser providers, not current I/O.
        with contextlib.ExitStack() as stack:
            for name in ("corpus_owner", "load_config", "_configured_disabled_sense_policy", "load_cursors", "save_cursors",
                         "_capture_corpus_page_version", "_open_source_nofollow", "_source_path_identity",
                         "_before_corpus_mutation", "atomic_write", "update_day_page", "_render_event_shard",
                         "_prepare_event_page_plan", "_compose_event_page_plans", "_publish_event_page_plan_batch",
                         "_stage_live_generation", "_commit_sense_cursors", "gbrain", "gbrain_call", "brain_sync"):
                stack.enter_context(mock.patch.object(
                    self.lib, name, side_effect=AssertionError("pure bridge invoked " + name)))
            yield

    def project(self, request):
        with self.pure_boundary():
            return self.lib._prepare_event_live_intake(**request)

    def refused(self, request):
        before = self.fixture.snapshot()
        with self.assertRaises(REFUSALS):
            self.project(request)
        self.assertEqual(self.fixture.snapshot(), before)

    def reseal_returns(self, request, entry):
        value = entry["source_returns"]
        value["returns_sha256"] = own(value, "returns_sha256")
        entry["expected_source_returns_sha256"] = value["returns_sha256"]
        request["expected_history_sha256"] = digest(request["history"])

    def assert_projection(self, projected, request):
        self.assertEqual(set(projected), RESULT_KEYS)
        self.assertEqual(projected["schema"], "sia-event-live-intake-projection-v1")
        self.assertEqual(projected["status"], "prepared-not-published")
        self.assertEqual(projected["projection_sha256"], own(projected, "projection_sha256"))
        self.assertEqual(projected["non_claims"], NON_CLAIMS)
        self.assertEqual(projected["bindings"], {
            "history_sha256": request["expected_history_sha256"],
            "source_catalog_sha256": request["expected_source_catalog_sha256"],
            "configuration_sha256": request["expected_configuration_sha256"],
            "profile_sha256": request["expected_profile_sha256"],
            "live_policy_sha256": request["expected_live_policy_sha256"],
            "observed_at": request["observed_at"],
        })
        history = request["history"]
        self.assertEqual(projected["source_non_claims"], {
            "configuration": request["configuration"]["non_claims"],
            "source_catalog": request["source_catalog"]["non_claims"],
            "profile": request["profile"]["non_claims"], "history": history["non_claims"],
            "source_returns": [{"returns_sha256": row["expected_source_returns_sha256"],
                                "non_claims": row["source_returns"]["non_claims"]} for row in history["entries"]],
            "event_batches": [{"batch_sha256": row["expected_batch_sha256"],
                               "non_claims": row["batch"]["non_claims"]}
                              for entry in history["entries"] for row in entry["event_batches"]],
            "live_loop": live_tests.NON_CLAIMS,
        })
        intake = projected["intake"]
        self.assertEqual(set(intake), INTAKE_KEYS)
        self.assertEqual(intake["schema"], "sia-live-intake-v1")
        self.assertEqual(intake["epoch_id"], history["epoch_id"])
        self.assertEqual(intake["started_at"], history["started_at"])
        self.assertIs(intake["complete"], True)
        self.assertEqual(projected["intake_sha256"], digest(intake))
        self.assertEqual(intake["symbols"], [row["source_id"] for row in request["source_catalog"]["sources"]])
        self.assertEqual(intake["contexts"], [request["profile"]["context"]])
        versions = {}
        for page in intake["pages"]:
            self.assertEqual(set(page), PAGE_KEYS)
            self.assertEqual(page, self.lib._corpus_page_version_from_bytes(
                slug=page["subject"], raw=page["content"].encode("utf-8")))
            self.assertNotIn(page["version_sha256"], versions)
            versions[page["version_sha256"]] = page
        current_subjects = [versions[version]["subject"] for version in intake["current_versions"]]
        self.assertEqual(len(current_subjects), len(set(current_subjects)))
        expected_locations, first_observations = [], {}
        for entry in history["entries"]:
            returns = entry["source_returns"]
            admissions = {}
            for row in entry["event_batches"]:
                for plan in row["batch"]["members"]:
                    for admitted in plan["admissions"]:
                        key = (plan["organ"], plan["date"], admitted["event_id"])
                        value = {"event_batch_sha256": row["expected_batch_sha256"],
                                 "plan_sha256": plan["plan_sha256"],
                                 **{field: admitted[field] for field in
                                    ("slug", "version_sha256", "disposition")}}
                        if key in admissions:
                            self.assertEqual(admissions[key], value)
                        admissions[key] = value
            for run in returns["runs"]:
                for position, record in enumerate(run["events"]):
                    identifier = observation_id(run["source_id"], record["event_id"])
                    admitted = admissions[(record["organ"], record["ts"][:10], record["event_id"])]
                    first = identifier not in first_observations
                    if first:
                        first_observations[identifier] = {
                            "id": identifier, "timestamp": returns["observed_at"],
                            "version_sha256": admitted["version_sha256"], "symbol": run["source_id"],
                            "context": request["profile"]["context"], "native_timestamp": record["ts"],
                        }
                    observation = first_observations[identifier]
                    expected_locations.append({
                        "source_returns_sha256": entry["expected_source_returns_sha256"],
                        "source_id": run["source_id"], "return_index": position,
                        "event_id": record["event_id"], "semantic_id": record["semantic_id"],
                        "admission": admitted, "observation_id": identifier,
                        "observation_version_sha256": observation["version_sha256"],
                        "observation_timestamp": observation["timestamp"],
                        "status": "first-observation" if first else "already-observed",
                    })
        self.assertEqual(projected["associations"], expected_locations)
        for row in projected["associations"]:
            self.assertEqual(set(row), ASSOCIATION_KEYS)
            self.assertEqual(set(row["admission"]), ADMISSION_KEYS)
        self.assertEqual(intake["observations"], list(first_observations.values()))
        for observation in intake["observations"]:
            self.assertEqual(set(observation), OBSERVATION_KEYS)
            self.assertIn(observation["version_sha256"], versions)
        self.assertLessEqual(len(canonical(projected)), self.lib.MAX_STATE_JSON_BYTES)

    def live_transition(self, projected, request, *, previous=None):
        deliveries = {"schema": "sia-live-deliveries-v1", "epoch_id": live_tests.EPOCH,
                      "complete": True, "records": []}
        return self.live.prepare_pulse(
            intake=projected["intake"], expected_intake_sha256=projected["intake_sha256"],
            deliveries=deliveries, expected_deliveries_sha256=digest(deliveries),
            previous_state=None if previous is None else previous["state"],
            expected_previous_state_sha256=None if previous is None else previous["state_sha256"],
            policy=request["live_policy"], expected_policy_sha256=request["expected_live_policy_sha256"],
            observed_at=request["observed_at"], idle=False, gist_inputs=None)

    def test_complete_projection_has_exact_closed_shapes_and_real_live_history_admission(self):
        request = self.request()
        original, before = copy.deepcopy(request), self.fixture.snapshot()
        projected = self.project(request)
        self.assert_projection(projected, request)
        self.assertEqual(request, original)
        self.assertEqual(self.fixture.snapshot(), before)
        transition = self.live_transition(projected, request)
        capture = transition["history_capture"]
        self.assertEqual(self.live.admit_history_capture(
            capture, expected_capture_sha256=transition["history_capture_sha256"]), capture)
        self.assertEqual(capture["intake"], projected["intake"])
        self.assertEqual(capture["policy"], request["live_policy"])
        self.assertEqual(capture["observed_at"], request["observed_at"])

    def test_public_internal_api_is_exact_keyword_only_without_defaults(self):
        parameters = inspect.signature(self.lib._prepare_event_live_intake).parameters
        self.assertEqual(list(parameters), [
            "history", "expected_history_sha256",
            "source_catalog", "expected_source_catalog_sha256",
            "configuration", "expected_configuration_sha256",
            "profile", "expected_profile_sha256",
            "live_policy", "expected_live_policy_sha256", "observed_at",
        ])
        for parameter in parameters.values():
            self.assertIs(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
            self.assertIs(parameter.default, inspect.Parameter.empty)

    def test_all_zero_return_collectors_are_explicit_without_fabricated_observations(self):
        request = self.request([self.entry({})])
        self.assertTrue(request["history"]["entries"][0]["source_returns"]["runs"])
        self.assertEqual(request["history"]["entries"][0]["event_batches"], [])
        projected = self.project(request)
        self.assert_projection(projected, request)
        for key in ("pages", "current_versions", "observations"):
            self.assertEqual(projected["intake"][key], [])
        self.assertEqual(projected["associations"], [])
        transition = self.live_transition(projected, request)
        self.assertEqual(transition["state"]["uses"], [])
        self.assertEqual(transition["state"]["traces"], [])

    def test_return_order_not_page_date_order_controls_first_observation_roster(self):
        newer = self.event("2026-01-07", "native:intake:newer")
        older = self.event(self.fixture.day, "native:intake:older")
        request = self.request([self.entry({"sense_custom:alpha": [newer, older]})])
        plans = request["history"]["entries"][0]["event_batches"][0]["batch"]["members"]
        self.assertEqual([plan["date"] for plan in plans], [self.fixture.day, "2026-01-07"])
        projected = self.project(request)
        self.assert_projection(projected, request)
        self.assertEqual([row["native_timestamp"] for row in projected["intake"]["observations"]],
                         [self.lib._event_replay_record(event)["ts"] for event in (newer, older)])
        self.assertTrue(all(row["timestamp"] == live_tests.NOW for row in projected["intake"]["observations"]))

    def test_duplicate_records_stay_in_plan_and_provenance_but_do_not_duplicate_source_use(self):
        event = self.event()
        request = self.request([self.entry({"sense_custom:alpha": [event, event]})])
        plan = request["history"]["entries"][0]["event_batches"][0]["batch"]["members"][0]
        self.assertEqual(plan["input_records"], [self.lib._event_replay_record(event), self.lib._event_replay_record(event)])
        projected = self.project(request)
        self.assert_projection(projected, request)
        self.assertEqual([row["status"] for row in projected["associations"]],
                         ["first-observation", "already-observed"])
        self.assertEqual([row["id"] for row in projected["intake"]["observations"]],
                         [observation_id("sense_custom:alpha", self.lib.event_memory_identity(event))])
        self.assertEqual(self.project(request), projected)
        transition = self.live_transition(projected, request)
        self.assertEqual(transition["history_capture"]["intake"], projected["intake"])

    def test_same_event_and_organ_from_distinct_declared_collectors_remain_distinct_associations(self):
        event = self.event()
        request = self.request([self.entry({"sense_custom:alpha": [event], "sense_custom:beta": [event]})])
        projected = self.project(request)
        self.assert_projection(projected, request)
        self.assertEqual([row["symbol"] for row in projected["intake"]["observations"]],
                         ["sense_custom:alpha", "sense_custom:beta"])
        self.assertEqual({row["version_sha256"] for row in projected["intake"]["observations"]},
                         {projected["associations"][0]["admission"]["version_sha256"]})

    def test_repeated_retained_event_across_return_days_keeps_each_original_plan_join(self):
        self.fixture.fixture._source()
        events = [self.fixture.event(day) for day in ("2026-01-06", "2026-01-07")]
        request = self.request([self.entry({"sense_custom:alpha": events})])
        projected = self.project(request)
        self.assert_projection(projected, request)
        plans = request["history"]["entries"][0]["event_batches"][0]["batch"]["members"]
        self.assertEqual([row["admission"]["plan_sha256"] for row in projected["associations"]],
                         [plan["plan_sha256"] for plan in plans])
        self.assertEqual([row["status"] for row in projected["associations"]],
                         ["first-observation", "already-observed"])
        self.assertEqual([row["id"] for row in projected["intake"]["observations"]],
                         [observation_id("sense_custom:alpha", self.lib.event_memory_identity(events[0]))])

    def test_repeated_association_in_later_batch_keeps_original_clock_version_and_native_metadata(self):
        first = self.entry({"sense_custom:alpha": [self.event()]})
        self.publish_entry_fixture(first)
        later = self.entry({"sense_custom:alpha": [self.event("2026-01-07")]},
                           stamp=live_tests.DELIVERED_AT, batch_id="later-source-return")
        first_request = self.request([first])
        projected_first = self.project(first_request)
        request = self.request([first, later])
        projected = self.project(request)
        self.assert_projection(projected, request)
        self.assertEqual(projected["intake"]["observations"], projected_first["intake"]["observations"])
        self.assertEqual([row["status"] for row in projected["associations"]],
                         ["first-observation", "already-observed"])
        self.assertNotEqual(first["source_returns"]["runs"][0]["events"][0]["ts"],
                            later["source_returns"]["runs"][0]["events"][0]["ts"])
        prior = self.live_transition(projected_first, first_request)
        continued = self.live_transition(projected, request, previous=prior)
        self.assertEqual(continued["state"]["uses"], prior["state"]["uses"])

    def test_page_append_preserves_original_version_history_without_transferring_its_uses(self):
        # Explicit permissive test input, not a computed novelty threshold or
        # a change to the existing diagnostic/live policy defaults.
        self.policy["novelty_admission"]["threshold"] = 0.0
        self.profile["live_policy_sha256"] = digest(self.policy)
        old = self.event()
        first = self.entry({"sense_custom:alpha": [old]})
        self.publish_entry_fixture(first)
        new = self.event(occurrence="native:intake:new-page-version")
        later = self.entry({"sense_custom:alpha": [old, new]},
                           stamp=live_tests.DELIVERED_AT, batch_id="page-append-return")
        first_request = self.request([first])
        first_projection = self.project(first_request)
        request = self.request([first, later])
        projected = self.project(request)
        self.assert_projection(projected, request)
        old_pages = first_projection["intake"]["pages"]
        old_observations = first_projection["intake"]["observations"]
        self.assertEqual(projected["intake"]["pages"][:len(old_pages)], old_pages)
        self.assertEqual(projected["intake"]["observations"][:len(old_observations)], old_observations)
        self.assertNotEqual(projected["intake"]["current_versions"], first_projection["intake"]["current_versions"])
        first_state = self.live_transition(first_projection, first_request)
        original_version = first_projection["intake"]["current_versions"][0]
        original_page = next(page for page in old_pages if page["version_sha256"] == original_version)
        original_uses = first_state["state"]["uses"]
        self.assertTrue(original_uses, "the original version must have actual admitted typed uses")
        self.assertEqual({use["version_sha256"] for use in original_uses}, {original_version})
        self.assertEqual({use["kind"] for use in original_uses}, {"encoding-admitted"})
        self.assertEqual(first_state["state"]["workspace"]["slots"], [original_page["subject"]])
        self.assertIsNotNone(first_state["state"]["held_selection_receipt"])
        self.assertEqual(first_state["state"]["workspace"]["state"]["episode"]["expires_at"], live_tests.EXPIRED_AT)
        with self.assertRaises(self.live.LiveLoopRefusal):
            self.live_transition(projected, request, previous=first_state)

        # A later complete empty return cut advances the controller clock;
        # it neither changes the original return time nor invents a use.
        expiry = self.entry({}, stamp=live_tests.EXPIRED_AT, batch_id="expired-controller-observation")
        expired_request = self.request([first, later, expiry])
        expired_projection = self.project(expired_request)
        self.assert_projection(expired_projection, expired_request)
        self.assertEqual(expired_projection["intake"], projected["intake"])
        state = self.live_transition(expired_projection, expired_request, previous=first_state)["state"]
        self.assertEqual(state["uses"][:len(original_uses)], original_uses)
        current_version = projected["intake"]["current_versions"][0]
        self.assertNotEqual(current_version, original_version)
        self.assertTrue(any(use["version_sha256"] == current_version for use in state["uses"]))
        self.assertEqual(state["traces"], [
            {"v": 1, "subject": next(page["subject"] for page in projected["intake"]["pages"]
                                      if page["version_sha256"] == version), "complete": True,
             "uses": [{"id": use["id"], "timestamp": use["timestamp"]}
                      for use in state["uses"] if use["version_sha256"] == version]}
            for version in projected["intake"]["current_versions"]])

    def test_first_entry_append_retains_before_and_target_versions_without_before_use(self):
        self.policy["novelty_admission"]["threshold"] = 0.0
        self.profile["live_policy_sha256"] = digest(self.policy)
        _old, source, _record = self.fixture.fixture._source()
        original_raw = source.read_bytes()
        event = self.event(occurrence="native:intake:first-append")
        entry = self.entry({"sense_custom:alpha": [event]})
        page = entry["event_batches"][0]["batch"]["members"][0]["pages"][0]
        self.assertIs(page["write"], True)
        self.assertIsNotNone(page["before"])
        before_raw = base64.b64decode(page["before"]["raw_utf8_base64"], validate=True)
        target_raw = base64.b64decode(page["raw_utf8_base64"], validate=True)
        self.assertEqual(before_raw, original_raw)
        before = self.lib._corpus_page_version_from_bytes(slug=page["slug"], raw=before_raw)
        target = self.lib._corpus_page_version_from_bytes(slug=page["slug"], raw=target_raw)
        self.assertNotEqual(before["version_sha256"], target["version_sha256"])
        request = self.request([entry])
        projected = self.project(request)
        self.assert_projection(projected, request)
        self.assertEqual(projected["intake"]["pages"], [before, target])
        self.assertEqual(projected["intake"]["current_versions"], [target["version_sha256"]])
        self.assertEqual([row["id"] for row in projected["intake"]["observations"]],
                         [observation_id("sense_custom:alpha", self.lib.event_memory_identity(event))])
        self.assertEqual({row["version_sha256"] for row in projected["intake"]["observations"]},
                         {target["version_sha256"]})
        state = self.live_transition(projected, request)["state"]
        self.assertTrue(state["uses"], "the newly returned target must have an actual admitted use")
        self.assertEqual({use["version_sha256"] for use in state["uses"]}, {target["version_sha256"]})
        self.assertFalse(any(use["version_sha256"] == before["version_sha256"] for use in state["uses"]))

    def test_retained_model_page_preserves_full_original_unicode_frontmatter_and_origin(self):
        old, source, _record = self.fixture.fixture._source()
        raw = source.read_bytes().replace(b"---\n", b"---\norigin: 'model'\n", 1)
        raw = raw.replace(b"# ", "# éΩ — ".encode("utf-8"), 1)
        source.write_bytes(raw)
        entry = self.entry({"sense_custom:alpha": [old]})
        request = self.request([entry])
        projected = self.project(request)
        self.assert_projection(projected, request)
        version = next(page for page in projected["intake"]["pages"] if page["subject"] == self.fixture.slug)
        self.assertEqual(version["content"].encode("utf-8"), raw)
        self.assertEqual(version["origin"], "model")
        self.assertEqual(version["source_sha256"], bytes_digest(raw))
        self.assertEqual(version["content_sha256"], bytes_digest(raw))

    def test_retained_epoch_admission_uses_actual_epoch_version_not_unwritten_event_day(self):
        _old, source, _record = self.fixture.fixture._source()
        self.fixture.fixture._commit_corpus()
        self.lib.consolidate_corpus()
        self.assertFalse(source.exists(), "existing bounded consolidation fixture did not produce its epoch")
        entry = self.entry({"sense_custom:alpha": [self.fixture.event("2026-01-07")]})
        request = self.request([entry])
        projected = self.project(request)
        self.assert_projection(projected, request)
        association = projected["associations"][0]
        self.assertEqual(association["admission"]["disposition"], "retained-epoch")
        self.assertTrue(association["admission"]["slug"].startswith("epochs/org/"))
        self.assertEqual([page["subject"] for page in projected["intake"]["pages"]],
                         [association["admission"]["slug"]])

    def test_known_native_collector_uses_existing_mapping_and_page_origin_rules(self):
        self.configuration = {"schema": "sia-controller-source-selection-v1",
                              "native_collectors": ["sense_jackal"], "custom_collectors": [],
                              "non_claims": list(SOURCE_NON_CLAIMS)}
        self.catalog = self.catalog_for(self.configuration)
        template = self.event()
        native = self.lib.Event(self.lib._SENSE_ORGAN["sense_jackal"], template.ts,
                                template.kind, template.summary, set(template.links),
                                set(template.tags), occurrence="native:intake:jackal-fixture")
        request = self.request([self.entry({"sense_jackal": [native]})])
        projected = self.project(request)
        self.assert_projection(projected, request)
        self.assertEqual(projected["intake"]["symbols"], ["sense_jackal"])
        self.assertEqual([page["origin"] for page in projected["intake"]["pages"]], ["derived"])

    def test_missing_zero_return_collector_or_reordered_runs_is_not_complete(self):
        request = self.request()
        changes = []
        missing = copy.deepcopy(request)
        entry = missing["history"]["entries"][0]
        self.assertEqual(entry["source_returns"]["runs"][-1]["events"], [])
        entry["source_returns"]["runs"].pop()
        self.reseal_returns(missing, entry)
        changes.append(missing)
        reordered = copy.deepcopy(request)
        entry = reordered["history"]["entries"][0]
        entry["source_returns"]["runs"].reverse()
        self.reseal_returns(reordered, entry)
        changes.append(reordered)
        incomplete = copy.deepcopy(request)
        incomplete["history"]["complete"] = False
        incomplete["expected_history_sha256"] = digest(incomplete["history"])
        changes.append(incomplete)
        incomplete_returns = copy.deepcopy(request)
        entry = incomplete_returns["history"]["entries"][0]
        entry["source_returns"]["complete"] = False
        self.reseal_returns(incomplete_returns, entry)
        changes.append(incomplete_returns)
        for changed in changes:
            self.refused(changed)

    def test_unknown_source_and_wrong_declared_organ_refuse_even_with_new_envelope_hashes(self):
        request = self.request()
        unknown = copy.deepcopy(request)
        entry = unknown["history"]["entries"][0]
        entry["source_returns"]["runs"][0]["source_id"] = "sense_custom:unselected"
        self.reseal_returns(unknown, entry)
        self.refused(unknown)
        wrong_organ = copy.deepcopy(request)
        wrong_organ["source_catalog"]["sources"][0]["organ"] = "other"
        wrong_organ["expected_source_catalog_sha256"] = digest(wrong_organ["source_catalog"])
        entry = wrong_organ["history"]["entries"][0]
        entry["source_returns"]["source_catalog_sha256"] = wrong_organ["expected_source_catalog_sha256"]
        self.reseal_returns(wrong_organ, entry)
        self.refused(wrong_organ)

    def test_unknown_native_selection_and_ambiguous_canonical_custom_names_refuse(self):
        request = self.request()
        unknown = copy.deepcopy(request)
        unknown["configuration"]["native_collectors"] = ["sense_not_installed"]
        unknown["expected_configuration_sha256"] = digest(unknown["configuration"])
        self.refused(unknown)
        duplicate = copy.deepcopy(request)
        duplicate["configuration"]["custom_collectors"][1]["name"] = "ALPHA"
        duplicate["expected_configuration_sha256"] = digest(duplicate["configuration"])
        duplicate["source_catalog"]["configuration_sha256"] = duplicate["expected_configuration_sha256"]
        duplicate["expected_source_catalog_sha256"] = digest(duplicate["source_catalog"])
        entry = duplicate["history"]["entries"][0]
        entry["source_returns"]["configuration_sha256"] = duplicate["expected_configuration_sha256"]
        entry["source_returns"]["source_catalog_sha256"] = duplicate["expected_source_catalog_sha256"]
        self.reseal_returns(duplicate, entry)
        self.refused(duplicate)

    def test_explicit_disabled_custom_selection_refuses_instead_of_omitting_its_returns(self):
        request = copy.deepcopy(self.request())
        request["configuration"]["custom_collectors"][0]["enabled"] = False
        request["expected_configuration_sha256"] = digest(request["configuration"])
        request["source_catalog"]["configuration_sha256"] = request["expected_configuration_sha256"]
        request["expected_source_catalog_sha256"] = digest(request["source_catalog"])
        for entry in request["history"]["entries"]:
            self.assertTrue(entry["source_returns"]["runs"][0]["events"])
            entry["source_returns"]["configuration_sha256"] = request["expected_configuration_sha256"]
            entry["source_returns"]["source_catalog_sha256"] = request["expected_source_catalog_sha256"]
            self.reseal_returns(request, entry)
        self.refused(request)

    def test_every_external_identity_pin_refuses_substitution(self):
        request = self.request()
        foreign = digest({"foreign": "independent synthetic artifact"})
        for key in ("expected_history_sha256", "expected_source_catalog_sha256",
                    "expected_configuration_sha256", "expected_profile_sha256", "expected_live_policy_sha256"):
            changed = copy.deepcopy(request)
            changed[key] = foreign
            with self.subTest(pin=key):
                self.refused(changed)
        for field in ("expected_source_returns_sha256", "expected_batch_sha256"):
            changed = copy.deepcopy(request)
            entry = changed["history"]["entries"][0]
            if field == "expected_source_returns_sha256":
                entry[field] = foreign
            else:
                entry["event_batches"][0][field] = foreign
            changed["expected_history_sha256"] = digest(changed["history"])
            self.refused(changed)

    def test_custom_selection_is_closed_explicit_absolute_and_canonical(self):
        original = self.request()
        self.assert_projection(self.project(original), original)
        selected = original["configuration"]["custom_collectors"][0]
        variants = [("missing-" + field, {key: value for key, value in selected.items() if key != field})
                    for field in selected]
        variants.extend([
            ("extra-comment", {**selected, "_comment": "compatibility config allows this; closed selection does not"}),
            ("ambient-home-path", {**selected, "path": "~/undeclared-source.log"}),
            ("relative-path", {**selected, "path": "undeclared-source.log"}),
            ("noncanonical-name", {**selected, "name": selected["name"].upper()}),
            ("noncanonical-organ", {**selected, "organ": selected["organ"].upper()}),
        ])
        for label, selection in variants:
            request = copy.deepcopy(original)
            request["configuration"]["custom_collectors"][0] = copy.deepcopy(selection)
            request["expected_configuration_sha256"] = digest(request["configuration"])
            request["source_catalog"]["configuration_sha256"] = request["expected_configuration_sha256"]
            request["expected_source_catalog_sha256"] = digest(request["source_catalog"])
            for entry in request["history"]["entries"]:
                entry["source_returns"]["configuration_sha256"] = request["expected_configuration_sha256"]
                entry["source_returns"]["source_catalog_sha256"] = request["expected_source_catalog_sha256"]
                self.reseal_returns(request, entry)
            with self.subTest(selection=label):
                self.refused(request)

    def test_configuration_profile_and_full_live_policy_are_immutable_across_history(self):
        first = self.entry({"sense_custom:alpha": [self.event()]})
        self.publish_entry_fixture(first)
        later = self.entry({}, stamp=live_tests.DELIVERED_AT, batch_id="empty-later-return")
        request = self.request([first, later])
        foreign = digest({"foreign": "epoch policy"})
        for key in ("configuration_sha256", "source_catalog_sha256", "profile_sha256", "live_policy_sha256"):
            changed = copy.deepcopy(request)
            entry = changed["history"]["entries"][-1]
            entry["source_returns"][key] = foreign
            self.reseal_returns(changed, entry)
            with self.subTest(binding=key):
                self.refused(changed)
        changed = copy.deepcopy(request)
        changed["live_policy"]["novelty_admission"]["comparison"] = "silently-changed-threshold-rule"
        changed["expected_live_policy_sha256"] = digest(changed["live_policy"])
        changed["profile"]["live_policy_sha256"] = changed["expected_live_policy_sha256"]
        changed["expected_profile_sha256"] = digest(changed["profile"])
        for entry in changed["history"]["entries"]:
            entry["source_returns"]["live_policy_sha256"] = changed["expected_live_policy_sha256"]
            entry["source_returns"]["profile_sha256"] = changed["expected_profile_sha256"]
            self.reseal_returns(changed, entry)
        self.refused(changed)

    def test_unsupported_profile_rules_refuse_instead_of_using_an_implicit_counting_policy(self):
        request = self.request()
        for field in ("scope", "symbol", "source_order", "event_order", "association_identity",
                      "repeated_association", "native_timestamp", "current_versions"):
            changed = copy.deepcopy(request)
            changed["profile"][field] = "unsupported-profile-rule"
            changed["expected_profile_sha256"] = digest(changed["profile"])
            for entry in changed["history"]["entries"]:
                entry["source_returns"]["profile_sha256"] = changed["expected_profile_sha256"]
                self.reseal_returns(changed, entry)
            with self.subTest(profile_field=field):
                self.refused(changed)

    def test_missing_or_foreign_event_batches_and_trimmed_duplicate_inputs_refuse(self):
        event = self.event()
        request = self.request([self.entry({"sense_custom:alpha": [event, event]})])
        missing = copy.deepcopy(request)
        missing["history"]["entries"][0]["event_batches"] = []
        missing["expected_history_sha256"] = digest(missing["history"])
        self.refused(missing)
        trimmed = copy.deepcopy(request)
        row = trimmed["history"]["entries"][0]["event_batches"][0]
        plan = row["batch"]["members"][0]
        old_pin = plan["plan_sha256"]
        plan["input_records"].pop()
        plan["plan_sha256"] = page_tests.own(plan)
        for write in row["batch"]["write_order"]:
            if write["plan_sha256"] == old_pin:
                write["plan_sha256"] = plan["plan_sha256"]
        row["batch"]["batch_sha256"] = own(row["batch"], "batch_sha256")
        row["expected_batch_sha256"] = row["batch"]["batch_sha256"]
        trimmed["expected_history_sha256"] = digest(trimmed["history"])
        self.refused(trimmed)
        foreign = self.entry({"sense_custom:alpha": [self.event(occurrence="native:intake:foreign")]}, batch_id="foreign")
        swapped = copy.deepcopy(request)
        swapped["history"]["entries"][0]["event_batches"] = foreign["event_batches"]
        swapped["expected_history_sha256"] = digest(swapped["history"])
        self.refused(swapped)

    def test_rehashed_wrong_admission_or_source_record_identity_cannot_join_a_page(self):
        request = self.request()
        changed = copy.deepcopy(request)
        entry = changed["history"]["entries"][0]
        record = entry["source_returns"]["runs"][0]["events"][0]
        record["semantic_id"] = digest({"foreign": "semantic identity"})
        self.reseal_returns(changed, entry)
        self.refused(changed)
        changed = copy.deepcopy(request)
        row = changed["history"]["entries"][0]["event_batches"][0]
        plan = row["batch"]["members"][0]
        old_pin = plan["plan_sha256"]
        plan["admissions"][0]["version_sha256"] = digest({"foreign": "page version"})
        plan["plan_sha256"] = page_tests.own(plan)
        for write in row["batch"]["write_order"]:
            if write["plan_sha256"] == old_pin:
                write["plan_sha256"] = plan["plan_sha256"]
        row["batch"]["batch_sha256"] = own(row["batch"], "batch_sha256")
        row["expected_batch_sha256"] = row["batch"]["batch_sha256"]
        changed["expected_history_sha256"] = digest(changed["history"])
        self.refused(changed)

    def test_unexplained_intervening_page_change_does_not_become_a_source_observation(self):
        first = self.entry({"sense_custom:alpha": [self.event()]})
        self.publish_entry_fixture(first)
        source = Path(self.lib.corpus_path(self.fixture.slug))
        raw = source.read_bytes()
        source.write_bytes(raw + b"\nUnobserved external page edit.\n")
        later = self.entry({"sense_custom:alpha": [self.event("2026-01-07")]},
                           stamp=live_tests.DELIVERED_AT, batch_id="later-unexplained-version")
        self.refused(self.request([first, later]))

    def test_original_controller_clock_and_unique_batch_positions_are_required(self):
        request = self.request()
        changed = copy.deepcopy(request)
        changed["observed_at"] = live_tests.DELIVERED_AT
        self.refused(changed)
        changed = copy.deepcopy(request)
        entry = changed["history"]["entries"][0]
        entry["source_returns"]["observed_at"] = entry["source_returns"]["runs"][0]["events"][0]["ts"]
        self.reseal_returns(changed, entry)
        self.refused(changed)
        changed = copy.deepcopy(request)
        changed["history"]["entries"].append(copy.deepcopy(changed["history"]["entries"][0]))
        changed["expected_history_sha256"] = digest(changed["history"])
        self.refused(changed)
        changed = copy.deepcopy(request)
        changed["history"]["started_at"] = live_tests.DELIVERED_AT
        changed["expected_history_sha256"] = digest(changed["history"])
        self.refused(changed)

    def test_legacy_replay_marker_is_not_a_complete_collector_return_record(self):
        request = self.request()
        legacy = {"v": 1, "sources": ["sense_custom:alpha"],
                  "events": request["history"]["entries"][0]["source_returns"]["runs"][0]["events"]}
        request["history"]["entries"][0]["source_returns"] = legacy
        request["history"]["entries"][0]["expected_source_returns_sha256"] = digest(legacy)
        request["expected_history_sha256"] = digest(request["history"])
        self.refused(request)

    def test_ambient_config_and_source_presence_are_not_read_as_selection_authority(self):
        request = self.request()
        with mock.patch.object(self.lib, "CONFIG", {"malformed": "ambient configuration"}), \
                mock.patch.object(self.lib, "CONFIG_ERRORS", [{"error": "ambient error"}]), \
                mock.patch.object(self.lib, "SENSES", []):
            projected = self.project(request)
        self.assert_projection(projected, request)
        for entry in self.configuration["custom_collectors"]:
            self.assertFalse(Path(entry["path"]).exists())
        self.assertIn(SOURCE_NON_CLAIMS[0], projected["non_claims"])

    def test_capture_hash_is_not_substituted_for_original_page_byte_identity(self):
        request = self.request()
        projected = self.project(request)
        self.assert_projection(projected, request)
        source_pin = request["history"]["entries"][0]["expected_source_returns_sha256"]
        for page in projected["intake"]["pages"]:
            self.assertEqual(page["source_sha256"], bytes_digest(page["content"].encode("utf-8")))
            self.assertEqual(page["content_sha256"], page["source_sha256"])
            self.assertNotEqual(page["source_sha256"], source_pin)
        self.assertNotIn("gist_inputs", projected)
        self.assertNotIn("history_capture", projected)

    def test_real_history_admission_refuses_omitted_or_rehashed_fabricated_typed_uses(self):
        request = self.request()
        projected = self.project(request)
        transition = self.live_transition(projected, request)
        original = transition["history_capture"]
        changed = copy.deepcopy(original)
        changed["intake"]["observations"].pop()
        changed["capture_sha256"] = own(changed, "capture_sha256")
        # The independent old pin always refuses changed complete history.
        with self.assertRaises(self.live.LiveLoopRefusal):
            self.live.admit_history_capture(changed, expected_capture_sha256=transition["history_capture_sha256"])
        changed = copy.deepcopy(original)
        changed["uses"].append({"unadmitted": "fabricated typed use"})
        changed["capture_sha256"] = own(changed, "capture_sha256")
        with self.assertRaises(self.live.LiveLoopRefusal):
            self.live.admit_history_capture(changed, expected_capture_sha256=changed["capture_sha256"])

    def test_projection_detaches_inputs_and_has_no_hidden_retry_counter(self):
        request = self.request()
        original = copy.deepcopy(request)
        projected = self.project(request)
        repeated = self.project(request)
        self.assertEqual(projected, repeated)
        self.assertEqual(request, original)
        projected["intake"]["observations"].clear()
        projected["source_non_claims"]["configuration"].clear()
        self.assertEqual(request, original)
        self.assertEqual(self.project(request), repeated)

    def test_later_real_pin_cannot_adopt_an_original_history_mutation(self):
        request = self.request()
        expected = self.project(request)
        policy_bytes = canonical(request["live_policy"])
        observed = []

        def no_change(raw):
            if raw == policy_bytes:
                observed.append(True)

        with mock.patch.object(self.lib, "hashlib", page_tests.capture_tests._HashShim(no_change)):
            self.assertEqual(self.project(request), expected)
        self.assertTrue(observed, "actual independent policy pin finalization must be exercised")
        changed = []

        def change_history(raw):
            if raw == policy_bytes and not changed:
                request["history"]["entries"][0]["source_returns"]["batch_id"] = "mutated-during-later-pin"
                changed.append(True)

        with mock.patch.object(self.lib, "hashlib", page_tests.capture_tests._HashShim(change_history)):
            self.refused(request)
        self.assertTrue(changed, "mutation did not reach the actual independent pin")

    def test_real_input_copy_cannot_hide_a_changed_original_request(self):
        request = self.request()
        changed = []

        def copied(value, *args, **kwargs):
            result = copy.deepcopy(value, *args, **kwargs)
            if not changed:
                request["history"]["entries"][0]["source_returns"]["batch_id"] = "mutated-after-real-copy"
                changed.append(True)
            return result

        with mock.patch.object(self.lib, "copy", page_tests._ModuleShim(copy, deepcopy=copied)):
            self.refused(request)
        self.assertTrue(changed, "the real copy callback was not reached")

    def test_fully_rehashed_target_requires_native_metadata_and_exact_returned_marker(self):
        original = self.request([self.entry({"sense_custom:alpha": [self.event()]})])
        self.assert_projection(self.project(original), original)
        for mutation in ("missing-marker", "invalid-counts"):
            request = copy.deepcopy(original)
            entry = request["history"]["entries"][0]
            row = entry["event_batches"][0]
            plan = row["batch"]["members"][0]
            page = next(page for page in plan["pages"] if page["write"])
            old_pin, raw = plan["plan_sha256"], self.fixture.raw(page)
            if mutation == "missing-marker":
                record = plan["input_records"][0]
                event = self.lib._event_from_replay_record(record)
                line = self.lib._event_line(event, record["event_id"], record["semantic_id"])[0]
                changed = raw.replace(line.encode("utf-8"), b"- Unbound replacement event.")
            else:
                changed = b"".join(b"sia_counts: []\n" if line.startswith(b"sia_counts:") else line
                                   for line in raw.splitlines(keepends=True))
            self.assertNotEqual(changed, raw, "native target fixture was not actually changed")
            self.fixture.retarget(plan, page, changed)
            for write in row["batch"]["write_order"]:
                if write["plan_sha256"] == old_pin:
                    write["plan_sha256"] = plan["plan_sha256"]
            row["batch"]["batch_sha256"] = own(row["batch"], "batch_sha256")
            row["expected_batch_sha256"] = row["batch"]["batch_sha256"]
            request["expected_history_sha256"] = digest(request["history"])
            with self.subTest(mutation=mutation):
                self.refused(request)

    def test_final_result_copy_cannot_adopt_a_post_digest_projection_change(self):
        request = self.request()
        self.assert_projection(self.project(request), request)
        changed = []

        def copied(value, *args, **kwargs):
            if type(value) is dict and value.get("schema") == "sia-event-live-intake-projection-v1":
                self.assertEqual(value["projection_sha256"], own(value, "projection_sha256"))
                value["non_claims"].clear()
                changed.append(True)
            return copy.deepcopy(value, *args, **kwargs)

        with mock.patch.object(self.lib, "copy", page_tests._ModuleShim(copy, deepcopy=copied)):
            self.refused(request)
        self.assertTrue(changed, "the actual final post-digest result copy was not exercised")

    def test_final_projection_digest_cannot_hide_a_changed_projector_result(self):
        request = self.request([self.entry({"sense_custom:alpha": [self.event()]})])
        expected = self.project(request)
        self.assert_projection(expected, request)
        body_bytes = canonical({key: value for key, value in expected.items() if key != "projection_sha256"})
        projector = self.lib._corpus_page_version_from_bytes
        returned, changed = [], []

        def project_page(**kwargs):
            version = projector(**kwargs)
            returned.append(version)
            return version

        def finalized(raw):
            if raw == body_bytes and not changed:
                self.assertTrue(returned)
                self.assertNotEqual(returned[-1]["origin"], "model")
                returned[-1]["origin"] = "model"
                changed.append(True)

        with mock.patch.object(self.lib, "_corpus_page_version_from_bytes", side_effect=project_page), \
                mock.patch.object(self.lib, "hashlib", page_tests.capture_tests._HashShim(finalized)):
            self.refused(request)
        self.assertTrue(changed, "the actual projection digest boundary was not exercised")

    def test_real_native_generation_integers_remain_exact_outside_live_json_safe_domain(self):
        # This declared float-bearing live policy and the genuine native stat
        # integers inhabit distinct admitted domains in one bounded envelope.
        self.policy["novelty_admission"]["threshold"] = 0.0
        self.profile["live_policy_sha256"] = digest(self.policy)
        self.fixture.fixture._source()
        request = self.request([self.entry({
            "sense_custom:alpha": [self.event("2026-01-07", "native:intake:new")],
        })])
        self.assertIs(type(request["live_policy"]["novelty_admission"]["threshold"]), float)
        original = canonical(request["history"])
        generations = [row["before"]["generation"]
                       for entry in request["history"]["entries"]
                       for item in entry["event_batches"]
                       for row in item["batch"]["read_dependencies"]["files"]
                       if row["before"] is not None]
        self.assertTrue(generations)
        for generation in generations:
            for field in ("mtime_ns", "ctime_ns"):
                self.assertIs(type(generation[field]), int)
        self.assertTrue(any(generation[field] > self.lib.MAX_JSON_SAFE_INTEGER
                            for generation in generations for field in ("mtime_ns", "ctime_ns")),
                        "fixture must exercise actual native stat integers beyond the live JSON-safe domain")
        projected = self.project(request)
        self.assert_projection(projected, request)
        self.assertEqual(canonical(request["history"]), original)
        self.assertEqual(projected["bindings"]["history_sha256"], bytes_digest(original))
        self.live_transition(projected, request)

    def test_complete_input_cap_precedes_copy_decode_hash_or_component_work(self):
        request = self.request()
        # Actual complete constituent sizes define this artificial lower
        # boundary; no production limit is raised or hand-estimated.
        boundary = max(len(canonical(value)) for value in request.values())
        self.assertGreater(len(canonical(request)), boundary)
        forbidden = mock.Mock(side_effect=AssertionError("materialization before complete bridge admission"))
        with mock.patch.object(self.lib, "MAX_STATE_JSON_BYTES", boundary), \
                mock.patch.object(self.lib, "copy", page_tests._ModuleShim(copy, deepcopy=forbidden)), \
                mock.patch.object(self.lib, "hashlib", page_tests._ModuleShim(hashlib, sha256=forbidden)), \
                mock.patch.object(self.lib, "base64", page_tests._ModuleShim(base64, b64encode=forbidden, b64decode=forbidden), create=True), \
                mock.patch.object(self.lib, "_event_from_replay_record", forbidden), \
                mock.patch.object(self.lib, "_corpus_page_version_from_bytes", forbidden), \
                self.assertRaises(REFUSALS):
            self.project(request)
        forbidden.assert_not_called()

    def test_complete_source_roster_cannot_be_clipped_to_encoding_capacity(self):
        request = self.request()
        changed = copy.deepcopy(request)
        changed["live_policy"]["encoding"]["max_symbols"] = len(["one-explicit-symbol-slot"])
        self.assertGreater(len(changed["source_catalog"]["sources"]), changed["live_policy"]["encoding"]["max_symbols"])
        changed["expected_live_policy_sha256"] = digest(changed["live_policy"])
        changed["profile"]["live_policy_sha256"] = changed["expected_live_policy_sha256"]
        changed["expected_profile_sha256"] = digest(changed["profile"])
        for entry in changed["history"]["entries"]:
            entry["source_returns"]["profile_sha256"] = changed["expected_profile_sha256"]
            entry["source_returns"]["live_policy_sha256"] = changed["expected_live_policy_sha256"]
            self.reseal_returns(changed, entry)
        self.refused(changed)

    def test_complete_escaped_output_is_reserved_before_copy_decode_hash_or_events(self):
        old, source, _record = self.fixture.fixture._source()
        raw = source.read_bytes()
        target_size = min(self.lib.MAX_EVENT_PAGE_BYTES, self.policy["limits"]["max_content_bytes"])
        padding = target_size - len(raw) - len(b"\n")
        self.assertGreater(padding, 0)
        retained = raw + b"\n" + b"\x01" * padding
        source.write_bytes(retained)
        request = self.request([self.entry({"sense_custom:alpha": [old]})])
        projected = self.project(request)
        self.assert_projection(projected, request)
        self.assertEqual(projected["intake"]["pages"][0]["content"].encode("utf-8"), retained)
        input_bytes, output_bytes = len(canonical(request)), len(canonical(projected))
        self.assertGreater(output_bytes, input_bytes, "real escaped output must exceed the complete input")
        # The observed complete input fits this artificial lower boundary;
        # the complete escaped output does not. The production cap is unchanged.
        forbidden = mock.Mock(side_effect=AssertionError("materialization before complete output reservation"))
        with mock.patch.object(self.lib, "MAX_STATE_JSON_BYTES", input_bytes), \
                mock.patch.object(self.lib, "copy", page_tests._ModuleShim(copy, deepcopy=forbidden)), \
                mock.patch.object(self.lib, "hashlib", page_tests._ModuleShim(hashlib, sha256=forbidden)), \
                mock.patch.object(self.lib, "base64", page_tests._ModuleShim(base64, b64encode=forbidden, b64decode=forbidden), create=True), \
                mock.patch.object(self.lib, "_event_from_replay_record", forbidden), \
                mock.patch.object(self.lib, "_corpus_page_version_from_bytes", forbidden), \
                self.assertRaises(REFUSALS):
            self.project(request)
        forbidden.assert_not_called()


class EventLiveIntakeArchitecture(unittest.TestCase):
    def test_architecture_names_the_pure_source_return_boundary(self):
        architecture = (Path(__file__).resolve().parents[1] / "docs/ARCHITECTURE.md").read_text()
        for phrase in ("_prepare_event_live_intake", "siaeventintake",
                       "caller-supplied collector returns", "first controller clock",
                       "before and target page versions", "retained-epoch index bytes",
                       "does not acquire a corpus lease"):
            self.assertIn(phrase, architecture)


if __name__ == "__main__":
    unittest.main()
