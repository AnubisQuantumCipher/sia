"""Pure integrated live-loop RED contract, before resident hook integration.

Root alone executes this suite. Its signed pages, clocks, emitted body bytes
and controller histories are SYNTHETIC fixtures, not new machine evidence.
The real encoding, activation, workspace, co-retrieval and gist components
must run. A planned transition is not publication, runtime delivery, or a win.

The live policy explicitly adds a positive age offset for same-pulse uses;
no frozen diagnostic policy or raw-baseline parameter freeze is changed.
Novelty gates admission, never evidence retention or an invented weighted
activation score. Successful explicit delivery is a separate admission type.

New controller timestamp literals were obtained BEFORE writing from JACKAL:
status=exact, formal=false; parsed=2000000000-4 exact=1999999996;
parsed=2000000000-3 exact=1999999997; parsed=2000000000-2 exact=1999999998;
parsed=2000000000-1 exact=1999999999; parsed=2000000000+9 exact=2000000009;
parsed=2000000000+10 exact=2000000010.
Nonclaims: NOT formal-bounded: this lane carries no Lean-checked certificate;
The epistemic class above is the STRONGEST claim this result supports;
exact rational arithmetic (not yet checker-covered).
Other numeric inputs are explicit choices or observed existing test limits.
No local numerical score, duration, or metric oracle is introduced.

Input contracts:
* intake: schema/epoch_id/started_at/complete/pages/current_versions/symbols/
  contexts/observations. pages retain ALL epoch versions. Each page has
  subject/content/origin/source_sha256/content_sha256/version_sha256.
  Version identity hashes subject+content_sha256+source_sha256+origin.
  current_versions selects at most one version of each subject.
  Observations have id/timestamp/version_sha256/symbol/context/native_timestamp.
* deliveries: schema/epoch_id/complete/records, the COMPLETE retained epoch.
* state: schema/epoch_id/observed_at/parent_state_sha256/intake/deliveries/
  policy/policy_sha256/uses/traces/encoding/admission/activation/workspace/
  held_selection_receipt/coretrieval_trace/coretrieval/idle/non_claims.
  A transition separately binds state_sha256 and complete history_capture.
* admission: one row per perception plus one row per delivered version, with
  kind/record_id/version_sha256/eligible/reason. No excluded occurrence drops.
* traces: current unique-subject activation inputs, using only exact-version
  uses. Full typed/versioned uses remain separately retained in state.
* held_selection_receipt binds the original payload generation, frame,
  admission and activation; sustained frames MUST NOT replace its reasons.
* recall rows: {row_ref,version_sha256,row}; row is ORIGINAL engine metadata
  including slug/score/title/type/chunk_text. Return rows unchanged plus order.
* delivery: exact emitted row wrappers + original order references and bounded
  base64 UTF-8 body witness, bytes and SHA, source state/policy/rank identities,
  request ID/completed_at/epoch, origin=derived, boundary/nonclaims. Its bound
  section is result-body-before-queue-health-footer-v1. Only runtime emit/flush
  can witness actual output; pure completion merely admits supplied bytes.
* history capture: schema/epoch_id/complete/scope/intake/deliveries/policy/
  policy_sha256/observed_at/uses/state_sha256/non_claims/capture_sha256.
  Admission recomputes threshold decisions and typed uses from all retained
  inputs. state_sha256 is supplied linkage, NOT replay of workspace chronology,
  resident publication, or historical authenticity.
"""

import base64
import copy
import hashlib
import importlib
import inspect
import json
import unittest
from unittest import mock

from tests import test_activation_trace as activation_tests
from tests import test_coretrieval_learning as coretrieval_tests
from tests import test_predictive_encoding as encoding_tests
from tests import test_replay_gist as gist_tests
from tests import test_workspace_broadcast as workspace_tests


NOW = 2000000000
START = 1999999996
PERCEPTION_TIMES = (1999999996, 1999999997, 1999999998, 1999999999)
DELIVERED_AT = 2000000009
EXPIRED_AT = 2000000010
EPOCH = "fixture-controller-epoch"
BODY_SCOPE = "result-body-before-queue-health-footer-v1"
SCOPE = "complete-controller-observations-since-declared-epoch-v1"
NON_CLAIMS = [
    "This is an integrated computed-unverified software transition, not JACKAL assurance, biological cognition, or a held-out win.",
    "A planned state, broadcast, or gist proposal is not durable publication, consumer delivery, acknowledgment, or execution of the resident loop.",
    "Novelty-threshold admission and explicit-delivery exemption are engineering workspace policies, not weighted ACT-R activation or a biological gain law.",
    "Controller encoding and service-output-completed times are distinct from native event times and do not establish human reading, understanding, or successful use.",
    "Complete history is scoped to the externally declared controller epoch; legacy recent-use tails and missing earlier observations are not reconstructed as complete traces.",
    "Hashes bind supplied bytes and version joins, not source authentication, historical completeness, loaded runtime behavior, or protection against hostile same-user mutation.",
    "Original content and origins remain unchanged; learned co-retrieval edges are retrieval-only and gist proposals are derived additions, not replacements for episodes.",
    "All encoding, activation, workspace, co-retrieval, gist, source and delivery nonclaims remain controlling.",
]


def canonical(value):
    return gist_tests.canonical(value)


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def bytes_digest(value):
    return hashlib.sha256(value).hexdigest()


def own_digest(value, field):
    return digest({key: item for key, item in value.items() if key != field})


def version_digest(page):
    return digest({key: page[key] for key in
                   ("subject", "content_sha256", "source_sha256", "origin")})


