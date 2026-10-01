"""Target-blind offline exposure overlays, never rewritten raw engine rows.

Only root schedules these synthetic tests. No real model, DB, resident corpus,
private query, JACKAL evaluation, metric adapter, or tuning procedure is used.
The existing signed fixture and stopped-process doubles supply all evidence.

The observation clock below is a deliberately chosen fixture input, not a
conversion from event maxima. Grid members are declared comparison policies,
not discovered optima. Hard ceilings are read from existing source contracts.
JACKAL previously returned status=exact, parsed=4096+1, exact=4097,
formal=false; NOT formal-bounded: this lane carries no Lean-checked certificate;
The epistemic class above is the STRONGEST claim this result supports;
exact rational arithmetic (not yet checker-covered).
No local score literal or retrieval-metric result is asserted here.
"""

import copy
import importlib
import inspect
import json
import unittest
from unittest import mock

from tests import test_activation_trace as activation_tests
from tests import test_cognitive_measurement as measurement_tests
from tests import test_cognitive_selection as selection_tests


sha = measurement_tests.sha
canonical = measurement_tests.canonical
body_digest = measurement_tests.body_digest
ARMS = ["raw-original", "cue-only", "cue-event-exposure"]
NON_CLAIMS = [
    "computed-unverified is local software computation, not a JACKAL assurance class or a cognitive win.",
    "Signed event times are retained-event-exposure proxies, not measured SIA encoding, presentation, retrieval-attempt, or successful-use times.",
    "The event-exposure arm does not establish an ACT-R implementation, a human-memory mechanism, or a retrieval-probability model.",
    "Only complete retained native occurrences witnessed in each exact returned chunk contribute; inspected pages are not the entire corpus or machine history.",
    "The cue-only ablation controls exact public metadata matching; this roster does not separately identify decay and frequency effects.",
    "Ranking sees public query cues and source-derived candidate exposures, never private answer keys, task classes, target sequences, or eligibility support.",
    "All arms are permutations of the same raw candidates; raw adapter order, score bytes, canonical-row receipts, source origins, and latency observations remain unchanged.",
    "Unavailable exposures preserve raw-order ties; resource overflow refuses the complete roster rather than clipping history or dropping queries.",
    "Observation time and the complete ordered activation grid are externally declared; this component neither chooses an optimum nor evaluates the calibration objective.",
    "Heldout parameter pins declare calibration-only selection chronology but do not independently prove when tuning or result inspection occurred.",
    "No rerank duration was measured, and retained raw latencies do not establish CPU, model, machine, or cognitive comparisons.",
    "No retrieval metrics, significance, statistical power, independent sampling, or public win are established; an independently frozen ordered-measurement adapter is still required.",
    "All retained capture, selection, measurement, baseline, raw-adapter, model, build, and activation nonclaims remain controlling.",
]


def policy_fixture(protocol_sha256, *, selected=None):
    """Freeze a complete grid and an objective without inspecting raw rows."""
    low = {**activation_tests.POLICY, "decay": 0.5}
    high = {**activation_tests.POLICY, "decay": 1.0} if selected is None else selected
    grid = [{"policy": copy.deepcopy(value), "policy_sha256": sha(canonical(value))}
            for value in (low, high)]
    return {
        "schema": "sia-cognitive-event-exposure-policy-v1",
        "exposures": "retained-native-excerpt-in-returned-chunk-v1",
        "cue_parser": "signed-history-exact-clause-v1",
        "timestamp_source": "signed-event-time-utc-v1",
        "observed_at": 2000000000,
        "ablation_roster": list(ARMS),
        "ordering": "cue-presence-activation-raw-rank-v1",
        "unavailable": "preserve-raw-order-v1",
        "overflow": "refuse-complete-run-v1",
        "activation_grid": grid,
        "activation_grid_sha256": sha(canonical(grid)),
        "calibration_objective": {
            "metric_protocol_sha256": protocol_sha256,
            "class": "recency-heavy", "metric": "recall_at_k", "cutoff": 1,
            "tie_break": "activation-grid-order-v1",
        },
        "resources": {
            "max_queries": 64, "max_source_events": 65536, "max_grid_policies": 64,
            "max_input_bytes": 16777216, "max_trace_bytes": 2097152,
            "max_output_bytes": 16777216,
        },
    }


def occurrence(event):
    return {key: event[key] for key in ("chain", "seq", "entry_hash")}


def use_id(event):
    return sha(canonical(["sia-cognitive-event-exposure-use-v1",
                          event["chain"], event["seq"], event["entry_hash"]]))


