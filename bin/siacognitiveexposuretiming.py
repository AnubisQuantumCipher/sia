"""Observe a new shared-worker replay and prepare conditional timing requests.

The original pure exposure stays byte-identical and retains its own untimed
nonclaims. Before any clock is read, this observer admits every source/policy
and performs the explicitly declared complete untimed exposure replay. It then
measures the same production arm workers, without a second rank implementation
or runtime replacement of the pure path. No engine, model or JACKAL is invoked.

The pure receipt reader replays supplied data but does not read current source
files or clocks. Its external pins are caller authority, not self-authentication.
"""

import contextlib
import copy
import os
import stat
import time

import siacognitiveenvelope as envelope
import siacognitiveexposure as exposure
import siacognitivemeasure as measurement


baseline = measurement.baseline_module
model_files = baseline.siavectormodel
ARMS = exposure.ARMS
MAX_INPUT_BYTES = envelope.MAX_INPUT_BYTES
MAX_DOCUMENT_BYTES = envelope.MAX_DOCUMENT_BYTES
MAX_OUTPUT_BYTES = measurement.MAX_ARTIFACT_BYTES
MAX_QUERIES = exposure.MAX_QUERIES
MAX_CLOCK_NS = baseline.raw_admission.MAX_SAFE_INTEGER
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
_POLICY = {
    "schema": "sia-cognitive-event-exposure-timing-policy-v1",
    "exposure_schema": "sia-cognitive-event-exposure-v1",
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
}
_LIMITS = {
    "max_input_bytes": MAX_INPUT_BYTES, "max_document_bytes": MAX_DOCUMENT_BYTES,
    "max_output_bytes": MAX_OUTPUT_BYTES, "max_queries": MAX_QUERIES,
    "max_clock_ns": MAX_CLOCK_NS,
}
_EXPOSURE_INPUT_LAYOUT = {
    "measurement_plan": None, "expected_measurement_plan_sha256": None,
    "rerank_policy": None, "expected_rerank_policy_sha256": None,
    "activation_policy": None, "expected_activation_policy_sha256": None,
    "replay_inputs": {
        "capture": None, "expected_capture_sha256": None,
        "selection_policy": None, "expected_policy_sha256": None,
        "selection": None, "expected_selection_sha256": None,
        "baseline_contract": None, "expected_baseline_contract_sha256": None,
        "metric_policy": None, "expected_metric_policy_sha256": None,
        "protocol": None, "expected_protocol_sha256": None,
        "baseline": None, "expected_baseline_sha256": None,
        "expected_parameter_freeze_sha256": None,
    },
}
_OBSERVE_LAYOUT = {
    "exposure_inputs": _EXPOSURE_INPUT_LAYOUT, "expected_exposure_sha256": None,
    "timing_policy": None, "expected_timing_policy_sha256": None,
    "producer_expectations": None, "expected_producer_sha256": None,
}
_PREPARE_LAYOUT = {**_OBSERVE_LAYOUT, "observation": None, "expected_observation_sha256": None}
_SOURCE_FIELDS = (
    "capture_sha256", "policy_sha256", "selection_sha256", "pages_sha256",
    "metric_policy_sha256", "baseline_contract_sha256", "protocol_sha256", "baseline_sha256",
    "query_roster_sha256", "split", "parameter_freeze_sha256", "measurement_plan_sha256",
    "rerank_policy_sha256", "activation_grid_sha256", "activation_policy_sha256",
)
_PRODUCER_CHECKS = "sibling-source-and-running-interpreter-pre-post-generation-v1"
_SPAN_KEYS = {"query_id", "arm", "start_ns", "end_ns", "input_sha256", "output_sha256"}
_OBSERVATION_KEYS = {
    "schema", "status", "exposure", "exposure_sha256", "exposure_inputs_sha256",
    "timing_policy", "timing_policy_sha256", "producer_expectations", "producer_sha256",
    "producer_checks", "query_spans", "pipeline_timing", "source_non_claims", "non_claims", "artifact_sha256",
}


