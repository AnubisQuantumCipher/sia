"""Witnessed replay changes focused meaning accessibility, not source truth.

The scalar delta rule is an engineering abstraction, not Schapiro et al.'s
phased network or biological consolidation. Their Methods: Learning and
Testing and analyses motivate inspectable updates and frozen readout:
https://pmc.ncbi.nlm.nih.gov/articles/PMC5124075/

Only public deterministic signed fixtures are used. There are no private
queries, desired-answer inputs, model calls, or corpus-compaction calls.
"""

import copy
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    import sia_test_home
except ModuleNotFoundError:
    from tests import sia_test_home

from tests import test_calibration_benchmark as ledger_tests


POLICY = {
    "schema": "sia-replay-gist-policy-v1",
    "grammar": "native-attest-intent-outcome-v1",
    "learning": {
        "algorithm": "witnessed-completion-delta-v1", "enabled": True,
        "rate": {"numerator": 1, "denominator": 2}, "initial": "zero-v1",
    },
    "readout": {
        "cue_roster": "complete-derived-native-cues-v1",
        "threshold": {"numerator": 1, "denominator": 2},
        "slots_per_cue": 1, "tie_break": "first-source-occurrence-v1",
        "static_control": "first-source-occurrence-v1",
    },
    "fidelity": {
        "support": "distinct-captured-occurrences-v1",
        "exceptions": "complete-same-cue-completions-v1",
        "origins": "preserve-and-attribute-no-promotion-v1",
        "unsupported": "retain-and-classify-v1",
    },
    # Explicit engineering ceilings, not fitted neuroscience parameters.
    "limits": {
        "max_input_bytes": 16777216, "max_output_bytes": 16777216,
        "max_occurrences": 256, "max_replay_steps": 256,
        "max_cues": 256, "max_completions": 256,
        "max_weight_updates": 65536, "max_trace_cells": 65536,
        "max_text_bytes": 1048576, "max_rational_bits": 4096,
    },
}

# Direct JACKAL results observed before authoring the expected state values.
# Retain the echoed parsed input and full non-formal assurance boundary.
EXACT_FIXTURES = {
    "first_present": {"status": "exact", "parsed": "0+1/2*(1-0)", "exact": "1/2"},
    "repeat_present": {"status": "exact", "parsed": "1/2+1/2*(1-1/2)", "exact": "3/4"},
    "later_absent": {"status": "exact", "parsed": "1/2+1/2*(0-1/2)", "exact": "1/4"},
    "initial_absent": {"status": "exact", "parsed": "0+1/2*(0-0)", "exact": "0"},
    "present_margin": {"status": "exact", "parsed": "3/4-1/2", "exact": "1/4"},
    "absent_margin": {"status": "exact", "parsed": "1/4-1/2", "exact": "-1/4"},
    "threshold_tie": {"status": "exact", "parsed": "1/2-1/2", "exact": "0"},
}
EXACT_NON_CLAIMS = [
    "NOT formal-bounded: this lane carries no Lean-checked certificate",
    "The epistemic class above is the STRONGEST claim this result supports",
    "exact rational arithmetic (not yet checker-covered)",
]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def occurrence(event):
    return {key: event[key] for key in ("chain", "seq", "entry_hash")}


def rational(value):
    numerator, separator, denominator = value.partition("/")
    return {"numerator": numerator, "denominator": denominator if separator else "1"}


def schedule(capture, *sequences):
    events = {(event["chain"], event["seq"]): event for event in capture["events"]}
    return {"schema": "sia-gist-replay-v1", "steps": [
        {"id": "step-" + str(index),
         "occurrence": occurrence(events[("aegis", seq)])}
        for index, seq in enumerate(sequences)]}


