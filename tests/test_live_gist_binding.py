"""Fresh native capture -> explicitly scoped live gist binding.

The composed native fixture uses the real capture-only frontdoor and registered private keeper; no benchmark questions,
engine, model, machine store or runtime source transaction is exercised.
Binding itself is pure. Full captures and original siagist artifacts survive.

Required observed supported-native witness failures BLOCK. An unsupported
grammar disposition or a complete cue made ineligible by an unobserved
alternative is not the same failure. Unobserved alternatives remain fresh
capture support, never fabricated controller observations or uses.

All clocks and component policies come from the established public fixtures.
No new calculated score, count, timestamp conversion or arithmetic oracle is
introduced. The original siagist result is compared as computed-unverified.
"""

import contextlib
import copy
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_native_history_capture as native_tests
from tests import test_calibration_benchmark as calibration_tests
from tests import test_live_loop as live_tests
from tests import test_replay_gist as gist_tests
from tests import test_event_page_plan as page_tests
from tests import test_event_live_intake as intake_tests


BINDING_NON_CLAIMS = [
    "Episode bindings establish supplied-record correspondence, not collector execution, source authenticity, source freshness, or acknowledgment.",
    "Fresh-capture-only alternatives support attributed gist content but do not create controller observations, encoding events, retrieval events, or uses.",
    "Scoped live proposals do not replace or narrow the complete native capture, replay result, alternative roster, or static control.",
    "The runtime must retain or revalidate fresh source generations through eventual publication; this pure binding does not perform that transaction.",
    "A bound gist proposal is not durable consolidation, publication, delivery, biological consolidation, or a cognitive win.",
]
RULES = {
    "observation_identity": "epoch-source-event-id-v1",
    "native_join": "exact-projected-record-and-signed-occurrence-v1",
    "page_join": "original-observation-and-current-capture-versions-v1",
    "replay": "supported-native-observation-order-once-v1",
    "support": "complete-capture-alternatives-without-synthetic-uses-v1",
    "proposals": "replay-touched-eligible-cues-only-v1",
}
RESULT_KEYS = {
    "schema", "status", "availability", "bindings", "intake", "episode_bindings",
    "gist_inputs", "gist", "episode_dispositions", "support_roster", "proposal_decisions",
    "proposed_candidate_ids", "source_non_claims", "non_claims", "binding_sha256",
}
EPISODE_KEYS = {
    "observation_id", "source_id", "native_occurrence", "disposition", "reason",
    "observation_version_sha256", "current_version_sha256", "original_witness",
    "current_witness", "replay_step_id", "cue_id", "cue_eligible",
}
WITNESS_KEYS = {
    "occurrence", "page_slug", "page_sha256", "event_id", "semantic_id", "excerpt",
    "excerpt_sha256", "start_byte", "end_byte",
}
SUPPORT_KEYS = {
    "occurrence", "cue_id", "completion_id", "origin", "status", "reason", "witness",
    "binding_scope", "observation_ids", "capture_sha256",
}
DECISION_KEYS = {"candidate_id", "cue_id", "selected_by_gist", "disposition", "reason"}
canonical = gist_tests.canonical
digest = gist_tests.sha
occurrence = gist_tests.occurrence


def own(value, field):
    return digest({key: item for key, item in value.items() if key != field})


def association_id(source_id, event_id):
    return digest({"schema": "sia-controller-event-association-v1",
                   "epoch_id": live_tests.EPOCH, "source_id": source_id, "event_id": event_id})


def live_policy():
    value = live_tests.policy_fixture()
    value["schema"] = "sia-live-loop-policy-v2"
    value["idle"] = "bound-native-episodes-replay-gist-fresh-derived-only-v2"
    value["recall_order"] = "origin-slot-preserving-activation-v1"
    return value