class CognitiveEventExposure(unittest.TestCase):
    def setUp(self):
        self.fixture = measurement_tests.CognitiveMeasurement(methodName="runTest")
        self.fixture.setUp()
        self.fixture._projected_row = selection_tests.CognitiveSelection._projected_row.__get__(self.fixture)
        self.addCleanup(self.fixture.doCleanups)

    def _module(self):
        try:
            module = importlib.import_module("siacognitiveexposure")
        except ModuleNotFoundError as exc:
            self.fail("pure target-blind event-exposure rerank API must exist: " + str(exc))
        for name in ("rerank_event_exposure", "parse_public_cue"):
            self.assertTrue(callable(getattr(module, name, None)), name)
        self.assertTrue(hasattr(module, "ExposureRefusal"))
        self.assertTrue(callable(getattr(module, "_rank_query", None)))
        return module

    def _inputs(self, *, split="calibration", choices=None, selected=None,
                policy_change=None, omit_freeze_pin=None):
        fixture = self.fixture
        fixture._inputs(split)
        measurement = importlib.import_module("siacognitivemeasure")
        protocol = fixture._protocol(measurement)
        policy = policy_fixture(protocol["protocol_sha256"], selected=selected)
        if policy_change is not None:
            policy_change(policy)
        policy_sha = sha(canonical(policy))
        activation = copy.deepcopy(policy["activation_grid"][-1]["policy"])
        activation_sha = sha(canonical(activation))
        freeze_pins = {
            "event_exposure_policy_sha256": policy_sha,
            "activation_grid_sha256": policy["activation_grid_sha256"],
            "selected_activation_policy_sha256": activation_sha,
        }
        original_freeze = fixture._freeze

        def frozen_before_observation():
            value = original_freeze()
            value["parameters"].update({key: item for key, item in freeze_pins.items()
                                        if key != omit_freeze_pin})
            value["parameters_sha256"] = sha(canonical(value["parameters"]))
            value["freeze_sha256"] = body_digest(value, "freeze_sha256")
            fixture.kw["expected_parameter_freeze_sha256"] = value["freeze_sha256"]
            # The existing fixture adds its retrieval-protocol pin before the
            # synthetic baseline executes, so no result-dependent retrofitting.
            return value

        if choices is None:
            # Unrelated, older exact-cue event, newer exact-cue event: original
            # raw score order is deliberately distinct from both overlays.
            rows = [("events/aegis/2026-01-04", 0),
                    ("events/aegis/2026-01-01", 0),
                    ("events/aegis/2026-01-02", 0)]
            choices = {row["id"]: rows for row in fixture._queries()}
        elif callable(choices):
            choices = choices(fixture)
        with mock.patch.object(fixture, "_freeze", side_effect=frozen_before_observation):
            baseline = fixture._baseline(protocol, choices, latency=True)
        replay = {
            **fixture.pk, "protocol": protocol,
            "expected_protocol_sha256": protocol["protocol_sha256"],
            "baseline": baseline, "expected_baseline_sha256": baseline["artifact_sha256"],
            "expected_parameter_freeze_sha256": fixture.kw["expected_parameter_freeze_sha256"],
        }
        with fixture._pure():
            plan = measurement.prepare_measurement(**replay)
        self.kw = {
            "measurement_plan": plan, "expected_measurement_plan_sha256": plan["plan_sha256"],
            "replay_inputs": replay, "rerank_policy": policy,
            "expected_rerank_policy_sha256": policy_sha,
            "activation_policy": activation, "expected_activation_policy_sha256": activation_sha,
        }

    def _call(self, module, **overrides):
        with self.fixture._pure():
            return module.rerank_event_exposure(**{**self.kw, **overrides})

    def _query(self, result, klass="recency-heavy", subject="wireplumber.service"):
        answer = self.fixture._answers(klass, subject)[0]
        return next(row for row in result["queries"] if row["id"] == answer["id"])

    def _policy_override(self, policy):
        return {"rerank_policy": policy, "expected_rerank_policy_sha256": sha(canonical(policy))}

    def _arms(self, query):
        self.assertEqual([row["name"] for row in query["arms"]], ARMS)
        return {row["name"]: row["order"] for row in query["arms"]}

    def _replayed_baseline(self, baseline):
        """Rebuild all outer pins: failures must come from independent replay."""
        baseline["artifact_sha256"] = body_digest(baseline, "artifact_sha256")
        replay = copy.deepcopy(self.kw["replay_inputs"])
        replay["baseline"] = baseline
        replay["expected_baseline_sha256"] = baseline["artifact_sha256"]
        if baseline["parameter_freeze"] is not None:
            replay["expected_parameter_freeze_sha256"] = baseline["parameter_freeze_sha256"]
        measurement = importlib.import_module("siacognitivemeasure")
        with self.fixture._pure():
            plan = measurement.prepare_measurement(**replay)
        return {"replay_inputs": replay, "measurement_plan": plan,
                "expected_measurement_plan_sha256": plan["plan_sha256"]}

    def test_public_api_requires_every_external_pin_and_no_ambient_clock(self):
        module = self._module()
        parameters = inspect.signature(module.rerank_event_exposure).parameters
        expected = {"measurement_plan", "expected_measurement_plan_sha256", "replay_inputs",
                    "rerank_policy", "expected_rerank_policy_sha256", "activation_policy",
                    "expected_activation_policy_sha256"}
        self.assertEqual(set(parameters), expected)
        for name in expected:
            self.assertIs(parameters[name].default, inspect.Parameter.empty)
            self.assertEqual(parameters[name].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_deterministic_detached_output_replays_sources_and_keeps_complete_measurement(self):
        module = self._module()
        self._inputs()
        before = copy.deepcopy(self.kw)
        result, repeated = self._call(module), self._call(module)
        self.assertEqual(self.kw, before)
        self.assertEqual(result, repeated)
        self.assertIsNot(result, repeated)
        self.assertEqual(result["schema"], "sia-cognitive-event-exposure-v1")
        self.assertEqual(result["status"], "computed-unverified")
        self.assertEqual(result["artifact_sha256"], body_digest(result, "artifact_sha256"))
        self.assertEqual(result["measurement_plan"], self.kw["measurement_plan"])
        self.assertIsNot(result["measurement_plan"], self.kw["measurement_plan"])
        for name in ("measurement_plan", "rerank_policy", "activation_policy"):
            self.assertEqual(result[name + "_sha256"], self.kw["expected_" + name + "_sha256"])
        self.assertEqual(result["activation_grid_sha256"], self.kw["rerank_policy"]["activation_grid_sha256"])
        self.assertEqual(result["rerank_policy"], self.kw["rerank_policy"])
        self.assertEqual(result["activation_policy"], self.kw["activation_policy"])
        self.assertEqual(result["observed_at"], self.kw["rerank_policy"]["observed_at"])
        result["queries"].clear()
        result["measurement_plan"]["queries"].clear()
        self.assertEqual(self.kw, before)

    def test_fixed_ablations_are_bijections_and_never_rewrite_raw_engine_order_or_receipts(self):
        module = self._module()
        self._inputs()
        result = self._call(module)
        source = self.kw["measurement_plan"]["baseline"]["observation"]
        self.assertEqual(result["measurement_plan"]["baseline"]["observation"], source)
        raw_queries = source["query"]["payload"]["results"]
        self.assertEqual([row["id"] for row in result["queries"]], [row["id"] for row in raw_queries])
        for query, raw in zip(result["queries"], raw_queries):
            references = ["row-" + str(rank) for rank, _row in enumerate(raw["rows"], 1)]
            self.assertEqual([row["row_ref"] for row in query["candidates"]], references)
            self.assertEqual([row["raw_row"] for row in query["candidates"]], raw["rows"])
            arms = self._arms(query)
            self.assertEqual(arms["raw-original"], references)
            for order in arms.values():
                self.assertEqual(sorted(order), sorted(references))
                self.assertEqual(len(set(order)), len(order))
            for candidate, row in zip(query["candidates"], raw["rows"]):
                self.assertEqual(candidate["raw_row"]["score_f64le_base64"], row["score_f64le_base64"])
            retained = next(row for row in result["measurement_plan"]["baseline"]["observation"]["query"]["payload"]["results"]
                            if row["id"] == query["id"])
            self.assertEqual(retained["ranked_rows_canonical_base64"], raw["ranked_rows_canonical_base64"])
            self.assertEqual(retained["ranked_rows_sha256"], raw["ranked_rows_sha256"])
            self.assertEqual(retained["latency_ms"], raw["latency_ms"])

    def test_cue_only_control_and_exposure_order_differ_without_first_latest_reversal(self):
        module = self._module()
        self._inputs()
        result = self._call(module)
        expected = {"raw-original": ["row-1", "row-2", "row-3"],
                    "cue-only": ["row-2", "row-3", "row-1"],
                    "cue-event-exposure": ["row-3", "row-2", "row-1"]}
        for klass in ("recency-heavy", "repetition-heavy", "novelty"):
            query = self._query(result, klass)
            self.assertEqual(self._arms(query), expected)
            self.assertEqual(query["cue"], {"chain": "aegis", "action": "OUTCOME:restart",
                                           "raw_subject": "wireplumber.service"})

    def test_rank_worker_receives_only_public_query_and_source_candidate_fields(self):
        module = self._module()
        self._inputs()
        original = module._rank_query
        seen = []

        def target_blind_worker(*, query, candidates, observed_at, activation_policy):
            self.assertEqual(set(query), {"id", "text", "cue"})
            self.assertEqual(set(query["cue"]), {"chain", "action", "raw_subject"})
            forbidden = {"answer_key", "answer", "class", "targets", "target_sequences", "support", "group_id"}

            def inspect_keys(value):
                if type(value) is dict:
                    self.assertFalse(forbidden.intersection(value))
                    for item in value.values():
                        inspect_keys(item)
                elif type(value) is list:
                    for item in value:
                        inspect_keys(item)

            inspect_keys({"query": query, "candidates": candidates, "policy": activation_policy})
            self.assertEqual(observed_at, self.kw["rerank_policy"]["observed_at"])
            seen.append(query["id"])
            return original(query=query, candidates=candidates, observed_at=observed_at,
                            activation_policy=activation_policy)

        with mock.patch.object(module, "_rank_query", side_effect=target_blind_worker), \
                mock.patch.object(module, "parse_public_cue", wraps=module.parse_public_cue) as parser:
            result = self._call(module)
        self.assertEqual(seen, [row["id"] for row in result["queries"]])
        self.assertEqual(parser.call_args_list,
                         [mock.call(row["text"]) for row in self.kw["measurement_plan"]["baseline"]["queries"]])

    def test_canonical_parser_supports_templates_and_preserves_quoted_embedded_syntax(self):
        module = self._module()
        selector = importlib.import_module("siacognitiveselect")
        action = 'CHECK:exact action "trap" in the complete signed fake chain'
        subject = '/tmp/Δ exact action "nested" and raw subject "x" in the complete signed false chain'
        for klass in ("recency-heavy", "repetition-heavy", "novelty"):
            query = selector._question(klass, "aegis", action, subject)
            with self.subTest(klass=klass):
                self.assertEqual(module.parse_public_cue(query),
                                 {"chain": "aegis", "action": action, "raw_subject": subject})
        newer = selector._question("recency-heavy", "aegis", action, subject, event_recency=True)
        self.assertEqual(module.parse_public_cue(newer),
                         {"chain": "aegis", "action": action, "raw_subject": subject})

    def test_parser_refuses_noncanonical_ambiguous_missing_or_extra_clauses_without_fallback(self):
        module = self._module()
        selector = importlib.import_module("siacognitiveselect")
        good = selector._question("novelty", "aegis", "OUTCOME:restart", "wireplumber.service")
        for bad in (None, True, {}, good + good, "prefix " + good, good + " suffix",
                    good.replace('"wireplumber.service"', '"wireplumber\\u002eservice"'),
                    good.replace('"OUTCOME:restart"', '"OUTCOME:restart" '),
                    good.replace('"wireplumber.service"', "null"),
                    good.replace("complete signed aegis chain", "complete signed ../aegis chain"),
                    "What happened most recently?", good.replace("exact action", "approximate action", 1)):
            with self.subTest(bad=bad), self.assertRaises(module.ExposureRefusal):
                module.parse_public_cue(bad)

    def test_exposures_bind_complete_native_occurrences_and_original_origin_not_private_targets(self):
        module = self._module()
        self._inputs()
        result = self._call(module)
        events = self.kw["replay_inputs"]["capture"]["events"]
        pages = {row["slug"]: row for row in self.kw["replay_inputs"]["selection"]["pages"]}
        query = self._query(result)
        for candidate in query["candidates"]:
            raw = candidate["raw_row"]
            page = pages[raw["slug"]]
            expected = [event for event in events if event["retention"]["status"] == "retained"
                        and event["retention"]["source_slug"] == raw["slug"]
                        and event["retention"]["retrieval_excerpt"].encode("utf-8")
                        in raw["chunk_text"].encode("utf-8")]
            self.assertEqual({canonical(row["occurrence"]) for row in candidate["exposures"]},
                             {canonical(occurrence(event)) for event in expected})
            self.assertEqual(candidate["origin"], page["origin"])
            self.assertEqual(candidate["page_text_sha256"], page["text_sha256"])
            self.assertEqual(candidate["chunk_text_sha256"], sha(raw["chunk_text"].encode("utf-8")))
            for exposure in candidate["exposures"]:
                event = next(row for row in expected if occurrence(row) == exposure["occurrence"])
                self.assertEqual(exposure["action"], event["row"][2])
                self.assertEqual(exposure["raw_subject"], event["row"][3])
                self.assertEqual(exposure["native_timestamp"], event["row"][1])
                self.assertEqual(exposure["event_time_utc"], event["projection"]["event_time_utc"])
                self.assertIs(type(exposure["timestamp"]), int)
                self.assertEqual(exposure["excerpt"], event["retention"]["retrieval_excerpt"])
                self.assertEqual(exposure["excerpt_sha256"], sha(exposure["excerpt"].encode("utf-8")))
                self.assertEqual(exposure["origin"], page["origin"])
            matches = [event for event in expected if event["chain"] == query["cue"]["chain"]
                       and event["row"][2] == query["cue"]["action"]
                       and event["row"][3] == query["cue"]["raw_subject"]]
            self.assertEqual({row["id"] for row in candidate["trace"]["uses"]}, {use_id(event) for event in matches})
            self.assertEqual(candidate["trace"]["subject"], candidate["row_ref"])
            self.assertIs(candidate["trace"]["complete"], True)
        # Older contrast is not a recency target, but is still a real exposure.
        target_seqs = self.fixture._answers("recency-heavy")[0]["answer"]["sequences"]
        self.assertTrue(any(exposure["occurrence"]["seq"] not in target_seqs
                            for candidate in query["candidates"] for exposure in candidate["exposures"]
                            if exposure["raw_subject"] == query["cue"]["raw_subject"]))

    def test_trace_receipts_are_actual_activation_results_on_all_matching_uses(self):
        module = self._module()
        self._inputs()
        result = self._call(module)
        activation = importlib.import_module("siaactivation")
        for query in result["queries"]:
            expected = activation.rank_traces([row["trace"] for row in query["candidates"]],
                                             observed_at=self.kw["rerank_policy"]["observed_at"],
                                             policy=self.kw["activation_policy"])
            self.assertEqual(query["activation"], expected)
            self.assertEqual(query["activation"]["status"], "computed-unverified")
            self.assertEqual(self._arms(query)["cue-event-exposure"], expected["order"])

    def test_every_retained_occurrence_in_shared_chunk_is_kept_once_and_sorted_by_event_time(self):
        module = self._module()
        rows = self.fixture._signed_rows()
        rows[1][1], rows[2][1] = "2026-01-01T02:00:00Z", "2026-01-01T01:00:00Z"
        self.fixture._resign_fixture(rows)
        choices = lambda fixture: {row["id"]: [("events/aegis/2026-01-01", 0)] for row in fixture._queries()}
        self._inputs(choices=choices)
        capture = self.kw["replay_inputs"]["capture"]
        events = [row for row in capture["events"] if row["seq"] in ("1", "2")]
        self.assertEqual([row["retention"]["status"] for row in events], ["retained", "retained"])
        query = self._query(self._call(module), "repetition-heavy")
        candidate = query["candidates"][0]
        for event in events:
            self.assertIn(event["retention"]["retrieval_excerpt"], candidate["raw_row"]["chunk_text"])
        self.assertEqual({canonical(row["occurrence"]) for row in candidate["exposures"]},
                         {canonical(occurrence(event)) for event in events})
        self.assertEqual([row["id"] for row in candidate["trace"]["uses"]],
                         [use_id(events[-1]), use_id(events[0])])
        self.assertEqual(len({row["id"] for row in candidate["trace"]["uses"]}), len(events))

    def test_matching_is_exact_action_and_raw_subject_not_basename_or_outcome_value(self):
        module = self._module()
        rows = self.fixture._signed_rows()
        rows[4][3] = "/usr/lib/wireplumber.service"
        rows[5][3] = "wireplumber.service"
        rows[4][4] = rows[1][4]
        self.fixture._resign_fixture(rows)
        choices = lambda fixture: {row["id"]: [("events/aegis/2026-01-04", 0),
                                               ("events/aegis/2026-01-05", 0),
                                               ("events/aegis/2026-01-01", 0)] for row in fixture._queries()}
        self._inputs(choices=choices)
        query = self._query(self._call(module))
        for candidate in query["candidates"][:-1]:
            self.assertTrue(candidate["exposures"])
            self.assertEqual(candidate["trace"]["uses"], [])
        self.assertTrue(query["candidates"][-1]["trace"]["uses"])
        self.assertEqual(self._arms(query)["cue-only"], ["row-3", "row-1", "row-2"])

    def test_duplicate_native_text_does_not_duplicate_an_occurrence_or_cross_source_slug(self):
        module = self._module()
        fixture = self.fixture
        native = selection_tests.CognitiveSelection._projected_row(fixture, 1)[4]
        for day in ("2026-01-01", "2026-01-04"):
            path = fixture._source(day)
            path.write_text(path.read_text(encoding="utf-8") + "\n" + native + "\n", encoding="utf-8")
        self._inputs()
        query = self._query(self._call(module))
        own = next(row for row in query["candidates"] if row["raw_row"]["slug"] == "events/aegis/2026-01-01")
        copied = next(row for row in query["candidates"] if row["raw_row"]["slug"] == "events/aegis/2026-01-04")
        self.assertIn(native, copied["raw_row"]["chunk_text"])
        self.assertEqual([row["occurrence"]["seq"] for row in own["exposures"]], ["1"])
        self.assertEqual([row["occurrence"]["seq"] for row in copied["exposures"]], ["4"])
        self.assertEqual(len(own["trace"]["uses"]), 1)
        self.assertEqual(copied["trace"]["uses"], [])

    def test_page_witness_outside_returned_chunk_receives_no_exposure_or_cue_credit(self):
        module = self._module()
        fixture = self.fixture
        native = selection_tests.CognitiveSelection._projected_row(fixture, 1)[4]
        path = fixture._source("2026-01-01")
        text = path.read_text(encoding="utf-8")
        self.assertIn(native, text)
        # Preserve the native line boundary. 2048 is the existing preparer
        # chunk-byte ceiling, not a locally derived marker-position literal.
        path.write_text(text.replace(native, "padding\n" + "p" * 2048 + "\n" + native), encoding="utf-8")
        choices = lambda source: {row["id"]: [("events/aegis/2026-01-01", 0)] for row in source._queries()}
        self._inputs(choices=choices)
        event = next(row for row in self.kw["replay_inputs"]["capture"]["events"] if row["seq"] == "1")
        self.assertEqual(event["retention"]["status"], "retained")
        query = self._query(self._call(module), "novelty")
        candidate = query["candidates"][0]
        self.assertNotIn(native, candidate["raw_row"]["chunk_text"])
        self.assertEqual(candidate["exposures"], [])
        self.assertEqual(candidate["trace"]["uses"], [])
        self.assertEqual(self._arms(query), {name: ["row-1"] for name in ARMS})

    def test_unwitnessed_and_lineage_only_occurrences_remain_declared_without_invented_uses(self):
        module = self._module()
        fixture = self.fixture
        selection_tests.CognitiveSelection._consolidate_sequence_fixture(fixture, 1, retain_exemplar=False)
        selection_tests.CognitiveSelection._replace_marker_with_split_decoys(fixture, 2)
        self._inputs(choices={})
        capture = self.kw["replay_inputs"]["capture"]
        statuses = {row["seq"]: row["retention"]["status"] for row in capture["events"]}
        self.assertEqual(statuses["1"], "lineage-only")
        self.assertEqual(statuses["2"], "no-admitted-witness")
        result = self._call(module)
        self.assertEqual(result["event_population"],
                         [{"occurrence": occurrence(event), "retention_status": event["retention"]["status"]}
                          for event in capture["events"]])
        self.assertTrue(all(query["candidates"] == [] for query in result["queries"]))

    def test_signed_occurrence_never_promotes_a_model_origin_page_to_evidence(self):
        module = self._module()
        path = self.fixture._source("2026-01-01")
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        path.write_text(text.replace("---\n", "---\norigin: model\n", 1), encoding="utf-8")
        self._inputs()
        query = self._query(self._call(module))
        candidate = next(row for row in query["candidates"] if row["raw_row"]["slug"] == "events/aegis/2026-01-01")
        self.assertEqual(candidate["origin"], "model")
        self.assertTrue(candidate["exposures"])
        self.assertTrue(all(row["origin"] == "model" for row in candidate["exposures"]))
        self.assertNotIn("origin", candidate["raw_row"])

    def test_empty_candidate_queries_remain_present_in_all_arms_with_unavailable_classes_unchanged(self):
        module = self._module()
        self._inputs(choices={})
        result = self._call(module)
        self.assertEqual([row["id"] for row in result["queries"]],
                         [row["id"] for row in self.kw["measurement_plan"]["queries"]])
        for query in result["queries"]:
            self.assertEqual(query["candidates"], [])
            self.assertEqual(self._arms(query), {name: [] for name in ARMS})
        self.assertEqual(result["measurement_plan"]["classes"], self.kw["measurement_plan"]["classes"])

    def test_event_population_is_not_the_activation_prefix_and_exclusions_are_explicit(self):
        module = self._module()
        selected = {**activation_tests.POLICY, "max_uses": 1, "max_total_uses": 1}
        choices = lambda fixture: {row["id"]: [("events/aegis/2026-01-05", 0)] for row in fixture._queries()}
        self._inputs(choices=choices, selected=selected)
        result = self._call(module)
        events = self.kw["replay_inputs"]["capture"]["events"]
        self.assertGreater(len(events), selected["max_total_uses"])
        self.assertEqual(result["event_population"],
                         [{"occurrence": occurrence(event), "retention_status": event["retention"]["status"]}
                          for event in events])
        expected = next(event for event in events if event["seq"] == "5")
        self.assertTrue(all(any(row["occurrence"] == occurrence(expected)
                                for row in query["candidates"][0]["exposures"])
                            for query in result["queries"]))

    def test_complete_same_chunk_use_overflow_refuses_without_clipping_or_scoring(self):
        module = self._module()
        rows = self.fixture._signed_rows()
        rows[2][1] = "2026-01-01T02:00:00Z"
        self.fixture._resign_fixture(rows)
        selected = {**activation_tests.POLICY, "max_uses": 1}
        choices = lambda fixture: {row["id"]: [("events/aegis/2026-01-01", 0)] for row in fixture._queries()}
        self._inputs(choices=choices, selected=selected)
        with mock.patch("siaactivation.rank_traces", side_effect=AssertionError("scored incomplete trace")), \
                mock.patch.object(module, "_rank_query", side_effect=AssertionError("entered rank worker before all traces admitted")), \
                self.assertRaises(module.ExposureRefusal):
            self._call(module)

    def test_late_query_aggregate_overflow_refuses_before_any_query_is_scored(self):
        module = self._module()
        selected = {**activation_tests.POLICY, "max_total_uses": 1}

        def choices(fixture):
            queries = fixture._queries()
            mapping = {row["id"]: [("events/aegis/2026-01-01", 0)] for row in queries}
            mapping[queries[-1]["id"]] = [("events/aegis/2026-01-01", 0), ("events/aegis/2026-01-02", 0)]
            return mapping

        self._inputs(choices=choices, selected=selected)
        before = copy.deepcopy(self.kw)
        with mock.patch("siaactivation.rank_traces", side_effect=AssertionError("partial roster was scored")), \
                mock.patch.object(module, "_rank_query", side_effect=AssertionError("ranked before later query admission")), \
                self.assertRaises(module.ExposureRefusal):
            self._call(module)
        self.assertEqual(self.kw, before)

    def test_source_query_trace_input_output_and_grid_caps_refuse_complete_run_before_scoring(self):
        module = self._module()
        self._inputs()
        for field in ("max_source_events", "max_queries", "max_trace_bytes", "max_input_bytes", "max_output_bytes", "max_grid_policies"):
            policy = copy.deepcopy(self.kw["rerank_policy"])
            policy["resources"][field] = 1
            with self.subTest(field=field), \
                    mock.patch("siaactivation.rank_traces", side_effect=AssertionError("scored before resource admission")), \
                    mock.patch.object(module, "_rank_query", side_effect=AssertionError("ranked before resource admission")), \
                    self.assertRaises(module.ExposureRefusal):
                self._call(module, **self._policy_override(policy))

    def test_invalid_structure_in_any_input_refuses_before_copy_serialization_or_activation(self):
        module = self._module()
        self._inputs()
        cycle = {}
        cycle["cycle"] = cycle
        for field, invalid in (("measurement_plan", cycle), ("replay_inputs", {"bad": float("inf")}),
                               ("rerank_policy", {"grid": cycle}), ("activation_policy", {"bad": float("nan")})):
            with self.subTest(field=field), \
                    mock.patch("copy.deepcopy", side_effect=AssertionError("copied unadmitted structure")), \
                    mock.patch("json.dumps", side_effect=AssertionError("serialized unadmitted structure")), \
                    mock.patch("siaactivation.rank_traces", side_effect=AssertionError("scored unadmitted structure")), \
                    self.assertRaises(module.ExposureRefusal):
                self._call(module, **{field: invalid})

    def test_observation_time_is_explicit_strict_and_not_repaired_from_event_maximum(self):
        module = self._module()
        self._inputs()
        for invalid in (None, True, "2000000000", -1, 0, 1.0):
            policy = copy.deepcopy(self.kw["rerank_policy"])
            policy["observed_at"] = invalid
            with self.subTest(invalid=invalid), \
                    mock.patch("siaactivation.rank_traces", side_effect=AssertionError("scored undefined ages")), \
                    self.assertRaises(module.ExposureRefusal):
                self._call(module, **self._policy_override(policy))
        policy = copy.deepcopy(self.kw["rerank_policy"])
        del policy["observed_at"]
        with self.assertRaises(module.ExposureRefusal):
            self._call(module, **self._policy_override(policy))

    def test_grid_is_full_ordered_bound_and_selected_policy_must_be_exact_member(self):
        module = self._module()
        self._inputs()
        for change in ("missing-policy", "foreign-hash", "duplicate", "stale-grid-pin", "boolean-policy"):
            policy = copy.deepcopy(self.kw["rerank_policy"])
            grid = policy["activation_grid"]
            if change == "missing-policy":
                del grid[0]["policy"]
            elif change == "foreign-hash":
                grid[0]["policy_sha256"] = "0" * 64
            elif change == "duplicate":
                grid.append(copy.deepcopy(grid[0]))
            elif change == "stale-grid-pin":
                grid.reverse()
            else:
                grid[0]["policy"]["decay"] = True
                grid[0]["policy_sha256"] = sha(canonical(grid[0]["policy"]))
            if change != "stale-grid-pin":
                policy["activation_grid_sha256"] = sha(canonical(grid))
            with self.subTest(change=change), self.assertRaises(module.ExposureRefusal):
                self._call(module, **self._policy_override(policy))
        foreign = {**self.kw["activation_policy"], "decay": 2}
        with self.assertRaises(module.ExposureRefusal):
            self._call(module, activation_policy=foreign, expected_activation_policy_sha256=sha(canonical(foreign)))

    def test_hard_activation_ceiling_and_no_new_parameter_or_implicit_best_member(self):
        module = self._module()
        self._inputs()
        for field in ("max_uses", "max_total_uses"):
            policy = copy.deepcopy(self.kw["rerank_policy"])
            policy["activation_grid"][0]["policy"][field] = 4097
            member = policy["activation_grid"][0]
            member["policy_sha256"] = sha(canonical(member["policy"]))
            policy["activation_grid_sha256"] = sha(canonical(policy["activation_grid"]))
            with self.subTest(field=field), self.assertRaises(module.ExposureRefusal):
                self._call(module, **self._policy_override(policy))
        result = self._call(module)
        self.assertEqual(result["activation_policy_sha256"], self.kw["expected_activation_policy_sha256"])
        for name in ("best_policy", "chosen_objective_value", "grid_scores", "tuning_results"):
            self.assertNotIn(name, result)

    def test_policy_is_closed_and_cannot_drop_ablation_reverse_novelty_or_change_timestamp_meaning(self):
        module = self._module()
        self._inputs()
        changes = (("schema", "sia-cognitive-retrieval-policy-v1"),
                   ("ablation_roster", ["raw-original", "cue-event-exposure"]),
                   ("ordering", "reverse-for-novelty"), ("timestamp_source", "actual-memory-use"),
                   ("exposures", "answer-sequences-only"), ("overflow", "clip-to-budget"),
                   ("unavailable", "drop-candidate"), ("cosine_weight", 1), ("choose_best", True))
        for field, value in changes:
            policy = copy.deepcopy(self.kw["rerank_policy"])
            policy[field] = value
            with self.subTest(field=field), self.assertRaises(module.ExposureRefusal):
                self._call(module, **self._policy_override(policy))
        for field, value in (("metric_protocol_sha256", "0" * 64), ("class", "associative-multi-hop"),
                             ("metric", "significance"), ("cutoff", True), ("tie_break", "heldout-score")):
            policy = copy.deepcopy(self.kw["rerank_policy"])
            policy["calibration_objective"][field] = value
            with self.subTest(objective=field), self.assertRaises(module.ExposureRefusal):
                self._call(module, **self._policy_override(policy))

    def test_all_external_pins_and_closed_measurement_replay_are_required(self):
        module = self._module()
        self._inputs()
        for field in ("expected_measurement_plan_sha256", "expected_rerank_policy_sha256", "expected_activation_policy_sha256"):
            for invalid in (None, True, "0" * 64):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(module.ExposureRefusal):
                    self._call(module, **{field: invalid})
        for field in ("expected_capture_sha256", "expected_policy_sha256", "expected_selection_sha256",
                      "expected_baseline_contract_sha256", "expected_metric_policy_sha256",
                      "expected_protocol_sha256", "expected_baseline_sha256"):
            replay = copy.deepcopy(self.kw["replay_inputs"])
            replay[field] = "0" * 64
            with self.subTest(replay=field), self.assertRaises(module.ExposureRefusal):
                self._call(module, replay_inputs=replay)
        with self.assertRaises(module.ExposureRefusal):
            self._call(module, replay_inputs={**self.kw["replay_inputs"], "trusted_answers": {}})

    def test_rehashed_plan_answer_source_raw_and_target_changes_cannot_replace_source_replay(self):
        module = self._module()
        self._inputs()
        for change in ("answer", "origin", "raw-chunk", "raw-score-bytes", "target", "query-roster", "request"):
            plan = copy.deepcopy(self.kw["measurement_plan"])
            baseline = plan["baseline"]
            if change == "answer":
                baseline["answer_key"][0]["answer"]["sequences"] = ["0"]
            elif change == "origin":
                origin = baseline["pages"][0]["origin"]
                baseline["pages"][0]["origin"] = "model" if origin != "model" else "evidence"
            elif change == "raw-chunk":
                baseline["observation"]["query"]["payload"]["results"][0]["rows"][0]["chunk_text"] = "invented witness"
            elif change == "raw-score-bytes":
                baseline["observation"]["query"]["payload"]["results"][0]["rows"][0]["score_f64le_base64"] = "AAAAAAAAAAA="
            elif change == "target":
                plan["queries"][0]["targets"] = []
            elif change == "query-roster":
                plan["queries"].pop()
            else:
                plan["jackal_requests"][0]["arguments"]["expression"] = "999"
            plan["plan_sha256"] = body_digest(plan, "plan_sha256")
            with self.subTest(change=change), self.assertRaises(module.ExposureRefusal):
                self._call(module, measurement_plan=plan, expected_measurement_plan_sha256=plan["plan_sha256"])

    def test_rehashed_capture_projection_timestamp_cannot_create_a_new_exposure_history(self):
        module = self._module()
        self._inputs()
        replay = copy.deepcopy(self.kw["replay_inputs"])
        capture = replay["capture"]
        event = next(row for row in capture["events"] if row["projection"] is not None)
        event["projection"]["event_time_utc"] = "2030-01-01T00:00:00Z"
        capture["capture_sha256"] = body_digest(capture, "capture_sha256")
        replay["expected_capture_sha256"] = capture["capture_sha256"]
        with self.assertRaises(module.ExposureRefusal):
            self._call(module, replay_inputs=replay)

    def test_heldout_requires_complete_preexisting_external_policy_grid_member_and_protocol_freeze(self):
        module = self._module()
        self._inputs(split="heldout")
        result = self._call(module)
        freeze = self.kw["measurement_plan"]["baseline"]["parameter_freeze"]
        expected = {"event_exposure_policy_sha256": self.kw["expected_rerank_policy_sha256"],
                    "activation_grid_sha256": self.kw["rerank_policy"]["activation_grid_sha256"],
                    "selected_activation_policy_sha256": self.kw["expected_activation_policy_sha256"],
                    "measurement_protocol_sha256": self.kw["replay_inputs"]["expected_protocol_sha256"]}
        self.assertEqual({key: freeze["parameters"][key] for key in expected}, expected)
        self.assertEqual(result["split"], "heldout")
        self.assertEqual(result["parameter_freeze_sha256"], self.kw["replay_inputs"]["expected_parameter_freeze_sha256"])
        replay = copy.deepcopy(self.kw["replay_inputs"])
        replay["expected_parameter_freeze_sha256"] = "0" * 64
        with self.assertRaises(module.ExposureRefusal):
            self._call(module, replay_inputs=replay)

    def test_foreign_heldout_rerank_grid_or_member_pin_refuses_after_valid_measurement_replay(self):
        module = self._module()
        self._inputs(split="heldout")
        for field in ("event_exposure_policy_sha256", "activation_grid_sha256", "selected_activation_policy_sha256"):
            for value in (None, "0" * 64):
                baseline = copy.deepcopy(self.kw["replay_inputs"]["baseline"])
                freeze = baseline["parameter_freeze"]
                if value is None:
                    del freeze["parameters"][field]
                else:
                    freeze["parameters"][field] = value
                freeze["parameters_sha256"] = sha(canonical(freeze["parameters"]))
                freeze["freeze_sha256"] = body_digest(freeze, "freeze_sha256")
                baseline["parameter_freeze_sha256"] = freeze["freeze_sha256"]
                overrides = self._replayed_baseline(baseline)
                with self.subTest(field=field, value=value), self.assertRaises(module.ExposureRefusal):
                    self._call(module, **overrides)

    def test_nonclaims_no_new_metrics_no_unmeasured_rerank_latency_and_all_raw_latencies_retained(self):
        module = self._module()
        self._inputs()
        result = self._call(module)
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertEqual(result["source_non_claims"], {
            "measurement": self.kw["measurement_plan"]["non_claims"],
            "history": self.kw["measurement_plan"]["source_non_claims"],
            "activation": activation_tests.NON_CLAIMS,
        })
        self.assertEqual(result["measurement_plan"]["baseline"]["observation"],
                         self.kw["measurement_plan"]["baseline"]["observation"])
        for forbidden in ("jackal_requests", "recall", "mrr", "win", "p_value", "statistical_power", "iid",
                          "cpu_comparison", "model_comparison", "rerank_latency_ms", "latency_ms", "speedup"):
            self.assertNotIn(forbidden, result)
            for query in result["queries"]:
                self.assertNotIn(forbidden, query)
                for arm in query["arms"]:
                    self.assertNotIn(forbidden, arm)


if __name__ == "__main__":
    unittest.main()
