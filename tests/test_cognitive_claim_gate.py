#!/usr/bin/env python3
"""Contracts for the pinned private cognitive baseline claim boundary.

Without an externally pinned private request the product exposes a complete,
structured refusal. The admitted runner has separate transport tests; no
unused benchmark scaffold, metric, gate, or publisher remains callable here.
"""

import ast
import contextlib
import importlib.machinery
import importlib.util
import inspect
import io
import json
import os
import re
import unittest
from unittest import mock

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")

BRAIN_METAPHOR_BOUNDARY = (
    "“Brain” is a product metaphor for auditable local machine memory; it is "
    "not a biological brain and does not establish cognition or neuroscience."
)

EXPECTED_REFUSAL = {
    "schema": "sia-cognitive-baseline-refusal-v1",
    "status": "refused",
    "reason": "pinned-request-required",
    "consequence_ceiling": "informational",
    "non_claims": [
        "The request SHA-256 binds caller-supplied bytes, not their authorship or the truth of supplied history.",
        "The private command does not consult resident memory readiness, corpus, index, or an ambient model.",
        "Baseline and upstream nonclaims remain controlling; this receipt adds no metric, significance, or cognitive-win authority.",
        "Lifecycle locking and descriptor checks do not establish protection against a hostile same-user process.",
    ],
}

PROVISIONAL_HELPERS = (
    "JackalMcpSession",
    "DescriptorBoundHybridQuery",
    "_bounded_cognitive_json_size",
    "_CognitiveRetentionBudget",
    "_cognitive_group_tokens",
    "assign_cognitive_splits",
    "_admit_cognitive_results",
    "observe_cognitive_arms",
    "observe_cognitive_population",
    "_admit_cognitive_page_map",
    "_cognitive_sorted_results",
    "build_cognitive_transforms",
    "cognitive_report_rows",
    "build_cognitive_fidelity_rows",
    "cognitive_fidelity_matrix",
    "_jackal_exact_metric",
    "_expression_mean",
    "_float_exact_token",
    "apply_cognitive_abstention_policy",
    "cognitive_metrics",
    "_admit_jackal_comparison",
    "_admit_jackal_comparison_or_refusal",
    "_admit_cognitive_metric_report",
    "cognitive_honesty_gate",
    "_cognitive_git_environment",
    "_cognitive_git",
    "_cognitive_git_bytes",
    "_cognitive_loaded_source_paths",
    "_default_cognitive_config_validator",
    "capture_cognitive_runtime_inputs",
    "verify_cognitive_runtime_inputs",
    "clean_cognitive_checkout_identity",
    "verify_cognitive_checkout_identity",
    "publish_cognitive_artifacts",
    "_validate_cognitive_output_path",
    "_cognitive_json_bytes",
    "_cognitive_jsonl_bytes",
)

PROVISIONAL_CONSTANTS = (
    "MAX_COGNITIVE_EXECUTABLE_BYTES",
    "MAX_COGNITIVE_WORK_ITEMS",
    "MAX_COGNITIVE_JACKAL_CALLS",
    "COGNITIVE_MCP_PROTOCOL_REQUESTS",
    "MAX_COGNITIVE_MCP_REQUESTS",
    "MAX_COGNITIVE_RETAINED_BYTES",
    "COGNITIVE_RANKING_POLICY",
    "COGNITIVE_ABSTENTION_INPUT_FIELDS",
    "COGNITIVE_ARM_NAMES",
    "COGNITIVE_ARTIFACT_NAMES",
    "COGNITIVE_ANCESTRY_BY_ARM",
    "_COGNITIVE_RETRIEVAL_RULE",
    "COGNITIVE_HONESTY_RULES",
)


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _read(relative):
    with open(os.path.join(REPO, relative), encoding="utf-8") as stream:
        return stream.read()


class CognitiveRefusalBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.siabench = _load(
            "siabench_cognitive_refusal", os.path.join(BIN, "siabench.py"))

    def test_refusal_envelope_is_complete_and_canonical(self):
        with self.assertRaises(self.siabench.BenchmarkRefusal) as raised:
            self.siabench.run_cognitive("/unused")
        self.assertEqual(json.loads(str(raised.exception)), EXPECTED_REFUSAL)

    def test_refusal_template_is_private_immutable_canonical_text(self):
        self.assertFalse(hasattr(
            self.siabench, "COGNITIVE_VECTOR_BASELINE_REFUSAL"))
        encoded = self.siabench._COGNITIVE_VECTOR_BASELINE_REFUSAL_JSON
        self.assertIs(type(encoded), str)
        self.assertEqual(
            encoded,
            json.dumps(
                EXPECTED_REFUSAL, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False),
        )

    def test_refusal_precedes_all_benchmark_side_effects(self):
        with mock.patch.object(
                self.siabench, "build_ledger_dataset") as build, \
                mock.patch.object(self.siabench, "_engine") as query, \
                mock.patch.object(self.siabench, "_atomic_text") as publish, \
                mock.patch.object(
                    self.siabench.sialib, "corpus_owner") as owner:
            with self.assertRaises(self.siabench.BenchmarkRefusal):
                self.siabench.run_cognitive(object(), repo=object())
        build.assert_not_called()
        query.assert_not_called()
        publish.assert_not_called()
        owner.assert_not_called()

    def test_cognitive_cli_reports_the_structured_refusal(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            status = self.siabench.main(
                ["cognitive", "--out", "/tmp/fixture-cognitive-run"])
        self.assertEqual(status, 1)
        self.assertEqual(stdout.getvalue(), "")
        prefix = "REFUSED: "
        self.assertTrue(stderr.getvalue().startswith(prefix))
        self.assertEqual(
            json.loads(stderr.getvalue()[len(prefix):]), EXPECTED_REFUSAL)

    def test_cognitive_cli_without_output_path_reports_the_same_refusal(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            try:
                status = self.siabench.main(["cognitive"])
            except SystemExit as exc:
                self.fail(
                    "argparse intercepted the missing-request cognitive "
                    f"refusal with SystemExit {exc.code}")
        self.assertEqual(status, 1)
        self.assertEqual(stdout.getvalue(), "")
        prefix = "REFUSED: "
        self.assertTrue(stderr.getvalue().startswith(prefix))
        self.assertEqual(
            json.loads(stderr.getvalue()[len(prefix):]), EXPECTED_REFUSAL)

    def test_top_level_help_exposes_pinned_private_cognitive_command(self):
        help_text = _read("bin/sia")
        self.assertIn(
            "sia bench [run|generate|score|cognitive|legacy]", help_text)
        self.assertIn(
            "cognitive runs an externally pinned private raw-vector baseline",
            help_text,
        )

    def test_no_dormant_benchmark_scaffold_remains(self):
        for name in PROVISIONAL_HELPERS + PROVISIONAL_CONSTANTS:
            with self.subTest(name=name):
                self.assertFalse(hasattr(self.siabench, name))
        runner = inspect.getsource(self.siabench.run_cognitive)
        function = ast.parse(runner).body[0]
        # The obsolete single-Raise assertion encoded absence of a runner.
        # Keep the scaffold exclusions and require the concrete private
        # delegate instead; its behavior is exercised by command tests.
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
        delegates = [node for node in calls if isinstance(node.func, ast.Attribute)
                     and isinstance(node.func.value, ast.Name)
                     and node.func.value.id == "siacognitivecommand"]
        self.assertEqual([node.func.attr for node in delegates], ["run_command"])
        delegate = delegates[0]
        self.assertEqual([node.id for node in delegate.args], ["out_dir"])
        self.assertEqual([(item.arg, item.value.id) for item in delegate.keywords],
                         [("repo", "repo"), ("request_file", "request_file"),
                          ("request_sha256", "request_sha256")])
        forbidden = set(PROVISIONAL_HELPERS) | {"_engine", "_atomic_text", "build_ledger_dataset"}
        self.assertFalse([node for node in calls if isinstance(node.func, ast.Name)
                          and node.func.id in forbidden])
        translations = [node for node in calls if isinstance(node.func, ast.Name)
                        and node.func.id == "BenchmarkRefusal"]
        self.assertEqual([ast.unparse(node) for node in translations], ["BenchmarkRefusal(str(exc))"])
        self.assertIn("structured refusal", runner.lower())

    def test_signed_ledger_dataset_has_only_explicit_private_history_capture(self):
        parameters = inspect.signature(
            self.siabench.build_ledger_dataset).parameters
        self.assertEqual(list(parameters), [
            "corpus", "chain_registry", "chain_names", "cognitive_history"])
        self.assertIs(parameters["cognitive_history"].default, False)
        self.assertEqual(parameters["cognitive_history"].kind,
                         inspect.Parameter.KEYWORD_ONLY)
        self.assertNotIn("split_policy", parameters)
        source = inspect.getsource(self.siabench.build_ledger_dataset)
        function = ast.parse(source).body[0]
        capture = function.body[-2]
        self.assertIsInstance(capture, ast.If)
        self.assertIsInstance(capture.test, ast.Name)
        self.assertEqual(capture.test.id, "cognitive_history")
        self.assertEqual(capture.orelse, [])
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)
                 and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == "siacognitivehistory"]
        self.assertEqual([node.func.attr for node in calls], ["build_capture"])
        self.assertIn(calls[0], list(ast.walk(capture)))
        self.assertNotIn("cognitive-group-disjoint", source)