class LiveGistBinding(unittest.TestCase):
    def setUp(self):
        try:
            self.component = importlib.import_module("sialivegist")
        except ModuleNotFoundError as exc:
            self.fail("missing pure native/live gist binder: " + str(exc))
        self.assertTrue(callable(getattr(self.component, "bind_replay_gist", None)))
        self.assertTrue(hasattr(self.component, "LiveGistRefusal"))
        self.fixture = native_tests.NativeHistoryCapture(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.lib, self.history = self.fixture.lib, self.fixture.history
        self.live = importlib.import_module("sialiveloop")
        self.gist = importlib.import_module("siagist")
        self.capture = self.fixture._call()
        self.fixture._assert_capture(self.capture)

    def version(self, page):
        return self.lib._corpus_page_version_from_bytes(
            slug=page["slug"], raw=page["text"].encode("utf-8"))

    def request(self, sequences=("1", "2"), *, capture=None):
        captured = self.capture if capture is None else capture
        events = {row["seq"]: row for row in captured["events"] if row["chain"] == "aegis"}
        source_pages = {row["slug"]: row for row in captured["pages"]}
        pages, observations, episodes, steps = [], [], [], []
        for seq, stamp in zip(sequences, live_tests.PERCEPTION_TIMES, strict=False):
            event = events[seq]
            native = self.lib.signed_ledger_event_projection(event["chain"], event["row"])
            record = self.lib._event_replay_record(native)
            page = source_pages[event["retention"]["source_slug"]]
            version = self.version(page)
            if version not in pages:
                pages.append(version)
            source_id = "sense_aegis"
            identity = association_id(source_id, record["event_id"])
            observations.append({"id": identity, "timestamp": stamp,
                                 "version_sha256": version["version_sha256"],
                                 "symbol": source_id, "context": "controller-source-return",
                                 "native_timestamp": record["ts"]})
            episodes.append({"observation_id": identity, "source_id": source_id,
                             "event_record": record, "native_occurrence": occurrence(event)})
            if event["row"][2].partition(":")[0] in ("INTENT", "OUTCOME"):
                steps.append({"id": identity, "occurrence": occurrence(event)})
        self.assertEqual(len(observations), len(sequences), "clock fixture must cover the entire declared roster")
        intake = {"schema": "sia-live-intake-v1", "epoch_id": live_tests.EPOCH,
                  "started_at": live_tests.START, "complete": True, "pages": pages,
                  "current_versions": [page["version_sha256"] for page in pages],
                  "symbols": ["sense_aegis"], "contexts": ["controller-source-return"],
                  "observations": observations}
        policy = live_policy()
        replay = {"schema": "sia-gist-replay-v1", "steps": steps}
        gist_policy = copy.deepcopy(gist_tests.POLICY)
        gist_inputs = {"capture": captured, "expected_capture_sha256": captured["capture_sha256"],
                       "replay": replay, "expected_replay_sha256": digest(replay),
                       "policy": gist_policy, "expected_policy_sha256": digest(gist_policy)}
        bindings = {"schema": "sia-live-episode-bindings-v1", "epoch_id": live_tests.EPOCH,
                    "intake_sha256": digest(intake), "observed_at": live_tests.NOW,
                    "live_policy": policy, "live_policy_sha256": digest(policy),
                    "capture_sha256": captured["capture_sha256"], "rules": dict(RULES),
                    "episodes": episodes, "non_claims": list(BINDING_NON_CLAIMS)}
        return {"intake": intake, "expected_intake_sha256": digest(intake),
                "episode_bindings": bindings, "expected_episode_bindings_sha256": digest(bindings),
                "gist_inputs": gist_inputs, "expected_gist_inputs_sha256": digest(gist_inputs)}

    def custos_request(self):
        """Synthetic legacy Custos rows and true keeper, not signature proof."""
        _state, corpus, registry, _rows, _encoded, _head = \
            calibration_tests._custos_fixture(str(self.fixture.root))
        observed_owner = []
        original_capture = self.fixture.bench._capture_ledger_sources

        def captured_sources(*args, **kwargs):
            self.fixture._assert_owned()
            observed_owner.append(True)
            return original_capture(*args, **kwargs)

        # NativeHistoryCapture already confines all owner/lifecycle paths to
        # this root. Only the active corpus is switched to the genuine
        # separately constructed Custos fixture for its explicit frontdoor.
        with mock.patch.object(self.fixture, "corpus", Path(corpus)), \
                mock.patch.object(self.lib, "CORPUS", corpus), \
                mock.patch.object(self.fixture.bench, "CORPUS", corpus), \
                mock.patch.object(self.fixture.bench, "_capture_ledger_sources",
                                  side_effect=captured_sources):
            captured = self.fixture._call(names=["custos"], registry=registry)
            self.fixture._assert_released()
        self.assertTrue(observed_owner, "the real source capture did not run under its actual owner")
        self.fixture._assert_capture(captured)
        self.assertEqual({row["chain"] for row in captured["chains"]}, {"custos"})
        self.assertEqual(captured["chains"][0]["chain_format"], self.fixture.bench.CUSTOS_CHAIN_FORMAT)

        event = next(row for row in captured["events"]
                     if row["chain"] == "custos" and row["seq"] == "1")
        native = self.lib.signed_ledger_event_projection("custos", event["row"])
        self.assertIsNotNone(native)
        record = self.lib._event_replay_record(native)
        source_page = next(page for page in captured["pages"]
                           if page["slug"] == event["retention"]["source_slug"])
        version = self.version(source_page)
        source_id = "sense_custos"
        identifier = association_id(source_id, record["event_id"])
        observation = {
            "id": identifier, "timestamp": live_tests.PERCEPTION_TIMES[0],
            "version_sha256": version["version_sha256"], "symbol": source_id,
            "context": "controller-source-return", "native_timestamp": record["ts"],
        }
        intake = {
            "schema": "sia-live-intake-v1", "epoch_id": live_tests.EPOCH,
            "started_at": live_tests.START, "complete": True, "pages": [version],
            "current_versions": [version["version_sha256"]], "symbols": [source_id],
            "contexts": ["controller-source-return"], "observations": [observation],
        }
        replay = {"schema": "sia-gist-replay-v1", "steps": []}
        gist_policy = copy.deepcopy(gist_tests.POLICY)
        gist_inputs = {
            "capture": captured, "expected_capture_sha256": captured["capture_sha256"],
            "replay": replay, "expected_replay_sha256": digest(replay),
            "policy": gist_policy, "expected_policy_sha256": digest(gist_policy),
        }
        policy = live_policy()
        episode = {
            "observation_id": identifier, "source_id": source_id,
            "event_record": record, "native_occurrence": occurrence(event),
        }
        bindings = {
            "schema": "sia-live-episode-bindings-v1", "epoch_id": live_tests.EPOCH,
            "intake_sha256": digest(intake), "observed_at": live_tests.NOW,
            "live_policy": policy, "live_policy_sha256": digest(policy),
            "capture_sha256": captured["capture_sha256"], "rules": dict(RULES),
            "episodes": [episode], "non_claims": list(BINDING_NON_CLAIMS),
        }
        return {
            "intake": intake, "expected_intake_sha256": digest(intake),
            "episode_bindings": bindings, "expected_episode_bindings_sha256": digest(bindings),
            "gist_inputs": gist_inputs, "expected_gist_inputs_sha256": digest(gist_inputs),
        }

    def test_known_custos_mapping_retains_complete_source_but_has_no_supported_gist_grammar(self):
        request = self.custos_request()
        original = copy.deepcopy(request)
        result = self.bind(request)
        body = self.assert_result(result, request)
        self.assertEqual(request, original)
        self.assertEqual(result["availability"], "no-eligible-native-episodes")
        self.assertEqual(result["proposed_candidate_ids"], [])
        self.assertEqual(request["gist_inputs"]["replay"]["steps"], [])
        self.assertEqual(body["replay_trace"], [])
        self.assertEqual(body["capture"], request["gist_inputs"]["capture"])
        row = result["episode_dispositions"][0]
        self.assertEqual(row["source_id"], "sense_custos")
        self.assertEqual(row["native_occurrence"],
                         request["episode_bindings"]["episodes"][0]["native_occurrence"])
        self.assertEqual(row["disposition"], "unsupported-native-grammar")
        self.assertEqual(row["reason"], "unsupported-native-chain")
        self.assertIsNone(row["replay_step_id"])
        observed_support = next(support for support in result["support_roster"]
                                if support["occurrence"] == row["native_occurrence"])
        self.assertEqual(observed_support["binding_scope"], "controller-observed-native")
        self.assertEqual(observed_support["observation_ids"], [row["observation_id"]])
        self.assertEqual(observed_support["reason"], "unsupported-native-chain")

    def test_known_custos_cannot_downgrade_missing_or_foreign_native_occurrence_to_unsupported_source(self):
        original = self.custos_request()
        result = self.bind(original)
        self.assert_result(result, original)
        self.assertEqual(result["episode_dispositions"][0]["disposition"], "unsupported-native-grammar")
        foreign_event = next(row for row in original["gist_inputs"]["capture"]["events"]
                             if row["chain"] == "custos" and row["seq"] == "2")
        foreign_chain = copy.deepcopy(original["episode_bindings"]["episodes"][0]["native_occurrence"])
        foreign_chain["chain"] = "aegis"
        for label, reference in (
                ("missing", None),
                ("different-real-custos-record", occurrence(foreign_event)),
                ("wrong-fixed-source-chain", foreign_chain)):
            request = copy.deepcopy(original)
            request["episode_bindings"]["episodes"][0]["native_occurrence"] = reference
            self.reseal(request)
            with self.subTest(occurrence=label):
                self.refuse(request)

    def test_known_custos_checks_whole_normalized_record_before_reporting_unsupported_grammar(self):
        request = self.custos_request()
        self.assert_result(self.bind(request), request)
        episode = request["episode_bindings"]["episodes"][0]
        original = episode["event_record"]
        event = self.lib._event_from_replay_record(original)
        changed = self.lib.Event(
            event.organ, event.ts, event.kind, "Different supplied Custos content.",
            event.links, event.tags, occurrence=event.occurrence)
        replacement = self.lib._event_replay_record(changed)
        self.assertEqual(replacement["event_id"], original["event_id"])
        self.assertNotEqual(replacement["semantic_id"], original["semantic_id"])
        episode["event_record"] = replacement
        self.reseal(request)
        self.refuse(request)

    def reseal(self, request):
        request["expected_intake_sha256"] = digest(request["intake"])
        bindings = request["episode_bindings"]
        bindings["intake_sha256"] = request["expected_intake_sha256"]
        bindings["live_policy_sha256"] = digest(bindings["live_policy"])
        gist_inputs = request["gist_inputs"]
        gist_inputs["expected_capture_sha256"] = gist_inputs["capture"]["capture_sha256"]
        gist_inputs["expected_replay_sha256"] = digest(gist_inputs["replay"])
        gist_inputs["expected_policy_sha256"] = digest(gist_inputs["policy"])
        bindings["capture_sha256"] = gist_inputs["expected_capture_sha256"]
        request["expected_episode_bindings_sha256"] = digest(bindings)
        request["expected_gist_inputs_sha256"] = digest(gist_inputs)

    @contextlib.contextmanager
    def pure_boundary(self):
        with contextlib.ExitStack() as stack:
            for name in ("capture_native_history", "build_ledger_dataset", "_require_usable_bundle", "_engine"):
                stack.enter_context(mock.patch.object(
                    self.fixture.bench, name, side_effect=AssertionError("binding invoked " + name)))
            for name in ("corpus_owner", "_capture_corpus_page_version", "gbrain", "gbrain_call",
                         "brain_sync", "atomic_write", "load_config", "_open_source_nofollow"):
                self.assertTrue(hasattr(self.lib, name), name)
                stack.enter_context(mock.patch.object(
                    self.lib, name, side_effect=AssertionError("binding invoked " + name)))
            stack.enter_context(mock.patch.object(
                gist_tests.ReplayGist, "_fixture", side_effect=AssertionError("legacy QA fixture")))
            yield

    def bind(self, request):
        with self.pure_boundary():
            return self.component.bind_replay_gist(**request)

    def refuse(self, request):
        original = copy.deepcopy(request)
        with self.assertRaises(self.component.LiveGistRefusal) as raised:
            self.bind(request)
        self.assertIs(type(raised.exception.reason), str)
        self.assertTrue(raised.exception.reason)
        self.assertEqual(list(raised.exception.non_claims), list(self.component.NON_CLAIMS))
        self.assertEqual(request, original)
        return raised.exception

    def replace_current(self, request, source_page):
        version = self.version(source_page)
        intake = request["intake"]
        previous = next(page for page in intake["pages"] if page["subject"] == version["subject"]
                        and page["version_sha256"] in intake["current_versions"])
        index = intake["current_versions"].index(previous["version_sha256"])
        if version not in intake["pages"]:
            intake["pages"].append(version)
        intake["current_versions"][index] = version["version_sha256"]
        return version

    def assert_witness(self, witness, page, event):
        self.assertEqual(set(witness), WITNESS_KEYS)
        self.assertEqual(witness["occurrence"], occurrence(event))
        self.assertEqual(witness["page_slug"], page["subject"])
        self.assertEqual(witness["page_sha256"], page["source_sha256"])
        native = self.lib.signed_ledger_event_projection(event["chain"], event["row"])
        record = self.lib._event_replay_record(native)
        line, _payload, _base = self.lib._event_line(native, record["event_id"], record["semantic_id"])
        self.assertEqual(witness["event_id"], record["event_id"])
        self.assertEqual(witness["semantic_id"], record["semantic_id"])
        self.assertEqual(witness["excerpt"], line)
        raw = page["content"].encode("utf-8")
        self.assertEqual(raw[witness["start_byte"]:witness["end_byte"]], line.encode("utf-8"))
        self.assertEqual(witness["excerpt_sha256"], hashlib.sha256(line.encode("utf-8")).hexdigest())

    def assert_result(self, result, request):
        self.assertEqual(set(result), RESULT_KEYS)
        self.assertEqual(result["schema"], "sia-live-replay-gist-binding-v1")
        self.assertEqual(result["status"], "bound-not-published")
        self.assertIn(result["availability"], (
            "proposals-prepared", "no-eligible-native-episodes", "no-accessible-completion"))
        self.assertEqual(result["binding_sha256"], own(result, "binding_sha256"))
        for name in ("intake", "episode_bindings", "gist_inputs"):
            self.assertEqual(result[name], request[name])
        bindings, gist_inputs = request["episode_bindings"], request["gist_inputs"]
        self.assertEqual(result["bindings"], {
            "intake_sha256": request["expected_intake_sha256"],
            "episode_bindings_sha256": request["expected_episode_bindings_sha256"],
            "gist_inputs_sha256": request["expected_gist_inputs_sha256"],
            "capture_sha256": gist_inputs["expected_capture_sha256"],
            "replay_sha256": gist_inputs["expected_replay_sha256"],
            "gist_policy_sha256": gist_inputs["expected_policy_sha256"],
            "live_policy_sha256": bindings["live_policy_sha256"],
            "observed_at": bindings["observed_at"], "epoch_id": bindings["epoch_id"],
        })
        self.assertEqual(result["gist"], self.gist.replay_gist(**gist_inputs))
        body = json.loads(result["gist"]["artifact_json"])
        self.assertEqual(body["capture"], gist_inputs["capture"])
        self.assertEqual(body["status"], "computed-unverified")
        self.assertEqual(result["non_claims"],
                         list(self.live.NON_CLAIMS) + list(self.gist.NON_CLAIMS) + BINDING_NON_CLAIMS)
        self.assertEqual(list(self.component.NON_CLAIMS), result["non_claims"])
        self.assertEqual(result["source_non_claims"], {
            "live_loop": list(self.live.NON_CLAIMS), "replay_gist": list(self.gist.NON_CLAIMS),
            "capture": gist_inputs["capture"]["non_claims"],
            "capture_sources": gist_inputs["capture"]["source_non_claims"],
            "episode_bindings": bindings["non_claims"],
        })
        self.assertEqual([row["observation_id"] for row in result["episode_dispositions"]],
                         [row["id"] for row in request["intake"]["observations"]])
        for row in result["episode_dispositions"]:
            self.assertEqual(set(row), EPISODE_KEYS)
            self.assertIn(row["disposition"], (
                "replay-bound", "unsupported-controller-source", "unsupported-native-grammar"))
        self.assertEqual([row["occurrence"] for row in result["support_roster"]],
                         [occurrence(event) for event in gist_inputs["capture"]["events"]])
        for support, original in zip(result["support_roster"], body["occurrences"], strict=True):
            self.assertEqual(set(support), SUPPORT_KEYS)
            self.assertEqual({key: support[key] for key in original}, original)
            self.assertEqual(support["capture_sha256"], gist_inputs["expected_capture_sha256"])
            matched = [row["observation_id"] for row in bindings["episodes"]
                       if row["native_occurrence"] == support["occurrence"]]
            self.assertEqual(support["observation_ids"], matched)
            self.assertEqual(support["binding_scope"],
                             "controller-observed-native" if matched else "fresh-capture-only")
        self.assertEqual([row["candidate_id"] for row in result["proposal_decisions"]],
                         [row["id"] for row in body["candidates"]])
        selected = {identity for row in body["readout"] for identity in row["selected"]}
        touched = {row["cue_id"] for row in result["episode_dispositions"]
                   if row["disposition"] == "replay-bound" and row["cue_eligible"] is True}
        proposed = []
        for decision, candidate in zip(result["proposal_decisions"], body["candidates"], strict=True):
            self.assertEqual(set(decision), DECISION_KEYS)
            self.assertEqual(decision["cue_id"], candidate["cue_id"])
            self.assertIs(decision["selected_by_gist"], candidate["id"] in selected)
            if candidate["id"] in selected and candidate["cue_id"] in touched:
                self.assertEqual(decision["disposition"], "proposed-live")
                self.assertIsNone(decision["reason"])
                proposed.append(candidate["id"])
            else:
                self.assertEqual(decision["disposition"], "not-proposed-live")
                self.assertIn(decision["reason"], (
                    "not-selected-by-gist", "cue-not-live-replay-touched", "ineligible-cue"))
        self.assertEqual(result["proposed_candidate_ids"], proposed)
        return body

    def test_public_api_requires_complete_keyword_only_inputs_and_independent_pins(self):
        parameters = inspect.signature(self.component.bind_replay_gist).parameters
        self.assertEqual(set(parameters), set(self.request()))
        for parameter in parameters.values():
            self.assertIs(parameter.default, inspect.Parameter.empty)
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_real_capture_only_source_and_unchanged_full_replay_result_are_retained(self):
        request = self.request()
        original = copy.deepcopy(request)
        result = self.bind(request)
        body = self.assert_result(result, request)
        self.assertEqual(request, original)
        self.assertEqual(result["availability"], "proposals-prepared")
        self.assertTrue(result["proposed_candidate_ids"])
        self.assertEqual(body["capture"]["generator"]["schema"], "sia-native-source-capture-v1")
        for row in result["episode_dispositions"]:
            self.assertEqual(row["disposition"], "replay-bound")
            event = next(event for event in self.capture["events"] if occurrence(event) == row["native_occurrence"])
            old = next(page for page in request["intake"]["pages"]
                       if page["version_sha256"] == row["observation_version_sha256"])
            current = next(page for page in request["intake"]["pages"]
                           if page["version_sha256"] == row["current_version_sha256"])
            self.assert_witness(row["original_witness"], old, event)
            self.assert_witness(row["current_witness"], current, event)
            self.assertNotEqual(old["source_sha256"], self.capture["capture_sha256"])

    def test_unobserved_same_cue_alternatives_stay_complete_fresh_capture_support(self):
        request = self.request(("1",))
        result = self.bind(request)
        body = self.assert_result(result, request)
        alternative = next(row for row in result["support_roster"] if row["occurrence"]["seq"] == "2")
        self.assertEqual(alternative["status"], "supported")
        self.assertEqual(alternative["binding_scope"], "fresh-capture-only")
        self.assertEqual(alternative["observation_ids"], [])
        self.assertNotIn(alternative["witness"]["page_slug"],
                         [page["subject"] for page in request["intake"]["pages"]])
        for candidate in body["candidates"]:
            if candidate["id"] in result["proposed_candidate_ids"]:
                bundle = json.loads(candidate["alternative_bundle_json"])
                self.assertIn(alternative["occurrence"],
                              [ref for row in bundle["alternatives"] for ref in row["occurrences"]])
        self.assertEqual(result["intake"]["observations"], request["intake"]["observations"])
        self.assertNotIn("uses", result)

    def test_static_unobserved_cues_are_retained_but_not_live_proposals(self):
        request = self.request(("1",))
        result = self.bind(request)
        body = self.assert_result(result, request)
        touched = {row["cue_id"] for row in result["episode_dispositions"]}
        untouched = [row for row in body["static_readout"] if row["cue_id"] not in touched]
        self.assertTrue(any(row["selected"] for row in untouched))
        self.assertTrue(all(row["disposition"] == "not-proposed-live"
                            for row in result["proposal_decisions"] if row["cue_id"] not in touched))

    def test_unsupported_native_grammar_is_not_missing_capture_or_required_witness(self):
        request = self.request(("5",))
        result = self.bind(request)
        self.assert_result(result, request)
        row = result["episode_dispositions"][0]
        self.assertEqual(row["disposition"], "unsupported-native-grammar")
        self.assertEqual(row["reason"], "unsupported-action-stage")
        self.assertIsNone(row["replay_step_id"])
        self.assertEqual(result["availability"], "no-eligible-native-episodes")
        self.assertEqual(result["proposed_candidate_ids"], [])

    def test_custom_copy_of_native_text_is_not_promoted_to_native_source(self):
        request = self.request(("1",))
        row = request["episode_bindings"]["episodes"][0]
        source_id = "sense_custom:fixture"
        identity = association_id(source_id, row["event_record"]["event_id"])
        row.update(observation_id=identity, source_id=source_id, native_occurrence=None)
        request["intake"]["symbols"] = [source_id]
        request["intake"]["observations"][0].update(id=identity, symbol=source_id)
        request["gist_inputs"]["replay"]["steps"] = []
        self.reseal(request)
        result = self.bind(request)
        self.assert_result(result, request)
        self.assertEqual(result["episode_dispositions"][0]["disposition"], "unsupported-controller-source")
        self.assertEqual(result["availability"], "no-eligible-native-episodes")

    def test_missing_unobserved_alternative_retains_complete_ineligible_cue(self):
        self.fixture.fixture._replace_marker_with_split_decoys("2")
        captured = self.fixture._call()
        request = self.request(("1",), capture=captured)
        result = self.bind(request)
        body = self.assert_result(result, request)
        self.assertEqual(result["episode_dispositions"][0]["disposition"], "replay-bound")
        self.assertIs(result["episode_dispositions"][0]["cue_eligible"], False)
        self.assertEqual(result["availability"], "no-eligible-native-episodes")
        self.assertEqual(result["proposed_candidate_ids"], [])
        self.assertTrue(any(row["status"] == "ineligible-cue" for row in body["replay_trace"]))
        counterpart = next(row for row in result["support_roster"] if row["occurrence"]["seq"] == "2")
        self.assertEqual(counterpart["binding_scope"], "fresh-capture-only")
        self.assertEqual(counterpart["status"], "unavailable")

    def test_complete_eligible_population_with_disabled_learning_is_not_missing_witness(self):
        request = self.request(("1",))
        request["gist_inputs"]["policy"]["learning"]["enabled"] = False
        self.reseal(request)
        result = self.bind(request)
        self.assert_result(result, request)
        self.assertIs(result["episode_dispositions"][0]["cue_eligible"], True)
        self.assertEqual(result["availability"], "no-accessible-completion")
        self.assertEqual(result["proposed_candidate_ids"], [])

    def test_required_observed_native_missing_witness_blocks_instead_of_empty_success(self):
        request = self.request(("1",))
        self.fixture.fixture._replace_marker_with_split_decoys("1")
        captured = self.fixture._call()
        self.history.admit_capture(captured)
        source = next(page for page in captured["pages"] if page["slug"] == request["intake"]["pages"][0]["subject"])
        self.replace_current(request, source)
        request["gist_inputs"]["capture"] = captured
        self.reseal(request)
        # It is a valid native store and a valid raw gist request, not malformed
        # source data being laundered into a desired binding refusal.
        self.assertTrue(self.gist.replay_gist(**request["gist_inputs"])["artifact_json"])
        refused = self.refuse(request)
        self.assertIn("witness", refused.reason)
        self.assertNotIn("unsupported", refused.reason)

    def test_missing_or_refused_capture_never_becomes_no_eligible_history(self):
        for bad in (None, {"status": "refused", "reason": "source-not-admitted"}):
            request = self.request(("5",))
            request["gist_inputs"]["capture"] = bad
            request["expected_gist_inputs_sha256"] = digest(request["gist_inputs"])
            with self.subTest(capture=bad):
                self.refuse(request)

    def test_every_input_pin_and_rehashed_required_occurrence_identity_is_checked(self):
        for field in ("expected_intake_sha256", "expected_episode_bindings_sha256", "expected_gist_inputs_sha256"):
            request = self.request()
            request[field] = "0" * 64
            with self.subTest(pin=field):
                self.refuse(request)
        for field, replacement in (("entry_hash", "0" * 64), ("seq", "missing-native-sequence"),
                                   ("chain", "sekhmet")):
            request = self.request(("1",))
            request["episode_bindings"]["episodes"][0]["native_occurrence"][field] = replacement
            self.reseal(request)
            with self.subTest(occurrence=field):
                self.refuse(request)

    def test_omitted_duplicate_reordered_or_relabeled_observation_bindings_refuse(self):
        for change in ("missing", "duplicate", "reordered", "unsupported-relabel"):
            request = self.request()
            rows = request["episode_bindings"]["episodes"]
            if change == "missing":
                rows.pop()
            elif change == "duplicate":
                rows.append(copy.deepcopy(rows[0]))
            elif change == "reordered":
                rows.reverse()
            else:
                rows[0]["native_occurrence"] = None
            self.reseal(request)
            with self.subTest(change=change):
                self.refuse(request)

    def test_replay_cannot_add_unobserved_native_cues_or_duplicate_an_observation(self):
        for change in ("foreign-cue", "duplicate", "omission", "order"):
            request = self.request()
            steps = request["gist_inputs"]["replay"]["steps"]
            if change == "foreign-cue":
                native = next(row for row in self.capture["events"] if row["seq"] == "3")
                steps.append({"id": "unobserved-native-step", "occurrence": occurrence(native)})
            elif change == "duplicate":
                steps.append({**steps[0], "id": "another-exposure-not-in-controller-history"})
            elif change == "omission":
                steps.pop()
            else:
                steps.reverse()
            self.reseal(request)
            self.assertTrue(self.gist.replay_gist(**request["gist_inputs"])["artifact_json"])
            with self.subTest(change=change):
                self.refuse(request)

    def test_rehashed_native_record_and_origin_version_substitutions_refuse(self):
        request = self.request(("1",))
        source = request["episode_bindings"]["episodes"][0]["event_record"]
        event = self.lib._event_from_replay_record(source)
        changed = self.lib.Event(event.organ, event.ts, event.kind, "different declared content",
                                 event.links, event.tags, occurrence=event.occurrence)
        request["episode_bindings"]["episodes"][0]["event_record"] = self.lib._event_replay_record(changed)
        self.reseal(request)
        self.refuse(request)
        request = self.request(("1",))
        page = request["intake"]["pages"][0]
        old = page["version_sha256"]
        self.assertNotEqual(page["origin"], "model")
        page["origin"] = "model"
        page["version_sha256"] = live_tests.version_digest(page)
        request["intake"]["current_versions"] = [page["version_sha256"]]
        request["intake"]["observations"][0]["version_sha256"] = page["version_sha256"]
        self.assertNotEqual(old, page["version_sha256"])
        self.reseal(request)
        self.refuse(request)

    def test_original_and_current_page_versions_can_differ_without_transferring_identity(self):
        request = self.request(("1",))
        old = copy.deepcopy(request["intake"]["pages"][0])
        source = self.fixture.fixture._source()
        source.write_bytes(source.read_bytes() + "\nFresh page tail Ω; original event retained.\n".encode("utf-8"))
        captured = self.fixture._call()
        page = next(page for page in captured["pages"] if page["slug"] == old["subject"])
        current = self.replace_current(request, page)
        request["gist_inputs"]["capture"] = captured
        self.reseal(request)
        result = self.bind(request)
        self.assert_result(result, request)
        row = result["episode_dispositions"][0]
        self.assertNotEqual(old["version_sha256"], current["version_sha256"])
        self.assertEqual(row["observation_version_sha256"], old["version_sha256"])
        self.assertEqual(row["current_version_sha256"], current["version_sha256"])
        event = next(event for event in captured["events"] if event["seq"] == "1")
        self.assert_witness(row["original_witness"], old, event)
        self.assert_witness(row["current_witness"], current, event)
        self.assertEqual(result["intake"]["observations"], request["intake"]["observations"])

    def test_changed_current_bytes_and_original_marker_decoys_refuse_after_rehash(self):
        request = self.request(("1",))
        source = copy.deepcopy(next(page for page in self.capture["pages"]
                                    if page["slug"] == request["intake"]["pages"][0]["subject"]))
        source["text"] += "\nCurrent intake is not the captured generation.\n"
        self.replace_current(request, source)
        self.reseal(request)
        self.refuse(request)
        request = self.request(("1",))
        original = request["intake"]["pages"][0]
        bad_raw = original["content"].replace("<!-- sia-event:", "<!-- not-the-event:").encode("utf-8")
        bad = self.lib._corpus_page_version_from_bytes(slug=original["subject"], raw=bad_raw)
        request["intake"]["pages"].append(bad)
        request["intake"]["observations"][0]["version_sha256"] = bad["version_sha256"]
        self.reseal(request)
        self.refuse(request)

    def test_required_current_version_and_exact_original_observation_metadata_cannot_be_omitted(self):
        for change in ("current-version", "observation-id", "native-timestamp"):
            request = self.request(("1",))
            if change == "current-version":
                request["intake"]["current_versions"] = []
            elif change == "observation-id":
                request["intake"]["observations"][0]["id"] = "rehashed-not-the-source-association"
                request["episode_bindings"]["episodes"][0]["observation_id"] = (
                    request["intake"]["observations"][0]["id"])
                request["gist_inputs"]["replay"]["steps"][0]["id"] = (
                    request["intake"]["observations"][0]["id"])
            else:
                other = next(event for event in self.capture["events"] if event["seq"] == "2")
                request["intake"]["observations"][0]["native_timestamp"] = other["row"][1]
            self.reseal(request)
            with self.subTest(change=change):
                self.refuse(request)

    def test_actual_model_origin_remains_model_in_capture_support_and_gist(self):
        source = self.fixture.fixture._source()
        source.write_bytes(source.read_bytes().replace(b"---\n", b"---\norigin: model\n", 1))
        captured = self.fixture._call()
        request = self.request(("1",), capture=captured)
        result = self.bind(request)
        body = self.assert_result(result, request)
        self.assertEqual(request["intake"]["pages"][0]["origin"], "model")
        self.assertTrue(all(row["focus"]["origin"] == "model" for row in body["candidates"]
                            if row["id"] in result["proposed_candidate_ids"]))
        self.assertEqual(result["support_roster"][1]["origin"], "model")

    def test_closed_contract_wrong_clock_rules_and_missing_nonclaims_refuse(self):
        for change in ("extra", "epoch", "clock-type", "clock-before-observation", "rule", "nonclaims", "policy"):
            request = self.request()
            bindings = request["episode_bindings"]
            if change == "extra":
                bindings["desired_gist"] = "not an input"
            elif change == "epoch":
                bindings["epoch_id"] = "another-controller-epoch"
            elif change == "clock-type":
                bindings["observed_at"] = True
            elif change == "clock-before-observation":
                bindings["observed_at"] = live_tests.START
            elif change == "rule":
                bindings["rules"]["support"] = "drop-unobserved-alternatives"
            elif change == "nonclaims":
                bindings["non_claims"] = []
            else:
                bindings["live_policy"]["schema"] = "sia-live-loop-policy-v1"
            self.reseal(request)
            with self.subTest(change=change):
                self.refuse(request)

    def test_full_repeated_documents_count_before_hash_copy_or_gist_work(self):
        request = self.request()
        # Alias an already identical native occurrence at another VALID JSON
        # position. Its bytes still count there; this is not an extra-field
        # refusal that could bypass the intended complete-byte boundary.
        request["gist_inputs"]["replay"]["steps"][0]["occurrence"] = (
            request["episode_bindings"]["episodes"][0]["native_occurrence"])
        boundary = max(len(canonical(value)) for value in request.values())
        self.assertGreater(len(canonical(request)), boundary)
        forbidden = mock.Mock(side_effect=AssertionError("work before whole repeated-document admission"))
        with mock.patch.object(self.component, "MAX_INPUT_BYTES", boundary), \
                mock.patch.object(self.component, "copy", page_tests._ModuleShim(copy, deepcopy=forbidden)), \
                mock.patch.object(self.component, "hashlib", page_tests._ModuleShim(hashlib, sha256=forbidden)), \
                mock.patch.object(self.gist, "replay_gist", forbidden):
            self.refuse_without_copy(request)
        forbidden.assert_not_called()

    def refuse_without_copy(self, request):
        with self.assertRaises(self.component.LiveGistRefusal):
            self.bind(request)

    def test_complete_output_duplication_is_reserved_before_gist_learning(self):
        request = self.request()
        raw_gist = self.gist.replay_gist(**request["gist_inputs"])
        repeated_documents = {"intake": request["intake"], "episode_bindings": request["episode_bindings"],
                              "gist_inputs": request["gist_inputs"], "gist": raw_gist}
        boundary = max(len(canonical(value)) for value in repeated_documents.values())
        self.assertGreater(len(canonical(repeated_documents)), boundary)
        forbidden = mock.Mock(side_effect=AssertionError("gist before complete repeated-output reservation"))
        with mock.patch.object(self.component, "MAX_OUTPUT_BYTES", boundary), \
                mock.patch.object(self.gist, "replay_gist", forbidden):
            self.refuse(request)
        forbidden.assert_not_called()

    def test_result_is_detached_and_repeated_binding_has_no_hidden_replay_count(self):
        request = self.request()
        original = copy.deepcopy(request)
        result = self.bind(request)
        repeated = self.bind(request)
        self.assertEqual(result, repeated)
        result["gist_inputs"]["capture"]["events"].clear()
        result["episode_bindings"]["non_claims"].clear()
        self.assertEqual(request, original)
        self.assertEqual(self.bind(request), repeated)

    def test_later_real_pin_cannot_adopt_changed_original_intake(self):
        request = self.request()
        expected = self.bind(request)
        pin_bytes = canonical(request["gist_inputs"])
        reached = []

        def unchanged(raw):
            if raw == pin_bytes:
                reached.append(True)

        with mock.patch.object(self.component, "hashlib", page_tests.capture_tests._HashShim(unchanged)):
            self.assertEqual(self.bind(request), expected)
        self.assertTrue(reached, "the complete independent gist-input pin was not exercised")
        changed = []

        def finalized(raw):
            if raw == pin_bytes and not changed:
                request["intake"]["observations"][0]["native_timestamp"] = "changed-during-later-pin"
                changed.append(True)

        with mock.patch.object(self.component, "hashlib", page_tests.capture_tests._HashShim(finalized)):
            self.refuse_without_copy(request)
        self.assertTrue(changed, "the actual later pin callback did not mutate the original input")

    def test_final_result_copy_cannot_adopt_changed_post_digest_binding(self):
        request = self.request()
        self.assert_result(self.bind(request), request)
        changed = []

        def copied(value, *args, **kwargs):
            if type(value) is dict and value.get("schema") == "sia-live-replay-gist-binding-v1":
                self.assertEqual(value["binding_sha256"], own(value, "binding_sha256"))
                value["non_claims"].clear()
                changed.append(True)
            return copy.deepcopy(value, *args, **kwargs)

        with mock.patch.object(self.component, "copy", page_tests._ModuleShim(copy, deepcopy=copied)):
            self.refuse_without_copy(request)
        self.assertTrue(changed, "the actual post-digest binding copy was not exercised")

    def pulse(self, request, *, legacy=False, idle=True, wrapper=None):
        bindings = request["episode_bindings"]
        policy = live_tests.policy_fixture() if legacy else bindings["live_policy"]
        deliveries = {"schema": "sia-live-deliveries-v1", "epoch_id": live_tests.EPOCH,
                      "complete": True, "records": []}
        return self.live.prepare_pulse(
            intake=request["intake"], expected_intake_sha256=request["expected_intake_sha256"],
            deliveries=deliveries, expected_deliveries_sha256=digest(deliveries),
            previous_state=None, expected_previous_state_sha256=None,
            policy=policy, expected_policy_sha256=digest(policy), observed_at=bindings["observed_at"],
            idle=idle, gist_inputs=wrapper)

    def wrapper(self, request):
        return {key: request[key] for key in (
            "episode_bindings", "expected_episode_bindings_sha256", "gist_inputs", "expected_gist_inputs_sha256")}

    def test_old_v1_capture_hash_gate_still_refuses_real_page_wire_hashes(self):
        request = self.request()
        for page in request["intake"]["pages"]:
            self.assertEqual(page["source_sha256"], hashlib.sha256(page["content"].encode("utf-8")).hexdigest())
            self.assertNotEqual(page["source_sha256"], self.capture["capture_sha256"])
        with self.assertRaises(self.live.LiveLoopRefusal):
            self.pulse(request, legacy=True, wrapper=request["gist_inputs"])

    def test_v2_explicit_wrapper_calls_binding_and_preserves_full_idle_receipt(self):
        request = self.request(("1",))
        expected = self.bind(request)
        with mock.patch.object(self.component, "bind_replay_gist", wraps=self.component.bind_replay_gist) as bind:
            result = self.pulse(request, wrapper=self.wrapper(request))
        self.assertEqual(bind.call_args_list, [mock.call(**request)])
        self.assertEqual(result["state"]["idle"], {"requested": True, "binding": expected})
        body = json.loads(expected["gist"]["artifact_json"])
        candidates = {row["id"]: row for row in body["candidates"]}
        self.assertEqual([page["content"] for page in result["gist_pages"]],
                         [candidates[identity]["text"] for identity in expected["proposed_candidate_ids"]])
        self.assertTrue(all(page["origin"] == "derived" for page in result["gist_pages"]))
        self.assertEqual(result["state"]["intake"], request["intake"])
        self.assertEqual(self.live.admit_history_capture(
            result["history_capture"], expected_capture_sha256=result["history_capture_sha256"]),
            result["history_capture"])

    def test_explicit_v2_policy_also_drives_real_nonidle_collector_return_intake(self):
        fixture = intake_tests.EventLiveIntakeProjection(methodName="runTest")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.policy = live_policy()
        fixture.profile["live_policy_sha256"] = digest(fixture.policy)
        request = fixture.request()
        projected = fixture.project(request)
        fixture.assert_projection(projected, request)
        transitioned = fixture.live_transition(projected, request)
        self.assertEqual(transitioned["state"]["intake"], projected["intake"])
        self.assertEqual(transitioned["state"]["policy"], fixture.policy)
        self.assertEqual(transitioned["gist_pages"], [])
        self.assertEqual(self.live.admit_history_capture(
            transitioned["history_capture"], expected_capture_sha256=transitioned["history_capture_sha256"]),
            transitioned["history_capture"])

    def test_v2_missing_wrong_wrapper_or_nonidle_gist_is_not_a_fallback(self):
        request = self.request()
        for wrapper in (None, request["gist_inputs"], {**self.wrapper(request), "ignore_missing": True}):
            with self.subTest(wrapper=wrapper), self.assertRaises(self.live.LiveLoopRefusal):
                self.pulse(request, wrapper=wrapper)
        with self.assertRaises(self.live.LiveLoopRefusal):
            self.pulse(request, idle=False, wrapper=self.wrapper(request))

    def test_v2_refuses_valid_binding_for_a_different_outer_clock_or_policy(self):
        original = self.request(("1",))
        self.assert_result(self.bind(original), original)
        for change in ("clock", "complete-live-policy"):
            foreign = copy.deepcopy(original)
            if change == "clock":
                foreign["episode_bindings"]["observed_at"] = live_tests.DELIVERED_AT
            else:
                # Explicit fixture input already exercised by the event/live
                # bridge; it is not a tuned or derived numerical policy oracle.
                foreign["episode_bindings"]["live_policy"]["novelty_admission"]["threshold"] = 0.0
            self.reseal(foreign)
            self.assert_result(self.bind(foreign), foreign)
            with self.subTest(binding=change), self.assertRaises(self.live.LiveLoopRefusal):
                self.pulse(original, wrapper=self.wrapper(foreign))


class ReplayGistReservation(unittest.TestCase):
    def test_existing_preflight_can_share_its_reservation_without_changing_legacy_return(self):
        gist = importlib.import_module("siagist")
        reserved_preflight = getattr(gist, "_preflight_with_reservation", None)
        self.assertTrue(callable(reserved_preflight), "missing shared gist preflight reservation")
        fixture = native_tests.NativeHistoryCapture(methodName="runTest")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        captured = fixture._call()
        replay = {"schema": "sia-gist-replay-v1", "steps": []}
        policy = copy.deepcopy(gist_tests.POLICY)
        args = (captured, captured["capture_sha256"], replay, digest(replay), policy, digest(policy))
        original = gist._preflight(*args)
        events, pages, groups, reserved = reserved_preflight(*args)
        self.assertEqual((events, pages, groups), original)
        self.assertIs(type(reserved), int)
        artifact = gist.replay_gist(captured, expected_capture_sha256=captured["capture_sha256"],
                                    replay=replay, expected_replay_sha256=digest(replay),
                                    policy=policy, expected_policy_sha256=digest(policy))
        self.assertGreaterEqual(reserved, len(artifact["artifact_json"].encode("utf-8")))


class LiveGistArchitecture(unittest.TestCase):
    def test_architecture_distinguishes_episode_binding_from_runtime_source_authority(self):
        architecture = (Path(__file__).resolve().parents[1] / "docs/ARCHITECTURE.md").read_text()
        for phrase in ("sialivegist", "bind_replay_gist", "fresh-capture-only",
                       "original observation version", "replay-touched eligible cues",
                       "outer pulse clock", "required native witnesses"):
            self.assertIn(phrase, architecture)


if __name__ == "__main__":
    unittest.main()
