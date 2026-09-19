"""Frozen private selection is a construction step, not a cognitive result.

Only fixture-owned ledgers/corpus are opened while constructing captures. The
selection APIs themselves must be pure. Root schedules this module's execution.

Boundary literals were obtained from JACKAL, status=exact:
parsed=131072+1 exact=131073; parsed=2048+1 exact=2049;
parsed=256+1 exact=257; parsed=4194304+1 exact=4194305.
Previously routed: parsed=4096+1 exact=4097; parsed=64+1 exact=65;
parsed=8000+1 exact=8001.
Nonclaims: NOT formal-bounded: this lane carries no Lean-checked certificate;
The epistemic class above is the STRONGEST claim this result supports;
exact rational arithmetic (not yet checker-covered).
"""

import copy
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests import test_cognitive_history_capture as capture_tests


ledger_tests = capture_tests.ledger_tests
sha = capture_tests.sha
canonical = capture_tests.canonical

CLASSES = ("recency-heavy", "repetition-heavy", "novelty",
           "associative-multi-hop", "consolidation-gist")
NON_CLAIMS = [
    "This is a grouped query-level split, not a temporal or source-page holdout.",
    "Shared source pages and signed-chain authentication anchors can occur across splits.",
    "Class names describe engineering tasks, not demonstrated cognitive mechanisms or wins.",
    "Novelty is first occurrence of an exact action and raw subject within a complete named signed chain, not machine-wide novelty.",
    "Latest recorded outcome follows signed sequence order, not necessarily event-time chronology.",
    "Unsupported associative and gist classes are not supplied by relabeling generic ledger QA.",
    "Excluded or unavailable witnesses remain declared; retained subsets do not establish complete-history answers.",
    "Selection hashes bind represented bytes; external capture and policy authentication remain caller obligations.",
    "No retrieval scores, tuned parameters, statistical power, or cognitive improvement are established.",
]


def policy_fixture():
    """Design choices and observed preparer/adapter ceilings, not tuned values."""
    return {
        "schema": "sia-cognitive-selection-policy-v1",
        "seed": "fixture-freeze-v1",
        "split": {"kind": "grouped-query-v1",
                  "group_key": "chain-raw-subject-v1",
                  "calibration_modulus": 5, "calibration_residue": 0},
        "pages": {"order": "seeded-slug-sha256-v1", "title": "slug-v1",
                  "max_pages": 256, "max_page_bytes": 131072,
                  "max_total_page_bytes": 4194304, "max_chunks": 4096},
        "queries": {"templates": "signed-history-tasks-v1",
                    "max_groups_per_class": 64, "max_queries": 64},
        "protocol": {"chunking": "utf8-contiguous-codepoint-v1",
                     "max_chunk_bytes": 2048,
                     "page_pooling": "single-chunk-per-slug",
                     "max_query_bytes": 8000},
        "required_classes": [],
    }


def group_id(chain, subject):
    return sha(canonical(["sia-cognitive-group-v1", chain, subject]))


