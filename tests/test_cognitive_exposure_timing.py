"""RED contract for a NEW timed exposure replay, not retroactive raw timing.

Only root schedules this suite. Synthetic signed-history fixtures and stopped
baseline doubles are reused; neither model nor DB nor private result is read.
Clock doubles are test instruments, never the production observation route.

JACKAL before writing, status=exact, formal=false:
parsed=130-100 exact=30;
parsed=(130-100+250-200)/2 exact=40;
parsed=2^53-1 exact=9007199254740991;
parsed=2^53-1+1 exact=9007199254740992.
Ordering lapse retained: the initial draft contained (100-100) before its
separate route and (250-200) after routing only its enclosing mean. Subsequent
calls returned status=exact, formal=false, parsed=100-100 exact=0 and
parsed=250-200 exact=50. These subsequent calls do not erase the ordering lapse.
Nonclaims: NOT formal-bounded: this lane carries no Lean-checked certificate;
The epistemic class above is the STRONGEST claim this result supports;
exact rational arithmetic (not yet checker-covered).
These fixtures do not establish clock accuracy or implementation correctness.
Other resource literals are observed existing declared source/test ceilings.
"""

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

import contextlib
import copy
import importlib
import inspect
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

try:
    import cognitive_host
except ModuleNotFoundError:
    from tests import cognitive_host  # type: ignore
from unittest import mock

from tests import test_cognitive_event_exposure as exposure_tests
from tests import test_cognitive_measurement as measurement_tests


sha = measurement_tests.sha
canonical = measurement_tests.canonical
body_digest = measurement_tests.body_digest
ARMS = exposure_tests.ARMS
BIN = Path(__file__).resolve().parents[1] / "bin"
NON_CLAIMS = [
    "This is a new local timed replay after a mandatory complete untimed exposure replay, not timing of the retained earlier exposure or raw retrieval execution.",
    "Integer perf_counter_ns endpoints are supplied local clock observations; neither artifact hashes nor eventual exact arithmetic establish physical-clock accuracy or historical execution truth.",
    "Per-arm spans cover the shared target-blind worker call through return; they exclude source admission, exposure construction, mandatory replay, final fidelity checking, and metric preparation.",
    "The raw-original span measures identity-order construction, not embedding, vector search, or raw retrieval latency.",
    "No additional warmup is performed; mandatory replay and prior process activity leave cache state uncontrolled, and no cold-start claim is established.",
    "Fixed sequential query-major arm order is retained without sample dropping, retries, or outlier filtering; it does not establish independent sampling, comparative speed, or statistical power.",
    "Source and running-interpreter byte/generation checks do not attest the loaded Python heap, complete system runtime, kernel, or protection against hostile same-user mutation.",
    "Raw adapter timing observations remain unchanged and separate; no per-query total, pipeline total, or composed raw-plus-rerank duration is measured by this worker-scope receipt.",
    "Heldout policy and producer pins declare prior freezing but do not independently prove tuning or inspection chronology.",
    "Complete exposure, activation, source, raw measurement, baseline, model, build, and protocol nonclaims remain controlling; no cognitive win is established.",
]
PLAN_NON_CLAIMS = [
    "This plan contains unevaluated JACKAL differences and class means over admitted integer clock endpoints, not arithmetic assurance or physical-clock accuracy.",
    "Receipt replay checks represented consistency against independent inputs and pins; it does not rerun a clock, authenticate historical execution, or reopen current producer sources.",
    "Per-arm worker durations remain separate from all original raw timing scopes; no speedup, cold-start, total-runtime, significance, or cognitive-win claim is established.",
    "All complete timing-observation, exposure, activation, source, raw measurement, baseline, model, build, and protocol nonclaims remain controlling.",
]
PIPELINE_UNAVAILABLE = {"status": "unavailable", "reason": "not-measured-by-worker-scope-v1"}


