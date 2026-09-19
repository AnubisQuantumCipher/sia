#!/usr/bin/env python3
"""The associative rerank ships default-off by measurement (whitepaper §4.3).

On the extended 22-probe tripwire set (2026-09-02) the blend scored uniformly
below the unmodified hybrid query (slug match@5 0.86 vs 0.91, reciprocal slug rank
0.67 vs 0.71, match@1 0.50 vs 0.59), so `sia ask` applies graph influence only
when `retrieval.associative_rerank` is explicitly true. The nightly tripwire
keeps measuring the blend lane regardless of the flag, so the hypothesis stays
under instrumentation and can earn its default back with a measured win.
"""

import ast
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

try:
    import sia_test_home  # test-only import-time path isolation
except ModuleNotFoundError:
    from tests import sia_test_home  # type: ignore


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(REPO, "bin")
# Set in the child this file spawns to check its own direct execution, so
# the child does not spawn another one forever.
_DIRECT_SELFTEST_ENV = "SIA_RETRIEVAL_POLICY_DIRECT_SELFTEST"


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AssociativeRerankPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sialib = _load(
            "sialib_rerank_policy_test", os.path.join(BIN, "sialib.py"))

    def test_default_is_off(self):
        for config in ({}, {"retrieval": {}},
                       {"retrieval": {"associative_rerank": False}}):
            self.assertFalse(
                self.sialib.associative_rerank_enabled(config=config), config)

    def test_explicit_true_enables(self):
        self.assertTrue(self.sialib.associative_rerank_enabled(
            config={"retrieval": {"associative_rerank": True}}))
        self.assertTrue(self.sialib.associative_rerank_enabled(config={
            "retrieval": {
                "_comment": "documented opt-in",
                "associative_rerank": True,
            },
        }))

    def test_nonbool_and_malformed_never_enable(self):
        for bad in ({"retrieval": {"associative_rerank": "true"}},
                    {"retrieval": {"associative_rerank": 1}},
                    {"retrieval": {"associative_rerank": True,
                                   "mystery": 1}},
                    {"retrieval": {"associative_rerank": True,
                                   "_comment": ["not", "text"]}},
                    {"retrieval": "on"},
                    {"retrieval": None},
                    []):
            self.assertFalse(
                self.sialib.associative_rerank_enabled(config=bad), bad)

    def test_shipped_example_is_accepted_without_config_errors(self):
        old_path = self.sialib.CONFIG_PATH
        old_errors = list(self.sialib.CONFIG_ERRORS)
        with tempfile.TemporaryDirectory() as root:
            self.sialib.CONFIG_PATH = os.path.join(root, "config.json")
            with open(os.path.join(REPO, "config.example.json"),
                      encoding="utf-8") as source, open(
                          self.sialib.CONFIG_PATH, "w",
                          encoding="utf-8") as target:
                target.write(source.read())
            try:
                loaded = self.sialib.load_config()
                self.assertEqual(self.sialib.CONFIG_ERRORS, [])
                self.assertFalse(
                    self.sialib.associative_rerank_enabled(config=loaded))
            finally:
                self.sialib.CONFIG_PATH = old_path
                self.sialib.CONFIG_ERRORS[:] = old_errors

    def test_load_config_flags_malformed_retrieval(self):
        # load_config records named errors for malformed retrieval blocks; the
        # helper then still fails closed to off (asserted above).
        recorded = []
        original = self.sialib._record_config_error
        self.sialib._record_config_error = recorded.append
        try:
            path = self.sialib.CONFIG_PATH
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as stream:
                json.dump({"retrieval": {"associative_rerank": "yes",
                                         "mystery": 1}}, stream)
            loaded = self.sialib.load_config()
        finally:
            self.sialib._record_config_error = original
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        self.assertIn("retrieval-unknown-key", recorded)
        self.assertIn("retrieval-associative-rerank-must-be-bool", recorded)
        self.assertFalse(
            self.sialib.associative_rerank_enabled(config=loaded))