class ExposureTimingRefusal(ValueError):
    """The complete new timing observation or its replay could not be admitted."""


def _fail(reason):
    error = ExposureTimingRefusal("cognitive exposure timing refused: " + reason)
    error.non_claims = list(NON_CLAIMS)
    raise error


def _keys(value, fields, label):
    if type(value) is not dict or len(value) != len(fields) or set(value) != set(fields):
        _fail(label + " fields are invalid")


def _hash(value, ceiling=MAX_DOCUMENT_BYTES):
    return measurement._sha(exposure._canonical(value, ceiling))


def _finish(body, field, ceiling):
    baseline._bounded(body, ceiling)
    body[field] = _hash(body, ceiling)
    exposure._json_size(body, ceiling)
    return body


def _producer_declaration(producer):
    _keys(producer, {"schema", "code_expectations", "interpreter"}, "producer")
    if producer["schema"] != "sia-cognitive-exposure-timing-producer-v1":
        _fail("producer schema is unsupported")
    code = producer["code_expectations"]
    _keys(code, {"schema", "files"}, "producer code inventory")
    if code["schema"] != "sia-bin-source-inventory-v1" or type(code["files"]) is not dict \
            or not code["files"] or len(code["files"]) > model_files.MAX_ENTRIES \
            or any(not name or name.startswith(".") or "/" in name or "\\" in name
                   or not measurement._digest(digest) for name, digest in code["files"].items()):
        _fail("producer source inventory is incomplete or malformed")
    interpreter = producer["interpreter"]
    _keys(interpreter, {"path", "sha256"}, "interpreter")
    baseline._path(interpreter["path"])
    if not measurement._digest(interpreter["sha256"]):
        _fail("interpreter byte expectation is invalid")


def _admit(kw, *, preparing=False):
    # ALL domains precede serialization of even an earlier valid document.
    baseline._bounded(kw, MAX_INPUT_BYTES)
    policy = kw["timing_policy"]
    _keys(policy, {*_POLICY, "metric_protocol_sha256", "arms", "resources"}, "timing policy")
    if any(type(policy[key]) is not str or policy[key] != expected for key, expected in _POLICY.items()) \
            or type(policy["arms"]) is not list or policy["arms"] != list(ARMS):
        _fail("timing policy changes a fixed observation or aggregation rule")
    _keys(policy["resources"], _LIMITS, "timing resources")
    for key, maximum in _LIMITS.items():
        value = policy["resources"][key]
        if type(value) is not int or not 0 < value <= maximum:
            _fail("timing capacity is invalid or exceeds its hard ceiling")
    resources = policy["resources"]
    envelope.admit_compound(envelope=kw, layout=_PREPARE_LAYOUT if preparing else _OBSERVE_LAYOUT,
                            max_input_bytes=resources["max_input_bytes"],
                            max_document_bytes=resources["max_document_bytes"])
    _producer_declaration(kw["producer_expectations"])
    for field in ("expected_exposure_sha256", "expected_timing_policy_sha256", "expected_producer_sha256"):
        if not measurement._digest(kw[field]):
            _fail("caller must independently supply every expectation digest")
    measurement._pin(policy, kw["expected_timing_policy_sha256"])
    measurement._pin(kw["producer_expectations"], kw["expected_producer_sha256"])
    if not measurement._digest(policy["metric_protocol_sha256"]) \
            or policy["metric_protocol_sha256"] != kw["exposure_inputs"]["replay_inputs"]["expected_protocol_sha256"]:
        _fail("timing policy differs from the independently pinned retrieval protocol")
    queries = kw["exposure_inputs"]["measurement_plan"]["baseline"]["queries"]
    if type(queries) is not list or not 0 < len(queries) <= resources["max_queries"]:
        _fail("complete query roster exceeds timing capacity or is absent")
    # A minimum guaranteed wrapper refuses an impossible output before copying
    # or invoking full replay. After replay, every complete span is reserved
    # before the first clock, and the pure plan is bounded before publication.
    minimum = {"observation": kw["observation"]} if preparing else {
        "exposure": {"measurement_plan": kw["exposure_inputs"]["measurement_plan"]}}
    exposure._json_size(minimum, resources["max_output_bytes"])
    if preparing:
        if not measurement._digest(kw["expected_observation_sha256"]):
            _fail("timing observation needs an independent external pin")
        measurement._pin(kw["observation"], kw["expected_observation_sha256"], "artifact_sha256")
    return policy