def policy_fixture(protocol_sha256):
    return {
        "schema": "sia-cognitive-event-exposure-timing-policy-v1",
        "exposure_schema": "sia-cognitive-event-exposure-v1",
        "metric_protocol_sha256": protocol_sha256,
        "arms": list(ARMS),
        "schedule": "query-major-fixed-arm-order-once-v1",
        "clock": "time.perf_counter_ns", "unit": "ns",
        "worker_scope": "admitted-target-blind-arm-call-through-return-v1",
        "pipeline_scope": "not-measured-v1",
        "admission": "complete-before-first-clock-v1",
        "pre_observation": "complete-untimed-exposure-replay-v1",
        "warmup": "no-additional-warmup-cache-state-uncontrolled-v1",
        "aggregation": "macro-query-within-class-v1",
        "numbers": "bounded-json-integer-endpoints-unevaluated-difference-v1",
        "raw_timings": "retain-original-separate-no-total-composition-v1",
        "missing": "refuse-complete-run-v1",
        "chronology": "externally-pinned-before-heldout-v1",
        "resources": {
            "max_input_bytes": 67108864, "max_document_bytes": 16777216,
            "max_output_bytes": 16777216, "max_queries": 64,
            "max_clock_ns": 9007199254740991,
        },
    }


def producer_fixture():
    """Independent caller expectations, never copied from a timing receipt."""
    interpreter = Path(sys.executable).resolve()
    return {
        "schema": "sia-cognitive-exposure-timing-producer-v1",
        "code_expectations": {"schema": "sia-bin-source-inventory-v1", "files": {
            path.name: sha(path.read_bytes()) for path in sorted(BIN.iterdir())
            if not path.name.startswith(".") and path.is_file()
        }},
        "interpreter": {"path": str(interpreter), "sha256": sha(interpreter.read_bytes())},
    }