class RehearsalEfficacyPartition(unittest.TestCase):
    """ROADMAP P1.3: the partition is pure, descriptive, and population-honest."""

    @classmethod
    def setUpClass(cls):
        cls.siabench = _load(
            "siabench_efficacy_test", os.path.join(BIN, "siabench.py"))

    def test_partitions_by_acceptor_fragment_overlap(self):
        results = [
            ("q1", ["events/journal"], 1),      # rehearsed family, hit
            ("q2", ["events/pacman"], None),    # unrehearsed family, miss
            ("q3", ["events/jackal"], None),    # rehearsed family, miss
            ("q4", ["organs/custos"], 2),       # unrehearsed family, hit
        ]
        reps = {"events/journal/2026-08-31": 1,
                "events/jackal/2026-08-31": 1,
                "events/sekhmet/2026-08-30": 0}
        report = self.siabench.rehearsal_efficacy_partition(results, reps)
        self.assertEqual(report["rehearsed"],
                         {"probes": 2, "hits": 1, "hit_rate": 0.5})
        self.assertEqual(report["unrehearsed"],
                         {"probes": 2, "hits": 1, "hit_rate": 0.5})
        self.assertTrue(any("no significance" in line
                            for line in report["non_claims"]))

    def test_empty_population_reports_none_not_zero(self):
        report = self.siabench.rehearsal_efficacy_partition(
            [("q", ["events/x"], 1)], {})
        self.assertIsNone(report["rehearsed"]["hit_rate"])
        self.assertEqual(report["rehearsed"]["probes"], 0)


class AskHonorsRerankDefault(unittest.TestCase):
    """With the flag off (default), `sia ask` must not consult graph or mind
    and must label the mode in the truth-boundary footer."""

    def test_default_off_skips_graph_and_labels_footer(self):
        import contextlib
        import io
        import json as _json
        import sys
        import types
        from unittest import mock
        sia = _load("sia_cli_rerank_test", os.path.join(BIN, "sia"))
        result = types.SimpleNamespace(
            returncode=0,
            stdout=_json.dumps([{"slug": "events/x/day", "score": 1,
                                 "type": "event-day", "title": "x",
                                 "chunk_text": "y"}]),
            stderr="")
        mind = sys.modules["siamind"]
        output = io.StringIO()
        with mock.patch.object(sia, "_gbrain_query", return_value=result), \
                mock.patch.object(sia.sialib, "corpus_origin",
                                  return_value="evidence"), \
                mock.patch.object(
                    sia.sialib, "read_json",
                    side_effect=AssertionError("graph must not be read")), \
                mock.patch.object(
                    mind, "load_mind",
                    side_effect=AssertionError("mind must not be loaded")), \
                mock.patch.object(sia, "_health_footer",
                                  side_effect=lambda **kwargs:
                                  "boundary: " + kwargs.get(
                                      "recall_degraded", "")), \
                contextlib.redirect_stdout(output):
            self.assertEqual(sia.cmd_ask("memory", touch=False), 0)
        rendered = output.getvalue()
        self.assertIn("off by measured default", rendered)
        self.assertIn("[evidence] events/x/day", rendered)


class DirectExecutionRunsEveryCase(unittest.TestCase):
    """The __main__ block must sit below every TestCase in this file.

    Incident: the block was written directly under AssociativeRerankPolicy,
    above RehearsalEfficacyPartition and AskHonorsRerankDefault.  Running
    `python3 tests/test_retrieval_policy.py` therefore called
    unittest.main() while those two classes did not yet exist, graded the
    four cases defined so far, and exited 0 — a green run that had silently
    skipped the rest.  Only the `python3 -m unittest` lane ever saw them.
    """

    def test_main_block_is_the_last_top_level_statement(self):
        with open(os.path.abspath(__file__), encoding="utf-8") as stream:
            tree = ast.parse(stream.read())
        guards = [(index, node) for index, node in enumerate(tree.body)
                  if isinstance(node, ast.If)
                  and "__main__" in ast.dump(node.test)]
        self.assertEqual(len(guards), 1, "expected one __main__ guard")
        index, _node = guards[0]
        self.assertEqual(index, len(tree.body) - 1,
                         "__main__ guard must be the last statement")

    def test_direct_execution_collects_every_class(self):
        # The inner run executes this file again, so it must not spawn a
        # third: the env flag makes the child skip this case only.
        if os.environ.get(_DIRECT_SELFTEST_ENV):
            self.skipTest("inner run spawned by the direct-execution guard")
        environment = dict(os.environ)
        environment[_DIRECT_SELFTEST_ENV] = "1"
        completed = subprocess.run(
            [sys.executable, os.path.abspath(__file__)],
            capture_output=True, text=True, env=environment, cwd=REPO,
            timeout=300)
        report = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, report)
        for name in ("AssociativeRerankPolicy",
                     "RehearsalEfficacyPartition",
                     "AskHonorsRerankDefault"):
            self.assertIn(name, report, report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