class _InterpreterPin:
    """Bounded streaming hash plus named and actual running-image generation."""

    def __init__(self, expected):
        self.path = expected["path"]
        self.fd = model_files._open(self.path, os.O_RDONLY)
        try:
            info = os.fstat(self.fd)
            if not model_files._valid_file(info, baseline.siavector.MAX_EXECUTABLE_BYTES, system=True) \
                    or not info.st_mode & 0o111 or os.pread(self.fd, 4, 0) != b"\x7fELF":
                _fail("interpreter is not an admitted ordinary executable")
            self.generation = model_files._generation(info)
            digest, size = model_files._hash_fd(self.fd, baseline.siavector.MAX_EXECUTABLE_BYTES)
            if size != info.st_size or digest != expected["sha256"]:
                _fail("running-interpreter byte expectation disagrees")
            self.current()
        except BaseException:
            os.close(self.fd)
            raise

    def current(self):
        if model_files._generation(os.fstat(self.fd)) != self.generation:
            _fail("interpreter source generation changed")
        rebound = model_files._open(self.path, os.O_RDONLY)
        try:
            if model_files._generation(os.fstat(rebound)) != self.generation:
                _fail("interpreter named generation changed")
        finally:
            os.close(rebound)
        # This fixed kernel-owned proc link is intentional running-image
        # authority, not an artifact-selected symlink or file-path fallback.
        running = os.open("/proc/self/exe", os.O_RDONLY | os.O_CLOEXEC)
        try:
            if model_files._generation(os.fstat(running)) != self.generation:
                _fail("declared interpreter is not the actual running executable generation")
        finally:
            os.close(running)

    def close(self):
        os.close(self.fd)


@contextlib.contextmanager
def _producer_sources(expected):
    directory = os.path.dirname(os.path.abspath(__file__))
    # No alternate source-root authority exists in the public contract.
    for module in (baseline, measurement, exposure, envelope, exposure.activation):
        if os.path.dirname(os.path.abspath(module.__file__)) != directory:
            _fail("producer loaded component paths do not share its source directory")
    with contextlib.ExitStack() as stack:
        code_current = baseline._code_sources(expected["code_expectations"], stack)
        interpreter = _InterpreterPin(expected["interpreter"])
        stack.callback(interpreter.close)

        def current():
            code_current()
            interpreter.current()

        current()
        yield current
        current()


def _replay(kw):
    source = exposure.rerank_event_exposure(**kw["exposure_inputs"])
    measurement._pin(source, kw["expected_exposure_sha256"], "artifact_sha256")
    if source["schema"] != kw["timing_policy"]["exposure_schema"] or source["status"] != "computed-unverified":
        _fail("complete replay did not produce the declared pure exposure")
    if source["split"] == "heldout":
        parameters = source["measurement_plan"]["baseline"]["parameter_freeze"]["parameters"]
        for key, expected in (("rerank_latency_policy_sha256", kw["expected_timing_policy_sha256"]),
                              ("rerank_timing_producer_sha256", kw["expected_producer_sha256"])):
            if type(parameters.get(key)) is not str or parameters[key] != expected:
                _fail("heldout parameter freeze omits or changes a required timing or producer pin")
    elif source["split"] != "calibration":
        _fail("timed exposure has no admitted split")
    return source


