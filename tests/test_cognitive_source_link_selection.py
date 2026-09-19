"""RED contract for an additive source-link join construction, not a result.

These are public synthetic signed-ledger fixtures. They are not claims that
any real machine history contains a usable join. Root alone runs this suite.

The new schema is deliberately NOT accepted by selection-v2, the existing raw
baseline, or its metric protocol. An independently tested adapter is future
work. This module adds no rank worker: public_queries is the target-blind
handoff boundary, and must replay the private selection before projecting it.

Frozen fixture policy below declares every selection/split rule. A relation
means that deterministic SIA projection of a signed arg1 subject generated a
non-organ unit link, independently retained in that occurrence's native line.
It does not mean the source signed a graph edge or asserted entity equivalence.
SEKHMET arg2 fallback and other source grammars are explicitly unsupported.
GENESIS-prefixed rows remain in event_population but never supply relations,
subject dependencies, queries, or the supported/unsupported non-genesis roster.

For every supported seed, enumerate each DIFFERENT native action of the exact
same chain/arg1 subject from the COMPLETE captured row population. Targets are
ALL occurrences of that counterpart action; unavailable targets are never
removed. Each seed-to-target path must cross source pages, all excerpts must
fit the real UTF-8 chunker, and one chunk per page must cover its whole support.

Dependency components are built BEFORE any witness eligibility/exclusions.
Nodes are exact chain/arg1 subjects, generated bridges, and native source pages;
an occurrence joins its subject, bridge, and every captured page containing its
exact native marker line. This includes inspected-only/non-evidence pages and
rows whose capture projection is absent. Group dependencies and occurrence
rosters are sorted canonically. ID = SHA256(canonical([
  'sia-cognitive-source-link-group-v1', dependencies
])). Split residue = int(SHA256(canonical([
  'sia-cognitive-source-link-split-v1', seed, group_id
])), 16) modulo calibration_modulus. No expected residue is invented here.
Every shared dependency therefore stays in one partition for this capture;
new captures can merge components, so longitudinal split stability is unclaimed.
Query ID = SHA256(canonical(['sia-cognitive-source-link-query-v1',
seed_occurrence, counterpart_action])); the seed occurrence includes its native
entry hash as well as its generation-stable event ID. Output query order is
ascending query ID, and each query contains exactly id/text/group_id/split.

All byte/count ceilings below are observed existing capture/preparer/adapter
ceilings or explicit fixture policy choices, not derived numerical results.
No retrieval scores, latency, fractions, or power calculations occur here.
"""

import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests import test_cognitive_history_capture as capture_tests


ledger_tests = capture_tests.ledger_tests
sha = capture_tests.sha
canonical = capture_tests.canonical

NON_CLAIMS = [
    "Source-link join is an engineering retrieval task, not demonstrated associative cognition or a causal relationship.",
    "Native signed subjects and deterministic SIA-generated links are different provenance layers; shared links do not establish entity equivalence.",
    "Only the declared SEKHMET arg1 projection is supported; unsupported sources and rows do not establish absent relationships.",
    "The complete captured signed population is not the entire machine history or corpus.",
    "Dependency components prevent shared declared subjects, bridges, occurrences, and source pages across query splits for this capture; authentication anchors remain shared.",
    "This is not a temporal holdout, and later captures may merge dependency components and change assignments.",
    "The seed event ID is a disclosed public cue bound to this capture, not an independently content-authenticating identifier.",
    "Unavailable witnesses are declared; a retained subset is never substituted for a complete counterpart target set.",
    "Page origins remain controlling; generated links and signed-row matches do not promote model or legacy-unlabeled pages to evidence.",
    "This schema is not a drop-in selection-v2, baseline, or measurement input; an independently tested adapter is required.",
    "No retrieval worker, metric, tuned parameters, statistical power, cognitive improvement, or real-source availability is established.",
    "Capture and policy hashes bind represented bytes; external authentication remains the caller's obligation.",
]