def _markdown_without_allowed_claim_contexts(text):
    """Remove sections explicitly labeled benchmark/history/reference."""
    kept = []
    allowed = False
    for line in text.splitlines():
        if line.startswith("#"):
            heading = line.lstrip("#").strip().casefold()
            allowed = any(token in heading for token in (
                "benchmark", "history", "historical", "reference", "credits"))
        if not allowed:
            kept.append(line)
    return "\n".join(kept)


def _without_required_brain_boundary(text):
    """Remove only the exact boundary, tolerating split QML line comments."""
    flat = " ".join(text.split())
    separator = r"(?:\s+//\s*|\s+)"
    pattern = separator.join(
        re.escape(token) for token in BRAIN_METAPHOR_BOUNDARY.split())
    return re.sub(pattern, "", flat)


def _brain_boundary_occurrences(text):
    """Count exact boundary text across prose and split line comments."""
    flat = " ".join(text.split())
    separator = r"(?:\s+//\s*|\s+)"
    pattern = separator.join(
        re.escape(token) for token in BRAIN_METAPHOR_BOUNDARY.split())
    return len(re.findall(pattern, flat))


class FirstContactClaimSurfaces(unittest.TestCase):
    def assert_boundary_near_first_claim(self, relative, claim, radius=4):
        lines = _read(relative).splitlines()
        claim_line = next(
            index for index, line in enumerate(lines) if claim in line)
        boundary_lines = []
        for index in range(len(lines)):
            nearby = " ".join(" ".join(lines[index:index + 4]).split())
            if BRAIN_METAPHOR_BOUNDARY in nearby:
                boundary_lines.append(index)
        self.assertTrue(
            any(abs(index - claim_line) <= radius for index in boundary_lines),
            f"{relative}: exact Brain-metaphor boundary is not adjacent to "
            f"the first-contact claim",
        )

    def test_markdown_titles_carry_the_exact_adjacent_boundary(self):
        for relative, claim in (
                ("README.md", "# SIA — the Omarchy Brain"),
                ("docs/MANUAL.md", "# SIA — The Omarchy Brain"),
                ("docs/WHITEPAPER.md", "# SIA:")):
            with self.subTest(path=relative):
                self.assert_boundary_near_first_claim(relative, claim)

    def test_every_changed_brain_boundary_surface_is_censused(self):
        expected_occurrences = {
            "Cockpit.qml": 3,
            "Model.js": 1,
            "Panel.qml": 2,
            "README.md": 1,
            "SECURITY.md": 1,
            "bin/sia": 1,
            "bin/sia-brainstem": 1,
            "bin/sia-mcp": 1,
            "bin/sialib.py": 2,
            "bin/siatakes.py": 1,
            "docs/CONTINUITY.md": 1,
            "docs/MANUAL.md": 1,
            "docs/WHITEPAPER.md": 1,
            "manifest.json": 1,
            "skill/SKILL.md": 1,
        }
        for relative, expected in expected_occurrences.items():
            with self.subTest(path=relative):
                self.assertEqual(
                    _brain_boundary_occurrences(_read(relative)), expected,
                    f"{relative}: exact Brain-boundary occurrence census "
                    "changed",
                )

    def test_bar_widget_description_carries_the_exact_boundary(self):
        # The top-level manifest description is the marketplace listing
        # paragraph and carries the product tagline instead; the boundary
        # rides every in-product surface a user actually reads on the
        # desktop — this description, the Panel tooltip, and the Cockpit.
        manifest = json.loads(_read("manifest.json"))
        self.assertIn(
            BRAIN_METAPHOR_BOUNDARY, manifest["barWidget"]["description"])
        self.assertNotIn(BRAIN_METAPHOR_BOUNDARY, manifest["description"])

    def test_panel_tooltip_always_carries_the_exact_boundary(self):
        panel = _read("Panel.qml")
        tooltip = panel.split("function tooltip()", 1)[1].split(
            "function applyStatus", 1)[0]
        self.assertIn(BRAIN_METAPHOR_BOUNDARY, tooltip)

    def test_every_panel_tooltip_branch_appends_the_boundary(self):
        panel = _read("Panel.qml")
        tooltip = panel.split("function tooltip()", 1)[1].split(
            "function applyStatus", 1)[0]
        markers = (
            'if (root.releaseLifecycle === "checking")',
            'if (root.releaseLifecycle === "setup")',
            'if (root.releaseLifecycle === "installing")',
            'if (root.releaseLifecycle === "repair")',
            'if (root.releaseLifecycle === "ahead")',
            'if (root.releaseLifecycle === "update")',
            'var brain = root.cockpitWorkspace',
        )
        starts = [tooltip.index(marker) for marker in markers]
        for index, marker in enumerate(markers):
            end = starts[index + 1] if index + 1 < len(starts) \
                else len(tooltip)
            branch = tooltip[starts[index]:end]
            with self.subTest(branch=marker):
                self.assertIn("return", branch)
                self.assertIn("brainBoundary", branch)

    def test_cockpit_header_carries_the_exact_adjacent_boundary(self):
        self.assert_boundary_near_first_claim(
            "Cockpit.qml", "SIA — THE OMARCHY BRAIN", radius=12)

    def test_unearned_names_are_absent_outside_labeled_evidence_contexts(self):
        patterns = {
            "ACT-R": r"\bACT-?R\b",
            "Hebbian": r"\bHebb(?:ian)?\b",
            "Global Workspace": r"\bGlobal(?:[- ]Neuronal)?[- ]Workspace\b",
            "HippoRAG": r"\bHippoRAG(?:-style)?\b",
            "spreading activation": r"\bspreading[- ]activation\b",
            "dopaminergic": r"\bdopamin(?:e|ergic)\b",
            "sleep/systems consolidation": (
                r"\bsystems consolidation\b|\bconsolidation\s*\(sleep\)|"
                r"\bsleep(?:-cycle)?\s+(?:systems\s+)?consolidation\b|"
                r"\bSleep turns episodes into knowledge\b|\bweekly gists?\b|"
                r"\bgist(?:-style)? consolidation\b"
            ),
            "conscious contents": r"\bconscious (?:contents?|slots?)\b",
            "neuro claim": (
                r"\bneuro(?:cognitive|science|scientific|nal|logical)?\b"
            ),
        }
        markdown = {"README.md", "docs/MANUAL.md", "docs/WHITEPAPER.md"}
        for relative in (
                "README.md", "docs/MANUAL.md", "docs/WHITEPAPER.md",
                "manifest.json", "Panel.qml", "Cockpit.qml"):
            text = _read(relative)
            if relative in markdown:
                text = _markdown_without_allowed_claim_contexts(text)
            text = _without_required_brain_boundary(text)
            for label, pattern in patterns.items():
                with self.subTest(path=relative, claim=label):
                    self.assertIsNone(
                        re.search(pattern, text, flags=re.IGNORECASE),
                        f"{relative}: unearned {label} claim remains outside a "
                        "clearly labeled benchmark/history/reference context",
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