def _worker_input(source, query, arm):
    return {"arm": arm, "query": {key: query[key] for key in ("id", "text", "cue")},
            "candidates": query["candidates"], "observed_at": source["observed_at"],
            "activation_policy": source["activation_policy"]}


def _worker_output(query, arm):
    return {"order": next(row["order"] for row in query["arms"] if row["name"] == arm),
            "activation": query["activation"] if arm == "cue-event-exposure" else None}


def _schedule(source, policy):
    queries = source["queries"]
    if type(queries) is not list or not 0 < len(queries) <= policy["resources"]["max_queries"]:
        _fail("replayed complete query roster exceeds timing capacity")
    return [{"query_id": query["id"], "arm": arm,
             "input_sha256": _hash(_worker_input(source, query, arm)),
             "output_sha256": _hash(_worker_output(query, arm))}
            for query in queries for arm in ARMS]


def _observation_body(kw, source, spans, inputs_sha):
    return {
        "schema": "sia-cognitive-event-exposure-timing-observation-v1", "status": "observed",
        "exposure": source, "exposure_sha256": kw["expected_exposure_sha256"],
        "exposure_inputs_sha256": inputs_sha,
        "timing_policy": kw["timing_policy"], "timing_policy_sha256": kw["expected_timing_policy_sha256"],
        "producer_expectations": kw["producer_expectations"], "producer_sha256": kw["expected_producer_sha256"],
        "producer_checks": _PRODUCER_CHECKS, "query_spans": spans,
        "pipeline_timing": dict(PIPELINE_UNAVAILABLE),
        "source_non_claims": {"exposure": source["non_claims"], "exposure_sources": source["source_non_claims"]},
        "non_claims": list(NON_CLAIMS),
    }


def _reserve_observation(kw, source, schedule, inputs_sha):
    resources = kw["timing_policy"]["resources"]
    # Fixed widest admitted endpoint spellings reserve the complete schedule.
    # These placeholders are never observations and never reach a result.
    spans = [{**row, "start_ns": resources["max_clock_ns"], "end_ns": resources["max_clock_ns"]}
             for row in schedule]
    body = _observation_body(kw, source, spans, inputs_sha)
    body["artifact_sha256"] = "0" * len(kw["expected_exposure_sha256"])
    baseline._bounded(body, resources["max_output_bytes"])
    exposure._json_size(body, resources["max_output_bytes"])


def _span(start, end, previous, policy):
    maximum = policy["resources"]["max_clock_ns"]
    if any(type(value) is not int or not 0 <= value <= maximum for value in (start, end)) \
            or end < start or previous is not None and start < previous:
        _fail("clock endpoints are invalid, reversed, overlapping, or outside capacity")