def policy_fixture():
    activation = {**activation_tests.POLICY, "age_offset_seconds": 1}
    return {
        "schema": "sia-live-loop-policy-v1",
        "scope": SCOPE,
        "time_unit": "unix-seconds-integer",
        "encoding": copy.deepcopy(encoding_tests.POLICY),
        "activation": activation,
        "workspace": copy.deepcopy(workspace_tests.POLICY),
        "coretrieval": copy.deepcopy(coretrieval_tests.POLICY),
        "novelty_admission": {
            "comparison": "strength-at-least-v1", "threshold": 2,
            "aggregation": "any-admitted-occurrence-per-version-v1",
            "explicit_delivery": "admit-without-novelty-filter-v1",
        },
        "activation_events": ["encoding-admitted", "service-output-completed"],
        "workspace_release": "expiry-only-v1",
        "recall_order": "activation-desc-stable-input-v1",
        "delivery_body": BODY_SCOPE,
        "delivery_activity": 1,
        "idle": "supported-capture-replay-gist-fresh-derived-only-v1",
        "limits": {
            "max_input_bytes": 16777216, "max_output_bytes": 16777216,
            "max_versions": 256, "max_observations": 4096,
            "max_deliveries": 4096, "max_rows": 256,
            "max_content_bytes": 1048576, "max_delivery_bytes": 1048576,
        },
    }