def policy_fixture():
    """Public, untuned fixture policy; not a real calibration parameter freeze."""
    return {
        "schema": "sia-cognitive-source-link-policy-v1",
        "seed": "public-source-link-fixture-v1",
        "population": "complete-captured-signed-rows-v1",
        "relations": {
            "projection": "sekhmet-native-arg1-unit-link-v1",
            "native_subject": "exact-chain-arg1-v1",
            "link_provenance": "deterministic-signed-row-projection-v1",
            "collision": "refuse-distinct-native-subjects-sharing-bridge-v1",
            "unsupported": "declare-source-and-row-roster-v1",
        },
        "split": {
            "kind": "dependency-components-before-eligibility-v1",
            "dependencies": "bridge-chain-arg1-native-source-page-v1",
            "calibration_modulus": 5,
            "calibration_residue": 0,
        },
        "queries": {
            "template": "seed-event-id-counterpart-action-v1",
            "targets": "all-complete-exact-subject-counterpart-occurrences-v1",
            "actions": "different-from-seed-native-action-v1",
            "witnesses": "exact-native-line-and-generated-link-v1",
            "origin": "evidence-only-support-v1",
            "page_relation": "every-seed-target-page-distinct-v1",
            "shortcuts": "exclude-whole-query-v1",
        },
        "pages": {
            "order": "seeded-slug-sha256-v1",
            "title": "slug-v1",
            "max_pages": 256,
            "max_page_bytes": 131072,
            "max_total_page_bytes": 4194304,
            "max_chunks": 4096,
        },
        "protocol": {
            "chunking": "utf8-contiguous-codepoint-v1",
            "max_chunk_bytes": 2048,
            "page_pooling": "single-chunk-per-slug",
            "max_query_bytes": 8000,
        },
        "resources": {
            "max_capture_bytes": 16777216,
            "max_policy_bytes": 2097152,
            "max_selection_bytes": 16777216,
            "max_events": 65536,
            "max_relations": 65536,
            "max_dependency_groups": 65536,
            "max_queries": 64,
            "overflow": "refuse-complete-request-v1",
        },
        "require_queries": False,
    }


def rehash(value, field):
    value[field] = sha(canonical({key: child for key, child in value.items()
                                  if key != field}))
    return value


def occurrence(event):
    return {"chain": event["chain"], "seq": event["seq"],
            "entry_hash": event["entry_hash"],
            "event_id": event["projection"]["event_id"]}


def public_text(seed, action):
    return (
        "In the captured signed sekhmet chain, which occurrences of exact action "
        + json.dumps(action, ensure_ascii=False)
        + " share the explicitly projected non-organ link of seed event "
        + json.dumps(seed["event_id"], ensure_ascii=False)
        + "? Return every counterpart occurrence with the seed and counterpart "
          "source witnesses; this asks for shared source links, not causation."
    )