def _observe(kw):
    policy = _admit(kw)
    initial_inputs_sha = _hash(kw["exposure_inputs"], policy["resources"]["max_input_bytes"])
    detached = copy.deepcopy(kw)
    policy = _admit(detached)
    inputs_sha = _hash(detached["exposure_inputs"], policy["resources"]["max_input_bytes"])
    if inputs_sha != initial_inputs_sha:
        _fail("input generation changed while detaching")
    with _producer_sources(detached["producer_expectations"]) as current:
        # This deliberately invokes the ordinary workers without clocks.
        # Its cache effects are named by the frozen observation policy.
        source = _replay(detached)
        schedule = _schedule(source, policy)
        _reserve_observation(detached, source, schedule, inputs_sha)
        current()
        queries, spans, index, previous = [], [], 0, None
        for query in source["queries"]:
            results = {}
            for arm in ARMS:
                arguments = _worker_input(source, query, arm)
                expected = schedule[index]
                if _hash(arguments) != expected["input_sha256"]:
                    _fail("target-blind inputs changed before timing")
                # Endpoint validation and output hashing occur AFTER the clock
                # closes. Nothing outside the shared worker is relabelled as
                # work performed inside this declared interval.
                start = time.perf_counter_ns()
                result = exposure._rank_arm(**arguments)
                end = time.perf_counter_ns()
                _span(start, end, previous, policy)
                baseline._bounded(result, policy["resources"]["max_document_bytes"])
                if _hash(arguments) != expected["input_sha256"] or _hash(result) != expected["output_sha256"]:
                    _fail("timed worker changed inputs or disagrees with complete untimed replay")
                results[arm] = result
                spans.append({**expected, "start_ns": start, "end_ns": end})
                previous = end
                index += 1
            queries.append({**query, "activation": results["cue-event-exposure"]["activation"],
                            "arms": [{"name": arm, "order": results[arm]["order"]} for arm in ARMS]})
        rebuilt = {**source, "queries": queries}
        measurement._pin(rebuilt, detached["expected_exposure_sha256"], "artifact_sha256")
        if not measurement._same(rebuilt, source):
            _fail("timed replay changed the complete original pure exposure")
        if _hash(kw["exposure_inputs"], policy["resources"]["max_input_bytes"]) != initial_inputs_sha \
                or not measurement._same(kw["timing_policy"], detached["timing_policy"]) \
                or not measurement._same(kw["producer_expectations"], detached["producer_expectations"]):
            _fail("caller input or expectation generation changed during observation")
        body = _observation_body(detached, rebuilt, spans, inputs_sha)
        result = _finish(body, "artifact_sha256", policy["resources"]["max_output_bytes"])
        current()
        return result


def _admit_observation(kw, source, schedule):
    observation = kw["observation"]
    _keys(observation, _OBSERVATION_KEYS, "timing observation")
    inputs_sha = _hash(kw["exposure_inputs"], kw["timing_policy"]["resources"]["max_input_bytes"])
    expected_body = _observation_body(kw, source, observation["query_spans"], inputs_sha)
    for field, expected in expected_body.items():
        if field == "query_spans":
            continue
        if not measurement._same(observation[field], expected):
            _fail("timing observation source, policy, producer, or boundary differs from independent replay")
    spans = observation["query_spans"]
    if type(spans) is not list or len(spans) != len(schedule):
        _fail("timing observation does not retain the complete fixed schedule")
    previous = None
    for observed, expected in zip(spans, schedule, strict=True):
        _keys(observed, _SPAN_KEYS, "timed worker span")
        if any(observed[field] != value for field, value in expected.items()):
            _fail("worker span schedule, input, or output differs from complete replay")
        _span(observed["start_ns"], observed["end_ns"], previous, kw["timing_policy"])
        previous = observed["end_ns"]
    return observation


def _samples(source, observation, observation_sha):
    metadata = {row["id"]: row for row in source["measurement_plan"]["queries"]}
    samples = []
    for index, span in enumerate(observation["query_spans"]):
        query = metadata[span["query_id"]]
        samples.append({
            "query_id": span["query_id"], "arm": span["arm"], "class": query["class"], "group_id": query["group_id"],
            "expression": "(" + str(span["end_ns"]) + "-" + str(span["start_ns"]) + ")", "unit": "ns",
            "given": {"observation_sha256": observation_sha, "source_pointer": "/query_spans/" + str(index),
                      "start_ns": span["start_ns"], "end_ns": span["end_ns"],
                      "representation": "bounded-json-integer-clock-endpoints-v1", "unit": "ns"},
        })
    return samples