class CognitiveExposureTiming(unittest.TestCase):
    def setUp(self):
        self.fx = exposure_tests.CognitiveEventExposure(methodName="runTest")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)

    def _module(self):
        try:
            module = importlib.import_module("siacognitiveexposuretiming")
        except ModuleNotFoundError as exc:
            self.fail("observed shared-worker timing and pure receipt admission must exist: " + str(exc))
        for name in ("observe_event_exposure", "prepare_rerank_latency"):
            self.assertTrue(callable(getattr(module, name, None)), name)
        self.assertTrue(hasattr(module, "ExposureTimingRefusal"))
        return module

    def _inputs(self, *, split="calibration", choices=None, freeze_pins="correct"):
        if hasattr(self, "kw"):
            # Each synthetic baseline owns a fresh output directory. Never
            # weaken its no-replace publication rule for a later subtest.
            self.fx.doCleanups()
            self.fx = exposure_tests.CognitiveEventExposure(methodName="runTest")
            self.fx.setUp()
            self.addCleanup(self.fx.doCleanups)
        producer = producer_fixture()
        producer_sha = sha(canonical(producer))
        original = self.fx.fixture._freeze

        def frozen_before_observation():
            value = original()
            measurement = importlib.import_module("siacognitivemeasure")
            protocol = self.fx.fixture._protocol(measurement)
            policy = policy_fixture(protocol["protocol_sha256"])
            if freeze_pins != "missing-policy":
                value["parameters"]["rerank_latency_policy_sha256"] = (
                    "0" * 64 if freeze_pins == "foreign-policy" else sha(canonical(policy)))
            if freeze_pins != "missing-producer":
                value["parameters"]["rerank_timing_producer_sha256"] = (
                    "0" * 64 if freeze_pins == "foreign-producer" else producer_sha)
            value["parameters_sha256"] = sha(canonical(value["parameters"]))
            value["freeze_sha256"] = body_digest(value, "freeze_sha256")
            self.fx.fixture.kw["expected_parameter_freeze_sha256"] = value["freeze_sha256"]
            return value

        with mock.patch.object(self.fx.fixture, "_freeze", side_effect=frozen_before_observation):
            self.fx._inputs(split=split, choices=choices)
        self.exposure = self.fx._call(importlib.import_module("siacognitiveexposure"))
        policy = policy_fixture(self.fx.kw["replay_inputs"]["expected_protocol_sha256"])
        self.kw = {
            "exposure_inputs": copy.deepcopy(self.fx.kw),
            "expected_exposure_sha256": self.exposure["artifact_sha256"],
            "timing_policy": policy, "expected_timing_policy_sha256": sha(canonical(policy)),
            "producer_expectations": producer, "expected_producer_sha256": producer_sha,
        }

    @contextlib.contextmanager
    def _no_execution(self):
        with mock.patch("subprocess.Popen", side_effect=AssertionError("timing observer spawned a process")), \
                mock.patch("siacognitivebaseline.run_baseline", side_effect=AssertionError("timing observer reran baseline")), \
                mock.patch("siavectorrun.observe_bound", side_effect=AssertionError("timing observer ran retrieval")), \
                mock.patch("siavectorrun.prepare_bound", side_effect=AssertionError("timing observer built an index")):
            yield

    def _observe(self, module, *, clock=None, **overrides):
        # Constant readings are valid resolution-limited synthetic observations,
        # not invented zero durations for omitted work. Tests verify every call.
        selected_clock = (lambda: 100) if clock is None else clock
        with mock.patch("time.perf_counter_ns", side_effect=selected_clock):
            return self._invoke(module, **overrides)

    def _invoke(self, module, **overrides):
        with self._no_execution():
            return module.observe_event_exposure(**{**self.kw, **overrides})

    def _prepare(self, module, observation, **overrides):
        with self.fx.fixture._pure(), \
                mock.patch("time.perf_counter_ns", side_effect=AssertionError("pure admission read the clock")):
            return module.prepare_rerank_latency(**{
                **self.kw, "observation": observation,
                "expected_observation_sha256": observation.get("artifact_sha256"), **overrides,
            })

    def _schedule(self):
        return [(query["id"], arm) for query in self.exposure["queries"] for arm in ARMS]

    def _worker_input(self, query, arm):
        return {"arm": arm, "query": {key: query[key] for key in ("id", "text", "cue")},
                "candidates": query["candidates"], "observed_at": self.exposure["observed_at"],
                "activation_policy": self.exposure["activation_policy"]}

    def _worker_output(self, query, arm):
        return {"order": next(row["order"] for row in query["arms"] if row["name"] == arm),
                "activation": query["activation"] if arm == "cue-event-exposure" else None}

    def _policy_override(self, policy):
        return {"timing_policy": policy, "expected_timing_policy_sha256": sha(canonical(policy))}

    def test_closed_keyword_only_observer_and_pure_preparation_apis(self):
        module = self._module()
        common = {"exposure_inputs", "expected_exposure_sha256", "timing_policy",
                  "expected_timing_policy_sha256", "producer_expectations", "expected_producer_sha256"}
        for name, fields in (("observe_event_exposure", common),
                             ("prepare_rerank_latency", common | {"observation", "expected_observation_sha256"})):
            parameters = inspect.signature(getattr(module, name)).parameters
            self.assertEqual(set(parameters), fields)
            for value in parameters.values():
                self.assertEqual(value.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(value.default, inspect.Parameter.empty)

    @cognitive_host.requires_admitted_interpreter
    def test_shared_target_blind_arm_worker_is_used_by_pure_and_timed_paths(self):
        module = self._module()
        self._inputs()
        exposure_module = importlib.import_module("siacognitiveexposure")
        self.assertTrue(callable(getattr(exposure_module, "_rank_arm", None)))
        worker = exposure_module._rank_arm
        trace = []

        def shared(**kwargs):
            self.assertEqual(set(kwargs), {"arm", "query", "candidates", "observed_at", "activation_policy"})
            self.assertEqual(set(kwargs["query"]), {"id", "text", "cue"})
            forbidden = {"answer_key", "answer", "class", "targets", "target_sequences", "support", "group_id"}

            def inspect_fields(value):
                if type(value) is dict:
                    self.assertFalse(forbidden.intersection(value))
                    for child in value.values():
                        inspect_fields(child)
                elif type(value) is list:
                    for child in value:
                        inspect_fields(child)

            inspect_fields(kwargs)
            trace.append(("worker", kwargs["query"]["id"], kwargs["arm"]))
            result = worker(**kwargs)
            self.assertEqual(set(result), {"order", "activation"})
            return result

        def clock():
            trace.append(("clock",))
            return 100

        with mock.patch.object(exposure_module, "_rank_arm", side_effect=shared):
            untimed = self.fx._call(exposure_module)
            self.assertEqual(trace, [("worker", query, arm) for query, arm in self._schedule()])
            trace.clear()
            observed = self._observe(module, clock=clock)
        expected = [("worker", query, arm) for query, arm in self._schedule()]
        for query, arm in self._schedule():
            expected.extend([("clock",), ("worker", query, arm), ("clock",)])
        self.assertEqual(trace, expected)  # Explicit mandatory replay, then timed schedule.
        self.assertEqual(canonical(observed["exposure"]), canonical(untimed))

    @cognitive_host.requires_admitted_interpreter
    def test_observation_binds_complete_schedule_worker_inputs_outputs_and_untimed_bytes(self):
        module = self._module()
        self._inputs()
        before = copy.deepcopy(self.kw)
        result = self._observe(module)
        self.assertEqual(self.kw, before)
        self.assertEqual(result["schema"], "sia-cognitive-event-exposure-timing-observation-v1")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["artifact_sha256"], body_digest(result, "artifact_sha256"))
        self.assertEqual(result["exposure_sha256"], self.kw["expected_exposure_sha256"])
        self.assertEqual(canonical(result["exposure"]), canonical(self.exposure))
        self.assertIsNot(result["exposure"], self.exposure)
        self.assertEqual(result["exposure_inputs_sha256"], sha(canonical(self.kw["exposure_inputs"])))
        self.assertEqual(result["timing_policy"], self.kw["timing_policy"])
        self.assertEqual(result["timing_policy_sha256"], self.kw["expected_timing_policy_sha256"])
        self.assertEqual(result["producer_expectations"], self.kw["producer_expectations"])
        self.assertEqual(result["producer_sha256"], self.kw["expected_producer_sha256"])
        self.assertEqual(result["producer_checks"], "sibling-source-and-running-interpreter-pre-post-generation-v1")
        self.assertEqual(result["pipeline_timing"], PIPELINE_UNAVAILABLE)
        self.assertEqual([(row["query_id"], row["arm"]) for row in result["query_spans"]], self._schedule())
        for query in self.exposure["queries"]:
            for arm in ARMS:
                span = next(row for row in result["query_spans"] if (row["query_id"], row["arm"]) == (query["id"], arm))
                self.assertEqual(set(span), {"query_id", "arm", "start_ns", "end_ns", "input_sha256", "output_sha256"})
                self.assertIs(type(span["start_ns"]), int)
                self.assertIs(type(span["end_ns"]), int)
                self.assertEqual((span["start_ns"], span["end_ns"]), (100, 100))
                self.assertEqual(span["input_sha256"], sha(canonical(self._worker_input(query, arm))))
                self.assertEqual(span["output_sha256"], sha(canonical(self._worker_output(query, arm))))
        result["exposure"]["queries"].clear()
        self.assertEqual(self.kw, before)

    @cognitive_host.requires_admitted_interpreter
    def test_empty_candidates_still_execute_each_arm_and_have_real_clock_readings(self):
        module = self._module()
        self._inputs(choices={})
        result = self._observe(module)
        self.assertEqual([(row["query_id"], row["arm"]) for row in result["query_spans"]], self._schedule())
        self.assertTrue(all(query["candidates"] == [] for query in result["exposure"]["queries"]))
        self.assertTrue(all(arm["order"] == [] for query in result["exposure"]["queries"] for arm in query["arms"]))
        prepared = self._prepare(module, result)
        self.assertEqual(prepared["classes"], self.exposure["measurement_plan"]["classes"])
        self.assertEqual([(row["query_id"], row["arm"]) for row in prepared["query_samples"]], self._schedule())

    def test_invalid_or_changed_inputs_refuse_before_copy_hash_clock_or_worker(self):
        module = self._module()
        self._inputs()
        cyclic = {}
        cyclic["self"] = cyclic
        for name, value in (("exposure_inputs", cyclic), ("timing_policy", {"bad": float("nan")}),
                            ("producer_expectations", {"bad": float("inf")})):
            with self.subTest(name=name), \
                    mock.patch("copy.deepcopy", side_effect=AssertionError("copied before admission")), \
                    mock.patch("json.dumps", side_effect=AssertionError("serialized before admission")), \
                    mock.patch("time.perf_counter_ns", side_effect=AssertionError("clock before admission")), \
                    self.assertRaises(module.ExposureTimingRefusal):
                self._invoke(module, **{name: value})
        changed = copy.deepcopy(self.kw["exposure_inputs"])
        changed["measurement_plan"]["baseline"]["queries"][-1]["text"] = "changed late query"
        with mock.patch("time.perf_counter_ns", side_effect=AssertionError("timed changed inputs")), \
                self.assertRaises(module.ExposureTimingRefusal):
            self._invoke(module, exposure_inputs=changed)

    def test_missing_or_wrong_external_pins_refuse_before_clock(self):
        module = self._module()
        self._inputs()
        for field in ("expected_exposure_sha256", "expected_timing_policy_sha256", "expected_producer_sha256"):
            for wrong in (None, True, "0" * 64):
                with self.subTest(field=field, wrong=wrong), \
                        mock.patch("time.perf_counter_ns", side_effect=AssertionError("timed an unpinned request")), \
                        self.assertRaises(module.ExposureTimingRefusal):
                    self._invoke(module, **{field: wrong})

    def test_complete_source_inventory_and_actual_interpreter_pin_are_required_before_clock(self):
        module = self._module()
        self._inputs()
        for change in ("missing-source", "changed-source", "wrong-interpreter", "symlink-interpreter"):
            producer = copy.deepcopy(self.kw["producer_expectations"])
            if change == "missing-source":
                del producer["code_expectations"]["files"]["siamind.py"]
            elif change == "changed-source":
                producer["code_expectations"]["files"]["siamind.py"] = "0" * 64
            elif change == "wrong-interpreter":
                producer["interpreter"]["sha256"] = "0" * 64
            else:
                link = self.fx.fixture.root / "interpreter-link"
                link.symlink_to(producer["interpreter"]["path"])
                producer["interpreter"]["path"] = str(link)
            with self.subTest(change=change), \
                    mock.patch("time.perf_counter_ns", side_effect=AssertionError("timed stale producer")), \
                    self.assertRaises(module.ExposureTimingRefusal):
                self._invoke(module, producer_expectations=producer,
                             expected_producer_sha256=sha(canonical(producer)))

    @cognitive_host.requires_admitted_interpreter
    def test_source_and_running_interpreter_generations_are_rechecked_after_timed_workers(self):
        module = self._module()
        self._inputs()
        real_fstat = os.fstat
        for target in (str(BIN / "siacognitiveexposuretiming.py"),
                       self.kw["producer_expectations"]["interpreter"]["path"]):
            clock_seen = []
            changed_stats = []

            def clock():
                clock_seen.append(True)
                return 100

            def changed_fstat(fd):
                info = real_fstat(fd)
                try:
                    path = os.readlink("/proc/self/fd/" + str(fd))
                except OSError:
                    return info
                if clock_seen and path == target:
                    self.assertNotEqual(info.st_mtime_ns, 0)
                    fields = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
                    fields["st_mtime_ns"] = 0
                    changed_stats.append(target)
                    return SimpleNamespace(**fields)
                return info

            # No actual production source or interpreter file is modified.
            with self.subTest(target=target), mock.patch("os.fstat", side_effect=changed_fstat), \
                    self.assertRaises(module.ExposureTimingRefusal):
                self._observe(module, clock=clock)
            self.assertTrue(clock_seen)
            self.assertTrue(changed_stats)

    def test_complete_declared_resource_caps_refuse_before_any_clock(self):
        module = self._module()
        self._inputs()
        for field in ("max_input_bytes", "max_document_bytes", "max_output_bytes", "max_queries"):
            policy = copy.deepcopy(self.kw["timing_policy"])
            policy["resources"][field] = 1
            with self.subTest(field=field), \
                    mock.patch("time.perf_counter_ns", side_effect=AssertionError("clock before complete reservation")), \
                    self.assertRaises(module.ExposureTimingRefusal):
                self._invoke(module, **self._policy_override(policy))
        for field in self.kw["timing_policy"]["resources"]:
            for bad in (None, True, 0, -1, 1.0, 9007199254740992):
                policy = copy.deepcopy(self.kw["timing_policy"])
                policy["resources"][field] = bad
                with self.subTest(field=field, bad=bad), \
                        mock.patch("time.perf_counter_ns", side_effect=AssertionError("timed invalid capacity")), \
                        self.assertRaises(module.ExposureTimingRefusal):
                    self._invoke(module, **self._policy_override(policy))

    def test_policy_cannot_hide_replay_relabel_scopes_or_drop_arms(self):
        module = self._module()
        self._inputs()
        for field, value in (("clock", "time.time"), ("unit", "ms"), ("pipeline_scope", "sum-worker-spans"),
                             ("pre_observation", "none"), ("warmup", "cold-start"),
                             ("schedule", "fastest-sample-only"), ("worker_scope", "raw-retrieval"),
                             ("raw_timings", "add-embedding-search-and-worker"), ("arms", ARMS[1:]),
                             ("metric_protocol_sha256", "0" * 64), ("extra", "unbounded-policy")):
            policy = copy.deepcopy(self.kw["timing_policy"])
            policy[field] = value
            with self.subTest(field=field), \
                    mock.patch("time.perf_counter_ns", side_effect=AssertionError("timed another contract")), \
                    self.assertRaises(module.ExposureTimingRefusal):
                self._invoke(module, **self._policy_override(policy))

    def test_clock_domain_reversal_failure_and_cap_refuse_without_success(self):
        module = self._module()
        self._inputs()
        for values in ([130, 100], [True], [-1], [1.0], [float("nan")], [9007199254740992]):
            with self.subTest(values=values), self.assertRaises(module.ExposureTimingRefusal):
                self._observe(module, clock=iter(values).__next__)
        with self.assertRaises(module.ExposureTimingRefusal):
            self._observe(module, clock=mock.Mock(side_effect=RuntimeError("clock unavailable")))

    @cognitive_host.requires_admitted_interpreter
    def test_late_timed_worker_failure_and_wrong_output_never_return_partial_receipt(self):
        module = self._module()
        self._inputs()
        exposure_module = importlib.import_module("siacognitiveexposure")
        worker = exposure_module._rank_arm
        last_query, last_arm = self._schedule()[-1]
        for mode in ("raise", "changed-order"):
            timed = []

            def clock():
                timed.append(True)
                return 100

            def late(**kwargs):
                value = worker(**kwargs)
                if timed and (kwargs["query"]["id"], kwargs["arm"]) == (last_query, last_arm):
                    if mode == "raise":
                        raise ValueError("late worker refused")
                    value = {**value, "order": list(reversed(value["order"]))}
                return value

            with self.subTest(mode=mode), mock.patch.object(exposure_module, "_rank_arm", side_effect=late), \
                    self.assertRaises(module.ExposureTimingRefusal):
                self._observe(module, clock=clock)
            self.assertTrue(timed)

    @cognitive_host.requires_admitted_interpreter
    def test_pure_receipt_preparation_emits_only_endpoint_differences_and_roster_class_means(self):
        module = self._module()
        self._inputs()
        # Equal clock readings are admitted as observed resolution-limited
        # endpoints, with neither omitted work nor a locally evaluated duration.
        observation = self._observe(module)
        plan = self._prepare(module, observation)
        self.assertEqual(plan["schema"], "sia-cognitive-event-exposure-latency-plan-v1")
        self.assertEqual(plan["status"], "prepared-for-jackal")
        self.assertEqual(plan["arithmetic_status"], "not-evaluated")
        self.assertEqual(plan["plan_sha256"], body_digest(plan, "plan_sha256"))
        self.assertEqual(plan["observation_sha256"], observation["artifact_sha256"])
        self.assertEqual(canonical(plan["observation"]), canonical(observation))
        self.assertEqual(plan["classes"], self.exposure["measurement_plan"]["classes"])
        metadata = {row["id"]: row for row in self.exposure["measurement_plan"]["queries"]}
        self.assertEqual([(sample["query_id"], sample["arm"]) for sample in plan["query_samples"]], self._schedule())
        for index, sample in enumerate(plan["query_samples"]):
            span = observation["query_spans"][index]
            self.assertEqual(sample["class"], metadata[sample["query_id"]]["class"])
            self.assertEqual(sample["group_id"], metadata[sample["query_id"]]["group_id"])
            self.assertEqual(sample["expression"], "(100-100)")
            self.assertEqual(sample["unit"], "ns")
            self.assertEqual(sample["given"], {
                "observation_sha256": observation["artifact_sha256"],
                "source_pointer": "/query_spans/" + str(index), "start_ns": span["start_ns"], "end_ns": span["end_ns"],
                "representation": "bounded-json-integer-clock-endpoints-v1", "unit": "ns",
            })
            requests = [row for row in plan["jackal_requests"]
                        if row["scope"] == {"kind": "query", "id": sample["query_id"]}
                        and row["arm"] == sample["arm"]]
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0]["arguments"], {"expression": sample["expression"]})
            self.assertEqual(requests[0]["metric"], "worker_ns")
            self.assertEqual(requests[0]["unit"], "ns")
            self.assertEqual(requests[0]["query_ids"], [sample["query_id"]])
            self.assertEqual(requests[0]["group_ids"], [sample["group_id"]])
            self.assertEqual(requests[0]["given"], [sample])
        for klass in plan["classes"]:
            for arm in ARMS:
                requests = [row for row in plan["jackal_requests"]
                            if row["scope"] == {"kind": "class", "id": klass["class"]} and row["arm"] == arm]
                if not klass["query_ids"]:
                    self.assertEqual(requests, [])
                    continue
                self.assertEqual(len(requests), 1)
                request = requests[0]
                samples = [row for row in plan["query_samples"] if row["class"] == klass["class"] and row["arm"] == arm]
                self.assertEqual(request["query_ids"], klass["query_ids"])
                self.assertEqual(request["group_ids"], klass["group_ids"])
                self.assertEqual(request["given"], samples)
                self.assertEqual(request["arguments"], {"expression": "(" + "+".join(
                    "(" + row["expression"] + ")" for row in samples) + ")/" + str(len(samples))})
                self.assertEqual(request["metric"], "mean_worker_ns")
                self.assertEqual(request["unit"], "ns")
        self.assertTrue(all(row["tool"] == "jackal_exact" for row in plan["jackal_requests"]))
        self.assertTrue(all("result" not in row and "status" not in row for row in plan["jackal_requests"]))

    @cognitive_host.requires_admitted_interpreter
    def test_pure_receipt_shape_and_output_caps_refuse_without_copy_clock_or_io(self):
        module = self._module()
        self._inputs()
        observation = self._observe(module)
        cyclic = {}
        cyclic["self"] = cyclic
        for malformed in (cyclic, {"query_spans": [float("nan")]}, {"query_spans": [object()]}):
            with self.subTest(kind=type(malformed)), \
                    mock.patch("copy.deepcopy", side_effect=AssertionError("copied malformed receipt")), \
                    mock.patch("json.dumps", side_effect=AssertionError("serialized malformed receipt")), \
                    self.assertRaises(module.ExposureTimingRefusal):
                self._prepare(module, malformed, expected_observation_sha256=observation["artifact_sha256"])
        for field in ("max_document_bytes", "max_input_bytes", "max_output_bytes"):
            policy = copy.deepcopy(self.kw["timing_policy"])
            policy["resources"][field] = 1
            changed = copy.deepcopy(observation)
            changed["timing_policy"] = policy
            changed["timing_policy_sha256"] = sha(canonical(policy))
            changed["artifact_sha256"] = body_digest(changed, "artifact_sha256")
            with self.subTest(field=field), \
                    mock.patch("copy.deepcopy", side_effect=AssertionError("copied an impossible complete output")), \
                    self.assertRaises(module.ExposureTimingRefusal):
                self._prepare(module, changed, **self._policy_override(policy))

    @cognitive_host.requires_admitted_interpreter
    def test_actual_distinct_clock_endpoints_are_retained_not_locally_subtracted(self):
        module = self._module()
        self._inputs()
        endpoints = iter([100, 130, 200, 250])

        def clock():
            return next(endpoints, 250)

        observation = self._observe(module, clock=clock)
        self.assertEqual([(row["start_ns"], row["end_ns"]) for row in observation["query_spans"][:2]],
                         [(100, 130), (200, 250)])
        plan = self._prepare(module, observation)
        self.assertEqual([row["expression"] for row in plan["query_samples"][:2]], ["(130-100)", "(250-200)"])
        for sample in plan["query_samples"]:
            for forbidden in ("duration", "elapsed_ns", "elapsed_ms", "result", "exact", "value"):
                self.assertNotIn(forbidden, sample)

    @cognitive_host.requires_admitted_interpreter
    def test_rehashed_receipt_substitution_does_not_replace_independent_replay(self):
        module = self._module()
        self._inputs()
        original = self._observe(module)
        for change in ("missing-span", "duplicate-span", "schedule", "arm", "input-digest", "output-digest",
                       "exposure", "producer", "policy", "pipeline", "extra", "clock", "overlap"):
            observation = copy.deepcopy(original)
            spans = observation["query_spans"]
            if change == "missing-span":
                spans.pop()
            elif change == "duplicate-span":
                spans[-1] = copy.deepcopy(spans[0])
            elif change == "schedule":
                spans.reverse()
            elif change == "arm":
                spans[0]["arm"] = "raw-retrieval"
            elif change == "input-digest":
                spans[0]["input_sha256"] = "0" * 64
            elif change == "output-digest":
                spans[0]["output_sha256"] = "0" * 64
            elif change == "exposure":
                observation["exposure"]["queries"][-1]["arms"][-1]["order"].reverse()
                observation["exposure"]["artifact_sha256"] = body_digest(observation["exposure"], "artifact_sha256")
                observation["exposure_sha256"] = observation["exposure"]["artifact_sha256"]
            elif change == "producer":
                observation["producer_expectations"]["interpreter"]["sha256"] = "0" * 64
                observation["producer_sha256"] = sha(canonical(observation["producer_expectations"]))
            elif change == "policy":
                observation["timing_policy"]["pre_observation"] = "none"
                observation["timing_policy_sha256"] = sha(canonical(observation["timing_policy"]))
            elif change == "pipeline":
                observation["pipeline_timing"] = {"start_ns": 0, "end_ns": 100}
            elif change == "extra":
                spans[0]["omitted_attempt"] = True
            elif change == "clock":
                spans[0]["start_ns"] = True
            else:
                spans[0]["end_ns"] = 130  # Later span still starts at the recorded 100.
            observation["artifact_sha256"] = body_digest(observation, "artifact_sha256")
            with self.subTest(change=change), self.assertRaises(module.ExposureTimingRefusal):
                self._prepare(module, observation)

    @cognitive_host.requires_admitted_interpreter
    def test_external_receipt_pin_is_required_and_not_replaced_by_its_selfhash(self):
        module = self._module()
        self._inputs()
        observation = self._observe(module)
        for wrong in (None, True, "0" * 64):
            with self.subTest(wrong=wrong), self.assertRaises(module.ExposureTimingRefusal):
                self._prepare(module, observation, expected_observation_sha256=wrong)
        altered = copy.deepcopy(observation)
        altered["query_spans"][-1]["end_ns"] = 130
        altered["artifact_sha256"] = body_digest(altered, "artifact_sha256")
        with self.assertRaises(module.ExposureTimingRefusal):
            self._prepare(module, altered, expected_observation_sha256=observation["artifact_sha256"])

    @cognitive_host.requires_admitted_interpreter
    def test_heldout_needs_policy_and_producer_pins_present_before_observation(self):
        module = self._module()
        for mode in ("missing-policy", "foreign-policy", "missing-producer", "foreign-producer"):
            self._inputs(split="heldout", freeze_pins=mode)
            with self.subTest(mode=mode), \
                    mock.patch("time.perf_counter_ns", side_effect=AssertionError("timed unfrozen heldout")), \
                    self.assertRaises(module.ExposureTimingRefusal):
                self._invoke(module)
        self._inputs(split="heldout")
        observation = self._observe(module)
        plan = self._prepare(module, observation)
        self.assertEqual(plan["split"], "heldout")
        self.assertEqual(plan["parameter_freeze_sha256"], self.exposure["parameter_freeze_sha256"])

    @cognitive_host.requires_admitted_interpreter
    def test_all_raw_timings_origins_and_original_nonclaims_remain_unchanged(self):
        module = self._module()
        self._inputs()
        observation = self._observe(module)
        plan = self._prepare(module, observation)
        self.assertEqual(observation["non_claims"], NON_CLAIMS)
        self.assertEqual(plan["non_claims"], PLAN_NON_CLAIMS)
        self.assertEqual(observation["source_non_claims"], {
            "exposure": self.exposure["non_claims"], "exposure_sources": self.exposure["source_non_claims"]})
        self.assertEqual(plan["source_non_claims"], {
            "observation": observation["non_claims"], "observation_sources": observation["source_non_claims"]})
        retained = plan["observation"]["exposure"]
        self.assertEqual(canonical(retained), canonical(self.exposure))
        self.assertEqual(plan["pipeline_timing"], PIPELINE_UNAVAILABLE)
        for container in (observation, plan):
            for forbidden in ("speedup", "win", "mean_latency", "mean_worker_ns", "raw_plus_rerank_ms",
                              "pipeline_total_ns", "cold_start", "best_policy", "p_value", "statistical_power"):
                self.assertNotIn(forbidden, container)


if __name__ == "__main__":
    unittest.main()