class CognitiveSourceLinkSelection(unittest.TestCase):
    def setUp(self):
        self.bench = ledger_tests.siabench
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state, self.corpus, old_registry = ledger_tests._signed_fixture(
            self.temp.name)
        self.registry = {"sekhmet": old_registry["aegis"]}
        rows = self._rows()
        for row, action, subject, value in zip(rows[1:], (
                "INTENT:restart", "OUTCOME:restart", "OUTCOME:restart",
                "INTENT:restart", "OUTCOME:restart"), (
                "wireplumber.service", "wireplumber.service", "wireplumber.service",
                "pipewire.service", "pipewire.service"), (
                "requested", "ok", "held", "requested", "ok")):
            row[2:5] = [action, subject, value]
        self._resign(rows)

    def _module(self):
        try:
            module = importlib.import_module("siacognitivesourcelink")
        except ModuleNotFoundError as exc:
            self.fail("additive source-link selection API must exist: " + str(exc))
        for name in ("select_source_links", "admit_selection", "public_queries"):
            self.assertTrue(callable(getattr(module, name, None)), name)
        self.assertTrue(hasattr(module, "SourceLinkRefusal"))
        return module

    def _rows(self):
        return [line.split("\t") for line in
                Path(self.registry["sekhmet"][0]).read_text(encoding="utf-8").splitlines()]

    def _resign(self, rows):
        """Only fixture-owned public deterministic keys, ledgers, and pages."""
        key = ledger_tests.Ed25519PrivateKey.from_private_bytes(
            bytes.fromhex("01" * 32))
        previous = sha(b"attest-genesis-v1")
        for row in rows:
            row[7] = previous
            previous = self.bench._entry_hash(row)
            row[8] = key.sign(bytes.fromhex(previous)).hex()
        Path(self.registry["sekhmet"][0]).write_text(
            "\n".join("\t".join(row) for row in rows) + "\n", encoding="utf-8")
        (Path(self.state) / "head.pin").write_text(
            f"{len(rows)} {previous}\n", encoding="utf-8")
        ledger_tests._write_projected_event_pages(self.corpus, "sekhmet", rows)

    def _capture(self):
        return self.bench.build_ledger_dataset(
            corpus=self.corpus, chain_registry=self.registry,
            cognitive_history=True)["cognitive_history"]

    def _source(self, day):
        return Path(self.corpus) / "events" / "sekhmet" / (day + ".md")

    def _pins(self, capture, policy):
        return {"capture": capture, "policy": policy,
                "expected_capture_sha256": capture["capture_sha256"],
                "expected_policy_sha256": sha(canonical(policy))}

    def _select(self, module, capture=None, policy=None):
        capture = self._capture() if capture is None else capture
        policy = policy_fixture() if policy is None else policy
        return module.select_source_links(**self._pins(capture, policy))

    def _event(self, capture, seq):
        return next(event for event in capture["events"]
                    if event["chain"] == "sekhmet" and event["seq"] == seq)

    def _answer(self, result, seed="1", action="OUTCOME:restart"):
        return next(answer for answer in result["answer_key"]
                    if answer["seed"]["seq"] == seed
                    and answer["counterpart_action"] == action)

    def _seed_answers(self, result, seed):
        return [answer for answer in result["answer_key"]
                if answer["seed"]["seq"] == seed]

    def _reasons(self, result):
        return {row["reason"] for row in result["exclusions"]}

    def test_public_additive_apis_exist(self):
        self._module()

    def test_deterministic_detached_pure_replay_and_closed_output(self):
        module = self._module()
        capture, policy = self._capture(), policy_fixture()
        before = copy.deepcopy((capture, policy))
        kwargs = self._pins(capture, policy)
        with mock.patch("builtins.open", side_effect=AssertionError("pure selector opened a path")), \
                mock.patch("os.open", side_effect=AssertionError("pure selector opened a descriptor")), \
                mock.patch("subprocess.run", side_effect=AssertionError("pure selector launched a child")):
            result = module.select_source_links(**kwargs)
            repeated = module.select_source_links(**kwargs)
            admitted = module.admit_selection(result, **kwargs)
        self.assertEqual((capture, policy), before)
        self.assertEqual(result, repeated)
        self.assertEqual(result, admitted)
        self.assertIsNot(result, admitted)
        self.assertIsNot(result["answer_key"], admitted["answer_key"])
        self.assertEqual(set(result), {
            "schema", "capture_sha256", "policy_sha256", "pages", "pages_sha256",
            "event_population", "source_coverage", "relations", "dependency_groups",
            "queries", "answer_key", "exclusions", "source_non_claims", "non_claims",
            "selection_sha256"})
        self.assertEqual(result["schema"], "sia-cognitive-source-link-selection-v1")
        self.assertEqual(result["capture_sha256"], capture["capture_sha256"])
        self.assertEqual(result["policy_sha256"], sha(canonical(policy)))
        self.assertEqual(result["event_population"], capture["events"])
        for query in result["queries"]:
            self.assertEqual(set(query), {"id", "text", "group_id", "split"})
        self.assertEqual([query["id"] for query in result["queries"]],
                         sorted(query["id"] for query in result["queries"]))
        self.assertEqual(result["pages_sha256"], sha(canonical(result["pages"])))
        self.assertEqual(result["selection_sha256"], rehash(
            copy.deepcopy(result), "selection_sha256")["selection_sha256"])
        result["pages"][0]["text"] = "detached"
        self.assertEqual((capture, policy), before)
        self.assertNotEqual(result, admitted)

    def test_real_capture_admission_not_only_capture_selfhash_is_required(self):
        module = self._module()
        history = importlib.import_module("siacognitivehistory")
        capture, policy = self._capture(), policy_fixture()
        with mock.patch.object(history, "admit_capture", wraps=history.admit_capture) as gate:
            self._select(module, capture, policy)
        gate.assert_called()
        for edit in ("row", "projection", "page", "event-population"):
            broken = copy.deepcopy(capture)
            if edit == "row":
                self._event(broken, "2")["row"][4] = "forged"
            elif edit == "projection":
                self._event(broken, "2")["projection"]["links"].append("units/foreign")
            elif edit == "page":
                broken["pages"][0]["text"] += "unbound page replacement"
            else:
                broken["events"].remove(self._event(broken, "2"))
            rehash(broken, "capture_sha256")
            with self.subTest(edit=edit), self.assertRaises(module.SourceLinkRefusal):
                self._select(module, broken, policy)

    def test_wrong_external_capture_and_policy_pins_refuse(self):
        module = self._module()
        capture, policy = self._capture(), policy_fixture()
        for name in ("expected_capture_sha256", "expected_policy_sha256"):
            kwargs = self._pins(capture, policy)
            kwargs[name] = "0" * 64
            with self.subTest(name=name), self.assertRaises(module.SourceLinkRefusal):
                module.select_source_links(**kwargs)

    def test_closed_policy_refuses_wrong_types_extra_fields_and_rule_changes(self):
        module = self._module()
        capture = self._capture()
        cases = [
            (None, "schema", "sia-cognitive-selection-policy-v2"),
            (None, "seed", ""), (None, "require_queries", 1),
            (None, "scores", {}), (None, "answer_key", []),
            ("relations", "projection", "infer-links-from-prose"),
            ("relations", "collision", "merge-aliases"),
            ("split", "kind", "independent-query"),
            ("split", "calibration_modulus", True),
            ("split", "calibration_residue", 5),
            ("queries", "targets", "retained-only"),
            ("queries", "origin", "promote-signed-matches"),
            ("resources", "overflow", "clip"),
            ("resources", "max_queries", False),
            ("resources", "max_events", 0),
            ("protocol", "max_chunk_bytes", 1),
            ("protocol", "page_pooling", "all-chunks"),
        ]
        for section, key, value in cases:
            policy = policy_fixture()
            (policy if section is None else policy[section])[key] = value
            with self.subTest(section=section, key=key), self.assertRaises(module.SourceLinkRefusal):
                self._select(module, capture, policy)

    def test_all_input_structure_is_bounded_before_hashing_or_copying(self):
        module = self._module()
        capture, policy = self._capture(), policy_fixture()
        variants = []
        excessive = copy.deepcopy(policy)
        excessive["resources"]["max_capture_bytes"] = 1
        variants.append((capture, excessive))
        cyclic = copy.deepcopy(capture)
        cyclic["unexpected"] = cyclic
        variants.append((cyclic, policy))
        wrong = copy.deepcopy(policy)
        wrong["seed"] = float("inf")
        variants.append((capture, wrong))
        exotic = copy.deepcopy(capture)
        exotic["unexpected"] = object()
        variants.append((exotic, policy))
        for supplied, selected_policy in variants:
            kwargs = {"capture": supplied, "policy": selected_policy,
                      "expected_capture_sha256": capture["capture_sha256"],
                      "expected_policy_sha256": "0" * 64}
            with mock.patch("copy.deepcopy", side_effect=AssertionError("copied before full admission")), \
                    mock.patch("json.dumps", side_effect=AssertionError("serialized before full admission")), \
                    self.assertRaises(module.SourceLinkRefusal):
                module.select_source_links(**kwargs)

    def test_complete_counterpart_occurrences_not_only_one_convenient_target(self):
        module = self._module()
        capture = self._capture()
        result = self._select(module, capture)
        answer = self._answer(result)
        expected = [occurrence(self._event(capture, seq)) for seq in ("2", "3")]
        self.assertEqual(answer["class"], "source-link-join")
        self.assertEqual(answer["seed"], occurrence(self._event(capture, "1")))
        self.assertEqual(answer["targets"], expected)
        self.assertEqual(answer["native_subject"], {
            "chain": "sekhmet", "field": "arg1", "value": "wireplumber.service"})
        self.assertEqual(answer["bridge"], "units/wireplumber")
        support = answer["support"]
        self.assertEqual([item["occurrence"] for item in support],
                         [answer["seed"], *expected])
        self.assertEqual([item["role"] for item in support],
                         ["seed", *["target" for _ in expected]])
        seed_page = support[0]["witness"]["source_slug"]
        self.assertTrue(all(item["witness"]["source_slug"] != seed_page
                            for item in support if item["role"] == "target"))
        coverage = next(row for row in result["source_coverage"] if row["chain"] == "sekhmet")
        self.assertEqual(coverage["status"], "supported")
        self.assertEqual(coverage["supported_sequences"], [row[0] for row in self._rows()[1:]])
        self.assertEqual(coverage["unsupported_sequences"], [])
        self.assertEqual([row["occurrence"]["seq"] for row in result["relations"]],
                         coverage["supported_sequences"])
        for item in result["answer_key"]:
            seed = self._event(capture, item["seed"]["seq"])
            self.assertNotEqual(item["counterpart_action"], seed["row"][2])

    def test_each_link_retains_both_native_subject_and_generated_provenance(self):
        module = self._module()
        capture = self._capture()
        result = self._select(module, capture)
        pages = {page["slug"]: page for page in capture["pages"]}
        preparer = importlib.import_module("siavectorprepare")
        for relation in result["relations"]:
            native = self._event(capture, relation["occurrence"]["seq"])
            self.assertEqual(relation["occurrence"], occurrence(native))
            self.assertEqual(relation["native_subject"], {
                "field": "arg1", "value": native["row"][3]})
            self.assertEqual(relation["action"], native["row"][2])
            link = relation["generated_link"]
            self.assertEqual(set(link), {"slug", "provenance"})
            self.assertEqual(link["provenance"], "deterministic-signed-row-projection-v1")
            self.assertIn(link["slug"], native["projection"]["links"])
            self.assertFalse(link["slug"].startswith("organs/"))
            witness = relation["witness"]
            page = pages[witness["source_slug"]]
            encoded = witness["excerpt"].encode("utf-8")
            token = ("[[" + link["slug"] + "]]").encode("utf-8")
            self.assertEqual(witness["excerpt"], native["retention"]["retrieval_excerpt"])
            self.assertEqual(witness["excerpt_sha256"], sha(encoded))
            self.assertEqual(witness["page_sha256"], page["sha256"])
            self.assertEqual(witness["page_lineage_sha256"], page["lineage_sha256"])
            self.assertEqual(witness["origin"], page["origin"])
            self.assertEqual(witness["link_token"].encode("utf-8"), token)
            self.assertEqual(encoded[witness["link_utf8_start"]:witness["link_utf8_end"]], token)
            chunks = list(preparer._chunk_bytes(page["text"]))
            chunk = chunks[witness["chunk_index"]]
            self.assertIn(encoded, chunk)
            self.assertEqual(witness["chunk_sha256"], sha(chunk))

    def test_full_pages_are_lossless_and_keep_source_origins(self):
        module = self._module()
        path = self._source("2026-01-02")
        raw = path.read_bytes() + "\r\nUNMODIFIED Ω\u2028TAIL\r\n".encode("utf-8")
        path.write_bytes(raw)
        capture = self._capture()
        result = self._select(module, capture)
        originals = {page["slug"]: page for page in capture["pages"]}
        self.assertEqual({page["slug"] for page in result["pages"]}, set(originals))
        for page in result["pages"]:
            original = originals[page["slug"]]
            self.assertEqual(set(page), {"slug", "title", "type", "origin", "text", "text_sha256"})
            self.assertEqual(page["title"], page["slug"])
            self.assertEqual(page["text"], original["text"])
            self.assertEqual(page["text_sha256"], original["sha256"])
            self.assertEqual(page["origin"], original["origin"])

    def test_missing_native_counterpart_excludes_complete_query_not_target(self):
        module = self._module()
        path = self._source("2026-01-03")
        text = path.read_text(encoding="utf-8")
        native = next(line for line in text.splitlines() if "<!-- sia-event:" in line)
        path.write_text(text.replace(native, "- withheld native fixture witness"), encoding="utf-8")
        capture = self._capture()
        self.assertEqual(self._event(capture, "3")["retention"]["status"], "no-admitted-witness")
        result = self._select(module, capture)
        self.assertEqual(self._seed_answers(result, "1"), [])
        self.assertIn("required-native-witness-unavailable", self._reasons(result))
        self.assertEqual(result["event_population"], capture["events"])
        self.assertTrue(any(row["occurrence"]["seq"] == "3" and row["witness"] is None
                            for row in result["relations"]))

    def test_absent_capture_projection_does_not_erase_native_counterpart(self):
        module = self._module()
        capture = self._capture()
        before = self._select(module, capture)
        broken = copy.deepcopy(capture)
        event = self._event(broken, "3")
        event["projection"] = None
        event["retention"] = {
            "status": "not-projected", "witness_kind": None, "source_slug": None,
            "index_file": None, "retrieval_excerpt": None,
            "projected_event_retained": False, "value_answer_retained": False}
        slug = "events/sekhmet/2026-01-03"
        next(page for page in broken["pages"] if page["slug"] == slug)["role"] = "inspected-only"
        rehash(broken, "capture_sha256")
        # This is an admitted capture state, not an invented relation fixture.
        importlib.import_module("siacognitivehistory").admit_capture(broken)
        result = self._select(module, broken)
        self.assertEqual(self._seed_answers(result, "1"), [])
        self.assertIn("required-native-witness-unavailable", self._reasons(result))
        self.assertEqual(result["event_population"], broken["events"])
        self.assertEqual(result["dependency_groups"], before["dependency_groups"])

    def test_internally_admitted_excerpt_substitution_does_not_become_a_native_relation(self):
        module = self._module()
        capture = self._capture()
        altered = copy.deepcopy(capture)
        event = self._event(altered, "3")
        page = next(page for page in altered["pages"]
                    if page["slug"] == event["retention"]["source_slug"])
        decoy = next(line for line in page["text"].split("\n")
                     if line.startswith("What [[organs/"))
        self.assertNotEqual(event["retention"]["retrieval_excerpt"], decoy)
        event["retention"]["retrieval_excerpt"] = decoy
        rehash(altered, "capture_sha256")
        importlib.import_module("siacognitivehistory").admit_capture(altered)
        result = self._select(module, altered)
        self.assertEqual(self._seed_answers(result, "1"), [])
        self.assertIn("required-native-witness-unavailable", self._reasons(result))

    def test_page_text_decoys_never_replace_exact_native_link_witness(self):
        module = self._module()
        path = self._source("2026-01-03")
        text = path.read_text(encoding="utf-8")
        native = next(line for line in text.splitlines() if "<!-- sia-event:" in line)
        marker_only = native[native.index("<!-- sia-event:"):]
        decoys = "- OUTCOME:restart wireplumber.service held\n- [[units/wireplumber]]\n" + marker_only
        path.write_text(text.replace(native, decoys), encoding="utf-8")
        result = self._select(module)
        self.assertEqual(self._seed_answers(result, "1"), [])
        self.assertIn("required-native-witness-unavailable", self._reasons(result))

    def test_origin_boundary_excludes_whole_query_without_promoting_page(self):
        module = self._module()
        path = self._source("2026-01-03")
        raw = path.read_bytes().replace(b"---\n", b"---\norigin: model\n", 1)
        path.write_bytes(raw)
        capture = self._capture()
        self.assertEqual(self._event(capture, "3")["retention"]["status"], "retained")
        result = self._select(module, capture)
        self.assertEqual(self._seed_answers(result, "1"), [])
        self.assertIn("required-source-origin-not-evidence", self._reasons(result))
        page = next(page for page in result["pages"]
                    if page["slug"] == "events/sekhmet/2026-01-03")
        self.assertEqual(page["origin"], "model")
        self.assertEqual(page["text"].encode("utf-8"), raw)

    def test_same_page_shortcut_excludes_whole_query_instead_of_dropping_target(self):
        module = self._module()
        rows = self._rows()
        next(row for row in rows if row[0] == "2")[1] = "2026-01-01T02:00:00Z"
        self._resign(rows)
        result = self._select(module)
        self.assertEqual(self._seed_answers(result, "1"), [])
        self.assertIn("seed-target-source-page-shortcut", self._reasons(result))

    def test_page_pooling_requires_all_counterpart_excerpts_in_one_page_chunk(self):
        module = self._module()
        rows = self._rows()
        next(row for row in rows if row[0] == "3")[1] = "2026-01-02T02:00:00Z"
        self._resign(rows)
        path = self._source("2026-01-02")
        text = path.read_text(encoding="utf-8")
        first = next(line for line in text.splitlines() if "<!-- sia-event:" in line)
        preparer = importlib.import_module("siavectorprepare")
        initial_chunks = list(preparer._chunk_bytes(text))
        for native in (line for line in text.splitlines() if "<!-- sia-event:" in line):
            self.assertTrue(any(native.encode("utf-8") in chunk for chunk in initial_chunks),
                            "fixture must start with whole native witnesses")
        # Newline-terminated padding keeps native markers as whole lines while
        # separating their actual chunks; it never edits either target payload.
        path.write_text(text.replace(first, first + "\n" + "padding\n" * 2048), encoding="utf-8")
        capture = self._capture()
        for seq in ("2", "3"):
            self.assertEqual(self._event(capture, seq)["retention"]["status"], "retained")
        chunks = list(preparer._chunk_bytes(path.read_text(encoding="utf-8")))
        options = []
        for seq in ("2", "3"):
            encoded = self._event(capture, seq)["retention"]["retrieval_excerpt"].encode("utf-8")
            options.append({index for index, chunk in enumerate(chunks) if encoded in chunk})
        self.assertTrue(all(options), "padding must preserve individual chunk witnesses")
        self.assertFalse(set.intersection(*options), "fixture must isolate page-pooling conflict")
        result = self._select(module, capture)
        self.assertEqual(self._seed_answers(result, "1"), [])
        self.assertIn("page-pooling-witness-conflict", self._reasons(result))

    def test_generated_bridge_collision_refuses_even_when_one_witness_is_missing(self):
        module = self._module()
        rows = self._rows()
        next(row for row in rows if row[0] == "3")[3] = "wireplumber"
        self._resign(rows)
        path = self._source("2026-01-03")
        text = path.read_text(encoding="utf-8")
        native = next(line for line in text.splitlines() if "<!-- sia-event:" in line)
        path.write_text(text.replace(native, "- missing collision witness"), encoding="utf-8")
        capture = self._capture()
        first, other = self._event(capture, "1"), self._event(capture, "3")
        self.assertNotEqual(first["row"][3], other["row"][3])
        self.assertEqual(first["projection"]["links"], other["projection"]["links"])
        with self.assertRaisesRegex(module.SourceLinkRefusal, "collision"):
            self._select(module, capture)

    def test_arg2_fallback_is_declared_unsupported_not_a_raw_arg1_alias(self):
        module = self._module()
        rows = self._rows()
        next(row for row in rows if row[0] == "3")[3:5] = ["-", "wireplumber.service"]
        self._resign(rows)
        capture = self._capture()
        fallback = self._event(capture, "3")
        self.assertIn("units/wireplumber", fallback["projection"]["links"])
        result = self._select(module, capture)
        coverage = next(row for row in result["source_coverage"] if row["chain"] == "sekhmet")
        self.assertEqual(coverage["status"], "partial")
        self.assertIn("3", coverage["unsupported_sequences"])
        self.assertNotIn("3", coverage["supported_sequences"])
        self.assertFalse(any(row["occurrence"]["seq"] == "3" for row in result["relations"]))
        self.assertTrue(all(target["seq"] != "3" for target in self._answer(result)["targets"]))

    def test_unsupported_source_is_explicit_not_an_empty_supported_graph(self):
        module = self._module()
        self.registry = {"aegis": self.registry["sekhmet"]}
        rows = [line.split("\t") for line in
                Path(self.registry["aegis"][0]).read_text(encoding="utf-8").splitlines()]
        ledger_tests._write_projected_event_pages(self.corpus, "aegis", rows)
        capture = self._capture()
        result = self._select(module, capture)
        self.assertEqual(result["queries"], [])
        self.assertEqual(result["answer_key"], [])
        self.assertEqual(result["relations"], [])
        coverage = next(row for row in result["source_coverage"] if row["chain"] == "aegis")
        self.assertEqual(coverage["status"], "unsupported")
        self.assertEqual(coverage["reason"], "unsupported-native-link-projection")
        self.assertEqual(coverage["supported_sequences"], [])
        self.assertEqual(coverage["unsupported_sequences"], [row[0] for row in rows[1:]])
        self.assertEqual(result["event_population"], capture["events"])
        policy = policy_fixture()
        policy["require_queries"] = True
        with self.assertRaisesRegex(module.SourceLinkRefusal, "required.*quer"):
            self._select(module, capture, policy)

    def test_shared_native_source_page_transitively_unites_distinct_subject_groups(self):
        module = self._module()
        rows = self._rows()
        next(row for row in rows if row[0] == "4")[1] = "2026-01-03T02:00:00Z"
        self._resign(rows)
        result = self._select(module)
        answers = result["answer_key"]
        wire = self._answer(result, "1")
        pipe = self._answer(result, "4")
        self.assertEqual(wire["group_id"], pipe["group_id"])
        group = next(row for row in result["dependency_groups"] if row["id"] == wire["group_id"])
        self.assertEqual(set(group["dependencies"]["bridges"]),
                         {"units/wireplumber", "units/pipewire"})
        self.assertIn("events/sekhmet/2026-01-03", group["dependencies"]["source_pages"])
        self.assertEqual({query["split"] for query in result["queries"]
                          if query["id"] in {answer["id"] for answer in answers}},
                         {group["split"]})

    def test_dependency_partition_precedes_origin_and_witness_eligibility(self):
        module = self._module()
        rows = self._rows()
        next(row for row in rows if row[0] == "4")[1] = "2026-01-03T02:00:00Z"
        self._resign(rows)
        before_capture = self._capture()
        before = self._select(module, before_capture)
        path = self._source("2026-01-03")
        path.write_bytes(path.read_bytes().replace(b"---\n", b"---\norigin: model\n", 1))
        after = self._select(module)
        self.assertEqual(before["dependency_groups"], after["dependency_groups"])
        self.assertNotEqual(before["answer_key"], after["answer_key"])

    def test_no_declared_dependency_can_cross_query_splits(self):
        module = self._module()
        policy = policy_fixture()
        result = self._select(module, policy=policy)
        owners = {}
        for group in result["dependency_groups"]:
            dependencies = group["dependencies"]
            self.assertEqual(set(dependencies), {"bridges", "subjects", "source_pages", "occurrences"})
            self.assertEqual(group["id"], sha(canonical([
                "sia-cognitive-source-link-group-v1", dependencies])))
            self.assertIn(group["split"], ("calibration", "heldout"))
            # Executable contract oracle; no static numeric split result is
            # claimed. The fixture never chooses a seed after seeing yield.
            split_hash = sha(canonical([
                "sia-cognitive-source-link-split-v1", policy["seed"], group["id"]]))
            remainder = int(split_hash, 16) % policy["split"]["calibration_modulus"]
            expected = ("calibration" if remainder == policy["split"]["calibration_residue"]
                        else "heldout")
            self.assertEqual(group["split"], expected)
            for kind, values in dependencies.items():
                for value in values:
                    key = (kind, canonical(value))
                    if key in owners:
                        self.assertEqual(owners[key], group["id"])
                    owners[key] = group["id"]
            for query in result["queries"]:
                if query["group_id"] == group["id"]:
                    self.assertEqual(query["split"], group["split"])

    def test_resource_limits_refuse_whole_population_pages_or_queries_without_clipping(self):
        module = self._module()
        capture = self._capture()
        for section, field in (
                ("resources", "max_events"), ("resources", "max_relations"),
                ("resources", "max_dependency_groups"), ("resources", "max_queries"),
                ("resources", "max_selection_bytes"), ("pages", "max_pages"),
                ("pages", "max_page_bytes"), ("pages", "max_total_page_bytes"),
                ("pages", "max_chunks")):
            policy = policy_fixture()
            policy[section][field] = 1
            with self.subTest(section=section, field=field), self.assertRaises(module.SourceLinkRefusal):
                self._select(module, capture, policy)

    def test_public_query_handoff_contains_only_explicit_cues_and_replays_privately(self):
        module = self._module()
        capture, policy = self._capture(), policy_fixture()
        result = self._select(module, capture, policy)
        kwargs = self._pins(capture, policy)
        for split in ("calibration", "heldout"):
            public = module.public_queries(result, split=split, **kwargs)
            selected = [row for row in result["queries"] if row["split"] == split]
            self.assertEqual(public, [{"id": row["id"], "text": row["text"]} for row in selected])
            for row in public:
                self.assertEqual(set(row), {"id", "text"})
                answer = next(answer for answer in result["answer_key"] if answer["id"] == row["id"])
                self.assertEqual(row["text"], public_text(answer["seed"], answer["counterpart_action"]))
                self.assertNotIn(answer["bridge"], row["text"])
                self.assertNotIn(answer["native_subject"]["value"], row["text"])
                for target in answer["targets"]:
                    self.assertNotIn(target["entry_hash"], row["text"])
                    self.assertNotIn(target["event_id"], row["text"])
            if public:
                public[0]["text"] = "worker-local edit"
                self.assertNotEqual(public, module.public_queries(result, split=split, **kwargs))
        for split in (None, True, "all", "training"):
            with self.subTest(split=split), self.assertRaises(module.SourceLinkRefusal):
                module.public_queries(result, split=split, **kwargs)

    def test_native_unicode_subject_is_preserved_without_entering_public_cues(self):
        module = self._module()
        rows = self._rows()
        for row in rows:
            if row[3] == "wireplumber.service":
                row[3] = 'Ω-"native-subject".service'
        self._resign(rows)
        result = self._select(module)
        answer = self._answer(result)
        self.assertEqual(answer["native_subject"]["value"], 'Ω-"native-subject".service')
        query = next(row for row in result["queries"] if row["id"] == answer["id"])
        self.assertEqual(query["text"], public_text(answer["seed"], answer["counterpart_action"]))
        self.assertNotIn(answer["native_subject"]["value"], query["text"])
        self.assertNotIn(answer["bridge"], query["text"])

    def test_seed_event_id_does_not_substitute_for_native_content_identity(self):
        module = self._module()
        original_capture = self._capture()
        original = self._select(module, original_capture)
        rows = self._rows()
        next(row for row in rows if row[0] == "1")[4] = "different-native-request"
        self._resign(rows)
        changed_capture = self._capture()
        changed = self._select(module, changed_capture)
        first, second = self._answer(original), self._answer(changed)
        self.assertEqual(first["seed"]["event_id"], second["seed"]["event_id"])
        self.assertNotEqual(first["seed"]["entry_hash"], second["seed"]["entry_hash"])
        self.assertNotEqual(first["id"], second["id"])
        for answer in (first, second):
            self.assertEqual(answer["id"], sha(canonical([
                "sia-cognitive-source-link-query-v1", answer["seed"],
                answer["counterpart_action"]])))

    def test_rehashed_answer_relation_page_and_partition_edits_fail_replay_and_handoff(self):
        module = self._module()
        capture, policy = self._capture(), policy_fixture()
        result = self._select(module, capture, policy)
        kwargs = self._pins(capture, policy)
        for edit in ("target-drop", "native-subject", "bridge", "origin", "page", "split", "query"):
            broken = copy.deepcopy(result)
            answer = self._answer(broken)
            if edit == "target-drop":
                answer["targets"].pop()
            elif edit == "native-subject":
                answer["native_subject"]["value"] = "forged.service"
            elif edit == "bridge":
                broken["relations"][0]["generated_link"]["slug"] = "units/foreign"
            elif edit == "origin":
                broken["relations"][0]["witness"]["origin"] = "model"
            elif edit == "page":
                broken["pages"][0]["text"] += "rehashed foreign page"
                broken["pages"][0]["text_sha256"] = sha(broken["pages"][0]["text"].encode("utf-8"))
                broken["pages_sha256"] = sha(canonical(broken["pages"]))
            elif edit == "split":
                group = broken["dependency_groups"][0]
                group["split"] = "heldout" if group["split"] == "calibration" else "calibration"
            else:
                broken["queries"][0]["text"] += " units/wireplumber"
            rehash(broken, "selection_sha256")
            with self.subTest(edit=edit), self.assertRaises(module.SourceLinkRefusal):
                module.admit_selection(broken, **kwargs)
            with self.subTest(edit=edit, boundary="worker"), self.assertRaises(module.SourceLinkRefusal):
                module.public_queries(broken, split="heldout", **kwargs)

    def test_replay_bounds_selection_before_any_source_copy_or_serialization(self):
        module = self._module()
        capture, policy = self._capture(), policy_fixture()
        result = self._select(module, capture, policy)
        kwargs = self._pins(capture, policy)
        cyclic = copy.deepcopy(result)
        cyclic["unexpected"] = cyclic
        for boundary in ("admit", "worker"):
            with mock.patch("copy.deepcopy", side_effect=AssertionError("copied before selection bound")), \
                    mock.patch("json.dumps", side_effect=AssertionError("serialized before selection bound")), \
                    self.assertRaises(module.SourceLinkRefusal):
                if boundary == "admit":
                    module.admit_selection(cyclic, **kwargs)
                else:
                    module.public_queries(cyclic, split="heldout", **kwargs)

    def test_source_generator_question_metadata_never_selects_relations_or_targets(self):
        module = self._module()
        capture = self._capture()
        altered = copy.deepcopy(capture)
        altered["question_coverage"] = []
        altered["generation_exclusions"] = []
        rehash(altered, "capture_sha256")
        importlib.import_module("siacognitivehistory").admit_capture(altered)
        first, second = self._select(module, capture), self._select(module, altered)
        for key in ("relations", "dependency_groups", "queries", "answer_key", "source_coverage"):
            self.assertEqual(first[key], second[key], key)

    def test_nonclaims_preserve_source_scope_and_explicit_non_drop_in_boundary(self):
        module = self._module()
        capture = self._capture()
        result = self._select(module, capture)
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertEqual(result["source_non_claims"], {
            "capture": capture["non_claims"], "source": capture["source_non_claims"]})
        self.assertNotIn("scores", result)
        self.assertNotIn("metrics", result)
        self.assertNotIn("worker_result", result)
        self.assertNotIn("real_source_available", result)


if __name__ == "__main__":
    unittest.main()