def _requests(classes, samples):
    requests = []
    for sample in samples:
        requests.append({
            "tool": "jackal_exact", "arguments": {"expression": sample["expression"]},
            "scope": {"kind": "query", "id": sample["query_id"]}, "arm": sample["arm"],
            "metric": "worker_ns", "unit": "ns", "query_ids": [sample["query_id"]],
            "group_ids": [sample["group_id"]], "given": [sample],
        })
    for klass in classes:
        identifiers = klass["query_ids"]
        if not identifiers:
            continue
        for arm in ARMS:
            given = [sample for sample in samples if sample["class"] == klass["class"] and sample["arm"] == arm]
            if [row["query_id"] for row in given] != identifiers \
                    or sorted({row["group_id"] for row in given}) != klass["group_ids"]:
                _fail("timing aggregation does not retain the complete query and group roster")
            requests.append({
                "tool": "jackal_exact", "arguments": {"expression": "(" + "+".join(
                    "(" + row["expression"] + ")" for row in given) + ")/" + str(len(given))},
                "scope": {"kind": "class", "id": klass["class"]}, "arm": arm,
                "metric": "mean_worker_ns", "unit": "ns", "query_ids": identifiers,
                "group_ids": klass["group_ids"], "given": given,
            })
    return requests


def _prepare(kw):
    _admit(kw, preparing=True)
    detached = copy.deepcopy(kw)
    policy = _admit(detached, preparing=True)
    source = _replay(detached)
    schedule = _schedule(source, policy)
    observation = _admit_observation(detached, source, schedule)
    samples = _samples(source, observation, detached["expected_observation_sha256"])
    classes = source["measurement_plan"]["classes"]
    body = {
        "schema": "sia-cognitive-event-exposure-latency-plan-v1", "status": "prepared-for-jackal",
        "arithmetic_status": "not-evaluated", **{field: source[field] for field in _SOURCE_FIELDS},
        "exposure_sha256": detached["expected_exposure_sha256"],
        "observation_sha256": detached["expected_observation_sha256"], "observation": observation,
        "timing_policy_sha256": detached["expected_timing_policy_sha256"], "timing_policy": policy,
        "producer_sha256": detached["expected_producer_sha256"],
        "query_samples": samples, "classes": classes, "jackal_requests": _requests(classes, samples),
        "pipeline_timing": dict(PIPELINE_UNAVAILABLE),
        "source_non_claims": {"observation": observation["non_claims"],
                              "observation_sources": observation["source_non_claims"]},
        "non_claims": list(PLAN_NON_CLAIMS),
    }
    return _finish(body, "plan_sha256", policy["resources"]["max_output_bytes"])


def _guard(function, kw, *, preparing=False):
    try:
        return function(kw)
    except ExposureTimingRefusal:
        raise
    except (baseline.BaselineRefusal, OSError, RuntimeError, ValueError, TypeError, KeyError,
            IndexError, OverflowError, RecursionError, UnicodeError, StopIteration) as exc:
        error = ExposureTimingRefusal("cognitive exposure timing could not admit the complete operation")
        error.non_claims = list(PLAN_NON_CLAIMS if preparing else NON_CLAIMS)
        upstream = getattr(exc, "non_claims", [])
        try:
            baseline._bounded(upstream, MAX_DOCUMENT_BYTES)
        except (baseline.BaselineRefusal, ValueError, TypeError, OverflowError, RecursionError, UnicodeError):
            _fail("upstream refusal nonclaims exceed their complete bound")
        if type(upstream) is not list or any(type(statement) is not str for statement in upstream):
            _fail("upstream refusal nonclaims are not bounded strings")
        error.upstream_non_claims = list(upstream)
        raise error from exc


def observe_event_exposure(*, exposure_inputs, expected_exposure_sha256, timing_policy,
                           expected_timing_policy_sha256, producer_expectations, expected_producer_sha256):
    """Observe only this new pinned, fully admitted shared-worker replay."""
    return _guard(_observe, locals())


def prepare_rerank_latency(*, observation, expected_observation_sha256, exposure_inputs,
                          expected_exposure_sha256, timing_policy, expected_timing_policy_sha256,
                          producer_expectations, expected_producer_sha256):
    """Replay a pinned receipt without reopening files or reading any clock."""
    return _guard(_prepare, locals(), preparing=True)