class LiveLoopPureIntegration(unittest.TestCase):
    """A real component pipeline; actual resident wrappers are a later gate."""

    def _module(self):
        try:
            module = importlib.import_module("sialiveloop")
        except ModuleNotFoundError as exc:
            self.fail("integrated live-loop component must exist: " + str(exc))
        for name in ("prepare_pulse", "rank_recall", "complete_delivery", "admit_history_capture"):
            self.assertTrue(callable(getattr(module, name, None)), name)
        self.assertTrue(hasattr(module, "LiveLoopRefusal"))
        return module

    def _inputs(self):
        source = gist_tests.ReplayGist(methodName="runTest")
        source.setUp()
        self.addCleanup(source.doCleanups)
        # The model origin is in the actual synthetic page bytes and capture,
        # not merely pasted over a producer label in the component request.
        captured = source._fixture(model_sequence="3")
        source.capture = captured
        events = {event["seq"]: event for event in captured["events"] if event["chain"] == "aegis"}
        pages = {page["slug"]: page for page in captured["pages"]}
        retained, observations = [], []
        for seq, stamp, symbol in zip(("1", "2", "3", "4"), PERCEPTION_TIMES,
                                      ("outcome", "outcome", "intent", "outcome"), strict=True):
            event = events[seq]
            page = pages[event["retention"]["source_slug"]]
            version = {"subject": page["slug"], "content": page["text"], "origin": page["origin"],
                       "source_sha256": captured["capture_sha256"], "content_sha256": page["sha256"]}
            version["version_sha256"] = version_digest(version)
            retained.append(version)
            observations.append({"id": "encoding-" + seq, "timestamp": stamp,
                                 "version_sha256": version["version_sha256"], "symbol": symbol,
                                 "context": "aegis", "native_timestamp": event["row"][1]})
        intake = {"schema": "sia-live-intake-v1", "epoch_id": EPOCH, "started_at": START,
                  "complete": True, "pages": retained,
                  "current_versions": [page["version_sha256"] for page in retained],
                  "symbols": ["outcome", "intent"], "contexts": ["aegis"],
                  "observations": observations}
        deliveries = {"schema": "sia-live-deliveries-v1", "epoch_id": EPOCH,
                      "complete": True, "records": []}
        self.gist_inputs = source.arguments()
        self.gist_source = source
        self.policy = policy_fixture()
        self.kw = {"intake": intake, "expected_intake_sha256": digest(intake),
                   "deliveries": deliveries, "expected_deliveries_sha256": digest(deliveries),
                   "previous_state": None, "expected_previous_state_sha256": None,
                   "policy": self.policy, "expected_policy_sha256": digest(self.policy),
                   "observed_at": NOW, "idle": False, "gist_inputs": None}

    def _prepare(self, module, **overrides):
        return module.prepare_pulse(**{**self.kw, **overrides})

    def _resume(self, result, **overrides):
        return {"previous_state": result["state"],
                "expected_previous_state_sha256": result["state_sha256"], **overrides}

    def _rows(self):
        return [{"row_ref": "row-" + page["subject"], "version_sha256": page["version_sha256"],
                 "row": {"slug": page["subject"], "score": 1.0, "title": page["subject"],
                         "type": "event", "chunk_text": page["content"]}}
                for page in self.kw["intake"]["pages"]
                if page["version_sha256"] in self.kw["intake"]["current_versions"]]

    def _rank(self, module, prepared, *, rows=None, observed_at=NOW, **overrides):
        rows = self._rows() if rows is None else rows
        return module.rank_recall(**{
            "rows": rows, "expected_rows_sha256": digest(rows), "state": prepared["state"],
            "expected_state_sha256": prepared["state_sha256"], "policy": self.policy,
            "expected_policy_sha256": digest(self.policy), "observed_at": observed_at, **overrides})

    def _delivery(self, module, ranked, *, refs=None, body=None, **overrides):
        refs = list(ranked["order"]) if refs is None else refs
        if body is None:
            # A declared synthetic emitted body, not a claim this test printed
            # it. Runtime tests must witness real stream.write + flush later.
            rows = {row["row_ref"]: row for row in ranked["rows"]}
            body = canonical([rows[ref] for ref in refs]) + b"\n"
        return module.complete_delivery(**{
            "ranked": ranked, "expected_ranked_sha256": ranked["rank_sha256"],
            "emitted_row_refs": refs, "output_utf8": body,
            "request_id": "fixture-delivery", "completed_at": DELIVERED_AT, **overrides})

    def _with_delivery(self, record):
        value = copy.deepcopy(self.kw["deliveries"])
        value["records"].append(record)
        return {"deliveries": value, "expected_deliveries_sha256": digest(value)}

    def _assert_hashes(self, result):
        self.assertEqual(result["schema"], "sia-live-loop-transition-v1")
        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["state"]["schema"], "sia-live-loop-state-v1")
        self.assertEqual(result["state_sha256"], digest(result["state"]))
        self.assertEqual(result["transition_sha256"], own_digest(result, "transition_sha256"))
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertNotIn("published", result)
        self.assertNotIn("consumed", result)

    def test_public_apis_require_explicit_pins_policies_clocks_and_complete_delivery_bytes(self):
        module = self._module()
        expected = {
            "prepare_pulse": {"intake", "expected_intake_sha256", "deliveries", "expected_deliveries_sha256",
                              "previous_state", "expected_previous_state_sha256", "policy", "expected_policy_sha256",
                              "observed_at", "idle", "gist_inputs"},
            "rank_recall": {"rows", "expected_rows_sha256", "state", "expected_state_sha256",
                            "policy", "expected_policy_sha256", "observed_at"},
            "complete_delivery": {"ranked", "expected_ranked_sha256", "emitted_row_refs", "output_utf8",
                                  "request_id", "completed_at"},
            "admit_history_capture": {"capture", "expected_capture_sha256"},
        }
        for name, fields in expected.items():
            signature = inspect.signature(getattr(module, name))
            self.assertEqual(set(signature.parameters), fields)
            for field, parameter in signature.parameters.items():
                self.assertIs(parameter.default, inspect.Parameter.empty, (name, field))
                if field != "capture":
                    self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY, (name, field))

    def test_perception_novelty_admission_workspace_and_activation_are_real_and_lossless(self):
        module = self._module()
        self._inputs()
        before = copy.deepcopy(self.kw)
        encoding = importlib.import_module("siaencoding")
        activation = importlib.import_module("siaactivation")
        workspace = importlib.import_module("siaworkspace")
        coretrieval = importlib.import_module("siacoretrieval")
        with mock.patch.object(encoding, "replay_encoding", wraps=encoding.replay_encoding) as enc, \
                mock.patch.object(activation, "rank_traces", wraps=activation.rank_traces) as act, \
                mock.patch.object(workspace, "advance_workspace", wraps=workspace.advance_workspace) as ws, \
                mock.patch.object(coretrieval, "learn_coretrieval", wraps=coretrieval.learn_coretrieval) as co, \
                mock.patch("builtins.open", side_effect=AssertionError("pure pulse opened a path")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("pure pulse started an engine")):
            result = self._prepare(module)
        self._assert_hashes(result)
        self.assertTrue(all(call.called for call in (enc, act, ws, co)))
        self.assertEqual(self.kw, before)
        state = result["state"]
        self.assertEqual(state["intake"], self.kw["intake"])
        self.assertEqual(state["deliveries"], self.kw["deliveries"])
        self.assertEqual(state["policy"], self.policy)
        self.assertEqual(state["policy_sha256"], digest(self.policy))
        self.assertEqual(state["encoding"]["non_claims"], list(encoding.NON_CLAIMS))
        self.assertEqual(state["activation"]["non_claims"], list(activation.NON_CLAIMS))
        self.assertEqual(state["workspace"]["non_claims"], list(workspace.NON_CLAIMS))
        self.assertEqual(state["coretrieval"]["non_claims"], list(coretrieval.LEARNING_NON_CLAIMS))
        expected = [{"kind": "perception", "record_id": row["id"],
                     "version_sha256": row["version_sha256"],
                     "eligible": encoded["encoding_strength"] >= self.policy["novelty_admission"]["threshold"],
                     "reason": ("encoding-strength-admitted"
                                if encoded["encoding_strength"] >= self.policy["novelty_admission"]["threshold"]
                                else "encoding-strength-below-threshold")}
                    for row, encoded in zip(self.kw["intake"]["observations"], state["encoding"]["events"], strict=True)]
        self.assertEqual(state["admission"], expected)
        self.assertTrue(any(row["eligible"] for row in expected))
        self.assertTrue(any(not row["eligible"] for row in expected))
        admitted = {row["record_id"] for row in expected if row["eligible"]}
        self.assertEqual({use["record_id"] for use in state["uses"]}, admitted)
        observations = {row["id"]: row for row in self.kw["intake"]["observations"]}
        for use in state["uses"]:
            self.assertEqual(use["kind"], "encoding-admitted")
            self.assertEqual(use["timestamp"], observations[use["record_id"]]["timestamp"])
            self.assertIs(type(use["timestamp"]), int)
        payload = json.loads(state["workspace"]["payload_json"])
        versions = {row["version_sha256"]: row for row in self.kw["intake"]["pages"]}
        selected = {versions[row["version_sha256"]]["subject"] for row in expected if row["eligible"]}
        self.assertEqual(set(state["workspace"]["slots"]), selected)
        for held in payload["selected"]:
            original = next(page for page in versions.values() if page["subject"] == held["subject"])
            self.assertEqual(held, {key: original[key] for key in
                                    ("subject", "content", "origin", "source_sha256")})
        self.assertTrue(any(row["origin"] == "model" for row in payload["selected"]))
        self.assertEqual(state["held_selection_receipt"]["admission"], state["admission"])
        self.assertEqual(state["held_selection_receipt"]["activation"], state["activation"])
        self.assertEqual(state["coretrieval"]["pairs"], [])
        self.assertEqual(result["gist_pages"], [])

    def test_live_recall_order_changes_without_rewriting_any_engine_row_or_source_origin(self):
        module = self._module()
        self._inputs()
        prepared = self._prepare(module)
        rows = self._rows()
        before = copy.deepcopy(rows)
        ranked = self._rank(module, prepared, rows=rows)
        self.assertEqual(ranked["schema"], "sia-live-recall-plan-v1")
        self.assertEqual(ranked["status"], "computed-unverified")
        self.assertEqual(ranked["rank_sha256"], own_digest(ranked, "rank_sha256"))
        self.assertEqual(ranked["rows"], rows)
        self.assertEqual(rows, before)
        self.assertEqual(set(ranked["order"]), {row["row_ref"] for row in rows})
        self.assertNotEqual(ranked["order"], [row["row_ref"] for row in rows])
        selected_subject = prepared["state"]["workspace"]["slots"][0]
        self.assertEqual(next(row["row"]["slug"] for row in rows
                              if row["row_ref"] == ranked["order"][0]), selected_subject)
        self.assertEqual(ranked["state_sha256"], prepared["state_sha256"])
        ranked["rows"][0]["row"]["chunk_text"] = "altered detached result"
        self.assertEqual(rows, before)

    def test_exact_supplied_output_delivery_drives_next_pulse_and_real_coretrieval(self):
        module = self._module()
        self._inputs()
        prepared = self._prepare(module)
        ranked = self._rank(module, prepared)
        delivery = self._delivery(module, ranked)
        self.assertEqual(delivery["schema"], "sia-live-delivery-v1")
        self.assertEqual(delivery["origin"], "derived")
        self.assertEqual(delivery["id"], "fixture-delivery")
        self.assertEqual(delivery["completed_at"], DELIVERED_AT)
        self.assertEqual(delivery["emitted_row_refs"], ranked["order"])
        self.assertEqual(delivery["rank_sha256"], ranked["rank_sha256"])
        self.assertEqual(delivery["state_sha256"], prepared["state_sha256"])
        self.assertEqual(delivery["epoch_id"], EPOCH)
        self.assertEqual(delivery["policy_sha256"], digest(self.policy))
        self.assertEqual(delivery["output_scope"], BODY_SCOPE)
        self.assertEqual(delivery["boundary"], "supplied-bytes-admitted-not-observed-output-v1")
        self.assertEqual(delivery["non_claims"], NON_CLAIMS)
        rows = {row["row_ref"]: row for row in ranked["rows"]}
        self.assertEqual(delivery["rows"], [rows[ref] for ref in ranked["order"]])
        raw = base64.b64decode(delivery["output_utf8_base64"], validate=True)
        self.assertEqual(raw, canonical(delivery["rows"]) + b"\n")
        self.assertEqual(delivery["output_sha256"], bytes_digest(raw))
        self.assertEqual(delivery["output_bytes"], len(raw))
        self.assertEqual(delivery["record_sha256"], own_digest(delivery, "record_sha256"))
        resumed = self._prepare(module, **self._resume(prepared, observed_at=DELIVERED_AT),
                                **self._with_delivery(delivery))
        self._assert_hashes(resumed)
        state = resumed["state"]
        delivered_uses = [use for use in state["uses"] if use["kind"] == "service-output-completed"]
        self.assertEqual([use["version_sha256"] for use in delivered_uses],
                         [row["version_sha256"] for row in delivery["rows"]])
        self.assertTrue(all(use["timestamp"] == DELIVERED_AT for use in delivered_uses))
        delivery_admissions = [row for row in state["admission"] if row["kind"] == "delivery"]
        self.assertEqual({row["version_sha256"] for row in delivery_admissions},
                         {row["version_sha256"] for row in delivery["rows"]})
        self.assertTrue(all(row["eligible"] and row["reason"] == "explicit-delivery-admitted"
                            for row in delivery_admissions))
        core = importlib.import_module("siacoretrieval")
        self.assertEqual(state["coretrieval"], core.learn_coretrieval(
            state["coretrieval_trace"], observed_at=DELIVERED_AT, policy=self.policy["coretrieval"]))
        self.assertTrue(state["coretrieval"]["graph"]["edges"])
        self.assertTrue(all(edge["scope"] == "retrieval-only" and edge["provenance"] == "learned-coreturn"
                            for edge in state["coretrieval"]["graph"]["edges"]))
        self.assertEqual(state["intake"]["pages"], prepared["state"]["intake"]["pages"])

    def test_sustained_payload_retains_original_selection_reasons_not_current_scores(self):
        module = self._module()
        self._inputs()
        before = self._prepare(module)
        after = self._prepare(module, **self._resume(before, observed_at=DELIVERED_AT))
        self.assertEqual(after["state"]["observed_at"], DELIVERED_AT)
        self.assertEqual(after["state"]["workspace"]["transition"], "sustained")
        self.assertNotEqual(after["state"]["activation"], before["state"]["activation"])
        self.assertEqual(after["state"]["workspace"]["payload_json"], before["state"]["workspace"]["payload_json"])
        self.assertEqual(after["state"]["held_selection_receipt"], before["state"]["held_selection_receipt"])
        self.assertEqual(after["state"]["uses"], before["state"]["uses"])
        broadcasts = after["state"]["workspace"]["broadcast"]
        self.assertEqual(list(broadcasts), self.policy["workspace"]["consumer_roster"])
        for payload in broadcasts.values():
            self.assertEqual(payload["payload_json"], before["state"]["workspace"]["payload_json"])

    def test_idle_runs_real_gist_and_proposes_only_fresh_derived_pages_with_complete_sources(self):
        module = self._module()
        self._inputs()
        before = self._prepare(module)
        original = copy.deepcopy(self.kw)
        gist = importlib.import_module("siagist")
        with mock.patch.object(gist, "replay_gist", wraps=gist.replay_gist) as replay:
            after = self._prepare(module, **self._resume(before, observed_at=EXPIRED_AT),
                                  idle=True, gist_inputs=self.gist_inputs)
        self.assertEqual(replay.call_args_list, [mock.call(**self.gist_inputs)])
        self.assertEqual(self.kw, original)
        self.assertEqual(after["state"]["uses"], before["state"]["uses"])
        self.assertEqual(after["state"]["workspace"]["release_reason"], "hold-expired")
        artifact = after["state"]["idle"]["gist"]
        body = json.loads(artifact["artifact_json"])
        self.assertEqual(body["capture"], self.gist_inputs["capture"])
        self.assertEqual(body["non_claims"], list(gist.NON_CLAIMS))
        selected = {identity for row in body["readout"] for identity in row["selected"]}
        candidates = {row["id"]: row for row in body["candidates"]}
        self.assertTrue(selected)
        self.assertEqual({row["content"] for row in after["gist_pages"]},
                         {candidates[identity]["text"] for identity in selected})
        old_subjects = {row["subject"] for row in self.kw["intake"]["pages"]}
        for page in after["gist_pages"]:
            self.assertNotIn(page["subject"], old_subjects)
            self.assertEqual(page["origin"], "derived")
            self.assertEqual(page["source_sha256"], artifact["artifact_sha256"])
            self.assertEqual(page["content_sha256"], bytes_digest(page["content"].encode("utf-8")))
            self.assertEqual(page["version_sha256"], version_digest(page))
        self.assertEqual(after["state"]["intake"]["pages"], before["state"]["intake"]["pages"])
        self.assertNotIn("published", after["state"]["idle"])

    def test_frontdoor_history_capture_reconstructs_complete_typed_versioned_uses(self):
        module = self._module()
        self._inputs()
        first = self._prepare(module)
        record = self._delivery(module, self._rank(module, first))
        result = self._prepare(module, **self._resume(first, observed_at=DELIVERED_AT),
                               **self._with_delivery(record))
        captured = result["history_capture"]
        self.assertEqual(captured["schema"], "sia-live-history-capture-v1")
        self.assertIs(captured["complete"], True)
        self.assertEqual(captured["scope"], SCOPE)
        self.assertEqual(captured["epoch_id"], EPOCH)
        self.assertEqual(captured["uses"], result["state"]["uses"])
        self.assertEqual(captured["intake"], self.kw["intake"])
        self.assertEqual(captured["deliveries"]["records"], [record])
        self.assertEqual(captured["policy"], self.policy)
        self.assertEqual(captured["policy_sha256"], digest(self.policy))
        self.assertEqual(captured["observed_at"], DELIVERED_AT)
        self.assertEqual(captured["non_claims"], NON_CLAIMS)
        self.assertEqual(captured["state_sha256"], result["state_sha256"])
        expected = result["history_capture_sha256"]
        self.assertEqual(expected, own_digest(captured, "capture_sha256"))
        self.assertEqual(captured["capture_sha256"], expected)
        admitted = module.admit_history_capture(captured, expected_capture_sha256=expected)
        self.assertEqual(admitted, captured)
        self.assertIsNot(admitted, captured)
        with self.assertRaises(module.LiveLoopRefusal):
            module.admit_history_capture(captured, expected_capture_sha256="0" * 64)

    def test_empty_initial_epoch_is_explicitly_complete_without_fabricated_uses_or_payload(self):
        module = self._module()
        self._inputs()
        intake = copy.deepcopy(self.kw["intake"])
        for field in ("pages", "current_versions", "observations"):
            intake[field] = []
        result = self._prepare(module, intake=intake, expected_intake_sha256=digest(intake))
        self._assert_hashes(result)
        state = result["state"]
        self.assertEqual(state["uses"], [])
        self.assertEqual(state["admission"], [])
        self.assertEqual(state["traces"], [])
        self.assertEqual(state["workspace"]["slots"], [])
        self.assertEqual(json.loads(state["workspace"]["payload_json"])["selected"], [])
        self.assertIsNone(state["held_selection_receipt"])
        self.assertEqual(state["coretrieval"]["pairs"], [])
        self.assertEqual(result["gist_pages"], [])
        ranked = self._rank(module, result, rows=[])
        self.assertEqual(ranked["rows"], [])
        self.assertEqual(ranked["order"], [])
        captured = result["history_capture"]
        self.assertEqual(module.admit_history_capture(
            captured, expected_capture_sha256=result["history_capture_sha256"]), captured)

    def test_same_pulse_use_requires_declared_positive_offset_without_silent_strict_lane_fallback(self):
        module = self._module()
        self._inputs()
        intake = copy.deepcopy(self.kw["intake"])
        for observation in intake["observations"]:
            observation["timestamp"] = NOW
        inputs = {"intake": intake, "expected_intake_sha256": digest(intake)}
        result = self._prepare(module, **inputs)
        self.assertTrue(result["state"]["uses"])
        self.assertTrue(all(use["timestamp"] == NOW for use in result["state"]["uses"]))
        self.assertEqual(result["state"]["policy"]["activation"]["age_offset_seconds"], 1)
        strict = copy.deepcopy(self.policy)
        strict["activation"]["age_offset_seconds"] = 0
        with self.assertRaises(module.LiveLoopRefusal):
            self._prepare(module, **inputs, policy=strict, expected_policy_sha256=digest(strict))
        self.assertEqual(activation_tests.POLICY["age_offset_seconds"], 0)

    def test_complete_emitted_roster_is_not_the_legacy_reinforced_subset(self):
        module = self._module()
        self._inputs()
        intake = copy.deepcopy(self.kw["intake"])
        # Eight is the observed cmd_ask display slice; five is its separate
        # legacy reinforcement slice. Neither becomes this helper's cap.
        intake["pages"] = []
        intake["observations"] = []
        for identity in ("a", "b", "c", "d", "e", "f", "g", "h"):
            content = "Synthetic original model page " + identity + ".\n"
            page = {"subject": "fixture/" + identity, "content": content, "origin": "model",
                    "content_sha256": bytes_digest(content.encode("utf-8")),
                    "source_sha256": self.kw["intake"]["pages"][0]["source_sha256"]}
            page["version_sha256"] = version_digest(page)
            intake["pages"].append(page)
        intake["current_versions"] = [page["version_sha256"] for page in intake["pages"]]
        self.kw.update(intake=intake, expected_intake_sha256=digest(intake))
        first = self._prepare(module)
        ranked = self._rank(module, first)
        self.assertEqual(ranked["order"], [row["row_ref"] for row in self._rows()],
                         "unavailable activation preserves stable input ties")
        record = self._delivery(module, ranked)
        self.assertEqual(record["emitted_row_refs"], ranked["order"])
        self.assertEqual(record["rows"], ranked["rows"])
        self.assertNotEqual(record["rows"], ranked["rows"][:5])
        result = self._prepare(module, **self._resume(first, observed_at=DELIVERED_AT),
                               **self._with_delivery(record))
        self.assertEqual([use["version_sha256"] for use in result["state"]["uses"]],
                         intake["current_versions"])
        self.assertEqual(result["state"]["intake"]["pages"], intake["pages"])

    def test_distinct_emitted_chunks_preserve_rows_but_do_not_multiply_same_version_uses(self):
        module = self._module()
        self._inputs()
        first = self._prepare(module)
        original = self._rows()[0]
        another = copy.deepcopy(original)
        another["row_ref"] = "another-chunk-row"
        another["row"]["chunk_text"] = original["row"]["chunk_text"].splitlines()[0]
        rows = [original, another]
        ranked = self._rank(module, first, rows=rows)
        record = self._delivery(module, ranked)
        self.assertEqual(record["rows"], rows)
        result = self._prepare(module, **self._resume(first, observed_at=DELIVERED_AT),
                               **self._with_delivery(record))
        uses = [use for use in result["state"]["uses"] if use["kind"] == "service-output-completed"]
        admissions = [row for row in result["state"]["admission"] if row["kind"] == "delivery"]
        self.assertEqual([use["version_sha256"] for use in uses], [original["version_sha256"]])
        self.assertEqual([row["version_sha256"] for row in admissions], [original["version_sha256"]])
        self.assertEqual(result["state"]["coretrieval"]["pairs"], [])

    def test_retry_is_deterministic_and_retained_delivery_is_not_applied_twice(self):
        module = self._module()
        self._inputs()
        first = self._prepare(module)
        record = self._delivery(module, self._rank(module, first))
        complete = self._with_delivery(record)
        arguments = self._resume(first, observed_at=DELIVERED_AT)
        applied = self._prepare(module, **arguments, **complete)
        retried = self._prepare(module, **arguments, **complete)
        self.assertEqual(retried, applied, "same planned transaction must be byte deterministic")
        next_frame = self._prepare(module, **self._resume(applied, observed_at=DELIVERED_AT), **complete)
        self.assertEqual(next_frame["state"]["uses"], applied["state"]["uses"])
        self.assertEqual(next_frame["state"]["coretrieval_trace"], applied["state"]["coretrieval_trace"])
        self.assertEqual(next_frame["state"]["coretrieval"], applied["state"]["coretrieval"])
        self.assertEqual(next_frame["state"]["held_selection_receipt"], applied["state"]["held_selection_receipt"])

    def test_rehashed_truncated_reordered_edited_or_foreign_epoch_history_refuses(self):
        module = self._module()
        self._inputs()
        first = self._prepare(module)
        record = self._delivery(module, self._rank(module, first))
        applied = self._prepare(module, **self._resume(first, observed_at=DELIVERED_AT),
                                **self._with_delivery(record))
        mutations = []
        for label in ("omit", "reorder", "edit", "epoch", "start", "lost-version"):
            intake = copy.deepcopy(self.kw["intake"])
            if label == "omit":
                intake["observations"].pop()
            elif label == "reorder":
                intake["observations"].reverse()
            elif label == "edit":
                intake["observations"][0]["native_timestamp"] = "changed provenance"
            elif label == "epoch":
                intake["epoch_id"] = "replacement-epoch"
            elif label == "start":
                intake["started_at"] = NOW
            else:
                removed = intake["pages"].pop()
                intake["current_versions"].remove(removed["version_sha256"])
                intake["observations"] = [row for row in intake["observations"]
                                          if row["version_sha256"] != removed["version_sha256"]]
            mutations.append((label, {"intake": intake, "expected_intake_sha256": digest(intake)}))
        for label, changed in mutations:
            with self.subTest(label=label), self.assertRaises(module.LiveLoopRefusal):
                self._prepare(module, **self._resume(applied, observed_at=DELIVERED_AT),
                              **self._with_delivery(record), **changed)
        with self.assertRaises(module.LiveLoopRefusal):
            self._prepare(module, **self._resume(applied, observed_at=DELIVERED_AT))
        conflicting = self._delivery(module, self._rank(module, first), body=b"different emitted body\n")
        with self.assertRaises(module.LiveLoopRefusal):
            self._prepare(module, **self._resume(applied, observed_at=DELIVERED_AT),
                          **self._with_delivery(conflicting))
        duplicate = self._with_delivery(record)["deliveries"]
        duplicate["records"].append(copy.deepcopy(record))
        with self.assertRaises(module.LiveLoopRefusal):
            self._prepare(module, **self._resume(first, observed_at=DELIVERED_AT),
                          deliveries=duplicate, expected_deliveries_sha256=digest(duplicate))

    def test_current_same_subject_version_change_or_missing_held_version_never_rewrites_episode(self):
        module = self._module()
        self._inputs()
        first = self._prepare(module)
        held_subject = first["state"]["workspace"]["slots"][0]
        old = next(page for page in self.kw["intake"]["pages"] if page["subject"] == held_subject)
        for label in ("new-version", "missing-current"):
            intake = copy.deepcopy(self.kw["intake"])
            intake["current_versions"].remove(old["version_sha256"])
            if label == "new-version":
                changed = {**old, "content": old["content"] + "New original version, not an overwrite.\n"}
                changed["content_sha256"] = bytes_digest(changed["content"].encode("utf-8"))
                changed["version_sha256"] = version_digest(changed)
                intake["pages"].append(changed)
                intake["current_versions"].append(changed["version_sha256"])
            with self.subTest(label=label), self.assertRaises(module.LiveLoopRefusal):
                self._prepare(module, **self._resume(first, observed_at=DELIVERED_AT),
                              intake=intake, expected_intake_sha256=digest(intake))
        self.assertEqual(first["state"]["intake"], self.kw["intake"])

    def test_recall_clock_is_explicit_and_cross_kind_record_ids_remain_distinct(self):
        module = self._module()
        self._inputs()
        first = self._prepare(module)
        activation = importlib.import_module("siaactivation")
        with mock.patch.object(activation, "rank_traces", wraps=activation.rank_traces) as rank:
            later = self._rank(module, first, observed_at=DELIVERED_AT)
        self.assertTrue(rank.called)
        self.assertTrue(all(call.kwargs["observed_at"] == DELIVERED_AT for call in rank.call_args_list))
        perception_id = next(use["record_id"] for use in first["state"]["uses"])
        record = self._delivery(module, later, request_id=perception_id)
        result = self._prepare(module, **self._resume(first, observed_at=DELIVERED_AT),
                               **self._with_delivery(record))
        matching = [use for use in result["state"]["uses"] if use["record_id"] == perception_id]
        self.assertEqual({use["kind"] for use in matching},
                         {"encoding-admitted", "service-output-completed"})
        self.assertEqual(len({use["id"] for use in matching}), len(matching))

    def test_delivery_refuses_wrong_pin_unknown_or_duplicate_refs_bad_body_and_early_clock(self):
        module = self._module()
        self._inputs()
        first = self._prepare(module)
        ranked = self._rank(module, first)
        bad_calls = [
            {"expected_ranked_sha256": "0" * 64},
            {"refs": ["unknown-row"], "body": b"body\n"},
            {"refs": [ranked["order"][0], ranked["order"][0]], "body": b"body\n"},
            {"body": b"\xff"}, {"body": "not bytes"},
            {"completed_at": START}, {"completed_at": float(DELIVERED_AT)},
        ]
        for changed in bad_calls:
            with self.subTest(changed=changed), self.assertRaises(module.LiveLoopRefusal):
                self._delivery(module, ranked, **changed)
        policy = copy.deepcopy(self.policy)
        policy["limits"]["max_delivery_bytes"] = 1
        self.policy = policy
        self.kw.update(policy=policy, expected_policy_sha256=digest(policy))
        bounded = self._rank(module, self._prepare(module))
        with self.assertRaises(module.LiveLoopRefusal):
            self._delivery(module, bounded, body=b"longer than the declared byte cap\n")

    def test_pulse_refuses_incomplete_ambiguous_future_or_foreign_inputs_before_component_work(self):
        module = self._module()
        self._inputs()
        cases = []
        for label in ("incomplete", "duplicate-observation", "future", "float-clock", "native-clock",
                      "content", "origin", "current-duplicate", "unknown-version", "unknown-symbol"):
            intake = copy.deepcopy(self.kw["intake"])
            if label == "incomplete":
                intake["complete"] = False
            elif label == "duplicate-observation":
                intake["observations"].append(copy.deepcopy(intake["observations"][0]))
            elif label == "future":
                intake["observations"][-1]["timestamp"] = DELIVERED_AT
            elif label == "float-clock":
                intake["observations"][0]["timestamp"] = float(START)
            elif label == "native-clock":
                intake["observations"][0]["timestamp"] = intake["observations"][0]["native_timestamp"]
            elif label == "content":
                intake["pages"][0]["content"] += "altered without original version identity"
            elif label == "origin":
                next(page for page in intake["pages"] if page["origin"] == "model")["origin"] = "evidence"
            elif label == "current-duplicate":
                intake["current_versions"].append(intake["current_versions"][0])
            elif label == "unknown-version":
                intake["observations"][0]["version_sha256"] = "0" * 64
            else:
                intake["observations"][0]["symbol"] = "not-in-the-declared-roster"
            cases.append((label, {"intake": intake, "expected_intake_sha256": digest(intake)}))
        incomplete = copy.deepcopy(self.kw["deliveries"])
        incomplete["complete"] = False
        foreign = copy.deepcopy(self.kw["deliveries"])
        foreign["epoch_id"] = "foreign-epoch"
        cases.extend([
            ("delivery-completeness", {"deliveries": incomplete,
                                       "expected_deliveries_sha256": digest(incomplete)}),
            ("delivery-epoch", {"deliveries": foreign, "expected_deliveries_sha256": digest(foreign)}),
            ("external-intake", {"expected_intake_sha256": "0" * 64}),
            ("external-deliveries", {"expected_deliveries_sha256": "0" * 64}),
            ("external-policy", {"expected_policy_sha256": "0" * 64}),
            ("previous-without-state", {"expected_previous_state_sha256": "0" * 64}),
            ("ambiguous-observation-clock", {"observed_at": str(NOW)}),
        ])
        encoding = importlib.import_module("siaencoding")
        for label, changed in cases:
            with self.subTest(label=label), \
                    mock.patch.object(encoding, "replay_encoding", side_effect=AssertionError("preflight was late")), \
                    self.assertRaises(module.LiveLoopRefusal):
                self._prepare(module, **changed)

    def test_complete_shape_and_capacity_are_checked_before_copy_serialization_or_hash(self):
        module = self._module()
        self._inputs()
        policy = copy.deepcopy(self.policy)
        policy["limits"]["max_input_bytes"] = 1
        policy_pin = digest(policy)
        cyclic = copy.deepcopy(self.kw["intake"])
        cyclic["observations"].append(cyclic)
        for changed in ({"policy": policy, "expected_policy_sha256": policy_pin},
                        {"intake": cyclic, "expected_intake_sha256": "0" * 64}):
            with self.subTest(capacity="policy" in changed), \
                    mock.patch("copy.deepcopy", side_effect=AssertionError("copied before complete shape bound")), \
                    mock.patch("json.dumps", side_effect=AssertionError("serialized before complete shape bound")), \
                    mock.patch("hashlib.sha256", side_effect=AssertionError("hashed before complete shape bound")), \
                    self.assertRaises(module.LiveLoopRefusal):
                self._prepare(module, **changed)

    def test_rank_refuses_row_rewrites_unknown_versions_or_stale_state_before_activation(self):
        module = self._module()
        self._inputs()
        first = self._prepare(module)
        cases = []
        for label in ("content", "subject", "version", "duplicate-ref"):
            rows = self._rows()
            if label == "content":
                rows[0]["row"]["chunk_text"] = "unjoined invented result text"
            elif label == "subject":
                rows[0]["row"]["slug"] = "foreign/page"
            elif label == "version":
                rows[0]["version_sha256"] = "0" * 64
            else:
                rows[-1]["row_ref"] = rows[0]["row_ref"]
            cases.append((label, {"rows": rows, "expected_rows_sha256": digest(rows)}))
        cases.extend([
            ("rows-pin", {"expected_rows_sha256": "0" * 64}),
            ("state-pin", {"expected_state_sha256": "0" * 64}),
            ("policy-pin", {"expected_policy_sha256": "0" * 64}),
            ("backwards-clock", {"observed_at": START}),
        ])
        activation = importlib.import_module("siaactivation")
        for label, changed in cases:
            # Prepare the helper's unchanged row pin outside the refusal spy.
            rows = changed.get("rows", self._rows())
            kwargs = {"rows": rows, "expected_rows_sha256": digest(rows),
                      "state": first["state"], "expected_state_sha256": first["state_sha256"],
                      "policy": self.policy, "expected_policy_sha256": digest(self.policy),
                      "observed_at": NOW, **changed}
            with self.subTest(label=label), \
                    mock.patch.object(activation, "rank_traces", side_effect=AssertionError("rank admission was late")), \
                    self.assertRaises(module.LiveLoopRefusal):
                module.rank_recall(**kwargs)

    def test_idle_refuses_valid_foreign_capture_or_missing_replay_without_partial_gist(self):
        module = self._module()
        self._inputs()
        first = self._prepare(module)
        foreign_capture = self.gist_source._fixture()
        foreign = self.gist_source.arguments(capture=foreign_capture)
        gist = importlib.import_module("siagist")
        # The separate gist API admits it; refusal below must be the loop's
        # source join, not malformed capture/replay or a broken gist producer.
        self.assertTrue(gist.replay_gist(**foreign)["artifact_json"])
        self.assertNotEqual(foreign["expected_capture_sha256"], self.gist_inputs["expected_capture_sha256"])
        with self.assertRaises(module.LiveLoopRefusal):
            self._prepare(module, **self._resume(first, observed_at=EXPIRED_AT), idle=True, gist_inputs=foreign)
        with self.assertRaises(module.LiveLoopRefusal):
            self._prepare(module, **self._resume(first, observed_at=EXPIRED_AT), idle=True, gist_inputs=None)
        with self.assertRaises(module.LiveLoopRefusal):
            self._prepare(module, gist_inputs=self.gist_inputs)
        wrong_pin = {**self.gist_inputs, "expected_capture_sha256": "0" * 64}
        with self.assertRaises(module.LiveLoopRefusal):
            self._prepare(module, **self._resume(first, observed_at=EXPIRED_AT), idle=True, gist_inputs=wrong_pin)
        self.assertEqual(first["gist_pages"], [])

    def test_rehashed_history_policy_omitted_or_fabricated_uses_and_legacy_tails_refuse(self):
        module = self._module()
        self._inputs()
        first = self._prepare(module)
        record = self._delivery(module, self._rank(module, first))
        result = self._prepare(module, **self._resume(first, observed_at=DELIVERED_AT),
                               **self._with_delivery(record))
        for label in ("policy", "missing-policy", "policy-pin", "omitted-use", "wrong-kind",
                      "native-clock", "unknown-version", "omitted-record", "future", "legacy-tail"):
            captured = copy.deepcopy(result["history_capture"])
            if label == "policy":
                captured["policy"]["novelty_admission"]["threshold"] = 1
                captured["policy_sha256"] = digest(captured["policy"])
            elif label == "missing-policy":
                del captured["policy"]["activation"]
                captured["policy_sha256"] = digest(captured["policy"])
            elif label == "policy-pin":
                captured["policy_sha256"] = "0" * 64
            elif label == "omitted-use":
                captured["uses"].pop()
            elif label == "wrong-kind":
                captured["uses"][0]["kind"] = "service-output-completed"
            elif label == "native-clock":
                captured["uses"][0]["timestamp"] = captured["intake"]["observations"][0]["native_timestamp"]
            elif label == "unknown-version":
                captured["uses"][0]["version_sha256"] = "0" * 64
            elif label == "omitted-record":
                captured["deliveries"]["records"] = []
            elif label == "future":
                captured["observed_at"] = NOW
            else:
                captured["intake"]["rt"] = [START, NOW]
                captured["scope"] = "legacy-recent-use-tail"
            captured["capture_sha256"] = own_digest(captured, "capture_sha256")
            with self.subTest(label=label), self.assertRaises(module.LiveLoopRefusal):
                module.admit_history_capture(captured, expected_capture_sha256=captured["capture_sha256"])