class ReplayGist(unittest.TestCase):
    _base_capture = None

    def setUp(self):
        try:
            self.component = importlib.import_module("siagist")
        except ModuleNotFoundError as exc:
            self.fail("pure witnessed replay-gist component must exist: " + str(exc))
        self.history = importlib.import_module("siacognitivehistory")
        self.bench = ledger_tests.siabench
        if type(self)._base_capture is None:
            type(self)._base_capture = self._fixture()
        self.capture = copy.deepcopy(type(self)._base_capture)

    def _fixture(self, *, change_rows=None, model_sequence=None):
        """Construct only a private copy of the existing public signed fixture."""
        temporary = tempfile.TemporaryDirectory(prefix="sia-gist-fixture-")
        self.addCleanup(temporary.cleanup)
        state, corpus, registry = ledger_tests._signed_fixture(temporary.name)
        path = Path(registry["aegis"][0])
        rows = [line.split("\t") for line in path.read_text(encoding="utf-8").splitlines()]
        if change_rows is not None:
            change_rows(rows)
            key = ledger_tests.Ed25519PrivateKey.from_private_bytes(bytes.fromhex("01" * 32))
            previous = hashlib.sha256(b"attest-genesis-v1").hexdigest()
            for row in rows:
                row[7] = previous
                previous = self.bench._entry_hash(row)
                row[8] = key.sign(bytes.fromhex(previous)).hex()
            path.write_text("\n".join("\t".join(row) for row in rows) + "\n", encoding="utf-8")
            (Path(state) / "head.pin").write_text(f"{len(rows)} {previous}\n", encoding="utf-8")
            ledger_tests._write_projected_event_pages(corpus, "aegis", rows)
        if model_sequence is not None:
            row = next(row for row in rows if row[0] == model_sequence)
            page = Path(corpus) / "events" / "aegis" / (row[1].split("T")[0] + ".md")
            text = page.read_text(encoding="utf-8")
            page.write_text(text.replace("---\n", "---\norigin: model\n", 1), encoding="utf-8")
        return self.bench.build_ledger_dataset(
            corpus=corpus, chain_registry=registry, cognitive_history=True)["cognitive_history"]

    def arguments(self, *, capture=None, replay=None, policy=None):
        captured = self.capture if capture is None else capture
        replayed = schedule(captured, "1", "2") if replay is None else replay
        configured = copy.deepcopy(POLICY) if policy is None else policy
        return {"capture": captured, "expected_capture_sha256": captured["capture_sha256"],
                "replay": replayed, "expected_replay_sha256": sha(replayed),
                "policy": configured, "expected_policy_sha256": sha(configured)}

    def invoke(self, **options):
        return self.component.replay_gist(**self.arguments(**options))

    def artifact(self, result):
        self.assertEqual(set(result), {"artifact_json", "artifact_sha256"})
        self.assertIs(type(result["artifact_json"]), str)
        raw = result["artifact_json"].encode("utf-8")
        body = json.loads(raw)
        self.assertEqual(raw, canonical(body))
        self.assertEqual(result["artifact_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(body["schema"], "sia-replay-gist-v1")
        self.assertEqual(body["component"], "replay-gist")
        self.assertEqual(body["status"], "computed-unverified")
        self.assertTrue(body["non_claims"])
        return body

    def cue(self, body, subject="wireplumber.service"):
        return next(row for row in body["cues"] if row["chain"] == "aegis"
                    and row["operation"] == "restart" and row["subject"] == subject)

    def focused(self, body, value, *, subject="wireplumber.service", stage="OUTCOME"):
        cue = self.cue(body, subject)
        return next(row for row in body["candidates"] if row["cue_id"] == cue["id"]
                    and row["focus"]["stage"] == stage and row["focus"]["value"] == value)

    def selected(self, body, *, subject="wireplumber.service", static=False):
        cue = self.cue(body, subject)
        readout = body["static_readout"] if static else body["readout"]
        row = next(row for row in readout if row["cue_id"] == cue["id"])
        candidates = {item["id"]: item for item in body["candidates"]}
        return [candidates[identifier] for identifier in row["selected"]]

    def weight(self, body, value, *, state="final_state", subject="wireplumber.service", stage="OUTCOME"):
        candidate = self.focused(body, value, subject=subject, stage=stage)
        return next(row["weight"] for row in body[state]
                    if row["completion_id"] == candidate["completion_id"]
                    and row["cue_id"] == candidate["cue_id"])

    def bundle(self, candidate):
        raw = candidate["alternative_bundle_json"].encode("utf-8")
        value = json.loads(raw)
        self.assertEqual(raw, canonical(value))
        self.assertEqual(candidate["alternative_bundle_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertIn(candidate["alternative_bundle_json"], candidate["text"],
                      "every focused meaning must carry its complete alternative bundle")
        return value

    def assert_source_bundle(self, body, candidate):
        bundle = self.bundle(candidate)
        cue = self.cue(body)
        self.assertEqual(bundle["cue"], {key: cue[key] for key in ("chain", "operation", "subject")})
        actual = {row["completion"]["value"]: row for row in bundle["alternatives"]}
        self.assertEqual(set(actual), {"ok", "held"})
        events = {event["seq"]: event for event in body["capture"]["events"] if event["chain"] == "aegis"}
        pages = {page["slug"]: page for page in body["capture"]["pages"]}
        for value, seq in (("ok", "1"), ("held", "2")):
            row, event = actual[value], events[seq]
            self.assertEqual(row["occurrences"], [occurrence(event)])
            self.assertEqual(row["completion"]["stage"], "OUTCOME")
            page = pages[event["retention"]["source_slug"]]
            self.assertEqual(row["completion"]["origin"], page["origin"])
            self.assertEqual(len(row["witnesses"]), len(row["occurrences"]))
            for witness in row["witnesses"]:
                self.assertEqual(witness["occurrence"], occurrence(event))
                self.assertEqual(witness["page_slug"], page["slug"])
                self.assertEqual(witness["page_sha256"], page["sha256"])
                self.assertEqual(witness["event_id"], event["projection"]["event_id"])
                self.assertEqual(witness["excerpt"], event["retention"]["retrieval_excerpt"])
                source = page["text"].encode("utf-8")
                excerpt = witness["excerpt"].encode("utf-8")
                self.assertEqual(source[witness["start_byte"]:witness["end_byte"]], excerpt)
                self.assertIn(event["projection"]["event_id"], witness["excerpt"])
        return bundle

    def test_public_api_is_explicit_and_has_no_target_or_query_input(self):
        signature = inspect.signature(self.component.replay_gist)
        self.assertEqual(set(signature.parameters), {
            "capture", "expected_capture_sha256", "replay", "expected_replay_sha256",
            "policy", "expected_policy_sha256"})
        for name, parameter in signature.parameters.items():
            self.assertIs(parameter.default, inspect.Parameter.empty)
            if name != "capture":
                self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
        arguments = self.arguments()
        for name in ("query", "answer_key", "preferred_outcome", "candidate_ids", "previous_state"):
            with self.subTest(name=name), self.assertRaises(TypeError):
                self.component.replay_gist(**arguments, **{name: "ok"})

    def test_immutable_artifact_retains_complete_capture_replay_policy_and_pins(self):
        arguments = self.arguments()
        before = copy.deepcopy(arguments)
        result = self.component.replay_gist(**arguments)
        body = self.artifact(result)
        self.assertEqual(arguments, before)
        self.assertEqual(body["capture"], arguments["capture"])
        self.assertEqual(body["replay"], arguments["replay"])
        self.assertEqual(body["policy"], arguments["policy"])
        for name in ("capture", "replay", "policy"):
            self.assertEqual(body[name + "_sha256"], arguments["expected_" + name + "_sha256"])
        self.assertEqual([row["occurrence"] for row in body["occurrences"]],
                         [occurrence(event) for event in self.capture["events"]])
        before_text = result["artifact_json"]
        body["capture"]["pages"][0]["text"] = "caller-local edit"
        self.assertEqual(result["artifact_json"], before_text)
        self.assertEqual(arguments, before)

    def test_empty_replay_has_neutral_state_but_retains_static_meanings_and_all_sources(self):
        body = self.artifact(self.invoke(replay=schedule(self.capture)))
        self.assertEqual(body["initial_state"], body["final_state"])
        self.assertEqual(body["replay_trace"], [])
        self.assertEqual(self.weight(body, "ok"), rational(EXACT_FIXTURES["initial_absent"]["exact"]))
        self.assertEqual(self.weight(body, "held"), rational(EXACT_FIXTURES["initial_absent"]["exact"]))
        self.assertEqual(self.selected(body), [])
        self.assertEqual([row["focus"]["value"] for row in self.selected(body, static=True)], ["ok"])
        self.assertEqual(body["capture"], self.capture)
        for candidate in self.selected(body, static=True):
            self.assert_source_bundle(body, candidate)

    def test_repeated_replay_changes_rational_accessibility_not_distinct_support(self):
        once = self.artifact(self.invoke(replay=schedule(self.capture, "1")))
        twice = self.artifact(self.invoke(replay=schedule(self.capture, "1", "1")))
        self.assertEqual(self.weight(once, "ok"), rational(EXACT_FIXTURES["first_present"]["exact"]))
        self.assertEqual(self.weight(twice, "ok"), rational(EXACT_FIXTURES["repeat_present"]["exact"]))
        self.assertEqual(once["candidates"], twice["candidates"])
        self.assertEqual(once["occurrences"], twice["occurrences"])
        self.assertEqual(once["capture"], twice["capture"])
        self.assertNotEqual(once["final_state"], twice["final_state"])
        self.assert_source_bundle(twice, self.selected(twice)[0])

    def test_order_changes_selected_focused_meaning_with_identical_source_and_static_control(self):
        forward = self.artifact(self.invoke(replay=schedule(self.capture, "1", "2")))
        reverse = self.artifact(self.invoke(replay=schedule(self.capture, "2", "1")))
        self.assertEqual(self.weight(forward, "ok"), rational(EXACT_FIXTURES["later_absent"]["exact"]))
        self.assertEqual(self.weight(forward, "held"), rational(EXACT_FIXTURES["first_present"]["exact"]))
        self.assertEqual(self.weight(reverse, "ok"), rational(EXACT_FIXTURES["first_present"]["exact"]))
        self.assertEqual(self.weight(reverse, "held"), rational(EXACT_FIXTURES["later_absent"]["exact"]))
        self.assertEqual(forward["candidates"], reverse["candidates"])
        self.assertEqual(forward["static_readout"], reverse["static_readout"])
        self.assertEqual(forward["capture"], reverse["capture"])
        selected_forward, selected_reverse = self.selected(forward)[0], self.selected(reverse)[0]
        self.assertEqual(selected_forward["focus"]["value"], "held")
        self.assertEqual(selected_reverse["focus"]["value"], "ok")
        self.assertNotEqual(selected_forward["id"], selected_reverse["id"])
        self.assertNotEqual(selected_forward["text"], selected_reverse["text"],
                            "the causal effect must select different focused meaning text")
        self.assertEqual(selected_forward["alternative_bundle_json"],
                         selected_reverse["alternative_bundle_json"])
        self.assert_source_bundle(forward, selected_forward)
        self.assert_source_bundle(reverse, selected_reverse)

    def test_each_candidate_declares_its_focus_before_the_shared_complete_alternatives(self):
        body = self.artifact(self.invoke())
        for value in ("ok", "held"):
            candidate = self.focused(body, value)
            self.assertEqual(set(candidate["focus"]), {"stage", "value", "origin"})
            prefix, separator, _tail = candidate["text"].partition(candidate["alternative_bundle_json"])
            self.assertTrue(separator)
            self.assertTrue(prefix.startswith("Recorded focus:"))
            self.assertIn(json.dumps(value), prefix)
            self.assertIn("OUTCOME", prefix)
            self.assertIn("wireplumber.service", prefix)
            self.assert_source_bundle(body, candidate)

    def test_disabled_learning_replays_targets_but_cannot_change_neutral_accessibility(self):
        policy = copy.deepcopy(POLICY)
        policy["learning"]["enabled"] = False
        learned = self.artifact(self.invoke())
        disabled = self.artifact(self.invoke(policy=policy))
        self.assertEqual(disabled["initial_state"], disabled["final_state"])
        self.assertEqual(self.selected(disabled), [])
        self.assertEqual(disabled["candidates"], learned["candidates"])
        self.assertEqual(disabled["static_readout"], learned["static_readout"])
        self.assertEqual([row["target_completion_id"] for row in disabled["replay_trace"]],
                         [row["target_completion_id"] for row in learned["replay_trace"]])
        for step in disabled["replay_trace"]:
            for update in step["updates"]:
                self.assertEqual(update["before"], update["after"])

    def test_replay_trace_exposes_every_same_cue_target_and_weight_transition(self):
        body = self.artifact(self.invoke())
        steps = body["replay_trace"]
        self.assertEqual([row["step_id"] for row in steps],
                         [row["id"] for row in body["replay"]["steps"]])
        self.assertEqual([row["occurrence"] for row in steps],
                         [row["occurrence"] for row in body["replay"]["steps"]])
        ok, held = self.focused(body, "ok"), self.focused(body, "held")
        first = {row["completion_id"]: row for row in steps[0]["updates"]}
        last = {row["completion_id"]: row for row in steps[-1]["updates"]}
        self.assertEqual(set(first), {ok["completion_id"], held["completion_id"]})
        self.assertEqual(set(last), set(first))
        self.assertEqual(first[ok["completion_id"]]["target"], 1)
        self.assertEqual(first[held["completion_id"]]["target"], 0)
        self.assertEqual(last[ok["completion_id"]]["target"], 0)
        self.assertEqual(last[held["completion_id"]]["target"], 1)
        self.assertEqual(last[ok["completion_id"]]["before"], first[ok["completion_id"]]["after"])
        self.assertEqual(last[ok["completion_id"]]["after"],
                         rational(EXACT_FIXTURES["later_absent"]["exact"]))
        self.assertEqual(self.weight(body, "requested", subject="pipewire.service", stage="INTENT"),
                         rational(EXACT_FIXTURES["initial_absent"]["exact"]))

    def test_readout_cue_roster_is_complete_and_never_derived_from_replay_targets(self):
        no_replay = self.artifact(self.invoke(replay=schedule(self.capture)))
        pipewire = self.artifact(self.invoke(replay=schedule(self.capture, "3")))
        self.assertEqual(no_replay["cues"], pipewire["cues"])
        expected = [row["id"] for row in pipewire["cues"]]
        self.assertEqual([row["cue_id"] for row in pipewire["readout"]], expected)
        self.assertEqual([row["cue_id"] for row in pipewire["static_readout"]], expected)
        self.assertEqual(self.selected(pipewire), [])
        selected = self.selected(pipewire, subject="pipewire.service")
        self.assertEqual([row["focus"]["stage"] for row in selected], ["INTENT"])
        self.assertEqual([row["focus"]["value"] for row in selected], ["requested"])
        self.assertNotIn("caused", selected[0]["text"].casefold())

    def test_binding_changes_cannot_turn_intention_into_completed_outcome(self):
        def replace_stage(rows):
            next(row for row in rows if row[0] == "1")[2] = "INTENT:restart"
        captured = self._fixture(change_rows=replace_stage)
        body = self.artifact(self.invoke(capture=captured, replay=schedule(captured, "1")))
        selected = self.selected(body)
        self.assertEqual(selected[0]["focus"]["stage"], "INTENT")
        self.assertEqual(selected[0]["focus"]["value"], "ok")
        self.assertFalse(any(row["focus"]["stage"] == "OUTCOME" and row["focus"]["value"] == "ok"
                             for row in body["candidates"] if row["cue_id"] == self.cue(body)["id"]))
        self.assertIn("held", selected[0]["alternative_bundle_json"])

    def test_negative_and_conditional_value_bytes_survive_focus_alternatives_and_replay(self):
        qualifier = "not ok unless a user approves; λ remains conditional"
        def replace_value(rows):
            next(row for row in rows if row[0] == "2")[4] = qualifier
        captured = self._fixture(change_rows=replace_value)
        body = self.artifact(self.invoke(capture=captured, replay=schedule(captured, "1", "1")))
        focused = self.selected(body)[0]
        self.assertEqual(focused["focus"]["value"], "ok")
        alternative = next(row for row in self.bundle(focused)["alternatives"]
                           if row["completion"]["value"] == qualifier)
        self.assertEqual(alternative["completion"]["value"].encode("utf-8"), qualifier.encode("utf-8"))
        self.assertIn(qualifier, focused["text"])
        self.assertEqual(body["capture"], captured)

    def test_model_source_origin_is_not_promoted_by_signed_rows_or_repeated_replay(self):
        captured = self._fixture(model_sequence="1")
        body = self.artifact(self.invoke(capture=captured, replay=schedule(captured, "1", "1")))
        focused = self.selected(body)[0]
        self.assertEqual(focused["focus"]["origin"], "model")
        self.assert_source_bundle(body, focused)
        self.assertEqual(body["capture"], captured)
        self.assertNotIn("verified-true", focused["text"])

    def test_incomplete_required_witness_makes_cue_ineligible_without_removing_capture(self):
        captured = copy.deepcopy(self.capture)
        event = next(event for event in captured["events"] if event["chain"] == "aegis" and event["seq"] == "2")
        slug = event["retention"]["source_slug"]
        event["retention"] = {
            "status": "no-admitted-witness", "witness_kind": None, "source_slug": None,
            "index_file": None, "retrieval_excerpt": None,
            "projected_event_retained": False, "value_answer_retained": False,
        }
        next(page for page in captured["pages"] if page["slug"] == slug)["role"] = "inspected-only"
        captured["capture_sha256"] = sha({key: value for key, value in captured.items() if key != "capture_sha256"})
        # Fixture control: this remains an admitted complete native-row store,
        # not a malformed capture that would make the desired refusal vacuous.
        self.history.admit_capture(captured)
        body = self.artifact(self.invoke(capture=captured, replay=schedule(captured, "1", "1")))
        cue = self.cue(body)
        self.assertFalse(cue["eligible"])
        self.assertEqual(cue["reason"], "incomplete-required-witness")
        self.assertEqual(self.selected(body), [])
        self.assertEqual(self.selected(body, static=True), [])
        self.assertEqual(body["capture"], captured)
        self.assertEqual([row["occurrence"] for row in body["occurrences"]],
                         [occurrence(item) for item in captured["events"]])

    def test_unsupported_native_rows_remain_explicit_and_cannot_be_replayed_as_gist_facts(self):
        body = self.artifact(self.invoke())
        unsupported = next(row for row in body["occurrences"] if row["occurrence"]["seq"] == "5")
        self.assertEqual(unsupported["status"], "unsupported")
        self.assertEqual(unsupported["reason"], "unsupported-action-stage")
        self.assertIsNone(unsupported["cue_id"])
        with self.assertRaises(self.component.GistRefusal):
            self.invoke(replay=schedule(self.capture, "5"))

    def test_external_pins_are_required_even_when_internal_capture_hash_is_valid(self):
        for field in ("expected_capture_sha256", "expected_replay_sha256", "expected_policy_sha256"):
            for invalid in (None, "f" * 64):
                arguments = self.arguments()
                arguments[field] = invalid
                with self.subTest(field=field, invalid=invalid), self.assertRaises(self.component.GistRefusal):
                    self.component.replay_gist(**arguments)

    def test_capture_proposition_origin_and_native_occurrence_substitutions_do_not_admit(self):
        for field in ("native-row", "projection", "origin", "page"):
            captured = copy.deepcopy(self.capture)
            event = next(event for event in captured["events"] if event["seq"] == "1")
            if field == "native-row":
                event["row"][4] = "a substituted outcome"
            elif field == "projection":
                event["projection"]["summary"] = "a substituted proposition"
            elif field == "origin":
                captured["pages"][0]["origin"] = "model"
            else:
                captured["pages"][0]["text"] += "\nchanged source bytes\n"
            # Rehashing the enclosing capture is not a replacement for its
            # native-row, projection, origin and source-byte admission.
            captured["capture_sha256"] = sha({key: value for key, value in captured.items() if key != "capture_sha256"})
            with self.subTest(field=field), self.assertRaises(self.component.GistRefusal):
                self.invoke(capture=captured, replay=schedule(captured))

    def test_all_policy_fields_are_required_and_closed(self):
        paths = [(key,) for key in POLICY]
        for section in ("learning", "readout", "fidelity", "limits"):
            paths.extend((section, key) for key in POLICY[section])
        for path in paths:
            policy = copy.deepcopy(POLICY)
            owner = policy if len(path) == 1 else policy[path[0]]
            del owner[path[-1]]
            with self.subTest(missing=path), self.assertRaises(self.component.GistRefusal):
                self.invoke(policy=policy)
        for section in (None, "learning", "readout", "fidelity", "limits"):
            policy = copy.deepcopy(POLICY)
            owner = policy if section is None else policy[section]
            owner["preferred_outcome"] = "ok"
            with self.subTest(extra=section), self.assertRaises(self.component.GistRefusal):
                self.invoke(policy=policy)

    def test_rational_domain_and_noncanonical_parameters_refuse_without_float_coercion(self):
        invalid = ({"numerator": True, "denominator": 2},
                   {"numerator": 1.0, "denominator": 2},
                   {"numerator": "1", "denominator": "2"},
                   {"numerator": 1, "denominator": 0},
                   {"numerator": -1, "denominator": 2},
                   {"numerator": 0, "denominator": 1},
                   {"numerator": 2, "denominator": 1},
                   {"numerator": 2, "denominator": 4},
                   {"numerator": float("nan"), "denominator": 1})
        for section, name in (("learning", "rate"), ("readout", "threshold")):
            for value in invalid:
                policy = copy.deepcopy(POLICY)
                policy[section][name] = value
                arguments = self.arguments()
                arguments["policy"] = policy
                try:
                    # Finite invalid-domain cases have matching external pins:
                    # a pin mismatch must not make their refusal vacuous.
                    arguments["expected_policy_sha256"] = sha(policy)
                except ValueError:
                    # NaN is unencodable. It must fail structural admission,
                    # before any policy hash or rational construction occurs.
                    arguments["expected_policy_sha256"] = "a" * 64
                with self.subTest(section=section, value=value), \
                        mock.patch.object(self.component.hashlib, "sha256", side_effect=AssertionError("hash before rational admission")), \
                        mock.patch.object(self.component, "Fraction", side_effect=AssertionError("fraction before rational admission")):
                    with self.assertRaises(self.component.GistRefusal):
                        self.component.replay_gist(**arguments)

    def test_policy_cannot_change_grammar_source_fidelity_or_target_blind_readout_contracts(self):
        paths = [("schema",), ("grammar",), ("learning", "algorithm"),
                 ("learning", "initial"), ("readout", "cue_roster"),
                 ("readout", "tie_break"), ("readout", "static_control")]
        paths.extend(("fidelity", name) for name in POLICY["fidelity"])
        for path in paths:
            policy = copy.deepcopy(POLICY)
            owner = policy if len(path) == 1 else policy[path[0]]
            owner[path[-1]] = "unapproved-contract"
            with self.subTest(path=path), self.assertRaises(self.component.GistRefusal):
                self.invoke(policy=policy)
        for value in (True, 0, -1, "1", 1.0):
            policy = copy.deepcopy(POLICY)
            policy["readout"]["slots_per_cue"] = value
            with self.subTest(slots=value), self.assertRaises(self.component.GistRefusal):
                self.invoke(policy=policy)

    def test_complete_late_replay_reference_admission_precedes_copy_hash_and_fraction(self):
        replay = schedule(self.capture, "1", "2")
        replay["steps"][-1]["occurrence"]["entry_hash"] = "f" * 64
        arguments = self.arguments(replay=replay)
        before = copy.deepcopy(arguments)
        with mock.patch.object(self.component.copy, "deepcopy", side_effect=AssertionError("copy before admission")), \
                mock.patch.object(self.component.hashlib, "sha256", side_effect=AssertionError("hash before admission")), \
                mock.patch.object(self.component, "Fraction", side_effect=AssertionError("learning before admission")):
            with self.assertRaises(self.component.GistRefusal):
                self.component.replay_gist(**arguments)
        self.assertEqual(arguments, before)

    def test_byte_work_trace_and_rational_budgets_admit_before_copy_hash_and_learning(self):
        for field in ("max_input_bytes", "max_output_bytes", "max_occurrences", "max_replay_steps",
                      "max_cues", "max_completions", "max_weight_updates", "max_trace_cells",
                      "max_text_bytes", "max_rational_bits"):
            policy = copy.deepcopy(POLICY)
            policy["limits"][field] = 1
            arguments = self.arguments(policy=policy)
            with self.subTest(field=field), \
                    mock.patch.object(self.component.copy, "deepcopy", side_effect=AssertionError("copy before budget")), \
                    mock.patch.object(self.component.hashlib, "sha256", side_effect=AssertionError("hash before budget")), \
                    mock.patch.object(self.component, "Fraction", side_effect=AssertionError("learning before budget")):
                with self.assertRaises(self.component.GistRefusal):
                    self.component.replay_gist(**arguments)

    def test_replay_and_limit_shapes_are_closed_exact_types_without_silent_truncation(self):
        invalid = []
        replay = schedule(self.capture, "1", "2")
        replay["steps"][-1]["id"] = replay["steps"][0]["id"]
        invalid.append(replay)
        replay = schedule(self.capture, "1")
        replay["steps"][0]["preferred_outcome"] = "ok"
        invalid.append(replay)
        invalid.extend(({"schema": "sia-gist-replay-v1", "steps": None},
                        {"schema": "sia-gist-replay-v1", "steps": [], "complete": True}))
        for replay in invalid:
            with self.subTest(replay=replay), self.assertRaises(self.component.GistRefusal):
                self.invoke(replay=replay)
        for field in POLICY["limits"]:
            for value in (True, 0, -1, "256"):
                policy = copy.deepcopy(POLICY)
                policy["limits"][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(self.component.GistRefusal):
                    self.invoke(policy=policy)
        for value in (None, 1, "yes"):
            policy = copy.deepcopy(POLICY)
            policy["learning"]["enabled"] = value
            with self.subTest(enabled=value), self.assertRaises(self.component.GistRefusal):
                self.invoke(policy=policy)

    def test_no_clock_model_files_processes_compaction_or_publication_are_used(self):
        arguments = self.arguments()
        with mock.patch("builtins.open", side_effect=AssertionError("opened path")), \
                mock.patch("os.open", side_effect=AssertionError("opened descriptor")), \
                mock.patch("subprocess.run", side_effect=AssertionError("launched child")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("launched process")), \
                mock.patch("time.time", side_effect=AssertionError("ambient clock")), \
                mock.patch.object(self.history.sialib, "consolidate_corpus", side_effect=AssertionError("old compaction")), \
                mock.patch.object(self.history.sialib, "gbrain", side_effect=AssertionError("resident/model access")):
            first = self.component.replay_gist(**arguments)
            second = self.component.replay_gist(**arguments)
        self.assertEqual(first, second)
        body = self.artifact(first)
        for forbidden in ("published", "durable", "heldout_win", "biological_consolidation", "causal_recovery"):
            self.assertNotIn(forbidden, body)
        claims = " ".join(body["non_claims"]).casefold()
        for boundary in ("engineering", "origin", "replay", "authenticate", "publication", "biological"):
            self.assertIn(boundary, claims)


if __name__ == "__main__":
    unittest.main()