class CognitiveSelection(unittest.TestCase):
    def setUp(self):
        self.bench = ledger_tests.siabench
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state, self.corpus, self.registry = ledger_tests._signed_fixture(
            self.temp.name)

    _signed_rows = ledger_tests.SignedLedgerDataset._signed_rows
    _projected_row = ledger_tests.SignedLedgerDataset._projected_row
    _replace_marker_with_split_decoys = (
        ledger_tests.SignedLedgerDataset._replace_marker_with_split_decoys)
    _consolidate_sequence_fixture = (
        ledger_tests.SignedLedgerDataset._consolidate_sequence_fixture)

    def _module(self):
        try:
            module = importlib.import_module("siacognitiveselect")
        except ModuleNotFoundError as exc:
            self.fail("pure cognitive selection API must exist: " + str(exc))
        for name in ("select_history", "admit_selection"):
            self.assertTrue(callable(getattr(module, name, None)), name)
        self.assertTrue(hasattr(module, "SelectionRefusal"))
        return module

    def _capture(self):
        return self.bench.build_ledger_dataset(
            corpus=self.corpus, chain_registry=self.registry,
            cognitive_history=True)["cognitive_history"]

    def _source(self, day="2026-01-01"):
        return Path(self.corpus) / "events" / "aegis" / (day + ".md")

    def _select(self, module, capture=None, policy=None):
        capture = self._capture() if capture is None else capture
        policy = policy_fixture() if policy is None else policy
        return module.select_history(
            capture, expected_capture_sha256=capture["capture_sha256"],
            policy=policy, expected_policy_sha256=sha(canonical(policy)))

    def _admit(self, module, selection, capture, policy):
        return module.admit_selection(
            selection, capture=capture, policy=policy,
            expected_capture_sha256=capture["capture_sha256"],
            expected_policy_sha256=sha(canonical(policy)))

    def _resign_fixture(self, rows):
        """Alter only the deterministic, private test chain and its pages."""
        key = ledger_tests.Ed25519PrivateKey.from_private_bytes(
            bytes.fromhex("01" * 32))
        previous = sha(b"attest-genesis-v1")
        for row in rows:
            row[7] = previous
            previous = self.bench._entry_hash(row)
            row[8] = key.sign(bytes.fromhex(previous)).hex()
        Path(self.registry["aegis"][0]).write_text(
            "\n".join("\t".join(row) for row in rows) + "\n",
            encoding="utf-8")
        (Path(self.state) / "head.pin").write_text(
            f"{len(rows)} {previous}\n", encoding="utf-8")
        ledger_tests._write_projected_event_pages(self.corpus, "aegis", rows)

    def _answers(self, result, klass, subject="wireplumber.service"):
        identifier = group_id("aegis", subject)
        return [row for row in result["answer_key"]
                if row["class"] == klass and row["group_id"] == identifier]

    def _reasons(self, result, klass=None):
        return {item["reason"] for item in result["exclusions"]
                if klass is None or item["class"] == klass}

    def test_public_pure_selection_api_exists(self):
        self._module()

    def test_selection_is_detached_deterministic_and_bound_to_external_pins(self):
        module = self._module()
        capture, policy = self._capture(), policy_fixture()
        before = copy.deepcopy((capture, policy))
        with mock.patch("builtins.open", side_effect=AssertionError("pure API opened a path")), \
                mock.patch("os.open", side_effect=AssertionError("pure API opened a descriptor")), \
                mock.patch("subprocess.run", side_effect=AssertionError("pure API launched a child")):
            result = self._select(module, capture, policy)
            repeated = self._select(module, capture, policy)
            admitted = self._admit(module, result, capture, policy)
        self.assertEqual((capture, policy), before)
        self.assertEqual(result, repeated)
        self.assertEqual(result, admitted)
        self.assertIsNot(result, admitted)
        self.assertIsNot(result["pages"], admitted["pages"])
        self.assertEqual(set(result), {
            "schema", "capture_sha256", "policy_sha256", "pages", "pages_sha256",
            "groups", "queries", "answer_key", "coverage", "exclusions",
            "source_non_claims", "non_claims", "selection_sha256"})
        self.assertEqual(result["schema"], "sia-cognitive-selection-v1")
        self.assertEqual(result["capture_sha256"], capture["capture_sha256"])
        self.assertEqual(result["policy_sha256"], sha(canonical(policy)))
        self.assertEqual(result["pages_sha256"], sha(canonical(result["pages"])))
        self.assertEqual(result["selection_sha256"], sha(canonical({
            key: value for key, value in result.items() if key != "selection_sha256"})))
        result["pages"][0]["text"] = "detached change"
        self.assertEqual((capture, policy), before)
        self.assertNotEqual(result, admitted)

    def test_wrong_external_pins_and_rehashed_capture_corruption_refuse(self):
        module = self._module()
        capture, policy = self._capture(), policy_fixture()
        for field in ("expected_capture_sha256", "expected_policy_sha256"):
            kwargs = {"expected_capture_sha256": capture["capture_sha256"],
                      "expected_policy_sha256": sha(canonical(policy)), "policy": policy}
            kwargs[field] = "0" * 64
            with self.subTest(field=field), self.assertRaises(module.SelectionRefusal):
                module.select_history(capture, **kwargs)
        broken = copy.deepcopy(capture)
        broken["pages"][0]["text"] += "unsigned replacement"
        broken["capture_sha256"] = sha(canonical({
            key: value for key, value in broken.items() if key != "capture_sha256"}))
        with self.assertRaises(module.SelectionRefusal):
            self._select(module, broken, policy)

    def test_policy_is_closed_typed_bounded_and_has_no_tuning_or_score_fields(self):
        module = self._module()
        capture = self._capture()
        cases = [
            ("seed", None), ("seed", ""), ("schema", True),
            ("scores", {}), ("split", {"kind": "temporal"}),
        ]
        for field, value in cases:
            policy = policy_fixture()
            policy[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(module.SelectionRefusal):
                self._select(module, capture, policy)
        for section, field, value in (
                ("pages", "max_pages", True), ("pages", "max_pages", 0),
                ("pages", "max_pages", 257), ("pages", "max_page_bytes", 131073),
                ("pages", "max_total_page_bytes", 4194305),
                ("pages", "max_chunks", 4097),
                ("queries", "max_queries", 65),
                ("queries", "max_groups_per_class", False),
                ("protocol", "max_chunk_bytes", 2049),
                ("protocol", "max_query_bytes", 8001),
                ("split", "calibration_modulus", True),
                ("split", "calibration_modulus", 1),
                ("split", "calibration_residue", 5)):
            policy = policy_fixture()
            policy[section][field] = value
            with self.subTest(section=section, field=field, value=value), \
                    self.assertRaises(module.SelectionRefusal):
                self._select(module, capture, policy)
        for malformed in (float("inf"), float("nan"), {"nested": []}):
            policy = policy_fixture()
            policy["seed"] = malformed
            with self.assertRaises(module.SelectionRefusal):
                module.select_history(capture, expected_capture_sha256=capture["capture_sha256"],
                                      policy=policy, expected_policy_sha256="0" * 64)
        cyclic = policy_fixture()
        cyclic["seed"] = cyclic
        with self.assertRaises(module.SelectionRefusal):
            module.select_history(capture, expected_capture_sha256=capture["capture_sha256"],
                                  policy=cyclic, expected_policy_sha256="0" * 64)

    def test_selected_pages_preserve_whole_exact_text_origin_and_preparer_shape(self):
        module = self._module()
        source = self._source()
        raw = source.read_bytes().replace(b"---\n", b"---\norigin: model\n", 1)
        raw += "\r\nLOSSLESS Ω\u2028TAIL\r\n".encode("utf-8")
        source.write_bytes(raw)
        capture = self._capture()
        result = self._select(module, capture)
        captured = {row["slug"]: row for row in capture["pages"]}
        for page in result["pages"]:
            original = captured[page["slug"]]
            self.assertEqual(set(page), {"slug", "title", "type", "origin", "text", "text_sha256"})
            self.assertEqual(page["title"], page["slug"])
            self.assertEqual(page["text"], original["text"])
            self.assertEqual(page["text_sha256"], original["sha256"])
            self.assertEqual(page["origin"], original["origin"])
        retained = next(row for row in result["pages"]
                        if row["slug"] == "events/aegis/2026-01-01")
        self.assertEqual(retained["text"].encode("utf-8"), raw)
        self.assertEqual(retained["origin"], "model")

    def test_oversized_capture_page_is_excluded_whole_not_clipped_or_relabelled(self):
        module = self._module()
        source = self._source()
        source.write_bytes(source.read_bytes() + b"z" * 131073)
        capture = self._capture()
        result = self._select(module, capture)
        slug = "events/aegis/2026-01-01"
        self.assertIn(slug, {row["slug"] for row in capture["pages"]})
        self.assertNotIn(slug, {row["slug"] for row in result["pages"]})
        self.assertIn("page-byte-budget", self._reasons(result))
        self.assertFalse(self._answers(result, "repetition-heavy"))
        self.assertFalse(self._answers(result, "novelty"))

    def test_page_selection_precedes_answer_selection_and_uses_frozen_slug_order(self):
        module = self._module()
        policy = policy_fixture()
        policy["pages"]["max_pages"] = 1
        capture = self._capture()
        ordered = sorted(capture["pages"], key=lambda page: (
            sha(canonical(["sia-cognitive-page-order-v1", policy["seed"], page["slug"]])),
            page["slug"]))
        result = self._select(module, capture, policy)
        self.assertEqual([row["slug"] for row in result["pages"]], [ordered[0]["slug"]])
        self.assertIn("page-count-budget", self._reasons(result))
        rows = self._signed_rows()
        rows[2][4] = "different-private-answer"
        self._resign_fixture(rows)
        changed = self._select(module, policy=policy)
        self.assertEqual([row["slug"] for row in changed["pages"]],
                         [row["slug"] for row in result["pages"]])

    def test_aggregate_page_bytes_and_chunk_budgets_never_trim_selected_pages(self):
        module = self._module()
        capture = self._capture()
        policy = policy_fixture()
        ordered = sorted(capture["pages"], key=lambda page: (
            sha(canonical(["sia-cognitive-page-order-v1", policy["seed"], page["slug"]])),
            page["slug"]))
        policy["pages"]["max_total_page_bytes"] = ordered[0]["size"]
        result = self._select(module, capture, policy)
        self.assertEqual([row["slug"] for row in result["pages"]], [ordered[0]["slug"]])
        self.assertEqual(result["pages"][0]["text"], ordered[0]["text"])
        self.assertIn("page-aggregate-byte-budget", self._reasons(result))
        policy = policy_fixture()
        policy["pages"]["max_chunks"] = 1
        result = self._select(module, capture, policy)
        preparer = importlib.import_module("siavectorprepare")
        self.assertEqual(sum(len(list(preparer._chunk_bytes(row["text"])))
                             for row in result["pages"]), 1)
        self.assertIn("page-chunk-budget", self._reasons(result))

    def test_exact_subject_grouping_spans_actions_and_classes_without_rebalancing(self):
        module = self._module()
        result = self._select(module)
        groups = {row["id"]: row for row in result["groups"]}
        # Hash-to-modulus results obtained from JACKAL mod_pow(exp=1,mod=5),
        # status=exact: wireplumber residue=3, pipewire=4, bluetooth=3.
        # NOT formal-bounded: this lane carries no Lean-checked certificate.
        # The epistemic class above is the STRONGEST claim this result supports.
        # modular exponentiation (square-and-multiply).
        for subject in ("wireplumber.service", "pipewire.service", "bluetooth.service"):
            self.assertEqual(groups[group_id("aegis", subject)], {
                "id": group_id("aegis", subject), "chain": "aegis",
                "subject": subject, "split": "heldout"})
        public = {row["id"]: row for row in result["queries"]}
        for row in result["answer_key"]:
            self.assertEqual(public[row["id"]]["split"], groups[row["group_id"]]["split"])
        pipewire = [row for row in result["answer_key"]
                    if row["group_id"] == group_id("aegis", "pipewire.service")]
        self.assertEqual({row["action"] for row in pipewire},
                         {"INTENT:restart", "OUTCOME:restart"})
        self.assertEqual({row["split"] for row in result["queries"]}, {"heldout"})

    def test_identical_basenames_do_not_merge_raw_subjects_or_split_assignments(self):
        module = self._module()
        rows = self._signed_rows()
        rows[1][3] = rows[2][3] = "/alpha/shared.service"
        rows[3][3] = rows[4][3] = "/beta/shared.service"
        self._resign_fixture(rows)
        result = self._select(module)
        groups = {row["subject"]: row for row in result["groups"]}
        # JACKAL exp=1,mod=5 status=exact: alpha residue=3, beta residue=0.
        # Same nonclaims as the modular fixture above; not a formal code proof.
        self.assertEqual(groups["/alpha/shared.service"]["split"], "heldout")
        self.assertEqual(groups["/beta/shared.service"]["split"], "calibration")
        self.assertNotEqual(groups["/alpha/shared.service"]["id"],
                            groups["/beta/shared.service"]["id"])
        self.assertNotIn("shared.service", groups)

    def test_chain_identity_remains_part_of_group_identity(self):
        module = self._module()
        other_root = self.root / "other-chain"
        other_root.mkdir()
        _state, _corpus, registry = ledger_tests._signed_fixture(str(other_root))
        ledger_tests._write_projected_event_pages(self.corpus, "sekhmet", self._signed_rows())
        self.registry["sekhmet"] = registry["aegis"]
        result = self._select(module)
        groups = {row["id"]: row for row in result["groups"]}
        self.assertIn(group_id("aegis", "wireplumber.service"), groups)
        self.assertIn(group_id("sekhmet", "wireplumber.service"), groups)
        self.assertNotEqual(group_id("aegis", "wireplumber.service"),
                            group_id("sekhmet", "wireplumber.service"))

    def test_public_queries_do_not_carry_private_classes_answers_or_witness_ids(self):
        module = self._module()
        result = self._select(module)
        for row in result["queries"]:
            self.assertEqual(set(row), {"id", "text", "split"})
            self.assertEqual(row["id"], self.bench._question_id({"question": row["text"]}))
            self.assertLessEqual(len(row["text"].encode("utf-8")), 8000)
        self.assertEqual({row["id"] for row in result["queries"]},
                         {row["id"] for row in result["answer_key"]})

    def test_recency_is_latest_recorded_sequence_not_maximum_utc_timestamp(self):
        module = self._module()
        rows = self._signed_rows()
        rows[1][1] = "2026-01-06T01:00:00Z"
        self._resign_fixture(rows)
        result = self._select(module)
        answers = self._answers(result, "recency-heavy")
        self.assertEqual(len(answers), 1)
        self.assertEqual(answers[0]["answer"], {
            "kind": "latest-recorded-outcome", "value": "held", "sequences": ["2"]})
        self.assertEqual({row["seq"] for row in answers[0]["support"]}, {"1", "2"})
        question = next(row["text"] for row in result["queries"] if row["id"] == answers[0]["id"])
        self.assertIn("latest recorded", question.casefold())
        self.assertNotIn("most recent event", question.casefold())

    def test_repetition_uses_complete_occurrence_set_and_novelty_uses_true_first(self):
        module = self._module()
        capture = self._capture()
        result = self._select(module, capture)
        repeated = self._answers(result, "repetition-heavy")
        self.assertEqual(len(repeated), 1)
        expected = [event for event in capture["events"]
                    if event["chain"] == "aegis" and event["row"][2] == "OUTCOME:restart"
                    and event["row"][3] == "wireplumber.service"]
        self.assertEqual(repeated[0]["answer"], {"kind": "occurrence-count", "value": len(expected),
                                               "sequences": [row["seq"] for row in expected]})
        self.assertEqual([row["seq"] for row in repeated[0]["support"]],
                         [row["seq"] for row in expected])
        first = self._answers(result, "novelty")
        self.assertEqual(first[0]["answer"], {"kind": "first-occurrence",
                         "value": expected[0]["row"][1], "sequences": ["1"]})
        chain = next(row for row in capture["chains"] if row["chain"] == "aegis")
        self.assertEqual(first[0]["scope"], {"kind": "complete-signed-chain", "chain": "aegis",
                         "head": chain["head"], "ledger_sha256": chain["ledger_sha256"]})

    def test_missing_first_witness_cannot_become_first_retained_or_partial_repetition(self):
        module = self._module()
        self._replace_marker_with_split_decoys("1")
        result = self._select(module)
        for klass in ("recency-heavy", "repetition-heavy", "novelty"):
            self.assertFalse(self._answers(result, klass))
            self.assertIn("required-witness-unavailable", self._reasons(result, klass))

    def test_lineage_only_is_not_text_support_and_gist_is_explicitly_unsupported(self):
        module = self._module()
        self._consolidate_sequence_fixture("1", retain_exemplar=False)
        result = self._select(module)
        self.assertFalse(self._answers(result, "novelty"))
        self.assertFalse(self._answers(result, "repetition-heavy"))
        coverage = {row["class"]: row for row in result["coverage"]}
        self.assertEqual(set(coverage), set(CLASSES))
        for klass, reason in (("associative-multi-hop", "no-witnessed-multi-hop-targets"),
                              ("consolidation-gist", "no-witnessed-gist-facts")):
            self.assertEqual(coverage[klass]["status"], "unsupported")
            self.assertEqual(coverage[klass]["reason"], reason)
            self.assertEqual(coverage[klass]["selected_queries"], 0)
            self.assertFalse(any(row["class"] == klass for row in result["answer_key"]))

    def test_excerpt_crossing_chunk_boundary_is_excluded_before_scoring(self):
        module = self._module()
        _row, _event, _eid, _sid, line, _payload, _day = self._projected_row("1")
        source = self._source()
        text = source.read_text(encoding="utf-8")
        prefix, suffix = text.split(line, 1)
        padding = "x" * (2048 - len(prefix.encode("utf-8")) - len(b"\n") - 1) + "\n"
        source.write_text(prefix + padding + line + suffix, encoding="utf-8")
        capture = self._capture()
        for sequence in ("1", "2"):
            self.assertEqual(next(row for row in capture["events"] if row["seq"] == sequence)
                             ["retention"]["status"], "retained")
        result = self._select(module, capture)
        self.assertFalse(self._answers(result, "novelty"))
        self.assertIn("required-excerpt-crosses-chunk", self._reasons(result, "novelty"))

    def test_distinct_required_chunks_on_one_page_cannot_pass_page_pooled_protocol(self):
        module = self._module()
        rows = self._signed_rows()
        rows[2][1] = "2026-01-01T02:00:00Z"
        self._resign_fixture(rows)
        line_a = self._projected_row("1")[4]
        line_b = self._projected_row("2")[4]
        source = self._source()
        text = source.read_text(encoding="utf-8")
        prefix = text.split(line_a, 1)[0]
        first = line_a + "\n"
        source.write_text(prefix + " " * (2048 - len(prefix.encode("utf-8")) - len(b"\n")) + "\n"
                          + first + " " * (2048 - len(first.encode("utf-8")) - len(b"\n")) + "\n"
                          + line_b + "\n", encoding="utf-8")
        capture = self._capture()
        for sequence in ("1", "2"):
            self.assertEqual(next(row for row in capture["events"] if row["seq"] == sequence)
                             ["retention"]["status"], "retained")
        result = self._select(module, capture)
        for klass in ("recency-heavy", "repetition-heavy"):
            self.assertFalse(self._answers(result, klass))
            self.assertIn("page-pooling-witness-conflict", self._reasons(result, klass))
        self.assertTrue(self._answers(result, "novelty"))

    def test_every_admitted_support_binds_exact_event_excerpt_and_utf8_chunk(self):
        module = self._module()
        capture = self._capture()
        result = self._select(module, capture)
        preparer = importlib.import_module("siavectorprepare")
        pages = {row["slug"]: row for row in result["pages"]}
        events = {(row["chain"], row["seq"]): row for row in capture["events"]}
        for answer in result["answer_key"]:
            self.assertEqual(set(answer), {"id", "class", "group_id", "action", "answer", "support", "scope"})
            seen_pages = {}
            for support in answer["support"]:
                self.assertEqual(set(support), {"chain", "seq", "entry_hash", "slug", "excerpt",
                                               "chunk_index", "chunk_sha256"})
                event = events[(support["chain"], support["seq"])]
                self.assertEqual(support["entry_hash"], event["entry_hash"])
                self.assertEqual(support["excerpt"], event["retention"]["retrieval_excerpt"])
                chunks = list(preparer._chunk_bytes(pages[support["slug"]]["text"]))
                chunk = chunks[support["chunk_index"]]
                self.assertIn(support["excerpt"].encode("utf-8"), chunk)
                self.assertEqual(support["chunk_sha256"], sha(chunk))
                self.assertEqual(seen_pages.setdefault(support["slug"], support["chunk_index"]),
                                 support["chunk_index"])

    def test_required_classes_refuse_missing_or_unsupported_coverage(self):
        module = self._module()
        capture = self._capture()
        for klass in ("associative-multi-hop", "consolidation-gist", "invented-class"):
            policy = policy_fixture()
            policy["required_classes"] = [klass]
            with self.subTest(klass=klass), self.assertRaises(module.SelectionRefusal):
                self._select(module, capture, policy)
        self._replace_marker_with_split_decoys("1")
        policy = policy_fixture()
        policy["required_classes"] = ["repetition-heavy"]
        with self.assertRaises(module.SelectionRefusal):
            self._select(module, policy=policy)

    def test_query_caps_declare_exclusions_and_preserve_preassigned_groups(self):
        module = self._module()
        capture = self._capture()
        complete = self._select(module, capture)
        policy = policy_fixture()
        policy["queries"]["max_queries"] = 1
        limited = self._select(module, capture, policy)
        self.assertEqual(len(limited["queries"]), 1)
        self.assertEqual(limited["groups"], complete["groups"])
        self.assertIn("query-count-budget", self._reasons(limited))
        policy = policy_fixture()
        policy["queries"]["max_groups_per_class"] = 1
        limited = self._select(module, capture, policy)
        for klass in CLASSES:
            self.assertLessEqual(len({row["group_id"] for row in limited["answer_key"]
                                      if row["class"] == klass}), 1)
        self.assertIn("class-group-budget", self._reasons(limited))

    def test_nonclaims_and_exclusions_are_immutable_admission_contracts(self):
        module = self._module()
        capture, policy = self._capture(), policy_fixture()
        result = self._select(module, capture, policy)
        self.assertEqual(result["non_claims"], NON_CLAIMS)
        self.assertEqual(result["source_non_claims"], {
            "capture": capture["non_claims"],
            "generator": capture["source_non_claims"]})
        for change in ("answer", "split", "class", "non_claims", "pages", "coverage"):
            altered = copy.deepcopy(result)
            if change == "answer":
                altered["answer_key"][0]["answer"]["value"] = "invented"
            elif change == "split":
                row = altered["queries"][0]
                row["split"] = "calibration" if row["split"] == "heldout" else "heldout"
            elif change == "class":
                altered["answer_key"][0]["class"] = "associative-multi-hop"
            elif change == "non_claims":
                altered["non_claims"] = []
            elif change == "pages":
                original = altered["pages"][0]["origin"]
                replacement = "model" if original != "model" else "evidence"
                self.assertNotEqual(original, replacement)
                altered["pages"][0]["origin"] = replacement
            else:
                altered["coverage"] = []
            altered["selection_sha256"] = sha(canonical({
                key: value for key, value in altered.items() if key != "selection_sha256"}))
            with self.subTest(change=change), self.assertRaises(module.SelectionRefusal):
                self._admit(module, altered, capture, policy)


if __name__ == "__main__":
    unittest.main()
